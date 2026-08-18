#!/usr/bin/env python3
"""Print the content digest that binds an engine-v2 PGO binary to its sources."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def source_paths(crate: Path) -> list[Path]:
    paths = list((crate / "src").rglob("*.rs"))
    paths.extend(
        path for path in (crate / "Cargo.toml", crate / "Cargo.lock") if path.exists()
    )
    return sorted(paths)


def source_digest(crate: Path) -> str:
    digest = hashlib.sha256()
    for path in source_paths(crate):
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} RUST_CRATE")
    print(source_digest(Path(sys.argv[1]).resolve()))
