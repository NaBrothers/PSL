from game.model.player import *
from game.utils.database import *
from game.model.card import *
from game.model.user import *
import random

# 卡池基类
class Pool:
    def __init__(self):
      self.pool = []
      self.init()

    def init(self):
      pass

    def choice(self, user):
      player = random.choice(self.pool)
      card = Card.new(player, user)
      return card

# 普通卡池
class NormalPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players;")
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

# 巅峰卡池
class BestPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall > 88;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 至尊卡池
class NBPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))
    
    def choice(self,user):
        player = random.choice(self.pool)
        card = Card.new(player, user, random.randint(1,10))
        return card

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
        sqlstr += ");"
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
        sqlstr += ");"
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
        sqlstr += ");"
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
        sqlstr += ");"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 全局卡池
g_pool = {
  "普通" : {
    "pool": NormalPool(),
    "cost" : 10
  },
  "球星" : {
    "pool": BetterPool(),
    "cost" : 30
  },
  "巨星" : {
    "pool": VipPool(),
    "cost" : 50
  },
  "巅峰" : {
    "pool": BestPool(),
    "cost" : 100
  },
  "至尊" : {
    "pool": NBPool(),
    "cost" : 0
  },
  "前锋": {
    "pool": ForwardPool(),
    "cost" : 30
  },
  "中场": {
    "pool": MidfieldPool(),
    "cost" : 30
  },
  "后卫": {
    "pool": GuardPool(),
    "cost" : 30
  },
  "门将": {
    "pool": GoalkeeperPool(),
    "cost" : 30
  },
  "十连": {
    "pool": None,
    "cost" : 200
  },
  "新手": {
    "pool": None,
    "cost" : 0
  }
}