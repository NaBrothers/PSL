import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from server.dependencies import get_current_user
from server.services.bag import BagService, BagError, CardNotFound, CardNotOwned

router = APIRouter(prefix="/api", tags=["bag"])


def _bag_svc():
    return BagService(server.database.db)


class BagCardSchema(BaseModel):
    id: int
    player_id: int
    name: str
    position: str
    overall: int
    real_overall: Optional[int] = None
    star: int
    style: str
    breach: int
    locked: bool
    status: int
    status_text: str
    top_abilities: Optional[list] = None


class BagPageSchema(BaseModel):
    cards: List[BagCardSchema]
    total: int
    page: int
    total_pages: int


class RecycleRequest(BaseModel):
    ids: List[int]


class RecycleResponse(BaseModel):
    recycled: List[str]
    failed: List[str]
    earned: int
    remaining_money: int


@router.get("/bag", response_model=BagPageSchema)
def get_bag(page: int = 1, page_size: int = 20, query: str = "", sort: str = "overall", position: str = "", color: str = "", for_position: str = "", user=Depends(get_current_user)):
    svc = _bag_svc()
    result = svc.get_bag(user["qq"], page=page, query=query, sort=sort, position=position, color=color, page_size=page_size)
    if for_position:
        from server.services.squad import SquadService
        squad_svc = SquadService(server.database.db)
        for card in result.cards:
            card.real_overall = squad_svc._compute_real_overall_for_player(card.player_id, card.star, card.style, {}, for_position)
        result.cards.sort(key=lambda c: (-(c.real_overall or c.overall), -c.star, c.name))
    return result


@router.get("/cards/{card_id}")
def get_card_detail(card_id: int, user=Depends(get_current_user)):
    svc = _bag_svc()
    try:
        return svc.get_card_detail(card_id, user["qq"])
    except CardNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/cards/{card_id}/lock")
def lock_card(card_id: int, user=Depends(get_current_user)):
    svc = _bag_svc()
    try:
        locked = svc.lock_card(card_id, user["qq"])
        return {"locked": locked}
    except CardNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CardNotOwned as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/cards/recycle", response_model=RecycleResponse)
def recycle_cards(req: RecycleRequest, user=Depends(get_current_user)):
    svc = _bag_svc()
    return svc.recycle_cards(user["qq"], req.ids)


@router.get("/cards/{card_id}/compare/{other_id}")
def compare_cards(card_id: int, other_id: int, user=Depends(get_current_user)):
    svc = _bag_svc()
    try:
        card1 = svc.get_card_detail(card_id, user["qq"])
        card2 = svc.get_card_detail(other_id, user["qq"])
        return {"card1": card1, "card2": card2}
    except CardNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/search")
def global_search(query: str = "", user=Depends(get_current_user)):
    db = server.database.db
    _fields = (
        "SELECT c.ID, c.Star, c.Style, c.Breach, p.Name, p.Position, p.Overall, "
        "u.Name as OwnerName, c.Player, c.Ext_Abilities, p.Height, "
        "p.Heading_Accuracy, p.Jumping, p.Strength, p.Long_Shots, p.Shot_Power, "
        "p.Finishing, p.Long_Passing, p.Short_Passing, p.Dribbling, p.Ball_Control, "
        "p.Balance, p.Sliding_Tackle, p.Standing_Tackle, p.Defensive_Awareness, "
        "p.Aggression, p.Interceptions, p.Sprint_Speed, p.Acceleration, "
        "p.Composure, p.GK_Handling, p.GK_Diving, p.GK_Positioning, p.GK_Reflexes, p.Reactions "
        "FROM cards c JOIN players p ON c.Player = p.ID JOIN users u ON c.User = u.QQ "
    )
    _order = (
        "ORDER BY (p.Overall + CASE c.Star "
        "WHEN 1 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2 WHEN 4 THEN 4 WHEN 5 THEN 6 "
        "WHEN 6 THEN 8 WHEN 7 THEN 11 WHEN 8 THEN 14 WHEN 9 THEN 17 WHEN 10 THEN 21 "
        "ELSE 0 END) DESC, p.Name ASC LIMIT 100"
    )
    if query and len(query) >= 1:
        rows = db.query_all(_fields + "WHERE p.Name LIKE ? " + _order, (f"%{query}%",))
    else:
        rows = db.query_all(_fields + _order)

    import json as _json
    from psl_core.constants import STARS, GOALKEEPER
    from psl_core.card import get_style_name, compute_overall, compute_abilities

    ABILITY_NAMES = {"Heading": "头球", "Finishing": "终结", "Short_Passing": "短传",
        "Dribbling": "盘带", "Tackling": "抢断", "Defence": "防守", "Speed": "速度",
        "Long_Shot": "远射", "Long_Passing": "长传", "IQ": "球商",
        "GK_Saving": "扑救", "GK_Positioning": "站位", "GK_Reaction": "反应"}

    results = []
    for r in rows:
        pos = (r[5] or "").split(",")[0].strip()
        ext = _json.loads(r[9]) if r[9] else {}
        height_val = int(r[10]) if r[10] and str(r[10]).isdigit() else 180
        abilities = compute_abilities(
            star=r[1], style=r[2], position=pos, height=height_val,
            heading_accuracy=r[11] or 0, jumping=r[12] or 0, strength=r[13] or 0,
            long_shots=r[14] or 0, shot_power=r[15] or 0, finishing=r[16] or 0,
            long_passing=r[17] or 0, short_passing=r[18] or 0, dribbling=r[19] or 0,
            ball_control=r[20] or 0, balance=r[21] or 0, sliding_tackle=r[22] or 0,
            standing_tackle=r[23] or 0, defensive_awareness=r[24] or 0,
            aggression=r[25] or 0, interceptions=r[26] or 0, sprint_speed=r[27] or 0,
            acceleration=r[28] or 0, composure=r[29] or 0, gk_handling=r[30] or 0,
            gk_diving=r[31] or 0, gk_positioning=r[32] or 0, gk_reflexes=r[33] or 0,
            reactions=r[34] or 0, ext_abilities=ext,
        )
        exclude = {"GK_Saving", "GK_Positioning", "GK_Reaction"} if pos not in GOALKEEPER else {"Heading", "Finishing", "Long_Shot", "Tackling"}
        ability_list = [(ABILITY_NAMES.get(k, k), v) for k, v in abilities.items() if k not in exclude]
        ability_list.sort(key=lambda x: -x[1])
        top3 = [{"name": a[0], "value": a[1]} for a in ability_list[:3]]
        results.append({
            "card_id": r[0], "player_id": r[8], "star": r[1], "style": r[2], "breach": r[3],
            "style_name": get_style_name(r[2], r[5]),
            "name": r[4], "position": pos, "overall": compute_overall(r[6], r[1]),
            "owner": r[7], "top_abilities": top3,
        })
    return {"results": results}
