from game.model.user import User
from game.engine.player import Player
from game.engine.team import Team
from game.engine.const import Const
from game.utils.image import toImage
from game.engine.display import Display
# from display import Display
import random
import math
import time


class Game:

    def __init__(self, matcher, user1, user2, npc=-1, difficulty=0):
        # bot回调函数
        self.matcher = matcher
        # 当前回合
        self.step = 0
        # 当前时间
        self.time = 0
        # 进攻方
        self.offence = Team(user1)
        # 防守方
        self.defence = Team(user2, npc, difficulty)
        # 主队
        self.home = self.offence
        # 客队
        self.away = self.defence
        # 上下半场
        self.half = "上半时"
        # 持球人
        self.ball_holder = self.offence.players[10]
        # 助攻人
        self.assister = None
        # gui
        # self.display = Display()
        # 打印过程
        self.print_str = ""
        # 四元组(时间，队伍，进球者，助攻者)
        self.timeline = []
        self.mode = Const.MODE_NORMAL

    # 比赛主逻辑
    async def start(self, mode):
        self.mode = mode
        self.resetPosition()
        if self.mode != Const.MODE_QUICK:
            await self.send("主 " + self.home.coach.name + " : " + self.away.coach.name + " 客\n比赛开始")
        while self.time < 45 * 60:
            self.oneStep()
            if self.time > 45 * 60:
                self.printCase("上半场结束")
            await self.send(self.print_str)
            self.print_str = ""
            if self.mode != Const.MODE_QUICK:
                time.sleep(Const.PRINT_DELAY)
        self.half = "下半时"
        self.time = 0
        if self.offence is self.home:
            self.swap()
        self.resetPosition()
        self.changeBallHolderToOpen()
        while self.time < 45 * 60:
            self.oneStep()
            if self.time > 45 * 60:
                self.printCase("下半场结束")
            await self.send(self.print_str)
            self.print_str = ""
            if self.mode != Const.MODE_QUICK:
                time.sleep(Const.PRINT_DELAY)

        stats = await self.printStats()
        return stats

    async def send(self, str):
        if self.mode == Const.MODE_QUICK:
            return
        await self.matcher.send(toImage(str))

    async def printStats(self):
        self.mode = Const.MODE_NORMAL
        self.home.getStats()
        self.away.getStats()

        self.print_str += "[终场比分]\n" 
        self.print_str += "主 " + self.home.coach.name + " " + \
            str(self.home.point) + ":" + str(self.away.point) + \
            " " + self.away.coach.name + " 客\n\n"

        if self.timeline:
            self.print_str += "[比赛事件]\n"
            maxLen = -1
            for case in self.timeline:
              if case[1] == self.home:
                maxLen = max(maxLen,len(case[2].getName()))
                if case[3] != None:
                  maxLen = max(maxLen,len(case[3].getName()))
            maxLen = max(maxLen, 8)
            print(maxLen)
            for case in self.timeline:
                if case[1] == self.home:
                    self.print_str += case[2].getName().rjust(maxLen) + "  进球"
                    self.print_str += "  " + str(str(case[0]) + "'").ljust(3)
                    if case[3] != None:
                        self.print_str += "\n"
                        self.print_str += case[3].getName().rjust(maxLen) + "  助攻"
                else:
                    self.print_str += "".ljust(maxLen+4) + str(case[0]) + "'  "
                    self.print_str += "进球  " + case[2].getName()
                    if case[3] != None:
                        self.print_str += "\n"
                        self.print_str += "".ljust(maxLen+9) + "助攻  " + case[3].getName()
                
                self.print_str += "\n\n"
      
        if self.home.goals_detailed or self.away.goals_detailed:
            self.print_str += "[进球统计]\n"

        if self.home.goals_detailed:
            self.print_str += "主队：\n"
            for item in self.home.goals_detailed:
                self.print_str += item[0] + " ("
                for i in item[1]:
                    self.print_str += str(i) + "\', "
                self.print_str = self.print_str[:-2]
                self.print_str += ")\n"

        if self.away.goals_detailed:
            self.print_str += "客队：\n"
            for item in self.away.goals_detailed:
                self.print_str += item[0] + " ("
                for i in item[1]:
                    self.print_str += str(i) + "\', "
                self.print_str = self.print_str[:-2]
                self.print_str += ")\n"

        if self.home.goals_detailed or self.away.goals_detailed:
            self.print_str += "\n"

        self.print_str += "[数据统计]\n"
        self.print_str += "控球率：" + str(round(self.home.control*100/(self.home.control+self.away.control), 1)) + \
            "%:" + str(round(self.away.control*100 /
                             (self.home.control+self.away.control), 1)) + "%\n"

        self.print_str += "射正：" + \
            str(self.home.shoots_in_target) + ":" + \
            str(self.away.shoots_in_target) + "\n"
        self.print_str += "射门：" + \
            str(self.home.shoots) + ":" + str(self.away.shoots) + "\n"
        self.print_str += "传球：" + \
            str(self.home.passes) + ":" + str(self.away.passes) + "\n"
        self.print_str += "传球成功率：" + str(round(self.home.successful_passes*100/self.home.passes, 1)) + "%:" + str(
            round(self.away.successful_passes*100/self.away.passes, 1)) + "%\n"
        self.print_str += "过人：" + \
            str(self.home.dribbles) + ":" + str(self.away.dribbles) + "\n"
        self.print_str += "抢断：" + \
            str(self.home.tackles) + ":" + str(self.away.tackles) + "\n"
        self.print_str += "扑救：" + \
            str(self.home.saves) + ":" + str(self.away.saves)
        msg = toImage(self.print_str)
        await self.matcher.send(msg)
        return msg
        # await self.matcher.send("终场比分：\n" +"主 " + self.home.coach.name + str(self.home.point) + ":" + str(self.away.point) + self.away.coach.name + " 客")

    # 开始一个回合

    def oneStep(self):
        self.step += 1
        self.reset_action_flag()
        while 1:
            # 打印球员
            # self.display.display(self.defence, self.offence, self.ball_holder)
            # time.sleep(1)
            self.offence.control += Const.ACTION_DELAY
            self.time += Const.ACTION_DELAY
            if self.time > 45 * 60:
                return
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
                shoot_defence_players_number
            )
            if holder_action == "SHOOT":
                shoot_x = self.ball_holder.shooting()
                distance = int(self.ball_holder.get_distance(shoot_x, 0))
                if distance >= 20:
                    case = Display.print_long_shot(self.ball_holder, distance)
                else:
                    case = Display.print_short_shot(self.ball_holder, distance)
                self.printCase(case)
                self.ball_holder.shoots += 1
                if shoot_x < Const.LEFT_GOALPOST or shoot_x > Const.RIGHT_GOALPOST:
                    case = Display.print_miss_shot()
                    self.printCase(case)
                    self.swap()
                    self.changeBallHolderToGK()
                else:
                    self.ball_holder.shoots_in_target += 1
                    # if shoot_x < Const.LEFT_GOALPOST + 1 or shoot_x > Const.RIGHT_GOALPOST-1:
                    #     self.printCaseWithPlayer(self.ball_holder, "射向了死角")
                    # elif shoot_x < Const.WIDTH/2 + 2 and shoot_x > Const.WIDTH/2 - 2:
                    #     self.printCaseWithPlayer(self.ball_holder, "射得太正了")
                    # else:
                    #     self.printCaseWithPlayer(self.ball_holder, "这脚射门质量尚可")

                    def_players = self.getWayDefencePlayers(
                        self.ball_holder.x, self.ball_holder.y, shoot_x, 0)
                    shoot = self.ball_holder.get_shooting_ability(shoot_x)
                    for def_player in def_players:
                        if def_player.position == "GK":
                            continue
                        # 计算防守球员到球路的距离
                        distance = def_player.get_distance_line(
                            self.ball_holder.x, self.ball_holder.y, Const.WIDTH / 2, 0)

                        if def_player.intercepting(shoot, distance):
                            case = Display.print_interception(def_player)
                            self.printCase(case)
                            self.swap()
                            self.changeBallHolder(def_player)
                            return
                    gk = self.getDefenceGK()
                    if gk.saving(shoot, self.ball_holder.get_distance(shoot_x, 0), math.fabs(shoot_x-Const.WIDTH/2)):
                        case = Display.print_saving(gk)
                        self.printCase(case)
                        gk.saves += 1
                        self.swap()
                        self.changeBallHolderToGK()
                        return
                    self.offence.point += 1
                    case = Display.print_goal(
                        self.ball_holder, gk, self.assister)
                    self.printCase(case)
                    self.ball_holder.goals += 1
                    self.ball_holder.goals_detailed.append(self.getTime())
                    if self.assister:
                      self.assister.assists += 1
                    self.timeline.append((self.getTime(), self.offence, self.ball_holder, self.assister))
                    self.swap()
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
                self.printCase(case)
                def_players = self.getWayDefencePlayers(
                    self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])
                for def_player in def_players:
                    if def_player.position == "GK":
                        continue
                    # 计算防守球员到球路的距离
                    distance = def_player.get_distance_line(
                        self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])

                    if def_player.intercepting(self.ball_holder.ability["Dribbling"], distance-def_player.ability["Speed"]/10):
                        case = Display.print_tackling(
                            self.ball_holder, def_player)
                        self.printCase(case)
                        def_player.tackles += 1
                        self.swap()
                        self.changeBallHolder(def_player)
                        return
                    else:
                        case = Display.print_dribbling(
                            self.ball_holder, def_player)
                        self.printCase(case)
                        self.ball_holder.dribbles += 1
                        def_player.action_flag = True
                self.ball_holder.moving(dribble_pos[0], dribble_pos[1])
            elif holder_action == "PASS":
                self.ball_holder.passes += 1
                passing = self.ball_holder.passing(self.getOffenceTeamMates())
                passing_type = passing[0]
                passing_aim = passing[1]
                if passing_type == "ROLLING":
                    distance = self.ball_holder.get_distance_player(
                        passing_aim)
                    case = Display.print_short_pass(
                        self.ball_holder, passing_aim, int(distance))
                    self.printCase(case)
                    def_players = self.getWayDefencePlayers(
                        self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
                    for def_player in def_players:
                        if def_player.position == "GK":
                            continue
                        # 计算防守球员到球路的距离
                        distance = def_player.get_distance_line(
                            self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
                        if def_player.intercepting(self.ball_holder.ability["Short_Passing"], distance):
                            case = Display.print_tackling(
                                self.ball_holder, def_player)
                            self.printCase(case)
                            def_player.tackles += 1
                            self.swap()
                            self.changeBallHolder(def_player)
                            return
                        else:
                            def_player.action_flag = True
                    self.ball_holder.successful_passes += 1
                    self.ball_holder.action_flag = False
                    self.assister = self.ball_holder
                    self.changeBallHolder(passing_aim)
                    # passing_aim.action_flag = True
                else:
                    passing_ability = self.ball_holder.get_passing_ability(
                        passing_aim)
                    distance = self.ball_holder.get_distance_player(
                        passing_aim)
                    case = Display.print_long_pass(
                        self.ball_holder, passing_aim, int(distance))
                    self.printCase(case)
                    if self.getLastSecondDefencePlayer().y > passing_aim.y and passing_aim.y < Const.LENGTH / 2:
                        self.printCaseWithPlayer(passing_aim, "处在越位位置")
                        self.swap()
                        self.changeBallHolderToGK()
                        return
                    for player in self.defence.players + self.offence.players:
                        if player.position == "GK":
                            continue
                        if player.get_distance_player(passing_aim) < 15 * distance / passing_ability + player.ability["Speed"] / 10\
                                and not player.action_flag:
                            player.approaching(passing_aim.x, passing_aim.y)
                            player.action_flag = True
                    roll_point_players = self.getPlayersInArea(
                        passing_aim.x, passing_aim.y, 15 * distance / passing_ability)
                    if len(roll_point_players) == 0:
                        self.printCaseWithPlayer(self.ball_holder, "传球出界")
                        self.swap()
                        self.changeBallHolderToGK()
                        return
                    roll_winner = roll_point_players[0]
                    largest_point = -1
                    for player in roll_point_players:
                        random_max = int(
                            player.ability["Heading"] * 100 / (player.get_distance_player(passing_aim) + 1))
                        rand = random.randint(0, random_max)
                        if rand > largest_point:
                            largest_point = rand
                            roll_winner = player
                    if self.isDefencePlayer(roll_winner):
                        self.printCaseWithPlayer(roll_winner, "顶到了球")
                        self.swap()
                        self.changeRandomBallHolder()
                        return
                    else:
                        self.ball_holder.successful_passes += 1
                        self.assister = self.ball_holder
                        distance_goal = roll_winner.get_distance(
                            Const.WIDTH / 2, 0)
                        rand = random.randint(
                            0, int(roll_winner.ability["Heading"] + distance_goal * 10))
                        if rand < roll_winner.ability["Heading"] and distance_goal < 16:
                            case = Display.print_high_shot(roll_winner)
                            self.printCase(case)
                            gk = self.getDefenceGK()
                            if distance_goal < 25 and \
                                    random.randint(0, int(5 * gk.ability["GK"] * (25 - distance_goal))) > 25 * roll_winner.ability["Heading"]:
                                case = Display.print_saving(gk)
                                self.printCase(case)
                                gk.saves += 1
                                self.swap()
                                self.changeBallHolderToGK()
                            else:
                                self.offence.point += 1
                                case = Display.print_goal(
                                    roll_winner, gk, self.assister)
                                self.printCase(case)
                                roll_winner.goals += 1
                                roll_winner.goals_detailed.append(
                                    self.getTime())
                                if self.assister:
                                  self.assister.assists += 1
                                self.timeline.append((self.getTime(), self.offence, self.ball_holder, self.assister))
                                self.swap()
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
                    self.ball_holder, self.getOffencePlayersInArea(player.x, player.y, 10))
            self.swapPosition(self.defence)
            # for player in self.defence.players:
            #   print(player.name + " " + str(int(player.x)) + " " + str(int(player.y)))
            # print("足球坐标：" + str(int(self.ball_holder.x)) + " " + str(int(self.ball_holder.y)))

    # 互换攻守方

    def swap(self):
        tmp = self.offence
        self.offence = self.defence
        self.defence = tmp
        self.printCase("球权转换")
        self.reset_action_flag()
        self.swapPosition(self.offence)
        self.swapPosition(self.defence)
        self.assister = None

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
        player = self.offence.players[random.randint(0, 10)]
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

    # 打印球场事件
    def printCase(self, case):
        minute = int(self.time / 60)
        second = self.time % 60
        lines = case.split("\n")
        for line in lines:
            print("主" + str(self.home.point) + ":" + str(self.away.point) +
                  "客 " + self.half + str(minute) + ":" + str(second) + " " + line)
            self.print_str += "主" + str(self.home.point) + ":" + str(self.away.point) + \
                "客 " + self.half + str(minute) + ":" + \
                str(second) + " " + line + "\n"

    # 打印球员事件
    def printCaseWithPlayer(self, player, case):
        self.printCase(player.coach + " " + player.getName() + " " + case)

    def getTime(self):
        if self.half == "上半时":
            return self.time // 60
        else:
            return self.time // 60 + 45
