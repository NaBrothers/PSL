from game.utils.database import *

class Global:

  def get(name, default = None):
    cursor = g_database.cursor()
    count = cursor.execute("select value from global where name = " + name)
    if count == 0:
      count = cursor.execute("insert into global values (" + name + ", " + str(default) + ")")
      count = cursor.execute("select value from global where name = " + name)
    ret = cursor.fetchone()[0]
    cursor.close()
    return ret

  def set(name, value):
    cursor = g_database.cursor()
    count = cursor.execute("update global set value = " + str(value) + " where name = " + name)
    cursor.close()