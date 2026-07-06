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


def test_final_third_attack_shape_stretches_advanced_line():
    match = MatchV2(_cards(), _cards(), "442", "442", config=EngineConfig())
    static_slots = [p.formation_pos for p in match.home.players]
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)
    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.78, match.pitch.width * 0.50),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    attackers = [p for p in match.home.players if p.position in ("ST", "CF", "LW", "RW", "LM", "RM")]
    midfielders = [p for p in match.home.players if p.position in ("CM", "LCM", "RCM", "CDM", "LDM", "RDM")]
    attacker_progress = max(p.tactical_anchor[0] / match.pitch.length for p in attackers)
    midfield_progress = sum(p.tactical_anchor[0] / match.pitch.length for p in midfielders) / len(midfielders)

    assert [p.formation_pos for p in match.home.players] == static_slots
    assert attacker_progress > 0.73
    assert attacker_progress - midfield_progress > 0.065


def test_final_third_shape_creates_weak_side_and_second_line_arrivals():
    match = MatchV2(_cards(), _cards(), "4141", "433", config=EngineConfig())
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)

    lm = next(p for p in match.home.players if p.position == "LM")
    lcm = next(p for p in match.home.players if p.position == "LCM")
    lm_base_y = lm.tactical_anchor[1]
    lcm_base_x = lcm.tactical_anchor[0]

    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.82, match.pitch.width * 0.78),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    center_y = match.pitch.width / 2.0
    lm_tuck = abs(lm.tactical_anchor[1] - center_y)
    lm_base_width = abs(lm_base_y - center_y)
    lcm_progress = lcm.tactical_anchor[0] / match.pitch.length
    lcm_base_progress = lcm_base_x / match.pitch.length

    assert lm_tuck < lm_base_width
    assert lcm_progress > lcm_base_progress + 0.10
    assert lm.formation_pos == lm.base_formation_pos


def test_wide_midfield_anchor_tucks_into_half_space_near_final_third_entry():
    match = MatchV2(_cards(), _cards(), "4141", "433", config=EngineConfig())
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)
    lm = next(p for p in match.home.players if p.position == "LM")
    lb = next(p for p in match.home.players if p.position == "LB")

    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.72, match.pitch.width * 0.32),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    center_y = match.pitch.width / 2.0
    lm_width = abs(lm.tactical_anchor[1] - center_y) / (match.pitch.width / 2.0)
    lb_width = abs(lb.tactical_anchor[1] - center_y) / (match.pitch.width / 2.0)

    assert lm_width < 0.54
    assert lb_width - lm_width > 0.08


def test_advanced_anchor_keeps_onside_buffer_against_defensive_line():
    match = MatchV2(_cards(), _cards(), "4141", "433", config=EngineConfig())
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)
    striker = next(p for p in match.home.players if p.position == "ST")

    for defender in match.away.players:
        if not defender.is_goalkeeper:
            defender.pos = (84.0, defender.pos[1])

    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.74, match.pitch.width * 0.24),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    assert striker.tactical_anchor[0] < 84.0 - 4.0


def test_attack_shape_keeps_rest_defense_near_opponent_front_line():
    match = MatchV2(_cards(), _cards(), "433", "433", config=EngineConfig())
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)

    # Simulate an opponent forward staying high for a counter while home attacks.
    for player in match.away.players:
        if player.position == "ST":
            player.pos = (match.pitch.length * 0.54, match.pitch.width / 2.0)
        elif not player.is_goalkeeper:
            player.pos = (match.pitch.length * 0.78, player.pos[1])

    match.home.compute_dynamic_positions(
        (match.pitch.length * 0.84, match.pitch.width * 0.70),
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    cover_players = [
        player for player in match.home.players
        if (
            player.base_formation_pos[0] / match.pitch.length < 0.45
            and not player.is_goalkeeper
        )
    ]
    deepest_cover_progress = min(player.tactical_anchor[0] / match.pitch.length for player in cover_players)

    assert deepest_cover_progress < 0.61


def test_off_ball_attack_targets_keep_rest_defense_layer():
    match = MatchV2(_cards(), _cards(), "433", "433", config=EngineConfig())
    match.home.update_phase(has_possession=True, ball_contested=False, config=match.config)
    holder = next(player for player in match.home.players if player.position == "RW")
    ball = (match.pitch.length * 0.84, match.pitch.width * 0.70)
    holder.pos = ball
    holder.target_pos = ball

    for player in match.away.players:
        if player.position == "ST":
            player.pos = (match.pitch.length * 0.54, match.pitch.width / 2.0)
        elif not player.is_goalkeeper:
            player.pos = (match.pitch.length * 0.78, player.pos[1])

    match.home.compute_dynamic_positions(
        ball,
        match.config,
        match.pitch,
        opponent_players=match.away.players,
    )

    cover_targets = []
    for player in match.home.players:
        if (
            player.index == holder.index
            or player.is_goalkeeper
            or player.base_formation_pos[0] / match.pitch.length >= 0.45
        ):
            continue
        target = player.choose_off_ball_attack(
            ball,
            match.config,
            match.pitch,
            match.home.attacking_right,
            ball_carrier=holder,
            opponents=match.away.players,
            teammates=match.home.players,
        )
        cover_targets.append(target[0] / match.pitch.length)

    assert max(cover_targets) < 0.62
    assert sum(cover_targets) / len(cover_targets) < 0.52
