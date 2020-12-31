from game.utils.database import *
from game.model.user import *
from game.model.player import *

class Card:
  def __init__(self, player, user, star, style, id):
    self.id = id
    self.player = player
    self.user = user
    self.star = star
    self.style = style

  def new(player, user, star = 1, style = 0, id=0):
    if style == 0:
      style = random.choice(list(Const.STYLE.keys()))
    return Card(player, user, star, style, id)

  def getCardByID(id):
        cursor = g_database.cursor()
        count = cursor.execute("select * from cards where id = " + str(id))
        if (count == 0):
            card = None
        else:
            data = cursor.fetchone()
            id = data[0]
            player = Player.getPlayerByID(data[1])
            user = User.getUserByQQ(data[2])
            star = data[3]
            style = data[4]
            card = Card(player, user, star, style, id)
        cursor.close()
        return card


  def format(self):
    return self.player.Position+"\t" + Const.QUALITY[self.player.Overall] + self.player.Name + "/ " + str(self.player.Overall) + " " + Const.STARS[self.star] + " " + Const.STYLE[self.style]["name"]
