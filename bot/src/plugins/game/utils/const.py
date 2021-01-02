# 常量

class Const:
    # 前锋位置
    FORWARD = ["ST", "RW", "RS", "LW", "CF", "LS", "LF", "RF"]

    # 中场位置
    MIDFIELD = ["RM", "LM", "LCM", "CM", "CDM",
                "CAM", "RAM", "RCM", "LDM", "LAM", "RDM"]

    # 后卫位置
    GUARD = ["RB", "CB", "LB", "RCB", "RWB", "LCB", "LWB"]

    # 门将位置
    GOALKEEPER = ["GK"]

    # 位置
    POSITIONS = ["前锋", "中场", "后卫", "门将"]

    # 星级
    STARS = { 1: {"star" : "★",
                  "ability" : 0
              },
              2: {"star" : "★×2",
                  "ability" : 1
              },
              3: {"star" : "★×3",
                  "ability" : 2
              },
              4: {"star" : "★×4",
                  "ability" : 4
              },
              5: {"star" : "★×5",
                  "ability" : 6
              },
              6: {"star" : "★×6",
                  "ability" : 8
              },
              7: {"star" : "★×7",
                  "ability" : 11
              },
              8: {"star" : "★×8",
                  "ability" : 14
              },
              9: {"star" : "★×9",
                  "ability" : 17
              },
              10: {"star" : "★×10",
                  "ability" : 21
              }
    }


    # 颜色
    COLOR = {"w": "gray",
             "g": "green",
             "b": "blue",
             "p": "#800080",
             "o": "orange",
             "r": "red",
             "f": "#FF69B4",
             "x": "#A52A2A"}

    # 状态
    STATUS = {0: "",
              1: "转会中",
              2: "比赛中"}

    # 特性
    STYLE = {
      "sniper": {
        "name" : "狙击手",
          "Dribbling" : 3,
          "Finishing" : 3
      },
      "finisher": {
        "name" : "终结者",
        "Finishing" : 3,
        "Heading" : 3
      },
      "deadeye": {
        "name" : "恶魔眼",
        "Short_Passing" : 3,
        "Long_Passing" : 3,
        "Finishing" : 3
      },
      "marksman": {
        "name" : "神枪手",
        "Dribbling" : 2,
        "Finishing" : 2,
        "Heading" : 2
      },
      "hawk": {
        "name" : "凤头鹰",
        "Speed" : 2,
        "Finishing" : 2,
        "Heading" : 2
      },
      "artist": {
        "name" : "艺术家",
        "Dribbling" : 3,
        "Short_Passing" : 3,
        "Long_Passing" : 3
      },
      "architect": {
        "name" : "建筑师",
        "Short_Passing" : 3,
        "Long_Passing" : 3,
        "Heading" : 3
      },
      "powerhous": {
        "name" : "抢球机器",
        "Tackling" : 3,
        "Defence" : 3
      },
      "maestro": {
        "name" : "大师",
        "Dribbling" : 2,
        "Short_Passing" : 2,
        "Long_Passing" : 2,
        "Finishing" : 2
      },
      "engine": {
        "name" : "发动机",
        "Dribbling" : 2,
        "Short_Passing" : 2,
        "Long_Passing" : 2,
        "Speed" : 2
      },
      "sentinal": {
        "name" : "哨兵",
        "Defence" : 3,
        "Heading" : 3
      },
      "guardian": {
        "name" : "护卫",
        "Defence" : 3,
        "Dribbling" : 3
      },
      "gladiator": {
        "name" : "斗士",
        "Finishing" : 3,
        "Defence" : 3
      },
      "backbone": {
        "name" : "骨干",
        "Defence" : 2,
        "Short_Passing" : 2,
        "Long_Passing" : 2,
        "Heading" : 2
      },
      "anchor": {
        "name" : "铁锚",
        "Speed" : 2,
        "Defence" : 2,
        "Heading" : 2
      },
      "hunter": {
        "name" : "狩猎者",
        "Finishing" : 3,
        "Speed" : 3
      },
      "catalyst": {
        "name" : "催化剂",
        "Short_Passing" : 3,
        "Long_Passing" : 3,
        "Speed" : 3
      },
      "shadow": {
        "name" : "暗影",
        "Finishing" : 3,
        "Defence" : 3
      },
      "speedster": {
        "name" : "疾速魔",
        "Speed" : 6
      },
      "slugger": {
        "name" : "重炮手",
        "Finishing" : 3,
        "Long_Shot" : 3
      }
    }