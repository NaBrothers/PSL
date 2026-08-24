#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
crate_dir="$repo_root/rust/engine_v2_core"
engine="$crate_dir/target/release/engine"
pgo_marker="$crate_dir/target/release/.engine.pgo"
auto_pgo=${PSL_ENGINE_AUTO_PGO:-1}
pgo_builder=${PSL_ENGINE_PGO_BUILDER:-"$repo_root/scripts/build_engine_v2_pgo.sh"}
source_digest() {
  python3 "$repo_root/scripts/engine_v2_source_digest.py" "$crate_dir"
}
marker_value() {
  sed -n "s/^$1=//p" "$pgo_marker"
}

if [[ -f "$pgo_marker" && ! -x "$engine" ]]; then
  rm -f "$pgo_marker"
fi

if [[ -x "$engine" && -f "$pgo_marker" ]]; then
  binary_digest=$(shasum -a 256 "$engine" | awk '{print $1}')
  if [[ "$(marker_value source)" == "$(source_digest)" \
      && "$(marker_value binary)" == "$binary_digest" ]]; then
    echo "Reusing PGO Rust engine: $engine"
    exit 0
  fi
  rm -f "$pgo_marker"
fi

if [[ "$auto_pgo" != "0" ]]; then
  request_dir=$(mktemp -d "${TMPDIR:-/tmp}/psl-engine-v2-auto-pgo.XXXXXX")
  trap 'rm -rf "$request_dir"' EXIT
  request="$request_dir/match-request.json"
  db_path=${PSL_DB_PATH:-"$repo_root/psl.db"}
  if python3 "$repo_root/scripts/generate_engine_v2_pgo_request.py" \
      --db "$db_path" --output "$request"; then
    echo "Building PGO Rust engine..."
    if "$pgo_builder" "$request"; then
      exit 0
    fi
    echo "PGO build failed; falling back to a normal release build." >&2
  else
    echo "PGO training request unavailable; falling back to a normal release build." >&2
  fi
fi

(cd "$crate_dir" && CARGO_BUILD_JOBS="${PSL_ENGINE_BUILD_JOBS:-1}" \
  cargo build --release --bin engine)
