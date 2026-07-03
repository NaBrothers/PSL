"""Main match loop: orchestrates the tick-based simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from psl_core.constants import FORMATION

from .config import EngineConfig, load_config_from_service
from .pitch import Pitch, Zone
from .ball import Ball, BallState, BallFlight, FlightType
from .player import Player, PlayerState
from .team import Team
from .actions import Action, ActionType
from .physics import distance, move_toward, direction
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
    """Tick-based football match simulation engine.

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
        """Initialize match.

        Args:
            home_cards: list of 11 dicts with keys: name, player_id, position, color,
                        and 13 ability keys (Finishing, Short_Passing, etc.)
            away_cards: same format as home_cards
            home_formation: formation string like "442"
            away_formation: formation string like "433"
            config: optional EngineConfig override
            config_service: optional GameConfigService for loading config from DB
        """
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
            # Fallback to 442
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

        # Setup formation positions
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

            # Record frame at intervals or on events
            if (t - start_tick) % self.config.frame_interval == 0:
                self._record_frame()

    def _tick(self):
        """Execute one simulation tick."""
        # 1. Handle dead ball
        if self.ball.state == BallState.DEAD:
            if self.ball.tick_dead():
                self._restart_play()
            return

        # 2. Handle ball in flight
        if self.ball.state == BallState.IN_FLIGHT:
            self._tick_flight()
            self._move_players()
            return

        # 3. Ball is held - the holder makes a decision
        if self.ball.state == BallState.HELD:
            self._tick_held()

        # 4. Move off-ball players
        self._move_players()

        # 5. Check for contests (pressing player reaches ball carrier)
        self._check_contests()

        # 6. Track possession
        if self.ball.holder_team:
            self.match_stats.record_possession(self.ball.holder_team)

    def _tick_held(self):
        """Process a tick where a player holds the ball."""
        holder_team = self.home if self.ball.holder_team == "home" else self.away
        holder = holder_team.players[self.ball.holder_idx]
        opponents = self.away if self.ball.holder_team == "home" else self.home

        # Holder chooses action
        action = holder.choose_action(
            holder_team.players,
            opponents.players,
            self.config,
            self.pitch,
            holder_team.attacking_right,
        )

        if action is None:
            return

        # Execute the action
        self._execute_action(holder, action, holder_team, opponents)

    def _tick_flight(self):
        """Process a tick where the ball is in flight."""
        completed = self.ball.tick_flight()

        if not completed:
            # Check for interceptions along the way
            self._check_interceptions()
            return

        # Flight complete - resolve arrival
        self._resolve_flight_arrival()

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

    def _execute_pass(
        self, passer: Player, action: Action, passer_team: Team, opponents: Team, is_long: bool
    ):
        """Execute a pass action."""
        passer.passes_attempted += 1

        speed = self.config.ball_long_pass_speed if is_long else self.config.ball_pass_speed
        flight_type = FlightType.LONG_PASS if is_long else FlightType.SHORT_PASS

        dist = distance(passer.pos, action.target)
        ticks_needed = max(1, round(dist / speed))

        flight = BallFlight(
            origin=passer.pos,
            target=action.target,
            flight_type=flight_type,
            speed=speed,
            ticks_total=ticks_needed,
            passer_idx=passer.index,
            passer_team=passer_team.side,
        )

        self.last_passer_idx = passer.index
        self.last_passer_team = passer_team.side

        # Release ball
        passer.state = PlayerState.OFF_BALL
        self.ball.set_flight(flight)

        self.trace.log_action(
            self.tick, passer_team.side, passer.name,
            "long_pass" if is_long else "short_pass",
            target=action.target, target_player=action.target_player_idx,
        )

        # Set pending ball flight for replay
        ft = "pass"
        self._pending_ball_flight = build_ball_flight_data(
            passer.pos, action.target, ft, on_target=False
        )

    def _execute_shot(self, shooter: Player, action: Action, shooter_team: Team, opponents: Team):
        """Execute a shot action."""
        shooter.shots += 1

        # Determine if on target
        on_target = random.random() < action.success_prob
        if on_target:
            shooter.shots_on_target += 1

        # Determine shot target (add inaccuracy if not on target)
        if on_target:
            # Aim within goal posts
            goal_y_min = self.pitch.goal_y_min
            goal_y_max = self.pitch.goal_y_max
            target_y = random.uniform(goal_y_min + 0.5, goal_y_max - 0.5)
            if shooter_team.attacking_right:
                target = (self.config.pitch_length, target_y)
            else:
                target = (0.0, target_y)
        else:
            # Miss: aim wide or high (outside goal)
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

        # Replay data
        self._pending_ball_flight = build_ball_flight_data(
            shooter.pos, target, "shot", on_target=on_target
        )
        self._pending_event_text = f"{'🎯' if on_target else '💨'} {shooter.name} shoots!"

    def _execute_dribble(self, dribbler: Player, action: Action, dribbler_team: Team, opponents: Team):
        """Execute a dribble action."""
        dribbler.dribbles_attempted += 1

        # Check if successful
        success = random.random() < action.success_prob

        if success:
            dribbler.dribbles_completed += 1
            # Move dribbler toward target
            speed = dribbler.get_move_speed(self.config) * self.config.dribble_speed_factor
            new_pos = move_toward(dribbler.pos, action.target, speed)
            new_pos = self.pitch.clamp(new_pos[0], new_pos[1])
            dribbler.distance_covered += distance(dribbler.pos, new_pos)
            dribbler.pos = new_pos
            self.ball.position = new_pos

            self.trace.log_action(
                self.tick, dribbler_team.side, dribbler.name, "dribble", success=True
            )
        else:
            # Dribble failed - loss of possession
            # Find closest opponent to take ball
            closest_opp = opponents.get_closest_to(dribbler.pos, exclude_gk=True)
            if closest_opp:
                closest_opp.tackles_attempted += 1
                closest_opp.tackles_won += 1
                self._give_ball(closest_opp, opponents)
                self.trace.log_action(
                    self.tick, dribbler_team.side, dribbler.name, "dribble",
                    success=False, tackled_by=closest_opp.name
                )
                self._pending_event_text = f"{closest_opp.name} tackles {dribbler.name}"
            else:
                # No one nearby - ball just goes loose, re-held
                pass

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

        # It's a pass - check if out of bounds
        if self.pitch.is_out_of_bounds(target_pos[0], target_pos[1]):
            self._handle_out_of_bounds(target_pos, flight)
            return

        # Find intended receiver or closest player from passer's team
        passer_team = self.home if flight.passer_team == "home" else self.away
        opp_team = self.away if flight.passer_team == "home" else self.home

        # Find closest teammate to target
        receiver = passer_team.get_closest_to(target_pos, exclude_indices=[flight.passer_idx])
        closest_opp = opp_team.get_closest_to(target_pos)

        if receiver is None:
            # No one to receive, opponent gets it
            if closest_opp:
                self._give_ball(closest_opp, opp_team)
            return

        recv_dist = distance(receiver.pos, target_pos)
        opp_dist = distance(closest_opp.pos, target_pos) if closest_opp else 999

        # Determine who gets the ball
        if opp_dist < recv_dist and opp_dist < 5.0:
            # Opponent intercepts
            if closest_opp:
                closest_opp.interceptions += 1
                self._give_ball(closest_opp, opp_team)
                self.trace.log_event(self.tick, "interception", player=closest_opp.name)
        else:
            # Receiver gets it - pass successful
            passer = passer_team.players[flight.passer_idx]
            passer.passes_completed += 1
            self._give_ball(receiver, passer_team)

    def _resolve_shot_arrival(self, flight: BallFlight):
        """Resolve a shot arriving at (or near) the goal."""
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        shooter = shooter_team.players[flight.passer_idx]

        target_pos = flight.target

        # Check if on target (within goal bounds)
        if not flight.on_target:
            # Shot missed - goal kick
            self._pending_event_text = f"{shooter.name}'s shot goes wide!"
            self.ball.set_dead("goal_kick", defending_team.side, self.config.goal_kick_restart_ticks)
            self._record_frame()  # Always record on shot event
            return

        # Shot is on target - check GK save
        gk = defending_team.goalkeeper
        gk_saving = gk.abilities.get("GK_Saving", 50) / 100.0
        gk_positioning = gk.abilities.get("GK_Positioning", 50) / 100.0
        gk_reaction = gk.abilities.get("GK_Reaction", 50) / 100.0

        # GK save probability
        gk_overall = (gk_saving * 0.5 + gk_positioning * 0.3 + gk_reaction * 0.2)
        save_prob = self.config.gk_save_base * (0.3 + 0.7 * gk_overall)

        # Distance from GK to shot target affects save probability
        gk_dist = distance(gk.pos, target_pos)
        if gk_dist > 5.0:
            save_prob *= max(0.3, 1.0 - (gk_dist - 5.0) / 15.0)

        save_prob = max(0.05, min(0.85, save_prob))

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

        # Check for assist
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

        # Reset positions to formation
        home_formation_data = FORMATION.get(self.home_formation_key, FORMATION["442"])
        away_formation_data = FORMATION.get(self.away_formation_key, FORMATION["442"])
        self.home.setup_formation(self.pitch, home_formation_data)
        self.away.setup_formation(self.pitch, away_formation_data)

    def _check_contests(self):
        """Check if any pressing player triggers a contest."""
        if self.ball.state != BallState.HELD:
            return

        holder_team = self.home if self.ball.holder_team == "home" else self.away
        opp_team = self.away if self.ball.holder_team == "home" else self.home
        holder = holder_team.players[self.ball.holder_idx]

        # Find opponents close enough for a contest
        for opp in opp_team.players:
            if opp.is_goalkeeper:
                continue
            d = distance(opp.pos, holder.pos)
            if d < self.config.contest_radius:
                self._resolve_contest(holder, opp, holder_team, opp_team)
                return  # One contest per tick max

    def _resolve_contest(
        self, holder: Player, challenger: Player, holder_team: Team, opp_team: Team
    ):
        """Resolve a 1v1 contest between dribbler and tackler."""
        holder.state = PlayerState.CONTEST
        challenger.state = PlayerState.CONTEST
        challenger.tackles_attempted += 1

        # Contest: Dribbling vs Tackling
        dribbling = holder.abilities.get("Dribbling", 50)
        tackling = challenger.abilities.get("Tackling", 50)

        # Probability holder keeps ball
        holder_strength = dribbling / (dribbling + tackling + 1)
        # Add some randomness
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
            self._give_ball(challenger, opp_team)
            holder.state = PlayerState.OFF_BALL
            self.trace.log_event(
                self.tick, "tackle",
                tackler=challenger.name, dispossessed=holder.name
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
                # Check interception chance
                defence = opp.abilities.get("Defence", 50) / 100.0
                intercept_chance = self.config.interception_base_chance * (0.5 + defence)
                # Closer = higher chance
                proximity_bonus = max(0, 1.0 - d / self.config.interception_radius) * 0.15
                total_chance = intercept_chance + proximity_bonus

                if random.random() < total_chance:
                    # Intercepted!
                    opp.interceptions += 1
                    self._give_ball(opp, opp_team)
                    self.trace.log_event(self.tick, "interception", player=opp.name)
                    return

    def _move_players(self):
        """Move all players and update their targets."""
        home_has_ball = self.ball.holder_team == "home" or (
            self.ball.flight and self.ball.flight.passer_team == "home"
        )
        away_has_ball = self.ball.holder_team == "away" or (
            self.ball.flight and self.ball.flight.passer_team == "away"
        )

        # Update targets
        self.home.update_off_ball(
            self.ball.position, home_has_ball, self.config, self.pitch
        )
        self.away.update_off_ball(
            self.ball.position, away_has_ball, self.config, self.pitch
        )

        # Assign pressers for defending team
        if self.ball.state == BallState.HELD:
            if self.ball.holder_team == "home":
                self.away.assign_presser(self.ball.position, self.config, self.pitch)
            else:
                self.home.assign_presser(self.ball.position, self.config, self.pitch)

        # Move
        self.home.move_all(self.config, self.pitch)
        self.away.move_all(self.config, self.pitch)

    def _give_ball(self, player: Player, team: Team):
        """Give the ball to a specific player."""
        # Clear previous holder state
        if self.ball.holder_team == "home":
            self.home.players[self.ball.holder_idx].state = PlayerState.OFF_BALL
        elif self.ball.holder_team == "away":
            self.away.players[self.ball.holder_idx].state = PlayerState.OFF_BALL

        player.state = PlayerState.ON_BALL
        self.ball.set_held(player.index, team.side, player.pos)

    def _handle_out_of_bounds(self, pos: Tuple[float, float], flight: BallFlight):
        """Handle ball going out of bounds."""
        passer_team_side = flight.passer_team
        other_team = "away" if passer_team_side == "home" else "home"

        if self.pitch.is_over_goal_line(pos[0]):
            # Over goal line
            if flight.flight_type == FlightType.SHOT:
                # Already handled in shot resolution
                self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
            else:
                # Was it deflected by defender? Simplified: if pass from attacking team
                # goes over their attacking goal line = goal kick
                # goes over own goal line = corner for opponent
                attacking_right = (passer_team_side == "home" and self.home.attacking_right) or \
                                  (passer_team_side == "away" and self.away.attacking_right)
                if (attacking_right and pos[0] >= self.config.pitch_length) or \
                   (not attacking_right and pos[0] <= 0):
                    # Attacking team put it over opponent's goal line = goal kick
                    self.ball.set_dead("goal_kick", other_team, self.config.goal_kick_restart_ticks)
                else:
                    # Over own goal line = corner for opponent
                    self.ball.set_dead("corner", other_team, self.config.goal_kick_restart_ticks)
        else:
            # Over touchline = throw-in for other team
            self.ball.set_dead("throw_in", other_team, self.config.throw_in_restart_ticks)

    def _restart_play(self):
        """Restart play after dead ball."""
        restart_team = self.home if self.ball.restart_team == "home" else self.away
        reason = self.ball.dead_reason

        if reason == "kickoff":
            # Kickoff from center
            self.ball.position = self.pitch.center
            # Give to a midfielder
            closest = restart_team.get_closest_to(self.pitch.center, exclude_gk=True)
            if closest:
                closest.pos = (self.pitch.center[0], self.pitch.center[1])
                self._give_ball(closest, restart_team)
                self._pending_cut = True

        elif reason == "goal_kick":
            # GK takes goal kick
            gk = restart_team.goalkeeper
            self._give_ball(gk, restart_team)
            # Position ball at 6-yard box
            if restart_team.attacking_right:
                self.ball.position = (6.0, self.pitch.width / 2.0)
                gk.pos = (6.0, self.pitch.width / 2.0)
            else:
                self.ball.position = (self.config.pitch_length - 6.0, self.pitch.width / 2.0)
                gk.pos = (self.config.pitch_length - 6.0, self.pitch.width / 2.0)

        elif reason == "corner":
            # Corner kick - give to closest outfield player
            # Place ball in corner
            opp_team = self.away if restart_team.side == "home" else self.home
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
            # Simplified: just give possession to closest player of restart team
            ball_pos = self.ball.position
            # Clamp ball to touchline
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

        # Find closest midfielder to center
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

        # Clear pending event data
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
