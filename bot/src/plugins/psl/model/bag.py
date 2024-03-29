from utils.database import *
from model.user import *
from model.player import *
from model.card import *

# 一系列Card
class Bag:
  def __init__(self, data:list): 
    ids = [i[0] for i in data]
    self.cards = Card.getCardByIDMany(ids)
    self.cards.sort(key = lambda p : (p.overall, p.player.Name), reverse=True)

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
      cursor = g_database.cursor()
      count = cursor.execute("insert into cards (user, player, star, style) values (" + str(user.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")
      count = cursor.execute("SELECT LAST_INSERT_ID()")
      id = cursor.fetchone()[0]
      cursor.close()
      return id

  def addToBagMany(user, cards:list):
      cursor = g_database.cursor()
      ids = []
      for card in cards:
        count = cursor.execute("insert into cards (user, player, star, style) values (" + str(user.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")
        count = cursor.execute("SELECT LAST_INSERT_ID()")
        ids.append(cursor.fetchone()[0])
      cursor.close()
      return ids
    