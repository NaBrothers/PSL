"""Configuration contract for the Rust match engine."""

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class TraceConfig:
    """Trace controls implemented by the Rust whole-match runner."""

    detail: str = "off"  # off | chosen | top_candidates | full
    top_k: int = 5


@dataclass
class EngineConfig:
    """JSON-serializable inputs consumed by Rust ``match_v2_run``."""

    trace: TraceConfig = field(default_factory=TraceConfig)

    pitch_length: float = 105.0
    pitch_width: float = 68.0
    tick_duration: float = 2.0
    total_ticks: int = 2700
    half_ticks: int = 1350
    frame_interval: int = 2
    transition_ticks: int = 3
    goal_kick_restart_ticks: int = 8
    throw_in_restart_ticks: int = 4

    player_max_speed: float = 5.5
    player_min_speed: float = 2.5
    ball_pass_speed: float = 18.0
    ball_long_pass_speed: float = 22.0
    ball_shot_speed: float = 28.0
    goal_width: float = 7.32

    contest_radius: float = 2.5
    contested_race_radius: float = 15.0
    press_radius: float = 12.0
    tackle_range: float = 6.0
    interception_reach: float = 3.5
    short_pass_base_success: float = 0.80
    long_pass_base_success: float = 0.55
    shot_ideal_distance: float = 20.0
    shot_on_target_base: float = 0.50
    gk_save_base: float = 0.78
    gk_position_error_factor: float = 0.05
    gk_reaction_delay_factor: float = 0.005
    clear_reward_base: float = 0.3
    carrier_speed: float = 3.0
    iq_noise_scale: float = 0.3
    goal_noise_scale: float = 0.008

    vision_base_fov: float = 180.0
    vision_iq_bonus_factor: float = 0.5
    vision_base_distance: float = 42.0
    vision_iq_distance_bonus_factor: float = 0.35
    vision_max_distance: float = 65.0
    pass_to_space_ball_speed: float = 15.0
    receive_reachability_scale: float = 0.2
    space_creation_radius: float = 10.0

    pass_error_divisor: float = 800.0
    first_touch_error_divisor: float = 700.0
    carry_error_divisor: float = 900.0
    tackle_fail_stun_seconds: float = 1.5
    target_occupation_weight: float = 0.18

    # Deterministic scenario controls used by engine tests and tuning agents.
    runner_shot_threshold: float = 0.18
    runner_forced_action: Optional[str] = None
    runner_forced_actions: Optional[list[str]] = None
    runner_forced_pass_target: Optional[tuple[float, float]] = None
    runner_forced_clear_target: Optional[tuple[float, float]] = None
    runner_force_receiver_offside: bool = False
    runner_force_specialized_goal: Optional[str] = None
    rng_trace: bool = False

    def to_rust_payload(self) -> dict:
        """Return exactly the runtime configuration accepted by Rust."""
        payload = asdict(self)
        trace = payload.pop("trace")
        payload["trace_detail"] = trace["detail"]
        payload["trace_top_k"] = trace["top_k"]
        return payload


# This is the single source of truth for production settings exposed by the
# configuration center. Deterministic runner controls remain test-only.
ENGINE_CONFIG_FIELDS = (
    {
        "name": "tick_duration",
        "default": 2.0,
        "label": "Tick时长(秒)",
        "type": "float",
    },
    {
        "name": "shot_on_target_base",
        "default": 0.52,
        "label": "射正基准概率",
        "type": "float",
    },
    {
        "name": "gk_save_base",
        "default": 0.66,
        "label": "门将扑救基准",
        "type": "float",
    },
    {
        "name": "press_radius",
        "default": 12.0,
        "label": "逼抢半径(米)",
        "type": "float",
    },
    {
        "name": "player_max_speed",
        "default": 8.0,
        "label": "球员最大速度(米/tick)",
        "type": "float",
    },
    {
        "name": "goal_noise_scale",
        "default": 0.008,
        "label": "Goal探索噪声",
        "type": "float",
    },
    {
        "name": "iq_noise_scale",
        "default": 0.3,
        "label": "球商决策噪声",
        "type": "float",
    },
)

ENGINE_CONFIG_DEFAULTS = {
    f"engine_v2.{field['name']}": field["default"]
    for field in ENGINE_CONFIG_FIELDS
}
ENGINE_CONFIG_ADMIN_ITEMS = [
    {
        "key": f"engine_v2.{field['name']}",
        "label": field["label"],
        "type": field["type"],
    }
    for field in ENGINE_CONFIG_FIELDS
]


def load_config_from_service(config_service) -> EngineConfig:
    """Load the supported Rust settings from ``GameConfigService``."""
    config = EngineConfig()
    if config_service is None:
        return config

    for key, default in ENGINE_CONFIG_DEFAULTS.items():
        try:
            value = config_service.get(key)
        except (KeyError, TypeError, ValueError):
            continue
        if value is None:
            continue
        attr_name = key.removeprefix("engine_v2.")
        setattr(config, attr_name, type(default)(value))

    return config
