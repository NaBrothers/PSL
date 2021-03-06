

class Const:
    # 球场长度
    LENGTH = 105

    # 球场宽度
    WIDTH = 68

    # 左门柱位置
    LEFT_GOALPOST = 30.385

    # 右门柱位置
    RIGHT_GOALPOST = 37.615

    # 球门宽度
    GOAL_WIDTH = 7.23

    # 角度对照表
    ANGLE = {
        0: "前",
        45: "右前",
        90: "右",
        135: "右后",
        180: "后",
        225: "左后",
        270: "左",
        315: "左前",
    }

    # 比赛动作间隔
    ACTION_DELAY = 30

    # 打印间隔
    PRINT_DELAY = 5

    # 比赛模式
    MODE_NORMAL = 0
    MODE_QUICK = 1
    MODE_LEAGUE = 2
    MODE_SILENCE = 3