#!/usr/bin/env python3
"""Build one representative PGO training request from complete real squads."""

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


def complete_squad_users(db) -> list[int]:
    rows = db.query_all(
        """
        SELECT u.QQ
        FROM users AS u
        JOIN team AS t ON t.User = u.QQ
        WHERE t.Position BETWEEN 0 AND 10 AND t.Card > 0
        GROUP BY u.QQ
        HAVING COUNT(DISTINCT t.Position) = 11
        ORDER BY u.QQ
        LIMIT 2
        """
    )
    return [int(row[0]) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "psl.db")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260824)
    args = parser.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"database does not exist: {args.db}")

    from psl_core.engine_v2 import load_config_from_service
    from scripts.validate_engine_v2_real_squads import _build_cards
    from server.database import Database
    from server.services.game_config import GameConfigService

    with tempfile.TemporaryDirectory(prefix="psl-auto-pgo-db-") as temp_dir:
        snapshot = Path(temp_dir) / "psl.db"
        source_uri = f"{args.db.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        db = Database(str(snapshot))
        try:
            users = complete_squad_users(db)
            if not users:
                raise SystemExit(
                    "database has no complete eleven-player squad for PGO training"
                )
            home_qq = users[0]
            away_qq = users[1] if len(users) > 1 else users[0]
            home_cards, home_formation = _build_cards(db, home_qq)
            away_cards, away_formation = _build_cards(db, away_qq)
            config = load_config_from_service(GameConfigService(db))
        finally:
            db.close()

    request = {
        "home_cards": home_cards,
        "away_cards": away_cards,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "config": config.to_rust_payload(),
        "seed": args.seed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"PGO request: {home_qq} ({home_formation}) vs "
        f"{away_qq} ({away_formation}) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
