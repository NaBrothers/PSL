#!/usr/bin/env bash
set -euo pipefail

native_flag=
if [[ ${1:-} == "--native" ]]; then
  native_flag=" -C target-cpu=native"
  shift
fi
if [[ $# -lt 1 ]]; then
  echo "usage: $0 [--native] MATCH_REQUEST.json [MATCH_REQUEST.json ...]" >&2
  exit 2
fi
for request in "$@"; do
  if [[ ! -f "$request" ]]; then
    echo "match request does not exist: $request" >&2
    exit 2
  fi
done

repo_root=$(cd "$(dirname "$0")/.." && pwd)
crate_dir="$repo_root/rust/engine_v2_core"
build_jobs=${PSL_ENGINE_BUILD_JOBS:-1}
pgo_root=$(mktemp -d "${TMPDIR:-/tmp}/psl-engine-v2-pgo.XXXXXX")
trap 'rm -rf "$pgo_root"' EXIT

host=$(rustc -vV | sed -n 's/^host: //p')
toolchain=$(rustc --print sysroot)
llvm_profdata="$toolchain/lib/rustlib/$host/bin/llvm-profdata"
if [[ ! -x "$llvm_profdata" ]]; then
  if ! command -v rustup >/dev/null 2>&1; then
    echo "matching llvm-profdata is missing and rustup is unavailable: $llvm_profdata" >&2
    exit 1
  fi
  rustup component add llvm-tools-preview >/dev/null
fi
if [[ ! -x "$llvm_profdata" ]]; then
  echo "matching llvm-profdata was not installed: $llvm_profdata" >&2
  exit 1
fi

profile_dir="$pgo_root/profile"
generate_target="$pgo_root/generate-target"
mkdir -p "$profile_dir"

(
  cd "$crate_dir"
  CARGO_BUILD_JOBS="$build_jobs" CARGO_TARGET_DIR="$generate_target" \
    RUSTFLAGS="-C profile-generate=$profile_dir -C codegen-units=1$native_flag" \
    cargo build --release --bin engine
)

for request in "$@"; do
  "$generate_target/release/engine" match_v2_run < "$request" > /dev/null
done

"$llvm_profdata" merge -o "$profile_dir/merged.profdata" "$profile_dir"/*.profraw
(
  cd "$crate_dir"
  CARGO_BUILD_JOBS="$build_jobs" \
    RUSTFLAGS="-C profile-use=$profile_dir/merged.profdata$native_flag" \
    cargo build --release --bin engine
)
marker="$crate_dir/target/release/.engine.pgo"
marker_tmp="$marker.tmp.$$"
{
  printf 'source=%s\n' "$(python3 "$repo_root/scripts/engine_v2_source_digest.py" "$crate_dir")"
  printf 'binary=%s\n' "$(shasum -a 256 "$crate_dir/target/release/engine" | awk '{print $1}')"
} > "$marker_tmp"
mv "$marker_tmp" "$marker"

echo "PGO engine built at $crate_dir/target/release/engine"
