"""Main match loop: orchestrates the tick-based simulation (Phase 2).

Phase 2 changes:
- Three-state ball ownership (HOME_POSSESSED / AWAY_POSSESSED / CONTESTED)
- Team phase detection (5 states)
- Aerial/heading contest system
- Goalkeeper model integration
- CARRY and CROSS action execution
- Formation dynamics
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
from .vision import get_visible_targets
from .goalkeeper import compute_gk_save_probability, should_rush_out, choose_distribution
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
    """Tick-based football match simulation engine (Phase 2).

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

        # Phase 2: possession tracking for transitions
        self._possession_changed_tick = -99
        self._last_ball_holder_idx = -1
        self._last_ball_holder_team = None

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
        """Execute one simulation tick."""
        # Reset _ticks_with_ball when holder changes
        current_holder = self.ball.holder_idx
        current_team = self.ball.holder_team
        if current_holder != self._last_ball_holder_idx or current_team != self._last_ball_holder_team:
            # New holder - reset their counter
            if current_holder >= 0 and current_team:
                team = self.home if current_team == "home" else self.away
                if current_holder < len(team.players):
                    team.players[current_holder]._ticks_with_ball = 0
            self._last_ball_holder_idx = current_holder
            self._last_ball_holder_team = current_team

        # 1. Handle dead ball
        if self.ball.state == BallState.DEAD:
            if self.ball.tick_dead():
                self._restart_play()
            return

        # 2. Handle ball in flight
        if self.ball.state == BallState.IN_FLIGHT:
            self._tick_flight()
            self._update_team_phases()
            self._move_players()
            return

        # 3. Handle contested ball (Phase 2)
        if self.ball.state == BallState.CONTESTED:
            self._tick_contested()
            self._update_team_phases()
            self._move_players()
            return

        # 4. Ball is held - the holder makes a decision
        if self.ball.state == BallState.HELD:
            self._tick_held()

        # 5. Update team phases
        self._update_team_phases()

        # 6. Move off-ball players
        self._move_players()

        # 7. Check for contests (pressing player reaches ball carrier)
        self._check_contests()

        # 8. Track possession
        if self.ball.holder_team:
            self.match_stats.record_possession(self.ball.holder_team)

    def _update_team_phases(self):
        """Update both teams' phase states based on current ball ownership."""
        ball_contested = self.ball.ownership == BallOwnership.CONTESTED

        home_has_ball = self.ball.holder_team == "home" or (
            self.ball.flight and self.ball.flight.passer_team == "home"
            and self.ball.state == BallState.IN_FLIGHT
        )
        away_has_ball = self.ball.holder_team == "away" or (
            self.ball.flight and self.ball.flight.passer_team == "away"
            and self.ball.state == BallState.IN_FLIGHT
        )

        self.home.update_phase(home_has_ball, ball_contested, self.config)
        self.away.update_phase(away_has_ball, ball_contested, self.config)

    def _tick_held(self):
        """Process a tick where a player holds the ball."""
        holder_team = self.home if self.ball.holder_team == "home" else self.away
        holder = holder_team.players[self.ball.holder_idx]
        opponents = self.away if self.ball.holder_team == "home" else self.home

        # Get team phase for scoring
        phase = holder_team.phase_name

        # Holder chooses action
        action = holder.choose_action(
            holder_team.players,
            opponents.players,
            self.config,
            self.pitch,
            holder_team.attacking_right,
            phase=phase,
        )

        if action is None:
            return

        # Execute the action
        self._execute_action(holder, action, holder_team, opponents)
        # HOLD means "do nothing else this tick"
        if action.action_type == ActionType.HOLD:
            return

    def _tick_flight(self):
        """Process a tick where the ball is in flight."""
        completed = self.ball.tick_flight()

        if not completed:
            self._check_interceptions()
            return

        # Flight complete - resolve arrival
        self._resolve_flight_arrival()

    def _tick_contested(self):
        """Process a tick where the ball is contested (loose).

        Players race to ball based on Speed.
        Distant players pre-position based on IQ.
        """
        self.ball.tick_contested()
        ball_pos = self.ball.position

        # Find closest player from each team
        home_closest = self.home.get_closest_to(ball_pos, exclude_gk=True)
        away_closest = self.away.get_closest_to(ball_pos, exclude_gk=True)

        # Players within race radius compete
        home_racers = self.home.get_players_in_radius(ball_pos, self.config.contested_race_radius)
        away_racers = self.away.get_players_in_radius(ball_pos, self.config.contested_race_radius)

        # Find the absolute closest player
        best_player = None
        best_team = None
        best_dist = float("inf")

        for p in home_racers:
            d = distance(p.pos, ball_pos)
            if d < best_dist:
                best_dist = d
                best_player = p
                best_team = self.home

        for p in away_racers:
            d = distance(p.pos, ball_pos)
            if d < best_dist:
                best_dist = d
                best_player = p
                best_team = self.away

        # If someone is close enough, they win the ball
        if best_player and best_dist < self.config.contest_radius:
            self._give_ball(best_player, best_team)
            self._possession_changed_tick = self.tick
            self.trace.log_event(
                self.tick, "contested_won",
                player=best_player.name, team=best_team.side,
            )
            return

        # Otherwise, players race toward ball
        for p in home_racers + away_racers:
            if not p.is_goalkeeper:
                p.target_pos = ball_pos

        # If contested too long (> 5 ticks), award to closest
        if self.ball.contested_ticks > 5 and best_player and best_team:
            self._give_ball(best_player, best_team)

    def _execute_action(self, holder: Player, action: Action, holder_team: Team, opponents: Team):
        """Execute a player's chosen action."""
        if action.action_type == ActionType.SHORT_PASS:
            self._execute_pass(holder, action, holder_team, opponents, is_long=False)
        elif action.action_type == ActionType.LONG_PASS:
            self._execute_pass(holder, action, holder_team, opponents, is_long=True)
        elif action.action_type == ActionType.SHOOT:
            self._execute_shot(holder, action, holder_team, opponents)
        elif action.action_type == ActionType.DRIBBLE:
            self._execute_dribble(holder, action, holder_team, opponents)
        elif action.action_type == ActionType.CARRY:
            self._execute_carry(holder, action, holder_team, opponents)
        elif action.action_type == ActionType.CROSS:
            self._execute_cross(holder, action, holder_team, opponents)
        elif action.action_type == ActionType.HOLD:
            self._execute_hold(holder, action, holder_team)

    def _execute_pass(
        self, passer: Player, action: Action, passer_team: Team, opponents: Team, is_long: bool
    ):
        """Execute a pass action."""
        passer.passes_attempted += 1

        speed = self.config.ball_long_pass_speed if is_long else self.config.ball_pass_speed
        flight_type = FlightType.LONG_PASS if is_long else FlightType.SHORT_PASS

        dist = distance(passer.pos, action.target)
        ticks_needed = max(1, round(dist / speed))

        # Only very long passes (>40m) are truly aerial
        is_aerial = is_long and dist > 40.0

        flight = BallFlight(
            origin=passer.pos,
            target=action.target,
            flight_type=flight_type,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=passer.index,
            passer_team=passer_team.side,
            is_aerial=is_aerial,
        )

        self.last_passer_idx = passer.index
        self.last_passer_team = passer_team.side

        passer.state = PlayerState.OFF_BALL
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, passer_team.side, passer.name,
            "long_pass" if is_long else "short_pass",
            target=action.target, target_player=action.target_player_idx,
        )

        ft = "pass"
        self._pending_ball_flight = build_ball_flight_data(
            passer.pos, action.target, ft, on_target=False
        )

    def _execute_shot(self, shooter: Player, action: Action, shooter_team: Team, opponents: Team):
        """Execute a shot action."""
        shooter.shots += 1

        on_target = random.random() < action.success_prob
        if on_target:
            shooter.shots_on_target += 1

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
        ticks_needed = max(1, round(dist / self.config.ball_shot_speed))

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

    def _execute_carry(self, carrier: Player, action: Action, carrier_team: Team, opponents: Team):
        """Execute a CARRY action (open space forward movement).

        Speed determines distance (8-15m). Success 85-95%.
        """
        carrier.carries_attempted += 1

        success = random.random() < action.success_prob

        if success:
            carrier.carries_completed += 1
            # Move carrier toward target
            speed = carrier.get_move_speed(self.config)
            carry_dist = self.config.carry_min_distance + (
                self.config.carry_max_distance - self.config.carry_min_distance
            ) * carrier.speed_value / 100.0
            new_pos = move_toward(carrier.pos, action.target, min(speed, carry_dist))
            new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
            carrier.distance_covered += distance(carrier.pos, new_pos)
            carrier.pos = new_pos
            self.ball.position = new_pos

            self.trace.log_action(
                self.tick, carrier_team.side, carrier.name, "carry",
                success=True, distance=round(distance(carrier.pos, new_pos), 1),
            )
        else:
            # Carry failed - ball goes loose
            carrier.state = PlayerState.OFF_BALL
            loose_pos = (
                carrier.pos[0] + random.uniform(-3, 3),
                carrier.pos[1] + random.uniform(-3, 3),
            )
            loose_pos = self.pitch.clamp(loose_pos[0], loose_pos[1])
            self.ball.set_contested(loose_pos)
            self._possession_changed_tick = self.tick
            self.trace.log_action(
                self.tick, carrier_team.side, carrier.name, "carry", success=False,
            )

    def _execute_dribble(self, dribbler: Player, action: Action, dribbler_team: Team, opponents: Team):
        """Execute a DRIBBLE action (1v1 take-on under pressure).

        Dribbling vs Tackling contest. Displacement 3-5m. Success 40-70%.
        """
        dribbler.dribbles_attempted += 1

        success = random.random() < action.success_prob

        if success:
            dribbler.dribbles_completed += 1
            # Move dribbler past defender (3-5m)
            dribble_dist = random.uniform(3.0, 5.0)
            new_pos = move_toward(dribbler.pos, action.target, dribble_dist)
            new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
            dribbler.distance_covered += distance(dribbler.pos, new_pos)
            dribbler.pos = new_pos
            self.ball.position = new_pos

            self.trace.log_action(
                self.tick, dribbler_team.side, dribbler.name, "dribble", success=True
            )
        else:
            # Dribble failed - loss of possession
            closest_opp = opponents.get_closest_to(dribbler.pos, exclude_gk=True)
            if closest_opp:
                closest_opp.tackles_attempted += 1
                closest_opp.tackles_won += 1
                self._give_ball(closest_opp, opponents)
                self._possession_changed_tick = self.tick
                self.trace.log_action(
                    self.tick, dribbler_team.side, dribbler.name, "dribble",
                    success=False, tackled_by=closest_opp.name
                )
            else:
                # Ball goes loose
                dribbler.state = PlayerState.OFF_BALL
                self.ball.set_contested(dribbler.pos)
                self._possession_changed_tick = self.tick

    def _execute_cross(self, crosser: Player, action: Action, crosser_team: Team, opponents: Team):
        """Execute a CROSS action (aerial delivery into box).

        Uses Long_Passing for accuracy. Ball is aerial -> triggers heading contest.
        """
        crosser.crosses_attempted += 1
        crosser.passes_attempted += 1

        target = action.target
        dist = distance(crosser.pos, target)
        speed = self.config.ball_long_pass_speed
        ticks_needed = max(1, round(dist / speed))

        flight = BallFlight(
            origin=crosser.pos,
            target=target,
            flight_type=FlightType.CROSS,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=crosser.index,
            passer_team=crosser_team.side,
            is_aerial=True,  # Crosses are always aerial
        )

        self.last_passer_idx = crosser.index
        self.last_passer_team = crosser_team.side

        crosser.state = PlayerState.OFF_BALL
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, crosser_team.side, crosser.name, "cross",
            target=target,
        )

        self._pending_ball_flight = build_ball_flight_data(
            crosser.pos, target, "pass", on_target=False
        )


    def _execute_hold(self, holder, action, holder_team):
        """Execute HOLD: player keeps the ball, no action this tick."""
        self.trace.log_action(self.tick, holder_team.side, holder.name, "hold")
    def _resolve_flight_arrival(self):
        """Resolve what happens when a ball flight completes."""
        flight = self.ball.flight
        if flight is None:
            return

        target_pos = flight.target

        # Check if it's a shot
        if flight.flight_type == FlightType.SHOT:
            self._resolve_shot_arrival(flight)
            return

        # Check if out of bounds
        if self.pitch.is_out_of_bounds(target_pos[0], target_pos[1]):
            self._handle_out_of_bounds(target_pos, flight)
            return

        # Aerial ball -> heading contest (Phase 2)
        if flight.is_aerial:
            self._resolve_aerial_arrival(flight)
            return

        # Ground pass - find receiver
        passer_team = self.home if flight.passer_team == "home" else self.away
        opp_team = self.away if flight.passer_team == "home" else self.home

        receiver = passer_team.get_closest_to(target_pos, exclude_indices=[flight.passer_idx])
        closest_opp = opp_team.get_closest_to(target_pos)

        if receiver is None:
            if closest_opp:
                self._give_ball(closest_opp, opp_team)
                self._possession_changed_tick = self.tick
            return

        recv_dist = distance(receiver.pos, target_pos)
        opp_dist = distance(closest_opp.pos, target_pos) if closest_opp else 999

        if opp_dist < recv_dist and opp_dist < 5.0:
            if closest_opp:
                closest_opp.interceptions += 1
                self._give_ball(closest_opp, opp_team)
                self._possession_changed_tick = self.tick
                self.trace.log_event(self.tick, "interception", player=closest_opp.name)
        else:
            passer = passer_team.players[flight.passer_idx]
            passer.passes_completed += 1
            # If this was a cross, mark it completed
            if flight.flight_type == FlightType.CROSS:
                passer.crosses_completed += 1
            self._give_ball(receiver, passer_team)

    def _resolve_aerial_arrival(self, flight: BallFlight):
        """Resolve an aerial ball arrival - heading contest (Phase 2).

        All players within heading_contest_radius compete.
        Each rolls: Heading * random(0.8, 1.2) / (distance_to_landing + 1)
        Winner can: header shot, headed pass, or ball drops loose.
        """
        target_pos = flight.target
        passer_team = self.home if flight.passer_team == "home" else self.away
        opp_team = self.away if flight.passer_team == "home" else self.home

        # Find all players within heading contest radius
        home_in_range = self.home.get_players_in_radius(target_pos, self.config.heading_contest_radius)
        away_in_range = self.away.get_players_in_radius(target_pos, self.config.heading_contest_radius)

        all_contestants = []
        for p in home_in_range:
            all_contestants.append((p, self.home))
        for p in away_in_range:
            all_contestants.append((p, self.away))

        if not all_contestants:
            # No one near landing point - ball goes loose
            self.ball.set_contested(target_pos)
            self._possession_changed_tick = self.tick
            return

        # Each player rolls: Heading * random(0.8, 1.2) / (dist + 1)
        best_roll = -1.0
        winner = None
        winner_team = None

        for p, team in all_contestants:
            heading = p.abilities.get("Heading", 50)
            d = distance(p.pos, target_pos)
            roll = heading * random.uniform(0.8, 1.2) / (d + 1.0)
            p.headers_attempted += 1
            if roll > best_roll:
                best_roll = roll
                winner = p
                winner_team = team

        if winner is None:
            self.ball.set_contested(target_pos)
            return

        winner.headers_won += 1

        # Determine what winner does with the header
        # Check if passer gets an assist (pass completed)
        passer = passer_team.players[flight.passer_idx]
        if winner_team == passer_team and winner.index != passer.index:
            passer.passes_completed += 1
            if flight.flight_type == FlightType.CROSS:
                passer.crosses_completed += 1

        # Winner options:
        # 1. Header shot (if near goal)
        # 2. Headed pass (give ball to winner)
        # 3. Ball drops loose (CONTESTED)
        if winner_team:
            goal_center = (
                self.pitch.away_goal_center() if winner_team.attacking_right
                else self.pitch.home_goal_center()
            )
            dist_to_goal = distance(winner.pos, goal_center)

            # Header shot if close to goal
            if dist_to_goal < self.config.heading_shot_distance and not winner.is_goalkeeper:
                self._execute_header_shot(winner, winner_team, goal_center)
            elif random.random() < self.config.heading_loose_ball_prob:
                # Ball drops loose
                loose_pos = self.pitch.clamp(
                    target_pos[0] + random.uniform(-3, 3),
                    target_pos[1] + random.uniform(-3, 3),
                )
                self.ball.set_contested(loose_pos)
                self._possession_changed_tick = self.tick
                self.trace.log_event(
                    self.tick, "header_loose",
                    player=winner.name,
                )
            else:
                # Winner controls the ball
                self._give_ball(winner, winner_team)

        self.trace.log_event(
            self.tick, "aerial_contest",
            winner=winner.name if winner else "",
            contestants=len(all_contestants),
        )

    def _execute_header_shot(self, header: Player, header_team: Team, goal_center: Tuple[float, float]):
        """Execute a header shot on goal."""
        header.shots += 1

        heading = header.abilities.get("Heading", 50) / 100.0
        finishing = header.abilities.get("Finishing", 50) / 100.0
        ability = (heading * 0.6 + finishing * 0.4)

        dist = distance(header.pos, goal_center)
        dist_factor = max(0.3, 1.0 - dist / self.config.heading_shot_distance)

        on_target_prob = 0.45 * (0.4 + 0.6 * ability) * dist_factor
        on_target_prob = max(0.1, min(0.70, on_target_prob))

        on_target = random.random() < on_target_prob
        if on_target:
            header.shots_on_target += 1

        if on_target:
            target_y = random.uniform(self.pitch.goal_y_min + 0.5, self.pitch.goal_y_max - 0.5)
            if header_team.attacking_right:
                target = (self.config.pitch_length, target_y)
            else:
                target = (0.0, target_y)
        else:
            if header_team.attacking_right:
                target_x = self.config.pitch_length + random.uniform(0.5, 3.0)
            else:
                target_x = -random.uniform(0.5, 3.0)
            target_y = random.uniform(self.pitch.goal_y_min - 3, self.pitch.goal_y_max + 3)
            target = (target_x, target_y)

        dist_to_target = distance(header.pos, target)
        ticks_needed = max(1, round(dist_to_target / self.config.ball_shot_speed))

        flight = BallFlight(
            origin=header.pos,
            target=target,
            flight_type=FlightType.SHOT,
            speed=self.config.ball_shot_speed,
            ticks_total=ticks_needed,
            passer_idx=header.index,
            passer_team=header_team.side,
            on_target=on_target,
        )

        self.last_passer_idx = header.index
        self.last_passer_team = header_team.side

        header.state = PlayerState.OFF_BALL
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, header_team.side, header.name, "header_shot",
            on_target=on_target,
        )

        self._pending_ball_flight = build_ball_flight_data(
            header.pos, target, "shot", on_target=on_target
        )
        self._pending_event_text = f"HEADER! {header.name} heads for goal!"

    def _resolve_shot_arrival(self, flight: BallFlight):
        """Resolve a shot arriving at (or near) the goal."""
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        shooter = shooter_team.players[flight.passer_idx]

        target_pos = flight.target

        if not flight.on_target:
            self._pending_event_text = f"{shooter.name}'s shot goes wide!"
            self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
            self._record_frame()
            return

        # Shot is on target - use GK model (Phase 2)
        gk = defending_team.goalkeeper

        # Compute save probability using the 3-stage GK model
        save_prob = compute_gk_save_probability(
            gk, target_pos, flight.origin, self.config
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

    def _check_contests(self):
        """Check if the designated presser triggers a contest."""
        if self.ball.state != BallState.HELD:
            return

        holder_team = self.home if self.ball.holder_team == "home" else self.away
        opp_team = self.away if self.ball.holder_team == "home" else self.home
        holder = holder_team.players[self.ball.holder_idx]

        # Only the designated presser can trigger a contest
        # And only if they are actively pressing (not just standing nearby)
        for opp in opp_team.players:
            if opp.is_goalkeeper:
                continue
            if opp.state != PlayerState.PRESSING:
                continue
            d = distance(opp.pos, holder.pos)
            if d < self.config.contest_radius:
                self._resolve_contest(holder, opp, holder_team, opp_team)
                return

    def _resolve_contest(
        self, holder: Player, challenger: Player, holder_team: Team, opp_team: Team
    ):
        """Resolve a 1v1 contest between dribbler and tackler."""
        holder.state = PlayerState.CONTEST
        challenger.state = PlayerState.CONTEST
        challenger.tackles_attempted += 1

        dribbling = holder.abilities.get("Dribbling", 50)
        tackling = challenger.abilities.get("Tackling", 50)

        holder_strength = dribbling / (dribbling + tackling + 1)
        holder_strength += random.uniform(-0.1, 0.1)
        holder_strength = max(0.15, min(0.85, holder_strength))

        if random.random() < holder_strength:
            # Holder keeps ball
            holder.state = PlayerState.ON_BALL
            challenger.state = PlayerState.OFF_BALL
            holder.dribbles_attempted += 1
            holder.dribbles_completed += 1
        else:
            # Challenger wins ball
            challenger.tackles_won += 1

            # Phase 2: sometimes ball goes loose instead of clean tackle
            if random.random() < 0.25:
                # Ball goes loose - CONTESTED
                holder.state = PlayerState.OFF_BALL
                challenger.state = PlayerState.OFF_BALL
                loose_pos = self.pitch.clamp(
                    holder.pos[0] + random.uniform(-3, 3),
                    holder.pos[1] + random.uniform(-2, 2),
                )
                self.ball.set_contested(loose_pos)
                self._possession_changed_tick = self.tick
                self.trace.log_event(
                    self.tick, "tackle_loose",
                    tackler=challenger.name, dispossessed=holder.name,
                )
            else:
                # Clean tackle - challenger gets ball
                self._give_ball(challenger, opp_team)
                holder.state = PlayerState.OFF_BALL
                self._possession_changed_tick = self.tick
                self.trace.log_event(
                    self.tick, "tackle",
                    tackler=challenger.name, dispossessed=holder.name,
                )

    def _check_interceptions(self):
        """Check if any defender intercepts a ball in flight."""
        if self.ball.flight is None:
            return

        flight = self.ball.flight
        ball_pos = self.ball.position
        passer_team_side = flight.passer_team
        opp_team = self.away if passer_team_side == "home" else self.home

        for opp in opp_team.players:
            d = distance(opp.pos, ball_pos)
            if d < self.config.interception_radius:
                defence = opp.abilities.get("Defence", 50) / 100.0
                intercept_chance = self.config.interception_base_chance * (0.5 + defence)
                proximity_bonus = max(0, 1.0 - d / self.config.interception_radius) * 0.15
                total_chance = intercept_chance + proximity_bonus

                if random.random() < total_chance:
                    opp.interceptions += 1
                    self._give_ball(opp, opp_team)
                    self._possession_changed_tick = self.tick
                    self.trace.log_event(self.tick, "interception", player=opp.name)
                    return

    def _move_players(self):
        """Move all players and update their targets."""
        home_has_ball = self.ball.holder_team == "home" or (
            self.ball.flight and self.ball.flight.passer_team == "home"
            and self.ball.state == BallState.IN_FLIGHT
        )
        away_has_ball = self.ball.holder_team == "away" or (
            self.ball.flight and self.ball.flight.passer_team == "away"
            and self.ball.state == BallState.IN_FLIGHT
        )

        # Get ball carrier info for intelligent off-ball decisions
        ball_carrier = None
        if self.ball.state == BallState.HELD and self.ball.holder_team:
            holder_team = self.home if self.ball.holder_team == "home" else self.away
            ball_carrier = holder_team.players[self.ball.holder_idx]

        # Update targets with Phase 2 intelligent AI
        self.home.update_off_ball(
            self.ball.position, home_has_ball, self.config, self.pitch,
            ball_carrier=ball_carrier if home_has_ball else None,
            opponents=self.away.players if home_has_ball else self.home.players,
        )
        self.away.update_off_ball(
            self.ball.position, away_has_ball, self.config, self.pitch,
            ball_carrier=ball_carrier if away_has_ball else None,
            opponents=self.home.players if away_has_ball else self.away.players,
        )

        # Assign pressers for defending team
        if self.ball.state == BallState.HELD:
            if self.ball.holder_team == "home":
                self.away.assign_pressers(self.ball.position, self.config, self.pitch)
            else:
                self.home.assign_pressers(self.ball.position, self.config, self.pitch)

        # Move all players
        self.home.move_all(self.config, self.pitch)
        self.away.move_all(self.config, self.pitch)

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

    def _handle_out_of_bounds(self, pos: Tuple[float, float], flight: BallFlight):
        """Handle ball going out of bounds."""
        passer_team_side = flight.passer_team
        other_team = "away" if passer_team_side == "home" else "home"

        if self.pitch.is_over_goal_line(pos[0]):
            if flight.flight_type == FlightType.SHOT:
                self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
            else:
                attacking_right = (passer_team_side == "home" and self.home.attacking_right) or \
                                  (passer_team_side == "away" and self.away.attacking_right)
                if (attacking_right and pos[0] >= self.config.pitch_length) or \
                   (not attacking_right and pos[0] <= 0):
                    self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
                else:
                    self.ball.set_dead("corner", other_team, self.config.goal_kick_restart_ticks)
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
            # GK takes goal kick - use distribution model (Phase 2)
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
