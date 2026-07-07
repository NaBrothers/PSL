from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.value_model import evaluate_pass_target, state_value
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
        "Heading": 84,
        "Short_Passing": 80,
        "Long_Passing": 76,
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
        overall=78,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    player.formation_pos = (x, y)
    player.base_formation_pos = (x, y)
    player.tactical_anchor = (x, y)
    return player


def _byline_context():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _player(8, "RW", 96.0, 9.0)
    striker = _player(9, "ST", 91.0, 34.0)
    striker.target_pos = (92.0, 34.0)
    striker.tactical_anchor = (92.0, 34.0)
    midfielder = _player(6, "CM", 82.0, 30.0)
    midfielder.target_pos = (84.0, 30.0)
    midfielder.tactical_anchor = (84.0, 30.0)
    far_winger = _player(10, "LW", 90.0, 48.0)
    far_winger.target_pos = (90.0, 45.0)
    far_winger.tactical_anchor = (90.0, 45.0)
    fullback = _player(4, "RB", 78.0, 8.0)
    fullback.target_pos = (77.0, 8.0)
    fullback.tactical_anchor = (77.0, 8.0)
    teammates = [carrier, striker, midfielder, far_winger, fullback]
    opponents = [
        _player(1, "LB", 88.0, 17.0, attacking=False),
        _player(2, "CB", 91.0, 29.0, attacking=False),
        _player(3, "CB", 93.0, 38.0, attacking=False),
        _player(4, "RB", 87.0, 50.0, attacking=False),
        _player(5, "DM", 82.0, 34.0, attacking=False),
    ]
    return config, pitch, carrier, teammates, opponents


def test_byline_carrier_prefers_box_delivery_over_extra_touch():
    config, pitch, carrier, teammates, opponents = _byline_context()
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    opp_positions = [opp.pos for opp in opponents]
    tm_positions = [tm.pos for tm in teammates if tm.index != carrier.index]
    passes = carrier._score_pass_point_options(
        teammates, opponents, config, pitch, True, opp_positions, tm_positions, current_value
    )
    carries = carrier._score_carry_options(
        config, pitch, True, opponents, opp_positions, tm_positions, teammates, current_value
    )

    best_pass = max(passes, key=lambda item: item[0])
    best_box_pass = max(
        (
            item for item in passes
            if item[2]["target"][0] / pitch.length > 1.0 - 16.5 / pitch.length
            and abs(item[2]["target"][1] - pitch.width / 2.0) < 20.2
        ),
        key=lambda item: item[0],
    )
    best_carry = max(carries, key=lambda item: item[0])
    target = best_box_pass[2]["target"]
    target_progress = target[0] / pitch.length
    target_in_box = (
        target_progress > 1.0 - 16.5 / pitch.length
        and abs(target[1] - pitch.width / 2.0) < 20.2
    )

    assert best_box_pass[0] > best_carry[0] * 0.90
    assert best_box_pass[1] == "pass"
    assert target_in_box
    assert best_box_pass[2]["success_prob"] > 0.20
    assert best_box_pass[2]["components"]["final_third_combination"] > 0.7


def test_low_success_box_delivery_keeps_some_risk_cost():
    config, pitch, carrier, teammates, opponents = _byline_context()
    striker = teammates[1]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    target = (101.0, 34.0)
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    value = evaluate_pass_target(
        carrier, striker, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.20,
        continuity=0.045,
    )

    assert value.success_prob < 0.15
    assert value.components["high_threat_space"] > 0.8
    assert value.components["risk_budget"] > 0.0
    assert value.risk_cost > 0.0


def test_wide_carrier_values_second_line_cutback_window():
    config = EngineConfig()
    pitch = Pitch(config=config)
    carrier = _player(8, "RM", 78.0, 58.0)
    midfielder = _player(6, "CM", 75.0, 34.0)
    midfielder.base_formation_pos = (52.0, 34.0)
    midfielder.tactical_anchor = (80.0, 34.0)
    striker = _player(9, "ST", 88.0, 34.0)
    teammates = [carrier, midfielder, striker]
    opponents = [
        _player(2, "CB", 89.0, 29.0, attacking=False),
        _player(3, "CB", 89.0, 39.0, attacking=False),
        _player(5, "DM", 75.0, 24.0, attacking=False),
    ]
    current_value = state_value(carrier.pos, carrier, teammates, opponents, config, pitch, True)
    target = (80.0, 34.0)
    pass_dist = distance(carrier.pos, target)
    dist_factor = max(0.35, 1.0 - max(0.0, pass_dist - 10.0) / 65.0)
    base_accuracy = config.short_pass_base_success * (
        0.35 + 0.65 * carrier.abilities["Short_Passing"] / 100.0
    ) * dist_factor

    value = evaluate_pass_target(
        carrier, midfielder, carrier.pos, target,
        teammates, opponents, config, pitch, True,
        current_value, base_accuracy,
        receiver_arrival=0.82,
        continuity=0.045,
    )

    assert value.components["second_line_cutback_space"] > 0.35
    assert value.components["second_line_cutback_value"] > 0.03
    assert value.score > 0.04
