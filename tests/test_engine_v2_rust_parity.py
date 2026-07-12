import subprocess
import random
from pathlib import Path
from unittest.mock import patch

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.decision import iq_temperature_factor
from psl_core.engine_v2.goal import GoalSwitchContext, PlayerGoal, goal_switch_cost
from psl_core.engine_v2.goal import select_goal, select_goal_candidate
from psl_core.engine_v2.goalkeeper import compute_gk_save_probability, should_rush_out, choose_distribution
from psl_core.engine_v2 import physics as py_physics
from psl_core.engine_v2 import vision as py_vision
from psl_core.engine_v2.interactions import (
    Interaction,
    InteractionType,
    detect_duel,
    detect_interception,
    detect_wasted_tackle,
    resolve_duel,
    resolve_interception,
)
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.position_value import (
    defensive_position_value,
    position_value,
    receive_reachability,
    space_creation_value,
)
from psl_core.engine_v2.rust_adapter import (
    choose_off_ball_defense_rust,
    evaluate_clear_rust,
    evaluate_carry_rust,
    evaluate_hold_rust,
    evaluate_shot_rust,
    position_values_rust,
    score_pass_point_option_tuples_rust,
    score_pass_point_options_rust,
    select_goal_candidate_rust,
    softmax_select_index_rust,
    softmax_select_index_with_temperature_rust,
)
from psl_core.engine_v2.value_model import (
    evaluate_clear,
    evaluate_carry_target,
    evaluate_hold,
    evaluate_shot,
    expected_pass_value_result,
    pass_lane_risk,
    pass_receive_value,
    receiver_pressure,
    shot_quality_at,
    state_value,
    turnover_consequence,
    ValueResult,
)
from tests.engine_v2_baseline_runner import run_python_baseline_match, summarize_engine_v2_run


ROOT = Path(__file__).resolve().parents[1]
RUST_CRATE = ROOT / "rust" / "engine_v2_core"


def _forced_kickoff_restart_sample(cards_factory):
    home_cards = cards_factory()
    away_cards = cards_factory()
    for key in ("Finishing", "Long_Shot", "IQ"):
        home_cards[9]["abilities"][key] = 99
    for key in ("GK_Saving", "GK_Positioning", "GK_Reaction"):
        away_cards[0]["abilities"][key] = 1

    config = EngineConfig(total_ticks=5, half_ticks=5, frame_interval=1)
    config.runner_forced_action = "shot"
    config.ball_shot_speed = 100.0
    config.gk_save_base = 0.0
    return home_cards, away_cards, config, 16


def _forced_assisted_goal_sample(cards_factory):
    home_cards = cards_factory()
    away_cards = cards_factory()
    for card in home_cards:
        for key in ("Finishing", "Long_Shot", "IQ", "Short_Passing", "Long_Passing"):
            card["abilities"][key] = 99
    for key in ("GK_Saving", "GK_Positioning", "GK_Reaction"):
        away_cards[0]["abilities"][key] = 1

    config = EngineConfig(total_ticks=6, half_ticks=6, frame_interval=1)
    config.runner_forced_actions = ["pass", "shot"]
    config.ball_shot_speed = 100.0
    config.gk_save_base = 0.0
    return home_cards, away_cards, config, 85


def _positions_payload(positions):
    if not positions:
        return "-"
    return ";".join(f"{x},{y}" for x, y in positions)


def _indexed_positions_payload(players):
    if not players:
        return "-"
    return ";".join(f"{idx},{x},{y}" for idx, x, y in players)


def _case_line(case_id, x, y, attacking_right, opponents, teammates, runner=None):
    runner_x, runner_y = ("-", "-") if runner is None else (str(runner[0]), str(runner[1]))
    return "\t".join([
        str(x),
        str(y),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        runner_x,
        runner_y,
        _positions_payload(opponents),
        _positions_payload(teammates),
        case_id,
    ])


def _shot_case_line(case_id, x, y, finishing, long_shot, attacking_right, opponents):
    return "\t".join([
        str(x),
        str(y),
        str(finishing),
        str(long_shot),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        "20.0",
        "0.50",
        "0.78",
        _positions_payload(opponents),
        case_id,
    ])


def _goal_switch_case_line(case_id, base, context_stability, role_discipline, pressure_interrupt, iq):
    return "\t".join([
        str(base),
        str(context_stability),
        str(role_discipline),
        str(pressure_interrupt),
        str(iq),
        case_id,
    ])


def _iq_temperature_case_line(case_id, iq, floor, low_iq_range, elite_discount):
    return "\t".join([
        str(iq),
        str(floor),
        str(low_iq_range),
        str(elite_discount),
        case_id,
    ])


def _select_goal_case_line(
    case_id,
    current_type,
    current_value,
    current_phase,
    candidate_type,
    candidate_value,
    candidate_phase,
    base,
    context_stability,
    role_discipline,
    pressure_interrupt,
    iq,
):
    return "\t".join([
        current_type,
        str(current_value),
        current_phase,
        candidate_type,
        str(candidate_value),
        candidate_phase,
        str(base),
        str(context_stability),
        str(role_discipline),
        str(pressure_interrupt),
        str(iq),
        case_id,
    ])


def _select_goal_candidate_case_line(
    case_id,
    values,
    gaussians,
    base,
    context_stability,
    role_discipline,
    pressure_interrupt,
    iq,
    goal_noise_scale,
):
    return "\t".join([
        ",".join(str(value) for value in values),
        ",".join(str(value) for value in gaussians),
        str(base),
        str(context_stability),
        str(role_discipline),
        str(pressure_interrupt),
        str(iq),
        str(goal_noise_scale),
        case_id,
    ])


class _FixedGaussian:
    def __init__(self, values):
        self.values = list(values)

    def gauss(self, _mu, _sigma):
        return self.values.pop(0)


def _defensive_position_case_line(
    case_id,
    pos,
    ball_pos,
    own_goal_x,
    attackers,
    teammates,
    formation_pos,
):
    return "\t".join([
        str(pos[0]),
        str(pos[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(own_goal_x),
        "105.0",
        "68.0",
        _positions_payload(attackers),
        _positions_payload(teammates),
        str(formation_pos[0]),
        str(formation_pos[1]),
        case_id,
    ])


def _state_case_line(case_id, x, y, player_index, finishing, long_shot, attacking_right, opponents, teammates):
    return "\t".join([
        str(x),
        str(y),
        str(player_index),
        str(finishing),
        str(long_shot),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        "20.0",
        "0.50",
        "0.78",
        _positions_payload(opponents),
        _indexed_positions_payload(teammates),
        case_id,
    ])


def _pass_receive_case_line(
    case_id,
    x,
    y,
    receiver_index,
    finishing,
    long_shot,
    receiver_anchor,
    receiver_base,
    attacking_right,
    opponents,
    teammates,
    receiver_goal_type="-",
    receiver_goal_target=None,
    receiver_goal_value=0.0,
):
    goal_x, goal_y = ("-", "-") if receiver_goal_target is None else (
        str(receiver_goal_target[0]),
        str(receiver_goal_target[1]),
    )
    return "\t".join([
        str(x),
        str(y),
        str(receiver_index),
        str(finishing),
        str(long_shot),
        str(receiver_anchor[0]),
        str(receiver_anchor[1]),
        str(receiver_base[0]),
        str(receiver_base[1]),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        "20.0",
        "0.50",
        "0.78",
        _positions_payload(opponents),
        _indexed_positions_payload(teammates),
        receiver_goal_type,
        goal_x,
        goal_y,
        str(receiver_goal_value),
        case_id,
    ])


def _expected_pass_case_line(
    case_id,
    origin,
    target,
    passer_finishing,
    passer_long_shot,
    passer_consecutive_carries,
    receiver_index,
    receiver_finishing,
    receiver_long_shot,
    receiver_anchor,
    receiver_base,
    attacking_right,
    opponents,
    teammates,
    current_value,
    base_accuracy,
    receiver_arrival,
    continuity,
    receiver_goal_type="-",
    receiver_goal_target=None,
    receiver_goal_value=0.0,
):
    goal_x, goal_y = ("-", "-") if receiver_goal_target is None else (
        str(receiver_goal_target[0]),
        str(receiver_goal_target[1]),
    )
    return "\t".join([
        str(origin[0]),
        str(origin[1]),
        str(target[0]),
        str(target[1]),
        str(passer_finishing),
        str(passer_long_shot),
        str(passer_consecutive_carries),
        str(receiver_index),
        str(receiver_finishing),
        str(receiver_long_shot),
        str(receiver_anchor[0]),
        str(receiver_anchor[1]),
        str(receiver_base[0]),
        str(receiver_base[1]),
        "1" if attacking_right else "0",
        "105.0",
        "68.0",
        "3.5",
        "20.0",
        "0.50",
        "0.78",
        str(current_value),
        str(base_accuracy),
        str(receiver_arrival),
        str(continuity),
        _positions_payload(opponents),
        _indexed_positions_payload(teammates),
        receiver_goal_type,
        goal_x,
        goal_y,
        str(receiver_goal_value),
        case_id,
    ])


def _hold_case_line(
    case_id,
    iq,
    is_midfielder,
    is_defender,
    hold_ticks,
    possession_ticks,
    current_pv,
    pressure,
    nearest_pressure,
    developing_runs,
    best_pass_score,
    shoot_score,
    opportunity_wait_value,
):
    return "\t".join([
        str(iq),
        "1" if is_midfielder else "0",
        "1" if is_defender else "0",
        str(hold_ticks),
        str(possession_ticks),
        str(current_pv),
        str(pressure),
        str(nearest_pressure),
        str(developing_runs),
        str(best_pass_score),
        str(shoot_score),
        str(opportunity_wait_value),
        case_id,
    ])


def _shot_support_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{idx},{x},{y},{tx},{ty},{1 if is_gk else 0}"
        for idx, x, y, tx, ty, is_gk in players
    )


def _carry_support_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{idx},{x},{y},{bx},{by},{1 if is_gk else 0}"
        for idx, x, y, bx, by, is_gk in players
    )


def _defender_actions_payload(defenders):
    if not defenders:
        return "-"
    return ";".join(
        f"{idx},{x},{y},{nx},{ny},{action},{speed},{defence}"
        for idx, x, y, nx, ny, action, speed, defence in defenders
    )


def _shot_eval_case_line(
    case_id,
    shooter_index,
    shooter_pos,
    finishing,
    long_shot,
    possession_ticks,
    consecutive_carries,
    last_receive_origin,
    dist_to_goal,
    angle_factor,
    pressure_factor,
    lane_factor,
    dist_factor,
    current_state_value,
    attacking_right,
    opponents,
    teammates,
):
    return "\t".join([
        str(shooter_index),
        str(shooter_pos[0]),
        str(shooter_pos[1]),
        str(finishing / 100.0 if finishing > 1 else finishing),
        str(long_shot / 100.0 if long_shot > 1 else long_shot),
        str(possession_ticks),
        str(consecutive_carries),
        str(last_receive_origin[0]),
        str(last_receive_origin[1]),
        str(dist_to_goal),
        str(angle_factor),
        str(pressure_factor),
        str(lane_factor),
        str(dist_factor),
        str(current_state_value),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        "0.50",
        "0.78",
        "20.0",
        "1.0",
        _positions_payload(opponents),
        _shot_support_payload(teammates),
        case_id,
    ])


def _carry_eval_case_line(
    case_id,
    carrier_index,
    carrier_pos,
    target,
    finishing,
    long_shot,
    consecutive_carries,
    possession_ticks,
    target_pv,
    current_pv,
    current_state_value,
    path_feasibility,
    attacking_right,
    opponents,
    teammates,
):
    return "\t".join([
        str(carrier_index),
        str(carrier_pos[0]),
        str(carrier_pos[1]),
        str(target[0]),
        str(target[1]),
        str(finishing / 100.0 if finishing > 1 else finishing),
        str(long_shot / 100.0 if long_shot > 1 else long_shot),
        str(consecutive_carries),
        str(possession_ticks),
        str(target_pv),
        str(current_pv),
        str(current_state_value),
        str(path_feasibility),
        "105.0",
        "68.0",
        "1" if attacking_right else "0",
        "3.0",
        "20.0",
        "0.50",
        "0.78",
        _positions_payload(opponents),
        _carry_support_payload(teammates),
        case_id,
    ])


def _run_rust_mode(mode, lines):
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", mode],
        cwd=RUST_CRATE,
        input="\n".join(lines),
        text=True,
        capture_output=True,
        check=True,
    )
    values = {}
    for line in proc.stdout.strip().splitlines():
        case_id, raw_value = line.split("\t")
        values[case_id] = float(raw_value)
    return values


def _run_rust_rows(mode, lines):
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", mode],
        cwd=RUST_CRATE,
        input="\n".join(lines),
        text=True,
        capture_output=True,
        check=True,
    )
    rows = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rows[fields[0]] = fields[1:]
    return rows


def _assert_close_tuple(actual, expected, eps=1e-12):
    assert len(actual) == len(expected)
    for raw, py_value in zip(actual, expected):
        assert abs(float(raw) - py_value) < eps


def _test_smoothstep(edge0, edge1, value):
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def test_rust_physics_helpers_match_python():
    scalar_cases = [
        ("distance", (0.0, 0.0, 3.0, 4.0), py_physics.distance((0.0, 0.0), (3.0, 4.0))),
        ("distance", (-2.5, 7.25, 4.75, -3.0), py_physics.distance((-2.5, 7.25), (4.75, -3.0))),
        ("angle_to_goal", (90.0, 34.0, 105.0, 34.0, 7.32), py_physics.angle_to_goal((90.0, 34.0), (105.0, 34.0), 7.32)),
        ("angle_to_goal", (110.0, 25.0, 105.0, 34.0, 7.32), py_physics.angle_to_goal((110.0, 25.0), (105.0, 34.0), 7.32)),
        ("player_speed", (-10, 5.5, 2.5), py_physics.player_speed(-10, 5.5, 2.5)),
        ("player_speed", (0, 5.5, 2.5), py_physics.player_speed(0, 5.5, 2.5)),
        ("player_speed", (99, 5.5, 2.5), py_physics.player_speed(99, 5.5, 2.5)),
        ("player_speed", (130, 5.5, 2.5), py_physics.player_speed(130, 5.5, 2.5)),
        ("clamp", (-1.5, 0.0, 1.0), py_physics.clamp(-1.5, 0.0, 1.0)),
        ("clamp", (0.4, 0.0, 1.0), py_physics.clamp(0.4, 0.0, 1.0)),
        ("clamp", (3.0, 0.0, 1.0), py_physics.clamp(3.0, 0.0, 1.0)),
        ("angle_between_points", (0.0, 0.0, 0.0, 1.0), py_physics.angle_between_points((0.0, 0.0), (0.0, 1.0))),
        ("angle_between_points", (0.0, 0.0, -1.0, -1.0), py_physics.angle_between_points((0.0, 0.0), (-1.0, -1.0))),
        ("angle_diff", (0.0, 180.0), py_physics.angle_diff(0.0, 180.0)),
        ("angle_diff", (0.0, -180.0), py_physics.angle_diff(0.0, -180.0)),
        ("angle_diff", (170.0, -170.0), py_physics.angle_diff(170.0, -170.0)),
        ("angle_diff", (-170.0, 170.0), py_physics.angle_diff(-170.0, 170.0)),
        ("smoothstep", (0.0, 1.0, -0.5), 0.0),
        ("smoothstep", (0.0, 1.0, 0.5), 0.5),
        ("smoothstep", (1.0, 1.0, 1.5), 1.0),
    ]
    tuple_cases = [
        ("direction", (0.0, 0.0, 3.0, 4.0), py_physics.direction((0.0, 0.0), (3.0, 4.0))),
        ("direction", (2.0, 2.0, 2.0, 2.0), py_physics.direction((2.0, 2.0), (2.0, 2.0))),
        ("move_toward", (0.0, 0.0, 3.0, 4.0, 2.5), py_physics.move_toward((0.0, 0.0), (3.0, 4.0), 2.5)),
        ("move_toward", (0.0, 0.0, 3.0, 4.0, 5.0), py_physics.move_toward((0.0, 0.0), (3.0, 4.0), 5.0)),
        ("move_toward", (0.0, 0.0, 3.0, 4.0, -1.0), py_physics.move_toward((0.0, 0.0), (3.0, 4.0), -1.0)),
        ("interpolate", (0.0, 0.0, 10.0, 20.0, 0.25), py_physics.interpolate((0.0, 0.0), (10.0, 20.0), 0.25)),
        ("interpolate", (0.0, 0.0, 10.0, 20.0, 1.4), py_physics.interpolate((0.0, 0.0), (10.0, 20.0), 1.4)),
        ("midpoint", (-2.0, 4.0, 8.0, -6.0), py_physics.midpoint((-2.0, 4.0), (8.0, -6.0))),
        ("point_along", (2.0, 3.0, 45.0, 10.0), py_physics.point_along((2.0, 3.0), 45.0, 10.0)),
        ("point_along", (2.0, 3.0, -120.0, 7.5), py_physics.point_along((2.0, 3.0), -120.0, 7.5)),
    ]
    bool_cases = [
        ("is_in_fov", (0.0, 45.0, 45.0), py_physics.is_in_fov(0.0, 45.0, 45.0)),
        ("is_in_fov", (0.0, 46.0, 45.0), py_physics.is_in_fov(0.0, 46.0, 45.0)),
        ("is_in_fov", (170.0, -170.0, 25.0), py_physics.is_in_fov(170.0, -170.0, 25.0)),
    ]

    lines = []
    expected = {}
    idx = 0
    for op, args, py_value in scalar_cases:
        case_id = f"{op}_{idx}"
        lines.append("\t".join([op, *(str(value) for value in args), case_id]))
        expected[case_id] = ("scalar", py_value)
        idx += 1
    for op, args, py_value in tuple_cases:
        case_id = f"{op}_{idx}"
        lines.append("\t".join([op, *(str(value) for value in args), case_id]))
        expected[case_id] = ("tuple", py_value)
        idx += 1
    for op, args, py_value in bool_cases:
        case_id = f"{op}_{idx}"
        lines.append("\t".join([op, *(str(value) for value in args), case_id]))
        expected[case_id] = ("bool", py_value)
        idx += 1

    rust_rows = _run_rust_rows("physics", lines)
    for case_id, (kind, py_value) in expected.items():
        if kind == "scalar":
            assert abs(float(rust_rows[case_id][0]) - py_value) < 1e-12
        elif kind == "tuple":
            _assert_close_tuple(rust_rows[case_id], py_value)
        else:
            assert (rust_rows[case_id][0] == "1") is py_value


def _vision_player(index, x, y, iq=80, facing=0.0):
    player = Player(
        index=index,
        name=f"Vision {index}",
        position="CM",
        color="gold",
        abilities={"IQ": iq, "Speed": 70},
    )
    player.pos = (x, y)
    player.facing_direction = facing
    return player


def _visible_indices_payload(players):
    return ";".join(f"{p.index},{p.pos[0]},{p.pos[1]}" for p in players) if players else "-"


def _offside_opponents_payload(players):
    if not players:
        return "-"
    return ";".join(f"{p.pos[0]},{1 if p.is_goalkeeper else 0}" for p in players)


def _pass_space_players_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.index},{p.pos[0]},{p.pos[1]},{p.target_pos[0]},{p.target_pos[1]},{p.tactical_anchor[0]},{p.tactical_anchor[1]},{1 if p.is_goalkeeper else 0},{1 if p.is_defender else 0},{1 if p.is_midfielder else 0},{1 if p.is_wide else 0}"
        for p in players
    )


def _pass_risk_players_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.index},{p.pos[0]},{p.pos[1]},{p.speed_value},{1 if p.is_goalkeeper else 0}"
        for p in players
    )


def _pass_team_players_payload(players):
    if not players:
        return "-"
    parts = []
    for p in players:
        goal = getattr(p, "current_goal", None)
        goal_value = 0.0 if goal is None else goal.value
        goal_type = "-" if goal is None else goal.goal_type
        goal_x = "-" if goal is None else str(goal.target_pos[0])
        goal_y = "-" if goal is None else str(goal.target_pos[1])
        parts.append(",".join([
            str(p.index),
            str(p.pos[0]),
            str(p.pos[1]),
            str(p.target_pos[0]),
            str(p.target_pos[1]),
            str(p.tactical_anchor[0]),
            str(p.tactical_anchor[1]),
            "1" if p.is_goalkeeper else "0",
            str(p.speed_value),
            str(p.abilities.get("Finishing", 50) / 100.0),
            str(p.abilities.get("Long_Shot", 50) / 100.0),
            str(p.base_formation_pos[0]),
            str(p.base_formation_pos[1]),
            "1" if p.is_defender else "0",
            "1" if p.is_midfielder else "0",
            "1" if p.is_wide else "0",
            str(goal_value),
            goal_type,
            goal_x,
            goal_y,
        ]))
    return ";".join(parts)


def _off_ball_candidates_payload(candidates):
    if not candidates:
        return "-"
    return ";".join(
        f"{x},{y},{ax},{ay}"
        for x, y, ax, ay in candidates
    )


def _off_ball_teammates_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.index},{p.pos[0]},{p.pos[1]},{p.target_pos[0]},{p.target_pos[1]},{p.tactical_anchor[0]},{p.tactical_anchor[1]},{1 if p.is_goalkeeper else 0}"
        for p in players
    )


def _defense_teammates_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.pos[0]},{p.pos[1]},{p.target_pos[0]},{p.target_pos[1]}"
        for p in players
    )


def test_rust_vision_helpers_match_python():
    config = EngineConfig()
    scalar_cases = [
        (
            "compute_facing_direction",
            (10.0, 10.0, 20.0, 10.0, "-", "-"),
            py_vision.compute_facing_direction((10.0, 10.0), (20.0, 10.0)),
        ),
        (
            "compute_facing_direction",
            (10.0, 10.0, 20.0, 10.0, 10.0, 20.0),
            py_vision.compute_facing_direction((10.0, 10.0), (20.0, 10.0), (10.0, 20.0)),
        ),
        ("compute_fov", (30, config.vision_base_fov, config.vision_iq_bonus_factor), py_vision.compute_fov(30, config)),
        ("compute_fov", (80, config.vision_base_fov, config.vision_iq_bonus_factor), py_vision.compute_fov(80, config)),
        ("compute_fov", (220, config.vision_base_fov, config.vision_iq_bonus_factor), py_vision.compute_fov(220, config)),
        (
            "compute_vision_distance",
            (30, config.vision_base_distance, config.vision_iq_distance_bonus_factor, config.vision_max_distance),
            py_vision.compute_vision_distance(30, config),
        ),
        (
            "compute_vision_distance",
            (120, config.vision_base_distance, config.vision_iq_distance_bonus_factor, config.vision_max_distance),
            py_vision.compute_vision_distance(120, config),
        ),
        (
            "compute_vision_distance",
            (200, config.vision_base_distance, config.vision_iq_distance_bonus_factor, config.vision_max_distance),
            py_vision.compute_vision_distance(200, config),
        ),
        ("compute_player_facing", (0.0, True), py_vision.compute_player_facing(_vision_player(0, 0.0, 0.0, facing=0.0), True)),
        ("compute_player_facing", (0.0, False), py_vision.compute_player_facing(_vision_player(0, 0.0, 0.0, facing=0.0), False)),
        ("compute_player_facing", (0.0005, True), py_vision.compute_player_facing(_vision_player(0, 0.0, 0.0, facing=0.0005), True)),
        ("compute_player_facing", (45.0, True), py_vision.compute_player_facing(_vision_player(0, 0.0, 0.0, facing=45.0), True)),
    ]
    lines = []
    expected_scalar = {}
    for idx, (op, args, py_value) in enumerate(scalar_cases):
        case_id = f"{op}_{idx}"
        lines.append("\t".join([op, *(str(value) for value in args), case_id]))
        expected_scalar[case_id] = py_value

    context_cases = [
        ("context_front", _vision_player(1, 10.0, 10.0, iq=80, facing=0.0), True, (10.0, 10.0), (30.0, 10.0)),
        ("context_side", _vision_player(1, 10.0, 10.0, iq=92, facing=30.0), True, (10.0, 10.0), (20.0, 35.0)),
        ("context_back", _vision_player(1, 10.0, 10.0, iq=120, facing=0.0), False, (10.0, 10.0), (-60.0, 10.0)),
    ]
    expected_context = {}
    for case_id, player, attacking_right, origin, target in context_cases:
        context = py_vision.build_vision_context(player, config, attacking_right)
        lines.append("\t".join([
            "context",
            str(player.iq_value),
            str(player.facing_direction),
            "1" if attacking_right else "0",
            str(config.vision_base_fov),
            str(config.vision_iq_bonus_factor),
            str(config.vision_base_distance),
            str(config.vision_iq_distance_bonus_factor),
            str(config.vision_max_distance),
            str(origin[0]),
            str(origin[1]),
            str(target[0]),
            str(target[1]),
            case_id,
        ]))
        expected_context[case_id] = (
            context.facing,
            context.fov,
            context.half_fov,
            context.max_distance,
            context.confidence(origin, target),
            context.visible(origin, target),
        )

    passer = _vision_player(0, 0.0, 0.0, iq=80)
    visible_group = [
        passer,
        _vision_player(1, 10.0, 0.0),
        _vision_player(2, -10.0, 0.0),
        _vision_player(3, 4.0, 8.0),
    ]
    fallback_group = [
        passer,
        _vision_player(4, -10.0, 5.0),
        _vision_player(5, -12.0, -5.0),
    ]
    visible_cases = [
        ("visible_front", passer, visible_group, (10.0, 0.0)),
        ("visible_fallback", passer, fallback_group, (10.0, 0.0)),
    ]
    expected_visible = {}
    for case_id, passer_obj, teammates, ball_pos in visible_cases:
        lines.append("\t".join([
            "visible_indices",
            str(passer_obj.index),
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            str(passer_obj.iq_value),
            str(ball_pos[0]),
            str(ball_pos[1]),
            str(config.vision_base_fov),
            _visible_indices_payload(teammates),
            str(config.vision_iq_bonus_factor),
            case_id,
        ]))
        expected_visible[case_id] = [p.index for p in py_vision.get_visible_targets(passer_obj, teammates, ball_pos, config)]

    target_cases = [
        ("target_front", passer, (12.0, 2.0), (10.0, 0.0)),
        ("target_back", passer, (-12.0, 2.0), (10.0, 0.0)),
    ]
    expected_target = {}
    for case_id, passer_obj, target, ball_pos in target_cases:
        lines.append("\t".join([
            "is_target_visible",
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            str(passer_obj.iq_value),
            str(target[0]),
            str(target[1]),
            str(ball_pos[0]),
            str(ball_pos[1]),
            str(config.vision_base_fov),
            str(config.vision_iq_bonus_factor),
            case_id,
        ]))
        expected_target[case_id] = py_vision.is_target_visible(passer_obj, target, ball_pos, config)

    rust_rows = _run_rust_rows("vision", lines)
    for case_id, py_value in expected_scalar.items():
        assert abs(float(rust_rows[case_id][0]) - py_value) < 1e-12
    for case_id, py_values in expected_context.items():
        _assert_close_tuple(rust_rows[case_id][:5], py_values[:5])
        assert (rust_rows[case_id][5] == "1") is py_values[5]
    for case_id, expected_indices in expected_visible.items():
        raw = rust_rows[case_id][0]
        rust_indices = [] if raw == "-" else [int(value) for value in raw.split(",")]
        assert rust_indices == expected_indices
    for case_id, py_value in expected_target.items():
        assert (rust_rows[case_id][0] == "1") is py_value


def test_rust_offside_helpers_match_python():
    config = EngineConfig()
    passer = _vision_player(0, 50.0, 34.0)

    def opp(idx, x, y=34.0, position="CB"):
        player = _vision_player(idx, x, y)
        player.position = position
        return player

    line_cases = [
        ("right_mixed", True, [opp(1, 104.0, position="GK"), opp(2, 88.0), opp(3, 80.0), opp(4, 92.0)]),
        ("left_mixed", False, [opp(1, 1.0, position="GK"), opp(2, 20.0), opp(3, 25.0), opp(4, 18.0)]),
        ("right_one", True, [opp(1, 100.0, position="GK"), opp(2, 78.0)]),
        ("left_none", False, [opp(1, 2.0, position="GK")]),
    ]
    lines = []
    expected_line = {}
    for case_id, attacking_right, opponents in line_cases:
        lines.append("\t".join([
            "line",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            _offside_opponents_payload(opponents),
            case_id,
        ]))
        expected_line[case_id] = passer._get_offside_line(opponents, attacking_right, config)

    position_cases = [
        ("right_onside_half", (52.0, 34.0), True, 50.0, None),
        ("right_ahead_ball", (82.0, 34.0), True, 80.0, 70.0),
        ("right_behind_ball", (82.0, 34.0), True, 80.0, 84.0),
        ("right_on_line", (80.0, 34.0), True, 80.0, 70.0),
        ("left_ahead_ball", (20.0, 34.0), False, 22.0, 30.0),
        ("left_behind_ball", (20.0, 34.0), False, 22.0, 18.0),
        ("left_no_ball", (20.0, 34.0), False, 22.0, None),
    ]
    expected_position = {}
    for case_id, pos, attacking_right, offside_line, ball_x in position_cases:
        lines.append("\t".join([
            "position",
            str(pos[0]),
            str(pos[1]),
            "1" if attacking_right else "0",
            str(offside_line),
            str(config.pitch_length),
            "-" if ball_x is None else str(ball_x),
            case_id,
        ]))
        expected_position[case_id] = passer._is_offside_position(
            pos,
            attacking_right,
            offside_line,
            config,
            ball_x=ball_x,
        )

    rust_rows = _run_rust_rows("offside", lines)
    for case_id, py_value in expected_line.items():
        assert abs(float(rust_rows[case_id][0]) - py_value) < 1e-12
    for case_id, py_value in expected_position.items():
        assert (rust_rows[case_id][0] == "1") is py_value


def _generic_pass_space_candidates_python(
    passer,
    teammates,
    opponents,
    config,
    pitch,
    attacking_right,
):
    import math

    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    forward_dir = 1.0 if attacking_right else -1.0
    vision = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    front_anchors = []
    for tm in teammates:
        if tm.index == passer.index or tm.is_goalkeeper:
            continue
        anchor_progress = (
            tm.tactical_anchor[0] / config.pitch_length
            if attacking_right
            else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
        )
        if anchor_progress > 0.58:
            front_anchors.append(tm.tactical_anchor)
    front_center = None
    if front_anchors:
        front_center = (
            sum(p[0] for p in front_anchors) / len(front_anchors),
            sum(p[1] for p in front_anchors) / len(front_anchors),
        )
    generic_centers = [passer.pos]
    if front_center is not None:
        generic_centers.append(front_center)
    if teammates:
        visible_anchors = [
            tm.tactical_anchor
            for tm in teammates
            if tm.index != passer.index
            and not tm.is_goalkeeper
            and vision.confidence(passer.pos, tm.tactical_anchor) > 0.0
        ]
        if visible_anchors:
            generic_centers.append((
                sum(p[0] for p in visible_anchors) / len(visible_anchors),
                sum(p[1] for p in visible_anchors) / len(visible_anchors),
            ))
    candidates = []
    seen_space_points = set()
    for center in generic_centers:
        for radius in (8.0, 16.0, 28.0, 40.0):
            for angle_deg in (-150, -105, -60, -25, 0, 25, 60, 105, 150):
                angle = math.radians(angle_deg)
                target = pitch.clamp(
                    center[0] + math.cos(angle) * radius * forward_dir,
                    center[1] + math.sin(angle) * radius,
                )
                key = (round(target[0], 1), round(target[1], 1))
                if key in seen_space_points:
                    continue
                seen_space_points.add(key)
                visibility = vision.confidence(passer.pos, target)
                if visibility <= 0.0:
                    continue
                if passer._is_offside_position(target, attacking_right, offside_line, config, ball_x=passer.pos[0]):
                    continue
                pass_distance = py_physics.distance(passer.pos, target)
                if pass_distance < 6.0 or pass_distance > 55.0:
                    continue
                pv = position_value(
                    target[0],
                    target[1],
                    pitch,
                    attacking_right,
                    opp_positions,
                    tm_positions,
                    config,
                )
                forward_gain = max(0.0, (target[0] - passer.pos[0]) * forward_dir) / max(1.0, config.pitch_length)
                distance_fit = 1.0 - max(0.0, pass_distance - 34.0) / 30.0
                score = pv * (0.45 + 0.55 * visibility) * (0.72 + 0.28 * forward_gain) * max(0.25, distance_fit)
                candidates.append((score, target[0], target[1], visibility, pv))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[:10]


def _receiver_base_targets_python(passer, receiver, receiver_goal, config, pitch, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    vision = py_vision.build_vision_context(passer, config, attacking_right)
    receiver_visibility = vision.confidence(passer.pos, receiver.pos)
    target_visibility = max(
        receiver_visibility,
        vision.confidence(passer.pos, receiver.target_pos),
        vision.confidence(passer.pos, receiver.tactical_anchor),
    )
    low_visibility = target_visibility < 0.18
    raw_targets = [(receiver.pos, 1.0)]
    receiver_goal_fit = 0.0
    if receiver_goal is not None and receiver_goal.goal_type in ("arc_arrival_for_cutback", "attack_far_post"):
        goal_visibility = vision.confidence(passer.pos, receiver_goal.target_pos)
        goal_dist = py_physics.distance(receiver.pos, receiver_goal.target_pos)
        target_progress_hint = (
            receiver_goal.target_pos[0] / config.pitch_length
            if attacking_right
            else (config.pitch_length - receiver_goal.target_pos[0]) / config.pitch_length
        )
        carrier_progress_hint = (
            passer.pos[0] / config.pitch_length
            if attacking_right
            else (config.pitch_length - passer.pos[0]) / config.pitch_length
        )
        support_depth = carrier_progress_hint - target_progress_hint
        target_centrality_hint = 1.0 - min(
            1.0,
            abs(receiver_goal.target_pos[1] - config.pitch_width / 2.0)
            / (config.pitch_width / 2.0),
        )
        if receiver_goal.goal_type == "arc_arrival_for_cutback":
            receiver_goal_fit = (
                _test_smoothstep(0.56, 0.84, target_progress_hint)
                * (1.0 - _test_smoothstep(0.86, 0.96, target_progress_hint))
                * (1.0 - _test_smoothstep(0.18, 0.34, abs(support_depth)))
                * _test_smoothstep(0.42, 0.84, target_centrality_hint)
                * (1.0 - _test_smoothstep(18.0, 42.0, goal_dist))
                * _test_smoothstep(0.005, 0.080, receiver_goal.value)
            )
        else:
            receiver_goal_fit = (
                _test_smoothstep(0.76, 0.94, target_progress_hint)
                * _test_smoothstep(0.22, 0.76, target_centrality_hint)
                * (1.0 - _test_smoothstep(16.0, 42.0, goal_dist))
                * _test_smoothstep(0.005, 0.080, receiver_goal.value)
            )
        receiver_goal_fit *= 0.35 + 0.65 * goal_visibility
        target_visibility = max(target_visibility, goal_visibility)
        low_visibility = target_visibility < 0.18
        if receiver_goal_fit > 0.0:
            raw_targets.append((receiver_goal.target_pos, 0.62 + 0.22 * receiver_goal_fit))

    future_x = receiver.pos[0] + (receiver.target_pos[0] - receiver.pos[0]) * 0.5
    future_y = receiver.pos[1] + (receiver.target_pos[1] - receiver.pos[1]) * 0.5
    raw_targets.append((pitch.clamp(future_x, future_y), 0.92))

    support_x = receiver.pos[0] * 0.65 + passer.pos[0] * 0.35
    support_y = receiver.pos[1] * 0.70 + passer.pos[1] * 0.30
    raw_targets.append((pitch.clamp(support_x, support_y), 0.88))

    switch_y = receiver.pos[1] * 0.45 + (config.pitch_width - passer.pos[1]) * 0.55
    if not low_visibility:
        raw_targets.append((pitch.clamp(support_x, switch_y), 0.76))

    tm_width_ratio = min(1.0, abs(receiver.tactical_anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
    tm_progress_hint = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    if not low_visibility and tm_width_ratio > 0.50 and tm_progress_hint > 0.56:
        wide_lane_y = receiver.tactical_anchor[1] * 0.72 + receiver.pos[1] * 0.28
        wide_lane_x = max(receiver.pos[0], receiver.tactical_anchor[0]) if attacking_right else min(receiver.pos[0], receiver.tactical_anchor[0])
        raw_targets.append((
            pitch.clamp(wide_lane_x + forward_dir * 4.0, wide_lane_y),
            0.78,
        ))

    move_progress = (receiver.target_pos[0] - receiver.pos[0]) * forward_dir
    if not low_visibility and move_progress > 1.0:
        lead_x = receiver.pos[0] + forward_dir * min(12.0, 4.0 + move_progress)
        lead_y = receiver.pos[1] + (receiver.target_pos[1] - receiver.pos[1]) * 0.35
        raw_targets.append((pitch.clamp(lead_x, lead_y), 0.82))

    return {
        "targets": [(target[0], target[1], arrival) for target, arrival in raw_targets],
        "receiver_visibility": receiver_visibility,
        "target_visibility": target_visibility,
        "low_visibility": low_visibility,
        "receiver_goal_fit": receiver_goal_fit,
    }


def _value_field_targets_python(receiver, receiver_goal_target, generic_candidates, config, attacking_right):
    role_progress = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    role_fit = _test_smoothstep(0.38, 0.76, role_progress) * (0.55 if receiver.is_defender else 1.0)
    results = []
    for space_score, target_x, target_y, visibility, target_space_value in generic_candidates:
        target = (target_x, target_y)
        goal_fit = 0.0 if receiver_goal_target is None else 1.0 - py_physics.distance(receiver_goal_target, target) / 18.0
        arrival_fit = max(
            0.0,
            1.0 - py_physics.distance(receiver.pos, target) / 28.0,
            1.0 - py_physics.distance(receiver.target_pos, target) / 24.0,
            1.0 - py_physics.distance(receiver.tactical_anchor, target) / 22.0,
            goal_fit,
        )
        expected_arrival = max(0.0, min(1.0, space_score * (0.30 + 0.48 * arrival_fit + 0.22 * role_fit) * 1.35))
        if expected_arrival < 0.18:
            continue
        results.append((
            target_x,
            target_y,
            max(0.42, expected_arrival),
            space_score,
            target_space_value,
            visibility,
            expected_arrival,
            arrival_fit,
        ))
    return results


def _stale_release_targets_python(passer, receiver, low_visibility, config, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    carrier_progress = (
        passer.pos[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - passer.pos[0]) / config.pitch_length
    )
    if (
        low_visibility
        or passer.consecutive_carries < 3
        or carrier_progress <= 0.62
        or receiver.is_defender
    ):
        return []
    outlet_dist = py_physics.distance(receiver.pos, passer.pos)
    if not (4.0 < outlet_dist < 34.0):
        return []
    stale_release = min(1.0, (passer.consecutive_carries - 2) / 4.0)
    support_weight = 1.0 if receiver.is_midfielder or receiver.is_wide else 0.72
    outlet_x = receiver.pos[0] + (receiver.target_pos[0] - receiver.pos[0]) * 0.35
    outlet_y = receiver.pos[1] + (receiver.target_pos[1] - receiver.pos[1]) * 0.35
    targets = [
        (*pitch_clamp_tuple(outlet_x, outlet_y, config), 0.86 * support_weight),
        (receiver.pos[0], receiver.pos[1], 0.90 * support_weight),
    ]
    lateral_sign = 1.0 if receiver.pos[1] >= passer.pos[1] else -1.0
    release_depth = 4.0 + 6.0 * stale_release
    release_width = min(12.0, max(4.0, abs(receiver.pos[1] - passer.pos[1]) * 0.50 + 4.0))
    release_x = passer.pos[0] - forward_dir * release_depth
    release_y = passer.pos[1] + lateral_sign * release_width
    if py_physics.distance((release_x, release_y), receiver.pos) < 28.0:
        targets.append((*pitch_clamp_tuple(release_x, release_y, config), 0.80 * support_weight))

    anchor_x = receiver.tactical_anchor[0] * 0.55 + receiver.pos[0] * 0.45
    anchor_y = receiver.tactical_anchor[1] * 0.70 + receiver.pos[1] * 0.30
    if py_physics.distance((anchor_x, anchor_y), passer.pos) < 34.0:
        targets.append((*pitch_clamp_tuple(anchor_x, anchor_y, config), 0.78 * support_weight))
    return targets


def _layoff_targets_python(passer, receiver, low_visibility, config, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    carrier_progress = (
        passer.pos[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - passer.pos[0]) / config.pitch_length
    )
    if low_visibility or carrier_progress <= 0.80 or receiver.is_defender:
        return []
    side_sign = 1.0 if receiver.tactical_anchor[1] >= config.pitch_width / 2.0 else -1.0
    raw_targets = (
        (passer.pos[0] - forward_dir * 5.0, config.pitch_width / 2.0, 0.76),
        (passer.pos[0] - forward_dir * 7.0, passer.pos[1] + side_sign * 5.0, 0.70),
        (passer.pos[0] - forward_dir * 9.0, receiver.tactical_anchor[1] * 0.45 + config.pitch_width / 2.0 * 0.55, 0.66),
    )
    targets = []
    for x, y, arrival in raw_targets:
        target = pitch_clamp_tuple(x, y, config)
        if py_physics.distance(target, receiver.pos) < 34.0:
            targets.append((*target, arrival))
    return targets


def _second_line_targets_python(passer, receiver, low_visibility, config, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    carrier_progress = (
        passer.pos[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - passer.pos[0]) / config.pitch_length
    )
    tm_base = receiver.base_formation_pos if receiver.base_formation_pos != (0.0, 0.0) else receiver.tactical_anchor
    tm_base_progress = (
        tm_base[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - tm_base[0]) / config.pitch_length
    )
    tm_progress_hint = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    second_line_role = (
        0.42 <= tm_base_progress <= 0.68
        and not receiver.is_defender
        and tm_progress_hint > 0.60
    )
    if low_visibility or carrier_progress <= 0.68 or not second_line_role:
        return []
    goal_side_x = config.pitch_length if attacking_right else 0.0
    arc_x = goal_side_x - forward_dir * 24.0
    support_x = (
        receiver.tactical_anchor[0] * 0.42
        + receiver.target_pos[0] * 0.26
        + arc_x * 0.32
    )
    support_y = (
        receiver.tactical_anchor[1] * 0.40
        + receiver.target_pos[1] * 0.20
        + config.pitch_width / 2.0 * 0.40
    )
    target = pitch_clamp_tuple(support_x, support_y, config)
    if py_physics.distance(target, receiver.pos) < 30.0:
        return [(*target, 0.72)]
    return []


def _box_delivery_targets_python(passer, receiver, low_visibility, config, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    carrier_progress = (
        passer.pos[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - passer.pos[0]) / config.pitch_length
    )
    carrier_width = abs(passer.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
    if low_visibility or carrier_progress <= 0.68 or carrier_width <= 0.34 or receiver.is_defender:
        return []
    target_role_progress = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    if target_role_progress <= 0.54:
        return []
    goal_side_x = config.pitch_length if attacking_right else 0.0
    box_edge_x = goal_side_x - forward_dir * 15.5
    cutback_x = min(box_edge_x, passer.pos[0] + forward_dir * 7.0) if attacking_right else max(box_edge_x, passer.pos[0] + forward_dir * 7.0)
    near_box_x = goal_side_x - forward_dir * 12.0
    center_y = config.pitch_width / 2.0
    carrier_side = 1.0 if passer.pos[1] >= center_y else -1.0
    delivery_targets = (
        (cutback_x, center_y, 0.66),
        (cutback_x, center_y + carrier_side * config.pitch_width * 0.10, 0.62),
        (near_box_x, center_y, 0.54),
        (near_box_x, center_y + carrier_side * config.pitch_width * 0.12, 0.50),
    )
    targets = []
    for tx, ty, arrival in delivery_targets:
        target = pitch_clamp_tuple(tx, ty, config)
        if py_physics.distance(target, receiver.pos) < 32.0:
            targets.append((*target, arrival))
    runner_x = receiver.pos[0] + (receiver.target_pos[0] - receiver.pos[0]) * 0.65
    runner_y = receiver.pos[1] + (receiver.target_pos[1] - receiver.pos[1]) * 0.65
    runner_target = pitch_clamp_tuple(
        runner_x,
        runner_y + (center_y - runner_y) * 0.35,
        config,
    )
    if py_physics.distance(runner_target, receiver.pos) < 18.0:
        targets.append((*runner_target, 0.74))
    return targets


def _delivery_space_targets_python(passer, receiver, low_visibility, config, attacking_right):
    forward_dir = 1.0 if attacking_right else -1.0
    receiver_forward = max(
        0.0,
        (receiver.tactical_anchor[0] - receiver.pos[0]) * forward_dir,
        (receiver.target_pos[0] - receiver.pos[0]) * forward_dir,
    )
    carrier_progress = (
        passer.pos[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - passer.pos[0]) / config.pitch_length
    )
    target_progress_hint = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    delivery_pressure = max(carrier_progress, target_progress_hint)
    central_pull = config.pitch_width / 2.0 - receiver.pos[1]
    if low_visibility or delivery_pressure <= 0.70 or not (receiver_forward > 0.5 or target_progress_hint > 0.76):
        return []
    targets = []
    for depth_scale, center_scale, arrival_base in (
        (0.45, 0.35, 0.74),
        (0.75, 0.55, 0.66),
        (1.05, 0.72, 0.58),
    ):
        run_depth = 3.0 + min(12.0, receiver_forward + 6.0) * depth_scale
        target = pitch_clamp_tuple(
            receiver.pos[0] + forward_dir * run_depth,
            receiver.pos[1] + central_pull * center_scale,
            config,
        )
        targets.append((*target, arrival_base))
    if carrier_progress > 0.82 and abs(passer.pos[1] - config.pitch_width / 2.0) > config.pitch_width * 0.14:
        for depth_scale, center_scale, arrival_base in (
            (0.20, 0.58, 0.70),
            (-0.15, 0.70, 0.64),
        ):
            support_depth = min(9.0, receiver_forward + 4.0) * depth_scale
            target_x = receiver.pos[0] + forward_dir * support_depth
            target_x = min(target_x, passer.pos[0] - 0.5) if attacking_right else max(target_x, passer.pos[0] + 0.5)
            target = pitch_clamp_tuple(
                target_x,
                receiver.pos[1] + central_pull * center_scale,
                config,
            )
            targets.append((*target, arrival_base))
    return targets


def pitch_clamp_tuple(x, y, config):
    return (
        max(0.5, min(config.pitch_length - 0.5, x)),
        max(0.5, min(config.pitch_width - 0.5, y)),
    )


def _receiver_spatial_candidates_python(
    passer,
    receiver,
    front_center,
    low_visibility,
    opponents,
    teammates,
    config,
    pitch,
    attacking_right,
):
    import math

    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    forward_dir = 1.0 if attacking_right else -1.0
    vision = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    spatial_candidates = []
    tm_anchor_progress = (
        receiver.tactical_anchor[0] / config.pitch_length
        if attacking_right
        else (config.pitch_length - receiver.tactical_anchor[0]) / config.pitch_length
    )
    tm_anchor_progress = max(0.0, min(1.0, tm_anchor_progress))
    tm_width_factor = min(1.0, abs(receiver.tactical_anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
    search_radius = 6.0 + 10.0 * tm_anchor_progress + 3.0 * tm_width_factor
    if not low_visibility:
        sample_angles = (-150, -105, -60, -25, 0, 25, 60, 105, 150)
        sample_radii = (search_radius * 0.55, search_radius)
        for center in (receiver.pos, receiver.target_pos, receiver.tactical_anchor):
            for radius in sample_radii:
                for angle_deg in sample_angles:
                    angle = math.radians(angle_deg)
                    ax = math.cos(angle) * radius * forward_dir
                    ay = math.sin(angle) * radius
                    pos = pitch.clamp(center[0] + ax, center[1] + ay)
                    point_visibility = vision.confidence(passer.pos, pos)
                    if point_visibility <= 0.0:
                        continue
                    if passer._is_offside_position(pos, attacking_right, offside_line, config, ball_x=passer.pos[0]):
                        continue
                    d_from_receiver = py_physics.distance(pos, receiver.pos)
                    if d_from_receiver > search_radius * 1.50:
                        continue
                    pv = position_value(
                        pos[0],
                        pos[1],
                        pitch,
                        attacking_right,
                        opp_positions,
                        tm_positions,
                        config,
                        runner_formation_pos=receiver.tactical_anchor,
                    )
                    receiver_arrival = max(0.25, 1.0 - d_from_receiver / (search_radius * 1.65))
                    spatial_candidates.append((
                        pv * receiver_arrival * (0.55 + 0.45 * point_visibility),
                        pos[0],
                        pos[1],
                        receiver_arrival,
                        pv,
                        point_visibility,
                    ))

    if not low_visibility and front_center is not None and tm_anchor_progress > 0.50:
        for angle_deg in (-60, -25, 0, 25, 60):
            angle = math.radians(angle_deg)
            radius = search_radius * 0.85
            pos = pitch.clamp(
                front_center[0] + math.cos(angle) * radius * forward_dir,
                front_center[1] + math.sin(angle) * radius,
            )
            point_visibility = vision.confidence(passer.pos, pos)
            if point_visibility <= 0.0:
                continue
            if passer._is_offside_position(pos, attacking_right, offside_line, config, ball_x=passer.pos[0]):
                continue
            d_from_receiver = py_physics.distance(pos, receiver.pos)
            pv = position_value(
                pos[0],
                pos[1],
                pitch,
                attacking_right,
                opp_positions,
                tm_positions,
                config,
                runner_formation_pos=receiver.tactical_anchor,
            )
            receiver_arrival = max(0.22, 1.0 - d_from_receiver / (search_radius * 1.90))
            spatial_candidates.append((
                pv * receiver_arrival * (0.55 + 0.45 * point_visibility),
                pos[0],
                pos[1],
                receiver_arrival,
                pv,
                point_visibility,
            ))

    spatial_candidates.sort(key=lambda item: item[0], reverse=True)
    return spatial_candidates[:3]


def _raw_pass_prevalue_python(
    passer,
    receiver,
    target,
    initial_receiver_arrival,
    receiver_visibility,
    receiver_goal_target,
    receiver_goal_value,
    receiver_goal_fit,
    opponents,
    teammates,
    config,
    pitch,
    attacking_right,
):
    vision = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    receiver_arrival = initial_receiver_arrival
    d = py_physics.distance(passer.pos, target)
    target_kind_space = py_physics.distance(target, receiver.pos) > 4.0
    invalid = {
        "valid": False,
        "receiver_arrival": receiver_arrival,
        "base_accuracy": 0.0,
        "continuity": 0.0,
        "perception": 0.0,
        "perception_multiplier": 0.0,
        "arrival_margin": 0.0,
        "receiver_time": 0.0,
        "defender_time": float("inf"),
        "defender_first_risk": 0.0,
        "target_occupation_risk": 0.0,
        "nearest_teammate_to_target": 0.0,
        "nearest_opp_to_target": 0.0,
        "box_space_pressure": 0.0,
        "goal_target_fit": 0.0,
        "is_long": False,
        "target_kind_space": target_kind_space,
        "distance": d,
    }
    if d < 3.0 or d > 55.0:
        return invalid

    perception = vision.confidence(passer.pos, target)
    if perception <= 0.0 and target_kind_space:
        return invalid

    if passer._is_offside_position(target, attacking_right, offside_line, config, ball_x=passer.pos[0]):
        receiver_arrival *= 0.25

    tm_speed = py_physics.player_speed(receiver.speed_value, config.player_max_speed, config.player_min_speed)
    receiver_time = py_physics.distance(receiver.pos, target) / max(0.1, tm_speed)
    defender_time = float("inf")
    nearest_opp_to_target = float("inf")
    for opp in opponents:
        nearest_opp_to_target = min(nearest_opp_to_target, py_physics.distance(opp.pos, target))
        opp_speed = py_physics.player_speed(opp.speed_value, config.player_max_speed, config.player_min_speed)
        if opp.is_goalkeeper:
            goal_x = config.pitch_length if attacking_right else 0.0
            goal_dist = abs(target[0] - goal_x)
            if goal_dist > 24.0:
                continue
            opp_speed *= 1.18
        defender_time = min(defender_time, py_physics.distance(opp.pos, target) / max(0.1, opp_speed))

    nearest_teammate_to_target = min(
        [
            py_physics.distance(teammate.pos, target)
            for teammate in teammates
            if teammate.index != passer.index and not teammate.is_goalkeeper
        ],
        default=py_physics.distance(receiver.pos, target),
    )
    arrival_margin = defender_time - receiver_time
    if arrival_margin < 0.0:
        receiver_arrival *= max(0.10, 1.0 + arrival_margin / 3.5)
    else:
        receiver_arrival *= 0.78 + 0.22 * min(1.0, arrival_margin / 4.0)

    defender_first_risk = _test_smoothstep(0.2, 3.8, -arrival_margin)
    target_occupation_risk = max(
        _test_smoothstep(0.6, 4.0, nearest_teammate_to_target - nearest_opp_to_target),
        (1.0 - _test_smoothstep(0.8, 3.2, nearest_opp_to_target))
        * _test_smoothstep(2.5, 7.0, nearest_teammate_to_target),
    )
    target_progress_for_risk = (
        target[0] / max(1.0, pitch.length)
        if attacking_right
        else (pitch.length - target[0]) / max(1.0, pitch.length)
    )
    target_centrality_for_risk = 1.0 - min(
        1.0,
        abs(target[1] - pitch.width / 2.0) / (pitch.width / 2.0),
    )
    box_space_pressure = (
        _test_smoothstep(0.78, 0.90, target_progress_for_risk)
        * _test_smoothstep(0.45, 0.85, target_centrality_for_risk)
        * _test_smoothstep(4.0, 16.0, py_physics.distance(receiver.pos, target))
    )
    if box_space_pressure > 0.0:
        required_margin = 0.8 + 1.8 * box_space_pressure
        margin_factor = max(0.24, min(1.0, (arrival_margin + 1.2) / required_margin))
        receiver_arrival *= 1.0 - box_space_pressure * (1.0 - margin_factor)
    if defender_first_risk > 0.0:
        receiver_arrival *= 1.0 - 0.62 * defender_first_risk
    if target_occupation_risk > 0.0:
        receiver_arrival *= 1.0 - 0.72 * target_occupation_risk

    is_long = d > 30.0
    passing = passer.abilities.get("Long_Passing" if is_long else "Short_Passing", 50) / 100.0
    base = config.long_pass_base_success if is_long else config.short_pass_base_success
    dist_factor = max(0.35, 1.0 - max(0.0, d - 10.0) / 65.0)
    base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor

    goal_target_fit = 0.0
    if receiver_goal_target is not None:
        goal_target_fit = max(0.0, 1.0 - py_physics.distance(target, receiver_goal_target) / 14.0) * receiver_goal_fit
        if goal_target_fit > 0.0:
            receiver_arrival = min(1.0, receiver_arrival * (1.0 + 0.10 * goal_target_fit))

    continuity = 0.075 if py_physics.distance(target, receiver.pos) <= 4.0 else 0.045
    continuity += 0.065 * goal_target_fit * max(0.0, min(1.0, receiver_goal_value * 2.4))
    perception_floor = 0.35 if not target_kind_space else 0.0
    perception_multiplier = 0.48 + 0.52 * max(
        perception,
        perception_floor,
        receiver_visibility * 0.55,
    )
    receiver_arrival *= perception_multiplier

    return {
        "valid": True,
        "receiver_arrival": receiver_arrival,
        "base_accuracy": base_accuracy,
        "continuity": continuity,
        "perception": perception,
        "perception_multiplier": perception_multiplier,
        "arrival_margin": arrival_margin,
        "receiver_time": receiver_time,
        "defender_time": defender_time,
        "defender_first_risk": defender_first_risk,
        "target_occupation_risk": target_occupation_risk,
        "nearest_teammate_to_target": nearest_teammate_to_target,
        "nearest_opp_to_target": nearest_opp_to_target,
        "box_space_pressure": box_space_pressure,
        "goal_target_fit": goal_target_fit,
        "is_long": is_long,
        "target_kind_space": target_kind_space,
        "distance": d,
    }


def _generic_candidates_payload(candidates):
    if not candidates:
        return "-"
    return ";".join(",".join(str(value) for value in item) for item in candidates)


def test_rust_generic_pass_space_candidates_match_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, anchor, position="CM", iq=92, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.tactical_anchor = anchor
        return p

    cases = []
    passer = player(0, 50.0, 34.0, (50.0, 34.0), iq=96, facing=0.0)
    teammates = [
        passer,
        player(1, 67.0, 20.0, (78.0, 18.0), "RW"),
        player(2, 68.0, 48.0, (76.0, 50.0), "LW"),
        player(3, 56.0, 34.0, (62.0, 34.0), "CM"),
        player(4, 8.0, 34.0, (8.0, 34.0), "GK"),
    ]
    opponents = [
        player(10, 86.0, 28.0, (86.0, 28.0), "CB"),
        player(11, 90.0, 40.0, (90.0, 40.0), "CB"),
        player(12, 103.0, 34.0, (103.0, 34.0), "GK"),
    ]
    cases.append(("right_attack", passer, teammates, opponents, True))

    left_passer = player(0, 55.0, 30.0, (55.0, 30.0), iq=88, facing=180.0)
    left_teammates = [
        left_passer,
        player(1, 36.0, 18.0, (28.0, 18.0), "LW", iq=82, facing=180.0),
        player(2, 38.0, 50.0, (30.0, 50.0), "RW", iq=82, facing=180.0),
        player(3, 49.0, 36.0, (44.0, 36.0), "CM", iq=82, facing=180.0),
    ]
    left_opponents = [
        player(10, 18.0, 30.0, (18.0, 30.0), "CB"),
        player(11, 14.0, 42.0, (14.0, 42.0), "CB"),
        player(12, 2.0, 34.0, (2.0, 34.0), "GK"),
    ]
    cases.append(("left_attack", left_passer, left_teammates, left_opponents, False))

    lines = []
    expected = {}
    for case_id, passer_obj, teammates_obj, opponents_obj, attacking_right in cases:
        context = py_vision.build_vision_context(passer_obj, config, attacking_right)
        offside_line = passer_obj._get_offside_line(opponents_obj, attacking_right, config)
        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents_obj if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates_obj if t.index != passer_obj.index]
        lines.append("\t".join([
            str(passer_obj.index),
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(offside_line),
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            _pass_space_players_payload(teammates_obj),
            _positions_payload(opp_positions),
            _positions_payload(tm_positions),
            case_id,
        ]))
        expected[case_id] = _generic_pass_space_candidates_python(
            passer_obj,
            teammates_obj,
            opponents_obj,
            config,
            pitch,
            attacking_right,
        )

    rows = _run_rust_rows("pass_space_generic", lines)
    for case_id, py_candidates in expected.items():
        raw = rows[case_id][0]
        rust_candidates = [] if raw == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in raw.split(";")
        ]
        assert len(rust_candidates) == len(py_candidates)
        for rust_item, py_item in zip(rust_candidates, py_candidates):
            _assert_close_tuple([str(value) for value in rust_item], py_item, eps=1e-11)


def test_rust_receiver_base_pass_targets_match_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, position="CM", iq=92, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 72.0, 18.0, (72.0, 18.0), (72.0, 18.0), "RW", iq=96, facing=20.0)
    receiver = player(1, 78.0, 38.0, (82.0, 34.0), (80.0, 38.0), "CM")
    arc_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(80.0, 34.0),
        value=0.05,
        confidence=0.05,
    )
    far_goal = PlayerGoal(
        goal_type="attack_far_post",
        target_pos=(95.0, 42.0),
        value=0.06,
        confidence=0.06,
    )
    low_vis_passer = player(0, 52.0, 34.0, (52.0, 34.0), (52.0, 34.0), iq=70, facing=0.0)
    low_vis_receiver = player(2, 38.0, 62.0, (36.0, 64.0), (34.0, 62.0), "LW")

    cases = [
        ("no_goal", passer, receiver, None, True),
        ("arc_goal", passer, receiver, arc_goal, True),
        ("far_goal", passer, receiver, far_goal, True),
        ("low_visibility", low_vis_passer, low_vis_receiver, None, True),
    ]

    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, goal, attacking_right in cases:
        context = py_vision.build_vision_context(passer_obj, config, attacking_right)
        goal_type = "-" if goal is None else goal.goal_type
        goal_x = "-" if goal is None else str(goal.target_pos[0])
        goal_y = "-" if goal is None else str(goal.target_pos[1])
        goal_value = "0.0" if goal is None else str(goal.value)
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            _pass_space_players_payload([receiver_obj]),
            "-",
            "-",
            goal_type,
            goal_x,
            goal_y,
            goal_value,
            case_id,
        ]))
        expected[case_id] = _receiver_base_targets_python(
            passer_obj,
            receiver_obj,
            goal,
            config,
            pitch,
            attacking_right,
        )

    rows = _run_rust_rows("pass_receiver_base_targets", lines)
    for case_id, py_value in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_value["targets"])
        for rust_target, py_target in zip(rust_targets, py_value["targets"]):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-11)
        assert abs(float(rows[case_id][1]) - py_value["receiver_visibility"]) < 1e-12
        assert abs(float(rows[case_id][2]) - py_value["target_visibility"]) < 1e-12
        assert (rows[case_id][3] == "1") is py_value["low_visibility"]
        assert abs(float(rows[case_id][4]) - py_value["receiver_goal_fit"]) < 1e-12


def test_rust_value_field_targets_match_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, position="CM", iq=92, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 50.0, 34.0, (50.0, 34.0), (50.0, 34.0), "CM", iq=95, facing=0.0)
    receiver = player(1, 70.0, 24.0, (78.0, 28.0), (80.0, 24.0), "RW")
    defender_receiver = player(2, 42.0, 18.0, (46.0, 20.0), (44.0, 18.0), "RB")
    teammates = [passer, receiver, defender_receiver]
    opponents = [
        player(10, 86.0, 28.0, (86.0, 28.0), (86.0, 28.0), "CB"),
        player(11, 90.0, 42.0, (90.0, 42.0), (90.0, 42.0), "CB"),
    ]
    generic = _generic_pass_space_candidates_python(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        True,
    )

    cases = [
        ("attacker_no_goal", receiver, None, generic, True),
        ("attacker_goal", receiver, (84.0, 34.0), generic, True),
        ("defender_role", defender_receiver, None, generic, True),
    ]
    lines = []
    expected = {}
    for case_id, receiver_obj, goal_target, candidates, attacking_right in cases:
        goal_x = "-" if goal_target is None else str(goal_target[0])
        goal_y = "-" if goal_target is None else str(goal_target[1])
        lines.append("\t".join([
            _pass_space_players_payload([receiver_obj]),
            "-",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            "1" if receiver_obj.is_defender else "0",
            goal_x,
            goal_y,
            _generic_candidates_payload(candidates),
            case_id,
        ]))
        expected[case_id] = _value_field_targets_python(
            receiver_obj,
            goal_target,
            candidates,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_value_field_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-11)


def test_rust_stale_release_targets_match_python():
    config = EngineConfig()

    def player(idx, x, y, target, anchor, position="CM", carries=3):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.consecutive_carries = carries
        return p

    passer = player(0, 72.0, 20.0, (72.0, 20.0), (72.0, 20.0), "RW", carries=4)
    midfielder = player(1, 80.0, 34.0, (84.0, 32.0), (82.0, 34.0), "CM")
    striker = player(2, 84.0, 42.0, (86.0, 40.0), (86.0, 42.0), "ST")
    defender = player(3, 65.0, 18.0, (68.0, 20.0), (66.0, 18.0), "RB")
    cases = [
        ("midfielder", passer, midfielder, False, True),
        ("striker_weight", passer, striker, False, True),
        ("defender_skip", passer, defender, False, True),
        ("low_visibility_skip", passer, midfielder, True, True),
        ("left_attack", player(0, 33.0, 48.0, (33.0, 48.0), (33.0, 48.0), "LW", carries=5), player(1, 24.0, 34.0, (20.0, 36.0), (22.0, 34.0), "LM"), False, False),
    ]
    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, low_visibility, attacking_right in cases:
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            _pass_space_players_payload([receiver_obj]),
            "1" if low_visibility else "0",
            str(passer_obj.consecutive_carries),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            case_id,
        ]))
        expected[case_id] = _stale_release_targets_python(
            passer_obj,
            receiver_obj,
            low_visibility,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_stale_release_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-12)


def test_rust_layoff_targets_match_python():
    config = EngineConfig()

    def player(idx, x, y, target, anchor, position="CM"):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 90.0, 20.0, (90.0, 20.0), (90.0, 20.0), "RW")
    receiver = player(1, 82.0, 34.0, (84.0, 34.0), (80.0, 42.0), "CM")
    defender = player(2, 84.0, 18.0, (84.0, 18.0), (82.0, 18.0), "RB")
    left_passer = player(0, 15.0, 48.0, (15.0, 48.0), (15.0, 48.0), "LW")
    left_receiver = player(3, 24.0, 34.0, (22.0, 34.0), (24.0, 24.0), "LM")
    cases = [
        ("right", passer, receiver, False, True),
        ("defender_skip", passer, defender, False, True),
        ("low_visibility_skip", passer, receiver, True, True),
        ("left", left_passer, left_receiver, False, False),
    ]
    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, low_visibility, attacking_right in cases:
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            _pass_space_players_payload([receiver_obj]),
            "1" if low_visibility else "0",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            case_id,
        ]))
        expected[case_id] = _layoff_targets_python(
            passer_obj,
            receiver_obj,
            low_visibility,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_layoff_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-12)


def test_rust_second_line_targets_match_python():
    config = EngineConfig()

    def player(idx, x, y, target, anchor, base, position="CM"):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base
        return p

    passer = player(0, 74.0, 20.0, (74.0, 20.0), (74.0, 20.0), (74.0, 20.0), "RW")
    receiver = player(1, 76.0, 34.0, (82.0, 34.0), (80.0, 34.0), (58.0, 34.0), "CM")
    defender = player(2, 76.0, 20.0, (80.0, 22.0), (80.0, 20.0), (58.0, 20.0), "RB")
    deep_base = player(3, 76.0, 44.0, (82.0, 42.0), (80.0, 44.0), (30.0, 44.0), "CM")
    left_passer = player(0, 31.0, 48.0, (31.0, 48.0), (31.0, 48.0), (31.0, 48.0), "LW")
    left_receiver = player(4, 28.0, 34.0, (22.0, 34.0), (24.0, 34.0), (47.0, 34.0), "CM")
    cases = [
        ("right", passer, receiver, False, True),
        ("low_visibility_skip", passer, receiver, True, True),
        ("defender_skip", passer, defender, False, True),
        ("base_skip", passer, deep_base, False, True),
        ("left", left_passer, left_receiver, False, False),
    ]
    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, low_visibility, attacking_right in cases:
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            _pass_space_players_payload([receiver_obj]),
            str(receiver_obj.base_formation_pos[0]),
            str(receiver_obj.base_formation_pos[1]),
            "1" if low_visibility else "0",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            case_id,
        ]))
        expected[case_id] = _second_line_targets_python(
            passer_obj,
            receiver_obj,
            low_visibility,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_second_line_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-12)


def test_rust_box_delivery_targets_match_python():
    config = EngineConfig()

    def player(idx, x, y, target, anchor, position="CM"):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 82.0, 18.0, (82.0, 18.0), (82.0, 18.0), "RW")
    receiver = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), "ST")
    defender = player(2, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), "CB")
    narrow_passer = player(0, 82.0, 32.0, (82.0, 32.0), (82.0, 32.0), "CM")
    left_passer = player(0, 22.0, 50.0, (22.0, 50.0), (22.0, 50.0), "LW")
    left_receiver = player(3, 16.0, 34.0, (12.0, 36.0), (14.0, 34.0), "ST")
    cases = [
        ("right", passer, receiver, False, True),
        ("low_visibility_skip", passer, receiver, True, True),
        ("defender_skip", passer, defender, False, True),
        ("width_skip", narrow_passer, receiver, False, True),
        ("left", left_passer, left_receiver, False, False),
    ]
    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, low_visibility, attacking_right in cases:
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            _pass_space_players_payload([receiver_obj]),
            "1" if low_visibility else "0",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            case_id,
        ]))
        expected[case_id] = _box_delivery_targets_python(
            passer_obj,
            receiver_obj,
            low_visibility,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_box_delivery_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-12)


def test_rust_delivery_space_targets_match_python():
    config = EngineConfig()

    def player(idx, x, y, target, anchor, position="CM"):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), "RW")
    receiver = player(1, 84.0, 44.0, (90.0, 38.0), (92.0, 42.0), "ST")
    low_pressure_receiver = player(2, 58.0, 44.0, (58.2, 44.0), (59.0, 44.0), "CM")
    left_passer = player(0, 21.0, 50.0, (21.0, 50.0), (21.0, 50.0), "LW")
    left_receiver = player(3, 22.0, 24.0, (16.0, 30.0), (14.0, 26.0), "ST")
    cases = [
        ("right_extra", passer, receiver, False, True),
        ("low_visibility_skip", passer, receiver, True, True),
        ("pressure_skip", player(0, 45.0, 18.0, (45.0, 18.0), (45.0, 18.0), "RW"), low_pressure_receiver, False, True),
        ("left_extra", left_passer, left_receiver, False, False),
    ]
    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, low_visibility, attacking_right in cases:
        lines.append("\t".join([
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            _pass_space_players_payload([receiver_obj]),
            "1" if low_visibility else "0",
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            case_id,
        ]))
        expected[case_id] = _delivery_space_targets_python(
            passer_obj,
            receiver_obj,
            low_visibility,
            config,
            attacking_right,
        )

    rows = _run_rust_rows("pass_delivery_space_targets", lines)
    for case_id, py_targets in expected.items():
        rust_targets = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_targets) == len(py_targets)
        for rust_target, py_target in zip(rust_targets, py_targets):
            _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-12)


def test_rust_receiver_spatial_candidates_match_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, position="CM", iq=92, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        return p

    passer = player(0, 58.0, 30.0, (58.0, 30.0), (58.0, 30.0), "CM", iq=94, facing=0.0)
    receiver = player(1, 68.0, 22.0, (76.0, 26.0), (80.0, 20.0), "RW")
    teammates = [
        passer,
        receiver,
        player(2, 70.0, 44.0, (78.0, 40.0), (80.0, 46.0), "LW"),
        player(3, 62.0, 34.0, (66.0, 34.0), (64.0, 34.0), "CM"),
    ]
    opponents = [
        player(10, 86.0, 28.0, (86.0, 28.0), (86.0, 28.0), "CB"),
        player(11, 90.0, 42.0, (90.0, 42.0), (90.0, 42.0), "CB"),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), "GK"),
    ]
    front_center = (78.0, 33.0)

    low_vis_passer = player(0, 52.0, 34.0, (52.0, 34.0), (52.0, 34.0), "CM", iq=70, facing=0.0)
    low_vis_receiver = player(4, 34.0, 62.0, (30.0, 63.0), (28.0, 62.0), "LW")

    cases = [
        ("with_front", passer, receiver, front_center, False, teammates, opponents, True),
        ("without_front", passer, receiver, None, False, teammates, opponents, True),
        ("low_visibility", low_vis_passer, low_vis_receiver, front_center, True, [low_vis_passer, low_vis_receiver], opponents, True),
    ]

    lines = []
    expected = {}
    for case_id, passer_obj, receiver_obj, front, low_visibility, teammates_obj, opponents_obj, attacking_right in cases:
        context = py_vision.build_vision_context(passer_obj, config, attacking_right)
        offside_line = passer_obj._get_offside_line(opponents_obj, attacking_right, config)
        opp_positions = [(o.pos[0], o.pos[1]) for o in opponents_obj if not o.is_goalkeeper]
        tm_positions = [(t.pos[0], t.pos[1]) for t in teammates_obj if t.index != passer_obj.index]
        lines.append("\t".join([
            _pass_space_players_payload([receiver_obj]),
            str(passer_obj.pos[0]),
            str(passer_obj.pos[1]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(offside_line),
            "1" if low_visibility else "0",
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            "-" if front is None else str(front[0]),
            "-" if front is None else str(front[1]),
            "-",
            "-",
            _positions_payload(opp_positions),
            _positions_payload(tm_positions),
            case_id,
        ]))
        expected[case_id] = _receiver_spatial_candidates_python(
            passer_obj,
            receiver_obj,
            front,
            low_visibility,
            opponents_obj,
            teammates_obj,
            config,
            pitch,
            attacking_right,
        )

    rows = _run_rust_rows("pass_receiver_spatial_candidates", lines)
    for case_id, py_candidates in expected.items():
        rust_candidates = [] if rows[case_id][0] == "-" else [
            tuple(float(part) for part in item.split(","))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_candidates) == len(py_candidates)
        for rust_item, py_item in zip(rust_candidates, py_candidates):
            _assert_close_tuple([str(value) for value in rust_item], py_item, eps=1e-11)


def test_rust_raw_pass_prevalue_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, position="CM", speed=72, short=78, long=74, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
        })
        return p

    passer = player(0, 62.0, 28.0, "CM", speed=76, short=84, long=78, iq=94, facing=0.0)
    receiver = player(1, 76.0, 35.0, "ST", speed=82)
    teammate = player(2, 70.0, 40.0, "CM", speed=74)
    cb = player(10, 82.0, 34.0, "CB", speed=68)
    gk = player(11, 103.0, 34.0, "GK", speed=60)
    opponents = [cb, gk]
    teammates = [passer, receiver, teammate]
    attacking_right = True
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    receiver_visibility = context.confidence(passer.pos, receiver.pos)

    cases = [
        ("feet", receiver, receiver.pos, 1.0, receiver_visibility, None, 0.0, 0.0),
        ("space", receiver, (84.0, 34.0), 0.72, receiver_visibility, (86.0, 34.0), 0.06, 0.45),
        ("near_gk", receiver, (98.0, 34.0), 0.66, receiver_visibility, None, 0.0, 0.0),
        ("too_close_invalid", receiver, (63.0, 28.5), 0.90, receiver_visibility, None, 0.0, 0.0),
    ]

    lines = []
    expected = {}
    for case_id, receiver_obj, target, initial_arrival, recv_visibility, goal_target, goal_value, goal_fit in cases:
        goal_x = "-" if goal_target is None else str(goal_target[0])
        goal_y = "-" if goal_target is None else str(goal_target[1])
        lines.append("\t".join([
            str(passer.index),
            str(passer.pos[0]),
            str(passer.pos[1]),
            _pass_risk_players_payload([receiver_obj]),
            str(target[0]),
            str(target[1]),
            str(initial_arrival),
            str(recv_visibility),
            str(passer.abilities["Short_Passing"]),
            str(passer.abilities["Long_Passing"]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(offside_line),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.short_pass_base_success),
            str(config.long_pass_base_success),
            goal_x,
            goal_y,
            str(goal_value),
            str(goal_fit),
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            _pass_risk_players_payload(opponents),
            _pass_risk_players_payload(teammates),
            case_id,
        ]))
        expected[case_id] = _raw_pass_prevalue_python(
            passer,
            receiver_obj,
            target,
            initial_arrival,
            recv_visibility,
            goal_target,
            goal_value,
            goal_fit,
            opponents,
            teammates,
            config,
            pitch,
            attacking_right,
        )

    rows = _run_rust_rows("pass_raw_prevalue", lines)
    keys = [
        "receiver_arrival",
        "base_accuracy",
        "continuity",
        "perception",
        "perception_multiplier",
        "arrival_margin",
        "receiver_time",
        "defender_time",
        "defender_first_risk",
        "target_occupation_risk",
        "nearest_teammate_to_target",
        "nearest_opp_to_target",
        "box_space_pressure",
        "goal_target_fit",
    ]
    for case_id, py_value in expected.items():
        fields = rows[case_id]
        assert (fields[0] == "1") is py_value["valid"]
        for offset, key in enumerate(keys, start=1):
            rust_value = float(fields[offset])
            if rust_value == float("inf"):
                assert py_value[key] == float("inf")
            else:
                assert abs(rust_value - py_value[key]) < 1e-11
        assert (fields[15] == "1") is py_value["is_long"]
        assert (fields[16] == "1") is py_value["target_kind_space"]
        assert abs(float(fields[17]) - py_value["distance"]) < 1e-12


def test_rust_raw_pass_value_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        p.tactical_anchor = (x, y)
        p.base_formation_pos = (x, y)
        return p

    passer = player(0, 72.0, 20.0, "RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=10.0)
    passer.consecutive_carries = 3
    receiver = player(1, 80.0, 34.0, "CM", speed=82, finish=78, long_shot=72)
    receiver.tactical_anchor = (78.0, 34.0)
    receiver.base_formation_pos = (62.0, 34.0)
    teammate = player(2, 82.0, 44.0, "ST", speed=80, finish=82, long_shot=70)
    cb = player(10, 86.0, 32.0, "CB", speed=70)
    gk = player(11, 103.0, 34.0, "GK", speed=60)
    opponents = [cb, gk]
    teammates = [passer, receiver, teammate]
    attacking_right = True
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    receiver_visibility = context.confidence(passer.pos, receiver.pos)
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions = [(t.index, t.pos[0], t.pos[1]) for t in teammates if t.index != receiver.index]
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    receiver.current_goal = goal

    cases = [
        ("feet", receiver.pos, 1.0, None, 0.0, 0.0, "-"),
        ("space_goal", (82.0, 34.0), 0.74, goal.target_pos, goal.value, 0.48, goal.goal_type),
        ("space_wide", (84.0, 42.0), 0.62, None, 0.0, 0.0, "-"),
    ]

    lines = []
    expected = {}
    for case_id, target, initial_arrival, goal_target, goal_value, goal_fit, goal_type in cases:
        goal_x = "-" if goal_target is None else str(goal_target[0])
        goal_y = "-" if goal_target is None else str(goal_target[1])
        receiver_goal_type = goal_type
        receiver_goal_target = goal_target
        receiver_goal_value = goal_value
        if goal_type == "-":
            receiver.current_goal = None
        else:
            receiver.current_goal = goal
        pre = _raw_pass_prevalue_python(
            passer,
            receiver,
            target,
            initial_arrival,
            receiver_visibility,
            goal_target,
            goal_value,
            goal_fit,
            opponents,
            teammates,
            config,
            pitch,
            attacking_right,
        )
        if pre["valid"]:
            value = expected_pass_value_result(
                passer,
                receiver,
                passer.pos,
                target,
                teammates,
                opponents,
                config,
                pitch,
                attacking_right,
                current_value,
                pre["base_accuracy"],
                receiver_arrival=pre["receiver_arrival"],
                continuity=pre["continuity"],
            )
            adjusted_score = value.score
            if pre["defender_first_risk"] > 0.0:
                adjusted_score *= 1.0 - 0.58 * pre["defender_first_risk"]
            if pre["target_occupation_risk"] > 0.0:
                adjusted_score *= 1.0 - 0.68 * pre["target_occupation_risk"]
            expected[case_id] = {
                "valid": adjusted_score > 0.0,
                "adjusted_score": adjusted_score,
                "score": value.score,
                "success_prob": value.success_prob,
                "risk_cost": value.risk_cost,
                "after_value": value.after_value,
                "effective_delta": value.components["effective_delta"],
                "continuity": value.components["continuity"],
                "lane_risk": value.components["lane_risk"],
                "receiver_pressure": value.components["receiver_pressure"],
                "turnover_consequence": value.components["turnover_consequence"],
                "receiver_arrival": pre["receiver_arrival"],
                "base_accuracy": pre["base_accuracy"],
                "defender_first_risk": pre["defender_first_risk"],
                "target_occupation_risk": pre["target_occupation_risk"],
                "goal_target_fit": pre["goal_target_fit"],
                "is_long": pre["is_long"],
                "target_kind_space": pre["target_kind_space"],
                "distance": pre["distance"],
            }
        else:
            expected[case_id] = {
                "valid": False,
                "adjusted_score": 0.0,
                "score": 0.0,
                "success_prob": 0.0,
                "risk_cost": 0.0,
                "after_value": 0.0,
                "effective_delta": 0.0,
                "continuity": 0.0,
                "lane_risk": 0.0,
                "receiver_pressure": 0.0,
                "turnover_consequence": 0.0,
                "receiver_arrival": pre["receiver_arrival"],
                "base_accuracy": pre["base_accuracy"],
                "defender_first_risk": pre["defender_first_risk"],
                "target_occupation_risk": pre["target_occupation_risk"],
                "goal_target_fit": pre["goal_target_fit"],
                "is_long": pre["is_long"],
                "target_kind_space": pre["target_kind_space"],
                "distance": pre["distance"],
            }
        lines.append("\t".join([
            str(passer.index),
            str(passer.pos[0]),
            str(passer.pos[1]),
            _pass_risk_players_payload([receiver]),
            str(target[0]),
            str(target[1]),
            str(initial_arrival),
            str(receiver_visibility),
            str(passer.abilities["Short_Passing"]),
            str(passer.abilities["Long_Passing"]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(offside_line),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.short_pass_base_success),
            str(config.long_pass_base_success),
            goal_x,
            goal_y,
            str(goal_value),
            str(goal_fit),
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            _pass_risk_players_payload(opponents),
            _pass_risk_players_payload(teammates),
            str(current_value),
            str(passer.abilities["Finishing"] / 100.0),
            str(passer.abilities["Long_Shot"] / 100.0),
            str(passer.consecutive_carries),
            str(receiver.index),
            str(receiver.abilities["Finishing"] / 100.0),
            str(receiver.abilities["Long_Shot"] / 100.0),
            str(receiver.tactical_anchor[0]),
            str(receiver.tactical_anchor[1]),
            str(receiver.base_formation_pos[0]),
            str(receiver.base_formation_pos[1]),
            receiver_goal_type,
            "-" if receiver_goal_target is None else str(receiver_goal_target[0]),
            "-" if receiver_goal_target is None else str(receiver_goal_target[1]),
            _indexed_positions_payload(teammate_positions),
            _positions_payload(opponent_positions),
            str(config.interception_reach),
            str(config.shot_ideal_distance),
            str(config.shot_on_target_base),
            str(config.gk_save_base),
            case_id,
        ]))

    rows = _run_rust_rows("pass_raw_value", lines)
    float_keys = [
        "adjusted_score",
        "score",
        "success_prob",
        "risk_cost",
        "after_value",
        "effective_delta",
        "continuity",
        "lane_risk",
        "receiver_pressure",
        "turnover_consequence",
        "receiver_arrival",
        "base_accuracy",
        "defender_first_risk",
        "target_occupation_risk",
        "goal_target_fit",
    ]
    for case_id, py_value in expected.items():
        fields = rows[case_id]
        assert (fields[0] == "1") is py_value["valid"]
        for offset, key in enumerate(float_keys, start=1):
            assert abs(float(fields[offset]) - py_value[key]) < 1e-11
        assert (fields[16] == "1") is py_value["is_long"]
        assert (fields[17] == "1") is py_value["target_kind_space"]
        assert abs(float(fields[18]) - py_value["distance"]) < 1e-12


def _receiver_pass_batch_python(
    passer,
    receiver,
    receiver_goal,
    generic_candidates,
    front_center,
    opponents,
    teammates,
    config,
    pitch,
    attacking_right,
    current_value,
):
    base = _receiver_base_targets_python(
        passer,
        receiver,
        receiver_goal,
        config,
        pitch,
        attacking_right,
    )
    goal_target = None if receiver_goal is None else receiver_goal.target_pos
    goal_value = 0.0 if receiver_goal is None else receiver_goal.value
    raw_targets = [((x, y), arrival) for x, y, arrival in base["targets"]]
    for x, y, arrival in _stale_release_targets_python(
        passer,
        receiver,
        base["low_visibility"],
        config,
        attacking_right,
    ):
        raw_targets.append(((x, y), arrival))
    for x, y, arrival in _layoff_targets_python(
        passer,
        receiver,
        base["low_visibility"],
        config,
        attacking_right,
    ):
        raw_targets.append(((x, y), arrival))
    for x, y, arrival in _second_line_targets_python(
        passer,
        receiver,
        base["low_visibility"],
        config,
        attacking_right,
    ):
        raw_targets.append(((x, y), arrival))
    for x, y, arrival in _box_delivery_targets_python(
        passer,
        receiver,
        base["low_visibility"],
        config,
        attacking_right,
    ):
        raw_targets.append(((x, y), arrival))
    for x, y, arrival in _delivery_space_targets_python(
        passer,
        receiver,
        base["low_visibility"],
        config,
        attacking_right,
    ):
        raw_targets.append(((x, y), arrival))
    for item in _value_field_targets_python(
        receiver,
        goal_target,
        generic_candidates,
        config,
        attacking_right,
    ):
        raw_targets.append(((item[0], item[1]), item[2]))
    for item in _receiver_spatial_candidates_python(
        passer,
        receiver,
        front_center,
        base["low_visibility"],
        opponents,
        teammates,
        config,
        pitch,
        attacking_right,
    ):
        raw_targets.append(((item[1], item[2]), item[3]))

    candidates = []
    for target, arrival in raw_targets:
        pre = _raw_pass_prevalue_python(
            passer,
            receiver,
            target,
            arrival,
            base["receiver_visibility"],
            goal_target,
            goal_value,
            base["receiver_goal_fit"],
            opponents,
            teammates,
            config,
            pitch,
            attacking_right,
        )
        if not pre["valid"]:
            continue
        value = expected_pass_value_result(
            passer,
            receiver,
            passer.pos,
            target,
            teammates,
            opponents,
            config,
            pitch,
            attacking_right,
            current_value,
            pre["base_accuracy"],
            receiver_arrival=pre["receiver_arrival"],
            continuity=pre["continuity"],
        )
        adjusted_score = value.score
        if pre["defender_first_risk"] > 0.0:
            adjusted_score *= 1.0 - 0.58 * pre["defender_first_risk"]
        if pre["target_occupation_risk"] > 0.0:
            adjusted_score *= 1.0 - 0.68 * pre["target_occupation_risk"]
        if adjusted_score <= 0.0:
            continue
        candidates.append((
            target[0],
            target[1],
            adjusted_score,
            value.score,
            value.success_prob,
            pre["receiver_arrival"],
            pre["base_accuracy"],
            pre["goal_target_fit"],
            pre["distance"],
            pre["is_long"],
            pre["target_kind_space"],
        ))
    return candidates


def _team_pass_batch_python(
    passer,
    teammates,
    opponents,
    config,
    pitch,
    attacking_right,
    current_value,
):
    generic = _generic_pass_space_candidates_python(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
    )
    front_anchors = []
    for tm in teammates:
        if tm.index == passer.index or tm.is_goalkeeper:
            continue
        anchor_progress = (
            tm.tactical_anchor[0] / config.pitch_length
            if attacking_right
            else (config.pitch_length - tm.tactical_anchor[0]) / config.pitch_length
        )
        if anchor_progress > 0.58:
            front_anchors.append(tm.tactical_anchor)
    front_center = None
    if front_anchors:
        front_center = (
            sum(p[0] for p in front_anchors) / len(front_anchors),
            sum(p[1] for p in front_anchors) / len(front_anchors),
        )
    results = []
    for tm in teammates:
        if tm.index == passer.index or tm.is_goalkeeper:
            continue
        for candidate in _receiver_pass_batch_python(
            passer,
            tm,
            getattr(tm, "current_goal", None),
            generic,
            front_center,
            opponents,
            teammates,
            config,
            pitch,
            attacking_right,
            current_value,
        ):
            results.append((tm.index, *candidate))
    return results


def _real_python_pass_details(passer, teammates, opponents, config, pitch, attacking_right):
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )
    details = []
    for score, action_type, candidate_details in candidates:
        assert action_type == "pass"
        components = candidate_details["components"]
        target = candidate_details["target"]
        details.append({
            "receiver_idx": candidate_details.get("target_player_idx", candidate_details.get("intended_receiver")),
            "target": target,
            "score": score,
            "success_prob": candidate_details["success_prob"],
            "risk_cost": candidate_details["risk_cost"],
            "after_value": candidate_details["after_value"],
            "effective_delta": components["effective_delta"],
            "continuity": components["continuity"],
            "lane_risk": components["lane_risk"],
            "receiver_pressure": components["receiver_pressure"],
            "turnover_consequence": components["turnover_consequence"],
            "receiver_arrival": components["receiver_arrival"],
            "base_accuracy": components["base_accuracy"],
            "receiver_goal_fit": components["receiver_goal_fit"],
            "distance": components["distance"],
            "is_long": bool(candidate_details["is_long"]),
            "target_kind_space": components["target_kind"] == "space",
        })
    return current_value, details


def _rust_team_pass_details(case_id, passer, teammates, opponents, config, attacking_right, current_value):
    return score_pass_point_options_rust(
        passer,
        teammates,
        opponents,
        config,
        Pitch(config=config),
        attacking_right,
        current_value=current_value,
    )


def _assert_pass_detail_lists_match(rust_details, py_details, eps=1e-10):
    assert len(rust_details) == len(py_details)
    float_keys = [
        "score",
        "success_prob",
        "risk_cost",
        "after_value",
        "effective_delta",
        "continuity",
        "lane_risk",
        "receiver_pressure",
        "turnover_consequence",
        "receiver_arrival",
        "base_accuracy",
        "receiver_goal_fit",
        "distance",
    ]
    for rust_item, py_item in zip(rust_details, py_details):
        assert rust_item["receiver_idx"] == py_item["receiver_idx"]
        _assert_close_tuple([str(rust_item["target"][0]), str(rust_item["target"][1])], py_item["target"], eps=eps)
        for key in float_keys:
            assert abs(rust_item[key] - py_item[key]) < eps
        assert rust_item["is_long"] is py_item["is_long"]
        assert rust_item["target_kind_space"] is py_item["target_kind_space"]


def test_rust_team_pass_batch_preserves_real_tick0_space_candidate_from_clean_baseline():
    config = EngineConfig()
    config.player_max_speed = 8.0
    config.shot_on_target_base = 0.52
    config.gk_save_base = 0.66

    def player(
        idx,
        position,
        pos,
        target,
        anchor,
        base,
        speed,
        finishing=50,
        long_shot=50,
        short_passing=50,
        long_passing=50,
        iq=80,
        goal=None,
    ):
        p = _vision_player(idx, pos[0], pos[1], iq=iq, facing=0.0)
        p.position = position
        p.pos = pos
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base
        p.abilities.update({
            "Speed": speed,
            "Finishing": finishing,
            "Long_Shot": long_shot,
            "Short_Passing": short_passing,
            "Long_Passing": long_passing,
            "IQ": iq,
        })
        if goal is not None:
            p.current_goal = PlayerGoal(
                goal_type=goal[0],
                target_pos=goal[1],
                value=goal[2],
                confidence=goal[2],
            )
        return p

    passer = player(
        9,
        "ST",
        (52.5, 34.0),
        (52.5, 34.0),
        (90.30000000000001, 34.0),
        (84.0, 34.0),
        speed=106,
        finishing=109,
        long_shot=96,
        short_passing=95,
        long_passing=82,
        iq=96,
    )
    passer.possession_ticks = 1
    teammates = [
        player(0, "GK", (0.5, 34.0), (2.8625, 34.0), (5.75, 34.0), (0.5, 34.0), 77, 39, 50),
        player(1, "LCB", (10.08, 22.0), (25.06831764705883, 21.772), (29.8014705882353, 21.700000000000003), (21.0, 22.0), 84, 53, 51, goal=("recycle_support", (25.06831764705883, 21.772), 0.1420285278055856)),
        player(2, "CB", (10.08, 34.0), (26.566549834480277, 33.177206453654776), (28.245, 34.0), (21.0, 34.0), 83, 53, 59, goal=("recycle_support", (26.566549834480277, 33.177206453654776), 0.13564723858302727)),
        player(3, "RCB", (10.08, 44.0), (24.871164705882354, 44.19), (29.542058823529413, 44.25), (21.0, 44.0), 82, 74, 79, goal=("recycle_support", (24.871164705882354, 44.19), 0.10482097216360726)),
        player(4, "LM", (24.192, 14.0), (46.66643717647058, 13.524000000000001), (53.37146749226005, 13.373684210526317), (50.4, 14.0), 97, 94, 91, goal=("recycle_support", (46.66643717647058, 13.524000000000001), 0.1392816791118147)),
        player(5, "LCM", (24.192, 28.0), (56.55751402571226, 26.293144161287593), (53.25040866873064, 27.812105263157896), (50.4, 28.0), 81, 80, 91, goal=("recycle_support", (56.55751402571226, 26.293144161287593), 0.15002229731995198)),
        player(6, "RCM", (24.192, 42.0), (46.55208847058823, 42.1904), (53.267702786377704, 42.25052631578947), (50.4, 42.0), 78, 94, 88, goal=("recycle_support", (46.55208847058823, 42.1904), 0.16087146788480214)),
        player(7, "RM", (24.192, 56.0), (46.68549529411764, 56.5236), (53.388761609907114, 56.688947368421054), (50.4, 56.0), 105, 95, 81, goal=("recycle_support", (46.68549529411764, 56.5236), 0.13390034342090681)),
        player(8, "LW", (40.32, 14.0), (64.79536397400497, 21.99306438148825), (90.30000000000001, 12.700000000000003), (84.0, 14.0), 101, 99, 89, goal=("recycle_support", (64.79536397400497, 21.99306438148825), 0.13882662296202564)),
        passer,
        player(10, "RW", (40.32, 56.0), (59.897084917441276, 43.30995233583826), (90.30000000000001, 57.43), (84.0, 56.0), 92, 99, 93, goal=("recycle_support", (59.897084917441276, 43.30995233583826), 0.09233770859357435)),
    ]
    opponents = [
        player(0, "GK", (104.5, 34.0), (104.5, 34.0), (97.29, 34.0), (104.5, 34.0), 60),
        player(1, "LB", (90.888, 14.0), (90.888, 14.0), (76.482, 15.599999999999998), (75.6, 14.0), 98),
        player(2, "LCB", (94.92, 28.0), (94.92, 28.0), (82.53, 28.48), (84.0, 28.0), 88),
        player(3, "RCB", (94.92, 42.0), (94.92, 42.0), (82.53, 41.36), (84.0, 42.0), 72),
        player(4, "RB", (90.888, 56.0), (90.888, 56.0), (76.482, 54.24), (75.6, 56.0), 90),
        player(5, "LCM", (80.80799999999999, 22.0), (80.80799999999999, 22.0), (61.362, 22.96), (54.6, 22.0), 83),
        player(6, "CM", (80.80799999999999, 34.0), (80.80799999999999, 34.0), (61.362, 34.0), (54.6, 34.0), 85),
        player(7, "RCM", (80.80799999999999, 44.0), (80.80799999999999, 44.0), (61.362, 43.2), (54.6, 44.0), 85),
        player(8, "LW", (64.68, 14.0), (64.68, 14.0), (37.169999999999995, 15.599999999999998), (20.999999999999996, 14.0), 101),
        player(9, "ST", (64.68, 34.0), (64.68, 34.0), (37.169999999999995, 34.0), (20.999999999999996, 34.0), 96),
        player(10, "RW", (64.68, 56.0), (64.68, 56.0), (37.169999999999995, 54.24), (20.999999999999996, 56.0), 86),
    ]

    rust_details = score_pass_point_options_rust(
        passer,
        teammates,
        opponents,
        config,
        Pitch(config=config),
        True,
        current_value=0.25348218539212514,
    )
    expected = [{
        "receiver_idx": 8,
        "target": (52.55768198700248, 17.996532190744126),
        "score": 0.006029532285089234,
        "success_prob": 0.497798540686114,
        "risk_cost": 0.06849412918383976,
        "after_value": 0.2795453495140451,
        "effective_delta": 0.026063164121919946,
        "continuity": 0.12364330421407256,
        "lane_risk": 0.0,
        "receiver_pressure": 0.0,
        "turnover_consequence": 0.27661564243409176,
        "receiver_arrival": 0.7085986093887051,
        "base_accuracy": 0.702511314713919,
        "receiver_goal_fit": 0.0,
        "distance": 16.003571761750987,
        "is_long": False,
        "target_kind_space": True,
    }]
    _assert_pass_detail_lists_match(rust_details, expected)


def test_rust_receiver_pass_batch_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 68.0, 20.0, (68.0, 20.0), (68.0, 20.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=10.0)
    passer.consecutive_carries = 3
    receiver = player(1, 78.0, 34.0, (83.0, 34.0), (80.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    teammate = player(2, 82.0, 44.0, (86.0, 42.0), (84.0, 44.0), position="ST", speed=80, finish=82, long_shot=70)
    cb = player(10, 86.0, 32.0, (86.0, 32.0), (86.0, 32.0), position="CB", speed=70)
    gk = player(11, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60)
    opponents = [cb, gk]
    teammates = [passer, receiver, teammate]
    attacking_right = True
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    generic = _generic_pass_space_candidates_python(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
    )
    goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    front_center = (82.0, 36.0)

    cases = [
        ("no_goal", None),
        ("with_goal", goal),
    ]
    lines = []
    expected = {}
    for case_id, receiver_goal in cases:
        receiver.current_goal = receiver_goal
        expected[case_id] = _receiver_pass_batch_python(
            passer,
            receiver,
            receiver_goal,
            generic,
            front_center,
            opponents,
            teammates,
            config,
            pitch,
            attacking_right,
            current_value,
        )
        goal_type = "-" if receiver_goal is None else receiver_goal.goal_type
        goal_x = "-" if receiver_goal is None else str(receiver_goal.target_pos[0])
        goal_y = "-" if receiver_goal is None else str(receiver_goal.target_pos[1])
        goal_value = "0.0" if receiver_goal is None else str(receiver_goal.value)
        opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
        teammate_positions = [(t.index, t.pos[0], t.pos[1]) for t in teammates if t.index != receiver.index]
        teammate_xy_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
        lines.append("\t".join([
            str(passer.index),
            str(passer.pos[0]),
            str(passer.pos[1]),
            _pass_space_players_payload([receiver]),
            _pass_risk_players_payload([receiver]),
            str(passer.abilities["Finishing"] / 100.0),
            str(passer.abilities["Long_Shot"] / 100.0),
            str(passer.abilities["Short_Passing"]),
            str(passer.abilities["Long_Passing"]),
            str(passer.consecutive_carries),
            str(receiver.index),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(offside_line),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.short_pass_base_success),
            str(config.long_pass_base_success),
            str(context.facing),
            str(context.fov),
            str(context.half_fov),
            str(context.max_distance),
            str(current_value),
            str(receiver.abilities["Finishing"] / 100.0),
            str(receiver.abilities["Long_Shot"] / 100.0),
            str(receiver.tactical_anchor[0]),
            str(receiver.tactical_anchor[1]),
            str(receiver.base_formation_pos[0]),
            str(receiver.base_formation_pos[1]),
            "1" if receiver.is_defender else "0",
            goal_type,
            goal_x,
            goal_y,
            goal_value,
            str(front_center[0]),
            str(front_center[1]),
            _generic_candidates_payload(generic),
            _indexed_positions_payload(teammate_positions),
            _positions_payload(opponent_positions),
            _positions_payload(teammate_xy_positions),
            _pass_risk_players_payload(opponents),
            _pass_risk_players_payload(teammates),
            str(config.interception_reach),
            str(config.shot_ideal_distance),
            str(config.shot_on_target_base),
            str(config.gk_save_base),
            case_id,
        ]))

    rows = _run_rust_rows("pass_receiver_batch", lines)
    for case_id, py_candidates in expected.items():
        rust_candidates = [] if rows[case_id][0] == "-" else [
            tuple(float(part) if idx < 9 else (part == "1") for idx, part in enumerate(item.split(",")))
            for item in rows[case_id][0].split(";")
        ]
        assert len(rust_candidates) == len(py_candidates)
        for rust_item, py_item in zip(rust_candidates, py_candidates):
            _assert_close_tuple([str(value) for value in rust_item[:9]], py_item[:9], eps=1e-11)
            assert rust_item[9] is py_item[9]
            assert rust_item[10] is py_item[10]


def test_rust_team_pass_batch_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 66.0, 22.0, (66.0, 22.0), (66.0, 22.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    passer.consecutive_carries = 3
    receiver_a = player(1, 78.0, 34.0, (83.0, 34.0), (80.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver_b = player(2, 82.0, 46.0, (86.0, 42.0), (84.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70)
    keeper = player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58)
    goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    receiver_a.current_goal = goal
    teammates = [passer, receiver_a, receiver_b, keeper]
    opponents = [
        player(10, 86.0, 32.0, (86.0, 32.0), (86.0, 32.0), position="CB", speed=70),
        player(11, 92.0, 44.0, (92.0, 44.0), (92.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = True
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    expected = _team_pass_batch_python(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        current_value,
    )
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions = [(t.index, t.pos[0], t.pos[1]) for t in teammates]
    teammate_xy_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    line = "\t".join([
        str(passer.index),
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(passer.abilities["Finishing"] / 100.0),
        str(passer.abilities["Long_Shot"] / 100.0),
        str(passer.abilities["Short_Passing"]),
        str(passer.abilities["Long_Passing"]),
        str(passer.consecutive_carries),
        "-",
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(offside_line),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.short_pass_base_success),
        str(config.long_pass_base_success),
        str(current_value),
        str(context.facing),
        str(context.fov),
        str(context.half_fov),
        str(context.max_distance),
        "-",
        "-",
        _pass_team_players_payload(teammates),
        _indexed_positions_payload(teammate_positions),
        _positions_payload(opponent_positions),
        _positions_payload(teammate_xy_positions),
        _pass_risk_players_payload(opponents),
        _pass_risk_players_payload(teammates),
        str(config.interception_reach),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        "-",
        "team_batch",
    ])
    rows = _run_rust_rows("pass_team_batch", [line])
    rust_candidates = [] if rows["team_batch"][0] == "-" else [
        tuple(float(part) if idx not in (0, 10, 11) else int(part) if idx == 0 else (part == "1") for idx, part in enumerate(item.split(",")))
        for item in rows["team_batch"][0].split(";")
    ]
    assert len(rust_candidates) == len(expected)
    for rust_item, py_item in zip(rust_candidates, expected):
        assert rust_item[0] == py_item[0]
        _assert_close_tuple([str(value) for value in rust_item[1:10]], py_item[1:10], eps=1e-11)
        assert rust_item[10] is py_item[10]
        assert rust_item[11] is py_item[11]


def test_rust_team_pass_batch_matches_real_python_method_core_fields():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    passer.consecutive_carries = 3
    receiver_a = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver_b = player(2, 86.0, 46.0, (90.0, 42.0), (91.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70)
    keeper = player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58)
    receiver_a.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    teammates = [passer, receiver_a, receiver_b, keeper]
    opponents = [
        player(10, 90.0, 32.0, (90.0, 32.0), (90.0, 32.0), position="CB", speed=70),
        player(11, 94.0, 44.0, (94.0, 44.0), (94.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = True
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]

    py_candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )
    py_core = []
    for score, action_type, details in py_candidates:
        assert action_type == "pass"
        components = details.get("components", {})
        receiver_idx = details.get("target_player_idx", details.get("intended_receiver"))
        target = details["target"]
        py_core.append((
            receiver_idx,
            target[0],
            target[1],
            score,
            details["success_prob"],
            bool(details["is_long"]),
            components.get("target_kind") == "space",
            components.get("distance"),
        ))

    opponent_positions_indexed = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions_indexed = [(t.index, t.pos[0], t.pos[1]) for t in teammates]
    teammate_xy_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    line = "\t".join([
        str(passer.index),
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(passer.abilities["Finishing"] / 100.0),
        str(passer.abilities["Long_Shot"] / 100.0),
        str(passer.abilities["Short_Passing"]),
        str(passer.abilities["Long_Passing"]),
        str(passer.consecutive_carries),
        "-",
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(offside_line),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.short_pass_base_success),
        str(config.long_pass_base_success),
        str(current_value),
        str(context.facing),
        str(context.fov),
        str(context.half_fov),
        str(context.max_distance),
        "-",
        "-",
        _pass_team_players_payload(teammates),
        _indexed_positions_payload(teammate_positions_indexed),
        _positions_payload(opponent_positions_indexed),
        _positions_payload(teammate_xy_positions),
        _pass_risk_players_payload(opponents),
        _pass_risk_players_payload(teammates),
        str(config.interception_reach),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        "-",
        "real_method",
    ])
    rows = _run_rust_rows("pass_team_batch", [line])
    rust_core = [] if rows["real_method"][0] == "-" else [
        (
            int(parts[0]),
            float(parts[1]),
            float(parts[2]),
            float(parts[3]),
            float(parts[5]),
            parts[10] == "1",
            parts[11] == "1",
            float(parts[9]),
        )
        for parts in (item.split(",") for item in rows["real_method"][0].split(";"))
    ]

    assert len(rust_core) == len(py_core)
    for rust_item, py_item in zip(rust_core, py_core):
        assert rust_item[0] == py_item[0]
        _assert_close_tuple([str(value) for value in rust_item[1:5]], py_item[1:5], eps=1e-10)
        assert rust_item[5] is py_item[5]
        assert rust_item[6] is py_item[6]
        assert abs(rust_item[7] - py_item[7]) < 1e-10


def test_rust_team_pass_batch_matches_real_python_method_left_core_fields():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=180.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 21.0, 50.0, (21.0, 50.0), (21.0, 50.0), position="LW", speed=79, short=83, long=81, finish=75, long_shot=73, iq=95)
    passer.consecutive_carries = 4
    receiver_a = player(1, 16.0, 34.0, (12.0, 32.0), (14.0, 34.0), base=(43.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver_b = player(2, 18.0, 22.0, (13.0, 25.0), (12.0, 22.0), base=(29.0, 22.0), position="ST", speed=80, finish=82, long_shot=70)
    keeper = player(3, 97.0, 34.0, (97.0, 34.0), (97.0, 34.0), position="GK", speed=58)
    teammates = [passer, receiver_a, receiver_b, keeper]
    opponents = [
        player(10, 15.0, 30.0, (15.0, 30.0), (15.0, 30.0), position="CB", speed=70),
        player(11, 12.0, 42.0, (12.0, 42.0), (12.0, 42.0), position="CB", speed=68),
        player(12, 2.0, 34.0, (2.0, 34.0), (2.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = False
    context = py_vision.build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]

    py_candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )
    py_core = []
    for score, action_type, details in py_candidates:
        assert action_type == "pass"
        components = details.get("components", {})
        receiver_idx = details.get("target_player_idx", details.get("intended_receiver"))
        target = details["target"]
        py_core.append((
            receiver_idx,
            target[0],
            target[1],
            score,
            details["success_prob"],
            bool(details["is_long"]),
            components.get("target_kind") == "space",
            components.get("distance"),
        ))

    teammate_positions_indexed = [(t.index, t.pos[0], t.pos[1]) for t in teammates]
    teammate_xy_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    line = "\t".join([
        str(passer.index),
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(passer.abilities["Finishing"] / 100.0),
        str(passer.abilities["Long_Shot"] / 100.0),
        str(passer.abilities["Short_Passing"]),
        str(passer.abilities["Long_Passing"]),
        str(passer.consecutive_carries),
        "-",
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(offside_line),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.short_pass_base_success),
        str(config.long_pass_base_success),
        str(current_value),
        str(context.facing),
        str(context.fov),
        str(context.half_fov),
        str(context.max_distance),
        "-",
        "-",
        _pass_team_players_payload(teammates),
        _indexed_positions_payload(teammate_positions_indexed),
        _positions_payload(opp_positions),
        _positions_payload(teammate_xy_positions),
        _pass_risk_players_payload(opponents),
        _pass_risk_players_payload(teammates),
        str(config.interception_reach),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        "-",
        "real_left",
    ])
    rows = _run_rust_rows("pass_team_batch", [line])
    rust_core = [] if rows["real_left"][0] == "-" else [
        (
            int(parts[0]),
            float(parts[1]),
            float(parts[2]),
            float(parts[3]),
            float(parts[5]),
            parts[10] == "1",
            parts[11] == "1",
            float(parts[9]),
        )
        for parts in (item.split(",") for item in rows["real_left"][0].split(";"))
    ]

    assert len(rust_core) == len(py_core)
    for rust_item, py_item in zip(rust_core, py_core):
        assert rust_item[0] == py_item[0]
        _assert_close_tuple([str(value) for value in rust_item[1:5]], py_item[1:5], eps=1e-10)
        assert rust_item[5] is py_item[5]
        assert rust_item[6] is py_item[6]
        assert abs(rust_item[7] - py_item[7]) < 1e-10


def test_rust_team_pass_batch_details_match_real_python_method_fields():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    passer.consecutive_carries = 3
    receiver_a = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver_b = player(2, 86.0, 46.0, (90.0, 42.0), (91.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70)
    keeper = player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58)
    receiver_a.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    teammates = [passer, receiver_a, receiver_b, keeper]
    opponents = [
        player(10, 90.0, 32.0, (90.0, 32.0), (90.0, 32.0), position="CB", speed=70),
        player(11, 94.0, 44.0, (94.0, 44.0), (94.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = True
    current_value, py_details = _real_python_pass_details(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
    )
    rust_details = _rust_team_pass_details(
        "details_method",
        passer,
        teammates,
        opponents,
        config,
        attacking_right,
        current_value,
    )
    _assert_pass_detail_lists_match(rust_details, py_details)


def test_rust_team_pass_batch_details_match_real_python_multiple_scenarios():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    right_passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    right_passer.consecutive_carries = 3
    right_receiver = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    right_receiver.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    right_teammates = [
        right_passer,
        right_receiver,
        player(2, 86.0, 46.0, (90.0, 42.0), (91.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70),
        player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58),
    ]
    right_opponents = [
        player(10, 90.0, 32.0, (90.0, 32.0), (90.0, 32.0), position="CB", speed=70),
        player(11, 94.0, 44.0, (94.0, 44.0), (94.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]

    left_passer = player(0, 21.0, 50.0, (21.0, 50.0), (21.0, 50.0), position="LW", speed=79, short=83, long=81, finish=75, long_shot=73, iq=95, facing=180.0)
    left_passer.consecutive_carries = 4
    left_teammates = [
        left_passer,
        player(1, 16.0, 34.0, (12.0, 32.0), (14.0, 34.0), base=(43.0, 34.0), position="CM", speed=82, finish=78, long_shot=72, facing=180.0),
        player(2, 18.0, 22.0, (13.0, 25.0), (12.0, 22.0), base=(29.0, 22.0), position="ST", speed=80, finish=82, long_shot=70, facing=180.0),
        player(3, 97.0, 34.0, (97.0, 34.0), (97.0, 34.0), position="GK", speed=58, facing=180.0),
    ]
    left_opponents = [
        player(10, 15.0, 30.0, (15.0, 30.0), (15.0, 30.0), position="CB", speed=70, facing=180.0),
        player(11, 12.0, 42.0, (12.0, 42.0), (12.0, 42.0), position="CB", speed=68, facing=180.0),
        player(12, 2.0, 34.0, (2.0, 34.0), (2.0, 34.0), position="GK", speed=60, facing=180.0),
    ]

    mid_passer = player(0, 56.0, 34.0, (56.0, 34.0), (56.0, 34.0), position="CM", speed=74, short=86, long=77, finish=70, long_shot=72, iq=92, facing=0.0)
    mid_passer.consecutive_carries = 1
    mid_teammates = [
        mid_passer,
        player(1, 66.0, 30.0, (68.0, 30.0), (70.0, 30.0), base=(58.0, 30.0), position="CM", speed=76),
        player(2, 70.0, 42.0, (72.0, 42.0), (74.0, 42.0), base=(64.0, 42.0), position="ST", speed=78),
        player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58),
    ]
    mid_opponents = [
        player(10, 76.0, 30.0, (76.0, 30.0), (76.0, 30.0), position="CB", speed=70),
        player(11, 79.0, 42.0, (79.0, 42.0), (79.0, 42.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]

    scenarios = [
        ("right_multi", right_passer, right_teammates, right_opponents, True),
        ("left_multi", left_passer, left_teammates, left_opponents, False),
        ("midfield_multi", mid_passer, mid_teammates, mid_opponents, True),
    ]
    for case_id, passer, teammates, opponents, attacking_right in scenarios:
        current_value, py_details = _real_python_pass_details(
            passer,
            teammates,
            opponents,
            config,
            pitch,
            attacking_right,
        )
        rust_details = _rust_team_pass_details(
            case_id,
            passer,
            teammates,
            opponents,
            config,
            attacking_right,
            current_value,
        )
        _assert_pass_detail_lists_match(rust_details, py_details)


def test_rust_pass_adapter_tuple_shape_matches_python_core_fields():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    passer.consecutive_carries = 3
    receiver = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    teammates = [
        passer,
        receiver,
        player(2, 86.0, 46.0, (90.0, 42.0), (91.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70),
        player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58),
    ]
    opponents = [
        player(10, 90.0, 32.0, (90.0, 32.0), (90.0, 32.0), position="CB", speed=70),
        player(11, 94.0, 44.0, (94.0, 44.0), (94.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = True
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    py_candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )
    rust_candidates = score_pass_point_option_tuples_rust(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        current_value=current_value,
    )
    assert len(rust_candidates) == len(py_candidates)
    component_keys = [
        "current_value",
        "after_value",
        "effective_delta",
        "continuity",
        "lane_risk",
        "receiver_pressure",
        "turnover_consequence",
        "receiver_arrival",
        "base_accuracy",
        "receiver_goal_fit",
        "distance",
        "success_prob",
        "risk_cost",
        "final_score",
    ]
    for rust, py in zip(rust_candidates, py_candidates):
        rust_score, rust_action, rust_details = rust
        py_score, py_action, py_details = py
        assert rust_action == py_action == "pass"
        assert abs(rust_score - py_score) < 1e-10
        assert rust_details["target"] == py_details["target"]
        assert abs(rust_details["success_prob"] - py_details["success_prob"]) < 1e-10
        assert abs(rust_details["lane_risk"] - py_details["lane_risk"]) < 1e-10
        assert abs(rust_details["turnover_consequence"] - py_details["turnover_consequence"]) < 1e-10
        assert abs(rust_details["after_value"] - py_details["after_value"]) < 1e-10
        assert abs(rust_details["risk_cost"] - py_details["risk_cost"]) < 1e-10
        assert rust_details["is_long"] == py_details["is_long"]
        assert rust_details["pass_type"] == py_details["pass_type"]
        assert rust_details.get("target_player_idx") == py_details.get("target_player_idx")
        assert rust_details.get("intended_receiver") == py_details.get("intended_receiver")
        for key in component_keys:
            assert abs(rust_details["components"][key] - py_details["components"][key]) < 1e-10
        assert rust_details["components"]["target_kind"] == py_details["components"]["target_kind"]


def test_rust_pass_adapter_opt_in_switch_matches_python_core_fields():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, x, y, target, anchor, base=None, position="CM", speed=72, short=78, long=74, finish=70, long_shot=66, iq=90, facing=0.0):
        p = _vision_player(idx, x, y, iq=iq, facing=facing)
        p.position = position
        p.target_pos = target
        p.tactical_anchor = anchor
        p.base_formation_pos = base or anchor
        p.abilities.update({
            "Speed": speed,
            "Short_Passing": short,
            "Long_Passing": long,
            "Finishing": finish,
            "Long_Shot": long_shot,
        })
        return p

    passer = player(0, 84.0, 18.0, (84.0, 18.0), (84.0, 18.0), position="RW", speed=78, short=84, long=80, finish=76, long_shot=74, iq=96, facing=8.0)
    passer.consecutive_carries = 3
    receiver = player(1, 88.0, 34.0, (93.0, 36.0), (90.0, 34.0), base=(62.0, 34.0), position="CM", speed=82, finish=78, long_shot=72)
    receiver.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(82.0, 34.0),
        value=0.06,
        confidence=0.06,
    )
    teammates = [
        passer,
        receiver,
        player(2, 86.0, 46.0, (90.0, 42.0), (91.0, 46.0), base=(76.0, 46.0), position="ST", speed=80, finish=82, long_shot=70),
        player(3, 8.0, 34.0, (8.0, 34.0), (8.0, 34.0), position="GK", speed=58),
    ]
    opponents = [
        player(10, 90.0, 32.0, (90.0, 32.0), (90.0, 32.0), position="CB", speed=70),
        player(11, 94.0, 44.0, (94.0, 44.0), (94.0, 44.0), position="CB", speed=68),
        player(12, 103.0, 34.0, (103.0, 34.0), (103.0, 34.0), position="GK", speed=60),
    ]
    attacking_right = True
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, attacking_right)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]

    config.rust_pass_batch_adapter_enabled = False
    py_candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )

    config.rust_pass_batch_adapter_enabled = True
    rust_candidates = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        opp_positions,
        tm_positions,
        current_value,
    )

    assert len(rust_candidates) == len(py_candidates)
    for rust, py in zip(rust_candidates, py_candidates):
        assert rust[1] == py[1] == "pass"
        assert abs(rust[0] - py[0]) < 1e-10
        assert rust[2]["target"] == py[2]["target"]
        assert abs(rust[2]["success_prob"] - py[2]["success_prob"]) < 1e-10
        assert abs(rust[2]["risk_cost"] - py[2]["risk_cost"]) < 1e-10
        assert rust[2].get("target_player_idx") == py[2].get("target_player_idx")
        assert rust[2].get("intended_receiver") == py[2].get("intended_receiver")
        assert rust[2]["components"]["target_kind"] == py[2]["components"]["target_kind"]


def test_rust_adapters_are_enabled_by_default():
    config = EngineConfig()
    assert config.rust_pass_batch_adapter_enabled is True
    assert config.rust_on_ball_evaluator_adapter_enabled is True
    assert config.rust_carry_options_adapter_enabled is True
    assert config.rust_pass_execution_adapter_enabled is True


def test_rust_hold_adapter_returns_python_value_result_shape():
    player = _vision_player(9, 70.0, 34.0, iq=88)
    player.position = "CM"
    player.hold_ticks = 2
    player.possession_ticks = 3
    py_value = evaluate_hold(
        player,
        current_pv=0.42,
        pressure=2,
        nearest_pressure=0.35,
        developing_runs=1.2,
        best_pass_score=0.18,
        shoot_score=0.04,
        opportunity_wait_value=0.32,
    )
    rust_value = evaluate_hold_rust(
        player,
        current_pv=0.42,
        pressure=2,
        nearest_pressure=0.35,
        developing_runs=1.2,
        best_pass_score=0.18,
        shoot_score=0.04,
        opportunity_wait_value=0.32,
    )

    assert isinstance(rust_value, ValueResult)
    assert abs(rust_value.score - py_value.score) < 1e-12
    for key in (
        "pressure_factor",
        "useful_development",
        "no_clear_release",
        "opportunity_wait",
        "opportunity_cost",
    ):
        assert abs(rust_value.components[key] - py_value.components[key]) < 1e-12


def test_rust_clear_adapter_returns_python_value_result_shape():
    config = EngineConfig()
    cases = [
        ("safe", 0.80, 0),
        ("own_pressure", 0.20, 2),
        ("own_high_pressure", 0.05, 4),
    ]
    for _case_id, x_progress, pressure in cases:
        py_value = evaluate_clear(x_progress, pressure, config)
        rust_value = evaluate_clear_rust(
            x_progress,
            pressure,
            config.clear_reward_base,
        )
        assert isinstance(rust_value, ValueResult)
        assert abs(rust_value.score - py_value.score) < 1e-12
        assert abs(rust_value.success_prob - py_value.success_prob) < 1e-12
        assert abs(rust_value.risk_cost - py_value.risk_cost) < 1e-12
        for key in (
            "current_value",
            "after_value",
            "delta",
            "success_prob",
            "risk_cost",
            "opportunity_cost",
            "continuity",
            "final_score",
            "danger",
            "pressure_factor",
        ):
            assert abs(rust_value.components[key] - py_value.components[key]) < 1e-12


def test_rust_on_ball_evaluator_adapter_opt_in_matches_python_scorers():
    config = EngineConfig()
    pitch = Pitch(config=config)
    holder = _teammate(1, 82.0, 30.0, 80, 82)
    holder.position = "RW"
    holder.abilities.update({"IQ": 88, "Dribbling": 82})
    holder.hold_ticks = 2
    holder.possession_ticks = 3
    holder.consecutive_carries = 1
    holder.last_receive_origin = (88.0, 34.0)
    teammates = [
        holder,
        _teammate(2, 76.0, 40.0, 74, 76),
        _teammate(3, 88.0, 34.0, 82, 70),
    ]
    teammates[1].target_pos = (74.0, 38.0)
    teammates[2].target_pos = (90.0, 34.0)
    opponents = [_opponent(10, 88.0, 30.0), _opponent(11, 90.0, 40.0)]

    pass_candidates = [(0.18, "pass", {"target": (88.0, 34.0)})]
    space_pass_candidates = []
    config.rust_on_ball_evaluator_adapter_enabled = False
    py_hold = holder._score_hold_value(
        teammates,
        opponents,
        config,
        pitch,
        True,
        pressure=2,
        shoot_score=0.04,
        pass_candidates=pass_candidates,
        space_pass_candidates=space_pass_candidates,
    )
    py_shot = holder._score_shoot(
        (config.pitch_length, config.pitch_width / 2.0),
        config,
        pitch,
        opponents,
        dist_to_goal=24.0,
        current_state_value=0.55,
        teammates=teammates,
        attacking_right=True,
    )
    py_clear = holder._score_clear_value(0.20, 2, config)
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != holder.index]
    py_carry = holder._score_carry_options(
        config,
        pitch,
        True,
        opponents,
        opp_positions,
        tm_positions,
        teammates,
        current_state_value=0.55,
    )

    config.rust_on_ball_evaluator_adapter_enabled = True
    rust_hold = holder._score_hold_value(
        teammates,
        opponents,
        config,
        pitch,
        True,
        pressure=2,
        shoot_score=0.04,
        pass_candidates=pass_candidates,
        space_pass_candidates=space_pass_candidates,
    )
    rust_shot = holder._score_shoot(
        (config.pitch_length, config.pitch_width / 2.0),
        config,
        pitch,
        opponents,
        dist_to_goal=24.0,
        current_state_value=0.55,
        teammates=teammates,
        attacking_right=True,
    )
    rust_clear = holder._score_clear_value(0.20, 2, config)
    rust_carry = holder._score_carry_options(
        config,
        pitch,
        True,
        opponents,
        opp_positions,
        tm_positions,
        teammates,
        current_state_value=0.55,
    )
    config.rust_carry_options_adapter_enabled = True
    rust_full_carry = holder._score_carry_options(
        config,
        pitch,
        True,
        opponents,
        opp_positions,
        tm_positions,
        teammates,
        current_state_value=0.55,
    )

    assert abs(rust_hold.score - py_hold.score) < 1e-12
    for key in ("pressure_factor", "useful_development", "no_clear_release", "opportunity_wait", "opportunity_cost"):
        assert abs(rust_hold.components[key] - py_hold.components[key]) < 1e-12

    assert abs(rust_shot[0] - py_shot[0]) < 1e-12
    for key in ("success_prob", "xg", "after_value", "risk_cost"):
        assert abs(rust_shot[1][key] - py_shot[1][key]) < 1e-12
    for key in ("save_estimate", "opportunity_cost", "shot_readiness", "possession_loss_multiplier", "support_release_window"):
        assert abs(rust_shot[1]["components"][key] - py_shot[1]["components"][key]) < 1e-12

    assert abs(rust_clear.score - py_clear.score) < 1e-12
    assert abs(rust_clear.components["danger"] - py_clear.components["danger"]) < 1e-12
    assert abs(rust_clear.components["pressure_factor"] - py_clear.components["pressure_factor"]) < 1e-12

    assert len(rust_carry) == len(py_carry)
    assert len(rust_full_carry) == len(py_carry)
    for rust_item, py_item in zip(rust_carry, py_carry):
        assert rust_item[1] == py_item[1] == "carry"
        assert abs(rust_item[0] - py_item[0]) < 1e-10
        assert rust_item[2]["target"] == py_item[2]["target"]
        assert abs(rust_item[2]["success_prob"] - py_item[2]["success_prob"]) < 1e-12
        assert abs(rust_item[2]["risk_cost"] - py_item[2]["risk_cost"]) < 1e-12
        assert abs(rust_item[2]["after_value"] - py_item[2]["after_value"]) < 1e-12
        for key in (
            "continuity",
            "pv_gain",
            "future_shot_gain",
            "carry_to_shoot_window",
            "effective_gain",
            "near_goal_multiplier",
            "release_pressure",
            "space_manipulation",
            "path_conflict_cost",
        ):
            assert abs(rust_item[2]["components"][key] - py_item[2]["components"][key]) < 1e-10
    for rust_item, py_item in zip(rust_full_carry, py_carry):
        assert rust_item[1] == py_item[1] == "carry"
        assert abs(rust_item[0] - py_item[0]) < 1e-10
        assert rust_item[2]["target"] == py_item[2]["target"]
        assert abs(rust_item[2]["success_prob"] - py_item[2]["success_prob"]) < 1e-12
        assert abs(rust_item[2]["risk_cost"] - py_item[2]["risk_cost"]) < 1e-12
        assert abs(rust_item[2]["after_value"] - py_item[2]["after_value"]) < 1e-12
        for key in (
            "continuity",
            "pv_gain",
            "future_shot_gain",
            "carry_to_shoot_window",
            "effective_gain",
            "near_goal_multiplier",
            "release_pressure",
            "space_manipulation",
            "path_conflict_cost",
        ):
            assert abs(rust_item[2]["components"][key] - py_item[2]["components"][key]) < 1e-10


def test_rust_shot_adapter_returns_python_value_result_shape():
    config = EngineConfig()
    shooter = _teammate(1, 82.0, 30.0, 80, 82)
    shooter.position = "RW"
    shooter.possession_ticks = 1
    shooter.consecutive_carries = 0
    shooter.last_receive_origin = (88.0, 34.0)
    teammates = [
        shooter,
        _teammate(2, 76.0, 40.0, 74, 76),
        _teammate(3, 88.0, 34.0, 82, 70),
    ]
    teammates[1].target_pos = (74.0, 38.0)
    teammates[2].target_pos = (90.0, 34.0)
    opponents = [_opponent(10, 88.0, 30.0), _opponent(11, 90.0, 40.0)]
    py_value = evaluate_shot(
        shooter,
        (config.pitch_length, config.pitch_width / 2.0),
        config,
        opponents,
        24.0,
        0.72,
        0.94,
        0.95,
        0.72,
        0.55,
        teammates=teammates,
        pitch=Pitch(config=config),
        attacking_right=True,
    )
    rust_value = evaluate_shot_rust(
        shooter,
        shooter.pos,
        dist_to_goal=24.0,
        angle_factor=0.72,
        pressure_factor=0.94,
        lane_factor=0.95,
        dist_factor=0.72,
        current_state_value=0.55,
        teammates=teammates,
        opponents=opponents,
        config=config,
        attacking_right=True,
    )

    assert isinstance(rust_value, ValueResult)
    assert abs(rust_value.score - py_value.score) < 1e-12
    assert abs(rust_value.success_prob - py_value.success_prob) < 1e-12
    assert abs(rust_value.after_value - py_value.after_value) < 1e-12
    assert abs(rust_value.risk_cost - py_value.risk_cost) < 1e-12
    for key in (
        "save_estimate",
        "opportunity_cost",
        "shot_readiness",
        "possession_loss_multiplier",
        "support_release_window",
    ):
        assert abs(rust_value.components[key] - py_value.components[key]) < 1e-12


def test_rust_shot_option_adapter_matches_python_wrapper():
    config = EngineConfig()
    pitch = Pitch(config=config)
    shooter = _teammate(1, 82.0, 30.0, 80, 82)
    shooter.position = "RW"
    shooter.possession_ticks = 2
    shooter.consecutive_carries = 1
    shooter.last_receive_origin = (78.0, 42.0)
    teammates = [
        shooter,
        _teammate(2, 78.0, 40.0, 74, 76),
        _teammate(3, 88.0, 34.0, 82, 70),
    ]
    opponents = [_opponent(10, 90.0, 30.0), _opponent(11, 90.0, 40.0)]
    goal_center = (config.pitch_length, config.pitch_width / 2.0)
    dist_to_goal = py_physics.distance(shooter.pos, goal_center)
    config.rust_shot_option_adapter_enabled = False
    config.rust_on_ball_evaluator_adapter_enabled = False
    py_score, py_details = shooter._score_shoot(
        goal_center,
        config,
        pitch,
        opponents,
        dist_to_goal,
        current_state_value=0.42,
        teammates=teammates,
        attacking_right=True,
    )
    config.rust_shot_option_adapter_enabled = True
    rust_score, rust_details = shooter._score_shoot(
        goal_center,
        config,
        pitch,
        opponents,
        dist_to_goal,
        current_state_value=0.42,
        teammates=teammates,
        attacking_right=True,
    )
    assert abs(rust_score - py_score) < 1e-12
    for key in ("success_prob", "on_target_prob", "xg", "after_value", "risk_cost"):
        assert abs(rust_details[key] - py_details[key]) < 1e-12
    for key in (
        "save_estimate",
        "opportunity_cost",
        "shot_readiness",
        "possession_loss_multiplier",
        "support_release_window",
    ):
        assert abs(rust_details["components"][key] - py_details["components"][key]) < 1e-12


def test_rust_carry_adapter_returns_python_value_result_shape():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _teammate(1, 70.0, 34.0, 78, 76)
    carrier.position = "RW"
    carrier.abilities["Dribbling"] = 82
    carrier.consecutive_carries = 2
    carrier.possession_ticks = 3
    target = (76.0, 38.0)
    target_pv = position_value(
        target[0],
        target[1],
        pitch,
        True,
        [(78.0, 35.0), (82.0, 42.0)],
        [(74.0, 40.0), (86.0, 34.0)],
        config,
    )
    current_pv = position_value(
        carrier.pos[0],
        carrier.pos[1],
        pitch,
        True,
        [(78.0, 35.0), (82.0, 42.0)],
        [(74.0, 40.0), (86.0, 34.0)],
        config,
    )
    teammates = [
        carrier,
        _teammate(2, 74.0, 40.0, 74, 76),
        _teammate(3, 86.0, 34.0, 82, 70),
    ]
    for tm in teammates:
        tm.base_formation_pos = tm.pos
    opponents = [_opponent(10, 78.0, 35.0), _opponent(11, 82.0, 42.0)]
    current_state_value = 0.44
    path_feasibility = 0.73
    py_value = evaluate_carry_target(
        carrier,
        target,
        target_pv,
        current_pv,
        current_state_value,
        path_feasibility,
        teammates,
        opponents,
        config,
        pitch,
        True,
    )
    rust_value = evaluate_carry_rust(
        carrier,
        target,
        target_pv,
        current_pv,
        current_state_value,
        path_feasibility,
        teammates,
        opponents,
        config,
        True,
    )

    assert isinstance(rust_value, ValueResult)
    assert abs(rust_value.score - py_value.score) < 1e-12
    assert abs(rust_value.after_value - py_value.after_value) < 1e-12
    assert abs(rust_value.risk_cost - py_value.risk_cost) < 1e-12
    for key in (
        "continuity",
        "pv_gain",
        "future_shot_gain",
        "carry_to_shoot_window",
        "effective_gain",
        "near_goal_multiplier",
        "release_pressure",
        "space_manipulation",
    ):
        assert abs(rust_value.components[key] - py_value.components[key]) < 1e-12


def test_rust_position_value_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        ("central_mid", 55.0, 34.0, True, [(70.0, 30.0), (74.0, 40.0)], [(52.0, 20.0)]),
        ("final_third", 82.0, 34.0, True, [(88.0, 28.0), (88.0, 40.0)], [(78.0, 22.0), (86.0, 34.0)]),
        ("wide_byline", 96.0, 9.0, True, [(90.0, 18.0), (92.0, 34.0)], [(91.0, 34.0), (82.0, 30.0)]),
        ("left_attack", 28.0, 42.0, False, [(18.0, 34.0), (24.0, 46.0)], [(33.0, 40.0)]),
        ("role_limited", 80.0, 34.0, True, [(84.0, 30.0), (86.0, 39.0)], [(70.0, 34.0)], (45.0, 34.0)),
    ]

    input_payload = "\n".join(
        _case_line(case_id, x, y, attacking_right, opponents, teammates, runner)
        for case_id, x, y, attacking_right, opponents, teammates, *runner_payload in cases
        for runner in [runner_payload[0] if runner_payload else None]
    )
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine"],
        cwd=RUST_CRATE,
        input=input_payload,
        text=True,
        capture_output=True,
        check=True,
    )
    rust_values = {}
    for line in proc.stdout.strip().splitlines():
        case_id, raw_value = line.split("\t")
        rust_values[case_id] = float(raw_value)

    for case in cases:
        case_id, x, y, attacking_right, opponents, teammates, *runner_payload = case
        runner = runner_payload[0] if runner_payload else None
        py_value = position_value(
            x,
            y,
            pitch,
            attacking_right,
            opponents,
            teammates,
            config,
            runner_formation_pos=runner,
        )
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_position_values_adapter_matches_python_batch():
    config = EngineConfig()
    pitch = Pitch(config=config)
    positions = [(42.0, 30.0), (64.0, 42.0), (78.0, 34.0)]
    teammates = [_teammate(1, 48.0, 34.0), _teammate(2, 70.0, 44.0)]
    opponents = [_opponent(20, 58.0, 35.0), _opponent(21, 80.0, 30.0)]
    rust_values = position_values_rust(positions, opponents, teammates, config, True)
    expected = [
        position_value(
            x,
            y,
            pitch,
            True,
            [(p.pos[0], p.pos[1]) for p in opponents],
            [(p.pos[0], p.pos[1]) for p in teammates],
            config,
        )
        for x, y in positions
    ]
    for rust_value, py_value in zip(rust_values, expected):
        assert abs(rust_value - py_value) < 1e-12


def _player(finishing: int, long_shot: int) -> Player:
    return Player(
        index=1,
        name="Shooter",
        position="ST",
        color="gold",
        abilities={
            "Finishing": finishing,
            "Long_Shot": long_shot,
            "Speed": 70,
        },
    )


def _opponent(index: int, x: float, y: float) -> Player:
    player = Player(
        index=index,
        name=f"Opp {index}",
        position="CB",
        color="gold",
        abilities={"Speed": 70},
    )
    player.pos = (x, y)
    return player


def _teammate(index: int, x: float, y: float, finishing: int = 70, long_shot: int = 70) -> Player:
    player = _player(finishing, long_shot)
    player.index = index
    player.name = f"TM {index}"
    player.pos = (x, y)
    return player


def test_rust_shot_quality_matches_python():
    config = EngineConfig()
    cases = [
        ("central_close", 90.0, 34.0, 82, 74, True, [(88.0, 29.0), (88.0, 39.0)]),
        ("wide_angle", 92.0, 18.0, 82, 74, True, [(89.0, 24.0), (91.0, 33.0)]),
        ("long_shot", 70.0, 34.0, 76, 86, True, [(80.0, 34.0)]),
        ("left_attack", 18.0, 36.0, 80, 72, False, [(25.0, 34.0), (22.0, 42.0)]),
    ]
    input_payload = "\n".join(
        _shot_case_line(case_id, x, y, finishing / 100.0, long_shot / 100.0, attacking_right, opponents)
        for case_id, x, y, finishing, long_shot, attacking_right, opponents in cases
    )
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "shot_quality"],
        cwd=RUST_CRATE,
        input=input_payload,
        text=True,
        capture_output=True,
        check=True,
    )
    rust_values = {}
    for line in proc.stdout.strip().splitlines():
        case_id, raw_value = line.split("\t")
        rust_values[case_id] = float(raw_value)

    for case_id, x, y, finishing, long_shot, attacking_right, opponents in cases:
        player = _player(finishing, long_shot)
        player.pos = (x, y)
        py_opponents = [_opponent(idx + 10, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_value = shot_quality_at((x, y), player, py_opponents, config, attacking_right)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_goalkeeper_save_and_rush_match_python():
    config = EngineConfig()
    save_cases = [
        ("central", (101.0, 34.0), (105.0, 34.0), (90.0, 34.0), 82, 80, 78),
        ("wide", (101.0, 30.0), (105.0, 39.0), (88.0, 20.0), 76, 70, 88),
        ("left_goal", (4.0, 34.0), (0.0, 30.0), (18.0, 42.0), 88, 84, 82),
    ]
    save_proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "gk_save"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([
                str(gk_pos[0]),
                str(gk_pos[1]),
                str(shot_target[0]),
                str(shot_target[1]),
                str(shot_origin[0]),
                str(shot_origin[1]),
                str(gk_saving),
                str(gk_positioning),
                str(gk_reaction),
                str(config.pitch_length),
                str(config.gk_position_error_factor),
                str(config.gk_reaction_delay_factor),
                str(config.gk_save_base),
                case_id,
            ])
            for case_id, gk_pos, shot_target, shot_origin, gk_saving, gk_positioning, gk_reaction in save_cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_save = {
        case_id: float(value)
        for case_id, value in (line.split("\t") for line in save_proc.stdout.strip().splitlines())
    }
    for case_id, gk_pos, shot_target, shot_origin, gk_saving, gk_positioning, gk_reaction in save_cases:
        gk = _teammate(0, gk_pos[0], gk_pos[1])
        gk.position = "GK"
        gk.abilities.update({
            "GK_Saving": gk_saving,
            "GK_Positioning": gk_positioning,
            "GK_Reaction": gk_reaction,
        })
        py_value = compute_gk_save_probability(gk, shot_target, shot_origin, config)
        assert abs(rust_save[case_id] - py_value) < 1e-12

    rush_cases = [
        ("far", (102.0, 34.0), (78.0, 34.0), 80, 80),
        ("close_good", (102.0, 34.0), (88.0, 34.0), 88, 84),
        ("close_bad", (102.0, 34.0), (88.0, 34.0), 45, 45),
    ]
    rush_proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "gk_rush"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([
                str(gk_pos[0]),
                str(gk_pos[1]),
                str(attacker_pos[0]),
                str(attacker_pos[1]),
                str(positioning),
                str(iq),
                str(config.gk_rush_distance),
                case_id,
            ])
            for case_id, gk_pos, attacker_pos, positioning, iq in rush_cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rush = {
        case_id: value == "1"
        for case_id, value in (line.split("\t") for line in rush_proc.stdout.strip().splitlines())
    }
    for case_id, gk_pos, attacker_pos, positioning, iq in rush_cases:
        gk = _teammate(0, gk_pos[0], gk_pos[1])
        gk.position = "GK"
        gk.abilities.update({"GK_Positioning": positioning, "IQ": iq})
        assert rust_rush[case_id] == should_rush_out(gk, attacker_pos, config)


def test_rust_goalkeeper_distribution_matches_python_with_explicit_rolls():
    config = EngineConfig()
    cases = [
        ("short_right", 34.0, 82, 82, 62, True, -0.05, 24.0, 8.0),
        ("long_right", 31.0, 55, 45, 82, True, 0.08, 58.0, 42.0),
        ("short_left", 30.0, 90, 86, 62, False, -0.02, 76.0, -6.0),
        ("long_left", 36.0, 50, 44, 88, False, 0.06, 52.0, 22.0),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "gk_distribution"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([
                str(gk_y),
                str(iq),
                str(short_passing),
                str(long_passing),
                "1" if attacking_right else "0",
                str(config.pitch_length),
                str(decision_noise),
                str(target_x_sample),
                str(target_y_sample),
                case_id,
            ])
            for case_id, gk_y, iq, short_passing, long_passing, attacking_right, decision_noise, target_x_sample, target_y_sample in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        case_id, dist_type, x, y = line.split("\t")
        rust_rows[case_id] = (dist_type, (float(x), float(y)))

    for case_id, gk_y, iq, short_passing, long_passing, attacking_right, decision_noise, target_x_sample, target_y_sample in cases:
        gk = _teammate(0, 4.5 if attacking_right else config.pitch_length - 4.5, gk_y)
        gk.position = "GK"
        gk.abilities.update({
            "IQ": iq,
            "Short_Passing": short_passing,
            "Long_Passing": long_passing,
        })
        with patch(
            "psl_core.engine_v2.goalkeeper.random.uniform",
            side_effect=[decision_noise, target_x_sample, target_y_sample],
        ):
            py_type, py_target = choose_distribution(gk, config, attacking_right, config.pitch_length)
        rust_type, rust_target = rust_rows[case_id]
        assert rust_type == py_type
        assert abs(rust_target[0] - py_target[0]) < 1e-12
        assert abs(rust_target[1] - py_target[1]) < 1e-12


def test_rust_gk_fallback_target_matches_python_formula():
    config = EngineConfig()
    rows = _run_rust_rows("gk_fallback_target", [
        "\t".join(["1", str(config.pitch_length), str(config.pitch_width), "right"]),
        "\t".join(["0", str(config.pitch_length), str(config.pitch_width), "left"]),
    ])
    _assert_close_tuple(rows["right"], (config.pitch_length * 0.55, config.pitch_width / 2.0), eps=1e-12)
    _assert_close_tuple(rows["left"], (config.pitch_length * 0.45, config.pitch_width / 2.0), eps=1e-12)


def test_rust_goal_switch_cost_matches_python():
    cases = [
        ("stable", 0.035, 1.0, 1.0, 0.0, 80),
        ("pressured", 0.040, 1.0, 1.0, 0.8, 80),
        ("low_iq", 0.035, 0.8, 1.2, 0.2, 55),
        ("elite_iq", 0.035, 1.0, 0.9, 0.0, 130),
    ]
    rust_values = _run_rust_mode("goal_switch_cost", [
        _goal_switch_case_line(*case)
        for case in cases
    ])
    for case_id, base, context_stability, role_discipline, pressure_interrupt, iq in cases:
        py_value = goal_switch_cost(GoalSwitchContext(
            base=base,
            context_stability=context_stability,
            role_discipline=role_discipline,
            pressure_interrupt=pressure_interrupt,
            iq=iq,
        ))
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_iq_temperature_factor_matches_python():
    cases = [
        ("low", 55, 0.35, 0.95, 0.25),
        ("normal", 100, 0.35, 0.95, 0.25),
        ("elite", 130, 0.35, 0.95, 0.25),
        ("high_discount", 130, 0.22, 1.20, 0.55),
    ]
    rust_values = _run_rust_mode("iq_temperature", [
        _iq_temperature_case_line(*case)
        for case in cases
    ])
    for case_id, iq, floor, low_iq_range, elite_discount in cases:
        py_value = iq_temperature_factor(
            iq,
            floor=floor,
            low_iq_range=low_iq_range,
            elite_discount=elite_discount,
        )
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_select_goal_deterministic_matches_python():
    cases = [
        ("none", "-", 0.0, "-", "progress_carry", 0.20, "execute", 0.035, 1.0, 1.0, 0.0, 80),
        ("within_cost", "cut_inside_to_shoot", 0.20, "drive", "recycle", 0.215, "execute", 0.04, 1.0, 1.0, 0.0, 80),
        ("clears_cost", "wide_hold_for_overlap", 0.20, "scan", "shoot", 0.31, "execute", 0.035, 1.0, 1.0, 0.0, 80),
        ("phase_update", "cut_inside_to_shoot", 0.20, "drive", "cut_inside_to_shoot", 0.08, "release", 0.50, 1.0, 1.0, 0.0, 80),
        ("drive_update", "cut_inside_to_shoot", 0.20, "drive", "cut_inside_to_shoot", 0.26, "drive", 0.50, 1.0, 1.0, 0.0, 80),
        ("scan_update", "hold_for_opportunity", 0.18, "scan", "hold_for_opportunity", 0.12, "scan", 0.50, 1.0, 1.0, 0.0, 80),
        ("defend_update", "defend_mark_runner", 0.20, "defend", "defend_press", 0.10, "defend", 0.50, 1.0, 1.0, 0.0, 80),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "select_goal"],
        cwd=RUST_CRATE,
        input="\n".join(_select_goal_case_line(*case) for case in cases),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        case_id, selected, switched, switch_cost, advantage, noisy_advantage, reason = line.split("\t")
        rust_rows[case_id] = {
            "selected": selected,
            "switched": switched == "1",
            "switch_cost": float(switch_cost),
            "value_advantage": float(advantage),
            "noisy_value_advantage": float(noisy_advantage),
            "reason": reason,
        }

    for (
        case_id,
        current_type,
        current_value,
        current_phase,
        candidate_type,
        candidate_value,
        candidate_phase,
        base,
        context_stability,
        role_discipline,
        pressure_interrupt,
        iq,
    ) in cases:
        current = None if current_type == "-" else PlayerGoal(
            goal_type=current_type,
            target_pos=(80.0, 34.0),
            value=current_value,
            context={} if current_phase == "-" else {"phase": current_phase},
        )
        candidate = PlayerGoal(
            goal_type=candidate_type,
            target_pos=(82.0, 34.0),
            value=candidate_value,
            context={} if candidate_phase == "-" else {"phase": candidate_phase},
        )
        py = select_goal(
            current,
            candidate,
            GoalSwitchContext(
                base=base,
                context_stability=context_stability,
                role_discipline=role_discipline,
                pressure_interrupt=pressure_interrupt,
                iq=iq,
                goal_noise_scale=0.0,
            ),
        )
        rust = rust_rows[case_id]
        expected_selected = "current" if py.reason == "current_goal_within_switch_cost" else "candidate"
        assert rust["selected"] == expected_selected
        assert rust["switched"] == py.switched
        assert abs(rust["switch_cost"] - py.switch_cost) < 1e-12
        assert abs(rust["value_advantage"] - py.value_advantage) < 1e-12
        assert abs(rust["noisy_value_advantage"] - py.noisy_value_advantage) < 1e-12
        assert rust["reason"] == py.reason


def test_rust_select_goal_candidate_noise_matches_python():
    cases = [
        ("no_noise", [0.20, 0.24], [0.0, 0.0], 0.035, 1.0, 1.0, 0.0, 80, 0.0),
        ("noise_flip", [0.200, 0.204], [0.010, -0.010], 0.035, 1.0, 1.0, 0.0, 70, 0.010),
        ("pressure_noise", [0.180, 0.181, 0.179], [-0.5, 0.2, 1.0], 0.035, 1.0, 1.0, 0.8, 65, 0.012),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "select_goal_candidate"],
        cwd=RUST_CRATE,
        input="\n".join(_select_goal_candidate_case_line(*case) for case in cases),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        case_id, index, candidate_noise, noisy_value = line.split("\t")
        rust_rows[case_id] = {
            "index": None if index == "-" else int(index),
            "candidate_noise": float(candidate_noise),
            "noisy_value": float(noisy_value),
        }

    for case_id, values, gaussians, base, context_stability, role_discipline, pressure_interrupt, iq, goal_noise_scale in cases:
        goals = [
            PlayerGoal(goal_type=f"goal_{idx}", target_pos=(80.0, 34.0), value=value)
            for idx, value in enumerate(values)
        ]
        py = select_goal_candidate(
            goals,
            GoalSwitchContext(
                base=base,
                context_stability=context_stability,
                role_discipline=role_discipline,
                pressure_interrupt=pressure_interrupt,
                iq=iq,
                goal_noise_scale=goal_noise_scale,
                rng=_FixedGaussian(gaussians),
            ),
        )
        rust = rust_rows[case_id]
        assert rust["index"] == goals.index(py.goal)
        assert abs(rust["candidate_noise"] - py.candidate_noise) < 1e-12
        assert abs(rust["noisy_value"] - py.noisy_value) < 1e-12


def test_rust_select_goal_candidate_adapter_matches_python_and_rng():
    import random

    goals = [
        PlayerGoal(goal_type="a", target_pos=(70.0, 34.0), value=0.120),
        PlayerGoal(goal_type="b", target_pos=(74.0, 36.0), value=0.124),
        PlayerGoal(goal_type="c", target_pos=(78.0, 32.0), value=0.119),
    ]
    context = GoalSwitchContext(iq=72, goal_noise_scale=0.010)
    random.seed(20260709)
    py = select_goal_candidate(goals, context)
    py_state = random.getstate()

    random.seed(20260709)
    rust = select_goal_candidate_rust(goals, context)
    rust_state = random.getstate()

    assert rust["index"] == goals.index(py.goal)
    assert abs(rust["candidate_noise"] - py.candidate_noise) < 1e-12
    assert abs(rust["noisy_value"] - py.noisy_value) < 1e-12
    assert rust_state == py_state


def test_rust_softmax_select_index_matches_python_formula():
    import math

    cases = [
        ("single", [0.2], 80, 0.4, 0),
        ("clear_best", [0.05, 0.18, 0.04], 82, 0.25, 1),
        ("close_scores", [0.101, 0.102, 0.100], 68, 0.72, 0),
        ("fallback", [0.0001, 0.0002], 75, 0.5, 1),
    ]
    rows = _run_rust_rows("softmax_select", [
        "\t".join([
            ",".join(str(score) for score in scores),
            str(iq),
            str(roll),
            str(fallback),
            case_id,
        ])
        for case_id, scores, iq, roll, fallback in cases
    ])

    for case_id, scores, iq, roll, fallback in cases:
        if len(scores) == 1:
            expected_idx = 0
            expected_temp = 0.0
            expected_total = 1.0
        elif max(scores) < 0.001:
            expected_idx = fallback % len(scores)
            expected_temp = 0.0
            expected_total = 1.0
        else:
            max_score = max(scores)
            min_score = min(scores)
            score_spread = max(0.0, max_score - min_score)
            expected_temp = (0.0012 + score_spread * 0.10) * iq_temperature_factor(
                iq,
                floor=0.18,
                low_iq_range=0.62,
                elite_discount=0.30,
            )
            expected_temp = max(0.0008, min(0.018, expected_temp))
            weights = [math.exp((score - max_score) / expected_temp) for score in scores]
            expected_total = sum(weights)
            threshold = roll * expected_total
            cumulative = 0.0
            expected_idx = len(scores) - 1
            for idx, weight in enumerate(weights):
                cumulative += weight
                if threshold <= cumulative:
                    expected_idx = idx
                    break

        assert int(rows[case_id][0]) == expected_idx
        assert abs(float(rows[case_id][1]) - expected_temp) < 1e-12
        assert abs(float(rows[case_id][2]) - expected_total) < 1e-12


def test_rust_softmax_adapter_opt_in_matches_python_selection():
    config = EngineConfig()
    player = _vision_player(1, 50.0, 34.0, iq=82)
    candidates = [
        (0.05, "hold", {"target": (50.0, 34.0)}),
        (0.18, "pass", {"target": (70.0, 34.0)}),
        (0.11, "carry", {"target": (55.0, 36.0)}),
    ]
    with patch("random.random", return_value=0.37):
        py_choice = player._softmax_select(candidates, config)
    config.rust_softmax_selection_adapter_enabled = True
    with patch("random.random", return_value=0.37):
        rust_choice = player._softmax_select(candidates, config)

    assert rust_choice == py_choice
    assert softmax_select_index_rust([0.05, 0.18, 0.11], 82, 0.37) == candidates.index(py_choice)


def test_rust_on_ball_selection_matches_python_release_noise_and_softmax():
    import math

    config = EngineConfig()
    player = _vision_player(1, 50.0, 34.0, iq=78)
    candidates = [
        player._make_candidate(
            "hold",
            0.118,
            {"target": (50.0, 34.0), "components": {}},
            "hold",
        ),
        player._make_candidate(
            "pass",
            0.142,
            {
                "target": (72.0, 42.0),
                "success_prob": 0.44,
                "components": {
                    "target_kind": "space",
                    "receiver_pressure": 0.34,
                    "high_threat_space": 0.72,
                },
            },
            "pass",
        ),
        player._make_candidate(
            "shoot",
            0.161,
            {"target": (105.0, 34.0), "components": {}},
            "shot",
        ),
        player._make_candidate(
            "carry",
            0.136,
            {"target": (56.0, 31.0), "components": {}},
            "carry",
        ),
    ]

    current_goal_type = "hold_for_opportunity"
    adjusted = player._apply_release_confidence(candidates, current_goal_type)
    noises = [0.005, -0.012, 0.003, 0.010]
    noisy_scores = [
        candidate.score * (1.0 + noise)
        for candidate, noise in zip(adjusted, noises)
    ]
    roll = 0.42
    max_score = max(noisy_scores)
    min_score = min(noisy_scores)
    score_spread = max(0.0, max_score - min_score)
    temperature = (0.0012 + score_spread * 0.10) * iq_temperature_factor(
        player.iq_value,
        floor=0.18,
        low_iq_range=0.62,
        elite_discount=0.30,
    )
    temperature = max(0.0008, min(0.018, temperature))
    weights = [math.exp((score - max_score) / temperature) for score in noisy_scores]
    threshold = roll * sum(weights)
    cumulative = 0.0
    expected_index = len(weights) - 1
    for idx, weight in enumerate(weights):
        cumulative += weight
        if threshold <= cumulative:
            expected_index = idx
            break

    action_codes = {"carry": 0, "pass": 1, "shoot": 2, "hold": 3, "clear": 4}
    rows = _run_rust_rows("on_ball_select", [
        "\t".join([
            ";".join(
                ",".join([
                    str(candidate.score),
                    str(action_codes[candidate.action_type]),
                    "1" if candidate.details.get("components", {}).get("target_kind") == "space" else "0",
                    str(candidate.value.success_prob or 0.0),
                    str(candidate.value.components.get("receiver_pressure", 0.0)),
                    str(candidate.value.components.get("high_threat_space", 0.0)),
                ])
                for candidate in candidates
            ),
            "1",
            str(player.iq_value),
            ",".join(str(noise) for noise in noises),
            str(roll),
            "0",
            "onball_select",
        ])
    ])
    assert int(rows["onball_select"][0]) == expected_index
    assert rows["onball_select"][1] == "1"
    assert rows["onball_select"][2] == "0"
    _assert_close_tuple(rows["onball_select"][3].split(","), [candidate.score for candidate in adjusted], eps=1e-12)
    _assert_close_tuple(rows["onball_select"][4].split(","), noisy_scores, eps=1e-12)


def test_rust_generic_on_ball_goal_continuity_matches_python():
    config = EngineConfig()
    player = _vision_player(1, 58.0, 42.0, iq=82)
    candidates = [
        player._make_candidate(
            "carry",
            0.126,
            {
                "target": (66.0, 39.0),
                "components": {
                    "progress_gain": 0.04,
                    "xg": 0.02,
                },
            },
            "carry",
        ),
        player._make_candidate(
            "pass",
            0.118,
            {
                "target": (72.0, 30.0),
                "components": {
                    "progress_gain": 0.02,
                    "target_kind": "space",
                    "receiver_pressure": 0.18,
                },
            },
            "pass",
        ),
        player._make_candidate(
            "hold",
            0.071,
            {"target": player.pos, "components": {}},
            "hold",
        ),
    ]
    py_biased, py_trace = player._apply_generic_on_ball_goal_continuity(
        candidates,
        config,
        tick=22,
    )
    action_codes = {"carry": 0, "pass": 1, "shoot": 2, "hold": 3, "clear": 4}
    rows = _run_rust_rows("on_ball_generic_goal", [
        "\t".join([
            ";".join(
                ",".join([
                    str(candidate.score),
                    str(action_codes[candidate.action_type]),
                    str(candidate.target[0]) if candidate.target else "-",
                    str(candidate.target[1]) if candidate.target else "-",
                    str(candidate.value.components.get("progress_gain", 0.0)),
                    str(candidate.value.components.get("xg", 0.0)),
                    str(candidate.value.components.get("nearest_pressure", candidate.value.components.get("receiver_pressure", 0.0))),
                    str(candidate.value.components.get("receiver_pressure", 0.0)),
                    "1" if candidate.value.components.get("target_kind") == "space" else "0",
                    str(candidate.value.components.get("lateral_change", 0.0)),
                ])
                for candidate in candidates
            ),
            "-",
            "0.0",
            "0.0",
            "0.0",
            "0",
            str(player.iq_value),
            str(config.goal_cut_inside_bias),
            "0.0",
            "onball_goal",
        ])
    ])
    rust = rows["onball_goal"]
    assert rust[0] == py_trace["goal"]["goal_type"]
    assert int(rust[1]) == action_codes[py_trace["goal"]["context"]["action"]]
    _assert_close_tuple(rust[2:4], py_trace["goal"]["target_pos"], eps=1e-12)
    assert abs(float(rust[4]) - py_trace["goal"]["value"]) < 1e-12
    assert rust[10] == ("1" if py_trace["switched"] else "0")
    assert abs(float(rust[11]) - py_trace["switch_cost"]) < 1e-12
    assert abs(float(rust[12]) - py_trace["value_advantage"]) < 1e-12
    assert rust[13] == py_trace["reason"]
    _assert_close_tuple(rust[14].split(","), [candidate.score for candidate in py_biased], eps=1e-12)


def test_rust_specialized_on_ball_bias_matches_python_formula():
    bias = 0.035
    goal_value = 0.24
    goal_target = (72.0, 38.0)
    candidates = [
        # carry candidate with stretch/manipulation
        (0.10, 0, (70.0, 37.0), {
            "carry_to_shoot_window": 0.08,
            "wide_second_line_carry_window": 0.03,
            "future_shot_gain": 0.04,
            "byline_carry_window": 0.00,
            "xg": 0.0,
            "shot_readiness": 0.0,
            "open_medium_window": 0.0,
            "clean_second_line_shot": 0.0,
            "space_manipulation": 0.10,
            "pressure_draw": 0.04,
        }),
        # pass candidate near support target
        (0.12, 1, (73.0, 39.0), {}),
        # hold candidate should receive target injection marker
        (0.07, 3, (58.0, 42.0), {}),
    ]

    def cget(components, key):
        return float(components.get(key, 0.0) or 0.0)

    expected = []
    for score, action_code, target, components in candidates:
        adjusted = score
        if action_code == 3:
            adjusted += bias * goal_value * 0.34
        elif action_code == 0:
            stretch_fit = max(0.0, 1.0 - py_physics.distance(target, goal_target) / 14.0)
            manipulation = max(
                cget(components, "space_manipulation"),
                cget(components, "pressure_draw"),
                cget(components, "carry_to_shoot_window") * 0.80,
                cget(components, "wide_second_line_carry_window") * 0.65,
            )
            adjusted += bias * goal_value * (0.80 * stretch_fit + 0.55 * manipulation)
        elif action_code == 1:
            support_fit = max(0.0, 1.0 - py_physics.distance(target, goal_target) / 13.0)
            adjusted += bias * support_fit * goal_value * 1.15
        expected.append(adjusted)

    payload = []
    for score, action_code, target, components in candidates:
        payload.append(",".join([
            str(score),
            str(action_code),
            str(target[0]),
            str(target[1]),
            str(cget(components, "carry_to_shoot_window")),
            str(cget(components, "wide_second_line_carry_window")),
            str(cget(components, "future_shot_gain")),
            str(cget(components, "byline_carry_window")),
            str(cget(components, "xg")),
            str(cget(components, "shot_readiness")),
            str(cget(components, "open_medium_window")),
            str(cget(components, "clean_second_line_shot")),
            str(cget(components, "space_manipulation")),
            str(cget(components, "pressure_draw")),
        ]))

    rows = _run_rust_rows("on_ball_specialized_bias", [
        "\t".join([
            ";".join(payload),
            "hold_for_opportunity",
            "scan",
            str(goal_target[0]),
            str(goal_target[1]),
            str(goal_value),
            str(bias),
            "2",
            "special_bias",
        ])
    ])
    _assert_close_tuple(rows["special_bias"][0].split(","), expected, eps=1e-12)
    assert rows["special_bias"][1] == "2"


def test_rust_cut_inside_goal_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_cut_inside_to_shoot_goal

    config = EngineConfig()
    player_pos = (76.0, 52.0)
    carry_components = {
        "future_shot_gain": 0.09,
        "carry_to_shoot_window": 0.16,
        "wide_second_line_carry_window": 0.04,
    }
    shot_components = {"xg": 0.035, "shot_readiness": 0.18}
    carry_target = (82.0, 42.0)
    py_goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=player_pos,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        best_carry_components=carry_components,
        best_shot_components=shot_components,
        best_carry_target=carry_target,
        consecutive_carries=2,
        goal_age_ticks=1,
        created_tick=None,
        tick=44,
    )
    rows = _run_rust_rows("cut_inside_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(carry_target[0]),
            str(carry_target[1]),
            str(carry_components["future_shot_gain"]),
            str(carry_components["carry_to_shoot_window"]),
            str(carry_components["wide_second_line_carry_window"]),
            str(shot_components["xg"]),
            str(shot_components["shot_readiness"]),
            "2",
            "1",
            "cut_inside",
        ])
    ])
    rust = rows["cut_inside"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    phase_by_code = {"0": "drive", "1": "release", "2": "finish"}
    assert phase_by_code[rust[5]] == py_goal.context["phase"]
    assert abs(float(rust[6]) - py_goal.context["progress"]) < 1e-12
    assert abs(float(rust[7]) - py_goal.context["width"]) < 1e-12
    assert abs(float(rust[8]) - py_goal.context["finish_window"]) < 1e-12
    assert abs(float(rust[9]) - py_goal.context["drive_staleness"]) < 1e-12


def test_rust_byline_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_byline_delivery_goal, evaluate_drive_byline_goal

    config = EngineConfig()
    player_pos = (84.0, 52.0)
    carry_target = (94.0, 55.0)
    carry_components = {
        "progress_gain": 0.09,
        "byline_carry_window": 0.18,
        "path_feasibility": 0.72,
        "space_manipulation": 0.08,
    }
    py_drive = evaluate_drive_byline_goal(
        player_pos=player_pos,
        carry_target=carry_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        carry_score=0.16,
        components=carry_components,
        delivery_support=0.42,
        tick=13,
    )
    drive_rows = _run_rust_rows("drive_byline_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(carry_target[0]),
            str(carry_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.16",
            str(carry_components["progress_gain"]),
            str(carry_components["byline_carry_window"]),
            str(carry_components["path_feasibility"]),
            str(carry_components["space_manipulation"]),
            "0.42",
            "drive_byline",
        ])
    ])
    rust_drive = drive_rows["drive_byline"]
    assert rust_drive[0] == "1"
    _assert_close_tuple(rust_drive[1:3], py_drive.target_pos, eps=1e-12)
    assert abs(float(rust_drive[3]) - py_drive.value) < 1e-12
    assert abs(float(rust_drive[4]) - py_drive.confidence) < 1e-12
    assert rust_drive[5] == "0"
    assert abs(float(rust_drive[6]) - py_drive.context["origin_progress"]) < 1e-12
    assert abs(float(rust_drive[7]) - py_drive.context["origin_width"]) < 1e-12
    assert abs(float(rust_drive[8]) - py_drive.context["target_progress"]) < 1e-12
    assert abs(float(rust_drive[9]) - py_drive.context["target_width"]) < 1e-12

    delivery_target = (99.0, 35.0)
    pass_components = {
        "target_progress": 0.94,
        "centrality": 0.88,
        "high_threat_space": 0.55,
        "final_third_combination": 0.42,
        "success_prob": 0.48,
        "receiver_pressure": 0.18,
        "lane_risk": 0.10,
    }
    py_delivery = evaluate_byline_delivery_goal(
        player_pos=player_pos,
        delivery_target=delivery_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        pass_score=0.14,
        components=pass_components,
        tick=13,
    )
    delivery_rows = _run_rust_rows("byline_delivery_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(delivery_target[0]),
            str(delivery_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.14",
            str(pass_components["target_progress"]),
            str(pass_components["centrality"]),
            str(pass_components["high_threat_space"]),
            str(pass_components["final_third_combination"]),
            str(pass_components["success_prob"]),
            str(pass_components["receiver_pressure"]),
            str(pass_components["lane_risk"]),
            "byline_delivery",
        ])
    ])
    rust_delivery = delivery_rows["byline_delivery"]
    assert rust_delivery[0] == "1"
    _assert_close_tuple(rust_delivery[1:3], py_delivery.target_pos, eps=1e-12)
    assert abs(float(rust_delivery[3]) - py_delivery.value) < 1e-12
    assert abs(float(rust_delivery[4]) - py_delivery.confidence) < 1e-12
    assert rust_delivery[5] == "1"
    assert abs(float(rust_delivery[6]) - py_delivery.context["origin_progress"]) < 1e-12
    assert abs(float(rust_delivery[7]) - py_delivery.context["origin_width"]) < 1e-12
    assert abs(float(rust_delivery[8]) - py_delivery.context["target_progress"]) < 1e-12
    assert abs(float(rust_delivery[9]) - py_delivery.context["centrality"]) < 1e-12


def test_rust_byline_carry_selection_matches_python_formula():
    config = EngineConfig()
    player = _vision_player(8, 84.0, 52.0)
    teammates = [
        player,
        _vision_player(9, 92.0, 34.0),
        _vision_player(7, 88.0, 42.0),
    ]
    teammates[1].target_pos = (94.0, 35.0)
    teammates[1].tactical_anchor = (93.0, 34.0)
    teammates[2].target_pos = (90.0, 42.0)
    teammates[2].tactical_anchor = (88.0, 42.0)
    carry_candidates = [
        (0.14, "carry", {"target": (94.0, 55.0), "components": {"byline_carry_window": 0.16}}),
        (0.18, "carry", {"target": (90.0, 45.0), "components": {"byline_carry_window": 0.04}}),
    ]

    carrier_progress = player.pos[0] / config.pitch_length
    carrier_width = abs(player.pos[1] - config.pitch_width / 2.0) / max(1.0, config.pitch_width / 2.0)
    support = 0.0
    if carrier_progress >= 0.58 and carrier_width >= 0.38:
        for teammate in teammates:
            if teammate.index == player.index or teammate.is_goalkeeper:
                continue
            for point in (teammate.pos, teammate.target_pos, teammate.tactical_anchor):
                progress = point[0] / max(1.0, config.pitch_length)
                centrality = 1.0 - min(1.0, abs(point[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
                depth_gap = point[0] - player.pos[0]
                weak_side = 1.0 if (point[1] - config.pitch_width / 2.0) * (player.pos[1] - config.pitch_width / 2.0) < 0.0 else 0.0
                box_target = (
                    _test_smoothstep(0.78, 0.94, progress)
                    * _test_smoothstep(0.45, 0.92, centrality)
                    * (0.60 + 0.25 * weak_side)
                )
                cutback_target = (
                    _test_smoothstep(0.62, 0.84, progress)
                    * _test_smoothstep(0.52, 0.92, centrality)
                    * _test_smoothstep(-12.0, 6.0, depth_gap)
                    * (1.0 - _test_smoothstep(18.0, 34.0, abs(depth_gap)))
                )
                support = max(support, box_target, cutback_target)
    support = max(0.0, min(1.0, support))
    expected = None
    for idx, (score, _action, details) in enumerate(carry_candidates):
        byline = details["components"]["byline_carry_window"]
        if byline <= 0.025:
            continue
        value = score * 0.35 + byline * (0.45 + 0.70 * support)
        if expected is None or value > expected[1]:
            expected = (idx, value, score, details["target"])

    teammate_payload = ";".join(
        ",".join([
            str(t.index),
            str(t.pos[0]),
            str(t.pos[1]),
            str(t.target_pos[0]),
            str(t.target_pos[1]),
            str(t.tactical_anchor[0]),
            str(t.tactical_anchor[1]),
            "1" if t.is_goalkeeper else "0",
        ])
        for t in teammates
    )
    carry_payload = ";".join(
        ",".join([
            str(score),
            str(details["target"][0]),
            str(details["target"][1]),
            str(details["components"]["byline_carry_window"]),
        ])
        for score, _action, details in carry_candidates
    )
    rows = _run_rust_rows("byline_carry_select", [
        "\t".join([
            str(player.index),
            "0.0",
            "1",
            str(player.pos[0]),
            str(player.pos[1]),
            teammate_payload,
            carry_payload,
            str(config.pitch_length),
            str(config.pitch_width),
        ])
    ])
    rust = rows["byline_carry"]
    assert abs(float(rust[0]) - support) < 1e-12
    assert int(rust[1]) == expected[0]
    assert abs(float(rust[2]) - expected[1]) < 1e-12
    assert abs(float(rust[3]) - expected[2]) < 1e-12
    _assert_close_tuple(rust[4:6], expected[3], eps=1e-12)


def test_rust_through_ball_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_through_ball_goal

    config = EngineConfig()
    player_pos = (68.0, 34.0)
    pass_target = (88.0, 33.0)
    components = {
        "target_kind": "space",
        "target_progress": 0.84,
        "centrality": 0.92,
        "progress_gain": 0.18,
        "high_threat_space": 0.50,
        "success_prob": 0.52,
        "receiver_pressure": 0.16,
        "lane_risk": 0.10,
    }
    py_goal = evaluate_through_ball_goal(
        player_pos=player_pos,
        pass_target=pass_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        pass_score=0.15,
        components=components,
        tick=18,
    )
    rows = _run_rust_rows("through_ball_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(pass_target[0]),
            str(pass_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.15",
            "1",
            str(components["target_progress"]),
            str(components["centrality"]),
            str(components["progress_gain"]),
            str(components["high_threat_space"]),
            str(components["success_prob"]),
            str(components["receiver_pressure"]),
            str(components["lane_risk"]),
        ])
    ])
    rust = rows["through_ball"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    assert abs(float(rust[5]) - py_goal.context["origin_progress"]) < 1e-12


def test_rust_wide_overlap_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_wide_hold_for_overlap_goal

    config = EngineConfig()
    player_pos = (76.0, 50.0)
    overlap_target = (84.0, 55.0)
    py_goal = evaluate_wide_hold_for_overlap_goal(
        player_pos=player_pos,
        overlap_target=overlap_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        overlap_value=0.22,
        immediate_best_score=0.08,
        tick=21,
    )
    rows = _run_rust_rows("wide_overlap_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(overlap_target[0]),
            str(overlap_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.22",
            "0.08",
            "0.0",
            "wide_overlap",
        ])
    ])
    rust = rows["wide_overlap"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    assert abs(float(rust[5]) - py_goal.context["progress"]) < 1e-12
    assert abs(float(rust[6]) - py_goal.context["width"]) < 1e-12
    assert abs(float(rust[7]) - py_goal.context["target_progress"]) < 1e-12
    assert abs(float(rust[8]) - py_goal.context["target_width"]) < 1e-12
    assert abs(float(rust[9]) - py_goal.context["forward_gap"]) < 1e-12
    assert abs(float(rust[10]) - py_goal.context["same_lane"]) < 1e-12


def test_rust_overlap_selection_matches_python_formula():
    config = EngineConfig()
    player = _vision_player(1, 72.0, 48.0)
    pass_candidates = [
        (0.16, "pass", {"target": (84.0, 54.0), "components": {"receiver_pressure": 0.20}}),
        (0.12, "pass", {"target": (80.0, 40.0), "components": {"receiver_pressure": 0.05}}),
        (0.05, "carry", {"target": (78.0, 44.0), "components": {}}),
    ]
    expected = None
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        target = details["target"]
        target_progress = target[0] / config.pitch_length
        target_width = abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        carrier_width = abs(player.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        forward_gap = target[0] - player.pos[0]
        overlap_value = (
            max(0.0, score)
            * max(0.0, min(1.0, forward_gap / 14.0))
            * max(0.0, min(1.0, (target_width - carrier_width + 0.25) / 0.45))
            * (1.0 - min(1.0, details["components"]["receiver_pressure"]))
            * max(0.0, min(1.0, (target_progress - 0.62) / 0.22))
        )
        if expected is None or overlap_value > expected[0]:
            expected = (overlap_value, target)
    rows = _run_rust_rows("overlap_select", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            ";".join(
                ",".join([
                    str(score),
                    str(details["target"][0]),
                    str(details["target"][1]),
                    str(details["components"].get("receiver_pressure", 0.0)),
                ])
                for score, action_type, details in pass_candidates
                if action_type == "pass"
            ),
            "overlap_select",
        ])
    ])
    rust = rows["overlap_select"]
    assert abs(float(rust[1]) - expected[0]) < 1e-12
    _assert_close_tuple(rust[2:4], expected[1], eps=1e-12)


def test_rust_layoff_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_release_pressure_with_layoff_goal

    config = EngineConfig()
    player_pos = (82.0, 46.0)
    layoff_target = (72.0, 36.0)
    py_goal = evaluate_release_pressure_with_layoff_goal(
        player_pos=player_pos,
        layoff_target=layoff_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        attracted_pressure=0.62,
        layoff_value=0.12,
        immediate_best_score=0.07,
        tick=23,
    )
    rows = _run_rust_rows("layoff_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(layoff_target[0]),
            str(layoff_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.62",
            "0.12",
            "0.07",
            "layoff",
        ])
    ])
    rust = rows["layoff"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    assert abs(float(rust[5]) - py_goal.context["progress"]) < 1e-12
    assert abs(float(rust[6]) - py_goal.context["target_progress"]) < 1e-12
    assert abs(float(rust[7]) - py_goal.context["target_centrality"]) < 1e-12
    assert abs(float(rust[8]) - py_goal.context["pass_distance"]) < 1e-12
    assert abs(float(rust[9]) - py_goal.context["backward_depth"]) < 1e-12


def test_rust_layoff_selection_matches_python_formula():
    config = EngineConfig()
    player = _vision_player(1, 82.0, 46.0)
    opponents = [_opponent(20, 78.0, 44.0), _opponent(21, 90.0, 50.0)]
    pass_candidates = [
        (0.15, "pass", {"target": (72.0, 36.0), "components": {"receiver_pressure": 0.12}}),
        (0.12, "pass", {"target": (84.0, 34.0), "components": {"receiver_pressure": 0.05}}),
    ]
    attracted_pressure = 0.0
    for opp in opponents:
        d = py_physics.distance(player.pos, opp.pos)
        if d < 11.0:
            attracted_pressure += 1.0 - d / 11.0
    attracted_pressure = min(1.0, attracted_pressure * 0.42)
    expected = None
    for score, _action, details in pass_candidates:
        target = details["target"]
        pass_distance = py_physics.distance(player.pos, target)
        target_progress = target[0] / config.pitch_length
        target_centrality = 1.0 - min(1.0, abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
        backward_depth = player.pos[0] - target[0]
        layoff_value = (
            max(0.0, score)
            * max(0.0, min(1.0, (18.0 - abs(pass_distance - 12.0)) / 18.0))
            * max(0.0, min(1.0, (target_centrality - 0.20) / 0.65))
            * max(0.0, min(1.0, (0.28 - abs(target_progress - player.pos[0] / config.pitch_length)) / 0.28))
            * (1.0 - min(1.0, details["components"]["receiver_pressure"]))
            * max(0.0, min(1.0, (backward_depth + 4.0) / 16.0))
        )
        if expected is None or layoff_value > expected[0]:
            expected = (layoff_value, target)
    rows = _run_rust_rows("layoff_select", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            ";".join(
                ",".join([
                    str(score),
                    str(details["target"][0]),
                    str(details["target"][1]),
                    str(details["components"]["receiver_pressure"]),
                ])
                for score, _action, details in pass_candidates
            ),
            ";".join(f"{o.pos[0]},{o.pos[1]}" for o in opponents),
            "layoff_select",
        ])
    ])
    rust = rows["layoff_select"]
    assert abs(float(rust[1]) - expected[0]) < 1e-12
    _assert_close_tuple(rust[2:4], expected[1], eps=1e-12)
    assert abs(float(rust[4]) - attracted_pressure) < 1e-12


def test_rust_release_support_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_release_to_arriving_support_goal

    config = EngineConfig()
    player_pos = (82.0, 42.0)
    support_target = (76.0, 35.0)
    shot_components = {
        "xg": 0.035,
        "shot_readiness": 0.12,
        "open_medium_window": 0.08,
        "clean_second_line_shot": 0.06,
    }
    py_goal = evaluate_release_to_arriving_support_goal(
        player_pos=player_pos,
        support_target=support_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        support_value=0.14,
        receiver_goal_fit=0.58,
        shot_components=shot_components,
        consecutive_carries=2,
        attracted_pressure=0.44,
        tick=31,
    )
    shot_readiness = max(
        shot_components["shot_readiness"],
        shot_components["open_medium_window"],
        shot_components["clean_second_line_shot"],
    )
    rows = _run_rust_rows("release_support_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(support_target[0]),
            str(support_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.14",
            "0.58",
            str(shot_components["xg"]),
            str(shot_readiness),
            "2",
            "0.44",
            "release_support",
        ])
    ])
    rust = rows["release_support"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    assert abs(float(rust[5]) - py_goal.context["progress"]) < 1e-12
    assert abs(float(rust[6]) - py_goal.context["target_progress"]) < 1e-12
    assert abs(float(rust[7]) - py_goal.context["target_centrality"]) < 1e-12
    assert abs(float(rust[8]) - py_goal.context["pass_distance"]) < 1e-12
    assert abs(float(rust[9]) - py_goal.context["layer_gap"]) < 1e-12
    assert abs(float(rust[10]) - py_goal.context["release_maturity"]) < 1e-12


def test_rust_arriving_support_selection_matches_python_formula():
    player = _vision_player(1, 82.0, 42.0)
    opponents = [_opponent(20, 78.0, 44.0), _opponent(21, 90.0, 50.0)]
    pass_candidates = [
        (0.16, "pass", {"target": (76.0, 35.0), "components": {
            "receiver_goal_fit": 0.58,
            "second_line_arrival_value": 0.08,
            "second_line_cutback_value": 0.04,
            "layoff_support_value": 0.03,
        }}),
        (0.18, "pass", {"target": (88.0, 36.0), "components": {
            "receiver_goal_fit": 0.30,
            "second_line_arrival_value": 0.05,
            "second_line_cutback_value": 0.02,
            "layoff_support_value": 0.01,
        }}),
    ]
    expected = None
    for score, _action, details in pass_candidates:
        components = details["components"]
        support_value = max(
            components["second_line_arrival_value"],
            components["second_line_cutback_value"],
            components["layoff_support_value"],
            max(0.0, score) * 0.55,
        )
        fit = components["receiver_goal_fit"] * (support_value + max(0.0, score) * 0.35)
        if expected is None or fit > expected[0]:
            expected = (fit, details["target"], support_value, components["receiver_goal_fit"])
    attracted = 0.0
    for opp in opponents:
        d = py_physics.distance(player.pos, opp.pos)
        if d < 11.0:
            attracted += 1.0 - d / 11.0
    attracted = min(1.0, attracted * 0.42)
    rows = _run_rust_rows("arriving_support_select", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            ";".join(
                ",".join([
                    str(score),
                    str(details["target"][0]),
                    str(details["target"][1]),
                    str(details["components"]["receiver_goal_fit"]),
                    str(details["components"]["second_line_arrival_value"]),
                    str(details["components"]["second_line_cutback_value"]),
                    str(details["components"]["layoff_support_value"]),
                ])
                for score, _action, details in pass_candidates
            ),
            ";".join(f"{o.pos[0]},{o.pos[1]}" for o in opponents),
            "arriving_support",
        ])
    ])
    rust = rows["arriving_support"]
    assert abs(float(rust[1]) - expected[0]) < 1e-12
    _assert_close_tuple(rust[2:4], expected[1], eps=1e-12)
    assert abs(float(rust[4]) - expected[2]) < 1e-12
    assert abs(float(rust[5]) - expected[3]) < 1e-12
    assert abs(float(rust[6]) - attracted) < 1e-12


def test_rust_hold_support_selection_matches_python_formula():
    config = EngineConfig()
    player = _vision_player(1, 82.0, 42.0)
    pass_candidates = [
        (0.16, "pass", {"target": (76.0, 35.0), "components": {
            "layoff_support_value": 0.07,
            "short_combination_value": 0.04,
            "second_line_cutback_value": 0.03,
            "layoff_retention_value": 0.02,
            "receiver_goal_fit": 0.50,
            "second_line_arrival_value": 0.04,
        }}),
    ]
    carry_candidates = [(0.12, "carry", {"components": {
        "carry_to_shoot_window": 0.08,
        "wide_second_line_carry_window": 0.04,
        "future_shot_gain": 0.06,
    }})]
    hold_candidates = [(0.03, "hold", {"components": {
        "opportunity_wait": 0.10,
        "opportunity_wait_value": 0.08,
        "no_clear_release": 0.05,
    }})]
    score, _action, details = pass_candidates[0]
    target = details["target"]
    components = details["components"]
    support_value = max(
        components["layoff_support_value"],
        components["short_combination_value"],
        components["second_line_cutback_value"],
        components["layoff_retention_value"],
        max(0.0, score) * 0.45,
    )
    pass_distance = py_physics.distance(player.pos, target)
    target_progress = target[0] / config.pitch_length
    target_centrality = 1.0 - min(1.0, abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
    fit = (
        support_value
        * max(0.0, min(1.0, (18.0 - abs(pass_distance - 12.0)) / 18.0))
        * max(0.0, min(1.0, (target_centrality - 0.18) / 0.70))
        * max(0.0, min(1.0, (0.90 - target_progress) / 0.26))
    )
    clear_carry_plan = 0.08
    support_plan_quality = max(
        _test_smoothstep(0.28, 0.70, 0.50),
        _test_smoothstep(0.012, 0.080, 0.04),
    )
    carry_interrupt = _test_smoothstep(0.070, 0.185, clear_carry_plan) * (1.0 - 0.55 * support_plan_quality)
    rows = _run_rust_rows("hold_support_select", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.16,76.0,35.0,0.07,0.04,0.03,0.02,0.50",
            "0.08,0.04,0.06",
            "0.10,0.08,0.05",
            "0",
            "hold_support",
        ])
    ])
    rust = rows["hold_support"]
    assert rust[0] == ("1" if carry_interrupt < 0.72 else "0")
    _assert_close_tuple(rust[1:3], target, eps=1e-12)
    assert abs(float(rust[3]) - fit) < 1e-12
    assert abs(float(rust[4]) - support_value) < 1e-12
    assert abs(float(rust[5]) - 0.10) < 1e-12
    assert abs(float(rust[6]) - 0.05) < 1e-12
    assert abs(float(rust[7]) - clear_carry_plan) < 1e-12
    assert abs(float(rust[8]) - support_plan_quality) < 1e-12
    assert abs(float(rust[9]) - carry_interrupt) < 1e-12


def test_rust_hold_opportunity_goal_generation_matches_python_formula():
    from psl_core.engine_v2.goal import evaluate_hold_for_opportunity_goal

    config = EngineConfig()
    player_pos = (74.0, 44.0)
    support_target = (66.0, 36.0)
    shot_components = {
        "xg": 0.03,
        "shot_readiness": 0.10,
        "open_medium_window": 0.05,
        "clean_second_line_shot": 0.04,
    }
    py_goal = evaluate_hold_for_opportunity_goal(
        player_pos=player_pos,
        support_target=support_target,
        attacking_right=True,
        pitch_length=config.pitch_length,
        pitch_width=config.pitch_width,
        support_value=0.13,
        hold_value=0.09,
        shot_components=shot_components,
        immediate_best_score=0.06,
        goal_age_ticks=2,
        tick=28,
    )
    shot_readiness = max(
        shot_components["shot_readiness"],
        shot_components["open_medium_window"],
        shot_components["clean_second_line_shot"],
    )
    rows = _run_rust_rows("hold_opportunity_goal", [
        "\t".join([
            str(player_pos[0]),
            str(player_pos[1]),
            str(support_target[0]),
            str(support_target[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.13",
            "0.09",
            str(shot_components["xg"]),
            str(shot_readiness),
            "0.06",
            "2",
            "hold_opportunity",
        ])
    ])
    rust = rows["hold_opportunity"]
    assert rust[0] == "1"
    _assert_close_tuple(rust[1:3], py_goal.target_pos, eps=1e-12)
    assert abs(float(rust[3]) - py_goal.value) < 1e-12
    assert abs(float(rust[4]) - py_goal.confidence) < 1e-12
    assert abs(float(rust[5]) - py_goal.context["progress"]) < 1e-12
    assert abs(float(rust[6]) - py_goal.context["target_progress"]) < 1e-12
    assert abs(float(rust[7]) - py_goal.context["target_centrality"]) < 1e-12
    assert abs(float(rust[8]) - py_goal.context["pass_distance"]) < 1e-12
    assert abs(float(rust[9]) - py_goal.context["lateral_gap"]) < 1e-12
    assert abs(float(rust[10]) - py_goal.context["opportunity_window"]) < 1e-12


def test_rust_support_opportunity_cost_matches_python_formula():
    player = _vision_player(1, 58.0, 34.0)
    config = EngineConfig()
    carry_candidates = [
        (
            0.16,
            "carry",
            {
                "components": {
                    "future_shot_gain": 0.08,
                    "carry_to_shoot_window": 0.18,
                    "effective_gain": 0.12,
                }
            },
        ),
        (
            0.09,
            "carry",
            {
                "components": {
                    "future_shot_gain": 0.01,
                    "carry_to_shoot_window": 0.02,
                    "effective_gain": 0.03,
                }
            },
        ),
    ]
    pass_candidates = [
        (
            0.19,
            "pass",
            {
                "components": {
                    "receiver_goal_fit": 0.62,
                    "second_line_arrival_value": 0.025,
                    "second_line_cutback_value": 0.010,
                    "layoff_support_value": 0.030,
                }
            },
        )
    ]
    py = player._apply_support_opportunity_cost(
        carry_candidates,
        pass_candidates,
        Pitch(config=config),
        True,
        config=None,
    )
    rows = _run_rust_rows("support_opportunity_cost", [
        "\t".join([
            ";".join(
                ",".join([
                    str(score),
                    str(details["components"].get("receiver_goal_fit", 0.0)),
                    str(details["components"].get("second_line_arrival_value", 0.0)),
                    str(details["components"].get("second_line_cutback_value", 0.0)),
                    str(details["components"].get("layoff_support_value", 0.0)),
                ])
                for score, _action, details in pass_candidates
            ),
            ";".join(
                ",".join([
                    str(score),
                    str(details["components"].get("future_shot_gain", 0.0)),
                    str(details["components"].get("carry_to_shoot_window", 0.0)),
                    str(details["components"].get("effective_gain", 0.0)),
                ])
                for score, _action, details in carry_candidates
            ),
            "0.0",
            "support_cost",
        ])
    ])
    _assert_close_tuple(rows["support_cost"][1].split(","), [item[0] for item in py], eps=1e-12)
    for rust_cost, py_item in zip(rows["support_cost"][2].split(","), py):
        assert abs(float(rust_cost) - py_item[2]["components"]["support_opportunity_cost"]) < 1e-12


def test_rust_softmax_temperature_adapter_matches_formula():
    scores = [0.21, 0.18, 0.16, 0.05]
    temperature = 0.017
    roll = 0.61
    import math

    max_score = max(scores)
    weights = [math.exp((score - max_score) / temperature) for score in scores]
    threshold = roll * sum(weights)
    cumulative = 0.0
    expected = len(scores) - 1
    for idx, weight in enumerate(weights):
        cumulative += weight
        if threshold <= cumulative:
            expected = idx
            break

    assert softmax_select_index_with_temperature_rust(scores, temperature, roll) == expected


def test_rust_defensive_position_value_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "protect_lane",
            (88.0, 34.0),
            (76.0, 34.0),
            105.0,
            [(80.0, 30.0), (84.0, 42.0)],
            [(90.0, 30.0), (92.0, 38.0)],
            (88.0, 34.0),
        ),
        (
            "crowded_wide",
            (90.0, 48.0),
            (82.0, 44.0),
            105.0,
            [(86.0, 46.0)],
            [(90.0, 45.0), (92.0, 49.0), (88.0, 52.0)],
            (84.0, 50.0),
        ),
        (
            "left_defense",
            (18.0, 34.0),
            (34.0, 38.0),
            0.0,
            [(30.0, 42.0), (28.0, 30.0)],
            [(20.0, 30.0)],
            (18.0, 34.0),
        ),
    ]
    rust_values = _run_rust_mode("defensive_position", [
        _defensive_position_case_line(*case)
        for case in cases
    ])
    for case_id, pos, ball_pos, own_goal_x, attackers, teammates, formation_pos in cases:
        py_value = defensive_position_value(
            pos,
            ball_pos,
            own_goal_x,
            pitch,
            attackers,
            teammates,
            formation_pos,
        )
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_receive_reachability_and_space_creation_match_python():
    config = EngineConfig()
    reach_cases = [
        ("runner_first", (72.0, 34.0), (68.0, 34.0), 5.2, [(78.0, 34.0)], [4.1], (60.0, 34.0), 15.0),
        ("defender_first", (72.0, 34.0), (60.0, 34.0), 3.5, [(70.0, 34.0), (76.0, 40.0)], [5.1, 4.2], (50.0, 34.0), 15.0),
        ("fallback_speed", (80.0, 20.0), (72.0, 30.0), 4.0, [(78.0, 22.0), (90.0, 50.0)], [3.5], (65.0, 34.0), 12.0),
    ]
    reach_lines = [
        "\t".join([
            str(target[0]),
            str(target[1]),
            str(runner[0]),
            str(runner[1]),
            str(runner_speed),
            str(ball[0]),
            str(ball[1]),
            _positions_payload(opponents),
            ",".join(str(speed) for speed in opponent_speeds),
            str(ball_speed),
            str(config.receive_reachability_scale),
            case_id,
        ])
        for case_id, target, runner, runner_speed, opponents, opponent_speeds, ball, ball_speed in reach_cases
    ]
    reach_values = _run_rust_mode("receive_reachability", reach_lines)
    for case_id, target, runner, runner_speed, opponents, opponent_speeds, ball, ball_speed in reach_cases:
        py_value = receive_reachability(
            target,
            runner,
            runner_speed,
            opponents,
            opponent_speeds,
            ball,
            ball_speed,
            config,
        )
        assert abs(reach_values[case_id] - py_value) < 1e-12

    space_cases = [
        ("none", (70.0, 34.0), []),
        ("one", (70.0, 34.0), [(72.0, 34.0), (90.0, 50.0)]),
        ("cap", (70.0, 34.0), [(70.0, 34.0), (72.0, 34.0), (74.0, 35.0), (76.0, 36.0)]),
    ]
    space_values = _run_rust_mode("space_creation", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            _positions_payload(opponents),
            str(config.space_creation_radius),
            case_id,
        ])
        for case_id, target, opponents in space_cases
    ])
    for case_id, target, opponents in space_cases:
        py_value = space_creation_value(target, opponents, [], config)
        assert abs(space_values[case_id] - py_value) < 1e-12


def _score_off_ball_attack_candidates_python(
    player,
    ball_pos,
    candidates,
    teammates,
    opponents,
    config,
    pitch,
    attacking_right,
):
    import math

    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != player.index]
    opp_speeds = [
        py_physics.player_speed(o.speed_value, config.player_max_speed, config.player_min_speed)
        for o in opponents if not o.is_goalkeeper
    ]
    anchor = player.tactical_anchor
    forward_dir = 1.0 if attacking_right else -1.0
    role_progress = anchor[0] / config.pitch_length if attacking_right else (config.pitch_length - anchor[0]) / config.pitch_length
    role_progress = max(0.0, min(1.0, role_progress))
    width_signed = (anchor[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
    width_factor = min(1.0, abs(width_signed))
    max_speed = py_physics.player_speed(player.speed_value, config.player_max_speed, config.player_min_speed)
    offside_line = player._get_offside_line(opponents, attacking_right, config)
    results = []
    for raw_x, raw_y, anchor_x, anchor_y in candidates:
        pos = pitch.clamp(raw_x, raw_y)
        anchor_pos = (anchor_x, anchor_y)
        pv = position_value(pos[0], pos[1], pitch, attacking_right, opp_positions, tm_positions, config, runner_formation_pos=anchor_pos)
        move_dist = py_physics.distance(pos, player.pos)
        candidate_progress = pos[0] / config.pitch_length if attacking_right else (config.pitch_length - pos[0]) / config.pitch_length
        carrier_progress_hint = ball_pos[0] / config.pitch_length if attacking_right else (config.pitch_length - ball_pos[0]) / config.pitch_length
        final_third_support_window = (
            max(0.0, min(1.0, (carrier_progress_hint - 0.68) / 0.22))
            * max(0.0, min(1.0, (candidate_progress - 0.66) / 0.18))
        )
        movement_window = max_speed * (4.0 + 3.0 * role_progress + 4.6 * final_third_support_window)
        movement_reach = 1.0 / (1.0 + (move_dist / max(1.0, movement_window)) ** 1.45)
        immediate_reach = receive_reachability(
            pos, player.pos, max_speed, opp_positions, opp_speeds,
            ball_pos, config.pass_to_space_ball_speed, config,
        )
        reach = 0.35 + 0.45 * movement_reach + 0.20 * immediate_reach
        pass_feasibility = 1.0
        dx = pos[0] - ball_pos[0]
        dy = pos[1] - ball_pos[1]
        path_len = math.sqrt(dx * dx + dy * dy)
        if path_len > 1.0:
            nx, ny = dx / path_len, dy / path_len
            for opp in opponents:
                if opp.is_goalkeeper:
                    continue
                px = opp.pos[0] - ball_pos[0]
                py = opp.pos[1] - ball_pos[1]
                proj = px * nx + py * ny
                if 2.0 < proj < path_len - 2.0:
                    perp = abs(px * ny - py * nx)
                    if perp < 4.0:
                        pass_feasibility *= 0.5
        dist_to_ball = py_physics.distance(pos, ball_pos)
        if dist_to_ball > 25.0:
            pass_feasibility *= max(0.1, 1.0 - (dist_to_ball - 25.0) / 35.0)
        space_bonus = space_creation_value(pos, opp_positions, tm_positions, config)
        role_dist = py_physics.distance(pos, anchor)
        role_limit = 14.0 + 22.0 * role_progress
        role_t = min(1.0, role_dist / max(1.0, role_limit * 1.8))
        role_shape_factor = 0.22 + 0.78 * (1.0 - role_t * role_t * (3.0 - 2.0 * role_t))
        inside_support = 0.0
        if width_factor > 0.35:
            anchor_width = abs(anchor[1] - config.pitch_width / 2.0)
            pos_width = abs(pos[1] - config.pitch_width / 2.0)
            inside_support = (
                max(0.0, min(1.0, (carrier_progress_hint - 0.68) / 0.22))
                * max(0.0, min(1.0, (candidate_progress - 0.66) / 0.18))
                * max(0.0, min(1.0, (anchor_width - pos_width) / max(1.0, anchor_width)))
            )
            role_shape_factor = max(role_shape_factor, 0.48 + 0.28 * inside_support)
        ahead_of_ball = (pos[0] - ball_pos[0]) * forward_dir
        ahead_t = max(0.0, min(1.0, ahead_of_ball / 18.0))
        support_run_factor = ahead_t * ahead_t * (3.0 - 2.0 * ahead_t)
        carrier_progress = ball_pos[0] / config.pitch_length if attacking_right else (config.pitch_length - ball_pos[0]) / config.pitch_length
        support_angle_dist = py_physics.distance(pos, ball_pos)
        support_angle_value = (
            max(0.0, min(1.0, (carrier_progress - 0.68) / 0.22))
            * (1.0 - min(1.0, abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)) * 0.35)
            * max(0.0, 1.0 - abs(support_angle_dist - 16.0) / 18.0)
        )
        cutback_depth = (ball_pos[0] - pos[0]) * forward_dir
        carrier_width = abs(ball_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        candidate_width = abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        second_line_support = (
            max(0.0, min(1.0, (carrier_progress - 0.66) / 0.20))
            * max(0.0, min(1.0, (candidate_progress - 0.60) / 0.14))
            * (1.0 - max(0.0, min(1.0, (candidate_progress - 0.82) / 0.10)))
            * max(0.0, min(1.0, (cutback_depth - 5.0) / 8.0))
            * (1.0 - max(0.0, min(1.0, (cutback_depth - 24.0) / 12.0)))
            * max(0.0, min(1.0, (carrier_width - candidate_width + 0.04) / 0.34))
            * (1.0 - candidate_width * 0.35)
        )
        layoff_window = (
            max(0.0, min(1.0, (carrier_progress - 0.70) / 0.18))
            * max(0.0, 1.0 - abs(support_angle_dist - 14.0) / 10.0)
            * (0.65 + 0.35 * (1.0 - min(1.0, abs(pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))))
        )
        if second_line_support > 0.0:
            role_shape_factor = max(role_shape_factor, 0.58 + 0.24 * second_line_support)
        arrival_goal_fit = 0.0
        arrival_goal_multiplier = 1.0
        arrival_goal_bonus = 0.0
        if player.current_goal and player.current_goal.goal_type in ("arc_arrival_for_cutback", "attack_far_post"):
            arrival_goal_fit = max(
                0.0,
                1.0 - py_physics.distance(pos, player.current_goal.target_pos) / (
                    11.0 if player.current_goal.goal_type == "arc_arrival_for_cutback" else 15.0
                ),
            )
            if arrival_goal_fit > 0.0:
                arrival_strength = max(0.0, min(1.0, float(player.current_goal.value or 0.0) * 2.5))
                arrival_goal_multiplier += arrival_goal_fit * arrival_strength * (
                    5.0 if player.current_goal.goal_type == "attack_far_post" else 1.25
                )
                arrival_goal_bonus = (
                    arrival_goal_fit
                    * max(0.0, float(player.current_goal.value or 0.0))
                    * (2.25 if player.current_goal.goal_type == "attack_far_post" else 0.55)
                )
        role_overlap = 0.0
        for teammate in teammates:
            if teammate.index == player.index or teammate.is_goalkeeper:
                continue
            teammate_anchor = getattr(teammate, "tactical_anchor", teammate.pos)
            anchor_dist = py_physics.distance(pos, teammate_anchor)
            own_anchor_dist = py_physics.distance(pos, anchor)
            if anchor_dist < 12.0 and anchor_dist + 2.0 < own_anchor_dist:
                role_overlap += (1.0 - anchor_dist / 12.0) ** 1.15
            current_dist = py_physics.distance(pos, teammate.pos)
            if current_dist < 8.0:
                role_overlap += 0.45 * (1.0 - current_dist / 8.0)
        role_overlap_factor = 1.0 / (1.0 + role_overlap * 0.72)
        target_width_signed = (pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0)
        cross_lane = max(0.0, -width_signed * target_width_signed)
        lane_factor = max(0.12, 1.0 - 0.88 * width_factor * cross_lane)
        offside_penalty = 1.0
        if player._is_offside_position(pos, attacking_right, offside_line, config, ball_x=ball_pos[0]):
            offside_penalty = 0.08
        else:
            if attacking_right and pos[0] > offside_line - 3.0:
                offside_penalty *= 0.45
            elif (not attacking_right) and pos[0] < offside_line + 3.0:
                offside_penalty *= 0.45
        score = (
            pv * reach * pass_feasibility * space_bonus * offside_penalty
            * role_shape_factor * lane_factor * role_overlap_factor
            * arrival_goal_multiplier
            * (
                1.0
                + 0.18 * role_progress * support_run_factor
                + 0.82 * support_angle_value
                + 1.35 * layoff_window
                + 0.70 * inside_support
                + 1.45 * second_line_support
            )
        ) + arrival_goal_bonus
        results.append((
            score, pos[0], pos[1], pv, reach, movement_reach, immediate_reach,
            pass_feasibility, space_bonus, role_shape_factor, role_overlap_factor,
            role_overlap, lane_factor, offside_penalty, support_angle_value,
            inside_support, second_line_support, arrival_goal_fit,
            arrival_goal_multiplier, arrival_goal_bonus, layoff_window,
            candidate_progress, candidate_width, support_angle_dist, dist_to_ball,
        ))
    return results


def _off_ball_attack_raw_candidates_python(anchor, ball_pos, attacking_right, pitch_length, pitch_width, is_defender, has_ball_carrier, anchor_samples, support_samples):
    import math

    forward_dir = 1.0 if attacking_right else -1.0
    role_progress = anchor[0] / pitch_length if attacking_right else (pitch_length - anchor[0]) / pitch_length
    role_progress = max(0.0, min(1.0, role_progress))
    width_signed = (anchor[1] - pitch_width / 2.0) / (pitch_width / 2.0)
    width_factor = min(1.0, abs(width_signed))
    search_radius = 10.0 + 16.0 * role_progress
    raw_candidates = [(anchor[0], anchor[1], anchor[0], anchor[1])]
    anchor_progress = (anchor[0] - ball_pos[0]) * forward_dir
    if anchor_progress > 0.0:
        raw_candidates.append((
            anchor[0] + forward_dir * min(10.0, anchor_progress * 0.45),
            anchor[1],
            anchor[0],
            anchor[1],
        ))
    for angle_unit, radius_unit in anchor_samples:
        angle = angle_unit * math.tau
        radius = radius_unit ** 0.65 * search_radius
        raw_candidates.append((
            anchor[0] + math.cos(angle) * radius,
            anchor[1] + math.sin(angle) * radius,
            anchor[0],
            anchor[1],
        ))
    if not has_ball_carrier:
        return raw_candidates

    support_pull = _test_smoothstep(0.38, 0.64, role_progress)
    support_depth = (role_progress - 0.46) * 34.0
    ball_support_x = ball_pos[0] + forward_dir * support_depth
    ball_support_y = ball_pos[1] * (1.0 - 0.30 * width_factor) + anchor[1] * (0.30 * width_factor)
    support_center = (
        anchor[0] * (1.0 - support_pull) + ball_support_x * support_pull,
        anchor[1] * (1.0 - support_pull) + ball_support_y * support_pull,
    )
    for angle_unit, radius_unit in support_samples:
        angle = angle_unit * math.tau
        radius = radius_unit ** 0.7 * (7.0 + 15.0 * role_progress)
        raw_candidates.append((
            support_center[0] + math.cos(angle) * radius,
            support_center[1] + math.sin(angle) * radius,
            anchor[0] * 0.35 + support_center[0] * 0.65,
            anchor[1] * 0.50 + support_center[1] * 0.50,
        ))
    ball_progress = ball_pos[0] / pitch_length if attacking_right else (pitch_length - ball_pos[0]) / pitch_length
    if ball_progress > 0.68 and not is_defender:
        side_sign = 1.0 if anchor[1] >= pitch_width / 2.0 else -1.0
        weak_side = max(0.0, min(1.0, -width_signed * ((ball_pos[1] - pitch_width / 2.0) / (pitch_width / 2.0))))
        support_centers = (
            (support_center[0] * 0.55 + ball_pos[0] * 0.45, support_center[1] * 0.55 + ball_pos[1] * 0.45),
            (anchor[0] * 0.35 + ball_pos[0] * 0.65, anchor[1] * 0.45 + ball_pos[1] * 0.55),
        )
        angle_bias = math.atan2(pitch_width / 2.0 - ball_pos[1], 10.0)
        support_angles = (
            angle_bias - 1.65,
            angle_bias - 0.95,
            angle_bias - 0.35,
            angle_bias,
            angle_bias + 0.35,
            angle_bias + 0.95,
            angle_bias + 1.65,
        )
        support_radii = (
            6.0,
            10.0 + 3.0 * _test_smoothstep(0.72, 0.88, ball_progress),
            15.0 + 5.0 * _test_smoothstep(0.70, 0.90, ball_progress),
        )
        for center_x, center_y in support_centers:
            for radius in support_radii:
                for angle in support_angles:
                    sx = center_x - forward_dir * math.cos(angle) * radius
                    sy = center_y + math.sin(angle) * radius
                    raw_candidates.append((sx, sy, sx, sy))
        if width_factor > 0.38 and role_progress > 0.58:
            arrival_t = max(0.0, min(1.0, (ball_progress - 0.68) / 0.20))
            arrival_depth = 6.0 + 7.0 * arrival_t
            center_lane = pitch_width / 2.0
            half_space = center_lane + side_sign * pitch_width * (0.06 + 0.06 * (1.0 - weak_side))
            central_arrival_x = ball_pos[0] - forward_dir * arrival_depth
            for sy in (half_space, center_lane):
                raw_candidates.append((central_arrival_x, sy, central_arrival_x, sy))
            if weak_side > 0.18:
                far_post_x = ball_pos[0] + forward_dir * (2.0 + 4.0 * arrival_t)
                far_post_y = center_lane + side_sign * pitch_width * 0.08
                raw_candidates.append((far_post_x, far_post_y, far_post_x, far_post_y))
    return raw_candidates


def test_rust_off_ball_attack_raw_generation_matches_python_formula():
    anchor = (76.0, 52.0)
    ball_pos = (82.0, 56.0)
    anchor_samples = [(0.1, 0.2), (0.4, 0.7), (0.9, 0.5)]
    support_samples = [(0.2, 0.3), (0.7, 0.8)]
    expected = _off_ball_attack_raw_candidates_python(
        anchor,
        ball_pos,
        True,
        105.0,
        68.0,
        False,
        True,
        anchor_samples,
        support_samples,
    )
    line = "\t".join([
        str(anchor[0]),
        str(anchor[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1",
        "105.0",
        "68.0",
        "0",
        "1",
        ";".join(f"{a},{r}" for a, r in anchor_samples),
        ";".join(f"{a},{r}" for a, r in support_samples),
        "raw",
    ])
    rows = _run_rust_rows("off_ball_attack_raw", [line])
    actual = [tuple(float(part) for part in item.split(",")) for item in rows["raw"][0].split(";")]
    assert len(actual) == len(expected)
    for rust_item, py_item in zip(actual, expected):
        _assert_close_tuple([str(value) for value in rust_item], py_item, eps=1e-10)


def test_rust_off_ball_attack_score_batch_matches_python_formula():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None):
        p = _vision_player(idx, x, y, iq=84)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        return p

    runner = player(6, "CM", 72.0, 42.0, target=(78.0, 38.0), anchor=(76.0, 40.0))
    runner.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(78.0, 34.0),
        value=0.08,
    )
    holder = player(8, "RW", 82.0, 56.0)
    teammates = [runner, holder, player(9, "ST", 90.0, 34.0, target=(92.0, 34.0), anchor=(90.0, 34.0))]
    opponents = [player(2, "CB", 90.0, 30.0), player(3, "CB", 91.0, 39.0)]
    raw_candidates = [
        (76.0, 40.0, 76.0, 40.0),
        (82.0, 34.0, 80.0, 36.0),
        (74.0, 52.0, 76.0, 40.0),
    ]
    expected = _score_off_ball_attack_candidates_python(
        runner,
        holder.pos,
        raw_candidates,
        teammates,
        opponents,
        config,
        pitch,
        True,
    )
    opp_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    opp_speeds = [py_physics.player_speed(o.speed_value, config.player_max_speed, config.player_min_speed) for o in opponents if not o.is_goalkeeper]
    tm_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != runner.index]
    offside_line = runner._get_offside_line(opponents, True, config)
    goal = runner.current_goal
    line = "\t".join([
        str(runner.index),
        str(runner.pos[0]),
        str(runner.pos[1]),
        str(runner.speed_value),
        str(runner.tactical_anchor[0]),
        str(runner.tactical_anchor[1]),
        "1",
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(offside_line),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        _off_ball_candidates_payload(raw_candidates),
        _positions_payload(opp_positions),
        ",".join(str(speed) for speed in opp_speeds),
        _positions_payload(tm_positions),
        _off_ball_teammates_payload(teammates),
        goal.goal_type,
        str(goal.target_pos[0]),
        str(goal.target_pos[1]),
        str(goal.value),
        str(config.pass_to_space_ball_speed),
        str(config.receive_reachability_scale),
        str(config.space_creation_radius),
        "offball",
    ])
    rows = _run_rust_rows("off_ball_attack_score", [line])
    actual = [] if rows["offball"][0] == "-" else [
        tuple(float(part) for part in item.split(","))
        for item in rows["offball"][0].split(";")
    ]
    assert len(actual) == len(expected)
    for rust_item, py_item in zip(actual, expected):
        _assert_close_tuple([str(value) for value in rust_item], py_item, eps=1e-10)


def test_rust_off_ball_attack_scoring_adapter_opt_in_matches_python_target():
    import random

    config = EngineConfig()
    config.goal_continuity_enabled = True
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None):
        p = _vision_player(idx, x, y, iq=84)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        return p

    def build_state():
        runner = player(6, "CM", 72.0, 42.0, target=(78.0, 38.0), anchor=(76.0, 40.0))
        holder = player(8, "RW", 82.0, 56.0)
        striker = player(9, "ST", 90.0, 34.0, target=(92.0, 34.0), anchor=(90.0, 34.0))
        opponents = [player(2, "CB", 90.0, 30.0), player(3, "CB", 91.0, 39.0)]
        return runner, holder, [runner, holder, striker], opponents

    random.seed(20260708)
    runner, holder, teammates, opponents = build_state()
    config.rust_off_ball_attack_scoring_adapter_enabled = False
    py_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=11,
        team_side="home",
    )
    py_goal = None if runner.current_goal is None else (
        runner.current_goal.goal_type,
        runner.current_goal.target_pos,
        runner.current_goal.value,
    )
    py_intent = runner.movement_intent

    random.seed(20260708)
    runner, holder, teammates, opponents = build_state()
    config.rust_off_ball_attack_scoring_adapter_enabled = True
    rust_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=11,
        team_side="home",
    )
    rust_goal = None if runner.current_goal is None else (
        runner.current_goal.goal_type,
        runner.current_goal.target_pos,
        runner.current_goal.value,
    )
    rust_intent = runner.movement_intent

    _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-10)
    assert rust_goal is not None and py_goal is not None
    assert rust_goal[0] == py_goal[0]
    _assert_close_tuple([str(value) for value in rust_goal[1]], py_goal[1], eps=1e-10)
    assert abs(rust_goal[2] - py_goal[2]) < 1e-10
    assert rust_intent == py_intent


def test_rust_off_ball_attack_raw_adapter_opt_in_matches_python_target_without_goal_mutation():
    import random

    config = EngineConfig()
    config.goal_continuity_enabled = False
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None):
        p = _vision_player(idx, x, y, iq=84)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        return p

    def build_state():
        runner = player(6, "CM", 72.0, 42.0, target=(78.0, 38.0), anchor=(76.0, 40.0))
        holder = player(8, "RW", 82.0, 56.0)
        striker = player(9, "ST", 90.0, 34.0, target=(92.0, 34.0), anchor=(90.0, 34.0))
        opponents = [player(2, "CB", 90.0, 30.0), player(3, "CB", 91.0, 39.0)]
        return runner, holder, [runner, holder, striker], opponents

    random.seed(20260710)
    runner, holder, teammates, opponents = build_state()
    config.rust_off_ball_attack_raw_adapter_enabled = False
    py_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=12,
        team_side="home",
    )
    py_intent = runner.movement_intent

    random.seed(20260710)
    runner, holder, teammates, opponents = build_state()
    config.rust_off_ball_attack_raw_adapter_enabled = True
    rust_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=12,
        team_side="home",
    )
    rust_intent = runner.movement_intent

    _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-10)
    assert rust_intent == py_intent


def test_rust_off_ball_attack_full_choice_adapter_matches_python_without_goal_mutation():
    import random

    config = EngineConfig()
    config.goal_continuity_enabled = False
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None, speed=70):
        p = _vision_player(idx, x, y, iq=84)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        p.base_formation_pos = anchor or (x, y)
        p.formation_pos = anchor or (x, y)
        p.abilities.update({"Speed": speed})
        return p

    def build_state():
        runner = player(6, "CM", 72.0, 42.0, target=(78.0, 38.0), anchor=(76.0, 40.0), speed=78)
        holder = player(8, "RW", 82.0, 56.0, speed=82)
        striker = player(9, "ST", 90.0, 34.0, target=(92.0, 34.0), anchor=(90.0, 34.0), speed=76)
        winger = player(7, "LW", 78.0, 18.0, target=(82.0, 20.0), anchor=(80.0, 20.0), speed=80)
        opponents = [
            player(2, "CB", 90.0, 30.0, speed=72),
            player(3, "CB", 91.0, 39.0, speed=70),
            player(4, "LB", 80.0, 53.0, speed=75),
        ]
        return runner, holder, [runner, holder, striker, winger], opponents

    random.seed(20260711)
    runner, holder, teammates, opponents = build_state()
    py_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=13,
        team_side="home",
    )
    py_intent = runner.movement_intent
    py_random_after = random.getstate()

    random.seed(20260711)
    runner, holder, teammates, opponents = build_state()
    config.rust_off_ball_attack_choice_adapter_enabled = True
    rust_target = runner.choose_off_ball_attack(
        holder.pos,
        config,
        pitch,
        True,
        ball_carrier=holder,
        opponents=opponents,
        teammates=teammates,
        tick=13,
        team_side="home",
    )
    rust_intent = runner.movement_intent
    rust_random_after = random.getstate()

    _assert_close_tuple([str(value) for value in rust_target], py_target, eps=1e-10)
    assert rust_intent == py_intent
    assert rust_random_after == py_random_after


def test_rust_off_ball_defense_score_batch_matches_python_formula():
    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None, speed=70, defence=70):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        p.base_formation_pos = anchor or (x, y)
        p.abilities.update({"Speed": speed, "Defence": defence})
        return p

    defender = player(4, "CB", 70.0, 34.0, anchor=(68.0, 34.0), defence=76)
    ball_pos = (78.0, 34.0)
    carrier = player(9, "ST", 78.0, 34.0, speed=78)
    carrier.consecutive_carries = 3
    attackers = [
        carrier,
        player(10, "LW", 80.0, 48.0, target=(82.0, 46.0)),
        player(11, "RW", 82.0, 24.0, target=(84.0, 26.0)),
    ]
    teammates = [
        player(2, "CB", 66.0, 28.0, target=(67.0, 29.0)),
        player(3, "RB", 72.0, 46.0, target=(74.0, 44.0)),
    ]
    candidates = [(68.0, 34.0), (75.0, 34.0), (78.0, 40.0)]
    attacking_right = False
    own_goal_x = config.pitch_length
    central_threat = 1.0 - min(1.0, abs(ball_pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
    ball_goal_dist = py_physics.distance(ball_pos, (own_goal_x, config.pitch_width / 2.0))
    shot_danger = max(0.0, 1.0 - ball_goal_dist / 32.0) * (0.55 + 0.45 * central_threat)
    carrier_progress = ball_pos[0] / config.pitch_length
    carrier_stale_threat = (
        max(0.0, min(1.0, (carrier.consecutive_carries - 1) / 3.0))
        * max(0.0, min(1.0, (carrier_progress - 0.62) / 0.24))
        * (0.55 + 0.45 * central_threat)
    )
    role_progress = (config.pitch_length - defender.base_formation_pos[0]) / config.pitch_length
    pressure_role = max(
        0.12,
        _test_smoothstep(0.36, 0.82, role_progress),
        _test_smoothstep(0.30, 0.56, role_progress) * (1.0 - _test_smoothstep(0.74, 0.92, role_progress)) * 0.72,
    )
    field_press_context = (
        _test_smoothstep(0.16, 0.50, carrier_progress)
        * (1.0 - _test_smoothstep(0.82, 0.96, carrier_progress))
        * (0.58 + 0.42 * central_threat)
        * pressure_role
    )
    dist_to_ball = py_physics.distance(defender.pos, ball_pos)
    teammates_no_gk = teammates
    defenders_closer_to_ball = sum(1 for tm in teammates_no_gk if py_physics.distance(tm.pos, ball_pos) < dist_to_ball - 1.0)
    close_defenders_near_ball = sum(1 for tm in teammates_no_gk if py_physics.distance(tm.pos, ball_pos) < max(config.press_radius * 0.72, config.tackle_range))
    nearest_def_dist = min([py_physics.distance(tm.pos, ball_pos) for tm in teammates_no_gk] + [dist_to_ball])
    dangerous_receivers = [
        atk for atk in attackers
        if atk is not carrier and (
            py_physics.distance(atk.pos, ball_pos) < 34.0
            or py_physics.distance(atk.pos, defender.tactical_anchor) < 28.0
            or py_physics.distance(atk.pos, defender.pos) < 18.0
        )
    ]

    def shot_lane_closure(point):
        goal_y = config.pitch_width / 2.0
        shot_dx = own_goal_x - ball_pos[0]
        shot_dy = goal_y - ball_pos[1]
        shot_len = (shot_dx * shot_dx + shot_dy * shot_dy) ** 0.5
        if shot_len <= 1.0:
            return 0.0
        nx, ny = shot_dx / shot_len, shot_dy / shot_len
        relx, rely = point[0] - ball_pos[0], point[1] - ball_pos[1]
        proj = relx * nx + rely * ny
        if proj <= 0.5 or proj >= shot_len - 0.5:
            return 0.0
        perp = abs(relx * ny - rely * nx)
        lane = 1.0 - _test_smoothstep(1.8, 7.5, perp)
        depth = 1.0 - min(1.0, abs((proj / shot_len) - 0.40) / 0.52)
        return max(0.0, lane) * (0.42 + 0.58 * max(0.0, depth))

    current_lane_closure = shot_lane_closure(defender.pos)
    shot_lane_threat = (1.0 - _test_smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * central_threat)
    attacker_positions = [(atk.pos[0], atk.pos[1]) for atk in attackers]
    teammate_positions = [(tm.pos[0], tm.pos[1]) for tm in teammates_no_gk]

    expected = []
    for point in candidates:
        base_score = defensive_position_value(point, ball_pos, own_goal_x, pitch, attacker_positions, teammate_positions, defender.tactical_anchor)
        dist_point_ball = py_physics.distance(point, ball_pos)
        press_value = max(0.0, 1.0 - dist_point_ball / max(config.press_radius, 0.1))
        cover_cost = min(0.75, defenders_closer_to_ball * 0.16 + len(attackers) * 0.08)
        nearest_gap = max(0.0, dist_to_ball - nearest_def_dist)
        first_presser_share = 1.0 / (1.0 + max(0, defenders_closer_to_ball) ** 1.55)
        swarm_cost = 1.0 / (1.0 + max(0, close_defenders_near_ball) * 0.72)
        distance_responsibility = max(0.08, 1.0 - nearest_gap / 10.0)
        pressure_responsibility = first_presser_share * swarm_cost * distance_responsibility
        distance_responsibility = max(0.25, 1.0 - max(0.0, dist_to_ball - nearest_def_dist) / 18.0)
        carrier_threat = 0.35 + 0.65 * max(shot_danger, carrier_stale_threat, field_press_context * 0.86)
        press_reward = press_value * pressure_responsibility * distance_responsibility * carrier_threat
        score = base_score * (1.0 + press_reward * 2.45) * (1.0 - cover_cost * 0.28)
        lane_closure = 0.0
        if shot_lane_threat > 0.0:
            lane_closure = shot_lane_closure(point)
            lane_improvement = max(0.0, lane_closure - current_lane_closure)
            score *= 1.0 + shot_lane_threat * (lane_closure * 0.26 + lane_improvement * 0.74)
        best_mark_value = 0.0
        for receiver in dangerous_receivers:
            receiver_progress = receiver.pos[0] / config.pitch_length
            receiver_centrality = 1.0 - min(1.0, abs(receiver.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
            receiver_ball_dist = py_physics.distance(receiver.pos, ball_pos)
            mark_dist = py_physics.distance(point, receiver.pos)
            useful_distance = 1.0 - _test_smoothstep(3.2, 10.5, mark_dist)
            goal_side_progress = (point[0] - receiver.pos[0])
            goal_side_fit = _test_smoothstep(0.0, 2.2, goal_side_progress) * (1.0 - _test_smoothstep(6.5, 12.0, goal_side_progress))
            receive_threat = _test_smoothstep(0.58, 0.90, receiver_progress) * (0.42 + 0.58 * receiver_centrality) * (1.0 - _test_smoothstep(28.0, 46.0, receiver_ball_dist))
            best_mark_value = max(best_mark_value, receive_threat * useful_distance * (0.48 + 0.52 * goal_side_fit))
        if best_mark_value > 0.0:
            score *= 1.0 + best_mark_value * 0.90
        if py_physics.distance(point, carrier.pos) < config.tackle_range:
            score *= 1.0 + carrier_threat * pressure_responsibility * 0.75
        expected.append((max(0.0, score), point[0], point[1]))

    line = "\t".join([
        str(defender.pos[0]), str(defender.pos[1]),
        str(defender.tactical_anchor[0]), str(defender.tactical_anchor[1]),
        str(defender.base_formation_pos[0]), str(defender.base_formation_pos[1]),
        str(ball_pos[0]), str(ball_pos[1]),
        "0",
        str(carrier.pos[0]), str(carrier.pos[1]),
        str(carrier.consecutive_carries),
        str(config.pitch_length), str(config.pitch_width),
        str(config.press_radius), str(config.tackle_range), str(config.carrier_speed),
        "-",
        "-",
        _positions_payload(candidates),
        _positions_payload(attacker_positions),
        _positions_payload([(atk.pos[0], atk.pos[1]) for atk in attackers]),
        _positions_payload([(r.pos[0], r.pos[1]) for r in dangerous_receivers]),
        _defense_teammates_payload(teammates_no_gk),
        "defense",
    ])
    rows = _run_rust_rows("off_ball_defense_score", [line])
    actual = [tuple(float(part) for part in item.split(",")) for item in rows["defense"][0].split(";")]
    assert len(actual) == len(expected)
    for rust_item, py_item in zip(actual, expected):
        _assert_close_tuple([str(rust_item[0]), str(rust_item[1]), str(rust_item[2])], py_item, eps=1e-10)


def test_rust_off_ball_defense_scoring_adapter_opt_in_matches_python_choice():
    import random

    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None, speed=70, defence=70):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        p.base_formation_pos = anchor or (x, y)
        p.abilities.update({"Speed": speed, "Defence": defence, "Tackling": defence})
        return p

    def build_state():
        defender = player(4, "CB", 70.0, 34.0, anchor=(68.0, 34.0), defence=76)
        carrier = player(9, "ST", 78.0, 34.0, speed=78)
        carrier.consecutive_carries = 3
        attackers = [
            carrier,
            player(10, "LW", 80.0, 48.0, target=(82.0, 46.0)),
            player(11, "RW", 82.0, 24.0, target=(84.0, 26.0)),
        ]
        teammates = [
            defender,
            player(2, "CB", 66.0, 28.0, target=(67.0, 29.0)),
            player(3, "RB", 72.0, 46.0, target=(74.0, 44.0)),
        ]
        return defender, carrier, attackers, teammates

    random.seed(20260708)
    defender, carrier, attackers, teammates = build_state()
    config.rust_off_ball_defense_scoring_adapter_enabled = False
    py_action, py_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=17,
        team_side="away",
    )

    random.seed(20260708)
    defender, carrier, attackers, teammates = build_state()
    config.rust_off_ball_defense_scoring_adapter_enabled = True
    rust_action, rust_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=17,
        team_side="away",
    )

    assert rust_action == py_action
    _assert_close_tuple(
        [str(value) for value in rust_details["target"]],
        py_details["target"],
        eps=1e-10,
    )


def test_rust_off_ball_defense_scoring_and_softmax_adapters_match_python_choice():
    import random

    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None, speed=70, defence=70):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        p.base_formation_pos = anchor or (x, y)
        p.abilities.update({"Speed": speed, "Defence": defence, "Tackling": defence})
        return p

    def build_state():
        defender = player(4, "CB", 70.0, 34.0, anchor=(68.0, 34.0), defence=76)
        carrier = player(9, "ST", 78.0, 34.0, speed=78)
        carrier.consecutive_carries = 3
        attackers = [
            carrier,
            player(10, "LW", 80.0, 48.0, target=(82.0, 46.0)),
            player(11, "RW", 82.0, 24.0, target=(84.0, 26.0)),
        ]
        teammates = [
            defender,
            player(2, "CB", 66.0, 28.0, target=(67.0, 29.0)),
            player(3, "RB", 72.0, 46.0, target=(74.0, 44.0)),
        ]
        return defender, carrier, attackers, teammates

    random.seed(20260709)
    defender, carrier, attackers, teammates = build_state()
    py_action, py_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=19,
        team_side="away",
    )

    random.seed(20260709)
    defender, carrier, attackers, teammates = build_state()
    config.rust_off_ball_defense_scoring_adapter_enabled = True
    config.rust_softmax_selection_adapter_enabled = True
    rust_action, rust_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=19,
        team_side="away",
    )

    assert rust_action == py_action
    _assert_close_tuple(
        [str(value) for value in rust_details["target"]],
        py_details["target"],
        eps=1e-10,
    )


def test_rust_off_ball_defense_full_choice_adapter_matches_python_choice():
    import random

    config = EngineConfig()
    pitch = Pitch(config=config)

    def player(idx, position, x, y, target=None, anchor=None, speed=70, defence=70):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        p.base_formation_pos = anchor or (x, y)
        p.formation_pos = anchor or (x, y)
        p.abilities.update({"Speed": speed, "Defence": defence, "Tackling": defence})
        return p

    def build_state():
        defender = player(4, "CB", 70.0, 34.0, anchor=(68.0, 34.0), defence=76)
        defender.last_def_action = "block_lane"
        defender.last_def_target = (67.0, 32.5)
        carrier = player(9, "ST", 78.0, 34.0, speed=78)
        carrier.consecutive_carries = 3
        attackers = [
            carrier,
            player(10, "LW", 80.0, 48.0, target=(82.0, 46.0)),
            player(11, "RW", 82.0, 24.0, target=(84.0, 26.0)),
        ]
        teammates = [
            defender,
            player(2, "CB", 66.0, 28.0, target=(67.0, 29.0)),
            player(3, "RB", 72.0, 46.0, target=(74.0, 44.0)),
            player(6, "DM", 69.0, 39.0, target=(70.0, 38.0)),
        ]
        return defender, carrier, attackers, teammates

    random.seed(20260710)
    defender, carrier, attackers, teammates = build_state()
    py_action, py_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=21,
        team_side="away",
    )
    py_random_after = random.getstate()

    random.seed(20260710)
    defender, carrier, attackers, teammates = build_state()
    config.rust_off_ball_defense_choice_adapter_enabled = True
    rust_action, rust_details = defender.choose_off_ball_defend(
        carrier.pos,
        config,
        pitch,
        attacking_right=False,
        ball_carrier=carrier,
        opponents=attackers,
        teammates=teammates,
        tick=21,
        team_side="away",
    )
    rust_random_after = random.getstate()

    assert rust_action == py_action
    _assert_close_tuple(
        [str(value) for value in rust_details["target"]],
        py_details["target"],
        eps=1e-10,
    )
    assert rust_random_after == py_random_after


def _defense_raw_candidates_python(
    defender,
    ball_pos,
    attacking_right,
    config,
    local_attackers,
    dangerous_receivers,
    ball_carrier,
    carrier_stale_threat,
    field_press_context,
    shot_danger,
    shot_lane_threat,
    random_samples,
    last_def_target=None,
):
    import math

    anchor = defender.tactical_anchor
    sampled_points = [
        anchor,
        pitch_clamp_tuple(
            anchor[0] * 0.85 + ball_pos[0] * 0.15,
            anchor[1] * 0.72 + ball_pos[1] * 0.28,
            config,
        ),
    ]

    if local_attackers:
        best_threat = 0.0
        best_target = None
        for opp in local_attackers:
            dist_to_ball = py_physics.distance(opp.pos, ball_pos)
            ball_proximity = max(0.2, 1.0 - dist_to_ball / 30.0)
            advance = 1.0 - opp.pos[0] / config.pitch_length if attacking_right else opp.pos[0] / config.pitch_length
            threat = ball_proximity * 0.6 + advance * 0.4
            if threat > best_threat:
                best_threat = threat
                best_target = opp
        if best_target is not None:
            mark_x = best_target.pos[0] - 1.5 if attacking_right else best_target.pos[0] + 1.5
            sampled_points.append(pitch_clamp_tuple(mark_x, best_target.pos[1], config))

        target_opp = min(local_attackers, key=lambda o: py_physics.distance(defender.pos, o.pos))
        sampled_points.append(pitch_clamp_tuple(
            (ball_pos[0] + target_opp.pos[0]) / 2.0,
            (ball_pos[1] + target_opp.pos[1]) / 2.0,
            config,
        ))

    if dangerous_receivers:
        goal_side = -1.0 if attacking_right else 1.0
        for receiver in dangerous_receivers:
            receiver_progress = (
                receiver.pos[0] / max(1.0, config.pitch_length)
                if not attacking_right
                else (config.pitch_length - receiver.pos[0]) / max(1.0, config.pitch_length)
            )
            receiver_centrality = 1.0 - min(
                1.0,
                abs(receiver.pos[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0),
            )
            receiver_ball_dist = py_physics.distance(receiver.pos, ball_pos)
            receive_threat = (
                _test_smoothstep(0.58, 0.90, receiver_progress)
                * (0.42 + 0.58 * receiver_centrality)
                * (1.0 - _test_smoothstep(28.0, 46.0, receiver_ball_dist))
            )
            if receive_threat <= 0.02:
                continue
            mark_gap = 2.4 + 1.2 * receive_threat
            lateral_gap = max(-2.8, min(2.8, defender.pos[1] - receiver.pos[1])) * 0.22
            sampled_points.append(pitch_clamp_tuple(
                receiver.pos[0] + goal_side * mark_gap,
                receiver.pos[1] + lateral_gap,
                config,
            ))

    if ball_carrier is not None:
        goal_side = -1.0 if attacking_right else 1.0
        lead = config.carrier_speed * 0.45
        sampled_points.append(pitch_clamp_tuple(ball_pos[0] + goal_side * lead, ball_pos[1], config))
        contain_depth = 2.2 + 1.6 * carrier_stale_threat
        contain_width = 3.0 + 2.0 * carrier_stale_threat
        for oy in (-contain_width, 0.0, contain_width):
            sampled_points.append(pitch_clamp_tuple(ball_pos[0] + goal_side * contain_depth, ball_pos[1] + oy, config))
        lateral_sign = -1.0 if defender.pos[1] < ball_pos[1] else 1.0
        angle_width = 5.5 + 3.0 * field_press_context
        angle_depth = 3.2 + 1.4 * max(field_press_context, shot_danger)
        sampled_points.append(pitch_clamp_tuple(
            ball_pos[0] + goal_side * angle_depth,
            ball_pos[1] + lateral_sign * angle_width,
            config,
        ))
        own_goal_x = 0.0 if attacking_right else config.pitch_length
        goal_y = config.pitch_width / 2.0
        shot_dx = own_goal_x - ball_pos[0]
        shot_dy = goal_y - ball_pos[1]
        shot_len = math.sqrt(shot_dx * shot_dx + shot_dy * shot_dy)
        if shot_len > 1.0 and shot_lane_threat > 0.05:
            nx, ny = shot_dx / shot_len, shot_dy / shot_len
            for lane_fraction in (0.30, 0.46):
                lane_depth = max(2.5, min(10.5, shot_len * lane_fraction))
                lane_x = ball_pos[0] + nx * lane_depth
                lane_y = ball_pos[1] + ny * lane_depth
                side_offset = max(-3.2, min(3.2, defender.pos[1] - lane_y)) * 0.45
                sampled_points.append(pitch_clamp_tuple(lane_x, lane_y + side_offset, config))

    for angle_unit, radius_unit in random_samples:
        angle = angle_unit * math.tau
        radius = radius_unit ** 0.7 * (8.0 + shot_danger * 4.0)
        sampled_points.append(pitch_clamp_tuple(
            defender.tactical_anchor[0] + math.cos(angle) * radius,
            defender.tactical_anchor[1] + math.sin(angle) * radius,
            config,
        ))
    if last_def_target is not None:
        sampled_points.append(last_def_target)
    return sampled_points


def test_rust_off_ball_defense_raw_generation_matches_python_formula():
    config = EngineConfig()

    def player(idx, position, x, y, target=None, anchor=None):
        p = _vision_player(idx, x, y)
        p.position = position
        p.target_pos = target or (x, y)
        p.tactical_anchor = anchor or (x, y)
        return p

    defender = player(4, "CB", 70.0, 34.0, anchor=(68.0, 34.0))
    ball_pos = (78.0, 34.0)
    carrier = player(9, "ST", 78.0, 34.0)
    local_attackers = [carrier, player(10, "LW", 80.0, 48.0)]
    dangerous_receivers = [player(10, "LW", 80.0, 48.0), player(11, "RW", 82.0, 24.0)]
    random_samples = [(0.1, 0.2), (0.4, 0.7), (0.8, 0.5)]
    expected = _defense_raw_candidates_python(
        defender,
        ball_pos,
        False,
        config,
        local_attackers,
        dangerous_receivers,
        carrier,
        carrier_stale_threat=0.3,
        field_press_context=0.2,
        shot_danger=0.4,
        shot_lane_threat=0.5,
        random_samples=random_samples,
        last_def_target=(66.0, 32.0),
    )
    line = "\t".join([
        str(defender.pos[0]), str(defender.pos[1]),
        str(defender.tactical_anchor[0]), str(defender.tactical_anchor[1]),
        str(ball_pos[0]), str(ball_pos[1]),
        "0",
        str(config.pitch_length), str(config.pitch_width),
        str(carrier.pos[0]), str(carrier.pos[1]),
        str(config.carrier_speed),
        "0.3",
        "0.2",
        "0.4",
        "0.5",
        _positions_payload([(p.pos[0], p.pos[1]) for p in local_attackers]),
        _positions_payload([(p.pos[0], p.pos[1]) for p in dangerous_receivers]),
        ";".join(f"{a},{r}" for a, r in random_samples),
        "66.0",
        "32.0",
        "defraw",
    ])
    rows = _run_rust_rows("off_ball_defense_raw", [line])
    actual = [tuple(float(part) for part in item.split(",")) for item in rows["defraw"][0].split(";")]
    assert len(actual) == len(expected)
    for rust_item, py_item in zip(actual, expected):
        _assert_close_tuple([str(value) for value in rust_item], py_item, eps=1e-10)


def test_rust_pass_lane_risk_matches_python():
    config = EngineConfig()
    cases = [
        ("clear_lane", (40.0, 34.0), (70.0, 34.0), [(55.0, 50.0)]),
        ("blocked_lane", (40.0, 34.0), (70.0, 34.0), [(55.0, 34.0), (60.0, 36.0)]),
        ("short_lane", (40.0, 34.0), (40.2, 34.2), [(40.1, 34.1)]),
    ]
    rust_values = _run_rust_mode("pass_lane_risk", [
        "\t".join([
            str(origin[0]),
            str(origin[1]),
            str(target[0]),
            str(target[1]),
            str(config.interception_reach),
            _positions_payload(opponents),
            case_id,
        ])
        for case_id, origin, target, opponents in cases
    ])
    for case_id, origin, target, opponents in cases:
        py_opponents = [_opponent(idx + 20, x, y) for idx, (x, y) in enumerate(opponents)]
        py_value = pass_lane_risk(origin, target, py_opponents, config)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_receiver_pressure_matches_python():
    cases = [
        ("open", (70.0, 34.0), [(90.0, 34.0)]),
        ("single_pressure", (70.0, 34.0), [(74.0, 34.0)]),
        ("crowded", (70.0, 34.0), [(74.0, 34.0), (68.0, 40.0), (72.0, 29.0)]),
    ]
    rust_values = _run_rust_mode("receiver_pressure", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            _positions_payload(opponents),
            case_id,
        ])
        for case_id, target, opponents in cases
    ])
    for case_id, target, opponents in cases:
        py_opponents = [_opponent(idx + 30, x, y) for idx, (x, y) in enumerate(opponents)]
        py_value = receiver_pressure(target, py_opponents)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_turnover_consequence_matches_python():
    config = EngineConfig()
    cases = [
        ("own_central", (25.0, 34.0), True, [(30.0, 34.0), (36.0, 28.0)]),
        ("opp_wide", (82.0, 10.0), True, [(70.0, 12.0)]),
        ("left_attack_own", (82.0, 34.0), False, [(76.0, 34.0)]),
    ]
    rust_values = _run_rust_mode("turnover_consequence", [
        "\t".join([
            str(loss_pos[0]),
            str(loss_pos[1]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            _positions_payload(opponents),
            case_id,
        ])
        for case_id, loss_pos, attacking_right, opponents in cases
    ])
    for case_id, loss_pos, attacking_right, opponents in cases:
        py_opponents = [_opponent(idx + 40, x, y) for idx, (x, y) in enumerate(opponents)]
        py_value = turnover_consequence(loss_pos, py_opponents, config, attacking_right)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_state_value_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "midfield_state",
            55.0,
            34.0,
            1,
            78,
            72,
            True,
            [(70.0, 30.0), (74.0, 40.0)],
            [(1, 55.0, 34.0), (2, 68.0, 22.0), (3, 72.0, 42.0)],
        ),
        (
            "advanced_state",
            82.0,
            34.0,
            1,
            82,
            76,
            True,
            [(88.0, 28.0), (88.0, 40.0)],
            [(1, 82.0, 34.0), (2, 76.0, 22.0), (3, 90.0, 34.0)],
        ),
        (
            "left_attack_state",
            28.0,
            40.0,
            1,
            80,
            74,
            False,
            [(20.0, 34.0), (24.0, 46.0)],
            [(1, 28.0, 40.0), (2, 35.0, 44.0), (3, 18.0, 34.0)],
        ),
    ]
    rust_values = _run_rust_mode("state_value", [
        _state_case_line(
            case_id,
            x,
            y,
            player_index,
            finishing / 100.0,
            long_shot / 100.0,
            attacking_right,
            opponents,
            teammates,
        )
        for case_id, x, y, player_index, finishing, long_shot, attacking_right, opponents, teammates in cases
    ])
    for case_id, x, y, player_index, finishing, long_shot, attacking_right, opponents, teammates in cases:
        player = _teammate(player_index, x, y, finishing, long_shot)
        py_teammates = [
            _teammate(idx, tx, ty, finishing if idx == player_index else 70, long_shot if idx == player_index else 70)
            for idx, tx, ty in teammates
        ]
        py_opponents = [_opponent(idx + 50, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_value = state_value((x, y), player, py_teammates, py_opponents, config, pitch, attacking_right)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_state_value_adapter_opt_in_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    player = _teammate(4, 64.0, 36.0, finishing=78, long_shot=72)
    teammates = [
        _teammate(1, 52.0, 30.0),
        player,
        _teammate(9, 82.0, 34.0),
    ]
    opponents = [_opponent(20, 68.0, 35.0), _opponent(21, 76.0, 40.0)]
    py_value = player._current_state_value(teammates, opponents, config, pitch, True)
    config.rust_state_value_adapter_enabled = True
    rust_value = player._current_state_value(teammates, opponents, config, pitch, True)
    assert abs(rust_value - py_value) < 1e-12


def test_rust_pass_receive_value_matches_python_without_receiver_goal():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "wide_receive",
            82.0,
            22.0,
            2,
            78,
            74,
            (84.0, 24.0),
            (62.0, 24.0),
            True,
            [(88.0, 28.0), (88.0, 40.0), (78.0, 22.0)],
            [(1, 72.0, 34.0), (2, 78.0, 20.0), (3, 88.0, 34.0)],
        ),
        (
            "central_second_line",
            78.0,
            34.0,
            2,
            74,
            80,
            (80.0, 34.0),
            (55.0, 34.0),
            True,
            [(86.0, 30.0), (86.0, 38.0)],
            [(1, 70.0, 34.0), (2, 72.0, 34.0), (3, 86.0, 24.0)],
        ),
        (
            "left_attack_receive",
            28.0,
            42.0,
            2,
            76,
            72,
            (26.0, 42.0),
            (55.0, 42.0),
            False,
            [(20.0, 34.0), (24.0, 46.0)],
            [(1, 34.0, 34.0), (2, 35.0, 44.0), (3, 18.0, 34.0)],
        ),
    ]
    rust_values = _run_rust_mode("pass_receive_value", [
        _pass_receive_case_line(
            case_id,
            x,
            y,
            receiver_index,
            finishing / 100.0,
            long_shot / 100.0,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
        )
        for (
            case_id,
            x,
            y,
            receiver_index,
            finishing,
            long_shot,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
        ) in cases
    ])
    for (
        case_id,
        x,
        y,
        receiver_index,
        finishing,
        long_shot,
        receiver_anchor,
        receiver_base,
        attacking_right,
        opponents,
        teammates,
    ) in cases:
        receiver = _teammate(receiver_index, x, y, finishing, long_shot)
        receiver.tactical_anchor = receiver_anchor
        receiver.base_formation_pos = receiver_base
        py_teammates = [
            _teammate(idx, tx, ty, finishing if idx == receiver_index else 70, long_shot if idx == receiver_index else 70)
            for idx, tx, ty in teammates
        ]
        for player in py_teammates:
            if player.index == receiver_index:
                player.tactical_anchor = receiver_anchor
                player.base_formation_pos = receiver_base
        py_opponents = [_opponent(idx + 60, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_value = pass_receive_value((x, y), receiver, py_teammates, py_opponents, config, pitch, attacking_right)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_pass_receive_value_matches_python_with_receiver_goal():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "arc_goal",
            78.0,
            35.0,
            2,
            76,
            80,
            (78.0, 35.0),
            (55.0, 35.0),
            True,
            [(88.0, 30.0), (88.0, 40.0)],
            [(1, 70.0, 34.0), (2, 72.0, 36.0), (3, 86.0, 24.0)],
            "arc_arrival_for_cutback",
            (78.0, 35.0),
            0.30,
        ),
        (
            "far_post_goal",
            91.0,
            39.0,
            2,
            82,
            74,
            (91.0, 39.0),
            (70.0, 45.0),
            True,
            [(88.0, 30.0), (90.0, 40.0)],
            [(1, 84.0, 12.0), (2, 86.0, 44.0), (3, 82.0, 34.0)],
            "attack_far_post",
            (91.0, 39.0),
            0.26,
        ),
    ]
    rust_values = _run_rust_mode("pass_receive_value", [
        _pass_receive_case_line(
            case_id,
            x,
            y,
            receiver_index,
            finishing / 100.0,
            long_shot / 100.0,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
            goal_type,
            goal_target,
            goal_value,
        )
        for (
            case_id,
            x,
            y,
            receiver_index,
            finishing,
            long_shot,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
            goal_type,
            goal_target,
            goal_value,
        ) in cases
    ])
    for (
        case_id,
        x,
        y,
        receiver_index,
        finishing,
        long_shot,
        receiver_anchor,
        receiver_base,
        attacking_right,
        opponents,
        teammates,
        goal_type,
        goal_target,
        goal_value,
    ) in cases:
        receiver = _teammate(receiver_index, x, y, finishing, long_shot)
        receiver.tactical_anchor = receiver_anchor
        receiver.base_formation_pos = receiver_base
        receiver.current_goal = PlayerGoal(
            goal_type=goal_type,
            target_pos=goal_target,
            value=goal_value,
        )
        py_teammates = [
            _teammate(idx, tx, ty, finishing if idx == receiver_index else 70, long_shot if idx == receiver_index else 70)
            for idx, tx, ty in teammates
        ]
        for player in py_teammates:
            if player.index == receiver_index:
                player.tactical_anchor = receiver_anchor
                player.base_formation_pos = receiver_base
                player.current_goal = receiver.current_goal
        py_opponents = [_opponent(idx + 70, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_value = pass_receive_value((x, y), receiver, py_teammates, py_opponents, config, pitch, attacking_right)
        assert abs(rust_values[case_id] - py_value) < 1e-12


def test_rust_expected_pass_core_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "safe_forward",
            (55.0, 34.0),
            (72.0, 34.0),
            78,
            74,
            0,
            2,
            76,
            72,
            (74.0, 34.0),
            (58.0, 34.0),
            True,
            [(82.0, 30.0), (82.0, 38.0)],
            [(1, 55.0, 34.0), (2, 70.0, 34.0), (3, 78.0, 22.0)],
            0.31,
            0.62,
            0.82,
            0.045,
            "-",
            None,
            0.0,
        ),
        (
            "stale_pressure_release",
            (82.0, 52.0),
            (76.0, 38.0),
            80,
            76,
            4,
            2,
            78,
            78,
            (76.0, 38.0),
            (58.0, 34.0),
            True,
            [(84.0, 49.0), (86.0, 42.0), (78.0, 38.0)],
            [(1, 82.0, 52.0), (2, 74.0, 38.0), (3, 88.0, 34.0)],
            0.44,
            0.58,
            0.74,
            0.050,
            "arc_arrival_for_cutback",
            (76.0, 38.0),
            0.24,
        ),
        (
            "left_attack_switch",
            (42.0, 24.0),
            (34.0, 46.0),
            75,
            80,
            1,
            2,
            80,
            76,
            (34.0, 46.0),
            (58.0, 46.0),
            False,
            [(30.0, 38.0), (36.0, 50.0)],
            [(1, 42.0, 24.0), (2, 36.0, 45.0), (3, 28.0, 34.0)],
            0.36,
            0.50,
            0.70,
            0.035,
            "-",
            None,
            0.0,
        ),
    ]
    rust_lines = [
        _expected_pass_case_line(
            case_id,
            origin,
            target,
            passer_finishing / 100.0,
            passer_long_shot / 100.0,
            passer_consecutive_carries,
            receiver_index,
            receiver_finishing / 100.0,
            receiver_long_shot / 100.0,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
            current_value,
            base_accuracy,
            receiver_arrival,
            continuity,
            receiver_goal_type,
            receiver_goal_target,
            receiver_goal_value,
        )
        for (
            case_id,
            origin,
            target,
            passer_finishing,
            passer_long_shot,
            passer_consecutive_carries,
            receiver_index,
            receiver_finishing,
            receiver_long_shot,
            receiver_anchor,
            receiver_base,
            attacking_right,
            opponents,
            teammates,
            current_value,
            base_accuracy,
            receiver_arrival,
            continuity,
            receiver_goal_type,
            receiver_goal_target,
            receiver_goal_value,
        ) in cases
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "expected_pass"],
        cwd=RUST_CRATE,
        input="\n".join(rust_lines),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_values = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rust_values[fields[0]] = {
            "score": float(fields[1]),
            "success_prob": float(fields[2]),
            "risk_cost": float(fields[3]),
            "after_value": float(fields[4]),
            "effective_delta": float(fields[5]),
            "continuity": float(fields[6]),
            "lane_risk": float(fields[7]),
            "receiver_pressure": float(fields[8]),
            "turnover_consequence": float(fields[9]),
        }

    for (
        case_id,
        origin,
        target,
        passer_finishing,
        passer_long_shot,
        passer_consecutive_carries,
        receiver_index,
        receiver_finishing,
        receiver_long_shot,
        receiver_anchor,
        receiver_base,
        attacking_right,
        opponents,
        teammates,
        current_value,
        base_accuracy,
        receiver_arrival,
        continuity,
        receiver_goal_type,
        receiver_goal_target,
        receiver_goal_value,
    ) in cases:
        passer = _teammate(1, origin[0], origin[1], passer_finishing, passer_long_shot)
        passer.consecutive_carries = passer_consecutive_carries
        receiver = _teammate(receiver_index, target[0], target[1], receiver_finishing, receiver_long_shot)
        receiver.tactical_anchor = receiver_anchor
        receiver.base_formation_pos = receiver_base
        if receiver_goal_type != "-":
            receiver.current_goal = PlayerGoal(
                goal_type=receiver_goal_type,
                target_pos=receiver_goal_target,
                value=receiver_goal_value,
            )
        py_teammates = [
            _teammate(idx, tx, ty, receiver_finishing if idx == receiver_index else passer_finishing, receiver_long_shot if idx == receiver_index else passer_long_shot)
            for idx, tx, ty in teammates
        ]
        for player in py_teammates:
            if player.index == receiver_index:
                player.tactical_anchor = receiver_anchor
                player.base_formation_pos = receiver_base
                player.current_goal = receiver.current_goal
        py_opponents = [_opponent(idx + 80, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_result = expected_pass_value_result(
            passer,
            receiver,
            origin,
            target,
            py_teammates,
            py_opponents,
            config,
            pitch,
            attacking_right,
            current_value,
            base_accuracy,
            receiver_arrival=receiver_arrival,
            continuity=continuity,
        )
        rust = rust_values[case_id]
        assert abs(rust["score"] - py_result.score) < 1e-12
        assert abs(rust["success_prob"] - py_result.success_prob) < 1e-12
        assert abs(rust["risk_cost"] - py_result.risk_cost) < 1e-12
        assert abs(rust["after_value"] - py_result.after_value) < 1e-12
        assert abs(rust["effective_delta"] - py_result.components["effective_delta"]) < 1e-12
        assert abs(rust["continuity"] - py_result.components["continuity"]) < 1e-12
        assert abs(rust["lane_risk"] - py_result.components["lane_risk"]) < 1e-12
        assert abs(rust["receiver_pressure"] - py_result.components["receiver_pressure"]) < 1e-12
        assert abs(rust["turnover_consequence"] - py_result.components["turnover_consequence"]) < 1e-12


def test_rust_hold_matches_python():
    cases = [
        ("calm_mid", 0.82, True, False, 0, 1, 0.42, 0, 0.0, 1.2, 0.02, 0.03, 0.35),
        ("pressed_def", 0.70, False, True, 2, 4, 0.24, 2, 0.75, 0.2, 0.11, 0.06, 0.10),
        ("shot_window", 0.88, False, False, 1, 3, 0.58, 1, 0.20, 1.8, 0.18, 0.14, 0.30),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "hold"],
        cwd=RUST_CRATE,
        input="\n".join(_hold_case_line(*case) for case in cases),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rust_rows[fields[0]] = {
            "score": float(fields[1]),
            "pressure_factor": float(fields[2]),
            "useful_development": float(fields[3]),
            "no_clear_release": float(fields[4]),
            "opportunity_wait": float(fields[5]),
            "opportunity_cost": float(fields[6]),
        }

    for (
        case_id,
        iq,
        is_midfielder,
        is_defender,
        hold_ticks,
        possession_ticks,
        current_pv,
        pressure,
        nearest_pressure,
        developing_runs,
        best_pass_score,
        shoot_score,
        opportunity_wait_value,
    ) in cases:
        holder = _teammate(1, 50.0, 34.0)
        holder.abilities["IQ"] = int(round(iq * 100))
        holder.position = "CM" if is_midfielder else "CB" if is_defender else "ST"
        holder.hold_ticks = hold_ticks
        holder.possession_ticks = possession_ticks
        py_value = evaluate_hold(
            holder,
            current_pv,
            pressure,
            nearest_pressure,
            developing_runs,
            best_pass_score,
            shoot_score,
            opportunity_wait_value,
        )
        rust = rust_rows[case_id]
        assert abs(rust["score"] - py_value.score) < 1e-12
        assert abs(rust["pressure_factor"] - py_value.components["pressure_factor"]) < 1e-12
        assert abs(rust["useful_development"] - py_value.components["useful_development"]) < 1e-12
        assert abs(rust["no_clear_release"] - py_value.components["no_clear_release"]) < 1e-12
        assert abs(rust["opportunity_wait"] - py_value.components["opportunity_wait"]) < 1e-12
        assert abs(rust["opportunity_cost"] - py_value.components["opportunity_cost"]) < 1e-12


def test_rust_clear_matches_python():
    config = EngineConfig()
    cases = [
        ("safe", 0.80, 0),
        ("own_pressure", 0.20, 2),
        ("own_high_pressure", 0.05, 4),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "clear"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([str(x_progress), str(pressure), str(config.clear_reward_base), case_id])
            for case_id, x_progress, pressure in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rust_rows[fields[0]] = {
            "score": float(fields[1]),
            "danger": float(fields[2]),
            "pressure_factor": float(fields[3]),
        }

    for case_id, x_progress, pressure in cases:
        py_value = evaluate_clear(x_progress, pressure, config)
        rust = rust_rows[case_id]
        assert abs(rust["score"] - py_value.score) < 1e-12
        assert abs(rust["danger"] - py_value.components["danger"]) < 1e-12
        assert abs(rust["pressure_factor"] - py_value.components["pressure_factor"]) < 1e-12


def test_rust_shot_evaluator_matches_python():
    config = EngineConfig()
    cases = [
        (
            "close_no_support",
            1,
            (90.0, 34.0),
            84,
            76,
            1,
            0,
            (90.0, 34.0),
            15.0,
            0.88,
            0.92,
            0.96,
            1.0,
            0.42,
            True,
            [(88.0, 29.0), (88.0, 39.0)],
            [],
        ),
        (
            "medium_with_layoff",
            1,
            (82.0, 30.0),
            80,
            82,
            1,
            0,
            (88.0, 34.0),
            24.0,
            0.72,
            0.94,
            0.95,
            0.72,
            0.55,
            True,
            [(88.0, 30.0), (90.0, 40.0)],
            [
                (1, 82.0, 30.0, 82.0, 30.0, False),
                (2, 76.0, 40.0, 74.0, 38.0, False),
                (3, 88.0, 34.0, 90.0, 34.0, False),
            ],
        ),
        (
            "left_long_shot",
            1,
            (35.0, 42.0),
            76,
            88,
            4,
            2,
            (44.0, 42.0),
            35.0,
            0.55,
            0.80,
            0.82,
            0.34,
            0.38,
            False,
            [(24.0, 40.0), (20.0, 34.0)],
            [
                (1, 35.0, 42.0, 35.0, 42.0, False),
                (2, 42.0, 30.0, 44.0, 32.0, False),
            ],
        ),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "shot_eval"],
        cwd=RUST_CRATE,
        input="\n".join(_shot_eval_case_line(*case) for case in cases),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rust_rows[fields[0]] = {
            "score": float(fields[1]),
            "on_target_prob": float(fields[2]),
            "xg": float(fields[3]),
            "save_estimate": float(fields[4]),
            "risk_cost": float(fields[5]),
            "opportunity_cost": float(fields[6]),
            "shot_readiness": float(fields[7]),
            "possession_loss_multiplier": float(fields[8]),
            "support_release_window": float(fields[9]),
        }

    for (
        case_id,
        shooter_index,
        shooter_pos,
        finishing,
        long_shot,
        possession_ticks,
        consecutive_carries,
        last_receive_origin,
        dist_to_goal,
        angle_factor,
        pressure_factor,
        lane_factor,
        dist_factor,
        current_state_value,
        attacking_right,
        opponents,
        teammates,
    ) in cases:
        shooter = _teammate(shooter_index, shooter_pos[0], shooter_pos[1], finishing, long_shot)
        shooter.possession_ticks = possession_ticks
        shooter.consecutive_carries = consecutive_carries
        shooter.last_receive_origin = last_receive_origin
        py_teammates = []
        for idx, x, y, tx, ty, is_gk in teammates:
            player = _teammate(idx, x, y)
            player.target_pos = (tx, ty)
            if is_gk:
                player.position = "GK"
            py_teammates.append(player)
        py_opponents = [_opponent(idx + 90, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        goal_pos = (config.pitch_length if attacking_right else 0.0, config.pitch_width / 2.0)
        py_value = evaluate_shot(
            shooter,
            goal_pos,
            config,
            py_opponents,
            dist_to_goal,
            angle_factor,
            pressure_factor,
            lane_factor,
            dist_factor,
            current_state_value=current_state_value,
            teammates=py_teammates,
            pitch=Pitch(config=config),
            attacking_right=attacking_right,
        )
        rust = rust_rows[case_id]
        assert abs(rust["score"] - py_value.score) < 1e-12
        assert abs(rust["on_target_prob"] - py_value.success_prob) < 1e-12
        assert abs(rust["xg"] - py_value.after_value) < 1e-12
        assert abs(rust["save_estimate"] - py_value.components["save_estimate"]) < 1e-12
        assert abs(rust["risk_cost"] - py_value.risk_cost) < 1e-12
        assert abs(rust["opportunity_cost"] - py_value.components["opportunity_cost"]) < 1e-12
        assert abs(rust["shot_readiness"] - py_value.components["shot_readiness"]) < 1e-12
        assert abs(rust["possession_loss_multiplier"] - py_value.components["possession_loss_multiplier"]) < 1e-12
        assert abs(rust["support_release_window"] - py_value.components["support_release_window"]) < 1e-12


def test_rust_carry_evaluator_matches_python():
    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        (
            "central_progress",
            1,
            (62.0, 34.0),
            (68.0, 34.0),
            80,
            76,
            0,
            1,
            0.42,
            0.36,
            0.38,
            0.92,
            True,
            [(78.0, 30.0), (78.0, 40.0)],
            [(1, 62.0, 34.0, 62.0, 34.0, False), (2, 72.0, 22.0, 64.0, 22.0, False)],
        ),
        (
            "wide_cut",
            1,
            (76.0, 54.0),
            (82.0, 42.0),
            84,
            80,
            1,
            3,
            0.55,
            0.40,
            0.43,
            0.78,
            True,
            [(84.0, 44.0), (88.0, 34.0)],
            [(1, 76.0, 54.0, 76.0, 54.0, False), (2, 80.0, 34.0, 62.0, 34.0, False)],
        ),
        (
            "left_attack",
            1,
            (38.0, 20.0),
            (31.0, 30.0),
            78,
            84,
            3,
            5,
            0.48,
            0.44,
            0.45,
            0.70,
            False,
            [(26.0, 34.0), (30.0, 24.0)],
            [(1, 38.0, 20.0, 38.0, 20.0, False), (2, 44.0, 34.0, 58.0, 34.0, False)],
        ),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "carry_eval"],
        cwd=RUST_CRATE,
        input="\n".join(_carry_eval_case_line(*case) for case in cases),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        fields = line.split("\t")
        rust_rows[fields[0]] = {
            "score": float(fields[1]),
            "after_value": float(fields[2]),
            "risk_cost": float(fields[3]),
            "continuity": float(fields[4]),
            "pv_gain": float(fields[5]),
            "future_shot_gain": float(fields[6]),
            "carry_to_shoot_window": float(fields[7]),
            "effective_gain": float(fields[8]),
            "near_goal_multiplier": float(fields[9]),
            "release_pressure": float(fields[10]),
            "space_manipulation": float(fields[11]),
        }

    for (
        case_id,
        carrier_index,
        carrier_pos,
        target,
        finishing,
        long_shot,
        consecutive_carries,
        possession_ticks,
        target_pv,
        current_pv,
        current_state_value,
        path_feasibility,
        attacking_right,
        opponents,
        teammates,
    ) in cases:
        carrier = _teammate(carrier_index, carrier_pos[0], carrier_pos[1], finishing, long_shot)
        carrier.consecutive_carries = consecutive_carries
        carrier.possession_ticks = possession_ticks
        py_teammates = []
        for idx, x, y, bx, by, is_gk in teammates:
            player = _teammate(idx, x, y, finishing if idx == carrier_index else 70, long_shot if idx == carrier_index else 70)
            player.base_formation_pos = (bx, by)
            if is_gk:
                player.position = "GK"
            py_teammates.append(player)
        py_opponents = [_opponent(idx + 100, ox, oy) for idx, (ox, oy) in enumerate(opponents)]
        py_value = evaluate_carry_target(
            carrier,
            target,
            target_pv,
            current_pv,
            current_state_value,
            path_feasibility,
            py_teammates,
            py_opponents,
            config,
            pitch,
            attacking_right,
        )
        rust = rust_rows[case_id]
        assert abs(rust["score"] - py_value.score) < 1e-12
        assert abs(rust["after_value"] - py_value.after_value) < 1e-12
        assert abs(rust["risk_cost"] - py_value.risk_cost) < 1e-12
        assert abs(rust["continuity"] - py_value.components["continuity"]) < 1e-12
        assert abs(rust["pv_gain"] - py_value.components["pv_gain"]) < 1e-12
        assert abs(rust["future_shot_gain"] - py_value.components["future_shot_gain"]) < 1e-12
        assert abs(rust["carry_to_shoot_window"] - py_value.components["carry_to_shoot_window"]) < 1e-12
        assert abs(rust["effective_gain"] - py_value.components["effective_gain"]) < 1e-12
        assert abs(rust["near_goal_multiplier"] - py_value.components["near_goal_multiplier"]) < 1e-12
        assert abs(rust["release_pressure"] - py_value.components["release_pressure"]) < 1e-12
        assert abs(rust["space_manipulation"] - py_value.components["space_manipulation"]) < 1e-12


def _interaction_player(index: int, x: float, y: float, speed: int = 80, defence: int = 80) -> Player:
    player = _teammate(index, x, y)
    player.abilities["Speed"] = speed
    player.abilities["Defence"] = defence
    player.abilities["Tackling"] = defence
    return player


def test_rust_detect_duel_matches_python():
    config = EngineConfig()
    cases = [
        (
            "path_duel",
            (80.0, 34.0),
            "carry",
            (92.0, 34.0),
            [
                (2, 86.0, 37.0, 86.0, 34.5, "approach", 80, 80),
                (3, 92.0, 50.0, 92.0, 50.0, "hold", 80, 80),
            ],
        ),
        (
            "no_duel_on_pass",
            (80.0, 34.0),
            "pass",
            (92.0, 34.0),
            [(2, 86.0, 34.0, 86.0, 34.0, "tackle", 80, 80)],
        ),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "detect_duel"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([
                str(holder[0]),
                str(holder[1]),
                action,
                str(target[0]),
                str(target[1]),
                str(config.tackle_range),
                _defender_actions_payload(defenders),
                case_id,
            ])
            for case_id, holder, action, target, defenders in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        case_id, defender_idx, dist = line.split("\t")
        rust_rows[case_id] = (None if defender_idx == "-" else int(defender_idx), float(dist))

    for case_id, holder_pos, action, target, defenders in cases:
        holder = _interaction_player(9, *holder_pos)
        py_defenders = [_interaction_player(idx, x, y, speed, defence) for idx, x, y, _, _, _, speed, defence in defenders]
        defender_new_positions = {idx: (nx, ny) for idx, _, _, nx, ny, _, _, _ in defenders}
        defender_actions = {idx: action_name for idx, _, _, _, _, action_name, _, _ in defenders}
        interaction = detect_duel(
            holder,
            action,
            py_defenders,
            defender_actions,
            config,
            defender_new_positions=defender_new_positions,
            carry_target=target,
        )
        rust_idx, rust_dist = rust_rows[case_id]
        if interaction is None:
            assert rust_idx is None
        else:
            assert rust_idx == interaction.defender.index
            assert abs(rust_dist - interaction.distance) < 1e-12


def test_rust_detect_interception_matches_python():
    config = EngineConfig()
    cases = [
        (
            "intercept",
            (40.0, 34.0),
            (72.0, 34.0),
            [(2, 56.0, 38.0, 56.0, 34.8, "block_lane", 80, 80)],
        ),
        (
            "clear",
            (40.0, 34.0),
            (72.0, 34.0),
            [(2, 56.0, 48.0, 56.0, 48.0, "block_lane", 80, 80)],
        ),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "detect_interception"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([
                str(origin[0]),
                str(origin[1]),
                str(target[0]),
                str(target[1]),
                str(config.interception_reach),
                _defender_actions_payload(defenders),
                case_id,
            ])
            for case_id, origin, target, defenders in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust_rows = {}
    for line in proc.stdout.strip().splitlines():
        case_id, defender_idx, dist = line.split("\t")
        rust_rows[case_id] = (None if defender_idx == "-" else int(defender_idx), float(dist))

    for case_id, origin, target, defenders in cases:
        py_defenders = [_interaction_player(idx, x, y, speed, defence) for idx, x, y, _, _, _, speed, defence in defenders]
        defender_new_positions = {idx: (nx, ny) for idx, _, _, nx, ny, _, _, _ in defenders}
        interaction = detect_interception(origin, target, py_defenders, defender_new_positions, config)
        rust_idx, rust_dist = rust_rows[case_id]
        if interaction is None:
            assert rust_idx is None
        else:
            assert rust_idx == interaction.defender.index
            assert abs(rust_dist - interaction.distance) < 1e-12


def test_rust_detect_wasted_tackle_matches_python():
    config = EngineConfig()
    holder_pos = (70.0, 34.0)
    defenders = [
        (2, 74.0, 34.0, 74.0, 34.0, "tackle", 80, 80),
        (3, 84.0, 34.0, 84.0, 34.0, "tackle", 80, 80),
        (4, 72.0, 42.0, 72.0, 42.0, "approach", 80, 80),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "detect_wasted_tackle"],
        cwd=RUST_CRATE,
        input="\t".join([
            str(holder_pos[0]),
            str(holder_pos[1]),
            "pass",
            str(config.tackle_range),
            _defender_actions_payload(defenders),
            "wasted",
        ]),
        text=True,
        capture_output=True,
        check=True,
    )
    _, payload = proc.stdout.strip().split("\t")
    rust = [] if payload == "-" else [
        (int(item.split(":")[0]), float(item.split(":")[1]))
        for item in payload.split(";")
    ]
    holder = _interaction_player(9, *holder_pos)
    py_defenders = [_interaction_player(idx, x, y, speed, defence) for idx, x, y, _, _, _, speed, defence in defenders]
    defender_actions = {idx: action_name for idx, _, _, _, _, action_name, _, _ in defenders}
    py = detect_wasted_tackle(holder, "pass", py_defenders, defender_actions, config)
    assert [idx for idx, _ in rust] == [interaction.defender.index for interaction in py]
    for (_, rust_dist), interaction in zip(rust, py):
        assert abs(rust_dist - interaction.distance) < 1e-12


def test_rust_detect_interactions_adapter_matches_python_bundle():
    config = EngineConfig()
    holder_pos = (70.0, 34.0)
    defenders = [
        (2, 74.0, 34.0, 74.0, 34.0, "tackle", 80, 80),
        (3, 82.0, 38.0, 82.0, 34.4, "block_lane", 80, 80),
        (4, 90.0, 50.0, 90.0, 50.0, "approach", 80, 80),
    ]
    rows = _run_rust_rows("detect_interactions", [
        "\t".join([
            str(holder_pos[0]),
            str(holder_pos[1]),
            "pass",
            "90.0",
            "34.0",
            str(config.tackle_range),
            str(config.interception_reach),
            _defender_actions_payload(defenders),
            "bundle",
            "bundle",
        ])
    ])
    rust = rows["bundle"]
    holder = _interaction_player(9, *holder_pos)
    py_defenders = [_interaction_player(idx, x, y, speed, defence) for idx, x, y, _, _, _, speed, defence in defenders]
    defender_actions = {idx: action_name for idx, _, _, _, _, action_name, _, _ in defenders}
    defender_new_positions = {idx: (nx, ny) for idx, _, _, nx, ny, _, _, _ in defenders}
    py_duel = detect_duel(
        holder,
        "pass",
        py_defenders,
        defender_actions,
        config,
        defender_new_positions,
        carry_target=(90.0, 34.0),
    )
    py_interception = detect_interception(holder_pos, (90.0, 34.0), py_defenders, defender_new_positions, config)
    py_wasted = detect_wasted_tackle(holder, "pass", py_defenders, defender_actions, config)

    assert rust[0] == ("-" if py_duel is None else str(py_duel.defender.index))
    assert rust[2] == ("-" if py_interception is None else str(py_interception.defender.index))
    if py_interception is not None:
        assert abs(float(rust[3]) - py_interception.distance) < 1e-12
    rust_wasted = [] if rust[4] == "-" else [
        (int(item.split(":")[0]), float(item.split(":")[1]))
        for item in rust[4].split(";")
    ]
    assert [idx for idx, _ in rust_wasted] == [interaction.defender.index for interaction in py_wasted]
    for (_, rust_dist), interaction in zip(rust_wasted, py_wasted):
        assert abs(rust_dist - interaction.distance) < 1e-12


def test_rust_resolve_duel_matches_python_with_explicit_rolls():
    config = EngineConfig()
    cases = [
        ("attacker", 84, 72, 8.0, -8.0),
        ("defender", 70, 86, -8.0, 8.0),
        ("loose", 80, 80, 2.0, -2.0),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "resolve_duel"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([str(atk), str(defn), str(atk_roll), str(def_roll), case_id])
            for case_id, atk, defn, atk_roll, def_roll in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust = {
        case_id: outcome
        for case_id, outcome in (line.split("\t") for line in proc.stdout.strip().splitlines())
    }
    for case_id, atk, defn, atk_roll, def_roll in cases:
        attacker = _interaction_player(9, 70.0, 34.0)
        defender = _interaction_player(2, 72.0, 34.0)
        attacker.abilities["Dribbling"] = atk
        defender.abilities["Tackling"] = defn
        interaction = Interaction(InteractionType.DUEL, attacker, defender, 2.0)
        with patch("psl_core.engine_v2.interactions.random.uniform", side_effect=[atk_roll, def_roll]):
            py = resolve_duel(interaction, config)
        assert rust[case_id] == py.outcome.value


def test_rust_duel_phase_plan_matches_duel_outcome_and_loose_payload():
    config = EngineConfig()
    holder_pos = (70.0, 34.0)
    cases = [
        ("attacker", 84, 72, 8.0, -8.0, "0", 2),
        ("defender", 70, 86, -8.0, 8.0, "1", 2),
        ("loose", 80, 80, 2.0, -2.0, "2", 4),
    ]
    for case_id, atk, defn, atk_roll, def_roll, outcome_code, randoms_used in cases:
        plan = _run_rust_rows("duel_phase_plan", [
            "\t".join([
                str(holder_pos[0]),
                str(holder_pos[1]),
                str(config.pitch_length),
                str(config.pitch_width),
                str(atk),
                str(defn),
                str(atk_roll),
                str(def_roll),
                "0.25",
                "0.75",
                case_id,
            ])
        ])[case_id]
        resolve = _run_rust_rows("resolve_duel", [
            "\t".join([str(atk), str(defn), str(atk_roll), str(def_roll), "duel"])
        ])["duel"][0]
        expected_code = {"attacker_wins": "0", "defender_wins": "1", "loose_ball": "2"}[resolve]
        expected_loose = (
            holder_pos[0] + (-3.0 + 6.0 * 0.25),
            holder_pos[1] + (-2.0 + 4.0 * 0.75),
        )
        expected_loose = (
            max(0.5, min(config.pitch_length - 0.5, expected_loose[0])),
            max(0.5, min(config.pitch_width - 0.5, expected_loose[1])),
        )
        assert plan[0] == outcome_code == expected_code
        _assert_close_tuple(plan[1:3], expected_loose, eps=1e-12)
        assert int(plan[3]) == randoms_used


def test_rust_resolve_interception_matches_python_with_explicit_roll():
    config = EngineConfig()
    cases = [
        ("intercept", 84, 72, 0.8, 0.05),
        ("miss", 84, 72, 0.8, 0.95),
        ("far_min", 60, 90, 3.2, 0.10),
    ]
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "engine", "--", "resolve_interception"],
        cwd=RUST_CRATE,
        input="\n".join(
            "\t".join([str(defence), str(passer), str(distance_to_lane), str(config.interception_reach), str(rand), case_id])
            for case_id, defence, passer, distance_to_lane, rand in cases
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    rust = {}
    for line in proc.stdout.strip().splitlines():
        case_id, intercepted, chance = line.split("\t")
        rust[case_id] = (intercepted == "1", float(chance))
    for case_id, defence, passer, distance_to_lane, rand in cases:
        defender = _interaction_player(2, 56.0, 34.0)
        defender.abilities["Defence"] = defence
        interaction = Interaction(InteractionType.INTERCEPTION, None, defender, distance_to_lane)
        with patch("psl_core.engine_v2.interactions.random.random", return_value=rand):
            py = resolve_interception(interaction, passer, config)
        assert rust[case_id][0] == py


def test_rust_carry_execution_matches_python_formula():
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "433", "442", config=config)
    holder = match.home.players[9]
    holder.pos = (54.0, 35.0)
    holder.abilities["Speed"] = 82
    holder.abilities["Dribbling"] = 78
    holder.consecutive_carries = 3
    target = (66.0, 31.0)
    match.away.players[0].position = "GK"
    match.away.players[2].pos = (58.0, 34.0)
    match.away.players[3].pos = (62.0, 38.0)

    expected_speed, expected_difficulty = match._compute_carry_speed(holder, target, match.home)
    expected_pos = py_physics.move_toward(holder.pos, target, expected_speed)
    expected_pos = match.pitch.clamp(expected_pos[0], expected_pos[1])
    progress = expected_pos[0] / match.pitch.length
    centrality = 1.0 - min(1.0, abs(expected_pos[1] - match.pitch.width / 2.0) / (match.pitch.width / 2.0))
    final_third_control = max(0.0, min(1.0, (progress - 0.72) / 0.18)) * max(0.0, min(1.0, centrality))
    stale = 1.0 + max(0, holder.consecutive_carries - 1) * 0.24 * final_third_control
    expected_error = ((100 - holder.abilities["Dribbling"]) / config.carry_error_divisor) * expected_difficulty * stale
    opponents = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in match.away.players
    )
    rows = _run_rust_rows("carry_execution", [
        "\t".join([
            str(holder.pos[0]),
            str(holder.pos[1]),
            str(target[0]),
            str(target[1]),
            str(holder.speed_value),
            str(holder.abilities["Dribbling"]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.carrier_speed),
            str(config.carry_error_divisor),
            str(holder.consecutive_carries),
            "0.001",
            "0.25",
            opponents,
            "0.75",
            "carry_exec",
        ])
    ])
    rust = rows["carry_exec"]
    assert abs(float(rust[0]) - expected_speed) < 1e-12
    assert abs(float(rust[1]) - expected_difficulty) < 1e-12
    _assert_close_tuple(rust[2:4], expected_pos, eps=1e-12)
    assert abs(float(rust[5]) - expected_error) < 1e-12
    assert (rust[6] == "1") == (0.001 < expected_error)


def test_rust_carry_phase_plan_matches_execution_payload():
    config = EngineConfig()
    holder_pos = (54.0, 35.0)
    target = (66.0, 31.0)
    opponents_payload = ";".join([
        "58.0,34.0,0",
        "62.0,38.0,0",
        "100.0,34.0,1",
    ])
    common = [
        str(holder_pos[0]),
        str(holder_pos[1]),
        str(target[0]),
        str(target[1]),
        "82",
        "78",
        "1",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.carrier_speed),
        str(config.carry_error_divisor),
        "3",
    ]
    cases = [
        ("ok", ["0.99", "0.25", opponents_payload, "0.75"], 1),
        ("err", ["0.001", "0.25", opponents_payload, "0.75"], 3),
    ]
    for case_id, random_fields, expected_randoms in cases:
        execution = _run_rust_rows("carry_execution", [
            "\t".join([*common, *random_fields, f"{case_id}_exec"])
        ])[f"{case_id}_exec"]
        plan = _run_rust_rows("carry_phase_plan", [
            "\t".join([*common, *random_fields, f"{case_id}_plan"])
        ])[f"{case_id}_plan"]
        assert plan[0:9] == execution[0:9]
        assert int(plan[9]) == expected_randoms


def test_rust_pass_execution_matches_python_formula():
    config = EngineConfig()
    passer = _interaction_player(9, 42.0, 34.0)
    passer.abilities["Short_Passing"] = 74
    ideal_target = (75.0, 42.0)
    opponents = [
        _interaction_player(2, 46.0, 34.0),
        _interaction_player(3, 55.0, 38.0),
        _interaction_player(0, 100.0, 34.0),
    ]
    opponents[2].position = "GK"
    lane_risk = 0.18
    passing = passer.abilities["Short_Passing"]
    dist_to_target = py_physics.distance(passer.pos, ideal_target)
    pressure = sum(1 for o in opponents if not o.is_goalkeeper and py_physics.distance(o.pos, passer.pos) < 8.0)
    ability_factor = max(0.0, min(1.0, passing / 100.0))
    error_radius = (
        (1.0 - ability_factor) * (1.2 + dist_to_target / 12.0)
        + pressure * 0.35
        + lane_risk * 2.5
    )
    randoms = [0.125, 0.65, 0.01, 0.25, 0.75]
    angle = randoms[0] * 6.283185307179586
    mag = randoms[1] * error_radius
    import math
    expected_target = (
        ideal_target[0] + math.cos(angle) * mag,
        ideal_target[1] + math.sin(angle) * mag,
    )
    expected_target = (
        max(0.5, min(config.pitch_length - 0.5, expected_target[0])),
        max(0.5, min(config.pitch_width - 0.5, expected_target[1])),
    )
    expected_error_chance = (100 - passing) / config.pass_error_divisor
    expected_stray = (
        ideal_target[0] + (-8.0 + 16.0 * randoms[3]),
        ideal_target[1] + (-8.0 + 16.0 * randoms[4]),
    )
    expected_stray = (
        max(0.5, min(config.pitch_length - 0.5, expected_stray[0])),
        max(0.5, min(config.pitch_width - 0.5, expected_stray[1])),
    )
    opponents_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    )
    rows = _run_rust_rows("pass_execution", [
        "\t".join([
            str(passer.pos[0]),
            str(passer.pos[1]),
            str(ideal_target[0]),
            str(ideal_target[1]),
            str(passing),
            "0",
            str(lane_risk),
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.ball_pass_speed),
            str(config.ball_long_pass_speed),
            opponents_payload,
            str(config.pass_error_divisor),
            *[str(value) for value in randoms],
            "pass_exec",
        ])
    ])
    rust = rows["pass_exec"]
    _assert_close_tuple(rust[0:2], expected_target, eps=1e-10)
    assert abs(float(rust[2]) - error_radius) < 1e-12
    assert abs(float(rust[3]) - expected_error_chance) < 1e-12
    assert rust[4] == "1"
    assert rust[5] == "1"
    assert int(rust[6]) == 5
    _assert_close_tuple(rust[7:9], expected_stray, eps=1e-12)


def test_rust_pass_phase_plan_matches_execution_trace_and_interception_payloads():
    config = EngineConfig()
    passer_pos = (42.0, 34.0)
    ideal_target = (75.0, 42.0)
    passing = 90
    lane_risk = 0.18
    randoms = [0.125, 0.65, 0.50, 0.25, 0.75]
    opponents_payload = ";".join([
        "46.0,34.0,0",
        "55.0,38.0,0",
        "100.0,34.0,1",
    ])
    pass_exec = _run_rust_rows("pass_execution", [
        "\t".join([
            str(passer_pos[0]),
            str(passer_pos[1]),
            str(ideal_target[0]),
            str(ideal_target[1]),
            str(passing),
            "0",
            str(lane_risk),
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.ball_pass_speed),
            str(config.ball_long_pass_speed),
            opponents_payload,
            str(config.pass_error_divisor),
            *[str(value) for value in randoms],
            "pass_exec",
        ])
    ])["pass_exec"]
    trace = _run_rust_rows("pass_trace_payload", [
        "\t".join([
            pass_exec[0],
            pass_exec[1],
            "70.0",
            "42.0",
            "0",
            "pass_trace",
        ])
    ])["pass_trace"]
    frame = _run_rust_rows("ball_flight_frame", [
        "\t".join([
            str(passer_pos[0]),
            str(passer_pos[1]),
            pass_exec[0],
            pass_exec[1],
            "pass",
            "0",
            "flight",
        ])
    ])["flight"]
    interception_roll = randoms[int(pass_exec[6])]
    intercepted = _run_rust_rows("resolve_interception", [
        "\t".join([
            "90",
            str(passing),
            "0.4",
            str(config.interception_reach),
            str(interception_roll),
            "interception",
        ])
    ])["interception"][0] == "1"
    expected_outcome = "1" if pass_exec[4] == "1" else ("2" if intercepted else "0")

    plan = _run_rust_rows("pass_phase_plan", [
        "\t".join([
            str(passer_pos[0]),
            str(passer_pos[1]),
            str(ideal_target[0]),
            str(ideal_target[1]),
            str(passing),
            "0",
            str(lane_risk),
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.ball_pass_speed),
            str(config.ball_long_pass_speed),
            opponents_payload,
            str(config.pass_error_divisor),
            *[str(value) for value in randoms],
            "1",
            "90",
            "0.4",
            str(config.interception_reach),
            "70.0",
            "42.0",
            "pass_plan",
        ])
    ])["pass_plan"]

    assert plan[0] == expected_outcome
    _assert_close_tuple(plan[1:3], [float(pass_exec[0]), float(pass_exec[1])], eps=1e-12)
    _assert_close_tuple(plan[3:5], [float(pass_exec[7]), float(pass_exec[8])], eps=1e-12)
    assert abs(float(plan[5]) - float(pass_exec[10])) < 1e-12
    assert int(plan[6]) == int(pass_exec[9])
    assert int(plan[7]) == int(pass_exec[11])
    assert plan[8:10] == trace
    _assert_close_tuple(plan[10:14], [float(value) for value in frame[0:4]], eps=1e-12)
    assert int(plan[14]) == int(pass_exec[6]) + 1


def test_rust_match_pass_stats_reports_completed_progression_fields():
    config = EngineConfig()
    rows = _run_rust_rows("match_stats", [
        "\t".join([
            "pass",
            "52.5",
            "34.0",
            "90.0",
            "34.0",
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
        ])
    ])
    assert rows["pass"] == ["0", "0", "1", "1", "1", "1", "1"]


def test_rust_shot_execution_matches_python_formula():
    import math

    config = EngineConfig()
    shooter_pos = (84.0, 35.0)
    cases = [
        ("on", True, 0.55, [0.10, 0.25, 0.90]),
        ("off", False, 0.20, [0.80, 0.40, 0.65]),
    ]
    rows = _run_rust_rows("shot_execution", [
        "\t".join([
            str(shooter_pos[0]),
            str(shooter_pos[1]),
            str(on_target_prob),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.goal_width),
            str(config.ball_shot_speed),
            *[str(value) for value in randoms],
            "0.0",
            case_id,
        ])
        for case_id, _expected_on_target, on_target_prob, randoms in cases
    ])
    for case_id, expected_on_target, on_target_prob, randoms in cases:
        goal_y_min = (config.pitch_width - config.goal_width) / 2.0
        goal_y_max = (config.pitch_width + config.goal_width) / 2.0
        if expected_on_target:
            target = (
                config.pitch_length,
                goal_y_min + 0.5 + randoms[1] * (goal_y_max - goal_y_min - 1.0),
            )
            used = 2
        else:
            target = (
                config.pitch_length + 0.5 + randoms[1] * 2.5,
                goal_y_min - 5.0 + randoms[2] * (config.goal_width + 10.0),
            )
            used = 3
        ticks = max(1, math.ceil(py_physics.distance(shooter_pos, target) / config.ball_shot_speed))
        rust = rows[case_id]
        assert (rust[0] == "1") is expected_on_target
        _assert_close_tuple(rust[1:3], target, eps=1e-12)
        assert int(rust[3]) == ticks
        assert int(rust[4]) == used


def test_rust_shot_phase_plan_matches_execution_xg_and_frame_payloads():
    config = EngineConfig()
    shooter_name = "Forward"
    shooter_pos = (84.0, 35.0)
    on_target_prob = 0.55
    randoms = [0.10, 0.25, 0.90]
    shot_exec = _run_rust_rows("shot_execution", [
        "\t".join([
            str(shooter_pos[0]),
            str(shooter_pos[1]),
            str(on_target_prob),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.goal_width),
            str(config.ball_shot_speed),
            *[str(value) for value in randoms],
            "0.0",
            "shot_exec",
        ])
    ])["shot_exec"]
    xg = _run_rust_rows("shot_xg", [
        "\t".join(["-", str(on_target_prob), str(config.goal_reward_constant), "shot_xg"])
    ])["shot_xg"][0]
    frame = _run_rust_rows("ball_flight_frame", [
        "\t".join([
            str(shooter_pos[0]),
            str(shooter_pos[1]),
            shot_exec[1],
            shot_exec[2],
            "shot",
            shot_exec[0],
            "flight",
        ])
    ])["flight"]

    plan = _run_rust_rows("shot_phase_plan", [
        "\t".join([
            shooter_name,
            str(shooter_pos[0]),
            str(shooter_pos[1]),
            "-",
            str(on_target_prob),
            str(config.goal_reward_constant),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.goal_width),
            str(config.ball_shot_speed),
            *[str(value) for value in randoms],
            "shot_plan",
        ])
    ])["shot_plan"]

    assert abs(float(plan[0]) - float(xg)) < 1e-12
    assert plan[1] == shot_exec[0]
    _assert_close_tuple(plan[2:4], [float(shot_exec[1]), float(shot_exec[2])], eps=1e-12)
    assert abs(float(plan[4]) - float(shot_exec[5])) < 1e-12
    assert abs(float(plan[5]) - float(shot_exec[6])) < 1e-12
    assert int(plan[6]) == int(shot_exec[3])
    assert int(plan[7]) == int(shot_exec[7])
    _assert_close_tuple(plan[8:12], [float(value) for value in frame[0:4]], eps=1e-12)
    assert int(plan[12]) == int(shot_exec[4])
    assert plan[13] == f"SHOT ON TARGET {shooter_name} shoots!"


def test_rust_clear_execution_matches_python_formula():
    import math

    config = EngineConfig()
    clearer_pos = (32.0, 22.0)
    target = (64.0, 48.0)
    rows = _run_rust_rows("clear_execution", [
        "\t".join([
            str(clearer_pos[0]),
            str(clearer_pos[1]),
            str(target[0]),
            str(target[1]),
            str(config.ball_long_pass_speed),
            "clear_exec",
        ])
    ])
    dist = py_physics.distance(clearer_pos, target)
    expected_ticks = max(1, math.ceil(dist / config.ball_long_pass_speed))
    rust = rows["clear_exec"]
    assert abs(float(rust[0]) - config.ball_long_pass_speed) < 1e-12
    assert int(rust[1]) == expected_ticks


def test_rust_clear_phase_plan_matches_execution_payload():
    config = EngineConfig()
    clearer_pos = (32.0, 22.0)
    target = (64.0, 48.0)
    execution = _run_rust_rows("clear_execution", [
        "\t".join([
            str(clearer_pos[0]),
            str(clearer_pos[1]),
            str(target[0]),
            str(target[1]),
            str(config.ball_long_pass_speed),
            "clear_exec",
        ])
    ])["clear_exec"]
    plan = _run_rust_rows("clear_phase_plan", [
        "\t".join([
            str(clearer_pos[0]),
            str(clearer_pos[1]),
            str(target[0]),
            str(target[1]),
            str(config.ball_long_pass_speed),
            "clear_plan",
        ])
    ])["clear_plan"]
    assert plan[0:4] == execution[2:6]
    assert abs(float(plan[4]) - float(execution[0])) < 1e-12
    assert int(plan[5]) == int(execution[1])
    assert int(plan[6]) == int(execution[6])


def test_rust_clear_target_matches_python_formula():
    config = EngineConfig()
    player = _vision_player(4, 30.0, 20.0)
    rows = _run_rust_rows("clear_target", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.25",
            "0.75",
            "clear_target",
        ])
    ])
    expected = (
        player.pos[0] + (15.0 + 0.25 * 15.0),
        player.pos[1] + (-20.0 + 0.75 * 40.0),
    )
    expected = (
        max(0.5, min(config.pitch_length - 0.5, expected[0])),
        max(0.5, min(config.pitch_width - 0.5, expected[1])),
    )
    _assert_close_tuple(rows["clear_target"], expected, eps=1e-12)


def test_rust_carry_offsets_match_python_sampling_formula():
    config = EngineConfig()
    player = _vision_player(7, 78.0, 52.0)
    player.abilities["Speed"] = 82
    player.abilities["Dribbling"] = 76
    opponents = [_opponent(20, 80.0, 54.0), _opponent(21, 88.0, 40.0)]
    attacking_right = True
    forward_dir = 1.0
    dribbling = player.abilities["Dribbling"] / 100.0
    max_speed = py_physics.player_speed(player.speed_value, config.player_max_speed, config.player_min_speed)
    base_dist = max(config.carrier_speed, max_speed * (0.42 + 0.18 * dribbling))
    expected = [
        (forward_dir * base_dist, 0.0),
        (forward_dir * base_dist * 0.75, base_dist * 0.75),
        (forward_dir * base_dist * 0.75, -base_dist * 0.75),
        (0.0, base_dist),
        (0.0, -base_dist),
    ]
    goal_center_y = config.pitch_width / 2.0
    center_pull = max(-base_dist, min(base_dist, goal_center_y - player.pos[1]))
    if abs(center_pull) > 0.25:
        expected.append((forward_dir * base_dist * 0.70, center_pull * 0.85))
        expected.append((forward_dir * base_dist * 0.35, center_pull))
    # Check the prefix and total count against Rust; full formula branches are
    # exercised by golden tests through the adapter.
    nearest_opp = min(py_physics.distance(player.pos, o.pos) for o in opponents if not o.is_goalkeeper)
    rows = _run_rust_rows("carry_offsets", [
        "\t".join([
            str(player.pos[0]),
            str(player.pos[1]),
            str(player.speed_value),
            str(player.abilities["Dribbling"]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.carrier_speed),
            str(nearest_opp),
            "carry_offsets",
        ])
    ])
    rust_offsets = [
        tuple(float(part) for part in item.split(","))
        for item in rows["carry_offsets"][0].split(";")
    ]
    assert len(rust_offsets) >= len(expected)
    for rust_item, expected_item in zip(rust_offsets, expected):
        _assert_close_tuple([str(value) for value in rust_item], expected_item, eps=1e-12)
    assert len(rust_offsets) == 23


def test_rust_carry_path_matches_python_formula():
    config = EngineConfig()
    carrier = _vision_player(7, 72.0, 42.0)
    carrier.abilities["Dribbling"] = 78
    target = (82.0, 35.0)
    opponents = [
        _opponent(20, 76.0, 40.0),
        _opponent(21, 86.0, 36.0),
    ]
    opponents[0].abilities.update({"Speed": 74, "Defence": 72, "Tackling": 76})
    opponents[1].abilities.update({"Speed": 81, "Defence": 80, "Tackling": 84})
    dx = target[0] - carrier.pos[0]
    dy = target[1] - carrier.pos[1]
    feasibility = 1.0
    my_speed = max(config.carrier_speed, 0.1)
    time_i_carry = (dx * dx + dy * dy) ** 0.5 / my_speed
    path_min_perp = 99.0
    path_peak_threat = 0.0
    path_peak_proj = 0.0
    path_peak_final_third_control = 0.0
    path_peak_control_factor = 0.0
    move_len = (dx * dx + dy * dy) ** 0.5
    for opp in opponents:
        opp_dx = opp.pos[0] - carrier.pos[0]
        opp_dy = opp.pos[1] - carrier.pos[1]
        perp_dist = abs(opp_dx * (dy / move_len) - opp_dy * (dx / move_len))
        proj = (opp_dx * dx + opp_dy * dy) / (move_len * move_len)
        if proj < -0.5 or proj > 2.0:
            continue
        path_min_perp = min(path_min_perp, perp_dist)
        def_speed = (opp.abilities["Speed"] / 100.0) * config.player_max_speed
        time_def_reaches = perp_dist / max(def_speed, 0.1)
        speed_factor = 0.82 + 0.36 * (opp.abilities["Speed"] / 100.0)
        defence_factor = 0.82 + 0.30 * (opp.abilities["Defence"] / 100.0)
        control_range = config.tackle_range * 0.62 * speed_factor * defence_factor
        duel_control = (
            max(0.0, 1.0 - perp_dist / max(0.1, control_range))
            * max(0.0, min(1.0, (proj + 0.10) / 1.10))
            * max(0.0, min(1.0, (1.10 - proj) / 1.10))
        )
        if duel_control > 0.0:
            my_drib = carrier.abilities["Dribbling"] / 100.0
            def_tack = opp.abilities["Tackling"] / 100.0
            control_factor = def_tack / (my_drib + def_tack + 0.01)
            feasibility *= max(0.34, 1.0 - duel_control * control_factor * 0.46)
            path_peak_threat = max(path_peak_threat, duel_control)
        target_progress = target[0] / config.pitch_length
        central_lane = 1.0 - min(1.0, abs(target[1] - config.pitch_width / 2.0) / (config.pitch_width / 2.0))
        final_third_control = (
            max(0.0, min(1.0, (target_progress - 0.72) / 0.18))
            * central_lane
            * max(0.0, 1.0 - perp_dist / 5.8)
            * max(0.0, min(1.0, (proj + 0.15) / 1.15))
            * max(0.0, min(1.0, (1.15 - proj) / 1.15))
        )
        if final_third_control > 0.0:
            my_drib = carrier.abilities["Dribbling"] / 100.0
            def_tack = opp.abilities["Tackling"] / 100.0
            control_factor = def_tack / (my_drib + def_tack + 0.01)
            if final_third_control > path_peak_final_third_control:
                path_peak_final_third_control = final_third_control
                path_peak_proj = proj
                path_peak_control_factor = control_factor
            feasibility *= max(0.48, 1.0 - final_third_control * control_factor * 0.34)
        if time_def_reaches < time_i_carry:
            threat = max(0.0, 1.0 - time_def_reaches / time_i_carry)
            my_drib = carrier.abilities["Dribbling"] / 100.0
            def_tack = opp.abilities["Tackling"] / 100.0
            skill_factor = my_drib / (my_drib + def_tack + 0.01)
            if threat > path_peak_threat:
                path_peak_threat = threat
                path_peak_proj = proj
            feasibility *= max(0.2, 1.0 - threat * (1.0 - skill_factor))
    opponent_payload = ";".join(
        ",".join([
            str(o.pos[0]),
            str(o.pos[1]),
            str(o.abilities["Speed"]),
            str(o.abilities["Defence"]),
            str(o.abilities["Tackling"]),
            "0",
        ])
        for o in opponents
    )
    rows = _run_rust_rows("carry_path", [
        "\t".join([
            str(carrier.pos[0]),
            str(carrier.pos[1]),
            str(target[0]),
            str(target[1]),
            str(carrier.abilities["Dribbling"]),
            str(config.tackle_range),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.player_max_speed),
            str(config.carrier_speed),
            opponent_payload,
            "carry_path",
        ])
    ])
    rust = rows["carry_path"]
    expected = [
        feasibility,
        path_min_perp,
        path_peak_threat,
        path_peak_proj,
        path_peak_final_third_control,
        path_peak_control_factor,
    ]
    _assert_close_tuple(rust, expected, eps=1e-12)


def test_rust_carry_finalize_matches_python_formula():
    evaluator_score = 0.184
    feasibility = 0.63
    path_peak_threat = 0.42
    path_peak_final_third_control = 0.31
    consecutive_carries = 3
    conflict_load = max(path_peak_threat, path_peak_final_third_control)
    repeated_load = _test_smoothstep(0.0, 3.0, max(0, consecutive_carries))
    feasibility_loss = _test_smoothstep(0.0, 0.55, 1.0 - feasibility)
    conflict_cost = (conflict_load ** 1.35) * (
        0.020
        + 0.115 * repeated_load
        + 0.075 * feasibility_loss
        + 0.105 * repeated_load * feasibility_loss
    )
    expected_score = max(0.0, evaluator_score - conflict_cost)
    rows = _run_rust_rows("carry_finalize", [
        "\t".join([
            str(evaluator_score),
            str(feasibility),
            str(path_peak_threat),
            str(path_peak_final_third_control),
            str(consecutive_carries),
            "carry_finalize",
        ])
    ])
    rust = rows["carry_finalize"]
    _assert_close_tuple(rust, [expected_score, conflict_cost, repeated_load, feasibility_loss], eps=1e-12)


def test_rust_hold_execution_matches_python_formula():
    config = EngineConfig()
    holder_pos = (60.0, 36.0)
    dribbling = 76
    opponents = [
        _interaction_player(2, 57.0, 35.0),
        _interaction_player(3, 66.0, 39.0),
        _interaction_player(0, 100.0, 34.0),
    ]
    opponents[2].position = "GK"
    opportunity_target = (68.0, 42.0)
    pressure_x = 0.0
    pressure_y = 0.0
    pressure = 0.0
    nearest_dist = float("inf")
    for opp in opponents:
        if opp.is_goalkeeper:
            continue
        dx = holder_pos[0] - opp.pos[0]
        dy = holder_pos[1] - opp.pos[1]
        d = max(0.1, (dx * dx + dy * dy) ** 0.5)
        nearest_dist = min(nearest_dist, d)
        if d < 8.0:
            w = 1.0 - d / 8.0
            pressure += w
            pressure_x += (dx / d) * w
            pressure_y += (dy / d) * w
    to_target_x = opportunity_target[0] - holder_pos[0]
    to_target_y = opportunity_target[1] - holder_pos[1]
    target_len = max(0.1, (to_target_x * to_target_x + to_target_y * to_target_y) ** 0.5)
    opportunity_x = to_target_x / target_len * 0.22
    opportunity_y = to_target_y / target_len * 0.52
    norm = max(0.1, (pressure_x * pressure_x + pressure_y * pressure_y) ** 0.5)
    away_x = pressure_x / norm if pressure > 0.0 else 0.0
    away_y = pressure_y / norm if pressure > 0.0 else 0.0
    adjust_x = away_x * 0.70 + opportunity_x + 0.12
    adjust_y = away_y * 0.70 + opportunity_y
    adjust_norm = max(0.1, (adjust_x * adjust_x + adjust_y * adjust_y) ** 0.5)
    dribbling_factor = dribbling / 100.0
    max_adjust = 0.45 + 1.15 * dribbling_factor
    move_dist = min(max_adjust, 0.35 + pressure * 0.55 + 0.35)
    expected_pos = (
        holder_pos[0] + adjust_x / adjust_norm * move_dist,
        holder_pos[1] + adjust_y / adjust_norm * move_dist,
    )
    expected_pos = (
        max(0.5, min(config.pitch_length - 0.5, expected_pos[0])),
        max(0.5, min(config.pitch_width - 0.5, expected_pos[1])),
    )
    expected_error = max(0.0, pressure - 0.6) * (100 - dribbling) / (config.carry_error_divisor * 1.8)
    randoms = [0.001, 0.25, 0.75]
    expected_loose = (
        expected_pos[0] + (-2.0 + 4.0 * randoms[1]),
        expected_pos[1] + (-2.0 + 4.0 * randoms[2]),
    )
    expected_loose = (
        max(0.5, min(config.pitch_length - 0.5, expected_loose[0])),
        max(0.5, min(config.pitch_width - 0.5, expected_loose[1])),
    )
    opponents_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    )
    rows = _run_rust_rows("hold_execution", [
        "\t".join([
            str(holder_pos[0]),
            str(holder_pos[1]),
            str(dribbling),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.carry_error_divisor),
            opponents_payload,
            str(opportunity_target[0]),
            str(opportunity_target[1]),
            *[str(value) for value in randoms],
            "hold_exec",
        ])
    ])
    rust = rows["hold_exec"]
    _assert_close_tuple(rust[0:2], expected_pos, eps=1e-12)
    assert abs(float(rust[2]) - py_physics.distance(holder_pos, expected_pos)) < 1e-12
    assert abs(float(rust[3]) - pressure) < 1e-12
    assert abs(float(rust[4]) - nearest_dist) < 1e-12
    assert abs(float(rust[5]) - expected_error) < 1e-12
    assert (rust[6] == "1") == (randoms[0] < expected_error)
    _assert_close_tuple(rust[7:9], expected_loose, eps=1e-12)


def test_rust_hold_phase_plan_matches_execution_payload():
    config = EngineConfig()
    holder_pos = (60.0, 36.0)
    dribbling = 76
    opportunity_target = (68.0, 42.0)
    randoms = [0.001, 0.25, 0.75]
    opponents_payload = ";".join([
        "57.0,35.0,0",
        "66.0,39.0,0",
        "100.0,34.0,1",
    ])
    execution = _run_rust_rows("hold_execution", [
        "\t".join([
            str(holder_pos[0]),
            str(holder_pos[1]),
            str(dribbling),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.carry_error_divisor),
            opponents_payload,
            str(opportunity_target[0]),
            str(opportunity_target[1]),
            *[str(value) for value in randoms],
            "hold_exec",
        ])
    ])["hold_exec"]
    plan = _run_rust_rows("hold_phase_plan", [
        "\t".join([
            str(holder_pos[0]),
            str(holder_pos[1]),
            str(dribbling),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.carry_error_divisor),
            opponents_payload,
            str(opportunity_target[0]),
            str(opportunity_target[1]),
            *[str(value) for value in randoms],
            "hold_plan",
        ])
    ])["hold_plan"]
    assert plan == execution


def test_rust_pass_arrival_matches_python_formula():
    from psl_core.engine_v2.ball import BallFlight, FlightType
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "433", "442", config=config)
    flight = BallFlight(
        origin=(42.0, 34.0),
        target=(70.0, 38.0),
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=3,
        passer_idx=9,
        passer_team="home",
        intended_receiver_idx=8,
    )
    match.home.players[8].pos = (65.0, 37.0)
    match.home.players[8].target_pos = (69.0, 38.0)
    match.away.players[2].pos = (68.0, 39.0)
    match.away.players[2].target_pos = (69.5, 38.5)
    target = flight.target
    best_receiver, receiver_score, _ = match._best_pass_arrival_player(
        flight,
        target,
        match.home,
        intended_receiver_idx=flight.intended_receiver_idx,
        target_occupation_weight=0.18,
    )
    best_opp, opponent_score, _ = match._best_pass_arrival_player(
        flight,
        target,
        match.away,
        intended_receiver_idx=-1,
        target_occupation_weight=0.18,
    )
    receiver_control = match._pass_control_strength(receiver_score)
    opponent_control = match._pass_control_strength(opponent_score)
    loose_control = match._pass_loose_control_strength(receiver_control, opponent_control)
    winner = max(
        (("receiver", receiver_control), ("opponent", opponent_control), ("loose", loose_control)),
        key=lambda item: item[1],
    )[0]

    def payload(players, is_passer_team):
        parts = []
        for p in players:
            parts.append(",".join([
                str(p.index),
                str(p.pos[0]),
                str(p.pos[1]),
                str(p.target_pos[0]),
                str(p.target_pos[1]),
                "-",
                "-",
                str(p.speed_value),
                "1" if is_passer_team and p.index == flight.passer_idx else "0",
                "1" if is_passer_team and p.index == flight.intended_receiver_idx else "0",
                "1" if is_passer_team else "0",
            ]))
        return ";".join(parts)

    rows = _run_rust_rows("pass_arrival", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            str(flight.ticks_total),
            str(config.contest_radius),
            str(config.player_max_speed),
            str(config.player_min_speed),
            "0.18",
            payload(match.home.players, True),
            payload(match.away.players, False),
            "pass_arrival",
        ])
    ])
    rust = rows["pass_arrival"]
    winner_by_code = {"0": "receiver", "1": "opponent", "2": "loose"}
    assert winner_by_code[rust[0]] == winner
    assert int(rust[1]) == best_receiver.index
    assert abs(float(rust[2]) - receiver_score) < 1e-12
    assert abs(float(rust[3]) - receiver_control) < 1e-12
    assert int(rust[4]) == best_opp.index
    assert abs(float(rust[5]) - opponent_score) < 1e-12
    assert abs(float(rust[6]) - opponent_control) < 1e-12
    assert abs(float(rust[7]) - loose_control) < 1e-12


def test_rust_pass_arrival_plan_matches_arrival_and_residual_velocity_payloads():
    from psl_core.engine_v2.ball import BallFlight, FlightType
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "433", "442", config=config)
    flight = BallFlight(
        origin=(42.0, 34.0),
        target=(70.0, 38.0),
        flight_type=FlightType.SHORT_PASS,
        speed=config.ball_pass_speed,
        ticks_total=3,
        passer_idx=9,
        passer_team="home",
        intended_receiver_idx=8,
    )
    match.home.players[8].pos = (65.0, 37.0)
    match.home.players[8].target_pos = (69.0, 38.0)
    match.away.players[2].pos = (68.0, 39.0)
    match.away.players[2].target_pos = (69.5, 38.5)
    target = flight.target

    def payload(players, is_passer_team):
        parts = []
        for p in players:
            parts.append(",".join([
                str(p.index),
                str(p.pos[0]),
                str(p.pos[1]),
                str(p.target_pos[0]),
                str(p.target_pos[1]),
                "-",
                "-",
                str(p.speed_value),
                "1" if is_passer_team and p.index == flight.passer_idx else "0",
                "1" if is_passer_team and p.index == flight.intended_receiver_idx else "0",
                "1" if is_passer_team else "0",
            ]))
        return ";".join(parts)

    receivers_payload = payload(match.home.players, True)
    opponents_payload = payload(match.away.players, False)
    arrival = _run_rust_rows("pass_arrival", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            str(flight.ticks_total),
            str(config.contest_radius),
            str(config.player_max_speed),
            str(config.player_min_speed),
            "0.18",
            receivers_payload,
            opponents_payload,
            "pass_arrival",
        ])
    ])["pass_arrival"]
    residual = _run_rust_rows("physics", [
        "\t".join([
            "residual_ball_velocity",
            str(flight.origin[0]),
            str(flight.origin[1]),
            str(target[0]),
            str(target[1]),
            str(flight.speed),
            "0.26",
            "residual",
        ])
    ])["residual"]
    plan = _run_rust_rows("pass_arrival_plan", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            str(flight.origin[0]),
            str(flight.origin[1]),
            str(flight.speed),
            str(flight.ticks_total),
            str(config.contest_radius),
            str(config.player_max_speed),
            str(config.player_min_speed),
            "0.18",
            "0.0",
            receivers_payload,
            opponents_payload,
            "pass_arrival_plan",
        ])
    ])["pass_arrival_plan"]

    assert plan[0] == arrival[0]
    assert plan[1] == arrival[1]
    assert plan[2] == arrival[4]
    _assert_close_tuple(plan[3:5], [float(residual[0]), float(residual[1])], eps=1e-12)
    assert abs(float(plan[5]) - float(arrival[2])) < 1e-12
    assert abs(float(plan[6]) - float(arrival[3])) < 1e-12
    assert abs(float(plan[7]) - float(arrival[5])) < 1e-12
    assert abs(float(plan[8]) - float(arrival[6])) < 1e-12
    assert abs(float(plan[9]) - float(arrival[7])) < 1e-12


def test_rust_pass_receive_plan_matches_first_touch_offside_and_receive_payloads():
    config = EngineConfig()
    receiver_pos = (68.0, 38.0)
    target_pos = (74.0, 42.0)
    iq = 78
    cases = [
        ("receive", "0", ["0.99", "0.25", "0.75"], "0", 1),
        ("touch_error", "0", ["0.001", "0.25", "0.75"], "1", 3),
        ("offside", "1", ["0.99", "0.25", "0.75"], "2", 1),
    ]
    for case_id, offside, randoms, expected_outcome, expected_randoms in cases:
        first_touch = _run_rust_rows("first_touch", [
            "\t".join([
                str(target_pos[0]),
                str(target_pos[1]),
                str(iq),
                str(config.pitch_length),
                str(config.pitch_width),
                str(config.first_touch_error_divisor),
                *randoms,
            ])
        ])["first_touch"]
        plan = _run_rust_rows("pass_receive_plan", [
            "\t".join([
                str(receiver_pos[0]),
                str(receiver_pos[1]),
                str(target_pos[0]),
                str(target_pos[1]),
                str(iq),
                offside,
                str(config.pitch_length),
                str(config.pitch_width),
                str(config.first_touch_error_divisor),
                *randoms,
                case_id,
            ])
        ])[case_id]
        assert plan[0] == expected_outcome
        _assert_close_tuple(plan[1:3], target_pos, eps=1e-12)
        _assert_close_tuple(plan[3:5], [float(first_touch[2]), float(first_touch[3])], eps=1e-12)
        assert abs(float(plan[5]) - py_physics.distance(receiver_pos, target_pos)) < 1e-12
        assert plan[6] == "1"
        assert abs(float(plan[7]) - float(first_touch[0])) < 1e-12
        assert int(plan[8]) == expected_randoms


def test_rust_shot_arrival_matches_python_formula():
    config = EngineConfig()
    gk = _interaction_player(0, 100.5, 34.0)
    gk.position = "GK"
    gk.abilities.update({"GK_Saving": 78, "GK_Positioning": 74, "GK_Reaction": 81})
    origin = (88.0, 35.5)
    target = (105.0, 36.0)
    save_prob = compute_gk_save_probability(gk, target, origin, config)
    in_box = (
        origin[0] / config.pitch_length > 1.0 - 16.5 / config.pitch_length
        and abs(origin[1] - config.pitch_width / 2.0) < 20.2
    )
    cases = [
        ("off", False, 0.0, 0),
        ("save", True, max(0.0, save_prob - 0.01), 1),
        ("goal", True, min(1.0, save_prob + 0.01), 2),
    ]
    rows = _run_rust_rows("shot_arrival", [
        "\t".join([
            str(origin[0]),
            str(origin[1]),
            str(target[0]),
            str(target[1]),
            "1",
            "1" if on_target else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(gk.pos[0]),
            str(gk.pos[1]),
            str(gk.abilities["GK_Saving"]),
            str(gk.abilities["GK_Positioning"]),
            str(gk.abilities["GK_Reaction"]),
            str(config.gk_position_error_factor),
            str(config.gk_reaction_delay_factor),
            str(config.gk_save_base),
            str(roll),
            case_id,
        ])
        for case_id, on_target, roll, _outcome in cases
    ])
    for case_id, on_target, _roll, outcome in cases:
        rust = rows[case_id]
        assert (rust[0] == "1") is in_box
        expected_save = save_prob if on_target else 0.0
        assert abs(float(rust[1]) - expected_save) < 1e-12
        assert int(rust[2]) == outcome


def test_rust_shot_arrival_plan_matches_arrival_log_and_event_payloads():
    config = EngineConfig()
    shooter_name = "Forward"
    keeper_name = "Keeper"
    origin = (88.0, 35.5)
    target = (105.0, 36.0)
    gk = _interaction_player(0, 100.5, 34.0)
    gk.position = "GK"
    gk.abilities.update({"GK_Saving": 78, "GK_Positioning": 74, "GK_Reaction": 81})
    total_xg = 0.42
    logged_xg = 0.11
    base = [
        shooter_name,
        keeper_name,
        str(origin[0]),
        str(origin[1]),
        str(target[0]),
        str(target[1]),
        "1",
    ]
    common_tail = [
        str(config.pitch_length),
        str(config.pitch_width),
        str(gk.pos[0]),
        str(gk.pos[1]),
        str(gk.abilities["GK_Saving"]),
        str(gk.abilities["GK_Positioning"]),
        str(gk.abilities["GK_Reaction"]),
        str(config.gk_position_error_factor),
        str(config.gk_reaction_delay_factor),
        str(config.gk_save_base),
    ]
    arrival_common = [
        str(origin[0]),
        str(origin[1]),
        str(target[0]),
        str(target[1]),
        "1",
    ]
    cases = [
        ("off", "0", "0.0", "0", "off_target", ""),
        ("save", "1", "0.0", "1", "saved", keeper_name),
        ("goal", "1", "1.0", "2", "goal", keeper_name),
    ]
    for case_id, on_target, save_roll, outcome_code, outcome, event_keeper in cases:
        arrival = _run_rust_rows("shot_arrival", [
            "\t".join([
                *arrival_common,
                on_target,
                *common_tail,
                save_roll,
                case_id,
            ])
        ])[case_id]
        shot_log_xg = _run_rust_rows("shot_log_xg", [
            "\t".join([str(total_xg), str(logged_xg), "0", "xg"])
        ])["xg"]
        event = _run_rust_rows("shot_arrival_event", [
            "\t".join([shooter_name, event_keeper, outcome, "event"])
        ])["event"]
        log_target = [str(target[0]), str(target[1])] if on_target == "1" else ["-", "-"]
        shot_log = _run_rust_rows("shot_log_entry", [
            "\t".join([
                str(origin[0]),
                str(origin[1]),
                *log_target,
                shot_log_xg[1],
                arrival[0],
                outcome,
                "log",
            ])
        ])["log"]
        plan = _run_rust_rows("shot_arrival_plan", [
            "\t".join([
                *base,
                on_target,
                *common_tail,
                save_roll,
                str(total_xg),
                str(logged_xg),
            ])
        ])["shot_arrival_plan"]

        assert plan[0] == outcome_code
        assert plan[1] == arrival[0]
        assert abs(float(plan[2]) - float(arrival[1])) < 1e-12
        assert abs(float(plan[3]) - float(shot_log_xg[0])) < 1e-12
        assert abs(float(plan[4]) - float(shot_log_xg[1])) < 1e-12
        expected_psxg = max(0.0, float(shot_log_xg[0])) if on_target == "1" else 0.0
        assert abs(float(plan[5]) - expected_psxg) < 1e-12
        assert plan[6:8] == shot_log[0:2]
        assert plan[8] == shot_log[4]
        if on_target == "1":
            _assert_close_tuple(plan[9:11], [float(shot_log[5]), float(shot_log[6])], eps=1e-12)
        else:
            assert plan[9:11] == ["-", "-"]
        assert int(float(plan[11])) == int(event[1])
        assert plan[12] == event[2]
        assert plan[13] == event[0]
        assert plan[14] == shot_log[3]


def test_rust_clearance_arrival_matches_python_closest_player():
    target = (60.0, 34.0)
    home_players = [
        (0, 20.0, 34.0),
        (4, 58.0, 33.0),
    ]
    away_players = [
        (0, 100.0, 34.0),
        (5, 63.0, 35.0),
    ]
    rows = _run_rust_rows("clearance_arrival", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
            ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
            "0.0",
            "clearance_arrival",
        ])
    ])
    rust = rows["clearance_arrival"]
    assert rust[0] == "0"
    assert int(rust[1]) == 4
    assert abs(float(rust[2]) - py_physics.distance((58.0, 33.0), target)) < 1e-12
    assert abs(float(rust[3]) - py_physics.distance((63.0, 35.0), target)) < 1e-12

    tie_rows = _run_rust_rows("clearance_arrival", [
        "\t".join([
            "50.0",
            "34.0",
            "1,49.0,34.0",
            "2,51.0,34.0",
            "0.0",
            "tie",
        ])
    ])
    assert tie_rows["tie"][0] == "1"
    assert int(tie_rows["tie"][1]) == 2


def test_rust_clearance_arrival_plan_matches_winner_and_completion_payload():
    target = (60.0, 34.0)
    home_players = [
        (0, 20.0, 34.0),
        (4, 58.0, 33.0),
    ]
    away_players = [
        (0, 100.0, 34.0),
        (5, 63.0, 35.0),
    ]
    for passer_home, expected_completed in (("1", "1"), ("0", "0")):
        arrival = _run_rust_rows("clearance_arrival", [
            "\t".join([
                str(target[0]),
                str(target[1]),
                ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
                ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
                "0.0",
                "clearance_arrival",
            ])
        ])["clearance_arrival"]
        plan = _run_rust_rows("clearance_arrival_plan", [
            "\t".join([
                str(target[0]),
                str(target[1]),
                ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
                ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
                passer_home,
                "0.0",
                "clearance_plan",
            ])
        ])["clearance_plan"]
        assert plan[0] == arrival[0]
        assert plan[1] == arrival[1]
        assert plan[2] == expected_completed
        assert abs(float(plan[3]) - float(arrival[2])) < 1e-12
        assert abs(float(plan[4]) - float(arrival[3])) < 1e-12


def test_rust_contested_owner_and_targets_match_python_formula():
    config = EngineConfig()
    ball_pos = (52.0, 34.0)
    home_players = [(1, 56.0, 34.0), (2, 60.0, 40.0)]
    away_players = [(3, 54.0, 33.0), (4, 70.0, 34.0)]
    rows = _run_rust_rows("contested_owner", [
        "\t".join([
            str(ball_pos[0]),
            str(ball_pos[1]),
            str(config.contest_radius),
            "1",
            ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
            ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
            "owner",
        ])
    ])
    rust = rows["owner"]
    assert rust[0] == "1"
    assert int(rust[1]) == 3
    assert abs(float(rust[2]) - py_physics.distance((54.0, 33.0), ball_pos)) < 1e-12
    assert rust[3] == "1"
    assert rust[4] == "0"

    plan_start = (52.0, 34.0)
    loose_velocity = (1.2, -0.4)
    tick_rows = _run_rust_rows("contested_tick", [
        "\t".join([
            str(plan_start[0]),
            str(plan_start[1]),
            str(loose_velocity[0]),
            str(loose_velocity[1]),
            "4",
            "tick",
        ])
    ])
    tick = tick_rows["tick"]
    clamped_tick_pos = (
        max(0.5, min(config.pitch_length - 0.5, float(tick[0]))),
        max(0.5, min(config.pitch_width - 0.5, float(tick[1]))),
    )
    owner_after_tick = _run_rust_rows("contested_owner", [
        "\t".join([
            str(clamped_tick_pos[0]),
            str(clamped_tick_pos[1]),
            str(config.contest_radius),
            tick[4],
            ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
            ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
            "owner_after_tick",
        ])
    ])["owner_after_tick"]
    plan = _run_rust_rows("contested_tick_plan", [
        "\t".join([
            str(plan_start[0]),
            str(plan_start[1]),
            str(loose_velocity[0]),
            str(loose_velocity[1]),
            "4",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.contest_radius),
            ";".join(f"{idx},{x},{y}" for idx, x, y in home_players),
            ";".join(f"{idx},{x},{y}" for idx, x, y in away_players),
            "plan",
        ])
    ])["plan"]
    _assert_close_tuple(plan[0:2], clamped_tick_pos, eps=1e-12)
    _assert_close_tuple(plan[2:4], [float(tick[2]), float(tick[3])], eps=1e-12)
    assert int(plan[4]) == int(tick[4])
    assert plan[5:10] == owner_after_tick[0:5]

    target_players = [
        (1, 56.0, 34.0, 58.0, 35.0, 0, 0, 80, 78),
        (2, 72.0, 46.0, 70.0, 42.0, 0, 0, 64, 70),
        (0, 20.0, 34.0, 18.0, 34.0, 1, 0, 60, 72),
        (5, 40.0, 34.0, 45.0, 34.0, 0, 1, 70, 70),
    ]
    target_rows = _run_rust_rows("contested_targets", [
        "\t".join([
            str(ball_pos[0]),
            str(ball_pos[1]),
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.player_max_speed),
            str(config.player_min_speed),
            str(config.contested_race_radius),
            ";".join(",".join(str(value) for value in player) for player in target_players),
            "targets",
        ])
    ])
    rust_targets = {
        int(parts[0]): ((float(parts[1]), float(parts[2])), int(parts[3]))
        for parts in (
            item.split(",")
            for item in target_rows["targets"][0].split(";")
        )
    }
    assert 5 not in rust_targets
    expected = {}
    for idx, x, y, ax, ay, is_gk, is_stunned, speed_value, iq_value in target_players:
        if is_stunned:
            continue
        if is_gk:
            expected[idx] = ((ax, ay), 0)
            continue
        dist_to_ball = py_physics.distance((x, y), ball_pos)
        speed = py_physics.player_speed(speed_value, config.player_max_speed, config.player_min_speed)
        nearby = sum(
            1
            for other_idx, ox, oy, _oax, _oay, other_gk, _stunned, _speed, _iq in target_players
            if other_idx != idx
            and not other_gk
            and py_physics.distance((ox, oy), ball_pos) < dist_to_ball + 1.5
        )
        race_reach = config.contested_race_radius * (0.84 + 0.22 * speed / max(config.player_max_speed, 0.1))
        first_ball_value = max(0.0, 1.0 - dist_to_ball / max(1.0, race_reach))
        first_ball_value = first_ball_value * first_ball_value * (3.0 - 2.0 * first_ball_value)
        contest_score = first_ball_value * (1.08 + 0.34 * (iq_value / 100.0)) / (1.0 + nearby * 0.35)
        support_pos = (
            max(0.5, min(config.pitch_length - 0.5, ax * 0.88 + ball_pos[0] * 0.12)),
            max(0.5, min(config.pitch_width - 0.5, ay * 0.90 + ball_pos[1] * 0.10)),
        )
        support_dist = py_physics.distance((x, y), support_pos)
        support_score = (
            0.05
            + min(0.24, nearby * 0.08)
            + min(0.08, support_dist / 80.0)
            + (1.0 - first_ball_value) * 0.08
        )
        expected[idx] = (ball_pos, 1) if contest_score > support_score else (support_pos, 0)
    assert set(rust_targets) == set(expected)
    for idx, (target, intent) in expected.items():
        _assert_close_tuple([str(value) for value in rust_targets[idx][0]], target, eps=1e-12)
        assert rust_targets[idx][1] == intent


def test_rust_score_goal_plan_matches_goal_event_and_restart_payload():
    config = EngineConfig()
    scorer_name = "Striker"
    assister_name = "Playmaker"
    assister_color = "gold"
    tick = 123
    goal_event = _run_rust_rows("goal_event", [
        "\t".join([
            scorer_name,
            "home",
            "1",
            "2",
            "9",
            "home",
            "7",
            "11",
            assister_name,
            assister_color,
            "goal_event",
        ])
    ])["goal_event"]
    plan = _run_rust_rows("score_goal_plan", [
        "\t".join([
            scorer_name,
            "home",
            "away",
            "1",
            "2",
            "9",
            "home",
            "7",
            "11",
            assister_name,
            assister_color,
            str(tick),
            str(config.tick_duration),
            "score_goal",
        ])
    ])["score_goal"]
    assert plan[0:6] == goal_event[0:6]
    assert int(plan[6]) == int((tick * config.tick_duration) / 60.0)
    assert plan[7] == goal_event[6]
    assert int(plan[8]) == 3000
    assert plan[9] == "away"
    assert int(plan[10]) == 3

    no_assist = _run_rust_rows("score_goal_plan", [
        "\t".join([
            scorer_name,
            "away",
            "home",
            "1",
            "2",
            "9",
            "home",
            "7",
            "11",
            assister_name,
            assister_color,
            str(tick),
            str(config.tick_duration),
            "no_assist",
        ])
    ])["no_assist"]
    assert no_assist[2] == "0"
    assert no_assist[4] == ""
    assert no_assist[9] == "home"


def test_rust_give_ball_plan_matches_possession_transfer_payloads():
    cases = [
        ("cross_team", "0", "3", "1", "5", (72.0, 40.0), (50.0, 34.0), "1", "1"),
        ("same_team", "1", "2", "1", "5", (72.0, 40.0), None, "0", "0"),
        ("no_prev", "-", "-1", "0", "4", (60.0, 30.0), None, "0", "1"),
    ]
    for case_id, prev_team, prev_idx, new_team, new_idx, pos, receive_origin, clear_offside, clear_goals in cases:
        origin_x, origin_y = ("-", "-") if receive_origin is None else (str(receive_origin[0]), str(receive_origin[1]))
        plan = _run_rust_rows("give_ball_plan", [
            "\t".join([
                prev_team,
                prev_idx,
                new_team,
                new_idx,
                str(pos[0]),
                str(pos[1]),
                origin_x,
                origin_y,
                "0.0",
                case_id,
            ])
        ])[case_id]
        assert plan[0] == ("1" if prev_team != "-" and int(prev_idx) >= 0 else "0")
        assert plan[1] == prev_team
        assert plan[2] == prev_idx
        assert plan[3] == clear_offside
        assert plan[4] == clear_goals
        assert plan[5] == new_team
        assert plan[6] == new_idx
        _assert_close_tuple(plan[7:9], pos, eps=1e-12)
        expected_origin = receive_origin if receive_origin is not None else pos
        _assert_close_tuple(plan[9:11], expected_origin, eps=1e-12)


def test_rust_player_move_speed_matches_python_formula():
    import math

    config = EngineConfig()
    cases = [
        ("press", (40.0, 30.0), (55.0, 36.0), 82, "press", "off_ball"),
        ("near", (40.0, 30.0), (40.3, 30.2), 60, "support", "off_ball"),
        ("pressing_state", (40.0, 30.0), (55.0, 36.0), 70, "idle", "pressing"),
    ]
    for case_id, pos, target, speed, intent, state in cases:
        max_speed = py_physics.player_speed(speed, config.player_max_speed, config.player_min_speed)
        dist_to_target = py_physics.distance(pos, target)
        urgency = 1.0 - math.exp(-dist_to_target / 14.0)
        intent_base = {
            "idle": 0.08,
            "support": 0.36,
            "attack_run": 0.56,
            "recover_shape": 0.42,
            "defend_shape": 0.30,
            "press": 0.58,
            "contest": 0.78,
            "mark": 0.32,
            "block_lane": 0.30,
        }.get(intent, 0.36)
        if state == "pressing":
            intent_base = max(intent_base, 0.58)
        expected = max_speed * (intent_base + (0.28 * urgency))
        if dist_to_target < 1.0:
            expected *= 0.20
        expected = max(0.2, min(max_speed * 0.92, expected))
        row = _run_rust_rows("physics", [
            "\t".join([
                "player_move_speed",
                str(pos[0]),
                str(pos[1]),
                str(target[0]),
                str(target[1]),
                str(speed),
                intent,
                state,
                str(config.player_max_speed),
                str(config.player_min_speed),
            ])
        ])[case_id if False else "player_move_speed"]
        assert abs(float(row[0]) - expected) < 1e-12


def test_rust_player_set_movement_target_matches_python_smoothing_formula():
    cases = [
        ("initial", (0.0, 0.0), (50.0, 34.0), "idle", "support"),
        ("small_jump", (50.0, 34.0), (52.0, 35.0), "support", None),
        ("medium_attack", (50.0, 34.0), (60.0, 38.0), "support", "attack_run"),
        ("large_press", (50.0, 34.0), (80.0, 50.0), "support", "press"),
        ("defensive", (50.0, 34.0), (80.0, 50.0), "support", "defend_shape"),
    ]
    for case_id, current_target, requested_target, current_intent, requested_intent in cases:
        intent = requested_intent if requested_intent is not None else current_intent
        if current_target == (0.0, 0.0):
            expected_target = requested_target
        else:
            jump = py_physics.distance(current_target, requested_target)
            if jump < 4.0:
                blend = 0.75
            elif jump < 14.0:
                blend = 0.45
            else:
                blend = 0.22
            if intent == "attack_run":
                blend = min(0.92, blend + 0.54)
            elif intent in ("press", "contest"):
                blend = min(0.78, blend + 0.30)
            elif intent in ("defend_shape", "mark", "block_lane"):
                blend *= 0.85
            expected_target = (
                current_target[0] * (1.0 - blend) + requested_target[0] * blend,
                current_target[1] * (1.0 - blend) + requested_target[1] * blend,
            )
        row = _run_rust_rows("physics", [
            "\t".join([
                "player_set_movement_target",
                str(current_target[0]),
                str(current_target[1]),
                str(requested_target[0]),
                str(requested_target[1]),
                current_intent,
                "-" if requested_intent is None else requested_intent,
                case_id,
            ])
        ])[case_id]
        _assert_close_tuple(row[0:2], expected_target, eps=1e-12)
        assert row[2] == intent


def test_rust_player_move_tick_matches_python_movement_formula():
    import math
    from psl_core.engine_v2.pitch import Pitch

    config = EngineConfig()
    pitch = Pitch(config=config)
    cases = [
        ("press", (40.0, 30.0), (55.0, 36.0), (0.4, -0.2), 82, "press", "off_ball"),
        ("clamp", (104.2, 66.5), (110.0, 80.0), (2.0, 2.0), 90, "attack_run", "off_ball"),
        ("on_ball", (40.0, 30.0), (55.0, 36.0), (0.4, -0.2), 82, "press", "on_ball"),
    ]
    for _case_id, pos, target, velocity, speed, intent, state in cases:
        max_speed = py_physics.player_speed(speed, config.player_max_speed, config.player_min_speed)
        dist_to_target = py_physics.distance(pos, target)
        urgency = 1.0 - math.exp(-dist_to_target / 14.0)
        intent_base = {
            "idle": 0.08,
            "support": 0.36,
            "attack_run": 0.56,
            "recover_shape": 0.42,
            "defend_shape": 0.30,
            "press": 0.58,
            "contest": 0.78,
            "mark": 0.32,
            "block_lane": 0.30,
        }.get(intent, 0.36)
        if state == "pressing":
            intent_base = max(intent_base, 0.58)
        desired_speed = max_speed * (intent_base + (0.28 * urgency))
        if dist_to_target < 1.0:
            desired_speed *= 0.20
        desired_speed = max(0.2, min(max_speed * 0.92, desired_speed))
        if state in ("on_ball", "stunned"):
            expected = {
                "moved": False,
                "pos": pos,
                "velocity": velocity,
                "distance": 0.0,
                "facing": None,
                "desired": 0.0,
            }
        else:
            dx = target[0] - pos[0]
            dy = target[1] - pos[1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 0.05:
                desired_vx, desired_vy = 0.0, 0.0
            else:
                desired_vx = dx / dist * desired_speed
                desired_vy = dy / dist * desired_speed
            vx, vy = velocity
            accel = max_speed * 0.42
            if intent in ("press", "contest", "attack_run"):
                accel *= 1.18
            dvx = desired_vx - vx
            dvy = desired_vy - vy
            dv_len = math.sqrt(dvx * dvx + dvy * dvy)
            if dv_len > accel:
                dvx = dvx / dv_len * accel
                dvy = dvy / dv_len * accel
            vx += dvx
            vy += dvy
            max_velocity = max_speed * 0.95
            v_len = math.sqrt(vx * vx + vy * vy)
            if v_len > max_velocity:
                vx = vx / v_len * max_velocity
                vy = vy / v_len * max_velocity
            raw_pos = (pos[0] + vx, pos[1] + vy)
            new_pos = pitch.clamp(raw_pos[0], raw_pos[1])
            new_velocity = (0.0, 0.0) if new_pos != raw_pos else (vx, vy)
            distance_covered = py_physics.distance(pos, new_pos)
            facing = py_physics.angle_between_points(pos, new_pos) if distance_covered > 0.1 else None
            expected = {
                "moved": True,
                "pos": new_pos,
                "velocity": new_velocity,
                "distance": distance_covered,
                "facing": facing,
                "desired": desired_speed,
            }
        row = _run_rust_rows("physics", [
            "\t".join([
                "player_move_tick",
                str(pos[0]),
                str(pos[1]),
                str(target[0]),
                str(target[1]),
                str(velocity[0]),
                str(velocity[1]),
                str(speed),
                intent,
                state,
                str(config.player_max_speed),
                str(config.player_min_speed),
                str(config.pitch_length),
                str(config.pitch_width),
            ])
        ])["player_move_tick"]
        assert (row[0] == "1") is expected["moved"]
        _assert_close_tuple(row[1:3], expected["pos"], eps=1e-12)
        _assert_close_tuple(row[3:5], expected["velocity"], eps=1e-12)
        assert abs(float(row[5]) - expected["distance"]) < 1e-12
        if expected["facing"] is None:
            assert row[6] == "-"
        else:
            assert abs(float(row[6]) - expected["facing"]) < 1e-12
        assert abs(float(row[7]) - expected["desired"]) < 1e-12


def test_rust_player_stun_helpers_match_python_formula():
    import math

    config = EngineConfig()
    apply_row = _run_rust_rows("physics", [
        "\t".join([
            "player_apply_stun",
            str(config.tackle_fail_stun_seconds),
            str(config.tick_duration),
            "apply",
        ])
    ])["apply"]
    assert apply_row[0] == "stunned"
    assert int(apply_row[1]) == max(1, math.ceil(config.tackle_fail_stun_seconds / config.tick_duration))

    cases = [
        ("zero", "stunned", 0, "stunned", 0),
        ("one", "stunned", 1, "off_ball", 0),
        ("two", "stunned", 2, "stunned", 1),
    ]
    for case_id, state, ticks, expected_state, expected_ticks in cases:
        row = _run_rust_rows("physics", [
            "\t".join([
                "player_tick_stun",
                state,
                str(ticks),
                case_id,
            ])
        ])[case_id]
        assert row[0] == expected_state
        assert int(row[1]) == expected_ticks


def test_rust_team_shape_plan_matches_legacy_dynamic_positions():
    from psl_core.engine_v2.match import MatchV2
    from psl_core.engine_v2.team import TeamPhase
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "4141", "433", config=config)
    ball_pos = (90.0, 18.0)
    match.home.phase = TeamPhase.ATTACKING
    match.away.players[1].pos = (87.0, 30.0)
    match.away.players[2].pos = (83.0, 38.0)

    match.home._compute_dynamic_positions_legacy(
        ball_pos,
        config,
        match.pitch,
        opponent_players=match.away.players,
    )
    expected = {player.index: player.tactical_anchor for player in match.home.players}
    players_payload = ";".join(
        ",".join([
            str(player.index),
            str(match.home._formation_coords[i][0]),
            str(match.home._formation_coords[i][1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for i, player in enumerate(match.home.players)
    )
    opponents_payload = ";".join(
        ",".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for player in match.away.players
    )
    rows = _run_rust_rows("team_shape_plan", [
        "\t".join([
            str(ball_pos[0]),
            str(ball_pos[1]),
            "1",
            "attacking",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.0",
            players_payload,
            opponents_payload,
            "team_shape",
        ])
    ])
    rust_anchors = {
        int(item.split(",")[0]): (float(item.split(",")[1]), float(item.split(",")[2]))
        for item in rows["team_shape"][0].split(";")
    }
    assert set(rust_anchors) == set(expected)
    for idx, anchor in expected.items():
        _assert_close_tuple([str(value) for value in rust_anchors[idx]], anchor, eps=1e-9)

    match.away.phase = TeamPhase.TRANSITION_DEF
    defending_ball = (45.0, 52.0)
    match.away._compute_dynamic_positions_legacy(
        defending_ball,
        config,
        match.pitch,
        opponent_players=match.home.players,
    )
    expected_def = {player.index: player.tactical_anchor for player in match.away.players}
    def_players_payload = ";".join(
        ",".join([
            str(player.index),
            str(match.away._formation_coords[i][0]),
            str(match.away._formation_coords[i][1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for i, player in enumerate(match.away.players)
    )
    home_opponents_payload = ";".join(
        ",".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for player in match.home.players
    )
    def_rows = _run_rust_rows("team_shape_plan", [
        "\t".join([
            str(defending_ball[0]),
            str(defending_ball[1]),
            "0",
            "transition_def",
            str(config.pitch_length),
            str(config.pitch_width),
            "0.0",
            def_players_payload,
            home_opponents_payload,
            "team_shape_def",
        ])
    ])
    rust_def = {
        int(item.split(",")[0]): (float(item.split(",")[1]), float(item.split(",")[2]))
        for item in def_rows["team_shape_def"][0].split(";")
    }
    assert set(rust_def) == set(expected_def)
    for idx, anchor in expected_def.items():
        _assert_close_tuple([str(value) for value in rust_def[idx]], anchor, eps=1e-9)


def test_rust_team_phase_update_matches_python_state_machine():
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    team = match.home
    cases = [
        ("contest", False, True, False, 99, "4", 99, "0"),
        ("won", True, False, False, 99, "1", 0, "1"),
        ("stable_atk", True, False, True, config.transition_ticks, "0", config.transition_ticks + 1, "1"),
        ("lost", False, False, True, 99, "3", 0, "0"),
        ("stable_def", False, False, False, config.transition_ticks, "2", config.transition_ticks + 1, "0"),
    ]
    for case_id, has_possession, contested, had_last, ticks, phase_code, expected_ticks, expected_had in cases:
        team._had_possession_last_tick = had_last
        team._ticks_since_possession_change = ticks
        row = _run_rust_rows("team_phase_update", [
            "\t".join([
                "1" if has_possession else "0",
                "1" if contested else "0",
                "1" if had_last else "0",
                str(ticks),
                str(config.transition_ticks),
                case_id,
            ])
        ])[case_id]
        assert row[0] == phase_code
        assert int(row[1]) == expected_ticks
        assert row[2] == expected_had

        team._had_possession_last_tick = had_last
        team._ticks_since_possession_change = ticks
        team._update_phase_legacy(has_possession, contested, config)
        phase_by_code = {
            "0": "attacking",
            "1": "transition_atk",
            "2": "defending",
            "3": "transition_def",
            "4": "contesting",
        }
        assert team.phase.value == phase_by_code[phase_code]
        assert team._ticks_since_possession_change == expected_ticks
        assert team._had_possession_last_tick == (expected_had == "1")


def test_rust_iq_noise_score_matches_python_formula():
    from psl_core.engine_v2.decision import iq_decision_noise

    config = EngineConfig()
    cases = [
        ("low_iq", 0.42, 65, -0.35),
        ("normal_iq", 0.42, 100, 0.20),
        ("elite_iq", 0.42, 128, 1.10),
    ]
    for case_id, score, iq, gaussian in cases:
        row = _run_rust_rows("iq_noise_score", [
            "\t".join([
                str(score),
                str(iq),
                str(config.iq_noise_scale),
                str(gaussian),
                case_id,
            ])
        ])[case_id]
        noise_scale = iq_decision_noise(iq) * config.iq_noise_scale
        expected = score * (1.0 + gaussian * noise_scale)
        assert abs(float(row[0]) - expected) < 1e-12
        assert abs(float(row[1]) - noise_scale) < 1e-12


def test_rust_match_v2_single_entrypoint_contract_shape():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig(total_ticks=0, half_ticks=0, frame_interval=1)
    response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        config,
        seed=20260709,
    )
    assert response["engine"] == "rust_match_v2"
    assert response["contract_version"] == 1
    for key in (
        "home_score",
        "away_score",
        "goals",
        "home_stats",
        "away_stats",
        "home_player_stats",
        "away_player_stats",
        "home_ratings",
        "away_ratings",
        "replay_url",
        "trace_id",
        "replay",
        "trace",
    ):
        assert key in response
    assert response["home_score"] == 0
    assert response["away_score"] == 0
    assert response["home_stats"]["possession"] == 50.0
    assert response["away_stats"]["possession"] == 50.0
    assert response["replay"][0]["type"] == "header"
    assert response["replay"][0]["formation_home"] == "433"
    assert response["replay"][0]["formation_away"] == "442"
    assert len(response["replay"][0]["home"]["players"]) == 11
    assert response["replay"][1]["type"] == "frame"
    assert response["replay"][1]["score"] == [0, 0]
    assert len(response["replay"][1]["home"]) == 11
    assert len(response["home_player_stats"]) == 11
    assert response["home_player_stats"][0]["position"] == "GK"
    assert response["home_player_stats"][9]["position"] == "ST"
    assert response["trace"]["entries"] == []

    running_config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    running = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        running_config,
        seed=20260709,
    )
    assert running["home_stats"]["possession"] + running["away_stats"]["possession"] == 100.0
    assert len(running["trace"]["entries"]) >= 4
    assert {"state", "action"}.issubset({entry["type"] for entry in running["trace"]["entries"]})
    assert any(entry["type"] == "action" for entry in running["trace"]["entries"])
    assert len(running["replay"]) >= 5

    selector_config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    selector_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        selector_config,
        seed=20260709,
    )
    selector_actions = {
        entry["action"]
        for entry in selector_response["trace"]["entries"]
        if entry["type"] == "action"
    }
    assert selector_actions & {"carry", "pass", "shot", "clear"}
    assert (
        selector_response["home_stats"]["carries"]
        + selector_response["away_stats"]["carries"]
        + selector_response["home_stats"]["passes"]
        + selector_response["away_stats"]["passes"]
        + selector_response["home_stats"]["shots"]
        + selector_response["away_stats"]["shots"]
        + selector_response["home_stats"]["clearances"]
        + selector_response["away_stats"]["clearances"]
    ) >= 1

    shot_config = EngineConfig(total_ticks=6, half_ticks=6, frame_interval=1)
    shot_config.runner_forced_action = "shot"
    shot_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        shot_config,
        seed=18,
    )
    actions = [entry for entry in shot_response["trace"]["entries"] if entry["type"] == "action"]
    events = [entry for entry in shot_response["trace"]["entries"] if entry["type"] == "event"]
    assert actions[0]["action"] == "shot"
    assert any(event["event"] == "shot_arrival" for event in events)


    carry_config = EngineConfig(total_ticks=2, half_ticks=2, frame_interval=1)
    carry_config.runner_forced_action = "carry"
    carry_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        carry_config,
        seed=20260709,
    )
    carry_actions = [entry for entry in carry_response["trace"]["entries"] if entry["type"] == "action"]
    assert carry_actions[0]["action"] == "carry"
    assert carry_response["home_stats"]["carries"] >= 1
    assert carry_response["home_player_stats"][9]["carries_completed"] >= 1
    assert carry_response["replay"][2]["ball"] != carry_response["replay"][1]["ball"]

    pass_config = EngineConfig(total_ticks=4, half_ticks=4, frame_interval=1)
    pass_config.runner_forced_action = "pass"
    pass_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        pass_config,
        seed=20260709,
    )
    pass_entries = pass_response["trace"]["entries"]
    assert any(entry.get("action") == "pass" for entry in pass_entries)
    assert any(entry.get("action") == "receive" or entry.get("event") in ("interception", "pass_loose") for entry in pass_entries)
    assert pass_response["home_stats"]["passes"] >= 1

    clear_config = EngineConfig(total_ticks=5, half_ticks=5, frame_interval=1)
    clear_config.runner_forced_action = "clear"
    clear_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        clear_config,
        seed=20260709,
    )
    clear_entries = clear_response["trace"]["entries"]
    assert any(entry.get("action") == "clear" for entry in clear_entries)
    assert any(entry.get("event") == "clearance_arrival" for entry in clear_entries)
    assert clear_response["home_stats"]["clearances"] >= 1

    move_config = EngineConfig(total_ticks=1, half_ticks=1, frame_interval=1)
    move_config.runner_forced_action = "hold"
    move_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        move_config,
        seed=20260709,
    )
    move_frames = [frame for frame in move_response["replay"] if frame["type"] == "frame"]
    assert len(move_frames) >= 2
    holder_idx = move_frames[0]["ball_holder"]
    assert any(
        idx != holder_idx and move_frames[0]["home"][idx] != move_frames[1]["home"][idx]
        for idx in range(11)
    )
    assert any(
        move_frames[0]["away"][idx] != move_frames[1]["away"][idx]
        for idx in range(11)
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "off_ball_choice"
        and entry.get("attack_choices", 0) > 0
        and entry.get("defense_choices", 0) > 0
        and entry.get("attack_goal_choices", 0) > 0
        and entry.get("defense_goal_choices", 0) > 0
        for entry in move_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "off_ball_goal"
        and entry.get("side") == "attack"
        and entry.get("goal_type")
        for entry in move_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "off_ball_goal"
        and entry.get("side") == "defense"
        and entry.get("goal_type", "").startswith("defend_")
        for entry in move_response["trace"]["entries"]
    )

    duel_home_cards = _cards()
    duel_away_cards = _cards()
    for card in duel_away_cards:
        card["abilities"]["Tackling"] = 99
        card["abilities"]["Defence"] = 99
        card["abilities"]["Speed"] = 90
    duel_config = EngineConfig(total_ticks=2, half_ticks=2, frame_interval=1)
    duel_config.runner_forced_action = "carry"
    duel_response = run_match_v2_rust(
        duel_home_cards,
        duel_away_cards,
        "433",
        "442",
        duel_config,
        seed=20260709,
    )
    duel_events = [
        entry
        for entry in duel_response["trace"]["entries"]
        if entry["type"] == "event" and entry.get("event") in {"tackle", "duel"}
    ]
    assert duel_events

    flight_move_config = EngineConfig(total_ticks=3, half_ticks=3, frame_interval=1)
    flight_move_config.runner_forced_action = "pass"
    flight_move_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        flight_move_config,
        seed=20260709,
    )
    flight_frames = [frame for frame in flight_move_response["replay"] if frame["type"] == "frame"]
    assert len(flight_frames) >= 3
    assert flight_frames[1]["ball_holder"] is None
    assert flight_frames[2]["ball_holder"] is None
    assert any(
        flight_frames[1]["home"][idx] != flight_frames[2]["home"][idx]
        for idx in range(11)
    )
    assert any(
        flight_frames[1]["away"][idx] != flight_frames[2]["away"][idx]
        for idx in range(11)
    )

    interception_home_cards = _cards()
    interception_away_cards = _cards()
    for card in interception_away_cards:
        card["abilities"]["Defence"] = 200
        card["abilities"]["Speed"] = 90
        card["abilities"]["Tackling"] = 99
    interception_config = EngineConfig(total_ticks=2, half_ticks=2, frame_interval=1)
    interception_config.runner_forced_action = "pass"
    interception_config.runner_forced_pass_target = (60.0, 34.0)
    interception_config.press_radius = 80
    interception_response = run_match_v2_rust(
        interception_home_cards,
        interception_away_cards,
        "433",
        "442",
        interception_config,
        seed=1,
    )
    assert any(
        entry["type"] == "event" and entry.get("event") == "interception"
        for entry in interception_response["trace"]["entries"]
    )
    assert any(player["interceptions"] > 0 for player in interception_response["away_player_stats"])
    assert any(player["pressures"] > 0 for player in interception_response["away_player_stats"])
    assert any(player["successful_pressures"] > 0 for player in interception_response["away_player_stats"])

    restart_home_cards, restart_away_cards, restart_config, restart_seed = (
        _forced_kickoff_restart_sample(_cards)
    )
    restart_response = run_match_v2_rust(
        restart_home_cards,
        restart_away_cards,
        "433",
        "442",
        restart_config,
        seed=restart_seed,
    )
    assert restart_response["home_score"] + restart_response["away_score"] >= 1
    assert restart_response["goals"]
    assert any(
        entry["type"] == "event" and entry.get("event") == "goal"
        for entry in restart_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "restart"
        and entry.get("reason") == "kickoff"
        for entry in restart_response["trace"]["entries"]
    )

    throw_in_config = EngineConfig(total_ticks=8, half_ticks=8, frame_interval=1)
    throw_in_config.runner_forced_action = "clear"
    throw_in_config.runner_forced_clear_target = (50.0, -5.0)
    throw_in_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        throw_in_config,
        seed=20260709,
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "out_of_bounds"
        and entry.get("reason") == "throw_in"
        for entry in throw_in_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "restart"
        and entry.get("reason") == "throw_in"
        for entry in throw_in_response["trace"]["entries"]
    )

    goal_kick_config = EngineConfig(total_ticks=12, half_ticks=12, frame_interval=1)
    goal_kick_config.runner_forced_action = "clear"
    goal_kick_config.runner_forced_clear_target = (106.0, 34.0)
    goal_kick_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        goal_kick_config,
        seed=20260709,
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "out_of_bounds"
        and entry.get("reason") == "goal_kick"
        for entry in goal_kick_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "restart"
        and entry.get("reason") == "goal_kick"
        and entry.get("receiver_idx") == 0
        for entry in goal_kick_response["trace"]["entries"]
    )

    offside_config = EngineConfig(total_ticks=6, half_ticks=6, frame_interval=1)
    offside_config.runner_forced_action = "pass"
    offside_config.runner_force_receiver_offside = True
    offside_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        offside_config,
        seed=20260709,
    )
    assert any(
        entry["type"] == "event" and entry.get("event") == "offside"
        for entry in offside_response["trace"]["entries"]
    )
    assert any(
        entry["type"] == "event"
        and entry.get("event") == "restart"
        and entry.get("reason") == "offside"
        for entry in offside_response["trace"]["entries"]
    )

    stats_home_cards, stats_away_cards, stats_config, stats_seed = (
        _forced_kickoff_restart_sample(_cards)
    )
    stats_response = run_match_v2_rust(
        stats_home_cards,
        stats_away_cards,
        "433",
        "442",
        stats_config,
        seed=stats_seed,
    )
    for key in (
        "shots_on_target",
        "pass_success_rate",
        "tackles",
        "interceptions",
        "distance_covered",
        "carries_completed",
        "crosses",
        "headers",
    ):
        assert key in stats_response["home_stats"]
    scorer_stats = max(stats_response["home_player_stats"], key=lambda player: player["goals"])
    for key in (
        "npxg",
        "post_shot_xg",
        "big_chances",
        "key_passes",
        "progressive_passes",
        "passes_into_box",
        "successful_crosses",
        "take_ons",
        "blocks",
        "dispossessed",
        "offsides",
        "psxg_faced",
        "goals_prevented",
        "pass_network",
    ):
        assert key in scorer_stats
    assert scorer_stats["goals"] >= 1
    assert scorer_stats["rating"] > 6.0
    assert scorer_stats["shots_on_target"] >= 1
    assert scorer_stats["shot_log"]
    assert scorer_stats["shot_log"][0]["outcome"] in {"goal", "saved", "off_target"}
    scorer_rating = next(
        rating for rating in stats_response["home_ratings"]
        if rating["name"] == scorer_stats["name"]
    )
    assert scorer_rating["rating"] > 6.0
    assert "position" in stats_response["home_ratings"][0]

    progressive_pass_config = EngineConfig(total_ticks=3, half_ticks=3, frame_interval=1)
    progressive_pass_config.runner_forced_action = "pass"
    progressive_pass_config.runner_forced_pass_target = (90.0, 34.0)
    progressive_pass_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        progressive_pass_config,
        seed=20260709,
    )
    progressive_passer = max(
        progressive_pass_response["home_player_stats"],
        key=lambda player: player["passes"],
    )
    for key in (
        "progressive_passes",
        "passes_into_final_third",
        "passes_into_box",
        "long_passes",
        "completed_long_passes",
    ):
        assert key in progressive_passer
        assert progressive_passer[key] >= 0

    pass_network_config = EngineConfig(total_ticks=3, half_ticks=3, frame_interval=1)
    pass_network_config.runner_forced_action = "pass"
    pass_network_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        pass_network_config,
        seed=20260709,
    )
    network_passer = max(
        pass_network_response["home_player_stats"],
        key=lambda player: player["passes"],
    )
    assert network_passer["completed_passes"] >= 1
    assert isinstance(network_passer["pass_network"], dict)

    assist_home_cards, assist_away_cards, assist_config, assist_seed = (
        _forced_assisted_goal_sample(_cards)
    )
    assist_response = run_match_v2_rust(
        assist_home_cards,
        assist_away_cards,
        "433",
        "442",
        assist_config,
        seed=assist_seed,
    )
    assert assist_response["goals"]
    assert "assister" in assist_response["goals"][0]
    assert "assister_color" in assist_response["goals"][0]
    assist_players = assist_response["home_player_stats"]
    assert all("assists" in player for player in assist_players)
    assert any(player["key_passes"] >= 1 for player in assist_players)
    assert any(player["goals"] >= 1 for player in assist_players)
    goal_frames = [
        frame
        for frame in assist_response["replay"]
        if frame.get("event_text") == "GOAL"
    ]
    assert goal_frames
    assert all(frame["ball_flight"]["type"] == "shot" for frame in goal_frames)
    assert all(frame["pause_ms"] > 0 for frame in goal_frames)
    assert all(frame["ball_holder"] is not None for frame in goal_frames)
    assert all(frame["ball_team"] in ("home", "away") for frame in goal_frames)

    specialized_goals = {
        "cut_inside_to_shoot": "drive",
        "wide_byline_attack": "drive",
        "through_ball_behind": "release",
        "release_pressure_with_layoff": "release",
        "release_to_arriving_support": "release",
        "hold_for_opportunity": "scan",
    }
    for goal_type, phase in specialized_goals.items():
        goal_config = EngineConfig(total_ticks=1, half_ticks=1, frame_interval=1)
        goal_config.runner_force_specialized_goal = goal_type
        goal_response = run_match_v2_rust(
            _cards(),
            _cards(),
            "433",
            "442",
            goal_config,
            seed=20260709,
        )
        assert any(
            entry["type"] == "event"
            and entry.get("event") == "on_ball_goal"
            and entry.get("goal_type") == goal_type
            and entry.get("phase") == phase
            for entry in goal_response["trace"]["entries"]
        )

    wrapper_config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    wrapper_config.rust_full_match_runner_enabled = True
    match = MatchV2(_cards(), _cards(), "433", "442", config=wrapper_config)
    result = match.run()
    replay = match.get_replay_data()
    trace = match.get_trace()
    assert result.home_score == running["home_score"]
    assert result.away_score == running["away_score"]
    assert replay[0]["type"] == "header"
    assert trace["entries"]


def test_match_v2_rust_flag_uses_rust_single_entrypoint():
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    assert config.rust_full_match_runner_enabled is True
    match = MatchV2(_cards(), _cards(), "433", "442", config=config)
    result = match.run()
    trace = match.get_trace()
    replay = match.get_replay_data()

    assert result.trace_id.startswith("rust-match-v2")
    assert trace["trace_id"] == "rust-match-v2"
    assert trace["entries"]
    assert replay[0]["type"] == "header"
    assert replay[0]["formation_home"] == "433"


def test_rust_match_v2_shot_arrival_uses_runtime_gk_config():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from tests.test_engine_v2_shape import _cards

    def first_arrival(save_base: float):
        config = EngineConfig(total_ticks=6, half_ticks=6, frame_interval=1)
        config.runner_forced_action = "shot"
        config.gk_save_base = save_base
        response = run_match_v2_rust(
            _cards(),
            _cards(),
            "433",
            "442",
            config,
            seed=18,
        )
        arrivals = [
            entry
            for entry in response["trace"]["entries"]
            if entry.get("type") == "event" and entry.get("event") == "shot_arrival"
        ]
        assert arrivals
        return config, arrivals[0]

    low_config, low_event = first_arrival(0.66)
    high_config, high_event = first_arrival(0.78)

    class DummyKeeper:
        pos = tuple(low_event["gk_pos"])
        abilities = {
            "GK_Saving": 80,
            "GK_Positioning": 80,
            "GK_Reaction": 80,
        }

    assert low_event["shot_origin"] == high_event["shot_origin"]
    assert low_event["shot_target"] == high_event["shot_target"]
    assert low_event["save_roll"] == high_event["save_roll"]
    expected_low = compute_gk_save_probability(
        DummyKeeper,
        tuple(low_event["shot_target"]),
        tuple(low_event["shot_origin"]),
        low_config,
    )
    expected_high = compute_gk_save_probability(
        DummyKeeper,
        tuple(high_event["shot_target"]),
        tuple(high_event["shot_origin"]),
        high_config,
    )
    assert abs(low_event["save_prob"] - expected_low) < 1e-12
    assert abs(high_event["save_prob"] - expected_high) < 1e-12
    assert high_event["save_prob"] > low_event["save_prob"]


def test_rust_match_v2_goal_kick_gk_uses_fallback_distribution():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig(total_ticks=20, half_ticks=20, frame_interval=1)
    config.runner_forced_actions = ["clear", "-"]
    config.runner_forced_clear_target = (106.0, 34.0)
    config.trace.detail = "full"
    response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        config,
        seed=20260709,
    )
    restart_tick = next(
        entry["tick"]
        for entry in response["trace"]["entries"]
        if entry["type"] == "event"
        and entry.get("event") == "restart"
        and entry.get("reason") == "goal_kick"
    )
    after_restart = [
        entry
        for entry in response["trace"]["entries"]
        if entry.get("tick", -1) > restart_tick
    ]
    counts = next(
        entry
        for entry in after_restart
        if entry["type"] == "event"
        and entry.get("event") == "on_ball_candidate_counts"
        and entry.get("player_idx") == 0
        and entry.get("team") == "away"
    )
    assert counts["pass_count"] >= 1
    assert counts["hold_count"] == 0
    assert counts["clear_count"] == 0
    assert next(
        entry
        for entry in after_restart
        if entry["type"] == "action"
        and entry.get("team") == "away"
        and entry.get("player") == "Player 0"
    )["action"] == "pass"


def test_rust_match_v2_full_runner_records_scored_on_ball_candidate_trace():
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig(total_ticks=80, half_ticks=80, frame_interval=1)
    config.trace.detail = "top_candidates"
    config.trace.top_k = 8
    match = MatchV2(_cards(), _cards(), "433", "442", config=config)
    match.run()
    decisions = match.get_trace()["decisions"]

    assert decisions
    checked = 0
    for decision in decisions:
        if decision.get("phase") != "on_ball":
            continue
        chosen = decision["chosen"]
        chosen_score = chosen["value"]["score"]
        alternative_scores = [item["value"]["score"] for item in decision["alternatives"]]
        checked += 1
        assert chosen["action_type"] in {"carry", "pass", "shoot", "hold", "clear"}
        assert isinstance(chosen_score, (int, float))
        assert all(isinstance(score, (int, float)) for score in alternative_scores)
    assert checked > 0


def test_rust_match_v2_goal_lifecycle_is_player_scoped_and_phase_synced():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from tests.test_engine_v2_shape import _cards

    hold_config = EngineConfig(total_ticks=2, half_ticks=2, frame_interval=1)
    hold_config.runner_force_specialized_goal = "hold_for_opportunity"
    hold_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        hold_config,
        seed=20260709,
    )
    hold_frames = [frame for frame in hold_response["replay"] if frame["type"] == "frame"]
    assert len(hold_frames) >= 3
    holder_idx = hold_frames[0]["ball_holder"]
    holder_goals = [
        frame["home_player_goals"][holder_idx]
        for frame in hold_frames
        if frame["ball_team"] == "home" and frame["ball_holder"] == holder_idx
    ]
    assert any(
        goal
        and goal["goal_type"] == "hold_for_opportunity"
        and goal["context"]["phase"] == "scan"
        for goal in holder_goals
    )
    for frame in hold_frames:
        if frame["ball_team"] == "home":
            assert all(
                goal is None
                or (
                    not goal["goal_type"].startswith("defend_")
                    and goal["context"]["phase"] in {"support", "scan"}
                )
                for goal in frame["home_player_goals"]
            )
            assert all(
                goal is None
                or (
                    goal["goal_type"].startswith("defend_")
                    and goal["context"]["phase"] == "defend"
                )
                for goal in frame["away_player_goals"]
            )

    pass_config = EngineConfig(total_ticks=4, half_ticks=4, frame_interval=1)
    pass_config.runner_forced_action = "pass"
    pass_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        pass_config,
        seed=20260709,
    )
    pass_frames = [frame for frame in pass_response["replay"] if frame["type"] == "frame"]
    receive_frame = next(
        frame
        for frame in pass_frames
        if frame["ball_team"] == "home"
        and frame["ball_holder"] is not None
        and frame["ball_holder"] != pass_frames[0]["ball_holder"]
    )
    assert receive_frame["home_player_goals"][receive_frame["ball_holder"]] is None
    assert all(
        goal is None or not goal["goal_type"].startswith("defend_")
        for goal in receive_frame["home_player_goals"]
    )

    restart_home_cards, restart_away_cards, restart_config, restart_seed = (
        _forced_kickoff_restart_sample(_cards)
    )
    restart_response = run_match_v2_rust(
        restart_home_cards,
        restart_away_cards,
        "433",
        "442",
        restart_config,
        seed=restart_seed,
    )
    restart_events = [
        entry
        for entry in restart_response["trace"]["entries"]
        if entry["type"] == "event" and entry.get("event") == "restart"
    ]
    assert restart_events
    restart_tick = restart_events[0]["tick"]
    restart_frames = [
        frame
        for frame in restart_response["replay"]
        if frame["type"] == "frame" and frame["t"] >= restart_tick * restart_config.tick_duration
    ]
    assert restart_frames
    assert all(goal is None for goal in restart_frames[0]["home_player_goals"])
    assert all(goal is None for goal in restart_frames[0]["away_player_goals"])


def test_rust_match_v2_short_match_structural_parity_against_python_runner():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig(total_ticks=12, half_ticks=6, frame_interval=1)
    config.goal_noise_scale = 0.0
    config.trace.detail = "top_candidates"
    config.trace.top_k = 5
    python_response = run_python_baseline_match(
        home_cards=_cards(),
        away_cards=_cards(),
        home_formation="433",
        away_formation="442",
        config=config,
        seed=20260708,
    )

    rust_response = run_match_v2_rust(
        _cards(),
        _cards(),
        "433",
        "442",
        config,
        seed=20260708,
    )

    assert [rust_response["home_score"], rust_response["away_score"]] == [
        python_response["home_score"],
        python_response["away_score"],
    ]
    assert rust_response["replay"][0]["type"] == python_response["replay"][0]["type"] == "header"
    assert len(rust_response["replay"]) == len(python_response["replay"])
    for side in ("home", "away"):
        for key in ("shots", "passes", "passes_completed", "possession"):
            assert rust_response[f"{side}_stats"][key] == python_response[f"{side}_stats"][key]
    assert rust_response["trace"]["entries"]
    assert python_response["trace"]["entries"]
    python_actions = [
        entry["action"]
        for entry in python_response["trace"]["entries"]
        if entry["type"] == "action"
    ][:12]
    rust_actions = [
        entry["action"]
        for entry in rust_response["trace"]["entries"]
        if entry["type"] == "action"
    ][:12]
    assert rust_actions == python_actions, {
        "python": summarize_engine_v2_run(python_response),
        "rust": summarize_engine_v2_run(rust_response),
    }
    for side in ("home", "away"):
        assert len(rust_response[f"{side}_player_stats"]) == 11
        assert len(rust_response[f"{side}_ratings"]) == 11


def test_rust_match_v2_multi_formation_structural_parity_against_python_runner():
    from psl_core.engine_v2.rust_adapter import run_match_v2_rust
    from tests.test_engine_v2_shape import _cards

    scenarios = [
        ("433", "442", 20260708),
        ("442", "442", 12345),
        ("4141", "433", 777),
    ]
    for home_formation, away_formation, seed in scenarios:
        config = EngineConfig(total_ticks=20, half_ticks=10, frame_interval=1)
        config.goal_noise_scale = 0.0
        config.trace.detail = "top_candidates"
        config.trace.top_k = 5
        python_response = run_python_baseline_match(
            home_cards=_cards(),
            away_cards=_cards(),
            home_formation=home_formation,
            away_formation=away_formation,
            config=config,
            seed=seed,
        )

        rust_response = run_match_v2_rust(
            _cards(),
            _cards(),
            home_formation,
            away_formation,
            config,
            seed=seed,
        )

        assert [rust_response["home_score"], rust_response["away_score"]] == [
            python_response["home_score"],
            python_response["away_score"],
        ]
        assert rust_response["replay"][0]["formation_home"] == home_formation
        assert rust_response["replay"][0]["formation_away"] == away_formation
        assert len(rust_response["replay"]) == len(python_response["replay"])
        assert rust_response["trace"]["entries"]
        assert python_response["trace"]["entries"]
        assert summarize_engine_v2_run(rust_response)["first_actions"] == summarize_engine_v2_run(python_response)["first_actions"]
        for side in ("home", "away"):
            assert len(rust_response[f"{side}_player_stats"]) == 11
            assert len(rust_response[f"{side}_ratings"]) == 11
            assert "possession" in rust_response[f"{side}_stats"]


def test_rust_defense_zone_helpers_match_python_formula():
    config = EngineConfig()
    defender_pos = (44.0, 34.0)
    anchor = (42.0, 34.0)
    ball_pos = (60.0, 30.0)
    attackers = [(64.0, 28.0), (70.0, 42.0)]
    attackers_payload = ";".join(f"{x},{y}" for x, y in attackers)

    best_threat = 0.0
    best_target = None
    for attacker in attackers:
        dist_to_ball = py_physics.distance(attacker, ball_pos)
        ball_proximity = max(0.2, 1.0 - dist_to_ball / 30.0)
        advance = 1.0 - attacker[0] / config.pitch_length
        threat = ball_proximity * 0.6 + advance * 0.4
        if threat > best_threat:
            best_threat = threat
            best_target = attacker
    mark_target = (best_target[0] - 1.5, best_target[1])
    mark_expected = (best_threat * 0.6, mark_target)

    target_opp = min(attackers, key=lambda attacker: py_physics.distance(defender_pos, attacker))
    lane_target = ((ball_pos[0] + target_opp[0]) / 2.0, (ball_pos[1] + target_opp[1]) / 2.0)
    dist_opp_to_ball = py_physics.distance(target_opp, ball_pos)
    threat = 0.2 if dist_opp_to_ball > 40.0 else max(0.2, 1.0 - dist_opp_to_ball / 40.0)
    block_expected = (threat * 0.5, lane_target)

    legacy_target = min(attackers, key=lambda attacker: py_physics.distance(defender_pos, attacker))
    legacy_dist_to_ball = py_physics.distance(legacy_target, ball_pos)
    legacy_threat = max(0.2, 1.0 - legacy_dist_to_ball / 30.0)
    legacy_mark_expected = (legacy_threat * 0.6, (legacy_target[0] - 1.5, legacy_target[1]))

    for kind, expected in (
        ("mark", mark_expected),
        ("block", block_expected),
        ("mark_legacy", legacy_mark_expected),
        ("block_legacy", block_expected),
    ):
        row = _run_rust_rows("defense_zone_helper", [
            "\t".join([
                kind,
                str(defender_pos[0]),
                str(defender_pos[1]),
                str(anchor[0]),
                str(anchor[1]),
                str(ball_pos[0]),
                str(ball_pos[1]),
                "1",
                str(config.pitch_length),
                str(config.pitch_width),
                attackers_payload,
                kind,
            ])
        ])[kind]
        assert abs(float(row[0]) - expected[0]) < 1e-12
        _assert_close_tuple(row[1:3], expected[1], eps=1e-12)


def test_rust_misc_defense_and_pass_helpers_match_python_formula():
    config = EngineConfig()
    tackling = 82
    dribbling = 74
    dist_to_ball = 1.2
    dist_factor = max(0.0, 1.0 - dist_to_ball / max(config.tackle_range * 0.9, 0.1))
    success_rate = max(0.0, min(0.75, (tackling / (tackling + dribbling + 1.0)) * dist_factor))
    tackle_score = max(0.0, success_rate * 1.8 - (1.0 - success_rate) * 0.35)
    tackle = _run_rust_rows("physics", [
        "\t".join([
            "score_tackle",
            str(tackling),
            str(dribbling),
            str(dist_to_ball),
            str(config.tackle_range),
            "tackle",
        ])
    ])["tackle"]
    assert abs(float(tackle[0]) - tackle_score) < 1e-12
    assert abs(float(tackle[1]) - success_rate) < 1e-12

    ball_pos = (40.0, 50.0)
    gk = _run_rust_rows("physics", [
        "\t".join([
            "gk_position_adjust",
            str(ball_pos[0]),
            str(ball_pos[1]),
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            "gk",
        ])
    ])["gk"]
    _assert_close_tuple(gk, (5.0, config.pitch_width / 2.0 + (ball_pos[1] - config.pitch_width / 2.0) * 0.3), eps=1e-12)

    score = 4.2
    scale = max(0.1, config.contest_radius * 1.55)
    expected_control = 1.0 / (1.0 + (max(0.0, score) / scale) ** 2)
    control = _run_rust_rows("physics", [
        "\t".join(["pass_control_strength", str(score), str(config.contest_radius), "control"])
    ])["control"]
    assert abs(float(control[0]) - expected_control) < 1e-12

    teammate_control = 0.35
    opponent_control = 0.52
    strongest = max(0.0, min(1.0, teammate_control), min(1.0, opponent_control))
    balance = 1.0 - abs(max(0.0, teammate_control) - max(0.0, opponent_control))
    expected_loose = max(0.0, 1.0 - strongest) * (0.25 + 0.20 * max(0.0, min(1.0, balance)))
    loose = _run_rust_rows("physics", [
        "\t".join(["pass_loose_control_strength", str(teammate_control), str(opponent_control), "loose"])
    ])["loose"]
    assert abs(float(loose[0]) - expected_loose) < 1e-12


def test_rust_restart_play_plan_matches_restart_decision_and_reset_payload():
    config = EngineConfig()
    players = [
        (0, 10.0, 34.0, 1),
        (4, 50.0, 34.0, 0),
        (9, 52.0, 32.0, 0),
    ]
    players_payload = ";".join(",".join(str(value) for value in player) for player in players)
    cases = [
        ("kickoff", (52.5, 34.0), "0.0"),
        ("goal_kick", (6.0, 34.0), "0.0"),
        ("corner", (80.0, 20.0), "0.25"),
        ("throw_in", (40.0, -2.0), "0.0"),
    ]
    for reason, ball_pos, corner_roll in cases:
        decision = _run_rust_rows("restart_helper", [
            "\t".join([
                "restart_play",
                reason,
                str(config.pitch_length),
                "1",
                str(ball_pos[0]),
                str(ball_pos[1]),
                str(config.pitch_width),
                players_payload,
                corner_roll,
            ])
        ])["restart_play"]
        plan = _run_rust_rows("restart_helper", [
            "\t".join([
                "restart_play_plan",
                reason,
                str(config.pitch_length),
                "1",
                str(ball_pos[0]),
                str(ball_pos[1]),
                str(config.pitch_width),
                players_payload,
                corner_roll,
            ])
        ])["restart_play_plan"]
        assert plan[0:5] == decision[0:5]
        assert plan[5] == "1"
        assert plan[6] == "1"


def test_rust_restart_shape_plan_matches_legacy_shape_targets():
    from psl_core.engine_v2.match import MatchV2
    from tests.test_engine_v2_shape import _cards

    config = EngineConfig()
    match = MatchV2(_cards(), _cards(), "433", "433", config=config)
    match.ball.set_dead("goal_kick", "home", 4)
    match.home.players[1].pos = (4.0, 20.0)
    match.away.players[9].pos = (5.0, 34.0)
    restart_team = match.home
    defending_team = match.away
    legacy_targets = {
        (player.team_side, player.index): target
        for player, target in match._goal_kick_shape_targets(restart_team, defending_team)
    }
    legacy_snap = {}
    for (side, idx), target in legacy_targets.items():
        team = match.home if side == "home" else match.away
        player = team.players[idx]
        legacy_snap[(side, idx)] = (
            match._must_leave_penalty_area_for_goal_kick(player, restart_team)
            or py_physics.distance(player.pos, target) > 16.0
        )
    restart_shape = match._goal_kick_spot(restart_team)

    def row(team, is_restart, offset):
        team_code = "0" if team.side == "home" else "1"
        rows = []
        for player in team.players:
            rows.append(",".join([
                str(player.index + offset),
                team_code,
                "1" if is_restart else "0",
                "1" if team.attacking_right else "0",
                "1" if restart_team.attacking_right else "0",
                str(player.base_formation_pos[0]),
                str(player.base_formation_pos[1]),
                str(player.pos[0]),
                str(player.pos[1]),
                "1" if player.is_goalkeeper else "0",
                "1" if player.is_attacker else "0",
                "1" if player.is_midfielder else "0",
                "1" if player.is_defender else "0",
                player.position,
            ]))
        return rows

    players_payload = ";".join(row(restart_team, True, 0) + row(defending_team, False, 1000))
    fields = _run_rust_rows("restart_helper", [
        "\t".join([
            "restart_shape_plan",
            "goal_kick",
            "1",
            str(config.pitch_length),
            str(config.pitch_width),
            players_payload,
            "restart_shape_plan",
        ])
    ])["restart_shape_plan"]
    assert fields[0] == "1"
    _assert_close_tuple(fields[1:3], restart_shape, eps=1e-12)
    rust_targets = {}
    for item in fields[3].split(";"):
        team_code, external_idx, x, y, snap = item.split(",")
        side = "home" if team_code == "0" else "away"
        idx = int(external_idx) if side == "home" else int(external_idx) - 1000
        rust_targets[(side, idx)] = ((float(x), float(y)), snap == "1")
    assert set(rust_targets) == set(legacy_targets)
    for key, target in legacy_targets.items():
        _assert_close_tuple(
            [str(value) for value in rust_targets[key][0]],
            target,
            eps=1e-12,
        )
        assert rust_targets[key][1] == legacy_snap[key]

    kickoff_targets = {
        (player.team_side, player.index): target
        for player, target in match._kickoff_shape_targets(match.away, match.home)
    }
    kickoff_payload = ";".join(row(match.away, True, 0) + row(match.home, False, 1000))
    kickoff_fields = _run_rust_rows("restart_helper", [
        "\t".join([
            "restart_shape_plan",
            "kickoff",
            "0",
            str(config.pitch_length),
            str(config.pitch_width),
            kickoff_payload,
            "kickoff_shape_plan",
        ])
    ])["kickoff_shape_plan"]
    assert kickoff_fields[0] == "1"
    _assert_close_tuple(kickoff_fields[1:3], (config.pitch_length / 2.0, config.pitch_width / 2.0), eps=1e-12)
    parsed_kickoff = {}
    for item in kickoff_fields[3].split(";"):
        team_code, external_idx, x, y, snap = item.split(",")
        side = "home" if team_code == "0" else "away"
        idx = int(external_idx) if side == "away" else int(external_idx) - 1000
        parsed_kickoff[(side, idx)] = ((float(x), float(y)), snap == "1")
    assert set(parsed_kickoff) == set(kickoff_targets)
    for key, target in kickoff_targets.items():
        _assert_close_tuple([str(value) for value in parsed_kickoff[key][0]], target, eps=1e-12)
        assert parsed_kickoff[key][1] is False


def test_rust_flight_movement_plan_matches_python_branch_and_target_formula():
    config = EngineConfig()
    target = (70.0, 38.0)
    attack_players = [
        (1, 68.0, 38.0, 62.0, 34.0, 0, 0),
        (2, 40.0, 20.0, 42.0, 22.0, 0, 0),
        (9, 68.0, 38.0, 65.0, 34.0, 1, 0),
        (4, 50.0, 30.0, 50.0, 30.0, 0, 1),
    ]
    defense_players = [
        (3, 69.0, 37.0, 65.0, 35.0, 0, 0),
        (5, 35.0, 50.0, 40.0, 48.0, 0, 0),
        (6, 48.0, 42.0, 48.0, 42.0, 0, 1),
    ]

    def payload(players):
        return ";".join(",".join(str(value) for value in player) for player in players)

    fields = _run_rust_rows("flight_movement_plan", [
        "\t".join([
            str(target[0]),
            str(target[1]),
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.contested_race_radius),
            "0.0",
            payload(attack_players),
            payload(defense_players),
            "flight_movement",
        ])
    ])["flight_movement"]
    parsed = {}
    for item in fields[0].split(";"):
        team_code, idx, action_code, x, y = item.split(",")
        parsed[(int(team_code), int(idx))] = (int(action_code), (float(x), float(y)))

    expected = {}
    for idx, x, y, ax, ay, is_passer, is_stunned in attack_players:
        if is_stunned:
            expected[(0, idx)] = (3, (x, y))
        elif not is_passer and py_physics.distance((x, y), target) < config.contested_race_radius * 1.35:
            expected[(0, idx)] = (1, target)
        else:
            expected[(0, idx)] = (
                0,
                (
                    max(0.5, min(config.pitch_length - 0.5, ax * 0.86 + target[0] * 0.14)),
                    max(0.5, min(config.pitch_width - 0.5, ay * 0.88 + target[1] * 0.12)),
                ),
            )
    for idx, x, y, ax, ay, _is_passer, is_stunned in defense_players:
        if is_stunned:
            expected[(1, idx)] = (3, (x, y))
        elif py_physics.distance((x, y), target) < config.contested_race_radius * 1.25:
            expected[(1, idx)] = (2, target)
        else:
            expected[(1, idx)] = (
                0,
                (
                    max(0.5, min(config.pitch_length - 0.5, ax * 0.88 + target[0] * 0.12)),
                    max(0.5, min(config.pitch_width - 0.5, ay * 0.90 + target[1] * 0.10)),
                ),
            )

    assert set(parsed) == set(expected)
    for key, (expected_action, expected_target) in expected.items():
        action, rust_target = parsed[key]
        assert action == expected_action
        _assert_close_tuple([str(value) for value in rust_target], expected_target, eps=1e-12)


def test_rust_out_of_bounds_plan_matches_restart_and_shot_log_payloads():
    config = EngineConfig()
    origin = (88.0, 35.0)
    total_xg = 0.47
    logged_xg = 0.12
    cases = [
        ("shot_goal_kick", "106.0", "1", "3", "1"),
        ("pass_throw", "50.0", "0", "0", "0"),
    ]
    for case_id, out_x, passer_home, flight_type_code, attacking_right in cases:
        restart = _run_rust_rows("physics", [
            "\t".join([
                "out_of_bounds_restart",
                out_x,
                str(config.pitch_length),
                passer_home,
                "restart",
            ])
        ])["restart"]
        plan = _run_rust_rows("physics", [
            "\t".join([
                "out_of_bounds_plan",
                out_x,
                str(config.pitch_length),
                str(config.pitch_width),
                passer_home,
                flight_type_code,
                str(origin[0]),
                str(origin[1]),
                attacking_right,
                str(total_xg),
                str(logged_xg),
                str(config.goal_kick_restart_ticks),
                str(config.throw_in_restart_ticks),
                case_id,
            ])
        ])[case_id]
        assert plan[0:2] == restart[0:2]
        expected_ticks = config.goal_kick_restart_ticks if restart[0] == "goal_kick" else config.throw_in_restart_ticks
        assert int(plan[2]) == expected_ticks
        if flight_type_code == "3":
            shot_log_xg = _run_rust_rows("shot_log_xg", [
                "\t".join([str(total_xg), str(logged_xg), "1", "xg"])
            ])["xg"]
            in_box = _run_rust_rows("physics", [
                "\t".join([
                    "is_attacking_box",
                    str(origin[0]),
                    str(origin[1]),
                    attacking_right,
                    str(config.pitch_length),
                    str(config.pitch_width),
                    "box",
                ])
            ])["box"][0]
            assert plan[3] == "1"
            _assert_close_tuple(plan[4:6], origin, eps=1e-12)
            assert abs(float(plan[6]) - float(shot_log_xg[1])) < 1e-12
            assert plan[7] == in_box
            assert plan[8] == "off_target"
        else:
            assert plan[3] == "0"
