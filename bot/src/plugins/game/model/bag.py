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
    self.cards = [Card(players[i], user, stars[i], styles[i], ids[i]) for i in range(len(data))]
    self.cards.sort(key = lambda p : (p.player.Overall, p.player.Name), reverse=True)
    