from model.user import User
from engine.player import Player
from engine.team import Team
from engine.const import Const
from engine.commentary import CommentaryRenderer, event_player_name, event_target_name
from engine.probability import build_shot_context, expected_threat, pass_success_probability, shot_on_target_goal_probability
from engine.types import MatchResult, TeamStats, GoalRecord
from engine.types import MatchEvent as PureMatchEvent
from utils.image import toImage
from engine.display import Display
from config import PROJECT_DIR
import random
import math
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
        self.step = 0
        self.time = 0
        self.offence = Team(user1)
        self.defence = Team(user2, npc, difficulty)
        self.home = self.offence
        self.away = self.defence
        self.half = "上半时"
        self.ball_holder = self.offence.players[10]
        self.assister = None
        self.timeline = []
        self.match_events = []
        self.current_events = []
        self.mode = Const.MODE_NORMAL
        self.rng = rng or random.Random(seed)
        self.commentary = CommentaryRenderer(self.rng)
        self.possession_action_count = 0
        self.possession_box_touches = 0
        self.broadcast_buffer = []
        self.last_broadcast_time = 0
        self.broadcast_has_goal = False
        self.event_seq = 0
        self._movement_tick = 0
        self.goal_kick_pending = False

    async def start(self, mode):
        self.mode = mode
        if self.mode in (Const.MODE_NORMAL, Const.MODE_QUICK):
            self.init_replay_recorder()
        self.resetPosition()
        if hasattr(self, 'recorder'):
            self.recorder.record_frame(self)
        if self.mode != Const.MODE_QUICK:
            await self.send("主 " + self.home.coach.name + " : " + self.away.coach.name + " 客\n比赛开始")
        self.last_broadcast_time = 0
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()
            await self.maybe_broadcast()
        await self.flush_broadcast("上半场结束")

        self.half = "下半时"
        self.time = 0
        self.last_broadcast_time = 0
        if self.offence is self.home:
            self.swap()
        self.resetPosition()
        self.changeBallHolderToOpen()
        if hasattr(self, 'recorder'):
            self.recorder.record_frame(self)
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()
            await self.maybe_broadcast()
        await self.flush_broadcast("下半场结束")

        stats = await self.printStats()
        self.replay_path = self.save_replay() if hasattr(self, 'recorder') else ""
        return stats

    async def send(self, str):
        if self.mode == Const.MODE_QUICK or self.mode == Const.MODE_SILENCE:
            return
        await self.matcher.send(toImage(str))

    def event_prefix(self, ev):
        return "主" + str(ev.home_score) + ":" + str(ev.away_score) + "客 " + self.half + str(ev.minute) + ":" + str(ev.second)

    def broadcast_goal(self, scorer):
        score = str(self.home.point) + ":" + str(self.away.point)
        team = self.offence.coach.name
        text = self.commentary.render("narrative", "goal_celebration", scorer=scorer.getName(False), team=team, score=score)
        prefix = "主" + score + "客 " + self.half + str(self.time // 60) + ":" + str(self.time % 60)
        self.broadcast_buffer.append(prefix + " /~$" + text + "/")

    async def maybe_broadcast(self):
        if self.mode == Const.MODE_QUICK or self.mode == Const.MODE_SILENCE:
            return
        elapsed = self.time - self.last_broadcast_time
        if self.broadcast_has_goal or elapsed >= self.BROADCAST_INTERVAL:
            await self.flush_broadcast()

    async def flush_broadcast(self, footer=None):
        if self.mode == Const.MODE_QUICK or self.mode == Const.MODE_SILENCE:
            self.broadcast_buffer = []
            self.broadcast_has_goal = False
            return
        lines = list(self.broadcast_buffer)
        if footer:
            lines.append(footer)
        self.broadcast_buffer = []
        self.broadcast_has_goal = False
        self.last_broadcast_time = self.time
        if not lines:
            return
        msg = "\n".join(lines)
        await self.send(msg)
        time.sleep(Const.PRINT_DELAY)

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
            (str(self.home.passes), "传球", str(self.away.passes)),
            (home_pass_rate, "传球成功率", away_pass_rate),
            (str(self.home.dribbles), "过人", str(self.away.dribbles)),
            (str(self.home.carries), "带球推进", str(self.away.carries)),
            (str(self.home.tackles), "抢断", str(self.away.tackles)),
            (str(self.home.interceptions), "拦截", str(self.away.interceptions)),
            (str(self.home.blocks), "封堵", str(self.away.blocks)),
            (str(self.home.saves), "扑救", str(self.away.saves)),
            (str(round(self.home.xg, 2)), "xG", str(round(self.away.xg, 2))),
            (str(self.home.key_passes), "关键传球", str(self.away.key_passes)),
            (str(self.home.box_touches), "禁区触球", str(self.away.box_touches)),
            (str(self.home.big_chances), "绝对机会", str(self.away.big_chances)),
        ]
        label_width = max(len(s[1]) for s in stats) + 2
        val_width = 8
        for home_val, label, away_val in stats:
            line = home_val.rjust(val_width) + "  " + label.center(label_width) + "  " + away_val.ljust(val_width)
            detail_msg += line + "\n"
        await self.matcher.send(toImage(detail_msg))
        return detail_msg

    # 开始一个回合

    def oneStep(self):
        self.play_possession()

    def play_possession(self):
        self.step += 1
        self.offence.possessions += 1
        self.possession_action_count = 0
        self.possession_box_touches = 0
        self.current_events = []
        self.reset_action_flag()
        while 1:
            if self.possession_action_count >= 28:
                self.swap()
                self.changeRandomBallHolder()
                return
            action_time = self.get_action_duration()
            self.offence.control += action_time
            self.time += action_time
            if self.time > 45 * 60:
                return
            self.possession_action_count += 1
            # 持球人行为
            self.ball_holder.action_flag = True
            self.keep_offence_players_onside()
            if self.goal_kick_pending and self.ball_holder.position == "GK":
                self.play_goal_kick()
                return
            action_frame = self.recorder.record_frame(self) if hasattr(self, 'recorder') else None
            # 持球人观测防守球员数量
            defence_players = self.getDefencePlayersInArea(
                self.ball_holder.x,
                self.ball_holder.y,
                10)
            # for def_p in defence_players:
            #   print(def_p.name)
            defence_players_number = len(defence_players)
            # 射门路线球员数量
            shoot_defence_players_number = len(
                self.getShootDefencePlayers(self.ball_holder.x, self.ball_holder.y))
            shot_context = self.create_shot(self.ball_holder, shoot_defence_players_number)
            # 持球人行为选择
            holder_action = self.ball_holder.choose_holding_action_type(
                defence_players_number,
                shoot_defence_players_number,
                self.rng,
                shot_context
            )
            if self.ball_holder.position == "GK":
                holder_action = "PASS"
            if holder_action == "SHOOT":
                shot = shot_context
                shoot_x = self.ball_holder.shooting(shot.on_target_probability, self.rng)
                self.record_shot_quality(shot, self.ball_holder)
                if shot.distance >= 20:
                    case = Display.print_long_shot(self.ball_holder, int(shot.distance))
                else:
                    case = Display.print_short_shot(self.ball_holder, int(shot.distance))
                self.printCase(case, "shot", 3, self.ball_holder, xg=shot.raw_xg)
                self.ball_holder.shoots += 1
                on_target = Const.LEFT_GOALPOST <= shoot_x <= Const.RIGHT_GOALPOST
                if not on_target:
                    case = Display.print_miss_shot()
                    self.printCase(case, "miss", 3, self.ball_holder, xg=shot.raw_xg)
                    if hasattr(self, 'recorder'):
                        flight = self.recorder.make_ball_flight(self, self.ball_holder, [shoot_x, 0], "shot", on_target=False)
                        self.recorder.record_frame(self, ball_flight=flight, event_text="MISS", pause_ms=1200)
                    self.swap()
                    self.changeBallHolderToGK()
                    self.record_transition_frame()
                    return
                def_players = self.getWayDefencePlayers(
                    self.ball_holder.x, self.ball_holder.y, shoot_x, 0)
                shoot = self.ball_holder.get_shooting_ability(shoot_x)
                for def_player in def_players:
                    if def_player.position == "GK":
                        continue
                    def_player.blocks += 1
                    def_player.interceptions += 1
                    distance = def_player.get_distance_line(
                        self.ball_holder.x, self.ball_holder.y, Const.WIDTH / 2, 0)

                    if def_player.intercepting(shoot, distance, self.rng):
                        case = Display.print_interception(def_player)
                        self.printCase(case, "turnover", 3, def_player)
                        self.swap()
                        self.changeBallHolder(def_player)
                        self.record_transition_frame()
                        return
                gk = self.getDefenceGK()
                self.ball_holder.shoots_in_target += 1
                goal_probability = self.adjust_shot_for_keeper(shot, gk)
                self.offence.adjusted_xg += shot.on_target_probability * goal_probability - shot.goal_probability
                if self.rng.random() >= goal_probability:
                    case = Display.print_saving(gk)
                    self.printCase(case, "save", 4, self.ball_holder, gk, shot.raw_xg)
                    gk.saves += 1
                    if hasattr(self, 'recorder'):
                        flight = self.recorder.make_ball_flight(self, self.ball_holder, [shoot_x, 0], "shot", on_target=True)
                        self.recorder.record_frame(self, ball_flight=flight, event_text="SAVE", pause_ms=1200)
                    self.swap()
                    self.changeBallHolderToGK()
                    self.record_transition_frame()
                    return
                case = Display.print_goal(
                    self.ball_holder, gk, self.assister)
                self.printCase(case, "goal", 5, self.ball_holder, self.assister, shot.raw_xg)
                self.offence.point += 1
                scorer = self.ball_holder
                self.ball_holder.goals += 1
                self.ball_holder.goals_detailed.append(self.getTime())
                if self.assister:
                    self.assister.assists += 1
                self.timeline.append(
                    (self.getTime(), self.offence, self.ball_holder, self.assister))
                if hasattr(self, 'recorder'):
                    flight = self.recorder.make_ball_flight(self, self.ball_holder, [shoot_x, 0], "shot", on_target=True)
                    self.recorder.record_frame(self, ball_flight=flight, event_text="GOAL", pause_ms=1500)
                self.swap()
                self.broadcast_goal(scorer)
                self.resetPosition()
                self.changeBallHolderToOpen()
                if hasattr(self, 'recorder'):
                    self.recorder.record_frame(self, cut=True)
                return
            elif holder_action == "DRIBBLE":
                dribble_pos = self.ball_holder.dribbling(self.getDefencePlayersInArea(
                    self.ball_holder.x,
                    self.ball_holder.y,
                    5))
                case = Display.print_controlling(
                    self.ball_holder, Const.ANGLE[dribble_pos[2]])
                self.printCase(case, "carry", 1, self.ball_holder)
                def_players = self.getWayDefencePlayers(
                    self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])
                for def_player in def_players:
                    if def_player.position == "GK":
                        continue
                    def_player.tackle_attempts += 1
                    # 计算防守球员到球路的距离
                    distance = def_player.get_distance_line(
                        self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])

                    if def_player.intercepting(self.ball_holder.ability["Dribbling"], distance-def_player.ability["Speed"]/10, self.rng):
                        case = Display.print_tackling(
                            self.ball_holder, def_player)
                        self.printCase(case, "turnover", 3, def_player, self.ball_holder)
                        def_player.tackles += 1
                        self.swap()
                        self.changeBallHolder(def_player)
                        self.record_transition_frame()
                        return
                    else:
                        case = Display.print_dribbling(
                            self.ball_holder, def_player)
                        self.printCase(case, "carry", 1, self.ball_holder, def_player)
                        self.ball_holder.dribbles += 1
                        def_player.action_flag = True
                carry_progress = max(0, self.ball_holder.y - dribble_pos[1])
                self.ball_holder.moving(dribble_pos[0], dribble_pos[1])
                if carry_progress >= 5:
                    self.ball_holder.carries += 1
                if carry_progress >= 12:
                    self.ball_holder.progressive_carries += 1
                self.record_box_touch(self.ball_holder)
                self.record_expected_threat(self.ball_holder, 0.8)
            elif holder_action == "PASS":
                self.ball_holder.passes += 1
                risky_line_pass = self.should_attempt_risky_line_pass()
                if risky_line_pass:
                    self.trigger_early_run()
                pass_targets = self.getOffenceTeamMates() if risky_line_pass else self.get_available_pass_targets()
                passing = self.ball_holder.passing(pass_targets, self.rng, self.build_pass_lane_bias(pass_targets))
                passing_type = passing[0]
                passing_aim = passing[1]
                if passing_type == "ROLLING":
                    distance = self.ball_holder.get_distance_player(
                        passing_aim)
                    case = Display.print_short_pass(
                        self.ball_holder, passing_aim, int(distance))
                    pass_event_type = "key_pass" if passing_aim.y <= 25 else "pass"
                    pass_importance = 2 if pass_event_type == "key_pass" else 1
                    self.printCase(case, pass_event_type, pass_importance, self.ball_holder, passing_aim)
                    if self.is_offside(self.ball_holder, passing_aim):
                        self.printCaseWithPlayer(passing_aim, "处在越位位置", "turnover", 3)
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.recorder.make_pass_flight(self, self.ball_holder, passing_aim)
                        self.swap()
                        self.changeBallHolderToGK()
                        self.record_transition_frame()
                        return
                    pressure = len(self.getDefencePlayersInArea(self.ball_holder.x, self.ball_holder.y, 10))
                    pass_probability = pass_success_probability(self.ball_holder.ability["Short_Passing"], distance, pressure, False)
                    if self.rng.random() > pass_probability:
                        self.printCaseWithPlayer(self.ball_holder, "传球失误", "turnover", 3)
                        interceptor = self.choose_pass_interceptor(self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y, 5)
                        passer = self.ball_holder
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.make_broken_pass_flight(action_frame, passer, passing_aim, interceptor)
                        self.swap()
                        if interceptor is not None:
                            self.changeBallHolder(interceptor)
                        else:
                            self.changeRandomBallHolder(target=passing_aim)
                            if action_frame is not None and action_frame.get("ball_flight") and hasattr(self, 'recorder'):
                                action_frame["ball_flight"]["path"].append(self.recorder._player_to_absolute(self, self.ball_holder))
                                action_frame["ball_flight"]["to"] = action_frame["ball_flight"]["path"][-1]
                        self.record_transition_frame()
                        return
                    def_players = self.getWayDefencePlayers(
                        self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
                    for def_player in def_players:
                        if def_player.position == "GK":
                            continue
                        def_player.tackle_attempts += 1
                        def_player.interceptions += 1
                        # 计算防守球员到球路的距离
                        distance = def_player.get_distance_line(
                            self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
                        if def_player.intercepting(self.ball_holder.ability["Short_Passing"], distance, self.rng):
                            case = Display.print_tackling(
                                self.ball_holder, def_player)
                            self.printCase(case, "turnover", 3, def_player, self.ball_holder)
                            def_player.tackles += 1
                            if action_frame is not None and hasattr(self, 'recorder'):
                                action_frame["ball_flight"] = self.recorder.make_pass_flight(self, self.ball_holder, def_player)
                            self.swap()
                            self.changeBallHolder(def_player)
                            self.record_transition_frame()
                            return
                        else:
                            def_player.action_flag = True
                    self.ball_holder.successful_passes += 1
                    self.ball_holder.action_flag = False
                    self.assister = self.ball_holder
                    if passing_aim.y <= 25:
                        self.offence.key_passes += 1
                    self.record_expected_threat(passing_aim, self.ball_holder.ability["Short_Passing"] / 100)
                    if hasattr(self, 'recorder') and self.recorder:
                        flight = self.recorder.make_pass_flight(self, self.ball_holder, passing_aim)
                        if action_frame is not None:
                            action_frame["ball_flight"] = flight
                    self.changeBallHolder(passing_aim)
                    self.record_box_touch(passing_aim)
                    # passing_aim.action_flag = True
                else:
                    passing_ability = self.ball_holder.get_passing_ability(
                        passing_aim)
                    distance = self.ball_holder.get_distance_player(
                        passing_aim)
                    case = Display.print_long_pass(
                        self.ball_holder, passing_aim, int(distance))
                    pass_event_type = "key_pass" if passing_aim.y <= 25 else "long_pass"
                    pass_importance = 2 if pass_event_type == "key_pass" else 1
                    self.printCase(case, pass_event_type, pass_importance, self.ball_holder, passing_aim)
                    if self.is_offside(self.ball_holder, passing_aim):
                        self.printCaseWithPlayer(passing_aim, "处在越位位置", "turnover", 3)
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.recorder.make_pass_flight(self, self.ball_holder, passing_aim)
                        self.swap()
                        self.changeBallHolderToGK()
                        self.record_transition_frame()
                        return
                    pressure = len(self.getDefencePlayersInArea(self.ball_holder.x, self.ball_holder.y, 12))
                    pass_probability = pass_success_probability(passing_ability, distance, pressure, True)
                    if self.rng.random() > pass_probability:
                        self.printCaseWithPlayer(self.ball_holder, "长传失误", "turnover", 3)
                        interceptor = self.choose_pass_interceptor(self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y, 8)
                        passer = self.ball_holder
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.make_broken_pass_flight(action_frame, passer, passing_aim, interceptor)
                        self.swap()
                        if interceptor is not None:
                            self.changeBallHolder(interceptor)
                        else:
                            self.changeRandomBallHolder(target=passing_aim)
                            if action_frame is not None and action_frame.get("ball_flight") and hasattr(self, 'recorder'):
                                action_frame["ball_flight"]["path"].append(self.recorder._player_to_absolute(self, self.ball_holder))
                                action_frame["ball_flight"]["to"] = action_frame["ball_flight"]["path"][-1]
                        self.record_transition_frame()
                        return
                    for player in self.defence.players + self.offence.players:
                        if player.position == "GK":
                            continue
                        if player.get_distance_player(passing_aim) < 15 * distance / passing_ability + player.ability["Speed"] / 10\
                                and not player.action_flag:
                            if self.isDefencePlayer(player):
                                player.tackle_attempts += 1
                            player.approaching(passing_aim.x, passing_aim.y)
                            player.action_flag = True
                    roll_point_players = self.getPlayersInArea(
                        passing_aim.x, passing_aim.y, 15 * distance / passing_ability)
                    if len(roll_point_players) == 0:
                        self.printCaseWithPlayer(self.ball_holder, "传球出界", "turnover", 3)
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.recorder.make_ball_flight(self, self.ball_holder, [passing_aim.x, passing_aim.y], "pass")
                        self.swap()
                        self.changeBallHolderToGK()
                        self.record_transition_frame()
                        return
                    roll_winner = roll_point_players[0]
                    largest_point = -1
                    for player in roll_point_players:
                        random_max = int(
                            player.ability["Heading"] * 100 / (player.get_distance_player(passing_aim) + 1))
                        rand = self.rng.randint(0, random_max)
                        if rand > largest_point:
                            largest_point = rand
                            roll_winner = player
                    if self.isDefencePlayer(roll_winner):
                        self.printCaseWithPlayer(roll_winner, "顶到了球", "turnover", 3)
                        if action_frame is not None and hasattr(self, 'recorder'):
                            action_frame["ball_flight"] = self.recorder.make_pass_flight(self, self.ball_holder, roll_winner)
                        self.swap()
                        self.changeBallHolder(roll_winner)
                        self.record_transition_frame()
                        return
                    else:
                        self.ball_holder.successful_passes += 1
                        self.assister = self.ball_holder
                        if passing_aim.y <= 25:
                            self.offence.key_passes += 1
                        self.record_expected_threat(passing_aim, passing_ability / 100)
                        self.record_box_touch(roll_winner)
                        if hasattr(self, 'recorder') and self.recorder:
                            flight = self.recorder.make_pass_flight(self, self.ball_holder, roll_winner)
                            if action_frame is not None:
                                action_frame["ball_flight"] = flight
                        distance_goal = roll_winner.get_distance(
                            Const.WIDTH / 2, 0)
                        rand = self.rng.randint(
                            0, int(roll_winner.ability["Heading"] + distance_goal * 10))
                        if rand < roll_winner.ability["Heading"] and distance_goal < 25:
                            header_shot = self.create_shot(roll_winner, len(self.getDefencePlayersInArea(roll_winner.x, roll_winner.y, 10)), True)
                            self.record_shot_quality(header_shot, roll_winner)
                            self.record_box_touch(roll_winner)
                            case = Display.print_high_shot(roll_winner)
                            self.printCase(case, "shot", 3, roll_winner, xg=header_shot.raw_xg)
                            gk = self.getDefenceGK()
                            roll_winner.shoots_in_target += 1
                            goal_probability = self.adjust_shot_for_keeper(header_shot, gk)
                            self.offence.adjusted_xg += header_shot.on_target_probability * goal_probability - header_shot.goal_probability
                            if self.rng.random() >= goal_probability:
                                case = Display.print_saving(gk)
                                self.printCase(case, "save", 4, roll_winner, gk, header_shot.raw_xg)
                                gk.saves += 1
                                if hasattr(self, 'recorder'):
                                    flight = self.recorder.make_ball_flight(self, roll_winner, [Const.WIDTH / 2, 0], "shot", on_target=True)
                                    self.recorder.record_frame(self, ball_flight=flight, event_text="SAVE", pause_ms=1200)
                                self.swap()
                                self.changeBallHolderToGK()
                                self.record_transition_frame()
                            else:
                                case = Display.print_goal(
                                    roll_winner, gk, self.assister)
                                self.printCase(case, "goal", 5, roll_winner, self.assister, header_shot.raw_xg)
                                self.offence.point += 1
                                scorer = roll_winner
                                roll_winner.goals += 1
                                roll_winner.goals_detailed.append(
                                    self.getTime())
                                if self.assister:
                                    self.assister.assists += 1
                                self.timeline.append(
                                    (self.getTime(), self.offence, roll_winner, self.assister))
                                if hasattr(self, 'recorder'):
                                    flight = self.recorder.make_ball_flight(self, roll_winner, [Const.WIDTH / 2, 0], "shot", on_target=True)
                                    self.recorder.record_frame(self, ball_flight=flight, event_text="GOAL", pause_ms=1500)
                                self.swap()
                                self.broadcast_goal(scorer)
                                self.resetPosition()
                                self.changeBallHolderToOpen()
                                if hasattr(self, 'recorder'):
                                    self.recorder.record_frame(self, cut=True)
                            return
                        else:
                            self.changeBallHolder(roll_winner)
                            if self.isDefencePlayer(roll_winner):
                                return

            self.run_off_ball_movement()

            if action_frame is not None and action_frame.get("ball_flight", {}).get("type") == "pass":
                action_frame["ball_flight"]["to"] = self.recorder._player_to_absolute(self, self.ball_holder)
            self.reset_action_flag()

    # 互换攻守方

    def swap(self):
        self.flush_possession_summary()
        tmp = self.offence
        self.offence = self.defence
        self.defence = tmp
        self.printCase("球权转换")
        self.reset_action_flag()
        self.swapPosition(self.offence)
        self.swapPosition(self.defence)
        self.assister = None
        self.possession_action_count = 0

    def run_off_ball_movement(self):
        self._movement_tick += 1
        offside_line = self.get_offside_line_y()
        presser = self.choose_defensive_presser()
        cover = self.choose_defensive_cover(presser)
        for player in self.offence.players:
            if player.action_flag or player == self.ball_holder:
                continue
            self.move_offence_player(player, offside_line)
        for player in self.defence.players:
            if player.action_flag or player == self.ball_holder:
                continue
            self.move_defence_player(player, presser, cover)
        self.keep_shape_bounds()

    def record_transition_frame(self):
        if not hasattr(self, 'recorder'):
            return
        self.run_off_ball_movement()
        self.recorder.record_frame(self, pause_ms=1400)

    def play_goal_kick(self):
        self.goal_kick_pending = False
        self.arrange_goal_kick_shape()
        if hasattr(self, 'recorder'):
            self.recorder.record_frame(self, event_text="GOAL_KICK_SETUP", pause_ms=900)
        self.ball_holder.passes += 1
        target = self.choose_goal_kick_target()
        distance = self.ball_holder.get_distance_player(target)
        event_type = "long_pass" if distance > 36 else "pass"
        case = Display.print_long_pass(self.ball_holder, target, int(distance)) if distance > 36 else Display.print_short_pass(self.ball_holder, target, int(distance))
        self.printCase(case, event_type, 2 if event_type == "long_pass" else 1, self.ball_holder, target)
        self.ball_holder.successful_passes += 1
        self.assister = None
        if hasattr(self, 'recorder') and self.recorder:
            flight = self.recorder.make_pass_flight(self, self.ball_holder, target)
            self.recorder.record_frame(self, ball_flight=flight, event_text="GOAL_KICK", pause_ms=800)
        self.changeBallHolder(target)
        self.run_off_ball_movement()
        if hasattr(self, 'recorder'):
            self.recorder.record_frame(self)

    def arrange_goal_kick_shape(self):
        left_goal_kick = self.offence is self.home
        def mirror_y(y):
            return y if left_goal_kick else Const.LENGTH - y

        for player in self.offence.players:
            y = self.set_piece_y(player, attacking=True, phase="goal_kick")
            self.set_player_absolute(player, self.team_shape_abs_x(player), mirror_y(y))
        for player in self.defence.players:
            y = self.set_piece_y(player, attacking=False, phase="goal_kick")
            self.set_player_absolute(player, self.team_shape_abs_x(player), mirror_y(y))

    def set_piece_y(self, player, attacking, phase):
        source_y = player.default_y
        if phase != "goal_kick":
            return self.shape_y(player, defending=not attacking)
        if player.position == "GK":
            return 5 if attacking else 100
        if attacking:
            if source_y >= 70:
                return self.remap(source_y, 70, 100, 18, 5)
            if source_y >= 50:
                return self.remap(source_y, 50, 70, 42, 26)
            if source_y >= 32:
                return self.remap(source_y, 32, 50, 50, 42)
            return self.remap(source_y, 20, 32, 60, 50)
        if source_y >= 70:
            return self.remap(source_y, 70, 100, 58, 100)
        if source_y >= 50:
            return self.remap(source_y, 50, 70, 44, 58)
        if source_y >= 32:
            return self.remap(source_y, 32, 50, 38, 44)
        return self.remap(source_y, 20, 32, 31, 36)

    def remap(self, value, src_min, src_max, dst_min, dst_max):
        if src_max == src_min:
            return dst_min
        ratio = self.clamp((value - src_min) / (src_max - src_min), 0, 1)
        return dst_min + (dst_max - dst_min) * ratio

    def team_shape_abs_x(self, player):
        return player.default_x if player in self.home.players else Const.WIDTH - player.default_x

    def set_player_absolute(self, player, abs_x, abs_y):
        if player in self.home.players:
            if self.offence is self.home:
                player.x = abs_x
                player.y = Const.LENGTH - abs_y
            else:
                player.x = Const.WIDTH - abs_x
                player.y = abs_y
        else:
            if self.offence is self.home:
                player.x = abs_x
                player.y = Const.LENGTH - abs_y
            else:
                player.x = Const.WIDTH - abs_x
                player.y = abs_y

    def choose_goal_kick_target(self):
        short_targets = [p for p in self.offence.players if p.position in ("LB", "LCB", "CB", "RCB", "RB")]
        long_targets = [p for p in self.offence.players if p.position in ("ST", "CF", "LW", "RW", "CAM")]
        if short_targets and (not long_targets or self.rng.random() < 0.72):
            return min(short_targets, key=lambda p: self.ball_holder.get_distance_player(p) - p.ability["Short_Passing"] / 20)
        return min(long_targets or self.getOffenceTeamMates(), key=lambda p: self.ball_holder.get_distance_player(p) - p.ability["Heading"] / 10)

    def move_offence_player(self, player, offside_line):
        if player.position == "GK":
            self.move_player_towards_home(player, max_drift=4, defending=False)
            return
        advance = self.offensive_shape_advance(player)
        support_y = self.clamp(
            self.shape_y(player, defending=False) - advance,
            self.attack_min_y(player, offside_line),
            self.attack_max_y(player),
        )
        support_x = self.clamp(
            self.shape_x(player, defending=False) + (self.ball_holder.x - Const.WIDTH / 2) * 0.25,
            self.lane_min_x(player, defending=False),
            self.lane_max_x(player, defending=False),
        )
        if player.get_distance(self.ball_holder.x, self.ball_holder.y) < 8:
            support_x = self.clamp(player.x + (player.x - self.ball_holder.x), self.lane_min_x(player, defending=False), self.lane_max_x(player, defending=False))
        support_x, support_y = self.apply_positioning_noise(player, support_x, support_y, defending=False)
        support_y = self.onside_target_y(player, support_y, offside_line)
        player.approaching(support_x, support_y)

    def move_defence_player(self, player, presser=None, cover=None):
        if player.position == "GK":
            self.move_player_towards_home(player, max_drift=3, defending=True)
            return
        if player is presser:
            self.move_defensive_presser(player)
            return
        if player is cover:
            self.move_defensive_cover(player, presser)
            return
        target_y = self.clamp(
            self.ball_holder.y - self.defensive_depth_offset(player),
            self.defence_min_y(player),
            self.defence_max_y(player),
        )
        target_x = self.clamp(
            self.defensive_target_x(player),
            self.lane_min_x(player, defending=True, emergency=self.is_defensive_danger()),
            self.lane_max_x(player, defending=True, emergency=self.is_defensive_danger()),
        )
        target_x, target_y = self.apply_positioning_noise(player, target_x, target_y, defending=True)
        player.approaching(target_x, target_y)

    def offensive_shape_advance(self, player):
        progress = Const.LENGTH - self.ball_holder.y
        if player.position in ("LB", "LCB", "CB", "RCB", "RB"):
            factor, cap = 0.42, 42
        elif "DM" in player.position or player.position == "CDM":
            factor, cap = 0.38, 34
        elif player.position in ("LCM", "CM", "RCM", "LM", "RM"):
            factor, cap = 0.48, 42
        elif player.position == "CAM":
            factor, cap = 0.58, 50
        else:
            factor, cap = 0.68, 58
        return self.clamp(progress * factor, 0, cap)

    def choose_defensive_presser(self):
        candidates = [p for p in self.defence.players if p.position != "GK"]
        if not candidates:
            return None
        urgency = 0
        if self.ball_holder.y <= 18:
            urgency = 1.0
        elif self.ball_holder.y <= 32:
            urgency = 0.58
        elif self.ball_holder.y <= 48:
            urgency = 0.30
        else:
            urgency = 0.12
        if urgency < 0.5 and self.rng.random() > urgency:
            return None
        return min(candidates, key=lambda p: p.get_distance_player(self.ball_holder) - p.ability["IQ"] / 18)

    def choose_defensive_cover(self, presser):
        if presser is None:
            return None
        candidates = [p for p in self.defence.players if p is not presser and p.position != "GK"]
        if not candidates:
            return None
        return min(candidates, key=lambda p: p.get_distance_player(presser) - p.ability["Defence"] / 20)

    def move_defensive_presser(self, player):
        pressure_gap = 4.5 if self.ball_holder.y <= 24 else 6.5
        dx = player.x - self.ball_holder.x
        dy = player.y - self.ball_holder.y
        distance = math.hypot(dx, dy) or 1
        target_x = self.ball_holder.x + dx / distance * pressure_gap
        target_y = self.ball_holder.y + dy / distance * pressure_gap
        player.approaching(
            self.clamp(target_x, self.lane_min_x(player, defending=True, emergency=True), self.lane_max_x(player, defending=True, emergency=True)),
            self.clamp(target_y, self.defence_min_y(player), self.defence_max_y(player)),
        )

    def move_defensive_cover(self, player, presser):
        target_x = (self.ball_holder.x + presser.x) / 2
        target_y = self.ball_holder.y - 10
        player.approaching(
            self.clamp(target_x, self.lane_min_x(player, defending=True, emergency=True), self.lane_max_x(player, defending=True, emergency=True)),
            self.clamp(target_y, self.defence_min_y(player), self.defence_max_y(player)),
        )

    def apply_positioning_noise(self, player, target_x, target_y, defending=False):
        iq = player.ability.get("IQ", 80)
        jitter = self.clamp((105 - iq) / 18, 0.4, 3.2)
        phase = (self._movement_tick + self.player_index(player) * 3) * 0.7
        target_x += math.sin(phase) * jitter
        target_y += math.cos(phase * 0.7) * jitter
        return (
            self.clamp(target_x, self.lane_min_x(player, defending), self.lane_max_x(player, defending)),
            target_y,
        )

    def player_index(self, player):
        for team in (self.home, self.away):
            for index, item in enumerate(team.players):
                if item is player:
                    return index
        return 0

    def move_player_towards_home(self, player, max_drift, defending=False):
        home_x = self.shape_x(player, defending)
        home_y = self.shape_y(player, defending)
        if player.get_distance(home_x, home_y) > max_drift:
            player.approaching(home_x, home_y)

    def keep_shape_bounds(self):
        offside_line = self.get_offside_line_y()
        for player in self.offence.players:
            if player.position == "GK":
                continue
            player.x = self.clamp(player.x, self.lane_min_x(player, defending=False), self.lane_max_x(player, defending=False))
            player.y = self.clamp(player.y, self.attack_min_y(player, offside_line), self.attack_max_y(player))
        emergency = self.is_defensive_danger()
        for player in self.defence.players:
            if player.position == "GK":
                continue
            player.x = self.clamp(player.x, self.lane_min_x(player, defending=True, emergency=emergency), self.lane_max_x(player, defending=True, emergency=emergency))
            player.y = self.clamp(player.y, self.defence_min_y(player), self.defence_max_y(player))

    def shape_x(self, player, defending=False):
        return Const.WIDTH - player.default_x if defending else player.default_x

    def shape_y(self, player, defending=False):
        y = Const.LENGTH - (Const.LENGTH - player.default_y) / 2
        return Const.LENGTH - y if defending else y

    def onside_target_y(self, player, y, offside_line):
        y = self.clamp(y, self.attack_min_y(player, offside_line), self.attack_max_y(player))
        if player is self.ball_holder or player.position == "GK":
            return y
        if offside_line is None or offside_line >= Const.LENGTH / 2:
            return y
        if player.position in ("ST", "CF", "LW", "RW", "CAM", "LM", "RM"):
            return max(y, min(self.ball_holder.y, offside_line) + 1.2)
        return y

    def move_onside_if_needed(self, player, offside_line):
        target_y = self.onside_target_y(player, player.y, offside_line)
        if target_y != player.y:
            player.approaching(player.x, target_y)

    def attack_min_y(self, player, offside_line=None):
        if player.position in ("ST", "CF", "LW", "RW"):
            return 8
        if player.position in ("CAM", "LM", "RM"):
            return 18
        if "M" in player.position or "DM" in player.position:
            return 30
        return 48

    def attack_max_y(self, player):
        if player.position in ("ST", "CF", "LW", "RW"):
            return 70
        if player.position in ("CAM", "LM", "RM"):
            return 78
        if "M" in player.position or "DM" in player.position:
            return 88
        return 92

    def defence_min_y(self, player):
        if player.position in ("LB", "LCB", "CB", "RCB", "RB"):
            return 12
        if "DM" in player.position or player.position == "CDM":
            return 24
        if "M" in player.position:
            return 34
        return 44

    def defence_max_y(self, player):
        if player.position in ("LB", "LCB", "CB", "RCB", "RB"):
            return 78
        if "DM" in player.position or player.position == "CDM":
            return 82
        if "M" in player.position:
            return 90
        return 96

    def defensive_depth_offset(self, player):
        if player.position in ("LB", "LCB", "CB", "RCB", "RB"):
            return 18
        if "DM" in player.position or player.position == "CDM":
            return 8
        if "M" in player.position:
            return -4
        return -18

    def defensive_shift_factor(self, player):
        if player.position in ("LB", "LCB", "CB", "RCB", "RB"):
            return 0.35
        if "M" in player.position:
            return 0.45
        return 0.55

    def defensive_target_x(self, player):
        base = self.shape_x(player, defending=True)
        ball_shift = (self.ball_holder.x - Const.WIDTH / 2) * self.defensive_shift_factor(player)
        if not self.is_defensive_danger():
            return base + ball_shift
        if player.position in ("LB", "RB"):
            is_ball_side = (self.ball_holder.x < Const.WIDTH / 2 and base < Const.WIDTH / 2) or \
                           (self.ball_holder.x >= Const.WIDTH / 2 and base >= Const.WIDTH / 2)
            if is_ball_side:
                return base + (self.ball_holder.x - base) * 0.55
            return Const.WIDTH / 2 + (base - Const.WIDTH / 2) * 0.35
        if player.position in ("LCB", "CB", "RCB"):
            return Const.WIDTH / 2 + (base - Const.WIDTH / 2) * 0.45
        return base + ball_shift * 0.7

    def is_defensive_danger(self):
        return self.ball_holder.y <= 34

    def lane_min_x(self, player, defending=False, emergency=False):
        center = self.shape_x(player, defending)
        if defending and emergency and player.position in ("LB", "RB"):
            center = Const.WIDTH / 2 + (center - Const.WIDTH / 2) * 0.28
        width = 10 if player.position in ("GK", "CB", "CDM", "CM", "CAM", "ST", "CF") else 12
        if defending and emergency:
            width += 8
        return self.clamp(center - width, 0, Const.WIDTH)

    def lane_max_x(self, player, defending=False, emergency=False):
        center = self.shape_x(player, defending)
        if defending and emergency and player.position in ("LB", "RB"):
            center = Const.WIDTH / 2 + (center - Const.WIDTH / 2) * 0.28
        width = 10 if player.position in ("GK", "CB", "CDM", "CM", "CAM", "ST", "CF") else 12
        if defending and emergency:
            width += 8
        return self.clamp(center + width, 0, Const.WIDTH)

    def clamp(self, value, minimum, maximum):
        return max(minimum, min(maximum, value))

    def get_action_duration(self):
        y = self.ball_holder.y
        if self.possession_action_count <= 1 and y > Const.LENGTH * 0.62:
            return self.rng.randint(3, 8)
        if y > Const.LENGTH * 0.62:
            return self.rng.randint(5, 12)
        if y > Const.LENGTH * 0.32:
            return self.rng.randint(4, 10)
        return self.rng.randint(3, 8)

    def get_shot_angle(self, x, y):
        left = math.atan2(Const.LEFT_GOALPOST - x, max(y, 1))
        right = math.atan2(Const.RIGHT_GOALPOST - x, max(y, 1))
        return abs(right - left) * 180 / math.pi

    def create_shot(self, shooter, pressure, is_header=False):
        distance = shooter.get_distance(Const.WIDTH / 2, 0)
        angle = self.get_shot_angle(shooter.x, shooter.y)
        shoot_ability = shooter.get_shooting_ability(Const.WIDTH / 2) if not is_header else shooter.ability["Heading"]
        assist_quality = 0 if self.assister is None else self.assister.get_passing_ability(shooter) / 100
        return build_shot_context(distance, angle, shoot_ability, pressure, assist_quality, is_header)

    def record_shot_quality(self, shot, shooter):
        self.offence.xg += shot.raw_xg
        self.offence.adjusted_xg += shot.goal_probability
        if shot.raw_xg >= 0.15 or shot.goal_probability >= 0.18:
            self.offence.big_chances += 1
        self.record_box_touch(shooter)
        return shot.raw_xg

    def adjust_shot_for_keeper(self, shot, keeper):
        keeper_ability = keeper.ability["GK_Saving"] * 0.45 + keeper.ability["GK_Reaction"] * 0.35 + keeper.ability["GK_Positioning"] * 0.20
        return shot_on_target_goal_probability(shot.shoot_ability, keeper_ability, shot.raw_xg)

    def record_expected_threat(self, player, action_quality=1.0):
        self.offence.xt += expected_threat(player.y, action_quality)

    def record_box_touch(self, player):
        if player.y <= 16.5 and self.possession_box_touches < 1:
            self.offence.box_touches += 1
            self.possession_box_touches += 1

    def get_offside_line_y(self):
        return min(self.getLastSecondDefencePlayer().y, self.ball_holder.y)

    def is_offside(self, passer, receiver):
        if receiver.position == "GK":
            return False
        if receiver.y >= 48:
            return False
        if receiver.y >= passer.y:
            return False
        if receiver.y >= self.ball_holder.y:
            return False
        return receiver.y < self.getLastSecondDefencePlayer().y - 0.2

    def choose_pass_interceptor(self, start_x, start_y, end_x, end_y, max_distance):
        candidates = self.getWayDefencePlayers(start_x, start_y, end_x, end_y)
        if not candidates:
            return None
        nearest = min(candidates, key=lambda p: p.get_distance_line(start_x, start_y, end_x, end_y))
        if nearest.get_distance_line(start_x, start_y, end_x, end_y) <= max_distance:
            return nearest
        return None

    def make_broken_pass_flight(self, action_frame, passer, target, interceptor=None):
        if action_frame is None or not hasattr(self, 'recorder'):
            return None
        first = self.recorder.make_ball_flight(self, passer, [target.x, target.y], "pass")
        if interceptor is not None:
            first["to"] = self.recorder._player_to_absolute(self, interceptor)
            first["path"] = [first["from"], first["to"]]
            return first
        first["path"] = [first["from"], first["to"]]
        return first

    # 攻守坐标转换
    def swapPosition(self, team):
        for player in team.players:
            player.x = Const.WIDTH - player.x
            player.y = Const.LENGTH - player.y

    # 重置球员位置
    def resetPosition(self):
        for player in self.defence.players + self.offence.players:
            player.reset_position()
        self.swapPosition(self.defence)

    # 重置行动标记
    def reset_action_flag(self):
        for player in self.defence.players + self.offence.players:
            player.action_flag = False

    # 转换持球人
    def changeBallHolder(self, player):
        if self.ball_holder is player:
            return
        self.ball_holder = player
        if player in self.offence.players:
            self.keep_offence_players_onside()
        # self.printCaseWithPlayer(player, "接到了球")

    def keep_offence_players_onside(self):
        offside_line = self.get_offside_line_y()
        for player in self.offence.players:
            if player.position == "GK":
                continue
            self.move_onside_if_needed(player, offside_line)

    # 随机转换持球人
    def changeRandomBallHolder(self, target=None, target_abs=None):
        if target_abs is not None and hasattr(self, 'recorder'):
            player = min(self.offence.players, key=lambda p: math.hypot(
                self.recorder._player_to_absolute(self, p)[0] - target_abs[0],
                self.recorder._player_to_absolute(self, p)[1] - target_abs[1]
            ))
        elif target is not None:
            player = min(self.offence.players, key=lambda p: p.get_distance(target.x, target.y))
        else:
            player = self.offence.players[self.rng.randint(0, 10)]
        self.changeBallHolder(player)

    # 转换持球人为门将
    def changeBallHolderToGK(self):
        player = self.offence.players[0]
        self.changeBallHolder(player)
        self.goal_kick_pending = True

    # 转换持球人为开球人
    def changeBallHolderToOpen(self):
        player = self.offence.players[10]
        self.changeBallHolder(player)

    # 获得攻方队友
    def getOffenceTeamMates(self):
        offence_team_mates = []
        for offence_player in self.offence.players:
            if offence_player != self.ball_holder:
                offence_team_mates.append(offence_player)
        return offence_team_mates

    def get_available_pass_targets(self):
        team_mates = self.getOffenceTeamMates()
        onside = [player for player in team_mates if not self.is_offside(self.ball_holder, player)]
        if onside:
            safe = [player for player in onside if player.y >= 48 or player.y >= self.getLastSecondDefencePlayer().y + 0.8]
            if safe:
                return safe
        if onside:
            return onside
        return team_mates

    def build_pass_lane_bias(self, targets):
        bias = {}
        holder_lane = self.pitch_lane(self.ball_holder.x)
        central_crowd = len(self.getPlayersInArea(self.ball_holder.x, self.ball_holder.y, 14))
        for player in targets:
            factor = 1.0
            lane = self.pitch_lane(player.x)
            if central_crowd >= 5 and lane != "center":
                factor *= 0.62
            if holder_lane == "center" and lane != "center" and self.ball_holder.y <= 62:
                factor *= 0.72
            if holder_lane != "center":
                if lane == holder_lane:
                    factor *= 0.78
                elif lane != "center":
                    factor *= 0.70
            if player.position in ("LB", "RB", "LM", "RM", "LW", "RW") and self.ball_holder.y <= 58:
                factor *= 0.72
            if lane == "center" and self.ball_holder.y <= 34 and player.y <= 24:
                factor *= 0.82
            bias[player] = factor
        return bias

    def pitch_lane(self, x):
        if x < Const.WIDTH / 3:
            return "left"
        if x > Const.WIDTH * 2 / 3:
            return "right"
        return "center"

    def should_attempt_risky_line_pass(self):
        if self.ball_holder.y >= 55:
            return False
        if not any(player.position in ("ST", "CF", "LW", "RW", "CAM") for player in self.getOffenceTeamMates()):
            return False
        return self.rng.random() < 0.12

    def trigger_early_run(self):
        runners = [
            player for player in self.getOffenceTeamMates()
            if player.position in ("ST", "CF", "LW", "RW", "CAM") and player.y < 48
        ]
        if not runners:
            return
        runner = min(runners, key=lambda p: p.get_distance(Const.WIDTH / 2, 0) - p.ability.get("Speed", 80) / 20)
        line = min(self.ball_holder.y, self.getLastSecondDefencePlayer().y)
        target_y = max(5, line - (2.0 + (100 - runner.ability.get("IQ", 80)) / 35))
        runner.approaching(runner.x, target_y)

    # 判断是否为守方球员
    def isDefencePlayer(self, player):
        return player in self.defence.players

    # 获得守方门将
    def getDefenceGK(self):
        return self.defence.players[0]

    # 确定区域内防守球员列表
    def getDefencePlayersInArea(self, x, y, radius):
        """
        :param defence_players: 防守球员列表
        :param x: 进攻方坐标系的横坐标
        :param y: 进攻方坐标系的纵坐标
        :param radius: 区域半径
        :return: 在此范围内的防守球员列表
        """
        defence_players_in_area = []
        for defence_player in self.defence.players:
            distance = math.sqrt(
                math.pow(defence_player.x - x, 2) +
                math.pow(defence_player.y - y, 2)
            )
            if distance < radius:
                defence_players_in_area.append(defence_player)
        return defence_players_in_area

    # 确定区域内进攻球员列表
    def getOffencePlayersInArea(self, x, y, radius):
        """
        :param offence_players: 进攻球员列表
        :param x: 进攻方坐标系的横坐标
        :param y: 进攻方坐标系的纵坐标
        :param radius: 区域半径
        :return: 在此范围内的进攻球员列表
        """
        offence_players_in_area = []
        for offence_player in self.offence.players:
            distance = math.sqrt(
                math.pow(offence_player.x - x, 2) +
                math.pow(offence_player.y - y, 2)
            )
            if distance < radius:
                offence_players_in_area.append(offence_player)
        return offence_players_in_area

    # 确定区域内球员列表
    def getPlayersInArea(self, x, y, radius):
        """
        :param defence_players: 防守球员列表
        :param offence_players: 进攻球员列表
        :param x: 进攻方坐标系的横坐标
        :param y: 进攻方坐标系的纵坐标
        :param radius: 半径区域
        :return: 在此范围内的球员
        """
        return self.getDefencePlayersInArea(x, y, radius) + self.getOffencePlayersInArea(x, y, radius)

    # 确定射门区域防守球员列表
    def getShootDefencePlayers(self, x, y):
        shoot_defence_players = []
        for defence_player in self.defence.players:
            def_x = defence_player.x
            def_y = defence_player.y
            def_v = defence_player.ability["Defence"] / 15
            if def_y > y:
                continue
            line_value = y * (def_x - x + def_v) - (def_y - y) * \
                (x - def_v - Const.LEFT_GOALPOST)
            if line_value < 0:
                continue
            line_value = y * (def_x - x - def_v) - (def_y - y) * \
                (x + def_v - Const.RIGHT_GOALPOST)
            if line_value > 0:
                continue
            shoot_defence_players.append(defence_player)
        return shoot_defence_players

    # 确定路线防守球员列表
    def getWayDefencePlayers(self, x, y, fin_x, fin_y):
        shoot_defence_players = []
        for defence_player in self.defence.players:
            def_x = defence_player.x
            def_y = defence_player.y
            def_v = defence_player.ability["Defence"] / 15
            if def_y > max(y, fin_y) or def_y < min(y, fin_y):
                continue
            line_value = (y - fin_y) * (def_x - x + def_v) - \
                (def_y - y) * (x - def_v - fin_x)
            if line_value < 0:
                continue
            line_value = (y - fin_y) * (def_x - x - def_v) - \
                (def_y - y) * (x + def_v - fin_x)
            if line_value > 0:
                continue
            shoot_defence_players.append(defence_player)
        return shoot_defence_players

    # 获取倒数第二位防守球员
    def getLastSecondDefencePlayer(self):
        min_y = 100
        min2_y = 101
        min_player = self.defence.players[0]
        for player in self.defence.players:
            if player.y < min_y:
                min2_y = min_y
                min_y = player.y
                min2_player = min_player
                min_player = player
            elif player.y < min2_y:
                min2_y = player.y
                min2_player = player
        return min2_player

    def printCase(self, case, event_type=None, importance=None, player=None, target=None, xg=0, result=""):
        minute = self.getTime()
        lines = case.split("\n")
        for line in lines:
            self.record_event(line, minute, importance, event_type, player, target, xg, result)

    # 打印球员事件
    def printCaseWithPlayer(self, player, case, event_type=None, importance=None):
        self.printCase(player.coach + " " + player.getName() + " " + case, event_type, importance, player)

    def record_event(self, text, minute=None, importance=None, event_type=None, player=None, target=None, xg=0, result=""):
        if minute is None:
            minute = self.getTime()
        second = self.time % 60
        self.event_seq += 1
        if event_type is None or importance is None:
            event_type, importance = self.classify_event(text)
        event = MatchEvent(minute, second, self.event_seq, event_type, text, self.home.point, self.away.point, importance, self.offence, player, xg, target, result)
        self.current_events.append(event)
        self.match_events.append(event)

    def classify_event(self, text):
        if "破门" in text or "入网" in text or "进了" in text:
            return "goal", 5
        if "扑救" in text or "扑出" in text or "抱住" in text or "挡了出去" in text:
            return "save", 4
        if "射门" in text or "打门" in text or "攻门" in text or "怒射" in text:
            return "shot", 3
        if "偏" in text or "横梁" in text or "立柱" in text or "打歪" in text:
            return "miss", 3
        if "拦" in text or "断" in text or "铲" in text or "顶到了球" in text:
            return "turnover", 3
        if "失误" in text or "出界" in text or "越位" in text:
            return "turnover", 3
        if "长传" in text or "传中" in text:
            return "long_pass", 2
        if "传" in text:
            return "pass", 1
        if "带球" in text or "过掉" in text or "推进" in text or "切入" in text:
            return "carry", 1
        return "other", 1

    def flush_possession_summary(self):
        if not self.current_events:
            return
        if any(ev.event_type == "goal" for ev in self.current_events):
            self.broadcast_has_goal = True
        if self.mode != Const.MODE_NORMAL:
            self.current_events = []
            return
        minute = self.getTime()
        key_events = [ev for ev in self.current_events if ev.importance >= 4]
        minor_events = [ev for ev in self.current_events if ev.importance == 3]
        sampled_minor = []
        for ev in minor_events:
            if ev.event_type in ("shot", "miss"):
                sampled_minor.append(ev)
            elif self.rng.random() < 0.4:
                sampled_minor.append(ev)
        # 抽样一些普通动作（传球/带球/过人）让播报更生动
        flavor_events = [ev for ev in self.current_events if ev.importance <= 2 and ev.event_type in ("pass", "long_pass", "key_pass", "carry")]
        sampled_flavor = []
        if flavor_events:
            count = min(2, len(flavor_events))
            sampled_flavor = self.rng.sample(flavor_events, count)
        highlight_events = key_events + sampled_minor
        summary = self.summarize_possession(self.current_events)
        self.current_events = []
        # 合并所有要输出的事件并按原始顺序排序
        all_events = sorted(sampled_flavor + highlight_events, key=lambda ev: ev.seq)
        lines = []
        if all_events:
            for ev in all_events:
                lines.append(self.event_prefix(ev) + " " + ev.text)
            # 有重要事件时不再重复输出possession总结，避免和事件detail重复
            if not highlight_events and summary:
                prefix = "主" + str(self.home.point) + ":" + str(self.away.point) + "客 " + self.half + str(minute) + ":" + str(self.time % 60)
                lines.append(prefix + " " + summary)
        elif summary:
            prefix = "主" + str(self.home.point) + ":" + str(self.away.point) + "客 " + self.half + str(minute) + ":" + str(self.time % 60)
            lines.append(prefix + " " + summary)
        else:
            return
        for line in lines:
            self.broadcast_buffer.append(line)

    def summarize_possession(self, events):
        team_name = self.offence.coach.name
        result = self.find_result_event(events)
        route = self.describe_route(events)
        if result:
            key = result.event_type if result.event_type in ("goal", "save", "miss", "turnover") else "quiet"
            return self.commentary.possession(
                key,
                team=team_name,
                route=route,
                player=event_player_name(result),
                target=event_target_name(result),
                xg_text=self.commentary.xg_text(result.xg),
            )
        passes = len([event for event in events if event.event_type in ("pass", "long_pass")])
        carries = len([event for event in events if event.event_type == "carry"])
        if passes + carries < 4:
            return ""
        if any(event.event_type == "long_pass" for event in events):
            return self.commentary.possession("quiet", route=self.commentary.route("long_pass", team=team_name))
        if carries >= 2:
            return self.commentary.possession("quiet", route=self.commentary.route("carry", team=team_name))
        return self.commentary.possession("quiet", route=self.commentary.route("pass", team=team_name))

    def find_result_event(self, events):
        for event in reversed(events):
            if event.event_type in ("goal", "save", "miss", "turnover"):
                return event
        for event in reversed(events):
            if event.event_type == "shot":
                return event
        return None

    def describe_route(self, events):
        long_passes = len([event for event in events if event.event_type == "long_pass"])
        key_passes = len([event for event in events if event.event_type == "key_pass"])
        carries = len([event for event in events if event.event_type == "carry"])
        passes = len([event for event in events if event.event_type == "pass"])
        if key_passes:
            return self.commentary.route("key_pass", team=self.offence.coach.name)
        if long_passes:
            return self.commentary.route("long_pass", team=self.offence.coach.name)
        if carries >= 2:
            return self.commentary.route("carry", team=self.offence.coach.name)
        if passes >= 5:
            return self.commentary.route("pass", team=self.offence.coach.name)
        if passes:
            return self.commentary.route("pass", team=self.offence.coach.name)
        return self.commentary.route("default", team=self.offence.coach.name)

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

    def getTime(self):
        if self.half == "上半时":
            return self.time // 60
        else:
            return self.time // 60 + 45

    def init_replay_recorder(self):
        from engine.replay import ReplayRecorder

        self.recorder = ReplayRecorder()
        self.recorder.record_header(
            self.home,
            self.away,
            self.home.coach.formation if hasattr(self.home.coach, 'formation') else "442",
            self.away.coach.formation if hasattr(self.away.coach, 'formation') else "442",
        )

    def save_replay(self):
        from engine.replay import ReplayRecorder
        import os
        import time as time_mod

        if not hasattr(self, 'recorder') or self.recorder is None:
            return ""
        replay_dir = os.path.join(os.environ.get("PSL_PROJECT_DIR", PROJECT_DIR), "data", "replays")
        ts = time_mod.strftime("%Y%m%d_%H%M%S")
        score = f"{self.home.point}-{self.away.point}"
        home_name = self.home.coach.name.replace(" ", "_")
        away_name = self.away.coach.name.replace(" ", "_")
        filename = f"{ts}_{home_name}_{away_name}_{score}.jsonl"
        filepath = os.path.join(replay_dir, filename)
        self.recorder.save(filepath)
        ReplayRecorder.cleanup(replay_dir, max_files=100)
        return filepath

    def run_simulation(self):
        """Run the full match simulation without any IO. Returns MatchResult."""
        self.mode = Const.MODE_SILENCE
        self.init_replay_recorder()

        self.resetPosition()
        self.recorder.record_frame(self)
        self.last_broadcast_time = 0
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()

        self.half = "下半时"
        self.time = 0
        self.last_broadcast_time = 0
        if self.offence is self.home:
            self.swap()
        self.resetPosition()
        self.changeBallHolderToOpen()
        self.recorder.record_frame(self)
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()

        result = self.to_result()

        filepath = self.save_replay()
        result.replay_path = filepath

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
                passes=team.passes,
                successful_passes=team.successful_passes,
                dribbles=team.dribbles,
                carries=team.carries,
                progressive_carries=team.progressive_carries,
                assists=team.assists,
                tackles=team.tackles,
                tackle_attempts=team.tackle_attempts,
                interceptions=team.interceptions,
                blocks=team.blocks,
                saves=team.saves,
                xg=team.xg,
                adjusted_xg=team.adjusted_xg,
                xt=team.xt,
                key_passes=team.key_passes,
                box_touches=team.box_touches,
                big_chances=team.big_chances,
                possessions=team.possessions,
                goals_detailed=team.goals_detailed,
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
