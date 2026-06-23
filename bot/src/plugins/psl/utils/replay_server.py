import http.server
import json
import os
import threading
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from config import PROJECT_DIR


ROOT = Path(PROJECT_DIR)
REPLAY_DIR = ROOT / "data" / "replays"
WEB_DIR = ROOT / "web"
_server = None
_thread = None


class ReplayHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path)
        route = unquote(parsed.path)
        if route.startswith("/replays"):
            rel = route[len("/replays"):].lstrip("/")
            return str(REPLAY_DIR / rel)
        rel = route.lstrip("/") or "replay.html"
        return str(WEB_DIR / rel)

    def do_GET(self):
        route = unquote(urlparse(self.path).path)
        if route.rstrip("/") == "/replays":
            self.send_replay_list()
            return
        if route == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def send_replay_list(self):
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(
            [f for f in os.listdir(REPLAY_DIR) if f.endswith(".jsonl")],
            reverse=True,
        )
        data = json.dumps(files).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def start_replay_server(port=8888):
    global _server, _thread
    if _server is not None:
        return _server
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _server = http.server.ThreadingHTTPServer(("", port), ReplayHandler)
    except OSError as exc:
        print(f"PSL Replay Viewer not started on {port}: {exc}")
        return None
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    print(f"PSL Replay Viewer: http://localhost:{port}")
    print(f"Replays dir: {REPLAY_DIR}")
    return _server


def replay_url(base_url, replay_path):
    if not replay_path:
        return ""
    filename = os.path.basename(replay_path)
    return base_url.rstrip("/") + "/?path=" + quote(filename)
