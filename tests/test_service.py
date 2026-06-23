"""Test the match service layer."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_match_service_run(core_modules, make_user, monkeypatch):
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]

    user1 = make_user(80001, "svc-home", money=0)
    user2 = make_user(80002, "svc-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    from service.match_service import MatchService

    svc = MatchService()
    output = svc.run_match(user1, user2, seed=42)

    assert output.result is not None
    assert output.result.home_stats.possessions > 0
    assert "[比赛战报]" in output.report_text
    assert "[终场比分]" in output.stats_text
    assert "[数据统计]" in output.stats_text
    assert "控球率" in output.stats_text
    assert "xG" in output.stats_text


def test_match_service_deterministic(core_modules, make_user, monkeypatch):
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]

    user1 = make_user(80011, "det-home", money=0)
    user2 = make_user(80012, "det-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    from service.match_service import MatchService

    svc = MatchService()
    o1 = svc.run_match(user1, user2, seed=999)
    o2 = svc.run_match(user1, user2, seed=999)

    assert o1.result.home_stats.point == o2.result.home_stats.point
    assert o1.result.away_stats.point == o2.result.away_stats.point
    assert o1.stats_text == o2.stats_text
