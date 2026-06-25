import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("PSL_DB_PATH", os.path.join(PROJECT_DIR, "psl.db"))
JWT_SECRET = os.environ.get("PSL_JWT_SECRET", "psl-dev-secret-change-in-prod")
JWT_EXPIRE_DAYS = 7
SERVER_PORT = int(os.environ.get("PSL_WEB_PORT", "8888"))
REPLAY_DIR = os.path.join(PROJECT_DIR, "data", "replays")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
WEB_DIST_DIR = os.path.join(PROJECT_DIR, "web", "dist")
