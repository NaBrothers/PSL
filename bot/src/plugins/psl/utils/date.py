import time
from model.globalAttr import Global

class Date:
    def init():
      date = Date.getCurrentDate()
      Global.set("date", date)
      return date

    def getCurrentDate():
      date = time.localtime(time.time())
      date = str(date.tm_year) + "-" + str(date.tm_mon) + "-" + str(date.tm_mday)
      return date