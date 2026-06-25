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
def get_bag(page: int = 1, query: str = "", sort: str = "overall", position: str = "", color: str = "", for_position: str = "", user=Depends(get_current_user)):
    svc = _bag_svc()
    result = svc.get_bag(user["qq"], page=page, query=query, sort=sort, position=position, color=color)
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
    if query and len(query) >= 1:
        rows = db.query_all(
            "SELECT c.ID, c.Star, c.Style, c.Breach, p.Name, p.Position, p.Overall, u.Name as OwnerName "
            "FROM cards c JOIN players p ON c.Player = p.ID JOIN users u ON c.User = u.QQ "
            "WHERE p.Name LIKE ? "
            "ORDER BY (p.Overall + CASE c.Star "
            "WHEN 1 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2 WHEN 4 THEN 4 WHEN 5 THEN 6 "
            "WHEN 6 THEN 8 WHEN 7 THEN 11 WHEN 8 THEN 14 WHEN 9 THEN 17 WHEN 10 THEN 21 "
            "ELSE 0 END) DESC, p.Name ASC "
            "LIMIT 100",
            (f"%{query}%",)
        )
    else:
        rows = db.query_all(
            "SELECT c.ID, c.Star, c.Style, c.Breach, p.Name, p.Position, p.Overall, u.Name as OwnerName "
            "FROM cards c JOIN players p ON c.Player = p.ID JOIN users u ON c.User = u.QQ "
            "ORDER BY (p.Overall + CASE c.Star "
            "WHEN 1 THEN 0 WHEN 2 THEN 1 WHEN 3 THEN 2 WHEN 4 THEN 4 WHEN 5 THEN 6 "
            "WHEN 6 THEN 8 WHEN 7 THEN 11 WHEN 8 THEN 14 WHEN 9 THEN 17 WHEN 10 THEN 21 "
            "ELSE 0 END) DESC, p.Name ASC "
            "LIMIT 100"
        )
    from server.services._formations import STARS
    style_names = {
        'sniper': '狙击手', 'finisher': '终结者', 'deadeye': '恶魔眼', 'marksman': '神枪手',
        'hawk': '凤头鹰', 'artist': '艺术家', 'architect': '建筑师', 'powerhous': '抢球机器',
        'maestro': '大师', 'engine': '发动机', 'sentinal': '哨兵', 'guardian': '护卫',
        'gladiator': '斗士', 'backbone': '骨干', 'anchor': '铁锚', 'hunter': '狩猎者',
        'catalyst': '催化剂', 'shadow': '暗影', 'speedster': '疾速魔', 'slugger': '重炮手',
        'bronzewall': '铜墙', 'ironwall': '铁壁', 'agilecat': '灵猫', 'gloves': '手套',
    }
    results = []
    for r in rows:
        star_bonus = STARS.get(r[1], {}).get("ability", 0)
        results.append({
            "card_id": r[0], "star": r[1], "style": r[2], "breach": r[3],
            "style_name": style_names.get(r[2], r[2]),
            "name": r[4], "position": r[5], "overall": r[6] + star_bonus,
            "owner": r[7],
        })
    return {"results": results}
