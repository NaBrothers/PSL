from psl_core.constants import FORMATION
from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2


ABILITY_KEYS = [
    "Finishing", "Short_Passing", "Long_Passing", "Dribbling",
    "Tackling", "Defence", "Speed", "IQ", "Heading",
    "Long_Shot", "GK_Saving", "GK_Positioning", "GK_Reaction",
]


def _cards():
    positions = FORMATION["442"]["positions"]
    cards = []
    for idx, pos in enumerate(positions):
        abilities = {key: 70 for key in ABILITY_KEYS}
        if pos == "GK":
            abilities.update({
                "GK_Saving": 80,
                "GK_Positioning": 80,
                "GK_Reaction": 80,
            })
        cards.append({
            "name": f"Player {idx}",
            "player_id": idx,
            "position": pos,
            "color": "gold",
            "overall": 70,
            "abilities": abilities,
        })
    return cards


def test_dynamic_shape_does_not_overwrite_static_formation_slots():
    match = MatchV2(_cards(), _cards(), "442", "442", config=EngineConfig())
    player = match.home.players[9]
    static_slot = player.formation_pos
    base_slot = player.base_formation_pos
    initial_anchor = player.tactical_anchor

    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)
    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.85, match.pitch.width * 0.25),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    assert player.formation_pos == static_slot
    assert player.base_formation_pos == base_slot
    assert player.tactical_anchor != initial_anchor


def test_kickoff_setup_keeps_formation_slots_static():
    match = MatchV2(_cards(), _cards(), "442", "442", config=EngineConfig())
    static_slots = [p.formation_pos for p in match.home.players]
    base_slots = [p.base_formation_pos for p in match.home.players]

    match._kickoff("home")

    assert [p.formation_pos for p in match.home.players] == static_slots
    assert [p.base_formation_pos for p in match.home.players] == base_slots
    assert any(p.tactical_anchor != p.formation_pos for p in match.home.players)
