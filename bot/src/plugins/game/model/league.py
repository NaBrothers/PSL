from game.model.user import User
from game.utils.database import *

class League:

  class Entry:
    def __init__(self, data: list):
      self.id = data[0]
      self.user = User.getUserByQQ(data[1])
      self.appearance = data[2]
      self.score = data[3]
      self.win = data[4]
      self.tie = data[5]
      self.lose = data[6]
      self.goal = data[7]
      self.lost_goal = data[8]

    def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update league set " + attr + " = " + str(value) + " where user = " + str(self.user.qq))
      cursor.close()

  def __init__(self, datas: list):
      self.entries = [League.Entry(data) for data in datas]
      self.entries.sort(key = lambda e: (-e.score, e.appearance, e.lost_goal - e.goal))

  def getLeague():
    cursor = g_database.cursor()
    count = cursor.execute("select * from league")
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return League(datas)

  def getLeagueEntryByQQ(qq):
    cursor = g_database.cursor()
    count = cursor.execute("select * from league where user = " + str(qq))
    data = cursor.fetchone()
    cursor.close()
    if count == 0:
      return None
    return League.Entry(data)

  def addUser(qq):
    cursor = g_database.cursor()
    cursor.execute("insert into league (user) values (" + str(qq) + ")")
    cursor.close()