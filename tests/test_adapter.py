"""Test adapter layer."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_bot_adapter_quick_match(core_modules, make_user, monkeypatch):
    from conftest import DummyMatcher
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]
    import adapter.bot_commands as bot_cmds
    monkeypatch.setattr(bot_cmds, "toImage", lambda text: text)

    user1 = make_user(90001, "adapter-home", money=0)
    user2 = make_user(90002, "adapter-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    matcher = DummyMatcher()
    asyncio.run(bot_cmds.handle_match_quick(matcher, user1, user2, seed=42))

    assert len(matcher.sent) == 2
    assert "[比赛战报]" in str(matcher.sent[0][0])
    assert "[数据统计]" in str(matcher.sent[1][0])


def test_web_adapter_serialization(core_modules, make_user, monkeypatch):
    from test_game_flows import build_full_squad

    formation_kernel = core_modules["kernel.formation"]

    user1 = make_user(90011, "web-home", money=0)
    user2 = make_user(90012, "web-away", money=0)
    build_full_squad(core_modules, user1, star=3)
    build_full_squad(core_modules, user2, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    asyncio.run(formation_kernel.auto_update(user1))
    asyncio.run(formation_kernel.auto_update(user2))

    from service.match_service import MatchService
    from adapter.web_api import serialize_match_result

    svc = MatchService()
    output = svc.run_match(user1, user2, seed=42)
    data = serialize_match_result(output.result)

    assert "home" in data
    assert "away" in data
    assert "events" in data
    assert "timeline" in data
    assert data["home"]["name"] != ""
    assert data["away"]["name"] != ""
    assert isinstance(data["home"]["stats"]["xg"], float)
    assert isinstance(data["events"], list)
    assert isinstance(data["timeline"], list)

    total_goals = data["home"]["score"] + data["away"]["score"]
    assert len(data["timeline"]) == total_goals
