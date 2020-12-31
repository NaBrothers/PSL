# 玩家信息
from game.utils.database import *
from game.model.bag import Bag

class User:
    def __init__(self, data: list):
        self.id = data[0]
        self.qq = data[1]
        self.name = data[2]
        self.level = data[3]
        self.money = data[4]
        self.isFirst = data[5]

    def format(self):
        return str(self.qq) + " " + self.name + " " + str(self.level) + "级\n" + "球币：" + str(self.money)

    def getUserByQQ(qq):
        cursor = g_database.cursor()
        count = cursor.execute("select * from users where qq = " + str(qq))
        if (count == 0):
            user = None
        else:
            user = User(cursor.fetchone())
        cursor.close()
        return user

    def spend(self, cost):
        self.money -= cost
        g_database.update("update users set money = " + str(self.money) + " where qq = " + str(self.qq))
    
    def earn(self, money):
        self.money += money
        g_database.update("update users set money = " + str(self.money) + " where qq = " + str(self.qq))

    def setIsFirst(self, isFirst):
        self.isFirst = isFirst
        g_database.update("update users set isfirst = " + isFirst + " where qq = " + str(self.qq))

    def getBag(self):
        cursor = g_database.cursor()
        count = cursor.execute("select * from cards where user = " + str(self.qq))
        if (count == 0):
            bag = None
        else:
            bag = Bag(cursor.fetchall())
        cursor.close()
        return bag

    def addToBag(self, card):
      g_database.update("insert into cards (user, player, star, style) values (" + str(self.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")

    def addToBagMany(self, cards:list):
      cursor = g_database.cursor()
      for card in cards:
        g_database.update("insert into cards (user, player, star, style) values (" + str(self.qq) + "," + str(card.player.ID)+ "," + str(card.star) + ",\"" + card.style +"\")")
      cursor.close()
