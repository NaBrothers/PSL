from game.model.user import User
from game.model.card import Card
from game.utils.database import *
from game.utils.const import Const
from game.model.player import Player

class NpcFormation():
  PLAYERS_COUNT = 11

  def __init__(self, npc, difficulty):
    normalized_npc = Const.NPC[npc % len(Const.NPC)]
    star = Const.DIFFICULTY[difficulty]["star"]

    self.name = normalized_npc["name"]
    self.formation = normalized_npc["formation"]
    self.coordinates = Const.FORMATION[self.formation]["coordinates"]
    positions = Const.FORMATION[self.formation]["positions"]
    self.cards = [
      Card.new(
        Player.getPlayerByID(normalized_npc["players"][i]),
        0,
        star,
        Const.NPC_STYLE[positions[i]],
        ) for i in range(0, NpcFormation.PLAYERS_COUNT)
      ]

  # 返回四个值：总能力，前场能力，中场能力，后场能力
  def getAbilities(self):
      total = 0
      forward = 0
      midfield = 0
      guard = 0
      forward_count = 0
      midfield_count = 0
      guard_count = 0
      positions = Const.FORMATION[self.formation]["positions"]
      for i in range(11):
        if positions[i] in Const.FORWARD:
          forward_count += 1 
        elif positions[i] in Const.MIDFIELD:
          midfield_count += 1
        elif positions[i] in Const.GUARD:
          guard_count += 1
        elif positions[i] in Const.GOALKEEPER:
          guard_count += 1
        if self.cards[i] == None:
          continue
        overall = self.cards[i].getRealOverall(positions[i])
        total += overall
        if positions[i] in Const.FORWARD:
          forward += overall
        elif positions[i] in Const.MIDFIELD:
          midfield += overall
        elif positions[i] in Const.GUARD:
          guard += overall
        elif positions[i] in Const.GOALKEEPER:
          guard += overall
      if forward_count == 0:
        forward_count = 1
      if midfield_count == 0:
        midfield_count = 1
      if guard_count == 0:
        guard_count = 1
      return (total, forward // forward_count, midfield // midfield_count, guard // guard_count)

  def isValid(self):
    return None not in self.cards