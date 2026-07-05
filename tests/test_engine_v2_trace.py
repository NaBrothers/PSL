import json

from psl_core.engine_v2.config import EngineConfig, TraceConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.value_model import ActionCandidate, ValueResult
from tests.test_engine_v2_shape import _cards


def _short_config():
    return EngineConfig(total_ticks=6, half_ticks=3, frame_interval=1)


def _run_with_trace(detail="off", top_k=5):
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


def test_trace_off_records_no_decisions():
    _, trace = _run_with_trace("off")

    assert trace["decisions"] == []


def test_chosen_trace_records_only_chosen_candidate():
    _, trace = _run_with_trace("chosen")

    assert trace["decisions"]
    first = trace["decisions"][0]
    assert first["chosen"]["phase"] == "on_ball"
    assert first["alternatives"] == []
    json.dumps(trace["decisions"])


def test_top_candidates_trace_respects_top_k():
    _, trace = _run_with_trace("top_candidates", top_k=2)

    assert trace["decisions"]
    first = trace["decisions"][0]
    assert len(first["alternatives"]) <= 2
    scores = [item["value"]["score"] for item in first["alternatives"]]
    assert scores == sorted(scores, reverse=True)


def test_trace_detail_does_not_change_short_match_result():
    off_result, _ = _run_with_trace("off")
    traced_result, traced = _run_with_trace("top_candidates", top_k=3)

    assert (traced_result.home_score, traced_result.away_score) == (off_result.home_score, off_result.away_score)
    assert traced_result.home_stats["shots"] == off_result.home_stats["shots"]
    assert traced_result.away_stats["passes"] == off_result.away_stats["passes"]
    assert traced["decisions"]
