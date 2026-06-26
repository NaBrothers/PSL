"""Challenge service - NPC challenge game logic."""

import sys
import os
import time
import random

from psl_core.constants import NPC, DIFFICULTY

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


class ChallengeError(Exception):
    pass


class ChallengeService:
    def __init__(self, db):
        self.db = db

    def get_info(self, qq: int) -> dict:
        from model.user import User
        from model.challenge_times import ChallengeTimes

        npc_idx = time.localtime(time.time()).tm_wday % len(NPC)
        u = User.getUserByQQ(qq)
        challenge_times = ChallengeTimes.getTimes(u)

        difficulties = [{"key": k, "star": v["star"]} for k, v in DIFFICULTY.items()]

        return {
            "npc_name": NPC[npc_idx]["name"],
            "npc_index": npc_idx,
            "times_left": challenge_times.times,
            "difficulties": difficulties,
        }

    def play(self, qq: int, difficulty: str, mode: str = "quick") -> dict:
        from model.user import User
        from model.formation import Formation
        from model.challenge_times import ChallengeTimes
        from engine.game import Game
        from presentation.report import build_report
        from engine.commentary import CommentaryRenderer

        if difficulty not in DIFFICULTY:
            raise ChallengeError("Invalid difficulty")

        npc_idx = time.localtime(time.time()).tm_wday % len(NPC)
        u = User.getUserByQQ(qq)
        challenge_times = ChallengeTimes.getTimes(u)

        if challenge_times.times <= 0:
            raise ChallengeError("No attempts left today")

        formation = Formation.getFormation(u)
        if not formation.isValid():
            raise ChallengeError("Formation incomplete")

        challenge_times.setTimes(challenge_times.times - 1)

        class NoOpMatcher:
            async def send(self, *a, **kw): pass
            async def finish(self, *a, **kw): pass

        game = Game(NoOpMatcher(), u, 0, npc_idx, difficulty)
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

        awards = DIFFICULTY[difficulty]["award"]
        award_msg = ""
        if match_result in awards:
            award_money = awards[match_result]["money"]
            u.earn(award_money)
            award_msg = f"${award_money}"

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
