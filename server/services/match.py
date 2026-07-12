"""Match service - runs matches for web API."""

import os
import json
import time as time_mod
from dataclasses import dataclass
from typing import List, Optional

from psl_core.card import get_color_code
from psl_core.constants import STARS
from psl_core.engine_v2.match import MatchV2


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

    def _run_match(self, home_qq: int, away_qq: int) -> MatchResultData:
        """Run a complete match through the Rust engine."""
        from server.services.squad import SquadService
        from server.services.bag import BagService
        from server.services.game_config import GameConfigService

        squad_svc = SquadService(self.db)
        bag_svc = BagService(self.db)
        config_svc = GameConfigService(self.db)

        home_squad = squad_svc.get_squad(home_qq)
        away_squad = squad_svc.get_squad(away_qq)

        if any(c is None for c in home_squad.cards):
            raise FormationIncomplete("Home formation incomplete")
        if any(c is None for c in away_squad.cards):
            raise FormationIncomplete("Away formation incomplete")

        def _build_cards(squad, qq):
            cards = []
            for card_info in squad.cards:
                detail = bag_svc.get_card_detail(card_info.id, qq)
                abilities = {k: v["value"] for k, v in detail["abilities"].items()}
                base_overall = card_info.overall - STARS[card_info.star]["ability"]
                cards.append({
                    "name": card_info.name,
                    "player_id": card_info.player_id,
                    "position": card_info.position,
                    "color": get_color_code(base_overall, card_info.star),
                    "overall": card_info.real_overall,
                    "abilities": abilities,
                })
            return cards

        home_cards = _build_cards(home_squad, home_qq)
        away_cards = _build_cards(away_squad, away_qq)

        # Get user names
        user1_row = self.db.query_one("SELECT Name FROM users WHERE qq = ?", (home_qq,))
        user2_row = self.db.query_one("SELECT Name FROM users WHERE qq = ?", (away_qq,))
        home_name = user1_row[0] if user1_row else f"User {home_qq}"
        away_name = user2_row[0] if user2_row else f"User {away_qq}"

        # Run match
        match = MatchV2(
            home_cards, away_cards,
            home_squad.formation, away_squad.formation,
            config_service=config_svc,
        )
        result = match.run()
        replay_data = match.get_replay_data()
        if replay_data and replay_data[0].get("type") == "header":
            replay_data[0]["home"]["name"] = home_name
            replay_data[0]["away"]["name"] = away_name

        # Save replay
        replay_dir = os.path.join(
            os.environ.get("PSL_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data", "replays"
        )
        os.makedirs(replay_dir, exist_ok=True)
        ts = time_mod.strftime("%Y%m%d_%H%M%S")
        score = f"{result.home_score}-{result.away_score}"
        filename = f"{ts}_{home_name.replace(' ', '_')}_{away_name.replace(' ', '_')}_{score}.jsonl"
        filepath = os.path.join(replay_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            for frame in replay_data:
                f.write(json.dumps(frame, ensure_ascii=False) + "\n")

        # Build replay URL
        replay_url = "/replays/" + os.path.basename(filepath) if filepath else None






        # Convert goals
        goals = [
            GoalInfo(
                minute=g["minute"],
                team_side=g["team_side"],
                scorer=g["scorer"],
                assister=g["assister"] if g.get("assister") else None,
                scorer_color=g.get("scorer_color", "w"),
                assister_color=g.get("assister_color") if g.get("assister") else None,
            )
            for g in result.goals
        ]

        # Build stats in the same format as existing code
        home_stats = self._v2_stats_to_dict(result.home_stats, result.home_player_stats)
        away_stats = self._v2_stats_to_dict(result.away_stats, result.away_player_stats)

        # Build ratings in the format expected by frontend
        def _rating_payload(raw):
            return {
                "name": raw.get("name", ""),
                "player_id": raw.get("player_id"),
                "position": raw.get("position", ""),
                "color": raw.get("color", "w"),
                "colored_name": raw.get("colored_name", raw.get("name", "")),
                "rating": raw.get("rating", 6.0),
            }

        home_ratings_list = [_rating_payload(r) for r in result.home_ratings]
        away_ratings_list = [_rating_payload(r) for r in result.away_ratings]
        all_players = [(r, "home") for r in home_ratings_list] + [(r, "away") for r in away_ratings_list]
        motm_player = max(all_players, key=lambda x: x[0]["rating"]) if all_players else None
        ratings = {
            "home_ratings": home_ratings_list,
            "away_ratings": away_ratings_list,
            "motm": {**motm_player[0], "team_side": motm_player[1]} if motm_player else None,
        }

        return MatchResultData(
            home_name=home_name,
            away_name=away_name,
            home_score=result.home_score,
            away_score=result.away_score,
            home_stats=home_stats,
            away_stats=away_stats,
            goals=goals,
            events=[],
            report=f"{home_name} {result.home_score} - {result.away_score} {away_name}",
            stats_text="",
            replay_url=replay_url,
            ratings=ratings,
            home_player_stats=result.home_player_stats,
            away_player_stats=result.away_player_stats,
        )

    def _v2_stats_to_dict(self, stats: dict, player_stats: list = None) -> dict:
        """Convert engine v2 stats dict to the standard serialized format.
        
        Aggregates advanced stats from player_stats if provided.
        """
        passes = stats.get("passes", 0)
        passes_completed = stats.get("passes_completed", 0)

        # Aggregate advanced stats from individual player data
        ps_list = player_stats or []
        total_xg = sum(p.get("xg", 0) for p in ps_list)
        total_progressive_passes = sum(p.get("progressive_passes", 0) for p in ps_list)
        total_key_passes = sum(p.get("key_passes", 0) for p in ps_list)
        total_carries = sum(p.get("carries", 0) for p in ps_list)
        total_progressive_carries = sum(p.get("progressive_carries", 0) for p in ps_list)
        total_crosses = stats.get("crosses_completed", 0) + stats.get("crosses", sum(p.get("crosses", 0) for p in ps_list))
        total_blocks = sum(p.get("blocks", 0) for p in ps_list)
        total_turnovers = sum(p.get("turnovers", 0) for p in ps_list)
        total_pressures = sum(p.get("pressures", 0) for p in ps_list)
        total_offsides = sum(p.get("offsides", 0) for p in ps_list)
        total_big_chances = sum(p.get("big_chances", 0) for p in ps_list)
        total_passes_into_box = sum(p.get("passes_into_box", 0) for p in ps_list)
        total_carries_into_box = sum(p.get("carries_into_box", 0) for p in ps_list)
        total_passes_final_third = sum(p.get("passes_into_final_third", 0) for p in ps_list)

        return {
            "possession": stats.get("possession", 50.0),
            "shots": stats.get("shots", 0),
            "shots_on_target": stats.get("shots_on_target", 0),
            "shots_in_box": total_carries_into_box,
            "passes": passes,
            "pass_success_rate": round(passes_completed / max(passes, 1) * 100, 1),
            "final_third_entries": total_passes_final_third,
            "box_entries": total_carries_into_box + total_passes_into_box,
            "progressive_passes": total_progressive_passes,
            "crosses": total_crosses,
            "corners": 0,
            "dribbles": stats.get("dribbles", 0),
            "carries": total_carries,
            "tackles": stats.get("tackles", 0),
            "pressures": total_pressures,
            "interceptions": stats.get("interceptions", 0),
            "blocks": total_blocks,
            "turnovers": total_turnovers,
            "saves": stats.get("saves", 0),
            "xg": round(total_xg, 2),
            "post_shot_xg": round(total_xg * 0.8, 2),
            "key_passes": total_key_passes,
            "box_touches": total_carries_into_box + total_passes_into_box,
            "big_chances": total_big_chances,
            "offsides": total_offsides,
        }

    def run_quick_match(self, home_qq: int, away_qq: int) -> MatchResultData:
        return self._run_match(home_qq, away_qq)

    def run_watch_match(self, home_qq: int, away_qq: int):
        """Generator that yields broadcast lines then final result dict."""
        result_data = self._run_match(home_qq, away_qq)
        yield {
            "type": "start",
            "text": f"主 {result_data.home_name} : {result_data.away_name} 客",
            "subtext": "比赛开始",
        }
        yield {"type": "half", "text": "上半场结束"}
        yield {"type": "half", "text": "下半场结束"}
        yield {"type": "result", "data": result_data}

    def run_ten_matches(self, home_qq: int, away_qq: int) -> TenMatchResult:
        results = []
        total_h = total_a = wins = draws = losses = 0
        for _ in range(10):
            r = self._run_match(home_qq, away_qq)
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
            r = self._run_match(home_qq, away_qq)
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
