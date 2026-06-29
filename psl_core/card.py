"""PSL Core Card - pure card ability computation, no DB or IO."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from psl_core.constants import (
    STARS, STYLE, GK_STYLE, GOALKEEPER, REAL_ABILITY, POSITION_MAP, ABILITIES, GK_ABILITIES,
)
from psl_core.talent import get_talent_multiplier_for_ability


def compute_abilities(
    star: int,
    style: str,
    position: str,
    height: int,
    heading_accuracy: int,
    jumping: int,
    strength: int,
    long_shots: int,
    shot_power: int,
    finishing: int,
    long_passing: int,
    short_passing: int,
    dribbling: int,
    ball_control: int,
    balance: int,
    sliding_tackle: int,
    standing_tackle: int,
    defensive_awareness: int,
    aggression: int,
    interceptions: int,
    sprint_speed: int,
    acceleration: int,
    composure: int,
    gk_handling: int,
    gk_diving: int,
    gk_positioning: int,
    gk_reflexes: int,
    reactions: int,
    ext_abilities: Optional[Dict[str, int]] = None,
    talents: Optional[Dict] = None,
    talent_mode: str = "display",
) -> Dict[str, int]:
    base_star_bonus = STARS[star]["ability"]
    is_gk = position in GOALKEEPER

    def _bonus(ability_key: str) -> int:
        mult = get_talent_multiplier_for_ability(ability_key, talents, is_gk, talent_mode, star)
        return int(base_star_bonus * mult)

    ability = {
        "Heading": _bonus("Heading") + int((heading_accuracy + jumping + strength + height - 100) / 4),
        "Long_Shot": _bonus("Long_Shot") + int((long_shots + shot_power) / 2),
        "Finishing": _bonus("Finishing") + int((finishing * 2 + shot_power) / 3),
        "Long_Passing": _bonus("Long_Passing") + int(long_passing),
        "Short_Passing": _bonus("Short_Passing") + int(short_passing),
        "Dribbling": _bonus("Dribbling") + int((dribbling * 2 + ball_control * 2 + balance) / 5),
        "Tackling": _bonus("Tackling") + int((sliding_tackle + standing_tackle) / 2),
        "Defence": _bonus("Defence") + int((defensive_awareness * 2 + aggression + interceptions * 2) / 5),
        "Speed": _bonus("Speed") + int((sprint_speed + acceleration) / 2),
        "IQ": _bonus("IQ") + int(composure),
        "GK_Saving": _bonus("GK_Saving") + int((gk_handling + gk_diving) / 2),
        "GK_Positioning": _bonus("GK_Positioning") + int(gk_positioning),
        "GK_Reaction": _bonus("GK_Reaction") + int((gk_reflexes * 2 + reactions) / 3),
    }

    if ext_abilities:
        for key, val in ext_abilities.items():
            if key in ability:
                ability[key] += int(val)

    styles = GK_STYLE.get(style) if position in GOALKEEPER else STYLE.get(style)
    if styles:
        style_scale = STARS[star]["style_scale"]
        for key, bonus in styles.items():
            if key == "name":
                continue
            if key in ability:
                ability[key] += round(bonus * style_scale / 3)

    return ability


def compute_real_overall(abilities: Dict[str, int], position: str) -> int:
    mapped = POSITION_MAP.get(position, position)
    if mapped not in REAL_ABILITY:
        return 0
    total = 0.0
    for attr, weight in REAL_ABILITY[mapped].items():
        total += weight * abilities.get(attr, 0)
    return int(total)


def compute_overall(base_overall: int, star: int) -> int:
    return base_overall + STARS[star]["ability"]


def compute_price(base_overall: int, star: int, breach: int = 0) -> int:
    x = base_overall - 74 if base_overall >= 80 else 6
    base_price = int(0.0131*x**5 - 0.6118*x**4 + 11.189*x**3 - 55.238*x**2 + 123.16*x - 29.137)
    return base_price * STARS[star]["count"] + base_price * breach


def compute_all_position_ratings(abilities: Dict[str, int]) -> List[Dict]:
    ratings = []
    for pos_key, weights in REAL_ABILITY.items():
        total = 0.0
        for attr, weight in weights.items():
            total += weight * abilities.get(attr, 0)
        ratings.append({"position": pos_key, "rating": int(total)})
    ratings.sort(key=lambda x: x["rating"], reverse=True)
    return ratings


def get_color_code(base_overall: int, star: int) -> str:
    ov = star + base_overall - 1
    if ov >= 97:
        return "$"
    elif ov >= 94:
        return "f"
    elif ov >= 92:
        return "r"
    elif ov >= 89:
        return "o"
    elif ov >= 87:
        return "p"
    elif ov >= 84:
        return "b"
    elif ov >= 82:
        return "g"
    return "w"


def get_name_with_color(name: str, base_overall: int, star: int) -> str:
    code = get_color_code(base_overall, star)
    return f"/~{code}{name}/"


def get_style_name(style: str, position: str) -> str:
    styles = GK_STYLE.get(style) if position in GOALKEEPER else STYLE.get(style)
    return styles["name"] if styles else ""


def format_price(price: int) -> str:
    if price >= 1000000:
        return "$" + str(price // 10000) + "万"
    elif price >= 100000:
        return "$" + format(price / 10000, '.1f') + "万"
    elif price >= 10000:
        return "$" + format(price / 10000, '.2f') + "万"
    return "$" + str(price)


def position_group(pos: str) -> str:
    from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER as GK
    if pos in GK:
        return "GK"
    if pos in GUARD:
        return "D"
    if pos in FORWARD:
        return "F"
    return "M"
