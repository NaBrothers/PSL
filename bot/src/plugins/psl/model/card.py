from utils.database import *
from model.user import *
from model.player import *
import json
import random

from psl_core.card import (
    compute_abilities, compute_real_overall, compute_overall,
    compute_price, get_name_with_color, get_style_name, format_price,
    compute_all_position_ratings,
)
from psl_core.constants import STARS, STYLE, GK_STYLE, GOALKEEPER, REAL_ABILITY, STATUS


class Card:
  def __init__(self, id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked, ext_abilities, breach):
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
    self.ext_abilities = ext_abilities
    self.breach = breach

    self.ability = compute_abilities(
        star=star,
        style=style,
        position=player.Position,
        height=int(player.Height),
        heading_accuracy=player.Heading_Accuracy,
        jumping=player.Jumping,
        strength=player.Strength,
        long_shots=player.Long_Shots,
        shot_power=player.Shot_Power,
        finishing=player.Finishing,
        long_passing=player.Long_Passing,
        short_passing=player.Short_Passing,
        dribbling=player.Dribbling,
        ball_control=player.Ball_Control,
        balance=player.Balance,
        sliding_tackle=player.Sliding_Tackle,
        standing_tackle=player.Standing_Tackle,
        defensive_awareness=player.Defensive_Awareness,
        aggression=player.Aggression,
        interceptions=player.Interceptions,
        sprint_speed=player.Sprint_Speed,
        acceleration=player.Acceleration,
        composure=player.Composure,
        gk_handling=player.GK_Handling,
        gk_diving=player.GK_Diving,
        gk_positioning=player.GK_Positioning,
        gk_reflexes=player.GK_Reflexes,
        reactions=player.Reactions,
        ext_abilities=ext_abilities,
    )

    self.overall = compute_overall(self.player.Overall, self.star)
    self.price = compute_price(self.player.Overall, self.star, self.breach)

  def new(player, user, star=1, style=0, id=0, status=False, locked=False):
    if style == 0:
      if player.Position in GOALKEEPER:
        style = random.choice(list(GK_STYLE.keys()))
      else:
        style = random.choice(list(STYLE.keys()))
    return Card(id, player, user, star, style, status, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, locked, {}, 0)

  def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update cards set " + attr + " = '" + str(value) + "' where id = " + str(self.id))
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
            ext_abilities = json.loads(data[17]) if data[17] is not None else {}
            breach = data[18]
            card = Card(id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked, ext_abilities, breach)
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
              ext_abilities = json.loads(data[17]) if data[17] is not None else {}
              breach = data[18]
              card = Card(id, player, user, star, style, status, appearance, goal, assist, tackle, save, total_appearance, total_goal, total_assist, total_tackle, total_save, locked, ext_abilities, breach)
              cards.append(card)
        
        cursor.close()
        return cards

  def format(self):
    return self.player.Position.ljust(3) + " " + self.getNameWithColor() + " " + str(self.overall) + " " + STARS[self.star]["star"] + " ◆+" + str(self.breach) + " " + self.getStyle() + " " + self.printPrice() + " " + self.getStatus()

  def getStatus(self):
    if self.status != 0:
      s = " (" + STATUS[self.status] + ")"
    elif self.locked:
      s = " (已锁定)"
    else:
      s = ""
    return s

  def printID(self):
    if self.id == 0:
      return ""
    return "[" + str(self.id) + "]"

  def getStyle(self):
    return get_style_name(self.style, self.player.Position)

  def getNameWithColor(self):
    return get_name_with_color(self.player.Name, self.player.Overall, self.star)

  def tocm(height):
      h = height.split("'")
      foot = int(h[0])
      inch = int(h[1])
      return int((foot*12+inch)*2.54)

  def tokg(weight):
      w = int(weight.rstrip("lbs"))
      return int(0.453592*w)

  def getRealOverall(self, position):
    return compute_real_overall(self.ability, position)

  def printRealOverall(self, position):
    real = self.getRealOverall(position)
    diff = real - self.overall
    if diff > 0:
      return str(real) + "/~r▲" + str(diff) + "/"
    elif diff < 0:
      return str(real) + "/~g▼" + str(-diff) + "/"
    else:
      return str(real) + "/~w" + "　" + "/"

  def printPrice(self):
    return format_price(self.price)
  
  def formatPrice(price):
    return format_price(price)

  def getOveralls(self):
    tmp = []
    for position in REAL_ABILITY.keys():
      tmp.append((position, self.getRealOverall(position)))
    tmp.sort(key=lambda x: x[1], reverse=True)
    return tmp

  def remove(self):
    cursor = g_database.cursor()
    cursor.execute("delete from cards where id = " + str(self.id))
    cursor.close()
