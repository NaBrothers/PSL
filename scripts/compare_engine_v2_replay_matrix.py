#!/usr/bin/env python3
"""Run a matrix of clean-Python vs Rust engine_v2 replay comparisons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compare_engine_v2_replays import (
    DEFAULT_BASELINE_REPO,
    build_cards,
    build_compare_config,
    compare_runs,
    run_python_baseline,
    run_rust_engine,
    summarize,
)
from server.database import Database


def parse_case(raw: str) -> tuple[int, int, int, int, int]:
    parts = raw.split(":")
    if len(parts) not in (4, 5):
        raise argparse.ArgumentTypeError(
            "case must be home:away:ticks:seed or home:away:ticks:half_ticks:seed"
        )
    try:
        home = int(parts[0])
        away = int(parts[1])
        ticks = int(parts[2])
        if len(parts) == 4:
            half_ticks = max(1, ticks // 2)
            seed = int(parts[3])
        else:
            half_ticks = int(parts[3])
            seed = int(parts[4])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return home, away, ticks, half_ticks, seed


def run_case(
    *,
    db: Database,
    baseline_repo: Path,
    home: int,
    away: int,
    ticks: int,
    half_ticks: int,
    seed: int,
    trace_detail: str,
    trace_top_k: int,
) -> dict[str, Any]:
    home_formation, home_cards = build_cards(db, home)
    away_formation, away_cards = build_cards(db, away)
    config = build_compare_config(
        db,
        total_ticks=ticks,
        half_ticks=half_ticks,
        trace_detail=trace_detail,
        trace_top_k=trace_top_k,
    )
    python_run = run_python_baseline(
        baseline_repo,
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config,
        seed=seed,
    )
    rust_run = run_rust_engine(
        home_formation,
        home_cards,
        away_formation,
        away_cards,
        config,
        seed=seed,
    )
    diff = compare_runs(python_run, rust_run)
    return {
        "home": home,
        "away": away,
        "ticks": ticks,
        "half_ticks": half_ticks,
        "seed": seed,
        "formations": [home_formation, away_formation],
        "python": summarize(python_run),
        "rust": summarize(rust_run),
        "diff": diff,
        "matched": (
            diff["first_action_diff"] is None
            and diff["first_frame_diff"] is None
            and diff.get("result_diff") is None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="psl.db")
    parser.add_argument("--baseline-repo", default=str(DEFAULT_BASELINE_REPO))
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        type=parse_case,
        required=True,
        help="home:away:ticks:seed or home:away:ticks:half_ticks:seed; repeatable",
    )
    parser.add_argument(
        "--trace-detail",
        default="top_candidates",
        choices=["off", "chosen", "top_candidates", "full"],
    )
    parser.add_argument("--trace-top-k", type=int, default=8)
    parser.add_argument("--out", default="")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()

    db = Database(args.db)
    baseline_repo = Path(args.baseline_repo)
    results: list[dict[str, Any]] = []
    first_failure: dict[str, Any] | None = None

    for home, away, ticks, half_ticks, seed in args.cases:
        result = run_case(
            db=db,
            baseline_repo=baseline_repo,
            home=home,
            away=away,
            ticks=ticks,
            half_ticks=half_ticks,
            seed=seed,
            trace_detail=args.trace_detail,
            trace_top_k=args.trace_top_k,
        )
        results.append(result)
        print(json.dumps({
            "home": home,
            "away": away,
            "ticks": ticks,
            "half_ticks": half_ticks,
            "seed": seed,
            "formations": result["formations"],
            "matched": result["matched"],
            "diff": result["diff"],
        }, ensure_ascii=False, sort_keys=True))
        if not result["matched"] and first_failure is None:
            first_failure = result
            if not args.keep_going:
                break

    report = {
        "baseline_repo": str(baseline_repo),
        "db": args.db,
        "total_cases": len(results),
        "matched_cases": sum(1 for result in results if result["matched"]),
        "first_failure": first_failure,
        "results": results,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "total_cases": report["total_cases"],
        "matched_cases": report["matched_cases"],
        "has_failure": first_failure is not None,
        "out": args.out or None,
    }, ensure_ascii=False, sort_keys=True))
    return 1 if first_failure is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
