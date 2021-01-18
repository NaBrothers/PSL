from game.model.formation import Formation
from game.model.user import User
from game.engine.player import Player
from game.utils.const import *
class Team:
  def __init__(self, user):
    # 教练
    self.coach = user
    self.players = self.getPlayers()
    self.point = 0
    self.control = 0
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.passes = 0
    self.successful_passes = 0
    self.surpasses = 0
    self.goals_detailed = []

  # 返回包含Player的列表
  def getPlayers(self):
    formation = Formation.getFormation(self.coach)
    players = []
    for i in range(0, 11):
      player = Player(formation.cards[i],
                      Const.FORMATION[formation.formation]["positions"][i],
                      formation.coordinates[i][0],
                      formation.coordinates[i][1],
                      self.coach.name)
      players.append(player)
    return players
    
  def getStats(self):
    for player in self.players:
      self.shoots += player.shoots
      self.shoots_in_target += player.shoots_in_target
      self.goals += player.goals
      self.passes += player.passes
      self.successful_passes += player.successful_passes
      self.surpasses += player.surpasses
      if player.goals_detailed:
        self.goals_detailed.append((player.getName(), player.goals_detailed))
