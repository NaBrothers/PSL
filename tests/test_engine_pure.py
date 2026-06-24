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

    assert len(result.events) > 50
    for ev in result.events:
        assert isinstance(ev, MatchEvent)
        assert ev.event_type != ""
        assert ev.seq > 0

    total_goals = result.home_stats.point + result.away_stats.point
    assert len(result.timeline) == total_goals
    for goal in result.timeline:
        assert isinstance(goal, GoalRecord)
        assert goal.team_side in ("home", "away")
        assert goal.scorer_name != ""


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
