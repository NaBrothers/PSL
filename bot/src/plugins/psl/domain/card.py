"""Pure domain model for a player card - delegates to psl_core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from domain.constants import STARS, STYLE, GK_STYLE, GOALKEEPER, REAL_ABILITY
from domain.player import PlayerData
from psl_core.card import (
    compute_abilities, compute_real_overall, compute_overall,
    compute_price, get_name_with_color, get_style_name, format_price,
    compute_all_position_ratings,
)


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
        return compute_overall(self.player.overall, self.star)

    @property
    def price(self) -> int:
        return compute_price(self.player.overall, self.star, self.breach)

    def invalidate_ability_cache(self):
        self._ability = None

    def _compute_ability(self) -> Dict[str, int]:
        p = self.player
        height_val = int(p.height) if p.height.isdigit() else 170
        return compute_abilities(
            star=self.star,
            style=self.style,
            position=p.position,
            height=height_val,
            heading_accuracy=p.heading_accuracy,
            jumping=p.jumping,
            strength=p.strength,
            long_shots=p.long_shots,
            shot_power=p.shot_power,
            finishing=p.finishing,
            long_passing=p.long_passing,
            short_passing=p.short_passing,
            dribbling=p.dribbling,
            ball_control=p.ball_control,
            balance=p.balance,
            sliding_tackle=p.sliding_tackle,
            standing_tackle=p.standing_tackle,
            defensive_awareness=p.defensive_awareness,
            aggression=p.aggression,
            interceptions=p.interceptions,
            sprint_speed=p.sprint_speed,
            acceleration=p.acceleration,
            composure=p.composure,
            gk_handling=p.gk_handling,
            gk_diving=p.gk_diving,
            gk_positioning=p.gk_positioning,
            gk_reflexes=p.gk_reflexes,
            reactions=p.reactions,
            ext_abilities=self.ext_abilities,
        )

    def get_real_overall(self, position: str) -> int:
        return compute_real_overall(self.ability, position)

    def get_name_with_color(self) -> str:
        return get_name_with_color(self.player.name, self.player.overall, self.star)

    def get_style_name(self) -> str:
        return get_style_name(self.style, self.player.position)

    def format_price(self) -> str:
        return format_price(self.price)
