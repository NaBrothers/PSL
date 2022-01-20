from model.user import User
from utils.database import *
from utils.const import *
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

  # 如果存在item，加上count
  # 如果没有，添加新的item
  def addItem(user,type,item,num):
    tp = (0, user.qq, type, item, num)
    cursor = g_database.cursor()
    count = cursor.execute("select * from items where user = " + str(user.qq) + " and type = " + str(type) + " and item = " + str(item))
    if count == 0:
      cursor.execute("insert into items values " + str(tp))
    else:
      old_item = Item.Entry(cursor.fetchone())
      cursor.execute("update items set count = " + str(old_item.count + num) + " where id = " + str(old_item.id))
    cursor.close()