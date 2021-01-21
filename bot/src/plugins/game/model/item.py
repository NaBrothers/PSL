from game.model.user import User
from game.utils.database import *
from game.utils.const import *
class Item:

  class Entry:
    def __init__(self, data: list):
      self.id = data[0]
      self.user = User.getUserByQQ(data[1])
      self.type = data[2]
      self.item = data[3]
      self.count = data[4]
      self.name = Const.ITEM[self.type]["item"][self.item]["name"]

    def set(self, attr, value):
      setattr(self, attr, value)
      cursor = g_database.cursor()
      count = cursor.execute("update items set " + attr + " = " + str(value) + " where id = " + str(self.id))
      cursor.close()

    def remove(self):
      cursor = g_database.cursor()
      count = cursor.execute("delete from items where id = " + str(self.id))
      cursor.close()

  def __init__(self, datas: list):
      self.entries = [Item.Entry(data) for data in datas]

  def getItems():
    cursor = g_database.cursor()
    count = cursor.execute("select * from items")
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return Item(datas)

  def getItemsByQQ(qq):
    cursor = g_database.cursor()
    count = cursor.execute("select * from items where user = " + str(qq))
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return Item(datas)

  def getItemsByQQandType(qq, type):
    cursor = g_database.cursor()
    count = cursor.execute("select * from items where user = " + str(qq) + " and type = " + str(type))
    datas = cursor.fetchall()
    cursor.close()
    if count == 0:
      return None
    return Item(datas)

  def addItem(qq,type,item,count):
    tp = (0, qq, type, item, count)
    cursor = g_database.cursor()
    cursor.execute("insert into items values " + str(tp))
    cursor.close()