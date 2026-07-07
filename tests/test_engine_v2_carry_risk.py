from tests.test_engine_v2_final_third_support import _db_cards

from psl_core.engine_v2.config import EngineConfig
from psl_core.engine_v2.match import MatchV2
from psl_core.engine_v2.player import PlayerState
from psl_core.engine_v2.value_model import state_value


def test_box_edge_carry_through_central_defenders_has_risk():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = (88.0, 34.0)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL

    # Put centre-backs close enough to control the central lane without making
    # this a scripted tackle.
    match.away.players[2].pos = (91.0, 31.5)
    match.away.players[3].pos = (91.0, 36.5)
    opp_positions = [opp.pos for opp in match.away.players if not opp.is_goalkeeper]
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    current_value = state_value(holder.pos, holder, match.home.players, match.away.players, match.config, match.pitch, True)

    carries = holder._score_carry_options(
        match.config,
        match.pitch,
        True,
        match.away.players,
        opp_positions,
        teammate_positions,
        match.home.players,
        current_value,
    )
    central_carries = [
        details for _, _, details in carries
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    ]

    assert central_carries
    assert min(details["success_prob"] for details in central_carries) < 0.9


def test_carry_feasibility_reflects_defender_control_range():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(
        player for player in match.home.players
        if player.position in ("RM", "RW", "LM", "LW", "RCM", "LCM", "CM")
    )
    holder.pos = (76.0, 55.8)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL
    defender = match.away.players[4]
    defender.pos = (80.0, 51.0)
    defender.target_pos = defender.pos
    defender.abilities["Speed"] = 82
    defender.abilities["Defence"] = 82
    defender.abilities["Tackling"] = 82
    opp_positions = [opp.pos for opp in match.away.players if not opp.is_goalkeeper]
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    current_value = state_value(holder.pos, holder, match.home.players, match.away.players, match.config, match.pitch, True)

    carries = holder._score_carry_options(
        match.config,
        match.pitch,
        True,
        match.away.players,
        opp_positions,
        teammate_positions,
        match.home.players,
        current_value,
    )
    risky = [
        details for _, _, details in carries
        if details["target"][0] > 80.0 and details["target"][1] < 52.5
    ]

    assert risky
    assert min(details["success_prob"] for details in risky) < 0.55


def test_repeated_final_third_carry_gets_extra_opportunity_cost():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = (88.0, 34.0)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL
    opp_positions = [opp.pos for opp in match.away.players if not opp.is_goalkeeper]
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    current_value = state_value(holder.pos, holder, match.home.players, match.away.players, match.config, match.pitch, True)

    holder.possession_ticks = 1
    holder.consecutive_carries = 0
    fresh = max(
        score for score, _, details in holder._score_carry_options(
            match.config, match.pitch, True, match.away.players,
            opp_positions, teammate_positions, match.home.players, current_value
        )
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    )
    holder.possession_ticks = 7
    holder.consecutive_carries = 4
    stale = max(
        score for score, _, details in holder._score_carry_options(
            match.config, match.pitch, True, match.away.players,
            opp_positions, teammate_positions, match.home.players, current_value
        )
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    )

    assert stale < fresh


def test_nearby_support_increases_repeated_carry_opportunity_cost():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = (88.0, 34.0)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL
    holder.possession_ticks = 7
    holder.consecutive_carries = 4
    support = next(
        player for player in match.home.players
        if player.index != holder.index and player.is_midfielder
    )
    for teammate in match.home.players:
        if teammate.index == holder.index or teammate.index == support.index or teammate.is_goalkeeper:
            continue
        teammate.pos = (35.0, 8.0 + teammate.index)
        teammate.target_pos = teammate.pos
        teammate.tactical_anchor = teammate.pos
    support.pos = (82.0, 39.0)
    support.target_pos = support.pos
    support.tactical_anchor = support.pos
    opp_positions = [opp.pos for opp in match.away.players if not opp.is_goalkeeper]
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    current_value = state_value(holder.pos, holder, match.home.players, match.away.players, match.config, match.pitch, True)

    with_support_candidates = [
        details for _, _, details in holder._score_carry_options(
            match.config, match.pitch, True, match.away.players,
            opp_positions, teammate_positions, match.home.players, current_value
        )
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    ]
    with_support_details = max(
        with_support_candidates,
        key=lambda details: details["components"]["support_nearby"],
    )
    support.pos = (40.0, 10.0)
    support.target_pos = support.pos
    support.tactical_anchor = support.pos
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    no_support_candidates = [
        details for _, _, details in holder._score_carry_options(
            match.config, match.pitch, True, match.away.players,
            opp_positions, teammate_positions, match.home.players, current_value
        )
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    ]
    no_support_details = max(
        no_support_candidates,
        key=lambda details: details["components"]["support_nearby"],
    )

    assert with_support_details["components"]["support_nearby"] > no_support_details["components"]["support_nearby"]
    assert with_support_details["components"]["support_release_cost"] > no_support_details["components"]["support_release_cost"]


def test_front_line_support_can_still_create_repeated_carry_opportunity_cost():
    home_formation, home_cards = _db_cards(10001)
    away_formation, away_cards = _db_cards(10002)
    match = MatchV2(
        home_cards,
        away_cards,
        home_formation,
        away_formation,
        config=EngineConfig(total_ticks=10, half_ticks=5),
    )
    holder = next(player for player in match.home.players if player.name == "K. Mbappé")
    holder.pos = (88.0, 34.0)
    holder.target_pos = holder.pos
    holder.state = PlayerState.ON_BALL
    holder.possession_ticks = 7
    holder.consecutive_carries = 4
    support = next(
        player for player in match.home.players
        if player.index != holder.index and not player.is_goalkeeper
    )
    for teammate in match.home.players:
        if teammate.index == holder.index or teammate.index == support.index or teammate.is_goalkeeper:
            continue
        teammate.pos = (35.0, 8.0 + teammate.index)
        teammate.target_pos = teammate.pos
        teammate.tactical_anchor = teammate.pos
    support.pos = (82.0, 39.0)
    support.target_pos = support.pos
    support.tactical_anchor = support.pos
    support.base_formation_pos = (86.0, 34.0)
    opp_positions = [opp.pos for opp in match.away.players if not opp.is_goalkeeper]
    teammate_positions = [tm.pos for tm in match.home.players if tm.index != holder.index]
    current_value = state_value(holder.pos, holder, match.home.players, match.away.players, match.config, match.pitch, True)

    candidates = [
        details for _, _, details in holder._score_carry_options(
            match.config, match.pitch, True, match.away.players,
            opp_positions, teammate_positions, match.home.players, current_value
        )
        if details["target"][0] > 90.0 and abs(details["target"][1] - match.pitch.width / 2.0) < 4.0
    ]
    details = max(candidates, key=lambda item: item["components"]["support_nearby"])

    assert details["components"]["support_nearby"] > 0.0
    assert details["components"]["support_release_cost"] > 1.0
