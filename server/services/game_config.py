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
    "pool.advanced.ten_cost": 0,

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
    "transfer.fee_percent": 5,
    "transfer.reference_count": 5,

    # Upgrade
    "upgrade.cost_percent": 0.1,

    # Newbie
    "newbie.bonus_money": 50000,

    # Talents
    "talent.mean": 1.0,
    "talent.std": 0.2,
    "talent.min": 0.5,
    "talent.max": 1.5,
    "talent.reroll_cost": 50000,
    "talent.reroll_max": 2,
    "talent.grade_d_max": 0.7,
    "talent.grade_c_max": 0.9,
    "talent.grade_b_max": 1.1,
    "talent.grade_a_max": 1.3,

    # Style scale per star (特性曲线)
    "style.scale.1": 2,
    "style.scale.2": 3,
    "style.scale.3": 4,
    "style.scale.4": 6,
    "style.scale.5": 8,
    "style.scale.6": 10,
    "style.scale.7": 13,
    "style.scale.8": 16,
    "style.scale.9": 19,
    "style.scale.10": 22,
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
        {"key": "transfer.reference_count", "label": "参考价取最近N笔", "type": "int"},
    ],
    "强化系统": [
        {"key": "upgrade.cost_percent", "label": "强化费用比例", "type": "float"},
    ],
    "新人福利": [
        {"key": "newbie.bonus_money", "label": "新人启动金", "type": "int"},
    ],
    "天赋系统": [
        {"key": "talent.mean", "label": "天赋均值", "type": "float"},
        {"key": "talent.std", "label": "天赋标准差", "type": "float"},
        {"key": "talent.min", "label": "天赋下限", "type": "float"},
        {"key": "talent.max", "label": "天赋上限", "type": "float"},
        {"key": "talent.reroll_cost", "label": "重铸费用", "type": "int"},
        {"key": "talent.reroll_max", "label": "重铸次数上限", "type": "int"},
        {"key": "talent.grade_d_max", "label": "D级上界", "type": "float"},
        {"key": "talent.grade_c_max", "label": "C级上界", "type": "float"},
        {"key": "talent.grade_b_max", "label": "B级上界", "type": "float"},
        {"key": "talent.grade_a_max", "label": "A级上界", "type": "float"},
    ],
    "特性曲线": [
        {"key": "style.scale.1", "label": "1★特性系数", "type": "int"},
        {"key": "style.scale.2", "label": "2★特性系数", "type": "int"},
        {"key": "style.scale.3", "label": "3★特性系数", "type": "int"},
        {"key": "style.scale.4", "label": "4★特性系数", "type": "int"},
        {"key": "style.scale.5", "label": "5★特性系数", "type": "int"},
        {"key": "style.scale.6", "label": "6★特性系数", "type": "int"},
        {"key": "style.scale.7", "label": "7★特性系数", "type": "int"},
        {"key": "style.scale.8", "label": "8★特性系数", "type": "int"},
        {"key": "style.scale.9", "label": "9★特性系数", "type": "int"},
        {"key": "style.scale.10", "label": "10★特性系数", "type": "int"},
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
        if key in DEFAULTS:
            self.set(key, DEFAULTS[key])
            return DEFAULTS[key]
        raise KeyError(f"Game config key not found: {key}")

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
