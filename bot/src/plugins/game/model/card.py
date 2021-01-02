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
    self.ability = {
      "Heading" : 0,
      "Long_Shot" : 0,
      "Finishing" : 0,
      "Long_Passing" : 0,
      "Short_Passing" : 0,
      "Dribbling" : 0,
      "Tackling" : 0,
      "Defence" : 0,
      "Speed" : 0,
      "IQ" : 0
    }
    self.overall = self.player.Overall + Const.STARS[self.star][1]

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
    return self.player.Position+"\t" + self.getNameWithColor() + " " + str(self.overall) + " " + Const.STARS[self.star][0] + " " + Const.STYLE[self.style]["name"] + status

  def getNameWithColor(self):
    overall = self.star + self.player.Overall
    if overall >= 100:
      ret = ""
      colors = ["r", "o", "p", "b", "g"]
      letters = list(self.player.Name)
      for i in range(len(letters)):
        ret += "/~"
        ret += colors[i%5]
        ret += letters[i]
      ret += "/"
      return ret

    ret = "/~"
    if overall >= 92:
      ret += "r"
    elif overall >= 89:
      ret += "o"
    elif overall >= 87:
      ret += "p"
    elif overall >= 84:
      ret += "b"
    elif overall >= 82:
      ret += "g"
    elif overall >= 80:
      ret += "w"
    ret += self.player.Name
    ret += "/"
    return ret