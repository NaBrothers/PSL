from model.formation import Formation
from model.npc_formation import NpcFormation
from model.user import User
from engine.player import Player
from utils.const import Const
class Team:
  def __init__(self, user, npc=-1, difficulty=0):
    # 教练
    self.coach = user
    self.npc = npc
    self.difficulty = difficulty
    if npc == -1:
      self.players = self.getPlayers()
    else:
      self.coach = User([
        0,
        0,
        Const.NPC[npc]["name"] + " " + difficulty,
        0,
        0,
        Const.NPC[npc]["formation"],
        False
      ]
      )
      self.players = self.getNpcPlayers()
    self.point = 0
    self.control = 0
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.passes = 0
    self.successful_passes = 0
    self.dribbles = 0
    self.assists = 0
    self.tackles = 0
    self.saves = 0
    self.goals_detailed = []

  # 返回包含NpcPlayer的列表
  def getNpcPlayers(self):
    formation = NpcFormation(self.npc, self.difficulty)
    players = []
    for i in range(0, 11):
      player = Player(formation.cards[i],
                      Const.FORMATION[formation.formation]["positions"][i],
                      formation.coordinates[i][0],
                      formation.coordinates[i][1],
                      Const.NPC[self.npc]["name"])
      players.append(player)
    return players

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
      self.dribbles += player.dribbles
      self.assists += player.assists
      self.tackles += player.tackles
      self.saves += player.saves
      if player.goals_detailed:
        self.goals_detailed.append((player.getName(), player.goals_detailed))
