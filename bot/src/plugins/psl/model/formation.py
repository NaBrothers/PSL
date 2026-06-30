from model.user import User
from model.card import Card
from utils.database import *

from psl_core.constants import FORMATION as FORMATION_DATA
from psl_core.formation import compute_formation_abilities, get_formation_positions


class Formation():
  PLAYERS_COUNT = 18

  def __init__(self, data:list):
    self.user = User.getUserByQQ(data[0][1])
    self.cards = [Card.getCardByID(i[2]) for i in data]
    self.formation = self.user.formation
    self.coordinates = FORMATION_DATA[self.formation]["coordinates"]

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

  def getAbilities(self, user):
      positions = get_formation_positions(self.formation)
      real_overalls = []
      for i in range(11):
        card = self.cards[i] if i < len(self.cards) else None
        if card is None:
          real_overalls.append(None)
        else:
          real_overalls.append(card.getRealOverall(positions[i]))
      return compute_formation_abilities(positions, real_overalls)

  def isValid(self):
    return None not in self.cards
