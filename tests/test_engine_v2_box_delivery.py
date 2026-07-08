from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.goal import PlayerGoal
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.value_model import evaluate_pass_target, pass_receive_value, state_value
from psl_core.engine_v2.physics import distance


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _player(index: int, position: str, x: float, y: float, attacking: bool = True) -> Player:
    abilities = {key: 72 for key in ABILITY_KEYS}
    abilities.update({
        "Finishing": 80,
        "Heading": 82,
        "Short_Passing": 78,
        "Long_Passing": 74,
        "Dribbling": 80,
        "Speed": 80,
        "IQ": 80,
        "Long_Shot": 76,
    })
    if not attacking:
        abilities.update({"Tackling": 76, "Defence": 78, "Speed": 74})
    player = Player(
        index=index,
        name=f"{position}{index}",
        position=position,
        color="gold",
        overall=76,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    player.tactical_anchor = (x, y)
    return player


def _wide_delivery_context():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 88.0, 12.0)
    striker = _player(9, "ST", 86.0, 30.0)
    striker.target_pos = (90.0, 34.0)
    striker.tactical_anchor = (90.0, 34.0)
    midfielder = _player(6, "CM", 78.0, 31.0)
    midfielder.target_pos = (82.0, 31.0)
    midfielder.tactical_anchor = (82.0, 31.0)
    winger = _player(10, "LW", 86.0, 52.0)
    winger.target_pos = (88.0, 50.0)
    winger.tactical_anchor = (88.0, 50.0)
    fullback = _player(4, "RB", 78.0, 8.0)
    fullback.target_pos = (77.0, 8.0)
    fullback.tactical_anchor = (77.0, 8.0)
    teammates = [carrier, striker, midfielder, winger, fullback]
    opponents = [
        _player(1, "LB", 84.0, 16.0, attacking=False),
        _player(2, "CB", 89.0, 28.0, attacking=False),
        _player(3, "CB", 91.0, 39.0, attacking=False),
        _player(4, "RB", 84.0, 50.0, attacking=False),
        _player(5, "DM", 80.0, 34.0, attacking=False),
    ]
    return config, pitch, carrier, striker, teammates, opponents


def test_high_threat_box_pass_can_pay_for_risk():
    config, pitch, carrier, striker, teammates, opponents = _wide_delivery_context()
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    target = (89.0, 34.0)
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    value = evaluate_pass_target(
        carrier, striker, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=1.0,
        continuity=0.045,
    )

    assert value.score > 0.05
    assert value.components["high_threat_space"] > 0.5
    assert value.components["risk_budget"] > 0.04


def test_wide_carrier_can_choose_positive_safe_outlet_when_box_lane_is_closed():
    config, pitch, carrier, _, teammates, opponents = _wide_delivery_context()
    carrier.facing_direction = 90.0
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    candidates = carrier._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        True,
        [opp.pos for opp in opponents],
        [tm.pos for tm in teammates if tm.index != carrier.index],
        current_value,
    )

    positive_candidates = [item for item in candidates if item[0] > 0.0]

    assert positive_candidates
    best_score, action_type, best_details = max(positive_candidates, key=lambda item: item[0])
    assert action_type == "pass"
    assert best_score > 0.02
    assert best_details["components"]["delta"] > 0.0
    assert best_details["success_prob"] < 0.95


def test_pass_candidate_penalizes_target_defender_can_reach_first():
    config, pitch, carrier, striker, teammates, opponents = _wide_delivery_context()
    carrier.pos = (70.0, 34.0)
    striker.pos = (84.0, 34.0)
    striker.target_pos = striker.pos
    striker.tactical_anchor = striker.pos
    for idx, opponent in enumerate(opponents):
        opponent.pos = (94.0 + idx, 8.0 + idx * 10.0)

    def striker_options():
        current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
        options = carrier._score_pass_point_options(
            teammates,
            opponents,
            config,
            pitch,
            True,
            [opp.pos for opp in opponents],
            [tm.pos for tm in teammates if tm.index != carrier.index],
            current_value,
        )
        return [
            (score, details)
            for score, _, details in options
            if details.get("target_player_idx") == striker.index
            or details.get("intended_receiver") == striker.index
        ]

    safe_options = striker_options()
    assert safe_options
    safe_best = max(score for score, _ in safe_options)

    opponents[1].pos = (82.0, 34.0)
    risky_options = striker_options()
    risky_best = max((score for score, _ in risky_options), default=0.0)

    assert risky_best < safe_best * 0.75
    if risky_options:
        _, details = min(
            risky_options,
            key=lambda item: item[1]["components"].get("arrival_margin", 99.0),
        )
        assert details["components"]["arrival_margin"] < safe_options[0][1]["components"]["arrival_margin"]
        assert details["components"]["target_occupation_risk"] > 0.0

def test_final_third_wide_receiver_has_creation_value():
    config, pitch, carrier, striker, teammates, opponents = _wide_delivery_context()
    passer = _player(6, "CM", 75.0, 34.0)
    carrier.pos = (84.0, 54.0)
    carrier.target_pos = (88.0, 50.0)
    carrier.tactical_anchor = carrier.target_pos
    teammates = [passer, carrier, striker]
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, True)
    target = carrier.pos
    pass_dist = distance(passer.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * passer.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    value = evaluate_pass_target(
        passer, carrier, passer.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=1.0,
        continuity=0.045,
    )

    assert value.components["wide_creation_space"] > 0.0
    assert value.components["wide_creation_value"] > 0.0
    assert value.risk_cost > 0.0


def test_current_shot_window_adds_cost_to_low_gain_release_pass():
    config, pitch, carrier, striker, teammates, opponents = _wide_delivery_context()
    carrier.pos = (90.0, 30.0)
    carrier.target_pos = carrier.pos
    striker.pos = (84.0, 34.0)
    striker.target_pos = striker.pos
    striker.tactical_anchor = striker.pos
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    target = striker.pos
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    value = evaluate_pass_target(
        carrier, striker, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=1.0,
        continuity=0.045,
    )

    assert value.components["current_shot_window"] > 0.0
    assert value.components["shoot_window_release_cost"] > 0.0


def test_second_line_receive_value_recognizes_low_pressure_arc_arrival():
    config = EngineConfig()
    pitch = Pitch(config=config)
    receiver = _player(6, "CM", 75.0, 34.0)
    receiver.base_formation_pos = (52.0, 34.0)
    receiver.tactical_anchor = (80.0, 34.0)
    striker = _player(9, "ST", 91.0, 34.0)
    wide = _player(7, "LM", 84.0, 18.0)
    teammates = [receiver, striker, wide]
    opponents = [
        _player(2, "CB", 91.0, 29.0, attacking=False),
        _player(3, "CB", 91.0, 39.0, attacking=False),
        _player(4, "DM", 76.0, 34.0, attacking=False),
    ]

    deep_value = pass_receive_value((74.0, 34.0), receiver, teammates, opponents, config, pitch, True)
    arc_value = pass_receive_value((83.0, 34.0), receiver, teammates, opponents, config, pitch, True)

    assert arc_value > deep_value + 0.02


def test_front_line_pass_sampler_sees_second_line_arc_space():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _player(9, "ST", 80.0, 34.0)
    carrier.facing_direction = 180.0
    midfielder = _player(6, "CM", 70.0, 34.0)
    midfielder.base_formation_pos = (52.0, 34.0)
    midfielder.tactical_anchor = (80.0, 34.0)
    midfielder.target_pos = (78.0, 34.0)
    winger = _player(7, "LM", 78.0, 18.0)
    teammates = [carrier, midfielder, winger]
    opponents = [
        _player(2, "CB", 90.0, 29.0, attacking=False),
        _player(3, "CB", 90.0, 39.0, attacking=False),
        _player(4, "DM", 76.0, 25.0, attacking=False),
    ]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    options = carrier._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        True,
        [(p.pos[0], p.pos[1]) for p in opponents],
        [(p.pos[0], p.pos[1]) for p in teammates if p.index != carrier.index],
        current_value,
    )

    cm_options = [
        details
        for _, _, details in options
        if details.get("target_player_idx") == midfielder.index
        or details.get("intended_receiver") == midfielder.index
    ]

    assert any(
        details["components"].get("second_line_arc_candidate", 0.0) > 0.0
        and 0.70 <= details["components"].get("target_progress", 0.0) <= 0.82
        and details["components"].get("centrality", 0.0) > 0.75
        for details in cm_options
    )


def test_receiver_arc_goal_increases_second_line_pass_value():
    config, pitch, carrier, _, teammates, opponents = _wide_delivery_context()
    midfielder = next(player for player in teammates if player.position == "CM")
    target = (80.0, 34.0)
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    without_goal = evaluate_pass_target(
        carrier, midfielder, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.9,
        continuity=0.045,
    )
    midfielder.current_goal = PlayerGoal(
        goal_type="arc_arrival_for_cutback",
        target_pos=target,
        value=0.26,
        context={"phase": "arrive"},
    )
    with_goal = evaluate_pass_target(
        carrier, midfielder, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.9,
        continuity=0.045,
    )

    assert with_goal.components["receiver_goal_arrival_value"] > 0.0
    assert with_goal.score > without_goal.score


def test_far_post_goal_increases_box_delivery_value():
    config, pitch, carrier, _, teammates, opponents = _wide_delivery_context()
    weak_side_runner = next(player for player in teammates if player.position == "LW")
    target = (96.5, 30.8)
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.long_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Long_Passing"] / 100.0
    ) * dist_factor

    without_goal = evaluate_pass_target(
        carrier, weak_side_runner, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.72,
        continuity=0.045,
    )
    weak_side_runner.current_goal = PlayerGoal(
        goal_type="attack_far_post",
        target_pos=target,
        value=0.30,
        context={"phase": "arrive"},
    )
    with_goal = evaluate_pass_target(
        carrier, weak_side_runner, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.72,
        continuity=0.045,
    )

    assert with_goal.components["receiver_goal_arrival_value"] > 0.0
    assert with_goal.score > without_goal.score
