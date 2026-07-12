"""Helpers for comparing current Rust engine_v2 work against a clean Python baseline.

The baseline must be a separate source checkout/snapshot without the current
Rust adapter changes. It is executed in a subprocess so imports cannot leak
from this dirty workspace into the baseline process.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest


DEFAULT_BASELINE_REPO = Path("/private/tmp/psl-dev-python-baseline")
BASELINE_PARITY_ENV = "PSL_ENGINE_V2_RUN_BASELINE_PARITY"


def baseline_repo_or_skip() -> Path:
    if os.environ.get(BASELINE_PARITY_ENV) != "1":
        pytest.skip(f"set {BASELINE_PARITY_ENV}=1 to run clean-baseline engine_v2 parity tests")
    repo = Path(os.environ.get("PSL_ENGINE_V2_BASELINE_REPO", str(DEFAULT_BASELINE_REPO)))
    if not repo.exists():
        pytest.skip(f"clean engine_v2 Python baseline not found: {repo}")
    if not (repo / "psl_core" / "engine_v2" / "match.py").exists():
        pytest.skip(f"invalid engine_v2 Python baseline: {repo}")
    if (repo / "psl_core" / "engine_v2" / "rust_adapter.py").exists():
        pytest.fail(f"baseline repo is polluted by Rust adapter changes: {repo}")
    return repo


def engine_config_payload(config: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in dataclasses.fields(config):
        if field.name == "trace":
            continue
        value = getattr(config, field.name)
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[field.name] = value
        elif isinstance(value, tuple):
            payload[field.name] = list(value)
        elif isinstance(value, list):
            payload[field.name] = value

    trace = getattr(config, "trace", None)
    if trace is not None:
        payload["trace"] = {
            "detail": getattr(trace, "detail", "off"),
            "top_k": getattr(trace, "top_k", 5),
            "include_off_ball": getattr(trace, "include_off_ball", False),
            "include_defense": getattr(trace, "include_defense", False),
            "sample_rate": getattr(trace, "sample_rate", 1),
        }
    return payload


def run_python_baseline_match(
    *,
    home_cards: list[dict[str, Any]],
    away_cards: list[dict[str, Any]],
    home_formation: str,
    away_formation: str,
    config: Any,
    seed: int,
    baseline_repo: Path | None = None,
) -> dict[str, Any]:
    repo = baseline_repo or baseline_repo_or_skip()
    script = r"""
import json
import random
import sys

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2

payload = json.load(sys.stdin)
random.seed(payload["seed"])

cfg = EngineConfig()
for key, value in payload["config"].items():
    if key == "trace":
        continue
    if hasattr(cfg, key):
        setattr(cfg, key, value)

trace_payload = payload["config"].get("trace", {})
for key, value in trace_payload.items():
    if hasattr(cfg.trace, key):
        setattr(cfg.trace, key, value)

match = MatchV2(
    payload["home_cards"],
    payload["away_cards"],
    payload["home_formation"],
    payload["away_formation"],
    config=cfg,
)
result = match.run()
print(json.dumps({
    "engine": "clean_python_baseline",
    "home_score": result.home_score,
    "away_score": result.away_score,
    "goals": result.goals,
    "home_stats": result.home_stats,
    "away_stats": result.away_stats,
    "home_player_stats": result.home_player_stats,
    "away_player_stats": result.away_player_stats,
    "home_ratings": result.home_ratings,
    "away_ratings": result.away_ratings,
    "replay": match.get_replay_data(),
    "trace": match.get_trace(),
}, ensure_ascii=False))
"""
    payload = {
        "home_cards": home_cards,
        "away_cards": away_cards,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "config": engine_config_payload(config),
        "seed": seed,
    }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env=env,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def summarize_engine_v2_run(run: dict[str, Any]) -> dict[str, Any]:
    trace = run.get("trace", {})
    replay = [frame for frame in run.get("replay", []) if frame.get("type") == "frame"]
    actions = [entry for entry in trace.get("entries", []) if entry.get("type") == "action"]
    events = [entry for entry in trace.get("entries", []) if entry.get("type") == "event"]
    holders = Counter((frame.get("ball_team"), frame.get("ball_holder")) for frame in replay)
    total_frames = max(1, len(replay))
    return {
        "score": [run.get("home_score"), run.get("away_score")],
        "frames": len(replay),
        "actions": dict(Counter(entry.get("action") for entry in actions)),
        "events": dict(Counter(entry.get("event") for entry in events)),
        "decision_count": len(trace.get("decisions", [])),
        "first_actions": [
            (entry.get("tick"), entry.get("team"), entry.get("player"), entry.get("action"))
            for entry in actions[:12]
        ],
        "max_holder_share": holders.most_common(1)[0][1] / total_frames if holders else 0.0,
        "ball_flight_frames": sum(1 for frame in replay if frame.get("ball_flight")),
        "home_stats": {
            key: run.get("home_stats", {}).get(key)
            for key in ("shots", "passes", "passes_completed", "possession")
        },
        "away_stats": {
            key: run.get("away_stats", {}).get(key)
            for key in ("shots", "passes", "passes_completed", "possession")
        },
    }
