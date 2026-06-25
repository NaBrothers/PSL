import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user
from server.services.lottery import LotteryService, LotteryError, InsufficientFunds, PoolNotFound

router = APIRouter(prefix="/api", tags=["lottery"])


@router.get("/lottery/pools")
def list_pools(user=Depends(get_current_user)):
    svc = LotteryService(server.database.db)
    return svc.list_pools(user["qq"])


class DrawRequest(BaseModel):
    pool: str
    count: int = 1


@router.post("/lottery/draw")
def draw(req: DrawRequest, user=Depends(get_current_user)):
    svc = LotteryService(server.database.db)
    try:
        result = svc.draw(user["qq"], req.pool, req.count)
        return {"pool_name": result.pool_name, "cards": [c.__dict__ for c in result.cards], "cost": result.cost, "remaining_money": result.remaining_money}
    except PoolNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InsufficientFunds as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LotteryError as e:
        raise HTTPException(status_code=400, detail=str(e))
