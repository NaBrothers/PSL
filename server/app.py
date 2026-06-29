import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from server.config import REPLAY_DIR, ASSETS_DIR, WEB_DIST_DIR
from server.routes.auth import router as auth_router
from server.routes.squad import router as squad_router
from server.routes.match import router as match_router
from server.routes.bag import router as bag_router
from server.routes.lottery import router as lottery_router
from server.routes.transfer import router as transfer_router
from server.routes.player import router as player_router
from server.routes.league import router as league_router
from server.routes.challenge import router as challenge_router
from server.routes.inbox import router as inbox_router
from server.routes.admin import router as admin_router

app = FastAPI(title="PSL Web API")

app.include_router(auth_router)
app.include_router(squad_router)
app.include_router(match_router)
app.include_router(bag_router)
app.include_router(lottery_router)
app.include_router(transfer_router)
app.include_router(player_router)
app.include_router(league_router)
app.include_router(challenge_router)
app.include_router(inbox_router)
app.include_router(admin_router)

os.makedirs(REPLAY_DIR, exist_ok=True)
app.mount("/replays", StaticFiles(directory=REPLAY_DIR), name="replays")

if os.path.isdir(ASSETS_DIR):
    app.mount("/game-assets", StaticFiles(directory=ASSETS_DIR), name="game-assets")

if os.path.isdir(WEB_DIST_DIR):
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        if path.startswith("api/") or path.startswith("replays/") or path.startswith("game-assets/"):
            return
        file_path = os.path.join(WEB_DIST_DIR, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(WEB_DIST_DIR, "index.html"))
