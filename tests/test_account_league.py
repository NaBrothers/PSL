import asyncio

import pytest


class Sender:
    def __init__(self, user_id, nickname):
        self.user_id = user_id
        self.nickname = nickname


class Event:
    def __init__(self, user_id, nickname):
        self.sender = Sender(user_id, nickname)


class CaptureMatcher:
    def __init__(self):
        self.sent = []

    async def send(self, message=None, **kwargs):
        self.sent.append((message, kwargs))


def test_check_account_creates_user_award_and_replays_offline(core_modules):
    asyncio.run(_test_check_account_creates_user_award_and_replays_offline(core_modules))


async def _test_check_account_creates_user_award_and_replays_offline(core_modules):
    User = core_modules["model.user"].User
    Item = core_modules["model.item"].Item
    Offline = core_modules["model.offline"].Offline
    account = core_modules["kernel.account"]

    matcher = CaptureMatcher()
    event = Event(30001, "first'user")
    user = await account.check_account(matcher, event)

    assert user.qq == 30001
    assert user.name == "first'user"
    assert len(matcher.sent) == 2
    items = Item.getItemsByQQandType(user.qq, 0)
    assert len(items.entries) == 1
    assert items.entries[0].name == "新手"

    Offline.send(user, "welcome back")
    matcher = CaptureMatcher()
    existing = await account.check_account(matcher, event)
    assert existing.qq == user.qq
    assert len(matcher.sent) == 1
    assert "welcome back" in str(matcher.sent[0][0])
    assert Offline.get(user) == []


def test_generate_schedule_round_robin_with_bye(core_modules, make_user):
    League = core_modules["model.league"].League
    Schedule = core_modules["model.schedule"].Schedule
    Global = core_modules["model.globalAttr"].Global
    league_kernel = __import__("kernel.league", fromlist=["generate_schedule"])

    users = [make_user(31000 + i, f"league{i}", money=0) for i in range(3)]
    for user in users:
        League.addUser(user.qq)
    League.addUser(0)
    Global.set("league_repeat", 1)

    league_kernel.generate_schedule()
    schedule = Schedule.getSchedule()
    assert schedule is not None
    assert schedule.getNumOfRounds() == 6
    assert len(schedule.entries) == 12

    real_games = [e for e in schedule.entries if e.home is not None and e.away is not None]
    byes = [e for e in schedule.entries if e.home is None or e.away is None]
    assert len(real_games) == 6
    assert len(byes) == 6
    assert all(e.finished == 0 for e in real_games)
    assert all(e.finished == 1 for e in byes)
