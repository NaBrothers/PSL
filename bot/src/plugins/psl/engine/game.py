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

    async def start(self, mode):
        self.mode = mode
        self.resetPosition()
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
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()
            await self.maybe_broadcast()
        await self.flush_broadcast("下半场结束")

        stats = await self.printStats()
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
            # 持球人行为选择
            holder_action = self.ball_holder.choose_holding_action_type(
                defence_players_number,
                shoot_defence_players_number,
                self.rng
            )
            if holder_action == "SHOOT":
                shot = self.create_shot(self.ball_holder, shoot_defence_players_number)
                shoot_x = self.ball_holder.shooting(shot.on_target_probability, self.rng)
                self.record_shot_quality(shot, self.ball_holder)
                if shot.distance >= 20:
                    case = Display.print_long_shot(self.ball_holder, int(shot.distance))
                else:
                    case = Display.print_short_shot(self.ball_holder, int(shot.distance))
                self.printCase(case, "shot", 3, self.ball_holder, xg=shot.raw_xg)
                self.ball_holder.shoots += 1
                if shoot_x < Const.LEFT_GOALPOST or shoot_x > Const.RIGHT_GOALPOST:
                    case = Display.print_miss_shot()
                    self.printCase(case, "miss", 3, self.ball_holder, xg=shot.raw_xg)
                    self.swap()
                    self.changeBallHolderToGK()
                    return
                def_players = self.getWayDefencePlayers(
                    self.ball_holder.x, self.ball_holder.y, shoot_x, 0)
                shoot = self.ball_holder.get_shooting_ability(shoot_x)
                for def_player in def_players:
                    if def_player.position == "GK":
                        continue
                    def_player.blocks += 1
                    def_player.interceptions += 1
                    # 计算防守球员到球路的距离
                    distance = def_player.get_distance_line(
                        self.ball_holder.x, self.ball_holder.y, Const.WIDTH / 2, 0)

                    if def_player.intercepting(shoot, distance, self.rng):
                        case = Display.print_interception(def_player)
                        self.printCase(case, "turnover", 3, def_player)
                        self.swap()
                        self.changeBallHolder(def_player)
                        return
                gk = self.getDefenceGK()
                self.ball_holder.shoots_in_target += 1
                goal_probability = self.adjust_shot_for_keeper(shot, gk)
                self.offence.adjusted_xg += shot.on_target_probability * goal_probability - shot.goal_probability
                if self.rng.random() >= goal_probability:
                    case = Display.print_saving(gk)
                    self.printCase(case, "save", 4, self.ball_holder, gk, shot.raw_xg)
                    gk.saves += 1
                    self.swap()
                    self.changeBallHolderToGK()
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
                self.swap()
                self.broadcast_goal(scorer)
                self.resetPosition()
                self.changeBallHolderToOpen()
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
                passing = self.ball_holder.passing(self.getOffenceTeamMates(), self.rng)
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
                    pressure = len(self.getDefencePlayersInArea(self.ball_holder.x, self.ball_holder.y, 10))
                    pass_probability = pass_success_probability(self.ball_holder.ability["Short_Passing"], distance, pressure, False)
                    if self.rng.random() > pass_probability:
                        self.printCaseWithPlayer(self.ball_holder, "传球失误", "turnover", 3)
                        self.swap()
                        self.changeRandomBallHolder()
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
                            self.swap()
                            self.changeBallHolder(def_player)
                            return
                        else:
                            def_player.action_flag = True
                    self.ball_holder.successful_passes += 1
                    self.ball_holder.action_flag = False
                    self.assister = self.ball_holder
                    if passing_aim.y <= 25:
                        self.offence.key_passes += 1
                    self.record_expected_threat(passing_aim, self.ball_holder.ability["Short_Passing"] / 100)
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
                    pressure = len(self.getDefencePlayersInArea(self.ball_holder.x, self.ball_holder.y, 12))
                    pass_probability = pass_success_probability(passing_ability, distance, pressure, True)
                    if self.rng.random() > pass_probability:
                        self.printCaseWithPlayer(self.ball_holder, "长传失误", "turnover", 3)
                        self.swap()
                        self.changeRandomBallHolder()
                        return
                    if self.getLastSecondDefencePlayer().y > passing_aim.y and passing_aim.y < Const.LENGTH / 2:
                        self.printCaseWithPlayer(passing_aim, "处在越位位置", "turnover", 3)
                        self.swap()
                        self.changeBallHolderToGK()
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
                        self.swap()
                        self.changeBallHolderToGK()
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
                        self.swap()
                        self.changeRandomBallHolder()
                        return
                    else:
                        self.ball_holder.successful_passes += 1
                        self.assister = self.ball_holder
                        if passing_aim.y <= 25:
                            self.offence.key_passes += 1
                        self.record_expected_threat(passing_aim, passing_ability / 100)
                        self.record_box_touch(roll_winner)
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
                                self.swap()
                                self.changeBallHolderToGK()
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
                                self.swap()
                                self.broadcast_goal(scorer)
                                self.resetPosition()
                                self.changeBallHolderToOpen()
                            return
                        else:
                            self.changeBallHolder(roll_winner)
                            if self.isDefencePlayer(roll_winner):
                                return

            self.swapPosition(self.defence)
            # 无球人进行无球跑动
            for player in self.defence.players + self.offence.players:
                if player.action_flag or player == self.ball_holder:
                    continue
                player.off_ball_moving(
                    self.ball_holder, self.getOffencePlayersInArea(player.x, player.y, 10), self.rng)
            self.swapPosition(self.defence)
            # for player in self.defence.players:
            #   print(player.name + " " + str(int(player.x)) + " " + str(int(player.y)))
            # print("足球坐标：" + str(int(self.ball_holder.x)) + " " + str(int(self.ball_holder.y)))

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
        # self.printCaseWithPlayer(player, "接到了球")

    # 随机转换持球人
    def changeRandomBallHolder(self):
        player = self.offence.players[self.rng.randint(0, 10)]
        self.changeBallHolder(player)

    # 转换持球人为门将
    def changeBallHolderToGK(self):
        player = self.offence.players[0]
        self.changeBallHolder(player)

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

    def run_simulation(self):
        """Run the full match simulation without any IO. Returns MatchResult."""
        self.mode = Const.MODE_SILENCE
        self.resetPosition()
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
        while self.time < 45 * 60:
            self.play_possession()
            if self.time > 45 * 60:
                self.flush_possession_summary()

        return self.to_result()

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
