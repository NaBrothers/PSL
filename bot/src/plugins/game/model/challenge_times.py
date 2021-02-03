from game.utils.database import *
from game.model.user import *
from game.model.globalAttr import Global
from game.utils.date import Date

class ChallengeTimes:
    def __init__(self, data):
        self.id = data[0]
        self.user = User.getUserByQQ(data[1])
        self.times = data[2]

    def getTimes(user):
        cursor = g_database.cursor()
        old_date = Global.get("date")
        cur_date = Date.getCurrentDate()
        if cur_date != old_date:
          Global.set("date", cur_date)
          cursor.execute("update challenge_times set timesleft = " + str(Const.TIMES_EVERYDAY))
        else:
          count = cursor.execute("select * from challenge_times where User = " + str(user.qq))
          if count == 0:
              cursor.execute("insert into challenge_times (User, TimesLeft) values (" + str(user.qq) + "," + str(Const.TIMES_EVERYDAY) + ")")
              cursor.execute("select * from challenge_times where User = " + str(user.qq))
        cursor.close()
        return ChallengeTimes(cursor.fetchone())

    def setTimes(self, times):
        cursor = g_database.cursor()
        count = cursor.execute("update challenge_times set timesleft = " + str(times) + " where id = " + str(self.id))
        cursor.close()