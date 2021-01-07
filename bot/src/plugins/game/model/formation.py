from game.model.user import User
from game.model.card import Card
from game.utils.database import *

class Formation():
  PLAYERS_COUNT = 17

  def __init__(self, data:list):
    self.user = User.getUserByQQ(data[0][1])
    self.cards = [Card.getCardByID(i[2]) for i in data]
    self.formation = self.user.formation
    self.coordinates = Const.FORMATION[self.formation]["coordinates"]

  def getFormation(user):
      cursor = g_database.cursor()
      count = cursor.execute("select * from team where user = " + str(user.qq) + " order by position;")
      if (count == 0):
          for i in range(Formation.PLAYERS_COUNT):
            cursor.execute("insert into team (user, card, position) values (" + str(user.qq) + "," + str(0) + "," + str(i) + ");")
          return Formation.getFormation(user)
      else:
          team = Formation(cursor.fetchall())
      cursor.close()
      return team

  # 返回四个值：总能力，前场能力，中场能力，后场能力
  def getAbilities(self, user):
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