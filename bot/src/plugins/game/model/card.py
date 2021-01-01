from game.utils.database import *
from game.model.user import *
from game.model.player import *

class Card:
  def __init__(self, id, player, user, star, style, status):
    self.id = id
    self.player = player
    self.user = user
    self.star = star
    self.style = style
    self.status = status

  def new(player, user, star = 1, style = 0, id=0, status=False):
    if style == 0:
      style = random.choice(list(Const.STYLE.keys()))
    return Card(id ,player, user, star, style, status)

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
            status = data[5]
            card = Card(id, player, user, star, style, status)
        cursor.close()
        return card


  def format(self):
    if self.status != 0:
      status = " (" + Const.STATUS[self.status] + ")"
    else:
      status = ""
    return self.player.Position+" " + Const.QUALITY[self.player.Overall] + self.player.Name + "/ " + str(self.player.Overall) + " " + Const.STARS[self.star] + " " + Const.STYLE[self.style]["name"] + status
