import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["league"])


@router.get("/league")
def get_league(user=Depends(get_current_user)):
    db = server.database.db
    rows = db.query_all(
        "SELECT l.User, l.Appearance, l.Score, l.Win, l.Tie, l.Lose, l.Goal, l.Lost_Goal, u.Name "
        "FROM league l JOIN users u ON l.User = u.QQ ORDER BY l.Score DESC, (l.Goal - l.Lost_Goal) DESC"
    )
    standings = []
    for r in rows:
        standings.append({
            "qq": r[0], "name": r[8] or "", "played": r[1], "points": r[2],
            "wins": r[3], "draws": r[4], "losses": r[5],
            "goals_for": r[6], "goals_against": r[7],
            "goal_diff": r[6] - r[7],
        })
    return {"standings": standings}


class LeagueRegisterRequest(BaseModel):
    pass


@router.post("/league/register")
def register(user=Depends(get_current_user)):
    db = server.database.db
    existing = db.query_one("SELECT ID FROM league WHERE User = ?", (user["qq"],))
    if existing:
        raise HTTPException(status_code=400, detail="Already registered")
    db.execute("INSERT INTO league (User) VALUES (?)", (user["qq"],))
    return {"ok": True}


@router.get("/league/schedule")
def get_schedule(user=Depends(get_current_user)):
    db = server.database.db
    rows = db.query_all(
        "SELECT s.ID, s.Round, s.Home, s.Away, s.Finished, s.Home_Goal, s.Away_Goal, "
        "uh.Name, ua.Name "
        "FROM schedule s "
        "JOIN users uh ON s.Home = uh.QQ "
        "JOIN users ua ON s.Away = ua.QQ "
        "ORDER BY s.Round, s.ID"
    )
    schedule = []
    for r in rows:
        schedule.append({
            "id": r[0], "round": r[1], "home_name": r[7] or "", "away_name": r[8] or "",
            "finished": bool(r[4]), "home_goal": r[5], "away_goal": r[6],
        })
    return {"schedule": schedule}


@router.get("/league/standings")
def get_standings(user=Depends(get_current_user)):
    return get_league(user)


@router.get("/league/stats")
def get_stats(user=Depends(get_current_user)):
    db = server.database.db
    scorers = db.query_all(
        "SELECT c.ID, p.Name, c.Goal, u.Name FROM cards c "
        "JOIN players p ON c.Player = p.ID JOIN users u ON c.User = u.QQ "
        "WHERE c.Goal > 0 ORDER BY c.Goal DESC LIMIT 10"
    )
    assists = db.query_all(
        "SELECT c.ID, p.Name, c.Assist, u.Name FROM cards c "
        "JOIN players p ON c.Player = p.ID JOIN users u ON c.User = u.QQ "
        "WHERE c.Assist > 0 ORDER BY c.Assist DESC LIMIT 10"
    )
    return {
        "top_scorers": [{"card_id": r[0], "player": r[1], "goals": r[2], "owner": r[3]} for r in scorers],
        "top_assists": [{"card_id": r[0], "player": r[1], "assists": r[2], "owner": r[3]} for r in assists],
    }
