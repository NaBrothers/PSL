#!/usr/bin/env python3
"""Summarize sequence tempo and team shape from a Rust engine_v2 match."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACE_STAT_KEYS = (
    "goals",
    "xg",
    "shots",
    "shots_in_box",
    "shots_outside_box",
    "passes",
    "passes_completed",
    "pass_success_rate",
    "possession",
    "carries",
    "clearances",
    "pressures",
    "tackle_attempts",
    "take_ons",
)


def _distance(left: list[float], right: list[float]) -> float:
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def _classify_pass(origin: list[float], target: list[float], attacking_right: bool) -> str:
    direction = target[0] - origin[0]
    if not attacking_right:
        direction *= -1.0
    if direction > 3.0:
        return "forward"
    if direction < -3.0:
        return "backward"
    return "lateral"


def _event_attacking_right(event: dict[str, Any], home_attacking_right: bool) -> bool:
    team = event.get("team_side")
    attacking_right = home_attacking_right if team == "home" else not home_attacking_right
    if event.get("half") == 2:
        attacking_right = not attacking_right
    return attacking_right


def _attacking_progress(
    position: list[float],
    attacking_right: bool,
    pitch_length: float = 105.0,
) -> float:
    return position[0] / pitch_length if attacking_right else 1.0 - position[0] / pitch_length


def _relative_width(position: list[float], pitch_width: float = 68.0) -> float:
    return abs(position[1] - pitch_width / 2.0) / (pitch_width / 2.0)


def _is_wide_final_third(position: list[float], attacking_right: bool) -> bool:
    return _attacking_progress(position, attacking_right) >= 0.72 and _relative_width(position) >= 0.48


def _is_byline_wide(position: list[float], attacking_right: bool) -> bool:
    return _attacking_progress(position, attacking_right) >= 0.86 and _relative_width(position) >= 0.50


def _is_central_box(position: list[float], attacking_right: bool) -> bool:
    return _attacking_progress(position, attacking_right) >= 0.84 and _relative_width(position) <= 0.45


def _is_strict_cutback(
    origin: list[float],
    target: list[float],
    attacking_right: bool,
) -> bool:
    progress_delta = (
        (target[0] - origin[0]) if attacking_right else (origin[0] - target[0])
    )
    inward_distance = abs(origin[1] - 34.0) - abs(target[1] - 34.0)
    return (
        _is_byline_wide(origin, attacking_right)
        and progress_delta <= -2.5
        and inward_distance >= 0.16 * (68.0 / 2.0)
        and _attacking_progress(target, attacking_right) >= 0.84
        and _relative_width(target) <= 0.60
    )


def _action_origin(event: dict[str, Any]) -> list[float] | None:
    origin = event.get("origin")
    return origin if isinstance(origin, list) and len(origin) == 2 else None


def _action_target(event: dict[str, Any]) -> list[float] | None:
    target = event.get("target")
    return target if isinstance(target, list) and len(target) == 2 else None


def _group_possessions(
    events: Iterable[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        possession_id = event.get("possession_id")
        if isinstance(possession_id, int):
            grouped[possession_id].append(event)
    return grouped


def _terminal_cause(
    event: dict[str, Any],
    previous_event: dict[str, Any] | None = None,
) -> str:
    event_type = str(event.get("event_type", "unknown"))
    outcome = str(event.get("outcome", "unknown"))
    tags = event.get("tags")
    if not isinstance(tags, list):
        tags = []
    if event_type == "recovery":
        if previous_event is None:
            return "recovery:unknown"
        previous_type = str(previous_event.get("event_type", "unknown"))
        previous_outcome = str(previous_event.get("outcome", "unknown"))
        return f"recovery:after_{previous_type}_{previous_outcome}"
    if event_type == "interception":
        subtype = (
            "delivery_error"
            if "delivery_error" in tags
            else "arrival"
            if "arrival_interception" in tags
            else "other"
        )
        return f"interception:{subtype}"
    if event_type in {"tackle", "duel"}:
        context = "pass_release" if "pass_release" in tags else "carry"
        return f"{event_type}:{context}:{outcome}"
    if event_type in {"pass", "carry", "clearance", "shot", "restart", "offside"}:
        return f"{event_type}:{outcome}"
    return f"{event_type}:{outcome}"


def _attack_pattern_summary(
    events: Iterable[dict[str, Any]],
    home_attacking_right: bool,
) -> dict[str, Any]:
    action_types = ("carry", "pass", "shot")
    byline_exit_types = ("carry", "other_pass", "strict_cutback", "shot", "none")
    shot_regions = ("central_box", "byline_wide", "wide_final_third", "outside")
    completed_actions: Counter[str] = Counter()
    wide_final_origin_actions: Counter[str] = Counter()
    byline_entry_types: Counter[str] = Counter()
    byline_exit_actions: Counter[str] = Counter()
    shot_origin_regions: Counter[str] = Counter()
    event_list = list(events)
    grouped = _group_possessions(event_list)
    strict_cutbacks: list[dict[str, Any]] = []
    wide_final_entries = 0

    for event in event_list:
        event_type = event.get("event_type")
        origin = _action_origin(event)
        target = _action_target(event)
        if event_type not in action_types or origin is None:
            continue
        attacking_right = _event_attacking_right(event, home_attacking_right)
        if event_type == "shot" and event.get("outcome") == "mishit":
            continue
        if event_type != "shot" and event.get("outcome") != "completed":
            continue
        completed_actions[event_type] += 1
        if _is_wide_final_third(origin, attacking_right):
            wide_final_origin_actions[event_type] += 1
        if event_type in {"carry", "pass"} and target is not None:
            target_wide_final = _is_wide_final_third(target, attacking_right)
            if target_wide_final and not _is_wide_final_third(origin, attacking_right):
                wide_final_entries += 1
            if _is_byline_wide(target, attacking_right) and not _is_byline_wide(
                origin, attacking_right
            ):
                byline_entry_types[event_type] += 1
            if event_type == "pass" and _is_strict_cutback(origin, target, attacking_right):
                strict_cutbacks.append(event)
        if event_type == "shot":
            if _is_byline_wide(origin, attacking_right):
                shot_origin_regions["byline_wide"] += 1
            elif _is_central_box(origin, attacking_right):
                shot_origin_regions["central_box"] += 1
            elif _is_wide_final_third(origin, attacking_right):
                shot_origin_regions["wide_final_third"] += 1
            else:
                shot_origin_regions["outside"] += 1

    byline_episode_count = 0
    byline_episodes_with_later_shot = 0
    byline_episodes_with_immediate_shot = 0
    shots_after_byline_in_possession = 0
    strict_cutback_immediate_shots = 0
    wide_possession_count = 0
    wide_possession_shots = 0

    for sequence_events in grouped.values():
        ordered = sorted(sequence_events, key=lambda event: (event["tick"], event["seq"]))
        action_events = [
            event
            for event in ordered
            if event.get("event_type") in action_types
            and _action_origin(event) is not None
            and (
                event.get("event_type") == "shot"
                or event.get("outcome") == "completed"
            )
        ]
        if not action_events:
            continue

        has_wide_final = False
        first_byline_index: int | None = None
        for index, event in enumerate(action_events):
            attacking_right = _event_attacking_right(event, home_attacking_right)
            origin = _action_origin(event)
            target = _action_target(event)
            if origin is None:
                continue
            has_wide_final = has_wide_final or _is_wide_final_third(origin, attacking_right)
            has_wide_final = has_wide_final or (
                target is not None and _is_wide_final_third(target, attacking_right)
            )
            if first_byline_index is None and (
                _is_byline_wide(origin, attacking_right)
                or (
                    target is not None
                    and event.get("event_type") in {"carry", "pass"}
                    and _is_byline_wide(target, attacking_right)
                )
            ):
                first_byline_index = index

        shots = [event for event in action_events if event.get("event_type") == "shot"]
        if has_wide_final:
            wide_possession_count += 1
            wide_possession_shots += int(bool(shots))
        if first_byline_index is None:
            continue

        byline_episode_count += 1
        byline_event = action_events[first_byline_index]
        later_actions = action_events[first_byline_index + 1 :]
        later_shots = [
            event for event in later_actions if event.get("event_type") == "shot"
        ]
        if later_shots:
            byline_episodes_with_later_shot += 1
            shots_after_byline_in_possession += len(later_shots)
        if any(
            int(shot["tick"]) - int(byline_event["tick"]) <= 8
            for shot in later_shots
        ):
            byline_episodes_with_immediate_shot += 1

        if not later_actions:
            byline_exit_actions["none"] += 1
            continue
        exit_action = later_actions[0]
        if exit_action.get("event_type") == "carry":
            byline_exit_actions["carry"] += 1
        elif exit_action.get("event_type") == "shot":
            byline_exit_actions["shot"] += 1
        else:
            origin = _action_origin(exit_action)
            target = _action_target(exit_action)
            attacking_right = _event_attacking_right(exit_action, home_attacking_right)
            if (
                origin is not None
                and target is not None
                and _is_strict_cutback(origin, target, attacking_right)
            ):
                byline_exit_actions["strict_cutback"] += 1
            else:
                byline_exit_actions["other_pass"] += 1

    for cutback in strict_cutbacks:
        sequence_events = grouped[int(cutback["possession_id"])]
        if any(
            event.get("event_type") == "shot"
            and 0 <= int(event["tick"]) - int(cutback["tick"]) <= 8
            for event in sequence_events
        ):
            strict_cutback_immediate_shots += 1

    return {
        "completed_actions": {
            action_type: completed_actions[action_type] for action_type in action_types
        },
        "wide_final_third_origin_actions": {
            action_type: wide_final_origin_actions[action_type] for action_type in action_types
        },
        "wide_final_third_entries": wide_final_entries,
        "byline_entries": {
            "total": sum(byline_entry_types.values()),
            **{action_type: byline_entry_types[action_type] for action_type in ("carry", "pass")},
        },
        "byline_episodes": {
            "count": byline_episode_count,
            "next_action": {
                action_type: byline_exit_actions[action_type]
                for action_type in byline_exit_types
            },
            "with_later_shot": byline_episodes_with_later_shot,
            "with_shot_within_8_ticks": byline_episodes_with_immediate_shot,
        },
        "strict_cutbacks": {
            "completed": len(strict_cutbacks),
            "with_shot_within_8_ticks": strict_cutback_immediate_shots,
        },
        "shots_after_byline_in_possession": shots_after_byline_in_possession,
        "shot_origin_regions": {
            region: shot_origin_regions[region] for region in shot_regions
        },
        "wide_possessions": {
            "count": wide_possession_count,
            "with_shot": wide_possession_shots,
        },
    }


def _event_has_tag(event: dict[str, Any], tag: str) -> bool:
    tags = event.get("tags")
    return isinstance(tags, list) and tag in tags


def _pass_causality_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    released_by_team: Counter[str] = Counter()
    completed_by_team: Counter[str] = Counter()
    released_outcomes: Counter[str] = Counter()
    released_failures: Counter[str] = Counter()
    release_duels: Counter[str] = Counter()
    release_duel_wins: Counter[str] = Counter()

    for event in events:
        team = event.get("team_side")
        if team not in {"home", "away"}:
            continue
        event_type = event.get("event_type")
        outcome = event.get("outcome")
        if event_type == "pass":
            released_by_team[team] += 1
            released_outcomes[str(outcome)] += 1
            if outcome == "completed":
                completed_by_team[team] += 1
                continue
            if outcome == "first_touch_error":
                cause = "first_touch_error"
            elif outcome == "offside":
                cause = "offside"
            elif outcome == "loose":
                cause = (
                    "delivery_error_loose"
                    if _event_has_tag(event, "delivery_error")
                    else "arrival_loose"
                )
            else:
                cause = f"other_{outcome}"
            released_failures[cause] += 1
        elif event_type == "interception":
            passer_team = "away" if team == "home" else "home"
            released_by_team[passer_team] += 1
            released_outcomes["intercepted"] += 1
            cause = (
                "delivery_error_interception"
                if _event_has_tag(event, "delivery_error")
                else "arrival_interception"
            )
            released_failures[cause] += 1
        elif event_type == "tackle" and _event_has_tag(event, "pass_release"):
            release_duels["attempts"] += 1
            if outcome == "won":
                release_duel_wins["won"] += 1
        elif event_type == "duel" and _event_has_tag(event, "pass_release"):
            release_duels["attempts"] += 1

    released_total = sum(released_by_team.values())
    completed_total = sum(completed_by_team.values())
    failed_total = sum(released_failures.values())
    return {
        "released": {
            "total": released_total,
            "home": released_by_team["home"],
            "away": released_by_team["away"],
        },
        "completed": completed_total,
        "completion_rate": round(completed_total / max(released_total, 1), 4),
        "outcomes": dict(sorted(released_outcomes.items())),
        "failure_causes": {
            cause: {
                "count": count,
                "share_of_released": round(count / max(released_total, 1), 4),
                "share_of_failed": round(count / max(failed_total, 1), 4),
            }
            for cause, count in sorted(released_failures.items())
        },
        "pass_release_duels": {
            "attempts": release_duels["attempts"],
            "tackles_won": release_duel_wins["won"],
            "win_rate": round(
                release_duel_wins["won"] / max(release_duels["attempts"], 1), 4
            ),
        },
    }


def _sequence_summary(
    events: Iterable[dict[str, Any]],
    home_attacking_right: bool,
    include_sequences: bool = False,
) -> dict[str, Any]:
    grouped = _group_possessions(events)

    sequences = []
    pass_directions: Counter[str] = Counter()
    terminal_events: Counter[str] = Counter()
    terminal_causes: Counter[str] = Counter()
    terminal_events_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    terminal_causes_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    pass_count_bands: Counter[str] = Counter()
    shots_by_pass_count: list[int] = []
    possession_ids = sorted(grouped)
    for possession_index, possession_id in enumerate(possession_ids):
        sequence_events = grouped[possession_id]
        ordered = sorted(sequence_events, key=lambda event: (event["tick"], event["seq"]))
        team = next(
            (
                str(event["team_side"])
                for event in ordered
                if event.get("team_side") in {"home", "away"}
                and event.get("event_type") in {"carry", "pass", "shot", "clearance", "restart"}
            ),
            str(ordered[0].get("team_side", "unknown")),
        )
        passes = [
            event
            for event in ordered
            if event["event_type"] == "pass"
            and event.get("outcome") == "completed"
            and event.get("team_side") == team
        ]
        for event in passes:
            origin = event.get("origin")
            target = event.get("target")
            if isinstance(origin, list) and isinstance(target, list):
                pass_directions[_classify_pass(origin, target, team == "home" and home_attacking_right or team == "away" and not home_attacking_right)] += 1
        terminal_event = ordered[-1]
        terminal = terminal_event["event_type"]
        terminal_cause = _terminal_cause(
            terminal_event,
            ordered[-2] if len(ordered) >= 2 else None,
        )
        if terminal_event.get("outcome") == "completed" and terminal in {"pass", "carry"}:
            if possession_index + 1 >= len(possession_ids):
                terminal_cause = f"match_end:after_{terminal}"
            else:
                next_events = sorted(
                    grouped[possession_ids[possession_index + 1]],
                    key=lambda event: (event["tick"], event["seq"]),
                )
                if next_events and next_events[0].get("half") != terminal_event.get("half"):
                    terminal_cause = f"period_end:after_{terminal}"
                else:
                    terminal_cause = f"unlogged_control_change:after_{terminal}"
        terminal_events[terminal] += 1
        terminal_causes[terminal_cause] += 1
        pass_band = "0" if not passes else "1" if len(passes) == 1 else "2-4" if len(passes) <= 4 else "5+"
        pass_count_bands[pass_band] += 1
        terminal_events_by_pass_band[pass_band][terminal] += 1
        terminal_causes_by_pass_band[pass_band][terminal_cause] += 1
        shot = next(
            (
                event
                for event in ordered
                if event["event_type"] == "shot" and event.get("outcome") != "mishit"
            ),
            None,
        )
        if shot is not None:
            shots_by_pass_count.append(len(passes))
        sequences.append(
            {
                "team": team,
                "possession_id": possession_id,
                "duration_seconds": max(0, ordered[-1]["match_second"] - ordered[0]["match_second"]),
                "passes": len(passes),
                "ended_in_shot": shot is not None,
                "terminal_event": terminal,
                "terminal_cause": terminal_cause,
            }
        )

    pass_total = sum(pass_directions.values())
    summary = {
        "sequence_count": len(sequences),
        "median_duration_seconds": round(median([sequence["duration_seconds"] for sequence in sequences]), 2)
        if sequences
        else 0.0,
        "p90_duration_seconds": round(
            _quantile([sequence["duration_seconds"] for sequence in sequences], 0.90), 2
        ),
        "median_completed_passes": round(median([sequence["passes"] for sequence in sequences]), 2)
        if sequences
        else 0.0,
        "p90_completed_passes": round(
            _quantile([sequence["passes"] for sequence in sequences], 0.90), 2
        ),
        "shot_sequence_rate": round(
            sum(sequence["ended_in_shot"] for sequence in sequences) / max(len(sequences), 1),
            4,
        ),
        "median_completed_passes_before_shot": round(median(shots_by_pass_count), 2)
        if shots_by_pass_count
        else 0.0,
        "pass_directions": {
            direction: {
                "count": count,
                "share": round(count / max(pass_total, 1), 4),
            }
            for direction, count in sorted(pass_directions.items())
        },
        "terminal_events": dict(sorted(terminal_events.items())),
        "terminal_causes": dict(sorted(terminal_causes.items())),
        "pass_count_bands": {
            band: {
                "count": pass_count_bands[band],
                "share": round(pass_count_bands[band] / max(len(sequences), 1), 4),
                "terminal_events": dict(sorted(terminal_events_by_pass_band[band].items())),
                "terminal_causes": dict(sorted(terminal_causes_by_pass_band[band].items())),
            }
            for band in ("0", "1", "2-4", "5+")
        },
    }
    if include_sequences:
        summary["sequences"] = sequences
    return summary


def _shape_summary(replay: Iterable[dict[str, Any]]) -> dict[str, Any]:
    width_by_team: dict[str, list[float]] = defaultdict(list)
    depth_by_team: dict[str, list[float]] = defaultdict(list)
    nearest_by_team: dict[str, list[float]] = defaultdict(list)
    crowd_by_team: dict[str, list[int]] = defaultdict(list)
    for frame in replay:
        if frame.get("type") != "frame":
            continue
        for team in ("home", "away"):
            positions = frame.get(team)
            if not isinstance(positions, list) or len(positions) < 2:
                continue
            outfield = positions[1:]
            xs = [position[0] for position in outfield]
            ys = [position[1] for position in outfield]
            width_by_team[team].append(max(ys) - min(ys))
            depth_by_team[team].append(max(xs) - min(xs))
            nearest_distances = []
            crowded_players = 0
            for index, position in enumerate(outfield):
                nearest = min(
                    _distance(position, other)
                    for other_index, other in enumerate(outfield)
                    if other_index != index
                )
                nearest_distances.append(nearest)
                if nearest < 5.0:
                    crowded_players += 1
            nearest_by_team[team].append(sum(nearest_distances) / len(nearest_distances))
            crowd_by_team[team].append(crowded_players)

    return {
        team: {
            "median_width_m": round(median(width_by_team[team]), 2) if width_by_team[team] else 0.0,
            "p10_width_m": round(_quantile(width_by_team[team], 0.10), 2),
            "median_depth_m": round(median(depth_by_team[team]), 2) if depth_by_team[team] else 0.0,
            "p10_depth_m": round(_quantile(depth_by_team[team], 0.10), 2),
            "median_nearest_teammate_m": round(median(nearest_by_team[team]), 2)
            if nearest_by_team[team]
            else 0.0,
            "p90_players_within_5m_of_teammate": round(_quantile(crowd_by_team[team], 0.90), 2),
        }
        for team in ("home", "away")
    }


def summarize_match(
    response: dict[str, Any],
    home_attacking_right: bool = True,
    include_sequences: bool = False,
) -> dict[str, Any]:
    events = response["events"]
    return {
        "score": [response["home_score"], response["away_score"]],
        "home_stats": response["home_stats"],
        "away_stats": response["away_stats"],
        "pass_causality": _pass_causality_summary(events),
        "sequence": _sequence_summary(events, home_attacking_right, include_sequences),
        "attack_patterns": _attack_pattern_summary(events, home_attacking_right),
        "shape": _shape_summary(response["replay"]),
    }


def _build_cards(db: Any, qq: int) -> tuple[list[dict[str, Any]], str]:
    from psl_core.card import get_color_code
    from psl_core.constants import STARS
    from server.services.bag import BagService
    from server.services.squad import SquadService

    squad = SquadService(db).get_squad(qq)
    if any(card is None for card in squad.cards):
        raise RuntimeError(f"user {qq} does not have a complete starting squad")
    bag = BagService(db)
    cards = []
    for card_info in squad.cards:
        detail = bag.get_card_detail(card_info.id, qq)
        cards.append(
            {
                "name": card_info.name,
                "player_id": card_info.player_id,
                "position": card_info.position,
                "color": get_color_code(
                    card_info.overall - STARS[card_info.star]["ability"],
                    card_info.star,
                ),
                "overall": card_info.real_overall,
                "abilities": {
                    key: value["value"] for key, value in detail["abilities"].items()
                },
            }
        )
    return cards, squad.formation


def _runtime_config_summary(config: Any) -> dict[str, Any]:
    payload = config.to_rust_payload()
    return {
        key: value
        for key, value in payload.items()
        if not key.startswith("runner_")
        and key not in {"rng_trace", "trace_detail", "trace_top_k"}
    }


def _aggregate_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        return {}

    direction_counts: Counter[str] = Counter()
    terminal_events: Counter[str] = Counter()
    terminal_causes: Counter[str] = Counter()
    pass_count_bands: Counter[str] = Counter()
    terminal_events_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    terminal_causes_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    completed_attack_actions: Counter[str] = Counter()
    pass_outcomes: Counter[str] = Counter()
    pass_failure_causes: Counter[str] = Counter()
    pass_release_duel_attempts = 0
    pass_release_duel_wins = 0
    wide_final_origin_actions: Counter[str] = Counter()
    byline_entry_types: Counter[str] = Counter()
    byline_exit_actions: Counter[str] = Counter()
    shot_origin_regions: Counter[str] = Counter()
    attack_totals: Counter[str] = Counter()
    for summary in summaries:
        for direction, data in summary["sequence"]["pass_directions"].items():
            direction_counts[direction] += data["count"]
        terminal_events.update(summary["sequence"]["terminal_events"])
        terminal_causes.update(summary["sequence"]["terminal_causes"])
        for band, data in summary["sequence"]["pass_count_bands"].items():
            pass_count_bands[band] += data["count"]
            terminal_events_by_pass_band[band].update(data["terminal_events"])
            terminal_causes_by_pass_band[band].update(data["terminal_causes"])
        causality = summary["pass_causality"]
        pass_outcomes.update(causality["outcomes"])
        pass_failure_causes.update(
            {
                cause: data["count"]
                for cause, data in causality["failure_causes"].items()
            }
        )
        pass_release_duel_attempts += causality["pass_release_duels"]["attempts"]
        pass_release_duel_wins += causality["pass_release_duels"]["tackles_won"]
        attack = summary["attack_patterns"]
        completed_attack_actions.update(attack["completed_actions"])
        wide_final_origin_actions.update(attack["wide_final_third_origin_actions"])
        byline_entry_types.update(
            {
                action_type: count
                for action_type, count in attack["byline_entries"].items()
                if action_type != "total"
            }
        )
        byline_exit_actions.update(attack["byline_episodes"]["next_action"])
        shot_origin_regions.update(attack["shot_origin_regions"])
        attack_totals["wide_final_third_entries"] += attack["wide_final_third_entries"]
        attack_totals["byline_entries"] += attack["byline_entries"]["total"]
        attack_totals["byline_episodes"] += attack["byline_episodes"]["count"]
        attack_totals["byline_episodes_with_later_shot"] += attack["byline_episodes"][
            "with_later_shot"
        ]
        attack_totals["byline_episodes_with_shot_within_8_ticks"] += attack[
            "byline_episodes"
        ]["with_shot_within_8_ticks"]
        attack_totals["strict_cutbacks"] += attack["strict_cutbacks"]["completed"]
        attack_totals["strict_cutbacks_with_shot_within_8_ticks"] += attack[
            "strict_cutbacks"
        ]["with_shot_within_8_ticks"]
        attack_totals["shots_after_byline_in_possession"] += attack[
            "shots_after_byline_in_possession"
        ]
        attack_totals["wide_possessions"] += attack["wide_possessions"]["count"]
        attack_totals["wide_possessions_with_shot"] += attack["wide_possessions"]["with_shot"]
    direction_total = sum(direction_counts.values())
    completed_attack_total = sum(completed_attack_actions.values())
    shot_origin_total = sum(shot_origin_regions.values())

    def average(path: tuple[str, ...]) -> float:
        values = []
        for summary in summaries:
            value: Any = summary
            for key in path:
                value = value[key]
            values.append(float(value))
        return round(mean(values), 3)

    return {
        "average_score": {
            "home": round(mean(float(summary["score"][0]) for summary in summaries), 3),
            "away": round(mean(float(summary["score"][1]) for summary in summaries), 3),
        },
        "average_home_stats": {
            key: round(mean(float(summary["home_stats"][key]) for summary in summaries), 3)
            for key in PACE_STAT_KEYS
        },
        "average_away_stats": {
            key: round(mean(float(summary["away_stats"][key]) for summary in summaries), 3)
            for key in PACE_STAT_KEYS
        },
        "pass_causality": {
            "average_released": round(
                mean(float(summary["pass_causality"]["released"]["total"]) for summary in summaries),
                3,
            ),
            "average_completion_rate": round(
                mean(float(summary["pass_causality"]["completion_rate"]) for summary in summaries),
                4,
            ),
            "outcomes": dict(sorted(pass_outcomes.items())),
            "failure_causes": {
                cause: {
                    "count": count,
                    "share_of_released": round(
                        count
                        / max(
                            sum(
                                summary["pass_causality"]["released"]["total"]
                                for summary in summaries
                            ),
                            1,
                        ),
                        4,
                    ),
                }
                for cause, count in sorted(pass_failure_causes.items())
            },
            "pass_release_duels": {
                "attempts": pass_release_duel_attempts,
                "tackles_won": pass_release_duel_wins,
                "win_rate": round(
                    pass_release_duel_wins / max(pass_release_duel_attempts, 1),
                    4,
                ),
            },
        },
        "sequence": {
            "average_count": average(("sequence", "sequence_count")),
            "median_duration_seconds": average(("sequence", "median_duration_seconds")),
            "p90_duration_seconds": average(("sequence", "p90_duration_seconds")),
            "median_completed_passes": average(("sequence", "median_completed_passes")),
            "p90_completed_passes": average(("sequence", "p90_completed_passes")),
            "shot_sequence_rate": average(("sequence", "shot_sequence_rate")),
            "median_completed_passes_before_shot": average(
                ("sequence", "median_completed_passes_before_shot")
            ),
            "pass_directions": {
                direction: {
                    "count": count,
                    "share": round(count / max(direction_total, 1), 4),
                }
                for direction, count in sorted(direction_counts.items())
            },
            "terminal_events": dict(sorted(terminal_events.items())),
            "terminal_causes": dict(sorted(terminal_causes.items())),
            "pass_count_bands": {
                band: {
                    "count": pass_count_bands[band],
                    "share": round(
                        pass_count_bands[band] / max(sum(pass_count_bands.values()), 1),
                        4,
                    ),
                    "terminal_events": dict(
                        sorted(terminal_events_by_pass_band[band].items())
                    ),
                    "terminal_causes": dict(
                        sorted(terminal_causes_by_pass_band[band].items())
                    ),
                }
                for band in ("0", "1", "2-4", "5+")
            },
        },
        "attack_patterns": {
            "completed_actions": dict(sorted(completed_attack_actions.items())),
            "wide_final_third_origin_actions": dict(
                sorted(wide_final_origin_actions.items())
            ),
            "wide_final_third_entries": attack_totals["wide_final_third_entries"],
            "byline_entries": {
                "total": attack_totals["byline_entries"],
                **dict(sorted(byline_entry_types.items())),
                "share_of_wide_final_third_entries": round(
                    attack_totals["byline_entries"]
                    / max(attack_totals["wide_final_third_entries"], 1),
                    4,
                ),
            },
            "byline_episodes": {
                "count": attack_totals["byline_episodes"],
                "next_action": dict(sorted(byline_exit_actions.items())),
                "next_action_share": {
                    action_type: round(
                        count / max(attack_totals["byline_episodes"], 1), 4
                    )
                    for action_type, count in sorted(byline_exit_actions.items())
                },
                "with_later_shot": attack_totals["byline_episodes_with_later_shot"],
                "with_later_shot_share": round(
                    attack_totals["byline_episodes_with_later_shot"]
                    / max(attack_totals["byline_episodes"], 1),
                    4,
                ),
                "with_shot_within_8_ticks": attack_totals[
                    "byline_episodes_with_shot_within_8_ticks"
                ],
            },
            "strict_cutbacks": {
                "completed": attack_totals["strict_cutbacks"],
                "share_of_completed_passes": round(
                    attack_totals["strict_cutbacks"]
                    / max(completed_attack_actions["pass"], 1),
                    4,
                ),
                "with_shot_within_8_ticks": attack_totals[
                    "strict_cutbacks_with_shot_within_8_ticks"
                ],
                "immediate_shot_rate": round(
                    attack_totals["strict_cutbacks_with_shot_within_8_ticks"]
                    / max(attack_totals["strict_cutbacks"], 1),
                    4,
                ),
            },
            "shots_after_byline_in_possession": attack_totals[
                "shots_after_byline_in_possession"
            ],
            "shot_origin_regions": {
                region: {
                    "count": count,
                    "share": round(count / max(shot_origin_total, 1), 4),
                }
                for region, count in sorted(shot_origin_regions.items())
            },
            "wide_possessions": {
                "count": attack_totals["wide_possessions"],
                "with_shot": attack_totals["wide_possessions_with_shot"],
                "shot_rate": round(
                    attack_totals["wide_possessions_with_shot"]
                    / max(attack_totals["wide_possessions"], 1),
                    4,
                ),
            },
            "wide_final_third_carry_share_of_all_actions": round(
                wide_final_origin_actions["carry"] / max(completed_attack_total, 1),
                4,
            ),
        },
        "shape": {
            team: {
                metric: average(("shape", team, metric))
                for metric in summaries[0]["shape"][team]
            }
            for team in ("home", "away")
        },
    }


def _run_real_squad_matches(args: argparse.Namespace) -> dict[str, Any]:
    from psl_core.engine_v2 import load_config_from_service
    from psl_core.engine_v2.rust_bridge import run_match
    from server.database import Database
    from server.services.game_config import GameConfigService

    with tempfile.TemporaryDirectory(prefix="psl-engine-v2-pace-") as temp_dir:
        snapshot = Path(temp_dir) / "psl.db"
        with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        db = Database(str(snapshot))
        try:
            home_cards, home_formation = _build_cards(db, args.home_qq)
            away_cards, away_formation = _build_cards(db, args.away_qq)
            config = load_config_from_service(GameConfigService(db))
            summaries = []
            for seed in range(args.seed, args.seed + args.seeds):
                response = run_match(
                    home_cards,
                    away_cards,
                    home_formation,
                    away_formation,
                    config,
                    seed=seed,
                )
                summary = summarize_match(response, include_sequences=args.show_sequences)
                summary["seed"] = seed
                summaries.append(summary)
        finally:
            db.close()

    return {
        "match_count": len(summaries),
        "seeds": [summary["seed"] for summary in summaries],
        "formations": {"home": home_formation, "away": away_formation},
        "runtime_config": _runtime_config_summary(config),
        "aggregate": _aggregate_summaries(summaries),
        **({"matches": summaries} if args.show_matches else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "psl.db")
    parser.add_argument("--home-qq", type=int, default=10001)
    parser.add_argument("--away-qq", type=int, default=10003)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument(
        "--show-matches",
        action="store_true",
        help="Include a per-seed summary in addition to the aggregate.",
    )
    parser.add_argument(
        "--show-sequences",
        action="store_true",
        help="Include every possession sequence in the per-match output.",
    )
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be at least 1")
    if args.show_sequences:
        args.show_matches = True
    print(json.dumps(_run_real_squad_matches(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
