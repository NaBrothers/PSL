from game.model.user import User
from game.engine.player import Player
from game.engine.team import Team
from game.engine.const import Const
from game.utils.image import toImage
# from display import Display
import random
import math
import time



class Game:

  def __init__(self, matcher, user1, user2):
    # bot回调函数
    self.matcher = matcher
    # 当前回合
    self.step = 0
    # 当前时间
    self.time = 0
    # 进攻方
    self.offence = Team(user1)
    # 防守方
    self.defence = Team(user2)
    # 主队
    self.home = self.offence
    # 客队
    self.away = self.defence
    # 主队得分
    self.home_point = 0
    # 客队得分
    self.away_point = 0
    # 上下半场
    self.half = "上半时"
    # 持球人
    self.ball_holder = self.offence.players[10]
    # gui
    # self.display = Display()
    # 打印过程
    self.print_str = ""

  # 比赛主逻辑
  async def start(self):
    self.resetPosition()
    await self.matcher.send("主 " + self.home.coach.name + ":" + self.away.coach.name + " 客\n比赛开始")
    while self.time < 45 * 60:
      self.oneStep()
      if self.time > 45 * 60:
        self.printCase("上半场结束")
      await self.matcher.send(toImage(self.print_str))
      self.print_str = ""
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
      await self.matcher.send(toImage(self.print_str))
      self.print_str = ""
      time.sleep(Const.PRINT_DELAY)
    await self.matcher.finish("终场比分：\n" +"主 " + self.home.coach.name + str(self.home_point) + ":" + str(self.away_point) + self.away.coach.name + " 客")



  # 开始一个回合
  def oneStep(self):
    self.step += 1
    self.reset_action_flag()
    while 1:
      # 打印球员
      # self.display.display(self.defence, self.offence, self.ball_holder)
      # time.sleep(1)

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
      shoot_defence_players_number = len(self.getShootDefencePlayers(self.ball_holder.x, self.ball_holder.y))
      # 持球人行为选择
      holder_action = self.ball_holder.choose_holding_action_type(
        defence_players_number,
        shoot_defence_players_number
      )
      if holder_action == "SHOOT":
        shoot_x = self.ball_holder.shooting()
        self.printCaseWithPlayer(self.ball_holder, "选择了射门 射门距离:" + str(int(self.ball_holder.get_distance(shoot_x, 0)))+"米")
        if shoot_x < Const.LEFT_GOALPOST or shoot_x > Const.RIGHT_GOALPOST:
          rand = random.randint(1, 10)
          if rand == 1:
            self.printCaseWithPlayer(self.ball_holder, "击中了门柱")
            self.swap()
            self.changeBallHolderToGK()
          else:
            self.printCaseWithPlayer(self.ball_holder, "射偏了")
            self.swap()
            self.changeBallHolderToGK()
        else:
          def_players = self.getWayDefencePlayers(self.ball_holder.x, self.ball_holder.y, shoot_x, 0)
          shoot = self.ball_holder.get_shooting_ability(shoot_x)
          for def_player in def_players:
            if def_player.position == "GK":
              continue
            # 计算防守球员到球路的距离
            distance = def_player.get_distance_line(self.ball_holder.x, self.ball_holder.y, Const.WIDTH / 2, 0)

            if def_player.intercepting(shoot, distance):
              self.printCaseWithPlayer(def_player, "拦截了射门")
              self.swap()
              self.changeBallHolder(def_player)
              return
          if self.getDefenceGK().saving(shoot):
            self.printCaseWithPlayer(self.getDefenceGK(), "扑住了球")
            self.swap()
            self.changeBallHolderToGK()
            return
          if self.ball_holder in self.home.players:
            self.home_point += 1
          else:
            self.away_point += 1
          self.printCaseWithPlayer(self.ball_holder,  "破门了！！！！")
          self.swap()
          self.resetPosition()
          self.changeBallHolderToOpen()
        return
      elif holder_action == "DRIBBLE":
        dribble_pos = self.ball_holder.dribbling(self.getDefencePlayersInArea(
        self.ball_holder.x,
        self.ball_holder.y,
        5))
        self.printCaseWithPlayer(self.ball_holder, "向" + Const.ANGLE[dribble_pos[2]] + "带球")
        def_players = self.getWayDefencePlayers(self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])
        for def_player in def_players:
          if def_player.position == "GK":
            continue
          # 计算防守球员到球路的距离
          distance = def_player.get_distance_line(self.ball_holder.x, self.ball_holder.y, dribble_pos[0], dribble_pos[1])

          if def_player.intercepting(self.ball_holder.ability["Dribbling"], distance-def_player.ability["Speed"]/10):
            self.printCaseWithPlayer(def_player, "抢下了球")
            self.swap()
            self.changeBallHolder(def_player)
            return
          else:
            self.printCaseWithPlayer(self.ball_holder, "过掉了" + def_player.name)
            def_player.action_flag = True
        self.ball_holder.moving(dribble_pos[0], dribble_pos[1])
      elif holder_action == "PASS":
        passing = self.ball_holder.passing(self.getOffenceTeamMates())
        passing_type = passing[0]
        passing_aim = passing[1]
        if passing_type == "ROLLING":
          self.printCaseWithPlayer(self.ball_holder, "选择地面传球给"+passing_aim.name+" 传球距离:"+str(int(self.ball_holder.get_distance_player(passing_aim)))+"米")
          def_players = self.getWayDefencePlayers(self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
          for def_player in def_players:
            if def_player.position == "GK":
              continue
            # 计算防守球员到球路的距离
            distance = def_player.get_distance_line(self.ball_holder.x, self.ball_holder.y, passing_aim.x, passing_aim.y)
            if def_player.intercepting(self.ball_holder.ability["Short_Passing"], distance):
              self.printCaseWithPlayer(def_player, "断下了传球")
              self.swap()
              self.changeBallHolder(def_player)
              return
            else:
              def_player.action_flag = True
          self.ball_holder.action_flag = False
          self.changeBallHolder(passing_aim)
          # passing_aim.action_flag = True
        else:
          passing_ability = self.ball_holder.get_passing_ability(passing_aim)
          distance = self.ball_holder.get_distance_player(passing_aim)
          self.printCaseWithPlayer(self.ball_holder, "选择过顶传球给" + passing_aim.name+" 传球距离:"+str(int(distance))+"米")
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
          roll_point_players = self.getPlayersInArea(passing_aim.x, passing_aim.y, 15 * distance / passing_ability)
          if len(roll_point_players) == 0:
            self.printCaseWithPlayer(self.ball_holder, "传球出界")
            self.swap()
            self.changeBallHolderToGK()
            return
          roll_winner = roll_point_players[0]
          largest_point = -1
          for player in roll_point_players:
            random_max = int(player.ability["Heading"] * 100 / (player.get_distance_player(passing_aim) + 1))
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
            distance_goal = roll_winner.get_distance(Const.WIDTH / 2, 0)
            rand = random.randint(0, int(roll_winner.ability["Heading"] + distance_goal * 10))
            if rand < roll_winner.ability["Heading"] and distance_goal < 16:
              self.printCaseWithPlayer(roll_winner, "直接头球攻门")

              if distance_goal < 25 and \
                random.randint(0, int(5 * self.getDefenceGK().ability["GK"] * (25 - distance_goal))) > 25 * roll_winner.ability["Heading"]:
                self.printCaseWithPlayer(self.getDefenceGK(), "扑住了球")
                self.swap()
                self.changeBallHolderToGK()
              else:
                if self.ball_holder in self.home.players:
                  self.home_point += 1
                else:
                  self.away_point += 1
                self.printCaseWithPlayer(roll_winner, "破门了！！！！")
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
        player.off_ball_moving(self.ball_holder, self.getOffencePlayersInArea(player.x, player.y, 10))
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
      line_value = y * (def_x - x + def_v) - (def_y - y) * (x - def_v - Const.LEFT_GOALPOST)
      if line_value < 0:
        continue
      line_value = y * (def_x - x - def_v) - (def_y - y) * (x + def_v - Const.RIGHT_GOALPOST)
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
      line_value = (y - fin_y) * (def_x - x + def_v) - (def_y - y) * (x - def_v - fin_x)
      if line_value < 0:
        continue
      line_value = (y - fin_y) * (def_x - x - def_v) - (def_y - y) * (x + def_v - fin_x)
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
    print("主" + str(self.home_point) + ":" + str(self.away_point) + "客 " + self.half + str(minute) + ":" + str(second) + " " + case)
    self.print_str += "主" + str(self.home_point) + ":" + str(self.away_point) + "客 " + self.half + str(minute) + ":" + str(second) + " " + case + "\n"

  # 打印球员事件
  def printCaseWithPlayer(self, player, case):
    if player in self.defence.players:
      coach = self.defence.coach
    else:
      coach = self.offence.coach
    self.printCase(coach.name + " " + player.position + " " + player.name + " " + case)




