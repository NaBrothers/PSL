"""Main match loop: 3-phase tick model (reward-driven engine v2).

Phase 1: All players choose actions simultaneously
Phase 2: Detect interactions (duel if holder carries + defender tackles;
         interception if pass + defender on path)
Phase 3: Resolve interactions, execute non-conflicting actions, check unforced errors
"""

from __future__ import annotations

import random
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from psl_core.constants import FORMATION

from .config import EngineConfig, load_config_from_service
from .pitch import Pitch, Zone
from .ball import Ball, BallState, BallOwnership, BallFlight, FlightType
from .player import Player, PlayerState
from .team import Team, TeamPhase
from .actions import Action, ActionType
from .physics import distance, move_toward, direction, player_speed
from .goalkeeper import compute_gk_save_probability
from .interactions import (
    detect_duel, detect_interception, detect_wasted_tackle,
    resolve_duel, resolve_interception,
    DuelOutcome, InteractionType,
)
from .stats import MatchStats
from .trace import MatchTrace
from .rating import compute_team_ratings
from .replay_adapter import build_header, build_frame, build_ball_flight_data


@dataclass
class MatchResult:
    """Result of a completed match."""
    home_score: int = 0
    away_score: int = 0
    goals: List[Dict] = field(default_factory=list)
    home_stats: Dict = field(default_factory=dict)
    away_stats: Dict = field(default_factory=dict)
    home_player_stats: List[Dict] = field(default_factory=list)
    away_player_stats: List[Dict] = field(default_factory=list)
    home_ratings: List[Dict] = field(default_factory=list)
    away_ratings: List[Dict] = field(default_factory=list)
    replay_url: Optional[str] = None
    trace_id: str = ""


class MatchV2:
    """Tick-based football match simulation engine - reward-driven 3-phase model.

    Usage:
        match = MatchV2(home_cards, away_cards, "442", "433")
        result = match.run()
        replay = match.get_replay_data()
    """

    def __init__(
        self,
        home_cards: List[Dict],
        away_cards: List[Dict],
        home_formation: str,
        away_formation: str,
        config: Optional[EngineConfig] = None,
        config_service=None,
    ):
        """Initialize match."""
        if config is not None:
            self.config = config
        elif config_service is not None:
            self.config = load_config_from_service(config_service)
        else:
            self.config = EngineConfig()

        self.pitch = Pitch(config=self.config)
        self.home_formation_key = home_formation
        self.away_formation_key = away_formation

        # Build teams
        self.home = self._build_team("home", home_cards, home_formation)
        self.away = self._build_team("away", away_cards, away_formation)

        # Ball
        self.ball = Ball()
        self.ball.position = self.pitch.center

        # State
        self.tick = 0
        self.half = 1
        self.home_score = 0
        self.away_score = 0
        self.last_passer_idx = -1
        self.last_passer_team = ""
        self._offside_flagged: set = set()  # player indices flagged offside at pass time

        # Stats & trace
        self.match_stats = MatchStats()
        self.trace = MatchTrace()

        # Replay frames
        self._replay_frames: List[Dict] = []
        self._pending_event_text: Optional[str] = None
        self._pending_ball_flight: Optional[Dict] = None
        self._pending_pause_ms: Optional[int] = None
        self._pending_cut: Optional[bool] = None

        # Result
        self._result: Optional[MatchResult] = None

    def _build_team(self, side: str, cards: List[Dict], formation_key: str) -> Team:
        """Build a Team from card data."""
        players = []
        formation_data = FORMATION.get(formation_key)
        if formation_data is None:
            formation_data = FORMATION["442"]
            formation_key = "442"

        positions = formation_data.get("positions", [])

        for i, card in enumerate(cards[:11]):
            abilities = {}
            ability_keys = [
                "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
                "Tackling", "Defence", "Speed", "IQ", "Heading",
                "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
            ]
            for key in ability_keys:
                abilities[key] = card.get(key, card.get("abilities", {}).get(key, 50))

            pos_name = positions[i] if i < len(positions) else "CM"

            player = Player(
                index=i,
                name=card.get("name", f"Player {i+1}"),
                position=pos_name,
                color=card.get("color", "gold"),
                player_id=str(card.get("player_id", "")),
                team_side=side,
                abilities=abilities,
                overall=card.get("overall", 50),
            )
            players.append(player)

        team = Team(
            side=side,
            name=f"{side.capitalize()} Team",
            formation=formation_key,
            players=players,
            attacking_right=(side == "home"),
        )

        team.setup_formation(self.pitch, formation_data)
        return team

    def run(self) -> MatchResult:
        """Run the full match simulation. Returns MatchResult."""
        # First half
        self.half = 1
        self._kickoff("home")
        self._run_half(start_tick=0, end_tick=self.config.half_ticks)

        # Half time: flip sides
        self._halftime()

        # Second half
        self.half = 2
        self._kickoff("away")
        self._run_half(start_tick=self.config.half_ticks, end_tick=self.config.total_ticks)

        # Compile result
        self._result = self._compile_result()
        return self._result

    def get_replay_data(self) -> List[Dict]:
        """Get replay data as list of JSONL-compatible dicts."""
        header = build_header(
            self.home,
            self.away,
            self.home_formation_key,
            self.away_formation_key,
            self.config.pitch_width,
            self.config.pitch_length,
        )
        return [header] + self._replay_frames

    def get_trace(self) -> Dict:
        """Get trace data for debugging."""
        return self.trace.to_dict()

    # -------------------------------------------------------------------------
    # Match flow
    # -------------------------------------------------------------------------

    def _run_half(self, start_tick: int, end_tick: int):
        """Run one half of the match."""
        for t in range(start_tick, end_tick):
            self.tick = t
            self._tick()

            if (t - start_tick) % self.config.frame_interval == 0:
                self._record_frame()

            # Position sampling every 10 ticks for heatmap
            if t % 10 == 0:
                for p in self.home.players:
                    p.position_samples.append((round(p.pos[0], 1), round(p.pos[1], 1)))
                for p in self.away.players:
                    p.position_samples.append((round(p.pos[0], 1), round(p.pos[1], 1)))

    def _tick(self):
        """Execute one simulation tick using the 3-phase model.

        Phase 1: All players choose actions simultaneously
        Phase 2: Detect interactions
        Phase 3: Resolve interactions, execute non-conflicting, check errors
        """
        # Handle dead ball (waiting for restart)
        if self.ball.state == BallState.DEAD:
            self._clear_team_goals(self.home)
            self._clear_team_goals(self.away)
            self._prepare_restart_shape()
            if self.ball.tick_dead():
                self._restart_play()
            return

        # Handle ball in flight
        if self.ball.state == BallState.IN_FLIGHT:
            self._tick_flight()
            return

        # Handle contested ball (loose)
        if self.ball.state == BallState.CONTESTED:
            self._tick_contested()
            return

        # Ball is HELD -- run the 3-phase tick
        if self.ball.state != BallState.HELD:
            return

        self.home.update_phase(
            has_possession=self.ball.holder_team == "home",
            ball_contested=False,
            config=self.config,
        )
        self.away.update_phase(
            has_possession=self.ball.holder_team == "away",
            ball_contested=False,
            config=self.config,
        )
        self._sync_goals_with_phase()

        # Tick stun timers
        for p in self.home.players + self.away.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)

        holder_team = self.home if self.ball.holder_team == "home" else self.away
        opp_team = self.away if self.ball.holder_team == "home" else self.home
        holder = holder_team.players[self.ball.holder_idx]
        holder.possession_ticks += 1

        # =====================================================================
        # PHASE 1: All players choose actions simultaneously
        # =====================================================================
        holder_team.compute_dynamic_positions(
            self.ball.position,
            self.config,
            self.pitch,
            opponent_players=opp_team.players,
        )
        opp_team.compute_dynamic_positions(
            self.ball.position,
            self.config,
            self.pitch,
            opponent_players=holder_team.players,
        )

        # Refresh attacking support targets before the holder compares
        # pass/hold/shot values. Actions still resolve simultaneously; this just
        # lets the value model see the current support field instead of a stale
        # one-tick-old shape.
        for tm in holder_team.players:
            if tm.index == holder.index:
                continue
            if tm.state == PlayerState.STUNNED:
                continue
            tm.choose_off_ball_attack(
                self.ball.position,
                self.config,
                self.pitch,
                holder_team.attacking_right,
                ball_carrier=holder,
                opponents=opp_team.players,
                teammates=holder_team.players,
                tick=self.tick,
                team_side=holder_team.side,
                trace=self.trace,
            )

        # Holder chooses on-ball action
        holder_action_type, holder_details = holder.choose_on_ball(
            holder_team.players,
            opp_team.players,
            self.config,
            self.pitch,
            holder_team.attacking_right,
            tick=self.tick,
            team_side=holder_team.side,
            trace=self.trace,
        )

        # Off-ball players choose actions
        defender_actions = {}  # {player.index: action_type}
        defender_new_positions = {}  # {player.index: new_pos}

        # Presser assignment removed: approach score now uses responsibility_cost
        # to naturally limit how many defenders press the ball.

        # Defending team players choose
        for opp in opp_team.players:
            if opp.state == PlayerState.STUNNED:
                defender_actions[opp.index] = "hold_position"
                continue
            action_type, details = opp.choose_off_ball_defend(
                self.ball.position,
                self.config,
                self.pitch,
                opp_team.attacking_right,
                ball_carrier=holder,
                opponents=holder_team.players,
                teammates=opp_team.players,
            )
            defender_actions[opp.index] = action_type
            # Compute the position they would move to
            if "target" in details:
                speed = opp.get_move_speed(self.config)
                new_pos = move_toward(opp.pos, details["target"], speed)
                new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
                defender_new_positions[opp.index] = new_pos

        # =====================================================================
        # PHASE 2: Detect interactions
        # =====================================================================

        duel_interaction = None
        interception_interaction = None
        wasted_tackles = []

        if holder_action_type == "carry":
            # Duel detection: holder carries + defender tackles within range
            duel_interaction = detect_duel(
                holder, "carry", opp_team.players, defender_actions, self.config,
                defender_new_positions,
                carry_target=holder_details.get("target", holder.pos),
            )
            # Check for wasted tackles (defender tackles but no conflict)
            if duel_interaction is None:
                wasted_tackles = detect_wasted_tackle(
                    holder, "carry", opp_team.players, defender_actions, self.config
                )

        elif holder_action_type in ("pass", "pass_to_space"):
            # Pass + defender on path = potential interception
            pass_target = holder_details.get("target", holder.pos)
            interception_interaction = detect_interception(
                holder.pos, pass_target,
                opp_team.players, defender_new_positions, self.config
            )
            # Wasted tackles: defender tackled but attacker passed
            wasted_tackles = detect_wasted_tackle(
                holder, "pass", opp_team.players, defender_actions, self.config
            )

        elif holder_action_type == "shoot":
            # Wasted tackles on shoot
            wasted_tackles = detect_wasted_tackle(
                holder, "shoot", opp_team.players, defender_actions, self.config
            )

        elif holder_action_type == "clear":
            wasted_tackles = detect_wasted_tackle(
                holder, "clear", opp_team.players, defender_actions, self.config
            )

        self._track_defensive_pressures(
            holder,
            holder_action_type,
            opp_team,
            defender_actions,
            defender_new_positions,
            duel_interaction is not None,
            interception_interaction is not None,
        )

        # =====================================================================
        # PHASE 3: Resolve interactions, execute actions, check errors
        # =====================================================================

        # Handle wasted tackles first (defender stunned for nothing)
        # Wasted tackles: no penalty, defender just continues (didn't actually commit)
        # (Only actual duel losses cause stun)

        # Resolve DUEL (carry vs tackle)
        if duel_interaction is not None:
            self._resolve_duel_phase3(
                duel_interaction, holder, holder_team, opp_team
            )
        elif holder_action_type == "carry":
            # No duel -- execute carry
            self._execute_carry_phase3(holder, holder_details, holder_team)
        elif holder_action_type in ("pass", "pass_to_space"):
            # Execute pass (interception checked during flight)
            self._execute_pass_phase3(
                holder, holder_details, holder_team, opp_team,
                interception_interaction
            )
        elif holder_action_type == "shoot":
            self._execute_shoot_phase3(holder, holder_details, holder_team, opp_team)
        elif holder_action_type == "hold":
            self._execute_hold_phase3(holder, holder_team, holder_details)
        elif holder_action_type == "clear":
            self._execute_clear_phase3(holder, holder_details, holder_team, opp_team)

        # Move all off-ball players
        self._move_off_ball_players(holder_team, opp_team, holder, holder_action_type)

        # Track possession
        if self.ball.holder_team:
            self.match_stats.record_possession(self.ball.holder_team)

    # -------------------------------------------------------------------------
    # Phase 3: Action execution
    # -------------------------------------------------------------------------

    def _is_attacking_box_pos(self, pos: Tuple[float, float], attacking_right: bool) -> bool:
        progress = pos[0] / self.pitch.length if attacking_right else (self.pitch.length - pos[0]) / self.pitch.length
        return (
            progress > 1.0 - 16.5 / self.pitch.length
            and abs(pos[1] - self.pitch.width / 2.0) < 20.2
        )

    def _residual_ball_velocity(self, flight: BallFlight, factor: float = 0.16) -> Tuple[float, float]:
        """Small remaining roll after an incomplete pass reaches its target."""
        dx = flight.target[0] - flight.origin[0]
        dy = flight.target[1] - flight.origin[1]
        length = max(0.1, (dx * dx + dy * dy) ** 0.5)
        residual = min(6.0, max(0.7, flight.speed * factor))
        return (dx / length * residual, dy / length * residual)

    def _track_defensive_pressures(
        self,
        holder: Player,
        holder_action_type: str,
        opp_team: Team,
        defender_actions: dict,
        defender_new_positions: dict,
        duel_detected: bool,
        interception_detected: bool,
    ):
        """Track pressure attempts separately from tackles/interceptions."""
        successful_action = holder_action_type in ("pass", "pass_to_space", "shoot", "clear")
        for defender in opp_team.players:
            if defender.is_goalkeeper:
                continue
            action = defender_actions.get(defender.index, "hold_position")
            new_pos = defender_new_positions.get(defender.index, defender.pos)
            d_now = distance(defender.pos, holder.pos)
            d_next = distance(new_pos, holder.pos)
            pressure_range = self.config.press_radius * 0.55
            is_pressure = (
                (
                    action in ("approach", "tackle")
                    and min(d_now, d_next) < pressure_range
                )
                or (
                    action in ("block_lane", "mark_runner")
                    and min(d_now, d_next) < pressure_range * 0.72
                )
            )
            if not is_pressure:
                continue

            if self.tick - defender.last_pressure_tick < 3:
                continue
            defender.last_pressure_tick = self.tick
            defender.pressures += 1
            if (
                duel_detected
                or interception_detected
                or action == "tackle"
                or successful_action
            ):
                defender.successful_pressures += 1

    def _resolve_duel_phase3(
        self, interaction, holder: Player, holder_team: Team, opp_team: Team
    ):
        """Resolve a duel between ball carrier and tackler."""
        defender = interaction.defender
        defender.tackles_attempted += 1
        holder.dribbles_attempted += 1

        result = resolve_duel(interaction, self.config)

        if result.outcome == DuelOutcome.ATTACKER_WINS:
            # Attacker keeps ball, defender stunned
            holder.dribbles_completed += 1
            defender.apply_stun(self.config)
            # Move carrier forward slightly
            target = holder.pos  # stays in place (won the duel)
            self.ball.position = holder.pos
            self.trace.log_event(
                self.tick, "duel",
                winner=holder.name, loser=defender.name, outcome="attacker_wins",
            )

        elif result.outcome == DuelOutcome.DEFENDER_WINS:
            # Clean tackle - defender wins ball
            defender.tackles_won += 1
            holder.dispossessed += 1
            holder.turnovers += 1
            holder.state = PlayerState.OFF_BALL
            self._give_ball(defender, opp_team)
            self.trace.log_event(
                self.tick, "tackle",
                tackler=defender.name, dispossessed=holder.name,
            )

        else:  # LOOSE_BALL
            # Ball goes contested
            holder.state = PlayerState.OFF_BALL
            loose_pos = self.pitch.clamp(
                holder.pos[0] + random.uniform(-3, 3),
                holder.pos[1] + random.uniform(-2, 2),
            )
            self.ball.set_contested(loose_pos)
            self.match_stats.record_contested()
            self.trace.log_event(
                self.tick, "duel",
                winner="", loser="", outcome="loose_ball",
            )

    def _execute_carry_phase3(self, holder: Player, details: dict, holder_team: Team):
        """Execute carry action (no duel occurred).

        Move holder toward target at carrier speed. Ball follows.
        Then check for unforced carry error.
        """
        holder.carries_attempted += 1
        holder.hold_ticks = 0
        target = details.get("target", holder.pos)

        # Move toward target at adaptive carry speed.
        carry_speed, carry_difficulty = self._compute_carry_speed(
            holder, target, holder_team
        )
        old_pos = holder.pos
        new_pos = move_toward(holder.pos, target, carry_speed)
        new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
        holder.pos = new_pos
        holder.distance_covered += distance(old_pos, new_pos)
        self.ball.position = new_pos

        # Unforced carry error scales with control ability and carry difficulty.
        dribbling = holder.abilities.get("Dribbling", 50)
        progress = new_pos[0] / self.pitch.length if holder_team.attacking_right else (self.pitch.length - new_pos[0]) / self.pitch.length
        centrality = 1.0 - min(1.0, abs(new_pos[1] - self.pitch.width / 2.0) / (self.pitch.width / 2.0))
        final_third_control = max(0.0, min(1.0, (progress - 0.72) / 0.18)) * max(0.0, min(1.0, centrality))
        stale_carry_difficulty = 1.0 + max(0, holder.consecutive_carries - 1) * 0.24 * final_third_control
        error_chance = ((100 - dribbling) / self.config.carry_error_divisor) * carry_difficulty * stale_carry_difficulty
        if random.random() < error_chance:
            # Ball goes loose
            holder.unforced_errors += 1
            holder.turnovers += 1
            holder.consecutive_carries = 0
            holder.state = PlayerState.OFF_BALL
            loose_pos = self.pitch.clamp(
                new_pos[0] + random.uniform(-3, 3),
                new_pos[1] + random.uniform(-2, 2),
            )
            self.ball.set_contested(loose_pos)
            self.match_stats.record_contested()
            self.trace.log_event(self.tick, "error", player=holder.name, error_type="carry")
        else:
            holder.carries_completed += 1
            holder.consecutive_carries += 1
            self._track_carry_stats(holder, old_pos, new_pos, holder_team.attacking_right)
            self.trace.log_action(
                self.tick, holder_team.side, holder.name, "carry",
                success=True, pos=new_pos, target=target, speed=round(carry_speed, 2),
            )

    def _compute_carry_speed(self, holder: Player, target: tuple, holder_team: Team):
        """Adaptive ball-carrying speed from ability, path space, and pressure."""
        opp_team = self.away if holder_team.side == "home" else self.home
        base_speed = player_speed(
            holder.speed_value,
            self.config.player_max_speed,
            self.config.player_min_speed,
        )
        dribbling = holder.abilities.get("Dribbling", 50) / 100.0
        control_factor = 0.42 + 0.34 * dribbling

        dx = target[0] - holder.pos[0]
        dy = target[1] - holder.pos[1]
        path_len = max(0.1, (dx * dx + dy * dy) ** 0.5)
        nx, ny = dx / path_len, dy / path_len

        path_pressure = 0.0
        close_pressure = 0.0
        for opp in opp_team.players:
            if opp.is_goalkeeper:
                continue
            ox = opp.pos[0] - holder.pos[0]
            oy = opp.pos[1] - holder.pos[1]
            dist = (ox * ox + oy * oy) ** 0.5
            if dist < 8.0:
                close_pressure += 1.0 - dist / 8.0

            proj = ox * nx + oy * ny
            if -1.0 < proj < path_len + 4.0:
                perp = abs(ox * ny - oy * nx)
                if perp < 7.0:
                    path_pressure += (1.0 - perp / 7.0) * (1.0 - max(0.0, proj) / (path_len + 8.0))

        pressure = min(1.0, path_pressure * 0.45 + close_pressure * 0.35)
        space_factor = 1.0 - pressure
        urgency = min(1.0, path_len / 12.0)

        personal_carry_cap = base_speed * (0.58 + 0.24 * dribbling)
        speed = base_speed * control_factor * (0.70 + 0.45 * space_factor) * (0.75 + 0.25 * urgency)
        speed = max(1.4, min(personal_carry_cap, speed))
        difficulty = 1.0 + pressure * 1.4 + max(0.0, speed - self.config.carrier_speed) * 0.18
        return speed, difficulty

    def _execute_pass_phase3(
        self,
        passer: Player,
        details: dict,
        passer_team: Team,
        opp_team: Team,
        interception_interaction,
    ):
        """Execute pass action.

        If interception detected in Phase 2, resolve it immediately.
        Otherwise, ball enters IN_FLIGHT state.
        Then check pass accuracy error.
        """
        passer.passes_attempted += 1
        passer.hold_ticks = 0
        passer.consecutive_carries = 0
        ideal_target = details.get("target", passer.pos)
        is_long = details.get("is_long", False)

        # Pass accuracy unforced error: (100-Passing)/500
        passing = passer.abilities.get("Short_Passing", 50)
        if is_long:
            passing = passer.abilities.get("Long_Passing", 50)
        dist_to_target = distance(passer.pos, ideal_target)
        pressure = sum(1 for o in opp_team.players if not o.is_goalkeeper and distance(o.pos, passer.pos) < 8.0)
        lane_risk = details.get("lane_risk", 0.0)
        ability_factor = max(0.0, min(1.0, passing / 100.0))
        error_radius = (
            (1.0 - ability_factor) * (1.2 + dist_to_target / 12.0)
            + pressure * 0.35
            + lane_risk * 2.5
        )
        if error_radius > 0.05:
            angle = random.uniform(0, math.tau)
            mag = random.random() * error_radius
            target = self.pitch.clamp(
                ideal_target[0] + math.cos(angle) * mag,
                ideal_target[1] + math.sin(angle) * mag,
            )
        else:
            target = ideal_target

        error_chance = (100 - passing) / self.config.pass_error_divisor
        if random.random() < error_chance:
            # Pass goes astray -- ball contested
            passer.unforced_errors += 1
            passer.turnovers += 1
            passer.state = PlayerState.OFF_BALL
            stray_pos = self.pitch.clamp(
                ideal_target[0] + random.uniform(-8, 8),
                ideal_target[1] + random.uniform(-8, 8),
            )
            self.ball.set_contested(stray_pos)
            self.match_stats.record_contested()
            self.trace.log_event(self.tick, "error", player=passer.name, error_type="pass_accuracy")
            return

        # Check if interception happens immediately
        if interception_interaction is not None:
            interceptor = interception_interaction.defender
            intercepted = resolve_interception(
                interception_interaction, passing, self.config
            )
            if intercepted:
                # Defender intercepts!
                interceptor.interceptions += 1
                passer.state = PlayerState.OFF_BALL
                self._give_ball(interceptor, opp_team)
                self.trace.log_event(
                    self.tick, "interception",
                    player=interceptor.name, team=opp_team.side,
                )
                return

        # No interception -- ball enters flight
        speed = self.config.ball_long_pass_speed if is_long else self.config.ball_pass_speed
        flight_type = FlightType.LONG_PASS if is_long else FlightType.SHORT_PASS
        dist = distance(passer.pos, target)
        ticks_needed = max(1, math.ceil(dist / speed))

        # Determine if this is a pass_to_space
        is_space_pass = "intended_receiver" in details and "target_player_idx" not in details

        flight = BallFlight(
            origin=passer.pos,
            target=target,
            flight_type=flight_type,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=passer.index,
            passer_team=passer_team.side,
            is_pass_to_space=is_space_pass,
        )

        self.last_passer_idx = passer.index
        self.last_passer_team = passer_team.side
        passer.state = PlayerState.OFF_BALL
        passer.current_goal = None
        self.ball.set_flight(flight)

        # Record which attacking players are offside at this moment
        opp_team = self.away if passer_team.side == "home" else self.home
        self._offside_flagged = set()
        for p in passer_team.players:
            if p.index == passer.index:
                continue
            if self._is_offside(p, passer_team, opp_team, pass_origin=passer.pos):
                self._offside_flagged.add(p.index)

        action_name = "pass_to_space" if is_space_pass else ("long_pass" if is_long else "short_pass")
        self.trace.log_action(
            self.tick, passer_team.side, passer.name,
            action_name,
            target=target,
            ideal_target=ideal_target,
            target_player=details.get("target_player_idx", details.get("intended_receiver", -1)),
        )

        self._pending_ball_flight = build_ball_flight_data(
            passer.pos, target, "pass", on_target=False
        )

    def _execute_shoot_phase3(
        self, shooter: Player, details: dict, shooter_team: Team, opp_team: Team
    ):
        """Execute shot action."""
        shooter.shots += 1
        shooter.hold_ticks = 0
        shooter.consecutive_carries = 0

        # Track key pass for the player who assisted the shot
        if self.last_passer_team == ("home" if shooter.team_side == "home" else "away"):
            assisting_team = self.home if self.last_passer_team == "home" else self.away
            if 0 <= self.last_passer_idx < len(assisting_team.players):
                if self.last_passer_idx != shooter.index:
                    assisting_team.players[self.last_passer_idx].key_passes += 1

        on_target_prob = details.get("on_target_prob", 0.3)
        # Estimate xG from shot details
        shot_xg = details.get("xg", on_target_prob * self.config.goal_reward_constant * 0.5)
        shot_xg = min(0.95, max(0.01, shot_xg))
        shooter.xg += shot_xg

        on_target = random.random() < on_target_prob
        if on_target:
            shooter.shots_on_target += 1

        goal_center = details.get("target", (self.config.pitch_length, self.config.pitch_width / 2))

        if on_target:
            goal_y_min = self.pitch.goal_y_min
            goal_y_max = self.pitch.goal_y_max
            target_y = random.uniform(goal_y_min + 0.5, goal_y_max - 0.5)
            if shooter_team.attacking_right:
                target = (self.config.pitch_length, target_y)
            else:
                target = (0.0, target_y)
        else:
            if shooter_team.attacking_right:
                target_x = self.config.pitch_length + random.uniform(0.5, 3.0)
            else:
                target_x = -random.uniform(0.5, 3.0)
            target_y = random.uniform(self.pitch.goal_y_min - 5, self.pitch.goal_y_max + 5)
            target = (target_x, target_y)

        dist = distance(shooter.pos, target)
        ticks_needed = max(1, math.ceil(dist / self.config.ball_shot_speed))

        flight = BallFlight(
            origin=shooter.pos,
            target=target,
            flight_type=FlightType.SHOT,
            speed=self.config.ball_shot_speed,
            ticks_total=ticks_needed,
            passer_idx=shooter.index,
            passer_team=shooter_team.side,
            on_target=on_target,
        )

        self.last_passer_idx = shooter.index
        self.last_passer_team = shooter_team.side
        shooter.state = PlayerState.OFF_BALL
        shooter.current_goal = None
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, shooter_team.side, shooter.name, "shot",
            on_target=on_target, distance=round(dist, 1),
        )

        self._pending_ball_flight = build_ball_flight_data(
            shooter.pos, target, "shot", on_target=on_target
        )
        self._pending_event_text = f"{'SHOT ON TARGET' if on_target else 'SHOT'} {shooter.name} shoots!"

    def _execute_clear_phase3(
        self, clearer: Player, details: dict, clearer_team: Team, opp_team: Team
    ):
        """Execute clearance action."""
        clearer.clearances += 1
        clearer.passes_attempted += 1
        clearer.hold_ticks = 0
        clearer.consecutive_carries = 0
        target = details.get("target", clearer.pos)

        dist = distance(clearer.pos, target)
        ticks_needed = max(1, math.ceil(dist / self.config.ball_long_pass_speed))

        flight = BallFlight(
            origin=clearer.pos,
            target=target,
            flight_type=FlightType.CLEARANCE,
            speed=self.config.ball_long_pass_speed,
            ticks_total=ticks_needed,
            passer_idx=clearer.index,
            passer_team=clearer_team.side,
        )

        self.last_passer_idx = clearer.index
        self.last_passer_team = clearer_team.side
        clearer.state = PlayerState.OFF_BALL
        clearer.current_goal = None
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, clearer_team.side, clearer.name, "clear",
            target=target,
        )

    def _execute_hold_phase3(self, holder: Player, holder_team: Team, details: dict = None):
        """Keep controlled possession with small shielding/scanning touches."""
        holder.hold_ticks += 1
        holder.consecutive_carries = 0
        opp_team = self.away if holder_team.side == "home" else self.home
        details = details or {}

        pressure_x = 0.0
        pressure_y = 0.0
        pressure = 0.0
        nearest_dist = float("inf")
        for opp in opp_team.players:
            if opp.is_goalkeeper:
                continue
            dx = holder.pos[0] - opp.pos[0]
            dy = holder.pos[1] - opp.pos[1]
            d = max(0.1, (dx * dx + dy * dy) ** 0.5)
            nearest_dist = min(nearest_dist, d)
            if d < 8.0:
                w = 1.0 - d / 8.0
                pressure += w
                pressure_x += (dx / d) * w
                pressure_y += (dy / d) * w

        old_pos = holder.pos
        opportunity_target = details.get("opportunity_target")
        opportunity_x = 0.0
        opportunity_y = 0.0
        if (
            isinstance(opportunity_target, (list, tuple))
            and len(opportunity_target) >= 2
        ):
            target_x = float(opportunity_target[0])
            target_y = float(opportunity_target[1])
            to_target_x = target_x - holder.pos[0]
            to_target_y = target_y - holder.pos[1]
            target_len = max(0.1, (to_target_x * to_target_x + to_target_y * to_target_y) ** 0.5)
            # Drift slightly into a better passing angle rather than standing
            # still. The direction is lateral-dominant so this remains control,
            # not a disguised carry.
            opportunity_x = to_target_x / target_len * 0.22
            opportunity_y = to_target_y / target_len * 0.52

        if pressure > 0.0 or opportunity_target:
            # Small shielding/scanning touch. Pressure pushes the carrier away
            # from defenders; an opportunity target adds a lateral adjustment
            # toward a cleaner passing angle.
            norm = max(0.1, (pressure_x * pressure_x + pressure_y * pressure_y) ** 0.5)
            away_x = pressure_x / norm if pressure > 0.0 else 0.0
            away_y = pressure_y / norm if pressure > 0.0 else 0.0
            forward_dir = 1.0 if holder_team.attacking_right else -1.0
            adjust_x = away_x * 0.70 + opportunity_x + forward_dir * (0.12 if pressure > 0.0 else 0.04)
            adjust_y = away_y * 0.70 + opportunity_y
            adjust_norm = max(0.1, (adjust_x * adjust_x + adjust_y * adjust_y) ** 0.5)
            dribbling = holder.abilities.get("Dribbling", 50) / 100.0
            max_adjust = 0.45 + 1.15 * dribbling
            scan_bonus = 0.35 if opportunity_target else 0.0
            move_dist = min(max_adjust, 0.35 + pressure * 0.55 + scan_bonus)
            new_pos = self.pitch.clamp(
                holder.pos[0] + adjust_x / adjust_norm * move_dist,
                holder.pos[1] + adjust_y / adjust_norm * move_dist,
            )
            holder.pos = new_pos
            holder.distance_covered += distance(old_pos, new_pos)

        self.ball.position = holder.pos

        # Shielding under heavy pressure can still produce a loose touch.
        dribbling = holder.abilities.get("Dribbling", 50)
        error_chance = max(0.0, pressure - 0.6) * (100 - dribbling) / (self.config.carry_error_divisor * 1.8)
        if random.random() < error_chance:
            holder.unforced_errors += 1
            holder.turnovers += 1
            holder.state = PlayerState.OFF_BALL
            loose_pos = self.pitch.clamp(
                holder.pos[0] + random.uniform(-2, 2),
                holder.pos[1] + random.uniform(-2, 2),
            )
            self.ball.set_contested(loose_pos)
            self.match_stats.record_contested()
            self.trace.log_event(self.tick, "error", player=holder.name, error_type="shield")
            return

        self.trace.log_action(
            self.tick, holder_team.side, holder.name, "hold",
            hold_ticks=holder.hold_ticks,
            pos=holder.pos,
            opportunity_target=opportunity_target,
            pressure=round(pressure, 2),
            nearest_def=round(nearest_dist, 1) if nearest_dist < 999 else None,
        )

    # -------------------------------------------------------------------------
    # Ball in flight
    # -------------------------------------------------------------------------

    def _tick_flight(self):
        """Process a tick where the ball is in flight."""
        completed = self.ball.tick_flight()

        if not completed:
            # Move players while ball is in flight
            self._move_all_players_flight()
            return

        # Flight complete - resolve arrival
        self._resolve_flight_arrival()

    def _resolve_flight_arrival(self):
        """Resolve ball arriving at flight target."""
        flight = self.ball.flight
        if flight is None:
            return

        target_pos = flight.target

        # Check if out of bounds
        if self.pitch.is_out_of_bounds(target_pos[0], target_pos[1]):
            self._handle_out_of_bounds(target_pos, flight)
            return

        # Shot arrival
        if flight.flight_type == FlightType.SHOT:
            self._resolve_shot_arrival(flight)
            return

        # Pass / Clearance arrival
        passer_team = self.home if flight.passer_team == "home" else self.away
        opp_team = self.away if flight.passer_team == "home" else self.home

        if flight.flight_type == FlightType.CLEARANCE:
            # Clearance: ball goes to closest player at target
            closest_home = self.home.get_closest_to(target_pos, exclude_gk=False)
            closest_away = self.away.get_closest_to(target_pos, exclude_gk=False)
            d_home = distance(closest_home.pos, target_pos) if closest_home else 999
            d_away = distance(closest_away.pos, target_pos) if closest_away else 999
            if d_home < d_away:
                self._give_ball(closest_home, self.home)
                if passer_team.side == "home":
                    passer_team.players[flight.passer_idx].passes_completed += 1
            else:
                self._give_ball(closest_away, self.away)
                if passer_team.side == "away":
                    passer_team.players[flight.passer_idx].passes_completed += 1
            return

        # Pass-to-space: first-to-arrive from EITHER team gets the ball
        if flight.is_pass_to_space:
            self._resolve_pass_to_space_arrival(flight, target_pos, passer_team, opp_team)
            return

        # Normal pass: find intended receiver or closest teammate
        target_player_idx = -1
        # Find closest teammate to target
        best_receiver = None
        best_dist = float("inf")
        for p in passer_team.players:
            if p.index == flight.passer_idx:
                continue
            d = distance(p.pos, target_pos)
            if d < best_dist:
                best_dist = d
                best_receiver = p

        if best_receiver and best_dist < 8.0:
            # First touch error: (100-IQ)/400
            iq = best_receiver.abilities.get("IQ", 50)
            touch_error_chance = (100 - iq) / self.config.first_touch_error_divisor
            if random.random() < touch_error_chance:
                # First touch error - ball goes contested
                best_receiver.unforced_errors += 1
                loose_pos = self.pitch.clamp(
                    target_pos[0] + random.uniform(-4, 4),
                    target_pos[1] + random.uniform(-4, 4),
                )
                self.ball.set_contested(loose_pos)
                self.match_stats.record_contested()
                self.trace.log_event(
                    self.tick, "error",
                    player=best_receiver.name, error_type="first_touch",
                )
                return

            # Offside check: receiver was flagged offside when pass was made
            if best_receiver.index in self._offside_flagged:
                opp_team_for_offside = self.away if passer_team.side == "home" else self.home
                best_receiver.offsides += 1
                self.ball.set_dead("offside", opp_team_for_offside.side, restart_ticks=2)
                self._offside_flagged = set()
                self.trace.log_event(
                    self.tick, "offside",
                    player=best_receiver.name, team=passer_team.side,
                )
                return
            self._offside_flagged = set()

            # Pass completed successfully
            self._give_ball(best_receiver, passer_team, receive_origin=flight.origin)
            passer = passer_team.players[flight.passer_idx]
            passer.passes_completed += 1
            self._track_pass_stats(passer, flight.origin, best_receiver.pos, passer_team.attacking_right)
            self.trace.log_action(
                self.tick, passer_team.side, best_receiver.name, "receive",
                success=True, pos=best_receiver.pos,
            )
        else:
            # No one close enough -- ball goes contested
            self.ball.set_contested(target_pos, self._residual_ball_velocity(flight, 0.26))
            self.match_stats.record_contested()

    def _resolve_shot_arrival(self, flight: BallFlight):
        """Resolve a shot arriving at (or near) the goal."""
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        shooter = shooter_team.players[flight.passer_idx]

        in_box = self._is_attacking_box_pos(flight.origin, shooter_team.attacking_right)

        if not flight.on_target:
            shooter.shot_log.append({
                "x": round(flight.origin[0], 1),
                "y": round(flight.origin[1], 1),
                "xg": round(shooter.xg - sum(s.get("xg", 0) for s in shooter.shot_log), 2),
                "in_box": in_box,
                "outcome": "off_target",
            })
            self._pending_event_text = f"{shooter.name}'s shot goes wide!"
            self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
            self._record_frame()
            return

        # Shot is on target - GK save check
        gk = defending_team.goalkeeper
        save_prob = compute_gk_save_probability(
            gk, flight.target, flight.origin, self.config
        )

        # Track xG for GK
        last_xg = shooter.xg - sum(s.get("xg", 0) for s in shooter.shot_log)
        gk.psxg_faced += max(0, last_xg)

        if random.random() < save_prob:
            # SAVE!
            gk.saves += 1
            shooter.shot_log.append({
                "x": round(flight.origin[0], 1),
                "y": round(flight.origin[1], 1),
                "xg": round(last_xg, 2),
                "in_box": in_box,
                "outcome": "saved",
                "target_x": round(flight.target[0], 1),
                "target_y": round(flight.target[1], 1),
            })
            self._give_ball(gk, defending_team)
            self._pending_event_text = f"{gk.name} saves {shooter.name}'s shot!"
            self._pending_pause_ms = 1000
            self.trace.log_event(self.tick, "save", keeper=gk.name, shooter=shooter.name)
            self._record_frame()
        else:
            # GOAL!
            shooter.shot_log.append({
                "x": round(flight.origin[0], 1),
                "y": round(flight.origin[1], 1),
                "xg": round(last_xg, 2),
                "in_box": in_box,
                "outcome": "goal",
                "target_x": round(flight.target[0], 1),
                "target_y": round(flight.target[1], 1),
            })
            gk.goals_conceded += 1
            self._score_goal(shooter, shooter_team, defending_team)

    def _resolve_pass_to_space_arrival(
        self, flight: BallFlight, target_pos: Tuple[float, float],
        passer_team: Team, opp_team: Team
    ):
        """Resolve a pass-to-space arrival.

        First-to-arrive from EITHER team gets the ball.
        If defender closer -> interception.
        If attacker closer -> successful pass completion.
        """
        # Find closest player from passer's team (excluding passer)
        best_tm = None
        best_tm_dist = float("inf")
        for p in passer_team.players:
            if p.index == flight.passer_idx:
                continue
            d = distance(p.pos, target_pos)
            if d < best_tm_dist:
                best_tm_dist = d
                best_tm = p

        # Find closest player from defending team
        best_opp = None
        best_opp_dist = float("inf")
        for p in opp_team.players:
            d = distance(p.pos, target_pos)
            if d < best_opp_dist:
                best_opp_dist = d
                best_opp = p

        # Determine who arrives first
        if best_opp and best_opp_dist < best_tm_dist:
            # Defender arrives first -> interception
            best_opp.interceptions += 1
            self._give_ball(best_opp, opp_team)
            self.trace.log_event(
                self.tick, "interception",
                player=best_opp.name, team=opp_team.side,
                context="pass_to_space",
            )
        elif best_tm and best_tm_dist < 10.0:
            # Teammate arrives first and is close enough to receive
            # First touch error check
            iq = best_tm.abilities.get("IQ", 50)
            touch_error_chance = (100 - iq) / self.config.first_touch_error_divisor
            if random.random() < touch_error_chance:
                best_tm.unforced_errors += 1
                loose_pos = self.pitch.clamp(
                    target_pos[0] + random.uniform(-4, 4),
                    target_pos[1] + random.uniform(-4, 4),
                )
                self.ball.set_contested(loose_pos)
                self.match_stats.record_contested()
                self.trace.log_event(
                    self.tick, "error",
                    player=best_tm.name, error_type="first_touch",
                )
                return

            # Offside check: receiver was flagged offside when pass was made
            if best_tm.index in self._offside_flagged:
                best_tm.offsides += 1
                self.ball.set_dead("offside", opp_team.side, restart_ticks=2)
                self._offside_flagged = set()
                self.trace.log_event(
                    self.tick, "offside",
                    player=best_tm.name, team=passer_team.side,
                )
                return
            self._offside_flagged = set()

            # Successful pass to space
            old_pos = best_tm.pos
            receive_pos = self.pitch.clamp(target_pos[0], target_pos[1])
            best_tm.pos = receive_pos
            best_tm.target_pos = receive_pos
            best_tm.distance_covered += distance(old_pos, receive_pos)
            self._give_ball(best_tm, passer_team, receive_origin=flight.origin)
            passer = passer_team.players[flight.passer_idx]
            passer.passes_completed += 1
            self._track_pass_stats(passer, flight.origin, receive_pos, passer_team.attacking_right)
            self.trace.log_action(
                self.tick, passer_team.side, best_tm.name, "receive_space_pass",
                success=True, pos=receive_pos,
            )
        else:
            # No one close enough -- ball goes contested
            self.ball.set_contested(target_pos, self._residual_ball_velocity(flight, 0.30))
            self.match_stats.record_contested()

    def _score_goal(self, scorer: Player, scoring_team: Team, conceding_team: Team):
        """Record a goal."""
        scorer.goals += 1

        assister_name = ""
        assister_color = ""
        if self.last_passer_team == scoring_team.side and self.last_passer_idx != scorer.index:
            if self.last_passer_idx < len(scoring_team.players):
                assister = scoring_team.players[self.last_passer_idx]
                assister.assists += 1
                assister_name = assister.name
                assister_color = assister.color

        if scoring_team.side == "home":
            self.home_score += 1
        else:
            self.away_score += 1

        minute = self._tick_to_minute()

        self.match_stats.record_goal(
            minute=minute,
            team_side=scoring_team.side,
            scorer_name=scorer.name,
            assister_name=assister_name,
            scorer_color=scorer.color,
            assister_color=assister_color,
        )

        self.trace.log_event(
            self.tick, "goal",
            scorer=scorer.name, team=scoring_team.side,
            assister=assister_name, minute=minute,
        )

        assist_text = f" (assist: {assister_name})" if assister_name else ""
        self._pending_event_text = f"GOAL! {scorer.name} scores!{assist_text} [{self.home_score}-{self.away_score}]"
        self._pending_pause_ms = 3000
        self._record_frame()

        # Reset for kickoff
        self.ball.set_dead("kickoff", conceding_team.side, 3)

        home_formation_data = FORMATION.get(self.home_formation_key, FORMATION["442"])
        away_formation_data = FORMATION.get(self.away_formation_key, FORMATION["442"])
        self.home.setup_formation(self.pitch, home_formation_data)
        self.away.setup_formation(self.pitch, away_formation_data)

    # -------------------------------------------------------------------------
    # Contested ball
    # -------------------------------------------------------------------------

    def _tick_contested(self):
        """Process a tick where the ball is contested (loose).

        Players race to ball. Closest picks it up.
        """
        self.ball.tick_contested()
        ball_pos = self.pitch.clamp(self.ball.position[0], self.ball.position[1])
        self.ball.position = ball_pos
        self.home.update_phase(False, True, self.config)
        self.away.update_phase(False, True, self.config)
        self._clear_team_goals(self.home)
        self._clear_team_goals(self.away)

        # Find closest player from each team
        best_player = None
        best_team = None
        best_dist = float("inf")

        for p in self.home.players:
            d = distance(p.pos, ball_pos)
            if d < best_dist:
                best_dist = d
                best_player = p
                best_team = self.home

        for p in self.away.players:
            d = distance(p.pos, ball_pos)
            if d < best_dist:
                best_dist = d
                best_player = p
                best_team = self.away

        # If someone is close enough, they win the ball
        if best_player and best_dist < self.config.contest_radius:
            self._give_ball(best_player, best_team)
            self.trace.log_event(
                self.tick, "contested_won",
                player=best_player.name, team=best_team.side,
            )
        else:
            # Nearby players contest the loose ball; the rest protect the second
            # ball and team shape instead of everyone sprinting into one point.
            for team, other in ((self.home, self.away), (self.away, self.home)):
                team.compute_dynamic_positions(
                    ball_pos, self.config, self.pitch,
                    opponent_players=other.players,
                )
                for p in team.players:
                    if p.state == PlayerState.STUNNED:
                        continue
                    if p.is_goalkeeper:
                        p.target_pos = p.tactical_anchor
                        p.movement_intent = "recover_shape"
                        continue

                    dist_to_ball = distance(p.pos, ball_pos)
                    speed = player_speed(
                        p.speed_value,
                        self.config.player_max_speed,
                        self.config.player_min_speed,
                    )
                    time_to_ball = dist_to_ball / max(speed, 0.1)
                    nearby_teammates = sum(
                        1
                        for teammate in team.players
                        if teammate.index != p.index
                        and not teammate.is_goalkeeper
                        and distance(teammate.pos, ball_pos) < dist_to_ball + 1.5
                    )
                    iq = p.iq_value / 100.0
                    race_reach = self.config.contested_race_radius * (0.84 + 0.22 * speed / max(self.config.player_max_speed, 0.1))
                    first_ball_value = max(0.0, 1.0 - dist_to_ball / max(1.0, race_reach))
                    first_ball_value = first_ball_value * first_ball_value * (3.0 - 2.0 * first_ball_value)
                    contest_score = first_ball_value * (1.08 + 0.34 * iq) / (1.0 + nearby_teammates * 0.35)

                    support_x = p.tactical_anchor[0] * 0.88 + ball_pos[0] * 0.12
                    support_y = p.tactical_anchor[1] * 0.90 + ball_pos[1] * 0.10
                    support_pos = self.pitch.clamp(support_x, support_y)
                    support_dist = distance(p.pos, support_pos)
                    support_score = (
                        0.05
                        + min(0.24, nearby_teammates * 0.08)
                        + min(0.08, support_dist / 80.0)
                        + (1.0 - first_ball_value) * 0.08
                    )

                    if contest_score > support_score:
                        p.target_pos = ball_pos
                        p.movement_intent = "contest"
                    else:
                        p.target_pos = support_pos
                        p.movement_intent = "recover_shape"

                team.move_all(self.config, self.pitch)

            # If contested too long, award to closest
            if self.ball.contested_ticks > 5 and best_player and best_team:
                self._give_ball(best_player, best_team)

        # Track possession (neutral during contested)
        self.match_stats.record_possession("")

    # -------------------------------------------------------------------------
    # Movement helpers
    # -------------------------------------------------------------------------

    def _adjust_defensive_pressure_targets_after_carry(
        self,
        holder_team: Team,
        opp_team: Team,
        holder: Player,
        holder_action_type: str,
    ):
        """Nudge responsible defenders toward the latest carrier position."""
        if holder_action_type not in ("carry", "hold"):
            return
        if (
            self.ball.state != BallState.HELD
            or self.ball.holder_team != holder_team.side
            or self.ball.holder_idx != holder.index
        ):
            return

        holder_progress = (
            holder.pos[0] / self.pitch.length
            if holder_team.attacking_right
            else (self.pitch.length - holder.pos[0]) / self.pitch.length
        )
        if holder_progress < 0.66 and holder.consecutive_carries < 2 and holder_action_type != "hold":
            return

        defenders = [
            p for p in opp_team.players
            if not p.is_goalkeeper and p.state != PlayerState.STUNNED
        ]
        if not defenders:
            return

        nearest_dist = min(distance(p.pos, holder.pos) for p in defenders)
        close_count = sum(
            1 for p in defenders
            if distance(p.pos, holder.pos) < max(self.config.tackle_range, self.config.press_radius * 0.70)
        )
        centrality = 1.0 - min(1.0, abs(holder.pos[1] - self.pitch.width / 2.0) / (self.pitch.width / 2.0))
        stale_threat = (
            max(0.0, min(1.0, (holder.consecutive_carries - 1) / 3.0))
            * max(0.0, min(1.0, (holder_progress - 0.62) / 0.24))
            * (0.55 + 0.45 * centrality)
        )
        if stale_threat <= 0.0:
            return

        goal_side = -1.0 if opp_team.attacking_right else 1.0
        for defender in defenders:
            d = distance(defender.pos, holder.pos)
            if d > self.config.press_radius * 1.25:
                continue
            target_d = distance(defender.target_pos, holder.pos)
            distance_responsibility = max(0.0, min(1.0, 1.0 - max(0.0, d - nearest_dist) / 11.0))
            crowd_factor = 1.0 / (1.0 + max(0, close_count - 1) * 0.45)
            intent_factor = (
                1.0 if defender.movement_intent == "press"
                else 0.72 if defender.movement_intent in ("block_lane", "mark")
                else 0.55
            )
            adjust = stale_threat * distance_responsibility * crowd_factor * intent_factor
            if adjust <= 0.08:
                continue

            contain_depth = 2.2 + 1.5 * stale_threat
            y_offset = max(-4.0, min(4.0, defender.pos[1] - holder.pos[1])) * 0.35
            pressure_target = self.pitch.clamp(
                holder.pos[0] + goal_side * contain_depth,
                holder.pos[1] + y_offset,
            )
            if distance(pressure_target, holder.pos) >= target_d:
                continue
            blend = min(0.55, 0.18 + 0.42 * adjust)
            defender.target_pos = (
                defender.target_pos[0] * (1.0 - blend) + pressure_target[0] * blend,
                defender.target_pos[1] * (1.0 - blend) + pressure_target[1] * blend,
            )
            if defender.movement_intent in ("defend_shape", "block_lane", "mark"):
                defender.movement_intent = "press"

    def _move_off_ball_players(
        self,
        holder_team: Team,
        opp_team: Team,
        holder: Player,
        holder_action_type: str = "",
    ):
        """Move all off-ball players one tick."""
        self._adjust_defensive_pressure_targets_after_carry(holder_team, opp_team, holder, holder_action_type)

        # Move each player (except holder who already moved)
        for p in holder_team.players:
            if p.index == holder.index:
                continue
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            p.move_tick(self.config, self.pitch)

        for p in opp_team.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            p.move_tick(self.config, self.pitch)

    def _move_all_players_flight(self):
        """Move all players during ball flight (off-ball positioning)."""
        ball_pos = self.ball.position
        target_pos = self.ball.flight.target if self.ball.flight else ball_pos
        passer_team_side = self.ball.flight.passer_team if self.ball.flight else ""

        # Attacking team repositions
        atk_team = self.home if passer_team_side == "home" else self.away
        def_team = self.away if passer_team_side == "home" else self.home
        self._clear_team_goals(def_team)

        atk_team.compute_dynamic_positions(target_pos, self.config, self.pitch, opponent_players=def_team.players)
        def_team.compute_dynamic_positions(target_pos, self.config, self.pitch, opponent_players=atk_team.players)

        for p in atk_team.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            dist_to_target = distance(p.pos, target_pos)
            if (
                self.ball.flight
                and p.index != self.ball.flight.passer_idx
                and dist_to_target < self.config.contested_race_radius * 1.35
            ):
                p.choose_off_ball_attack(
                    target_pos, self.config, self.pitch, atk_team.attacking_right,
                    opponents=def_team.players, teammates=atk_team.players,
                    tick=self.tick,
                    team_side=atk_team.side,
                    trace=self.trace,
                )
            else:
                support_x = p.tactical_anchor[0] * 0.86 + target_pos[0] * 0.14
                support_y = p.tactical_anchor[1] * 0.88 + target_pos[1] * 0.12
                p.set_movement_target(self.pitch.clamp(support_x, support_y), "recover_shape")
            p.move_tick(self.config, self.pitch)

        for p in def_team.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            if distance(p.pos, target_pos) < self.config.contested_race_radius * 1.25:
                p.choose_off_ball_defend(
                    target_pos, self.config, self.pitch, def_team.attacking_right,
                    opponents=atk_team.players, teammates=def_team.players,
                )
            else:
                support_x = p.tactical_anchor[0] * 0.88 + target_pos[0] * 0.12
                support_y = p.tactical_anchor[1] * 0.90 + target_pos[1] * 0.10
                p.set_movement_target(self.pitch.clamp(support_x, support_y), "defend_shape")
            p.move_tick(self.config, self.pitch)

    # -------------------------------------------------------------------------
    # Ball possession
    # -------------------------------------------------------------------------

    def _clear_team_goals(self, team: Team):
        for player in team.players:
            player.current_goal = None

    def _sync_goals_with_phase(self):
        """Clear player goals that no longer match the team's phase."""
        attacking_side = self.ball.holder_team if self.ball.state == BallState.HELD else ""
        if attacking_side != "home":
            self._clear_team_goals(self.home)
        if attacking_side != "away":
            self._clear_team_goals(self.away)

    def _track_pass_stats(self, passer, origin, target, attacking_right: bool):
        """Track progressive pass, passes into box, long pass, key pass stats."""
        dist = distance(origin, target)
        forward_dir = 1.0 if attacking_right else -1.0
        progress = (target[0] - origin[0]) * forward_dir
        origin_progress = origin[0] / self.pitch.length if attacking_right else (self.pitch.length - origin[0]) / self.pitch.length
        target_progress = target[0] / self.pitch.length if attacking_right else (self.pitch.length - target[0]) / self.pitch.length
        origin_wide = abs(origin[1] - self.pitch.width / 2) > self.pitch.width * 0.28
        target_in_box = (
            target_progress > (1.0 - 16.5 / self.pitch.length)
            and abs(target[1] - self.pitch.width / 2) < 20.2
        )
        if origin_wide and target_in_box and progress > 3.0:
            passer.crosses_attempted += 1
            passer.crosses_completed += 1

        # Progressive pass: moves ball >10m toward opponent goal
        if progress > 10.0:
            passer.progressive_passes += 1

        # Long pass
        if dist > 30.0:
            passer.long_passes += 1
            passer.completed_long_passes += 1

        # Pass into final third
        if attacking_right:
            if target[0] > self.pitch.length * 2 / 3:
                passer.passes_into_final_third += 1
            if target[0] > self.pitch.length - 16.5 and abs(target[1] - self.pitch.width / 2) < 20.2:
                passer.passes_into_box += 1
        else:
            if target[0] < self.pitch.length / 3:
                passer.passes_into_final_third += 1
            if target[0] < 16.5 and abs(target[1] - self.pitch.width / 2) < 20.2:
                passer.passes_into_box += 1

    def _track_carry_stats(self, player, old_pos, new_pos, attacking_right: bool):
        """Track progressive carries, carries into box."""
        forward_dir = 1.0 if attacking_right else -1.0
        progress = (new_pos[0] - old_pos[0]) * forward_dir

        if progress > 5.0:
            player.progressive_carries += 1

        if attacking_right:
            if new_pos[0] > self.pitch.length * 2 / 3 and old_pos[0] <= self.pitch.length * 2 / 3:
                player.carries_into_final_third += 1
            if new_pos[0] > self.pitch.length - 16.5 and abs(new_pos[1] - self.pitch.width / 2) < 20.2:
                if old_pos[0] <= self.pitch.length - 16.5:
                    player.carries_into_box += 1
        else:
            if new_pos[0] < self.pitch.length / 3 and old_pos[0] >= self.pitch.length / 3:
                player.carries_into_final_third += 1
            if new_pos[0] < 16.5 and abs(new_pos[1] - self.pitch.width / 2) < 20.2:
                if old_pos[0] >= 16.5:
                    player.carries_into_box += 1

    def _is_offside(self, receiver, attacking_team, defending_team, pass_origin=None) -> bool:
        """Check if receiver is in an offside position.

        Offside = receiver ahead of 2nd-last defender AND ahead of ball
        at the moment the pass was played, AND in opponent's half.
        pass_origin: ball position when the pass was made.
        """
        if receiver.is_goalkeeper:
            return False

        # Use pass origin for the 'ahead of ball' check, NOT current ball position
        ball_x = pass_origin[0] if pass_origin else self.ball.position[0]

        if attacking_team.attacking_right:
            if receiver.pos[0] <= self.pitch.length / 2:
                return False

            # Defenders protect goal at x=105: last defender = highest x
            def_xs = sorted(
                [p.pos[0] for p in defending_team.players if not p.is_goalkeeper],
                reverse=True
            )
            offside_line = def_xs[1] if len(def_xs) >= 2 else def_xs[0] if def_xs else self.pitch.length

            return receiver.pos[0] > offside_line and receiver.pos[0] > ball_x
        else:
            if receiver.pos[0] >= self.pitch.length / 2:
                return False

            # Defenders protect goal at x=0: last defender = lowest x
            def_xs = sorted(
                [p.pos[0] for p in defending_team.players if not p.is_goalkeeper],
                reverse=False
            )
            offside_line = def_xs[1] if len(def_xs) >= 2 else def_xs[0] if def_xs else 0.0

            return receiver.pos[0] < offside_line and receiver.pos[0] < ball_x

    def _give_ball(self, player: Player, team: Team, receive_origin: Tuple[float, float] = None):
        """Give the ball to a specific player."""
        # Clear previous holder state
        if self.ball.holder_team == "home" and self.ball.holder_idx >= 0:
            if self.ball.holder_idx < len(self.home.players):
                self.home.players[self.ball.holder_idx].state = PlayerState.OFF_BALL
                self.home.players[self.ball.holder_idx].current_goal = None
        elif self.ball.holder_team == "away" and self.ball.holder_idx >= 0:
            if self.ball.holder_idx < len(self.away.players):
                self.away.players[self.ball.holder_idx].state = PlayerState.OFF_BALL
                self.away.players[self.ball.holder_idx].current_goal = None

        # If ball changes team, clear offside flags (defender touched ball resets offside)
        if self.ball.holder_team and self.ball.holder_team != team.side:
            self._offside_flagged = set()

        player.state = PlayerState.ON_BALL
        player.hold_ticks = 0
        player.possession_ticks = 0
        player.consecutive_carries = 0
        player.last_receive_origin = receive_origin or player.pos
        player.current_goal = None
        self.ball.set_held(player.index, team.side, player.pos)

    # -------------------------------------------------------------------------
    # Restarts
    # -------------------------------------------------------------------------

    def _handle_out_of_bounds(self, pos: Tuple[float, float], flight: BallFlight):
        """Handle ball going out of bounds."""
        passer_team_side = flight.passer_team
        other_team = "away" if passer_team_side == "home" else "home"

        # Log shot that went out of bounds (off-target)
        if flight.flight_type == FlightType.SHOT:
            shooter_team = self.home if passer_team_side == "home" else self.away
            shooter = shooter_team.players[flight.passer_idx]
            attacking_right = shooter_team.attacking_right
            last_xg = shooter.xg - sum(s.get("xg", 0) for s in shooter.shot_log)
            shooter.shot_log.append({
                "x": round(flight.origin[0], 1),
                "y": round(flight.origin[1], 1),
                "xg": round(max(0, last_xg), 2),
                "in_box": self._is_attacking_box_pos(flight.origin, attacking_right),
                "outcome": "off_target",
            })

        if self.pitch.is_over_goal_line(pos[0]):
            if flight.flight_type == FlightType.SHOT:
                self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
            else:
                self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
        else:
            self.ball.set_dead("throw_in", other_team, self.config.throw_in_restart_ticks)

    def _restart_play(self):
        """Restart play after dead ball."""
        restart_team = self.home if self.ball.restart_team == "home" else self.away
        reason = self.ball.dead_reason
        self._prepare_restart_shape(force=True)

        if reason == "kickoff":
            self.ball.position = self.pitch.center
            closest = restart_team.get_closest_to(self.pitch.center, exclude_gk=True)
            if closest:
                closest.pos = (self.pitch.center[0], self.pitch.center[1])
                self._give_ball(closest, restart_team)
                self._pending_cut = True

        elif reason == "goal_kick":
            gk = restart_team.goalkeeper
            gk.pos = self._goal_kick_spot(restart_team)
            gk.target_pos = gk.pos
            self._give_ball(gk, restart_team)
            self.ball.position = gk.pos

        elif reason == "corner":
            if restart_team.attacking_right:
                corner_pos = (self.config.pitch_length - 0.5, random.choice([0.5, self.config.pitch_width - 0.5]))
            else:
                corner_pos = (0.5, random.choice([0.5, self.config.pitch_width - 0.5]))

            self.ball.position = corner_pos
            closest = restart_team.get_closest_to(corner_pos, exclude_gk=True)
            if closest:
                closest.pos = corner_pos
                self._give_ball(closest, restart_team)

        elif reason == "throw_in":
            ball_pos = self.ball.position
            ball_pos = self.pitch.clamp(ball_pos[0], ball_pos[1])
            self.ball.position = ball_pos
            closest = restart_team.get_closest_to(ball_pos, exclude_gk=True)
            if closest:
                self._give_ball(closest, restart_team)

        elif reason == "offside":
            # Free kick to defending team from offside position
            ball_pos = self.ball.position
            ball_pos = self.pitch.clamp(ball_pos[0], ball_pos[1])
            self.ball.position = ball_pos
            closest = restart_team.get_closest_to(ball_pos, exclude_gk=True)
            if closest:
                self._give_ball(closest, restart_team)

        else:
            # Fallback: give ball to closest player on restart team
            ball_pos = self.ball.position
            ball_pos = self.pitch.clamp(ball_pos[0], ball_pos[1])
            closest = restart_team.get_closest_to(ball_pos, exclude_gk=True)
            if closest:
                self._give_ball(closest, restart_team)

        self.last_passer_idx = -1
        self.last_passer_team = ""
        self._offside_flagged: set = set()  # player indices flagged offside at pass time

    def _prepare_restart_shape(self, force: bool = False):
        """Move players toward restart-specific shape while the ball is dead."""
        if self.ball.restart_team not in ("home", "away"):
            return
        restart_team = self.home if self.ball.restart_team == "home" else self.away
        defending_team = self.away if restart_team.side == "home" else self.home
        if self.ball.dead_reason == "goal_kick":
            targets = self._goal_kick_shape_targets(restart_team, defending_team)
            ball_pos = self._goal_kick_spot(restart_team)
        elif self.ball.dead_reason == "kickoff":
            targets = self._kickoff_shape_targets(restart_team, defending_team)
            ball_pos = self.pitch.center
        else:
            return
        for player, target in targets:
            player.state = PlayerState.OFF_BALL
            if force:
                player.movement_intent = "recover_shape"
                player.target_pos = target
                if self._must_leave_penalty_area_for_goal_kick(player, restart_team):
                    player.pos = target
                    player.velocity = (0.0, 0.0)
                elif distance(player.pos, target) > 16.0:
                    player.pos = target
                    player.velocity = (0.0, 0.0)
                else:
                    player.move_tick(self.config, self.pitch)
            else:
                player.set_movement_target(target, "recover_shape")
                player.move_tick(self.config, self.pitch)
        self.ball.position = ball_pos

    def _must_leave_penalty_area_for_goal_kick(self, player: Player, restart_team: Team) -> bool:
        if player.team_side == restart_team.side:
            return False
        if restart_team.attacking_right:
            return player.pos[0] < 16.5
        return player.pos[0] > self.pitch.length - 16.5

    def _goal_kick_spot(self, team: Team) -> Tuple[float, float]:
        x = 6.0 if team.attacking_right else self.config.pitch_length - 6.0
        return (x, self.pitch.width / 2.0)

    def _goal_kick_shape_targets(self, restart_team: Team, defending_team: Team) -> List[Tuple[Player, Tuple[float, float]]]:
        """Goal-kick setup using formation depth as a reusable set-piece shape."""
        targets: List[Tuple[Player, Tuple[float, float]]] = []

        def progress_of(pos: Tuple[float, float], team: Team) -> float:
            return pos[0] / self.pitch.length if team.attacking_right else (self.pitch.length - pos[0]) / self.pitch.length

        def x_from_progress(progress: float, team: Team) -> float:
            return progress * self.pitch.length if team.attacking_right else (1.0 - progress) * self.pitch.length

        def target_progress(base_progress: float, attacking: bool, is_gk: bool) -> float:
            if is_gk:
                return 6.0 / self.pitch.length
            if attacking:
                if base_progress < 0.28:
                    return 0.18 + base_progress * 0.42
                if base_progress < 0.52:
                    return 0.34 + (base_progress - 0.28) / 0.24 * 0.18
                if base_progress < 0.70:
                    return 0.52 + (base_progress - 0.52) / 0.18 * 0.12
                return 0.64 + (base_progress - 0.70) / 0.30 * 0.12
            return base_progress

        def defending_distance_from_restart_goal(player: Player) -> float:
            if player.is_goalkeeper:
                return self.pitch.length - 6.0
            if player.is_attacker:
                return 34.0
            if player.is_midfielder:
                return 48.0
            if player.is_defender:
                return 63.0
            return 70.0

        for team, attacking in ((restart_team, True), (defending_team, False)):
            ball_side = -1.0 if restart_team.attacking_right else 1.0
            for player in team.players:
                base_progress = progress_of(player.base_formation_pos, team)
                base_width = player.base_formation_pos[1] - self.pitch.width / 2.0
                if attacking:
                    progress = target_progress(base_progress, attacking, player.is_goalkeeper)
                    x = x_from_progress(progress, team)
                    width_scale = 1.08
                    y = self.pitch.width / 2.0 + base_width * width_scale
                else:
                    distance_from_goal = defending_distance_from_restart_goal(player)
                    if restart_team.attacking_right:
                        x = distance_from_goal
                    else:
                        x = self.pitch.length - distance_from_goal
                    width_scale = 0.92
                    y = self.pitch.width / 2.0 + base_width * width_scale
                    y += ball_side * 2.2
                targets.append((player, self.pitch.clamp(x, y)))
        targets = [
            (player, target)
            for player, target in targets
            if player is not restart_team.goalkeeper
        ]
        targets.append((restart_team.goalkeeper, self._goal_kick_spot(restart_team)))
        return targets

    def _kickoff_shape_targets(self, restart_team: Team, other_team: Team) -> List[Tuple[Player, Tuple[float, float]]]:
        """Kickoff setup compressed into each team's own half."""
        targets: List[Tuple[Player, Tuple[float, float]]] = []
        half_x = self.pitch.length / 2.0

        def team_targets(team: Team) -> List[Tuple[Player, Tuple[float, float]]]:
            rows = []
            for player, base in zip(team.players, team._formation_coords):
                progress = base[0] / self.pitch.length if team.attacking_right else (self.pitch.length - base[0]) / self.pitch.length
                compressed_progress = progress * 0.48
                if team.attacking_right:
                    x = max(0.5, min(half_x - 1.0, compressed_progress * self.pitch.length))
                else:
                    x = min(self.pitch.length - 0.5, max(half_x + 1.0, self.pitch.length - compressed_progress * self.pitch.length))
                rows.append((player, self.pitch.clamp(x, base[1])))
            return rows

        targets.extend(team_targets(restart_team))
        targets.extend(team_targets(other_team))

        forward_positions = {"ST", "CF", "LW", "RW", "LF", "RF", "LS", "RS"}
        forward_candidates = [p for p in restart_team.players if p.position in forward_positions]
        kicker = min(forward_candidates, key=lambda p: distance(p.pos, self.pitch.center), default=None)
        if kicker is None:
            kicker = restart_team.get_closest_to(self.pitch.center, exclude_gk=True)
        if kicker:
            targets = [(player, target) for player, target in targets if player is not kicker]
            targets.append((kicker, self.pitch.center))
        return targets

    def _kickoff(self, team_side: str):
        """Set up kickoff for a team.
        
        Keep each team's original shape, compressed into its own half.
        The kicking team sends one forward to the center spot.
        """
        self.ball.position = self.pitch.center
        team = self.home if team_side == "home" else self.away
        other_team = self.away if team_side == "home" else self.home
        half_x = self.pitch.length / 2.0

        def place_team_in_own_half(t):
            for p, base in zip(t.players, t._formation_coords):
                progress = base[0] / self.pitch.length if t.attacking_right else (self.pitch.length - base[0]) / self.pitch.length
                compressed_progress = progress * 0.48
                if t.attacking_right:
                    x = max(0.5, min(half_x - 1.0, compressed_progress * self.pitch.length))
                else:
                    x = min(self.pitch.length - 0.5, max(half_x + 1.0, self.pitch.length - compressed_progress * self.pitch.length))
                p.pos = self.pitch.clamp(x, base[1])
                p.target_pos = p.pos
                p.tactical_anchor = p.pos

        place_team_in_own_half(team)
        place_team_in_own_half(other_team)

        # Kicker at center
        forward_positions = {"ST", "CF", "LW", "RW", "LF", "RF", "LS", "RS"}
        forward_candidates = [p for p in team.players if p.position in forward_positions]
        kicker = min(forward_candidates, key=lambda p: distance(p.pos, self.pitch.center), default=None)
        if kicker is None:
            kicker = team.get_closest_to(self.pitch.center, exclude_gk=True)
        if kicker:
            kicker.pos = self.pitch.center
            kicker.target_pos = kicker.pos
            self._give_ball(kicker, team)
        self._pending_cut = True
        self._record_frame()

    def _halftime(self):
        """Process halftime: flip directions."""
        home_formation_data = FORMATION.get(self.home_formation_key, FORMATION["442"])
        away_formation_data = FORMATION.get(self.away_formation_key, FORMATION["442"])

        self.home.flip_direction(self.pitch, home_formation_data)
        self.away.flip_direction(self.pitch, away_formation_data)

        self._pending_cut = True

    # -------------------------------------------------------------------------
    # Replay
    # -------------------------------------------------------------------------

    def _record_frame(self):
        """Record a replay frame with current state."""
        frame = build_frame(
            tick=self.tick,
            tick_duration=self.config.tick_duration,
            half=self.half,
            home_team=self.home,
            away_team=self.away,
            ball_pos=self.ball.position,
            ball_holder_idx=self.ball.holder_idx,
            ball_team=self.ball.holder_team if self.ball.holder_team else None,
            home_score=self.home_score,
            away_score=self.away_score,
            ball_flight=self._pending_ball_flight,
            event_text=self._pending_event_text,
            pause_ms=self._pending_pause_ms,
            cut=self._pending_cut,
        )
        self._replay_frames.append(frame)

        self._pending_ball_flight = None
        self._pending_event_text = None
        self._pending_pause_ms = None
        self._pending_cut = None

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _tick_to_minute(self) -> int:
        """Convert current tick to match minute."""
        total_seconds = self.tick * self.config.tick_duration
        return min(90, int(total_seconds / 60.0))

    def _compile_result(self) -> MatchResult:
        """Compile final match result."""
        home_ratings = compute_team_ratings(
            self.home.players, self.home_score, self.away_score
        )
        away_ratings = compute_team_ratings(
            self.away.players, self.away_score, self.home_score
        )

        # Merge ratings into player stats
        home_ps = self.home.get_player_stats()
        away_ps = self.away.get_player_stats()
        for i, ps in enumerate(home_ps):
            if i < len(home_ratings):
                ps["rating"] = home_ratings[i].get("rating", 6.0)
        for i, ps in enumerate(away_ps):
            if i < len(away_ratings):
                ps["rating"] = away_ratings[i].get("rating", 6.0)

        return MatchResult(
            home_score=self.home_score,
            away_score=self.away_score,
            goals=self.match_stats.goals,
            home_stats=self.match_stats.get_home_stats(self.home),
            away_stats=self.match_stats.get_away_stats(self.away),
            home_player_stats=home_ps,
            away_player_stats=away_ps,
            home_ratings=home_ratings,
            away_ratings=away_ratings,
            replay_url=None,
            trace_id=self.trace.trace_id,
        )
