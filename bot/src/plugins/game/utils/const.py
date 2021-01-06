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
                  "ability" : 0,
                  "cost" : 0
              },
              2: {"star" : "★×2",
                  "ability" : 1,
                  "cost" : 200
              },
              3: {"star" : "★×3",
                  "ability" : 2,
                  "cost" : 400
              },
              4: {"star" : "★×4",
                  "ability" : 4,
                  "cost" : 600
              },
              5: {"star" : "★×5",
                  "ability" : 6,
                  "cost" : 800
              },
              6: {"star" : "★×6",
                  "ability" : 8,
                  "cost" : 1000
              },
              7: {"star" : "★×7",
                  "ability" : 11,
                  "cost" : 1200
              },
              8: {"star" : "★×8",
                  "ability" : 14,
                  "cost" : 1400
              },
              9: {"star" : "★×9",
                  "ability" : 17,
                  "cost" : 1600
              },
              10: {"star" : "★×10",
                  "ability" : 21,
                  "cost" : 1800
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

    # GK特性
    GK_STYLE = {
      "bronzewall": {
        "name" : "铜墙",
          "GK_Saving" : 3,
          "Long_Passing" : 2
      },
      "ironwall": {
        "name" : "铁壁",
          "GK_Reaction" : 2,
          "Speed" : 2,
          "Long_Passing" : 2
      },
      "agilecat": {
        "name" : "灵猫",
          "GK_Reaction" : 2,
          "Speed" : 2,
          "GK_Positioning" : 2
      },
      "gloves": {
        "name" : "手套",
          "GK_Reaction" : 2,
          "GK_Saving" : 2,
          "Speed" : 2
      }
    }

    # 阵容
    FORMATION = {
      "442" : {
        "positions" : ["GK", "LB", "LCB", "RCB", "RB", "CDM", "LCM", "RCM", "CAM", "CF", "ST"],
        "coordinates" : [(34,100),(14,72),(28,80),(42,80),(56,72),(34,66),(22,52),(44,52),(34,36),(22,20),(44,20)]
      }
    }

    # 真实能力
    REAL_ABILITY = {
      "ST" : {
        "Heading" : 0.16,
        "Long_Shot" : 0.05,
        "Finishing" : 0.29,
        "Long_Passing" : 0,
        "Short_Passing" : 0.08,
        "Dribbling" : 0.27,
        "Tackling" : 0,
        "Defence" : 0,
        "Speed" : 0.15
      },
      "CF" : {
        "Heading" : 0.03,
        "Long_Shot" : 0.06,
        "Finishing" : 0.17,
        "Long_Passing" : 0,
        "Short_Passing" : 0.14,
        "Dribbling" : 0.45,
        "Tackling" : 0,
        "Defence" : 0,
        "Speed" : 0.15
      },
      "LRW" : {
        "Heading" : 0,
        "Long_Shot" : 0.06,
        "Finishing" : 0.15,
        "Long_Passing" : 0,
        "Short_Passing" : 0.14,
        "Dribbling" : 0.45,
        "Tackling" : 0,
        "Defence" : 0,
        "Speed" : 0.2
      },
      "LRM" : {
        "Heading" : 0,
        "Long_Shot" : 0.07,
        "Finishing" : 0.125,
        "Long_Passing" : 0.03,
        "Short_Passing" : 0.19,
        "Dribbling" : 0.435,
        "Tackling" : 0,
        "Defence" : 0,
        "Speed" : 0.15
      },
      "AM" : {
        "Heading" : 0,
        "Long_Shot" : 0.08,
        "Finishing" : 0.1,
        "Long_Passing" : 0.06,
        "Short_Passing" : 0.24,
        "Dribbling" : 0.42,
        "Tackling" : 0,
        "Defence" : 0,
        "Speed" : 0.1
      },
      "CM" : {
        "Heading" : 0,
        "Long_Shot" : 0.06,
        "Finishing" : 0.03,
        "Long_Passing" : 0.19,
        "Short_Passing" : 0.25,
        "Dribbling" : 0.31,
        "Tackling" : 0.07,
        "Defence" : 0.07,
        "Speed" : 0
      },
      "DM" : {
        "Heading" : 0,
        "Long_Shot" : 0,
        "Finishing" : 0,
        "Long_Passing" : 0.13,
        "Short_Passing" : 0.18,
        "Dribbling" : 0.13,
        "Tackling" : 0.22,
        "Defence" : 0.35,
        "Speed" : 0
      },
      "CB" : {
        "Heading" : 0.12,
        "Long_Shot" : 0,
        "Finishing" : 0,
        "Long_Passing" : 0,
        "Short_Passing" : 0.06,
        "Dribbling" : 0.05,
        "Tackling" : 0.33,
        "Defence" : 0.41,
        "Speed" : 0.02
      },
      "LRB" : {
        "Heading" : 0.05,
        "Long_Shot" : 0,
        "Finishing" : 0,
        "Long_Passing" : 0,
        "Short_Passing" : 0.09,
        "Dribbling" : 0.09,
        "Tackling" : 0.33,
        "Defence" : 0.27,
        "Speed" : 0.16
      },
      "GK" : {
        "GK_Saving" : 0.33,
        "GK_Reaction" : 0.33,
        "GK_Positioning" : 0.33,
      }
    }