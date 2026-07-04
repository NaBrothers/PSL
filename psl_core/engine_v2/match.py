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

    def _tick(self):
        """Execute one simulation tick using the 3-phase model.

        Phase 1: All players choose actions simultaneously
        Phase 2: Detect interactions
        Phase 3: Resolve interactions, execute non-conflicting, check errors
        """
        # Handle dead ball (waiting for restart)
        if self.ball.state == BallState.DEAD:
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

        # Tick stun timers
        for p in self.home.players + self.away.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)

        holder_team = self.home if self.ball.holder_team == "home" else self.away
        opp_team = self.away if self.ball.holder_team == "home" else self.home
        holder = holder_team.players[self.ball.holder_idx]

        # =====================================================================
        # PHASE 1: All players choose actions simultaneously
        # =====================================================================

        # Holder chooses on-ball action
        holder_action_type, holder_details = holder.choose_on_ball(
            holder_team.players,
            opp_team.players,
            self.config,
            self.pitch,
            holder_team.attacking_right,
        )

        # Off-ball players choose actions
        defender_actions = {}  # {player.index: action_type}
        defender_new_positions = {}  # {player.index: new_pos}

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

        # Attacking team off-ball choose positions
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
            )

        # =====================================================================
        # PHASE 2: Detect interactions
        # =====================================================================

        duel_interaction = None
        interception_interaction = None
        wasted_tackles = []

        if holder_action_type == "carry":
            # Duel detection: holder carries + defender tackles within range
            duel_interaction = detect_duel(
                holder, "carry", opp_team.players, defender_actions, self.config
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

        # =====================================================================
        # PHASE 3: Resolve interactions, execute actions, check errors
        # =====================================================================

        # Handle wasted tackles first (defender stunned for nothing)
        for wt in wasted_tackles:
            wt.defender.apply_stun(self.config)
            wt.defender.tackles_attempted += 1
            self.trace.log_event(
                self.tick, "wasted_tackle",
                player=wt.defender.name, team=opp_team.side,
            )

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
        elif holder_action_type == "clear":
            self._execute_clear_phase3(holder, holder_details, holder_team, opp_team)

        # Move all off-ball players
        self._move_off_ball_players(holder_team, opp_team, holder)

        # Track possession
        if self.ball.holder_team:
            self.match_stats.record_possession(self.ball.holder_team)

    # -------------------------------------------------------------------------
    # Phase 3: Action execution
    # -------------------------------------------------------------------------

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
        target = details.get("target", holder.pos)

        # Move toward target at carrier speed
        carry_speed = self.config.carrier_speed
        old_pos = holder.pos
        new_pos = move_toward(holder.pos, target, carry_speed)
        new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
        holder.pos = new_pos
        holder.distance_covered += distance(old_pos, new_pos)
        self.ball.position = new_pos

        # Unforced carry error: (100-Dribbling)/600
        dribbling = holder.abilities.get("Dribbling", 50)
        error_chance = (100 - dribbling) / self.config.carry_error_divisor
        if random.random() < error_chance:
            # Ball goes loose
            holder.unforced_errors += 1
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
            self.trace.log_action(
                self.tick, holder_team.side, holder.name, "carry",
                success=True, pos=new_pos,
            )

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
        target = details.get("target", passer.pos)
        is_long = details.get("is_long", False)

        # Pass accuracy unforced error: (100-Passing)/500
        passing = passer.abilities.get("Short_Passing", 50)
        if is_long:
            passing = passer.abilities.get("Long_Passing", 50)
        error_chance = (100 - passing) / self.config.pass_error_divisor
        if random.random() < error_chance:
            # Pass goes astray -- ball contested
            passer.unforced_errors += 1
            passer.state = PlayerState.OFF_BALL
            stray_pos = self.pitch.clamp(
                target[0] + random.uniform(-8, 8),
                target[1] + random.uniform(-8, 8),
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

        flight = BallFlight(
            origin=passer.pos,
            target=target,
            flight_type=flight_type,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=passer.index,
            passer_team=passer_team.side,
        )

        self.last_passer_idx = passer.index
        self.last_passer_team = passer_team.side
        passer.state = PlayerState.OFF_BALL
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, passer_team.side, passer.name,
            "long_pass" if is_long else "short_pass",
            target=target, target_player=details.get("target_player_idx", -1),
        )

        self._pending_ball_flight = build_ball_flight_data(
            passer.pos, target, "pass", on_target=False
        )

    def _execute_shoot_phase3(
        self, shooter: Player, details: dict, shooter_team: Team, opp_team: Team
    ):
        """Execute shot action."""
        shooter.shots += 1

        on_target_prob = details.get("on_target_prob", 0.3)
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
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, clearer_team.side, clearer.name, "clear",
            target=target,
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

            # Pass completed successfully
            self._give_ball(best_receiver, passer_team)
            passer_team.players[flight.passer_idx].passes_completed += 1
            self.trace.log_action(
                self.tick, passer_team.side, best_receiver.name, "receive",
                success=True,
            )
        else:
            # No one close enough -- ball goes contested
            self.ball.set_contested(target_pos)
            self.match_stats.record_contested()

    def _resolve_shot_arrival(self, flight: BallFlight):
        """Resolve a shot arriving at (or near) the goal."""
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        shooter = shooter_team.players[flight.passer_idx]

        if not flight.on_target:
            self._pending_event_text = f"{shooter.name}'s shot goes wide!"
            self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
            self._record_frame()
            return

        # Shot is on target - GK save check
        gk = defending_team.goalkeeper
        save_prob = compute_gk_save_probability(
            gk, flight.target, flight.origin, self.config
        )

        if random.random() < save_prob:
            # SAVE!
            gk.saves += 1
            self._give_ball(gk, defending_team)
            self._pending_event_text = f"{gk.name} saves {shooter.name}'s shot!"
            self._pending_pause_ms = 1000
            self.trace.log_event(self.tick, "save", keeper=gk.name, shooter=shooter.name)
            self._record_frame()
        else:
            # GOAL!
            self._score_goal(shooter, shooter_team, defending_team)

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
        ball_pos = self.ball.position

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
            # Players race toward ball
            for p in self.home.players + self.away.players:
                if p.state != PlayerState.STUNNED:
                    p.target_pos = ball_pos
            # Move all players toward ball
            self.home.move_all(self.config, self.pitch)
            self.away.move_all(self.config, self.pitch)

            # If contested too long, award to closest
            if self.ball.contested_ticks > 5 and best_player and best_team:
                self._give_ball(best_player, best_team)

        # Track possession (neutral during contested)
        self.match_stats.record_possession("")

    # -------------------------------------------------------------------------
    # Movement helpers
    # -------------------------------------------------------------------------

    def _move_off_ball_players(self, holder_team: Team, opp_team: Team, holder: Player):
        """Move all off-ball players one tick."""
        # Update dynamic formations
        holder_team.compute_dynamic_positions(self.ball.position, self.config, self.pitch)
        opp_team.compute_dynamic_positions(self.ball.position, self.config, self.pitch)

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
        passer_team_side = self.ball.flight.passer_team if self.ball.flight else ""

        # Attacking team repositions
        atk_team = self.home if passer_team_side == "home" else self.away
        def_team = self.away if passer_team_side == "home" else self.home

        for p in atk_team.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            p.choose_off_ball_attack(
                ball_pos, self.config, self.pitch, atk_team.attacking_right,
                opponents=def_team.players, teammates=atk_team.players,
            )
            p.move_tick(self.config, self.pitch)

        for p in def_team.players:
            if p.state == PlayerState.STUNNED:
                p.tick_stun(self.config)
                continue
            p.choose_off_ball_defend(
                ball_pos, self.config, self.pitch, def_team.attacking_right,
                opponents=atk_team.players, teammates=def_team.players,
            )
            p.move_tick(self.config, self.pitch)

    # -------------------------------------------------------------------------
    # Ball possession
    # -------------------------------------------------------------------------

    def _give_ball(self, player: Player, team: Team):
        """Give the ball to a specific player."""
        # Clear previous holder state
        if self.ball.holder_team == "home" and self.ball.holder_idx >= 0:
            if self.ball.holder_idx < len(self.home.players):
                self.home.players[self.ball.holder_idx].state = PlayerState.OFF_BALL
        elif self.ball.holder_team == "away" and self.ball.holder_idx >= 0:
            if self.ball.holder_idx < len(self.away.players):
                self.away.players[self.ball.holder_idx].state = PlayerState.OFF_BALL

        player.state = PlayerState.ON_BALL
        self.ball.set_held(player.index, team.side, player.pos)

    # -------------------------------------------------------------------------
    # Restarts
    # -------------------------------------------------------------------------

    def _handle_out_of_bounds(self, pos: Tuple[float, float], flight: BallFlight):
        """Handle ball going out of bounds."""
        passer_team_side = flight.passer_team
        other_team = "away" if passer_team_side == "home" else "home"

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

        if reason == "kickoff":
            self.ball.position = self.pitch.center
            closest = restart_team.get_closest_to(self.pitch.center, exclude_gk=True)
            if closest:
                closest.pos = (self.pitch.center[0], self.pitch.center[1])
                self._give_ball(closest, restart_team)
                self._pending_cut = True

        elif reason == "goal_kick":
            gk = restart_team.goalkeeper
            if restart_team.attacking_right:
                gk.pos = (6.0, self.pitch.width / 2.0)
            else:
                gk.pos = (self.config.pitch_length - 6.0, self.pitch.width / 2.0)
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

        self.last_passer_idx = -1
        self.last_passer_team = ""

    def _kickoff(self, team_side: str):
        """Set up kickoff for a team."""
        self.ball.position = self.pitch.center
        team = self.home if team_side == "home" else self.away

        closest = team.get_closest_to(self.pitch.center, exclude_gk=True)
        if closest:
            closest.pos = self.pitch.center
            self._give_ball(closest, team)
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
        return MatchResult(
            home_score=self.home_score,
            away_score=self.away_score,
            goals=self.match_stats.goals,
            home_stats=self.match_stats.get_home_stats(self.home),
            away_stats=self.match_stats.get_away_stats(self.away),
            home_player_stats=self.home.get_player_stats(),
            away_player_stats=self.away.get_player_stats(),
            home_ratings=compute_team_ratings(
                self.home.players, self.home_score, self.away_score
            ),
            away_ratings=compute_team_ratings(
                self.away.players, self.away_score, self.home_score
            ),
            replay_url=None,
            trace_id=self.trace.trace_id,
        )
