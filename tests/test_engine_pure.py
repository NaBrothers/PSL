"""Test the new run_simulation() pure interface."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_run_simulation_produces_match_result(core_modules, make_user, monkeypatch):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game

    user1 = make_user(70001, "sim-home", money=0)
    user2 = make_user(70002, "sim-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    game = Game(DummyMatcher(), user1, user2, seed=555)
    result = game.run_simulation()

    from engine.types import MatchResult, TeamStats, GoalRecord, MatchEvent

    assert isinstance(result, MatchResult)
    assert isinstance(result.home_stats, TeamStats)
    assert isinstance(result.away_stats, TeamStats)

    assert result.home_stats.name != ""
    assert result.away_stats.name != ""
    assert result.home_stats.possessions > 0
    assert result.away_stats.possessions > 0
    assert result.home_stats.passes > 0
    assert result.home_stats.xg >= 0
    assert isinstance(result.home_stats.player_stats, list)
    assert len(result.home_stats.player_stats) == 11
    assert isinstance(result.home_stats.position_stats, dict)
    assert "GK" in result.home_stats.position_stats
    assert isinstance(result.home_stats.zone_stats, dict)
    assert "final_third_entries" in result.home_stats.zone_stats
    assert result.home_stats.progressive_passes >= 0
    assert result.home_stats.shots_in_box + result.home_stats.shots_outside_box == result.home_stats.shoots

    assert len(result.events) == result.home_stats.point + result.away_stats.point
    for ev in result.events:
        assert isinstance(ev, MatchEvent)
        assert ev.event_type == "goal"
        assert ev.seq > 0

    total_goals = result.home_stats.point + result.away_stats.point
    assert len(result.timeline) == total_goals
    for goal in result.timeline:
        assert isinstance(goal, GoalRecord)
        assert goal.team_side in ("home", "away")
        assert goal.scorer_name != ""

    assert game._rust_replay_data[0]["type"] == "header"
    assert game._rust_match_seed == 555
    assert game.engine_backend == "rust_match_v2"
    assert game.engine_trace_id.startswith("rust-match-v2")
    assert result.replay_path


def test_run_simulation_deterministic(core_modules, make_user, monkeypatch):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game

    user1 = make_user(70011, "det-home", money=0)
    user2 = make_user(70012, "det-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    results = []
    for _ in range(2):
        game = Game(DummyMatcher(), user1, user2, seed=777)
        results.append(game.run_simulation())

    r1, r2 = results
    assert r1.home_stats.point == r2.home_stats.point
    assert r1.away_stats.point == r2.away_stats.point
    assert r1.home_stats.shoots == r2.home_stats.shoots
    assert r1.home_stats.passes == r2.home_stats.passes
    assert round(r1.home_stats.xg, 6) == round(r2.home_stats.xg, 6)
    assert len(r1.events) == len(r2.events)


def test_run_simulation_no_io_side_effects(core_modules, make_user, monkeypatch):
    """run_simulation should not call matcher.send at all."""
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game

    user1 = make_user(70021, "noio-home", money=0)
    user2 = make_user(70022, "noio-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    matcher = DummyMatcher()
    game = Game(matcher, user1, user2, seed=888)
    game.run_simulation()

    assert len(matcher.sent) == 0


def test_rust_player_stats_feed_league_updates(
    core_modules, make_user, monkeypatch, tmp_path
):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    Card = core_modules["model.card"].Card
    Formation = core_modules["model.formation"].Formation
    League = core_modules["model.league"].League
    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game
    league_kernel = __import__("kernel.league", fromlist=["update_stats"])

    home_user = make_user(70031, "league-home", money=0)
    away_user = make_user(70032, "league-away", money=0)
    build_full_squad(core_modules, home_user, star=3)
    build_full_squad(core_modules, away_user, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(home_user))
    asyncio.run(formation_kernel.auto_update(away_user))
    monkeypatch.setenv("PSL_PROJECT_DIR", str(tmp_path))

    home_formation = Formation.getFormation(home_user)
    away_formation = Formation.getFormation(away_user)
    League.addUser(home_user.qq)
    League.addUser(away_user.qq)

    game = Game(DummyMatcher(), home_user, away_user, seed=889)
    game.run_simulation()
    assert game.engine_backend == "rust_match_v2"

    expected_home = [
        (player.goals, player.assists, player.tackles, player.saves)
        for player in game.home.players
    ]
    expected_away = [
        (player.goals, player.assists, player.tackles, player.saves)
        for player in game.away.players
    ]
    assert len(expected_home) == len(expected_away) == 11

    # Presentation may aggregate repeatedly before league persistence.
    game.home.getStats()
    game.away.getStats()
    game.home.getStats()
    game.away.getStats()
    assert [
        (player.goals, player.assists, player.tackles, player.saves)
        for player in game.home.players
    ] == expected_home
    assert [
        (player.goals, player.assists, player.tackles, player.saves)
        for player in game.away.players
    ] == expected_away

    league_kernel.update_stats(game, home_formation, away_formation)

    for formation, expected in (
        (home_formation, expected_home),
        (away_formation, expected_away),
    ):
        for original_card, player_totals in zip(formation.cards[:11], expected):
            card = Card.getCardByID(original_card.id)
            goals, assists, tackles, saves = player_totals
            assert card.appearance == 1
            assert card.goal == goals
            assert card.assist == assists
            assert card.tackle == tackles
            assert card.save == saves
            assert card.total_appearance == 1
            assert card.total_goal == goals
            assert card.total_assist == assists
            assert card.total_tackle == tackles
            assert card.total_save == saves

    home_entry = League.getLeagueEntryByQQ(home_user.qq)
    away_entry = League.getLeagueEntryByQQ(away_user.qq)
    assert home_entry.appearance == away_entry.appearance == 1
    assert home_entry.goal == game.home.goals
    assert away_entry.goal == game.away.goals
    assert home_entry.lost_goal == game.away.goals
    assert away_entry.lost_goal == game.home.goals
