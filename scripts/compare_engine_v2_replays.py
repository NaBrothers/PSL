#!/usr/bin/env python3
"""Compare current Rust engine_v2 runs against a clean Python baseline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psl_core.engine_v2.config import EngineConfig, TraceConfig
from psl_core.engine_v2.rust_adapter import run_match_v2_rust
from server.database import Database
from server.services.bag import BagService
from server.services.game_config import GameConfigService
from server.services.squad import SquadService

DEFAULT_BASELINE_REPO = Path("/private/tmp/psl-dev-python-baseline")


def build_cards(db: Database, qq: int) -> tuple[str, list[dict[str, Any]]]:
    squad_svc = SquadService(db)
    bag_svc = BagService(db)
    squad = squad_svc.get_squad(qq)
    if any(card is None for card in squad.cards):
        raise RuntimeError(f"Squad for {qq} is incomplete")
    cards: list[dict[str, Any]] = []
    for card_info in squad.cards:
        detail = bag_svc.get_card_detail(card_info.id, qq)
        cards.append({
            "name": card_info.name,
            "player_id": card_info.player_id,
            "position": card_info.position,
            "color": "gold" if card_info.star >= 7 else "silver" if card_info.star >= 4 else "bronze",
            "overall": card_info.real_overall,
            "abilities": {key: value["value"] for key, value in detail["abilities"].items()},
        })
    return squad.formation, cards


def engine_config_payload(config: EngineConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in config.__dict__.items():
        if key == "trace":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, tuple):
            payload[key] = list(value)
        elif isinstance(value, list):
            payload[key] = value
    payload["trace"] = {
        "detail": config.trace.detail,
        "top_k": config.trace.top_k,
        "include_off_ball": config.trace.include_off_ball,
        "include_defense": config.trace.include_defense,
        "sample_rate": config.trace.sample_rate,
    }
    return payload


def run_python_baseline(
    baseline_repo: Path,
    home_cards: list[dict[str, Any]],
    away_cards: list[dict[str, Any]],
    home_formation: str,
    away_formation: str,
    config: EngineConfig,
    seed: int,
) -> dict[str, Any]:
    if not (baseline_repo / "psl_core" / "engine_v2" / "match.py").exists():
        raise RuntimeError(f"invalid Python baseline repo: {baseline_repo}")
    if (baseline_repo / "psl_core" / "engine_v2" / "rust_adapter.py").exists():
        raise RuntimeError(f"baseline repo is polluted by Rust adapter changes: {baseline_repo}")

    script = r"""
import json
import math
import os
import random
import sys

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.goalkeeper import compute_gk_save_probability
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.physics import distance
import psl_core.engine_v2.value_model as value_model

payload = json.load(sys.stdin)
random.seed(payload["seed"])
if os.environ.get("PSL_PY_RNG_TRACE"):
    _rng_counter = {"draws": 0}
    _trace_context = {"match": None, "tick": 0}
    _orig_random = random.random
    _orig_uniform = random.uniform
    _orig_gauss = random.gauss

    def _counted_random():
        _rng_counter["draws"] += 1
        return _orig_random()

    def _counted_uniform(a, b):
        _rng_counter["draws"] += 1
        return _orig_uniform(a, b)

    def _counted_gauss(mu, sigma):
        if random.getstate()[2] is None:
            _rng_counter["draws"] += 2
        return _orig_gauss(mu, sigma)

    random.random = _counted_random
    random.uniform = _counted_uniform
    random.gauss = _counted_gauss

    _orig_tick = MatchV2._tick

    def _traced_tick(self):
        _trace_context["match"] = self
        _trace_context["tick"] = self.tick
        self.trace.log_event(
            self.tick,
            "py_rng",
            label="tick_start",
            draws=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
        )
        result = _orig_tick(self)
        self.trace.log_event(
            self.tick,
            "py_rng",
            label="tick_end",
            draws=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
        )
        return result

    MatchV2._tick = _traced_tick

    _pass_snapshot_tick = int(os.environ.get("PSL_PY_PASS_SNAPSHOT_TICK", "-1"))
    _pass_snapshot_receiver = int(os.environ.get("PSL_PY_PASS_SNAPSHOT_RECEIVER", "-1"))
    _pass_snapshot_passer = os.environ.get("PSL_PY_PASS_SNAPSHOT_PASSER", "")
    _pass_snapshot_x = os.environ.get("PSL_PY_PASS_SNAPSHOT_X")
    _pass_snapshot_y = os.environ.get("PSL_PY_PASS_SNAPSHOT_Y")
    _pass_snapshot_target = (
        (float(_pass_snapshot_x), float(_pass_snapshot_y))
        if _pass_snapshot_x is not None and _pass_snapshot_y is not None
        else None
    )
    _pass_snapshot_radius = float(os.environ.get("PSL_PY_PASS_SNAPSHOT_RADIUS", "0.05"))
    _orig_expected_pass_value_result = value_model.expected_pass_value_result

    def _player_snapshot(player):
        goal = getattr(player, "current_goal", None)
        base = getattr(player, "base_formation_pos", getattr(player, "tactical_anchor", player.pos))
        return {
            "idx": player.index,
            "name": player.name,
            "position": player.position,
            "pos": list(player.pos),
            "target_pos": list(getattr(player, "target_pos", player.pos)),
            "tactical_anchor": list(getattr(player, "tactical_anchor", player.pos)),
            "base_pos": list(base),
            "is_goalkeeper": bool(getattr(player, "is_goalkeeper", False)),
            "finishing": player.abilities.get("Finishing", 0),
            "long_shot": player.abilities.get("Long_Shot", 0),
            "speed": player.abilities.get("Speed", 0),
            "goal_type": getattr(goal, "goal_type", None),
            "goal_target": list(getattr(goal, "target_pos", player.pos)) if goal is not None else None,
            "goal_value": getattr(goal, "value", 0.0) if goal is not None else 0.0,
        }

    def _target_matches(target):
        if _pass_snapshot_target is None:
            return True
        return distance(target, _pass_snapshot_target) <= _pass_snapshot_radius

    def _traced_expected_pass_value_result(*args, **kwargs):
        result = _orig_expected_pass_value_result(*args, **kwargs)
        if _pass_snapshot_tick < 0:
            return result
        passer = args[0] if len(args) > 0 else kwargs.get("passer")
        receiver = args[1] if len(args) > 1 else kwargs.get("receiver")
        origin = args[2] if len(args) > 2 else kwargs.get("origin")
        target = args[3] if len(args) > 3 else kwargs.get("target")
        teammates = args[4] if len(args) > 4 else kwargs.get("teammates", [])
        opponents = args[5] if len(args) > 5 else kwargs.get("opponents", [])
        current_value = args[9] if len(args) > 9 else kwargs.get("current_value")
        base_accuracy = args[10] if len(args) > 10 else kwargs.get("base_accuracy")
        receiver_arrival = kwargs.get("receiver_arrival", args[11] if len(args) > 11 else 1.0)
        continuity = kwargs.get("continuity", args[12] if len(args) > 12 else 0.03)
        match = _trace_context.get("match")
        tick = _trace_context.get("tick", 0)
        if (
            match is not None
            and tick == _pass_snapshot_tick
            and passer is not None
            and receiver is not None
            and target is not None
            and (_pass_snapshot_receiver < 0 or receiver.index == _pass_snapshot_receiver)
            and (not _pass_snapshot_passer or passer.name == _pass_snapshot_passer)
            and _target_matches(target)
        ):
            match.trace.log_event(
                tick,
                "py_pass_value_snapshot",
                passer=passer.name,
                passer_idx=passer.index,
                receiver=receiver.name,
                receiver_idx=receiver.index,
                origin=list(origin),
                target=list(target),
                current_value=current_value,
                base_accuracy=base_accuracy,
                receiver_arrival_input=receiver_arrival,
                continuity_input=continuity,
                result=result.to_dict(),
                teammates=[_player_snapshot(player) for player in teammates],
                opponents=[_player_snapshot(player) for player in opponents],
            )
        return result

    value_model.expected_pass_value_result = _traced_expected_pass_value_result
    value_model.evaluate_pass_target = _traced_expected_pass_value_result

    _orig_choose_off_ball_attack = Player.choose_off_ball_attack
    _orig_choose_on_ball = Player.choose_on_ball
    _orig_choose_off_ball_defend = Player.choose_off_ball_defend

    def _trace_player_rng(trace, tick, label, player):
        if trace is None:
            return
        trace.log_event(
            tick,
            "py_rng_player",
            label=label,
            player=player.name,
            player_idx=player.index,
            draws=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
        )

    def _traced_choose_off_ball_attack(self, *args, **kwargs):
        tick = kwargs.get("tick", 0)
        trace = kwargs.get("trace")
        _trace_player_rng(trace, tick, "before_attack", self)
        result = _orig_choose_off_ball_attack(self, *args, **kwargs)
        _trace_player_rng(trace, tick, "after_attack", self)
        return result

    def _traced_choose_on_ball(self, *args, **kwargs):
        tick = kwargs.get("tick", 0)
        trace = kwargs.get("trace")
        _trace_player_rng(trace, tick, "before_holder_choice", self)
        result = _orig_choose_on_ball(self, *args, **kwargs)
        _trace_player_rng(trace, tick, "after_holder_choice", self)
        return result

    def _traced_choose_off_ball_defend(self, *args, **kwargs):
        tick = kwargs.get("tick", 0)
        trace = kwargs.get("trace")
        _trace_player_rng(trace, tick, "before_defense", self)
        result = _orig_choose_off_ball_defend(self, *args, **kwargs)
        _trace_player_rng(trace, tick, "after_defense", self)
        return result

    Player.choose_off_ball_attack = _traced_choose_off_ball_attack
    Player.choose_on_ball = _traced_choose_on_ball
    Player.choose_off_ball_defend = _traced_choose_off_ball_defend

    _orig_execute_pass_phase3 = MatchV2._execute_pass_phase3

    def _traced_execute_pass_phase3(self, passer, details, passer_team, opp_team, interception_interaction):
        ideal_target = details.get("target", passer.pos)
        is_long = details.get("is_long", False)
        passing = passer.abilities.get("Long_Passing" if is_long else "Short_Passing", 50)
        dist_to_target = distance(passer.pos, ideal_target)
        pressure = sum(
            1 for o in opp_team.players
            if not o.is_goalkeeper and distance(o.pos, passer.pos) < 8.0
        )
        lane_risk = details.get("lane_risk", 0.0)
        ability_factor = max(0.0, min(1.0, passing / 100.0))
        error_radius = (
            (1.0 - ability_factor) * (1.2 + dist_to_target / 12.0)
            + pressure * 0.35
            + lane_risk * 2.5
        )
        preview = random.Random()
        preview.setstate(random.getstate())
        preview_values = []
        if error_radius > 0.05:
            angle_unit = preview.random()
            mag_unit = preview.random()
            preview_values.extend([angle_unit, mag_unit])
            angle = angle_unit * math.tau
            mag = mag_unit * error_radius
            target = self.pitch.clamp(
                ideal_target[0] + math.cos(angle) * mag,
                ideal_target[1] + math.sin(angle) * mag,
            )
        else:
            target = ideal_target
        error_roll = preview.random()
        preview_values.append(error_roll)
        error_chance = (100 - passing) / self.config.pass_error_divisor
        interception_roll = None
        interception_chance = 0.0
        if error_roll >= error_chance and interception_interaction is not None:
            interception_roll = preview.random()
            preview_values.append(interception_roll)
            defender = interception_interaction.defender
            defence = defender.abilities.get("Defence", 50)
            base_chance = defence / 200.0
            proximity_factor = max(0.3, 1.0 - interception_interaction.distance / self.config.interception_reach)
            pass_quality = passing / 150.0
            interception_chance = max(0.05, min(0.60, base_chance * proximity_factor * (1.0 - pass_quality * 0.4)))
        self.trace.log_event(
            self.tick,
            "py_pass_phase_debug",
            team=passer_team.side,
            player=passer.name,
            holder_idx=passer.index,
            receiver_idx=details.get("intended_receiver", details.get("target_player_idx", -1)),
            passer_pos=list(passer.pos),
            ideal_target=list(ideal_target),
            preview_target=list(target),
            passing=passing,
            is_long=is_long,
            lane_risk=lane_risk,
            error_radius=error_radius,
            error_chance=error_chance,
            error_roll=error_roll,
            randoms=preview_values,
            draws_before=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
            interception_present=interception_interaction is not None,
            interceptor_idx=(
                interception_interaction.defender.index
                if interception_interaction is not None
                else None
            ),
            interceptor=(
                interception_interaction.defender.name
                if interception_interaction is not None
                else ""
            ),
            interception_distance=(
                interception_interaction.distance
                if interception_interaction is not None
                else 0.0
            ),
            interception_roll=interception_roll,
            interception_chance=interception_chance,
            intercepted=(
                interception_roll is not None
                and interception_roll < interception_chance
            ),
        )
        result = _orig_execute_pass_phase3(self, passer, details, passer_team, opp_team, interception_interaction)
        self.trace.log_event(
            self.tick,
            "py_pass_phase_after_debug",
            player=passer.name,
            draws_after=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
        )
        return result

    MatchV2._execute_pass_phase3 = _traced_execute_pass_phase3

    _orig_resolve_shot_arrival = MatchV2._resolve_shot_arrival

    def _traced_resolve_shot_arrival(self, flight):
        shooter_team = self.home if flight.passer_team == "home" else self.away
        defending_team = self.away if flight.passer_team == "home" else self.home
        gk = defending_team.goalkeeper
        save_prob = (
            compute_gk_save_probability(gk, flight.target, flight.origin, self.config)
            if flight.on_target
            else 0.0
        )
        preview_rng = random.Random()
        preview_rng.setstate(random.getstate())
        next_random = preview_rng.random() if flight.on_target else None
        self.trace.log_event(
            self.tick,
            "py_shot_arrival_debug",
            on_target=flight.on_target,
            save_prob=save_prob,
            next_random=next_random,
            draws_before=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
            shot_origin=list(flight.origin),
            shot_target=list(flight.target),
            gk_pos=list(gk.pos),
        )
        result = _orig_resolve_shot_arrival(self, flight)
        self.trace.log_event(
            self.tick,
            "py_shot_arrival_after_debug",
            draws_after=_rng_counter["draws"],
            gauss_cached=random.getstate()[2] is not None,
        )
        return result

    MatchV2._resolve_shot_arrival = _traced_resolve_shot_arrival
cfg = EngineConfig()
for key, value in payload["config"].items():
    if key == "trace":
        continue
    if hasattr(cfg, key):
        setattr(cfg, key, value)
for key, value in payload["config"].get("trace", {}).items():
    if hasattr(cfg.trace, key):
        setattr(cfg.trace, key, value)
match = MatchV2(
    payload["home_cards"],
    payload["away_cards"],
    payload["home_formation"],
    payload["away_formation"],
    config=cfg,
)
result = match.run()
print(json.dumps({
    "engine": "clean_python_baseline",
    "score": [result.home_score, result.away_score],
    "formations": [payload["home_formation"], payload["away_formation"]],
    "goals": result.goals,
    "trace": match.get_trace(),
    "replay": match.get_replay_data(),
    "stats": {
        "home": result.home_stats,
        "away": result.away_stats,
    },
    "player_stats": {
        "home": result.home_player_stats,
        "away": result.away_player_stats,
    },
    "ratings": {
        "home": result.home_ratings,
        "away": result.away_ratings,
    },
}, ensure_ascii=False))
"""
    payload = {
        "home_cards": home_cards,
        "away_cards": away_cards,
        "home_formation": home_formation,
        "away_formation": away_formation,
        "config": engine_config_payload(config),
        "seed": seed,
    }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(baseline_repo)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=baseline_repo,
        env=env,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def build_compare_config(
    db: Database,
    total_ticks: int,
    half_ticks: int,
    trace_detail: str,
    trace_top_k: int,
) -> EngineConfig:
    config_service = GameConfigService(db)
    config = EngineConfig()
    for key, value in config_service.get_all().items():
        if not key.startswith("engine_v2."):
            continue
        attr_name = key.replace("engine_v2.", "")
        if not hasattr(config, attr_name):
            continue
        current = getattr(config, attr_name)
        try:
            if isinstance(current, bool):
                parsed = str(value).strip().lower() in ("1", "true", "yes", "on")
            else:
                parsed = type(current)(value)
            setattr(config, attr_name, parsed)
        except Exception:
            pass
    config.total_ticks = total_ticks
    config.half_ticks = half_ticks
    config.frame_interval = 1
    config.trace = TraceConfig(detail=trace_detail, top_k=trace_top_k, include_off_ball=True, include_defense=True)
    return config


def run_rust_engine(
    home_formation: str,
    home_cards: list[dict[str, Any]],
    away_formation: str,
    away_cards: list[dict[str, Any]],
    config: EngineConfig,
    seed: int,
) -> dict[str, Any]:
    response = run_match_v2_rust(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config,
        seed=seed,
    )
    return {
        "engine": "rust",
        "score": [response["home_score"], response["away_score"]],
        "formations": [home_formation, away_formation],
        "goals": response.get("goals", []),
        "trace": response.get("trace", {}),
        "replay": response.get("replay", []),
        "stats": {
            "home": response.get("home_stats", {}),
            "away": response.get("away_stats", {}),
        },
        "player_stats": {
            "home": response.get("home_player_stats", []),
            "away": response.get("away_player_stats", []),
        },
        "ratings": {
            "home": response.get("home_ratings", []),
            "away": response.get("away_ratings", []),
        },
    }


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    trace = run["trace"]
    replay = [frame for frame in run["replay"] if frame.get("type") == "frame"]
    actions = [entry for entry in trace.get("entries", []) if entry.get("type") == "action"]
    events = [entry for entry in trace.get("entries", []) if entry.get("type") == "event"]
    holders = Counter((frame.get("ball_team"), frame.get("ball_holder")) for frame in replay)
    ball_positions = [frame.get("ball") for frame in replay if frame.get("ball")]
    sideline_frames = 0
    goal_line_frames = 0
    for ball_y, ball_x in ball_positions:
        if ball_y <= 2.0 or ball_y >= 66.0:
            sideline_frames += 1
        if ball_x <= 2.0 or ball_x >= 103.0:
            goal_line_frames += 1
    total_frames = max(1, len(replay))
    return {
        "engine": run["engine"],
        "score": run["score"],
        "formations": run["formations"],
        "frames": len(replay),
        "actions": dict(Counter(entry.get("action") for entry in actions)),
        "events": dict(Counter(entry.get("event") for entry in events)),
        "decisions": len(trace.get("decisions", [])),
        "top_holders": [
            {"team": team, "player": player, "frames": count}
            for (team, player), count in holders.most_common(8)
        ],
        "max_holder_share": holders.most_common(1)[0][1] / total_frames if holders else 0.0,
        "sideline_share": sideline_frames / total_frames,
        "goal_line_share": goal_line_frames / total_frames,
        "ball_flight_frames": sum(1 for frame in replay if frame.get("ball_flight")),
    }


def _point_differs(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if a is None or b is None:
        return a != b
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return a != b
    return any(abs(float(left) - float(right)) > tolerance for left, right in zip(a, b))


def _positions_differs(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return a != b
    for left, right in zip(a, b):
        if _point_differs(left, right, tolerance):
            return True
    return False


def _action_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("tick"),
        entry.get("team"),
        entry.get("player"),
        entry.get("action"),
    )


def _strip_rust_team_stat_extensions(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    # The Rust adapter exposes clearances at team level for its public contract;
    # the clean Python baseline only exposes it in per-player stats.
    normalized.pop("clearances", None)
    return normalized


def _strip_rust_player_stat_extensions(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    # Public Rust adapter fields used by the web/contract tests; the clean
    # Python baseline only exposes the attempted carry count per player.
    normalized.pop("carries_completed", None)
    return normalized


def _normalize_player_stats_for_compare(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for side, players in value.items():
        if isinstance(players, list):
            normalized[side] = [
                _strip_rust_player_stat_extensions(player) for player in players
            ]
        else:
            normalized[side] = players
    return normalized


def _values_equal(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _values_equal(l_item, r_item, tolerance)
            for l_item, r_item in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left.keys()) != set(right.keys()):
            return False
        return all(_values_equal(left[key], right[key], tolerance) for key in left)
    return left == right


def _result_diff(python_run: dict[str, Any], rust_run: dict[str, Any]) -> dict[str, Any] | None:
    keys = ("score", "formations", "goals", "stats", "player_stats", "ratings")
    python_values = {key: python_run.get(key) for key in keys}
    rust_values = {key: rust_run.get(key) for key in keys}
    if isinstance(python_values.get("stats"), dict) and isinstance(rust_values.get("stats"), dict):
        python_values["stats"] = {
            side: _strip_rust_team_stat_extensions(stats)
            for side, stats in python_values["stats"].items()
        }
        rust_values["stats"] = {
            side: _strip_rust_team_stat_extensions(stats)
            for side, stats in rust_values["stats"].items()
        }
    python_values["player_stats"] = _normalize_player_stats_for_compare(
        python_values.get("player_stats")
    )
    rust_values["player_stats"] = _normalize_player_stats_for_compare(
        rust_values.get("player_stats")
    )
    fields = [key for key in keys if not _values_equal(python_values.get(key), rust_values.get(key))]
    if not fields:
        return None
    return {
        "fields": fields,
        "python": {key: python_values.get(key) for key in fields},
        "rust": {key: rust_values.get(key) for key in fields},
    }


def compare_runs(python_run: dict[str, Any], rust_run: dict[str, Any]) -> dict[str, Any]:
    python_frames = [frame for frame in python_run["replay"] if frame.get("type") == "frame"]
    rust_frames = [frame for frame in rust_run["replay"] if frame.get("type") == "frame"]
    python_actions = [entry for entry in python_run["trace"].get("entries", []) if entry.get("type") == "action"]
    rust_actions = [entry for entry in rust_run["trace"].get("entries", []) if entry.get("type") == "action"]

    first_frame_diff: dict[str, Any] | None = None
    for index, (python_frame, rust_frame) in enumerate(zip(python_frames, rust_frames)):
        fields: list[str] = []
        for key in ("t", "half", "ball_holder", "ball_team", "score", "ball_flight"):
            if python_frame.get(key) != rust_frame.get(key):
                fields.append(key)
        if _point_differs(python_frame.get("ball"), rust_frame.get("ball")):
            fields.append("ball")
        if _positions_differs(python_frame.get("home"), rust_frame.get("home")):
            fields.append("home")
        if _positions_differs(python_frame.get("away"), rust_frame.get("away")):
            fields.append("away")
        if fields:
            first_frame_diff = {
                "index": index,
                "t": python_frame.get("t"),
                "fields": fields,
                "python": {key: python_frame.get(key) for key in fields},
                "rust": {key: rust_frame.get(key) for key in fields},
            }
            break
    if first_frame_diff is None and len(python_frames) != len(rust_frames):
        first_frame_diff = {
            "index": min(len(python_frames), len(rust_frames)),
            "fields": ["frame_count"],
            "python": {"frame_count": len(python_frames)},
            "rust": {"frame_count": len(rust_frames)},
        }

    first_action_diff: dict[str, Any] | None = None
    for index, (python_action, rust_action) in enumerate(zip(python_actions, rust_actions)):
        if _action_signature(python_action) != _action_signature(rust_action):
            first_action_diff = {
                "index": index,
                "python": python_action,
                "rust": rust_action,
            }
            break
    if first_action_diff is None and len(python_actions) != len(rust_actions):
        first_action_diff = {
            "index": min(len(python_actions), len(rust_actions)),
            "python": {"action_count": len(python_actions)},
            "rust": {"action_count": len(rust_actions)},
        }

    return {
        "first_frame_diff": first_frame_diff,
        "first_action_diff": first_action_diff,
        "result_diff": _result_diff(python_run, rust_run),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="psl.db")
    parser.add_argument("--home", type=int, required=True)
    parser.add_argument("--away", type=int, required=True)
    parser.add_argument("--ticks", type=int, default=400)
    parser.add_argument("--half-ticks", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument("--trace-detail", default="top_candidates", choices=["off", "chosen", "top_candidates", "full"])
    parser.add_argument("--trace-top-k", type=int, default=5)
    parser.add_argument("--baseline-repo", default=str(DEFAULT_BASELINE_REPO))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    db = Database(args.db)
    half_ticks = args.half_ticks if args.half_ticks > 0 else max(1, args.ticks // 2)
    home_formation, home_cards = build_cards(db, args.home)
    away_formation, away_cards = build_cards(db, args.away)
    config = build_compare_config(
        db,
        total_ticks=args.ticks,
        half_ticks=half_ticks,
        trace_detail=args.trace_detail,
        trace_top_k=args.trace_top_k,
    )
    python_run = run_python_baseline(
        Path(args.baseline_repo),
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config,
        seed=args.seed,
    )
    rust_run = run_rust_engine(
        home_formation,
        home_cards,
        away_formation,
        away_cards,
        config,
        seed=args.seed,
    )
    report = {
        "home": args.home,
        "away": args.away,
        "ticks": args.ticks,
        "seed": args.seed,
        "baseline_repo": str(Path(args.baseline_repo)),
        "python": summarize(python_run),
        "rust": summarize(rust_run),
        "diff": compare_runs(python_run, rust_run),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.out:
        Path(args.out).write_text(json.dumps({
            "report": report,
            "python": python_run,
            "rust": rust_run,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
