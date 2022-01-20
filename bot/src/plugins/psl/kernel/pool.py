from model.player import *
from utils.database import *
from model.card import *
from model.user import *
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

# 初级卡池
class ElementaryPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))



# 初级前锋卡池
class ElementaryForwardPool(Pool):
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

# 初级中场卡池
class ElementaryMidfieldPool(Pool):
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

# 初级后卫卡池
class ElementaryGuardPool(Pool):
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
# 初级门将卡池
class ElementaryGoalkeeperPool(Pool):
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

# 中级卡池
class IntermediatePool(Pool):
    def init(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall > 83;")
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 中级前锋卡池
class IntermediateForwardPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.FORWARD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.FORWARD[i]
            sqlstr += "'"
        sqlstr += ") and Overall > 83;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 中级中场卡池
class IntermediateMidfieldPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.MIDFIELD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.MIDFIELD[i]
            sqlstr += "'"
        sqlstr += ") and Overall > 83;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 中级后卫卡池
class IntermediateGuardPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.GUARD)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.GUARD[i]
            sqlstr += "'"
        sqlstr += ") and Overall > 83;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 中级门将卡池
class IntermediateGoalkeeperPool(Pool):
    def init(self):
        cursor = g_database.cursor()
        sqlstr = "SELECT * from players where ("
        for i in range(len(Const.GOALKEEPER)):
            if i != 0:
                sqlstr += " OR "
            sqlstr += "Position='"
            sqlstr += Const.GOALKEEPER[i]
            sqlstr += "'"
        sqlstr += ") and Overall > 83;"
        count = cursor.execute(sqlstr)
        result = cursor.fetchall()
        cursor.close()
        for i in range(count):
            self.pool.append(Player(result[i]))

# 高级卡池
class AdvancedPool(Pool):
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

# 全局卡池
g_pool = {
  "初级" : {
    "pool":  ElementaryPool(),
    "name" : "初级球员卡包",
    "cost" : 1000,
    "ten_cost" : 9500,
    "visible" : True
  },
  "初级前锋" : {
    "pool":  ElementaryForwardPool(),
    "name" : "初级前锋卡包",
    "cost" : 1500,
    "ten_cost" : 14250,
    "visible" : True
  },
  "初级中场" : {
    "pool":  ElementaryMidfieldPool(),
    "name" : "初级中场卡包",
    "cost" : 1500,
    "ten_cost" : 14250,
    "visible" : True
  },
  "初级后卫" : {
    "pool":  ElementaryGuardPool(),
    "name" : "初级后卫卡包",
    "cost" : 1500,
    "ten_cost" : 14250,
    "visible" : True
  },
  "初级门将" : {
    "pool":  ElementaryGoalkeeperPool(),
    "name" : "初级门将卡包",
    "cost" : 1750,
    "ten_cost" : 16625,
    "visible" : True
  },
  "中级" : {
    "pool":  IntermediatePool(),
    "name" : "中级球员卡包",
    "cost" : 2500,
    "ten_cost" : 23750,
    "visible" : True
  },
  "中级前锋" : {
    "pool":  IntermediateForwardPool(),
    "name" : "中级前锋卡包",
    "cost" : 3750,
    "visible" : True
  },
  "中级中场" : {
    "pool":  IntermediateMidfieldPool(),
    "name" : "中级中场卡包",
    "cost" : 3750,
    "visible" : True
  },
  "中级后卫" : {
    "pool":  IntermediateGuardPool(),
    "name" : "中级后卫卡包",
    "cost" : 3750,
    "visible" : True
  },
  "中级门将" : {
    "pool":  IntermediateGoalkeeperPool(),
    "name" : "中级门将卡包",
    "cost" : 5000,
    "visible" : True
  },
  "高级" : {
    "pool":  AdvancedPool(),
    "name" : "高级球员卡包",
    "cost" : 7500,
    "visible" : True
  },
  "巅峰" : {
    "pool":  BestPool(),
    "name" : "巅峰球员卡包",
    "cost" : 0,
    "visible" : False
  },
  "新手": {
    "pool": None,
    "name" : "新手限定卡包",
    "cost" : 0,
    "visible" : False,
    "info" : "二十张球员卡（前锋*6，中场*6，后卫*6，门将*2，至少一张能力值89以上）"
  },
  
}