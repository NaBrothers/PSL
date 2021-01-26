from game.model.card import Card
from game.engine.const import Const
import random
import math
import sys


class Player:
  def __init__(self, card, position, default_x, default_y, coach):
    """

    :param card: 球员卡
    :param x: 当前横坐标
    :param y: 当前纵坐标
    :param default_x: 默认横坐标
    :param default_y: 默认纵坐标
    :param action_flag: 行动标记
    """
    self.name = card.getNameWithColor()
    self.coach = coach
    self.position = position
    # 格式 ability["Short_Passing"] 具体请看Card
    self.ability = card.ability
    self.x = default_x
    self.y = default_y
    self.default_x = default_x
    self.default_y = default_y
    self.action_flag = False
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.passes = 0
    self.successful_passes = 0
    self.assists = 0
    self.tackles = 0
    self.saves = 0
    self.dribbles = 0
    self.goals_detailed = []

  # def __init__(self, name, position, ability, x, y):
  #   self.name = name
  #   self.position = position
  #   # 格式 ability["Short_Passing"] 具体请看Card
  #   self.ability = ability
  #   self.x = x
  #   self.y = y
  #   self.default_x = x
  #   self.default_y = y
  #   self.action_flag = False


  # 无球跑动-无球行为
  def off_ball_moving(self, ball_holder, team_mate_in_range):
    if self in team_mate_in_range:
      del team_mate_in_range[team_mate_in_range.index(self)]
    if self.position == "GK":
      self.approaching(self.default_x, self.default_y)
    else:
      distance_default = self.get_distance(self.default_x, self.default_y)
      if distance_default > 30:
        self.approaching(self.default_x, self.default_y)
      if len(team_mate_in_range) > 0:
        self.go_away(team_mate_in_range[0].x, team_mate_in_range[0].y)
        return
      distance_ball = self.get_distance_player(ball_holder)
      rand = random.randint(0, int(distance_default * 100 + distance_ball * 100))
      if rand < distance_default * 100:
        self.approaching(self.default_x, self.default_y)
      else:
        self.approaching(ball_holder.x, ball_holder.y)

  # 移动到指定点-有球/无球行为
  def moving(self, x, y):
    self.x = x
    self.y = y

  # 向指定点靠近-无球行为
  def approaching(self, x, y):
    distance = self.get_distance(x, y)
    if distance < self.ability["Speed"]/10:
      self.moving(x, y)
    else:
      aim_x = self.x + (x - self.x) * self.ability["Speed"] / (10 * distance)
      aim_y = self.y + (y - self.y) * self.ability["Speed"] / (10 * distance)
      self.moving(aim_x, aim_y)

  # 远离指定点-无球行为
  def go_away(self, x, y):
    distance = self.get_distance(x, y)
    if distance == 0:
      rand = random.randint(0, 360)
      aim_x = self.x + self.ability["Speed"] * math.cos(rand * math.pi / 180) / 10
      aim_y = self.x + self.ability["Speed"] * math.sin(rand * math.pi / 180) / 10
    else:
      aim_x = self.x - (x - self.x) * self.ability["Speed"] / (10 * distance)
      aim_y = self.y - (y - self.y) * self.ability["Speed"] / (10 * distance)
    self.moving(self.get_x_inside(aim_x), self.get_y_inside(aim_y))

  # 盘带-持球行为
  def dribbling(self, defence_players: list):
    best_angle = 0
    best_sum = -99999
    for angle in range(0, 360, 45):
      x = self.x + math.sin(angle*math.pi/180)*self.ability["Speed"]/10
      y = self.y - math.cos(angle*math.pi/180)*self.ability["Speed"]/10

      cur_sum = -math.sqrt(math.pow(x - Const.WIDTH/2, 2) + math.pow(y, 2))
      for defence_player in defence_players:
        cur_sum += defence_player.get_distance(x, y)
      if cur_sum > best_sum:
        best_sum = cur_sum
        best_angle = angle
    return self.get_x_inside(self.x + math.sin(best_angle * math.pi / 180) * self.ability["Speed"] / 10), \
           self.get_y_inside(self.y - math.cos(best_angle * math.pi / 180) * self.ability["Speed"] / 10), \
           best_angle

  # 射门-持球行为
  def shooting(self):
    distance = self.get_distance(Const.WIDTH / 2, 0)
    shoot_ability = self.ability["Finishing"] if distance < 20 else self.ability["Long_Shot"]
    miss_rate = distance/shoot_ability
    random_min = (Const.LEFT_GOALPOST - Const.GOAL_WIDTH * miss_rate / 2) * 100
    random_max = (Const.RIGHT_GOALPOST + Const.GOAL_WIDTH * miss_rate / 2) * 100
    rand = random.randint(int(random_min), int(random_max))
    return rand / 100

  # 选择传球目标-持球行为
  def passing(self, team_mates: list):
    best_choice_player = team_mates[0]
    best_value = sys.maxsize
    for player in team_mates:
      cur_value = (20 + 2 * self.get_distance_player(player) + random.randint(1, 100)) * \
                  (10 + player.get_distance(Const.WIDTH / 2, 0) + random.randint(1, 100))
      if cur_value < best_value:
        best_value = cur_value
        best_choice_player = player
    distance = self.get_distance_player(best_choice_player)
    if distance > 30:
      passing_type = "LOBBING"
    else:
      passing_type = "ROLLING"
    return passing_type, best_choice_player


  # 拦截-被动触发
  def intercepting(self, ability, distance):
    if distance < 0:
      distance = 0
    tackling = self.ability["Tackling"]
    def_v = self.ability["Defence"] / 15
    efficiency = (def_v - distance) / def_v
    if efficiency <= 0:
      return False
    success_rate = self.get_success_rate(tackling * efficiency, ability)
    rand = random.randint(0, int((success_rate + 1)*100))
    if rand < 100:
      return False
    else:
      return True

  # 扑救-被动触发
  def saving(self, shoot_ability, distance, shoot_place):
    success_rate = self.get_success_rate(self.ability["GK_Saving"], shoot_ability) *\
      math.pow(distance, 0.6)*self.ability["GK_Reaction"]*math.pow(shoot_ability, -1)/4 *\
      math.pow(1.1, math.pow(self.ability["GK_Positioning"], 1.5)/shoot_ability-shoot_place)*0.65
    rand = random.randint(0, int((success_rate + 1)*100))
    if rand < 100:
      return False
    else:
      return True

  # 动作成功率
  def get_success_rate(self, self_ability, opposite_ability):
    return math.pow(1.1, self_ability - opposite_ability)

  # 持球行为选择
  def choose_holding_action_type(self, defence_players_number, shoot_defence_players_number):
    shoot_rate_factor = self.get_shooting_rate(shoot_defence_players_number) * 100
    if shoot_rate_factor > 0:
      rand = random.randint(0, 100)
      if rand < shoot_rate_factor:
        return "SHOOT"
    dribbling_rate_factor = self.get_dribbling_rate(defence_players_number) * 100
    passing_rate_factor = self.get_passing_rate(defence_players_number) * 100
    sum_rate_factor = dribbling_rate_factor + passing_rate_factor
    rand = random.randint(0, int(sum_rate_factor))
    if rand < dribbling_rate_factor and self.get_distance(self.default_x, self.default_y) < 25:
      return "DRIBBLE"
    else:
      return "PASS"

  # 射门选择率
  def get_shooting_rate(self, shoot_defence_players_number):
    distance = self.get_distance(Const.WIDTH / 2, 0)
    if distance > 40:
      return 0
    return math.pow(0.99, 0.004 * math.pow(distance, 3) * shoot_defence_players_number)

  # 盘带选择率
  def get_dribbling_rate(self, defence_players_number):
    return self.ability["Dribbling"] / ((defence_players_number + 1) * (self.get_distance(self.default_x, self.default_y) + 1))

  # 传球选择率
  def get_passing_rate(self, defence_players_number):
    return (self.ability["Long_Passing"] + self.ability["Short_Passing"]) * (defence_players_number + 1) / 40

  # 获取射门能力值
  def get_shooting_ability(self, shoot_x):
    distance = self.get_distance(shoot_x, 0)
    if distance < 20:
      return self.ability["Finishing"]
    else:
      return self.ability["Long_Shot"]

  # 获得传球能力值
  def get_passing_ability(self, player):
    distance = self.get_distance_player(player)
    if distance < 30:
      return self.ability["Short_Passing"]
    else:
      return self.ability["Long_Passing"]

  # 与球员距离计算
  def get_distance_player(self, player):
    return self.get_distance(player.x, player.y)

  # 与点距离计算
  def get_distance(self, x, y):
    return math.sqrt(math.pow(self.x - x, 2) + math.pow(self.y - y, 2))

  # 点与直线距离计算
  def get_distance_line(self, x1, y1, x2, y2):
    a = y1 - y2
    b = x2 - x1
    c = y1 * (x1 - x2) - x1 * (y1 - y2)
    if a == 0 and b == 0:
      return self.get_distance(x1, y1)
    return math.fabs(a * self.x + b * self.y + c) / math.sqrt(math.pow(a, 2) + math.pow(b, 2))

  # 重置位置为开球位置
  def reset_position(self):
    self.x = self.default_x
    self.y = Const.LENGTH - (Const.LENGTH - self.default_y) / 2

  # 横坐标取场内
  def get_x_inside(self, x):
    if x < 0:
      return 0
    if x > Const.WIDTH:
      return Const.WIDTH
    return x

  # 纵坐标取场内
  def get_y_inside(self, y):
    if y < 0:
      return 0
    if y > Const.LENGTH:
      return Const.LENGTH
    return y

  def getName(self):
    return self.position + " " + self.name