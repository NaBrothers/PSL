from game.utils.database import *
from game.utils.const import *


class Player:

    # 输入一个数据库游标返回的结果
    # 输出一个Player对象
    def __init__(self, data: list):
        self.PrimaryID = data[0]
        self.ID = data[1]
        self.Name = data[2]
        self.Age = data[3]
        self.Photo = data[4]
        self.Nationality = data[5]
        self.Flag = data[6]
        self.Overall = data[7]
        self.Potential = data[8]
        self.Club = data[9]
        self.Club_Logo = data[10]
        self.Value = data[11]
        self.Wage = data[12]
        self.Special = data[13]
        self.Preferred_Foot = data[14]
        self.Weak_Foot = data[15]
        self.Skill_Moves = data[16]
        self.International_Reputation = data[17]
        self.Work_Rate = data[18]
        self.Body_Type = data[19]
        self.Real_Face = data[20]
        self.Release_Clause = data[21]
        self.Position = data[22]
        self.Jersey_Number = data[23]
        self.Height = data[24]
        self.Weigh = data[25]
        self.LS = data[26]
        self.ST = data[27]
        self.RS = data[28]
        self.LW = data[29]
        self.LF = data[30]
        self.CF = data[31]
        self.RF = data[32]
        self.RW = data[33]
        self.LAM = data[34]
        self.CAM = data[35]
        self.RAM = data[36]
        self.LM = data[37]
        self.LCM = data[38]
        self.CM = data[39]
        self.RCM = data[40]
        self.RM = data[41]
        self.LWB = data[42]
        self.LDM = data[43]
        self.CDM = data[44]
        self.RDM = data[45]
        self.RWB = data[46]
        self.LB = data[47]
        self.LCB = data[48]
        self.CB = data[49]
        self.RCB = data[50]
        self.RB = data[51]
        self.GK = data[52]
        self.Likes = data[53]
        self.Dislikes = data[54]
        self.Following = data[55]
        self.Crossing = data[56]
        self.Finishing = data[57]
        self.Heading_Accuracy = data[58]
        self.Short_Passing = data[59]
        self.Volleys = data[60]
        self.Dribbling = data[61]
        self.Curve = data[62]
        self.FK_Accuracy = data[63]
        self.Long_Passing = data[64]
        self.Ball_Control = data[65]
        self.Acceleration = data[66]
        self.Sprint_Speed = data[67]
        self.Agility = data[68]
        self.Reactions = data[69]
        self.Balance = data[70]
        self.Shot_Power = data[71]
        self.Jumping = data[72]
        self.Stamina = data[73]
        self.Strength = data[74]
        self.Long_Shots = data[75]
        self.Aggression = data[76]
        self.Interceptions = data[77]
        self.Positioning = data[78]
        self.Vision = data[79]
        self.Penalties = data[80]
        self.Composure = data[81]
        self.Defensive_Awareness = data[82]
        self.Standing_Tackle = data[83]
        self.Sliding_Tackle = data[84]
        self.GK_Diving = data[85]
        self.GK_Handling = data[86]
        self.GK_Kicking = data[87]
        self.GK_Positioning = data[88]
        self.GK_Reflexes = data[89]

    # 返回一个格式化字符串
    def format(self):
        if not PICTURE_MODE:
            return self.Name+" (" + Const.STARS[self.Overall][0] + ") "+str(self.Overall)+" "+self.Position+" "
        else:
            return Const.STARS[self.Overall][1] + self.Name + "/ " + str(self.Overall)+" "+self.Position+" "


    def getPlayerByID(id):
        cursor = g_database.cursor()
        count = cursor.execute("select * from players where id = " + str(id))
        if (count == 0):
            player = None
        else:
            player = Player(cursor.fetchone())
        cursor.close()
        return player

    def getPlayerByIDMany(ids: list):
        cursor = g_database.cursor()
        sql = "select * from players where id in ("
        for id in ids:
            sql += str(id)+","
        sql += "-1)"
        count = cursor.execute(sql)
        if (count == 0):
            players = []
        else:
            data = cursor.fetchall()
            id2player = {}
            for line in data:
              player = Player(line)
              id2player[player.ID] = player
            players = [id2player[i] for i in ids]
        cursor.close()

        return players
