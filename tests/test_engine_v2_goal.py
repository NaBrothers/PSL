from psl_core.engine_v2.goal import (
    evaluate_attack_far_post_goal,
    build_defensive_goal,
    build_off_ball_attack_goal,
    build_on_ball_action_goal,
    GoalSwitchContext,
    PlayerGoal,
    select_goal_candidate,
    evaluate_arc_arrival_for_cutback_goal,
    evaluate_cut_inside_to_shoot_goal,
    evaluate_hold_for_opportunity_goal,
    evaluate_byline_delivery_goal,
    evaluate_drive_byline_goal,
    evaluate_release_to_arriving_support_goal,
    evaluate_release_pressure_with_layoff_goal,
    evaluate_through_ball_goal,
    evaluate_wide_hold_for_overlap_goal,
    goal_switch_cost,
    select_goal,
)
from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.decision import iq_decision_noise, iq_temperature_factor
from psl_core.engine_v2.ball import BallState
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.physics import distance
from psl_core.engine_v2.replay_adapter import build_frame
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


def _engine_config(**kwargs) -> EngineConfig:
    config = EngineConfig(**kwargs)
    config.goal_noise_scale = 0.0
    return config


class _FixedGaussian:
    def __init__(self, values):
        self.values = list(values)

    def gauss(self, _mu, _sigma):
        return self.values.pop(0)


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
    config = _engine_config(total_ticks=4, half_ticks=2)
    match = MatchV2(_cards(), _cards(), "442", "442", config=config)
    match.home.players[8].current_goal = _goal("arc_arrival_for_cutback", 0.30)
    match.away.players[9].current_goal = _goal("hold_for_opportunity", 0.25)
    match.ball.state = BallState.HELD
    match.ball.holder_team = "away"
    match.ball.holder_idx = 9

    match._sync_goals_with_phase()

    assert match.home.players[8].current_goal is None
    assert match.away.players[9].current_goal is not None


def test_replay_frame_shows_engine_current_goals_without_phase_filtering():
    class _Team:
        def __init__(self, players):
            self.players = players

    home_player = _player(1, "CM", 60.0, 34.0)
    away_player = _player(2, "CB", 46.0, 34.0)
    home_player.current_goal = PlayerGoal(
        goal_type="progress_carry",
        target_pos=(66.0, 34.0),
        value=0.2,
    )
    away_player.current_goal = PlayerGoal(
        goal_type="defend_cover_lane",
        target_pos=(50.0, 34.0),
        value=0.2,
        context={"action": "block_lane"},
    )

    frame = build_frame(
        tick=1,
        tick_duration=2.0,
        half=1,
        home_team=_Team([home_player]),
        away_team=_Team([away_player]),
        ball_pos=(60.0, 34.0),
        ball_holder_idx=0,
        ball_team="home",
        home_score=0,
        away_score=0,
    )

    assert frame["home_player_goals"] == ["progress_carry"]
    assert frame["away_player_goals"] == ["defend_cover_lane"]

    home_player.current_goal = PlayerGoal(
        goal_type="defend_press",
        target_pos=(60.0, 34.0),
        value=0.2,
        context={"action": "approach"},
    )
    away_player.current_goal = PlayerGoal(
        goal_type="run_behind",
        target_pos=(42.0, 34.0),
        value=0.2,
    )
    frame = build_frame(
        tick=2,
        tick_duration=2.0,
        half=1,
        home_team=_Team([home_player]),
        away_team=_Team([away_player]),
        ball_pos=(60.0, 34.0),
        ball_holder_idx=0,
        ball_team="home",
        home_score=0,
        away_score=0,
    )

    assert frame["home_player_goals"] == ["defend_press"]
    assert frame["away_player_goals"] == ["run_behind"]


def test_give_ball_clears_previous_and_new_holder_goals_on_turnover():
    config = _engine_config(total_ticks=4, half_ticks=2)
    match = MatchV2(_cards(), _cards(), "442", "442", config=config)
    previous = match.home.players[8]
    new_holder = match.away.players[4]
    previous.current_goal = PlayerGoal(
        goal_type="progress_carry",
        target_pos=(70.0, 34.0),
        value=0.2,
    )
    new_holder.current_goal = PlayerGoal(
        goal_type="defend_press",
        target_pos=(52.0, 34.0),
        value=0.2,
        context={"action": "approach"},
    )
    match.ball.set_held(previous.index, match.home.side, previous.pos)

    match._give_ball(new_holder, match.away)

    assert previous.current_goal is None
    assert new_holder.current_goal is None
    assert match.ball.holder_team == "away"
    assert match.ball.holder_idx == new_holder.index


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


def test_cut_inside_drive_goal_updates_same_intent_target_without_switch():
    current = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(82.0, 44.0),
        value=0.20,
        context={"phase": "drive", "goal_age_ticks": 0},
    )
    candidate = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(84.0, 42.0),
        value=0.26,
        context={"phase": "drive", "goal_age_ticks": 2},
    )

    selection = select_goal(current, candidate, GoalSwitchContext(base=0.50))

    assert not selection.switched
    assert selection.goal is candidate
    assert selection.reason == "current_goal_drive_updated"
    assert selection.goal.target_pos == (84.0, 42.0)
    assert selection.goal.context["goal_age_ticks"] == 2


def test_hold_for_opportunity_scan_goal_updates_lifecycle_without_switch():
    current = PlayerGoal(
        goal_type="hold_for_opportunity",
        target_pos=(72.0, 42.0),
        value=0.18,
        context={"phase": "scan", "goal_age_ticks": 0},
    )
    candidate = PlayerGoal(
        goal_type="hold_for_opportunity",
        target_pos=(74.0, 40.0),
        value=0.12,
        context={"phase": "scan", "goal_age_ticks": 4},
    )

    selection = select_goal(current, candidate, GoalSwitchContext(base=0.50))

    assert not selection.switched
    assert selection.goal is candidate
    assert selection.reason == "current_goal_scan_updated"
    assert selection.goal.target_pos == (74.0, 40.0)
    assert selection.goal.context["goal_age_ticks"] == 4


def test_pressure_interrupt_lowers_goal_switch_cost():
    stable = GoalSwitchContext(base=0.04, pressure_interrupt=0.0, iq=80)
    pressured = GoalSwitchContext(base=0.04, pressure_interrupt=0.8, iq=80)

    assert goal_switch_cost(pressured) < goal_switch_cost(stable)


def test_goal_noise_can_flip_close_switch_decision():
    current = _goal("hold_for_opportunity", 0.200)
    candidate = _goal("release_to_arriving_support", 0.231)
    context = GoalSwitchContext(
        base=0.035,
        iq=70,
        goal_noise_scale=0.010,
        rng=_FixedGaussian([0.020]),
    )

    selection = select_goal(current, candidate, context)

    assert selection.switched
    assert selection.value_advantage < selection.switch_cost
    assert selection.noisy_value_advantage > selection.switch_cost
    assert selection.switch_noise > 0.0


def test_goal_noise_does_not_override_clear_value_gap_when_capped():
    current = _goal("hold_for_opportunity", 0.200)
    candidate = _goal("release_to_arriving_support", 0.255)
    context = GoalSwitchContext(
        base=0.035,
        iq=130,
        goal_noise_scale=0.008,
        rng=_FixedGaussian([-1.0]),
    )

    selection = select_goal(current, candidate, context)

    assert selection.switched
    assert selection.value_advantage > selection.switch_cost
    assert selection.noisy_value_advantage > selection.switch_cost


def test_goal_candidate_noise_only_affects_close_goal_values():
    lower = _goal("support_carrier", 0.200)
    higher = _goal("arc_arrival_for_cutback", 0.204)
    context = GoalSwitchContext(
        iq=70,
        goal_noise_scale=0.010,
        rng=_FixedGaussian([0.010, -0.010]),
    )

    choice = select_goal_candidate([lower, higher], context)

    assert choice is not None
    assert choice.goal is lower
    assert choice.noisy_value > higher.value


def test_iq_above_100_reduces_decision_noise_with_diminishing_returns():
    assert iq_decision_noise(70) > iq_decision_noise(100)
    assert iq_decision_noise(100) > iq_decision_noise(130)
    assert iq_decision_noise(130) > 0.0


def test_iq_temperature_factor_keeps_elite_players_more_stable():
    low = iq_temperature_factor(70, floor=0.18, low_iq_range=0.62, elite_discount=0.30)
    normal = iq_temperature_factor(100, floor=0.18, low_iq_range=0.62, elite_discount=0.30)
    elite = iq_temperature_factor(130, floor=0.18, low_iq_range=0.62, elite_discount=0.30)

    assert low > normal > elite > 0.0


def test_defensive_goal_maps_box_threat_to_protect_box():
    goal = build_defensive_goal(
        action_type="block_lane",
        target_pos=(82.0, 34.0),
        value=0.20,
        tick=9,
        pressure=0.25,
        threat=0.72,
    )

    assert goal.goal_type == "defend_protect_box"
    assert goal.context["action"] == "block_lane"


def test_defensive_goal_keeps_cover_lane_when_threat_is_lower():
    goal = build_defensive_goal(
        action_type="block_lane",
        target_pos=(72.0, 42.0),
        value=0.12,
        tick=9,
        pressure=0.18,
        threat=0.32,
    )

    assert goal.goal_type == "defend_cover_lane"


def test_off_ball_attack_goal_maps_second_line_support():
    goal = build_off_ball_attack_goal(
        target_pos=(78.0, 34.0),
        value=0.21,
        tick=10,
        components={
            "second_line_support": 0.32,
            "candidate_progress": 0.74,
            "candidate_width": 0.10,
        },
    )

    assert goal.goal_type == "support_second_line"
    assert goal.context["second_line_support"] == 0.32


def test_off_ball_attack_goal_maps_width_and_recycle():
    wide = build_off_ball_attack_goal(
        target_pos=(72.0, 58.0),
        value=0.12,
        tick=10,
        components={"candidate_progress": 0.68, "candidate_width": 0.72},
    )
    recycle = build_off_ball_attack_goal(
        target_pos=(55.0, 34.0),
        value=0.08,
        tick=10,
        components={"candidate_progress": 0.46, "candidate_width": 0.10},
    )

    assert wide.goal_type == "hold_width"
    assert recycle.goal_type == "recycle_support"


def test_off_ball_attack_goal_maps_box_arrival():
    goal = build_off_ball_attack_goal(
        target_pos=(94.0, 34.0),
        value=0.18,
        tick=10,
        components={
            "candidate_progress": 0.88,
            "candidate_width": 0.10,
            "support_angle_value": 0.34,
        },
    )

    assert goal.goal_type == "attack_box"
    assert goal.context["box_arrival"] > 0.0


def test_on_ball_action_goal_maps_core_actions():
    carry = build_on_ball_action_goal(
        action_type="carry",
        target_pos=(70.0, 34.0),
        value=0.12,
        tick=4,
        components={"progress_gain": 0.04},
    )
    shot = build_on_ball_action_goal(
        action_type="shoot",
        target_pos=(105.0, 34.0),
        value=0.20,
        tick=4,
        components={"xg": 0.12},
    )
    through = build_on_ball_action_goal(
        action_type="pass",
        target_pos=(82.0, 38.0),
        value=0.15,
        tick=4,
        components={"progress_gain": 0.05, "target_kind": "space"},
    )

    assert carry.goal_type == "progress_carry"
    assert shot.goal_type == "create_shot"
    assert through.goal_type == "through_ball"


def test_generic_on_ball_goal_continuity_keeps_close_existing_intent():
    config = _engine_config()
    config.goal_cut_inside_bias = 0.08
    player = _player(8, "CM", 64.0, 34.0)
    player.current_goal = PlayerGoal(
        goal_type="recycle",
        target_pos=(58.0, 34.0),
        value=0.300,
        confidence=0.300,
        created_tick=7,
        last_updated_tick=8,
        context={"action": "pass"},
    )
    pass_candidate = player._make_candidate(
        "pass",
        0.300,
        {"target": (58.0, 34.0), "components": {"progress_gain": -0.03}},
        "test",
    )
    carry_candidate = player._make_candidate(
        "carry",
        0.307,
        {"target": (67.0, 34.0), "components": {"progress_gain": 0.02}},
        "test",
    )

    biased, goal_trace = player._apply_generic_on_ball_goal_continuity(
        [pass_candidate, carry_candidate],
        config,
        tick=9,
    )

    assert goal_trace is not None
    assert not goal_trace["switched"]
    assert goal_trace["reason"] == "current_goal_within_switch_cost"
    assert player.current_goal is not None
    assert player.current_goal.goal_type == "recycle"
    pass_score = next(candidate.score for candidate in biased if candidate.action_type == "pass")
    carry_score = next(candidate.score for candidate in biased if candidate.action_type == "carry")
    assert pass_score > pass_candidate.score
    assert carry_score == carry_candidate.score


def test_goal_taxonomy_covers_architecture_goal_families():
    on_ball_goals = {
        build_on_ball_action_goal(
            action_type="shoot",
            target_pos=(105.0, 34.0),
            value=0.20,
            tick=1,
            components={"xg": 0.12},
        ).goal_type,
        build_on_ball_action_goal(
            action_type="carry",
            target_pos=(72.0, 34.0),
            value=0.12,
            tick=1,
            components={"progress_gain": 0.04},
        ).goal_type,
        build_on_ball_action_goal(
            action_type="hold",
            target_pos=(70.0, 34.0),
            value=0.05,
            tick=1,
            components={},
        ).goal_type,
        build_on_ball_action_goal(
            action_type="pass",
            target_pos=(58.0, 44.0),
            value=0.08,
            tick=1,
            components={"progress_gain": -0.04},
        ).goal_type,
        build_on_ball_action_goal(
            action_type="pass",
            target_pos=(70.0, 58.0),
            value=0.08,
            tick=1,
            components={"progress_gain": 0.02, "lateral_change": 0.40},
        ).goal_type,
        build_on_ball_action_goal(
            action_type="pass",
            target_pos=(86.0, 34.0),
            value=0.11,
            tick=1,
            components={"target_kind": "space", "progress_gain": 0.08},
        ).goal_type,
    }
    off_ball_goals = {
        build_off_ball_attack_goal(
            target_pos=(78.0, 34.0),
            value=0.15,
            tick=1,
            components={"second_line_support": 0.20},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(72.0, 38.0),
            value=0.12,
            tick=1,
            components={"inside_support": 0.24},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(74.0, 42.0),
            value=0.12,
            tick=1,
            components={"support_angle_value": 0.24},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(72.0, 58.0),
            value=0.10,
            tick=1,
            components={"candidate_progress": 0.66, "candidate_width": 0.70},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(88.0, 34.0),
            value=0.10,
            tick=1,
            components={"candidate_progress": 0.80, "candidate_width": 0.92},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(94.0, 34.0),
            value=0.12,
            tick=1,
            components={"candidate_progress": 0.88, "candidate_width": 0.10, "support_angle_value": 0.30},
        ).goal_type,
        build_off_ball_attack_goal(
            target_pos=(50.0, 34.0),
            value=0.08,
            tick=1,
            components={"candidate_progress": 0.45, "candidate_width": 0.20},
        ).goal_type,
    }
    defense_goals = {
        build_defensive_goal(action_type="approach", target_pos=(80.0, 34.0), value=0.1, tick=1).goal_type,
        build_defensive_goal(action_type="block_lane", target_pos=(76.0, 34.0), value=0.1, tick=1).goal_type,
        build_defensive_goal(action_type="mark_runner", target_pos=(78.0, 44.0), value=0.1, tick=1).goal_type,
        build_defensive_goal(action_type="hold_position", target_pos=(78.0, 34.0), value=0.1, tick=1, threat=0.70).goal_type,
        build_defensive_goal(action_type="hold_position", target_pos=(58.0, 34.0), value=0.1, tick=1, threat=0.10).goal_type,
    }

    assert {"create_shot", "progress_carry", "protect_ball", "recycle", "switch_play", "through_ball"} <= on_ball_goals
    assert {"support_second_line", "drop_between_lines", "support_carrier", "hold_width", "run_behind", "attack_box", "recycle_support"} <= off_ball_goals
    assert {"defend_press", "defend_cover_lane", "defend_mark_runner", "defend_protect_box", "defend_recover_shape"} <= defense_goals


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


def test_cut_inside_goal_uses_best_carry_target_when_available():
    goal = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.09,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.04,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        best_carry_target=(83.5, 43.0),
        tick=42,
    )

    assert goal is not None
    assert goal.target_pos == (83.5, 43.0)


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


def test_cut_inside_drive_value_decays_when_plan_gets_stale():
    fresh = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.09,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.04,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        consecutive_carries=0,
        goal_age_ticks=0,
        tick=42,
    )
    stale = evaluate_cut_inside_to_shoot_goal(
        player_pos=(78.0, 56.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        best_carry_components={
            "future_shot_gain": 0.09,
            "carry_to_shoot_window": 0.12,
            "wide_second_line_carry_window": 0.04,
        },
        best_shot_components={"xg": 0.025, "shot_readiness": 0.0},
        consecutive_carries=4,
        goal_age_ticks=7,
        tick=49,
    )

    assert fresh is not None
    assert stale is not None
    assert stale.value < fresh.value
    assert stale.context["drive_staleness"] > fresh.context["drive_staleness"]


def test_cut_inside_release_phase_stays_traceable_without_forcing_clear():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
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
    assert carrier.current_goal is not None
    assert carrier.current_goal.goal_type == "cut_inside_to_shoot"
    assert carrier.current_goal.context["phase"] == "release"


def test_on_ball_goal_trace_records_cut_inside_without_forcing_action():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
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
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
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


def test_cut_inside_goal_biases_carry_toward_goal_target():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 78.0, 56.0)
    carrier.current_goal = PlayerGoal(
        goal_type="cut_inside_to_shoot",
        target_pos=(84.0, 42.0),
        value=0.30,
        created_tick=1,
        last_updated_tick=1,
        context={"phase": "drive"},
    )
    near_goal_carry = carrier._make_candidate(
        "carry",
        0.050,
        {
            "target": (84.0, 42.5),
            "components": {
                "carry_to_shoot_window": 0.0,
                "wide_second_line_carry_window": 0.0,
            },
        },
        "test",
    )
    wide_carry = carrier._make_candidate(
        "carry",
        0.050,
        {
            "target": (84.0, 56.0),
            "components": {
                "carry_to_shoot_window": 0.0,
                "wide_second_line_carry_window": 0.0,
            },
        },
        "test",
    )

    biased, goal_trace = carrier._apply_on_ball_goal_bias(
        [near_goal_carry, wide_carry],
        [(0.050, "carry", near_goal_carry.details), (0.050, "carry", wide_carry.details)],
        [],
        [],
        [],
        {},
        0.050,
        config,
        pitch,
        True,
        tick=2,
    )

    assert goal_trace is not None
    near_score = next(candidate.score for candidate in biased if candidate.target == (84.0, 42.5))
    wide_score = next(candidate.score for candidate in biased if candidate.target == (84.0, 56.0))
    assert near_score > wide_score


def test_hold_for_opportunity_biases_carry_to_stretch_space():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 78.0, 54.0)
    carrier.current_goal = PlayerGoal(
        goal_type="hold_for_opportunity",
        target_pos=(82.0, 44.0),
        value=0.34,
        created_tick=1,
        last_updated_tick=1,
        context={"phase": "scan"},
    )
    stretch_carry = carrier._make_candidate(
        "carry",
        0.040,
        {
            "target": (82.0, 44.5),
            "components": {"pressure_draw": 0.35, "space_manipulation": 0.42},
        },
        "test",
    )
    static_hold = carrier._make_candidate(
        "hold",
        0.040,
        {"target": carrier.pos, "components": {}},
        "test",
    )

    biased, goal_trace = carrier._apply_on_ball_goal_bias(
        [stretch_carry, static_hold],
        [(0.040, "carry", stretch_carry.details)],
        [],
        [],
        [],
        {"components": {"xg": 0.025, "shot_readiness": 0.0}},
        0.040,
        config,
        pitch,
        True,
        tick=2,
    )

    assert goal_trace is not None
    carry_score = next(candidate.score for candidate in biased if candidate.action_type == "carry")
    hold_score = next(candidate.score for candidate in biased if candidate.action_type == "hold")
    assert carry_score > hold_score


def test_goal_continuity_can_be_disabled_for_on_ball_trace():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
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
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
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


def test_on_ball_goal_releases_to_arriving_arc_support():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(7, "RW", 78.0, 54.0)
    carrier.facing_direction = -90.0
    carrier.possession_ticks = 2
    support = _player(6, "CM", 70.0, 36.0)
    support.tactical_anchor = (76.0, 35.0)
    support.base_formation_pos = (52.0, 35.0)
    support.target_pos = (78.0, 35.0)
    support.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=(78.0, 35.0),
        value=0.32,
        context={"phase": "arrive"},
    )
    striker = _player(9, "ST", 88.0, 34.0)
    teammates = [carrier, support, striker]
    opponents = [
        _player(2, "CB", 89.0, 30.0, attacking=False),
        _player(3, "CB", 90.0, 41.0, attacking=False),
        _player(4, "LB", 82.0, 54.0, attacking=False),
    ]
    trace = MatchTrace()

    carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=8,
        team_side="home",
        trace=trace,
    )

    goal_payload = trace.decisions[-1]["goal"]
    assert goal_payload["goal"]["goal_type"] == "release_to_arriving_support"
    alternatives = trace.decisions[-1]["alternatives"]
    candidate_targets = [
        item["target"]
        for item in alternatives
        if item["action_type"] in ("pass", "pass_to_space")
        and item["value"]["components"].get("receiver_goal_fit", 0.0) > 0.0
    ]
    chosen = trace.decisions[-1]["chosen"]
    if chosen["action_type"] in ("pass", "pass_to_space"):
        candidate_targets.append(chosen["target"])
    assert any(distance(tuple(target), support.current_goal.target_pos) < 14.0 for target in candidate_targets)


def test_on_ball_goal_trace_records_through_ball_behind_option():
    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(6, "CM", 68.0, 34.0)
    carrier.facing_direction = 0.0
    runner = _player(9, "ST", 82.0, 34.0)
    runner.target_pos = (88.0, 34.0)
    runner.tactical_anchor = (88.0, 34.0)
    winger = _player(8, "RW", 76.0, 54.0)
    teammates = [carrier, runner, winger]
    opponents = [
        _player(2, "CB", 84.0, 28.0, attacking=False),
        _player(3, "CB", 84.0, 40.0, attacking=False),
        _player(5, "DM", 74.0, 34.0, attacking=False),
    ]
    trace = MatchTrace()

    carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=8,
        team_side="home",
        trace=trace,
    )

    goal_payload = trace.decisions[-1]["goal"]
    assert goal_payload is not None
    through_candidates = [
        item
        for item in trace.decisions[-1]["alternatives"] + [trace.decisions[-1]["chosen"]]
        if item["action_type"] == "pass"
        and item["value"]["components"].get("target_kind") == "space"
        and item["value"]["components"].get("progress_gain", 0.0) > 0.08
        and item["value"]["components"].get("high_threat_space", 0.0) > 0.0
    ]
    assert through_candidates


def test_wide_carrier_can_choose_drive_byline_goal_before_cross():
    import random

    config = _engine_config(total_ticks=4, half_ticks=2, frame_interval=1)
    config.goal_continuity_enabled = True
    config.goal_cut_inside_bias = 0.08
    config.trace.detail = "full"
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 82.0, 58.0)
    striker = _player(9, "ST", 91.0, 34.0)
    striker.target_pos = (93.0, 34.0)
    far_winger = _player(10, "LW", 90.0, 30.5)
    far_winger.target_pos = (96.0, 30.8)
    midfielder = _player(6, "CM", 80.0, 34.0)
    teammates = [carrier, striker, far_winger, midfielder]
    opponents = [
        _player(1, "LB", 86.0, 51.0, attacking=False),
        _player(2, "CB", 91.0, 29.0, attacking=False),
        _player(3, "CB", 93.0, 39.0, attacking=False),
        _player(5, "DM", 81.0, 34.0, attacking=False),
    ]
    trace = MatchTrace()

    random.seed(7)
    carrier.choose_on_ball(
        teammates,
        opponents,
        config,
        pitch,
        True,
        tick=8,
        team_side="home",
        trace=trace,
    )

    goal_payload = trace.decisions[-1]["goal"]
    assert goal_payload is not None
    assert goal_payload["goal"]["goal_type"] in {"wide_byline_attack", "cut_inside_to_shoot"}
    if goal_payload["goal"]["goal_type"] == "wide_byline_attack":
        chosen = trace.decisions[-1]["chosen"]
        assert chosen["action_type"] == "carry"
        assert distance(tuple(chosen["target"]), tuple(goal_payload["goal"]["target_pos"])) < 1.0
    carry_targets = [
        item["target"]
        for item in trace.decisions[-1]["alternatives"] + [trace.decisions[-1]["chosen"]]
        if item["action_type"] == "carry"
        and item["value"]["components"].get("byline_carry_window", 0.0) > 0.0
    ]
    assert carry_targets


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
    config = _engine_config()
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


def test_generic_off_ball_goal_continuity_keeps_close_support_intent():
    import random

    config = _engine_config()
    config.goal_continuity_enabled = True
    config.trace.detail = "full"
    config.trace.include_off_ball = True
    random.seed(12)
    pitch = Pitch(config=config)
    player = _player(6, "CM", 70.0, 34.0)
    player.tactical_anchor = (72.0, 34.0)
    existing_target = (74.0, 36.0)
    player.current_goal = PlayerGoal(
        goal_type="support_carrier",
        target_pos=existing_target,
        value=0.840,
        confidence=0.840,
        created_tick=4,
        last_updated_tick=5,
        context={"phase": "support"},
    )
    ball_carrier = _player(8, "RW", 78.0, 48.0)
    teammates = [player, ball_carrier, _player(9, "ST", 88.0, 34.0)]
    opponents = [
        _player(2, "CB", 90.0, 30.0, attacking=False),
        _player(3, "CB", 90.0, 40.0, attacking=False),
    ]
    trace = MatchTrace()

    target = player.choose_off_ball_attack(
        ball_carrier.pos,
        config,
        pitch,
        True,
        ball_carrier=ball_carrier,
        opponents=opponents,
        teammates=teammates,
        tick=9,
        team_side="home",
        trace=trace,
    )

    goal_trace = trace.decisions[-1]["goal"]
    assert goal_trace is not None
    assert not goal_trace["switched"]
    assert goal_trace["reason"] == "current_goal_within_switch_cost"
    assert player.current_goal is not None
    assert player.current_goal.goal_type == "support_carrier"
    assert distance(target, existing_target) < distance(player.pos, existing_target)


def test_off_ball_arc_arrival_goal_can_be_disabled():
    config = _engine_config()
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
    config = _engine_config()
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
    config = _engine_config()
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
    assert player.current_goal.target_pos[0] < opponents[1].pos[0]
    assert abs(player.current_goal.target_pos[1] - config.goal_y_min()) < 1.0
    assert distance(player.target_pos, player.current_goal.target_pos) < 6.0


def test_wide_attack_assigns_distinct_arc_and_far_post_targets():
    import random

    config = _engine_config()
    config.goal_continuity_enabled = True
    pitch = Pitch(config=config)
    ball_carrier = _player(11, "RW", 88.0, 58.0)
    runners = [
        _player(6, "LCM", 72.0, 26.0),
        _player(7, "CM", 74.0, 34.0),
        _player(8, "RCM", 74.0, 42.0),
        _player(9, "ST", 89.0, 34.0),
        _player(10, "LW", 91.0, 18.0),
    ]
    anchors = {
        "LCM": ((78.0, 28.0), (52.0, 28.0)),
        "CM": ((80.0, 34.0), (52.0, 34.0)),
        "RCM": ((78.0, 42.0), (52.0, 42.0)),
        "ST": ((90.0, 34.0), (84.0, 34.0)),
        "LW": ((92.0, 18.0), (84.0, 14.0)),
    }
    for runner in runners:
        runner.tactical_anchor, runner.base_formation_pos = anchors[runner.position]
    teammates = runners + [ball_carrier]
    opponents = [
        _player(2, "CB", 91.0, 30.0, attacking=False),
        _player(3, "CB", 91.0, 39.0, attacking=False),
        _player(5, "CM", 80.0, 34.0, attacking=False),
    ]

    random.seed(4)
    for runner in runners:
        runner.choose_off_ball_attack(
            ball_carrier.pos,
            config,
            pitch,
            True,
            ball_carrier=ball_carrier,
            opponents=opponents,
            teammates=teammates,
            tick=100,
        )

    arc_goals = [
        runner.current_goal
        for runner in runners
        if runner.current_goal is not None and runner.current_goal.goal_type == "arc_arrival_for_cutback"
    ]
    far_post_goals = [
        runner.current_goal
        for runner in runners
        if runner.current_goal is not None and runner.current_goal.goal_type == "attack_far_post"
    ]

    assert len(arc_goals) <= 2
    assert len(far_post_goals) <= 1
    for goal in far_post_goals:
        assert abs(goal.target_pos[1] - config.goal_y_min()) < 1.0


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


def test_release_to_arriving_support_goal_appears_for_arc_receiver_goal():
    goal = evaluate_release_to_arriving_support_goal(
        player_pos=(78.0, 54.0),
        support_target=(78.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.16,
        receiver_goal_fit=0.62,
        shot_components={"xg": 0.035, "shot_readiness": 0.05},
        tick=50,
    )

    assert goal is not None
    assert goal.goal_type == "release_to_arriving_support"
    assert goal.context["phase"] == "release"
    assert goal.value > 0.0


def test_release_to_arriving_support_goal_absent_when_shot_window_is_clear():
    goal = evaluate_release_to_arriving_support_goal(
        player_pos=(86.0, 35.0),
        support_target=(78.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.16,
        receiver_goal_fit=0.62,
        shot_components={"xg": 0.16, "shot_readiness": 0.70},
        tick=50,
    )

    assert goal is None


def test_release_to_arriving_support_goal_grows_after_pressure_is_attracted():
    early = evaluate_release_to_arriving_support_goal(
        player_pos=(78.0, 54.0),
        support_target=(78.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.16,
        receiver_goal_fit=0.62,
        shot_components={"xg": 0.035, "shot_readiness": 0.05},
        consecutive_carries=0,
        attracted_pressure=0.0,
        tick=50,
    )
    mature = evaluate_release_to_arriving_support_goal(
        player_pos=(78.0, 54.0),
        support_target=(78.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        support_value=0.16,
        receiver_goal_fit=0.62,
        shot_components={"xg": 0.035, "shot_readiness": 0.05},
        consecutive_carries=3,
        attracted_pressure=0.55,
        tick=53,
    )

    assert early is not None
    assert mature is not None
    assert mature.value > early.value


def test_through_ball_goal_appears_for_central_space_pass_behind_line():
    goal = evaluate_through_ball_goal(
        player_pos=(68.0, 34.0),
        pass_target=(88.0, 34.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        pass_score=0.18,
        components={
            "target_kind": "space",
            "progress_gain": 20.0 / 105.0,
            "target_progress": 88.0 / 105.0,
            "centrality": 1.0,
            "high_threat_space": 0.72,
            "success_prob": 0.56,
            "receiver_pressure": 0.12,
            "lane_risk": 0.18,
        },
        tick=72,
    )

    assert goal is not None
    assert goal.goal_type == "through_ball_behind"
    assert goal.context["phase"] == "release"
    assert goal.value > 0.0


def test_byline_delivery_goal_appears_for_deep_wide_carrier():
    goal = evaluate_byline_delivery_goal(
        player_pos=(96.0, 9.0),
        delivery_target=(101.0, 34.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        pass_score=0.16,
        components={
            "target_kind": "space",
            "target_progress": 101.0 / 105.0,
            "centrality": 1.0,
            "high_threat_space": 0.84,
            "final_third_combination": 0.86,
            "success_prob": 0.28,
            "receiver_pressure": 0.28,
            "lane_risk": 0.18,
        },
        tick=74,
    )

    assert goal is not None
    assert goal.goal_type == "wide_byline_attack"
    assert goal.context["phase"] == "release"
    assert goal.value > 0.0


def test_drive_byline_goal_appears_before_delivery_zone():
    goal = evaluate_drive_byline_goal(
        player_pos=(82.0, 58.0),
        carry_target=(91.0, 60.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        carry_score=0.08,
        components={
            "byline_carry_window": 0.62,
            "path_feasibility": 0.78,
            "progress_gain": 9.0 / 105.0,
            "space_manipulation": 0.32,
        },
        tick=74,
    )

    assert goal is not None
    assert goal.goal_type == "wide_byline_attack"
    assert goal.context["phase"] == "drive"
    assert goal.value > 0.0


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
        goal_width=7.32,
        tick=96,
    )

    assert goal is not None
    assert goal.goal_type == "attack_far_post"
    assert goal.value > 0.0
    assert goal.target_pos[0] > 90.0
    assert 30.0 <= goal.target_pos[1] < 34.0
    assert goal.context["weak_side"] > 0.0


def test_attack_far_post_goal_targets_weak_side_post_not_wide_channel():
    goal = evaluate_attack_far_post_goal(
        player_pos=(84.0, 20.0),
        anchor_pos=(86.0, 22.0),
        ball_pos=(88.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )

    assert goal is not None
    assert abs(goal.target_pos[1] - 30.34) < 1.0

    opposite_goal = evaluate_attack_far_post_goal(
        player_pos=(84.0, 48.0),
        anchor_pos=(86.0, 46.0),
        ball_pos=(88.0, 10.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )

    assert opposite_goal is not None
    assert abs(opposite_goal.target_pos[1] - 37.66) < 1.0


def test_attack_far_post_goal_keeps_weak_side_y_when_attack_direction_flips():
    right_attack = evaluate_attack_far_post_goal(
        player_pos=(84.0, 20.0),
        anchor_pos=(86.0, 22.0),
        ball_pos=(88.0, 58.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )
    left_attack = evaluate_attack_far_post_goal(
        player_pos=(21.0, 20.0),
        anchor_pos=(19.0, 22.0),
        ball_pos=(17.0, 58.0),
        attacking_right=False,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )
    lower_right_attack = evaluate_attack_far_post_goal(
        player_pos=(84.0, 48.0),
        anchor_pos=(86.0, 46.0),
        ball_pos=(88.0, 10.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )
    lower_left_attack = evaluate_attack_far_post_goal(
        player_pos=(21.0, 48.0),
        anchor_pos=(19.0, 46.0),
        ball_pos=(17.0, 10.0),
        attacking_right=False,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
        tick=96,
    )

    assert right_attack is not None
    assert left_attack is not None
    assert lower_right_attack is not None
    assert lower_left_attack is not None
    assert right_attack.target_pos[0] > 90.0
    assert left_attack.target_pos[0] < 15.0
    assert abs(right_attack.target_pos[1] - left_attack.target_pos[1]) < 0.01
    assert abs(lower_right_attack.target_pos[1] - lower_left_attack.target_pos[1]) < 0.01
    assert right_attack.target_pos[1] < 34.0
    assert lower_right_attack.target_pos[1] > 34.0


def test_attack_far_post_goal_absent_when_ball_is_not_wide():
    goal = evaluate_attack_far_post_goal(
        player_pos=(84.0, 20.0),
        anchor_pos=(86.0, 22.0),
        ball_pos=(88.0, 35.0),
        attacking_right=True,
        pitch_length=105.0,
        pitch_width=68.0,
        goal_width=7.32,
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
        goal_width=7.32,
        tick=96,
    )

    assert goal is not None
    assert goal.value < 0.01
