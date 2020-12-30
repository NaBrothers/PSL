from game.utils.database import *
from game.model.user import *
from game.model.player import *

class Bag:
  def __init__(self, data:list):
    self.user = User.getUserByQQ(data[0][1])
    players = Player.getPlayerByIDMany([i[2] for i in data])
    ids = [i[0] for i in data]
    self.players = [(ids[i], players[i]) for i in range(len(players))]
    self.players.sort(key = lambda p : p[1].Overall, reverse=True)

  def getBagByUser(user):  
        cursor = g_database.cursor()
        count = cursor.execute("select * from bag where user = " + str(user.qq))
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
    