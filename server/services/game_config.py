"""Game config service - centralized game configuration via global table."""

import json
from typing import Any, Optional

# Default values for all configurable parameters
DEFAULTS = {
    # Challenge
    "challenge.daily_attempts": 5,

    # Pack costs
    "pool.elementary.cost": 1000,
    "pool.elementary.ten_cost": 9000,
    "pool.elementary_forward.cost": 1500,
    "pool.elementary_forward.ten_cost": 13500,
    "pool.elementary_goalkeeper.cost": 1750,
    "pool.elementary_goalkeeper.ten_cost": 15750,
    "pool.intermediate.cost": 2500,
    "pool.intermediate.ten_cost": 22500,
    "pool.intermediate_forward.cost": 3750,
    "pool.intermediate_forward.ten_cost": 33750,
    "pool.intermediate_goalkeeper.cost": 5000,
    "pool.intermediate_goalkeeper.ten_cost": 45000,
    "pool.advanced.cost": 7500,

    # Pool thresholds
    "pool.intermediate.min_overall": 83,
    "pool.advanced.min_overall": 86,
    "pool.best.min_overall": 88,

    # League match rewards
    "league.match_reward.win_money": 2000,
    "league.match_reward.lose_money": 1000,
    "league.match_reward.tie_money": 1500,
    "league.match_reward.goal_bonus": 100,
    "league.match_reward.goal_bonus_cap": 5,
    "league.match_reward.card_count": 5,

    # League season
    "league.season_reward.money_multiplier": 5000,
    "league.individual_award.money": 25000,

    # Transfer
    "transfer.fee_percent": 0,

    # Upgrade
    "upgrade.cost_percent": 0.1,

    # Newbie
    "newbie.bonus_money": 50000,
}

# Map Chinese pool keys to config key prefixes
POOL_KEY_MAP = {
    "初级": "pool.elementary",
    "初级前锋": "pool.elementary_forward",
    "初级中场": "pool.elementary_forward",
    "初级后卫": "pool.elementary_forward",
    "初级门将": "pool.elementary_goalkeeper",
    "中级": "pool.intermediate",
    "中级前锋": "pool.intermediate_forward",
    "中级中场": "pool.intermediate_forward",
    "中级后卫": "pool.intermediate_forward",
    "中级门将": "pool.intermediate_goalkeeper",
    "高级": "pool.advanced",
}

# Grouped for admin UI display
CONFIG_GROUPS = {
    "挑战系统": [
        {"key": "challenge.daily_attempts", "label": "每日挑战次数", "type": "int"},
    ],
    "卡包价格": [
        {"key": "pool.elementary.cost", "label": "初级单抽", "type": "int"},
        {"key": "pool.elementary.ten_cost", "label": "初级十连", "type": "int"},
        {"key": "pool.elementary_forward.cost", "label": "初级前锋单抽", "type": "int"},
        {"key": "pool.elementary_forward.ten_cost", "label": "初级前锋十连", "type": "int"},
        {"key": "pool.elementary_goalkeeper.cost", "label": "初级门将单抽", "type": "int"},
        {"key": "pool.elementary_goalkeeper.ten_cost", "label": "初级门将十连", "type": "int"},
        {"key": "pool.intermediate.cost", "label": "中级单抽", "type": "int"},
        {"key": "pool.intermediate.ten_cost", "label": "中级十连", "type": "int"},
        {"key": "pool.intermediate_forward.cost", "label": "中级前锋单抽", "type": "int"},
        {"key": "pool.intermediate_forward.ten_cost", "label": "中级前锋十连", "type": "int"},
        {"key": "pool.intermediate_goalkeeper.cost", "label": "中级门将单抽", "type": "int"},
        {"key": "pool.intermediate_goalkeeper.ten_cost", "label": "中级门将十连", "type": "int"},
        {"key": "pool.advanced.cost", "label": "高级单抽", "type": "int"},
    ],
    "卡池阈值": [
        {"key": "pool.intermediate.min_overall", "label": "中级最低OVR", "type": "int"},
        {"key": "pool.advanced.min_overall", "label": "高级最低OVR", "type": "int"},
        {"key": "pool.best.min_overall", "label": "巅峰最低OVR", "type": "int"},
    ],
    "联赛奖励": [
        {"key": "league.match_reward.win_money", "label": "胜利奖金", "type": "int"},
        {"key": "league.match_reward.lose_money", "label": "失败奖金", "type": "int"},
        {"key": "league.match_reward.tie_money", "label": "平局奖金", "type": "int"},
        {"key": "league.match_reward.goal_bonus", "label": "进球奖金(每球)", "type": "int"},
        {"key": "league.match_reward.goal_bonus_cap", "label": "进球奖金上限(球数)", "type": "int"},
        {"key": "league.match_reward.card_count", "label": "每场发卡包数", "type": "int"},
        {"key": "league.season_reward.money_multiplier", "label": "赛季排名奖金系数", "type": "int"},
        {"key": "league.individual_award.money", "label": "个人奖项奖金", "type": "int"},
    ],
    "转会市场": [
        {"key": "transfer.fee_percent", "label": "交易税(%)", "type": "float"},
    ],
    "强化系统": [
        {"key": "upgrade.cost_percent", "label": "强化费用比例", "type": "float"},
    ],
    "新人福利": [
        {"key": "newbie.bonus_money", "label": "新人启动金", "type": "int"},
    ],
}


class GameConfigService:
    def __init__(self, db):
        self.db = db
        self._cache = {}

    def get(self, key: str) -> Any:
        if key in self._cache:
            return self._cache[key]
        row = self.db.query_one(
            'SELECT Value FROM "global" WHERE Name = ?', (f"config:{key}",)
        )
        if row:
            val = json.loads(row[0])
            self._cache[key] = val
            return val
        return DEFAULTS.get(key)

    def set(self, key: str, value: Any):
        self._cache[key] = value
        existing = self.db.query_one(
            'SELECT ID FROM "global" WHERE Name = ?', (f"config:{key}",)
        )
        val_str = json.dumps(value)
        if existing:
            self.db.execute(
                'UPDATE "global" SET Value = ? WHERE Name = ?', (val_str, f"config:{key}")
            )
        else:
            self.db.execute(
                'INSERT INTO "global" (Name, Value) VALUES (?, ?)', (f"config:{key}", val_str)
            )

    def get_all(self) -> dict:
        result = {}
        for key, default in DEFAULTS.items():
            result[key] = self.get(key)
        return result

    def get_groups(self) -> list:
        all_values = self.get_all()
        groups = []
        for group_name, items in CONFIG_GROUPS.items():
            group_items = []
            for item in items:
                group_items.append({
                    **item,
                    "value": all_values.get(item["key"], DEFAULTS.get(item["key"])),
                    "default": DEFAULTS.get(item["key"]),
                })
            groups.append({"name": group_name, "items": group_items})
        return groups

    def clear_cache(self):
        self._cache = {}
