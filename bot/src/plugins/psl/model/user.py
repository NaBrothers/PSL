# 玩家信息
from utils.database import *
class User:
    def __init__(self, data: list):
        self.id = data[0]
        self.qq = data[1]
        self.name = data[2]
        self.level = data[3]
        self.money = data[4]
        self.formation = data[5]
        self.isAdmin = data[6]

    def format(self):
        return "[" + str(self.id) + "] " + self.name

    def getUserByQQ(qq):
        cursor = g_database.cursor()
        count = cursor.execute("select * from users where qq = " + str(qq))
        if (count == 0):
            user = None
        else:
            user = User(cursor.fetchone())
        cursor.close()
        return user
    
    def getUserById(id):
        cursor = g_database.cursor()
        count = cursor.execute("select * from users where ID = " + str(id))
        if (count == 0):
            user = None
        else:
            user = User(cursor.fetchone())
        cursor.close()
        return user

    def spend(self, cost):
        cursor = g_database.cursor()
        cursor.execute("update users set money = money - " + str(cost) + " where qq = " + str(self.qq))
        cursor.execute("select money from users where qq = " + str(self.qq))
        self.money = cursor.fetchone()[0]
        cursor.close()
    
    def earn(self, money):
        cursor = g_database.cursor()
        cursor.execute("update users set money = money + " + str(money) + " where qq = " + str(self.qq))
        cursor.execute("select money from users where qq = " + str(self.qq))
        self.money = cursor.fetchone()[0]
        cursor.close()

    def setFormation(self, formation):
        self.formation = formation
        g_database.update("update users set formation = " + formation + " where qq = " + str(self.qq))

    def addUser(qq, name):
        cursor = g_database.cursor()
        cursor.execute("insert into users (qq, name, level, money) values (" + str(qq) + ",'" + name + "',0, 0)")
        cursor.execute("select * from users where qq = " + str(qq))
        user = User(cursor.fetchone())
        cursor.close()
        return user

    def getAllUsers():
        users = []
        cursor = g_database.cursor()
        count = cursor.execute("select * from users;")
        ret = cursor.fetchall()
        for i in ret:
          users.append(User(i))
        cursor.close()
        return users
