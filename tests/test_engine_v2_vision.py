from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.pitch import Pitch
from psl_core.engine_v2.player import Player
from psl_core.engine_v2.value_model import state_value
from psl_core.engine_v2.vision import build_vision_context, compute_fov, compute_vision_distance


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _player(index: int, position: str, x: float, y: float, iq: int = 80) -> Player:
    abilities = {key: 72 for key in ABILITY_KEYS}
    abilities.update({
        "Short_Passing": 78,
        "Long_Passing": 76,
        "Dribbling": 78,
        "Speed": 78,
        "IQ": iq,
    })
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


def test_vision_context_uses_facing_fov_and_distance():
    config = EngineConfig()
    low_iq = _player(6, "CM", 50.0, 34.0, iq=70)
    high_iq = _player(8, "CM", 50.0, 34.0, iq=120)

    assert compute_fov(low_iq.iq_value, config) < compute_fov(high_iq.iq_value, config)
    assert compute_vision_distance(low_iq.iq_value, config) < compute_vision_distance(high_iq.iq_value, config)

    low_iq.facing_direction = 0.0
    vision = build_vision_context(low_iq, config, attacking_right=True)

    assert vision.confidence(low_iq.pos, (70.0, 34.0)) > 0.8
    assert vision.confidence(low_iq.pos, (30.0, 34.0)) == 0.0


def test_pass_candidates_include_vision_components():
    config = EngineConfig()
    pitch = Pitch(config=config)
    passer = _player(6, "CM", 50.0, 34.0, iq=90)
    passer.facing_direction = 0.0
    forward = _player(9, "ST", 70.0, 34.0, iq=80)
    backward = _player(4, "CB", 34.0, 34.0, iq=80)
    teammates = [passer, forward, backward]
    opponents = [
        _player(2, "CB", 82.0, 29.0, iq=80),
        _player(3, "CB", 82.0, 39.0, iq=80),
    ]
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, True)

    options = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        True,
        [opp.pos for opp in opponents],
        [tm.pos for tm in teammates if tm.index != passer.index],
        current_value,
    )

    forward_options = [
        details for _, _, details in options
        if details.get("target_player_idx") == forward.index
        or details.get("intended_receiver") == forward.index
    ]
    backward_options = [
        details for _, _, details in options
        if details.get("target_player_idx") == backward.index
        or details.get("intended_receiver") == backward.index
    ]

    assert forward_options
    assert max(d["components"]["vision_target_confidence"] for d in forward_options) > 0.8
    assert not any(d["components"]["target_kind"] == "space" for d in backward_options)
    if backward_options:
        assert any(d["components"]["target_kind"] == "feet" for d in backward_options)
        assert max(d["components"]["vision_target_confidence"] for d in backward_options) == 0.0
    assert all("vision_fov" in d["components"] for d in forward_options + backward_options)


def test_visible_tactical_space_can_create_pass_without_receiver_visibility():
    config = EngineConfig()
    pitch = Pitch(config=config)
    passer = _player(8, "RW", 92.0, 10.0, iq=90)
    passer.facing_direction = 50.0
    striker = _player(9, "ST", 76.0, 8.0, iq=80)
    striker.target_pos = (82.0, 18.0)
    striker.tactical_anchor = (88.0, 32.0)
    midfielder = _player(6, "CM", 76.0, 24.0, iq=80)
    midfielder.target_pos = (82.0, 22.0)
    midfielder.tactical_anchor = (82.0, 34.0)
    teammates = [passer, striker, midfielder]
    opponents = [
        _player(2, "CB", 90.0, 29.0, iq=80),
        _player(3, "CB", 92.0, 39.0, iq=80),
    ]
    current_value = state_value(passer.pos, passer, teammates, opponents, config, pitch, True)

    options = passer._score_pass_point_options(
        teammates,
        opponents,
        config,
        pitch,
        True,
        [opp.pos for opp in opponents],
        [tm.pos for tm in teammates if tm.index != passer.index],
        current_value,
    )

    tactical_options = [
        details for _, _, details in options
        if details["components"].get("tactical_space")
    ]

    assert tactical_options
    assert any(
        details["components"]["vision_receiver_confidence"]
        < details["components"]["tactical_space_visibility"]
        and details["components"]["tactical_space_visibility"] > 0.35
        and details["components"]["expected_arrival_confidence"] > 0.20
        and details["components"]["tactical_space_pattern"] == "value_field_space"
        for details in tactical_options
    )
