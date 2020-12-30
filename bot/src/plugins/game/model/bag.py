from game.utils.database import *
from game.model.user import *
from game.model.player import *

class Bag:
  def __init__(self, data:list):
    self.user = User.getUserByQQ(data[0][0])
    self.players = [Player.getPlayerByID(i[1]) for i in data]

  def getBagByUser(user):  
        cursor = g_database.cursor()
        count = cursor.execute("select user,player from bag where user = " + str(user.qq))
        if (count == 0):
            bag = None
        else:
            bag = Bag(cursor.fetchall())
        cursor.close()
        return bag

  def add(user, player):
      g_database.update("insert into bag (user, player) values (" + str(user.qq) + "," + str(player.ID)+")")

  def addMany(user, players:list):
      cursor = g_database.cursor()
      for player in players:
        cursor.execute("insert into bag (user, player) values (" + str(user.qq) + "," + str(player.ID)+")")
      cursor.close()
    