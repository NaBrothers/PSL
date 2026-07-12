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
from .replay_adapter import build_header, build_frame


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


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
        seed: Optional[int] = None,
    ):
        """Initialize match."""
        if config is not None:
            self.config = config
        elif config_service is not None:
            self.config = load_config_from_service(config_service)
        else:
            self.config = EngineConfig()

        self.pitch = Pitch(config=self.config)
        self.seed = seed
        self.home_cards = home_cards
        self.away_cards = away_cards
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
        self._rust_replay_data: Optional[List[Dict]] = None
        self._rust_trace_data: Optional[Dict] = None
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
        if getattr(self.config, "rust_full_match_runner_enabled", False):
            return self._run_via_rust_match_runner()

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

    def _run_via_rust_match_runner(self) -> MatchResult:
        """Run the complete match through the Rust single-entry runner."""
        from .rust_adapter import run_match_v2_rust

        response = run_match_v2_rust(
            self.home_cards,
            self.away_cards,
            self.home_formation_key,
            self.away_formation_key,
            self.config,
            seed=self.seed if self.seed is not None else random.getrandbits(64),
        )
        self.home_score = int(response["home_score"])
        self.away_score = int(response["away_score"])
        self._rust_replay_data = list(response.get("replay", []))
        self._replay_frames = self._rust_replay_data[1:] if self._rust_replay_data else []
        trace_payload = response.get("trace", {})
        self._rust_trace_data = trace_payload
        self.trace.trace_id = response.get("trace_id", self.trace.trace_id)
        self._result = MatchResult(
            home_score=self.home_score,
            away_score=self.away_score,
            goals=response.get("goals", []),
            home_stats=response.get("home_stats", {}),
            away_stats=response.get("away_stats", {}),
            home_player_stats=response.get("home_player_stats", []),
            away_player_stats=response.get("away_player_stats", []),
            home_ratings=response.get("home_ratings", []),
            away_ratings=response.get("away_ratings", []),
            replay_url=response.get("replay_url"),
            trace_id=trace_payload.get("trace_id", response.get("trace_id", "")),
        )
        return self._result

    def get_replay_data(self) -> List[Dict]:
        """Get replay data as list of JSONL-compatible dicts."""
        if self._rust_replay_data is not None:
            return self._rust_replay_data
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
        if self._rust_trace_data is not None:
            return self._rust_trace_data
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
        self.config._runtime_tick_token = self.tick
        self.config._shot_quality_cache = {}

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
                tick=self.tick,
                team_side=opp_team.side,
                trace=self.trace,
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

        if getattr(self.config, "rust_interaction_detection_adapter_enabled", False):
            from .rust_adapter import detect_interactions_rust

            action_target = holder_details.get("target", holder.pos)
            duel_interaction, interception_interaction, wasted_tackles = detect_interactions_rust(
                holder,
                holder_action_type,
                action_target,
                opp_team.players,
                defender_actions,
                defender_new_positions,
                self.config,
            )
            if holder_action_type != "carry":
                duel_interaction = None
            if holder_action_type != "pass":
                interception_interaction = None
            if holder_action_type == "carry" and duel_interaction is not None:
                wasted_tackles = []
        else:
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

            elif holder_action_type == "pass":
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
        elif holder_action_type == "pass":
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
        from .rust_adapter import is_attacking_box_pos_rust

        return is_attacking_box_pos_rust(pos, attacking_right, self.config)

    def _residual_ball_velocity(self, flight: BallFlight, factor: float = 0.16) -> Tuple[float, float]:
        """Small remaining roll after an incomplete pass reaches its target."""
        from .rust_adapter import residual_ball_velocity_rust

        return residual_ball_velocity_rust(flight, factor)

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
        if getattr(self.config, "rust_interaction_detection_adapter_enabled", False):
            from .rust_adapter import track_defensive_pressures_rust

            pressure_events = track_defensive_pressures_rust(
                holder,
                holder_action_type,
                opp_team.players,
                defender_actions,
                defender_new_positions,
                self.config,
                duel_detected,
                interception_detected,
            )
            for defender in opp_team.players:
                successful = pressure_events.get(defender.index)
                if successful is None:
                    continue
                if self.tick - defender.last_pressure_tick < 3:
                    continue
                defender.last_pressure_tick = self.tick
                defender.pressures += 1
                if successful:
                    defender.successful_pressures += 1
            return

        successful_action = holder_action_type in ("pass", "shoot", "clear")
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

        loose_pos = None
        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import duel_phase_plan_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            duel_randoms = [
                -12.0 + 24.0 * rng.random(),
                -12.0 + 24.0 * rng.random(),
                rng.random(),
                rng.random(),
            ]
            duel_plan = duel_phase_plan_rust(
                holder,
                defender,
                self.config,
                duel_randoms,
            )
            for _ in range(duel_plan["randoms_used"]):
                random.random()
            outcome = duel_plan["outcome"]
            loose_pos = duel_plan["loose_pos"]
        elif getattr(self.config, "rust_interaction_resolution_adapter_enabled", False):
            from .rust_adapter import resolve_duel_rust

            result = resolve_duel_rust(
                interaction,
                random.uniform(-12, 12),
                random.uniform(-12, 12),
            )
            outcome = result.outcome.value
        else:
            result = resolve_duel(interaction, self.config)
            outcome = result.outcome.value

        if outcome == "attacker_wins":
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

        elif outcome == "defender_wins":
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
            if loose_pos is None:
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

        old_pos = holder.pos
        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import carry_phase_plan_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            carry_randoms = [rng.random() for _ in range(3)]
            carry_result = carry_phase_plan_rust(
                holder,
                target,
                holder_team.attacking_right,
                self.away.players if holder_team.side == "home" else self.home.players,
                self.config,
                carry_randoms,
            )
            for _ in range(carry_result["randoms_used"]):
                random.random()
            carry_speed = carry_result["carry_speed"]
            new_pos = carry_result["new_pos"]
            error_chance = carry_result["error_chance"]
            carry_error = carry_result["is_error"]
            loose_pos = carry_result["loose_pos"]
            distance_covered = carry_result["distance_covered"]
        elif getattr(self.config, "rust_carry_execution_adapter_enabled", False):
            from .rust_adapter import execute_carry_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            carry_randoms = [rng.random() for _ in range(3)]
            carry_result = execute_carry_rust(
                holder,
                target,
                holder_team.attacking_right,
                self.away.players if holder_team.side == "home" else self.home.players,
                self.config,
                carry_randoms,
            )
            for _ in range(carry_result["randoms_used"]):
                random.random()
            carry_speed = carry_result["carry_speed"]
            new_pos = carry_result["new_pos"]
            error_chance = carry_result["error_chance"]
            carry_error = carry_result["is_error"]
            loose_pos = carry_result["loose_pos"]
            distance_covered = carry_result["distance_covered"]
        else:
            # Move toward target at adaptive carry speed.
            carry_speed, carry_difficulty = self._compute_carry_speed(
                holder, target, holder_team
            )
            new_pos = move_toward(holder.pos, target, carry_speed)
            new_pos = self.pitch.clamp(new_pos[0], new_pos[1])

            # Unforced carry error scales with control ability and carry difficulty.
            dribbling = holder.abilities.get("Dribbling", 50)
            progress = new_pos[0] / self.pitch.length if holder_team.attacking_right else (self.pitch.length - new_pos[0]) / self.pitch.length
            centrality = 1.0 - min(1.0, abs(new_pos[1] - self.pitch.width / 2.0) / (self.pitch.width / 2.0))
            final_third_control = max(0.0, min(1.0, (progress - 0.72) / 0.18)) * max(0.0, min(1.0, centrality))
            stale_carry_difficulty = 1.0 + max(0, holder.consecutive_carries - 1) * 0.24 * final_third_control
            error_chance = ((100 - dribbling) / self.config.carry_error_divisor) * carry_difficulty * stale_carry_difficulty
            carry_error = random.random() < error_chance
            loose_pos = self.pitch.clamp(
                new_pos[0] + random.uniform(-3, 3),
                new_pos[1] + random.uniform(-2, 2),
            )
            distance_covered = distance(old_pos, new_pos)
        holder.pos = new_pos
        holder.distance_covered += distance_covered
        self.ball.position = new_pos

        if carry_error:
            # Ball goes loose
            holder.unforced_errors += 1
            holder.turnovers += 1
            holder.consecutive_carries = 0
            holder.state = PlayerState.OFF_BALL
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

        passing = passer.abilities.get("Short_Passing", 50)
        if is_long:
            passing = passer.abilities.get("Long_Passing", 50)
        lane_risk = details.get("lane_risk", 0.0)
        intended_receiver_idx = details.get("intended_receiver", details.get("target_player_idx", -1))
        intended_receiver = None
        if 0 <= intended_receiver_idx < len(passer_team.players):
            intended_receiver = passer_team.players[intended_receiver_idx]

        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import pass_phase_plan_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            pass_randoms = [rng.random() for _ in range(5)]
            pass_plan = pass_phase_plan_rust(
                passer,
                ideal_target,
                is_long,
                lane_risk,
                opp_team.players,
                intended_receiver,
                interception_interaction,
                self.config,
                pass_randoms,
            )
            for _ in range(pass_plan["randoms_used"]):
                random.random()

            if pass_plan["outcome"] == "pass_accuracy_error":
                passer.unforced_errors += 1
                passer.turnovers += 1
                passer.state = PlayerState.OFF_BALL
                self.ball.set_contested(pass_plan["stray_pos"])
                self.match_stats.record_contested()
                self.trace.log_event(self.tick, "error", player=passer.name, error_type="pass_accuracy")
                return

            if pass_plan["outcome"] == "interception" and interception_interaction is not None:
                interceptor = interception_interaction.defender
                interceptor.interceptions += 1
                passer.state = PlayerState.OFF_BALL
                self._give_ball(interceptor, opp_team)
                self.trace.log_event(
                    self.tick, "interception",
                    player=interceptor.name, team=opp_team.side,
                )
                return

            flight_type = FlightType.LONG_PASS if pass_plan["flight_type_code"] == 1 else FlightType.SHORT_PASS
            flight = BallFlight(
                origin=passer.pos,
                target=pass_plan["target"],
                flight_type=flight_type,
                speed=pass_plan["speed"],
                ticks_total=pass_plan["ticks_needed"],
                passer_idx=passer.index,
                passer_team=passer_team.side,
                is_pass_to_space=False,
                intended_receiver_idx=intended_receiver_idx,
            )

            self.last_passer_idx = passer.index
            self.last_passer_team = passer_team.side
            passer.state = PlayerState.OFF_BALL
            passer.current_goal = None
            self.ball.set_flight(flight)

            from .rust_adapter import flag_offside_players_rust

            defending_team = self.away if passer_team.side == "home" else self.home
            self._offside_flagged = flag_offside_players_rust(
                passer_team,
                defending_team,
                passer.index,
                passer.pos,
                self.config,
            )

            self.trace.log_action(
                self.tick, passer_team.side, passer.name,
                "pass",
                target=pass_plan["target"],
                ideal_target=ideal_target,
                target_player=intended_receiver_idx,
                pass_type=pass_plan["pass_type"],
                target_kind=pass_plan["target_kind"],
            )
            self._pending_ball_flight = pass_plan["ball_flight"]
            return

        if getattr(self.config, "rust_pass_execution_adapter_enabled", False):
            from .rust_adapter import execute_pass_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            pass_randoms = [rng.random() for _ in range(5)]
            pass_result = execute_pass_rust(
                passer,
                ideal_target,
                is_long,
                lane_risk,
                opp_team.players,
                self.config,
                pass_randoms,
            )
            for _ in range(pass_result["randoms_used"]):
                random.random()
            target = pass_result["target"]
            pass_accuracy_error = pass_result["is_error"]
            stray_pos = pass_result["stray_pos"]
            speed = pass_result["speed"]
            ticks_needed = pass_result["ticks_needed"]
            flight_type_code = pass_result["flight_type_code"]
        else:
            # Pass accuracy unforced error: (100-Passing)/500
            dist_to_target = distance(passer.pos, ideal_target)
            pressure = sum(1 for o in opp_team.players if not o.is_goalkeeper and distance(o.pos, passer.pos) < 8.0)
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
            pass_accuracy_error = random.random() < error_chance
            stray_pos = self.pitch.clamp(
                ideal_target[0] + random.uniform(-8, 8),
                ideal_target[1] + random.uniform(-8, 8),
            ) if pass_accuracy_error else None
            speed = self.config.ball_long_pass_speed if is_long else self.config.ball_pass_speed
            dist = distance(passer.pos, target)
            ticks_needed = max(1, math.ceil(dist / speed))
            flight_type_code = 1 if is_long else 0

        intercepted = False
        interceptor = interception_interaction.defender if interception_interaction is not None else None
        if interception_interaction is not None and not pass_accuracy_error:
            if getattr(self.config, "rust_interaction_resolution_adapter_enabled", False):
                from .rust_adapter import resolve_interception_rust

                intercepted = resolve_interception_rust(
                    interception_interaction,
                    passing,
                    random.random(),
                    self.config,
                )
            else:
                intercepted = resolve_interception(
                    interception_interaction, passing, self.config
                )

        from .rust_adapter import pass_phase_outcome_rust

        pass_outcome = pass_phase_outcome_rust(
            pass_accuracy_error,
            interception_interaction is not None,
            intercepted,
        )

        if pass_outcome == "pass_accuracy_error":
            # Pass goes astray -- ball contested
            passer.unforced_errors += 1
            passer.turnovers += 1
            passer.state = PlayerState.OFF_BALL
            self.ball.set_contested(stray_pos)
            self.match_stats.record_contested()
            self.trace.log_event(self.tick, "error", player=passer.name, error_type="pass_accuracy")
            return

        if pass_outcome == "interception" and interceptor is not None:
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
        flight_type = FlightType.LONG_PASS if flight_type_code == 1 else FlightType.SHORT_PASS

        # Internal action and replay event are unified as pass_to_point.
        # pass_type/target_kind remain diagnostic fields, not action types.
        components = details.get("components", {}) if details else {}

        flight = BallFlight(
            origin=passer.pos,
            target=target,
            flight_type=flight_type,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=passer.index,
            passer_team=passer_team.side,
            is_pass_to_space=False,
            intended_receiver_idx=intended_receiver_idx,
        )

        self.last_passer_idx = passer.index
        self.last_passer_team = passer_team.side
        passer.state = PlayerState.OFF_BALL
        passer.current_goal = None
        self.ball.set_flight(flight)

        # Record which attacking players are offside at this moment
        from .rust_adapter import flag_offside_players_rust

        opp_team = self.away if passer_team.side == "home" else self.home
        self._offside_flagged = flag_offside_players_rust(
            passer_team,
            opp_team,
            passer.index,
            passer.pos,
            self.config,
        )

        from .rust_adapter import pass_trace_payload_rust

        pass_trace = pass_trace_payload_rust(target, intended_receiver, is_long)
        self.trace.log_action(
            self.tick, passer_team.side, passer.name,
            "pass",
            target=target,
            ideal_target=ideal_target,
            target_player=intended_receiver_idx,
            pass_type=pass_trace["pass_type"],
            target_kind=pass_trace["target_kind"],
        )

        from .rust_adapter import build_ball_flight_data_rust

        self._pending_ball_flight = build_ball_flight_data_rust(
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
        from .rust_adapter import key_pass_for_shot_rust

        key_pass = key_pass_for_shot_rust(
            shooter,
            shooter_team,
            self.last_passer_team,
            self.last_passer_idx,
        )
        if key_pass["has_key_pass"]:
            shooter_team.players[key_pass["passer_idx"]].key_passes += 1

        on_target_prob = details.get("on_target_prob", 0.3)
        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import shot_phase_plan_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            shot_randoms = [rng.random() for _ in range(3)]
            shot_plan = shot_phase_plan_rust(
                shooter,
                details,
                on_target_prob,
                shooter_team.attacking_right,
                self.config,
                shot_randoms,
            )
            for _ in range(shot_plan["randoms_used"]):
                random.random()
            shooter.xg += shot_plan["shot_xg"]
            if shot_plan["on_target"]:
                shooter.shots_on_target += 1

            flight = BallFlight(
                origin=shooter.pos,
                target=shot_plan["target"],
                flight_type=FlightType.SHOT,
                speed=shot_plan["speed"],
                ticks_total=shot_plan["ticks_needed"],
                passer_idx=shooter.index,
                passer_team=shooter_team.side,
                on_target=shot_plan["on_target"],
            )

            self.last_passer_idx = shooter.index
            self.last_passer_team = shooter_team.side
            shooter.state = PlayerState.OFF_BALL
            shooter.current_goal = None
            self.ball.set_flight(flight)

            self.trace.log_action(
                self.tick, shooter_team.side, shooter.name, "shot",
                on_target=shot_plan["on_target"], distance=round(shot_plan["distance"], 1),
            )

            self._pending_ball_flight = shot_plan["ball_flight"]
            self._pending_event_text = shot_plan["event_text"]
            return

        # Estimate xG from shot details
        from .rust_adapter import shot_xg_rust

        shot_xg = shot_xg_rust(details, on_target_prob, self.config)
        shooter.xg += shot_xg

        if getattr(self.config, "rust_shot_execution_adapter_enabled", False):
            from .rust_adapter import execute_shot_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            shot_randoms = [rng.random() for _ in range(3)]
            shot_result = execute_shot_rust(
                shooter,
                on_target_prob,
                shooter_team.attacking_right,
                self.config,
                shot_randoms,
            )
            for _ in range(shot_result["randoms_used"]):
                random.random()
            on_target = shot_result["on_target"]
            target = shot_result["target"]
            ticks_needed = shot_result["ticks_needed"]
            shot_speed = shot_result["speed"]
            dist = shot_result["distance"]
            pending_event_text = shot_result["event_text"]
        else:
            on_target = random.random() < on_target_prob
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
            shot_speed = self.config.ball_shot_speed
            pending_event_text = f"{'SHOT ON TARGET' if on_target else 'SHOT'} {shooter.name} shoots!"
        if on_target:
            shooter.shots_on_target += 1

        flight = BallFlight(
            origin=shooter.pos,
            target=target,
            flight_type=FlightType.SHOT,
            speed=shot_speed,
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

        from .rust_adapter import build_ball_flight_data_rust

        self._pending_ball_flight = build_ball_flight_data_rust(
            shooter.pos, target, "shot", on_target=on_target
        )
        self._pending_event_text = pending_event_text

    def _execute_clear_phase3(
        self, clearer: Player, details: dict, clearer_team: Team, opp_team: Team
    ):
        """Execute clearance action."""
        clearer.clearances += 1
        clearer.passes_attempted += 1
        clearer.hold_ticks = 0
        clearer.consecutive_carries = 0
        target = details.get("target", clearer.pos)

        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import clear_phase_plan_rust

            clear_result = clear_phase_plan_rust(clearer, target, self.config)
            clear_speed = clear_result["speed"]
            ticks_needed = clear_result["ticks_needed"]
            flight_origin = clear_result["origin"]
            flight_target = clear_result["target"]
        elif getattr(self.config, "rust_clear_execution_adapter_enabled", False):
            from .rust_adapter import execute_clear_rust

            clear_result = execute_clear_rust(clearer, target, self.config)
            clear_speed = clear_result["speed"]
            ticks_needed = clear_result["ticks_needed"]
            flight_origin = clear_result["origin"]
            flight_target = clear_result["target"]
        else:
            dist = distance(clearer.pos, target)
            clear_speed = self.config.ball_long_pass_speed
            ticks_needed = max(1, math.ceil(dist / clear_speed))
            flight_origin = clearer.pos
            flight_target = target

        flight = BallFlight(
            origin=flight_origin,
            target=flight_target,
            flight_type=FlightType.CLEARANCE,
            speed=clear_speed,
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

        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import hold_phase_plan_rust

            opportunity_target = details.get("opportunity_target")
            rng = random.Random()
            rng.setstate(random.getstate())
            hold_randoms = [rng.random() for _ in range(3)]
            hold_result = hold_phase_plan_rust(
                holder,
                holder_team.attacking_right,
                opp_team.players,
                opportunity_target,
                self.config,
                hold_randoms,
            )
            for _ in range(hold_result["randoms_used"]):
                random.random()
            holder.pos = hold_result["new_pos"]
            holder.distance_covered += hold_result["distance_covered"]
            self.ball.position = holder.pos
            if hold_result["is_error"]:
                holder.unforced_errors += 1
                holder.turnovers += 1
                holder.state = PlayerState.OFF_BALL
                self.ball.set_contested(hold_result["loose_pos"])
                self.match_stats.record_contested()
                self.trace.log_event(self.tick, "error", player=holder.name, error_type="shield")
                return

            self.trace.log_action(
                self.tick, holder_team.side, holder.name, "hold",
                hold_ticks=holder.hold_ticks,
                pos=holder.pos,
                opportunity_target=opportunity_target,
                pressure=hold_result["trace_pressure"],
                nearest_def=hold_result["trace_nearest_def"],
            )
            return

        if getattr(self.config, "rust_hold_execution_adapter_enabled", False):
            from .rust_adapter import execute_hold_rust

            opportunity_target = details.get("opportunity_target")
            rng = random.Random()
            rng.setstate(random.getstate())
            hold_randoms = [rng.random() for _ in range(3)]
            hold_result = execute_hold_rust(
                holder,
                holder_team.attacking_right,
                opp_team.players,
                opportunity_target,
                self.config,
                hold_randoms,
            )
            for _ in range(hold_result["randoms_used"]):
                random.random()
            holder.pos = hold_result["new_pos"]
            holder.distance_covered += hold_result["distance_covered"]
            self.ball.position = holder.pos
            pressure = hold_result["pressure"]
            nearest_dist = hold_result["nearest_dist"]
            if hold_result["is_error"]:
                holder.unforced_errors += 1
                holder.turnovers += 1
                holder.state = PlayerState.OFF_BALL
                self.ball.set_contested(hold_result["loose_pos"])
                self.match_stats.record_contested()
                self.trace.log_event(self.tick, "error", player=holder.name, error_type="shield")
                return

            self.trace.log_action(
                self.tick, holder_team.side, holder.name, "hold",
                hold_ticks=holder.hold_ticks,
                pos=holder.pos,
                opportunity_target=opportunity_target,
                pressure=hold_result["trace_pressure"],
                nearest_def=hold_result["trace_nearest_def"],
            )
            return

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
        if self.ball.flight is None:
            return
        from .rust_adapter import tick_ball_flight_rust

        flight_tick = tick_ball_flight_rust(self.ball.flight)
        self.ball.flight.ticks_elapsed = flight_tick["ticks_elapsed"]
        self.ball.position = flight_tick["position"]
        completed = flight_tick["complete"]

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
            if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
                from .rust_adapter import clearance_arrival_plan_rust

                arrival = clearance_arrival_plan_rust(target_pos, flight, self.home, self.away)
                if arrival["winner_team"] == "home":
                    closest_home = (
                        self.home.players[arrival["player_idx"]]
                        if arrival["player_idx"] is not None and 0 <= arrival["player_idx"] < len(self.home.players)
                        else None
                    )
                    closest_away = None
                else:
                    closest_home = None
                    closest_away = (
                        self.away.players[arrival["player_idx"]]
                        if arrival["player_idx"] is not None and 0 <= arrival["player_idx"] < len(self.away.players)
                        else None
                    )
                passer_completed = arrival["passer_completed"]
            elif getattr(self.config, "rust_clearance_arrival_adapter_enabled", False):
                from .rust_adapter import resolve_clearance_arrival_rust

                arrival = resolve_clearance_arrival_rust(target_pos, self.home, self.away)
                if arrival["winner_team"] == "home":
                    closest_home = (
                        self.home.players[arrival["player_idx"]]
                        if arrival["player_idx"] is not None and 0 <= arrival["player_idx"] < len(self.home.players)
                        else None
                    )
                    closest_away = None
                else:
                    closest_home = None
                    closest_away = (
                        self.away.players[arrival["player_idx"]]
                        if arrival["player_idx"] is not None and 0 <= arrival["player_idx"] < len(self.away.players)
                        else None
                    )
                passer_completed = (
                    (arrival["winner_team"] == "home" and passer_team.side == "home")
                    or (arrival["winner_team"] == "away" and passer_team.side == "away")
                )
            else:
                # Clearance: ball goes to closest player at target
                closest_home = self.home.get_closest_to(target_pos, exclude_gk=False)
                closest_away = self.away.get_closest_to(target_pos, exclude_gk=False)
                d_home = distance(closest_home.pos, target_pos) if closest_home else 999
                d_away = distance(closest_away.pos, target_pos) if closest_away else 999
                if d_home >= d_away:
                    closest_home = None
                else:
                    closest_away = None
                passer_completed = (
                    (closest_home is not None and passer_team.side == "home")
                    or (closest_away is not None and passer_team.side == "away")
                )
            if closest_home is not None:
                self._give_ball(closest_home, self.home)
                if passer_completed:
                    passer_team.players[flight.passer_idx].passes_completed += 1
            elif closest_away is not None:
                self._give_ball(closest_away, self.away)
                if passer_completed:
                    passer_team.players[flight.passer_idx].passes_completed += 1
            return

        self._resolve_pass_arrival(flight, target_pos, passer_team, opp_team)
        return

    def _resolve_pass_arrival(
        self, flight: BallFlight, target_pos: Tuple[float, float],
        passer_team: Team, opp_team: Team
    ):
        """Resolve a pass-to-point arrival as teammate/opponent/loose control."""
        loose_velocity = None
        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import pass_arrival_plan_rust

            arrival = pass_arrival_plan_rust(
                flight,
                target_pos,
                passer_team,
                opp_team,
                self.config,
                target_occupation_weight=0.18,
            )
            winner = arrival["winner"]
            loose_velocity = arrival["loose_velocity"]
            best_receiver = (
                passer_team.players[arrival["receiver_idx"]]
                if arrival["receiver_idx"] is not None and 0 <= arrival["receiver_idx"] < len(passer_team.players)
                else None
            )
            best_opp = (
                opp_team.players[arrival["opponent_idx"]]
                if arrival["opponent_idx"] is not None and 0 <= arrival["opponent_idx"] < len(opp_team.players)
                else None
            )
        else:
            best_receiver, best_receiver_score, _ = self._best_pass_arrival_player(
                flight,
                target_pos,
                passer_team,
                intended_receiver_idx=flight.intended_receiver_idx,
                target_occupation_weight=0.18,
            )
            best_opp, best_opp_score, _ = self._best_pass_arrival_player(
                flight,
                target_pos,
                opp_team,
                intended_receiver_idx=-1,
                target_occupation_weight=0.18,
            )
            receiver_control = self._pass_control_strength(best_receiver_score)
            opponent_control = self._pass_control_strength(best_opp_score)
            loose_control = self._pass_loose_control_strength(receiver_control, opponent_control)
            winner = max(
                (("receiver", receiver_control), ("opponent", opponent_control), ("loose", loose_control)),
                key=lambda item: item[1],
            )[0]

        if winner == "opponent" and best_opp:
            best_opp.interceptions += 1
            self._give_ball(best_opp, opp_team)
            self.trace.log_event(
                self.tick, "interception",
                player=best_opp.name, team=opp_team.side,
                context="normal_pass_arrival",
            )
            return

        if winner == "receiver" and best_receiver:
            self._complete_pass_receive(
                flight,
                target_pos,
                best_receiver,
                passer_team,
                opp_team,
            )
        else:
            # No one close enough -- ball goes contested
            self.ball.set_contested(
                target_pos,
                loose_velocity if loose_velocity is not None else self._residual_ball_velocity(flight, 0.26),
            )
            self.match_stats.record_contested()

    def _resolve_shot_arrival(self, flight: BallFlight):
        """Resolve a shot arriving at (or near) the goal."""
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        shooter = shooter_team.players[flight.passer_idx]

        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import shot_arrival_plan_rust

            save_roll = random.random() if flight.on_target else 0.0
            shot_plan = shot_arrival_plan_rust(
                flight,
                shooter,
                shooter_team,
                defending_team,
                self.config,
                save_roll,
            )
            shooter.shot_log.append(shot_plan["shot_log"])

            if shot_plan["outcome"] == "off_target":
                self._pending_event_text = shot_plan["pending_event_text"]
                self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
                self._record_frame()
                return

            gk = defending_team.goalkeeper
            gk.psxg_faced += shot_plan["psxg_delta"]

            if shot_plan["outcome"] == "saved":
                gk.saves += 1
                self._give_ball(gk, defending_team)
                self._pending_event_text = shot_plan["pending_event_text"]
                self._pending_pause_ms = shot_plan["pause_ms"]
                self.trace.log_event(self.tick, "save", keeper=gk.name, shooter=shooter.name)
                self._record_frame()
                return

            gk.goals_conceded += 1
            self._score_goal(shooter, shooter_team, defending_team)
            return

        if getattr(self.config, "rust_shot_arrival_adapter_enabled", False):
            from .rust_adapter import resolve_shot_arrival_rust

            save_roll = random.random() if flight.on_target else 0.0
            shot_arrival = resolve_shot_arrival_rust(
                flight,
                shooter_team,
                defending_team,
                self.config,
                save_roll,
            )
            in_box = shot_arrival["in_box"]
            save_prob = shot_arrival["save_prob"]
            shot_outcome = shot_arrival["outcome"]
        else:
            in_box = self._is_attacking_box_pos(flight.origin, shooter_team.attacking_right)
            if flight.on_target:
                gk = defending_team.goalkeeper
                save_prob = compute_gk_save_probability(
                    gk, flight.target, flight.origin, self.config
                )
                shot_outcome = "saved" if random.random() < save_prob else "goal"
            else:
                save_prob = 0.0
                shot_outcome = "off_target"

        if not flight.on_target:
            from .rust_adapter import shot_arrival_event_rust, shot_log_entry_rust, shot_log_xg_rust

            shot_log_xg = shot_log_xg_rust(shooter.xg, shooter.shot_log)
            shot_event = shot_arrival_event_rust(shooter.name, "", "off_target")
            shooter.shot_log.append(shot_log_entry_rust(
                flight.origin,
                None,
                shot_log_xg["rounded_xg"],
                in_box,
                "off_target",
            ))
            self._pending_event_text = shot_event["pending_event_text"]
            self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
            self._record_frame()
            return

        gk = defending_team.goalkeeper

        # Track xG for GK
        from .rust_adapter import shot_log_xg_rust

        shot_log_xg = shot_log_xg_rust(shooter.xg, shooter.shot_log)
        last_xg = shot_log_xg["raw_xg"]
        gk.psxg_faced += max(0, last_xg)

        if shot_outcome == "saved":
            # SAVE!
            from .rust_adapter import shot_arrival_event_rust, shot_log_entry_rust

            shot_event = shot_arrival_event_rust(shooter.name, gk.name, "saved")
            gk.saves += 1
            shooter.shot_log.append(shot_log_entry_rust(
                flight.origin,
                flight.target,
                shot_log_xg["rounded_xg"],
                in_box,
                "saved",
            ))
            self._give_ball(gk, defending_team)
            self._pending_event_text = shot_event["pending_event_text"]
            self._pending_pause_ms = shot_event["pause_ms"]
            self.trace.log_event(self.tick, "save", keeper=gk.name, shooter=shooter.name)
            self._record_frame()
        else:
            # GOAL!
            from .rust_adapter import shot_log_entry_rust

            shooter.shot_log.append(shot_log_entry_rust(
                flight.origin,
                flight.target,
                shot_log_xg["rounded_xg"],
                in_box,
                "goal",
            ))
            gk.goals_conceded += 1
            self._score_goal(shooter, shooter_team, defending_team)

    def _pass_control_strength(self, score: float) -> float:
        """Continuous control strength from pass-arrival score."""
        from .rust_adapter import pass_control_strength_rust

        return pass_control_strength_rust(score, self.config)

    def _pass_loose_control_strength(self, teammate_control: float, opponent_control: float) -> float:
        """Continuous loose-ball control when neither side owns the target."""
        from .rust_adapter import pass_loose_control_strength_rust

        return pass_loose_control_strength_rust(teammate_control, opponent_control)

    def _pass_arrival_score(
        self,
        flight: BallFlight,
        player: Player,
        team: Team,
        target: Tuple[float, float],
        intended: bool = False,
        target_occupation_weight: float = 0.0,
    ) -> float:
        speed = player_speed(player.speed_value, self.config.player_max_speed, self.config.player_min_speed)
        target_bias = 0.0
        if intended:
            target_bias += 0.75
        if player.target_pos:
            target_bias += max(0.0, 1.0 - distance(player.target_pos, target) / 16.0) * 0.55
        if player.current_goal is not None:
            target_bias += max(0.0, 1.0 - distance(player.current_goal.target_pos, target) / 16.0) * 0.65
        committed_run = _smoothstep(0.12, 0.82, target_bias)
        movement_share = 0.24 + 0.52 * committed_run
        flight_ticks = max(1, getattr(flight, "ticks_total", 1))
        raw_dist = distance(player.pos, target)
        effective_dist = max(0.0, raw_dist - speed * flight_ticks * movement_share)
        occupation_weight = max(0.0, target_occupation_weight) * (1.0 - 0.55 * committed_run)
        effective_dist += raw_dist * occupation_weight
        if team.side != flight.passer_team:
            effective_dist += max(0.0, target_bias) * 0.18
        return effective_dist

    def _best_pass_arrival_player(
        self,
        flight: BallFlight,
        target_pos: Tuple[float, float],
        team: Team,
        intended_receiver_idx: int = -1,
        target_occupation_weight: float = 0.0,
    ):
        best_player = None
        best_score = float("inf")
        best_dist = float("inf")
        for player in team.players:
            if team.side == flight.passer_team and player.index == flight.passer_idx:
                continue
            dist = distance(player.pos, target_pos)
            score = self._pass_arrival_score(
                flight,
                player,
                team,
                target_pos,
                intended=player.index == intended_receiver_idx,
                target_occupation_weight=target_occupation_weight,
            )
            if score < best_score:
                best_score = score
                best_dist = dist
                best_player = player
        return best_player, best_score, best_dist

    def _complete_pass_receive(
        self,
        flight: BallFlight,
        target_pos: Tuple[float, float],
        receiver: Player,
        passer_team: Team,
        opp_team: Team,
    ) -> None:
        if getattr(self.config, "rust_phase_plan_adapter_enabled", False):
            from .rust_adapter import pass_receive_plan_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            touch_randoms = [rng.random() for _ in range(3)]
            receive_plan = pass_receive_plan_rust(
                receiver,
                target_pos,
                receiver.index in self._offside_flagged,
                self.config,
                touch_randoms,
            )
            for _ in range(receive_plan["randoms_used"]):
                random.random()

            if receive_plan["outcome"] == "first_touch_error":
                receiver.unforced_errors += 1
                self.ball.set_contested(receive_plan["loose_pos"])
                self.match_stats.record_contested()
                self.trace.log_event(
                    self.tick, "error",
                    player=receiver.name, error_type="first_touch",
                )
                return

            if receive_plan["outcome"] == "offside":
                receiver.offsides += 1
                self.ball.set_dead("offside", opp_team.side, restart_ticks=2)
                self._offside_flagged = set()
                self.trace.log_event(
                    self.tick, "offside",
                    player=receiver.name, team=passer_team.side,
                )
                return
            self._offside_flagged = set()

            receive_pos = receive_plan["receive_pos"]
            receiver.pos = receive_pos
            receiver.target_pos = receive_pos
            receiver.distance_covered += receive_plan["distance_covered"]

            self._give_ball(receiver, passer_team, receive_origin=flight.origin)
            passer = passer_team.players[flight.passer_idx]
            passer.passes_completed += 1
            self._track_pass_stats(passer, flight.origin, receive_pos, passer_team.attacking_right)
            self.trace.log_action(
                self.tick, passer_team.side, receiver.name, "receive",
                success=True, pos=receive_pos, receive_kind=receive_plan["receive_kind"],
            )
            return

        if getattr(self.config, "rust_first_touch_adapter_enabled", False):
            from .rust_adapter import resolve_first_touch_rust

            rng = random.Random()
            rng.setstate(random.getstate())
            touch_randoms = [rng.random() for _ in range(3)]
            first_touch = resolve_first_touch_rust(
                receiver,
                target_pos,
                self.config,
                touch_randoms,
            )
            for _ in range(first_touch["randoms_used"]):
                random.random()
            touch_error = first_touch["is_error"]
            loose_pos = first_touch["loose_pos"]
        else:
            iq = receiver.abilities.get("IQ", 50)
            touch_error_chance = (100 - iq) / self.config.first_touch_error_divisor
            touch_error = random.random() < touch_error_chance
            loose_pos = self.pitch.clamp(
                target_pos[0] + random.uniform(-4, 4),
                target_pos[1] + random.uniform(-4, 4),
            ) if touch_error else None
        if touch_error:
            receiver.unforced_errors += 1
            self.ball.set_contested(loose_pos)
            self.match_stats.record_contested()
            self.trace.log_event(
                self.tick, "error",
                player=receiver.name, error_type="first_touch",
            )
            return

        if receiver.index in self._offside_flagged:
            receiver.offsides += 1
            self.ball.set_dead("offside", opp_team.side, restart_ticks=2)
            self._offside_flagged = set()
            self.trace.log_event(
                self.tick, "offside",
                player=receiver.name, team=passer_team.side,
            )
            return
        self._offside_flagged = set()

        old_pos = receiver.pos
        receive_kind = "space" if distance(old_pos, target_pos) > 4.0 else "feet"
        receive_pos = self.pitch.clamp(target_pos[0], target_pos[1])
        receiver.pos = receive_pos
        receiver.target_pos = receive_pos
        receiver.distance_covered += distance(old_pos, receive_pos)

        self._give_ball(receiver, passer_team, receive_origin=flight.origin)
        passer = passer_team.players[flight.passer_idx]
        passer.passes_completed += 1
        self._track_pass_stats(passer, flight.origin, receive_pos, passer_team.attacking_right)
        self.trace.log_action(
            self.tick, passer_team.side, receiver.name, "receive",
            success=True, pos=receive_pos, receive_kind=receive_kind,
        )

    def _score_goal(self, scorer: Player, scoring_team: Team, conceding_team: Team):
        """Record a goal."""
        from .rust_adapter import score_goal_plan_rust

        goal_plan = score_goal_plan_rust(
            scorer,
            scoring_team,
            conceding_team,
            self.home_score,
            self.away_score,
            self.last_passer_team,
            self.last_passer_idx,
            self.tick,
            self.config,
        )
        scorer.goals += 1

        if goal_plan["has_assist"]:
            scoring_team.players[goal_plan["assister_idx"]].assists += 1
        assister_name = goal_plan["assister_name"]
        assister_color = goal_plan["assister_color"]
        self.home_score = goal_plan["home_score"]
        self.away_score = goal_plan["away_score"]

        self.match_stats.record_goal(
            minute=goal_plan["minute"],
            team_side=scoring_team.side,
            scorer_name=scorer.name,
            assister_name=assister_name,
            scorer_color=scorer.color,
            assister_color=assister_color,
        )

        self.trace.log_event(
            self.tick, "goal",
            scorer=scorer.name, team=scoring_team.side,
            assister=assister_name, minute=goal_plan["minute"],
        )

        self._pending_event_text = goal_plan["event_text"]
        self._pending_pause_ms = goal_plan["pause_ms"]
        self._record_frame()

        # Reset for kickoff
        self.ball.set_dead("kickoff", goal_plan["restart_team"], goal_plan["restart_ticks"])

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
        if getattr(self.config, "rust_contested_owner_adapter_enabled", False):
            from .rust_adapter import contested_tick_plan_rust

            contested_plan = contested_tick_plan_rust(
                self.ball,
                self.home,
                self.away,
                self.config,
            )
            self.ball.contested_ticks = contested_plan["contested_ticks"]
            self.ball.position = contested_plan["position"]
            self.ball.loose_velocity = contested_plan["loose_velocity"]
        else:
            self.ball.tick_contested()
        ball_pos = self.pitch.clamp(self.ball.position[0], self.ball.position[1])
        self.ball.position = ball_pos
        self.home.update_phase(False, True, self.config)
        self.away.update_phase(False, True, self.config)
        self._clear_team_goals(self.home)
        self._clear_team_goals(self.away)

        if getattr(self.config, "rust_contested_owner_adapter_enabled", False):
            if contested_plan["winner_team"] == "home":
                best_team = self.home
                best_player = (
                    self.home.players[contested_plan["player_idx"]]
                    if contested_plan["player_idx"] is not None
                    and 0 <= contested_plan["player_idx"] < len(self.home.players)
                    else None
                )
            elif contested_plan["winner_team"] == "away":
                best_team = self.away
                best_player = (
                    self.away.players[contested_plan["player_idx"]]
                    if contested_plan["player_idx"] is not None
                    and 0 <= contested_plan["player_idx"] < len(self.away.players)
                    else None
                )
            else:
                best_team = None
                best_player = None
            best_dist = contested_plan["distance"]
            immediate_win = contested_plan["immediate_win"]
            forced_win = contested_plan["forced_win"]
        else:
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
            immediate_win = best_player is not None and best_dist < self.config.contest_radius
            forced_win = self.ball.contested_ticks > 5 and best_player is not None and best_team is not None

        # If someone is close enough, they win the ball
        if best_player and immediate_win:
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
                if getattr(self.config, "rust_contested_targets_adapter_enabled", False):
                    from .rust_adapter import select_contested_targets_rust

                    contested_targets = select_contested_targets_rust(ball_pos, team, self.config)
                    for p in team.players:
                        result = contested_targets.get(p.index)
                        if result is None:
                            continue
                        p.target_pos = result["target"]
                        p.movement_intent = result["intent"]
                else:
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
            if forced_win and best_player and best_team:
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
        defenders = [
            p for p in opp_team.players
            if not p.is_goalkeeper and p.state != PlayerState.STUNNED
        ]
        ball_is_held_by_holder = (
            self.ball.state == BallState.HELD
            and self.ball.holder_team == holder_team.side
            and self.ball.holder_idx == holder.index
        )
        from .rust_adapter import defensive_pressure_adjust_plan_rust

        pressure_adjustments = defensive_pressure_adjust_plan_rust(
            holder,
            holder_team.attacking_right,
            opp_team.attacking_right,
            holder_action_type,
            ball_is_held_by_holder,
            defenders,
            self.config,
        )
        for defender in defenders:
            adjustment = pressure_adjustments.get(defender.index)
            if adjustment is None:
                continue
            defender.target_pos = adjustment["target"]
            if adjustment["movement_intent"] is not None:
                defender.movement_intent = adjustment["movement_intent"]

    def _adjust_defensive_pressure_targets_after_carry_legacy(
        self,
        holder_team: Team,
        opp_team: Team,
        holder: Player,
        holder_action_type: str,
    ):
        """Legacy Python pressure-target composition for parity checks."""
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

        from .rust_adapter import flight_movement_plan_rust

        movement_plan = flight_movement_plan_rust(
            target_pos,
            self.ball.flight,
            atk_team,
            def_team,
            self.config,
        )

        for p in atk_team.players:
            planned = movement_plan.get((atk_team.side, p.index), {})
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            if planned.get("action") == "attack_ai":
                p.choose_off_ball_attack(
                    target_pos, self.config, self.pitch, atk_team.attacking_right,
                    opponents=def_team.players, teammates=atk_team.players,
                    tick=self.tick,
                    team_side=atk_team.side,
                    trace=self.trace,
                )
            else:
                p.set_movement_target(planned.get("target", p.tactical_anchor), "recover_shape")
            p.move_tick(self.config, self.pitch)

        for p in def_team.players:
            planned = movement_plan.get((def_team.side, p.index), {})
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            if planned.get("action") == "defense_ai":
                p.choose_off_ball_defend(
                    target_pos, self.config, self.pitch, def_team.attacking_right,
                    opponents=atk_team.players, teammates=def_team.players,
                )
            else:
                p.set_movement_target(planned.get("target", p.tactical_anchor), "defend_shape")
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
        from .rust_adapter import track_pass_stats_rust

        stats = track_pass_stats_rust(origin, target, attacking_right, self.config)
        passer.crosses_attempted += stats["crosses_attempted"]
        passer.crosses_completed += stats["crosses_completed"]
        passer.progressive_passes += stats["progressive_passes"]
        passer.long_passes += stats["long_passes"]
        passer.completed_long_passes += stats["completed_long_passes"]
        passer.passes_into_final_third += stats["passes_into_final_third"]
        passer.passes_into_box += stats["passes_into_box"]

    def _track_carry_stats(self, player, old_pos, new_pos, attacking_right: bool):
        """Track progressive carries, carries into box."""
        from .rust_adapter import track_carry_stats_rust

        stats = track_carry_stats_rust(old_pos, new_pos, attacking_right, self.config)
        player.progressive_carries += stats["progressive_carries"]
        player.carries_into_final_third += stats["carries_into_final_third"]
        player.carries_into_box += stats["carries_into_box"]

    def _is_offside(self, receiver, attacking_team, defending_team, pass_origin=None) -> bool:
        """Check if receiver is in an offside position.

        Offside = receiver ahead of 2nd-last defender AND ahead of ball
        at the moment the pass was played, AND in opponent's half.
        pass_origin: ball position when the pass was made.
        """
        from .rust_adapter import is_offside_rust

        ball_x = pass_origin[0] if pass_origin else self.ball.position[0]
        return is_offside_rust(receiver, attacking_team, defending_team, ball_x, self.config)

    def _give_ball(self, player: Player, team: Team, receive_origin: Tuple[float, float] = None):
        """Give the ball to a specific player."""
        from .rust_adapter import give_ball_plan_rust

        give_plan = give_ball_plan_rust(self.ball, player, team, receive_origin)
        # Clear previous holder state
        if give_plan["clear_previous_holder"]:
            previous_team = self.home if give_plan["previous_holder_team"] == "home" else self.away
            previous_idx = give_plan["previous_holder_idx"]
            if 0 <= previous_idx < len(previous_team.players):
                previous_team.players[previous_idx].state = PlayerState.OFF_BALL
                previous_team.players[previous_idx].current_goal = None

        # If ball changes team, clear offside flags (defender touched ball resets offside)
        if give_plan["clear_offside_flags"]:
            self._offside_flagged = set()
        if give_plan["clear_team_goals"]:
            self._clear_team_goals(self.home)
            self._clear_team_goals(self.away)

        player.state = PlayerState.ON_BALL
        player.hold_ticks = 0
        player.possession_ticks = 0
        player.consecutive_carries = 0
        player.last_receive_origin = give_plan["last_receive_origin"]
        player.current_goal = None
        self.ball.set_held(give_plan["new_holder_idx"], team.side, give_plan["ball_pos"])

    # -------------------------------------------------------------------------
    # Restarts
    # -------------------------------------------------------------------------

    def _handle_out_of_bounds(self, pos: Tuple[float, float], flight: BallFlight):
        """Handle ball going out of bounds."""
        passer_team_side = flight.passer_team
        shooter_team = self.home if passer_team_side == "home" else self.away
        shooter = (
            shooter_team.players[flight.passer_idx]
            if flight.flight_type == FlightType.SHOT and 0 <= flight.passer_idx < len(shooter_team.players)
            else None
        )
        from .rust_adapter import out_of_bounds_plan_rust

        out_plan = out_of_bounds_plan_rust(pos, flight, shooter, shooter_team if shooter is not None else None, self.config)
        if shooter is not None and out_plan["shot_log"] is not None:
            shooter.shot_log.append(out_plan["shot_log"])
        self.ball.set_dead(out_plan["reason"], out_plan["restart_team"], out_plan["restart_ticks"])

    def _restart_play(self):
        """Restart play after dead ball."""
        restart_team = self.home if self.ball.restart_team == "home" else self.away
        reason = self.ball.dead_reason
        self._prepare_restart_shape(force=True)
        from .rust_adapter import restart_play_plan_rust

        corner_roll = float(random.randrange(2)) if reason == "corner" else 0.0
        restart = restart_play_plan_rust(
            reason,
            restart_team,
            self.ball.position,
            self.config,
            corner_roll,
        )
        self.ball.position = restart["ball_pos"]
        receiver = (
            restart_team.players[restart["receiver_idx"]]
            if restart["receiver_idx"] is not None
            and 0 <= restart["receiver_idx"] < len(restart_team.players)
            else None
        )
        if receiver is not None:
            if restart["set_receiver_pos"]:
                receiver.pos = restart["ball_pos"]
                receiver.target_pos = restart["ball_pos"]
            self._give_ball(receiver, restart_team)
        if restart["pending_cut"]:
            self._pending_cut = True

        if restart["reset_last_passer"]:
            self.last_passer_idx = -1
            self.last_passer_team = ""
        if restart["clear_offside_flags"]:
            self._offside_flagged = set()  # player indices flagged offside at pass time

    def _prepare_restart_shape(self, force: bool = False):
        """Move players toward restart-specific shape while the ball is dead."""
        if self.ball.restart_team not in ("home", "away"):
            return
        restart_team = self.home if self.ball.restart_team == "home" else self.away
        defending_team = self.away if restart_team.side == "home" else self.home
        from .rust_adapter import restart_shape_plan_rust

        restart_shape = restart_shape_plan_rust(
            self.ball.dead_reason,
            force,
            restart_team,
            defending_team,
            self.config,
        )
        if not restart_shape["has_shape"]:
            return
        for team in (restart_team, defending_team):
            for player in team.players:
                result = restart_shape["targets"].get((team.side, player.index))
                if result is None:
                    continue
                target = result["target"]
                player.state = PlayerState.OFF_BALL
                if force:
                    player.movement_intent = "recover_shape"
                    player.target_pos = target
                    if result["snap"]:
                        player.pos = target
                        player.velocity = (0.0, 0.0)
                    else:
                        player.move_tick(self.config, self.pitch)
                else:
                    player.set_movement_target(target, "recover_shape")
                    player.move_tick(self.config, self.pitch)
        self.ball.position = restart_shape["ball_pos"]

    def _prepare_restart_shape_legacy(self, force: bool = False):
        """Legacy Python composition for restart shape parity fallback."""
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
        from .rust_adapter import must_leave_penalty_area_for_goal_kick_rust

        return must_leave_penalty_area_for_goal_kick_rust(player, restart_team, self.config)

    def _goal_kick_spot(self, team: Team) -> Tuple[float, float]:
        from .rust_adapter import goal_kick_spot_rust

        return goal_kick_spot_rust(team, self.config)

    def _goal_kick_shape_targets(self, restart_team: Team, defending_team: Team) -> List[Tuple[Player, Tuple[float, float]]]:
        """Goal-kick setup using formation depth as a reusable set-piece shape."""
        from .rust_adapter import goal_kick_shape_targets_rust

        rust_targets = goal_kick_shape_targets_rust(restart_team, defending_team, self.config)
        targets: List[Tuple[Player, Tuple[float, float]]] = []
        for team in (restart_team, defending_team):
            for player in team.players:
                target = rust_targets.get((team.side, player.index))
                if target is not None and player is not restart_team.goalkeeper:
                    targets.append((player, target))
        targets.append((restart_team.goalkeeper, self._goal_kick_spot(restart_team)))
        return targets

    def _kickoff_shape_targets(self, restart_team: Team, other_team: Team) -> List[Tuple[Player, Tuple[float, float]]]:
        """Kickoff setup compressed into each team's own half."""
        from .rust_adapter import kickoff_shape_targets_rust

        shape = kickoff_shape_targets_rust(restart_team, other_team, self.config)
        targets: List[Tuple[Player, Tuple[float, float]]] = []
        for team in (restart_team, other_team):
            for player in team.players:
                target = shape["targets"].get((team.side, player.index))
                if target is not None:
                    targets.append((player, target))
        return targets

    def _kickoff(self, team_side: str):
        """Set up kickoff for a team.
        
        Keep each team's original shape, compressed into its own half.
        The kicking team sends one forward to the center spot.
        """
        self.ball.position = self.pitch.center
        team = self.home if team_side == "home" else self.away
        other_team = self.away if team_side == "home" else self.home
        targets = self._kickoff_shape_targets(team, other_team)
        kicker = None
        for player, target in targets:
            player.pos = target
            player.target_pos = target
            player.tactical_anchor = target
            if target == self.pitch.center and player.team_side == team.side:
                kicker = player
        if kicker:
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
