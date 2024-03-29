from model.user import User
from utils.database import *
from model.schedule import *

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
      self.condition = ""

    def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update league set " + attr + " = " + str(value) + " where user = " + str(self.user.qq))
      cursor.close()

  def __init__(self, datas: list):
      self.entries = [League.Entry(data) for data in datas]
      for entry in self.entries:
            entry.condition = Schedule.getRecentCondition(entry.user, 5)
      self.entries.sort(key = lambda e: (-e.score, e.appearance, e.lost_goal - e.goal))

  def getLeague():
    cursor = g_database.cursor()
    count = cursor.execute("select * from league where user <> 0")
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return League(datas)

  def getLeagueWithNull():
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

  def getCount():
    cursor = g_database.cursor()
    cursor.execute("select count(*) from league")
    count = cursor.fetchone()[0]
    cursor.close()
    return count

  def clear():
    cursor = g_database.cursor()
    cursor.execute("update cards set appearance = 0")
    cursor.execute("update cards set goal = 0")
    cursor.execute("update cards set assist = 0")
    cursor.execute("update cards set tackle = 0")
    cursor.execute("update cards set save = 0")
    cursor.execute("delete from schedule")
    cursor.execute("delete from league")
    cursor.close()