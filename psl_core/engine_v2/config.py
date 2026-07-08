"""Engine V2 configuration parameters with defaults."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraceConfig:
    """Decision trace controls for tuning scripts."""

    detail: str = "off"  # off | chosen | top_candidates | full
    top_k: int = 5
    include_off_ball: bool = False
    include_defense: bool = False
    focus_players: tuple[int, ...] = ()
    focus_ticks: tuple[tuple[int, int], ...] = ()
    sample_rate: int = 1

    def should_trace(self, tick: int, player_idx: int, phase: str) -> bool:
        """Return whether a decision should be recorded."""
        if self.detail == "off":
            return False
        if phase == "off_ball_attack" and not self.include_off_ball:
            return False
        if phase == "off_ball_defense" and not self.include_defense:
            return False
        if self.focus_players and player_idx not in self.focus_players:
            return False
        if self.focus_ticks:
            if not any(start <= tick <= end for start, end in self.focus_ticks):
                return False
        sample_rate = max(1, int(self.sample_rate))
        return tick % sample_rate == 0


@dataclass
class EngineConfig:
    """All tunable parameters for the match engine."""

    trace: TraceConfig = field(default_factory=TraceConfig)

    # Pitch dimensions (meters)
    pitch_length: float = 105.0
    pitch_width: float = 68.0

    # Goal dimensions
    goal_width: float = 7.32
    goal_depth: float = 2.44  # Not used geometrically, just for reference

    # Timing
    tick_duration: float = 2.0  # seconds per tick
    total_ticks: int = 2700  # ticks for full 90 min match
    half_ticks: int = 1350  # ticks per half
    frame_interval: int = 2  # record a frame every N ticks

    # Player movement
    player_max_speed: float = 5.5  # meters per tick at Speed=99
    player_min_speed: float = 2.5  # meters per tick at Speed=1
    dribble_speed_factor: float = 0.7  # speed multiplier when dribbling

    # Ball physics
    ball_pass_speed: float = 18.0  # meters per tick for short pass
    ball_long_pass_speed: float = 22.0  # meters per tick for long pass
    ball_shot_speed: float = 28.0  # meters per tick for shot

    # Action scoring weights (base probabilities before ability scaling)
    short_pass_base_success: float = 0.80
    long_pass_base_success: float = 0.55
    shot_base_accuracy: float = 0.35
    dribble_base_success: float = 0.60
    tackle_base_success: float = 0.45

    # Shot parameters
    shot_on_target_base: float = 0.50
    gk_save_base: float = 0.78
    shot_max_distance: float = 35.0  # max effective shooting distance
    shot_ideal_distance: float = 20.0  # ideal shooting distance

    # Pressing
    press_radius: float = 12.0  # distance within which a defender will press
    contest_radius: float = 2.5  # distance to trigger contest

    # IQ / decision making
    iq_noise_factor: float = 1.0  # noise = (100 - IQ) / 100 * iq_noise_factor
    decision_temperature: float = 1.0  # softmax temperature base

    # Goal continuity layer (disabled by default while acceptance tests mature)
    goal_continuity_enabled: bool = True
    goal_cut_inside_bias: float = 0.035
    goal_noise_scale: float = 0.008

    # Formation positioning
    formation_pull_strength: float = 0.5  # how strongly players return to formation
    forward_bias_attack: float = 8.0  # meters forward bias when attacking
    compact_factor: float = 0.7  # how compact team stays (0=spread, 1=tight)

    # Match balance
    possession_inertia: float = 0.6  # probability of retaining possession on loose ball
    interception_radius: float = 3.0  # distance within which interception is checked
    interception_base_chance: float = 0.06  # base interception probability per defender in radius

    # Out-of-play
    goal_kick_restart_ticks: int = 8  # ticks to wait after goal kick
    throw_in_restart_ticks: int = 4  # ticks to wait after throw-in

    # Stamina (simplified for Phase 1)
    stamina_enabled: bool = False
    stamina_drain_per_tick: float = 0.01
    stamina_sprint_multiplier: float = 2.0

    # =========================================================================
    # Phase 2: Formation Dynamics
    # =========================================================================
    formation_advance_factor: float = 0.08  # how aggressively team pushes up with ball
    formation_side_shift_factor: float = 0.06  # how much team shifts toward ball side
    compactness: float = 1.3  # vertical tightness (0.5=spread, 1.5=compact)
    width: float = 1.0  # horizontal spread (0.5=narrow, 1.5=wide)

    # =========================================================================
    # Phase 2: Transition detection
    # =========================================================================
    transition_ticks: int = 3  # ticks a transition state lasts after possession change

    # =========================================================================
    # Phase 2: Carry action
    # =========================================================================
    carry_min_distance: float = 8.0  # min carry distance (meters)
    carry_max_distance: float = 15.0  # max carry distance (meters)
    carry_base_success: float = 0.90  # base carry success rate
    carry_defender_check_radius: float = 12.0  # radius to check for defenders ahead

    # =========================================================================
    # Phase 2: Cross action
    # =========================================================================
    cross_zone_x_threshold: float = 0.82  # DEPRECATED: gate removed; cross determined by target availability
    cross_base_success: float = 0.50  # base cross success rate
    cross_target_box_depth: float = 18.0  # how deep into box crosses target

    # =========================================================================
    # Phase 2: Aerial / Heading
    # =========================================================================
    heading_contest_radius: float = 8.0  # radius within which players compete for aerial ball
    heading_shot_distance: float = 18.0  # max distance from goal for header shot
    heading_loose_ball_prob: float = 0.20  # probability ball drops loose after header

    # =========================================================================
    # Phase 2: Vision system
    # =========================================================================
    vision_base_fov: float = 180.0  # base field of view in degrees
    vision_iq_bonus_factor: float = 0.5  # degrees per IQ point added to FOV
    vision_base_distance: float = 42.0
    vision_iq_distance_bonus_factor: float = 0.35
    vision_max_distance: float = 65.0

    # =========================================================================
    # Phase 2: Goalkeeper model
    # =========================================================================
    gk_position_error_factor: float = 0.05  # meters of error per (100-Positioning) point
    gk_reaction_delay_factor: float = 0.005  # fraction of delay per (100-Reaction) point
    gk_rush_distance: float = 20.0  # distance threshold for GK rush decision
    gk_rush_success_base: float = 0.50  # base rush-out success

    # =========================================================================
    # Phase 2: Off-ball movement
    # =========================================================================
    find_space_radius: float = 15.0  # radius to search for space
    make_run_distance: float = 20.0  # distance for forward runs
    drop_deep_distance: float = 12.0  # distance to drop back toward carrier
    go_wide_y_target: float = 8.0  # y-distance from sideline for go-wide
    press_close_speed_bonus: float = 1.2  # speed multiplier when pressing
    block_lane_offset: float = 5.0  # meters offset for lane blocking
    cover_depth: float = 8.0  # meters behind pressing teammate

    # =========================================================================
    # Phase 2: Contested ball
    # =========================================================================
    contested_race_radius: float = 15.0  # radius within which players race to loose ball
    contested_preposition_factor: float = 0.5  # IQ factor for pre-positioning

    # =========================================================================
    # Phase 2: Layered on-ball decision model
    # =========================================================================
    # DEPRECATED: release_threshold_base - gate removed; all actions compete equally
    release_threshold_base: float = 0.25

    # Carrier movement speed (meters per tick while carrying the ball)
    carrier_jog_speed: float = 4.0  # default jogging with ball
    carrier_sprint_speed: float = 6.5  # when clear space ahead

    # DEPRECATED: forced_decision_radius - removed; carry feasibility handles close range naturally
    forced_decision_radius: float = 2.5

    # DEPRECATED: iq_threshold_adjustment - removed with release_threshold
    iq_threshold_adjustment: float = 0.003

    # =========================================================================
    # Phase 2: Tactic weights (all 1.0 for Phase 2, Phase 3 fills)
    # =========================================================================
    # These are placeholders - Phase 3 will replace with per-tactic values

    # =========================================================================
    # Reward-driven engine v2 (3-phase tick model)
    # =========================================================================

    # Tackle parameters
    tackle_range: float = 6.0  # meters - defender must be within this to attempt tackle
    tackle_fail_stun_seconds: float = 1.5  # seconds stunned after failed tackle
    tackle_success_bonus: float = 0.0  # no bonus needed, natural from duel

    # Interception
    interception_reach: float = 3.5  # meters - perpendicular distance to pass path

    # Unforced errors
    pass_error_divisor: float = 800.0  # (100-Passing)/divisor = error chance
    first_touch_error_divisor: float = 700.0  # (100-IQ)/divisor = error chance
    carry_error_divisor: float = 900.0  # (100-Dribbling)/divisor = error chance

    # Rewards
    goal_reward_constant: float = 1.0  # multiplier for shoot score to make competitive
    clear_reward_base: float = 0.3  # base for clearance when not under pressure

    # Carrier movement (reward-driven model)
    carrier_speed: float = 3.0  # meters per tick when carrying (jog)
    carrier_sprint_speed_v2: float = 4.5  # meters per tick when clear ahead

    # =========================================================================
    # Space Model Upgrade
    # =========================================================================
    iq_noise_scale: float = 0.3  # noise multiplier for (100-IQ)/100
    space_creation_radius: float = 10.0  # radius for counting drawn defenders
    receive_reachability_scale: float = 0.2  # sigmoid steepness for arrival advantage
    pass_to_space_ball_speed: float = 15.0  # speed of ball for arrival calculations

    def goal_y_min(self) -> float:
        """Y coordinate of near goal post."""
        return (self.pitch_width - self.goal_width) / 2.0

    def goal_y_max(self) -> float:
        """Y coordinate of far goal post."""
        return (self.pitch_width + self.goal_width) / 2.0


# Default config keys for GameConfigService integration
ENGINE_V2_CONFIG_KEYS = {
    "engine_v2.tick_duration": 2.0,
    "engine_v2.total_ticks": 2700,
    "engine_v2.frame_interval": 2,
    "engine_v2.player_max_speed": 8.0,
    "engine_v2.ball_pass_speed": 18.0,
    "engine_v2.ball_shot_speed": 28.0,
    "engine_v2.shot_max_distance": 35.0,
    "engine_v2.press_radius": 12.0,
    "engine_v2.contest_radius": 3.0,
    "engine_v2.goal_continuity_enabled": True,
    "engine_v2.goal_cut_inside_bias": 0.035,
    "engine_v2.goal_noise_scale": 0.008,
}


def load_config_from_service(config_service) -> EngineConfig:
    """Load engine config from GameConfigService, falling back to defaults."""
    cfg = EngineConfig()
    if config_service is None:
        return cfg

    for key, default in ENGINE_V2_CONFIG_KEYS.items():
        attr_name = key.replace("engine_v2.", "")
        try:
            value = config_service.get(key)
            if value is not None and hasattr(cfg, attr_name):
                if isinstance(default, bool):
                    if isinstance(value, str):
                        parsed = value.strip().lower() in ("1", "true", "yes", "on")
                    else:
                        parsed = bool(value)
                    setattr(cfg, attr_name, parsed)
                else:
                    setattr(cfg, attr_name, type(default)(value))
        except Exception:
            pass

    return cfg
