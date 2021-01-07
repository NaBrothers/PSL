from game.model.formation import Formation
from game.model.user import User
from game.engine.player import Player
from game.utils.const import *
class Team:
  def __init__(self, user):
    # 教练
    self.coach = user
    self.players = self.getPlayers()

  # 返回包含Player的列表
  def getPlayers(self):
    formation = Formation.getFormation(self.coach)
    players = []
    for i in range(0, 11):
      player = Player(formation.cards[i],
                      Const.FORMATION[formation.formation]["positions"][i],
                      formation.coordinates[i][0],
                      formation.coordinates[i][1])
      players.append(player)
    return players
    
