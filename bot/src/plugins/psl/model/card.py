from utils.database import *
from model.user import *
from model.player import *

class Card:
  def __init__(self, id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked):
    self.id = id
    self.player = player
    self.user = user
    self.star = star
    self.style = style
    self.status = status
    self.appearance = appearance
    self.goal = goal
    self.assist = assist
    self.tackle = tackle
    self.save = save
    self.total_appearance = total_appearance
    self.total_goal = total_goal
    self.total_assist = total_assist
    self.total_tackle = total_tackle
    self.total_save = total_save
    self.locked = locked
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
  
    self.price = self.player.price * Const.STARS[self.star]["count"]

  def new(player, user, star = 1, style = 0, id=0, status=False, locked=False):
    if style == 0:
      if player.Position in Const.GOALKEEPER:
        style = random.choice(list(Const.GK_STYLE.keys()))
      else:
        style = random.choice(list(Const.STYLE.keys()))
    return Card(id ,player, user, star, style, status, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, locked)

  def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update cards set " + attr + " = " + str(value) + " where id = " + str(self.id))
      cursor.close()

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
            appearance = data[6]
            goal = data[7]
            assist = data[8]
            tackle = data[9]
            save = data[10]
            total_appearance = data[11]
            total_goal = data[12]
            total_assist = data[13]
            total_tackle = data[14]
            total_save = data[15]
            locked = data[16]
            card = Card(id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked)
        cursor.close()
        return card

  def getCardByIDMany(ids):
        cursor = g_database.cursor()
        cards = []
        sql = "select * from cards where id in ("
        for id in ids:
            sql += str(id)+","
        sql += "-1)"
        count = cursor.execute(sql)
        if count:
          datas = cursor.fetchall()
          player_ids = [data[1] for data in datas]
          players = Player.getPlayerByIDMany(player_ids)
          user = User.getUserByQQ(datas[0][2])
          for i,data in enumerate(datas):
              id = data[0]
              player = players[i]
              user = user
              star = data[3]
              style = data[4]
              status = data[5]
              appearance = data[6]
              goal = data[7]
              assist = data[8]
              tackle = data[9]
              save = data[10]
              total_appearance = data[11]
              total_goal = data[12]
              total_assist = data[13]
              total_tackle = data[14]
              total_save = data[15]
              locked = data[16]
              card = Card(id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked)
              cards.append(card)
        
        cursor.close()
        return cards

  def format(self):
    return self.player.Position.ljust(3)+" " + self.getNameWithColor() + " " + str(self.overall) + " " + Const.STARS[self.star]["star"] + " " + self.getStyle() +  " " + self.printPrice() + " " + self.getStatus()

  def getStatus(self):
    if self.status != 0:
      status = " (" + Const.STATUS[self.status] + ")"
    elif self.locked:
      status = " (已锁定)"
    else:
      status = ""
    return status

  def printID(self):
    if self.id == 0:
      return ""
    return "[" + str(self.id) + "]"

  def getStyle(self):
    styles = Const.GK_STYLE[self.style] if self.player.Position in Const.GOALKEEPER else Const.STYLE[self.style]
    return styles["name"]

  def getNameWithColor(self):
    overall = self.star + self.player.Overall - 1
    ret = "/~"
    if overall >= 97:
      ret += "$"
    elif overall >= 94:
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

  def getRealOverall(self, position):
    if position in ["ST", "RS", "LS"]:
      position = "ST"
    elif position in ["CF", "LF", "RF"]:
      position = "CF"
    elif position in ["RW", "LW"]:
      position = "LRW"
    elif position in ["CAM", "RAM", "LAM"]:
      position = "AM"
    elif position in ["LM", "RM"]:
      position = "LRM"
    elif position in ["CM", "RCM", "LCM"]:
      position = "CM"
    elif position in ["CDM", "RDM", "LDM"]:
      position = "DM"
    elif position in ["CB", "RCB", "LCB"]:
      position = "CB"
    elif position in ["LB", "LWB", "RB", "RWB"]:
      position = "LRB"
    elif position in ["GK"]:
      position = "GK"
    overall = 0
    for a in Const.REAL_ABILITY[position].keys():
      overall += Const.REAL_ABILITY[position][a] * self.ability[a]
    return int(overall)

  def printRealOverall(self, position):
    real = self.getRealOverall(position)
    diff = real - self.overall
    if diff > 0:
      return str(real) + "/~r▲" + str(diff)  + "/"
    elif diff < 0:
      return str(real) + "/~g▼" + str(-diff)  + "/"
    else:
      return str(real) + "/~w" + "　" + "/"

  def printPrice(self):
    return Card.formatPrice(self.price)
  
  def formatPrice(price):
    if price >= 1000000:
      price = price // 10000
      return "$" + str(price) + "万"
    elif price >= 100000:
      price = format(price/10000, '.1f')
      return "$" + str(price) + "万"
    elif price >= 10000:
      price = format(price/10000, '.2f')
      return "$" + str(price) + "万"
    return "$" + str(price)

  # 返回(位置，能力)的列表
  def getOveralls(self):
    tmp = []
    for position in Const.REAL_ABILITY.keys():
      tmp.append((position, self.getRealOverall(position)))
    tmp.sort(key = lambda x: x[1], reverse=True)
    return tmp

  def remove(self):
    cursor = g_database.cursor()
    cursor.execute("delete from cards where id = " + str(self.id))
    cursor.close()