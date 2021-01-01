from game.utils.database import *
from game.model.user import *
from game.model.player import *
from game.model.card import *

class Transfer:
  def __init__(self, data:list): 
    self.id = data[0]
    self.user = User.getUserByQQ(data[1])
    self.card = Card.getCardByID(data[2])
    self.cost = data[3]

  def format(self):
    return self.user.name + " [" + str(self.card.id) + "] " + self.card.player.Position+"\t" + Const.QUALITY[self.card.player.Overall] + self.card.player.Name + "/ " + str(self.card.player.Overall) + " " + Const.STARS[self.card.star] + " " + Const.STYLE[self.card.style]["name"] + " $" + str(self.cost) 
    