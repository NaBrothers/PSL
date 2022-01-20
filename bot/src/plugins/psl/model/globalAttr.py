from utils.database import *

class Global:

  def get(name, default = 0):
    cursor = g_database.cursor()
    count = cursor.execute("select value from global where name = \'" + name + "\'")
    if count == 0:
      count = cursor.execute("insert into global (name, value) values (\'" + name + "\', \'" + str(default) + "\')")
      count = cursor.execute("select value from global where name = \'" + name + "\'")
    ret = cursor.fetchone()[0]
    cursor.close()
    if ret.isdecimal():
      return int(ret)
    return ret

  def set(name, value):
    cursor = g_database.cursor()
    count = cursor.execute("select value from global where name = \'" + name + "\'")
    if count == 0:
      count = cursor.execute("insert into global (name, value) values (\'" + name + "\', \'" + str(value) + "\')")
    else:
      count = cursor.execute("update global set value = \'" + str(value) + "\' where name = \'" + name + "\'")
    cursor.close()