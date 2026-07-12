import random

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from tests.engine_v2_baseline_runner import run_python_baseline_match, summarize_engine_v2_run
from tests.test_engine_v2_shape import _cards


def _golden_short_match_summary(
    rust_pass_adapter: bool = False,
    rust_on_ball_adapter: bool = False,
    rust_verified_on_ball_profile: bool = False,
    *,
    seed: int = 20260708,
    total_ticks: int = 12,
    half_ticks: int = 6,
    home_formation: str = "433",
    away_formation: str = "442",
):
    random.seed(seed)
    cfg = EngineConfig(total_ticks=total_ticks, half_ticks=half_ticks, frame_interval=1)
    cfg.rust_full_match_runner_enabled = False
    cfg.goal_noise_scale = 0.0
    cfg.trace.detail = "top_candidates"
    cfg.trace.top_k = 2
    cfg.rust_pass_batch_adapter_enabled = rust_pass_adapter
    cfg.rust_on_ball_evaluator_adapter_enabled = rust_on_ball_adapter
    if rust_verified_on_ball_profile:
        cfg.enable_rust_adapters_for_verified_on_ball()

    match = MatchV2(_cards(), _cards(), home_formation, away_formation, config=cfg)
    result = match.run()
    trace = match.get_trace()
    replay = match.get_replay_data()
    actions = [entry for entry in trace["entries"] if entry["type"] == "action"][:8]

    return {
        "score": [result.home_score, result.away_score],
        "home_stats": {
            key: result.home_stats[key]
            for key in ("shots", "passes", "passes_completed", "possession")
        },
        "away_stats": {
            key: result.away_stats[key]
            for key in ("shots", "passes", "passes_completed", "possession")
        },
        "trace_total_entries": trace["total_entries"],
        "decision_count": len(trace["decisions"]),
        "action_summary": [
            (entry["tick"], entry["team"], entry["player"], entry["action"])
            for entry in actions
        ],
        "first_decision": {
            "tick": trace["decisions"][0]["tick"],
            "team": trace["decisions"][0]["team"],
            "player_idx": trace["decisions"][0]["player_idx"],
            "chosen_action": trace["decisions"][0]["chosen"]["action_type"],
            "chosen_source": trace["decisions"][0]["chosen"]["source"],
            "alternative_actions": [
                item["action_type"] for item in trace["decisions"][0]["alternatives"]
            ],
        },
        "replay_header_type": replay[0]["type"],
        "frame_count": len(replay) - 1,
        "first_frame_type": replay[1]["type"],
        "first_frame_score": replay[1]["score"],
    }


def _disable_rust_adapters(config: EngineConfig) -> None:
    for key in dir(config):
        if key.startswith("rust_") and key.endswith("_adapter_enabled"):
            setattr(config, key, False)
    config.rust_full_match_runner_enabled = False


def _current_python_short_match_run(
    *,
    seed: int,
    total_ticks: int,
    half_ticks: int,
    home_formation: str,
    away_formation: str,
):
    random.seed(seed)
    cfg = EngineConfig(total_ticks=total_ticks, half_ticks=half_ticks, frame_interval=1)
    cfg.goal_noise_scale = 0.0
    cfg.trace.detail = "top_candidates"
    cfg.trace.top_k = 5
    _disable_rust_adapters(cfg)
    match = MatchV2(_cards(), _cards(), home_formation, away_formation, config=cfg)
    result = match.run()
    return {
        "home_score": result.home_score,
        "away_score": result.away_score,
        "home_stats": result.home_stats,
        "away_stats": result.away_stats,
        "replay": match.get_replay_data(),
        "trace": match.get_trace(),
    }


def test_current_python_without_rust_adapters_matches_clean_dev_baseline():
    scenarios = [
        ("433", "442", 20260708, 12, 6),
        ("442", "442", 12345, 20, 10),
        ("4141", "433", 777, 20, 10),
    ]
    for home_formation, away_formation, seed, total_ticks, half_ticks in scenarios:
        cfg = EngineConfig(total_ticks=total_ticks, half_ticks=half_ticks, frame_interval=1)
        cfg.goal_noise_scale = 0.0
        cfg.trace.detail = "top_candidates"
        cfg.trace.top_k = 5
        _disable_rust_adapters(cfg)
        baseline = run_python_baseline_match(
            home_cards=_cards(),
            away_cards=_cards(),
            home_formation=home_formation,
            away_formation=away_formation,
            config=cfg,
            seed=seed,
        )
        current = _current_python_short_match_run(
            seed=seed,
            total_ticks=total_ticks,
            half_ticks=half_ticks,
            home_formation=home_formation,
            away_formation=away_formation,
        )
        assert summarize_engine_v2_run(current) == summarize_engine_v2_run(baseline)


def test_engine_v2_short_match_golden_contract():
    assert _golden_short_match_summary() == {
        "score": [0, 0],
        "home_stats": {
            "shots": 0,
            "passes": 1,
            "passes_completed": 0,
            "possession": 55.6,
        },
        "away_stats": {
            "shots": 0,
            "passes": 1,
            "passes_completed": 1,
            "possession": 44.4,
        },
        "trace_total_entries": 12,
        "decision_count": 11,
        "action_summary": [
            (0, "home", "Player 9", "hold"),
            (1, "home", "Player 9", "hold"),
            (2, "home", "Player 9", "hold"),
            (3, "home", "Player 9", "hold"),
            (4, "home", "Player 9", "hold"),
            (5, "home", "Player 9", "pass"),
            (6, "away", "Player 9", "hold"),
            (7, "away", "Player 9", "hold"),
        ],
        "first_decision": {
            "tick": 0,
            "team": "home",
            "player_idx": 9,
            "chosen_action": "hold",
            "chosen_source": "hold",
            "alternative_actions": ["shoot", "carry"],
        },
        "replay_header_type": "header",
        "frame_count": 14,
        "first_frame_type": "frame",
        "first_frame_score": [0, 0],
    }


def test_engine_v2_short_match_rust_pass_adapter_matches_python_contract():
    assert _golden_short_match_summary(rust_pass_adapter=True) == _golden_short_match_summary()


def test_engine_v2_rust_pass_adapter_matches_python_across_short_scenarios():
    scenarios = [
        {"seed": 20260708, "home_formation": "433", "away_formation": "442"},
        {"seed": 12345, "home_formation": "442", "away_formation": "442"},
        {"seed": 777, "home_formation": "4141", "away_formation": "433"},
    ]
    for scenario in scenarios:
        kwargs = {**scenario, "total_ticks": 8, "half_ticks": 4}
        assert _golden_short_match_summary(rust_pass_adapter=True, **kwargs) == _golden_short_match_summary(**kwargs)


def test_engine_v2_rust_pass_adapter_matches_python_longer_short_match():
    kwargs = {
        "seed": 424242,
        "total_ticks": 20,
        "half_ticks": 10,
        "home_formation": "4141",
        "away_formation": "442",
    }
    assert _golden_short_match_summary(rust_pass_adapter=True, **kwargs) == _golden_short_match_summary(**kwargs)


def test_engine_v2_verified_rust_on_ball_profile_matches_python_short_scenarios():
    scenarios = [
        {"seed": 20260708, "home_formation": "433", "away_formation": "442"},
        {"seed": 12345, "home_formation": "442", "away_formation": "442"},
        {"seed": 777, "home_formation": "4141", "away_formation": "433"},
    ]
    for scenario in scenarios:
        kwargs = {**scenario, "total_ticks": 8, "half_ticks": 4}
        assert _golden_short_match_summary(
            rust_verified_on_ball_profile=True,
            **kwargs,
        ) == _golden_short_match_summary(**kwargs)


def test_engine_v2_verified_rust_profile_matches_python_longer_short_match():
    kwargs = {
        "seed": 515151,
        "total_ticks": 20,
        "half_ticks": 10,
        "home_formation": "4141",
        "away_formation": "442",
    }
    assert _golden_short_match_summary(
        rust_verified_on_ball_profile=True,
        **kwargs,
    ) == _golden_short_match_summary(**kwargs)
