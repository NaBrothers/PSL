from game.utils.database import *
from game.model.user import *
from game.model.player import *
from game.model.card import *

# 一系列Card
class Bag:
  def __init__(self, data:list): 
    ids = [i[0] for i in data]
    players = Player.getPlayerByIDMany([i[1] for i in data])
    user = data[0][2]
    stars = [i[3] for i in data]
    styles = [i[4] for i in data]
    statuses = [i[5] for i in data]
    self.cards = [Card(ids[i], players[i], user, stars[i], styles[i], statuses[i]) for i in range(len(data))]
    self.cards.sort(key = lambda p : (p.player.Overall, p.player.Name), reverse=True)

  def getBag(user):
      cursor = g_database.cursor()
      count = cursor.execute("select * from cards where user = " + str(user.qq))
      if (count == 0):
          bag = None
      else:
          bag = Bag(cursor.fetchall())
      cursor.close()
      return bag

  def addToBag(user, card):
      g_database.update("insert into cards (user, player, star, style) values (" + str(user.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")

  def addToBagMany(user, cards:list):
      cursor = g_database.cursor()
      for card in cards:
        g_database.update("insert into cards (user, player, star, style) values (" + str(user.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")
      cursor.close()
    