import json
import random

from psl_core.engine_v2.config import EngineConfig, TraceConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.value_model import (
    ActionCandidate,
    ValueResult,
    evaluate_carry_target,
    evaluate_clear,
    evaluate_hold,
    evaluate_pass_target,
    evaluate_shot,
    state_value,
)
from tests.test_engine_v2_shape import _cards


def _short_config():
    return EngineConfig(total_ticks=6, half_ticks=3, frame_interval=1)


def _run_with_trace(detail="off", top_k=5):
    random.seed(12345)
    cfg = _short_config()
    cfg.trace.detail = detail
    cfg.trace.top_k = top_k
    match = MatchV2(_cards(), _cards(), "442", "442", config=cfg)
    result = match.run()
    return result, match.get_trace()


def test_trace_config_should_trace_filters():
    trace = TraceConfig(detail="top_candidates", focus_players=(9,), focus_ticks=((2, 5),), sample_rate=2)

    assert trace.should_trace(2, 9, "on_ball")
    assert not trace.should_trace(3, 9, "on_ball")
    assert not trace.should_trace(2, 8, "on_ball")
    assert not trace.should_trace(6, 9, "on_ball")
    assert not TraceConfig().should_trace(2, 9, "on_ball")


def test_value_result_and_candidate_are_json_serializable():
    value = ValueResult(
        score=0.42,
        success_prob=0.7,
        risk_cost=0.1,
        current_value=0.2,
        after_value=0.5,
        components={"target": (1.0, 2.0)},
    )
    candidate = ActionCandidate(
        phase="on_ball",
        action_type="pass",
        target=(1.0, 2.0),
        value=value,
        details={"target": (1.0, 2.0)},
        source="feet",
    )

    payload = candidate.to_dict()
    json.dumps(payload)
    assert payload["value"]["components"]["delta"] == 0.3
    assert payload["target"] == [1.0, 2.0]


def test_on_ball_evaluators_return_json_serializable_value_results():
    cfg = _short_config()
    match = MatchV2(_cards(), _cards(), "442", "442", config=cfg)
    player = match.home.players[9]
    teammate = match.home.players[10]
    opponents = match.away.players
    teammates = match.home.players
    current_value = state_value(player.pos, player, teammates, opponents, cfg, match.pitch, True)

    pass_value = evaluate_pass_target(
        player, teammate, player.pos, teammate.pos,
        teammates, opponents, cfg, match.pitch, True,
        current_value, 0.7,
    )
    carry_value = evaluate_carry_target(
        player, match.pitch.clamp(player.pos[0] + 3.0, player.pos[1]),
        0.5, 0.4, current_value, 0.8,
        teammates, opponents, cfg, match.pitch, True,
    )
    shot_value = evaluate_shot(
        player, (cfg.pitch_length, cfg.pitch_width / 2.0), cfg, opponents,
        18.0, 0.8, 0.9, 0.95, 1.0,
    )
    hold_value = evaluate_hold(player, 0.4, 1, 0.2, 0.5, 0.1, 0.0)
    clear_value = evaluate_clear(0.2, 2, cfg)

    for value in (pass_value, carry_value, shot_value, hold_value, clear_value):
        assert isinstance(value, ValueResult)
        payload = value.to_dict()
        json.dumps(payload)
        assert "final_score" in payload["components"]


def test_trace_off_records_no_decisions():
    _, trace = _run_with_trace("off")

    assert trace["decisions"] == []


def test_chosen_trace_records_only_chosen_candidate():
    _, trace = _run_with_trace("chosen")

    assert trace["decisions"]
    first = trace["decisions"][0]
    assert first["chosen"]["phase"] == "on_ball"
    assert isinstance(first["pos"], list)
    assert len(first["pos"]) == 2
    assert first["alternatives"] == []
    json.dumps(trace["decisions"])


def test_top_candidates_trace_respects_top_k():
    _, trace = _run_with_trace("top_candidates", top_k=2)

    assert trace["decisions"]
    first = trace["decisions"][0]
    assert len(first["alternatives"]) <= 2
    scores = [item["value"]["score"] for item in first["alternatives"]]
    assert scores == sorted(scores, reverse=True)
    assert "consecutive_carries" in first["chosen"]["value"]["components"]


def test_release_confidence_preserves_hold_when_actions_do_not_clear_baseline():
    cfg = _short_config()
    match = MatchV2(_cards(), _cards(), "442", "442", config=cfg)
    player = match.home.players[9]
    hold = ActionCandidate(
        phase="on_ball",
        action_type="hold",
        target=player.pos,
        value=ValueResult(score=0.050, components={}),
        details={"target": player.pos},
        source="hold",
    )
    weak_shot = ActionCandidate(
        phase="on_ball",
        action_type="shoot",
        target=(cfg.pitch_length, cfg.pitch_width / 2.0),
        value=ValueResult(score=0.052, components={}),
        details={},
        source="shot",
    )

    adjusted = player._apply_release_confidence([hold, weak_shot])
    adjusted_hold = next(item for item in adjusted if item.action_type == "hold")
    adjusted_shot = next(item for item in adjusted if item.action_type == "shoot")

    assert adjusted_hold.score == hold.score
    assert adjusted_shot.score < adjusted_hold.score


def test_release_confidence_keeps_clear_release_action_when_advantage_is_real():
    cfg = _short_config()
    match = MatchV2(_cards(), _cards(), "442", "442", config=cfg)
    player = match.home.players[9]
    hold = ActionCandidate(
        phase="on_ball",
        action_type="hold",
        target=player.pos,
        value=ValueResult(score=0.050, components={}),
        details={"target": player.pos},
        source="hold",
    )
    clear_pass = ActionCandidate(
        phase="on_ball",
        action_type="pass",
        target=match.home.players[10].pos,
        value=ValueResult(score=0.140, components={}),
        details={},
        source="pass",
    )

    adjusted = player._apply_release_confidence([hold, clear_pass])
    adjusted_pass = next(item for item in adjusted if item.action_type == "pass")

    assert adjusted_pass.score > hold.score
    assert adjusted_pass.score > 0.13


def test_hold_goal_requires_safer_release_for_space_pass():
    cfg = _short_config()
    match = MatchV2(_cards(), _cards(), "442", "442", config=cfg)
    player = match.home.players[9]
    hold = ActionCandidate(
        phase="on_ball",
        action_type="hold",
        target=player.pos,
        value=ValueResult(score=0.080, components={}),
        details={"target": player.pos},
        source="hold",
    )
    risky_space = ActionCandidate(
        phase="on_ball",
        action_type="pass_to_space",
        target=(90.0, 34.0),
        value=ValueResult(
            score=0.115,
            success_prob=0.36,
            components={"receiver_pressure": 0.35, "high_threat_space": 0.85},
        ),
        details={"target": (90.0, 34.0)},
        source="pass",
    )

    adjusted = player._apply_release_confidence([hold, risky_space], "hold_for_opportunity")
    adjusted_hold = next(item for item in adjusted if item.action_type == "hold")
    adjusted_space = next(item for item in adjusted if item.action_type == "pass_to_space")

    assert adjusted_space.score < risky_space.score
    assert adjusted_space.score > adjusted_hold.score


def test_trace_detail_does_not_change_short_match_result():
    off_result, _ = _run_with_trace("off")
    traced_result, traced = _run_with_trace("top_candidates", top_k=3)

    assert (traced_result.home_score, traced_result.away_score) == (off_result.home_score, off_result.away_score)
    assert traced_result.home_stats["shots"] == off_result.home_stats["shots"]
    assert traced_result.away_stats["passes"] == off_result.away_stats["passes"]
    assert traced["decisions"]
