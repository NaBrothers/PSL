#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
crate_dir="$repo_root/rust/engine_v2_core"
engine="$crate_dir/target/release/engine"
pgo_marker="$crate_dir/target/release/.engine.pgo"
source_digest() {
  python3 "$repo_root/scripts/engine_v2_source_digest.py" "$crate_dir"
}

if [[ -f "$pgo_marker" && ! -x "$engine" ]]; then
  rm -f "$pgo_marker"
fi

if [[ -x "$engine" && -f "$pgo_marker" ]]; then
  if [[ "$(cat "$pgo_marker")" == "$(source_digest)" ]]; then
    echo "Reusing PGO Rust engine: $engine"
    exit 0
  fi
  rm -f "$pgo_marker"
fi

(cd "$crate_dir" && cargo build --release --bin engine)
