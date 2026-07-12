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


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


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
            self.players[i].base_formation_pos = pitch_pos
            self.players[i].tactical_anchor = pitch_pos
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
        from .rust_adapter import team_phase_update_rust

        phase_update = team_phase_update_rust(self, has_possession, ball_contested, config)
        self.phase = TeamPhase(phase_update["phase"])
        self._ticks_since_possession_change = phase_update["ticks_since_possession_change"]
        self._had_possession_last_tick = phase_update["had_possession_last_tick"]
        return

    def _update_phase_legacy(self, has_possession: bool, ball_contested: bool, config: "EngineConfig"):
        """Legacy Python team phase transition formula."""
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
        """Update each player's dynamic tactical anchor from the current ball context.

        `formation_pos` stays as the static formation slot for the current half.
        `tactical_anchor` is the soft role reference used by position-value
        scoring so shape can advance, retreat, and shift with the ball without
        rewriting the player's real formation identity.
        """
        if not self._formation_coords:
            return

        if getattr(config, "rust_team_shape_plan_adapter_enabled", False):
            from .rust_adapter import team_shape_plan_rust

            anchors = team_shape_plan_rust(self, ball_pos, config, pitch, opponent_players)
            for player in self.players:
                anchor = anchors.get(player.index)
                if anchor is not None:
                    player.tactical_anchor = anchor
            return

        self._compute_dynamic_positions_legacy(ball_pos, config, pitch, opponent_players)

    def _compute_dynamic_positions_legacy(
        self,
        ball_pos: Tuple[float, float],
        config: "EngineConfig",
        pitch: "Pitch",
        opponent_players: list = None,
    ):
        """Legacy Python tactical-anchor formula kept for parity fallback."""
        if not self._formation_coords:
            return

        length = pitch.length
        width = pitch.width
        ball_progress = ball_pos[0] / length if self.attacking_right else (length - ball_pos[0]) / length
        ball_progress = max(0.0, min(1.0, ball_progress))
        side_shift = (ball_pos[1] - width / 2.0)

        is_defending = self.phase in (TeamPhase.DEFENDING, TeamPhase.TRANSITION_DEF, TeamPhase.CONTESTING)
        is_transition_def = self.phase == TeamPhase.TRANSITION_DEF
        offside_line = None
        if opponent_players:
            def_xs = sorted([p.pos[0] for p in opponent_players if not p.is_goalkeeper], reverse=self.attacking_right)
            if len(def_xs) >= 2:
                offside_line = def_xs[1]
            elif def_xs:
                offside_line = def_xs[0]

        for i, player in enumerate(self.players):
            base = self._formation_coords[i]
            base_progress = base[0] / length if self.attacking_right else (length - base[0]) / length
            base_width_offset = base[1] - width / 2.0

            if is_defending:
                # Keep line identity from the base shape, but let the whole block
                # breathe with the ball. Transition defense is allowed to stay a
                # little higher before settling into the block.
                block_center = 0.18 + 0.50 * ball_progress
                if is_transition_def:
                    block_center += 0.06
                line_offset = (base_progress - 0.50) * 0.72
                progress = max(0.05, min(0.92, block_center + line_offset))
                y = width / 2.0 + base_width_offset * 0.92 + side_shift * 0.14
            else:
                # In possession, the team can expand and move up with the ball,
                # but the original line order remains a soft reference.
                if player.is_goalkeeper:
                    # Keeper behaves as a soft sweeper outlet: he follows the
                    # block a little, but remains clearly behind the defensive
                    # line as a passing option.
                    progress = min(0.18, max(0.02, base_progress + ball_progress * 0.10))
                    y = width / 2.0 + side_shift * 0.05
                else:
                    # Preserve line identity first. The ball nudges each line
                    # forward differently: forwards threaten the last line,
                    # midfielders connect, defenders support behind midfield.
                    advance_pressure = max(0.0, ball_progress - base_progress)
                    width_ratio = min(1.0, abs(base_width_offset) / (width / 2.0))
                    role_side = base_width_offset / max(1.0, width / 2.0)
                    ball_side = side_shift / max(1.0, width / 2.0)
                    same_side = max(0.0, min(1.0, role_side * ball_side))
                    weak_side = max(0.0, min(1.0, -role_side * ball_side))
                    advanced_role = max(0.0, min(1.0, (base_progress - 0.42) / 0.38))
                    support_role = max(0.0, min(1.0, (base_progress - 0.22) / 0.42))
                    second_line_role = (
                        _smoothstep(0.42, 0.54, base_progress)
                        * (1.0 - _smoothstep(0.62, 0.74, base_progress))
                    )

                    # Advanced and wide anchors naturally attack more space as
                    # the ball progresses. This keeps the logic geometric:
                    # wide forwards overlap because their base width/depth says
                    # they are wide and advanced, not because of a position name.
                    final_third_pressure = max(0.0, ball_progress - 0.50)
                    push = advance_pressure * (0.18 + 0.30 * advanced_role + 0.14 * width_ratio)
                    box_arrival = final_third_pressure * (0.58 * advanced_role + 0.20 * width_ratio)
                    wide_midfield_support = (
                        final_third_pressure
                        * width_ratio
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                        * 0.34
                    )
                    wide_midfield_outlet = (
                        _smoothstep(0.56, 0.74, ball_progress)
                        * width_ratio
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                        * 0.16
                    )
                    second_line_arrival = (
                        final_third_pressure
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                        * (0.10 + 0.10 * (1.0 - width_ratio))
                    )
                    arc_support_pressure = (
                        _smoothstep(0.78, 0.90, ball_progress)
                        * second_line_role
                        * (1.0 - 0.45 * _smoothstep(0.56, 0.84, width_ratio))
                    )
                    arc_support_arrival = arc_support_pressure * (
                        0.075 + 0.055 * (1.0 - width_ratio) + 0.035 * weak_side
                    )
                    weak_side_arrival = (
                        final_third_pressure
                        * width_ratio
                        * weak_side
                        * _smoothstep(0.38, 0.68, base_progress)
                        * (0.10 + 0.18 * advanced_role)
                    )
                    wide_arrival_depth = (
                        _smoothstep(0.70, 0.88, ball_progress)
                        * width_ratio
                        * _smoothstep(0.44, 0.64, base_progress)
                        * (0.20 + 0.18 * weak_side + 0.10 * same_side)
                    )
                    line_stretch = max(0.0, ball_progress - 0.66) * (0.10 + 0.16 * advanced_role)
                    progress = (
                        base_progress
                        + push
                        + box_arrival
                        + wide_midfield_support
                        + wide_midfield_outlet
                        + second_line_arrival
                        + arc_support_arrival
                        + weak_side_arrival
                        + wide_arrival_depth
                        + line_stretch
                        + 0.015
                        + 0.045 * advanced_role
                    )

                    # Cover line: deeper roles support attacks but remain a
                    # rest-defense layer behind midfield.
                    cover_cap = 0.54 + ball_progress * (0.08 + 0.08 * support_role)
                    if advanced_role < 0.35:
                        wide_support_cap = (
                            final_third_pressure
                            * width_ratio
                            * _smoothstep(0.38, 0.58, base_progress)
                            * 0.18
                        )
                        second_line_cap = (
                            final_third_pressure
                            * _smoothstep(0.38, 0.58, base_progress)
                            * (0.08 + 0.10 * (1.0 - width_ratio) + 0.08 * weak_side)
                        )
                        arc_support_cap = arc_support_pressure * (
                            0.070 + 0.060 * (1.0 - width_ratio) + 0.035 * weak_side
                        )
                        wide_arrival_cap = (
                            _smoothstep(0.70, 0.88, ball_progress)
                            * width_ratio
                            * _smoothstep(0.44, 0.64, base_progress)
                            * (0.10 + 0.12 * weak_side + 0.06 * same_side)
                        )
                        progress = min(
                            progress,
                            cover_cap
                            + wide_support_cap
                            + wide_midfield_outlet
                            + second_line_cap
                            + arc_support_cap
                            + wide_arrival_cap,
                        )

                    progress = max(0.08, min(0.94, progress))
                    width_expansion = (
                        1.00
                        + (0.16 * same_side + 0.05 * (1.0 - same_side - weak_side)) * ball_progress
                        + (0.14 * same_side + 0.04 * (1.0 - same_side - weak_side)) * advanced_role
                        - 0.26 * weak_side * _smoothstep(0.62, 0.88, ball_progress)
                    )
                    width_expansion = max(0.62, min(1.32, width_expansion))
                    overlap_width = base_width_offset * width_expansion
                    half_space_pressure = _smoothstep(0.58, 0.82, ball_progress)
                    half_space_pull = -base_width_offset * half_space_pressure * (
                        0.16 + 0.48 * weak_side + 0.08 * (1.0 - same_side)
                    )
                    far_post_tuck = -base_width_offset * (
                        _smoothstep(0.72, 0.88, ball_progress)
                        * width_ratio
                        * weak_side
                        * (0.16 + 0.12 * advanced_role)
                    )
                    second_line_tuck = -base_width_offset * (
                        final_third_pressure
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                        * (0.16 + 0.22 * weak_side)
                    )
                    arc_support_tuck = -base_width_offset * arc_support_pressure * (
                        0.10 + 0.18 * (1.0 - width_ratio) + 0.08 * weak_side
                    )
                    wide_midfield_half_space_tuck = -base_width_offset * (
                        _smoothstep(0.66, 0.80, ball_progress)
                        * width_ratio
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                        * (0.62 + 0.42 * same_side + 0.18 * weak_side)
                    )
                    y = (
                        width / 2.0
                        + overlap_width
                        + half_space_pull
                        + far_post_tuck
                        + second_line_tuck
                        + arc_support_tuck
                        + wide_midfield_half_space_tuck
                        + side_shift * (0.12 + 0.08 * width_ratio)
                    )
                    wide_midfield_half_space = (
                        _smoothstep(0.66, 0.80, ball_progress)
                        * width_ratio
                        * (1.0 - advanced_role)
                        * _smoothstep(0.38, 0.58, base_progress)
                    )
                    if wide_midfield_half_space > 0.0:
                        target_offset = base_width_offset * 0.42
                        target_y = width / 2.0 + target_offset
                        y = y * (1.0 - 0.75 * wide_midfield_half_space) + target_y * (0.75 * wide_midfield_half_space)

                # Soft offside-line awareness for attacking anchors. Forwards
                # can still threaten the line, but their default support point
                # should not live several meters beyond it.
                if offside_line is not None and not player.is_goalkeeper:
                    line_progress = offside_line / length if self.attacking_right else (length - offside_line) / length
                    buffer = 0.060 - 0.020 * max(0.0, min(1.0, (base_progress - 0.42) / 0.38))
                    onside_progress = line_progress - buffer
                    if progress > onside_progress:
                        progress = min(progress * 0.15 + onside_progress * 0.85, onside_progress)
                        progress = max(0.10, min(0.94, progress))

            x = progress * length if self.attacking_right else (1.0 - progress) * length
            player.tactical_anchor = pitch.clamp(x, y)

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
        # formation_pos is static; compute_dynamic_positions updates tactical_anchor.

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
            "tackles": sum(p.tackles_won for p in self.players),
            "tackles_won": sum(p.tackles_won for p in self.players),
            "interceptions": sum(p.interceptions for p in self.players),
            "dribbles": sum(p.dribbles_completed for p in self.players),
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
        """Get per-player statistics (full detail for frontend)."""
        result = []
        for p in self.players:
            passes_total = p.passes_attempted
            pass_rate = round(p.passes_completed / passes_total * 100, 1) if passes_total > 0 else 0
            result.append({
                "name": p.name,
                "colored_name": p.name,
                "position": p.position,
                "goals": p.goals,
                "assists": p.assists,
                "shots": p.shots,
                "shots_on_target": p.shots_on_target,
                "xg": round(p.xg, 2),
                "npxg": round(p.xg, 2),
                "post_shot_xg": round(p.xg * 0.8, 2),
                "big_chances": sum(1 for s in p.shot_log if s.get("xg", 0) > 0.3),
                "big_chances_missed": sum(1 for s in p.shot_log if s.get("xg", 0) > 0.3 and s.get("outcome") != "goal"),
                "passes": passes_total,
                "completed_passes": p.passes_completed,
                "key_passes": p.key_passes,
                "xa": round(p.key_passes * 0.12, 2),
                "progressive_passes": p.progressive_passes,
                "passes_into_final_third": p.passes_into_final_third,
                "passes_into_box": p.passes_into_box,
                "long_passes": p.long_passes,
                "completed_long_passes": p.completed_long_passes,
                "crosses": p.crosses_attempted,
                "successful_crosses": p.crosses_completed,
                "carries": p.carries_attempted,
                "progressive_carries": p.progressive_carries,
                "carries_into_final_third": p.carries_into_final_third,
                "carries_into_box": p.carries_into_box,
                "take_ons": p.dribbles_attempted,
                "successful_take_ons": p.dribbles_completed,
                "tackles_attempted": p.tackles_attempted,
                "tackles_won": p.tackles_won,
                "interceptions": p.interceptions,
                "blocks": p.blocks,
                "clearances": p.clearances,
                "pressures": p.pressures,
                "successful_pressures": p.successful_pressures,
                "turnovers": p.turnovers,
                "dispossessed": p.dispossessed,
                "offsides": p.offsides,
                "saves": p.saves,
                "goals_conceded": p.goals_conceded,
                "psxg_faced": round(p.psxg_faced, 2),
                "goals_prevented": round(p.psxg_faced - p.goals_conceded, 2) if p.is_goalkeeper else 0.0,
                "rating": 0.0,
                "shot_log": p.shot_log,
                "pass_network": {},
                "position_samples": p.position_samples,
                "distance_covered": round(p.distance_covered, 1),
            })
        return result
