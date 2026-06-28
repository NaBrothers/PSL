"""Match service - runs matches for web API."""

import sys
import os
import re
import time as time_mod
from dataclasses import dataclass, field
from typing import List, Optional

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


def _strip_color(text: str) -> str:
    if not text:
        return text
    return re.sub(r'/~[a-z$]([^/]*)/', r'\1', text)


def _clean_player_name(text: str) -> str:
    """Strip color markup and position prefix like 'LM /~pName/' -> 'Name'."""
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


class MatchError(Exception):
    pass


class UserNotFound(MatchError):
    pass


class FormationIncomplete(MatchError):
    pass


@dataclass
class GoalInfo:
    minute: int
    team_side: str
    scorer: str
    assister: Optional[str]
    scorer_color: str = "w"
    assister_color: Optional[str] = None


@dataclass
class MatchEventInfo:
    minute: int
    second: int
    event_type: str
    text: str
    importance: int
    team_side: str


@dataclass
class MatchResultData:
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    home_stats: dict
    away_stats: dict
    goals: List[GoalInfo]
    events: List[MatchEventInfo]
    report: str
    stats_text: str
    replay_url: Optional[str]
    ratings: Optional[dict] = None
    home_player_stats: Optional[list] = None
    away_player_stats: Optional[list] = None


@dataclass
class TenMatchResult:
    results: List[dict]
    total_home_goals: int
    total_away_goals: int
    wins: int
    draws: int
    losses: int


@dataclass
class OddsResult:
    home_win_odds: float
    draw_odds: float
    away_win_odds: float
    samples: int


class MatchService:
    def __init__(self, db):
        self.db = db

    def run_quick_match(self, home_qq: int, away_qq: int) -> MatchResultData:
        game = self._create_game(home_qq, away_qq)
        return self._run_and_collect(game)

    def run_watch_match(self, home_qq: int, away_qq: int):
        """Generator that yields broadcast lines then final result dict."""
        game = self._create_game(home_qq, away_qq)
        from engine.const import Const
        game.mode = Const.MODE_NORMAL
        game.init_replay_recorder()
        game.resetPosition()
        if hasattr(game, 'recorder'):
            game.recorder.record_frame(game)

        yield {"type": "start", "text": f"主 {game.home.coach.name} : {game.away.coach.name} 客", "subtext": "比赛开始"}
        time_mod.sleep(1)

        game.last_broadcast_time = 0
        while game.time < 45 * 60:
            game.play_possession()
            if game.time > 45 * 60:
                game.flush_possession_summary()
            elapsed = game.time - game.last_broadcast_time
            if game.broadcast_has_goal or elapsed >= game.BROADCAST_INTERVAL:
                lines = list(game.broadcast_buffer)
                game.broadcast_buffer = []
                game.broadcast_has_goal = False
                game.last_broadcast_time = game.time
                if lines:
                    time_mod.sleep(2)
                    yield {"type": "broadcast", "lines": lines}

        if game.broadcast_buffer:
            time_mod.sleep(2)
            yield {"type": "broadcast", "lines": list(game.broadcast_buffer)}
            game.broadcast_buffer = []
        time_mod.sleep(1)
        yield {"type": "half", "text": "上半场结束"}

        game.half = "下半时"
        game.time = 0
        game.last_broadcast_time = 0
        if game.offence is game.home:
            game.swap()
        game.resetPosition()
        game.changeBallHolderToOpen()
        if hasattr(game, 'recorder'):
            game.recorder.record_frame(game)

        time_mod.sleep(2)
        while game.time < 45 * 60:
            game.play_possession()
            if game.time > 45 * 60:
                game.flush_possession_summary()
            elapsed = game.time - game.last_broadcast_time
            if game.broadcast_has_goal or elapsed >= game.BROADCAST_INTERVAL:
                lines = list(game.broadcast_buffer)
                game.broadcast_buffer = []
                game.broadcast_has_goal = False
                game.last_broadcast_time = game.time
                if lines:
                    time_mod.sleep(2)
                    yield {"type": "broadcast", "lines": lines}

        if game.broadcast_buffer:
            time_mod.sleep(2)
            yield {"type": "broadcast", "lines": list(game.broadcast_buffer)}
            game.broadcast_buffer = []
        time_mod.sleep(1)
        yield {"type": "half", "text": "下半场结束"}

        time_mod.sleep(2)
        result_data = self._collect_result(game)
        yield {"type": "result", "data": result_data}

    def run_ten_matches(self, home_qq: int, away_qq: int) -> TenMatchResult:
        results = []
        total_h = total_a = wins = draws = losses = 0
        for _ in range(10):
            game = self._create_game(home_qq, away_qq)
            r = self._run_and_collect(game)
            results.append({"home_score": r.home_score, "away_score": r.away_score})
            total_h += r.home_score
            total_a += r.away_score
            if r.home_score > r.away_score:
                wins += 1
            elif r.home_score == r.away_score:
                draws += 1
            else:
                losses += 1
        return TenMatchResult(results=results, total_home_goals=total_h, total_away_goals=total_a, wins=wins, draws=draws, losses=losses)

    def run_odds(self, home_qq: int, away_qq: int, samples: int = 20) -> OddsResult:
        win = draw = lose = 1
        for _ in range(samples):
            game = self._create_game(home_qq, away_qq)
            r = self._run_and_collect(game)
            if r.home_score > r.away_score:
                win += 1
            elif r.home_score == r.away_score:
                draw += 1
            else:
                lose += 1
        total = samples + 3
        return OddsResult(
            home_win_odds=round(total / win, 2),
            draw_odds=round(total / draw, 2),
            away_win_odds=round(total / lose, 2),
            samples=samples,
        )

    def _create_game(self, home_qq: int, away_qq: int):
        from model.user import User
        from model.formation import Formation

        user1 = User.getUserByQQ(home_qq)
        if user1 is None:
            raise UserNotFound(f"Home user {home_qq} not found")
        user2 = User.getUserByQQ(away_qq)
        if user2 is None:
            raise UserNotFound(f"Away user {away_qq} not found")

        formation1 = Formation.getFormation(user1)
        if not formation1.isValid():
            raise FormationIncomplete("Home formation incomplete")
        formation2 = Formation.getFormation(user2)
        if not formation2.isValid():
            raise FormationIncomplete("Away formation incomplete")

        from engine.game import Game

        class NoOpMatcher:
            async def send(self, *args, **kwargs):
                pass
            async def finish(self, *args, **kwargs):
                pass

        game = Game(NoOpMatcher(), user1, user2)
        return game

    def _run_and_collect(self, game) -> MatchResultData:
        game.mode = 1  # quick mode
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
        return self._collect_result(game)

    def _collect_result(self, game) -> MatchResultData:
        result = game.to_result()
        game.replay_path = game.save_replay() if hasattr(game, 'recorder') else ""
        result.replay_path = game.replay_path

        from presentation.report import build_report
        from presentation.stats import format_stats
        from engine.commentary import CommentaryRenderer
        import random

        rng = random.Random()
        commentary = CommentaryRenderer(rng)
        report = build_report(result, commentary)
        stats_text = format_stats(result)

        goals = [
            GoalInfo(
                minute=g.minute,
                team_side=g.team_side,
                scorer=_clean_player_name(g.scorer_name),
                assister=_clean_player_name(g.assister_name) if g.assister_name else None,
                scorer_color=_player_color_from_markup(g.scorer_name),
                assister_color=_player_color_from_markup(g.assister_name) if g.assister_name else None,
            )
            for g in result.timeline
        ]

        events = [
            MatchEventInfo(
                minute=ev.minute, second=ev.second, event_type=ev.event_type,
                text=ev.text, importance=ev.importance, team_side=ev.team_side,
            )
            for ev in result.events if ev.importance >= 3
        ]

        replay_url = None
        if result.replay_path:
            from model.globalAttr import Global
            base_url = Global.get("replay_base_url", "http://122.51.203.110:8888")
            from utils.replay_server import replay_url as make_url
            replay_url = make_url(base_url, result.replay_path)

        from engine.rating import compute_match_ratings
        ratings = compute_match_ratings(
            result.home_stats.player_stats,
            result.away_stats.player_stats,
        )

        return MatchResultData(
            home_name=result.home_stats.name,
            away_name=result.away_stats.name,
            home_score=result.home_stats.point,
            away_score=result.away_stats.point,
            home_stats=self._serialize_stats(result.home_stats),
            away_stats=self._serialize_stats(result.away_stats),
            goals=goals,
            events=events,
            report=report,
            stats_text=stats_text,
            replay_url=replay_url,
            ratings=ratings,
            home_player_stats=result.home_stats.player_stats,
            away_player_stats=result.away_stats.player_stats,
        )

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
