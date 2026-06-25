"""Formation constants shared by server services."""

FORWARD = ['ST', 'RW', 'RS', 'LW', 'CF', 'LS', 'LF', 'RF']
MIDFIELD = ['RM', 'LM', 'LCM', 'CM', 'CDM', 'CAM', 'RAM', 'RCM', 'LDM', 'LAM', 'RDM']
GUARD = ['RB', 'CB', 'LB', 'RCB', 'RWB', 'LCB', 'LWB']
GOALKEEPER = ['GK']

STARS = {
    1: {"ability": 0, "count": 1},
    2: {"ability": 1, "count": 2},
    3: {"ability": 2, "count": 3},
    4: {"ability": 4, "count": 5},
    5: {"ability": 6, "count": 8},
    6: {"ability": 8, "count": 13},
    7: {"ability": 11, "count": 21},
    8: {"ability": 14, "count": 34},
    9: {"ability": 17, "count": 55},
    10: {"ability": 21, "count": 89},
}

FORMATIONS = {
    "442": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "CF", "ST"]},
    "433": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "LCM", "CM", "RCM", "LW", "ST", "RW"]},
    "343": {"positions": ["GK", "LCB", "CB", "RCB", "LM", "LCM", "RCM", "RM", "LW", "ST", "RW"]},
    "4231": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "LDM", "RDM", "LM", "RM", "CAM", "ST"]},
    "352": {"positions": ["GK", "LCB", "CB", "RCB", "LDM", "RDM", "LM", "RM", "CAM", "CF", "ST"]},
    "532": {"positions": ["GK", "LB", "LCB", "CB", "RCB", "RB", "CDM", "LCM", "RCM", "CF", "ST"]},
    "4141": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "CDM", "LM", "LCM", "RCM", "RM", "ST"]},
    "451": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "CM", "RCM", "RM", "ST"]},
    "3421": {"positions": ["GK", "LCB", "CB", "RCB", "LM", "LCM", "RCM", "RM", "LAM", "RAM", "ST"]},
    "424": {"positions": ["GK", "LB", "LCB", "RCB", "RB", "LCM", "RCM", "LW", "CF", "ST", "RW"]},
}
