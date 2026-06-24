"""Pure domain constants - no DB or IO dependencies."""


FORWARD = ["ST", "RW", "RS", "LW", "CF", "LS", "LF", "RF"]
MIDFIELD = ["RM", "LM", "LCM", "CM", "CDM", "CAM", "RAM", "RCM", "LDM", "LAM", "RDM"]
GUARD = ["RB", "CB", "LB", "RCB", "RWB", "LCB", "LWB"]
GOALKEEPER = ["GK"]

STARS = {
    1: {"star": "★", "ability": 0, "cost": 0, "count": 1},
    2: {"star": "★×2", "ability": 1, "cost": 200, "count": 2},
    3: {"star": "★×3", "ability": 2, "cost": 400, "count": 3},
    4: {"star": "★×4", "ability": 4, "cost": 600, "count": 5},
    5: {"star": "★×5", "ability": 6, "cost": 800, "count": 8},
    6: {"star": "★×6", "ability": 8, "cost": 1000, "count": 13},
    7: {"star": "★×7", "ability": 11, "cost": 1200, "count": 21},
    8: {"star": "★×8", "ability": 14, "cost": 1400, "count": 34},
    9: {"star": "★×9", "ability": 17, "cost": 1600, "count": 55},
    10: {"star": "★×10", "ability": 21, "cost": 1800, "count": 89},
}

STYLE = {
    "sniper": {"name": "狙击手", "Dribbling": 3, "Finishing": 3},
    "finisher": {"name": "终结者", "Finishing": 3, "Heading": 3},
    "deadeye": {"name": "恶魔眼", "Short_Passing": 3, "Long_Passing": 3, "Finishing": 3},
    "marksman": {"name": "神枪手", "Dribbling": 2, "Finishing": 2, "Heading": 2},
    "hawk": {"name": "凤头鹰", "Speed": 2, "Finishing": 2, "Heading": 2},
    "artist": {"name": "艺术家", "Dribbling": 3, "Short_Passing": 3, "Long_Passing": 3},
    "architect": {"name": "建筑师", "Short_Passing": 3, "Long_Passing": 3, "Heading": 3},
    "powerhous": {"name": "抢球机器", "Tackling": 3, "Defence": 3},
    "maestro": {"name": "大师", "Dribbling": 2, "Short_Passing": 2, "Long_Passing": 2, "Finishing": 2},
    "engine": {"name": "发动机", "Dribbling": 2, "Short_Passing": 2, "Long_Passing": 2, "Speed": 2},
    "sentinal": {"name": "哨兵", "Defence": 3, "Heading": 3},
    "guardian": {"name": "护卫", "Tackling": 3, "Defence": 3, "Speed": 3},
    "anchor": {"name": "磐石", "Tackling": 3, "Defence": 3, "Heading": 3},
    "shadow": {"name": "暗影", "Tackling": 3, "Speed": 3},
    "hunter": {"name": "猎人", "Speed": 3, "Finishing": 3},
    "catalyst": {"name": "催化剂", "Speed": 3, "Short_Passing": 3, "Long_Passing": 3},
    "basic": {"name": "基础", "Dribbling": 1, "Short_Passing": 1, "Long_Passing": 1, "Speed": 1, "Finishing": 1, "Tackling": 1, "Defence": 1, "Heading": 1},
    "gladiator": {"name": "角斗士", "Tackling": 2, "Defence": 2, "Heading": 2, "Finishing": 2},
    "backbone": {"name": "支柱", "Tackling": 2, "Defence": 2, "Heading": 2, "Long_Passing": 2},
    "sniper2": {"name": "精确射手", "Finishing": 4, "Long_Shot": 4},
}

GK_STYLE = {
    "wall": {"name": "铁壁", "GK_Saving": 3, "GK_Reaction": 3},
    "shield": {"name": "盾牌", "GK_Saving": 3, "GK_Positioning": 3},
    "cat": {"name": "灵猫", "GK_Reaction": 3, "Speed": 3},
    "glove": {"name": "手套", "GK_Saving": 2, "GK_Positioning": 2, "GK_Reaction": 2},
}

COLOR = {
    "w": "gray",
    "g": "green",
    "b": "blue",
    "p": "#800080",
    "o": "orange",
    "r": "red",
    "f": "#FF69B4",
    "x": "#A52A2A",
}

REAL_ABILITY = {
    "ST": {"Finishing": 0.30, "Heading": 0.15, "Long_Shot": 0.10, "Dribbling": 0.15, "Speed": 0.20, "Short_Passing": 0.10},
    "CF": {"Finishing": 0.25, "Dribbling": 0.20, "Short_Passing": 0.20, "Speed": 0.15, "Heading": 0.10, "Long_Shot": 0.10},
    "LRW": {"Speed": 0.25, "Dribbling": 0.25, "Finishing": 0.20, "Short_Passing": 0.15, "Long_Passing": 0.15},
    "AM": {"Dribbling": 0.20, "Short_Passing": 0.25, "Finishing": 0.20, "Speed": 0.15, "Long_Passing": 0.10, "Long_Shot": 0.10},
    "LRM": {"Speed": 0.20, "Dribbling": 0.20, "Short_Passing": 0.20, "Long_Passing": 0.15, "Defence": 0.15, "Tackling": 0.10},
    "CM": {"Short_Passing": 0.25, "Long_Passing": 0.20, "Dribbling": 0.15, "Defence": 0.15, "Tackling": 0.15, "Speed": 0.10},
    "DM": {"Defence": 0.25, "Tackling": 0.25, "Short_Passing": 0.15, "Long_Passing": 0.15, "Heading": 0.10, "Speed": 0.10},
    "CB": {"Defence": 0.30, "Tackling": 0.25, "Heading": 0.20, "Speed": 0.15, "Long_Passing": 0.10},
    "LRB": {"Speed": 0.25, "Defence": 0.20, "Tackling": 0.20, "Short_Passing": 0.15, "Dribbling": 0.10, "Long_Passing": 0.10},
    "GK": {"GK_Saving": 0.35, "GK_Reaction": 0.30, "GK_Positioning": 0.25, "Speed": 0.05, "Long_Passing": 0.05},
}
