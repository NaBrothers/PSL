"""Challenge service - NPC challenge game logic."""

import sys
import os
import re
import time
import random

from psl_core.constants import NPC, DIFFICULTY

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


def _strip_color(text: str) -> str:
    if not text:
        return text
    return re.sub(r'/~[a-z$]([^/]*)/', r'\1', text)


def _clean_player_name(text: str) -> str:
    if not text:
        return text
    cleaned = _strip_color(text)
    parts = cleaned.split(' ', 1)
    if len(parts) == 2 and parts[0].isupper() and len(parts[0]) <= 3:
        return parts[1]
    return cleaned


def _player_color_from_markup(text: str) -> str:
    if not text:
        return "w"
    match = re.search(r'/~([a-z$])', text)
    return match.group(1) if match else "w"


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
        from presentation.stats import format_stats
        from engine.commentary import CommentaryRenderer
        from engine.rating import compute_match_ratings

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
        stats_text = format_stats(result)

        goals = [
            {
                "minute": g.minute,
                "team_side": g.team_side,
                "scorer": _clean_player_name(g.scorer_name),
                "assister": _clean_player_name(g.assister_name) if g.assister_name else None,
                "scorer_color": _player_color_from_markup(g.scorer_name),
                "assister_color": _player_color_from_markup(g.assister_name) if g.assister_name else None,
            }
            for g in result.timeline
        ]

        home_stats = self._serialize_stats(result.home_stats)
        away_stats = self._serialize_stats(result.away_stats)

        ratings = compute_match_ratings(
            result.home_stats.player_stats,
            result.away_stats.player_stats,
        )

        replay_url = None
        game.replay_path = game.save_replay() if hasattr(game, 'recorder') else ""
        if game.replay_path:
            from model.globalAttr import Global
            base_url = Global.get("replay_base_url", "http://122.51.203.110:8888")
            from utils.replay_server import replay_url as make_url
            replay_url = make_url(base_url, game.replay_path)

        return {
            "home_name": result.home_stats.name,
            "away_name": result.away_stats.name,
            "home_score": result.home_stats.point,
            "away_score": result.away_stats.point,
            "result": match_result,
            "award": award_msg,
            "report": report,
            "stats_text": stats_text,
            "goals": goals,
            "home_stats": home_stats,
            "away_stats": away_stats,
            "ratings": ratings,
            "replay_url": replay_url,
            "times_left": challenge_times.times,
        }

    def _serialize_stats(self, stats) -> dict:
        return {
            "possession": stats.control,
            "shots": stats.shoots,
            "shots_on_target": stats.shoots_in_target,
            "shots_in_box": stats.shots_in_box,
            "passes": stats.passes,
            "pass_success_rate": round(stats.successful_passes / max(stats.passes, 1) * 100, 1),
            "final_third_entries": stats.final_third_entries,
            "box_entries": stats.box_entries,
            "progressive_passes": stats.progressive_passes,
            "crosses": stats.crosses,
            "corners": stats.corners,
            "dribbles": stats.dribbles,
            "carries": stats.carries,
            "tackles": stats.tackles,
            "pressures": stats.pressures,
            "interceptions": stats.interceptions,
            "blocks": stats.blocks,
            "turnovers": stats.turnovers,
            "saves": stats.saves,
            "xg": round(stats.xg, 2),
            "post_shot_xg": round(stats.post_shot_xg, 2),
            "key_passes": stats.key_passes,
            "box_touches": stats.box_touches,
            "big_chances": stats.big_chances,
            "offsides": stats.offsides,
        }
