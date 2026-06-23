import asyncio
import pytest

from conftest import FinishException


def add_card(mods, user, player_id, star=1):
    Player = mods["model.player"].Player
    Card = mods["model.card"].Card
    Bag = mods["model.bag"].Bag
    player = Player.getPlayerByID(player_id)
    assert player is not None
    return Bag.addToBag(user, Card.new(player, user, star=star))


def patch_finish(monkeypatch, matcher):
    async def finish(message=None, **kwargs):
        raise FinishException(message, kwargs)

    monkeypatch.setattr(matcher, "finish", finish)


def build_full_squad(mods, user, star=3):
    player_ids = [200389, 212622, 203376, 155862, 216267, 189596, 192985, 215914, 200104, 158023, 188545]
    for player_id in player_ids:
        add_card(mods, user, player_id, star=star)
    return player_ids


def test_lottery_single_ten_and_newbee_award(core_modules, make_user, monkeypatch):
    asyncio.run(_test_lottery_single_ten_and_newbee_award(core_modules, make_user, monkeypatch))


async def _test_lottery_single_ten_and_newbee_award(core_modules, make_user, monkeypatch):
    User = core_modules["model.user"].User
    Bag = core_modules["model.bag"].Bag
    Item = core_modules["model.item"].Item
    lottery = core_modules["kernel.lottery"]
    patch_finish(monkeypatch, lottery.try_lottery)

    user = make_user(20001, "lottery", money=100000)
    before_money = user.money

    with pytest.raises(FinishException) as single:
        await lottery.try_single(user, "初级")
    user = User.getUserByQQ(user.qq)
    bag = Bag.getBag(user)
    assert len(bag.cards) == 1
    assert user.money == before_money - lottery.g_pool["初级"]["cost"]
    assert "[CQ:image" in str(single.value.message)

    with pytest.raises(FinishException):
        await lottery.try_ten(user, "初级")
    user = User.getUserByQQ(user.qq)
    bag = Bag.getBag(user)
    assert len(bag.cards) == 11
    assert user.money == before_money - lottery.g_pool["初级"]["cost"] - lottery.g_pool["初级"]["ten_cost"]

    Item.addItem(user, 0, 0, 1)
    with pytest.raises(FinishException):
        await lottery.try_award(user, "新手")
    user = User.getUserByQQ(user.qq)
    bag = Bag.getBag(user)
    assert len(bag.cards) == 31
    assert Item.getItemsByQQandType(user.qq, 0) is None
    assert any(card.player.Overall > 88 for card in bag.cards)


def test_recycle_upgrade_breach_and_lock_flows(core_modules, make_user, monkeypatch):
    asyncio.run(_test_recycle_upgrade_breach_and_lock_flows(core_modules, make_user, monkeypatch))


async def _test_recycle_upgrade_breach_and_lock_flows(core_modules, make_user, monkeypatch):
    User = core_modules["model.user"].User
    Card = core_modules["model.card"].Card
    Bag = core_modules["model.bag"].Bag
    bag_kernel = core_modules["kernel.bag"]
    player_kernel = core_modules["kernel.player"]
    patch_finish(monkeypatch, player_kernel.player_menu)
    patch_finish(monkeypatch, bag_kernel.user_bag)

    user = make_user(20002, "cards", money=1000000)
    card1 = add_card(core_modules, user, 158023, star=1)
    card2 = add_card(core_modules, user, 158023, star=1)
    card3 = add_card(core_modules, user, 158023, star=2)
    recycle_card = add_card(core_modules, user, 190871, star=1)

    with pytest.raises(FinishException) as locked:
        await player_kernel.player_lock(str(recycle_card))
    assert "锁定" in str(locked.value.message)
    assert Card.getCardByID(recycle_card).locked in (1, True, "True")

    with pytest.raises(FinishException):
        await player_kernel.player_upgrade(user, str(card1), str(card2))
    upgraded = Card.getCardByID(card1)
    assert upgraded.star == 2
    assert Card.getCardByID(card2) is None
    assert User.getUserByQQ(user.qq).money < 1000000

    with pytest.raises(FinishException):
        await player_kernel.player_breach(User.getUserByQQ(user.qq), str(card1), str(card3))
    breached = Card.getCardByID(card1)
    assert breached.breach >= 2
    assert breached.ext_abilities
    assert Card.getCardByID(card3) is None

    user = User.getUserByQQ(user.qq)
    before = user.money
    with pytest.raises(FinishException):
        await bag_kernel.recycle_cards(user, Bag.getBag(user), [str(recycle_card), str(card1)])
    after = User.getUserByQQ(user.qq)
    assert after.money > before
    assert Card.getCardByID(card1) is None
    assert Card.getCardByID(recycle_card) is not None


def test_transfer_market_buy_sell_and_self_reclaim(core_modules, make_user, monkeypatch):
    asyncio.run(_test_transfer_market_buy_sell_and_self_reclaim(core_modules, make_user, monkeypatch))


async def _test_transfer_market_buy_sell_and_self_reclaim(core_modules, make_user, monkeypatch):
    User = core_modules["model.user"].User
    Card = core_modules["model.card"].Card
    Transfer = core_modules["model.transfer"].Transfer
    Offline = core_modules["model.offline"].Offline
    transfer_kernel = core_modules["kernel.transfer"]
    patch_finish(monkeypatch, transfer_kernel.transfer)

    seller = make_user(20003, "seller", money=0)
    buyer = make_user(20004, "buyer", money=50000)
    card_id = add_card(core_modules, seller, 158023, star=1)

    with pytest.raises(FinishException):
        await transfer_kernel.sell_card(seller, str(card_id), "10000")
    listed = Card.getCardByID(card_id)
    assert listed.status == 1

    cursor = core_modules["utils.database"].g_database.cursor()
    assert cursor.execute("select * from transfer where card = " + str(card_id)) == 1
    transfer = Transfer(cursor.fetchone())
    cursor.close()
    assert transfer.user.qq == seller.qq
    assert transfer.cost == 10000

    with pytest.raises(FinishException):
        await transfer_kernel.buy_card(buyer, str(card_id))
    sold = Card.getCardByID(card_id)
    assert sold.user.qq == buyer.qq
    assert sold.status == 0
    assert User.getUserByQQ(buyer.qq).money == 40000
    assert User.getUserByQQ(seller.qq).money == 10000
    assert Offline.get(seller)

    with pytest.raises(FinishException):
        await transfer_kernel.sell_card(buyer, str(card_id), "9000")
    with pytest.raises(FinishException):
        await transfer_kernel.buy_card(buyer, str(card_id))
    assert Card.getCardByID(card_id).user.qq == buyer.qq
    assert Card.getCardByID(card_id).status == 0


def test_auto_formation_and_silent_match_engine(core_modules, make_user, monkeypatch):
    asyncio.run(_test_auto_formation_and_silent_match_engine(core_modules, make_user, monkeypatch))


async def _test_auto_formation_and_silent_match_engine(core_modules, make_user, monkeypatch):
    Formation = core_modules["model.formation"].Formation
    Card = core_modules["model.card"].Card
    formation_kernel = core_modules["kernel.formation"]
    Game = core_modules["engine.game"].Game
    EngineConst = __import__("engine.const", fromlist=["Const"]).Const

    user1 = make_user(20005, "coach1", money=0)
    user2 = make_user(20006, "coach2", money=0)
    for user in (user1, user2):
        build_full_squad(core_modules, user, star=3)

    async def finish_no_raise(*args, **kwargs):
        return None

    monkeypatch.setattr(formation_kernel.get_team, "finish", finish_no_raise)
    await formation_kernel.auto_update(user1)
    await formation_kernel.auto_update(user2)

    team1 = Formation.getFormation(user1)
    team2 = Formation.getFormation(user2)
    assert team1.isValid()
    assert team2.isValid()
    assert all(card.status == 2 for card in team1.cards if card is not None)

    matcher = core_modules["tests.conftest"].DummyMatcher() if "tests.conftest" in core_modules else None
    if matcher is None:
        from conftest import DummyMatcher
        matcher = DummyMatcher()
    game = Game(matcher, user1, user2)
    stats = await game.start(EngineConst.MODE_SILENCE)
    assert stats is None
    assert game.home.point >= 0
    assert game.away.point >= 0
    assert game.home.shoots >= game.home.shoots_in_target
    assert game.away.shoots >= game.away.shoots_in_target


def test_challenge_award_and_npc_formation(core_modules, make_user, monkeypatch):
    asyncio.run(_test_challenge_award_and_npc_formation(core_modules, make_user, monkeypatch))


async def _test_challenge_award_and_npc_formation(core_modules, make_user, monkeypatch):
    Item = core_modules["model.item"].Item
    User = core_modules["model.user"].User
    NpcFormation = __import__("model.npc_formation", fromlist=["NpcFormation"]).NpcFormation
    challenge = __import__("kernel.challenge", fromlist=["pay_award", "challenge_matcher"])

    patch_finish(monkeypatch, challenge.challenge_matcher)
    user = make_user(20007, "challenger", money=0)
    npc_team = NpcFormation(0, "简单")
    assert npc_team.isValid()
    total, forward, midfield, guard = npc_team.getAbilities()
    assert total > 0
    assert min(forward, midfield, guard) > 0

    with pytest.raises(FinishException):
        await challenge.pay_award(user, "win", "简单", 0)
    user = User.getUserByQQ(user.qq)
    assert user.money == 500
    items = Item.getItemsByQQandType(user.qq, 0)
    assert len(items.entries) == 1
    assert items.entries[0].name == "初级"
    assert items.entries[0].count == 2
