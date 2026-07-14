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


def _sequence_summary(
    events: Iterable[dict[str, Any]],
    home_attacking_right: bool,
    include_sequences: bool = False,
) -> dict[str, Any]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        team = event.get("team_side")
        possession_id = event.get("possession_id")
        if team in {"home", "away"} and isinstance(possession_id, int):
            grouped[(team, possession_id)].append(event)

    sequences = []
    pass_directions: Counter[str] = Counter()
    terminal_events: Counter[str] = Counter()
    shots_by_pass_count: list[int] = []
    for (team, possession_id), sequence_events in grouped.items():
        ordered = sorted(sequence_events, key=lambda event: (event["tick"], event["seq"]))
        passes = [
            event
            for event in ordered
            if event["event_type"] == "pass" and event.get("outcome") == "completed"
        ]
        for event in passes:
            origin = event.get("origin")
            target = event.get("target")
            if isinstance(origin, list) and isinstance(target, list):
                pass_directions[_classify_pass(origin, target, team == "home" and home_attacking_right or team == "away" and not home_attacking_right)] += 1
        terminal = ordered[-1]["event_type"]
        terminal_events[terminal] += 1
        shot = next((event for event in ordered if event["event_type"] == "shot"), None)
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
        "sequence": _sequence_summary(events, home_attacking_right, include_sequences),
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
    for summary in summaries:
        for direction, data in summary["sequence"]["pass_directions"].items():
            direction_counts[direction] += data["count"]
        terminal_events.update(summary["sequence"]["terminal_events"])
    direction_total = sum(direction_counts.values())

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
