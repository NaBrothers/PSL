from engine.team import Team
from engine.const import Const
from engine.commentary import CommentaryRenderer, event_player_name, event_target_name
from engine.types import MatchResult, TeamStats, GoalRecord
from engine.types import MatchEvent as PureMatchEvent
from utils.image import toImage
from presentation.stats import _display_width, _format_stat_line
from config import PROJECT_DIR
import json
import os
import random
import re
import time
from dataclasses import dataclass


@dataclass
class MatchEvent:
    minute: int
    second: int
    seq: int
    event_type: str
    text: str
    home_score: int = 0
    away_score: int = 0
    importance: int = 1
    team: object = None
    player: object = None
    xg: float = 0
    target: object = None
    result: str = ""


class Game:

    BROADCAST_INTERVAL = 270

    def __init__(self, matcher, user1, user2, npc=-1, difficulty=0, seed=None, rng=None):
        self.matcher = matcher
        self.home = Team(user1)
        self.away = Team(user2, npc, difficulty)
        self.half = "上半时"
        self.timeline = []
        self.match_events = []
        self.mode = Const.MODE_NORMAL
        self.seed = seed
        self.rng = rng or random.Random(seed)
        self.commentary = CommentaryRenderer(self.rng)
        self.event_seq = 0

    def _load_engine_config(self):
        if hasattr(self, "_engine_config"):
            return self._engine_config

        from psl_core.engine_v2.config import EngineConfig, load_config_from_service

        config = EngineConfig()
        try:
            from server.database import Database
            from server.services.game_config import GameConfigService

            db_path = os.environ.get("PSL_DB_PATH", os.path.join(PROJECT_DIR, "psl.db"))
            config_db = Database(db_path)
            try:
                config_service = GameConfigService(config_db)
                config = load_config_from_service(config_service)
            finally:
                config_db.close()
        except Exception:
            # A missing configuration store must not reintroduce an engine fallback.
            pass

        self._engine_config = config
        return config
    def _formation_key(self, team):
        formation = getattr(team.coach, "formation", "442")
        return formation if formation else "442"

    def _rust_card_payload(self, player):
        card = player.card
        colored_name = card.getNameWithColor()
        color_match = re.match(r"/~([^/])", colored_name)
        try:
            overall = card.getRealOverall(player.position)
        except Exception:
            overall = getattr(card, "overall", 50)
        return {
            "name": player.getName(False),
            "player_id": getattr(card.player, "ID", ""),
            "position": player.position,
            "color": color_match.group(1) if color_match else "w",
            "overall": overall,
            "abilities": dict(player.ability),
        }

    def _apply_rust_player_stats(self, team, stats):
        field_map = {
            "goals": "goals",
            "assists": "assists",
            "shots": "shoots",
            "shots_on_target": "shoots_in_target",
            "xg": "xg",
            "npxg": "npxg",
            "post_shot_xg": "post_shot_xg",
            "big_chances": "big_chances",
            "big_chances_missed": "big_chances_missed",
            "passes": "passes",
            "completed_passes": "successful_passes",
            "key_passes": "key_passes",
            "xa": "xa",
            "progressive_passes": "progressive_passes",
            "passes_into_final_third": "passes_into_final_third",
            "passes_into_box": "passes_into_box",
            "long_passes": "long_passes",
            "completed_long_passes": "completed_long_passes",
            "crosses": "crosses",
            "successful_crosses": "successful_crosses",
            "carries": "carries",
            "progressive_carries": "progressive_carries",
            "carries_into_final_third": "carries_into_final_third",
            "carries_into_box": "carries_into_box",
            "take_ons": "take_ons",
            "successful_take_ons": "successful_take_ons",
            "tackles_attempted": "tackle_attempts",
            "tackles_won": "tackles",
            "interceptions": "interceptions",
            "blocks": "blocks",
            "clearances": "clearances",
            "pressures": "pressures",
            "successful_pressures": "successful_pressures",
            "turnovers": "turnovers",
            "dispossessed": "dispossessed",
            "offsides": "offsides",
            "saves": "saves",
            "goals_conceded": "goals_conceded",
            "psxg_faced": "psxg_faced",
            "goals_prevented": "goals_prevented",
        }
        for index, player in enumerate(team.players):
            player_stats = stats[index] if index < len(stats) else {}
            for source, target in field_map.items():
                setattr(player, target, player_stats.get(source, 0))

            player.short_passes = max(0, player.passes - player.long_passes)
            player.completed_short_passes = max(
                0, player.successful_passes - player.completed_long_passes
            )
            player.dribbles = player.successful_take_ons
            player.shot_log = list(player_stats.get("shot_log", []))
            player.position_samples = [
                tuple(sample) for sample in player_stats.get("position_samples", [])
            ]
            player.goals_detailed = []
            player.current_carry_progress = 0

            pass_network = {}
            for receiver_idx, count in player_stats.get("pass_network", {}).items():
                try:
                    receiver = team.players[int(receiver_idx)]
                except (ValueError, IndexError, TypeError):
                    continue
                pass_network[id(receiver)] = count
            player.pass_connections = pass_network

    def _find_rust_player(self, team, name):
        return next(
            (player for player in team.players if player.getName(False) == name),
            None,
        )

    def _apply_rust_goals(self, goals):
        self.timeline = []
        self.match_events = []
        self.event_seq = 0
        home_score = 0
        away_score = 0

        for goal in sorted(goals, key=lambda item: int(item.get("minute", 0))):
            minute = int(goal.get("minute", 0))
            side = goal.get("team_side", "home")
            team = self.home if side == "home" else self.away
            scorer = self._find_rust_player(team, goal.get("scorer", ""))
            assister = self._find_rust_player(team, goal.get("assister", ""))
            if scorer is None:
                continue

            scorer.goals_detailed.append(minute)
            self.timeline.append((minute, team, scorer, assister))
            event_home_score = home_score
            event_away_score = away_score
            if side == "home":
                home_score += 1
            else:
                away_score += 1
            self.event_seq += 1
            text = scorer.getName() + " 破门"
            if assister is not None:
                text += "，助攻 " + assister.getName()
            self.match_events.append(MatchEvent(
                minute=minute,
                second=0,
                seq=self.event_seq,
                event_type="goal",
                text=text,
                home_score=event_home_score,
                away_score=event_away_score,
                importance=5,
                team=team,
                player=scorer,
                target=assister,
                result="goal",
            ))

    def _apply_rust_team_stats(self, team, raw_stats, score):
        team.getStats()
        possession = float(raw_stats.get("possession", 50.0))
        team.point = int(score)
        team.goals = int(score)
        team.control = int(round(possession * 54.0))
        team.shots_in_box = sum(
            1
            for player in team.players
            for shot in player.shot_log
            if shot.get("in_box")
        )
        team.shots_outside_box = max(0, team.shoots - team.shots_in_box)
        team.xg = round(sum(player.xg for player in team.players), 3)
        team.open_play_xg = team.xg
        team.set_piece_xg = 0
        team.npxg = round(sum(player.npxg for player in team.players), 3)
        team.adjusted_xg = team.xg
        team.xt = 0
        team.final_third_entries = sum(
            player.passes_into_final_third + player.carries_into_final_third
            for player in team.players
        )
        team.box_entries = sum(
            player.passes_into_box + player.carries_into_box
            for player in team.players
        )
        team.key_passes = sum(player.key_passes for player in team.players)
        team.box_touches = team.box_entries
        team.big_chances = sum(player.big_chances for player in team.players)
        team.corners = int(raw_stats.get("corners", 0))
        team.offsides_forced = int(raw_stats.get("offsides_forced", 0))
        team.possessions = max(1, team.turnovers + team.shoots + team.passes // 4)
        team.avg_possession_duration = team.control / team.possessions
        team.zone_stats = {
            "left_channel_attacks": 0,
            "center_channel_attacks": 0,
            "right_channel_attacks": 0,
            "final_third_entries": team.final_third_entries,
            "box_entries": team.box_entries,
            "shots_in_box": team.shots_in_box,
            "shots_outside_box": team.shots_outside_box,
        }

    def _save_rust_replay(self):
        replay_data = getattr(self, "_rust_replay_data", None)
        if not replay_data:
            return ""

        header = replay_data[0] if replay_data[0].get("type") == "header" else None
        if header is not None:
            header.setdefault("home", {})["name"] = self.home.coach.name
            header.setdefault("away", {})["name"] = self.away.coach.name

        replay_dir = os.path.join(
            os.environ.get("PSL_PROJECT_DIR", PROJECT_DIR), "data", "replays"
        )
        os.makedirs(replay_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        match_id = format(getattr(self, "_rust_match_seed", 0), "016x")
        score = f"{self.home.point}-{self.away.point}"
        home_name = self.home.coach.name.replace(" ", "_")
        away_name = self.away.coach.name.replace(" ", "_")
        filename = f"{timestamp}_{match_id}_{home_name}_{away_name}_{score}.jsonl"
        filepath = os.path.join(replay_dir, filename)
        with open(filepath, "w", encoding="utf-8") as replay_file:
            for frame in replay_data:
                replay_file.write(json.dumps(frame, ensure_ascii=False) + "\n")
        replay_files = sorted(
            (
                (os.path.getmtime(os.path.join(replay_dir, name)), os.path.join(replay_dir, name))
                for name in os.listdir(replay_dir)
                if name.endswith(".jsonl")
                and os.path.isfile(os.path.join(replay_dir, name))
            ),
            key=lambda item: item[0],
        )
        for _, old_path in replay_files[:-100]:
            os.remove(old_path)
        return filepath

    def _run_rust_match(self):
        from psl_core.engine_v2.match import MatchV2

        config = self._load_engine_config()
        self._rust_match_seed = (
            self.seed if self.seed is not None else self.rng.getrandbits(64)
        )
        match = MatchV2(
            [self._rust_card_payload(player) for player in self.home.players],
            [self._rust_card_payload(player) for player in self.away.players],
            self._formation_key(self.home),
            self._formation_key(self.away),
            config=config,
            seed=self._rust_match_seed,
        )
        result = match.run()
        self.engine_trace_id = result.trace_id
        self.engine_backend = "rust_match_v2"
        self._rust_replay_data = match.get_replay_data()
        self._apply_rust_player_stats(self.home, result.home_player_stats)
        self._apply_rust_player_stats(self.away, result.away_player_stats)
        self._apply_rust_goals(result.goals)
        self._apply_rust_team_stats(self.home, result.home_stats, result.home_score)
        self._apply_rust_team_stats(self.away, result.away_stats, result.away_score)
        self.half = "下半时"
        self.time = 45 * 60
        return result


    async def start(self, mode):
        return await self._start_rust_match(mode)

    async def _start_rust_match(self, mode):
        self.mode = mode
        if self.mode != Const.MODE_QUICK:
            await self.send(
                "主 " + self.home.coach.name + " : "
                + self.away.coach.name + " 客\n比赛开始"
            )

        self._run_rust_match()

        if self.mode not in (Const.MODE_QUICK, Const.MODE_SILENCE):
            first_half = [event for event in self.match_events if event.minute <= 45]
            second_half = [event for event in self.match_events if event.minute > 45]
            for events, footer in (
                (first_half, "上半场结束"),
                (second_half, "下半场结束"),
            ):
                lines = []
                for event in events:
                    home_score = event.home_score + (1 if event.team is self.home else 0)
                    away_score = event.away_score + (1 if event.team is self.away else 0)
                    score = str(home_score) + ":" + str(away_score)
                    celebration = self.commentary.render(
                        "narrative",
                        "goal_celebration",
                        scorer=event.player.getName(False),
                        team=event.team.coach.name,
                        score=score,
                    )
                    lines.append(
                        "主" + score + "客 "
                        + ("上半时" if event.minute <= 45 else "下半时")
                        + str(event.minute) + ":0 " + event.text
                        + " /~$" + celebration + "/"
                    )
                lines.append(footer)
                await self.send("\n".join(lines))

        stats = await self.printStats()
        if self.mode in (Const.MODE_NORMAL, Const.MODE_QUICK):
            self.replay_path = self._save_rust_replay()
        else:
            self.replay_path = ""
        return stats


    async def send(self, str):
        if self.mode == Const.MODE_QUICK or self.mode == Const.MODE_SILENCE:
            return
        await self.matcher.send(toImage(str))


    async def printStats(self):
        self.home.getStats()
        self.away.getStats()

        if self.mode == Const.MODE_SILENCE:
            return

        report = self.build_match_report()
        if report:
            await self.matcher.send(toImage("[比赛战报]\n" + report))

        detail_msg = "[终场比分]\n"
        detail_msg += "主 " + self.home.coach.name + " " + \
            str(self.home.point) + ":" + str(self.away.point) + \
            " " + self.away.coach.name + " 客\n\n"

        if self.timeline:
            detail_msg += "[比赛事件]\n"
            maxLen = -1
            for case in self.timeline:
                if case[1] == self.home:
                    maxLen = max(maxLen, len(case[2].getName()))
                    if case[3] != None:
                        maxLen = max(maxLen, len(case[3].getName()))
            maxLen = max(maxLen+2, 8)
            for case in self.timeline:
                if case[1] == self.home:
                    detail_msg += case[2].getName().rjust(maxLen) + "   ⚽ "
                    detail_msg += "  " + str(str(case[0]) + "'").ljust(3)
                    if case[3] != None:
                        detail_msg += "\n"
                        detail_msg += str("(" + case[3].getName() + ")").rjust(maxLen)
                else:
                    detail_msg += "".ljust(maxLen+4) + str(case[0]) + "'  "
                    detail_msg += " ⚽   " + case[2].getName()
                    if case[3] != None:
                        detail_msg += "\n"
                        detail_msg += "".ljust(maxLen+9) + "      (" + case[3].getName() + ")"

                detail_msg += "\n\n"
        else:
            maxLen = 8

        if self.home.goals_detailed or self.away.goals_detailed:
            detail_msg += "[进球统计]\n"

        if self.home.goals_detailed:
            detail_msg += "主队：\n"
            for item in self.home.goals_detailed:
                detail_msg += item[0] + " ("
                for i in item[1]:
                    detail_msg += str(i) + "', "
                detail_msg = detail_msg[:-2]
                detail_msg += ")\n"

        if self.away.goals_detailed:
            detail_msg += "客队：\n"
            for item in self.away.goals_detailed:
                detail_msg += item[0] + " ("
                for i in item[1]:
                    detail_msg += str(i) + "', "
                detail_msg = detail_msg[:-2]
                detail_msg += ")\n"

        if self.home.goals_detailed or self.away.goals_detailed:
            detail_msg += "\n"

        detail_msg += "[数据统计]\n"
        total_control = self.home.control + self.away.control
        home_ctrl = str(round(self.home.control*100/total_control, 1)) + "%"
        away_ctrl = str(round(self.away.control*100/total_control, 1)) + "%"
        home_pass_rate = "0%" if self.home.passes == 0 else str(round(self.home.successful_passes*100/self.home.passes, 1)) + "%"
        away_pass_rate = "0%" if self.away.passes == 0 else str(round(self.away.successful_passes*100/self.away.passes, 1)) + "%"
        stats = [
            (home_ctrl, "控球率", away_ctrl),
            (str(self.home.shoots_in_target), "射正", str(self.away.shoots_in_target)),
            (str(self.home.shoots), "射门", str(self.away.shoots)),
            (str(self.home.shots_in_box), "禁区射门", str(self.away.shots_in_box)),
            (str(self.home.passes), "传球", str(self.away.passes)),
            (home_pass_rate, "传球成功率", away_pass_rate),
            (str(self.home.final_third_entries), "进攻三区进入", str(self.away.final_third_entries)),
            (str(self.home.box_entries), "禁区进入", str(self.away.box_entries)),
            (str(self.home.progressive_passes), "推进传球", str(self.away.progressive_passes)),
            (str(self.home.crosses), "传中", str(self.away.crosses)),
            (str(self.home.corners), "角球", str(self.away.corners)),
            (str(self.home.dribbles), "过人", str(self.away.dribbles)),
            (str(self.home.carries), "带球推进", str(self.away.carries)),
            (str(self.home.tackles), "抢断", str(self.away.tackles)),
            (str(self.home.pressures), "逼抢", str(self.away.pressures)),
            (str(self.home.interceptions), "拦截", str(self.away.interceptions)),
            (str(self.home.blocks), "封堵", str(self.away.blocks)),
            (str(self.home.turnovers), "丢失球权", str(self.away.turnovers)),
            (str(self.home.saves), "扑救", str(self.away.saves)),
            (str(round(self.home.xg, 2)), "xG", str(round(self.away.xg, 2))),
            (str(round(self.home.post_shot_xg, 2)), "PSxG", str(round(self.away.post_shot_xg, 2))),
            (str(self.home.key_passes), "关键传球", str(self.away.key_passes)),
            (str(self.home.box_touches), "禁区触球", str(self.away.box_touches)),
            (str(self.home.big_chances), "绝对机会", str(self.away.big_chances)),
        ]
        label_width = max(max(_display_width(s[1]) for s in stats) + 2, 14)
        for home_val, label, away_val in stats:
            line = _format_stat_line(home_val, label, away_val, maxLen, label_width)
            detail_msg += line + "\n"
        await self.matcher.send(toImage(detail_msg))
        return detail_msg


    def build_match_report(self):
        home = self.home
        away = self.away
        home_name = home.coach.name
        away_name = away.coach.name
        total_control = home.control + away.control
        home_ctrl = round(home.control * 100 / total_control, 1) if total_control else 50
        away_ctrl = round(away.control * 100 / total_control, 1) if total_control else 50
        score = f"{home.point}:{away.point}"

        paragraphs = []
        paragraphs.append(f"{home_name} 与 {away_name} 战成 {score}。")

        # 比赛结果
        if home.point == away.point:
            key = "result_draw_0" if home.point == 0 else "result_draw"
        elif home.point > away.point:
            diff = home.point - away.point
            key = "result_home_big_win" if diff >= 3 else ("result_home_win_2" if diff == 2 else "result_home_win_1")
        else:
            diff = away.point - home.point
            key = "result_away_big_win" if diff >= 3 else ("result_away_win_2" if diff == 2 else "result_away_win_1")
        paragraphs.append(self.commentary.render("narrative", key, home=home_name, away=away_name, score=score))

        # 控球和场面
        shots = f"{home.shoots}:{away.shoots}"
        sot = f"{home.shoots_in_target}:{away.shoots_in_target}"
        if home_ctrl > 55:
            paragraphs.append(self.commentary.render("narrative", "control_dominant",
                dominant=home_name, other=away_name, ctrl=str(home_ctrl), shots=shots, sot=sot))
        elif away_ctrl > 55:
            paragraphs.append(self.commentary.render("narrative", "control_dominant",
                dominant=away_name, other=home_name, ctrl=str(away_ctrl), shots=shots, sot=sot))
        else:
            paragraphs.append(self.commentary.render("narrative", "control_balanced",
                home_ctrl=str(home_ctrl), away_ctrl=str(away_ctrl), shots=shots, sot=sot))

        # 进球叙述
        goals = [(ev.minute, ev) for ev in self.match_events if ev.event_type == "goal"]
        if goals:
            parts = []
            for minute, ev in goals:
                scorer = event_player_name(ev)
                if ev.target:
                    parts.append(self.commentary.render("narrative", "goal_desc",
                        minute=str(minute), scorer=scorer, assister=ev.target.getName()))
                else:
                    parts.append(self.commentary.render("narrative", "goal_desc_solo",
                        minute=str(minute), scorer=scorer))
            paragraphs.append(" ".join(parts))
        else:
            shots_total = home.shoots + away.shoots
            if shots_total > 20:
                paragraphs.append(self.commentary.render("narrative", "goals_none_many_shots", total_shots=str(shots_total)))
            else:
                paragraphs.append(self.commentary.render("narrative", "goals_none_few_shots"))

        # 门将表现
        saves_events = [ev for ev in self.match_events if ev.event_type == "save"]
        if saves_events:
            keeper_saves = {}
            for ev in saves_events:
                if ev.target:
                    name = ev.target.getName()
                    keeper_saves[name] = keeper_saves.get(name, 0) + 1
                elif ev.player:
                    name = ev.player.getName()
                    keeper_saves[name] = keeper_saves.get(name, 0) + 1
            if keeper_saves:
                best_keeper = max(keeper_saves, key=keeper_saves.get)
                best_saves = keeper_saves[best_keeper]
                if best_saves >= 3:
                    paragraphs.append(self.commentary.render("narrative", "keeper_heroic", keeper=best_keeper, saves=str(best_saves)))

        # xG 对比
        home_xg = round(home.xg, 2)
        away_xg = round(away.xg, 2)
        if home_xg + away_xg > 0:
            if home.point > home_xg + 0.5:
                paragraphs.append(self.commentary.render("narrative", "xg_overperform_home", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
            elif away.point > away_xg + 0.5:
                paragraphs.append(self.commentary.render("narrative", "xg_overperform_away", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
            elif home_xg > home.point + 0.8:
                paragraphs.append(self.commentary.render("narrative", "xg_underperform_home", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))
            elif away_xg > away.point + 0.8:
                paragraphs.append(self.commentary.render("narrative", "xg_underperform_away", home=home_name, away=away_name, home_xg=str(home_xg), away_xg=str(away_xg)))

        return "\n".join(paragraphs)


    def run_simulation(self):
        """Run the full match simulation without any IO. Returns MatchResult."""
        self.mode = Const.MODE_SILENCE
        self._run_rust_match()
        result = self.to_result()
        self.replay_path = self._save_rust_replay()
        result.replay_path = self.replay_path
        return result

    def to_result(self) -> MatchResult:
        """Convert internal game state to a pure MatchResult data object."""
        self.home.getStats()
        self.away.getStats()

        def _team_stats(team) -> TeamStats:
            return TeamStats(
                name=team.coach.name,
                point=team.point,
                control=team.control,
                shoots=team.shoots,
                shoots_in_target=team.shoots_in_target,
                goals=team.goals,
                shots_in_box=team.shots_in_box,
                shots_outside_box=team.shots_outside_box,
                passes=team.passes,
                successful_passes=team.successful_passes,
                progressive_passes=team.progressive_passes,
                passes_into_final_third=team.passes_into_final_third,
                passes_into_box=team.passes_into_box,
                long_passes=team.long_passes,
                completed_long_passes=team.completed_long_passes,
                short_passes=team.short_passes,
                completed_short_passes=team.completed_short_passes,
                crosses=team.crosses,
                successful_crosses=team.successful_crosses,
                corners=team.corners,
                final_third_entries=team.final_third_entries,
                box_entries=team.box_entries,
                dribbles=team.dribbles,
                carries=team.carries,
                progressive_carries=team.progressive_carries,
                carries_into_final_third=team.carries_into_final_third,
                carries_into_box=team.carries_into_box,
                take_ons=team.take_ons,
                successful_take_ons=team.successful_take_ons,
                assists=team.assists,
                tackles=team.tackles,
                tackle_attempts=team.tackle_attempts,
                interceptions=team.interceptions,
                blocks=team.blocks,
                clearances=team.clearances,
                pressures=team.pressures,
                successful_pressures=team.successful_pressures,
                defensive_actions=team.defensive_actions,
                turnovers=team.turnovers,
                offsides=team.offsides,
                offsides_forced=team.offsides_forced,
                saves=team.saves,
                xg=team.xg,
                open_play_xg=team.open_play_xg,
                set_piece_xg=team.set_piece_xg,
                npxg=team.npxg,
                post_shot_xg=team.post_shot_xg,
                psxg_faced=team.psxg_faced,
                goals_prevented=team.goals_prevented,
                adjusted_xg=team.adjusted_xg,
                xt=team.xt,
                key_passes=team.key_passes,
                box_touches=team.box_touches,
                big_chances=team.big_chances,
                possessions=team.possessions,
                avg_possession_duration=team.avg_possession_duration,
                goals_detailed=team.goals_detailed,
                player_stats=team.player_stats,
                position_stats=team.position_stats,
                zone_stats=team.zone_stats,
            )

        events = []
        for ev in self.match_events:
            team_side = "home" if ev.team == self.home else "away"
            player_name = ev.player.getName() if ev.player else ""
            target_name = ev.target.getName() if ev.target else ""
            events.append(PureMatchEvent(
                minute=ev.minute,
                second=ev.second,
                seq=ev.seq,
                event_type=ev.event_type,
                text=ev.text,
                home_score=ev.home_score,
                away_score=ev.away_score,
                importance=ev.importance,
                team_side=team_side,
                player_name=player_name,
                xg=ev.xg,
                target_name=target_name,
                result=ev.result,
            ))

        timeline = []
        for item in self.timeline:
            team_side = "home" if item[1] == self.home else "away"
            scorer_name = item[2].getName() if item[2] else ""
            assister_name = item[3].getName() if item[3] else None
            timeline.append(GoalRecord(
                minute=item[0],
                team_side=team_side,
                scorer_name=scorer_name,
                assister_name=assister_name,
            ))

        return MatchResult(
            home_stats=_team_stats(self.home),
            away_stats=_team_stats(self.away),
            events=events,
            timeline=timeline,
        )
