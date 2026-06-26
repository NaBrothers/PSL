from model.player import *
from utils.database import *
from model.card import *
from model.user import *
import random

from psl_core.constants import FORWARD, MIDFIELD, GUARD, GOALKEEPER


def _first_pos_condition(positions):
    """Build SQL condition matching first position in comma-separated Position field."""
    parts = []
    for pos in positions:
        parts.append(f"substr(Position, 1, instr(Position || ',', ',') - 1) = '{pos}'")
    return "(" + " OR ".join(parts) + ")"


class Pool:
    def __init__(self):
      self.pool = []
      self.init()

    def init(self):
      pass

    def choice(self, user):
      player = random.choice(self.pool)
      card = Card.new(player, user)
      return card


def _load_players(position_group=None, min_overall=None):
    cursor = g_database.cursor()
    sql = "SELECT * FROM players"
    conditions = []
    if position_group:
        conditions.append(_first_pos_condition(position_group))
    if min_overall:
        conditions.append(f"Overall > {min_overall}")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    count = cursor.execute(sql)
    result = cursor.fetchall()
    cursor.close()
    return [Player(result[i]) for i in range(count)]


class ElementaryPool(Pool):
    def init(self):
        self.pool = _load_players()

class ElementaryForwardPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=FORWARD)

class ElementaryMidfieldPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=MIDFIELD)

class ElementaryGuardPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=GUARD)

class ElementaryGoalkeeperPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=GOALKEEPER)

class IntermediatePool(Pool):
    def init(self):
        self.pool = _load_players(min_overall=83)

class IntermediateForwardPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=FORWARD, min_overall=83)

class IntermediateMidfieldPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=MIDFIELD, min_overall=83)

class IntermediateGuardPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=GUARD, min_overall=83)

class IntermediateGoalkeeperPool(Pool):
    def init(self):
        self.pool = _load_players(position_group=GOALKEEPER, min_overall=83)

class AdvancedPool(Pool):
    def init(self):
        self.pool = _load_players(min_overall=86)

class BestPool(Pool):
    def init(self):
        self.pool = _load_players(min_overall=88)

class NBPool(Pool):
    def init(self):
        self.pool = _load_players()

    def choice(self, user):
      player = random.choice(self.pool)
      star = random.randint(1, 10)
      card = Card.new(player, user, star)
      return card


g_pool = {
  "初级": {
    "pool": ElementaryPool(),
    "name": "初级球员卡包",
    "cost": 1000,
    "ten_cost": 9500,
    "visible": True
  },
  "初级前锋": {
    "pool": ElementaryForwardPool(),
    "name": "初级前锋卡包",
    "cost": 1500,
    "ten_cost": 14250,
    "visible": True
  },
  "初级中场": {
    "pool": ElementaryMidfieldPool(),
    "name": "初级中场卡包",
    "cost": 1500,
    "ten_cost": 14250,
    "visible": True
  },
  "初级后卫": {
    "pool": ElementaryGuardPool(),
    "name": "初级后卫卡包",
    "cost": 1500,
    "ten_cost": 14250,
    "visible": True
  },
  "初级门将": {
    "pool": ElementaryGoalkeeperPool(),
    "name": "初级门将卡包",
    "cost": 1750,
    "ten_cost": 16625,
    "visible": True
  },
  "中级": {
    "pool": IntermediatePool(),
    "name": "中级球员卡包",
    "cost": 2500,
    "ten_cost": 23750,
    "visible": True
  },
  "中级前锋": {
    "pool": IntermediateForwardPool(),
    "name": "中级前锋卡包",
    "cost": 3750,
    "visible": True
  },
  "中级中场": {
    "pool": IntermediateMidfieldPool(),
    "name": "中级中场卡包",
    "cost": 3750,
    "visible": True
  },
  "中级后卫": {
    "pool": IntermediateGuardPool(),
    "name": "中级后卫卡包",
    "cost": 3750,
    "visible": True
  },
  "中级门将": {
    "pool": IntermediateGoalkeeperPool(),
    "name": "中级门将卡包",
    "cost": 5000,
    "visible": True
  },
  "高级": {
    "pool": AdvancedPool(),
    "name": "高级球员卡包",
    "cost": 7500,
    "visible": True
  },
  "巅峰": {
    "pool": BestPool(),
    "name": "巅峰球员卡包",
    "cost": 0,
    "visible": False
  },
  "新手": {
    "pool": None,
    "name": "新手限定卡包",
    "cost": 0,
    "visible": False,
    "info": "二十张球员卡（前锋*6，中场*6，后卫*6，门将*2，至少一张能力值89以上）"
  },
  "至尊": {
    "pool": NBPool(),
    "name": "至尊卡包",
    "cost": 0,
    "ten_cost": 0,
    "visible": False
  },
}
