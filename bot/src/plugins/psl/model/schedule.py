from model.user import User
from utils.database import *

class Schedule:

  class Entry:
    def __init__(self, data: list):
      self.id = data[0]
      self.round = data[1]
      self.home = User.getUserByQQ(data[2])
      self.away = User.getUserByQQ(data[3])
      self.finished = data[4]
      self.home_goal = data[5]
      self.away_goal = data[6]

    def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update schedule set " + attr + " = " + str(value) + " where id = " + str(self.id))
      cursor.close()

  def __init__(self, datas: list):
      self.entries = [Schedule.Entry(data) for data in datas]

  def getSchedule():
    cursor = g_database.cursor()
    count = cursor.execute("select * from schedule")
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return Schedule(datas)

  def getScheduleEntryByID(id):
    cursor = g_database.cursor()
    count = cursor.execute("select * from schedule where id = " + str(id))
    data = cursor.fetchone()
    cursor.close()
    if count == 0:
      return None
    return Schedule.Entry(data)

  def addEntry(data):
    cursor = g_database.cursor()
    cursor.execute("insert into schedule values " + str(data))
    cursor.close()

  def getCurrentRound():
    cursor = g_database.cursor()
    count = cursor.execute("select round from schedule where finished = false order by round")
    if count == 0:
      return None
    cur = cursor.fetchone()[0]
    count = cursor.execute("select * from schedule where round = " + str(cur))
    datas = cursor.fetchall()
    cursor.close()
    return Schedule(datas)

  def getCurrentEntry(user):
    cursor = g_database.cursor()
    count = cursor.execute("select round from schedule where finished = false order by round")
    if count == 0:
      return None
    cur = cursor.fetchone()[0]
    count = cursor.execute("select * from schedule where round = " + str(cur) + " and (home = " + str(user.qq) + " or away = " + str(user.qq) + ")")
    data = cursor.fetchone()
    cursor.close()
    entry = Schedule.Entry(data)
    return entry

  def getNumOfRounds(self):
    rounds = [entry.round for entry in self.entries]
    return max(rounds)

  def getRecentCondition(user, round):
    cursor = g_database.cursor()
    count = cursor.execute("SELECT * FROM schedule where (home = " + str(user.qq) + " or away = " + str(user.qq) + ") and finished = 1 order by id desc limit " + str(round))
    if count == 0:
          return ""
    datas = cursor.fetchall();
    cursor.close()
    res = []
    entries = [Schedule.Entry(data) for data in datas]
    for entry in entries:
          if entry.home.qq == user.qq and entry.home_goal > entry.away_goal or entry.away.qq == user.qq and entry.away_goal > entry.home_goal:
                res.append("/~r胜/")
          elif entry.home.qq == user.qq and entry.home_goal == entry.away_goal or entry.away.qq == user.qq and entry.away_goal == entry.home_goal:
                res.append("/~g平/")
          else:
                res.append("/~b负/")
    res.reverse();
    return "".join(res)