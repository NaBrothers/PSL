"""Admin routes - management panel API."""

import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from server.dependencies import get_current_user
from server.services.game_config import GameConfigService
from server.services.inbox import InboxService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user=Depends(get_current_user)):
    row = server.database.db.query_one("SELECT isAdmin FROM users WHERE QQ = ?", (user["qq"],))
    if not row or not row[0]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _config_svc():
    return GameConfigService(server.database.db)


def _inbox_svc():
    return InboxService(server.database.db)


# ─── Config ─────────────────────────────────────────────

@router.get("/config")
def get_config(user=Depends(_require_admin)):
    svc = _config_svc()
    return {"groups": svc.get_groups()}


class ConfigUpdateRequest(BaseModel):
    key: str
    value: float | int | str


@router.post("/config")
def update_config(req: ConfigUpdateRequest, user=Depends(_require_admin)):
    svc = _config_svc()
    svc.set(req.key, req.value)
    return {"ok": True, "key": req.key, "value": req.value}


# ─── Players ────────────────────────────────────────────

@router.get("/players")
def list_players(user=Depends(_require_admin)):
    rows = server.database.db.query_all(
        "SELECT u.ID, u.QQ, u.Name, u.Level, u.Money, u.isAdmin, "
        "(SELECT COUNT(*) FROM cards c WHERE c.User = u.QQ) as card_count "
        "FROM users u ORDER BY u.ID"
    )
    return [
        {"id": r[0], "qq": r[1], "name": r[2], "level": r[3], "money": r[4], "is_admin": bool(r[5]), "card_count": r[6]}
        for r in rows
    ]


class ModifyMoneyRequest(BaseModel):
    qq: int
    amount: int
    action: str  # "add" | "set"


@router.post("/players/money")
def modify_money(req: ModifyMoneyRequest, user=Depends(_require_admin)):
    if req.action == "set":
        server.database.db.execute("UPDATE users SET Money = ? WHERE QQ = ?", (req.amount, req.qq))
    elif req.action == "add":
        server.database.db.execute("UPDATE users SET Money = Money + ? WHERE QQ = ?", (req.amount, req.qq))
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    row = server.database.db.query_one("SELECT Money FROM users WHERE QQ = ?", (req.qq,))
    return {"ok": True, "new_money": row[0] if row else 0}


class ResetChallengeRequest(BaseModel):
    qq: int


@router.post("/players/reset-challenge")
def reset_challenge(req: ResetChallengeRequest, user=Depends(_require_admin)):
    svc = _config_svc()
    daily = svc.get("challenge.daily_attempts")
    server.database.db.execute("UPDATE challenge_times SET TimesLeft = ? WHERE User = (SELECT ID FROM users WHERE QQ = ?)", (daily, req.qq))
    return {"ok": True}


# ─── Broadcast ──────────────────────────────────────────

class BroadcastRequest(BaseModel):
    title: str
    content: str = ""
    msg_type: str = "system"


@router.post("/broadcast")
def send_broadcast(req: BroadcastRequest, user=Depends(_require_admin)):
    svc = _inbox_svc()
    svc.broadcast(req.msg_type, req.title, req.content)
    return {"ok": True}


# ─── Pack Distribution ──────────────────────────────────

class DistributePackRequest(BaseModel):
    qq: Optional[int] = None  # None = all players
    pool_key: str
    count: int = 1


@router.post("/distribute-packs")
def distribute_packs(req: DistributePackRequest, user=Depends(_require_admin)):
    from server.services.lottery import LotteryService
    svc = LotteryService(server.database.db)

    if req.qq:
        targets = [req.qq]
    else:
        rows = server.database.db.query_all("SELECT QQ FROM users")
        targets = [r[0] for r in rows]

    results = []
    for qq in targets:
        try:
            result = svc.draw(qq, req.pool_key, req.count)
            results.append({"qq": qq, "ok": True, "cards": len(result.cards)})
            # Notify via inbox
            inbox = _inbox_svc()
            inbox.send(qq, "reward", f"管理员发放卡包", f"获得 {req.count} 个 {req.pool_key} 卡包")
        except Exception as e:
            results.append({"qq": qq, "ok": False, "error": str(e)})

    return {"results": results, "total": len(targets)}


# ─── Stats ──────────────────────────────────────────────

@router.get("/stats")
def get_stats(user=Depends(_require_admin)):
    total_money = server.database.db.query_one("SELECT SUM(Money), AVG(Money), COUNT(*) FROM users")
    total_cards = server.database.db.query_one("SELECT COUNT(*), AVG(Star) FROM cards")
    market_count = server.database.db.query_one("SELECT COUNT(*) FROM transfer")

    return {
        "players": {
            "total": total_money[2] if total_money else 0,
            "total_money": total_money[0] or 0,
            "avg_money": round(total_money[1] or 0),
        },
        "cards": {
            "total": total_cards[0] if total_cards else 0,
            "avg_star": round(total_cards[1] or 0, 1),
        },
        "market": {
            "listings": market_count[0] if market_count else 0,
        },
    }
