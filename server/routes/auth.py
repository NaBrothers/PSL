import server.database
from fastapi import APIRouter, HTTPException, Header
from server.auth import hash_pin, verify_pin, create_token, decode_token
from server.schemas import PlayerListItem, SetupPinRequest, LoginRequest, LoginResponse, UserInfo

router = APIRouter(prefix="/api", tags=["auth"])


def _db():
    return server.database.db


@router.get("/players", response_model=list[PlayerListItem])
def list_players():
    rows = _db().query_all("SELECT ID, QQ, Name, WebPinHash FROM users")
    return [
        PlayerListItem(id=r[0], qq=r[1], name=r[2] or "", has_pin=r[3] is not None)
        for r in rows
    ]


@router.post("/auth/setup-pin")
def setup_pin(req: SetupPinRequest):
    if len(req.pin) != 4 or not req.pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")
    row = _db().query_one("SELECT ID, WebPinHash FROM users WHERE qq = ?", (req.qq,))
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if row[1] is not None:
        raise HTTPException(status_code=400, detail="PIN already set. Use login instead.")
    pin_hash = hash_pin(req.pin)
    _db().execute("UPDATE users SET WebPinHash = ? WHERE qq = ?", (pin_hash, req.qq))
    return {"ok": True}


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if len(req.pin) != 4 or not req.pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")
    row = _db().query_one("SELECT ID, QQ, Name, Money, Formation, WebPinHash FROM users WHERE qq = ?", (req.qq,))
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if row[5] is None:
        raise HTTPException(status_code=400, detail="PIN not set. Use setup-pin first.")
    if not verify_pin(req.pin, row[5]):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    token = create_token(req.qq)
    user = UserInfo(id=row[0], qq=row[1], name=row[2] or "", money=row[3] or 0, formation=row[4] or "442")
    return LoginResponse(token=token, user=user)


@router.get("/me", response_model=UserInfo)
def get_me(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization[7:]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    qq = payload.get("qq")
    row = _db().query_one("SELECT ID, QQ, Name, Money, Formation FROM users WHERE qq = ?", (qq,))
    if row is None:
        raise HTTPException(status_code=401, detail="User not found")
    return UserInfo(id=row[0], qq=row[1], name=row[2] or "", money=row[3] or 0, formation=row[4] or "442")
