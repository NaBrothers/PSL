#!/usr/bin/env python3
"""Simple HTTP server for PSL replay viewer.

Serves:
- /replays/ -> data/replays/ directory (JSONL files)
- / -> web/ directory (HTML viewer)
"""

import http.server
import os
import sys
from pathlib import Path
from functools import partial

ROOT = Path(__file__).resolve().parent
REPLAY_DIR = ROOT / "data" / "replays"
WEB_DIR = ROOT / "web"


class ReplayHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith("/replays"):
            rel = path[len("/replays"):]
            if rel.startswith("/"):
                rel = rel[1:]
            return str(REPLAY_DIR / rel)
        rel = path.lstrip("/")
        if not rel:
            rel = "replay.html"
        return str(WEB_DIR / rel)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)

    handler = ReplayHandler
    server = http.server.HTTPServer(("", port), handler)
    print(f"PSL Replay Viewer: http://localhost:{port}")
    print(f"Replays dir: {REPLAY_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
