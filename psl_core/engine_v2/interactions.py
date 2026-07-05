"""Interaction detection and resolution for the 3-phase tick model.

Phase 2: Detect interactions between actions chosen by different players.
Phase 3: Resolve each interaction with probability-based outcomes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player
    from .config import EngineConfig


class InteractionType(Enum):
    DUEL = "duel"                 # attacker carry/dribble vs defender tackle
    INTERCEPTION = "interception" # pass path vs defender position
    BLOCK = "block"              # shot path vs defender position
    WASTED_TACKLE = "wasted"     # defender tackles but attacker already passed


class DuelOutcome(Enum):
    ATTACKER_WINS = "attacker_wins"   # dribble past, defender stunned
    DEFENDER_WINS = "defender_wins"   # clean tackle
    LOOSE_BALL = "loose_ball"         # ball goes free (CONTESTED)


@dataclass
class Interaction:
    interaction_type: InteractionType
    attacker: "Player"
    defender: "Player"
    distance: float


@dataclass
class DuelResult:
    outcome: DuelOutcome
    winner: Optional["Player"]
    loser: Optional["Player"]


def detect_duel(
    holder: "Player",
    holder_action_type: str,
    defenders: List["Player"],
    defender_actions: dict,
    config: "EngineConfig",
    defender_new_positions: dict = None,
) -> Optional[Interaction]:
    """Detect if a 1v1 duel should occur this tick.

    A duel happens when the carrier's path enters a defender's control area.
    Explicit tackle intent expands that control area, but is not required.
    """
    if holder_action_type not in ("carry", "dribble"):
        return None

    if defender_new_positions is None:
        defender_new_positions = {}

    for defender in defenders:
        action = defender_actions.get(defender.index)
        d_now = math.sqrt((holder.pos[0] - defender.pos[0]) ** 2 + (holder.pos[1] - defender.pos[1]) ** 2)
        new_pos = defender_new_positions.get(defender.index, defender.pos)
        d_next = math.sqrt((holder.pos[0] - new_pos[0]) ** 2 + (holder.pos[1] - new_pos[1]) ** 2)
        control_range = config.tackle_range * (1.0 if action == "tackle" else 0.06)
        d = min(d_now, d_next)
        if d < control_range:
            return Interaction(
                interaction_type=InteractionType.DUEL,
                attacker=holder,
                defender=defender,
                distance=d,
            )
    return None


def detect_wasted_tackle(
    holder: "Player",
    holder_action_type: str,
    defenders: List["Player"],
    defender_actions: dict,
    config: "EngineConfig",
) -> List[Interaction]:
    """Detect defenders who tackled but the attacker passed/shot (wasted)."""
    if holder_action_type in ("carry", "dribble"):
        return []

    wasted = []
    for defender in defenders:
        action = defender_actions.get(defender.index)
        if action != "tackle":
            continue
        d = math.sqrt((holder.pos[0] - defender.pos[0]) ** 2 + (holder.pos[1] - defender.pos[1]) ** 2)
        if d < config.tackle_range * 1.5:
            wasted.append(Interaction(
                interaction_type=InteractionType.WASTED_TACKLE,
                attacker=holder,
                defender=defender,
                distance=d,
            ))
    return wasted


def detect_interception(
    pass_origin: Tuple[float, float],
    pass_target: Tuple[float, float],
    defenders: List["Player"],
    defender_new_positions: dict,
    config: "EngineConfig",
) -> Optional[Interaction]:
    """Detect if a defender moved onto the pass path this tick.

    Only checks defenders whose movement this tick placed them
    near the pass trajectory.
    """
    # Pass vector
    dx = pass_target[0] - pass_origin[0]
    dy = pass_target[1] - pass_origin[1]
    pass_length = math.sqrt(dx * dx + dy * dy)
    if pass_length < 1.0:
        return None

    # Normalized direction
    nx, ny = dx / pass_length, dy / pass_length

    for defender in defenders:
        new_pos = defender_new_positions.get(defender.index, defender.pos)
        # Project defender position onto pass line
        px = new_pos[0] - pass_origin[0]
        py = new_pos[1] - pass_origin[1]
        proj = px * nx + py * ny  # projection along pass direction

        if proj < 2.0 or proj > pass_length - 2.0:
            continue  # defender is behind passer or beyond target

        # Perpendicular distance to pass line
        perp = abs(px * ny - py * nx)
        if perp < config.interception_reach:
            return Interaction(
                interaction_type=InteractionType.INTERCEPTION,
                attacker=None,
                defender=defender,
                distance=perp,
            )
    return None


def resolve_duel(interaction: Interaction, config: "EngineConfig") -> DuelResult:
    """Resolve a 1v1 duel between ball carrier and tackler."""
    attacker = interaction.attacker
    defender = interaction.defender

    atk_ability = attacker.abilities.get("Dribbling", 50)
    def_ability = defender.abilities.get("Tackling", 50)

    # Distance factor: gentle decay (close=full strength, at range edge=60%)
    dist_factor = max(0.6, 1.0 - interaction.distance / (config.tackle_range * 2.5))

    # Roll
    # Equal abilities should be 50/50 - no distance penalty in the roll itself
    atk_roll = atk_ability + random.uniform(-12, 12)
    def_roll = def_ability + random.uniform(-12, 12)

    diff = def_roll - atk_roll

    if diff > 8:
        return DuelResult(DuelOutcome.DEFENDER_WINS, winner=defender, loser=attacker)
    elif diff < -8:
        return DuelResult(DuelOutcome.ATTACKER_WINS, winner=attacker, loser=defender)
    else:
        return DuelResult(DuelOutcome.LOOSE_BALL, winner=None, loser=None)


def resolve_interception(
    interaction: Interaction,
    passer_ability: int,
    config: "EngineConfig",
) -> bool:
    """Resolve whether an interception succeeds. Returns True if intercepted."""
    defender = interaction.defender
    defence = defender.abilities.get("Defence", 50)

    # Interception chance based on Defence and proximity to pass line
    base_chance = defence / 200.0  # Defence=80 → 40% base
    proximity_factor = max(0.3, 1.0 - interaction.distance / config.interception_reach)

    # Passer ability reduces interception chance
    pass_quality = passer_ability / 150.0  # Passing=80 → 53% quality reduces interception

    final_chance = base_chance * proximity_factor * (1.0 - pass_quality * 0.4)
    final_chance = max(0.05, min(0.60, final_chance))

    return random.random() < final_chance
