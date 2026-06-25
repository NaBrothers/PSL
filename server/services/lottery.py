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
    name: str
    position: str
    overall: int
    star: int
    style: str
    style_name: str


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
        for key, pool in g_pool.items():
            if not pool.get("visible", False):
                continue
            pools.append(PoolInfo(
                key=key, name=pool["name"], cost=pool["cost"],
                ten_cost=pool.get("ten_cost", 0), visible=True,
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

        if count == 10:
            if "ten_cost" not in pool:
                raise LotteryError("Pool does not support 10x draw")
            cost = pool["ten_cost"]
        else:
            cost = pool["cost"] * count

        if user.money < cost:
            raise InsufficientFunds(f"Need {cost}, have {user.money}")

        cards = []
        for _ in range(count):
            card = pool["pool"].choice(user)
            cards.append(card)

        ids = Bag.addToBagMany(user, cards) if count > 1 else [Bag.addToBag(user, cards[0])]
        user.spend(cost)

        style_names = {
            'sniper': '狙击手', 'finisher': '终结者', 'deadeye': '恶魔眼', 'marksman': '神枪手',
            'hawk': '凤头鹰', 'artist': '艺术家', 'architect': '建筑师', 'powerhous': '抢球机器',
            'maestro': '大师', 'engine': '发动机', 'sentinal': '哨兵', 'guardian': '护卫',
            'gladiator': '斗士', 'backbone': '骨干', 'anchor': '铁锚', 'hunter': '狩猎者',
            'catalyst': '催化剂', 'shadow': '暗影', 'speedster': '疾速魔', 'slugger': '重炮手',
            'bronzewall': '铜墙', 'ironwall': '铁壁', 'agilecat': '灵猫', 'gloves': '手套',
        }
        drawn = []
        for i, card in enumerate(cards):
            drawn.append(DrawnCard(
                id=ids[i], name=card.player.Name, position=card.player.Position,
                overall=card.overall, star=card.star, style=card.style,
                style_name=style_names.get(card.style, card.style),
            ))

        return DrawResult(pool_name=pool["name"], cards=drawn, cost=cost, remaining_money=user.money)
