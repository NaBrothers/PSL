#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Building frontend..."
cd web && npm run build && cd ..

echo "Building Rust engine..."
scripts/build_engine_v2_release.sh

pkill -f "python3 bot/bot.py" 2>/dev/null || true
pkill -f "python3 -m server" 2>/dev/null || true
sleep 1

echo "Starting bot..."
export PSL_RUST_PROFILE=release
nohup python3 bot/bot.py > /dev/null 2>&1 &

echo "Starting web server..."
export PSL_WEB_PORT=8088
nohup python3 -m server > /dev/null 2>&1 &

echo "Done. Bot and web server started."
