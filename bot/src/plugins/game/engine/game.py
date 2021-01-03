from game.engine.player import Player
from game.engine.team import Team

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

  # 比赛主逻辑
  def start():
    pass

  # 互换攻守方
  def swap():
    tmp = self.offence
    self.offence = self.defence
    self.defence = tmp