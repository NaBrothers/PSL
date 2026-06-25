import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user
from server.services.player_ops import PlayerOpsService, PlayerOpsError

router = APIRouter(prefix="/api", tags=["player"])


class UpgradeRequest(BaseModel):
    main_id: int
    sub_id: int


@router.post("/cards/upgrade")
def upgrade_card(req: UpgradeRequest, user=Depends(get_current_user)):
    svc = PlayerOpsService(server.database.db)
    try:
        return svc.upgrade(user["qq"], req.main_id, req.sub_id)
    except PlayerOpsError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cards/breach")
def breach_card(req: UpgradeRequest, user=Depends(get_current_user)):
    svc = PlayerOpsService(server.database.db)
    try:
        return svc.breach(user["qq"], req.main_id, req.sub_id)
    except PlayerOpsError as e:
        raise HTTPException(status_code=400, detail=str(e))
