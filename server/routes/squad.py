import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from server.dependencies import get_current_user
from server.services.squad import SquadService, SquadError, CardNotFound, InvalidFormation


router = APIRouter(prefix="/api", tags=["squad"])


def _squad_svc():
    return SquadService(server.database.db)


class CardInfoSchema(BaseModel):
    id: int
    player_id: int
    name: str
    position: str
    overall: int
    real_overall: int
    star: int
    style: str
    breach: int
    locked: bool
    status: int


class SquadResponse(BaseModel):
    formation: str
    total_ability: int
    forward_ability: int
    midfield_ability: int
    guard_ability: int
    positions: List[str]
    cards: List[Optional[CardInfoSchema]]


class FormationRequest(BaseModel):
    formation: str


class SwapRequest(BaseModel):
    card_id_1: int
    card_id_2: int


@router.get("/squad", response_model=SquadResponse)
def get_squad(user=Depends(get_current_user)):
    svc = _squad_svc()
    data = svc.get_squad(user["qq"])
    return data


@router.get("/squad/{user_id}", response_model=SquadResponse)
def get_squad_by_id(user_id: int, _user=Depends(get_current_user)):
    svc = _squad_svc()
    row = server.database.db.query_one("SELECT QQ FROM users WHERE ID = ?", (user_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = svc.get_squad(row[0])
    return data


@router.post("/squad/formation", response_model=SquadResponse)
def change_formation(req: FormationRequest, user=Depends(get_current_user)):
    svc = _squad_svc()
    try:
        svc.change_formation(user["qq"], req.formation)
    except InvalidFormation as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.get_squad(user["qq"])


@router.post("/squad/swap", response_model=SquadResponse)
def swap_players(req: SwapRequest, user=Depends(get_current_user)):
    svc = _squad_svc()
    try:
        svc.swap_players(user["qq"], req.card_id_1, req.card_id_2)
    except CardNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SquadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.get_squad(user["qq"])


@router.post("/squad/auto", response_model=SquadResponse)
def auto_squad(user=Depends(get_current_user)):
    svc = _squad_svc()
    return svc.auto_squad(user["qq"])


class AssignRequest(BaseModel):
    slot: int
    card_id: int


@router.post("/squad/assign", response_model=SquadResponse)
def assign_player(req: AssignRequest, user=Depends(get_current_user)):
    svc = _squad_svc()
    try:
        svc.assign_player(user["qq"], req.slot, req.card_id)
    except CardNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SquadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.get_squad(user["qq"])
