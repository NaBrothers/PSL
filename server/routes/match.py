import server.database
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from server.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["match"])


class MatchRequest(BaseModel):
    opponent_id: int
    mode: str = "quick"  # quick | watch | ten | odds


class GoalSchema(BaseModel):
    minute: int
    team_side: str
    scorer: str
    assister: Optional[str]


class EventSchema(BaseModel):
    minute: int
    second: int
    event_type: str
    text: str
    importance: int
    team_side: str


class MatchResultSchema(BaseModel):
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    home_stats: dict
    away_stats: dict
    goals: List[GoalSchema]
    events: List[EventSchema]
    report: str
    stats_text: str
    replay_url: Optional[str]


class TenMatchSchema(BaseModel):
    results: List[dict]
    total_home_goals: int
    total_away_goals: int
    wins: int
    draws: int
    losses: int


class OddsSchema(BaseModel):
    home_win_odds: float
    draw_odds: float
    away_win_odds: float
    samples: int


class OpponentSchema(BaseModel):
    id: int
    qq: int
    name: str
    total_ability: int = 0


@router.get("/matches/opponents", response_model=List[OpponentSchema])
def list_opponents(user=Depends(get_current_user)):
    rows = server.database.db.query_all("SELECT ID, QQ, Name FROM users WHERE QQ != ?", (user["qq"],))
    from server.services.squad import SquadService
    svc = SquadService(server.database.db)
    result = []
    for r in rows:
        try:
            squad = svc.get_squad(r[1])
            total = squad.get("total_ability", 0) if isinstance(squad, dict) else getattr(squad, "total_ability", 0)
        except:
            total = 0
        result.append(OpponentSchema(id=r[0], qq=r[1], name=r[2] or "", total_ability=total))
    return result


@router.post("/matches")
def create_match(req: MatchRequest, user=Depends(get_current_user)):
    opponent_row = server.database.db.query_one("SELECT QQ FROM users WHERE ID = ?", (req.opponent_id,))
    if opponent_row is None:
        raise HTTPException(status_code=404, detail="Opponent not found")
    away_qq = opponent_row[0]

    from server.services.match import MatchService, MatchError, UserNotFound, FormationIncomplete
    svc = MatchService(server.database.db)

    try:
        if req.mode == "quick":
            result = svc.run_quick_match(user["qq"], away_qq)
            return result.__dict__
        elif req.mode == "ten":
            result = svc.run_ten_matches(user["qq"], away_qq)
            return result.__dict__
        elif req.mode == "odds":
            result = svc.run_odds(user["qq"], away_qq)
            return result.__dict__
        elif req.mode == "watch":
            result = svc.run_quick_match(user["qq"], away_qq)
            return result.__dict__
        else:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {req.mode}")
    except UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FormationIncomplete as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MatchError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/watch")
def watch_match(opponent_id: int, authorization: str = ""):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    from server.auth import decode_token
    try:
        payload = decode_token(authorization[7:])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    qq = payload.get("qq")
    user_row = server.database.db.query_one("SELECT ID, QQ, Name, Money, Formation FROM users WHERE qq = ?", (qq,))
    if user_row is None:
        raise HTTPException(status_code=401, detail="User not found")

    opponent_row = server.database.db.query_one("SELECT QQ FROM users WHERE ID = ?", (opponent_id,))
    if opponent_row is None:
        raise HTTPException(status_code=404, detail="Opponent not found")
    away_qq = opponent_row[0]

    from server.services.match import MatchService, MatchError, UserNotFound, FormationIncomplete
    import json

    svc = MatchService(server.database.db)

    def event_stream():
        try:
            for msg in svc.run_watch_match(qq, away_qq):
                if msg["type"] == "result":
                    data = msg["data"].__dict__
                    data["goals"] = [g.__dict__ for g in data["goals"]]
                    data["events"] = [e.__dict__ for e in data["events"]]
                    yield f"data: {json.dumps({'type': 'result', 'data': data}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
        except (UserNotFound, FormationIncomplete, MatchError) as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
