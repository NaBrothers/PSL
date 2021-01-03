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
      "Heading" : Const.STARS[self.star]["ability"]+int((player.Heading_Accuracy+player.Jumping+player.Strength+Card.tocm(player.Height)-100)/4),
      "Long_Shot" : Const.STARS[self.star]["ability"]+int((player.Long_Shots+player.Shot_Power)/2),
      "Finishing" : Const.STARS[self.star]["ability"]+int((player.Finishing*2+player.Shot_Power)/3),
      "Long_Passing" : Const.STARS[self.star]["ability"]+int(player.Long_Passing),
      "Short_Passing" : Const.STARS[self.star]["ability"]+int(player.Short_Passing),
      "Dribbling" : Const.STARS[self.star]["ability"]+int((player.Dribbling*2+player.Ball_Control*2+player.Balance)/5),
      "Tackling" : Const.STARS[self.star]["ability"]+int((player.Sliding_Tackle+player.Standing_Tackle)/2),
      "Defence" : Const.STARS[self.star]["ability"]+int((player.Defensive_Awareness*2+player.Aggression+player.Interceptions*2)/5),
      "Speed" : Const.STARS[self.star]["ability"]+int((player.Sprint_Speed+player.Acceleration)/2),
      "IQ" : Const.STARS[self.star]["ability"]+int(player.Composure),
      "GK_Saving" : Const.STARS[self.star]["ability"]+int((player.GK_Handling+player.GK_Diving)/2),
      "GK_Positioning" : Const.STARS[self.star]["ability"]+int(player.GK_Positioning),
      "GK_Reaction" : Const.STARS[self.star]["ability"]+int((player.GK_Reflexes*2+player.Reactions)/3)
    }
    self.overall = self.player.Overall + Const.STARS[self.star]["ability"]
    styles = Const.GK_STYLE[style] if self.player.Position in Const.GOALKEEPER else Const.STYLE[style]
    for ability in styles.keys():
      if ability == "name":
        continue
      self.ability[ability] += styles[ability]*self.star

  def new(player, user, star = 1, style = 0, id=0, status=False):
    if style == 0:
      if player.Position in Const.GOALKEEPER:
        style = random.choice(list(Const.GK_STYLE.keys()))
      else:
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
    styles = Const.GK_STYLE[self.style] if self.player.Position in Const.GOALKEEPER else Const.STYLE[self.style]
    return self.player.Position+"\t" + self.getNameWithColor() + " " + str(self.overall) + " " + Const.STARS[self.star]["star"] + " " + styles["name"] + status

  def getNameWithColor(self):
    overall = self.star + self.player.Overall - 1
    if overall >= 97:
      ret = ""
      colors = ["r", "o", "p", "b", "f", "g"]
      letters = list(self.player.Name)
      for i in range(len(letters)):
        ret += "/~"
        ret += colors[i%6]
        ret += letters[i]
      ret += "/"
      return ret

    ret = "/~"
    if overall >= 94:
      ret += "f"
    elif overall >= 92:
      ret += "r"
    elif overall >= 89:
      ret += "o"
    elif overall >= 87:
      ret += "p"
    elif overall >= 84:
      ret += "b"
    elif overall >= 82:
      ret += "g"
    else:
      ret += "w"
    ret += self.player.Name
    ret += "/"
    return ret

  def tocm(height):
      h = height.split("'")
      foot = int(h[0])
      inch = int(h[1])
      return int((foot*12+inch)*2.54)

  def tokg(weight):
      w = int(weight.rstrip("lbs"))
      return int(0.453592*w)