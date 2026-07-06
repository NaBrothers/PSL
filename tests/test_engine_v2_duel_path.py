from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.interactions import detect_duel
from psl_core.engine_v2.player import Player


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _player(index: int, position: str, x: float, y: float) -> Player:
    abilities = {key: 80 for key in ABILITY_KEYS}
    player = Player(
        index=index,
        name=f"P{index}",
        position=position,
        color="gold",
        overall=80,
        abilities=abilities,
    )
    player.pos = (x, y)
    player.target_pos = (x, y)
    return player


def test_carry_path_entering_defender_control_triggers_duel():
    config = EngineConfig()
    holder = _player(9, "ST", 80.0, 34.0)
    defender = _player(2, "CB", 86.0, 37.0)
    defender_next = (86.0, 34.5)

    interaction = detect_duel(
        holder,
        "carry",
        [defender],
        {defender.index: "approach"},
        config,
        defender_new_positions={defender.index: defender_next},
        carry_target=(92.0, 34.0),
    )

    assert interaction is not None
    assert interaction.defender is defender
