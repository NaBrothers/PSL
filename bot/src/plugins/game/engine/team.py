from game.model.formation import Formation
from game.model.user import User
from game.engine.player import Player
class Team:
  def __init__(self, user):
    # 教练
    self.coach = user
    self.players = getPlayers()

  # 返回包含Player的列表
  def getPlayers():
    cards = Formation.getFormation(self.coach)
    return [Player(card) for card in cards]
    
