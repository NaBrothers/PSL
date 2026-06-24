"""Pure domain model for a player card (ability calculation, pricing, color)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from domain.constants import STARS, STYLE, GK_STYLE, GOALKEEPER, REAL_ABILITY, COLOR
from domain.player import PlayerData


@dataclass
class CardData:
    id: int
    player: PlayerData
    user_qq: int
    star: int
    style: str
    status: int = 0
    appearance: int = 0
    goal: int = 0
    assist: int = 0
    tackle: int = 0
    save: int = 0
    total_appearance: int = 0
    total_goal: int = 0
    total_assist: int = 0
    total_tackle: int = 0
    total_save: int = 0
    locked: bool = False
    ext_abilities: Dict[str, int] = field(default_factory=dict)
    breach: int = 0

    def __post_init__(self):
        self._ability: Optional[Dict[str, int]] = None

    @property
    def ability(self) -> Dict[str, int]:
        if self._ability is not None:
            return self._ability
        self._ability = self._compute_ability()
        return self._ability

    @property
    def overall(self) -> int:
        return self.player.overall + STARS[self.star]["ability"]

    @property
    def price(self) -> int:
        return self.player.price * STARS[self.star]["count"] + self.player.price * self.breach

    def invalidate_ability_cache(self):
        self._ability = None

    def _compute_ability(self) -> Dict[str, int]:
        p = self.player
        star_bonus = STARS[self.star]["ability"]
        height_val = int(p.height) if p.height.isdigit() else 170
        ability = {
            "Heading": star_bonus + int((p.heading_accuracy + p.jumping + p.strength + height_val - 100) / 4),
            "Long_Shot": star_bonus + int((p.long_shots + p.shot_power) / 2),
            "Finishing": star_bonus + int((p.finishing * 2 + p.shot_power) / 3),
            "Long_Passing": star_bonus + int(p.long_passing),
            "Short_Passing": star_bonus + int(p.short_passing),
            "Dribbling": star_bonus + int((p.dribbling * 2 + p.ball_control * 2 + p.balance) / 5),
            "Tackling": star_bonus + int((p.sliding_tackle + p.standing_tackle) / 2),
            "Defence": star_bonus + int((p.defensive_awareness * 2 + p.aggression + p.interceptions * 2) / 5),
            "Speed": star_bonus + int((p.sprint_speed + p.acceleration) / 2),
            "IQ": star_bonus + int(p.composure),
            "GK_Saving": star_bonus + int((p.gk_handling + p.gk_diving) / 2),
            "GK_Positioning": star_bonus + int(p.gk_positioning),
            "GK_Reaction": star_bonus + int((p.gk_reflexes * 2 + p.reactions) / 3),
        }

        for key, val in self.ext_abilities.items():
            if key in ability:
                ability[key] += int(val)

        styles = GK_STYLE.get(self.style) if p.position in GOALKEEPER else STYLE.get(self.style)
        if styles:
            for key, bonus in styles.items():
                if key == "name":
                    continue
                if key in ability:
                    ability[key] += bonus * self.star

        return ability

    def get_real_overall(self, position: str) -> int:
        pos_map = {
            "ST": "ST", "RS": "ST", "LS": "ST",
            "CF": "CF", "LF": "CF", "RF": "CF",
            "RW": "LRW", "LW": "LRW",
            "CAM": "AM", "RAM": "AM", "LAM": "AM",
            "LM": "LRM", "RM": "LRM",
            "CM": "CM", "RCM": "CM", "LCM": "CM",
            "CDM": "DM", "RDM": "DM", "LDM": "DM",
            "CB": "CB", "RCB": "CB", "LCB": "CB",
            "LB": "LRB", "LWB": "LRB", "RB": "LRB", "RWB": "LRB",
            "GK": "GK",
        }
        mapped = pos_map.get(position, position)
        if mapped not in REAL_ABILITY:
            return self.overall
        total = 0.0
        for attr, weight in REAL_ABILITY[mapped].items():
            total += weight * self.ability.get(attr, 0)
        return int(total)

    def get_name_with_color(self) -> str:
        ov = self.star + self.player.overall - 1
        if ov >= 97:
            code = "$"
        elif ov >= 94:
            code = "f"
        elif ov >= 92:
            code = "r"
        elif ov >= 89:
            code = "o"
        elif ov >= 87:
            code = "p"
        elif ov >= 84:
            code = "b"
        elif ov >= 82:
            code = "g"
        else:
            code = "w"
        return f"/~{code}{self.player.name}/"

    def get_style_name(self) -> str:
        styles = GK_STYLE.get(self.style) if self.player.position in GOALKEEPER else STYLE.get(self.style)
        return styles["name"] if styles else ""

    def format_price(self) -> str:
        price = self.price
        if price >= 1000000:
            return "$" + str(price // 10000) + "万"
        elif price >= 100000:
            return "$" + format(price / 10000, '.1f') + "万"
        elif price >= 10000:
            return "$" + format(price / 10000, '.2f') + "万"
        return "$" + str(price)
