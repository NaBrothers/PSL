import pymysql
import random

HOSTNAME="127.0.0.1"
USERNAME="navi"
PASSWORD="woshinaiwei"
DBNAME="bot"

#前锋位置
forward = ["ST","RW","RS","LW","CF","LS","LF","RF"]

#中场位置
middle = ["RM","LM","LCM","CM","CDM","CAM","RAM","RCM","LDM","LAM","RDM"]

#后卫位置
back = ["RB","CB","LB","RCB","RWB","LCB","LWB"]

#门将位置
goalkeeper = ["GK"]


def getPlayer_external(pos,min=0):
    if pos not in ["forward","middle","back","goalkeeper","前锋", "中场", "后卫", "门将"]:
        return "unkown position"
    if pos == "forward" or pos == "前锋":
        return getPlayer(min,forward)
    if pos == "middle" or pos == "中场":
        return getPlayer(min,middle)
    if pos == "back" or pos == "后卫":
        return getPlayer(min,back)
    if pos == "goalkeeper" or pos == "门将":
        return getPlayer(min,goalkeeper)

def getPlayer(min,positions):
    # 打开数据库连接
    db = pymysql.connect(HOSTNAME,USERNAME,PASSWORD,DBNAME )

    # 使用 cursor() 方法创建一个游标对象 cursor
    cursor = db.cursor()
    # 使用 execute()  方法执行 SQL 查询
    sqlstr = "SELECT Name,Overall,Position,Photo from players where ("
    for i in range(len(positions)):
        if i != 0:
            sqlstr += " OR "
        sqlstr += "Position='"
        sqlstr += positions[i]
        sqlstr += "'"
    sqlstr += ") AND Overall>="
    sqlstr += str(min)
    count = cursor.execute(sqlstr)
    index = random.randint(0,count-1)
    for i in range(index):
        result = cursor.fetchone()
    cursor.close()
    db.close()
    
    return str(result).strip('()')




