"""Lottery service - card pack draws."""

import sys
import os
from dataclasses import dataclass
from typing import List

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


class LotteryError(Exception):
    pass


class InsufficientFunds(LotteryError):
    pass


class PoolNotFound(LotteryError):
    pass


@dataclass
class DrawnCard:
    id: int
    player_id: int
    name: str
    position: str
    overall: int
    star: int
    style: str
    style_name: str
    nationality: str = ""
    club: str = ""
    top_abilities: list = None


@dataclass
class DrawResult:
    pool_name: str
    cards: List[DrawnCard]
    cost: int
    remaining_money: int


@dataclass
class PoolInfo:
    key: str
    name: str
    cost: int
    ten_cost: int
    visible: bool


class LotteryService:
    def __init__(self, db):
        self.db = db

    def list_pools(self, qq: int) -> dict:
        from kernel.pool import g_pool
        from model.item import Item

        pools = []
        from server.services.game_config import GameConfigService, POOL_KEY_MAP
        config = GameConfigService(self.db)
        for key, pool in g_pool.items():
            if not pool.get("visible", False):
                continue
            cfg_base = POOL_KEY_MAP.get(key)
            cost = config.get(f"{cfg_base}.cost") if cfg_base else pool["cost"]
            ten_cost = config.get(f"{cfg_base}.ten_cost") if cfg_base else pool.get("ten_cost", 0)
            pools.append(PoolInfo(
                key=key, name=pool["name"], cost=cost or pool["cost"],
                ten_cost=ten_cost or pool.get("ten_cost", 0), visible=True,
            ))

        reward_packs = []
        items = Item.getItemsByQQandType(qq, 0)
        if items:
            for item in items.entries:
                reward_packs.append({"name": item.name, "count": item.count})

        return {"pools": [p.__dict__ for p in pools], "reward_packs": reward_packs}

    def draw(self, qq: int, pool_key: str, count: int = 1) -> DrawResult:
        from kernel.pool import g_pool
        from model.user import User
        from model.bag import Bag
        from model.card import Card

        if pool_key not in g_pool or not g_pool[pool_key].get("visible", False):
            raise PoolNotFound(f"Pool '{pool_key}' not found")

        pool = g_pool[pool_key]
        user = User.getUserByQQ(qq)
        if user is None:
            raise LotteryError("User not found")

        from server.services.game_config import GameConfigService, POOL_KEY_MAP
        config = GameConfigService(self.db)
        cfg_base = POOL_KEY_MAP.get(pool_key)
        pool_cost = config.get(f"{cfg_base}.cost") if cfg_base else pool["cost"]
        pool_ten_cost = config.get(f"{cfg_base}.ten_cost") if cfg_base else pool.get("ten_cost")
        if count == 10:
            if not pool_ten_cost:
                raise LotteryError("Pool does not support 10x draw")
            cost = pool_ten_cost
        else:
            cost = (pool_cost or pool["cost"]) * count

        if user.money < cost:
            raise InsufficientFunds(f"Need {cost}, have {user.money}")

        cards = []
        for _ in range(count):
            card = pool["pool"].choice(user)
            cards.append(card)

        ids = Bag.addToBagMany(user, cards) if count > 1 else [Bag.addToBag(user, cards[0])]
        user.spend(cost)

        from psl_core.card import get_style_name
        from psl_core.constants import GOALKEEPER
        ABILITY_NAMES = {"Heading": "头球", "Finishing": "终结", "Short_Passing": "短传",
            "Dribbling": "盘带", "Tackling": "抢断", "Defence": "防守", "Speed": "速度",
            "Long_Shot": "远射", "Long_Passing": "长传", "IQ": "球商",
            "GK_Saving": "扑救", "GK_Positioning": "站位", "GK_Reaction": "反应"}
        drawn = []
        for i, card in enumerate(cards):
            pos = card.player.Position.split(",")[0].strip() if card.player.Position else ""
            exclude = {"GK_Saving", "GK_Positioning", "GK_Reaction"} if pos not in GOALKEEPER else {"Heading", "Finishing", "Long_Shot", "Tackling"}
            ability_list = [(ABILITY_NAMES.get(k, k), v) for k, v in card.ability.items() if k not in exclude]
            ability_list.sort(key=lambda x: -x[1])
            top3 = [{"name": a[0], "value": a[1]} for a in ability_list[:3]]
            drawn.append(DrawnCard(
                id=ids[i], player_id=card.player.ID, name=card.player.Name, position=card.player.Position,
                overall=card.overall, star=card.star, style=card.style,
                style_name=get_style_name(card.style, card.player.Position),
                nationality=card.player.Nationality or "",
                club=card.player.Club or "",
                top_abilities=top3,
            ))

        return DrawResult(pool_name=pool["name"], cards=drawn, cost=cost, remaining_money=user.money)

    def draw_reward(self, qq: int, pool_key: str) -> DrawResult:
        from kernel.pool import g_pool
        from kernel.lottery import try_newbee
        from model.user import User
        from model.bag import Bag
        from model.card import Card
        from model.item import Item

        user = User.getUserByQQ(qq)
        if user is None:
            raise LotteryError("User not found")

        items = Item.getItemsByQQandType(qq, 0)
        if items is None:
            raise PoolNotFound("No reward packs available")
        matching = [item for item in items.entries if item.name == pool_key]
        if len(matching) == 0:
            raise PoolNotFound(f"Reward pack '{pool_key}' not found")

        if pool_key not in g_pool:
            raise PoolNotFound(f"Pool '{pool_key}' not found in game data")

        pool = g_pool[pool_key]
        cards = []
        if pool_key == "新手":
            from kernel.pool import ElementaryForwardPool, ElementaryMidfieldPool, ElementaryGuardPool, ElementaryGoalkeeperPool, BestPool
            fw_pool = g_pool["初级前锋"]["pool"]
            mf_pool = g_pool["初级中场"]["pool"]
            gd_pool = g_pool["初级后卫"]["pool"]
            gk_pool = g_pool["初级门将"]["pool"]
            best_pool = g_pool.get("巅峰", {}).get("pool")
            for _ in range(6):
                cards.append(fw_pool.choice(user))
            for _ in range(6):
                cards.append(mf_pool.choice(user))
            for _ in range(6):
                cards.append(gd_pool.choice(user))
            for _ in range(2):
                cards.append(gk_pool.choice(user))
        else:
            for _ in range(matching[0].count):
                card = pool["pool"].choice(user)
                cards.append(card)

        ids = Bag.addToBagMany(user, cards) if len(cards) > 1 else [Bag.addToBag(user, cards[0])]

        for item in matching:
            item.remove()

        from psl_core.card import get_style_name
        from psl_core.constants import GOALKEEPER
        ABILITY_NAMES = {"Heading": "头球", "Finishing": "终结", "Short_Passing": "短传",
            "Dribbling": "盘带", "Tackling": "抢断", "Defence": "防守", "Speed": "速度",
            "Long_Shot": "远射", "Long_Passing": "长传", "IQ": "球商",
            "GK_Saving": "扑救", "GK_Positioning": "站位", "GK_Reaction": "反应"}
        drawn = []
        for i, card in enumerate(cards):
            pos = card.player.Position.split(",")[0].strip() if card.player.Position else ""
            exclude = {"GK_Saving", "GK_Positioning", "GK_Reaction"} if pos not in GOALKEEPER else {"Heading", "Finishing", "Long_Shot", "Tackling"}
            ability_list = [(ABILITY_NAMES.get(k, k), v) for k, v in card.ability.items() if k not in exclude]
            ability_list.sort(key=lambda x: -x[1])
            top3 = [{"name": a[0], "value": a[1]} for a in ability_list[:3]]
            drawn.append(DrawnCard(
                id=ids[i], player_id=card.player.ID, name=card.player.Name, position=card.player.Position,
                overall=card.overall, star=card.star, style=card.style,
                style_name=get_style_name(card.style, card.player.Position),
                nationality=card.player.Nationality or "",
                club=card.player.Club or "",
                top_abilities=top3,
            ))

        return DrawResult(pool_name=f"(奖励){pool_key}", cards=drawn, cost=0, remaining_money=user.money)
