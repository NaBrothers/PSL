"""Team model: manages a squad of 11 players with formation dynamics (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .player import Player, PlayerState
from .physics import distance

if TYPE_CHECKING:
    from .config import EngineConfig
    from .pitch import Pitch


class TeamPhase(Enum):
    """Team phase state for tactical decisions."""
    ATTACKING = "attacking"
    TRANSITION_ATK = "transition_atk"  # just won ball (< N ticks)
    DEFENDING = "defending"
    TRANSITION_DEF = "transition_def"  # just lost ball (< N ticks)
    CONTESTING = "contesting"  # ball is contested


@dataclass
class Team:
    """A team of 11 players in the match."""

    side: str  # "home" or "away"
    name: str
    formation: str  # e.g. "442"
    players: List[Player] = field(default_factory=list)
    attacking_right: bool = True  # direction of attack

    # Cached formation coordinates (pitch coords) - base positions
    _formation_coords: List[Tuple[float, float]] = field(default_factory=list)

    # Phase 2: Team phase state
    phase: TeamPhase = TeamPhase.DEFENDING
    _ticks_since_possession_change: int = 99  # large = stable
    _had_possession_last_tick: bool = False

    @property
    def goalkeeper(self) -> Player:
        return self.players[0]

    @property
    def phase_name(self) -> str:
        """Get phase name string for scoring framework."""
        return self.phase.value

    def setup_formation(self, pitch: "Pitch", formation_data: Dict):
        """Position players according to formation.

        Args:
            pitch: Pitch object for coordinate conversion
            formation_data: dict with "coordinates" list of (x, y) percentage tuples
        """
        coords = formation_data.get("coordinates", [])
        if len(coords) != 11:
            raise ValueError(f"Formation must have 11 coordinates, got {len(coords)}")

        self._formation_coords = []
        for i, coord in enumerate(coords):
            pitch_pos = pitch.formation_to_pitch(coord, self.attacking_right)
            self._formation_coords.append(pitch_pos)
            self.players[i].formation_pos = pitch_pos
            self.players[i].pos = pitch_pos
            self.players[i].target_pos = pitch_pos

    def flip_direction(self, pitch: "Pitch", formation_data: Dict):
        """Flip attacking direction (for second half)."""
        self.attacking_right = not self.attacking_right
        self.setup_formation(pitch, formation_data)

    def update_phase(self, has_possession: bool, ball_contested: bool, config: "EngineConfig"):
        """Update team phase based on possession state.

        Phase transitions:
        - CONTESTED ball -> CONTESTING
        - Just won ball (within transition_ticks) -> TRANSITION_ATK
        - Just lost ball (within transition_ticks) -> TRANSITION_DEF
        - Stable possession -> ATTACKING
        - Stable no possession -> DEFENDING
        """
        if ball_contested:
            self.phase = TeamPhase.CONTESTING
            return

        # Detect possession change
        if has_possession != self._had_possession_last_tick:
            self._ticks_since_possession_change = 0
        else:
            self._ticks_since_possession_change += 1

        self._had_possession_last_tick = has_possession

        # Determine phase
        if has_possession:
            if self._ticks_since_possession_change < config.transition_ticks:
                self.phase = TeamPhase.TRANSITION_ATK
            else:
                self.phase = TeamPhase.ATTACKING
        else:
            if self._ticks_since_possession_change < config.transition_ticks:
                self.phase = TeamPhase.TRANSITION_DEF
            else:
                self.phase = TeamPhase.DEFENDING

    def compute_dynamic_positions(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        opponent_players: list = None,
    ):
        """Set formation_pos to the static initial position from formation coordinates.

        The dynamic three-line computation has been removed. Formation positioning
        is now purely driven by position_value scoring (role_distance_decay provides
        the soft pull toward base formation area). This method retains the signature
        for backward compatibility but only ensures formation_pos is set from the
        static base coordinates established in __init__/setup_formation.
        """
        # formation_pos is already set from setup_formation / __init__.
        # This method is now a no-op; the static base position is the anchor
        # and all dynamic positioning emerges from PV-driven off-ball decisions.
        pass

    def get_closest_to(
        self,
        pos: Tuple[float, float],
        exclude_gk: bool = False,
        exclude_indices: Optional[List[int]] = None,
    ) -> Optional[Player]:
        """Find the closest player to a position."""
        best = None
        best_dist = float("inf")
        for p in self.players:
            if exclude_gk and p.is_goalkeeper:
                continue
            if exclude_indices and p.index in exclude_indices:
                continue
            d = distance(p.pos, pos)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def get_players_in_radius(
        self, pos: Tuple[float, float], radius: float
    ) -> List[Player]:
        """Get all players within a radius of a position."""
        return [p for p in self.players if distance(p.pos, pos) < radius]

    def update_off_ball(
        self,
        ball_pos: Tuple[float, float],
        has_possession: bool,
        config: "EngineConfig",
        pitch: "Pitch",
        ball_carrier: Optional[Player] = None,
        opponents: Optional[List[Player]] = None,
    ):
        """Update all off-ball players' targets using Phase 2 intelligent AI."""
        # Dynamic three-line computation removed; formation_pos is static from setup.
        # Off-ball positioning is now purely PV-driven.

        for player in self.players:
            if player.state == PlayerState.ON_BALL:
                continue

            if has_possession:
                player.state = PlayerState.OFF_BALL
                player.decide_off_ball_attacking_v2(
                    ball_pos, config, pitch, self.attacking_right,
                    ball_carrier=ball_carrier,
                    opponents=opponents or [],
                    teammates=self.players,
                )
            else:
                player.state = PlayerState.OFF_BALL
                player.decide_off_ball_defending_v2(
                    ball_pos, config, pitch, self.attacking_right,
                    opponents=opponents or [],
                )

    def assign_pressers(
        self, ball_carrier_pos: Tuple[float, float], config: "EngineConfig", pitch: "Pitch"
    ):
        """Assign one closest non-GK player to press the ball carrier."""
        # Clear all presser flags first
        for p in self.players:
            p._is_designated_presser = False
        
        # Find closest eligible presser
        candidates = []
        for p in self.players:
            if p.is_goalkeeper or p.state == PlayerState.ON_BALL:
                continue
            d = distance(p.pos, ball_carrier_pos)
            if d < config.press_radius * 2:
                candidates.append((d, p))

        candidates.sort(key=lambda x: x[0])

        # Only the closest player is designated presser
        if candidates:
            candidates[0][1]._is_designated_presser = True
            candidates[0][1].decide_press(ball_carrier_pos, config, pitch)

    # Keep backward compatibility
    def assign_presser(
        self, ball_carrier_pos: Tuple[float, float], config: "EngineConfig", pitch: "Pitch"
    ):
        """Assign the closest non-GK player to press the ball carrier."""
        self.assign_pressers(ball_carrier_pos, config, pitch)

    def move_all(self, config: "EngineConfig", pitch: "Pitch"):
        """Move all players one tick."""
        for player in self.players:
            player.move_tick(config, pitch)

    def get_stats(self) -> Dict:
        """Aggregate team statistics."""
        stats = {
            "shots": sum(p.shots for p in self.players),
            "shots_on_target": sum(p.shots_on_target for p in self.players),
            "passes": sum(p.passes_attempted for p in self.players),
            "passes_completed": sum(p.passes_completed for p in self.players),
            "pass_success_rate": 0.0,
            "tackles": sum(p.tackles_attempted for p in self.players),
            "tackles_won": sum(p.tackles_won for p in self.players),
            "interceptions": sum(p.interceptions for p in self.players),
            "dribbles": sum(p.dribbles_attempted for p in self.players),
            "dribbles_completed": sum(p.dribbles_completed for p in self.players),
            "saves": sum(p.saves for p in self.players),
            "goals": sum(p.goals for p in self.players),
            "distance_covered": sum(p.distance_covered for p in self.players),
            # Phase 2 stats
            "carries": sum(p.carries_attempted for p in self.players),
            "carries_completed": sum(p.carries_completed for p in self.players),
            "crosses": sum(p.crosses_attempted for p in self.players),
            "crosses_completed": sum(p.crosses_completed for p in self.players),
            "headers": sum(p.headers_attempted for p in self.players),
            "headers_won": sum(p.headers_won for p in self.players),
        }
        if stats["passes"] > 0:
            stats["pass_success_rate"] = round(
                stats["passes_completed"] / stats["passes"] * 100, 1
            )
        return stats

    def get_player_stats(self) -> List[Dict]:
        """Get per-player statistics."""
        result = []
        for p in self.players:
            result.append({
                "name": p.name,
                "position": p.position,
                "goals": p.goals,
                "assists": p.assists,
                "shots": p.shots,
                "shots_on_target": p.shots_on_target,
                "passes_attempted": p.passes_attempted,
                "passes_completed": p.passes_completed,
                "tackles_attempted": p.tackles_attempted,
                "tackles_won": p.tackles_won,
                "dribbles_attempted": p.dribbles_attempted,
                "dribbles_completed": p.dribbles_completed,
                "interceptions": p.interceptions,
                "saves": p.saves,
                "distance_covered": round(p.distance_covered, 1),
                # Phase 2
                "carries_attempted": p.carries_attempted,
                "carries_completed": p.carries_completed,
                "crosses_attempted": p.crosses_attempted,
                "crosses_completed": p.crosses_completed,
                "headers_attempted": p.headers_attempted,
                "headers_won": p.headers_won,
            })
        return result
