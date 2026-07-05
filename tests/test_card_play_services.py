import json
import os
import random

import pytest


def _server_db():
    import server.database
    server.database.db = server.database.Database(os.environ["PSL_DB_PATH"])
    return server.database.db


def _add_card(mods, user, player_id, star=1):
    Player = mods["model.player"].Player
    Card = mods["model.card"].Card
    Bag = mods["model.bag"].Bag
    player = Player.getPlayerByID(player_id)
    assert player is not None
    return Bag.addToBag(user, Card.new(player, user, star=star))


def test_player_ops_rejects_same_locked_and_busy_sub_cards(core_modules, make_user):
    from server.services.player_ops import PlayerOpsError, PlayerOpsService

    Card = core_modules["model.card"].Card
    user = make_user(21001, "ops", money=1000000)
    main_id = _add_card(core_modules, user, 158023, star=1)
    locked_sub_id = _add_card(core_modules, user, 158023, star=1)
    busy_sub_id = _add_card(core_modules, user, 158023, star=1)
    main = Card.getCardByID(main_id)
    locked_sub = Card.getCardByID(locked_sub_id)
    busy_sub = Card.getCardByID(busy_sub_id)
    locked_sub.set("locked", True)
    busy_sub.set("status", 1)

    svc = PlayerOpsService(_server_db())

    with pytest.raises(PlayerOpsError, match="different"):
        svc.upgrade(user.qq, main_id, main_id)
    with pytest.raises(PlayerOpsError, match="locked"):
        svc.upgrade(user.qq, main_id, locked_sub_id)
    with pytest.raises(PlayerOpsError, match="idle"):
        svc.breach(user.qq, main_id, busy_sub_id)

    assert Card.getCardByID(main_id) is not None
    assert main.star == 1


def test_player_ops_allows_squad_main_but_requires_idle_sub(core_modules, make_user):
    from server.services.player_ops import PlayerOpsService

    Card = core_modules["model.card"].Card
    user = make_user(21002, "squad-main", money=1000000)
    main_id = _add_card(core_modules, user, 158023, star=1)
    sub_id = _add_card(core_modules, user, 158023, star=1)
    Card.getCardByID(main_id).set("status", 2)

    result = PlayerOpsService(_server_db()).upgrade(user.qq, main_id, sub_id)

    assert result["new_star"] == 2
    assert Card.getCardByID(main_id).star == 2
    assert Card.getCardByID(sub_id) is None


def test_lottery_reward_newbie_uses_best_pool_floor(core_modules, make_user, monkeypatch):
    from server.services.lottery import LotteryService

    Item = core_modules["model.item"].Item
    Card = core_modules["model.card"].Card
    Player = core_modules["model.player"].Player
    pool = core_modules["kernel.pool"]
    user = make_user(21003, "newbie", money=0)
    Item.addItem(user, 0, 0, 1)

    low_player = Player.getPlayerByID(200104)
    high_player = Player.getPlayerByID(231747)
    assert low_player.Overall <= 88
    assert high_player.Overall > 88

    monkeypatch.setattr(pool.g_pool["初级前锋"]["pool"], "choice", lambda u: Card.new(low_player, u))
    monkeypatch.setattr(pool.g_pool["初级中场"]["pool"], "choice", lambda u: Card.new(low_player, u))
    monkeypatch.setattr(pool.g_pool["初级后卫"]["pool"], "choice", lambda u: Card.new(low_player, u))
    monkeypatch.setattr(pool.g_pool["初级门将"]["pool"], "choice", lambda u: Card.new(low_player, u))
    monkeypatch.setattr(pool.g_pool["巅峰"]["pool"], "choice", lambda u: Card.new(high_player, u))
    monkeypatch.setattr(random, "randint", lambda a, b: a)

    result = LotteryService(_server_db()).draw_reward(user.qq, "新手")

    assert len(result.cards) == 20
    assert any(card.player_id == high_player.ID for card in result.cards)
    assert Item.getItemsByQQandType(user.qq, 0) is None


def test_lottery_pool_threshold_config_refreshes_web_pool(core_modules, make_user):
    from server.services.game_config import GameConfigService
    from server.services.lottery import LotteryService, LotteryError

    db = _server_db()
    user = make_user(21004, "threshold", money=1000000)
    config = GameConfigService(db)
    config.set("pool.advanced.min_overall", 999)

    with pytest.raises(LotteryError, match="no available"):
        LotteryService(db).draw(user.qq, "高级", 1)


def test_style_scale_config_changes_card_detail_ability(core_modules, make_user):
    from server.services.bag import BagService
    from server.services.game_config import GameConfigService

    server_db = _server_db()
    bot_db = core_modules["utils.database"].g_database
    user = make_user(21005, "style-scale", money=0)
    card_id = _add_card(core_modules, user, 158023, star=5)
    bot_db.update(f"UPDATE cards SET Style = 'hunter', Talents = '{json.dumps({'t': [1,1,1,1,1,1], 'o': [0,1,2,3,4,5], 'r': 1, 'rc': 0})}' WHERE ID = {card_id}")

    svc = BagService(server_db)
    before = svc.get_card_detail(card_id, user.qq)["abilities"]["Speed"]["value"]
    GameConfigService(server_db).set("style.scale.5", 30)
    after = svc.get_card_detail(card_id, user.qq)["abilities"]["Speed"]["value"]

    assert after > before
