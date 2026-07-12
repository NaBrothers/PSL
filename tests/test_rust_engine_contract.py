"""Contract and architecture tests for the Rust-only match engine."""

import random
import sys
from pathlib import Path

from psl_core.engine_v2 import EngineConfig, MatchV2, TraceConfig
from psl_core.engine_v2.match import MatchResult
from psl_core.presentation import build_match_presentation


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

    required_fields = {
        "seq",
        "tick",
        "match_second",
        "minute",
        "second",
        "half",
        "possession_id",
        "event_type",
        "team_side",
        "player",
        "target_player",
        "assist_player",
        "outcome",
        "xg",
        "score_before",
        "score_after",
        "origin",
        "target",
        "tags",
    }
    identity_fields = {
        "player_id",
        "name",
        "color",
        "colored_name",
        "position",
    }
    assert len(result.events) > len(result.goals)
    assert [event["seq"] for event in result.events] == list(
        range(1, len(result.events) + 1)
    )

    score = [0, 0]
    goal_events = []
    for event in result.events:
        assert required_fields <= event.keys()
        assert event["score_before"] == score
        assert event["minute"] == event["match_second"] // 60
        assert event["second"] == event["match_second"] % 60
        assert event["team_side"] in {"home", "away"}
        assert identity_fields <= event["player"].keys()
        assert isinstance(event["tags"], list)
        assert event["xg"] >= 0
        for position_key in ("origin", "target"):
            position = event[position_key]
            assert position is None or (
                isinstance(position, list) and len(position) == 2
            )

        if event["event_type"] == "shot" and event["outcome"] == "goal":
            goal_events.append(event)
            scoring_index = 0 if event["team_side"] == "home" else 1
            expected_score = score.copy()
            expected_score[scoring_index] += 1
            assert event["score_after"] == expected_score
        else:
            assert event["score_after"] == score
        score = event["score_after"]

    assert score == [result.home_score, result.away_score]
    assert len(goal_events) == result.home_score + result.away_score


def test_match_presentation_is_deterministic_and_rng_isolated():
    events = [
        {
            "seq": 1,
            "tick": 90,
            "match_second": 180,
            "minute": 3,
            "second": 0,
            "half": 1,
            "possession_id": 4,
            "event_type": "pass",
            "team_side": "home",
            "player": {
                "player_id": "8",
                "name": "Playmaker",
                "color": "b",
                "colored_name": "/~bPlaymaker/",
                "position": "CM",
            },
            "target_player": {
                "player_id": "9",
                "name": "Striker",
                "color": "r",
                "colored_name": "/~rStriker/",
                "position": "ST",
            },
            "assist_player": None,
            "outcome": "completed",
            "xg": 0.0,
            "score_before": [0, 0],
            "score_after": [0, 0],
            "origin": [52.0, 34.0],
            "target": [82.0, 34.0],
            "tags": ["progressive", "through_ball", "space"],
        },
        {
            "seq": 2,
            "tick": 92,
            "match_second": 184,
            "minute": 3,
            "second": 4,
            "half": 1,
            "possession_id": 4,
            "event_type": "shot",
            "team_side": "home",
            "player": {
                "player_id": "9",
                "name": "Striker",
                "color": "r",
                "colored_name": "/~rStriker/",
                "position": "ST",
            },
            "target_player": {
                "player_id": "0",
                "name": "Keeper",
                "color": "b",
                "colored_name": "/~bKeeper/",
                "position": "GK",
            },
            "assist_player": {
                "player_id": "8",
                "name": "Playmaker",
                "color": "b",
                "colored_name": "/~bPlaymaker/",
                "position": "CM",
            },
            "outcome": "goal",
            "xg": 0.42,
            "score_before": [0, 0],
            "score_after": [1, 0],
            "origin": [92.0, 34.0],
            "target": [105.0, 34.0],
            "tags": ["in_box", "big_chance", "scored"],
        },
    ]
    result = MatchResult(
        home_score=1,
        away_score=0,
        events=events,
        home_stats={"possession": 55, "shots": 1, "shots_on_target": 1, "xg": 0.42},
        away_stats={"possession": 45},
        presentation_seed=987654321,
    )

    random.seed(20260713)
    rng_state = random.getstate()
    first = build_match_presentation(result, "Home", "Away")
    assert random.getstate() == rng_state
    second = build_match_presentation(result, "Home", "Away")

    assert first == second
    assert first.events
    assert first.broadcasts
    assert "直塞" in "\n".join(
        line for batch in first.broadcasts for line in batch
    )
    assert "Playmaker" in first.report
    assert "Striker" in first.report
