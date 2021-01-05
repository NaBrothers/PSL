from game.model.user import User
from game.model.card import Card
from game.utils.database import *

class Formation():
  PLAYERS_COUNT = 17

  def __init__(self, data:list):
    self.user = User.getUserByQQ(data[0][1])
    self.cards = [Card.getCardByID(i[2]) for i in data]
    self.formation = self.user.formation

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