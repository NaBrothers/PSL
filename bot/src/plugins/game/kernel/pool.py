from game.model.player import *
from game.utils.database import *
import random

# 卡池基类
class Pool:
    def __init__(self):
      self.pool = []
      self.init()

    def init(self):
      pass

    def choice(self):
      return random.choice(self.pool)

# 普通卡池
class NormalPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall >= 80;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 球星卡池
class BetterPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall > 83;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 巨星卡池
class VipPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall > 86;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 前锋卡池
class ForwardPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.FORWARD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.FORWARD[i]
            sqlstr += "'"
        sqlstr += ") AND Overall >= 80;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 中场卡池
class MidfieldPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.MIDFIELD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.MIDFIELD[i]
            sqlstr += "'"
        sqlstr += ") AND Overall >= 80;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 后卫卡池
class GuardPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.GUARD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.GUARD[i]
            sqlstr += "'"
        sqlstr += ") AND Overall >= 80;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))
# 门将卡池
class GoalkeeperPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.GOALKEEPER)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.GOALKEEPER[i]
            sqlstr += "'"
        sqlstr += ") AND Overall >= 80;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 全局卡池
g_pool = {
  "普通" : NormalPool(),
  "球星" : BetterPool(),
  "巨星" : VipPool(),
  "前锋": ForwardPool(),
  "中场": MidfieldPool(),
  "后卫": GuardPool(),
  "门将": GoalkeeperPool(),
  "十连": None
}