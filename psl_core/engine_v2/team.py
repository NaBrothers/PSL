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
        """Compute dynamic 3-line formation based on ball and possession.

        Three lines (defence/midfield/attack) move as units:
        - When attacking: lines push toward opponent goal, following ball
        - When defending: lines compress toward own goal
        - Forward line limited by offside (opponent's last defender)
        """
        # Determine attacking direction
        if self.attacking_right:
            own_goal_x = 0.0
            opp_goal_x = pitch.length
            ball_progress = ball_pos[0] / pitch.length  # 0=own goal, 1=opp goal
        else:
            own_goal_x = pitch.length
            opp_goal_x = 0.0
            ball_progress = 1.0 - ball_pos[0] / pitch.length

        # Compute the offside line (opponent's second-last defender position)
        offside_x = opp_goal_x  # default: at opponent goal line
        if opponent_players:
            opp_xs = sorted(
                [p.pos[0] for p in opponent_players if not p.is_goalkeeper],
                reverse=(not self.attacking_right)  # sort toward our attack direction
            )
            if len(opp_xs) >= 2:
                offside_x = opp_xs[1]  # second-last defender
            elif len(opp_xs) >= 1:
                offside_x = opp_xs[0]

        # =====================================================================
        # Compute 3-line target x-positions
        # Each line follows the ball but with offset
        # =====================================================================
        has_ball = (self.phase in (TeamPhase.ATTACKING, TeamPhase.TRANSITION_ATK))

        if has_ball:
            # Attacking: push lines forward following ball
            # Defence line: behind ball, providing safety
            if self.attacking_right:
                def_line_x = max(ball_pos[0] - 35.0, 15.0)  # at least 15m from own goal
                mid_line_x = max(ball_pos[0] - 15.0, 30.0)
                atk_line_x = min(ball_pos[0] + 10.0, offside_x - 1.0)  # respect offside!
            else:
                def_line_x = min(ball_pos[0] + 35.0, pitch.length - 15.0)
                mid_line_x = min(ball_pos[0] + 15.0, pitch.length - 30.0)
                atk_line_x = max(ball_pos[0] - 10.0, offside_x + 1.0)
        else:
            # Defending: compact lines between ball and own goal
            if self.attacking_right:
                # Our goal at x=0, defend toward x=0
                def_line_x = max(min(ball_pos[0] - 10.0, 30.0), 12.0)
                mid_line_x = max(min(ball_pos[0] + 5.0, 45.0), 25.0)
                atk_line_x = max(min(ball_pos[0] + 20.0, 60.0), 40.0)
            else:
                # Our goal at x=105, defend toward x=105
                def_line_x = min(max(ball_pos[0] + 10.0, 75.0), 93.0)
                mid_line_x = min(max(ball_pos[0] - 5.0, 60.0), 80.0)
                atk_line_x = min(max(ball_pos[0] - 20.0, 45.0), 65.0)

        # Y-shift: team shifts toward ball side
        center_y = pitch.width / 2.0
        y_shift = (ball_pos[1] - center_y) * config.formation_side_shift_factor

        # =====================================================================
        # Assign each player to their line and compute position
        # =====================================================================
        for i, player in enumerate(self.players):
            if i >= len(self._formation_coords):
                break

            base_x, base_y = self._formation_coords[i]

            # Determine which line this player belongs to based on original position
            # Using base_x relative to pitch: low base_x = defensive, high = attacking
            if self.attacking_right:
                norm_x = base_x / pitch.length  # 0=near own goal, 1=near opp goal
            else:
                norm_x = 1.0 - base_x / pitch.length

            if player.is_goalkeeper:
                # GK stays near own goal
                if self.attacking_right:
                    new_x = max(3.0, def_line_x - 15.0)
                else:
                    new_x = min(pitch.length - 3.0, def_line_x + 15.0)
                new_y = base_y + y_shift * 0.2
            elif norm_x < 0.35:
                # Defender: use defence line
                # Keep relative y-spacing within the line
                line_x = def_line_x
                new_x = line_x
                new_y = base_y + y_shift
            elif norm_x < 0.6:
                # Midfielder: use midfield line
                line_x = mid_line_x
                new_x = line_x
                new_y = base_y + y_shift
            else:
                # Attacker: use attack line (limited by offside)
                line_x = atk_line_x
                new_x = line_x
                new_y = base_y + y_shift

            # Apply width modifier to y-spread
            dy_from_center = new_y - center_y
            new_y = center_y + dy_from_center * config.width

            player.formation_pos = pitch.clamp(new_x, new_y)

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
        # Update dynamic formation positions
        self.compute_dynamic_positions(ball_pos, config, pitch)

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
