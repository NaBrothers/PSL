#!/usr/bin/env python3
"""Run deterministic Rust-engine invariants against real local squads."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_cards(db, qq: int) -> tuple[list[dict], str]:
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
        abilities = {key: value["value"] for key, value in detail["abilities"].items()}
        base_overall = card_info.overall - STARS[card_info.star]["ability"]
        cards.append(
            {
                "name": card_info.name,
                "player_id": card_info.player_id,
                "position": card_info.position,
                "color": get_color_code(base_overall, card_info.star),
                "overall": card_info.real_overall,
                "abilities": abilities,
            }
        )
    return cards, squad.formation


def _distance(a: list[float], b: list[float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _scan_match(response: dict) -> dict:
    entries = response["trace"]["entries"]
    events = response["events"]
    same_position_seconds: dict[str, int] = {}
    max_same_position_seconds = 0
    prior_holder: tuple[str, list[float], float] | None = None
    for frame in response["replay"]:
        if frame.get("type") != "frame":
            continue
        holder_idx = frame.get("ball_holder")
        team = frame.get("ball_team")
        if holder_idx is None or team not in {"home", "away"}:
            prior_holder = None
            continue
        positions = frame[team]
        if not isinstance(holder_idx, int) or holder_idx >= len(positions):
            prior_holder = None
            continue
        pos = positions[holder_idx]
        holder_key = f"{team}:{holder_idx}"
        time_value = float(frame["t"])
        if (
            prior_holder is not None
            and prior_holder[0] == holder_key
            and _distance(prior_holder[1], pos) < 0.05
        ):
            same_position_seconds[holder_key] = int(
                same_position_seconds.get(holder_key, 0) + (time_value - prior_holder[2])
            )
        else:
            same_position_seconds[holder_key] = 0
        max_same_position_seconds = max(
            max_same_position_seconds, same_position_seconds[holder_key]
        )
        prior_holder = (holder_key, pos, time_value)

    long_shots = [
        event
        for event in events
        if event["event_type"] == "shot"
        and event["origin"] is not None
        and event["target"] is not None
        and _distance(event["origin"], event["target"]) > 50.0
    ]
    attacker_wins = [
        entry
        for entry in entries
        if entry.get("event") == "duel" and entry.get("outcome") == "attacker_wins"
    ]
    carries = [entry for entry in entries if entry.get("action") == "carry"]
    return {
        "home_score": response["home_score"],
        "away_score": response["away_score"],
        "home_possession": response["home_stats"]["possession"],
        "away_possession": response["away_stats"]["possession"],
        "max_same_position_seconds": max_same_position_seconds,
        "long_shots_over_50m": len(long_shots),
        "attacker_won_duels": len(attacker_wins),
        "carries": len(carries),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "psl.db")
    parser.add_argument("--home-qq", type=int, default=10001)
    parser.add_argument("--away-qq", type=int, default=10003)
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--start-seed", type=int, default=1)
    args = parser.parse_args()

    from psl_core.engine_v2 import EngineConfig
    from psl_core.engine_v2.rust_bridge import run_match
    from server.database import Database
    from server.services.game_config import GameConfigService

    with tempfile.TemporaryDirectory(prefix="psl-engine-v2-real-squads-") as temp_dir:
        db_path = Path(temp_dir) / "psl.db"
        # A plain file copy omits uncheckpointed WAL pages from a running server.
        # SQLite backup produces a self-contained, transactionally consistent snapshot.
        with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as source:
            with sqlite3.connect(db_path) as destination:
                source.backup(destination)
        db = Database(str(db_path))
        try:
            home_cards, home_formation = _build_cards(db, args.home_qq)
            away_cards, away_formation = _build_cards(db, args.away_qq)
            config = EngineConfig()
            config_service = GameConfigService(db)
            for key in (
                "tick_duration",
                "shot_on_target_base",
                "gk_save_base",
                "press_radius",
                "player_max_speed",
                "goal_noise_scale",
                "iq_noise_scale",
            ):
                setattr(config, key, type(getattr(config, key))(config_service.get(f"engine_v2.{key}")))

            matches = []
            for seed in range(args.start_seed, args.start_seed + args.seeds):
                response = run_match(
                    home_cards,
                    away_cards,
                    home_formation,
                    away_formation,
                    config,
                    seed=seed,
                )
                matches.append({"seed": seed, **_scan_match(response)})
        finally:
            db.close()

    total = len(matches)
    summary = {
        "match_count": total,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "avg_home_goals": round(sum(match["home_score"] for match in matches) / total, 3),
        "avg_away_goals": round(sum(match["away_score"] for match in matches) / total, 3),
        "max_same_position_seconds": max(
            match["max_same_position_seconds"] for match in matches
        ),
        "matches_with_120s_same_position_hold": sum(
            match["max_same_position_seconds"] >= 120 for match in matches
        ),
        "long_shots_over_50m": sum(
            match["long_shots_over_50m"] for match in matches
        ),
        "max_possession_pct": max(
            max(match["home_possession"], match["away_possession"]) for match in matches
        ),
        "min_attacker_won_duels": min(match["attacker_won_duels"] for match in matches),
        "min_carries": min(match["carries"] for match in matches),
        "seed_results": matches,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    failures = []
    if summary["matches_with_120s_same_position_hold"] > 0:
        failures.append("found held-ball runs at one position for at least 120 seconds")
    if summary["long_shots_over_50m"] > 0:
        failures.append("found shots longer than 50m")
    if summary["min_attacker_won_duels"] > 0 and summary["min_carries"] == 0:
        failures.append("attacker-won duels did not produce any carries")
    if failures:
        print("\nFAILURES:", *failures, sep="\n- ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
