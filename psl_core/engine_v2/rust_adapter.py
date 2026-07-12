"""Bridge between Python entry points and the Rust engine_v2 executable."""

from __future__ import annotations

import subprocess
import fcntl
import json
import os
from pathlib import Path
from typing import List, Tuple

from .value_model import state_value
from .value_model import ValueResult
from .vision import build_vision_context


ROOT = Path(__file__).resolve().parents[2]
RUST_CRATE = ROOT / "rust" / "engine_v2_core"
RUST_PROFILE = os.environ.get("PSL_RUST_PROFILE", "release").strip().lower()
if RUST_PROFILE not in {"debug", "release"}:
    RUST_PROFILE = "release"
RUST_TARGET_DIR = "release" if RUST_PROFILE == "release" else "debug"
RUST_CLI = RUST_CRATE / "target" / RUST_TARGET_DIR / "engine"
RUST_BUILD_LOCK = RUST_CRATE / "target" / f".engine.{RUST_TARGET_DIR}.lock"


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = max(0.0, min(1.0, (value - edge0) / max(1e-6, edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _rust_cli_needs_build() -> bool:
    if not RUST_CLI.exists():
        return True
    try:
        cli_mtime = RUST_CLI.stat().st_mtime
    except FileNotFoundError:
        return True
    src_dir = RUST_CRATE / "src"
    return any(path.stat().st_mtime > cli_mtime for path in src_dir.rglob("*.rs"))


def _ensure_rust_cli_built() -> None:
    RUST_BUILD_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with RUST_BUILD_LOCK.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if _rust_cli_needs_build():
            cmd = ["cargo", "build", "--quiet", "--bin", "engine"]
            if RUST_PROFILE == "release":
                cmd.insert(2, "--release")
            subprocess.run(
                cmd,
                cwd=RUST_CRATE,
                text=True,
                capture_output=True,
                check=True,
            )
        fcntl.flock(lock_file, fcntl.LOCK_UN)


def _positions_payload(positions):
    if not positions:
        return "-"
    return ";".join(f"{x},{y}" for x, y in positions)


def _indexed_positions_payload(players):
    if not players:
        return "-"
    return ";".join(f"{idx},{x},{y}" for idx, x, y in players)


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


def _run_rust_rows(mode: str, lines: List[str]) -> dict:
    if _rust_cli_needs_build():
        _ensure_rust_cli_built()
    try:
        proc = subprocess.run(
            [str(RUST_CLI), mode],
            cwd=RUST_CRATE,
            input="\n".join(lines),
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        _ensure_rust_cli_built()
        proc = subprocess.run(
            [str(RUST_CLI), mode],
            cwd=RUST_CRATE,
            input="\n".join(lines),
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if exc.returncode != -9:
            raise
        _ensure_rust_cli_built()
        proc = subprocess.run(
            [str(RUST_CLI), mode],
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


def _run_rust_json(mode: str, payload: dict) -> dict:
    """Run a Rust JSON-mode command and return its JSON object response."""
    if _rust_cli_needs_build():
        _ensure_rust_cli_built()
    try:
        proc = subprocess.run(
            [str(RUST_CLI), mode],
            cwd=RUST_CRATE,
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        _ensure_rust_cli_built()
        proc = subprocess.run(
            [str(RUST_CLI), mode],
            cwd=RUST_CRATE,
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            capture_output=True,
            check=True,
        )
    return json.loads(proc.stdout)


def run_match_v2_rust(
    home_cards,
    away_cards,
    home_formation: str,
    away_formation: str,
    config,
    seed=None,
):
    """Run a full MatchV2 request through the single Rust match entrypoint."""
    payload = {
        "home_cards": home_cards,
        "away_cards": away_cards,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "config": {
            "pitch_length": config.pitch_length,
            "pitch_width": config.pitch_width,
            "tick_duration": config.tick_duration,
            "total_ticks": config.total_ticks,
            "half_ticks": config.half_ticks,
            "frame_interval": config.frame_interval,
            "goal_kick_restart_ticks": config.goal_kick_restart_ticks,
            "throw_in_restart_ticks": config.throw_in_restart_ticks,
            "runner_shot_threshold": getattr(config, "runner_shot_threshold", 0.18),
            "runner_forced_action": getattr(config, "runner_forced_action", None),
            "runner_forced_actions": getattr(config, "runner_forced_actions", None),
            "runner_force_defender_lane": getattr(config, "runner_force_defender_lane", False),
            "runner_forced_pass_target": getattr(config, "runner_forced_pass_target", None),
            "runner_forced_clear_target": getattr(config, "runner_forced_clear_target", None),
            "runner_force_receiver_offside": getattr(config, "runner_force_receiver_offside", False),
            "runner_force_specialized_goal": getattr(config, "runner_force_specialized_goal", None),
            "trace_detail": getattr(getattr(config, "trace", None), "detail", "off"),
            "trace_top_k": getattr(getattr(config, "trace", None), "top_k", 5),
            "player_max_speed": config.player_max_speed,
            "player_min_speed": config.player_min_speed,
            "ball_pass_speed": config.ball_pass_speed,
            "ball_long_pass_speed": config.ball_long_pass_speed,
            "ball_shot_speed": config.ball_shot_speed,
            "goal_width": config.goal_width,
            "contest_radius": config.contest_radius,
            "contested_race_radius": getattr(config, "contested_race_radius", 15.0),
            "press_radius": config.press_radius,
            "tackle_range": config.tackle_range,
            "interception_reach": config.interception_reach,
            "short_pass_base_success": config.short_pass_base_success,
            "long_pass_base_success": config.long_pass_base_success,
            "shot_ideal_distance": config.shot_ideal_distance,
            "shot_on_target_base": config.shot_on_target_base,
            "gk_save_base": config.gk_save_base,
            "gk_position_error_factor": config.gk_position_error_factor,
            "gk_reaction_delay_factor": config.gk_reaction_delay_factor,
            "clear_reward_base": config.clear_reward_base,
            "carrier_speed": config.carrier_speed,
            "iq_noise_scale": config.iq_noise_scale,
            "goal_noise_scale": getattr(config, "goal_noise_scale", 0.008),
            "vision_base_fov": config.vision_base_fov,
            "vision_iq_bonus_factor": config.vision_iq_bonus_factor,
            "vision_base_distance": config.vision_base_distance,
            "vision_iq_distance_bonus_factor": config.vision_iq_distance_bonus_factor,
            "vision_max_distance": config.vision_max_distance,
            "pass_to_space_ball_speed": getattr(config, "pass_to_space_ball_speed", config.ball_pass_speed),
            "receive_reachability_scale": getattr(config, "receive_reachability_scale", 1.0),
            "space_creation_radius": getattr(config, "space_creation_radius", 10.0),
            "find_space_radius": config.find_space_radius,
            "pass_error_divisor": config.pass_error_divisor,
            "first_touch_error_divisor": config.first_touch_error_divisor,
            "carry_error_divisor": config.carry_error_divisor,
        },
        "seed": seed,
    }
    return _run_rust_json("match_v2_run", payload)


def _parse_pass_team_batch_details(raw: str):
    if raw == "-":
        return []
    parsed = []
    for item in raw.split(";"):
        parts = item.split(",")
        extras = parts[19:]
        parsed.append({
            "receiver_idx": int(parts[0]),
            "target": (float(parts[1]), float(parts[2])),
            "score": float(parts[3]),
            "raw_score": float(parts[4]),
            "success_prob": float(parts[5]),
            "risk_cost": float(parts[6]),
            "after_value": float(parts[7]),
            "effective_delta": float(parts[8]),
            "continuity": float(parts[9]),
            "lane_risk": float(parts[10]),
            "receiver_pressure": float(parts[11]),
            "turnover_consequence": float(parts[12]),
            "receiver_arrival": float(parts[13]),
            "base_accuracy": float(parts[14]),
            "receiver_goal_fit": float(parts[15]),
            "distance": float(parts[16]),
            "is_long": parts[17] == "1",
            "target_kind_space": parts[18] == "1",
            "perception": float(extras[0]) if len(extras) > 0 else 0.0,
            "perception_multiplier": float(extras[1]) if len(extras) > 1 else 0.0,
            "arrival_margin": float(extras[2]) if len(extras) > 2 else 0.0,
            "defender_first_risk": float(extras[3]) if len(extras) > 3 else 0.0,
            "target_occupation_risk": float(extras[4]) if len(extras) > 4 else 0.0,
            "nearest_teammate_to_target": float(extras[5]) if len(extras) > 5 else 0.0,
            "nearest_opp_to_target": float(extras[6]) if len(extras) > 6 else 0.0,
            "box_space_pressure": float(extras[7]) if len(extras) > 7 else 0.0,
            "tactical_space": extras[8] == "1" if len(extras) > 8 else False,
            "tactical_space_prior": float(extras[9]) if len(extras) > 9 else 0.0,
            "tactical_space_value": float(extras[10]) if len(extras) > 10 else 0.0,
            "tactical_space_visibility": float(extras[11]) if len(extras) > 11 else 0.0,
            "expected_arrival_confidence": float(extras[12]) if len(extras) > 12 else 0.0,
            "expected_arrival_fit": float(extras[13]) if len(extras) > 13 else 0.0,
        })
    return parsed


def score_pass_point_options_rust(
    passer,
    teammates,
    opponents,
    config,
    pitch,
    attacking_right: bool,
    current_value: float | None = None,
):
    """Return Rust pass-team-batch details for controlled parity checks."""
    if current_value is None:
        current_value = state_value(
            passer.pos, passer, teammates, opponents, config, pitch, attacking_right
        )
    context = build_vision_context(passer, config, attacking_right)
    offside_line = passer._get_offside_line(opponents, attacking_right, config)
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions_indexed = [(t.index, t.pos[0], t.pos[1]) for t in teammates]
    teammate_xy_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != passer.index]
    line = "\t".join([
        str(passer.index),
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(passer.abilities.get("Finishing", 50) / 100.0),
        str(passer.abilities.get("Long_Shot", 50) / 100.0),
        str(passer.abilities.get("Short_Passing", 50)),
        str(passer.abilities.get("Long_Passing", 50)),
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
        _positions_payload(opponent_positions),
        _positions_payload(teammate_xy_positions),
        _pass_risk_players_payload(opponents),
        _pass_risk_players_payload(teammates),
        str(config.interception_reach),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        "-",
        "pass_team_batch",
    ])
    rows = _run_rust_rows("pass_team_batch_details", [line])
    return _parse_pass_team_batch_details(rows["pass_team_batch"][0])


def state_value_rust(player, teammates, opponents, config, pitch, attacking_right: bool):
    """Compute state value in Rust."""
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions_indexed = [(t.index, t.pos[0], t.pos[1]) for t in teammates]
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.index),
        str(player.abilities.get("Finishing", 50) / 100.0),
        str(player.abilities.get("Long_Shot", 50) / 100.0),
        str(config.pitch_length),
        str(config.pitch_width),
        "1" if attacking_right else "0",
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        _positions_payload(opponent_positions),
        _indexed_positions_payload(teammate_positions_indexed),
        "state",
    ])
    rows = _run_rust_rows("state_value", [line])
    return float(rows["state"][0])


def position_values_rust(positions, opponents, teammates, config, attacking_right: bool):
    """Batch compute position_value for raw positions in Rust."""
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    teammate_positions = [(t.pos[0], t.pos[1]) for t in teammates]
    lines = []
    for case_id, pos in enumerate(positions):
        lines.append("\t".join([
            str(pos[0]),
            str(pos[1]),
            str(config.pitch_length),
            str(config.pitch_width),
            "1" if attacking_right else "0",
            "-",
            "-",
            _positions_payload(opponent_positions),
            _positions_payload(teammate_positions),
            str(case_id),
        ]))
    rows = _run_rust_rows("position_value", lines)
    return [float(rows[str(idx)][0]) for idx in range(len(positions))]


def is_attacking_box_pos_rust(pos, attacking_right: bool, config):
    """Return attacking penalty-box classification from Rust."""
    line = "\t".join([
        "is_attacking_box",
        str(pos[0]),
        str(pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "box",
    ])
    rows = _run_rust_rows("physics", [line])
    return rows["box"][0] == "1"


def player_move_tick_rust(player, config, pitch):
    """Return one off-ball movement tick from Rust."""
    line = "\t".join([
        "player_move_tick",
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.target_pos[0]),
        str(player.target_pos[1]),
        str(player.velocity[0]),
        str(player.velocity[1]),
        str(player.speed_value),
        player.movement_intent,
        player.state.value,
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.pitch_length),
        str(config.pitch_width),
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["player_move_tick"]
    return {
        "moved": fields[0] == "1",
        "pos": (float(fields[1]), float(fields[2])),
        "velocity": (float(fields[3]), float(fields[4])),
        "distance_covered": float(fields[5]),
        "facing_direction": None if fields[6] == "-" else float(fields[6]),
        "desired_speed": float(fields[7]),
    }


def player_move_speed_rust(player, config):
    """Return adaptive off-ball move speed from Rust."""
    line = "\t".join([
        "player_move_speed",
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.target_pos[0]),
        str(player.target_pos[1]),
        str(player.speed_value),
        player.movement_intent,
        player.state.value,
        str(config.player_max_speed),
        str(config.player_min_speed),
    ])
    rows = _run_rust_rows("physics", [line])
    return float(rows["player_move_speed"][0])


def player_set_movement_target_rust(player, target, intent):
    """Return movement target smoothing from Rust."""
    line = "\t".join([
        "player_set_movement_target",
        str(player.target_pos[0]),
        str(player.target_pos[1]),
        str(target[0]),
        str(target[1]),
        player.movement_intent,
        "-" if intent is None else intent,
        "set_movement_target",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["set_movement_target"]
    return {
        "target_pos": (float(fields[0]), float(fields[1])),
        "movement_intent": fields[2],
    }


def player_tick_stun_rust(player):
    """Return one stun timer tick from Rust."""
    line = "\t".join([
        "player_tick_stun",
        player.state.value,
        str(player.stun_ticks_remaining),
        "tick_stun",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["tick_stun"]
    return {
        "state": fields[0],
        "stun_ticks_remaining": int(fields[1]),
    }


def player_apply_stun_rust(config):
    """Return stun state and duration from Rust."""
    line = "\t".join([
        "player_apply_stun",
        str(config.tackle_fail_stun_seconds),
        str(config.tick_duration),
        "apply_stun",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["apply_stun"]
    return {
        "state": fields[0],
        "stun_ticks_remaining": int(fields[1]),
    }


def residual_ball_velocity_rust(flight, factor: float = 0.16):
    """Return residual loose-ball velocity from Rust."""
    line = "\t".join([
        "residual_ball_velocity",
        str(flight.origin[0]),
        str(flight.origin[1]),
        str(flight.target[0]),
        str(flight.target[1]),
        str(flight.speed),
        str(factor),
        "residual",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["residual"]
    return (float(fields[0]), float(fields[1]))


def out_of_bounds_restart_rust(pos, flight, config):
    """Return dead-ball restart reason/team for an out-of-bounds flight."""
    line = "\t".join([
        "out_of_bounds_restart",
        str(pos[0]),
        str(config.pitch_length),
        "1" if flight.passer_team == "home" else "0",
        "out",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["out"]
    return {
        "reason": fields[0],
        "restart_team": fields[1],
    }


def out_of_bounds_plan_rust(pos, flight, shooter, shooter_team, config):
    """Return out-of-bounds restart and optional shot-log payload from Rust."""
    logged_sum = sum(s.get("xg", 0) for s in getattr(shooter, "shot_log", [])) if shooter is not None else 0.0
    total_xg = getattr(shooter, "xg", 0.0) if shooter is not None else 0.0
    flight_type_code = 3 if getattr(flight.flight_type, "value", "") == "shot" else 0
    line = "\t".join([
        "out_of_bounds_plan",
        str(pos[0]),
        str(config.pitch_length),
        str(config.pitch_width),
        "1" if flight.passer_team == "home" else "0",
        str(flight_type_code),
        str(flight.origin[0]),
        str(flight.origin[1]),
        "1" if shooter_team is not None and shooter_team.attacking_right else "0",
        str(total_xg),
        str(logged_sum),
        str(config.goal_kick_restart_ticks),
        str(config.throw_in_restart_ticks),
        "out_plan",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["out_plan"]
    shot_log = None
    if fields[3] == "1":
        shot_log = {
            "x": float(fields[4]),
            "y": float(fields[5]),
            "xg": float(fields[6]),
            "in_box": fields[7] == "1",
            "outcome": fields[8],
        }
    return {
        "reason": fields[0],
        "restart_team": fields[1],
        "restart_ticks": int(fields[2]),
        "shot_log": shot_log,
    }


def flag_offside_players_rust(passer_team, opp_team, passer_idx: int, pass_origin, config):
    """Return passer-team player indices offside at pass time using Rust offside helpers."""
    opponent_payload = ";".join(
        f"{p.pos[0]},{1 if p.is_goalkeeper else 0}"
        for p in opp_team.players
    ) or "-"
    rows = _run_rust_rows("offside", [
        "\t".join([
            "line",
            "1" if passer_team.attacking_right else "0",
            str(config.pitch_length),
            opponent_payload,
            "line",
        ])
    ])
    offside_line = float(rows["line"][0])
    lines = []
    player_indices = []
    for player in passer_team.players:
        if player.index == passer_idx:
            continue
        player_indices.append(player.index)
        lines.append("\t".join([
            "position",
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if passer_team.attacking_right else "0",
            str(offside_line),
            str(config.pitch_length),
            str(pass_origin[0]),
            f"p_{player.index}",
        ]))
    if not lines:
        return set()
    rows = _run_rust_rows("offside", lines)
    return {
        idx
        for idx in player_indices
        if rows[f"p_{idx}"][0] == "1"
    }


def is_offside_rust(receiver, attacking_team, defending_team, ball_x: float, config):
    """Return whether receiver is offside using Rust offside helpers."""
    if receiver.is_goalkeeper:
        return False
    opponent_payload = ";".join(
        f"{p.pos[0]},{1 if p.is_goalkeeper else 0}"
        for p in defending_team.players
    ) or "-"
    line_row = _run_rust_rows("offside", [
        "\t".join([
            "line",
            "1" if attacking_team.attacking_right else "0",
            str(config.pitch_length),
            opponent_payload,
            "line",
        ])
    ])
    offside_line = float(line_row["line"][0])
    rows = _run_rust_rows("offside", [
        "\t".join([
            "position",
            str(receiver.pos[0]),
            str(receiver.pos[1]),
            "1" if attacking_team.attacking_right else "0",
            str(offside_line),
            str(config.pitch_length),
            str(ball_x),
            "offside",
        ])
    ])
    return rows["offside"][0] == "1"


def build_goal_event_rust(
    scorer,
    scoring_team,
    home_score: int,
    away_score: int,
    last_passer_team: str,
    last_passer_idx: int,
):
    """Return goal event/assist/score payload from Rust."""
    assister_name = ""
    assister_color = ""
    if 0 <= last_passer_idx < len(scoring_team.players):
        assister = scoring_team.players[last_passer_idx]
        assister_name = assister.name
        assister_color = assister.color
    line = "\t".join([
        scorer.name,
        scoring_team.side,
        str(home_score),
        str(away_score),
        str(scorer.index),
        last_passer_team if last_passer_team else "-",
        str(last_passer_idx),
        str(len(scoring_team.players)),
        assister_name,
        assister_color,
        "goal",
    ])
    rows = _run_rust_rows("goal_event", [line])
    fields = rows["goal"]
    return {
        "home_score": int(fields[0]),
        "away_score": int(fields[1]),
        "has_assist": fields[2] == "1",
        "assister_idx": int(fields[3]),
        "assister_name": fields[4],
        "assister_color": fields[5],
        "event_text": fields[6],
    }


def score_goal_plan_rust(
    scorer,
    scoring_team,
    conceding_team,
    home_score: int,
    away_score: int,
    last_passer_team: str,
    last_passer_idx: int,
    tick: int,
    config,
):
    """Return full goal scoring event/score/restart plan from Rust."""
    assister_name = ""
    assister_color = ""
    if 0 <= last_passer_idx < len(scoring_team.players):
        assister = scoring_team.players[last_passer_idx]
        assister_name = assister.name
        assister_color = assister.color
    line = "\t".join([
        scorer.name,
        scoring_team.side,
        conceding_team.side,
        str(home_score),
        str(away_score),
        str(scorer.index),
        last_passer_team if last_passer_team else "-",
        str(last_passer_idx),
        str(len(scoring_team.players)),
        assister_name,
        assister_color,
        str(tick),
        str(config.tick_duration),
        "score_goal",
    ])
    rows = _run_rust_rows("score_goal_plan", [line])
    fields = rows["score_goal"]
    return {
        "home_score": int(fields[0]),
        "away_score": int(fields[1]),
        "has_assist": fields[2] == "1",
        "assister_idx": int(fields[3]),
        "assister_name": fields[4],
        "assister_color": fields[5],
        "minute": int(fields[6]),
        "event_text": fields[7],
        "pause_ms": int(fields[8]),
        "restart_team": fields[9],
        "restart_ticks": int(fields[10]),
    }


def give_ball_plan_rust(ball, player, team, receive_origin):
    """Return possession transfer state plan from Rust."""
    prev_team_code = {"home": "0", "away": "1"}.get(ball.holder_team, "-")
    new_team_code = "0" if team.side == "home" else "1"
    line = "\t".join([
        prev_team_code,
        str(ball.holder_idx),
        new_team_code,
        str(player.index),
        str(player.pos[0]),
        str(player.pos[1]),
        "-" if receive_origin is None else str(receive_origin[0]),
        "-" if receive_origin is None else str(receive_origin[1]),
        "0.0",
        "give_ball",
    ])
    rows = _run_rust_rows("give_ball_plan", [line])
    fields = rows["give_ball"]
    return {
        "clear_previous_holder": fields[0] == "1",
        "previous_holder_team": None if fields[1] == "-" else ("home" if fields[1] == "0" else "away"),
        "previous_holder_idx": int(fields[2]),
        "clear_offside_flags": fields[3] == "1",
        "clear_team_goals": fields[4] == "1",
        "new_holder_team": "home" if fields[5] == "0" else "away",
        "new_holder_idx": int(fields[6]),
        "ball_pos": (float(fields[7]), float(fields[8])),
        "last_receive_origin": (float(fields[9]), float(fields[10])),
    }


def build_ball_flight_data_rust(from_pos, to_pos, flight_type: str, on_target: bool = False):
    """Build replay ball-flight frame payload in Rust."""
    line = "\t".join([
        str(from_pos[0]),
        str(from_pos[1]),
        str(to_pos[0]),
        str(to_pos[1]),
        flight_type,
        "1" if on_target else "0",
        "flight",
    ])
    rows = _run_rust_rows("ball_flight_frame", [line])
    fields = rows["flight"]
    return {
        "from": [float(fields[0]), float(fields[1])],
        "to": [float(fields[2]), float(fields[3])],
        "type": fields[4],
        "on_target": fields[5] == "1",
    }


def tick_ball_flight_rust(flight):
    """Advance ball flight one tick in Rust."""
    line = "\t".join([
        str(flight.origin[0]),
        str(flight.origin[1]),
        str(flight.target[0]),
        str(flight.target[1]),
        str(flight.ticks_elapsed),
        str(flight.ticks_total),
        "flight_tick",
    ])
    rows = _run_rust_rows("flight_tick", [line])
    fields = rows["flight_tick"]
    return {
        "position": (float(fields[0]), float(fields[1])),
        "ticks_elapsed": int(fields[2]),
        "complete": fields[3] == "1",
    }


def flight_movement_plan_rust(target_pos, flight, atk_team, def_team, config):
    """Return flight-phase movement branch/target plan for attack and defense teams."""
    def payload(team, is_attack):
        rows = []
        for player in team.players:
            is_passer = (
                is_attack
                and flight is not None
                and player.index == flight.passer_idx
            )
            rows.append(",".join([
                str(player.index),
                str(player.pos[0]),
                str(player.pos[1]),
                str(player.tactical_anchor[0]),
                str(player.tactical_anchor[1]),
                "1" if is_passer else "0",
                "1" if getattr(player, "state", None) is not None and player.state.value == "stunned" else "0",
            ]))
        return ";".join(rows) or "-"

    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.contested_race_radius),
        "0.0",
        payload(atk_team, True),
        payload(def_team, False),
        "flight_movement",
    ])
    rows = _run_rust_rows("flight_movement_plan", [line])
    raw = rows["flight_movement"][0]
    result = {}
    if raw == "-":
        return result
    action_by_code = {
        "0": "shape",
        "1": "attack_ai",
        "2": "defense_ai",
        "3": "stunned",
    }
    for item in raw.split(";"):
        team_code, idx, action_code, x, y = item.split(",")
        side = atk_team.side if team_code == "0" else def_team.side
        result[(side, int(idx))] = {
            "action": action_by_code.get(action_code, "shape"),
            "target": (float(x), float(y)),
        }
    return result


def key_pass_for_shot_rust(shooter, shooter_team, last_passer_team: str, last_passer_idx: int):
    """Return key-pass credit decision for a shot from Rust."""
    line = "\t".join([
        shooter_team.side,
        str(shooter.index),
        last_passer_team if last_passer_team else "-",
        str(last_passer_idx),
        str(len(shooter_team.players)),
        "key_pass",
    ])
    rows = _run_rust_rows("key_pass", [line])
    fields = rows["key_pass"]
    return {
        "has_key_pass": fields[0] == "1",
        "passer_idx": int(fields[1]),
    }


def pass_phase_outcome_rust(pass_accuracy_error: bool, interception_present: bool, intercepted: bool):
    """Return pass phase outcome code from Rust."""
    line = "\t".join([
        "1" if pass_accuracy_error else "0",
        "1" if interception_present else "0",
        "1" if intercepted else "0",
        "pass_outcome",
    ])
    rows = _run_rust_rows("pass_phase_outcome", [line])
    code = int(rows["pass_outcome"][0])
    return {0: "flight", 1: "pass_accuracy_error", 2: "interception"}[code]


def pass_trace_payload_rust(target, intended_receiver, is_long: bool):
    """Return pass trace pass_type/target_kind payload from Rust."""
    line = "\t".join([
        str(target[0]),
        str(target[1]),
        "-" if intended_receiver is None else str(intended_receiver.pos[0]),
        "-" if intended_receiver is None else str(intended_receiver.pos[1]),
        "1" if is_long else "0",
        "pass_trace",
    ])
    rows = _run_rust_rows("pass_trace_payload", [line])
    fields = rows["pass_trace"]
    return {
        "pass_type": "long_pass" if fields[0] == "1" else "short_pass",
        "target_kind": "space" if fields[1] == "1" else "feet",
    }


def pass_phase_plan_rust(
    passer,
    ideal_target,
    is_long: bool,
    lane_risk: float,
    opponents,
    intended_receiver,
    interception_interaction,
    config,
    random_values,
):
    """Return the full pass phase execution plan from Rust."""
    passing = passer.abilities.get("Long_Passing" if is_long else "Short_Passing", 50)
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    interceptor = interception_interaction.defender if interception_interaction is not None else None
    line = "\t".join([
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(ideal_target[0]),
        str(ideal_target[1]),
        str(passing),
        "1" if is_long else "0",
        str(lane_risk),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.ball_pass_speed),
        str(config.ball_long_pass_speed),
        opponent_payload,
        str(config.pass_error_divisor),
        *[str(value) for value in random_values],
        "1" if interception_interaction is not None else "0",
        str(interceptor.abilities.get("Defence", 50)) if interceptor is not None else "0.0",
        str(interception_interaction.distance) if interception_interaction is not None else "0.0",
        str(config.interception_reach),
        "-" if intended_receiver is None else str(intended_receiver.pos[0]),
        "-" if intended_receiver is None else str(intended_receiver.pos[1]),
        "pass_plan",
    ])
    rows = _run_rust_rows("pass_phase_plan", [line])
    fields = rows["pass_plan"]
    return {
        "outcome": {0: "flight", 1: "pass_accuracy_error", 2: "interception"}[int(fields[0])],
        "target": (float(fields[1]), float(fields[2])),
        "stray_pos": (float(fields[3]), float(fields[4])),
        "speed": float(fields[5]),
        "ticks_needed": int(fields[6]),
        "flight_type_code": int(fields[7]),
        "pass_type": "long_pass" if fields[8] == "1" else "short_pass",
        "target_kind": "space" if fields[9] == "1" else "feet",
        "ball_flight": {
            "from": [float(fields[10]), float(fields[11])],
            "to": [float(fields[12]), float(fields[13])],
            "type": "pass",
            "on_target": False,
        },
        "randoms_used": int(fields[14]),
    }


def shot_xg_rust(details, on_target_prob: float, config):
    """Return clamped shot xG contribution from Rust."""
    explicit_xg = details.get("xg") if details else None
    line = "\t".join([
        "-" if explicit_xg is None else str(explicit_xg),
        str(on_target_prob),
        str(config.goal_reward_constant),
        "shot_xg",
    ])
    rows = _run_rust_rows("shot_xg", [line])
    return float(rows["shot_xg"][0])


def shot_phase_plan_rust(shooter, details, on_target_prob: float, attacking_right: bool, config, random_values):
    """Return the full shot phase execution plan from Rust."""
    explicit_xg = details.get("xg") if details else None
    line = "\t".join([
        shooter.name,
        str(shooter.pos[0]),
        str(shooter.pos[1]),
        "-" if explicit_xg is None else str(explicit_xg),
        str(on_target_prob),
        str(config.goal_reward_constant),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.goal_width),
        str(config.ball_shot_speed),
        *[str(value) for value in random_values],
        "shot_plan",
    ])
    rows = _run_rust_rows("shot_phase_plan", [line])
    fields = rows["shot_plan"]
    return {
        "shot_xg": float(fields[0]),
        "on_target": fields[1] == "1",
        "target": (float(fields[2]), float(fields[3])),
        "speed": float(fields[4]),
        "distance": float(fields[5]),
        "ticks_needed": int(fields[6]),
        "flight_type_code": int(fields[7]),
        "ball_flight": {
            "from": [float(fields[8]), float(fields[9])],
            "to": [float(fields[10]), float(fields[11])],
            "type": "shot",
            "on_target": fields[1] == "1",
        },
        "randoms_used": int(fields[12]),
        "event_text": fields[13],
    }


def shot_log_xg_rust(total_xg: float, shot_log, clamp_nonnegative: bool = False):
    """Return raw and rounded shot-log xG from Rust."""
    logged_sum = sum(s.get("xg", 0) for s in shot_log)
    line = "\t".join([
        str(total_xg),
        str(logged_sum),
        "1" if clamp_nonnegative else "0",
        "shot_log_xg",
    ])
    rows = _run_rust_rows("shot_log_xg", [line])
    fields = rows["shot_log_xg"]
    return {
        "raw_xg": float(fields[0]),
        "rounded_xg": float(fields[1]),
    }


def shot_arrival_event_rust(shooter_name: str, keeper_name: str, outcome: str):
    """Return shot-arrival event payload from Rust."""
    line = "\t".join([
        shooter_name,
        keeper_name,
        outcome,
        "shot_event",
    ])
    rows = _run_rust_rows("shot_arrival_event", [line])
    fields = rows["shot_event"]
    return {
        "pending_event_text": fields[0],
        "pause_ms": int(fields[1]),
        "trace_event": fields[2],
    }


def shot_log_entry_rust(origin, target, xg: float, in_box: bool, outcome: str):
    """Return shot log entry payload from Rust."""
    line = "\t".join([
        str(origin[0]),
        str(origin[1]),
        "-" if target is None else str(target[0]),
        "-" if target is None else str(target[1]),
        str(xg),
        "1" if in_box else "0",
        outcome,
        "shot_log",
    ])
    rows = _run_rust_rows("shot_log_entry", [line])
    fields = rows["shot_log"]
    payload = {
        "x": float(fields[0]),
        "y": float(fields[1]),
        "xg": float(fields[2]),
        "in_box": fields[3] == "1",
        "outcome": fields[4],
    }
    if fields[5] != "-":
        payload["target_x"] = float(fields[5])
    if fields[6] != "-":
        payload["target_y"] = float(fields[6])
    return payload


def goal_kick_spot_rust(team, config):
    """Return goal-kick spot from Rust."""
    line = "\t".join([
        "goal_kick_spot",
        "1" if team.attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "goal_kick_spot",
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["goal_kick_spot"]
    return (float(fields[0]), float(fields[1]))


def must_leave_penalty_area_for_goal_kick_rust(player, restart_team, config):
    """Return whether opponent must leave the goal-kick penalty area."""
    line = "\t".join([
        "must_leave_goal_kick_box",
        "1" if player.team_side == restart_team.side else "0",
        str(player.pos[0]),
        "1" if restart_team.attacking_right else "0",
        str(config.pitch_length),
        "must_leave",
    ])
    rows = _run_rust_rows("restart_helper", [line])
    return rows["must_leave"][0] == "1"


def kickoff_shape_targets_rust(restart_team, other_team, config):
    """Return kickoff shape targets and kicker index from Rust."""
    id_map = {}

    def payload(team, is_restart, offset):
        rows = []
        for player, base in zip(team.players, team._formation_coords):
            external_idx = player.index + offset
            id_map[external_idx] = (team.side, player.index)
            rows.append(",".join([
                str(external_idx),
                "1" if is_restart else "0",
                "1" if team.attacking_right else "0",
                str(base[0]),
                str(base[1]),
                str(player.pos[0]),
                str(player.pos[1]),
                "1" if player.is_goalkeeper else "0",
                player.position,
            ]))
        return rows

    players_payload = ";".join(payload(restart_team, True, 0) + payload(other_team, False, 1000)) or "-"
    line = "\t".join([
        "kickoff_shape",
        str(config.pitch_length),
        str(config.pitch_width),
        players_payload,
        "kickoff_shape",
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["kickoff_shape"]
    kicker_index = None if fields[0] == "-" else id_map.get(int(fields[0]))
    targets = {}
    if fields[1] != "-":
        for item in fields[1].split(";"):
            idx, x, y = item.split(",")
            key = id_map.get(int(idx))
            if key is not None:
                targets[key] = (float(x), float(y))
    return {
        "kicker_index": kicker_index,
        "targets": targets,
    }


def goal_kick_shape_targets_rust(restart_team, defending_team, config):
    """Return goal-kick shape targets from Rust."""
    id_map = {}

    def payload(team, is_restart, offset):
        rows = []
        for player in team.players:
            external_idx = player.index + offset
            id_map[external_idx] = (team.side, player.index)
            rows.append(",".join([
                str(external_idx),
                "1" if is_restart else "0",
                "1" if team.attacking_right else "0",
                "1" if restart_team.attacking_right else "0",
                str(player.base_formation_pos[0]),
                str(player.base_formation_pos[1]),
                "1" if player.is_goalkeeper else "0",
                "1" if player.is_attacker else "0",
                "1" if player.is_midfielder else "0",
                "1" if player.is_defender else "0",
            ]))
        return rows

    players_payload = ";".join(payload(restart_team, True, 0) + payload(defending_team, False, 1000)) or "-"
    line = "\t".join([
        "goal_kick_shape",
        str(config.pitch_length),
        str(config.pitch_width),
        players_payload,
        "goal_kick_shape",
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["goal_kick_shape"]
    targets = {}
    if fields[0] != "-":
        for item in fields[0].split(";"):
            idx, x, y = item.split(",")
            key = id_map.get(int(idx))
            if key is not None:
                targets[key] = (float(x), float(y))
    return targets


def restart_play_decision_rust(reason: str, restart_team, ball_pos, config, corner_roll: float):
    """Return restart ball position and receiver from Rust."""
    id_map = {}
    rows = []
    for player in restart_team.players:
        id_map[player.index] = player.index
        rows.append(",".join([
            str(player.index),
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if player.is_goalkeeper else "0",
        ]))
    players_payload = ";".join(rows) or "-"
    line = "\t".join([
        "restart_play",
        reason,
        str(config.pitch_length),
        "1" if restart_team.attacking_right else "0",
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(config.pitch_width),
        players_payload,
        str(corner_roll),
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["restart_play"]
    return {
        "ball_pos": (float(fields[0]), float(fields[1])),
        "receiver_idx": None if fields[2] == "-" else int(fields[2]),
        "set_receiver_pos": fields[3] == "1",
        "pending_cut": fields[4] == "1",
    }


def restart_play_plan_rust(reason: str, restart_team, ball_pos, config, corner_roll: float):
    """Return restart play receiver/ball/reset plan from Rust."""
    rows = []
    for player in restart_team.players:
        rows.append(",".join([
            str(player.index),
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if player.is_goalkeeper else "0",
        ]))
    players_payload = ";".join(rows) or "-"
    line = "\t".join([
        "restart_play_plan",
        reason,
        str(config.pitch_length),
        "1" if restart_team.attacking_right else "0",
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(config.pitch_width),
        players_payload,
        str(corner_roll),
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["restart_play_plan"]
    return {
        "ball_pos": (float(fields[0]), float(fields[1])),
        "receiver_idx": None if fields[2] == "-" else int(fields[2]),
        "set_receiver_pos": fields[3] == "1",
        "pending_cut": fields[4] == "1",
        "reset_last_passer": fields[5] == "1",
        "clear_offside_flags": fields[6] == "1",
    }


def restart_shape_plan_rust(reason: str, force: bool, restart_team, defending_team, config):
    """Return restart shape ball position, player targets, and snap decisions from Rust."""
    id_map = {}

    def payload(team, is_restart, offset):
        rows = []
        for player in team.players:
            external_idx = player.index + offset
            team_code = 0 if team.side == "home" else 1
            id_map[(team_code, external_idx)] = (team.side, player.index)
            rows.append(",".join([
                str(external_idx),
                str(team_code),
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

    players_payload = ";".join(
        payload(restart_team, True, 0)
        + payload(defending_team, False, 1000)
    ) or "-"
    line = "\t".join([
        "restart_shape_plan",
        reason,
        "1" if force else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        players_payload,
        "restart_shape_plan",
    ])
    rows = _run_rust_rows("restart_helper", [line])
    fields = rows["restart_shape_plan"]
    targets = {}
    if fields[3] != "-":
        for item in fields[3].split(";"):
            team_code_raw, external_idx_raw, x_raw, y_raw, snap_raw = item.split(",")
            key = id_map.get((int(team_code_raw), int(external_idx_raw)))
            if key is not None:
                targets[key] = {
                    "target": (float(x_raw), float(y_raw)),
                    "snap": snap_raw == "1",
                }
    return {
        "has_shape": fields[0] == "1",
        "ball_pos": (float(fields[1]), float(fields[2])),
        "targets": targets,
    }


def team_shape_plan_rust(team, ball_pos, config, pitch, opponent_players=None):
    """Return dynamic tactical anchors for a team from Rust."""
    players_payload = ";".join(
        ",".join([
            str(player.index),
            str(team._formation_coords[i][0]),
            str(team._formation_coords[i][1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for i, player in enumerate(team.players)
    ) or "-"
    opponents_payload = ";".join(
        ",".join([
            str(player.pos[0]),
            str(player.pos[1]),
            "1" if player.is_goalkeeper else "0",
        ])
        for player in (opponent_players or [])
    ) or "-"
    line = "\t".join([
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if team.attacking_right else "0",
        team.phase.value,
        str(config.pitch_length),
        str(config.pitch_width),
        "0.0",
        players_payload,
        opponents_payload,
        "team_shape",
    ])
    rows = _run_rust_rows("team_shape_plan", [line])
    raw = rows["team_shape"][0]
    if raw == "-":
        return {}
    anchors = {}
    for item in raw.split(";"):
        idx, x, y = item.split(",")
        anchors[int(idx)] = (float(x), float(y))
    return anchors


def team_phase_update_rust(team, has_possession: bool, ball_contested: bool, config):
    """Return team phase-state transition from Rust."""
    line = "\t".join([
        "1" if has_possession else "0",
        "1" if ball_contested else "0",
        "1" if team._had_possession_last_tick else "0",
        str(team._ticks_since_possession_change),
        str(config.transition_ticks),
        "team_phase",
    ])
    rows = _run_rust_rows("team_phase_update", [line])
    fields = rows["team_phase"]
    phase_by_code = {
        "0": "attacking",
        "1": "transition_atk",
        "2": "defending",
        "3": "transition_def",
        "4": "contesting",
    }
    return {
        "phase": phase_by_code[fields[0]],
        "ticks_since_possession_change": int(fields[1]),
        "had_possession_last_tick": fields[2] == "1",
    }


def track_pass_stats_rust(origin, target, attacking_right: bool, config):
    """Return pass stat increments from Rust."""
    line = "\t".join([
        "pass",
        str(origin[0]),
        str(origin[1]),
        str(target[0]),
        str(target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
    ])
    rows = _run_rust_rows("match_stats", [line])
    fields = rows["pass"]
    return {
        "crosses_attempted": int(fields[0]),
        "crosses_completed": int(fields[1]),
        "progressive_passes": int(fields[2]),
        "long_passes": int(fields[3]),
        "completed_long_passes": int(fields[4]),
        "passes_into_final_third": int(fields[5]),
        "passes_into_box": int(fields[6]),
    }


def track_carry_stats_rust(old_pos, new_pos, attacking_right: bool, config):
    """Return carry stat increments from Rust."""
    line = "\t".join([
        "carry",
        str(old_pos[0]),
        str(old_pos[1]),
        str(new_pos[0]),
        str(new_pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
    ])
    rows = _run_rust_rows("match_stats", [line])
    fields = rows["carry"]
    return {
        "progressive_carries": int(fields[0]),
        "carries_into_final_third": int(fields[1]),
        "carries_into_box": int(fields[2]),
    }


def generate_carry_offsets_rust(player, opponents, config, attacking_right: bool):
    """Generate carry candidate offsets in Rust."""
    nearest_opp = min(
        [_distance(player.pos, o.pos) for o in opponents if not o.is_goalkeeper],
        default=99.0,
    )
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.speed_value),
        str(player.abilities.get("Dribbling", 50)),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.carrier_speed),
        str(nearest_opp),
        "carry_offsets",
    ])
    rows = _run_rust_rows("carry_offsets", [line])
    payload = rows["carry_offsets"][0]
    if payload == "-":
        return []
    return [
        (float(parts[0]), float(parts[1]))
        for parts in (
            item.split(",")
            for item in payload.split(";")
        )
    ]


def evaluate_carry_path_rust(player, target, opponents, config, attacking_right: bool):
    """Evaluate carry path feasibility and threat metrics in Rust."""
    opponent_payload = ";".join(
        ",".join([
            str(o.pos[0]),
            str(o.pos[1]),
            str(o.abilities.get("Speed", 50)),
            str(o.abilities.get("Defence", 50)),
            str(o.abilities.get("Tackling", 50)),
            "1" if o.is_goalkeeper else "0",
        ])
        for o in opponents
    ) or "-"
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(target[0]),
        str(target[1]),
        str(player.abilities.get("Dribbling", 50)),
        str(config.tackle_range),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.carrier_speed),
        opponent_payload,
        "carry_path",
    ])
    rows = _run_rust_rows("carry_path", [line])
    fields = rows["carry_path"]
    return {
        "feasibility": float(fields[0]),
        "path_min_perp": float(fields[1]),
        "path_peak_threat": float(fields[2]),
        "path_peak_proj": float(fields[3]),
        "path_peak_final_third_control": float(fields[4]),
        "path_peak_control_factor": float(fields[5]),
    }


def finalize_carry_score_rust(value, feasibility: float, path_peak_threat: float, path_peak_final_third_control: float, consecutive_carries: int):
    """Apply carry conflict cost in Rust."""
    line = "\t".join([
        str(value.score),
        str(feasibility),
        str(path_peak_threat),
        str(path_peak_final_third_control),
        str(consecutive_carries),
        "carry_finalize",
    ])
    rows = _run_rust_rows("carry_finalize", [line])
    fields = rows["carry_finalize"]
    return {
        "score": float(fields[0]),
        "conflict_cost": float(fields[1]),
        "repeated_load": float(fields[2]),
        "feasibility_loss": float(fields[3]),
    }


def score_carry_options_rust(carrier, teammates, opponents, config, attacking_right: bool, current_state_value: float):
    """Generate and score carry options fully in Rust."""
    opponent_payload = ";".join(
        ",".join([
            str(o.pos[0]),
            str(o.pos[1]),
            str(o.abilities.get("Speed", 50)),
            str(o.abilities.get("Defence", 50)),
            str(o.abilities.get("Tackling", 50)),
            "1" if o.is_goalkeeper else "0",
        ])
        for o in opponents
    ) or "-"
    teammates_payload = _carry_support_payload(teammates)
    line = "\t".join([
        str(carrier.index),
        str(carrier.pos[0]),
        str(carrier.pos[1]),
        str(carrier.speed_value),
        str(carrier.abilities.get("Dribbling", 50)),
        str(carrier.abilities.get("Finishing", 50) / 100.0),
        str(carrier.abilities.get("Long_Shot", 50) / 100.0),
        str(carrier.consecutive_carries),
        str(carrier.possession_ticks),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.carrier_speed),
        str(config.tackle_range),
        str(current_state_value),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        "0.0",
        opponent_payload,
        teammates_payload,
        "carry_options",
    ])
    rows = _run_rust_rows("carry_options", [line])
    payload = rows["carry_options"][0]
    if payload == "-":
        return []
    results = []
    component_keys = (
        "continuity",
        "pv_gain",
        "future_shot_gain",
        "carry_to_shoot_window",
        "wide_second_line_carry_window",
        "byline_carry_window",
        "half_space_entry",
        "lane_gain",
        "progress_gain",
        "effective_gain",
        "near_goal_multiplier",
        "shooting_window_multiplier",
        "possession_multiplier",
        "final_third_stale_multiplier",
        "release_pressure",
        "support_nearby",
        "pressure_draw",
        "space_manipulation",
        "path_min_perp",
        "path_peak_threat",
        "path_peak_proj",
        "path_peak_final_third_control",
        "path_conflict_cost",
    )
    for item in payload.split(";"):
        values = [float(part) for part in item.split(",")]
        components = {
            key: value
            for key, value in zip(component_keys, values[6:])
        }
        components["support_release_cost"] = 1.0 + 0.55 * float(components.get("support_nearby", 0.0) or 0.0)
        results.append((
            values[0],
            "carry",
            {
                "target": (values[1], values[2]),
                "success_prob": values[3],
                "risk_cost": values[4],
                "current_value": current_state_value,
                "after_value": values[5],
                "components": components,
            },
        ))
    return results


def score_pass_point_option_tuples_rust(
    passer,
    teammates,
    opponents,
    config,
    pitch,
    attacking_right: bool,
    current_value: float | None = None,
):
    """Return `(score, "pass", details)` tuples from Rust pass batch output.

    This preserves the legacy Python `_score_pass_point_options` result shape
    for callers that still consume the compatibility layer.
    """
    rows = score_pass_point_options_rust(
        passer,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        current_value=current_value,
    )
    candidates = []
    for row in rows:
        target = row["target"]
        is_long = row["is_long"]
        target_kind = "space" if row["target_kind_space"] else "feet"
        vision = build_vision_context(passer, config, attacking_right)
        receiver = next((tm for tm in teammates if tm.index == row["receiver_idx"]), None)
        receiver_confidence = 0.0 if receiver is None else vision.confidence(passer.pos, receiver.pos)
        target_progress = (
            target[0] / max(1.0, config.pitch_length)
            if attacking_right
            else (config.pitch_length - target[0]) / max(1.0, config.pitch_length)
        )
        centrality = 1.0 - min(
            1.0,
            abs(target[1] - config.pitch_width / 2.0) / max(1.0, config.pitch_width / 2.0),
        )
        forward_dir = 1.0 if attacking_right else -1.0
        progress_gain = (target[0] - passer.pos[0]) * forward_dir / max(1.0, config.pitch_length)
        lateral_change = abs(target[1] - passer.pos[1]) / max(1.0, config.pitch_width)
        delta = row["after_value"] - (current_value or 0.0)
        origin_progress = (
            passer.pos[0] / max(1.0, config.pitch_length)
            if attacking_right
            else (config.pitch_length - passer.pos[0]) / max(1.0, config.pitch_length)
        )
        final_third_combination = (
            _smoothstep(0.78, 0.92, origin_progress)
            * _smoothstep(0.70, 0.84, target_progress)
            * _smoothstep(0.35, 0.70, centrality)
            * _smoothstep(0.04, 0.18, max(0.0, delta))
            * (1.0 - _smoothstep(0.35, 0.80, row["receiver_pressure"]))
        )
        high_threat_space = (
            _smoothstep(0.72, 0.90, target_progress)
            * _smoothstep(0.24, 0.52, centrality)
            * _smoothstep(0.04, 0.18, max(0.0, delta))
            * (1.0 - _smoothstep(0.45, 0.85, row["receiver_pressure"]))
        )
        second_line_arc_candidate = 0.0
        if receiver is not None:
            receiver_base_progress = (
                receiver.base_formation_pos[0] / max(1.0, config.pitch_length)
                if attacking_right
                else (config.pitch_length - receiver.base_formation_pos[0]) / max(1.0, config.pitch_length)
            )
            second_line_role = (
                0.42 <= receiver_base_progress <= 0.68
                and not receiver.is_defender
            )
            if (
                second_line_role
                and origin_progress > 0.68
                and 0.70 <= target_progress <= 0.84
                and centrality > 0.58
            ):
                second_line_arc_candidate = min(1.0, (target_progress - 0.70) / 0.14) * centrality
        details = {
            "target": target,
            "success_prob": row["success_prob"],
            "lane_risk": row["lane_risk"],
            "turnover_consequence": row["turnover_consequence"],
            "current_value": current_value,
            "after_value": row["after_value"],
            "risk_cost": row["risk_cost"],
            "is_long": is_long,
            "pass_type": "long_pass" if is_long else "short_pass",
            "components": {
                "current_value": current_value,
                "after_value": row["after_value"],
                "delta": delta,
                "effective_delta": row["effective_delta"],
                "continuity": row["continuity"],
                "lane_risk": row["lane_risk"],
                "receiver_pressure": row["receiver_pressure"],
                "turnover_consequence": row["turnover_consequence"],
                "receiver_arrival": row["receiver_arrival"],
                "base_accuracy": row["base_accuracy"],
                "receiver_goal_fit": row["receiver_goal_fit"],
                "distance": row["distance"],
                "target_progress": target_progress,
                "centrality": centrality,
                "progress_gain": progress_gain,
                "lateral_change": lateral_change,
                "high_threat_space": high_threat_space,
                "final_third_combination": final_third_combination,
                "second_line_arc_candidate": second_line_arc_candidate,
                "vision_facing": vision.facing,
                "vision_fov": vision.fov,
                "vision_max_distance": vision.max_distance,
                "vision_receiver_confidence": receiver_confidence,
                "vision_target_confidence": row["perception"],
                "vision_multiplier": row["perception_multiplier"],
                "arrival_margin": row["arrival_margin"],
                "defender_first_risk": row["defender_first_risk"],
                "target_occupation_risk": row["target_occupation_risk"],
                "nearest_teammate_to_target": row["nearest_teammate_to_target"],
                "nearest_opp_to_target": row["nearest_opp_to_target"],
                "box_space_pressure": row["box_space_pressure"],
                "tactical_space": row["tactical_space"],
                "tactical_space_pattern": "value_field_space" if row["tactical_space"] else "",
                "tactical_space_prior": row["tactical_space_prior"],
                "tactical_space_value": row["tactical_space_value"],
                "tactical_space_visibility": row["tactical_space_visibility"],
                "expected_arrival_confidence": row["expected_arrival_confidence"],
                "expected_arrival_fit": row["expected_arrival_fit"],
                "target_kind": target_kind,
                "success_prob": row["success_prob"],
                "risk_cost": row["risk_cost"],
                "final_score": row["raw_score"],
            },
        }
        if row["target_kind_space"]:
            details["intended_receiver"] = row["receiver_idx"]
        else:
            details["target_player_idx"] = row["receiver_idx"]
        candidates.append((row["score"], "pass", details))
    return candidates


def evaluate_hold_rust(
    player,
    current_pv: float,
    pressure: int,
    nearest_pressure: float,
    developing_runs: float,
    best_pass_score: float,
    shoot_score: float,
    opportunity_wait_value: float,
):
    """Evaluate hold using the Rust hold kernel with Python ValueResult shape."""
    line = "\t".join([
        str(player.iq_value / 100.0),
        "1" if player.is_midfielder else "0",
        "1" if player.is_defender else "0",
        str(player.hold_ticks),
        str(player.possession_ticks),
        str(current_pv),
        str(pressure),
        str(nearest_pressure),
        str(developing_runs),
        str(best_pass_score),
        str(shoot_score),
        str(opportunity_wait_value),
        "hold",
    ])
    rows = _run_rust_rows("hold", [line])
    fields = rows["hold"]
    components = {
        "pressure_factor": float(fields[1]),
        "useful_development": float(fields[2]),
        "no_clear_release": float(fields[3]),
        "opportunity_wait": float(fields[4]),
        "opportunity_cost": float(fields[5]),
    }
    return ValueResult(score=float(fields[0]), components=components)


def evaluate_clear_rust(x_progress: float, pressure: int, clear_reward_base: float):
    """Evaluate clear using the Rust clear kernel with Python ValueResult shape."""
    line = "\t".join([
        str(x_progress),
        str(pressure),
        str(clear_reward_base),
        "clear",
    ])
    rows = _run_rust_rows("clear", [line])
    fields = rows["clear"]
    score = float(fields[0])
    components = {
        "current_value": 0.0,
        "after_value": 0.0,
        "delta": 0.0,
        "success_prob": 1.0,
        "risk_cost": 0.0,
        "opportunity_cost": 0.0,
        "continuity": 0.0,
        "final_score": score,
        "danger": float(fields[1]),
        "pressure_factor": float(fields[2]),
    }
    return ValueResult(
        score=score,
        success_prob=1.0,
        risk_cost=0.0,
        current_value=0.0,
        after_value=0.0,
        components=components,
    )


def _shot_support_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.index},{p.pos[0]},{p.pos[1]},{p.target_pos[0]},{p.target_pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in players
    )


def _carry_support_payload(players):
    if not players:
        return "-"
    return ";".join(
        f"{p.index},{p.pos[0]},{p.pos[1]},{p.base_formation_pos[0]},{p.base_formation_pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in players
    )


def _off_ball_candidates_payload(candidates):
    if not candidates:
        return "-"
    return ";".join(
        f"{x},{y},{anchor[0]},{anchor[1]}"
        for x, y, anchor in candidates
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


def _defender_actions_payload(players, defender_actions, defender_new_positions):
    if not players:
        return "-"
    return ";".join(
        ",".join([
            str(p.index),
            str(p.pos[0]),
            str(p.pos[1]),
            str(defender_new_positions.get(p.index, p.pos)[0]),
            str(defender_new_positions.get(p.index, p.pos)[1]),
            str(defender_actions.get(p.index, "")),
            str(p.abilities.get("Speed", 50)),
            str(p.abilities.get("Defence", 50)),
        ])
        for p in players
    )


def detect_interactions_rust(
    holder,
    holder_action_type: str,
    action_target,
    defenders,
    defender_actions,
    defender_new_positions,
    config,
):
    """Detect duel/interception/wasted-tackle interactions in one Rust call."""
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        holder_action_type,
        str(action_target[0]),
        str(action_target[1]),
        str(config.tackle_range),
        str(config.interception_reach),
        _defender_actions_payload(defenders, defender_actions, defender_new_positions),
        "interactions",
        "interactions",
    ])
    rows = _run_rust_rows("detect_interactions", [line])
    fields = rows["interactions"]
    from .interactions import Interaction, InteractionType

    def interaction_from_fields(kind, idx_raw, distance_raw, attacker):
        if idx_raw == "-":
            return None
        defender_idx = int(idx_raw)
        defender = next((p for p in defenders if p.index == defender_idx), None)
        if defender is None:
            return None
        return Interaction(
            interaction_type=kind,
            attacker=attacker,
            defender=defender,
            distance=float(distance_raw),
        )

    duel = interaction_from_fields(
        InteractionType.DUEL,
        fields[0],
        fields[1],
        holder,
    )
    interception = interaction_from_fields(
        InteractionType.INTERCEPTION,
        fields[2],
        fields[3],
        None,
    )
    wasted = []
    if fields[4] != "-":
        for item in fields[4].split(";"):
            idx_raw, distance_raw = item.split(":")
            interaction = interaction_from_fields(
                InteractionType.WASTED_TACKLE,
                idx_raw,
                distance_raw,
                holder,
            )
            if interaction is not None:
                wasted.append(interaction)
    return duel, interception, wasted


def track_defensive_pressures_rust(
    holder,
    holder_action_type: str,
    defenders,
    defender_actions,
    defender_new_positions,
    config,
    duel_detected: bool,
    interception_detected: bool,
):
    """Return defender pressure tracking decisions from Rust."""
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        holder_action_type,
        str(config.press_radius),
        _defender_actions_payload(defenders, defender_actions, defender_new_positions),
        "1" if duel_detected else "0",
        "1" if interception_detected else "0",
    ])
    rows = _run_rust_rows("defensive_pressures", [line])
    raw = rows["pressures"][0]
    if raw == "-":
        return {}
    result = {}
    for item in raw.split(";"):
        idx_raw, successful_raw = item.split(":")
        result[int(idx_raw)] = successful_raw == "1"
    return result


def defensive_pressure_adjust_plan_rust(
    holder,
    holder_team_attacking_right: bool,
    opp_team_attacking_right: bool,
    holder_action_type: str,
    ball_is_held_by_holder: bool,
    defenders,
    config,
):
    """Return post-carry defensive pressure target nudges from Rust."""
    payload = ";".join(
        ",".join([
            str(p.index),
            str(p.pos[0]),
            str(p.pos[1]),
            str(p.target_pos[0]),
            str(p.target_pos[1]),
            p.movement_intent,
        ])
        for p in defenders
    ) or "-"
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(holder.consecutive_carries),
        "1" if holder_team_attacking_right else "0",
        "1" if opp_team_attacking_right else "0",
        holder_action_type,
        "1" if ball_is_held_by_holder else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.tackle_range),
        str(config.press_radius),
        "0.0",
        payload,
        "pressure_adjust",
    ])
    rows = _run_rust_rows("defensive_pressure_adjust", [line])
    raw = rows["pressure_adjust"][0]
    if raw == "-":
        return {}
    result = {}
    for item in raw.split(";"):
        idx_raw, x_raw, y_raw, intent_raw = item.split(",")
        result[int(idx_raw)] = {
            "target": (float(x_raw), float(y_raw)),
            "movement_intent": "press" if intent_raw == "1" else None,
        }
    return result


def defense_zone_helper_rust(kind: str, player, ball_pos, attackers, attacking_right: bool, config):
    """Return mark-runner/block-lane zone helper score and target from Rust."""
    attackers_payload = ";".join(
        f"{attacker.pos[0]},{attacker.pos[1]}"
        for attacker in attackers
    ) or "-"
    op = "mark" if kind == "mark" else "block"
    line = "\t".join([
        op,
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.tactical_anchor[0]),
        str(player.tactical_anchor[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        attackers_payload,
        "defense_zone",
    ])
    rows = _run_rust_rows("defense_zone_helper", [line])
    fields = rows["defense_zone"]
    return float(fields[0]), (float(fields[1]), float(fields[2]))


def tackle_score_rust(player, ball_carrier, dist_to_ball: float, config):
    """Return tackle score from Rust."""
    line = "\t".join([
        "score_tackle",
        str(player.abilities.get("Tackling", 50)),
        str(ball_carrier.abilities.get("Dribbling", 50)),
        str(dist_to_ball),
        str(config.tackle_range),
        "tackle",
    ])
    rows = _run_rust_rows("physics", [line])
    return float(rows["tackle"][0])


def gk_position_adjust_rust(ball_pos, attacking_right: bool, config):
    """Return goalkeeper positioning target from Rust."""
    line = "\t".join([
        "gk_position_adjust",
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "gk_position",
    ])
    rows = _run_rust_rows("physics", [line])
    fields = rows["gk_position"]
    return (float(fields[0]), float(fields[1]))


def pass_control_strength_rust(score: float, config):
    """Return pass-arrival control strength from Rust."""
    line = "\t".join([
        "pass_control_strength",
        str(score),
        str(config.contest_radius),
        "pass_control",
    ])
    rows = _run_rust_rows("physics", [line])
    return float(rows["pass_control"][0])


def pass_loose_control_strength_rust(teammate_control: float, opponent_control: float):
    """Return loose pass-arrival control strength from Rust."""
    line = "\t".join([
        "pass_loose_control_strength",
        str(teammate_control),
        str(opponent_control),
        "pass_loose_control",
    ])
    rows = _run_rust_rows("physics", [line])
    return float(rows["pass_loose_control"][0])


def resolve_duel_rust(interaction, attacker_uniform: float, defender_uniform: float):
    """Resolve a duel in Rust with explicit roll offsets."""
    attacker = interaction.attacker
    defender = interaction.defender
    line = "\t".join([
        str(attacker.abilities.get("Dribbling", 50)),
        str(defender.abilities.get("Tackling", 50)),
        str(attacker_uniform),
        str(defender_uniform),
        "duel",
    ])
    rows = _run_rust_rows("resolve_duel", [line])
    outcome = rows["duel"][0]
    from .interactions import DuelOutcome, DuelResult

    if outcome == "attacker_wins":
        return DuelResult(DuelOutcome.ATTACKER_WINS, winner=attacker, loser=defender)
    if outcome == "defender_wins":
        return DuelResult(DuelOutcome.DEFENDER_WINS, winner=defender, loser=attacker)
    return DuelResult(DuelOutcome.LOOSE_BALL, winner=None, loser=None)


def duel_phase_plan_rust(holder, defender, config, random_values):
    """Return full duel phase outcome and loose-ball payload from Rust."""
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(config.pitch_length),
        str(config.pitch_width),
        str(holder.abilities.get("Dribbling", 50)),
        str(defender.abilities.get("Tackling", 50)),
        str(random_values[0]),
        str(random_values[1]),
        str(random_values[2]),
        str(random_values[3]),
        "duel_plan",
    ])
    rows = _run_rust_rows("duel_phase_plan", [line])
    fields = rows["duel_plan"]
    return {
        "outcome": {0: "attacker_wins", 1: "defender_wins", 2: "loose_ball"}[int(fields[0])],
        "loose_pos": (float(fields[1]), float(fields[2])),
        "randoms_used": int(fields[3]),
    }


def resolve_interception_rust(interaction, passer_ability: int, random_value: float, config):
    """Resolve an interception in Rust with explicit random value."""
    defender = interaction.defender
    line = "\t".join([
        str(defender.abilities.get("Defence", 50)),
        str(passer_ability),
        str(interaction.distance),
        str(config.interception_reach),
        str(random_value),
        "interception",
    ])
    rows = _run_rust_rows("resolve_interception", [line])
    return rows["interception"][0] == "1"


def execute_carry_rust(
    holder,
    target,
    attacking_right: bool,
    opponents,
    config,
    random_values,
):
    """Compute carry execution result in Rust with explicit random values."""
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(target[0]),
        str(target[1]),
        str(holder.speed_value),
        str(holder.abilities.get("Dribbling", 50)),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.carrier_speed),
        str(config.carry_error_divisor),
        str(holder.consecutive_carries),
        str(random_values[0]),
        str(random_values[1]),
        opponent_payload,
        str(random_values[2]),
        "carry_exec",
    ])
    rows = _run_rust_rows("carry_execution", [line])
    fields = rows["carry_exec"]
    return {
        "carry_speed": float(fields[0]),
        "carry_difficulty": float(fields[1]),
        "new_pos": (float(fields[2]), float(fields[3])),
        "distance_covered": float(fields[4]),
        "error_chance": float(fields[5]),
        "is_error": fields[6] == "1",
        "loose_pos": (float(fields[7]), float(fields[8])),
        "randoms_used": 3 if fields[6] == "1" else 1,
    }


def carry_phase_plan_rust(
    holder,
    target,
    attacking_right: bool,
    opponents,
    config,
    random_values,
):
    """Return the full carry phase execution plan from Rust."""
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(target[0]),
        str(target[1]),
        str(holder.speed_value),
        str(holder.abilities.get("Dribbling", 50)),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.carrier_speed),
        str(config.carry_error_divisor),
        str(holder.consecutive_carries),
        str(random_values[0]),
        str(random_values[1]),
        opponent_payload,
        str(random_values[2]),
        "carry_plan",
    ])
    rows = _run_rust_rows("carry_phase_plan", [line])
    fields = rows["carry_plan"]
    return {
        "carry_speed": float(fields[0]),
        "carry_difficulty": float(fields[1]),
        "new_pos": (float(fields[2]), float(fields[3])),
        "distance_covered": float(fields[4]),
        "error_chance": float(fields[5]),
        "is_error": fields[6] == "1",
        "loose_pos": (float(fields[7]), float(fields[8])),
        "randoms_used": int(fields[9]),
    }


def execute_pass_rust(
    passer,
    ideal_target,
    is_long: bool,
    lane_risk: float,
    opponents,
    config,
    random_values,
):
    """Compute pass execution result in Rust with explicit random values."""
    passing = passer.abilities.get("Long_Passing" if is_long else "Short_Passing", 50)
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    line = "\t".join([
        str(passer.pos[0]),
        str(passer.pos[1]),
        str(ideal_target[0]),
        str(ideal_target[1]),
        str(passing),
        "1" if is_long else "0",
        str(lane_risk),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.ball_pass_speed),
        str(config.ball_long_pass_speed),
        opponent_payload,
        str(config.pass_error_divisor),
        str(random_values[0]),
        str(random_values[1]),
        str(random_values[2]),
        str(random_values[3]),
        str(random_values[4]),
        "pass_exec",
    ])
    rows = _run_rust_rows("pass_execution", [line])
    fields = rows["pass_exec"]
    return {
        "target": (float(fields[0]), float(fields[1])),
        "error_radius": float(fields[2]),
        "error_chance": float(fields[3]),
        "is_error": fields[4] == "1",
        "used_target_error": fields[5] == "1",
        "randoms_used": int(fields[6]),
        "stray_pos": (float(fields[7]), float(fields[8])),
        "ticks_needed": int(fields[9]),
        "speed": float(fields[10]),
        "flight_type_code": int(fields[11]),
    }


def execute_shot_rust(
    shooter,
    on_target_prob: float,
    attacking_right: bool,
    config,
    random_values,
):
    """Compute shot execution result in Rust with explicit random values."""
    line = "\t".join([
        str(shooter.pos[0]),
        str(shooter.pos[1]),
        str(on_target_prob),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.goal_width),
        str(config.ball_shot_speed),
        str(random_values[0]),
        str(random_values[1]),
        str(random_values[2]),
        "0.0",
        "shot_exec",
    ])
    rows = _run_rust_rows("shot_execution", [line])
    fields = rows["shot_exec"]
    return {
        "on_target": fields[0] == "1",
        "target": (float(fields[1]), float(fields[2])),
        "ticks_needed": int(fields[3]),
        "randoms_used": int(fields[4]),
        "speed": float(fields[5]) if len(fields) > 5 else config.ball_shot_speed,
        "distance": float(fields[6]) if len(fields) > 6 else _distance(shooter.pos, (float(fields[1]), float(fields[2]))),
        "flight_type_code": int(fields[7]) if len(fields) > 7 else 3,
        "event_text": f"{'SHOT ON TARGET' if fields[0] == '1' else 'SHOT'} {shooter.name} shoots!",
    }


def execute_clear_rust(clearer, target, config):
    """Compute clearance flight parameters in Rust."""
    line = "\t".join([
        str(clearer.pos[0]),
        str(clearer.pos[1]),
        str(target[0]),
        str(target[1]),
        str(config.ball_long_pass_speed),
        "clear_exec",
    ])
    rows = _run_rust_rows("clear_execution", [line])
    fields = rows["clear_exec"]
    return {
        "speed": float(fields[0]),
        "ticks_needed": int(fields[1]),
        "origin": (float(fields[2]), float(fields[3])) if len(fields) > 3 else clearer.pos,
        "target": (float(fields[4]), float(fields[5])) if len(fields) > 5 else target,
        "flight_type_code": int(fields[6]) if len(fields) > 6 else 2,
    }


def clear_phase_plan_rust(clearer, target, config):
    """Return the full clearance phase execution plan from Rust."""
    line = "\t".join([
        str(clearer.pos[0]),
        str(clearer.pos[1]),
        str(target[0]),
        str(target[1]),
        str(config.ball_long_pass_speed),
        "clear_plan",
    ])
    rows = _run_rust_rows("clear_phase_plan", [line])
    fields = rows["clear_plan"]
    return {
        "origin": (float(fields[0]), float(fields[1])),
        "target": (float(fields[2]), float(fields[3])),
        "speed": float(fields[4]),
        "ticks_needed": int(fields[5]),
        "flight_type_code": int(fields[6]),
    }


def generate_clear_target_rust(player, attacking_right: bool, config, depth_roll: float, lateral_roll: float):
    """Generate clear target in Rust with explicit random samples."""
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(depth_roll),
        str(lateral_roll),
        "clear_target",
    ])
    rows = _run_rust_rows("clear_target", [line])
    fields = rows["clear_target"]
    return (float(fields[0]), float(fields[1]))


def generate_gk_fallback_target_rust(attacking_right: bool, config):
    """Generate GK fallback target in Rust."""
    line = "\t".join([
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "gk_fallback",
    ])
    rows = _run_rust_rows("gk_fallback_target", [line])
    fields = rows["gk_fallback"]
    return (float(fields[0]), float(fields[1]))


def choose_gk_distribution_rust(gk, teammates, opponents, config, pitch, attacking_right: bool):
    """Choose goalkeeper distribution using Rust-backed pass/fallback kernels."""
    current_state_value = state_value_rust(gk, teammates, opponents, config, pitch, attacking_right)
    pass_candidates = score_pass_point_option_tuples_rust(
        gk,
        teammates,
        opponents,
        config,
        pitch,
        attacking_right,
        current_value=current_state_value,
    )
    if pass_candidates:
        from .decision import iq_decision_noise
        import random

        noise_scale = iq_decision_noise(gk.iq_value) * config.iq_noise_scale
        score_noises = [random.gauss(0.0, noise_scale) for _ in pass_candidates]
        rng_after_noise = random.getstate()
        roll_rng = random.Random()
        roll_rng.setstate(rng_after_noise)
        roll = roll_rng.random()
        chosen_index = softmax_select_index_rust(
            [score * (1.0 + noise) for (score, _action, _details), noise in zip(pass_candidates, score_noises)],
            gk.iq_value,
            roll,
            fallback_index=0,
        )
        random.random()
        selected = pass_candidates[chosen_index if chosen_index is not None else 0]
        return selected[1], selected[2]

    fallback = []
    for tm in teammates:
        if tm.index == gk.index or tm.is_goalkeeper:
            continue
        target = tm.pos
        d = _distance(gk.pos, target)
        if d < 4.0 or d > 70.0:
            continue
        is_long = d > 32.0
        passing = gk.abilities.get("Long_Passing" if is_long else "Short_Passing", 50) / 100.0
        base = config.long_pass_base_success if is_long else config.short_pass_base_success
        dist_factor = max(0.30, 1.0 - max(0.0, d - 10.0) / 72.0)
        base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor
        rows = _run_rust_rows("expected_pass", ["\t".join([
            str(gk.pos[0]),
            str(gk.pos[1]),
            str(target[0]),
            str(target[1]),
            str(gk.abilities.get("Finishing", 50) / 100.0),
            str(gk.abilities.get("Long_Shot", 50) / 100.0),
            str(gk.consecutive_carries),
            str(tm.index),
            str(tm.abilities.get("Finishing", 50) / 100.0),
            str(tm.abilities.get("Long_Shot", 50) / 100.0),
            str(tm.tactical_anchor[0]),
            str(tm.tactical_anchor[1]),
            str(tm.base_formation_pos[0]),
            str(tm.base_formation_pos[1]),
            "1" if attacking_right else "0",
            str(config.pitch_length),
            str(config.pitch_width),
            str(config.interception_reach),
            str(config.shot_ideal_distance),
            str(config.shot_on_target_base),
            str(config.gk_save_base),
            str(current_state_value),
            str(base_accuracy),
            "1.0",
            "0.055",
            _positions_payload([(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]),
            _indexed_positions_payload([(t.index, t.pos[0], t.pos[1]) for t in teammates]),
            "-",
            "-",
            "-",
            "0.0",
            "gk_pass",
        ])])
        fields = rows["gk_pass"]
        score = float(fields[0])
        success_prob = float(fields[1])
        risk_cost = float(fields[2])
        after_value = float(fields[3])
        lane_risk = float(fields[6])
        receiver_pressure_value = float(fields[7])
        turnover_consequence_value = float(fields[8])
        safety = success_prob * (1.0 - receiver_pressure_value) * (1.0 - lane_risk)
        rank = score + after_value * 0.12 + safety * 0.040 - risk_cost * 0.20
        fallback.append((rank, {
            "target": target,
            "target_player_idx": tm.index,
            "success_prob": success_prob,
            "lane_risk": lane_risk,
            "turnover_consequence": turnover_consequence_value,
            "current_value": current_state_value,
            "after_value": after_value,
            "risk_cost": risk_cost,
            "is_long": is_long,
            "pass_type": "long_pass" if is_long else "short_pass",
            "components": {
                "target_kind": "feet",
                "gk_fallback": True,
                "lane_risk": lane_risk,
                "receiver_pressure": receiver_pressure_value,
                "turnover_consequence": turnover_consequence_value,
                "success_prob": success_prob,
                "risk_cost": risk_cost,
                "current_value": current_state_value,
                "after_value": after_value,
            },
        }))
    if fallback:
        _, details = max(fallback, key=lambda item: item[0])
        return "pass", details

    target = generate_gk_fallback_target_rust(attacking_right, config)
    return "pass", {
        "target": target,
        "target_player_idx": -1,
        "success_prob": 0.35,
        "is_long": True,
        "pass_type": "long_pass",
    }


def apply_iq_noise_score_rust(score: float, iq: float, config, gaussian: float):
    """Apply IQ decision noise to a score using Rust formula."""
    line = "\t".join([
        str(score),
        str(iq),
        str(config.iq_noise_scale),
        str(gaussian),
        "iq_noise",
    ])
    rows = _run_rust_rows("iq_noise_score", [line])
    fields = rows["iq_noise"]
    return {
        "score": float(fields[0]),
        "noise_scale": float(fields[1]),
    }


def execute_hold_rust(
    holder,
    attacking_right: bool,
    opponents,
    opportunity_target,
    config,
    random_values,
):
    """Compute hold/shield execution result in Rust with explicit random values."""
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    has_opportunity = (
        isinstance(opportunity_target, (list, tuple))
        and len(opportunity_target) >= 2
    )
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(holder.abilities.get("Dribbling", 50)),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.carry_error_divisor),
        opponent_payload,
        str(float(opportunity_target[0])) if has_opportunity else "-",
        str(float(opportunity_target[1])) if has_opportunity else "-",
        str(random_values[0]),
        str(random_values[1]),
        str(random_values[2]),
        "hold_exec",
    ])
    rows = _run_rust_rows("hold_execution", [line])
    fields = rows["hold_exec"]
    return {
        "new_pos": (float(fields[0]), float(fields[1])),
        "distance_covered": float(fields[2]),
        "pressure": float(fields[3]),
        "nearest_dist": float(fields[4]),
        "error_chance": float(fields[5]),
        "is_error": fields[6] == "1",
        "loose_pos": (float(fields[7]), float(fields[8])),
        "randoms_used": int(fields[9]),
        "trace_pressure": float(fields[10]) if len(fields) > 10 else round(float(fields[3]), 2),
        "trace_nearest_def": None if len(fields) > 11 and fields[11] == "-" else (
            float(fields[11]) if len(fields) > 11 else (
                round(float(fields[4]), 1) if float(fields[4]) < 999 else None
            )
        ),
    }


def hold_phase_plan_rust(
    holder,
    attacking_right: bool,
    opponents,
    opportunity_target,
    config,
    random_values,
):
    """Return the full hold phase execution plan from Rust."""
    opponent_payload = ";".join(
        f"{p.pos[0]},{p.pos[1]},{1 if p.is_goalkeeper else 0}"
        for p in opponents
    ) or "-"
    has_opportunity = (
        isinstance(opportunity_target, (list, tuple))
        and len(opportunity_target) >= 2
    )
    line = "\t".join([
        str(holder.pos[0]),
        str(holder.pos[1]),
        str(holder.abilities.get("Dribbling", 50)),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.carry_error_divisor),
        opponent_payload,
        str(float(opportunity_target[0])) if has_opportunity else "-",
        str(float(opportunity_target[1])) if has_opportunity else "-",
        str(random_values[0]),
        str(random_values[1]),
        str(random_values[2]),
        "hold_plan",
    ])
    rows = _run_rust_rows("hold_phase_plan", [line])
    fields = rows["hold_plan"]
    return {
        "new_pos": (float(fields[0]), float(fields[1])),
        "distance_covered": float(fields[2]),
        "pressure": float(fields[3]),
        "nearest_dist": float(fields[4]),
        "error_chance": float(fields[5]),
        "is_error": fields[6] == "1",
        "loose_pos": (float(fields[7]), float(fields[8])),
        "randoms_used": int(fields[9]),
        "trace_pressure": float(fields[10]),
        "trace_nearest_def": None if fields[11] == "-" else float(fields[11]),
    }


def _arrival_players_payload(players, passer_idx: int, intended_receiver_idx: int, is_passer_team: bool):
    if not players:
        return "-"
    parts = []
    for p in players:
        goal = getattr(p, "current_goal", None)
        goal_x = "-" if goal is None else str(goal.target_pos[0])
        goal_y = "-" if goal is None else str(goal.target_pos[1])
        parts.append(",".join([
            str(p.index),
            str(p.pos[0]),
            str(p.pos[1]),
            str(p.target_pos[0]),
            str(p.target_pos[1]),
            goal_x,
            goal_y,
            str(p.speed_value),
            "1" if is_passer_team and p.index == passer_idx else "0",
            "1" if is_passer_team and p.index == intended_receiver_idx else "0",
            "1" if is_passer_team else "0",
        ]))
    return ";".join(parts)


def resolve_pass_arrival_rust(
    flight,
    target_pos,
    passer_team,
    opp_team,
    config,
    target_occupation_weight: float = 0.18,
):
    """Resolve pass-arrival control owner in Rust."""
    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        str(flight.ticks_total),
        str(config.contest_radius),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(target_occupation_weight),
        _arrival_players_payload(
            passer_team.players,
            flight.passer_idx,
            flight.intended_receiver_idx,
            True,
        ),
        _arrival_players_payload(
            opp_team.players,
            flight.passer_idx,
            -1,
            False,
        ),
        "pass_arrival",
    ])
    rows = _run_rust_rows("pass_arrival", [line])
    fields = rows["pass_arrival"]
    winner_by_code = {"0": "receiver", "1": "opponent", "2": "loose"}
    return {
        "winner": winner_by_code.get(fields[0], "loose"),
        "receiver_idx": None if fields[1] == "-" else int(fields[1]),
        "receiver_score": float(fields[2]),
        "receiver_control": float(fields[3]),
        "opponent_idx": None if fields[4] == "-" else int(fields[4]),
        "opponent_score": float(fields[5]),
        "opponent_control": float(fields[6]),
        "loose_control": float(fields[7]),
    }


def pass_arrival_plan_rust(
    flight,
    target_pos,
    passer_team,
    opp_team,
    config,
    target_occupation_weight: float = 0.18,
):
    """Return pass-arrival outcome plus loose-ball velocity from Rust."""
    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        str(flight.origin[0]),
        str(flight.origin[1]),
        str(flight.speed),
        str(flight.ticks_total),
        str(config.contest_radius),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(target_occupation_weight),
        "0.0",
        _arrival_players_payload(
            passer_team.players,
            flight.passer_idx,
            flight.intended_receiver_idx,
            True,
        ),
        _arrival_players_payload(
            opp_team.players,
            flight.passer_idx,
            -1,
            False,
        ),
        "pass_arrival_plan",
    ])
    rows = _run_rust_rows("pass_arrival_plan", [line])
    fields = rows["pass_arrival_plan"]
    winner_by_code = {"0": "receiver", "1": "opponent", "2": "loose"}
    return {
        "winner": winner_by_code.get(fields[0], "loose"),
        "receiver_idx": None if fields[1] == "-" else int(fields[1]),
        "opponent_idx": None if fields[2] == "-" else int(fields[2]),
        "loose_velocity": (float(fields[3]), float(fields[4])),
        "receiver_score": float(fields[5]),
        "receiver_control": float(fields[6]),
        "opponent_score": float(fields[7]),
        "opponent_control": float(fields[8]),
        "loose_control": float(fields[9]),
    }


def resolve_first_touch_rust(receiver, target_pos, config, randoms):
    """Resolve first-touch error in Rust with explicit random values."""
    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        str(receiver.abilities.get("IQ", 50)),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.first_touch_error_divisor),
        str(randoms[0]),
        str(randoms[1]),
        str(randoms[2]),
    ])
    rows = _run_rust_rows("first_touch", [line])
    fields = rows["first_touch"]
    return {
        "error_chance": float(fields[0]),
        "is_error": fields[1] == "1",
        "loose_pos": (float(fields[2]), float(fields[3])),
        "randoms_used": 3 if fields[1] == "1" else 1,
    }


def pass_receive_plan_rust(receiver, target_pos, offside_flagged: bool, config, randoms):
    """Return the full pass receive completion plan from Rust."""
    line = "\t".join([
        str(receiver.pos[0]),
        str(receiver.pos[1]),
        str(target_pos[0]),
        str(target_pos[1]),
        str(receiver.abilities.get("IQ", 50)),
        "1" if offside_flagged else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.first_touch_error_divisor),
        str(randoms[0]),
        str(randoms[1]),
        str(randoms[2]),
        "receive_plan",
    ])
    rows = _run_rust_rows("pass_receive_plan", [line])
    fields = rows["receive_plan"]
    return {
        "outcome": {0: "receive", 1: "first_touch_error", 2: "offside"}[int(fields[0])],
        "receive_pos": (float(fields[1]), float(fields[2])),
        "loose_pos": (float(fields[3]), float(fields[4])),
        "distance_covered": float(fields[5]),
        "receive_kind": "space" if fields[6] == "1" else "feet",
        "first_touch_error_chance": float(fields[7]),
        "randoms_used": int(fields[8]),
    }


def resolve_shot_arrival_rust(flight, shooter_team, defending_team, config, save_roll: float):
    """Resolve shot-arrival save/goal/off-target classification in Rust."""
    gk = defending_team.goalkeeper
    line = "\t".join([
        str(flight.origin[0]),
        str(flight.origin[1]),
        str(flight.target[0]),
        str(flight.target[1]),
        "1" if shooter_team.attacking_right else "0",
        "1" if flight.on_target else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(gk.pos[0]),
        str(gk.pos[1]),
        str(gk.abilities.get("GK_Saving", 50)),
        str(gk.abilities.get("GK_Positioning", 50)),
        str(gk.abilities.get("GK_Reaction", 50)),
        str(config.gk_position_error_factor),
        str(config.gk_reaction_delay_factor),
        str(config.gk_save_base),
        str(save_roll),
        "shot_arrival",
    ])
    rows = _run_rust_rows("shot_arrival", [line])
    fields = rows["shot_arrival"]
    outcome_by_code = {"0": "off_target", "1": "saved", "2": "goal"}
    return {
        "in_box": fields[0] == "1",
        "save_prob": float(fields[1]),
        "outcome": outcome_by_code.get(fields[2], "off_target"),
    }


def shot_arrival_plan_rust(flight, shooter, shooter_team, defending_team, config, save_roll: float):
    """Return the full shot arrival classification/log/event plan from Rust."""
    gk = defending_team.goalkeeper
    logged_sum = sum(s.get("xg", 0) for s in shooter.shot_log)
    line = "\t".join([
        shooter.name,
        gk.name,
        str(flight.origin[0]),
        str(flight.origin[1]),
        str(flight.target[0]),
        str(flight.target[1]),
        "1" if shooter_team.attacking_right else "0",
        "1" if flight.on_target else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(gk.pos[0]),
        str(gk.pos[1]),
        str(gk.abilities.get("GK_Saving", 50)),
        str(gk.abilities.get("GK_Positioning", 50)),
        str(gk.abilities.get("GK_Reaction", 50)),
        str(config.gk_position_error_factor),
        str(config.gk_reaction_delay_factor),
        str(config.gk_save_base),
        str(save_roll),
        str(shooter.xg),
        str(logged_sum),
    ])
    rows = _run_rust_rows("shot_arrival_plan", [line])
    fields = rows["shot_arrival_plan"]
    target_x = None if fields[9] == "-" else float(fields[9])
    target_y = None if fields[10] == "-" else float(fields[10])
    shot_log = {
        "x": float(fields[6]),
        "y": float(fields[7]),
        "xg": float(fields[4]),
        "in_box": fields[14] == "1",
        "outcome": fields[8],
    }
    if target_x is not None:
        shot_log["target_x"] = target_x
    if target_y is not None:
        shot_log["target_y"] = target_y
    return {
        "outcome": {0: "off_target", 1: "saved", 2: "goal"}[int(fields[0])],
        "in_box": fields[1] == "1",
        "save_prob": float(fields[2]),
        "raw_xg": float(fields[3]),
        "rounded_xg": float(fields[4]),
        "psxg_delta": float(fields[5]),
        "shot_log": shot_log,
        "pause_ms": int(float(fields[11])),
        "trace_event": fields[12],
        "pending_event_text": fields[13],
    }


def resolve_clearance_arrival_rust(target_pos, home_team, away_team):
    """Resolve clearance arrival closest player in Rust."""
    def payload(team):
        return ";".join(
            f"{p.index},{p.pos[0]},{p.pos[1]}"
            for p in team.players
        ) or "-"

    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        payload(home_team),
        payload(away_team),
        "0.0",
        "clearance_arrival",
    ])
    rows = _run_rust_rows("clearance_arrival", [line])
    fields = rows["clearance_arrival"]
    return {
        "winner_team": "home" if fields[0] == "0" else "away",
        "player_idx": None if fields[1] == "-" else int(fields[1]),
        "home_distance": float(fields[2]),
        "away_distance": float(fields[3]),
    }


def clearance_arrival_plan_rust(target_pos, flight, home_team, away_team):
    """Return clearance winner and passer-completion decision from Rust."""
    def payload(team):
        return ";".join(
            f"{p.index},{p.pos[0]},{p.pos[1]}"
            for p in team.players
        ) or "-"

    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        payload(home_team),
        payload(away_team),
        "1" if flight.passer_team == "home" else "0",
        "0.0",
        "clearance_plan",
    ])
    rows = _run_rust_rows("clearance_arrival_plan", [line])
    fields = rows["clearance_plan"]
    return {
        "winner_team": "home" if fields[0] == "0" else "away",
        "player_idx": None if fields[1] == "-" else int(fields[1]),
        "passer_completed": fields[2] == "1",
        "home_distance": float(fields[3]),
        "away_distance": float(fields[4]),
    }


def resolve_contested_owner_rust(ball_pos, contested_ticks: int, home_team, away_team, config):
    """Resolve immediate/forced contested-ball owner in Rust."""
    def payload(team):
        return ";".join(
            f"{p.index},{p.pos[0]},{p.pos[1]}"
            for p in team.players
        ) or "-"

    line = "\t".join([
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(config.contest_radius),
        str(contested_ticks),
        payload(home_team),
        payload(away_team),
        "contested_owner",
    ])
    rows = _run_rust_rows("contested_owner", [line])
    fields = rows["contested_owner"]
    return {
        "winner_team": None if fields[0] == "-" else ("home" if fields[0] == "0" else "away"),
        "player_idx": None if fields[1] == "-" else int(fields[1]),
        "distance": float(fields[2]),
        "immediate_win": fields[3] == "1",
        "forced_win": fields[4] == "1",
    }


def select_contested_targets_rust(ball_pos, team, config):
    """Select contested-ball movement targets for one team in Rust."""
    payload = ";".join(
        ",".join([
            str(p.index),
            str(p.pos[0]),
            str(p.pos[1]),
            str(p.tactical_anchor[0]),
            str(p.tactical_anchor[1]),
            "1" if p.is_goalkeeper else "0",
            "1" if getattr(p, "state", None) is not None and p.state.value == "stunned" else "0",
            str(p.speed_value),
            str(p.iq_value),
        ])
        for p in team.players
    ) or "-"
    line = "\t".join([
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        str(config.contested_race_radius),
        payload,
        "contested_targets",
    ])
    rows = _run_rust_rows("contested_targets", [line])
    raw = rows["contested_targets"][0]
    if raw == "-":
        return {}
    outputs = {}
    for item in raw.split(";"):
        idx, x, y, intent_code = item.split(",")
        outputs[int(idx)] = {
            "target": (float(x), float(y)),
            "intent": "contest" if intent_code == "1" else "recover_shape",
        }
    return outputs


def tick_contested_ball_rust(ball):
    """Advance contested loose-ball roll in Rust."""
    line = "\t".join([
        str(ball.position[0]),
        str(ball.position[1]),
        str(ball.loose_velocity[0]),
        str(ball.loose_velocity[1]),
        str(ball.contested_ticks),
        "contested_tick",
    ])
    rows = _run_rust_rows("contested_tick", [line])
    fields = rows["contested_tick"]
    return {
        "position": (float(fields[0]), float(fields[1])),
        "loose_velocity": (float(fields[2]), float(fields[3])),
        "contested_ticks": int(fields[4]),
    }


def contested_tick_plan_rust(ball, home_team, away_team, config):
    """Advance contested ball and resolve immediate/forced owner in one Rust plan."""
    def payload(team):
        return ";".join(
            f"{p.index},{p.pos[0]},{p.pos[1]}"
            for p in team.players
        ) or "-"

    line = "\t".join([
        str(ball.position[0]),
        str(ball.position[1]),
        str(ball.loose_velocity[0]),
        str(ball.loose_velocity[1]),
        str(ball.contested_ticks),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.contest_radius),
        payload(home_team),
        payload(away_team),
        "contested_plan",
    ])
    rows = _run_rust_rows("contested_tick_plan", [line])
    fields = rows["contested_plan"]
    return {
        "position": (float(fields[0]), float(fields[1])),
        "loose_velocity": (float(fields[2]), float(fields[3])),
        "contested_ticks": int(fields[4]),
        "winner_team": None if fields[5] == "-" else ("home" if fields[5] == "0" else "away"),
        "player_idx": None if fields[6] == "-" else int(fields[6]),
        "distance": float(fields[7]),
        "immediate_win": fields[8] == "1",
        "forced_win": fields[9] == "1",
    }


def _f64_list_payload(values):
    if not values:
        return "-"
    return ",".join(str(value) for value in values)


def _usize_list_payload(values):
    if not values:
        return "-"
    return ",".join(str(value) for value in values)


def choose_off_ball_defense_rust(
    defender,
    ball_pos,
    ball_carrier,
    teammates,
    opponents,
    config,
    attacking_right: bool,
    random_samples,
    score_noises,
    roll_by_count,
    fallback_index_by_count,
):
    """Run the full off-ball defensive candidate path in Rust."""
    attackers = [o for o in opponents if not o.is_goalkeeper]
    teammates_no_gk = [t for t in teammates if t.index != defender.index and not t.is_goalkeeper]
    base_ref = (
        defender.base_formation_pos
        if defender.base_formation_pos != (0.0, 0.0)
        else defender.formation_pos
    )
    previous_goal = getattr(defender, "current_goal", None)
    if previous_goal is not None and not previous_goal.goal_type.startswith("defend_"):
        previous_goal = None
    line = "\t".join([
        str(defender.pos[0]),
        str(defender.pos[1]),
        str(defender.tactical_anchor[0]),
        str(defender.tactical_anchor[1]),
        str(base_ref[0]),
        str(base_ref[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        "-" if ball_carrier is None else str(ball_carrier.pos[0]),
        "-" if ball_carrier is None else str(ball_carrier.pos[1]),
        "0" if ball_carrier is None else str(ball_carrier.consecutive_carries),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.press_radius),
        str(config.tackle_range),
        str(config.carrier_speed),
        str(defender.iq_value),
        "-" if not defender.last_def_action else str(defender.last_def_target[0]),
        "-" if not defender.last_def_action else str(defender.last_def_target[1]),
        "-" if previous_goal is None else str(previous_goal.target_pos[0]),
        "-" if previous_goal is None else str(previous_goal.target_pos[1]),
        _positions_payload([(p.pos[0], p.pos[1]) for p in attackers]),
        _defense_teammates_payload(teammates_no_gk),
        ";".join(f"{angle},{radius}" for angle, radius in random_samples) or "-",
        _f64_list_payload(score_noises),
        _f64_list_payload(roll_by_count),
        _usize_list_payload(fallback_index_by_count),
        "defchoice",
    ])
    rows = _run_rust_rows("off_ball_defense_choice", [line])
    fields = rows["defchoice"]
    if fields[0] == "-":
        return None
    previous_goal_score = None if fields[10] == "-" else float(fields[10])
    return {
        "action_type": fields[0],
        "target": (float(fields[1]), float(fields[2])),
        "score": float(fields[3]),
        "candidate_count": int(fields[4]),
        "used_roll": fields[5] == "1",
        "used_random_choice": fields[6] == "1",
        "pressure_responsibility": float(fields[7]),
        "shot_danger": float(fields[8]),
        "carrier_stale_threat": float(fields[9]),
        "previous_goal_score": previous_goal_score,
        "components": {
            "base_score": float(fields[11]),
            "press_value": float(fields[12]),
            "carrier_threat": float(fields[13]),
            "shot_lane_closure": float(fields[14]),
            "best_mark_value": float(fields[15]),
        },
    }


def generate_off_ball_defense_raw_candidates_rust(
    defender,
    ball_pos,
    attacking_right: bool,
    config,
    local_attackers,
    dangerous_receivers,
    ball_carrier,
    carrier_stale_threat: float,
    field_press_context: float,
    shot_danger: float,
    shot_lane_threat: float,
    random_samples,
):
    """Generate off-ball defense sampled points using Rust."""
    line = "\t".join([
        str(defender.pos[0]),
        str(defender.pos[1]),
        str(defender.tactical_anchor[0]),
        str(defender.tactical_anchor[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "-" if ball_carrier is None else str(ball_carrier.pos[0]),
        "-" if ball_carrier is None else str(ball_carrier.pos[1]),
        str(config.carrier_speed),
        str(carrier_stale_threat),
        str(field_press_context),
        str(shot_danger),
        str(shot_lane_threat),
        _positions_payload([(p.pos[0], p.pos[1]) for p in local_attackers]),
        _positions_payload([(p.pos[0], p.pos[1]) for p in dangerous_receivers]),
        ";".join(f"{angle},{radius}" for angle, radius in random_samples) or "-",
        "-" if not defender.last_def_action else str(defender.last_def_target[0]),
        "-" if not defender.last_def_action else str(defender.last_def_target[1]),
        "defraw",
    ])
    rows = _run_rust_rows("off_ball_defense_raw", [line])
    payload = rows["defraw"][0]
    if payload == "-":
        return []
    return [
        tuple(float(value) for value in item.split(","))
        for item in payload.split(";")
    ]


def score_off_ball_defense_candidates_rust(
    defender,
    ball_pos,
    ball_carrier,
    candidates,
    teammates,
    opponents,
    config,
    attacking_right: bool,
):
    """Batch score off-ball defense candidate points using Rust."""
    if not candidates:
        return []
    attackers = [o for o in opponents if not o.is_goalkeeper]
    teammates_no_gk = [t for t in teammates if t.index != defender.index and not t.is_goalkeeper]
    local_attackers = [
        o for o in attackers
        if _distance(o.pos, defender.tactical_anchor) < 24.0 or _distance(o.pos, defender.pos) < 16.0
    ]
    dangerous_receivers = [
        o for o in attackers
        if o is not ball_carrier
        and (
            _distance(o.pos, ball_pos) < 34.0
            or _distance(o.pos, defender.tactical_anchor) < 28.0
            or _distance(o.pos, defender.pos) < 18.0
        )
    ]
    base_ref = (
        defender.base_formation_pos
        if defender.base_formation_pos != (0.0, 0.0)
        else defender.formation_pos
    )
    line = "\t".join([
        str(defender.pos[0]),
        str(defender.pos[1]),
        str(defender.tactical_anchor[0]),
        str(defender.tactical_anchor[1]),
        str(base_ref[0]),
        str(base_ref[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        "-" if ball_carrier is None else str(ball_carrier.pos[0]),
        "-" if ball_carrier is None else str(ball_carrier.pos[1]),
        "0" if ball_carrier is None else str(ball_carrier.consecutive_carries),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.press_radius),
        str(config.tackle_range),
        str(config.carrier_speed),
        "-" if not defender.last_def_action else str(defender.last_def_target[0]),
        "-" if not defender.last_def_action else str(defender.last_def_target[1]),
        _positions_payload(candidates),
        _positions_payload([(p.pos[0], p.pos[1]) for p in attackers]),
        _positions_payload([(p.pos[0], p.pos[1]) for p in local_attackers]),
        _positions_payload([(p.pos[0], p.pos[1]) for p in dangerous_receivers]),
        _defense_teammates_payload(teammates_no_gk),
        "defense",
    ])
    rows = _run_rust_rows("off_ball_defense_score", [line])
    payload = rows["defense"][0]
    if payload == "-":
        return []
    results = []
    for item in payload.split(";"):
        parts = item.split(",")
        results.append((
            float(parts[0]),
            (float(parts[1]), float(parts[2])),
            {
                "base_score": float(parts[3]),
                "press_value": float(parts[4]),
                "pressure_responsibility": float(parts[5]),
                "carrier_threat": float(parts[6]),
                "shot_lane_closure": float(parts[7]),
                "best_mark_value": float(parts[8]),
            },
        ))
    return results


def _distance(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (dx * dx + dy * dy) ** 0.5


def score_off_ball_attack_candidates_rust(
    player,
    ball_pos,
    raw_candidates,
    teammates,
    opponents,
    config,
    attacking_right: bool,
):
    """Batch score off-ball attack raw candidates using Rust."""
    if not raw_candidates:
        return []
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    opponent_speeds = [
        (o.speed_value if hasattr(o, "speed_value") else o.abilities.get("Speed", 50))
        for o in opponents
        if not o.is_goalkeeper
    ]
    opponent_speeds = [
        (max(0, min(99, speed)) / 99.0) * (config.player_max_speed - config.player_min_speed)
        + config.player_min_speed
        for speed in opponent_speeds
    ]
    teammate_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != player.index]
    offside_line = player._get_offside_line(opponents, attacking_right, config)
    goal = getattr(player, "current_goal", None)
    if goal is not None and goal.goal_type not in ("arc_arrival_for_cutback", "attack_far_post"):
        goal = None
    line = "\t".join([
        str(player.index),
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.speed_value),
        str(player.tactical_anchor[0]),
        str(player.tactical_anchor[1]),
        "1" if attacking_right else "0",
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(offside_line),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        _off_ball_candidates_payload(raw_candidates),
        _positions_payload(opponent_positions),
        ",".join(str(speed) for speed in opponent_speeds),
        _positions_payload(teammate_positions),
        _off_ball_teammates_payload(teammates),
        "-" if goal is None else goal.goal_type,
        "-" if goal is None else str(goal.target_pos[0]),
        "-" if goal is None else str(goal.target_pos[1]),
        "0.0" if goal is None else str(goal.value),
        str(config.pass_to_space_ball_speed),
        str(config.receive_reachability_scale),
        str(config.space_creation_radius),
        "offball",
    ])
    rows = _run_rust_rows("off_ball_attack_score", [line])
    payload = rows["offball"][0]
    if payload == "-":
        return []
    results = []
    component_keys = (
        "pv",
        "reach",
        "movement_reach",
        "immediate_reach",
        "pass_feasibility",
        "space_bonus",
        "role_shape_factor",
        "role_overlap_factor",
        "role_overlap",
        "lane_factor",
        "offside_penalty",
        "support_angle_value",
        "inside_support",
        "second_line_support",
        "arrival_goal_fit",
        "arrival_goal_multiplier",
        "arrival_goal_bonus",
        "layoff_window",
        "candidate_progress",
        "candidate_width",
        "support_angle_dist",
        "dist_to_ball",
    )
    for item in payload.split(";"):
        values = [float(part) for part in item.split(",")]
        components = {"kind": "space"}
        components.update({
            key: value
            for key, value in zip(component_keys, values[3:])
        })
        results.append((values[0], (values[1], values[2]), components))
    return results


def choose_off_ball_attack_rust(
    player,
    ball_pos,
    stay_score: float,
    raw_candidates,
    teammates,
    opponents,
    config,
    attacking_right: bool,
    score_noises,
    roll: float,
):
    """Choose an off-ball attacking target using Rust raw candidate scores."""
    if not raw_candidates:
        return None
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    opponent_speeds = [
        (o.speed_value if hasattr(o, "speed_value") else o.abilities.get("Speed", 50))
        for o in opponents
        if not o.is_goalkeeper
    ]
    opponent_speeds = [
        (max(0, min(99, speed)) / 99.0) * (config.player_max_speed - config.player_min_speed)
        + config.player_min_speed
        for speed in opponent_speeds
    ]
    teammate_positions = [(t.pos[0], t.pos[1]) for t in teammates if t.index != player.index]
    offside_line = player._get_offside_line(opponents, attacking_right, config)
    goal = getattr(player, "current_goal", None)
    if goal is not None and goal.goal_type not in ("arc_arrival_for_cutback", "attack_far_post"):
        goal = None
    line = "\t".join([
        str(player.index),
        str(player.pos[0]),
        str(player.pos[1]),
        str(player.speed_value),
        str(player.tactical_anchor[0]),
        str(player.tactical_anchor[1]),
        "1" if attacking_right else "0",
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(offside_line),
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.player_max_speed),
        str(config.player_min_speed),
        _off_ball_candidates_payload(raw_candidates),
        _positions_payload(opponent_positions),
        ",".join(str(speed) for speed in opponent_speeds),
        _positions_payload(teammate_positions),
        _off_ball_teammates_payload(teammates),
        "-" if goal is None else goal.goal_type,
        "-" if goal is None else str(goal.target_pos[0]),
        "-" if goal is None else str(goal.target_pos[1]),
        "0.0" if goal is None else str(goal.value),
        str(config.pass_to_space_ball_speed),
        str(config.receive_reachability_scale),
        str(config.space_creation_radius),
        str(player.iq_value),
        _f64_list_payload(score_noises),
        str(stay_score),
        str(roll),
        "offball_choice",
    ])
    rows = _run_rust_rows("off_ball_attack_choice", [line])
    fields = rows["offball_choice"]
    if fields[0] == "-":
        return None
    component_keys = (
        "pv",
        "reach",
        "movement_reach",
        "immediate_reach",
        "pass_feasibility",
        "space_bonus",
        "role_shape_factor",
        "role_overlap_factor",
        "role_overlap",
        "lane_factor",
        "offside_penalty",
        "support_angle_value",
        "inside_support",
        "second_line_support",
        "arrival_goal_fit",
        "arrival_goal_multiplier",
        "arrival_goal_bonus",
        "layoff_window",
        "candidate_progress",
        "candidate_width",
        "support_angle_dist",
        "dist_to_ball",
    )
    components = {"kind": "stay" if fields[6] == "0" else "space"}
    components.update({
        key: float(value)
        for key, value in zip(component_keys, fields[7:])
    })
    return {
        "target": (float(fields[0]), float(fields[1])),
        "score": float(fields[2]),
        "max_score": float(fields[3]),
        "candidate_count": int(fields[4]),
        "used_roll": fields[5] == "1",
        "components": components,
    }


def generate_off_ball_attack_raw_candidates_rust(
    anchor,
    ball_pos,
    attacking_right: bool,
    pitch_length: float,
    pitch_width: float,
    is_defender: bool,
    has_ball_carrier: bool,
    anchor_samples,
    support_samples,
):
    """Generate non-goal off-ball attack raw candidates using Rust."""
    line = "\t".join([
        str(anchor[0]),
        str(anchor[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        "1" if attacking_right else "0",
        str(pitch_length),
        str(pitch_width),
        "1" if is_defender else "0",
        "1" if has_ball_carrier else "0",
        ";".join(f"{angle},{radius}" for angle, radius in anchor_samples) or "-",
        ";".join(f"{angle},{radius}" for angle, radius in support_samples) or "-",
        "raw",
    ])
    rows = _run_rust_rows("off_ball_attack_raw", [line])
    payload = rows["raw"][0]
    if payload == "-":
        return []
    return [
        (parts[0], parts[1], (parts[2], parts[3]))
        for parts in (
            tuple(float(value) for value in item.split(","))
            for item in payload.split(";")
        )
    ]


def evaluate_off_ball_arrival_goals_rust(
    player,
    anchor,
    ball_pos,
    attacking_right: bool,
    config,
):
    """Evaluate arc-arrival and far-post off-ball goals in Rust."""
    base_pos = getattr(player, "base_formation_pos", anchor)
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(anchor[0]),
        str(anchor[1]),
        str(ball_pos[0]),
        str(ball_pos[1]),
        str(base_pos[0]),
        str(base_pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.goal_width),
        "0.0",
        "arrival_goals",
    ])
    rows = _run_rust_rows("off_ball_arrival_goals", [line])
    fields = rows["arrival_goals"]
    goals = []
    if fields[0] == "1":
        goals.append({
            "goal_type": "arc_arrival_for_cutback",
            "target_pos": (float(fields[1]), float(fields[2])),
            "value": float(fields[3]),
            "confidence": float(fields[4]),
            "phase": "arrive",
            "completion": "reach_arc_target",
            "abort": "wide_window_closed",
            "handoff": "off_ball_value_model",
            "context": {
                "ball_progress": float(fields[5]),
                "ball_width": float(fields[6]),
                "anchor_progress": float(fields[7]),
                "base_progress": float(fields[8]),
                "anchor_width": float(fields[9]),
                "target_dist": float(fields[10]),
            },
        })
    if fields[11] == "1":
        goals.append({
            "goal_type": "attack_far_post",
            "target_pos": (float(fields[12]), float(fields[13])),
            "value": float(fields[14]),
            "confidence": float(fields[15]),
            "phase": "arrive",
            "completion": "reach_far_post",
            "abort": "wide_delivery_window_closed",
            "handoff": "off_ball_value_model",
            "context": {
                "ball_progress": float(fields[16]),
                "ball_width": float(fields[17]),
                "weak_side": float(fields[18]),
                "player_progress": float(fields[19]),
                "anchor_progress": float(fields[20]),
                "target_dist": float(fields[21]),
            },
        })
    return goals


def build_off_ball_attack_goal_rust(target_pos, value: float, tick: int, components, current_goal=None, iq: int = 75):
    """Build and select generic off-ball attack goal metadata in Rust."""
    if current_goal is not None and current_goal.goal_type not in {
        "support_second_line",
        "drop_between_lines",
        "support_carrier",
        "hold_width",
        "run_behind",
        "attack_box",
        "recycle_support",
    }:
        current_goal = None
    line = "\t".join([
        str(target_pos[0]),
        str(target_pos[1]),
        str(value),
        str(float(components.get("second_line_support", 0.0) or 0.0)),
        str(float(components.get("inside_support", 0.0) or 0.0)),
        str(float(components.get("support_angle_value", 0.0) or 0.0)),
        str(float(components.get("layoff_window", 0.0) or 0.0)),
        str(float(components.get("candidate_progress", 0.0) or 0.0)),
        str(float(components.get("candidate_width", 0.0) or 0.0)),
        "-" if current_goal is None else current_goal.goal_type,
        "0.0" if current_goal is None else str(current_goal.target_pos[0]),
        "0.0" if current_goal is None else str(current_goal.target_pos[1]),
        "0.0" if current_goal is None else str(current_goal.value),
        "0.020",
        str(iq),
        "offball_goal",
    ])
    rows = _run_rust_rows("off_ball_attack_goal_build", [line])
    fields = rows["offball_goal"]
    from .goal import PlayerGoal, goal_context

    candidate_goal = PlayerGoal(
        goal_type=fields[0],
        target_pos=(float(fields[1]), float(fields[2])),
        value=float(fields[3]),
        confidence=float(fields[4]),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="support",
            completion="receive_or_open_lane",
            abort="possession_or_shape_changed",
            handoff="off_ball_space_value",
            box_arrival=float(fields[5]),
            second_line_support=float(fields[6]),
            inside_support=float(fields[7]),
            support_angle_value=float(fields[8]),
            layoff_window=float(fields[9]),
            candidate_progress=float(fields[10]),
            candidate_width=float(fields[11]),
        ),
    )
    selected_is_candidate = (
        current_goal is None
        or fields[20] in {"no_current_goal", "candidate_clears_switch_cost"}
    )
    selected_goal = PlayerGoal(
        goal_type=fields[12],
        target_pos=(float(fields[13]), float(fields[14])),
        value=float(fields[15]),
        confidence=max(0.0, min(1.0, float(fields[15]))),
        created_tick=tick if selected_is_candidate else current_goal.created_tick,
        last_updated_tick=tick,
        context=dict(candidate_goal.context) if selected_is_candidate else dict(current_goal.context),
    )
    return {
        "candidate_goal": candidate_goal,
        "selected_goal": selected_goal,
        "selected_is_candidate": selected_is_candidate,
        "trace": {
            "goal": selected_goal.to_dict(),
            "switched": fields[16] == "1",
            "switch_cost": float(fields[17]),
            "value_advantage": float(fields[18]),
            "switch_noise": 0.0,
            "noisy_value_advantage": float(fields[19]),
            "reason": fields[20],
        },
    }


def build_defensive_goal_rust(
    action_type: str,
    target_pos,
    value: float,
    tick: int,
    pressure: float,
    threat: float,
    current_goal=None,
    iq: int = 75,
):
    """Build and select defensive goal metadata in Rust."""
    if current_goal is not None and not current_goal.goal_type.startswith("defend_"):
        current_goal = None
    pressure_interrupt = max(0.0, min(1.0, threat * 0.55))
    line = "\t".join([
        action_type,
        str(target_pos[0]),
        str(target_pos[1]),
        str(value),
        str(pressure),
        str(threat),
        "-" if current_goal is None else current_goal.goal_type,
        "0.0" if current_goal is None else str(current_goal.target_pos[0]),
        "0.0" if current_goal is None else str(current_goal.target_pos[1]),
        "0.0" if current_goal is None else str(current_goal.value),
        "0.022",
        str(pressure_interrupt),
        str(iq),
        "0.0",
        "defensive_goal",
    ])
    rows = _run_rust_rows("defensive_goal_build", [line])
    fields = rows["defensive_goal"]
    from .goal import PlayerGoal, goal_context

    candidate_goal = PlayerGoal(
        goal_type=fields[0],
        target_pos=(float(fields[1]), float(fields[2])),
        value=float(fields[3]),
        confidence=float(fields[4]),
        created_tick=tick,
        last_updated_tick=tick,
        context=goal_context(
            phase="defend",
            completion="deny_space_or_recover_shape",
            abort="possession_or_threat_changed",
            handoff="defensive_space_value",
            action=fields[5],
            pressure=float(fields[6]),
            threat=float(fields[7]),
        ),
    )
    reason = fields[16]
    selected_is_candidate = (
        current_goal is None
        or reason in {
            "no_current_goal",
            "candidate_clears_switch_cost",
            "current_defensive_goal_updated",
        }
    )
    selected_goal = PlayerGoal(
        goal_type=fields[8],
        target_pos=(float(fields[9]), float(fields[10])),
        value=float(fields[11]),
        confidence=max(0.0, min(1.0, float(fields[11]))),
        created_tick=(
            current_goal.created_tick
            if reason == "current_defensive_goal_updated"
            else tick if selected_is_candidate else current_goal.created_tick
        ),
        last_updated_tick=tick,
        context=dict(candidate_goal.context) if selected_is_candidate else dict(current_goal.context),
    )
    return {
        "candidate_goal": candidate_goal,
        "selected_goal": selected_goal,
        "selected_is_candidate": selected_is_candidate,
        "trace": {
            "goal": selected_goal.to_dict(),
            "switched": fields[12] == "1",
            "switch_cost": float(fields[13]),
            "value_advantage": float(fields[14]),
            "switch_noise": 0.0,
            "noisy_value_advantage": float(fields[15]),
            "reason": reason,
        },
    }


def evaluate_shot_rust(
    shooter,
    shooter_pos,
    dist_to_goal: float,
    angle_factor: float,
    pressure_factor: float,
    lane_factor: float,
    dist_factor: float,
    current_state_value: float,
    teammates,
    opponents,
    config,
    attacking_right: bool,
):
    """Evaluate shot using the Rust shot kernel with Python ValueResult shape."""
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    line = "\t".join([
        str(shooter.index),
        str(shooter_pos[0]),
        str(shooter_pos[1]),
        str(shooter.abilities.get("Finishing", 50) / 100.0),
        str(shooter.abilities.get("Long_Shot", 50) / 100.0),
        str(shooter.possession_ticks),
        str(shooter.consecutive_carries),
        str(shooter.last_receive_origin[0]),
        str(shooter.last_receive_origin[1]),
        str(dist_to_goal),
        str(angle_factor),
        str(pressure_factor),
        str(lane_factor),
        str(dist_factor),
        str(current_state_value),
        str(config.pitch_length),
        str(config.pitch_width),
        "1" if attacking_right else "0",
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        str(config.shot_ideal_distance),
        str(config.goal_reward_constant),
        _positions_payload(opponent_positions),
        _shot_support_payload(teammates),
        "shot",
    ])
    rows = _run_rust_rows("shot_eval", [line])
    fields = rows["shot"]
    components = {
        "xg": float(fields[2]),
        "save_estimate": float(fields[3]),
        "opportunity_cost": float(fields[5]),
        "shot_readiness": float(fields[6]),
        "possession_loss_multiplier": float(fields[7]),
        "support_release_window": float(fields[8]),
    }
    return ValueResult(
        score=float(fields[0]),
        success_prob=float(fields[1]),
        risk_cost=float(fields[4]),
        current_value=current_state_value,
        after_value=float(fields[2]),
        components=components,
    )


def score_shot_option_rust(
    shooter,
    opponents,
    teammates,
    config,
    attacking_right: bool,
    current_state_value: float,
):
    """Compute full shoot option in Rust."""
    line = "\t".join([
        str(shooter.pos[0]),
        str(shooter.pos[1]),
        str(shooter.index),
        str(shooter.abilities.get("Finishing", 50) / 100.0),
        str(shooter.abilities.get("Long_Shot", 50) / 100.0),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(config.goal_width),
        str(config.shot_ideal_distance),
        str(shooter.possession_ticks),
        str(shooter.consecutive_carries),
        str(shooter.last_receive_origin[0]),
        str(shooter.last_receive_origin[1]),
        str(current_state_value),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        str(config.goal_reward_constant),
        _positions_payload([(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]),
        _shot_support_payload(teammates),
    ])
    rows = _run_rust_rows("shot_option", [line])
    fields = rows["shot_option"]
    components = {
        "xg": float(fields[2]),
        "save_estimate": float(fields[3]),
        "opportunity_cost": float(fields[5]),
        "shot_readiness": float(fields[6]),
        "possession_loss_multiplier": float(fields[7]),
        "support_release_window": float(fields[8]),
    }
    return (
        float(fields[0]),
        {
            "target": (float(fields[9]), float(fields[10])),
            "success_prob": float(fields[1]),
            "on_target_prob": float(fields[1]),
            "xg": float(fields[2]),
            "after_value": float(fields[2]),
            "risk_cost": float(fields[4]),
            "components": components,
        },
    )


def evaluate_carry_rust(
    carrier,
    target,
    target_pv: float,
    current_pv: float,
    current_state_value: float,
    path_feasibility: float,
    teammates,
    opponents,
    config,
    attacking_right: bool,
):
    """Evaluate carry using the Rust carry kernel with Python ValueResult shape."""
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    line = "\t".join([
        str(carrier.index),
        str(carrier.pos[0]),
        str(carrier.pos[1]),
        str(target[0]),
        str(target[1]),
        str(carrier.abilities.get("Finishing", 50) / 100.0),
        str(carrier.abilities.get("Long_Shot", 50) / 100.0),
        str(carrier.consecutive_carries),
        str(carrier.possession_ticks),
        str(target_pv),
        str(current_pv),
        str(current_state_value),
        str(path_feasibility),
        str(config.pitch_length),
        str(config.pitch_width),
        "1" if attacking_right else "0",
        str(config.carrier_speed),
        str(config.shot_ideal_distance),
        str(config.shot_on_target_base),
        str(config.gk_save_base),
        _positions_payload(opponent_positions),
        _carry_support_payload(teammates),
        "carry",
    ])
    rows = _run_rust_rows("carry_eval", [line])
    return _carry_value_from_fields(rows["carry"], current_state_value)


def _carry_value_from_fields(fields, current_state_value: float):
    components = {
        "continuity": float(fields[3]),
        "pv_gain": float(fields[4]),
        "future_shot_gain": float(fields[5]),
        "carry_to_shoot_window": float(fields[6]),
        "effective_gain": float(fields[7]),
        "near_goal_multiplier": float(fields[8]),
        "release_pressure": float(fields[9]),
        "space_manipulation": float(fields[10]),
    }
    return ValueResult(
        score=float(fields[0]),
        success_prob=1.0,
        risk_cost=float(fields[2]),
        current_value=current_state_value,
        after_value=float(fields[1]),
        components=components,
    )


def evaluate_carries_rust(
    carrier,
    carry_inputs,
    current_pv: float,
    current_state_value: float,
    teammates,
    opponents,
    config,
    attacking_right: bool,
):
    """Batch evaluate carry targets using one Rust CLI invocation.

    carry_inputs is an iterable of (case_id, target, target_pv, path_feasibility).
    """
    opponent_positions = [(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]
    lines = []
    for case_id, target, target_pv, path_feasibility in carry_inputs:
        lines.append("\t".join([
            str(carrier.index),
            str(carrier.pos[0]),
            str(carrier.pos[1]),
            str(target[0]),
            str(target[1]),
            str(carrier.abilities.get("Finishing", 50) / 100.0),
            str(carrier.abilities.get("Long_Shot", 50) / 100.0),
            str(carrier.consecutive_carries),
            str(carrier.possession_ticks),
            str(target_pv),
            str(current_pv),
            str(current_state_value),
            str(path_feasibility),
            str(config.pitch_length),
            str(config.pitch_width),
            "1" if attacking_right else "0",
            str(config.carrier_speed),
            str(config.shot_ideal_distance),
            str(config.shot_on_target_base),
            str(config.gk_save_base),
            _positions_payload(opponent_positions),
            _carry_support_payload(teammates),
            str(case_id),
        ]))
    rows = _run_rust_rows("carry_eval", lines)
    return {
        case_id: _carry_value_from_fields(rows[str(case_id)], current_state_value)
        for case_id, *_ in carry_inputs
    }


def softmax_select_index_rust(scores, iq: int, roll: float, fallback_index: int = 0):
    """Select a candidate index using the Rust softmax kernel."""
    line = "\t".join([
        ",".join(str(score) for score in scores),
        str(iq),
        str(roll),
        str(fallback_index),
        "softmax",
    ])
    rows = _run_rust_rows("softmax_select", [line])
    fields = rows["softmax"]
    return None if fields[0] == "-" else int(fields[0])


def softmax_select_index_with_temperature_rust(scores, temperature: float, roll: float, fallback_index: int = 0):
    """Select a candidate index using a caller-supplied softmax temperature."""
    line = "\t".join([
        ",".join(str(score) for score in scores),
        str(temperature),
        str(roll),
        str(fallback_index),
        "softmax_temp",
    ])
    rows = _run_rust_rows("softmax_select_temp", [line])
    fields = rows["softmax_temp"]
    return None if fields[0] == "-" else int(fields[0])


def select_on_ball_candidate_rust(
    candidates,
    current_goal_type: str,
    iq: int,
    score_noises,
    roll: float,
    fallback_index: int = 0,
):
    """Run on-ball release confidence + IQ noise + softmax selection in Rust."""
    action_codes = {
        "carry": 0,
        "pass": 1,
        "shoot": 2,
        "hold": 3,
        "clear": 4,
    }
    payload_parts = []
    for candidate in candidates:
        components = getattr(getattr(candidate, "value", None), "components", {}) or {}
        details = getattr(candidate, "details", {}) or {}
        detail_components = details.get("components", {}) if isinstance(details, dict) else {}
        target_kind = components.get("target_kind") or detail_components.get("target_kind") or ""
        success_prob = float(getattr(getattr(candidate, "value", None), "success_prob", 0.0) or 0.0)
        if not success_prob and isinstance(details, dict):
            success_prob = float(details.get("success_prob", 0.0) or 0.0)
        receiver_pressure = float(components.get("receiver_pressure", detail_components.get("receiver_pressure", 0.0)) or 0.0)
        high_threat_space = float(components.get("high_threat_space", detail_components.get("high_threat_space", 0.0)) or 0.0)
        payload_parts.append(",".join([
            str(candidate.score),
            str(action_codes.get(candidate.action_type, 0)),
            "1" if target_kind == "space" else "0",
            str(success_prob),
            str(receiver_pressure),
            str(high_threat_space),
        ]))
    line = "\t".join([
        ";".join(payload_parts) or "-",
        "1" if current_goal_type == "hold_for_opportunity" else "0",
        str(iq),
        _f64_list_payload(score_noises),
        str(roll),
        str(fallback_index),
        "onball_select",
    ])
    rows = _run_rust_rows("on_ball_select", [line])
    fields = rows["onball_select"]
    if fields[0] == "-":
        return None
    adjusted_scores = [] if fields[3] == "-" else [float(value) for value in fields[3].split(",")]
    noisy_scores = [] if fields[4] == "-" else [float(value) for value in fields[4].split(",")]
    return {
        "index": int(fields[0]),
        "used_roll": fields[1] == "1",
        "used_random_choice": fields[2] == "1",
        "adjusted_scores": adjusted_scores,
        "noisy_scores": noisy_scores,
    }


def _on_ball_candidate_full_payload(candidate, config, attacking_right: bool, player_pos):
    action_codes = {
        "carry": 0,
        "pass": 1,
        "shoot": 2,
        "hold": 3,
        "clear": 4,
    }
    components = getattr(getattr(candidate, "value", None), "components", {}) or {}
    details = getattr(candidate, "details", {}) or {}
    detail_components = details.get("components", {}) if isinstance(details, dict) else {}
    target = getattr(candidate, "target", None)
    target_x = "-" if target is None else str(target[0])
    target_y = "-" if target is None else str(target[1])

    def component(name, default=0.0):
        return float(components.get(name, detail_components.get(name, default)) or 0.0)

    target_kind = components.get("target_kind") or detail_components.get("target_kind") or ""
    success_prob = float(getattr(getattr(candidate, "value", None), "success_prob", 0.0) or 0.0)
    if not success_prob and isinstance(details, dict):
        success_prob = float(details.get("success_prob", 0.0) or 0.0)
    receiver_pressure = component("receiver_pressure")
    high_threat_space = component("high_threat_space")
    progress_gain = component("progress_gain")
    if not progress_gain and target is not None:
        forward_dir = 1.0 if attacking_right else -1.0
        progress_gain = (target[0] - player_pos[0]) * forward_dir / max(1.0, config.pitch_length)
    target_progress = component("target_progress")
    if not target_progress and target is not None:
        target_progress = (
            target[0] / max(1.0, config.pitch_length)
            if attacking_right
            else (config.pitch_length - target[0]) / max(1.0, config.pitch_length)
        )
    centrality = component("centrality")
    if not centrality and target is not None:
        centrality = 1.0 - min(
            1.0,
            abs(target[1] - config.pitch_width / 2.0) / max(1.0, config.pitch_width / 2.0),
        )
    return ",".join([
        str(candidate.score),
        str(action_codes.get(candidate.action_type, 0)),
        target_x,
        target_y,
        "1" if target_kind == "space" else "0",
        str(success_prob),
        str(receiver_pressure),
        str(high_threat_space),
        str(progress_gain),
        str(component("xg", details.get("xg", 0.0) if isinstance(details, dict) else 0.0)),
        str(component("nearest_pressure", receiver_pressure)),
        str(component("lateral_change")),
        str(component("carry_to_shoot_window")),
        str(component("wide_second_line_carry_window")),
        str(component("future_shot_gain")),
        str(component("byline_carry_window")),
        str(component("shot_readiness")),
        str(component("open_medium_window")),
        str(component("clean_second_line_shot")),
        str(component("space_manipulation")),
        str(component("pressure_draw")),
        str(target_progress),
        str(centrality),
        str(component("final_third_combination")),
        str(component("lane_risk", details.get("lane_risk", 0.0) if isinstance(details, dict) else 0.0)),
        str(component("second_line_arrival_value")),
        str(component("second_line_cutback_value")),
        str(component("layoff_support_value")),
        str(component("short_combination_value")),
        str(component("layoff_retention_value")),
        str(component("receiver_goal_fit")),
        str(component("opportunity_wait")),
        str(component("opportunity_wait_value")),
        str(component("no_clear_release")),
        str(component("path_feasibility", success_prob)),
    ])


def _on_ball_teammates_payload(teammates):
    return ";".join(
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
    ) or "-"


def choose_on_ball_full_decision_rust(
    player,
    candidates,
    teammates,
    opponents,
    config,
    attacking_right: bool,
    tick: int,
):
    """Run the post-candidate on-ball decision pipeline in one Rust call."""
    import random
    from .decision import iq_decision_noise

    if not candidates:
        return None

    current_goal = getattr(player, "current_goal", None)
    current_context = getattr(current_goal, "context", {}) or {}
    noise_scale = iq_decision_noise(player.iq_value) * config.iq_noise_scale
    score_noises = [random.gauss(0.0, noise_scale) for _ in candidates]

    rng_after_score_noise = random.getstate()
    selection_rng = random.Random()
    selection_rng.setstate(rng_after_score_noise)
    selection_roll = selection_rng.random()
    fallback_rng = random.Random()
    fallback_rng.setstate(rng_after_score_noise)
    fallback_index = fallback_rng.randrange(len(candidates)) if candidates else 0

    goal_noise_scale = max(0.0, float(getattr(config, "goal_noise_scale", 0.0)))
    goal_noise_count = len(candidates) + 8
    goal_candidate_noises = []
    if goal_noise_scale > 0.0:
        from .decision import iq_decision_noise as _iq_noise

        iq_instability = _iq_noise(player.iq_value)
        scale = goal_noise_scale * (0.25 + iq_instability)
        goal_candidate_noises = [random.gauss(0.0, scale) for _ in range(goal_noise_count)]
        switch_noise_input = random.gauss(0.0, scale)
    else:
        goal_candidate_noises = [0.0 for _ in range(goal_noise_count)]
        switch_noise_input = 0.0

    generic_rng = random.Random()
    generic_rng.setstate(rng_after_score_noise)
    generic_roll = generic_rng.random()
    generic_fallback_rng = random.Random()
    generic_fallback_rng.setstate(rng_after_score_noise)
    generic_fallback_index = generic_fallback_rng.randrange(len(candidates)) if candidates else 0

    payload = ";".join(
        _on_ball_candidate_full_payload(candidate, config, attacking_right, player.pos)
        for candidate in candidates
    ) or "-"
    line = "\t".join([
        str(player.index),
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(player.iq_value),
        str(player.consecutive_carries),
        str(tick),
        "1" if getattr(config, "goal_continuity_enabled", False) else "0",
        str(getattr(config, "goal_cut_inside_bias", 0.0)),
        str(goal_noise_scale),
        "-" if current_goal is None else str(current_goal.goal_type),
        "0.0" if current_goal is None else str(current_goal.target_pos[0]),
        "0.0" if current_goal is None else str(current_goal.target_pos[1]),
        "0.0" if current_goal is None else str(current_goal.value),
        "0.0" if current_goal is None else str(current_goal.confidence),
        "0" if current_goal is None else str(current_goal.created_tick),
        "-" if current_goal is None else str(current_context.get("phase", "-")),
        payload,
        _on_ball_teammates_payload(teammates),
        _positions_payload([(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]),
        _f64_list_payload(score_noises),
        str(selection_roll),
        str(fallback_index),
        _f64_list_payload(goal_candidate_noises),
        str(switch_noise_input),
        str(generic_roll),
        str(generic_fallback_index),
        "onball_full",
    ])
    rows = _run_rust_rows("on_ball_full_decision", [line])
    fields = rows["onball_full"]
    if fields[0] == "-":
        return None
    final_scores = [] if fields[2] == "-" else [float(value) for value in fields[2].split(",")]
    adjusted_scores = [] if fields[3] == "-" else [float(value) for value in fields[3].split(",")]
    opportunity_indices = [] if fields[4] == "-" else [int(value) for value in fields[4].split(",")]
    goal_payload = None
    if fields[5] == "1":
        goal_payload = {
            "goal_type": fields[6],
            "target_pos": (float(fields[7]), float(fields[8])),
            "value": float(fields[9]),
            "confidence": float(fields[10]),
            "phase": fields[11],
            "created_tick": int(fields[12]),
            "switched": fields[13] == "1",
            "switch_cost": float(fields[14]),
            "value_advantage": float(fields[15]),
            "switch_noise": float(fields[16]),
            "noisy_value_advantage": float(fields[17]),
            "reason": fields[18],
            "candidate_noise": float(fields[19]),
            "candidate_noisy_value": float(fields[20]),
            "selected_action_code": int(fields[21]),
        }
    return {
        "index": int(fields[0]),
        "action_code": int(fields[1]),
        "final_scores": final_scores,
        "adjusted_scores": adjusted_scores,
        "opportunity_target_indices": opportunity_indices,
        "goal": goal_payload,
        "used_roll": fields[22] == "1",
        "used_random_choice": fields[23] == "1",
        "generic_used_roll": fields[24] == "1",
        "generic_used_random_choice": fields[25] == "1",
        "goal_noise_count": int(fields[26]),
        "switch_noise_used": fields[27] == "1",
    }


def apply_generic_on_ball_goal_rust(player, candidates, current_goal, config):
    """Apply generic on-ball action goal continuity in Rust."""
    action_codes = {
        "carry": 0,
        "pass": 1,
        "shoot": 2,
        "hold": 3,
        "clear": 4,
    }
    payload = []
    for candidate in candidates:
        components = getattr(getattr(candidate, "value", None), "components", {}) or {}
        details = getattr(candidate, "details", {}) or {}
        detail_components = details.get("components", {}) if isinstance(details, dict) else {}
        target = getattr(candidate, "target", None)
        target_x = "-" if target is None else str(target[0])
        target_y = "-" if target is None else str(target[1])
        pressure = components.get("nearest_pressure", components.get("receiver_pressure", 0.0)) or 0.0
        target_kind = components.get("target_kind") or detail_components.get("target_kind") or ""
        payload.append(",".join([
            str(candidate.score),
            str(action_codes.get(candidate.action_type, 0)),
            target_x,
            target_y,
            str(float(components.get("progress_gain", 0.0) or 0.0)),
            str(float(components.get("xg", 0.0) or 0.0)),
            str(float(pressure)),
            str(float(components.get("receiver_pressure", 0.0) or 0.0)),
            "1" if target_kind == "space" else "0",
            str(float(components.get("lateral_change", 0.0) or 0.0)),
        ]))

    goal = current_goal
    if goal is not None and goal.goal_type not in {
        "create_shot",
        "progress_carry",
        "protect_ball",
        "recycle",
        "switch_play",
        "through_ball",
        "clear_danger",
    }:
        goal = None
    goal_type = "-" if goal is None else goal.goal_type
    goal_x = "0.0" if goal is None else str(goal.target_pos[0])
    goal_y = "0.0" if goal is None else str(goal.target_pos[1])
    goal_value = "0.0" if goal is None else str(goal.value)
    goal_action = "" if goal is None else str((goal.context or {}).get("action", ""))
    line = "\t".join([
        ";".join(payload) or "-",
        goal_type,
        goal_x,
        goal_y,
        goal_value,
        str(action_codes.get(goal_action, 0)),
        str(player.iq_value),
        str(getattr(config, "goal_cut_inside_bias", 0.0)),
        "0.0",
        "onball_goal",
    ])
    rows = _run_rust_rows("on_ball_generic_goal", [line])
    fields = rows["onball_goal"]
    if fields[0] == "-":
        return None
    return {
        "selected_goal_type": fields[0],
        "selected_action_code": int(fields[1]),
        "selected_target": (float(fields[2]), float(fields[3])),
        "selected_value": float(fields[4]),
        "candidate_goal_type": fields[5],
        "candidate_action_code": int(fields[6]),
        "candidate_target": (float(fields[7]), float(fields[8])),
        "candidate_value": float(fields[9]),
        "switched": fields[10] == "1",
        "switch_cost": float(fields[11]),
        "value_advantage": float(fields[12]),
        "reason": fields[13],
        "biased_scores": [float(value) for value in fields[14].split(",")] if fields[14] != "-" else [],
    }


def apply_specialized_on_ball_bias_rust(player, candidates, selected_goal, selected_phase: str, config):
    """Apply specialized selected-goal score bias in Rust."""
    action_codes = {
        "carry": 0,
        "pass": 1,
        "shoot": 2,
        "hold": 3,
        "clear": 4,
    }
    payload = []
    for candidate in candidates:
        components = getattr(getattr(candidate, "value", None), "components", {}) or {}
        target = getattr(candidate, "target", None)
        payload.append(",".join([
            str(candidate.score),
            str(action_codes.get(candidate.action_type, 0)),
            str(target[0]) if target is not None else "-",
            str(target[1]) if target is not None else "-",
            str(float(components.get("carry_to_shoot_window", 0.0) or 0.0)),
            str(float(components.get("wide_second_line_carry_window", 0.0) or 0.0)),
            str(float(components.get("future_shot_gain", 0.0) or 0.0)),
            str(float(components.get("byline_carry_window", 0.0) or 0.0)),
            str(float(components.get("xg", 0.0) or 0.0)),
            str(float(components.get("shot_readiness", 0.0) or 0.0)),
            str(float(components.get("open_medium_window", 0.0) or 0.0)),
            str(float(components.get("clean_second_line_shot", 0.0) or 0.0)),
            str(float(components.get("space_manipulation", 0.0) or 0.0)),
            str(float(components.get("pressure_draw", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        ";".join(payload) or "-",
        selected_goal.goal_type,
        selected_phase,
        str(selected_goal.target_pos[0]),
        str(selected_goal.target_pos[1]),
        str(selected_goal.value),
        str(max(0.0, float(getattr(config, "goal_cut_inside_bias", 0.0)))),
        str(player.consecutive_carries),
        "special_bias",
    ])
    rows = _run_rust_rows("on_ball_specialized_bias", [line])
    fields = rows["special_bias"]
    return {
        "biased_scores": [float(value) for value in fields[0].split(",")] if fields[0] != "-" else [],
        "opportunity_target_indices": [] if fields[1] == "-" else [int(value) for value in fields[1].split(",")],
    }


def select_goal_candidate_rust(goal_candidates, context):
    """Select best goal candidate in Rust while consuming Python RNG identically."""
    import random
    from .decision import iq_decision_noise

    base = max(0.0, float(context.goal_noise_scale))
    noises = []
    if base <= 0.0:
        noises = [0.0 for _ in goal_candidates]
    else:
        iq_instability = iq_decision_noise(context.iq)
        pressure = max(0.0, min(1.0, float(context.pressure_interrupt)))
        scale = base * (0.25 + iq_instability) * (1.0 + 0.35 * pressure)
        noises = [float(random.gauss(0.0, scale)) for _ in goal_candidates]
    line = "\t".join([
        ",".join(str(goal.value) for goal in goal_candidates) or "-",
        ",".join(str(noise) for noise in noises) or "-",
        str(context.base),
        str(context.context_stability),
        str(context.role_discipline),
        str(context.pressure_interrupt),
        str(context.iq),
        str(context.goal_noise_scale),
        "goal_candidate",
    ])
    rows = _run_rust_rows("select_goal_candidate", [line])
    fields = rows["goal_candidate"]
    if fields[0] == "-":
        return None
    return {
        "index": int(fields[0]),
        "candidate_noise": float(fields[1]),
        "noisy_value": float(fields[2]),
    }


def evaluate_cut_inside_goal_rust(
    player,
    attacking_right: bool,
    config,
    best_carry_components,
    best_shot_components,
    best_carry_target,
    goal_age_ticks: int,
):
    """Evaluate cut-inside-to-shoot goal candidate in Rust."""
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        "-" if best_carry_target is None else str(best_carry_target[0]),
        "-" if best_carry_target is None else str(best_carry_target[1]),
        str(float(best_carry_components.get("future_shot_gain", 0.0) or 0.0)),
        str(float(best_carry_components.get("carry_to_shoot_window", 0.0) or 0.0)),
        str(float(best_carry_components.get("wide_second_line_carry_window", 0.0) or 0.0)),
        str(float(best_shot_components.get("xg", 0.0) or 0.0)),
        str(float(best_shot_components.get("shot_readiness", 0.0) or 0.0)),
        str(player.consecutive_carries),
        str(goal_age_ticks),
        "cut_inside",
    ])
    rows = _run_rust_rows("cut_inside_goal", [line])
    fields = rows["cut_inside"]
    if fields[0] != "1":
        return None
    phase_by_code = {0: "drive", 1: "release", 2: "finish"}
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": phase_by_code.get(int(fields[5]), "drive"),
        "progress": float(fields[6]),
        "width": float(fields[7]),
        "finish_window": float(fields[8]),
        "drive_staleness": float(fields[9]),
    }


def evaluate_drive_byline_goal_rust(player, carry_target, attacking_right: bool, config, carry_score: float, components, delivery_support: float):
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(carry_target[0]),
        str(carry_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(carry_score),
        str(float(components.get("progress_gain", 0.0) or 0.0)),
        str(float(components.get("byline_carry_window", 0.0) or 0.0)),
        str(float(components.get("path_feasibility", components.get("success_prob", 0.0)) or 0.0)),
        str(float(components.get("space_manipulation", 0.0) or 0.0)),
        str(delivery_support),
        "drive_byline",
    ])
    rows = _run_rust_rows("drive_byline_goal", [line])
    fields = rows["drive_byline"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "drive",
        "origin_progress": float(fields[6]),
        "origin_width": float(fields[7]),
        "target_progress": float(fields[8]),
        "target_width": float(fields[9]),
    }


def select_byline_carry_rust(player, teammates, carry_candidates, attacking_right: bool, config):
    """Select byline carry candidate and delivery support in Rust."""
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
    ) or "-"
    carry_payload = []
    carry_indices = []
    for idx, (score, action_type, details) in enumerate(carry_candidates):
        if action_type != "carry":
            continue
        target = details.get("target") if details else None
        if target is None:
            continue
        components = details.get("components", {}) if details else {}
        carry_indices.append(idx)
        carry_payload.append(",".join([
            str(score),
            str(target[0]),
            str(target[1]),
            str(float(components.get("byline_carry_window", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        str(player.index),
        "0.0",
        "1" if attacking_right else "0",
        str(player.pos[0]),
        str(player.pos[1]),
        teammate_payload,
        ";".join(carry_payload) or "-",
        str(config.pitch_length),
        str(config.pitch_width),
    ])
    rows = _run_rust_rows("byline_carry_select", [line])
    fields = rows["byline_carry"]
    if fields[1] == "-":
        return {
            "delivery_support": float(fields[0]),
            "candidate_index": None,
            "value": 0.0,
            "score": 0.0,
            "target": player.pos,
        }
    local_idx = int(fields[1])
    return {
        "delivery_support": float(fields[0]),
        "candidate_index": carry_indices[local_idx],
        "value": float(fields[2]),
        "score": float(fields[3]),
        "target": (float(fields[4]), float(fields[5])),
    }


def evaluate_byline_delivery_goal_rust(player, delivery_target, attacking_right: bool, config, pass_score: float, components):
    target_progress = float(
        components.get(
            "target_progress",
            delivery_target[0] / max(1.0, config.pitch_length)
            if attacking_right
            else (config.pitch_length - delivery_target[0]) / max(1.0, config.pitch_length),
        )
        or 0.0
    )
    centrality = float(
        components.get(
            "centrality",
            1.0 - min(1.0, abs(delivery_target[1] - config.pitch_width / 2.0) / max(1.0, config.pitch_width / 2.0)),
        )
        or 0.0
    )
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(delivery_target[0]),
        str(delivery_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(pass_score),
        str(target_progress),
        str(centrality),
        str(float(components.get("high_threat_space", 0.0) or 0.0)),
        str(float(components.get("final_third_combination", 0.0) or 0.0)),
        str(float(components.get("success_prob", 0.0) or 0.0)),
        str(float(components.get("receiver_pressure", 0.0) or 0.0)),
        str(float(components.get("lane_risk", 0.0) or 0.0)),
        "byline_delivery",
    ])
    rows = _run_rust_rows("byline_delivery_goal", [line])
    fields = rows["byline_delivery"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "release",
        "origin_progress": float(fields[6]),
        "origin_width": float(fields[7]),
        "target_progress": float(fields[8]),
        "centrality": float(fields[9]),
        "high_threat_space": float(components.get("high_threat_space", 0.0) or 0.0),
        "final_third_combination": float(components.get("final_third_combination", 0.0) or 0.0),
        "success_prob": float(components.get("success_prob", 0.0) or 0.0),
        "receiver_pressure": float(components.get("receiver_pressure", 0.0) or 0.0),
        "lane_risk": float(components.get("lane_risk", 0.0) or 0.0),
    }


def evaluate_through_ball_goal_rust(player, pass_target, attacking_right: bool, config, pass_score: float, components):
    target_kind = str(components.get("target_kind", ""))
    target_progress = float(
        components.get(
            "target_progress",
            pass_target[0] / max(1.0, config.pitch_length)
            if attacking_right
            else (config.pitch_length - pass_target[0]) / max(1.0, config.pitch_length),
        )
        or 0.0
    )
    centrality = float(
        components.get(
            "centrality",
            1.0 - min(1.0, abs(pass_target[1] - config.pitch_width / 2.0) / max(1.0, config.pitch_width / 2.0)),
        )
        or 0.0
    )
    forward_dir = 1.0 if attacking_right else -1.0
    progress_gain = float(
        components.get(
            "progress_gain",
            (pass_target[0] - player.pos[0]) * forward_dir / max(1.0, config.pitch_length),
        )
        or 0.0
    )
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(pass_target[0]),
        str(pass_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(pass_score),
        "1" if target_kind == "space" else "0",
        str(target_progress),
        str(centrality),
        str(progress_gain),
        str(float(components.get("high_threat_space", 0.0) or 0.0)),
        str(float(components.get("success_prob", 0.0) or 0.0)),
        str(float(components.get("receiver_pressure", 0.0) or 0.0)),
        str(float(components.get("lane_risk", 0.0) or 0.0)),
    ])
    rows = _run_rust_rows("through_ball_goal", [line])
    fields = rows["through_ball"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "release",
        "origin_progress": float(fields[5]),
        "target_progress": target_progress,
        "centrality": centrality,
        "progress_gain": progress_gain,
        "high_threat_space": float(components.get("high_threat_space", 0.0) or 0.0),
        "success_prob": float(components.get("success_prob", 0.0) or 0.0),
        "receiver_pressure": float(components.get("receiver_pressure", 0.0) or 0.0),
        "lane_risk": float(components.get("lane_risk", 0.0) or 0.0),
    }


def evaluate_wide_hold_overlap_goal_rust(player, overlap_target, attacking_right: bool, config, overlap_value: float, immediate_best_score: float):
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(overlap_target[0]),
        str(overlap_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(overlap_value),
        str(immediate_best_score),
        "0.0",
        "wide_overlap",
    ])
    rows = _run_rust_rows("wide_overlap_goal", [line])
    fields = rows["wide_overlap"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "wait",
        "progress": float(fields[5]),
        "width": float(fields[6]),
        "target_progress": float(fields[7]),
        "target_width": float(fields[8]),
        "forward_gap": float(fields[9]),
        "same_lane": float(fields[10]),
        "overlap_value": overlap_value,
        "immediate_best_score": immediate_best_score,
    }


def select_overlap_candidate_rust(player, pass_candidates, attacking_right: bool, config):
    """Select best overlap support target in Rust."""
    payload = []
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        target = details.get("target") if details else None
        if not target:
            continue
        components = details.get("components", {}) if details else {}
        payload.append(",".join([
            str(score),
            str(target[0]),
            str(target[1]),
            str(float(components.get("receiver_pressure", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        ";".join(payload) or "-",
        "overlap_select",
    ])
    rows = _run_rust_rows("overlap_select", [line])
    fields = rows["overlap_select"]
    if fields[0] == "-":
        return None
    return {
        "index": int(fields[0]),
        "value": float(fields[1]),
        "target": (float(fields[2]), float(fields[3])),
    }


def select_layoff_candidate_rust(player, pass_candidates, opponents, attacking_right: bool, config):
    """Select best layoff target and attracted pressure in Rust."""
    payload = []
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        target = details.get("target") if details else None
        if not target:
            continue
        components = details.get("components", {}) if details else {}
        payload.append(",".join([
            str(score),
            str(target[0]),
            str(target[1]),
            str(float(components.get("receiver_pressure", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        ";".join(payload) or "-",
        _positions_payload([(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]),
        "layoff_select",
    ])
    rows = _run_rust_rows("layoff_select", [line])
    fields = rows["layoff_select"]
    if fields[0] == "-":
        return None
    return {
        "index": int(fields[0]),
        "value": float(fields[1]),
        "target": (float(fields[2]), float(fields[3])),
        "attracted_pressure": float(fields[4]),
    }


def select_arriving_support_rust(player, pass_candidates, opponents):
    """Select best arriving-support target/value in Rust."""
    payload = []
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        target = details.get("target") if details else None
        if not target:
            continue
        components = details.get("components", {}) if details else {}
        payload.append(",".join([
            str(score),
            str(target[0]),
            str(target[1]),
            str(float(components.get("receiver_goal_fit", 0.0) or 0.0)),
            str(float(components.get("second_line_arrival_value", 0.0) or 0.0)),
            str(float(components.get("second_line_cutback_value", 0.0) or 0.0)),
            str(float(components.get("layoff_support_value", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        ";".join(payload) or "-",
        _positions_payload([(o.pos[0], o.pos[1]) for o in opponents if not o.is_goalkeeper]),
        "arriving_support",
    ])
    rows = _run_rust_rows("arriving_support_select", [line])
    fields = rows["arriving_support"]
    if fields[0] == "-":
        return None
    return {
        "index": int(fields[0]),
        "fit": float(fields[1]),
        "target": (float(fields[2]), float(fields[3])),
        "support_value": float(fields[4]),
        "receiver_goal_fit": float(fields[5]),
        "attracted_pressure": float(fields[6]),
    }


def select_hold_support_rust(player, pass_candidates, carry_candidates, candidates, attacking_right: bool, config, current_opportunity_goal: bool):
    """Select hold-for-opportunity support inputs in Rust."""
    pass_payload = []
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        target = details.get("target") if details else None
        if not target:
            continue
        components = details.get("components", {}) if details else {}
        pass_payload.append(",".join([
            str(score),
            str(target[0]),
            str(target[1]),
            str(float(components.get("layoff_support_value", 0.0) or 0.0)),
            str(float(components.get("short_combination_value", 0.0) or 0.0)),
            str(float(components.get("second_line_cutback_value", 0.0) or 0.0)),
            str(float(components.get("layoff_retention_value", 0.0) or 0.0)),
            str(float(components.get("receiver_goal_fit", 0.0) or 0.0)),
        ]))
    carry_payload = []
    for _score, action_type, details in carry_candidates:
        if action_type != "carry":
            continue
        components = details.get("components", {}) if details else {}
        carry_payload.append(",".join([
            str(float(components.get("carry_to_shoot_window", 0.0) or 0.0)),
            str(float(components.get("wide_second_line_carry_window", 0.0) or 0.0)),
            str(float(components.get("future_shot_gain", 0.0) or 0.0)),
        ]))
    hold_payload = []
    for candidate in candidates:
        if getattr(candidate, "action_type", "") != "hold":
            continue
        components = getattr(getattr(candidate, "value", None), "components", {}) or {}
        hold_payload.append(",".join([
            str(float(components.get("opportunity_wait", 0.0) or 0.0)),
            str(float(components.get("opportunity_wait_value", 0.0) or 0.0)),
            str(float(components.get("no_clear_release", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        ";".join(pass_payload) or "-",
        ";".join(carry_payload) or "-",
        ";".join(hold_payload) or "-",
        "1" if current_opportunity_goal else "0",
        "hold_support",
    ])
    rows = _run_rust_rows("hold_support_select", [line])
    fields = rows["hold_support"]
    return {
        "has_support": fields[0] == "1",
        "target": (float(fields[1]), float(fields[2])),
        "fit": float(fields[3]),
        "support_value": float(fields[4]),
        "hold_support": float(fields[5]),
        "no_clear_release": float(fields[6]),
        "clear_carry_plan": float(fields[7]),
        "support_plan_quality": float(fields[8]),
        "carry_interrupt": float(fields[9]),
    }


def evaluate_layoff_goal_rust(player, layoff_target, attacking_right: bool, config, attracted_pressure: float, layoff_value: float, immediate_best_score: float):
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(layoff_target[0]),
        str(layoff_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(attracted_pressure),
        str(layoff_value),
        str(immediate_best_score),
        "layoff",
    ])
    rows = _run_rust_rows("layoff_goal", [line])
    fields = rows["layoff"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "release",
        "progress": float(fields[5]),
        "target_progress": float(fields[6]),
        "target_centrality": float(fields[7]),
        "pass_distance": float(fields[8]),
        "backward_depth": float(fields[9]),
        "attracted_pressure": attracted_pressure,
        "layoff_value": layoff_value,
        "immediate_best_score": immediate_best_score,
    }


def evaluate_release_support_goal_rust(player, support_target, attacking_right: bool, config, support_value: float, receiver_goal_fit: float, shot_components, consecutive_carries: int, attracted_pressure: float):
    shot_readiness = max(
        float(shot_components.get("shot_readiness", 0.0) or 0.0),
        float(shot_components.get("open_medium_window", 0.0) or 0.0),
        float(shot_components.get("clean_second_line_shot", 0.0) or 0.0),
    )
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(support_target[0]),
        str(support_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(support_value),
        str(receiver_goal_fit),
        str(float(shot_components.get("xg", 0.0) or 0.0)),
        str(shot_readiness),
        str(consecutive_carries),
        str(attracted_pressure),
        "release_support",
    ])
    rows = _run_rust_rows("release_support_goal", [line])
    fields = rows["release_support"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "release",
        "progress": float(fields[5]),
        "target_progress": float(fields[6]),
        "target_centrality": float(fields[7]),
        "pass_distance": float(fields[8]),
        "layer_gap": float(fields[9]),
        "release_maturity": float(fields[10]),
        "support_value": support_value,
        "receiver_goal_fit": receiver_goal_fit,
        "current_shot": float(shot_components.get("xg", 0.0) or 0.0),
        "shot_readiness": shot_readiness,
        "consecutive_carries": consecutive_carries,
        "attracted_pressure": attracted_pressure,
    }


def evaluate_hold_opportunity_goal_rust(player, support_target, attacking_right: bool, config, support_value: float, hold_value: float, shot_components, immediate_best_score: float, goal_age_ticks: int):
    shot_readiness = max(
        float(shot_components.get("shot_readiness", 0.0) or 0.0),
        float(shot_components.get("open_medium_window", 0.0) or 0.0),
        float(shot_components.get("clean_second_line_shot", 0.0) or 0.0),
    )
    line = "\t".join([
        str(player.pos[0]),
        str(player.pos[1]),
        str(support_target[0]),
        str(support_target[1]),
        "1" if attacking_right else "0",
        str(config.pitch_length),
        str(config.pitch_width),
        str(support_value),
        str(hold_value),
        str(float(shot_components.get("xg", 0.0) or 0.0)),
        str(shot_readiness),
        str(immediate_best_score),
        str(goal_age_ticks),
        "hold_opportunity",
    ])
    rows = _run_rust_rows("hold_opportunity_goal", [line])
    fields = rows["hold_opportunity"]
    if fields[0] != "1":
        return None
    return {
        "target_pos": (float(fields[1]), float(fields[2])),
        "value": float(fields[3]),
        "confidence": float(fields[4]),
        "phase": "scan",
        "progress": float(fields[5]),
        "target_progress": float(fields[6]),
        "target_centrality": float(fields[7]),
        "pass_distance": float(fields[8]),
        "lateral_gap": float(fields[9]),
        "opportunity_window": float(fields[10]),
        "current_shot": float(shot_components.get("xg", 0.0) or 0.0),
        "shot_readiness": shot_readiness,
        "support_value": support_value,
        "hold_value": hold_value,
        "immediate_best_score": immediate_best_score,
        "goal_age_ticks": goal_age_ticks,
    }


def apply_support_opportunity_cost_rust(carry_candidates, pass_candidates):
    """Apply carry opportunity cost from live support passes in Rust."""
    pass_payload = []
    for score, action_type, details in pass_candidates:
        if action_type != "pass":
            continue
        components = details.get("components", {}) if details else {}
        pass_payload.append(",".join([
            str(score),
            str(float(components.get("receiver_goal_fit", 0.0) or 0.0)),
            str(float(components.get("second_line_arrival_value", 0.0) or 0.0)),
            str(float(components.get("second_line_cutback_value", 0.0) or 0.0)),
            str(float(components.get("layoff_support_value", 0.0) or 0.0)),
        ]))
    carry_payload = []
    carry_indices = []
    for idx, (score, action_type, details) in enumerate(carry_candidates):
        if action_type != "carry":
            continue
        components = details.get("components", {}) if details else {}
        carry_indices.append(idx)
        carry_payload.append(",".join([
            str(score),
            str(float(components.get("future_shot_gain", 0.0) or 0.0)),
            str(float(components.get("carry_to_shoot_window", 0.0) or 0.0)),
            str(float(components.get("effective_gain", 0.0) or 0.0)),
        ]))
    line = "\t".join([
        ";".join(pass_payload) or "-",
        ";".join(carry_payload) or "-",
        "0.0",
        "support_cost",
    ])
    rows = _run_rust_rows("support_opportunity_cost", [line])
    fields = rows["support_cost"]
    support_pressure = float(fields[0])
    scores = [] if fields[1] == "" else [float(value) for value in fields[1].split(",")]
    costs = [] if fields[2] == "" else [float(value) for value in fields[2].split(",")]
    adjusted = list(carry_candidates)
    for local_idx, original_idx in enumerate(carry_indices):
        score, action_type, details = adjusted[original_idx]
        new_score = scores[local_idx]
        cost = costs[local_idx]
        if details is not None and support_pressure > 0.0:
            details = dict(details)
            components = dict(details.get("components", {}) or {})
            components["support_opportunity_pressure"] = support_pressure
            components["support_opportunity_cost"] = cost
            details["components"] = components
        adjusted[original_idx] = (new_score, action_type, details)
    return adjusted
