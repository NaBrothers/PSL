import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user
from server.services.challenge import ChallengeService, ChallengeError

router = APIRouter(prefix="/api", tags=["challenge"])


def _challenge_svc():
    return ChallengeService(server.database.db)


@router.get("/challenge")
def get_challenge(user=Depends(get_current_user)):
    svc = _challenge_svc()
    return svc.get_info(user["qq"])


class ChallengePlayRequest(BaseModel):
    difficulty: str
    mode: str = "quick"


@router.post("/challenge/play")
def play_challenge(req: ChallengePlayRequest, user=Depends(get_current_user)):
    svc = _challenge_svc()
    try:
        return svc.play(user["qq"], req.difficulty, req.mode)
    except ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
