# 玩家信息

class User:
  def __init__(self, data: list):
    self.id = data[0]
    self.qq = data[1]
    self.name = data[2]
    self.level = data[3]

  def format(self):
    return str(self.qq) + " " + self.name + " " + str(self.level) + "级" 
