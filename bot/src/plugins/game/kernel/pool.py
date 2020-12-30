from game.model.player import *
from game.utils.database import *

# 卡池
class Pool:

    def __init__(self):
      # 普通卡池
      self.normal = Pool.init_normal()
      # 四五星卡池
      self.vip = Pool.init_vip()
      # 前锋卡池
      self.forward = Pool.init_forward()
      # 中场卡池
      self.midfield = Pool.init_midfield()
      # 后卫卡池
      self.guard = Pool.init_guard()
      # 门将卡池
      self.goalkeeper = Pool.init_goalkeeper()

    def init_normal():
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall >= 80;")
        result = cursor.fetchall()
        cursor.close()
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret

    def init_vip():
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where Overall >= 86;")
        result = cursor.fetchall()
        cursor.close()
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret

    def init_forward():
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
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret

    def init_midfield():
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
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret

    def init_guard():
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
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret


    def init_goalkeeper():
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
        ret = []
        for i in range(count):
            ret.append(Player(result[i]))
        return ret

# 全局卡池
g_pool = Pool()