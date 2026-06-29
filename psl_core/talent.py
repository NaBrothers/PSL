"""PSL Core Talent - pure talent generation and computation, no DB or IO."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

FIELD_TALENT_DIMS = [
    {"key": "shooting", "name": "射门", "abilities": ["Finishing", "Long_Shot", "Heading"]},
    {"key": "passing", "name": "传球", "abilities": ["Short_Passing", "Long_Passing"]},
    {"key": "dribbling", "name": "盘带", "abilities": ["Dribbling"]},
    {"key": "defending", "name": "防守", "abilities": ["Tackling", "Defence"]},
    {"key": "speed", "name": "速度", "abilities": ["Speed"]},
    {"key": "iq", "name": "球商", "abilities": ["IQ"]},
]

GK_TALENT_DIMS = [
    {"key": "saving", "name": "扑救", "abilities": ["GK_Saving"]},
    {"key": "positioning", "name": "站位", "abilities": ["GK_Positioning"]},
    {"key": "reaction", "name": "反应", "abilities": ["GK_Reaction"]},
    {"key": "speed", "name": "速度", "abilities": ["Speed"]},
    {"key": "passing", "name": "传球", "abilities": ["Short_Passing", "Long_Passing"]},
    {"key": "iq", "name": "球商", "abilities": ["IQ"]},
]

GRADE_THRESHOLDS = [
    ("SSS", 1.47),
    ("SS", 1.4),
    ("S", 1.3),
    ("A", 1.1),
    ("B", 0.9),
    ("C", 0.7),
    ("D", 0.0),
]

GRADE_COLORS = {
    "SSS": "$",
    "SS": "f",
    "S": "p",
    "A": "b",
    "B": "w",
    "C": "o",
    "D": "r",
}


def generate_talents(mean: float = 1.0, std: float = 0.2,
                     t_min: float = 0.5, t_max: float = 1.5,
                     rng: Optional[random.Random] = None) -> dict:
    r = rng or random
    talents = [round(max(t_min, min(t_max, r.gauss(mean, std))), 2) for _ in range(6)]
    order = list(range(6))
    r.shuffle(order)
    return {"t": talents, "o": order, "r": 1, "rc": 0}


def revealed_count_for_star(star: int) -> int:
    if star <= 0:
        return 0
    return min(star, 6)


def get_talent_grade(multiplier: float) -> str:
    for grade, threshold in GRADE_THRESHOLDS:
        if multiplier >= threshold:
            return grade
    return "D"


def get_talent_grade_color(grade: str) -> str:
    return GRADE_COLORS.get(grade, "w")


def get_average_grade(talents_data: dict, is_gk: bool = False, star: int = 10) -> Optional[str]:
    if not talents_data:
        return None
    revealed = revealed_count_for_star(star)
    if revealed == 0:
        return None
    order = talents_data["o"]
    multipliers = talents_data["t"]
    total = sum(multipliers[order[i]] for i in range(revealed))
    avg = total / revealed
    return get_talent_grade(avg)


def get_dims(is_gk: bool) -> list:
    return GK_TALENT_DIMS if is_gk else FIELD_TALENT_DIMS


def ability_to_talent_index(ability_key: str, is_gk: bool) -> int:
    dims = get_dims(is_gk)
    for i, dim in enumerate(dims):
        if ability_key in dim["abilities"]:
            return i
    return -1


def get_talent_multiplier_for_ability(ability_key: str, talents_data: dict,
                                       is_gk: bool, mode: str = "display",
                                       star: int = 10) -> float:
    if not talents_data:
        return 1.0
    dim_index = ability_to_talent_index(ability_key, is_gk)
    if dim_index < 0:
        return 1.0
    if mode == "engine":
        return talents_data["t"][dim_index]
    order = talents_data["o"]
    revealed = revealed_count_for_star(star)
    reveal_position = order.index(dim_index) if dim_index in order else -1
    if reveal_position < revealed:
        return talents_data["t"][dim_index]
    return 1.0


def format_talents_bot(talents_data: dict, is_gk: bool, star: int = 10) -> str:
    if not talents_data:
        return ""
    dims = get_dims(is_gk)
    revealed = revealed_count_for_star(star)
    order = talents_data["o"]
    parts = []
    hidden_count = 0
    for i in range(6):
        dim_idx = order[i]
        if i < revealed:
            mult = talents_data["t"][dim_idx]
            grade = get_talent_grade(mult)
            color = get_talent_grade_color(grade)
            parts.append(f"{dims[dim_idx]['name']}[/~{color}{grade}/]")
        else:
            hidden_count += 1
    if hidden_count > 0:
        parts.append(f"???×{hidden_count}")
    return f"天赋({revealed}/6): " + " ".join(parts)


def get_talent_display(talents_data: dict, is_gk: bool, star: int = 10) -> list:
    dims = get_dims(is_gk)
    revealed = revealed_count_for_star(star)
    order = talents_data["o"] if talents_data else list(range(6))
    revealed_set = set(order[i] for i in range(revealed)) if talents_data else set()
    result = []
    for dim_idx in range(6):
        dim = dims[dim_idx]
        if talents_data and dim_idx in revealed_set:
            mult = talents_data["t"][dim_idx]
            grade = get_talent_grade(mult)
            result.append({"name": dim["name"], "key": dim["key"], "grade": grade, "revealed": True})
        else:
            result.append({"name": dim["name"], "key": dim["key"], "grade": "?", "revealed": False})
    return result
