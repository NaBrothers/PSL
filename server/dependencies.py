from fastapi import Depends, HTTPException, Header
from server.auth import decode_token
from server.database import db


def get_current_user(authorization: str = Header()):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = authorization[7:]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    qq = payload.get("qq")
    if not qq:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    row = db.query_one("SELECT * FROM users WHERE qq = ?", (qq,))
    if row is None:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": row[0], "qq": row[1], "name": row[2] or "", "money": row[4] or 0, "formation": row[5] or "442"}
