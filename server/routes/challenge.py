import sys
import os
import time
import server.database
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from server.dependencies import get_current_user

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)

router = APIRouter(prefix="/api", tags=["challenge"])


@router.get("/challenge")
def get_challenge(user=Depends(get_current_user)):
    from utils.const import Const
    from model.user import User
    from model.challenge_times import ChallengeTimes

    npc = time.localtime(time.time()).tm_wday % len(Const.NPC)
    u = User.getUserByQQ(user["qq"])
    challenge_times = ChallengeTimes.getTimes(u)

    difficulties = []
    for key, val in Const.DIFFICULTY.items():
        difficulties.append({"key": key, "star": val["star"]})

    return {
        "npc_name": Const.NPC[npc]["name"],
        "npc_index": npc,
        "times_left": challenge_times.times,
        "difficulties": difficulties,
    }


class ChallengePlayRequest(BaseModel):
    difficulty: str
    mode: str = "quick"


@router.post("/challenge/play")
def play_challenge(req: ChallengePlayRequest, user=Depends(get_current_user)):
    from utils.const import Const
    from model.user import User
    from model.formation import Formation
    from model.challenge_times import ChallengeTimes
    from engine.game import Game

    if req.difficulty not in Const.DIFFICULTY:
        raise HTTPException(status_code=400, detail="Invalid difficulty")

    npc = time.localtime(time.time()).tm_wday % len(Const.NPC)
    u = User.getUserByQQ(user["qq"])
    challenge_times = ChallengeTimes.getTimes(u)

    if challenge_times.times <= 0:
        raise HTTPException(status_code=400, detail="No attempts left today")

    formation = Formation.getFormation(u)
    if not formation.isValid():
        raise HTTPException(status_code=400, detail="Formation incomplete")

    challenge_times.setTimes(challenge_times.times - 1)

    class NoOpMatcher:
        async def send(self, *a, **kw): pass
        async def finish(self, *a, **kw): pass

    game = Game(NoOpMatcher(), u, 0, npc, req.difficulty)
    game.mode = 1
    game.init_replay_recorder()
    game.resetPosition()
    if hasattr(game, 'recorder'):
        game.recorder.record_frame(game)
    while game.time < 45 * 60:
        game.play_possession()
    game.half = "下半时"
    game.time = 0
    if game.offence is game.home:
        game.swap()
    game.resetPosition()
    game.changeBallHolderToOpen()
    if hasattr(game, 'recorder'):
        game.recorder.record_frame(game)
    while game.time < 45 * 60:
        game.play_possession()

    result = game.to_result()

    if result.home_stats.point > result.away_stats.point:
        match_result = "win"
    elif result.home_stats.point == result.away_stats.point:
        match_result = "tie"
    else:
        match_result = "lose"

    awards = Const.DIFFICULTY[req.difficulty]["award"]
    award_msg = ""
    if match_result in awards:
        award_money = awards[match_result]["money"]
        u.earn(award_money)
        award_msg = f"${award_money}"

    from presentation.report import build_report
    from engine.commentary import CommentaryRenderer
    import random
    commentary = CommentaryRenderer(random.Random())
    report = build_report(result, commentary)

    return {
        "home_score": result.home_stats.point,
        "away_score": result.away_stats.point,
        "result": match_result,
        "award": award_msg,
        "report": report,
        "times_left": challenge_times.times,
    }
