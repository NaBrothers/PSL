"""Integration checks for automatic engine-v2 PGO build routing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_builder_runs_auto_pgo_with_generated_real_request(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "rust" / "engine_v2_core" / "src").mkdir(parents=True)
    for name in (
        "build_engine_v2_release.sh",
        "engine_v2_source_digest.py",
        "generate_engine_v2_pgo_request.py",
    ):
        shutil.copy2(ROOT / "scripts" / name, repo / "scripts" / name)
    (repo / "rust" / "engine_v2_core" / "src" / "lib.rs").write_text("")
    (repo / "rust" / "engine_v2_core" / "Cargo.toml").write_text("")
    (repo / "rust" / "engine_v2_core" / "Cargo.lock").write_text("")

    stub = repo / "stub-pgo.sh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "test -s \"$1\"\n"
        "python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); "
        "assert len(p[\"home_cards\"]) == 11; "
        "assert len(p[\"away_cards\"]) == 11' \"$1\"\n"
        "touch \"$PSL_TEST_PGO_CALLED\"\n"
    )
    stub.chmod(0o755)
    called = tmp_path / "pgo-called"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PSL_ENGINE_PGO_BUILDER": str(stub),
        "PSL_TEST_PGO_CALLED": str(called),
        "PSL_DB_PATH": str(ROOT / "psl.db"),
    }
    process = subprocess.run(
        [str(repo / "scripts" / "build_engine_v2_release.sh")],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert called.exists()
    assert "Building PGO Rust engine" in process.stdout


def test_release_builder_falls_back_when_auto_pgo_fails(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "rust" / "engine_v2_core").mkdir(parents=True)
    for name in (
        "build_engine_v2_release.sh",
        "engine_v2_source_digest.py",
        "generate_engine_v2_pgo_request.py",
    ):
        shutil.copy2(ROOT / "scripts" / name, repo / "scripts" / name)

    failing_pgo = repo / "fail-pgo.sh"
    failing_pgo.write_text("#!/usr/bin/env bash\nexit 1\n")
    failing_pgo.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cargo = bin_dir / "cargo"
    cargo.write_text(
        "#!/usr/bin/env bash\n"
        "touch \"$PSL_TEST_CARGO_CALLED\"\n"
    )
    cargo.chmod(0o755)
    cargo_called = tmp_path / "cargo-called"
    process = subprocess.run(
        [str(repo / "scripts" / "build_engine_v2_release.sh")],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PYTHONPATH": str(ROOT),
            "PSL_DB_PATH": str(ROOT / "psl.db"),
            "PSL_ENGINE_PGO_BUILDER": str(failing_pgo),
            "PSL_TEST_CARGO_CALLED": str(cargo_called),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    assert cargo_called.exists()
    assert "falling back to a normal release build" in process.stderr
