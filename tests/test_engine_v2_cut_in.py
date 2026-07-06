from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.value_model import state_value


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _player(index: int, position: str, x: float, y: float) -> Player:
    abilities = {key: 72 for key in ABILITY_KEYS}
    abilities.update({
        "Finishing": 80,
        "Long_Shot": 82,
        "Dribbling": 82,
        "Short_Passing": 74,
        "Long_Passing": 72,
        "Speed": 82,
        "IQ": 78,
    })
    if position in ("LB", "RB", "CB"):
        abilities.update({"Tackling": 74, "Defence": 76, "Speed": 72})
    player = Player(
        index=index,
        name=f"P{index}",
        position=position,
        color="gold",
        overall=75,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    player.tactical_anchor = (x, y)
    return player


def _wide_attack_context():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 72.0, 9.0)
    teammates = [
        carrier,
        _player(9, "ST", 86.0, 34.0),
        _player(10, "LW", 82.0, 54.0),
        _player(6, "CM", 66.0, 34.0),
    ]
    opponents = [
        _player(1, "LB", 76.0, 4.0),
        _player(2, "CB", 86.0, 30.0),
        _player(3, "CB", 88.0, 38.0),
        _player(4, "RB", 84.0, 47.0),
    ]
    return config, pitch, carrier, teammates, opponents


def test_wide_advanced_carrier_can_discover_cut_inside_carry():
    config, pitch, carrier, teammates, opponents = _wide_attack_context()
    opp_positions = [opp.pos for opp in opponents]
    tm_positions = [tm.pos for tm in teammates if tm.index != carrier.index]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)

    candidates = carrier._score_carry_options(
        config, pitch, True, opponents, opp_positions, tm_positions, teammates, current_value
    )
    score, _, details = max(candidates, key=lambda item: item[0])
    target = details["target"]
    components = details["components"]

    assert score > 0.05
    assert target[0] > carrier.pos[0] + 3.0
    assert target[1] > carrier.pos[1] + 3.5
    assert components["lane_gain"] > 0.10
    assert components["future_shot_gain"] > 0.01


def test_cut_inside_shooting_lane_can_prefer_shot_over_extra_touch():
    config, pitch, _, teammates, opponents = _wide_attack_context()
    carrier = teammates[0]
    carrier.pos = (90.0, 30.0)
    carrier.target_pos = carrier.pos
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    opp_positions = [opp.pos for opp in opponents]
    tm_positions = [tm.pos for tm in teammates if tm.index != carrier.index]

    carry_candidates = carrier._score_carry_options(
        config, pitch, True, opponents, opp_positions, tm_positions, teammates, current_value
    )
    best_carry = max(score for score, _, _ in carry_candidates)
    goal = (config.pitch_length, config.pitch_width / 2.0)
    dist_to_goal = ((goal[0] - carrier.pos[0]) ** 2 + (goal[1] - carrier.pos[1]) ** 2) ** 0.5
    shoot_score, shoot_details = carrier._score_shoot(
        goal, config, pitch, opponents, dist_to_goal, current_value
    )

    assert shoot_details["xg"] > 0.08
    assert shoot_score > best_carry


def test_half_width_final_third_carrier_samples_inside_lane_without_false_path_crush():
    config, pitch, carrier, teammates, opponents = _wide_attack_context()
    carrier.pos = (76.0, 22.0)
    carrier.target_pos = carrier.pos
    opp_positions = [opp.pos for opp in opponents]
    tm_positions = [tm.pos for tm in teammates if tm.index != carrier.index]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)

    candidates = carrier._score_carry_options(
        config, pitch, True, opponents, opp_positions, tm_positions, teammates, current_value
    )
    inside_candidates = [
        (score, details)
        for score, _, details in candidates
        if details["target"][0] > carrier.pos[0] + 1.0
        and abs(details["target"][1] - pitch.width / 2.0) < abs(carrier.pos[1] - pitch.width / 2.0)
    ]
    _, details = max(
        inside_candidates,
        key=lambda item: item[1]["components"]["half_space_entry"],
    )

    assert details["target"][0] / pitch.length > 0.72
    assert abs(details["target"][1] - pitch.width / 2.0) / (pitch.width / 2.0) < 0.32
    assert details["success_prob"] > 0.45
    assert details["components"]["half_space_entry"] > 0.01


def test_first_inside_touch_from_wide_second_line_gets_continuation_value():
    config, pitch, carrier, teammates, opponents = _wide_attack_context()
    carrier.position = "LM"
    carrier.pos = (78.0, 56.0)
    carrier.target_pos = carrier.pos
    carrier.consecutive_carries = 0
    opp_positions = [opp.pos for opp in opponents]
    tm_positions = [tm.pos for tm in teammates if tm.index != carrier.index]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)

    candidates = carrier._score_carry_options(
        config, pitch, True, opponents, opp_positions, tm_positions, teammates, current_value
    )
    inside_candidates = [
        details
        for _, _, details in candidates
        if details["target"][0] > carrier.pos[0] + 2.0
        and abs(details["target"][1] - pitch.width / 2.0) < abs(carrier.pos[1] - pitch.width / 2.0)
    ]
    best_inside = max(
        inside_candidates,
        key=lambda details: details["components"]["future_shot_gain"],
    )

    assert best_inside["components"]["wide_second_line_carry_window"] > 0.0
    assert best_inside["components"]["future_shot_gain"] > 0.04
    assert best_inside["components"]["carry_to_shoot_window"] > 0.0
