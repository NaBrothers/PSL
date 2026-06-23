"""Pure domain model for team formation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from domain.card import CardData
from domain.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER


@dataclass
class FormationData:
    formation_type: str
    cards: List[Optional[CardData]]
    positions: List[str]
    coordinates: List[tuple]

    def is_valid(self) -> bool:
        return None not in self.cards

    def get_abilities(self) -> tuple:
        total = 0
        forward = 0
        midfield = 0
        guard = 0
        forward_count = 0
        midfield_count = 0
        guard_count = 0

        for i in range(len(self.positions)):
            pos = self.positions[i]
            if pos in FORWARD:
                forward_count += 1
            elif pos in MIDFIELD:
                midfield_count += 1
            elif pos in GUARD or pos in GOALKEEPER:
                guard_count += 1

            card = self.cards[i] if i < len(self.cards) else None
            if card is None:
                continue

            overall = card.get_real_overall(pos)
            total += overall
            if pos in FORWARD:
                forward += overall
            elif pos in MIDFIELD:
                midfield += overall
            elif pos in GUARD or pos in GOALKEEPER:
                guard += overall

        forward_count = max(forward_count, 1)
        midfield_count = max(midfield_count, 1)
        guard_count = max(guard_count, 1)
        return (total, forward // forward_count, midfield // midfield_count, guard // guard_count)
