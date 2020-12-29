# 玩家信息
from game.utils.database import *


class User:
    def __init__(self, data: list):
        self.id = data[0]
        self.qq = data[1]
        self.name = data[2]
        self.level = data[3]

    def format(self):
        return str(self.qq) + " " + self.name + " " + str(self.level) + "级"

    def getUserByQQ(qq):
        cursor = g_database.cursor()
        count = cursor.execute("select * from users where qq = " + str(qq))
        if (count == 0):
            user = None
        else:
            user = User(cursor.fetchone())
        cursor.close()
        return user
