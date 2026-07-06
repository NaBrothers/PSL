from psl_core.engine_v2.goal import (
    evaluate_attack_far_post_goal,
    GoalSwitchContext,
    PlayerGoal,
    evaluate_arc_arrival_for_cutback_goal,
    evaluate_cut_inside_to_shoot_goal,
    evaluate_hold_for_opportunity_goal,
    evaluate_release_pressure_with_layoff_goal,
    evaluate_wide_hold_for_overlap_goal,
    goal_switch_cost,
    select_goal,
)
from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.ball import BallState
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.trace import MatchTrace
from tests.test_engine_v2_shape import _cards


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _goal(goal_type: str, value: float) -> PlayerGoal:
    return PlayerGoal(
        goal_type=goal_type,
        target_pos=(80.0, 34.0),
        value=value,
        confidence=0.8,
        created_tick=12,
        last_updated_tick=14,
        context={"source": "test"},
    )


def _player(index: int, position: str, x: float, y: float, attacking: bool = True) -> Player:
    abilities = {key: 72 for key in ABILITY_KEYS}
    abilities.update({
        "Finishing": 80,
        "Long_Shot": 82,
        "Dribbling": 84,
        "Short_Passing": 78,
        "Long_Passing": 74,
        "Speed": 84,
        "IQ": 82,
    })
    if not attacking:
        abilities.update({"Tackling": 76, "Defence": 78, "Speed": 74})
    player = Player(
        index=index,
        name=f"{position}{index}",
        position=position,
        color="gold",
        overall=78,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    player.tactical_anchor = (x, y)
    return player


def test_player_goal_serializes_trace_state():
    payload = _goal("cut_inside_to_shoot", 0.20).to_dict()

    assert payload["goal_type"] == "cut_inside_to_shoot"
    assert payload["target_pos"] == [80.0, 34.0]
    assert payload["value"] == 0.20
    assert payload["confidence"] == 0.8
    assert payload["created_tick"] == 12
    assert payload["last_updated_tick"] == 14
    assert payload["context"] == {"source": "test"}


def test_transition_to_defense_clears_team_goals():
    config = EngineConfig(total_ticks=4, half_ticks=2)
    match = MatchV2(_cards(), _cards(), "442", "442", config=config)
    match.home.players[8].current_goal = _goal("arc_arrival_for_cutback", 0.30)
    match.away.players[9].current_goal = _goal("hold_for_opportunity", 0.25)
    match.ball.state = BallState.HELD
    match.ball.holder_team = "away"
    match.ball.holder_idx = 9

    match._sync_goals_with_phase()

    assert match.home.players[8].current_goal is None
    assert match.away.players[9].current_goal is not None


def test_goal_persists_when_candidate_does_not_clear_switch_cost():
    current = _goal("cut_inside_to_shoot", 0.20)
    candidate = _goal("recycle", 0.215)
    context = GoalSwitchContext(base=0.04, context_stability=1.0, role_discipline=1.0, pressure_interrupt=0.0, iq=80)

    selection = select_goal(current, candidate, context)

    assert not selection.switched
    assert selection.goal is current
    assert selection.reason == "current_goal_within_switch_cost"
    assert selection.value_advantage > 0.0
    assert selection.switch_cost > selection.value_advantage


def test_goal_switches_immediately_when_candidate_clears_switch_cost():
    current = _goal("wide_hold_for_overlap", 0.20)
    candidate = _goal("shoot", 0.31)
    context = GoalSwitchContext(base=0.035, context_stability=1.0, role_discipline=1.0, pressure_interrupt=0.0, iq=80)

    selection = select_goal(current, candidate, context)

    assert selection.switched
    assert selection.goal is candidate
    assert selection.reason == "candidate_clears_switch_cost"
    assert selection.value_advantage > selection.switch_cost


def test_same_goal_type_updates_lifecycle_without_switch_cost():
    current = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(82.0, 44.0),
        value=0.20,
        context={"phase": "drive"},
    )
    candidate = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(82.0, 44.0),
        value=0.08,
        context={"phase": "release"},
    )

    selection = select_goal(current, candidate, GoalSwitchContext(base=0.50))

    assert not selection.switched
    assert selection.goal is candidate
    assert selection.reason == "current_goal_phase_updated"
    assert selection.goal.context["phase"] == "release"


def test_pressure_interrupt_lowers_goal_switch_cost():
    stable = GoalSwitchContext(base=0.04, pressure_interrupt=0.0, iq=80)
    pressured = GoalSwitchContext(base=0.04, pressure_interrupt=0.8, iq=80)

    assert goal_switch_cost(pressured) < goal_switch_cost(stable)


def test_cut_inside_goal_appears_for_wide_future_shot_window():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.09,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.20,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        tick=42,
    )

    assert goal is not None
    assert goal.goal_type == "cut_inside_to_shoot"
    assert goal.value > 0.0
    assert goal.target_pos[0] > 78.0
    assert abs(goal.target_pos[1] - 34.0) < abs(56.0 - 34.0)
    assert goal.context["future_shot_gain"] == 0.09
    assert goal.context["phase"] == "drive"


def test_cut_inside_goal_absent_when_shot_gain_is_missing():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.01,
            "carry_to_shoot_window": 0.0,
            "wide_second_line_carry_window": 0.0,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        tick=42,
    )

    assert goal is None


def test_cut_inside_goal_marks_finish_phase_when_shot_window_exists():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(90.0, 31.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.05,
            "carry_to_shoot_window": 0.06,
            "wide_second_line_carry_window": 0.02,
        },
        best_shot_components={"xg": 0.15, "shot_readiness": 0.55},
        tick=44,
    )

    assert goal is not None
    assert goal.context["phase"] == "finish"
    assert goal.context["finish_window"] > 0.35


def test_cut_inside_goal_marks_release_phase_after_stalled_wide_drive():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.08,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.04,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        consecutive_carries=4,
        tick=48,
    )

    assert goal is not None
    assert goal.context["phase"] == "release"


def test_cut_inside_goal_marks_release_phase_after_stalled_goal_age():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.08,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.04,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        consecutive_carries=0,
        goal_age_ticks=8,
        created_tick=40,
        tick=48,
    )

    assert goal is not None
    assert goal.created_tick == 40
    assert goal.context["phase"] == "release"
    assert goal.context["goal_age_ticks"] == 8


def test_cut_inside_release_phase_clears_current_goal():
    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(8, "LW", 78.0, 58.0)
    carrier.current_goal = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(82.0, 44.0),
        value=0.25,
        context={"phase": "drive"},
    )
    carrier.consecutive_carries = 4
    teammates = [carrier, _player(9, "ST", 88.0, 34.0), _player(6, "CM", 74.0, 34.0)]
    opponents = [
        _player(2, "CB", 90.0, 30.0, attacking=False),
        _player(3, "CB", 90.0, 39.0, attacking=False),
    ]
    trace = MatchTrace()

    carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=5,
        team_side="home",
        trace=trace,
    )

    assert trace.decisions[-1]["goal"]["goal"]["context"]["phase"] == "release"
    assert carrier.current_goal is None


def test_on_ball_goal_trace_records_cut_inside_without_forcing_action():
    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.02
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 78.0, 56.0)
    teammates = [
        carrier,
        _player(9, "ST", 88.0, 34.0),
        _player(6, "CM", 74.0, 34.0),
    ]
    opponents = [
        _player(2, "CB", 89.0, 29.0, attacking=False),
        _player(3, "CB", 89.0, 39.0, attacking=False),
        _player(4, "LB", 80.0, 58.0, attacking=False),
    ]
    trace = MatchTrace()

    action, details = carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=1,
        team_side="home",
        trace=trace,
    )

    assert action in {"carry", "pass", "pass_to_space", "shoot", "hold", "clear"}
    assert isinstance(details, dict)
    assert trace.decisions
    goal_payload = trace.decisions[-1].get("goal")
    assert goal_payload is not None
    assert goal_payload["goal"]["goal_type"] == "cut_inside_to_shoot"
    assert goal_payload["reason"] in {
        "no_current_goal",
        "candidate_clears_switch_cost",
        "current_goal_within_switch_cost",
    }
    assert carrier.current_goal is not None


def test_cut_inside_goal_biases_second_touch_shot_window():
    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 88.0, 30.0)
    carrier.current_goal = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(90.0, 32.0),
        value=0.4,
        created_tick=1,
        last_updated_tick=2,
    )
    carrier.consecutive_carries = 2
    teammates = [carrier, _player(9, "ST", 91.0, 34.0)]
    opponents = [
        _player(2, "CB", 94.0, 29.0, attacking=False),
        _player(3, "CB", 94.0, 39.0, attacking=False),
    ]

    action, _ = carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=3,
        team_side="home",
        trace=None,
    )

    assert action in {"shoot", "carry", "pass", "pass_to_space", "hold", "clear"}
    assert carrier.current_goal is not None
    assert carrier.current_goal.goal_type == "cut_inside_to_shoot"


def test_goal_continuity_can_be_disabled_for_on_ball_trace():
    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = False
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 78.0, 56.0)
    teammates = [carrier, _player(9, "ST", 88.0, 34.0)]
    opponents = [_player(2, "CB", 89.0, 34.0, attacking=False)]
    trace = MatchTrace()

    action, _ = carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=1,
        team_side="home",
        trace=trace,
    )

    assert trace.decisions
    assert "goal" not in trace.decisions[-1]
    assert carrier.current_goal is None


def test_on_ball_goal_does_not_hold_when_overlap_pass_is_already_best():
    config = EngineConfig(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.02
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 70.0, 58.0)
    carrier.abilities["Dribbling"] = 58
    carrier.abilities["Long_Shot"] = 48
    overlapping = _player(2, "RB", 78.0, 62.0)
    overlapping.target_pos = (86.0, 62.0)
    overlapping.tactical_anchor = (86.0, 62.0)
    teammates = [
        carrier,
        overlapping,
        _player(9, "ST", 86.0, 34.0),
    ]
    opponents = [
        _player(3, "CB", 88.0, 31.0, attacking=False),
        _player(4, "CB", 89.0, 39.0, attacking=False),
        _player(5, "LB", 74.0, 54.0, attacking=False),
    ]
    trace = MatchTrace()

    action, _ = carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=1,
        team_side="home",
        trace=trace,
    )

    goal_payload = trace.decisions[-1].get("goal")
    assert action in {"pass", "pass_to_space"}
    assert goal_payload is None or goal_payload["goal"]["goal_type"] != "wide_hold_for_overlap"


def test_arc_arrival_goal_appears_for_wide_final_third_attack():
    goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(72.0, 48.0),
        anchor_pos=(78.0, 42.0),
        ball_pos=(80.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
    )

    assert goal is not None
    assert goal.goal_type == "arc_arrival_for_cutback"
    assert goal.value > 0.0
    assert 74.0 < goal.target_pos[0] < 84.5
    assert abs(goal.target_pos[1] - 34.0) < abs(42.0 - 34.0)
    assert goal.context["ball_width"] > 0.28


def test_arc_arrival_goal_absent_when_ball_is_not_wide_or_advanced():
    goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(72.0, 48.0),
        anchor_pos=(78.0, 42.0),
        ball_pos=(64.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
    )

    assert goal is None


def test_arc_arrival_goal_exposes_front_line_fit_components():
    midfield_goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(72.0, 34.0),
        anchor_pos=(72.0, 34.0),
        ball_pos=(82.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
    )
    front_line_goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(88.0, 34.0),
        anchor_pos=(88.0, 34.0),
        ball_pos=(82.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
    )

    assert midfield_goal is not None
    assert front_line_goal is None or front_line_goal.value < midfield_goal.value


def test_arc_arrival_prefers_midfield_support_over_front_line_runner():
    midfield_goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(70.0, 38.0),
        anchor_pos=(74.0, 38.0),
        ball_pos=(84.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
        base_pos=(52.0, 38.0),
    )
    front_line_goal = evaluate_arc_arrival_for_cutback_goal(
        player_pos=(84.0, 34.0),
        anchor_pos=(82.0, 35.0),
        ball_pos=(84.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=52,
        base_pos=(84.0, 34.0),
    )

    assert midfield_goal is not None
    assert front_line_goal is None or midfield_goal.value > front_line_goal.value


def test_off_ball_arc_arrival_goal_sets_current_goal_when_enabled():
    config = EngineConfig()
    config.goal_continuity_enabled = True
    pitch = Pitch(config=config)
    player = _player(6, "CM", 72.0, 48.0)
    player.tactical_anchor = (78.0, 42.0)
    ball_carrier = _player(8, "RW", 80.0, 56.0)
    teammates = [player, ball_carrier, _player(9, "ST", 88.0, 34.0)]
    opponents = [
        _player(2, "CB", 89.0, 29.0, attacking=False),
        _player(3, "CB", 89.0, 39.0, attacking=False),
    ]

    player.choose_off_ball_attack(
        ball_carrier.pos,
        config,
        pitch,
        True,
        ball_carrier=ball_carrier,
        opponents=opponents,
        teammates=teammates,
    )

    assert player.current_goal is not None
    assert player.current_goal.goal_type == "arc_arrival_for_cutback"
    assert abs(player.current_goal.target_pos[1] - pitch.width / 2.0) < abs(player.tactical_anchor[1] - pitch.width / 2.0)


def test_off_ball_arc_arrival_goal_can_be_disabled():
    config = EngineConfig()
    config.goal_continuity_enabled = False
    pitch = Pitch(config=config)
    player = _player(6, "CM", 72.0, 48.0)
    player.tactical_anchor = (78.0, 42.0)
    ball_carrier = _player(8, "RW", 80.0, 56.0)

    player.choose_off_ball_attack(
        ball_carrier.pos,
        config,
        pitch,
        True,
        ball_carrier=ball_carrier,
        opponents=[],
        teammates=[player, ball_carrier],
    )

    assert player.current_goal is None


def test_off_ball_attack_clears_stale_on_ball_goal():
    config = EngineConfig()
    config.goal_continuity_enabled = True
    pitch = Pitch(config=config)
    player = _player(6, "CM", 72.0, 42.0)
    player.current_goal = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(82.0, 34.0),
        value=0.2,
        context={"phase": "drive"},
    )
    ball_carrier = _player(8, "RW", 80.0, 56.0)

    player.choose_off_ball_attack(
        ball_carrier.pos,
        config,
        pitch,
        True,
        ball_carrier=ball_carrier,
        opponents=[],
        teammates=[player, ball_carrier],
    )

    assert player.current_goal is None or player.current_goal.goal_type != "cut_inside_to_shoot"


def test_off_ball_far_post_goal_sets_current_goal_when_enabled():
    config = EngineConfig()
    config.goal_continuity_enabled = True
    pitch = Pitch(config=config)
    player = _player(10, "LW", 91.0, 18.0)
    player.tactical_anchor = (92.0, 18.0)
    ball_carrier = _player(8, "RW", 88.0, 58.0)
    teammates = [player, ball_carrier, _player(9, "ST", 90.0, 34.0)]
    opponents = [
        _player(2, "CB", 91.0, 30.0, attacking=False),
        _player(3, "CB", 91.0, 39.0, attacking=False),
    ]

    player.choose_off_ball_attack(
        ball_carrier.pos,
        config,
        pitch,
        True,
        ball_carrier=ball_carrier,
        opponents=opponents,
        teammates=teammates,
    )

    assert player.current_goal is not None
    assert player.current_goal.goal_type == "attack_far_post"
    assert player.current_goal.target_pos[0] > 90.0


def test_wide_hold_goal_appears_for_developing_overlap():
    goal = evaluate_wide_hold_for_overlap_goal(
        player_pos=(76.0, 58.0),
        overlap_target=(84.0, 62.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        overlap_value=0.16,
        immediate_best_score=0.06,
        tick=70,
    )

    assert goal is not None
    assert goal.goal_type == "wide_hold_for_overlap"
    assert goal.value > 0.0
    assert goal.target_pos == (76.0, 58.0)
    assert goal.context["overlap_value"] == 0.16


def test_wide_hold_goal_absent_when_immediate_action_is_too_good():
    goal = evaluate_wide_hold_for_overlap_goal(
        player_pos=(76.0, 58.0),
        overlap_target=(84.0, 62.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        overlap_value=0.16,
        immediate_best_score=0.32,
        tick=70,
    )

    assert goal is None


def test_release_pressure_goal_appears_for_short_layoff_under_pressure():
    goal = evaluate_release_pressure_with_layoff_goal(
        player_pos=(82.0, 42.0),
        layoff_target=(74.0, 34.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        attracted_pressure=0.55,
        layoff_value=0.11,
        immediate_best_score=0.08,
        tick=88,
    )

    assert goal is not None
    assert goal.goal_type == "release_pressure_with_layoff"
    assert goal.target_pos == (74.0, 34.0)
    assert goal.value > 0.0
    assert goal.context["attracted_pressure"] == 0.55


def test_release_pressure_goal_absent_without_pressure():
    goal = evaluate_release_pressure_with_layoff_goal(
        player_pos=(82.0, 42.0),
        layoff_target=(74.0, 34.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        attracted_pressure=0.05,
        layoff_value=0.11,
        immediate_best_score=0.08,
        tick=88,
    )

    assert goal is None


def test_hold_for_opportunity_goal_appears_for_low_quality_possession():
    goal = evaluate_hold_for_opportunity_goal(
        player_pos=(78.0, 34.0),
        support_target=(72.0, 42.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.11,
        hold_value=0.35,
        shot_components={"xg": 0.035, "shot_readiness": 0.02},
        immediate_best_score=0.08,
        tick=80,
    )

    assert goal is not None
    assert goal.goal_type == "hold_for_opportunity"
    assert goal.context["phase"] == "scan"
    assert goal.context["current_shot"] == 0.035


def test_hold_for_opportunity_goal_absent_when_shot_window_is_clear():
    goal = evaluate_hold_for_opportunity_goal(
        player_pos=(90.0, 34.0),
        support_target=(82.0, 42.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.14,
        hold_value=0.40,
        shot_components={"xg": 0.18, "shot_readiness": 0.70},
        immediate_best_score=0.18,
        tick=82,
    )

    assert goal is None


def test_hold_for_opportunity_goal_can_retain_without_support_target():
    goal = evaluate_hold_for_opportunity_goal(
        player_pos=(72.0, 34.0),
        support_target=(72.0, 34.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.0,
        hold_value=0.45,
        shot_components={"xg": 0.025, "shot_readiness": 0.0},
        immediate_best_score=0.04,
        tick=84,
    )

    assert goal is not None
    assert goal.goal_type == "hold_for_opportunity"
    assert goal.target_pos == (72.0, 34.0)
    assert goal.context["pass_distance"] == 0.0


def test_attack_far_post_goal_appears_for_weak_side_runner_on_deep_wide_attack():
    goal = evaluate_attack_far_post_goal(
        player_pos=(84.0, 20.0),
        anchor_pos=(86.0, 22.0),
        ball_pos=(88.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=96,
    )

    assert goal is not None
    assert goal.goal_type == "attack_far_post"
    assert goal.value > 0.0
    assert goal.target_pos[0] > 90.0
    assert goal.target_pos[1] < 34.0
    assert goal.context["weak_side"] > 0.0


def test_attack_far_post_goal_absent_when_ball_is_not_wide():
    goal = evaluate_attack_far_post_goal(
        player_pos=(84.0, 20.0),
        anchor_pos=(86.0, 22.0),
        ball_pos=(88.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=96,
    )

    assert goal is None


def test_attack_far_post_goal_is_low_value_for_deep_support_player():
    goal = evaluate_attack_far_post_goal(
        player_pos=(56.0, 22.0),
        anchor_pos=(58.0, 22.0),
        ball_pos=(88.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        tick=96,
    )

    assert goal is not None
    assert goal.value < 0.01
