#!/usr/bin/env python3
"""Summarize sequence tempo and team shape from a Rust engine_v2 match."""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from math import hypot
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PREMIER_LEAGUE_2024_25_BENCHMARK = {
    "season": "2024/25",
    "matches": 380,
    "provider": "PremierLeague.com Opta team stats API",
    "source": (
        "https://footballapi.pulselive.com/football/stats/ranked/teams/"
        "{stat}?comps=1&compSeasons=719&page=0&pageSize=20"
    ),
    "definition_source": "https://www.statsperform.com/zh/opta-event-definitions/",
    "totals": {
        "passes": 339493,
        "passes_completed": 284230,
        "shots": 9850,
        "shots_on_target": 3460,
        "blocked_shots": 2835,
        "goals": 1115,
    },
    "home_away_source": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
    "home_away": {
        "home_goals": 575,
        "away_goals": 540,
        "home_shots": 5226,
        "away_shots": 4623,
        "home_shots_on_target": 1837,
        "away_shots_on_target": 1621,
    },
    "source_consistency": {
        "shots_delta": 9850 - (5226 + 4623),
        "shots_on_target_delta": 3460 - (1837 + 1621),
        "goals_delta": 1115 - (575 + 540),
        "note": (
            "overall targets use PremierLeague.com Opta totals; home/away splits use "
            "football-data.co.uk and differ by one shot and two shots on target"
        ),
    },
    "unavailable": {
        "xg": "the historical PremierLeague.com team stats API returned no records",
    },
}

PACE_STAT_KEYS = (
    "goals",
    "xg",
    "shots",
    "shots_on_target",
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
    "successful_take_ons",
)

PLAYER_TEAM_STAT_FIELDS = {
    "shots": "shots",
    "shots_on_target": "shots_on_target",
    "goals": "goals",
    "passes": "passes",
    "passes_completed": "completed_passes",
    "tackle_attempts": "tackles_attempted",
    "tackles_won": "tackles_won",
    "take_ons": "take_ons",
    "successful_take_ons": "successful_take_ons",
    "saves": "saves",
    "blocks": "blocks",
    "interceptions": "interceptions",
    "pressures": "pressures",
    "successful_pressures": "successful_pressures",
    "turnovers": "turnovers",
    "clearances": "clearances",
    "carries": "carries",
    "carries_completed": "carries_completed",
    "crosses": "crosses",
    "crosses_completed": "successful_crosses",
    "long_passes": "long_passes",
    "completed_long_passes": "completed_long_passes",
    "key_passes": "key_passes",
    "offsides": "offsides",
    "progressive_passes": "progressive_passes",
    "passes_into_final_third": "passes_into_final_third",
    "passes_into_box": "passes_into_box",
    "carries_into_final_third": "carries_into_final_third",
    "carries_into_box": "carries_into_box",
    "progressive_carries": "progressive_carries",
}


def _integrity_check(
    actual: float,
    expected: float,
    *,
    actual_source: str,
    expected_source: str,
    tolerance: float = 0.0,
    severity: str = "error",
) -> dict[str, Any]:
    delta = float(actual) - float(expected)
    return {
        "status": "ok" if abs(delta) <= tolerance + 1e-9 else severity,
        "actual": actual,
        "expected": expected,
        "delta": round(delta, 4),
        "tolerance": tolerance,
        "actual_source": actual_source,
        "expected_source": expected_source,
    }


def _subset_integrity_check(
    subset: float,
    superset: float,
    *,
    subset_source: str,
    superset_source: str,
    severity: str = "error",
) -> dict[str, Any]:
    overflow = max(float(subset) - float(superset), 0.0)
    return {
        "status": "ok" if overflow <= 1e-9 else severity,
        "actual": subset,
        "expected_max": superset,
        "delta": round(overflow, 4),
        "tolerance": 0.0,
        "actual_source": subset_source,
        "expected_source": superset_source,
    }


def _team_event_count(
    events: Iterable[dict[str, Any]],
    team: str,
    event_type: str,
    outcomes: set[str] | None = None,
) -> int:
    return sum(
        1
        for event in events
        if event.get("team_side") == team
        and event.get("event_type") == event_type
        and (outcomes is None or event.get("outcome") in outcomes)
    )


def _event_xg(event: dict[str, Any]) -> float:
    value = event.get("xg_exact", event.get("xg", 0.0))
    return float(value or 0.0)


def _shot_outcome_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    event_list = list(events)
    outcomes = ("goal", "saved", "blocked", "off_target", "period_end")
    by_team = {
        team: {
            outcome: _team_event_count(event_list, team, "shot", {outcome})
            for outcome in outcomes
        }
        for team in ("home", "away")
    }
    censored_on_target_by_team = {
        team: sum(
            1
            for event in event_list
            if event.get("team_side") == team
            and event.get("event_type") == "shot"
            and event.get("outcome") == "period_end"
            and _event_has_tag(event, "on_target")
        )
        for team in ("home", "away")
    }
    xg_by_team = {
        team: sum(
            _event_xg(event)
            for event in event_list
            if event.get("team_side") == team
            and event.get("event_type") == "shot"
        )
        for team in ("home", "away")
    }
    return {
        "by_team": by_team,
        "total": {
            outcome: sum(by_team[team][outcome] for team in ("home", "away"))
            for outcome in outcomes
        },
        "censored_on_target": {
            **censored_on_target_by_team,
            "total": sum(censored_on_target_by_team.values()),
        },
        "event_xg": {
            **xg_by_team,
            "total": sum(xg_by_team.values()),
        },
    }


def _shot_family_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    event_list = [
        event for event in events if event.get("event_type") == "shot"
    ]
    families = {
        "shoot_action": [
            event
            for event in event_list
            if not _event_has_tag(event, "carry_finish")
        ],
        "carry_finish": [
            event
            for event in event_list
            if _event_has_tag(event, "carry_finish")
        ],
    }
    result: dict[str, Any] = {
        "definition": (
            "mutually exclusive shot-event mechanism families; carry_finish is a "
            "controlled carry crossing the attacking goal line, not a selected Shoot "
            "action, so mechanism tuning must not infer Shoot finishing quality from "
            "the blended conversion rate"
        )
    }
    for family, family_events in families.items():
        shots = len(family_events)
        goals = sum(event.get("outcome") == "goal" for event in family_events)
        event_xg = sum(_event_xg(event) for event in family_events)
        result[family] = {
            "shots": shots,
            "goals": goals,
            "event_xg": event_xg,
            "xg_per_shot": round(event_xg / max(shots, 1), 4),
            "goal_conversion_rate": round(goals / max(shots, 1), 4),
        }
    result["closure"] = {
        "classified": sum(result[family]["shots"] for family in families),
        "shot_events": len(event_list),
        "delta": sum(result[family]["shots"] for family in families) - len(event_list),
    }
    return result


def _shot_release_summary(response: dict[str, Any]) -> dict[str, Any]:
    events = response.get("events", [])
    trace = response.get("trace", {})
    trace_entries = trace.get("entries", [])
    trace_decisions = trace.get("decisions", [])
    released_by_team = Counter(
        event.get("team_side")
        for event in events
        if event.get("event_type") == "shot"
        and not _event_has_tag(event, "carry_finish")
        and event.get("team_side") in {"home", "away"}
    )
    unreleased_entries = [
        entry
        for entry in trace_entries
        if entry.get("event") == "shot_unreleased"
        and entry.get("team") in {"home", "away"}
    ]
    prepared_entries = [
        entry
        for entry in trace_entries
        if entry.get("event") == "shot_prepared"
        and entry.get("team") in {"home", "away"}
    ]
    abandoned_entries = [
        entry
        for entry in trace_entries
        if entry.get("event") == "shot_abandoned"
        and entry.get("team") in {"home", "away"}
    ]
    unreleased_by_team = Counter(entry["team"] for entry in unreleased_entries)
    prepared_by_team = Counter(entry["team"] for entry in prepared_entries)
    abandoned_by_team = Counter(entry["team"] for entry in abandoned_entries)
    selected_decisions = [
        decision
        for decision in trace_decisions
        if isinstance(decision.get("chosen"), dict)
        and decision["chosen"].get("action_type") == "shoot"
        and decision.get("team") in {"home", "away"}
    ]
    selected_decisions_by_team = Counter(
        decision["team"] for decision in selected_decisions
    )
    pre_release_duel_losses_by_team: Counter[str] = Counter()
    for event in events:
        if not (
            _event_has_tag(event, "shot_release")
            and _event_has_tag(event, "possession_won")
        ):
            continue
        event_team = event.get("team_side")
        if event_team not in {"home", "away"}:
            continue
        attacking_team = "away" if event_team == "home" else "home"
        pre_release_duel_losses_by_team[attacking_team] += 1
    body_probabilities = [
        float(entry["body_release_probability"])
        for entry in unreleased_entries
        if isinstance(entry.get("body_release_probability"), (int, float))
    ]
    readiness_before = [
        float(entry["release_readiness_before"])
        for entry in unreleased_entries
        if isinstance(entry.get("release_readiness_before"), (int, float))
    ]
    readiness_after = [
        float(entry["release_readiness_after"])
        for entry in unreleased_entries
        if isinstance(entry.get("release_readiness_after"), (int, float))
    ]
    released = sum(released_by_team.values())
    unreleased = len(unreleased_entries)
    pre_release_duel_losses = sum(pre_release_duel_losses_by_team.values())
    observable_resolutions_by_team = {
        team: (
            released_by_team[team]
            + unreleased_by_team[team]
            + abandoned_by_team[team]
            + pre_release_duel_losses_by_team[team]
        )
        for team in ("home", "away")
    }
    has_decision_trace = bool(trace_decisions)
    selected_by_team = {
        team: (
            selected_decisions_by_team[team]
            if has_decision_trace
            else observable_resolutions_by_team[team]
        )
        for team in ("home", "away")
    }
    selected = sum(selected_by_team.values())
    unresolved_by_team = {
        team: max(selected_by_team[team] - observable_resolutions_by_team[team], 0)
        for team in ("home", "away")
    }
    unresolved = sum(unresolved_by_team.values())
    return {
        "scope": (
            "full decision trace counts every chosen Shoot and partitions it into formal shot, "
            "terminal shot_unreleased, explicit abandonment, pre-release duel loss, or unresolved; "
            "shot_prepared is an intermediate contact and does not close the selected attempt; "
            "without decision trace the selected count is only the observable resolved lower bound"
        ),
        "selection_source": (
            "decision_trace" if has_decision_trace else "observable_resolution_lower_bound"
        ),
        "selected": selected,
        "prepared_contacts": len(prepared_entries),
        "unreleased": unreleased,
        "abandoned": len(abandoned_entries),
        "pre_release_duel_losses": pre_release_duel_losses,
        "released": released,
        "unresolved": unresolved,
        "selection_accounting_status": "ok" if unresolved == 0 else "incomplete",
        "release_rate": round(released / max(selected, 1), 4),
        "by_team": {
            team: {
                "selected": selected_by_team[team],
                "prepared_contacts": prepared_by_team[team],
                "unreleased": unreleased_by_team[team],
                "abandoned": abandoned_by_team[team],
                "pre_release_duel_losses": pre_release_duel_losses_by_team[team],
                "released": released_by_team[team],
                "unresolved": unresolved_by_team[team],
                "release_rate": round(
                    released_by_team[team] / max(selected_by_team[team], 1),
                    4,
                ),
            }
            for team in ("home", "away")
        },
        "unreleased_body_probability": {
            "mean": round(mean(body_probabilities), 3) if body_probabilities else 0.0,
            "median": round(median(body_probabilities), 3) if body_probabilities else 0.0,
        },
        "unreleased_readiness": {
            "mean_before": round(mean(readiness_before), 3) if readiness_before else 0.0,
            "mean_after": round(mean(readiness_after), 3) if readiness_after else 0.0,
        },
    }


def _direct_shot_creations(
    events: Iterable[dict[str, Any]],
    team: str,
) -> tuple[Counter[str], Counter[str], float]:
    ordered = sorted(events, key=lambda event: int(event.get("seq", 0) or 0))
    key_passes: Counter[str] = Counter()
    assists: Counter[str] = Counter()
    expected_assists = 0.0
    for index, shot in enumerate(ordered):
        if shot.get("team_side") != team or shot.get("event_type") != "shot":
            continue
        shooter_id = (
            shot.get("player", {}).get("player_id")
            if isinstance(shot.get("player"), dict)
            else None
        )
        possession_id = shot.get("possession_id")
        creator_id = None
        for prior in reversed(ordered[:index]):
            if prior.get("possession_id") != possession_id:
                continue
            event_type = prior.get("event_type")
            if (
                event_type in {"recovery", "interception", "tackle", "loose_ball"}
                or _event_has_tag(prior, "second_ball")
            ):
                break
            if event_type != "pass":
                continue
            target = prior.get("target_player")
            target_id = target.get("player_id") if isinstance(target, dict) else None
            player = prior.get("player")
            passer_id = player.get("player_id") if isinstance(player, dict) else None
            if (
                prior.get("team_side") == team
                and prior.get("outcome") == "completed"
                and target_id == shooter_id
                and passer_id is not None
            ):
                creator_id = str(passer_id)
            break
        if creator_id is None:
            continue
        key_passes[creator_id] += 1
        expected_assists += _event_xg(shot)
        assist_player = shot.get("assist_player")
        assist_id = (
            assist_player.get("player_id") if isinstance(assist_player, dict) else None
        )
        if shot.get("outcome") == "goal" and assist_id is not None:
            assists[str(assist_id)] += 1
    return key_passes, assists, expected_assists


def _metric_integrity_summary(response: dict[str, Any]) -> dict[str, Any]:
    events = response.get("events", [])
    team_payloads = {
        "home": (response.get("home_stats", {}), response.get("home_player_stats", [])),
        "away": (response.get("away_stats", {}), response.get("away_player_stats", [])),
    }
    teams: dict[str, Any] = {}
    issue_counts: Counter[str] = Counter()
    validation_check_counts: Counter[str] = Counter()
    compatibility_notice_counts: Counter[str] = Counter()

    for team, (team_stats, player_stats) in team_payloads.items():
        checks: dict[str, Any] = {}
        for team_field, player_field in PLAYER_TEAM_STAT_FIELDS.items():
            player_total = sum(float(player.get(player_field, 0) or 0) for player in player_stats)
            checks[f"{team_field}.team_vs_players"] = _integrity_check(
                float(team_stats.get(team_field, 0) or 0),
                player_total,
                actual_source=f"{team}_stats.{team_field}",
                expected_source=f"sum({team}_player_stats.{player_field})",
            )

        event_expectations = {
            "shots.team_vs_events": (
                float(team_stats.get("shots", 0) or 0),
                _team_event_count(events, team, "shot"),
                f"{team}_stats.shots",
                "shot events",
            ),
            "shots_on_target.team_vs_events": (
                float(team_stats.get("shots_on_target", 0) or 0),
                sum(
                    1
                    for event in events
                    if event.get("team_side") == team
                    and event.get("event_type") == "shot"
                    and (
                        event.get("outcome") in {"goal", "saved"}
                        or (
                            event.get("outcome") == "period_end"
                            and _event_has_tag(event, "on_target")
                        )
                    )
                ),
                f"{team}_stats.shots_on_target",
                "goal/saved shot events plus on-target period-end attempts",
            ),
            "goals.team_vs_events": (
                float(team_stats.get("goals", 0) or 0),
                _team_event_count(events, team, "shot", {"goal"}),
                f"{team}_stats.goals",
                "shot events with goal outcome",
            ),
            "tackles_won.team_vs_events": (
                float(team_stats.get("tackles_won", 0) or 0),
                _team_event_count(events, team, "tackle", {"won"}),
                f"{team}_stats.tackles_won",
                "won tackle events",
            ),
            "successful_take_ons.team_vs_events": (
                float(team_stats.get("successful_take_ons", 0) or 0),
                sum(
                    1
                    for event in events
                    if event.get("team_side") == team
                    and event.get("event_type") == "duel"
                    and event.get("outcome") == "won"
                    and _event_has_tag(event, "take_on_completed")
                    and _event_has_tag(event, "spatially_separated")
                ),
                f"{team}_stats.successful_take_ons",
                "won take-on episodes completed after spatially separating from the defender",
            ),
            "take_ons.team_vs_events": (
                float(team_stats.get("take_ons", 0) or 0),
                sum(
                    1
                    for event in events
                    if event.get("team_side") == team
                    and event.get("event_type") == "duel"
                    and event.get("outcome") == "attempted"
                    and _event_has_tag(event, "take_on_attempt")
                ),
                f"{team}_stats.take_ons",
                "new physical take-on episode events tagged take_on_attempt",
            ),
            "interceptions.team_vs_events": (
                float(team_stats.get("interceptions", 0) or 0),
                _team_event_count(events, team, "interception", {"won"}),
                f"{team}_stats.interceptions",
                "won interception events",
            ),
            "passes_completed.team_vs_events": (
                float(team_stats.get("passes_completed", 0) or 0),
                _team_event_count(events, team, "pass", {"completed"}),
                f"{team}_stats.passes_completed",
                "completed pass events",
            ),
            "corners.team_vs_events": (
                float(team_stats.get("corners", 0) or 0),
                _team_event_count(events, team, "restart", {"corner"}),
                f"{team}_stats.corners",
                "corner restart events",
            ),
            "goal_kicks.team_vs_events": (
                float(team_stats.get("goal_kicks", 0) or 0),
                _team_event_count(events, team, "restart", {"goal_kick"}),
                f"{team}_stats.goal_kicks",
                "goal-kick restart events",
            ),
            "throw_ins.team_vs_events": (
                float(team_stats.get("throw_ins", 0) or 0),
                _team_event_count(events, team, "restart", {"throw_in"}),
                f"{team}_stats.throw_ins",
                "throw-in restart events",
            ),
            "offside_free_kicks.team_vs_events": (
                float(team_stats.get("offside_free_kicks", 0) or 0),
                _team_event_count(events, team, "restart", {"offside"}),
                f"{team}_stats.offside_free_kicks",
                "offside restart events awarded to the team",
            ),
        }
        for name, (actual, expected, actual_source, expected_source) in event_expectations.items():
            checks[name] = _integrity_check(
                actual,
                expected,
                actual_source=actual_source,
                expected_source=expected_source,
            )

        checks["xg.team_vs_events"] = _integrity_check(
            float(team_stats.get("xg", 0.0) or 0.0),
            round(
                sum(
                    _event_xg(event)
                    for event in events
                    if event.get("team_side") == team
                    and event.get("event_type") == "shot"
                ),
                2,
            ),
            actual_source=f"{team}_stats.xg",
            expected_source="round(sum(shot events.xg_exact), 2)",
            tolerance=0.005,
        )
        player_xg = sum(float(player.get("xg", 0.0) or 0.0) for player in player_stats)
        checks["xg.team_vs_rounded_players"] = _integrity_check(
            float(team_stats.get("xg", 0.0) or 0.0),
            player_xg,
            actual_source=f"{team}_stats.xg",
            expected_source=f"sum({team}_player_stats.xg), each player already rounded",
            tolerance=round(0.005 * max(len(player_stats), 1) + 0.005, 3),
            severity="warning",
        )
        player_psxg = sum(
            float(player.get("post_shot_xg", 0.0) or 0.0) for player in player_stats
        )
        checks["post_shot_xg.team_vs_rounded_players"] = _integrity_check(
            float(team_stats.get("post_shot_xg", 0.0) or 0.0),
            player_psxg,
            actual_source=f"{team}_stats.post_shot_xg",
            expected_source=f"sum({team}_player_stats.post_shot_xg), each player already rounded",
            tolerance=round(0.005 * max(len(player_stats), 1) + 0.005, 3),
            severity="warning",
        )
        attempted = float(team_stats.get("passes", 0) or 0)
        completed = float(team_stats.get("passes_completed", 0) or 0)
        opponent = "away" if team == "home" else "home"
        released_pass_terminals = _team_event_count(events, team, "pass") + sum(
            1
            for event in events
            if (
                event.get("team_side") == opponent
                and event.get("event_type") == "interception"
                and "pass_cut_out" in (event.get("tags") or [])
            )
            or (
                event.get("team_side") == team
                and event.get("event_type") == "offside"
                and _event_has_tag(event, "pass_release")
            )
        )
        checks["passes_attempted.team_vs_terminal_events"] = _integrity_check(
            attempted,
            released_pass_terminals,
            actual_source=f"{team}_stats.passes",
            expected_source=(
                f"{team} pass terminal events + {opponent} pass-cut-out interceptions"
            ),
        )
        expected_rate = round(completed / attempted * 100.0, 1) if attempted else 0.0
        checks["pass_success_rate"] = _integrity_check(
            float(team_stats.get("pass_success_rate", 0.0) or 0.0),
            expected_rate,
            actual_source=f"{team}_stats.pass_success_rate",
            expected_source="passes_completed / passes",
            tolerance=0.01,
        )
        crosses = float(team_stats.get("crosses", 0) or 0)
        completed_crosses = float(team_stats.get("crosses_completed", 0) or 0)
        non_cross_attempted = attempted - crosses
        non_cross_completed = completed - completed_crosses
        checks["non_cross_passes.non_negative"] = _subset_integrity_check(
            crosses,
            attempted,
            subset_source=f"{team}_stats.crosses",
            superset_source=f"{team}_stats.passes",
        )
        checks["non_cross_completed_passes.non_negative"] = _subset_integrity_check(
            completed_crosses,
            completed,
            subset_source=f"{team}_stats.crosses_completed",
            superset_source=f"{team}_stats.passes_completed",
        )
        checks["non_cross_completed_passes.subset_of_non_cross_passes"] = (
            _subset_integrity_check(
                non_cross_completed,
                non_cross_attempted,
                subset_source=(
                    f"{team}_stats.passes_completed - "
                    f"{team}_stats.crosses_completed"
                ),
                superset_source=f"{team}_stats.passes - {team}_stats.crosses",
            )
        )
        checks["shots_partition"] = _integrity_check(
            float(team_stats.get("shots", 0) or 0),
            float(team_stats.get("shots_in_box", 0) or 0)
            + float(team_stats.get("shots_outside_box", 0) or 0),
            actual_source=f"{team}_stats.shots",
            expected_source="shots_in_box + shots_outside_box",
        )
        shot_outcomes = {
            outcome: _team_event_count(events, team, "shot", {outcome})
            for outcome in ("goal", "saved", "blocked", "off_target", "period_end")
        }
        checks["shots.outcome_partition"] = _integrity_check(
            float(team_stats.get("shots", 0) or 0),
            sum(shot_outcomes.values()),
            actual_source=f"{team}_stats.shots",
            expected_source="goal + saved + blocked + off_target + period_end shot events",
        )
        checks["shots_on_target.goals_plus_opponent_saves"] = _integrity_check(
            float(team_stats.get("shots_on_target", 0) or 0),
            float(team_stats.get("goals", 0) or 0)
            + float(team_payloads[opponent][0].get("saves", 0) or 0),
            actual_source=f"{team}_stats.shots_on_target",
            expected_source=f"{team}_stats.goals + {opponent}_stats.saves",
            tolerance=sum(
                1
                for event in events
                if event.get("team_side") == team
                and event.get("event_type") == "shot"
                and event.get("outcome") == "period_end"
                and _event_has_tag(event, "on_target")
            ),
        )
        checks["shots_on_target.subset_of_shots"] = _subset_integrity_check(
            float(team_stats.get("shots_on_target", 0) or 0),
            float(team_stats.get("shots", 0) or 0),
            subset_source=f"{team}_stats.shots_on_target",
            superset_source=f"{team}_stats.shots",
        )
        for completed_field, attempted_field in (
            ("passes_completed", "passes"),
            ("tackles_won", "tackle_attempts"),
            ("successful_take_ons", "take_ons"),
            ("carries_completed", "carries"),
            ("crosses_completed", "crosses"),
            ("completed_long_passes", "long_passes"),
        ):
            checks[f"{completed_field}.subset_of_{attempted_field}"] = (
                _subset_integrity_check(
                    float(team_stats.get(completed_field, 0) or 0),
                    float(team_stats.get(attempted_field, 0) or 0),
                    subset_source=f"{team}_stats.{completed_field}",
                    superset_source=f"{team}_stats.{attempted_field}",
                )
            )

        team_shot_events = [
            event
            for event in events
            if event.get("team_side") == team and event.get("event_type") == "shot"
        ]
        big_chances = sum(
            _event_has_tag(event, "big_chance") for event in team_shot_events
        )
        checks["big_chances.team_vs_events"] = _integrity_check(
            float(team_stats.get("big_chances", 0) or 0),
            big_chances,
            actual_source=f"{team}_stats.big_chances",
            expected_source=f"{team} shot events tagged big_chance from unrounded xg",
        )

        key_passes, assists, expected_assists = _direct_shot_creations(events, team)
        player_key_passes = sum(float(player.get("key_passes", 0) or 0) for player in player_stats)
        player_assists = sum(float(player.get("assists", 0) or 0) for player in player_stats)
        player_xa = sum(float(player.get("xa", 0.0) or 0.0) for player in player_stats)
        checks["key_passes.players_vs_shot_provenance"] = _integrity_check(
            player_key_passes,
            sum(key_passes.values()),
            actual_source=f"sum({team}_player_stats.key_passes)",
            expected_source="shots whose direct creator is the final completed passer",
        )
        checks["assists.players_vs_goal_events"] = _integrity_check(
            player_assists,
            sum(assists.values()),
            actual_source=f"sum({team}_player_stats.assists)",
            expected_source="goal events with an assist_player",
        )
        checks["xa.players_vs_shot_provenance"] = _integrity_check(
            player_xa,
            expected_assists,
            actual_source=f"sum({team}_player_stats.xa), each player already rounded",
            expected_source="sum(xg) for shots with a direct creator",
            tolerance=round(
                0.005 * max(len(player_stats) + sum(key_passes.values()), 1) + 0.005,
                3,
            ),
            severity="warning",
        )

        opponent_player_stats = team_payloads[opponent][1]
        player_psxg_faced = sum(
            float(player.get("psxg_faced", 0.0) or 0.0) for player in opponent_player_stats
        )
        player_goals_conceded = sum(
            float(player.get("goals_conceded", 0) or 0) for player in opponent_player_stats
        )
        checks["post_shot_xg.team_vs_opponent_psxg_faced"] = _integrity_check(
            float(team_stats.get("post_shot_xg", 0.0) or 0.0),
            player_psxg_faced,
            actual_source=f"{team}_stats.post_shot_xg",
            expected_source=f"sum({opponent}_player_stats.psxg_faced)",
            tolerance=round(0.005 * max(len(opponent_player_stats), 1) + 0.005, 3),
            severity="warning",
        )
        checks["goals.team_vs_opponent_goals_conceded"] = _integrity_check(
            float(team_stats.get("goals", 0) or 0),
            player_goals_conceded,
            actual_source=f"{team}_stats.goals",
            expected_source=f"sum({opponent}_player_stats.goals_conceded)",
        )

        checks["blocks.team_vs_opponent_shots"] = _integrity_check(
            float(team_stats.get("blocks", 0) or 0),
            _team_event_count(events, opponent, "shot", {"blocked"}),
            actual_source=f"{team}_stats.blocks",
            expected_source=f"{opponent} blocked shot events",
        )
        checks["saves.team_vs_opponent_shots"] = _integrity_check(
            float(team_stats.get("saves", 0) or 0),
            _team_event_count(events, opponent, "shot", {"saved"}),
            actual_source=f"{team}_stats.saves",
            expected_source=f"{opponent} saved shot events",
        )

        compatibility_aliases = {
            "tackles": {
                "status": "warning",
                "actual": team_stats.get("tackles", 0),
                "canonical_field": "tackles_won",
                "attempt_field": "tackle_attempts",
                "definition": "compatibility alias currently means successful tackles, not attempts",
            },
            "dribbles": {
                "status": "warning",
                "actual": team_stats.get("dribbles", 0),
                "canonical_field": "successful_take_ons",
                "attempt_field": "take_ons",
                "definition": "compatibility alias currently means successful take-ons, not attempts",
            },
            "free_kicks": {
                "status": "warning",
                "actual": team_stats.get("free_kicks", 0),
                "canonical_field": "offside_free_kicks",
                "definition": "compatibility alias counts only offside restarts, not all free kicks",
            },
        }
        for check in checks.values():
            issue_counts[check["status"]] += 1
            validation_check_counts[check["status"]] += 1
        issue_counts["warning"] += len(compatibility_aliases)
        compatibility_notice_counts.update(compatibility_aliases.keys())
        teams[team] = {
            "status": "error"
            if any(check["status"] == "error" for check in checks.values())
            else "warning",
            "checks": checks,
            "compatibility_aliases": compatibility_aliases,
        }

    score_checks = {
        "home_score_vs_goals": _integrity_check(
            float(response.get("home_score", 0) or 0),
            float(response.get("home_stats", {}).get("goals", 0) or 0),
            actual_source="home_score",
            expected_source="home_stats.goals",
        ),
        "away_score_vs_goals": _integrity_check(
            float(response.get("away_score", 0) or 0),
            float(response.get("away_stats", {}).get("goals", 0) or 0),
            actual_source="away_score",
            expected_source="away_stats.goals",
        ),
        "possession_sum": _integrity_check(
            float(response.get("home_stats", {}).get("possession", 0.0) or 0.0)
            + float(response.get("away_stats", {}).get("possession", 0.0) or 0.0),
            100.0,
            actual_source="home_stats.possession + away_stats.possession",
            expected_source="100 percent of controlled-possession ticks",
            tolerance=0.2,
        ),
    }
    match_clock = response.get("match_clock", {})
    ball_state_ticks = match_clock.get("ball_state_ticks", {})
    state_tick_values = {
        state: ball_state_ticks.get(state)
        for state in ("held", "in_flight", "free_ball", "dead")
    }
    match_ticks = match_clock.get("match_ticks")
    active_play_ticks = match_clock.get("active_play_ticks")
    dead_ball_ticks = match_clock.get("dead_ball_ticks")
    if isinstance(match_ticks, (int, float)) and all(
        isinstance(value, (int, float)) for value in state_tick_values.values()
    ):
        score_checks["ball_state_ticks_match_match_clock"] = _integrity_check(
            sum(float(value) for value in state_tick_values.values()),
            float(match_ticks),
            actual_source="sum(match_clock.ball_state_ticks)",
            expected_source="match_clock.match_ticks",
        )
    if (
        isinstance(active_play_ticks, (int, float))
        and isinstance(state_tick_values["held"], (int, float))
        and isinstance(state_tick_values["in_flight"], (int, float))
        and isinstance(state_tick_values["free_ball"], (int, float))
    ):
        score_checks["active_ball_state_ticks_match_active_play"] = _integrity_check(
            float(state_tick_values["held"])
            + float(state_tick_values["in_flight"])
            + float(state_tick_values["free_ball"]),
            float(active_play_ticks),
            actual_source=(
                "held + in_flight + free_ball match_clock.ball_state_ticks"
            ),
            expected_source="match_clock.active_play_ticks",
        )
    if (
        isinstance(dead_ball_ticks, (int, float))
        and isinstance(state_tick_values["dead"], (int, float))
    ):
        score_checks["dead_ball_state_ticks_match_dead_clock"] = _integrity_check(
            float(state_tick_values["dead"]),
            float(dead_ball_ticks),
            actual_source="match_clock.ball_state_ticks.dead",
            expected_source="match_clock.dead_ball_ticks",
        )
    for check in score_checks.values():
        issue_counts[check["status"]] += 1
        validation_check_counts[check["status"]] += 1
    overall_status = "error" if issue_counts["error"] else "warning" if issue_counts["warning"] else "ok"
    held_ticks = int(state_tick_values["held"] or 0)
    in_flight_ticks = int(state_tick_values["in_flight"] or 0)
    free_ball_ticks = int(state_tick_values["free_ball"] or 0)
    dead_ticks = int(state_tick_values["dead"] or 0)
    active_ticks = int(active_play_ticks or 0)
    total_ticks = int(match_ticks or 0)
    neutral_active_ticks = in_flight_ticks + free_ball_ticks
    return {
        "status": overall_status,
        "issue_counts": dict(sorted(issue_counts.items())),
        "issue_breakdown": {
            "validation_checks": dict(sorted(validation_check_counts.items())),
            "compatibility_notices": {
                "total": sum(compatibility_notice_counts.values()),
                "by_field": dict(sorted(compatibility_notice_counts.items())),
            },
        },
        "cross_team_checks": score_checks,
        "teams": teams,
        "possession_scope": {
            "controlled_ticks": held_ticks,
            "neutral_active_ticks": neutral_active_ticks,
            "dead_ticks": dead_ticks,
            "controlled_share_of_match": round(
                held_ticks / max(total_ticks, 1),
                4,
            ),
            "controlled_share_of_active_play": round(
                held_ticks / max(active_ticks, 1),
                4,
            ),
            "neutral_share_of_active_play": round(
                neutral_active_ticks / max(active_ticks, 1),
                4,
            ),
        },
        "definitions": {
            "possession": "relative share within Held ticks only, credited to the tick's starting controller; controlled_share_of_match and neutral_share_of_active_play must be inspected separately because InFlight, FreeBall, and Dead ticks are excluded from the displayed 100 percent split",
            "xg": "unconditional goal probability for each formally released shot: probability of clearing the blocking lane multiplied by the conditional on-target-and-beat-goalkeeper probability; body-release failure is excluded because it does not create a shot event",
            "shots_on_target": "goal plus saved attempts and any on-target shot censored by period end; blocked shots are excluded",
            "shots_on_target_share": "literal engine shots_on_target divided by all released shots; this is not Opta shooting accuracy",
            "provider_shooting_accuracy": "provider-style shots on target divided by shots excluding ordinary blocked attempts; engine blocks cannot yet distinguish ordinary blocks from last-line on-target blocks, so only a sensitivity interval is reported",
            "shot_outcomes": "every released shot has one terminal event; period_end is a censored attempt and is not treated as off_target",
            "pass_attempts": "authoritative team/player counters include every released pass; event terminal types are split across pass, interception, tackle, and loose-ball flows",
            "pass_failure_cause_classes": "mutually exclusive dominant causes of unsuccessful pass releases; a technical delivery error takes precedence over its eventual control disposition",
            "pass_terminal_control_classes": "mutually exclusive terminal disposition of every pass release; completed, opposing control, unresolved control, out of play, offside, and period-end censoring close to all attempts",
            "non_cross_passes": "engine pass attempts minus engine-classified crosses; completed non-cross passes subtract completed crosses from completed passes",
            "clearances": "clearances are a separate action family and never contribute to pass attempts or completed passes",
            "tackle_attempts": "failed attempts have no public match event and are audited only from player-to-team aggregation",
            "key_passes": "the final completed pass directly received by the shooter before a shot, with any recovery, defensive control event, or second-ball transition breaking the creation chain; public assist_player remains reserved for goals, so integrity is checked only from player-to-team aggregation",
            "xa": "sum of the resulting shots' xG for each key passer; exposed at player level and rounded after aggregation",
            "post_shot_xg": "internal proxy: the released shot's pre-shot xG is accumulated only for on-target attempts; it preserves shooter-versus-goalkeeper accounting but does not model provider PSxG from shot placement or velocity",
            "turnovers": "internal control-loss proxy recorded at selected execution and duel boundaries; it is not an exhaustive team-possession-loss count, and a later same-team second-ball recovery does not reverse it, so it must not be calibrated against provider possession-lost totals",
            "free_kicks": "the engine currently models only offside free-kick restarts; offside_free_kicks is canonical and free_kicks is a compatibility alias",
            "big_chances": "engine heuristic: shot events with xG >= 0.30; not an Opta big-chance classification",
            "npxg": "currently identical to xG because the engine does not model penalty shots",
        },
        "external_comparability": {
            "goals": "direct_observation_but_missing_set_piece_families",
            "shots": "direct_observation_but_missing_set_piece_families",
            "shots_on_target": "bounded_by_unclassified_last_line_blocks",
            "pass_success_rate": "scope_mismatch_crosses_and_restart_deliveries",
            "possession": "internal_only",
            "xg": "engine_model_only_no_available_provider_benchmark",
            "big_chances": "internal_only",
            "post_shot_xg": "internal_proxy_not_provider_comparable",
            "turnovers": "internal_control_loss_proxy",
            "npxg": "engine_xg_alias_while_penalties_are_unmodelled",
            "key_passes": "direct_shot_provenance_but_provider_event_rules_may_differ",
            "xa": "engine_xg_based_internal_model",
            "free_kicks": "incomplete",
            "tackles": "compatibility_alias",
            "dribbles": "compatibility_alias",
            "tackle_attempts": "provider_definition_dependent",
            "take_ons": "provider_definition_dependent",
            "carries": "provider_definition_dependent",
            "interceptions": "internal_opposing_control_wins_including_delivery_errors",
            "pressures": "internal_only",
            "successful_pressures": "internal_only",
            "progressive_passes": "engine_threshold_definition",
            "progressive_carries": "engine_threshold_definition",
            "passes_into_final_third": "engine_zone_entry_definition",
            "passes_into_box": "engine_zone_entry_definition",
            "carries_into_final_third": "engine_zone_entry_definition",
            "carries_into_box": "engine_zone_entry_definition",
            "headers": "unsupported_zero_placeholder",
            "headers_won": "unsupported_zero_placeholder",
        },
        "calibration_policy": {
            "direct_aggregate_validation_only": {
                "metrics": ["goals", "shots"],
                "reason": "the event totals are directly observable, but missing penalties and physical set-piece shot families make their gaps unsafe as isolated open-play tuning targets",
            },
            "bounded_aggregate_validation_only": {
                "metrics": [
                    "shots_on_target",
                    "shots_on_target_share",
                    "provider_shooting_accuracy",
                ],
                "reason": "engine blocks do not distinguish ordinary blocks from provider on-target last-line blocks",
            },
            "scope_mismatched_do_not_point_calibrate": {
                "metrics": ["passes", "passes_completed", "pass_success_rate"],
                "reason": "engine pass actions include crosses and omit restart deliveries that belong to the provider pass scope",
            },
            "internal_diagnostic_only": {
                "metrics": [
                    "possession",
                    "xg",
                    "post_shot_xg",
                    "big_chances",
                    "turnovers",
                    "pressures",
                    "successful_pressures",
                    "progressive_passes",
                    "progressive_carries",
                    "passes_into_final_third",
                    "passes_into_box",
                    "carries_into_final_third",
                    "carries_into_box",
                ],
                "reason": "these fields use engine-specific state, thresholds, or models rather than a provider-equivalent event definition",
            },
            "provider_definition_dependent": {
                "metrics": [
                    "tackle_attempts",
                    "tackles_won",
                    "take_ons",
                    "successful_take_ons",
                    "carries",
                    "carries_completed",
                    "interceptions",
                ],
                "reason": "the engine counters are internally consistent but their event inclusion rules are not provider-equivalent",
            },
            "compatibility_aliases_do_not_analyze_as_canonical": {
                "metrics": ["tackles", "dribbles", "free_kicks"],
                "reason": "these fields intentionally expose narrower canonical counters under legacy names",
            },
            "unsupported_placeholders": {
                "metrics": ["headers", "headers_won"],
                "reason": "these fields are currently constant zero and must never be interpreted as simulated output",
            },
        },
    }


def _distance(left: list[float], right: list[float]) -> float:
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def _distribution_values(distribution: dict[Any, Any]) -> list[float]:
    values: list[float] = []
    for value, count in distribution.items():
        values.extend([float(value)] * int(count))
    return values


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


def _pass_distance_band(event: dict[str, Any]) -> str:
    for tag, band in (
        ("distance_0_10", "0-10m"),
        ("distance_10_20", "10-20m"),
        ("distance_20_30", "20-30m"),
        ("distance_30_plus", "30m+"),
    ):
        if _event_has_tag(event, tag):
            return band
    origin = event.get("origin")
    target = event.get("target")
    if not (
        isinstance(origin, list)
        and len(origin) >= 2
        and isinstance(target, list)
        and len(target) >= 2
    ):
        return "unknown"
    distance_m = _distance(origin, target)
    if distance_m < 10.0:
        return "0-10m"
    if distance_m < 20.0:
        return "10-20m"
    if distance_m < 30.0:
        return "20-30m"
    return "30m+"


def _pass_breakdown_bucket(
    buckets: dict[str, Counter[str]],
    bucket: str,
    outcome: str,
) -> None:
    buckets[bucket]["attempted"] += 1
    buckets[bucket][outcome] += 1


def _pass_breakdown_summary(
    buckets: dict[str, Counter[str]],
    order: tuple[str, ...],
) -> dict[str, Any]:
    return {
        bucket: {
            "attempted": buckets[bucket]["attempted"],
            "completed": buckets[bucket]["completed"],
            "completion_rate": round(
                buckets[bucket]["completed"] / max(buckets[bucket]["attempted"], 1),
                4,
            ),
            "outcomes": {
                outcome: count
                for outcome, count in sorted(buckets[bucket].items())
                if outcome != "attempted"
            },
        }
        for bucket in order
        if buckets[bucket]["attempted"]
    }


def _pass_causality_summary(
    events: Iterable[dict[str, Any]],
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
) -> dict[str, Any]:
    released_by_team: Counter[str] = Counter()
    completed_by_team: Counter[str] = Counter()
    released_outcomes: Counter[str] = Counter()
    released_outcomes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    released_failures: Counter[str] = Counter()
    outcome_classes: Counter[str] = Counter()
    outcome_classes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    terminal_control_classes: Counter[str] = Counter()
    terminal_control_classes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    release_duels: Counter[str] = Counter()
    release_duel_wins: Counter[str] = Counter()
    by_length: dict[str, Counter[str]] = defaultdict(Counter)
    by_target_kind: dict[str, Counter[str]] = defaultdict(Counter)
    by_distance: dict[str, Counter[str]] = defaultdict(Counter)
    by_profile: dict[str, Counter[str]] = defaultdict(Counter)
    out_of_play_by_stage: Counter[str] = Counter()
    out_of_play_by_restart: Counter[str] = Counter()
    out_of_play_by_distance_and_stage: dict[str, Counter[str]] = defaultdict(Counter)

    def record_release_breakdown(event: dict[str, Any], outcome: str) -> None:
        length = "long" if _event_has_tag(event, "long") else "short"
        target_kind = "space" if _event_has_tag(event, "space") else "feet"
        distance_band = _pass_distance_band(event)
        _pass_breakdown_bucket(by_length, length, outcome)
        _pass_breakdown_bucket(by_target_kind, target_kind, outcome)
        _pass_breakdown_bucket(by_distance, distance_band, outcome)
        _pass_breakdown_bucket(
            by_profile,
            f"{length}:{target_kind}:{distance_band}",
            outcome,
        )

    for event in events:
        team = event.get("team_side")
        if team not in {"home", "away"}:
            continue
        event_type = event.get("event_type")
        outcome = event.get("outcome")
        if event_type == "pass":
            released_by_team[team] += 1
            released_outcomes[str(outcome)] += 1
            released_outcomes_by_team[team][str(outcome)] += 1
            record_release_breakdown(event, str(outcome))
            if outcome == "out_of_play":
                stage = (
                    "residual_free_ball"
                    if _event_has_tag(event, "second_ball")
                    else "direct_flight"
                )
                restart = (
                    "goal_kick"
                    if _event_has_tag(event, "goal_kick")
                    else "corner"
                    if _event_has_tag(event, "corner")
                    else "throw_in"
                    if _event_has_tag(event, "throw_in")
                    else "unknown"
                )
                out_of_play_by_stage[stage] += 1
                out_of_play_by_restart[restart] += 1
                out_of_play_by_distance_and_stage[_pass_distance_band(event)][stage] += 1
            if outcome == "completed":
                completed_by_team[team] += 1
                outcome_class = "completed"
                outcome_classes[outcome_class] += 1
                outcome_classes_by_team[team][outcome_class] += 1
                terminal_control_classes["completed"] += 1
                terminal_control_classes_by_team[team]["completed"] += 1
                continue
            if outcome == "first_touch_error":
                cause = "first_touch_error"
                outcome_class = "technical_failure"
                terminal_control_class = "unresolved_control"
            elif outcome == "offside":
                cause = "offside"
                outcome_class = "offside"
                terminal_control_class = "offside"
            elif outcome == "loose":
                cause = (
                    "delivery_error_loose"
                    if _event_has_tag(event, "delivery_error")
                    else "arrival_loose"
                )
                outcome_class = (
                    "technical_failure"
                    if _event_has_tag(event, "delivery_error")
                    else "unresolved_control"
                )
                terminal_control_class = "unresolved_control"
            elif outcome == "out_of_play":
                cause = "other_out_of_play"
                outcome_class = "out_of_play"
                terminal_control_class = "out_of_play"
            elif outcome == "period_end":
                cause = "other_period_end"
                outcome_class = "period_end_censored"
                terminal_control_class = "period_end_censored"
            else:
                cause = f"other_{outcome}"
                outcome_class = "other_failure"
                terminal_control_class = "other_failure"
            released_failures[cause] += 1
            outcome_classes[outcome_class] += 1
            outcome_classes_by_team[team][outcome_class] += 1
            terminal_control_classes[terminal_control_class] += 1
            terminal_control_classes_by_team[team][terminal_control_class] += 1
        elif event_type == "interception" and _event_has_tag(event, "pass_cut_out"):
            passer_team = "away" if team == "home" else "home"
            released_by_team[passer_team] += 1
            released_outcomes["intercepted"] += 1
            released_outcomes_by_team[passer_team]["intercepted"] += 1
            record_release_breakdown(event, "intercepted")
            cause = (
                "delivery_error_interception"
                if _event_has_tag(event, "delivery_error")
                else "arrival_interception"
            )
            released_failures[cause] += 1
            outcome_class = (
                "technical_failure"
                if _event_has_tag(event, "delivery_error")
                else "opposing_control"
            )
            outcome_classes[outcome_class] += 1
            outcome_classes_by_team[passer_team][outcome_class] += 1
            terminal_control_classes["opposing_control"] += 1
            terminal_control_classes_by_team[passer_team]["opposing_control"] += 1
        elif event_type == "offside" and _event_has_tag(event, "pass_release"):
            released_by_team[team] += 1
            released_outcomes["offside"] += 1
            released_outcomes_by_team[team]["offside"] += 1
            released_failures["offside"] += 1
            outcome_classes["offside"] += 1
            outcome_classes_by_team[team]["offside"] += 1
            terminal_control_classes["offside"] += 1
            terminal_control_classes_by_team[team]["offside"] += 1
            record_release_breakdown(event, "offside")
        elif event_type == "tackle" and _event_has_tag(event, "pass_release"):
            release_duels["attempts"] += 1
            if outcome == "won":
                release_duel_wins["won"] += 1
        elif event_type == "duel" and _event_has_tag(event, "pass_release"):
            release_duels["attempts"] += 1

    attributed_total = sum(released_by_team.values())
    attributed_completed = sum(completed_by_team.values())
    attempted_by_team = {
        "home": int(home_stats.get("passes", 0)),
        "away": int(away_stats.get("passes", 0)),
    }
    completed_by_stat = {
        "home": int(home_stats.get("passes_completed", 0)),
        "away": int(away_stats.get("passes_completed", 0)),
    }
    attempted_total = sum(attempted_by_team.values())
    completed_total = sum(completed_by_stat.values())
    failed_total = max(attempted_total - completed_total, 0)
    attributed_failed_total = sum(released_failures.values())
    unattributed_failed = max(failed_total - attributed_failed_total, 0)
    if unattributed_failed:
        released_failures["unattributed_terminal"] += unattributed_failed
    period_end_non_cross = sum(
        1
        for event in events
        if event.get("event_type") == "pass"
        and event.get("outcome") == "period_end"
        and not _event_has_tag(event, "cross")
    )
    return {
        "attempted": {
            "total": attempted_total,
            **attempted_by_team,
        },
        "completed": completed_total,
        "completed_by_team": completed_by_stat,
        "completion_rate": round(completed_total / max(attempted_total, 1), 4),
        "attributed_releases": {
            "total": attributed_total,
            "home": released_by_team["home"],
            "away": released_by_team["away"],
            "completed": attributed_completed,
        },
        "attributed_outcomes": dict(sorted(released_outcomes.items())),
        "outcome_classes": {
            "definition": (
                "mutually exclusive dominant failure-cause classes; technical_failure "
                "takes precedence over the eventual control state and must not be read "
                "as a terminal-possession partition"
            ),
            "total": dict(sorted(outcome_classes.items())),
            "by_team": {
                team: dict(sorted(outcome_classes_by_team[team].items()))
                for team in ("home", "away")
            },
            "closure": {
                "classified": sum(outcome_classes.values()),
                "attempted": attempted_total,
                "delta": sum(outcome_classes.values()) - attempted_total,
            },
        },
        "terminal_control_classes": {
            "definition": (
                "mutually exclusive terminal disposition of every released pass; "
                "opposing_control includes technically mis-hit deliveries controlled "
                "by the opponent, while unresolved_control includes technical errors "
                "that remain loose"
            ),
            "total": dict(sorted(terminal_control_classes.items())),
            "by_team": {
                team: dict(sorted(terminal_control_classes_by_team[team].items()))
                for team in ("home", "away")
            },
            "closure": {
                "classified": sum(terminal_control_classes.values()),
                "attempted": attempted_total,
                "delta": sum(terminal_control_classes.values()) - attempted_total,
            },
        },
        "period_end_non_cross": period_end_non_cross,
        "attributed_outcomes_by_team": {
            team: dict(sorted(released_outcomes_by_team[team].items()))
            for team in ("home", "away")
        },
        "failure_causes": {
            cause: {
                "count": count,
                "share_of_attempted": round(count / max(attempted_total, 1), 4),
                "share_of_failed": round(count / max(failed_total, 1), 4),
            }
            for cause, count in sorted(released_failures.items())
        },
        "out_of_play": {
            "by_stage": dict(sorted(out_of_play_by_stage.items())),
            "by_restart": dict(sorted(out_of_play_by_restart.items())),
            "by_distance_and_stage": {
                distance_band: dict(sorted(stages.items()))
                for distance_band, stages in sorted(
                    out_of_play_by_distance_and_stage.items()
                )
            },
        },
        "breakdown": {
            "by_length": _pass_breakdown_summary(by_length, ("short", "long")),
            "by_target_kind": _pass_breakdown_summary(
                by_target_kind,
                ("feet", "space"),
            ),
            "by_distance": _pass_breakdown_summary(
                by_distance,
                ("0-10m", "10-20m", "20-30m", "30m+", "unknown"),
            ),
            "by_profile": _pass_breakdown_summary(
                by_profile,
                tuple(sorted(by_profile)),
            ),
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
    if possession_ids:
        observed_possession_id_span = possession_ids[-1] - possession_ids[0] + 1
        missing_possession_ids = observed_possession_id_span - len(possession_ids)
    else:
        observed_possession_id_span = 0
        missing_possession_ids = 0
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
        "scope": (
            "event_observed possession segments only; duration runs from first to last "
            "public event and excludes unlogged held time before, between, or after events"
        ),
        "observability": {
            "first_possession_id": possession_ids[0] if possession_ids else None,
            "last_possession_id": possession_ids[-1] if possession_ids else None,
            "possession_id_span": observed_possession_id_span,
            "observed_possession_ids": len(possession_ids),
            "missing_possession_ids_in_span": missing_possession_ids,
            "all_possession_ids_observed": missing_possession_ids == 0,
        },
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
        "distributions": {
            "duration_seconds": dict(
                sorted(Counter(sequence["duration_seconds"] for sequence in sequences).items())
            ),
            "completed_passes": dict(
                sorted(Counter(sequence["passes"] for sequence in sequences).items())
            ),
            "completed_passes_before_shot": dict(sorted(Counter(shots_by_pass_count).items())),
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


def _held_body_separation_summary(
    replay: Iterable[dict[str, Any]],
    body_separation_m: float = 0.9,
    deep_overlap_m: float = 0.7,
) -> dict[str, Any]:
    def relative_segment_minimum_distance(
        holder_start: list[Any],
        holder_end: list[Any],
        defender_start: list[Any],
        defender_end: list[Any],
    ) -> float:
        relative_start = (
            float(defender_start[0]) - float(holder_start[0]),
            float(defender_start[1]) - float(holder_start[1]),
        )
        relative_end = (
            float(defender_end[0]) - float(holder_end[0]),
            float(defender_end[1]) - float(holder_end[1]),
        )
        relative_delta = (
            relative_end[0] - relative_start[0],
            relative_end[1] - relative_start[1],
        )
        length_squared = (
            relative_delta[0] * relative_delta[0]
            + relative_delta[1] * relative_delta[1]
        )
        progress = (
            max(
                0.0,
                min(
                    1.0,
                    -(
                        relative_start[0] * relative_delta[0]
                        + relative_start[1] * relative_delta[1]
                    )
                    / length_squared,
                ),
            )
            if length_squared > 1e-9
            else 0.0
        )
        return hypot(
            relative_start[0] + relative_delta[0] * progress,
            relative_start[1] + relative_delta[1] * progress,
        )

    replay_frames = [frame for frame in replay if frame.get("type") == "frame"]
    held_frames = 0
    below_body_separation_frames = 0
    deep_overlap_frames = 0
    minimum_separation_m: float | None = None
    samples: list[dict[str, Any]] = []

    for frame in replay_frames:
        if frame.get("ball_flight") is not None:
            continue
        team = frame.get("ball_team")
        holder = frame.get("ball_holder")
        if team not in {"home", "away"} or not isinstance(holder, int):
            continue
        teammates = frame.get(team)
        opponents = frame.get("away" if team == "home" else "home")
        if (
            not isinstance(teammates, list)
            or not isinstance(opponents, list)
            or holder < 0
            or holder >= len(teammates)
            or not opponents
        ):
            continue
        holder_position = teammates[holder]
        if not isinstance(holder_position, list) or len(holder_position) < 2:
            continue

        nearest_index, nearest_distance = min(
            (
                (
                    opponent_index,
                    hypot(
                    float(opponent[0]) - float(holder_position[0]),
                    float(opponent[1]) - float(holder_position[1]),
                    ),
                )
                for opponent_index, opponent in enumerate(opponents)
                if isinstance(opponent, list) and len(opponent) >= 2
            ),
            key=lambda item: item[1],
            default=(-1, float("inf")),
        )
        if nearest_index < 0:
            continue

        held_frames += 1
        minimum_separation_m = (
            nearest_distance
            if minimum_separation_m is None
            else min(minimum_separation_m, nearest_distance)
        )
        if nearest_distance < body_separation_m:
            below_body_separation_frames += 1
        if nearest_distance < deep_overlap_m:
            deep_overlap_frames += 1
            if len(samples) < 8:
                samples.append(
                    {
                        "t": frame.get("t"),
                        "half": frame.get("half"),
                        "team": team,
                        "holder": holder,
                        "defender": nearest_index,
                        "distance_m": round(nearest_distance, 4),
                    }
                )

    continuous_held_intervals = 0
    path_below_body_separation_intervals = 0
    path_deep_overlap_intervals = 0
    minimum_path_separation_m: float | None = None
    path_samples: list[dict[str, Any]] = []
    for start, end in zip(replay_frames, replay_frames[1:]):
        team = start.get("ball_team")
        holder = start.get("ball_holder")
        if (
            start.get("ball_flight") is not None
            or end.get("ball_flight") is not None
            or team not in {"home", "away"}
            or not isinstance(holder, int)
            or end.get("ball_team") != team
            or end.get("ball_holder") != holder
            or float(end.get("t", 0.0)) <= float(start.get("t", 0.0))
        ):
            continue
        start_teammates = start.get(team)
        end_teammates = end.get(team)
        start_opponents = start.get("away" if team == "home" else "home")
        end_opponents = end.get("away" if team == "home" else "home")
        if (
            not isinstance(start_teammates, list)
            or not isinstance(end_teammates, list)
            or not isinstance(start_opponents, list)
            or not isinstance(end_opponents, list)
            or holder < 0
            or holder >= len(start_teammates)
            or holder >= len(end_teammates)
        ):
            continue
        holder_start = start_teammates[holder]
        holder_end = end_teammates[holder]
        if (
            not isinstance(holder_start, list)
            or len(holder_start) < 2
            or not isinstance(holder_end, list)
            or len(holder_end) < 2
        ):
            continue
        path_distances = [
            (
                defender_index,
                relative_segment_minimum_distance(
                    holder_start,
                    holder_end,
                    defender_start,
                    defender_end,
                ),
            )
            for defender_index, (defender_start, defender_end) in enumerate(
                zip(start_opponents, end_opponents)
            )
            if isinstance(defender_start, list)
            and len(defender_start) >= 2
            and isinstance(defender_end, list)
            and len(defender_end) >= 2
        ]
        if not path_distances:
            continue
        defender_index, path_distance = min(path_distances, key=lambda item: item[1])
        continuous_held_intervals += 1
        minimum_path_separation_m = (
            path_distance
            if minimum_path_separation_m is None
            else min(minimum_path_separation_m, path_distance)
        )
        if path_distance < body_separation_m:
            path_below_body_separation_intervals += 1
        if path_distance < deep_overlap_m:
            path_deep_overlap_intervals += 1
            if len(path_samples) < 8:
                path_samples.append(
                    {
                        "start_t": start.get("t"),
                        "end_t": end.get("t"),
                        "half": start.get("half"),
                        "team": team,
                        "holder": holder,
                        "defender": defender_index,
                        "minimum_distance_m": round(path_distance, 4),
                    }
                )

    return {
        "definition": (
            "nearest opponent distance on controlled replay frames with a valid ball holder "
            "and no active or terminal ball flight; "
            "frame endpoints and the relative linear path between continuous held frames are "
            "reported separately because safe endpoints can still render as a body crossing"
        ),
        "body_separation_m": body_separation_m,
        "deep_overlap_m": deep_overlap_m,
        "held_frames": held_frames,
        "minimum_separation_m": (
            round(minimum_separation_m, 4)
            if minimum_separation_m is not None
            else None
        ),
        "below_body_separation_frames": below_body_separation_frames,
        "below_body_separation_rate": round(
            below_body_separation_frames / max(held_frames, 1),
            4,
        ),
        "deep_overlap_frames": deep_overlap_frames,
        "deep_overlap_rate": round(deep_overlap_frames / max(held_frames, 1), 4),
        "deep_overlap_samples": samples,
        "continuous_held_intervals": continuous_held_intervals,
        "minimum_path_separation_m": (
            round(minimum_path_separation_m, 4)
            if minimum_path_separation_m is not None
            else None
        ),
        "path_below_body_separation_intervals": path_below_body_separation_intervals,
        "path_below_body_separation_rate": round(
            path_below_body_separation_intervals
            / max(continuous_held_intervals, 1),
            4,
        ),
        "path_deep_overlap_intervals": path_deep_overlap_intervals,
        "path_deep_overlap_rate": round(
            path_deep_overlap_intervals / max(continuous_held_intervals, 1),
            4,
        ),
        "path_deep_overlap_samples": path_samples,
    }


def summarize_match(
    response: dict[str, Any],
    home_attacking_right: bool = True,
    include_sequences: bool = False,
) -> dict[str, Any]:
    events = response["events"]
    return {
        "score": [response["home_score"], response["away_score"]],
        "match_clock": response.get("match_clock", {}),
        "home_stats": response["home_stats"],
        "away_stats": response["away_stats"],
        "metric_integrity": _metric_integrity_summary(response),
        "pass_causality": _pass_causality_summary(
            events,
            response["home_stats"],
            response["away_stats"],
        ),
        "shot_outcomes": _shot_outcome_summary(events),
        "shot_families": _shot_family_summary(events),
        "shot_release": _shot_release_summary(response),
        "body_challenges": _body_challenge_summary(events),
        "carry_contacts": _carry_contact_summary(events),
        "held_body_separation": _held_body_separation_summary(response["replay"]),
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


def _aggregate_shot_outcomes(
    summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    outcomes = ("goal", "saved", "blocked", "off_target", "period_end")
    by_team = {
        team: Counter(
            {
                outcome: sum(
                    int(summary["shot_outcomes"]["by_team"][team].get(outcome, 0))
                    for summary in summaries
                )
                for outcome in outcomes
            }
        )
        for team in ("home", "away")
    }
    total = Counter(
        {
            outcome: sum(by_team[team][outcome] for team in ("home", "away"))
            for outcome in outcomes
        }
    )
    terminal_count = sum(total.values())
    match_count = max(len(summaries), 1)
    return {
        "total": dict(total),
        "by_team": {team: dict(counts) for team, counts in by_team.items()},
        "per_match": {
            outcome: round(count / match_count, 3)
            for outcome, count in total.items()
        },
        "share": {
            outcome: round(count / max(terminal_count, 1), 4)
            for outcome, count in total.items()
        },
        "terminal_count": terminal_count,
    }


def _all_team_checks_ok(
    summaries: Iterable[dict[str, Any]],
    check_names: Iterable[str],
) -> bool:
    names = tuple(check_names)
    return all(
        all(
            summary["metric_integrity"]["teams"][team]["checks"][check_name][
                "status"
            ]
            == "ok"
            for team in ("home", "away")
            for check_name in names
        )
        for summary in summaries
    )


def _weighted_team_pass_success_rate(
    summaries: Iterable[dict[str, Any]],
    team: str,
) -> float:
    stats_key = f"{team}_stats"
    attempted = 0
    completed = 0
    for summary in summaries:
        stats = summary[stats_key]
        attempted += int(stats.get("passes", 0) or 0)
        completed += int(stats.get("passes_completed", 0) or 0)
    return round(completed / max(attempted, 1) * 100.0, 3)


def _weighted_team_take_on_success_rate(
    summaries: Iterable[dict[str, Any]],
    team: str,
) -> float:
    stats_key = f"{team}_stats"
    attempted = 0
    completed = 0
    for summary in summaries:
        stats = summary[stats_key]
        attempted += int(stats.get("take_ons", 0) or 0)
        completed += int(stats.get("successful_take_ons", 0) or 0)
    return round(completed / max(attempted, 1) * 100.0, 3)


def _body_challenge_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    by_context: dict[str, Counter[str]] = defaultdict(Counter)
    by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    for event in events:
        if event.get("event_type") != "duel" or not _event_has_tag(
            event,
            "body_challenge",
        ):
            continue
        outcome = str(event.get("outcome") or "unknown")
        team = str(event.get("team_side") or "")
        context = next(
            (
                context
                for context, tags in (
                    ("take_on", ("take_on", "take_on_attempt")),
                    ("ball_protection", ("ball_protection",)),
                    ("pass_release", ("pass_release",)),
                    ("shot_release", ("shot_release",)),
                )
                if any(_event_has_tag(event, tag) for tag in tags)
            ),
            "unknown",
        )
        outcomes[outcome] += 1
        by_context[context][outcome] += 1
        if team in by_team:
            by_team[team][outcome] += 1

    def context_summary(context_outcomes: Counter[str]) -> dict[str, Any]:
        terminal = sum(
            context_outcomes[outcome]
            for outcome in ("retained", "released", "won", "loose")
        )
        attacker_continues = (
            context_outcomes["retained"] + context_outcomes["released"]
        )
        return {
            "terminal": terminal,
            "attacker_continues": attacker_continues,
            "defender_wins": context_outcomes["won"],
            "loose": context_outcomes["loose"],
            "attacker_continuation_rate": round(
                attacker_continues / max(terminal, 1),
                4,
            ),
            "outcomes": dict(sorted(context_outcomes.items())),
        }

    total = context_summary(outcomes)
    return {
        "definition": (
            "physical body contacts are separate from formal tackle attempts and "
            "completed take-ons; retained/released means the attacker kept enough "
            "control to continue the current action, not that the defender was beaten"
        ),
        **total,
        "by_context": {
            context: context_summary(context_outcomes)
            for context, context_outcomes in sorted(by_context.items())
        },
        "by_team": {
            team: dict(sorted(team_outcomes.items()))
            for team, team_outcomes in by_team.items()
        },
    }


def _carry_contact_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    by_context: dict[str, Counter[str]] = defaultdict(Counter)
    by_defender_action: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        event_type = str(event.get("event_type") or "")
        outcome = str(event.get("outcome") or "unknown")
        if event_type not in {"duel", "tackle"} or outcome == "attempted":
            continue
        context = next(
            (
                context
                for context, tags in (
                    ("take_on", ("take_on",)),
                    ("ball_protection", ("ball_protection",)),
                )
                if any(_event_has_tag(event, tag) for tag in tags)
            ),
            None,
        )
        if context is None:
            continue
        result = {
            "retained": "attacker_continues",
            "won": "defender_wins",
            "loose": "loose",
        }.get(outcome)
        if result is None:
            continue
        defender_action = (
            "body_challenge"
            if _event_has_tag(event, "body_challenge")
            else "tackle"
            if event_type == "tackle"
            else "other"
        )
        outcomes[result] += 1
        by_context[context][result] += 1
        by_defender_action[defender_action][result] += 1

    def contact_summary(contact_outcomes: Counter[str]) -> dict[str, Any]:
        contacts = sum(contact_outcomes.values())
        return {
            "contacts": contacts,
            "attacker_continues": contact_outcomes["attacker_continues"],
            "defender_wins": contact_outcomes["defender_wins"],
            "loose": contact_outcomes["loose"],
            "attacker_continuation_rate": round(
                contact_outcomes["attacker_continues"] / max(contacts, 1),
                4,
            ),
        }

    return {
        "definition": (
            "all terminal physical contacts during Carry actions, including formal "
            "tackles and non-tackle body challenges; this is an interaction outcome "
            "audit and is not the provider-compatible completed take-on rate"
        ),
        **contact_summary(outcomes),
        "by_context": {
            context: contact_summary(context_outcomes)
            for context, context_outcomes in sorted(by_context.items())
        },
        "by_defender_action": {
            action: contact_summary(action_outcomes)
            for action, action_outcomes in sorted(by_defender_action.items())
        },
    }


def _aggregate_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        return {}

    shot_outcomes = _aggregate_shot_outcomes(summaries)
    shot_families = {
        "definition": summaries[0]["shot_families"]["definition"],
        **{
            family: {
                "shots": sum(
                    int(summary["shot_families"][family]["shots"])
                    for summary in summaries
                ),
                "goals": sum(
                    int(summary["shot_families"][family]["goals"])
                    for summary in summaries
                ),
                "event_xg": round(
                    sum(
                        float(summary["shot_families"][family]["event_xg"])
                        for summary in summaries
                    ),
                    4,
                ),
            }
            for family in ("shoot_action", "carry_finish")
        },
    }
    for family in ("shoot_action", "carry_finish"):
        family_stats = shot_families[family]
        family_stats["xg_per_shot"] = round(
            family_stats["event_xg"] / max(family_stats["shots"], 1),
            4,
        )
        family_stats["goal_conversion_rate"] = round(
            family_stats["goals"] / max(family_stats["shots"], 1),
            4,
        )
    shot_families["closure"] = {
        "classified": sum(
            shot_families[family]["shots"]
            for family in ("shoot_action", "carry_finish")
        ),
        "shot_events": shot_outcomes["terminal_count"],
    }
    shot_families["closure"]["delta"] = (
        shot_families["closure"]["classified"]
        - shot_families["closure"]["shot_events"]
    )
    shot_release_selected = sum(
        int(summary["shot_release"]["selected"]) for summary in summaries
    )
    shot_release_prepared_contacts = sum(
        int(summary["shot_release"]["prepared_contacts"]) for summary in summaries
    )
    shot_release_unreleased = sum(
        int(summary["shot_release"]["unreleased"]) for summary in summaries
    )
    shot_release_abandoned = sum(
        int(summary["shot_release"]["abandoned"]) for summary in summaries
    )
    shot_release_pre_release_duel_losses = sum(
        int(summary["shot_release"]["pre_release_duel_losses"])
        for summary in summaries
    )
    shot_release_released = sum(
        int(summary["shot_release"]["released"]) for summary in summaries
    )
    shot_release_unresolved = sum(
        int(summary["shot_release"]["unresolved"]) for summary in summaries
    )
    shot_release_by_team = {
        team: {
            field: sum(
                int(summary["shot_release"]["by_team"][team][field])
                for summary in summaries
            )
            for field in (
                "selected",
                "prepared_contacts",
                "unreleased",
                "abandoned",
                "pre_release_duel_losses",
                "released",
                "unresolved",
            )
        }
        for team in ("home", "away")
    }
    unreleased_body_probability_weight = sum(
        float(summary["shot_release"]["unreleased_body_probability"]["mean"])
        * int(summary["shot_release"]["unreleased"])
        for summary in summaries
    )
    unreleased_readiness_before_weight = sum(
        float(summary["shot_release"]["unreleased_readiness"]["mean_before"])
        * int(summary["shot_release"]["unreleased"])
        for summary in summaries
    )
    unreleased_readiness_after_weight = sum(
        float(summary["shot_release"]["unreleased_readiness"]["mean_after"])
        * int(summary["shot_release"]["unreleased"])
        for summary in summaries
    )
    total_shots = sum(
        int(summary[team]["shots"])
        for summary in summaries
        for team in ("home_stats", "away_stats")
    )
    total_shots_on_target = sum(
        int(summary[team]["shots_on_target"])
        for summary in summaries
        for team in ("home_stats", "away_stats")
    )
    total_stat_goals = sum(
        int(summary[team]["goals"])
        for summary in summaries
        for team in ("home_stats", "away_stats")
    )
    total_published_team_xg = sum(
        float(summary[team]["xg"])
        for summary in summaries
        for team in ("home_stats", "away_stats")
    )
    total_event_xg = sum(
        float(summary["shot_outcomes"].get("event_xg", {}).get("total", 0.0))
        for summary in summaries
    )
    total_score_goals = sum(
        int(summary["score"][0]) + int(summary["score"][1]) for summary in summaries
    )
    held_body_frames = sum(
        int(summary.get("held_body_separation", {}).get("held_frames", 0))
        for summary in summaries
    )
    held_below_body_separation_frames = sum(
        int(
            summary.get("held_body_separation", {}).get(
                "below_body_separation_frames",
                0,
            )
        )
        for summary in summaries
    )
    held_deep_overlap_frames = sum(
        int(summary.get("held_body_separation", {}).get("deep_overlap_frames", 0))
        for summary in summaries
    )
    held_minimum_separations = [
        float(minimum)
        for summary in summaries
        if (
            minimum := summary.get("held_body_separation", {}).get(
                "minimum_separation_m"
            )
        )
        is not None
    ]
    held_continuous_intervals = sum(
        int(
            summary.get("held_body_separation", {}).get(
                "continuous_held_intervals",
                0,
            )
        )
        for summary in summaries
    )
    held_path_below_body_separation_intervals = sum(
        int(
            summary.get("held_body_separation", {}).get(
                "path_below_body_separation_intervals",
                0,
            )
        )
        for summary in summaries
    )
    held_path_deep_overlap_intervals = sum(
        int(
            summary.get("held_body_separation", {}).get(
                "path_deep_overlap_intervals",
                0,
            )
        )
        for summary in summaries
    )
    held_minimum_path_separations = [
        float(minimum)
        for summary in summaries
        if (
            minimum := summary.get("held_body_separation", {}).get(
                "minimum_path_separation_m"
            )
        )
        is not None
    ]
    match_clock_totals: Counter[str] = Counter()
    ball_state_tick_totals: Counter[str] = Counter()
    for summary in summaries:
        clock = summary.get("match_clock", {})
        for field in (
            "match_seconds",
            "active_play_seconds",
            "dead_ball_seconds",
            "match_ticks",
            "active_play_ticks",
            "dead_ball_ticks",
        ):
            match_clock_totals[field] += float(clock.get(field, 0) or 0)
        ball_state_tick_totals.update(
            {
                state: int(count)
                for state, count in clock.get("ball_state_ticks", {}).items()
            }
        )
    total_pass_attempts = sum(
        int(summary["pass_causality"]["attempted"]["total"]) for summary in summaries
    )
    total_pass_completions = sum(
        int(summary["pass_causality"]["completed"]) for summary in summaries
    )
    pass_attempts_by_team = {
        team: sum(
            int(summary["pass_causality"]["attempted"][team]) for summary in summaries
        )
        for team in ("home", "away")
    }
    pass_completions_by_team = {
        team: sum(
            int(summary["pass_causality"]["completed_by_team"][team])
            for summary in summaries
        )
        for team in ("home", "away")
    }
    pass_outcomes_by_team = {
        team: sum(
            sum(
                int(count)
                for count in summary["pass_causality"]["attributed_outcomes_by_team"][
                    team
                ].values()
            )
            for summary in summaries
        )
        for team in ("home", "away")
    }
    total_attributed_pass_outcomes = sum(
        sum(
            int(count)
            for count in summary["pass_causality"]["attributed_outcomes"].values()
        )
        for summary in summaries
    )
    direction_counts: Counter[str] = Counter()
    terminal_events: Counter[str] = Counter()
    terminal_causes: Counter[str] = Counter()
    pass_count_bands: Counter[str] = Counter()
    terminal_events_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    terminal_causes_by_pass_band: dict[str, Counter[str]] = defaultdict(Counter)
    sequence_distributions: dict[str, Counter[float]] = {
        "duration_seconds": Counter(),
        "completed_passes": Counter(),
        "completed_passes_before_shot": Counter(),
    }
    completed_attack_actions: Counter[str] = Counter()
    pass_outcomes: Counter[str] = Counter()
    pass_failure_causes: Counter[str] = Counter()
    pass_outcome_classes: Counter[str] = Counter()
    pass_outcome_classes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    pass_terminal_control_classes: Counter[str] = Counter()
    pass_terminal_control_classes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    pass_out_of_play_by_stage: Counter[str] = Counter()
    pass_out_of_play_by_restart: Counter[str] = Counter()
    pass_out_of_play_by_distance_and_stage: dict[str, Counter[str]] = defaultdict(
        Counter
    )
    pass_breakdowns: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    pass_release_duel_attempts = 0
    pass_release_duel_wins = 0
    body_challenge_outcomes: Counter[str] = Counter()
    body_challenge_outcomes_by_team: dict[str, Counter[str]] = {
        "home": Counter(),
        "away": Counter(),
    }
    body_challenge_outcomes_by_context: dict[str, Counter[str]] = defaultdict(
        Counter
    )
    carry_contact_outcomes: Counter[str] = Counter()
    carry_contact_outcomes_by_context: dict[str, Counter[str]] = defaultdict(Counter)
    carry_contact_outcomes_by_defender_action: dict[str, Counter[str]] = defaultdict(
        Counter
    )
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
        for metric, distribution in summary["sequence"]["distributions"].items():
            sequence_distributions[metric].update(
                {
                    float(value): int(count)
                    for value, count in distribution.items()
                }
            )
        causality = summary["pass_causality"]
        pass_outcomes.update(causality["attributed_outcomes"])
        pass_outcome_classes.update(
            causality.get("outcome_classes", {}).get("total", {})
        )
        for team in ("home", "away"):
            pass_outcome_classes_by_team[team].update(
                causality.get("outcome_classes", {})
                .get("by_team", {})
                .get(team, {})
            )
        pass_terminal_control_classes.update(
            causality.get("terminal_control_classes", {}).get("total", {})
        )
        for team in ("home", "away"):
            pass_terminal_control_classes_by_team[team].update(
                causality.get("terminal_control_classes", {})
                .get("by_team", {})
                .get(team, {})
            )
        pass_failure_causes.update(
            {
                cause: data["count"]
                for cause, data in causality["failure_causes"].items()
            }
        )
        pass_out_of_play_by_stage.update(causality["out_of_play"]["by_stage"])
        pass_out_of_play_by_restart.update(causality["out_of_play"]["by_restart"])
        for distance_band, stages in causality["out_of_play"][
            "by_distance_and_stage"
        ].items():
            pass_out_of_play_by_distance_and_stage[distance_band].update(stages)
        for dimension, buckets in causality["breakdown"].items():
            for bucket, data in buckets.items():
                pass_breakdowns[dimension][bucket]["attempted"] += int(data["attempted"])
                pass_breakdowns[dimension][bucket]["completed"] += int(data["completed"])
                pass_breakdowns[dimension][bucket].update(
                    {
                        outcome: count
                        for outcome, count in data["outcomes"].items()
                        if outcome != "completed"
                    }
                )
        pass_release_duel_attempts += causality["pass_release_duels"]["attempts"]
        pass_release_duel_wins += causality["pass_release_duels"]["tackles_won"]
        body_challenge_outcomes.update(
            summary.get("body_challenges", {}).get("outcomes", {})
        )
        for team in ("home", "away"):
            body_challenge_outcomes_by_team[team].update(
                summary.get("body_challenges", {})
                .get("by_team", {})
                .get(team, {})
            )
        for context, data in (
            summary.get("body_challenges", {}).get("by_context", {}).items()
        ):
            body_challenge_outcomes_by_context[context].update(
                data.get("outcomes", {})
            )
        carry_contacts = summary.get("carry_contacts", {})
        carry_contact_outcomes.update(
            {
                outcome: int(carry_contacts.get(outcome, 0))
                for outcome in ("attacker_continues", "defender_wins", "loose")
            }
        )
        for context, data in carry_contacts.get("by_context", {}).items():
            carry_contact_outcomes_by_context[context].update(
                {
                    outcome: int(data.get(outcome, 0))
                    for outcome in ("attacker_continues", "defender_wins", "loose")
                }
            )
        for action, data in carry_contacts.get("by_defender_action", {}).items():
            carry_contact_outcomes_by_defender_action[action].update(
                {
                    outcome: int(data.get(outcome, 0))
                    for outcome in ("attacker_continues", "defender_wins", "loose")
                }
            )
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
    failed_passes = total_pass_attempts - total_pass_completions
    attributed_failed_passes = sum(
        count
        for outcome, count in pass_outcomes.items()
        if outcome != "completed"
    )
    pass_breakdown_partition_checks = {
        dimension: {
            "attempted": sum(bucket["attempted"] for bucket in buckets.values()),
            "completed": sum(bucket["completed"] for bucket in buckets.values()),
        }
        for dimension, buckets in pass_breakdowns.items()
    }
    aggregate_integrity_checks = {
        "pass_outcomes_equal_attempts": (
            total_attributed_pass_outcomes == total_pass_attempts
        ),
        "home_pass_outcomes_equal_attempts": (
            pass_outcomes_by_team["home"] == pass_attempts_by_team["home"]
        ),
        "away_pass_outcomes_equal_attempts": (
            pass_outcomes_by_team["away"] == pass_attempts_by_team["away"]
        ),
        "completed_passes_not_above_attempts": (
            total_pass_completions <= total_pass_attempts
        ),
        "home_completed_passes_not_above_attempts": (
            pass_completions_by_team["home"] <= pass_attempts_by_team["home"]
        ),
        "away_completed_passes_not_above_attempts": (
            pass_completions_by_team["away"] <= pass_attempts_by_team["away"]
        ),
        "failed_pass_outcomes_equal_attempts_minus_completions": (
            attributed_failed_passes == failed_passes
        ),
        "pass_outcome_classes_equal_attempts": (
            not pass_outcome_classes
            or sum(pass_outcome_classes.values()) == total_pass_attempts
        ),
        "pass_terminal_control_classes_equal_attempts": (
            not pass_terminal_control_classes
            or sum(pass_terminal_control_classes.values()) == total_pass_attempts
        ),
        "home_pass_outcome_classes_equal_attempts": (
            not pass_outcome_classes_by_team["home"]
            or sum(pass_outcome_classes_by_team["home"].values())
            == pass_attempts_by_team["home"]
        ),
        "away_pass_outcome_classes_equal_attempts": (
            not pass_outcome_classes_by_team["away"]
            or sum(pass_outcome_classes_by_team["away"].values())
            == pass_attempts_by_team["away"]
        ),
        "out_of_play_stages_equal_out_of_play_outcomes": (
            sum(pass_out_of_play_by_stage.values()) == pass_outcomes["out_of_play"]
        ),
        "out_of_play_restarts_equal_out_of_play_outcomes": (
            sum(pass_out_of_play_by_restart.values()) == pass_outcomes["out_of_play"]
        ),
        "pass_breakdowns_partition_attempts": all(
            totals["attempted"] == total_pass_attempts
            for totals in pass_breakdown_partition_checks.values()
        ),
        "pass_breakdowns_partition_completions": all(
            totals["completed"] == total_pass_completions
            for totals in pass_breakdown_partition_checks.values()
        ),
        "all_matches_have_valid_non_cross_pass_partition": all(
            all(
                summary["metric_integrity"]["teams"][team]["checks"][check]["status"]
                == "ok"
                for team in ("home", "away")
                for check in (
                    "non_cross_passes.non_negative",
                    "non_cross_completed_passes.non_negative",
                    "non_cross_completed_passes.subset_of_non_cross_passes",
                )
            )
            for summary in summaries
        ),
        "all_matches_team_stats_equal_player_totals": _all_team_checks_ok(
            summaries,
            (
                f"{team_field}.team_vs_players"
                for team_field in PLAYER_TEAM_STAT_FIELDS
            ),
        ),
        "all_matches_core_events_equal_team_stats": _all_team_checks_ok(
            summaries,
            (
                "shots.team_vs_events",
                "shots_on_target.team_vs_events",
                "goals.team_vs_events",
                "passes_completed.team_vs_events",
                "tackles_won.team_vs_events",
                "interceptions.team_vs_events",
                "corners.team_vs_events",
                "goal_kicks.team_vs_events",
                "throw_ins.team_vs_events",
                "offside_free_kicks.team_vs_events",
            )
        ),
        "all_matches_shot_value_accounting_consistent": _all_team_checks_ok(
            summaries,
            (
                "xg.team_vs_events",
                "xg.team_vs_rounded_players",
                "post_shot_xg.team_vs_rounded_players",
                "post_shot_xg.team_vs_opponent_psxg_faced",
            )
        ),
        "all_matches_shot_creation_accounting_consistent": _all_team_checks_ok(
            summaries,
            (
                "key_passes.players_vs_shot_provenance",
                "assists.players_vs_goal_events",
                "xa.players_vs_shot_provenance",
            )
        ),
        "all_matches_shot_defense_accounting_consistent": _all_team_checks_ok(
            summaries,
            (
                "blocks.team_vs_opponent_shots",
                "saves.team_vs_opponent_shots",
                "goals.team_vs_opponent_goals_conceded",
            )
        ),
        "shots_on_target_not_above_shots": total_shots_on_target <= total_shots,
        "goals_not_above_shots_on_target": total_stat_goals <= total_shots_on_target,
        "score_goals_equal_stat_goals": total_score_goals == total_stat_goals,
        "shot_terminal_outcomes_equal_shots": (
            shot_outcomes["terminal_count"] == total_shots
        ),
        "shot_families_equal_shots": (
            shot_families["closure"]["classified"] == total_shots
            and shot_families["closure"]["delta"] == 0
        ),
        "all_matches_xg_equal_shot_events": all(
            all(
                summary["metric_integrity"]["teams"][team]["checks"][
                    "xg.team_vs_events"
                ]["status"]
                == "ok"
                for team in ("home", "away")
            )
            for summary in summaries
        ),
        "all_matches_shots_on_target_equal_resolved_plus_censored": all(
            all(
                summary["metric_integrity"]["teams"][team]["checks"][
                    "shots_on_target.team_vs_events"
                ]["status"]
                == "ok"
                for team in ("home", "away")
            )
            for summary in summaries
        ),
        "all_matches_shot_outcomes_partition_shots": all(
            all(
                summary["metric_integrity"]["teams"][team]["checks"][
                    "shots.outcome_partition"
                ]["status"]
                == "ok"
                for team in ("home", "away")
            )
            for summary in summaries
        ),
        "ball_state_ticks_equal_match_ticks": (
            sum(ball_state_tick_totals.values())
            == int(match_clock_totals["match_ticks"])
        ),
        "all_matches_free_of_integrity_errors": all(
            int(summary["metric_integrity"]["issue_counts"].get("error", 0)) == 0
            for summary in summaries
        ),
    }

    def average(path: tuple[str, ...]) -> float:
        values = []
        for summary in summaries:
            value: Any = summary
            for key in path:
                value = value[key]
            values.append(float(value))
        return round(mean(values), 3)

    average_home_stats = {
        key: round(mean(float(summary["home_stats"][key]) for summary in summaries), 3)
        for key in PACE_STAT_KEYS
    }
    average_away_stats = {
        key: round(mean(float(summary["away_stats"][key]) for summary in summaries), 3)
        for key in PACE_STAT_KEYS
    }
    mean_match_pass_success_rate = {
        "home": average_home_stats["pass_success_rate"],
        "away": average_away_stats["pass_success_rate"],
    }
    mean_match_take_on_success_rate = {
        team: round(
            mean(
                (
                    float(summary[f"{team}_stats"]["successful_take_ons"])
                    / max(float(summary[f"{team}_stats"]["take_ons"]), 1.0)
                    * 100.0
                )
                for summary in summaries
            ),
            3,
        )
        for team in ("home", "away")
    }
    average_home_stats["pass_success_rate"] = _weighted_team_pass_success_rate(
        summaries,
        "home",
    )
    average_away_stats["pass_success_rate"] = _weighted_team_pass_success_rate(
        summaries,
        "away",
    )

    aggregate = {
        "average_score": {
            "home": round(mean(float(summary["score"][0]) for summary in summaries), 3),
            "away": round(mean(float(summary["score"][1]) for summary in summaries), 3),
        },
        "average_home_stats": average_home_stats,
        "average_away_stats": average_away_stats,
        "rate_diagnostics": {
            "pass_success_rate": {
                "sample_weighted": {
                    "home": average_home_stats["pass_success_rate"],
                    "away": average_away_stats["pass_success_rate"],
                },
                "mean_match_rate": mean_match_pass_success_rate,
                "authoritative": "sample_weighted",
            },
            "take_on_success_rate": {
                "sample_weighted": {
                    team: _weighted_team_take_on_success_rate(summaries, team)
                    for team in ("home", "away")
                },
                "mean_match_rate": mean_match_take_on_success_rate,
                "authoritative": "sample_weighted",
                "definition": (
                    "completed take-ons require a new forward carry duel, an "
                    "attacker-wins outcome, and a later carry position beyond "
                    "the defender's contact body with physical separation; "
                    "continued shielding and repeated contact with the same "
                    "defender do not create additional attempts or wins"
                ),
            },
        },
        "metric_integrity": {
            "status": (
                "ok"
                if all(aggregate_integrity_checks.values())
                else "error"
            ),
            "checks": aggregate_integrity_checks,
            "core_totals": {
                "passes_attempted": total_pass_attempts,
                "passes_completed": total_pass_completions,
                "pass_terminal_outcomes": total_attributed_pass_outcomes,
                "passes_by_team": {
                    team: {
                        "attempted": pass_attempts_by_team[team],
                        "completed": pass_completions_by_team[team],
                        "terminal_outcomes": pass_outcomes_by_team[team],
                    }
                    for team in ("home", "away")
                },
                "shots": total_shots,
                "shot_terminal_outcomes": shot_outcomes["terminal_count"],
                "shots_on_target": total_shots_on_target,
                "stat_goals": total_stat_goals,
                "score_goals": total_score_goals,
            },
            "match_issue_counts": dict(
                sorted(
                    sum(
                        (
                            Counter(summary["metric_integrity"]["issue_counts"])
                            for summary in summaries
                        ),
                        Counter(),
                    ).items()
                )
            ),
            "match_issue_breakdown": {
                "validation_checks": dict(
                    sorted(
                        sum(
                            (
                                Counter(
                                    summary["metric_integrity"]
                                    .get("issue_breakdown", {})
                                    .get("validation_checks", {})
                                )
                                for summary in summaries
                            ),
                            Counter(),
                        ).items()
                    )
                ),
                "compatibility_notices": {
                    "total": sum(
                        int(
                            summary["metric_integrity"]
                            .get("issue_breakdown", {})
                            .get("compatibility_notices", {})
                            .get("total", 0)
                        )
                        for summary in summaries
                    ),
                    "by_field": dict(
                        sorted(
                            sum(
                                (
                                    Counter(
                                        summary["metric_integrity"]
                                        .get("issue_breakdown", {})
                                        .get("compatibility_notices", {})
                                        .get("by_field", {})
                                    )
                                    for summary in summaries
                                ),
                                Counter(),
                            ).items()
                        )
                    ),
                },
            },
        },
        "match_clock": {
            "average_match_seconds": round(
                match_clock_totals["match_seconds"] / len(summaries), 3
            ),
            "average_active_play_seconds": round(
                match_clock_totals["active_play_seconds"] / len(summaries), 3
            ),
            "average_dead_ball_seconds": round(
                match_clock_totals["dead_ball_seconds"] / len(summaries), 3
            ),
            "active_play_ratio": round(
                match_clock_totals["active_play_seconds"]
                / max(match_clock_totals["match_seconds"], 1.0),
                4,
            ),
            "average_ball_state_ticks": {
                state: round(count / len(summaries), 3)
                for state, count in sorted(ball_state_tick_totals.items())
            },
            "ball_state_share_of_match": {
                state: round(
                    count / max(match_clock_totals["match_ticks"], 1.0),
                    4,
                )
                for state, count in sorted(ball_state_tick_totals.items())
            },
            "passes_per_active_play_minute": round(
                total_pass_attempts
                / max(match_clock_totals["active_play_seconds"] / 60.0, 1.0),
                3,
            ),
            "shots_per_active_play_minute": round(
                total_shots
                / max(match_clock_totals["active_play_seconds"] / 60.0, 1.0),
                3,
            ),
        },
        "shot_outcomes": shot_outcomes,
        "shot_families": shot_families,
        "shooting_distribution": {
            "scope": (
                "joint internal diagnostic from formal shot events, including separately "
                "identified carry_finish goals; event xg_exact is authoritative for derived "
                "rates while xg remains a two-decimal display field; published team xG is "
                "rounded per team per match and xG has no provider benchmark in this report"
            ),
            "shots": total_shots,
            "goals": total_score_goals,
            "event_xg": round(total_event_xg, 3),
            "event_xg_exact": total_event_xg,
            "published_team_xg": round(total_published_team_xg, 3),
            "published_rounding_delta": round(
                total_published_team_xg - total_event_xg,
                3,
            ),
            "xg_per_shot": round(total_event_xg / max(total_shots, 1), 4),
            "goal_conversion_rate": round(
                total_score_goals / max(total_shots, 1),
                4,
            ),
            "goals_minus_xg": round(total_score_goals - total_event_xg, 3),
            "goals_per_xg": round(
                total_score_goals / max(total_event_xg, 1e-9),
                4,
            ),
        },
        "shot_release": {
            "scope": summaries[0]["shot_release"]["scope"],
            "selection_source": (
                "decision_trace"
                if all(
                    summary["shot_release"]["selection_source"] == "decision_trace"
                    for summary in summaries
                )
                else "observable_resolution_lower_bound"
            ),
            "selected": shot_release_selected,
            "prepared_contacts": shot_release_prepared_contacts,
            "unreleased": shot_release_unreleased,
            "abandoned": shot_release_abandoned,
            "pre_release_duel_losses": shot_release_pre_release_duel_losses,
            "released": shot_release_released,
            "unresolved": shot_release_unresolved,
            "selection_accounting_status": (
                "ok" if shot_release_unresolved == 0 else "incomplete"
            ),
            "release_rate": round(
                shot_release_released / max(shot_release_selected, 1),
                4,
            ),
            "per_match": {
                "selected": round(shot_release_selected / len(summaries), 3),
                "prepared_contacts": round(
                    shot_release_prepared_contacts / len(summaries),
                    3,
                ),
                "unreleased": round(shot_release_unreleased / len(summaries), 3),
                "abandoned": round(
                    shot_release_abandoned / len(summaries),
                    3,
                ),
                "pre_release_duel_losses": round(
                    shot_release_pre_release_duel_losses / len(summaries),
                    3,
                ),
                "released": round(shot_release_released / len(summaries), 3),
                "unresolved": round(shot_release_unresolved / len(summaries), 3),
            },
            "by_team": {
                team: {
                    **counts,
                    "release_rate": round(
                        counts["released"] / max(counts["selected"], 1),
                        4,
                    ),
                }
                for team, counts in shot_release_by_team.items()
            },
            "unreleased_body_probability_mean": round(
                unreleased_body_probability_weight
                / max(shot_release_unreleased, 1),
                3,
            ),
            "unreleased_readiness_mean_before": round(
                unreleased_readiness_before_weight
                / max(shot_release_unreleased, 1),
                3,
            ),
            "unreleased_readiness_mean_after": round(
                unreleased_readiness_after_weight
                / max(shot_release_unreleased, 1),
                3,
            ),
        },
        "pass_causality": {
            "average_attempted": round(
                mean(
                    float(summary["pass_causality"]["attempted"]["total"])
                    for summary in summaries
                ),
                3,
            ),
            "completion_rate": round(
                total_pass_completions / max(total_pass_attempts, 1),
                4,
            ),
            "mean_match_completion_rate": round(
                mean(float(summary["pass_causality"]["completion_rate"]) for summary in summaries),
                4,
            ),
            "rate_definitions": {
                "completion_rate": (
                    "sample-wide weighted rate: total completed passes / total attempted passes"
                ),
                "mean_match_completion_rate": (
                    "unweighted arithmetic mean of each match's completion rate; diagnostic only"
                ),
                "benchmark_comparison": "completion_rate",
            },
            "sample_integrity": {
                "attempted": total_pass_attempts,
                "completed": total_pass_completions,
                "failed": total_pass_attempts - total_pass_completions,
                "attributed_outcomes": total_attributed_pass_outcomes,
                "by_team": {
                    team: {
                        "attempted": pass_attempts_by_team[team],
                        "completed": pass_completions_by_team[team],
                        "failed": (
                            pass_attempts_by_team[team] - pass_completions_by_team[team]
                        ),
                        "attributed_outcomes": pass_outcomes_by_team[team],
                        "status": (
                            "ok"
                            if pass_outcomes_by_team[team] == pass_attempts_by_team[team]
                            else "error"
                        ),
                    }
                    for team in ("home", "away")
                },
                "status": (
                    "ok"
                    if total_attributed_pass_outcomes == total_pass_attempts
                    and all(
                        pass_outcomes_by_team[team] == pass_attempts_by_team[team]
                        for team in ("home", "away")
                    )
                    else "error"
                ),
            },
            "attributed_outcomes": dict(sorted(pass_outcomes.items())),
            "outcome_classes": {
                "definition": summaries[0]["pass_causality"]["outcome_classes"].get(
                    "definition"
                ),
                "total": dict(sorted(pass_outcome_classes.items())),
                "by_team": {
                    team: dict(sorted(pass_outcome_classes_by_team[team].items()))
                    for team in ("home", "away")
                },
                "closure": {
                    "classified": sum(pass_outcome_classes.values()),
                    "attempted": total_pass_attempts,
                    "delta": sum(pass_outcome_classes.values()) - total_pass_attempts,
                },
            },
            "terminal_control_classes": {
                "definition": summaries[0]["pass_causality"][
                    "terminal_control_classes"
                ].get("definition"),
                "total": dict(sorted(pass_terminal_control_classes.items())),
                "by_team": {
                    team: dict(
                        sorted(pass_terminal_control_classes_by_team[team].items())
                    )
                    for team in ("home", "away")
                },
                "closure": {
                    "classified": sum(pass_terminal_control_classes.values()),
                    "attempted": total_pass_attempts,
                    "delta": (
                        sum(pass_terminal_control_classes.values())
                        - total_pass_attempts
                    ),
                },
            },
            "failure_causes": {
                cause: {
                    "count": count,
                    "share_of_attempted": round(
                        count
                        / max(
                            sum(
                                summary["pass_causality"]["attempted"]["total"]
                                for summary in summaries
                            ),
                            1,
                        ),
                        4,
                    ),
                }
                for cause, count in sorted(pass_failure_causes.items())
            },
            "out_of_play": {
                "by_stage": dict(sorted(pass_out_of_play_by_stage.items())),
                "by_restart": dict(sorted(pass_out_of_play_by_restart.items())),
                "by_distance_and_stage": {
                    distance_band: dict(sorted(stages.items()))
                    for distance_band, stages in sorted(
                        pass_out_of_play_by_distance_and_stage.items()
                    )
                },
            },
            "breakdown": {
                dimension: {
                    bucket: {
                        "attempted": data["attempted"],
                        "completed": data["completed"],
                        "completion_rate": round(
                            data["completed"] / max(data["attempted"], 1),
                            4,
                        ),
                        "outcomes": {
                            outcome: count
                            for outcome, count in sorted(data.items())
                            if outcome != "attempted"
                        },
                    }
                    for bucket, data in buckets.items()
                }
                for dimension, buckets in pass_breakdowns.items()
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
        "body_challenges": {
            "definition": summaries[0]
            .get("body_challenges", {})
            .get("definition"),
            "terminal": sum(
                body_challenge_outcomes[outcome]
                for outcome in ("retained", "released", "won", "loose")
            ),
            "attacker_continues": (
                body_challenge_outcomes["retained"]
                + body_challenge_outcomes["released"]
            ),
            "defender_wins": body_challenge_outcomes["won"],
            "loose": body_challenge_outcomes["loose"],
            "attacker_continuation_rate": round(
                (
                    body_challenge_outcomes["retained"]
                    + body_challenge_outcomes["released"]
                )
                / max(
                    sum(
                        body_challenge_outcomes[outcome]
                        for outcome in ("retained", "released", "won", "loose")
                    ),
                    1,
                ),
                4,
            ),
            "outcomes": dict(sorted(body_challenge_outcomes.items())),
            "by_context": {
                context: {
                    "terminal": sum(
                        outcomes[outcome]
                        for outcome in ("retained", "released", "won", "loose")
                    ),
                    "attacker_continues": (
                        outcomes["retained"] + outcomes["released"]
                    ),
                    "defender_wins": outcomes["won"],
                    "loose": outcomes["loose"],
                    "attacker_continuation_rate": round(
                        (outcomes["retained"] + outcomes["released"])
                        / max(
                            sum(
                                outcomes[outcome]
                                for outcome in (
                                    "retained",
                                    "released",
                                    "won",
                                    "loose",
                                )
                            ),
                            1,
                        ),
                        4,
                    ),
                    "outcomes": dict(sorted(outcomes.items())),
                }
                for context, outcomes in sorted(
                    body_challenge_outcomes_by_context.items()
                )
            },
            "by_team": {
                team: dict(sorted(outcomes.items()))
                for team, outcomes in body_challenge_outcomes_by_team.items()
            },
        },
        "carry_contacts": {
            "definition": summaries[0].get("carry_contacts", {}).get("definition"),
            "contacts": sum(carry_contact_outcomes.values()),
            "attacker_continues": carry_contact_outcomes["attacker_continues"],
            "defender_wins": carry_contact_outcomes["defender_wins"],
            "loose": carry_contact_outcomes["loose"],
            "attacker_continuation_rate": round(
                carry_contact_outcomes["attacker_continues"]
                / max(sum(carry_contact_outcomes.values()), 1),
                4,
            ),
            "by_context": {
                context: {
                    "contacts": sum(outcomes.values()),
                    "attacker_continues": outcomes["attacker_continues"],
                    "defender_wins": outcomes["defender_wins"],
                    "loose": outcomes["loose"],
                    "attacker_continuation_rate": round(
                        outcomes["attacker_continues"]
                        / max(sum(outcomes.values()), 1),
                        4,
                    ),
                }
                for context, outcomes in sorted(
                    carry_contact_outcomes_by_context.items()
                )
            },
            "by_defender_action": {
                action: {
                    "contacts": sum(outcomes.values()),
                    "attacker_continues": outcomes["attacker_continues"],
                    "defender_wins": outcomes["defender_wins"],
                    "loose": outcomes["loose"],
                    "attacker_continuation_rate": round(
                        outcomes["attacker_continues"]
                        / max(sum(outcomes.values()), 1),
                        4,
                    ),
                }
                for action, outcomes in sorted(
                    carry_contact_outcomes_by_defender_action.items()
                )
            },
        },
        "held_body_separation": {
            "definition": summaries[0]
            .get("held_body_separation", {})
            .get("definition"),
            "body_separation_m": summaries[0]
            .get("held_body_separation", {})
            .get("body_separation_m", 0.9),
            "deep_overlap_m": summaries[0]
            .get("held_body_separation", {})
            .get("deep_overlap_m", 0.7),
            "held_frames": held_body_frames,
            "minimum_separation_m": (
                round(min(held_minimum_separations), 4)
                if held_minimum_separations
                else None
            ),
            "below_body_separation_frames": held_below_body_separation_frames,
            "below_body_separation_rate": round(
                held_below_body_separation_frames / max(held_body_frames, 1),
                4,
            ),
            "deep_overlap_frames": held_deep_overlap_frames,
            "deep_overlap_rate": round(
                held_deep_overlap_frames / max(held_body_frames, 1),
                4,
            ),
            "matches_with_deep_overlap": sum(
                int(
                    summary.get("held_body_separation", {}).get(
                        "deep_overlap_frames",
                        0,
                    )
                    > 0
                )
                for summary in summaries
            ),
            "continuous_held_intervals": held_continuous_intervals,
            "minimum_path_separation_m": (
                round(min(held_minimum_path_separations), 4)
                if held_minimum_path_separations
                else None
            ),
            "path_below_body_separation_intervals": (
                held_path_below_body_separation_intervals
            ),
            "path_below_body_separation_rate": round(
                held_path_below_body_separation_intervals
                / max(held_continuous_intervals, 1),
                4,
            ),
            "path_deep_overlap_intervals": held_path_deep_overlap_intervals,
            "path_deep_overlap_rate": round(
                held_path_deep_overlap_intervals
                / max(held_continuous_intervals, 1),
                4,
            ),
            "matches_with_path_deep_overlap": sum(
                int(
                    summary.get("held_body_separation", {}).get(
                        "path_deep_overlap_intervals",
                        0,
                    )
                    > 0
                )
                for summary in summaries
            ),
        },
        "sequence": {
            "average_count": average(("sequence", "sequence_count")),
            "scope": (
                "event_observed possession segments only; durations and conversion rates "
                "exclude unlogged controlled time"
            ),
            "observability": {
                "matches_with_all_possession_ids_observed": sum(
                    summary["sequence"]
                    .get("observability", {})
                    .get("all_possession_ids_observed")
                    is True
                    for summary in summaries
                ),
                "matches_with_missing_possession_ids": sum(
                    summary["sequence"]
                    .get("observability", {})
                    .get("all_possession_ids_observed")
                    is False
                    for summary in summaries
                ),
                "matches_with_unknown_possession_id_observability": sum(
                    "all_possession_ids_observed"
                    not in summary["sequence"].get("observability", {})
                    for summary in summaries
                ),
                "missing_possession_ids_in_span": sum(
                    int(
                        summary["sequence"]
                        .get("observability", {})
                        .get("missing_possession_ids_in_span", 0)
                    )
                    for summary in summaries
                ),
            },
            "median_duration_seconds": round(
                median(_distribution_values(sequence_distributions["duration_seconds"])),
                2,
            )
            if sequence_distributions["duration_seconds"]
            else 0.0,
            "p90_duration_seconds": round(
                _quantile(
                    _distribution_values(sequence_distributions["duration_seconds"]),
                    0.90,
                ),
                2,
            ),
            "median_completed_passes": round(
                median(_distribution_values(sequence_distributions["completed_passes"])),
                2,
            )
            if sequence_distributions["completed_passes"]
            else 0.0,
            "p90_completed_passes": round(
                _quantile(
                    _distribution_values(sequence_distributions["completed_passes"]),
                    0.90,
                ),
                2,
            ),
            "shot_sequence_rate": round(
                sum(sequence_distributions["completed_passes_before_shot"].values())
                / max(sum(pass_count_bands.values()), 1),
                4,
            ),
            "median_completed_passes_before_shot": round(
                median(
                    _distribution_values(
                        sequence_distributions["completed_passes_before_shot"]
                    )
                ),
                2,
            )
            if sequence_distributions["completed_passes_before_shot"]
            else 0.0,
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
    aggregate["premier_league_alignment"] = _premier_league_alignment(summaries)
    return aggregate


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _premier_league_alignment(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    benchmark = PREMIER_LEAGUE_2024_25_BENCHMARK
    match_count = len(summaries)
    target_matches = float(benchmark["matches"])
    totals = benchmark["totals"]
    home_away = benchmark["home_away"]
    targets = {
        "passes": totals["passes"] / target_matches,
        "pass_success_rate": totals["passes_completed"] / totals["passes"] * 100.0,
        "shots": totals["shots"] / target_matches,
        "shots_on_target": totals["shots_on_target"] / target_matches,
        "shots_on_target_share": totals["shots_on_target"] / totals["shots"] * 100.0,
        "provider_shooting_accuracy": (
            totals["shots_on_target"]
            / (totals["shots"] - totals["blocked_shots"])
            * 100.0
        ),
        "goals": totals["goals"] / target_matches,
        "goal_conversion_rate": totals["goals"] / totals["shots"] * 100.0,
        "home_goals": home_away["home_goals"] / target_matches,
        "away_goals": home_away["away_goals"] / target_matches,
        "home_shots": home_away["home_shots"] / target_matches,
        "away_shots": home_away["away_shots"] / target_matches,
        "home_shots_on_target": home_away["home_shots_on_target"] / target_matches,
        "away_shots_on_target": home_away["away_shots_on_target"] / target_matches,
    }

    def calculate(sample: list[dict[str, Any]]) -> dict[str, float]:
        home = [summary["home_stats"] for summary in sample]
        away = [summary["away_stats"] for summary in sample]
        raw_attempted = sum(float(stats["passes"]) for stats in home + away)
        raw_completed = sum(float(stats["passes_completed"]) for stats in home + away)
        crosses = sum(float(stats["crosses"]) for stats in home + away)
        completed_crosses = sum(
            float(stats["crosses_completed"]) for stats in home + away
        )
        comparable_open_play_attempted = max(raw_attempted - crosses, 0.0)
        comparable_open_play_completed = max(
            raw_completed - completed_crosses,
            0.0,
        )
        censored_non_cross_pass_outcomes = sum(
            float(
                summary.get("pass_causality", {}).get(
                    "period_end_non_cross",
                    summary.get("pass_causality", {})
                    .get("attributed_outcomes", {})
                    .get("period_end", 0),
                )
            )
            for summary in sample
        )
        shots = sum(float(stats["shots"]) for stats in home + away)
        raw_shots_on_target = sum(
            float(stats["shots_on_target"]) for stats in home + away
        )
        censored_on_target = sum(
            float(summary["shot_outcomes"].get("censored_on_target", {}).get("total", 0))
            for summary in sample
        )
        resolved_shots_on_target = max(
            raw_shots_on_target - censored_on_target,
            0.0,
        )
        home_censored_on_target = sum(
            float(summary["shot_outcomes"].get("censored_on_target", {}).get("home", 0))
            for summary in sample
        )
        away_censored_on_target = sum(
            float(summary["shot_outcomes"].get("censored_on_target", {}).get("away", 0))
            for summary in sample
        )
        blocked_shots = sum(
            float(summary["shot_outcomes"]["total"]["blocked"])
            for summary in sample
        )
        missing_goal_kick_pass_candidates = sum(
            float(stats.get("goal_kicks", 0)) for stats in home + away
        )
        missing_corner_pass_candidates = sum(
            float(stats.get("corners", 0)) for stats in home + away
        )
        missing_offside_free_kick_pass_candidates = sum(
            float(stats.get("offside_free_kicks", 0)) for stats in home + away
        )
        missing_restart_pass_candidates = (
            missing_goal_kick_pass_candidates
            + missing_corner_pass_candidates
            + missing_offside_free_kick_pass_candidates
        )
        comparable_pass_attempts_lower = comparable_open_play_attempted
        comparable_pass_attempts_upper = (
            comparable_pass_attempts_lower + missing_restart_pass_candidates
        )
        comparable_open_play_success_rate = (
            comparable_open_play_completed
            / max(comparable_open_play_attempted, 1.0)
            * 100.0
        )
        comparable_pass_success_lower = (
            comparable_open_play_completed
            / max(comparable_pass_attempts_upper, 1.0)
            * 100.0
        )
        restart_only_pass_success_upper = (
            comparable_open_play_completed + missing_restart_pass_candidates
        ) / max(comparable_pass_attempts_upper, 1.0) * 100.0
        comparable_pass_success_upper = (
            comparable_open_play_completed
            + censored_non_cross_pass_outcomes
            + missing_restart_pass_candidates
        ) / max(comparable_pass_attempts_upper, 1.0) * 100.0
        divisor = max(len(sample), 1)
        return {
            "passes": comparable_pass_attempts_lower / divisor,
            "pass_success_rate": comparable_open_play_success_rate,
            "shots": shots / divisor,
            "shots_on_target": resolved_shots_on_target / divisor,
            "shots_on_target_share": (
                resolved_shots_on_target / max(shots, 1.0) * 100.0
            ),
            "provider_shooting_accuracy": (
                resolved_shots_on_target / max(shots - blocked_shots, 1.0) * 100.0
            ),
            "goals": sum(float(summary["score"][0] + summary["score"][1]) for summary in sample)
            / divisor,
            "goal_conversion_rate": (
                sum(
                    float(summary["score"][0] + summary["score"][1])
                    for summary in sample
                )
                / max(shots, 1.0)
                * 100.0
            ),
            "home_goals": sum(float(summary["score"][0]) for summary in sample) / divisor,
            "away_goals": sum(float(summary["score"][1]) for summary in sample) / divisor,
            "home_shots": sum(float(stats["shots"]) for stats in home) / divisor,
            "away_shots": sum(float(stats["shots"]) for stats in away) / divisor,
            "home_shots_on_target": max(
                sum(float(stats["shots_on_target"]) for stats in home)
                - home_censored_on_target,
                0.0,
            ) / divisor,
            "away_shots_on_target": max(
                sum(float(stats["shots_on_target"]) for stats in away)
                - away_censored_on_target,
                0.0,
            ) / divisor,
            "_raw_engine_passes": raw_attempted / divisor,
            "_engine_crosses_excluded": crosses / divisor,
            "_engine_completed_crosses_excluded": completed_crosses / divisor,
            "_comparable_open_play_passes": comparable_open_play_attempted / divisor,
            "_comparable_open_play_completed": comparable_open_play_completed / divisor,
            "_missing_goal_kick_pass_candidates": (
                missing_goal_kick_pass_candidates / divisor
            ),
            "_missing_corner_pass_candidates": missing_corner_pass_candidates / divisor,
            "_missing_offside_free_kick_pass_candidates": (
                missing_offside_free_kick_pass_candidates / divisor
            ),
            "_missing_restart_pass_candidates": (
                missing_restart_pass_candidates / divisor
            ),
            "_censored_non_cross_pass_outcomes": (
                censored_non_cross_pass_outcomes / divisor
            ),
            "_raw_engine_shots_on_target": raw_shots_on_target / divisor,
            "_censored_on_target": censored_on_target / divisor,
            "_pass_success_rate_lower_bound": comparable_pass_success_lower,
            "_restart_only_pass_success_rate_upper_bound": (
                restart_only_pass_success_upper
            ),
            "_pass_success_rate_upper_bound": comparable_pass_success_upper,
            "_shots_on_target_upper_bound": (
                resolved_shots_on_target + blocked_shots + censored_on_target
            ) / divisor,
            "_shots_on_target_share_lower_bound": (
                resolved_shots_on_target / max(shots, 1.0) * 100.0
            ),
            "_shots_on_target_share_upper_bound": (
                (resolved_shots_on_target + blocked_shots + censored_on_target)
                / max(shots, 1.0)
                * 100.0
            ),
            "_provider_shooting_accuracy_lower_bound": (
                resolved_shots_on_target
                / max(shots - blocked_shots, 1.0)
                * 100.0
            ),
            "_provider_shooting_accuracy_upper_bound": (
                (resolved_shots_on_target + blocked_shots + censored_on_target)
                / max(shots, 1.0)
                * 100.0
            ),
        }

    current = calculate(summaries)
    current["provider_shooting_accuracy"] = current[
        "_provider_shooting_accuracy_lower_bound"
    ]
    current["shots_on_target_share"] = current[
        "_shots_on_target_share_lower_bound"
    ]
    comparison_intervals = {
        "shots_on_target": (
            current["shots_on_target"],
            current["_shots_on_target_upper_bound"],
        ),
        "provider_shooting_accuracy": (
            current["_provider_shooting_accuracy_lower_bound"],
            current["_provider_shooting_accuracy_upper_bound"],
        ),
        "shots_on_target_share": (
            current["_shots_on_target_share_lower_bound"],
            current["_shots_on_target_share_upper_bound"],
        ),
    }
    comparability = {
        "passes": "incomplete_lower_observation",
        "pass_success_rate": "known_scope_sensitivity_only",
        "shots": "direct",
        "shots_on_target": "bounded",
        "shots_on_target_share": "bounded",
        "provider_shooting_accuracy": "bounded",
        "goals": "direct",
        "goal_conversion_rate": "derived_direct",
        "home_goals": "confounded",
        "away_goals": "confounded",
        "home_shots": "confounded",
        "away_shots": "confounded",
        "home_shots_on_target": "confounded_bounded",
        "away_shots_on_target": "confounded_bounded",
    }
    optimization_safety = {
        "passes": (
            False,
            "missing simulated goal-kick, corner, and free-kick deliveries prevent attributing the total gap only to open-play passing",
        ),
        "pass_success_rate": (
            False,
            "provider scope is only partially bounded while goal-kick, corner, and free-kick delivery outcomes are not simulated",
        ),
        "shots": (
            False,
            "penalties, ordinary foul free kicks, and physical corner deliveries are not fully modelled",
        ),
        "shots_on_target": (
            False,
            "last-line blocks are not distinguished and some set-piece shot families are absent",
        ),
        "shots_on_target_share": (
            False,
            "last-line blocks are not distinguished and some set-piece shot families are absent",
        ),
        "provider_shooting_accuracy": (
            False,
            "block type is unresolved and missing set-piece shot families may have a different accuracy mix",
        ),
        "goals": (
            False,
            "the final score is directly comparable but missing penalty and set-piece mechanisms make the gap unsafe as an open-play finishing target",
        ),
        "goal_conversion_rate": (
            False,
            "the ratio directly exposes the joint shot-volume and scoring distribution, but missing set-piece shot families make it unsafe as an isolated finishing calibration target",
        ),
        "home_goals": (
            False,
            "fixed-side squad strength is confounded with home advantage and set-piece mechanisms are incomplete",
        ),
        "away_goals": (
            False,
            "fixed-side squad strength is confounded with home advantage and set-piece mechanisms are incomplete",
        ),
        "home_shots": (
            False,
            "fixed-side squad strength is confounded with home advantage and set-piece mechanisms are incomplete",
        ),
        "away_shots": (
            False,
            "fixed-side squad strength is confounded with home advantage and set-piece mechanisms are incomplete",
        ),
        "home_shots_on_target": (
            False,
            "side assignment, block classification, and missing set-piece mechanisms are confounded",
        ),
        "away_shots_on_target": (
            False,
            "side assignment, block classification, and missing set-piece mechanisms are confounded",
        ),
    }
    bootstrap_values: dict[str, list[float]] = {
        metric: [] for metric in targets
    }
    if match_count > 1:
        rng = random.Random(202425)
        for _ in range(4000):
            sample = [summaries[rng.randrange(match_count)] for _ in range(match_count)]
            sampled = calculate(sample)
            for metric, value in sampled.items():
                if metric not in bootstrap_values:
                    continue
                bootstrap_values[metric].append(value)

    metrics = {}
    for metric, target in targets.items():
        value = current[metric]
        samples = bootstrap_values[metric]
        comparison_interval = comparison_intervals.get(metric)
        direct_observation_eligible = comparability[metric] in {
            "direct",
            "derived_direct",
        }
        calibration_eligible = (
            direct_observation_eligible and optimization_safety[metric][0]
        )
        if comparison_interval is not None:
            lower, upper = comparison_interval
            if target < lower:
                target_relation = "below_interval"
                current_relation_to_target = "above_target"
            elif target > upper:
                target_relation = "above_interval"
                current_relation_to_target = "below_target"
            else:
                target_relation = "within_interval"
                current_relation_to_target = "target_within_current_interval"
        elif direct_observation_eligible:
            target_relation = (
                "below_point"
                if target < value
                else "above_point"
                if target > value
                else "equal"
            )
            current_relation_to_target = (
                "above_target"
                if value > target
                else "below_target"
                if value < target
                else "equal"
            )
        else:
            target_relation = "not_directly_comparable"
            current_relation_to_target = "not_directly_comparable"
        metrics[metric] = {
            "current": round(value, 3),
            "current_95_ci": [
                round(_percentile(samples, 0.025), 3) if samples else round(value, 3),
                round(_percentile(samples, 0.975), 3) if samples else round(value, 3),
            ],
            "comparison_interval": (
                [round(comparison_interval[0], 3), round(comparison_interval[1], 3)]
                if comparison_interval is not None
                else None
            ),
            "target": round(target, 3),
            "target_relation": target_relation,
            "current_relation_to_target": current_relation_to_target,
            "direct_observation_eligible": direct_observation_eligible,
            "calibration_eligible": calibration_eligible,
            "absolute_gap": round(value - target, 3) if calibration_eligible else None,
            "relative_gap": (
                round(value / target - 1.0, 4) if calibration_eligible else None
            ),
            "comparison_status": comparability[metric],
            "optimization_safe": optimization_safety[metric][0],
            "optimization_caveat": optimization_safety[metric][1],
        }
        if metric == "pass_success_rate":
            metrics[metric]["known_scope_sensitivity_interval"] = [
                round(current["_pass_success_rate_lower_bound"], 3),
                round(current["_pass_success_rate_upper_bound"], 3),
            ]
    return {
        "benchmark": {
            **benchmark,
            "metric_mapping": {
                "passes": (
                    "Opta total_pass includes open-play passes, goal kicks, corners, and free "
                    "kicks taken as passes; it excludes crosses, throw-ins, and goalkeeper "
                    "throws. Engine pass actions currently combine open-play passes and crosses "
                    "but do not simulate restart deliveries as pass actions. The reported lower "
                    "observation subtracts engine-classified crosses. Goal kicks, corners, and "
                    "offside free kicks are exposed as known missing pass candidates, but "
                    "ordinary foul free kicks are not modelled or counted, so the result is not "
                    "a complete provider-scope bound."
                ),
                "passes_completed": (
                    "Opta accurate_pass excludes crosses. Engine completed passes ending in "
                    "stable same-team control without material opponent contact are reduced by "
                    "completed crosses. Period-end pass flights retain their attempts but have an "
                    "unknown completion outcome. The reported sensitivity range treats those "
                    "censored flights and every known goal-kick, corner, and offside-free-kick "
                    "candidate as failed versus completed. "
                    "It is not a complete bound because ordinary foul free-kick deliveries are "
                    "absent."
                ),
                "shots": (
                    "Opta total_scoring_att; compared with released shots including blocked "
                    "and off-target attempts"
                ),
                "shots_on_target": (
                    "Opta ontarget_scoring_att includes goals, goalkeeper saves, and last-line "
                    "blocks. Engine shots_on_target also includes on-target flights censored by "
                    "period end. The reported lower bound keeps only resolved goals and saves; "
                    "the upper bound additionally treats every block and censored on-target "
                    "flight as provider on target."
                ),
                "shots_on_target_share": (
                    "Provider shots on target divided by all shots. The engine lower endpoint "
                    "uses resolved goals and saves; the upper endpoint also treats every blocked "
                    "and period-end on-target attempt as provider on target."
                ),
                "provider_shooting_accuracy": (
                    "Opta shooting accuracy is shots on target divided by shots excluding "
                    "ordinary blocked attempts. Because engine blocks do not distinguish "
                    "ordinary blocks from last-line blocks and period-end flights have no "
                    "resolved terminal outcome, the lower endpoint is resolved goals and saves "
                    "divided by non-blocked shots. The upper endpoint treats every block and "
                    "censored on-target flight as on target."
                ),
                "home_away_splits": (
                    "Side-specific engine values are confounded when the same two squads stay "
                    "on fixed home and away sides across seeds. Diagnose home advantage only "
                    "from equal-squad or paired fixtures with the squads swapped."
                ),
                "goals": "Opta goals; compared with the final match score",
                "goal_conversion_rate": (
                    "final goals divided by all released shots; use as a joint distribution "
                    "diagnostic rather than an isolated finishing target because penalty and "
                    "set-piece shot families are incomplete"
                ),
                "optimization_use": (
                    "Direct statistical comparability does not imply that a point gap is safe "
                    "to close by tuning the open-play mechanism. Penalties, ordinary foul free "
                    "kicks, and physical corner deliveries are not fully represented."
                ),
            },
            "comparability": comparability,
            "source_consistency": {
                **benchmark["source_consistency"],
                "status": (
                    "exact"
                    if all(
                        delta == 0
                        for key, delta in benchmark["source_consistency"].items()
                        if key.endswith("_delta")
                    )
                    else "documented_difference"
                ),
            },
        },
        "sample_matches": match_count,
        "metrics": metrics,
        "engine_scope_diagnostics": {
            "raw_released_passes_per_match": round(current["_raw_engine_passes"], 3),
            "crosses_excluded_from_opta_pass_comparison_per_match": round(
                current["_engine_crosses_excluded"], 3
            ),
            "completed_crosses_excluded_from_opta_pass_comparison_per_match": round(
                current["_engine_completed_crosses_excluded"], 3
            ),
            "comparable_open_play_passes_per_match": round(
                current["_comparable_open_play_passes"], 3
            ),
            "comparable_open_play_completed_passes_per_match": round(
                current["_comparable_open_play_completed"], 3
            ),
            "goal_kick_pass_candidates_missing_from_engine_pass_actions_per_match": round(
                current["_missing_goal_kick_pass_candidates"], 3
            ),
            "corner_pass_candidates_missing_from_engine_pass_actions_per_match": round(
                current["_missing_corner_pass_candidates"], 3
            ),
            "offside_free_kick_pass_candidates_missing_from_engine_pass_actions_per_match": round(
                current["_missing_offside_free_kick_pass_candidates"], 3
            ),
            "restart_pass_candidate_upper_bound_per_match": round(
                current["_missing_restart_pass_candidates"], 3
            ),
            "known_restart_pass_attempt_sensitivity_range_per_match": [
                round(current["passes"], 3),
                round(
                    current["passes"]
                    + current["_missing_restart_pass_candidates"],
                    3,
                ),
            ],
            "known_restart_pass_success_rate_sensitivity_range": [
                round(current["_pass_success_rate_lower_bound"], 3),
                round(current["_restart_only_pass_success_rate_upper_bound"], 3),
            ],
            "known_scope_pass_success_rate_sensitivity_range": [
                round(current["_pass_success_rate_lower_bound"], 3),
                round(current["_pass_success_rate_upper_bound"], 3),
            ],
            "period_end_pass_outcomes_censored_per_match": round(
                current["_censored_non_cross_pass_outcomes"],
                3,
            ),
            "shots_on_target_comparable_interval_per_match": [
                round(current["shots_on_target"], 3),
                round(current["_shots_on_target_upper_bound"], 3),
            ],
            "raw_engine_shots_on_target_per_match": round(
                current["_raw_engine_shots_on_target"],
                3,
            ),
            "period_end_on_target_censored_per_match": round(
                current["_censored_on_target"],
                3,
            ),
            "provider_shooting_accuracy_comparable_interval": [
                round(current["_provider_shooting_accuracy_lower_bound"], 3),
                round(current["_provider_shooting_accuracy_upper_bound"], 3),
            ],
            "shots_on_target_share_comparable_interval": [
                round(current["_shots_on_target_share_lower_bound"], 3),
                round(current["_shots_on_target_share_upper_bound"], 3),
            ],
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
