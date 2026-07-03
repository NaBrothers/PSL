"""Engine V2 configuration parameters with defaults."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EngineConfig:
    """All tunable parameters for the match engine."""

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
    player_max_speed: float = 8.0  # meters per tick at Speed=99
    player_min_speed: float = 4.0  # meters per tick at Speed=1
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
    shot_on_target_base: float = 0.55
    gk_save_base: float = 0.64
    shot_max_distance: float = 35.0  # max effective shooting distance
    shot_ideal_distance: float = 18.0  # ideal shooting distance

    # Pressing
    press_radius: float = 12.0  # distance within which a defender will press
    contest_radius: float = 2.5  # distance to trigger contest

    # IQ / decision making
    iq_noise_factor: float = 1.0  # noise = (100 - IQ) / 100 * iq_noise_factor
    decision_temperature: float = 1.0  # softmax temperature base

    # Formation positioning
    formation_pull_strength: float = 0.3  # how strongly players return to formation
    forward_bias_attack: float = 8.0  # meters forward bias when attacking
    compact_factor: float = 0.7  # how compact team stays (0=spread, 1=tight)

    # Match balance
    possession_inertia: float = 0.6  # probability of retaining possession on loose ball
    interception_radius: float = 5.0  # distance within which interception is checked
    interception_base_chance: float = 0.15  # base interception probability per defender in radius

    # Out-of-play
    goal_kick_restart_ticks: int = 2  # ticks to wait after goal kick
    throw_in_restart_ticks: int = 1  # ticks to wait after throw-in

    # Stamina (simplified for Phase 1)
    stamina_enabled: bool = False
    stamina_drain_per_tick: float = 0.01
    stamina_sprint_multiplier: float = 2.0

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
                setattr(cfg, attr_name, type(default)(value))
        except Exception:
            pass

    return cfg
