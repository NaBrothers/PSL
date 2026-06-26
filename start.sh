#!/bin/bash
cd "$(dirname "$0")"

pkill -f "python3 bot/bot.py" 2>/dev/null
pkill -f "python3 -m server" 2>/dev/null
sleep 1

echo "Building frontend..."
cd web && npm run build && cd ..

echo "Starting bot..."
nohup python3 bot/bot.py > /dev/null 2>&1 &

echo "Starting web server..."
export PSL_WEB_PORT=8088
nohup python3 -m server > /dev/null 2>&1 &

echo "Done. Bot and web server started."
