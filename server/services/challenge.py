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

    def get_npc_squad(self, difficulty: str = "简单") -> dict:
        from model.player import Player
        from psl_core.constants import NPC_STYLE, STARS, FORWARD, MIDFIELD, GUARD
        from psl_core.formation import get_formation_positions
        from psl_core.card import compute_abilities, compute_real_overall, compute_overall

        if difficulty not in DIFFICULTY:
            raise ChallengeError("Invalid difficulty")

        star = DIFFICULTY[difficulty]["star"]

        npc_idx = time.localtime(time.time()).tm_wday % len(NPC)
        npc = NPC[npc_idx]
        formation = npc["formation"]
        player_ids = npc["players"]

        positions = get_formation_positions(formation)

        cards = []
        total = 0
        fwd = 0
        mid = 0
        grd = 0
        fwd_count = 0
        mid_count = 0
        grd_count = 0

        for i, pid in enumerate(player_ids):
            p = Player.getPlayerByID(pid)
            if p is None:
                cards.append(None)
                continue
            pos = positions[i] if i < len(positions) else "CM"
            style = NPC_STYLE.get(pos, "normal")

            abilities = compute_abilities(
                star=star,
                style=style,
                position=p.Position,
                height=int(p.Height) if p.Height else 180,
                heading_accuracy=p.Heading_Accuracy or 0,
                jumping=p.Jumping or 0,
                strength=p.Strength or 0,
                long_shots=p.Long_Shots or 0,
                shot_power=p.Shot_Power or 0,
                finishing=p.Finishing or 0,
                long_passing=p.Long_Passing or 0,
                short_passing=p.Short_Passing or 0,
                dribbling=p.Dribbling or 0,
                ball_control=p.Ball_Control or 0,
                balance=p.Balance or 0,
                sliding_tackle=p.Sliding_Tackle or 0,
                standing_tackle=p.Standing_Tackle or 0,
                defensive_awareness=p.Defensive_Awareness or 0,
                aggression=p.Aggression or 0,
                interceptions=p.Interceptions or 0,
                sprint_speed=p.Sprint_Speed or 0,
                acceleration=p.Acceleration or 0,
                composure=p.Composure or 0,
                gk_handling=p.GK_Handling or 0,
                gk_diving=p.GK_Diving or 0,
                gk_positioning=p.GK_Positioning or 0,
                gk_reflexes=p.GK_Reflexes or 0,
                reactions=p.Reactions or 0,
            )
            real_ov = compute_real_overall(abilities, pos)
            base_ov = compute_overall(p.Overall, star)

            cards.append({
                "id": 0,
                "player_id": p.ID,
                "name": p.Name,
                "position": pos,
                "overall": base_ov,
                "real_overall": real_ov,
                "star": star,
                "style": style,
                "breach": 0,
                "locked": False,
                "status": 0,
            })

            if pos in FORWARD:
                fwd += real_ov
                fwd_count += 1
            elif pos in MIDFIELD:
                mid += real_ov
                mid_count += 1
            elif pos in GUARD or pos == "GK":
                grd += real_ov
                grd_count += 1
            total += real_ov

        return {
            "formation": formation,
            "total_ability": total,
            "forward_ability": fwd // max(fwd_count, 1),
            "midfield_ability": mid // max(mid_count, 1),
            "guard_ability": grd // max(grd_count, 1),
            "positions": positions[:len(player_ids)],
            "cards": cards,
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
            # Give item rewards (card packs)
            if "item" in awards[match_result]:
                from model.item import Item
                from psl_core.constants import ITEM
                for item_type_key, sub_items in awards[match_result]["item"].items():
                    for sub_item_key, amount in sub_items.items():
                        Item.addItem(u, item_type_key, sub_item_key, amount)
                        pack_name = ITEM[item_type_key]["item"][sub_item_key]["name"]
                        award_msg += f" + {pack_name}卡包x{amount}"


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
            "home_player_stats": result.home_stats.player_stats,
            "away_player_stats": result.away_stats.player_stats,
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
