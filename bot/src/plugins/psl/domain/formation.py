"""Pure domain model for team formation - delegates to psl_core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from domain.card import CardData
from psl_core.formation import compute_formation_abilities


@dataclass
class FormationData:
    formation_type: str
    cards: List[Optional[CardData]]
    positions: List[str]
    coordinates: List[tuple]

    def is_valid(self) -> bool:
        return None not in self.cards

    def get_abilities(self) -> tuple:
        real_overalls = []
        for i, pos in enumerate(self.positions):
            card = self.cards[i] if i < len(self.cards) else None
            if card is None:
                real_overalls.append(None)
            else:
                real_overalls.append(card.get_real_overall(pos))
        return compute_formation_abilities(self.positions, real_overalls)
