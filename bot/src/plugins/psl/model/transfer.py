from utils.database import *
from model.user import *
from model.player import *
from model.card import *

class Transfer:
  def __init__(self, data:list): 
    self.id = data[0]
    self.user = User.getUserByQQ(data[1])
    self.card = Card.getCardByID(data[2])
    self.cost = data[3]

  def format(self):
    return self.user.name + " [" + str(self.card.id) + "] " + self.card.player.Position+"\t" + self.card.getNameWithColor() + " " + str(self.card.overall) + " " + Const.STARS[self.card.star]["star"] + " ◆+" + str(self.breach)  + " " + self.card.getStyle() + " " + Card.formatPrice(self.cost)
    