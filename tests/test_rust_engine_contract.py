"""Contract and architecture tests for the Rust-only match engine."""

import sys
from pathlib import Path

from psl_core.engine_v2 import EngineConfig, MatchV2, TraceConfig


ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"


def _cards(overall: int = 80) -> list[dict]:
    abilities = {
        "Finishing": overall,
        "Short_Passing": overall,
        "Long_Passing": overall,
        "Dribbling": overall,
        "Tackling": overall,
        "Defence": overall,
        "Speed": overall,
        "IQ": overall,
        "Heading": overall,
        "Long_Shot": overall,
        "GK_Saving": overall,
        "GK_Positioning": overall,
        "GK_Reaction": overall,
    }
    return [
        {
            "name": f"Player {index}",
            "player_id": str(index),
            "color": "$" if index == 0 else "b",
            "overall": overall,
            "abilities": abilities,
        }
        for index in range(11)
    ]


def test_python_package_contains_only_rust_contract_boundary():
    package = ROOT / "psl_core" / "engine_v2"
    source_files = {path.name for path in package.glob("*.py")}
    assert source_files == {
        "__init__.py",
        "config.py",
        "match.py",
        "rust_bridge.py",
    }

    config_fields = vars(EngineConfig())
    assert not any(name.startswith("rust_") for name in config_fields)

    if str(BOT_ROOT) not in sys.path:
        sys.path.insert(0, str(BOT_ROOT))
    from engine.game import Game

    assert not hasattr(Game, "play_possession")
    assert not hasattr(Game, "_start_legacy")
    assert not hasattr(Game, "_run_simulation_legacy")


def test_engine_config_serializes_rust_runtime_contract():
    config = EngineConfig(
        total_ticks=8,
        half_ticks=4,
        trace=TraceConfig(detail="top_candidates", top_k=3),
        runner_forced_action="hold",
    )
    payload = config.to_rust_payload()

    assert payload["total_ticks"] == 8
    assert payload["half_ticks"] == 4
    assert payload["trace_detail"] == "top_candidates"
    assert payload["trace_top_k"] == 3
    assert payload["runner_forced_action"] == "hold"
    assert "trace" not in payload


def test_match_facade_runs_rust_contract_deterministically():
    config = EngineConfig(total_ticks=8, half_ticks=4, frame_interval=1)
    first = MatchV2(_cards(), _cards(), "433", "442", config=config, seed=42)
    second = MatchV2(_cards(), _cards(), "433", "442", config=config, seed=42)

    first_result = first.run()
    second_result = second.run()

    assert first_result.trace_id.startswith("rust-match-v2:")
    assert first_result.home_score == second_result.home_score
    assert first_result.away_score == second_result.away_score
    assert first_result.home_stats == second_result.home_stats
    assert first_result.away_stats == second_result.away_stats
    assert len(first_result.home_player_stats) == 11
    assert len(first_result.away_player_stats) == 11
    replay = first.get_replay_data()
    assert replay[0]["type"] == "header"
    assert replay[0]["home"]["players"][0] == {
        "name": "Player 0",
        "player_id": "0",
        "pos": "GK",
        "color": "$",
        "colored_name": "/~$Player 0/",
    }
    assert first_result.home_player_stats[0]["player_id"] == "0"
    assert first_result.home_player_stats[0]["color"] == "$"
    assert first_result.home_player_stats[0]["colored_name"] == "/~$Player 0/"
    assert first_result.home_ratings[0]["player_id"] == "0"
    assert first_result.home_ratings[0]["color"] == "$"
    assert first_result.home_ratings[0]["colored_name"] == "/~$Player 0/"

    frames = [line for line in replay if line["type"] == "frame"]
    assert frames
    for frame in frames:
        assert len(frame["home_player_goals"]) == 11
        assert len(frame["away_player_goals"]) == 11
        assert all(
            goal is None or isinstance(goal, str)
            for goal in frame["home_player_goals"] + frame["away_player_goals"]
        )

    assert replay == second.get_replay_data()
    assert first.get_trace()["trace_id"] == "rust-match-v2"


def test_match_facade_runs_only_once():
    match = MatchV2(
        _cards(),
        _cards(),
        "442",
        "442",
        config=EngineConfig(total_ticks=2, half_ticks=1, frame_interval=1),
        seed=7,
    )
    first = match.run()
    second = match.run()

    assert first is second


def test_match_result_preserves_goal_assister_identity():
    match = MatchV2(
        _cards(90),
        _cards(90),
        "433",
        "433",
        config=EngineConfig(),
        seed=2,
    )

    result = match.run()

    assert len(result.goals) == 1
    goal = result.goals[0]
    assert goal["scorer"] == "Player 9"
    assert goal["scorer_color"] == "b"
    assert goal["assister"] == "Player 6"
    assert goal["assister_color"] == "b"
