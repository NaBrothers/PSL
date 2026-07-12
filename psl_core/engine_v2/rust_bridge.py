"""Subprocess bridge to the Rust whole-match engine."""

from __future__ import annotations

import fcntl
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .config import EngineConfig


ROOT = Path(__file__).resolve().parents[2]
RUST_CRATE = ROOT / "rust" / "engine_v2_core"
RUST_ENGINE = RUST_CRATE / "target" / "release" / "engine"
RUST_BUILD_LOCK = RUST_CRATE / "target" / ".engine.release.lock"


class RustEngineError(RuntimeError):
    """Raised when the Rust engine cannot build or complete a match."""


def _source_paths() -> list[Path]:
    paths = list((RUST_CRATE / "src").rglob("*.rs"))
    paths.extend(
        path
        for path in (RUST_CRATE / "Cargo.toml", RUST_CRATE / "Cargo.lock")
        if path.exists()
    )
    return paths


def _needs_build() -> bool:
    if not RUST_ENGINE.exists():
        return True
    binary_mtime = RUST_ENGINE.stat().st_mtime
    return any(path.stat().st_mtime > binary_mtime for path in _source_paths())


def _build_release_engine() -> None:
    RUST_BUILD_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with RUST_BUILD_LOCK.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            if not _needs_build():
                return
            process = subprocess.run(
                ["cargo", "build", "--quiet", "--release", "--bin", "engine"],
                cwd=RUST_CRATE,
                text=True,
                capture_output=True,
                check=False,
            )
            if process.returncode != 0:
                raise RustEngineError(
                    "failed to build Rust match engine:\n"
                    + (process.stderr.strip() or process.stdout.strip())
                )
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _run_json(mode: str, payload: Mapping[str, Any]) -> dict:
    _build_release_engine()
    try:
        process = subprocess.run(
            [str(RUST_ENGINE), mode],
            cwd=RUST_CRATE,
            input=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise RustEngineError(f"failed to start Rust match engine: {exc}") from exc

    if process.returncode != 0:
        raise RustEngineError(
            f"Rust match engine exited with code {process.returncode}:\n"
            + (process.stderr.strip() or process.stdout.strip())
        )
    try:
        response = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RustEngineError(
            f"Rust match engine returned invalid JSON: {process.stdout[:500]!r}"
        ) from exc
    if not isinstance(response, dict):
        raise RustEngineError("Rust match engine response must be a JSON object")
    return response


def run_match(
    home_cards: Sequence[Mapping[str, Any]],
    away_cards: Sequence[Mapping[str, Any]],
    home_formation: str,
    away_formation: str,
    config: EngineConfig,
    seed: Optional[int] = None,
) -> dict:
    """Run one complete match through Rust's sole production entrypoint."""
    response = _run_json(
        "match_v2_run",
        {
            "home_cards": list(home_cards),
            "away_cards": list(away_cards),
            "home_formation": home_formation,
            "away_formation": away_formation,
            "config": config.to_rust_payload(),
            "seed": seed,
        },
    )
    if response.get("engine") != "rust_match_v2":
        raise RustEngineError(
            f"unexpected engine backend: {response.get('engine')!r}"
        )
    if response.get("contract_version") != 1:
        raise RustEngineError(
            f"unsupported Rust engine contract: {response.get('contract_version')!r}"
        )
    return response
