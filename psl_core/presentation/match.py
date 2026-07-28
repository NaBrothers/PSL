"""Turn Rust match facts into shared Chinese reports and broadcasts."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


BROADCAST_INTERVAL_SECONDS = 270


SHOT_TEMPLATES = {
    "goal": [
        "{player} 冷静完成终结，皮球入网{xg}。",
        "{player} 抓住防线露出的空当，一脚改写比分{xg}。",
        "{player} 出现在最危险的位置，把这次攻势转化为进球{xg}。",
        "{player} 的射门干净利落，门将没能阻止皮球入网{xg}。",
    ],
    "saved": [
        "{player} 完成一脚有威胁的攻门{xg}，{keeper} 将球扑出。",
        "{player} 把球送向门框范围{xg}，{keeper} 反应迅速化解险情。",
        "{player} 获得射门窗口{xg}，但 {keeper} 守住了球门。",
        "{player} 的攻门质量不低{xg}，{keeper} 用一次扑救作出回应。",
    ],
    "off_target": [
        "{player} 找到射门机会{xg}，可惜皮球偏出。",
        "{player} 尝试完成终结{xg}，最后一脚没能命中目标。",
        "{player} 赶在封堵前起脚{xg}，皮球与球门擦肩而过。",
        "{player} 的射门没有压住{xg}，这次进攻就此结束。",
    ],
}

PASS_TEMPLATES = {
    "through_ball": [
        "{player} 送出直塞，{target} 向防线身后前插。",
        "{player} 看见纵深空当，一脚把球塞给 {target}。",
        "{player} 用穿透性传球找到前插的 {target}。",
    ],
    "cross": [
        "{player} 从边路把球送入禁区，{target} 赶向落点。",
        "{player} 起球传中，禁区内的 {target} 准备接应。",
        "{player} 在边路完成传中，皮球找到 {target} 一侧。",
    ],
    "into_box": [
        "{player} 把球送进禁区，{target} 接到这次推进。",
        "{player} 找到禁区内的 {target}，进攻继续向球门靠近。",
        "{player} 的传球穿过防线来到 {target} 脚下。",
    ],
    "progressive": [
        "{player} 用一脚向前传递找到 {target}，球队越过一道防线。",
        "{player} 把球交给前方的 {target}，进攻节奏随之加快。",
        "{player} 找到推进线路，{target} 在前场接球。",
    ],
    "long": [
        "{player} 起长传越过中场，{target} 控制住落点。",
        "{player} 用大范围转移找到 {target}。",
        "{player} 直接把球送向前场，{target} 完成接应。",
    ],
    "completed": [
        "{player} 将球交给 {target}。",
        "{player} 与 {target} 完成衔接。",
        "{player} 稳稳找到接应的 {target}。",
    ],
    "offside": [
        "{player} 的传球找到了前插的 {target}，但边裁举旗示意越位。",
        "{target} 启动稍早，{player} 的传球被判越位。",
    ],
    "first_touch_error": [
        "{player} 找到 {target}，但后者第一脚没有把球控制住。",
        "{target} 停球出现偏差，{player} 的传递没能延续攻势。",
    ],
    "misplaced": [
        "{player} 的传球偏离目标，球队丢掉了这次推进机会。",
        "{player} 没能把球送到队友脚下，球权重新变得开放。",
    ],
    "loose": [
        "{player} 把球送向空当，双方开始争抢第二落点。",
        "{player} 的传球没有直接找到队友，皮球进入五五开的区域。",
    ],
}

DEFENSE_TEMPLATES = {
    "interception": [
        "{player} 读懂传球线路，抢先把球截下。",
        "{player} 及时横移完成拦截，终止了这次推进。",
        "{player} 卡住线路，把对方的传球收入脚下。",
    ],
    "tackle": [
        "{player} 抓准时机完成抢断，球权就此易手。",
        "{player} 在对抗中干净地把球夺回。",
        "{player} 贴近持球人完成抢断，防线重新拿到球权。",
    ],
    "duel": [
        "{player} 在一对一中完成摆脱，继续控制球权。",
        "{player} 赢下正面对抗，把进攻延续下去。",
    ],
    "clearance": [
        "{player} 把球清出危险区域，双方争夺第二落点。",
        "{player} 及时完成解围，暂时缓解门前压力。",
    ],
}

ROUTE_TEMPLATES = {
    "through_ball": [
        "{team} 在中路找到防线身后的纵深",
        "{team} 突然用直塞提高进攻速度",
        "{team} 的连续传递撕开了纵向空当",
    ],
    "cross": [
        "{team} 从边路推进后送出传中",
        "{team} 把进攻展开到边路并将球送入禁区",
        "{team} 利用宽度拉开防线后起球",
    ],
    "carry": [
        "{team} 依靠持球推进压过中场",
        "{team} 通过连续带球把防线向后压",
        "{team} 用个人推进打开前场空间",
    ],
    "long": [
        "{team} 用长传直接越过中场",
        "{team} 从后场起球寻找前场落点",
        "{team} 选择更直接的方式发起攻势",
    ],
    "pass": [
        "{team} 通过连续传递耐心向前推进",
        "{team} 调动防线后把球送到前场",
        "{team} 控制住球权并逐步压上",
    ],
    "default": [
        "{team} 组织起一轮攻势",
        "{team} 拿到球权后向前推进",
        "{team} 在前场寻找进攻出口",
    ],
}


@dataclass(frozen=True)
class PresentedEvent:
    minute: int
    second: int
    event_type: str
    text: str
    importance: int
    team_side: str
    seq: int = 0
    possession_id: int = 0
    home_score: int = 0
    away_score: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "minute": self.minute,
            "second": self.second,
            "event_type": self.event_type,
            "text": self.text,
            "importance": self.importance,
            "team_side": self.team_side,
            "seq": self.seq,
            "possession_id": self.possession_id,
            "home_score": self.home_score,
            "away_score": self.away_score,
        }


@dataclass
class MatchPresentation:
    events: List[PresentedEvent] = field(default_factory=list)
    broadcasts: List[List[str]] = field(default_factory=list)
    report: str = ""
    stats_text: str = ""


def _section_seed(seed: int, section: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(
            "{}:{}".format(seed, section).encode("utf-8"),
            digest_size=8,
        ).digest(),
        "big",
    )


def _choice(seed: int, section: str, options: Sequence[str]) -> str:
    if not options:
        return ""
    return random.Random(_section_seed(seed, section)).choice(list(options))


def _identity_name(identity: Any, colored: bool = True) -> str:
    if not isinstance(identity, dict):
        return ""
    name = identity.get("colored_name") if colored else identity.get("name")
    name = name or identity.get("name") or ""
    position = identity.get("position") or ""
    return "{} {}".format(position, name).strip()


def _plain_name(identity: Any) -> str:
    if not isinstance(identity, dict):
        return ""
    return str(identity.get("name") or "")


def _tags(event: Dict[str, Any]) -> set:
    return set(event.get("tags") or [])


def _xg_suffix(xg: float) -> str:
    if xg <= 0:
        return ""
    if xg >= 0.3:
        quality = "，这是一次绝佳机会"
    elif xg >= 0.15:
        quality = "，机会质量很高"
    elif xg >= 0.07:
        quality = "，这次攻门有一定威胁"
    else:
        quality = "，射门难度不小"
    return "{}（xG {:.2f}）".format(quality, xg)


def _event_text(event: Dict[str, Any], seed: int) -> Tuple[str, int]:
    event_type = event.get("event_type", "")
    outcome = event.get("outcome", "")
    tags = _tags(event)
    seq = int(event.get("seq", 0))
    player = _identity_name(event.get("player")) or "球员"
    target = _identity_name(event.get("target_player")) or "队友"

    if event_type == "shot":
        template = _choice(
            seed,
            "shot:{}:{}".format(outcome, seq),
            SHOT_TEMPLATES.get(outcome, SHOT_TEMPLATES["off_target"]),
        )
        text = template.format(
            player=player,
            keeper=target or "门将",
            xg=_xg_suffix(float(event.get("xg", 0) or 0)),
        )
        assister = _identity_name(event.get("assist_player"))
        if outcome == "goal" and assister:
            text += " 助攻来自 {}。".format(assister)
        if outcome == "goal":
            return text, 5
        if outcome == "saved" or "big_chance" in tags:
            return text, 4
        return text, 3

    if event_type == "pass":
        if outcome in ("offside", "first_touch_error", "misplaced", "loose"):
            key = outcome
        elif "through_ball" in tags:
            key = "through_ball"
        elif "cross" in tags:
            key = "cross"
        elif "into_box" in tags:
            key = "into_box"
        elif "progressive" in tags:
            key = "progressive"
        elif "long" in tags:
            key = "long"
        else:
            key = "completed"
        template = _choice(
            seed,
            "pass:{}:{}".format(key, seq),
            PASS_TEMPLATES[key],
        )
        importance = 3 if key in ("through_ball", "cross", "into_box") else 2
        return template.format(player=player, target=target), importance

    if event_type in ("interception", "tackle", "duel", "clearance"):
        key = event_type
        template = _choice(
            seed,
            "defense:{}:{}".format(key, seq),
            DEFENSE_TEMPLATES[key],
        )
        importance = 3 if key in ("interception", "tackle") else 2
        return template.format(player=player, target=target), importance

    if event_type == "carry":
        if "into_box" in tags:
            return "{} 持球突入禁区，把防线向球门方向压缩。".format(player), 3
        if "progressive" in tags or "into_final_third" in tags:
            return "{} 通过带球越过一道防线。".format(player), 2
        return "{} 继续控制球权向前移动。".format(player), 1

    if event_type == "restart":
        labels = {
            "kickoff": "中圈开球",
            "goal_kick": "球门球",
            "throw_in": "边线球",
            "corner": "角球",
            "offside": "越位后的任意球",
        }
        return "{} 准备执行{}。".format(
            player,
            labels.get(outcome, "定位球"),
        ), 1

    return "", 0


def _is_presentable(event: Dict[str, Any], importance: int) -> bool:
    event_type = event.get("event_type")
    outcome = event.get("outcome")
    tags = _tags(event)
    if event_type == "shot":
        return True
    if event_type in ("interception", "tackle"):
        return True
    if event_type == "pass":
        return (
            outcome != "completed"
            or bool(tags.intersection({"through_ball", "cross", "into_box"}))
        )
    if event_type == "carry":
        return bool(tags.intersection({"into_box", "into_final_third"}))
    return event_type == "restart" and outcome in ("corner", "offside")


def _present_events(raw_events: Iterable[Dict[str, Any]], seed: int) -> List[PresentedEvent]:
    presented = []
    for event in sorted(raw_events, key=lambda item: int(item.get("seq", 0))):
        text, importance = _event_text(event, seed)
        if not text or not _is_presentable(event, importance):
            continue
        score_after = event.get("score_after") or [0, 0]
        presented.append(
            PresentedEvent(
                minute=int(event.get("minute", 0)),
                second=int(event.get("second", 0)),
                event_type=str(event.get("event_type", "")),
                text=text,
                importance=importance,
                team_side=str(event.get("team_side", "")),
                seq=int(event.get("seq", 0)),
                possession_id=int(event.get("possession_id", 0)),
                home_score=int(score_after[0]),
                away_score=int(score_after[1]),
            )
        )
    return presented


def _route_kind(events: Sequence[Dict[str, Any]]) -> str:
    all_tags = set()
    for event in events:
        all_tags.update(_tags(event))
    if "through_ball" in all_tags:
        return "through_ball"
    if "cross" in all_tags:
        return "cross"
    if any(
        event.get("event_type") == "carry"
        and _tags(event).intersection({"progressive", "into_final_third", "into_box"})
        for event in events
    ):
        return "carry"
    if "long" in all_tags and "progressive" in all_tags:
        return "long"
    if sum(
        event.get("event_type") == "pass" and event.get("outcome") == "completed"
        for event in events
    ) >= 3:
        return "pass"
    return "default"


def _attacking_side(events: Sequence[Dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("event_type") == "shot":
            return str(event.get("team_side", "home"))
    for event in events:
        if event.get("event_type") in ("pass", "carry"):
            return str(event.get("team_side", "home"))
    return str(events[0].get("team_side", "home"))


def _possession_value(events: Sequence[Dict[str, Any]]) -> int:
    value = 0
    for event in events:
        event_type = event.get("event_type")
        outcome = event.get("outcome")
        tags = _tags(event)
        if event_type == "shot":
            if outcome == "goal":
                value = max(value, 10)
            elif outcome == "saved":
                value = max(value, 8)
            elif "big_chance" in tags:
                value = max(value, 7)
            else:
                value = max(value, 6)
        elif tags.intersection({"cross", "through_ball"}):
            value = max(value, 5)
        elif "into_box" in tags:
            value = max(value, 4)
        elif event_type in ("interception", "tackle"):
            value = max(value, 3)
        elif "progressive" in tags:
            value = max(value, 2)
    return value


def _possession_summary(
    events: Sequence[Dict[str, Any]],
    seed: int,
    home_name: str,
    away_name: str,
) -> Tuple[int, int, str, bool]:
    attacking_side = _attacking_side(events)
    team_name = home_name if attacking_side == "home" else away_name
    route_kind = _route_kind(events)
    route = _choice(
        seed,
        "route:{}:{}".format(events[0].get("possession_id", 0), route_kind),
        ROUTE_TEMPLATES[route_kind],
    ).format(team=team_name)
    terminal = next(
        (event for event in reversed(events) if event.get("event_type") == "shot"),
        None,
    )
    if terminal is not None:
        text, importance = _event_text(terminal, seed)
        is_goal = terminal.get("outcome") == "goal"
        if is_goal:
            score = terminal.get("score_after") or [0, 0]
            text += " /~$⚽ 进球！比分来到 {}:{}/".format(
                int(score[0]),
                int(score[1]),
            )
        return (
            int(terminal.get("match_second", 0)),
            importance,
            "{}，{}".format(route, text),
            is_goal,
        )

    defense = next(
        (
            event
            for event in reversed(events)
            if event.get("event_type") in ("interception", "tackle", "clearance")
            and event.get("team_side") != attacking_side
        ),
        None,
    )
    if defense is not None:
        text, importance = _event_text(defense, seed)
        return (
            int(defense.get("match_second", 0)),
            importance,
            "{}，{}".format(route, text),
            False,
        )

    last = events[-1]
    if route_kind in ("through_ball", "cross"):
        ending = _choice(
            seed,
            "quiet:{}".format(events[0].get("possession_id", 0)),
            [
                "但防线及时收缩，没有让机会变成射门。",
                "禁区内的最后处理没能形成攻门。",
                "对手守住了关键区域，这轮攻势未能完成终结。",
            ],
        )
    else:
        ending = _choice(
            seed,
            "quiet:{}".format(events[0].get("possession_id", 0)),
            [
                "但最后一传没有出现，进攻只能重新组织。",
                "对手保持住阵型，没有留下清晰的射门窗口。",
                "这轮推进没能继续深入危险区域。",
            ],
        )
    return int(last.get("match_second", 0)), 2, "{}，{}".format(route, ending), False


def _score_at(events: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    if not events:
        return 0, 0
    score = events[-1].get("score_after") or [0, 0]
    return int(score[0]), int(score[1])


def _broadcast_prefix(match_second: int, score: Tuple[int, int]) -> str:
    half = "上半时" if match_second < 45 * 60 else "下半时"
    half_second = match_second if match_second < 45 * 60 else match_second - 45 * 60
    return "主{}:{}客 {}{:02d}:{:02d}".format(
        score[0],
        score[1],
        half,
        half_second // 60,
        half_second % 60,
    )


def _build_broadcasts(
    raw_events: Sequence[Dict[str, Any]],
    seed: int,
    home_name: str,
    away_name: str,
) -> List[List[str]]:
    possessions: Dict[int, List[Dict[str, Any]]] = {}
    for event in raw_events:
        possession_id = int(event.get("possession_id", 0))
        possessions.setdefault(possession_id, []).append(event)

    summaries = []
    for possession_id, events in possessions.items():
        events.sort(key=lambda item: int(item.get("seq", 0)))
        value = _possession_value(events)
        if value <= 0:
            continue
        second, importance, text, is_goal = _possession_summary(
            events,
            seed,
            home_name,
            away_name,
        )
        summaries.append(
            {
                "possession_id": possession_id,
                "second": second,
                "importance": max(value, importance),
                "text": text,
                "goal": is_goal,
                "score": _score_at(events),
            }
        )
    summaries.sort(key=lambda item: (item["second"], item["possession_id"]))

    # Keep every dangerous attack and one representative sequence per three-minute
    # interval, so the broadcast has rhythm without dumping the raw event stream.
    selected = []
    best_by_bucket: Dict[int, Dict[str, Any]] = {}
    for summary in summaries:
        if summary["importance"] >= 4:
            selected.append(summary)
            continue
        bucket = summary["second"] // 180
        current = best_by_bucket.get(bucket)
        if current is None or summary["importance"] > current["importance"]:
            best_by_bucket[bucket] = summary
    selected.extend(best_by_bucket.values())
    selected.sort(key=lambda item: (item["second"], item["possession_id"]))

    batches: List[List[str]] = []
    buffer: List[str] = []
    buffer_start: Optional[int] = None
    halftime_emitted = False
    for summary in selected:
        second = int(summary["second"])
        if not halftime_emitted and second >= 45 * 60:
            if buffer:
                batches.append(buffer)
                buffer = []
            batches.append(["上半场结束"])
            halftime_emitted = True
            buffer_start = None

        if buffer_start is None:
            buffer_start = second
        if second - buffer_start >= BROADCAST_INTERVAL_SECONDS or summary["goal"]:
            if buffer:
                batches.append(buffer)
                buffer = []
            buffer_start = second

        line = "{} {}".format(
            _broadcast_prefix(second, summary["score"]),
            summary["text"],
        )
        buffer.append(line)
        if summary["goal"]:
            batches.append(buffer)
            buffer = []
            buffer_start = None

    if buffer:
        batches.append(buffer)
    if not halftime_emitted:
        batches.append(["上半场结束"])
    batches.append(["下半场结束"])
    return batches


def _result_paragraph(
    home_name: str,
    away_name: str,
    home_score: int,
    away_score: int,
) -> str:
    score = "{}:{}".format(home_score, away_score)
    if home_score == away_score:
        if home_score == 0:
            return "{} 与 {} 互交白卷，最终比分为 {}。".format(
                home_name, away_name, score
            )
        return "{} 与 {} 战成 {}，双方各取所需。".format(
            home_name, away_name, score
        )
    winner = home_name if home_score > away_score else away_name
    loser = away_name if home_score > away_score else home_name
    margin = abs(home_score - away_score)
    if margin >= 3:
        return "{} 以 {} 大胜 {}，比赛走势较早失去悬念。".format(
            winner, score, loser
        )
    return "{} 以 {} 击败 {}。".format(winner, score, loser)


def _build_report(
    result: Any,
    home_name: str,
    away_name: str,
    seed: int,
) -> str:
    home = result.home_stats
    away = result.away_stats
    paragraphs = [
        _result_paragraph(
            home_name,
            away_name,
            int(result.home_score),
            int(result.away_score),
        )
    ]

    home_possession = float(home.get("possession", 50.0) or 0)
    away_possession = float(away.get("possession", 50.0) or 0)
    shots = "{}:{}".format(home.get("shots", 0), away.get("shots", 0))
    shots_on_target = "{}:{}".format(
        home.get("shots_on_target", 0),
        away.get("shots_on_target", 0),
    )
    if abs(home_possession - away_possession) >= 10:
        dominant = home_name if home_possession > away_possession else away_name
        possession = max(home_possession, away_possession)
        paragraphs.append(
            "{} 拿到 {:.1f}% 的控球率；两队射门比为 {}，射正比为 {}。".format(
                dominant,
                possession,
                shots,
                shots_on_target,
            )
        )
    else:
        paragraphs.append(
            "双方控球接近，射门比为 {}，射正比为 {}，比赛长期处于拉锯状态。".format(
                shots,
                shots_on_target,
            )
        )

    goals = [
        event
        for event in result.events
        if event.get("event_type") == "shot" and event.get("outcome") == "goal"
    ]
    if goals:
        goal_lines = []
        for event in goals:
            scorer = _identity_name(event.get("player"))
            assister = _identity_name(event.get("assist_player"))
            line = "第{}分钟，{} 完成破门".format(
                int(event.get("minute", 0)),
                scorer,
            )
            if assister:
                line += "，{} 送出助攻".format(assister)
            line += "（xG {:.2f}）".format(float(event.get("xg", 0) or 0))
            goal_lines.append(line)
        paragraphs.append("；".join(goal_lines) + "。")
    else:
        total_shots = int(home.get("shots", 0)) + int(away.get("shots", 0))
        if total_shots >= 20:
            paragraphs.append(
                "两队合计完成 {} 次射门，但门将和防线守住了全部机会。".format(
                    total_shots
                )
            )
        else:
            paragraphs.append("双方都没能持续制造清晰机会，禁区内的最后处理不足。")

    through_home = through_away = cross_home = cross_away = 0
    for event in result.events:
        event_tags = _tags(event)
        side = event.get("team_side")
        if "through_ball" in event_tags:
            if side == "home":
                through_home += 1
            else:
                through_away += 1
        if "cross" in event_tags:
            if side == "home":
                cross_home += 1
            else:
                cross_away += 1
    tactical_parts = []
    if through_home + through_away:
        tactical_parts.append(
            "直塞尝试 {}:{}".format(through_home, through_away)
        )
    if cross_home + cross_away:
        tactical_parts.append("传中 {}:{}".format(cross_home, cross_away))
    if tactical_parts:
        paragraphs.append(
            "进攻方式上，{}；两队在纵深与边路的选择存在明显差异。".format(
                "，".join(tactical_parts)
            )
        )

    home_xg = float(home.get("xg", 0) or 0)
    away_xg = float(away.get("xg", 0) or 0)
    if home_xg + away_xg > 0:
        xg_line = "预期进球为 {:.2f}:{:.2f}".format(home_xg, away_xg)
        home_delta = int(result.home_score) - home_xg
        away_delta = int(result.away_score) - away_xg
        if max(home_delta, away_delta) > 0.7:
            efficient = home_name if home_delta > away_delta else away_name
            xg_line += "，{} 的终结效率更高".format(efficient)
        elif min(home_delta, away_delta) < -0.8:
            wasteful = home_name if home_delta < away_delta else away_name
            xg_line += "，{} 没能兑现创造出的机会".format(wasteful)
        paragraphs.append(xg_line + "。")

    all_ratings = list(result.home_ratings or []) + list(result.away_ratings or [])
    if all_ratings:
        motm = max(all_ratings, key=lambda item: float(item.get("rating", 0) or 0))
        paragraphs.append(
            "{} 以 {:.1f} 分成为本场评分最高的球员。".format(
                motm.get("colored_name") or motm.get("name") or "球员",
                float(motm.get("rating", 0) or 0),
            )
        )

    return "\n".join(paragraphs)


def _display_width(text: str) -> int:
    width = 0
    skip_color = False
    for char in text:
        if skip_color:
            skip_color = False
            continue
        if char == "/":
            continue
        if char == "~":
            skip_color = True
            continue
        width += 2 if ord(char) > 127 else 1
    return width


def _stat_line(home_value: Any, label: str, away_value: Any, width: int = 10) -> str:
    home_text = str(home_value)
    away_text = str(away_value)
    label_width = 16
    left = " " * max(0, width - _display_width(home_text)) + home_text
    label_padding = max(0, label_width - _display_width(label))
    label_text = (
        " " * (label_padding // 2)
        + label
        + " " * (label_padding - label_padding // 2)
    )
    return "{}  {}  {}".format(left, label_text, away_text)


def _format_percent(value: Any) -> str:
    return "{:.1f}%".format(float(value or 0))


def _build_stats_text(result: Any, home_name: str, away_name: str) -> str:
    home = result.home_stats
    away = result.away_stats
    lines = [
        "[终场比分]",
        "主 {} {}:{} {} 客".format(
            home_name,
            result.home_score,
            result.away_score,
            away_name,
        ),
        "",
    ]
    goals = [
        event
        for event in result.events
        if event.get("event_type") == "shot" and event.get("outcome") == "goal"
    ]
    if goals:
        lines.append("[进球]")
        for event in goals:
            scorer = _identity_name(event.get("player"))
            assister = _identity_name(event.get("assist_player"))
            detail = "{}' {}".format(int(event.get("minute", 0)), scorer)
            if assister:
                detail += "（助攻：{}）".format(assister)
            lines.append(detail)
        lines.append("")

    home_pass_rate = home.get("pass_success_rate", 0)
    away_pass_rate = away.get("pass_success_rate", 0)
    rows = [
        (
            _format_percent(home.get("possession")),
            "稳定控制占比",
            _format_percent(away.get("possession")),
        ),
        (home.get("shots", 0), "射门", away.get("shots", 0)),
        (home.get("shots_on_target", 0), "射正", away.get("shots_on_target", 0)),
        (home.get("shots_in_box", 0), "禁区射门", away.get("shots_in_box", 0)),
        (home.get("passes", 0), "传球", away.get("passes", 0)),
        (_format_percent(home_pass_rate), "传球成功率", _format_percent(away_pass_rate)),
        (home.get("progressive_passes", 0), "推进传球", away.get("progressive_passes", 0)),
        (home.get("passes_into_final_third", 0), "进攻三区进入", away.get("passes_into_final_third", 0)),
        (home.get("passes_into_box", 0), "禁区进入", away.get("passes_into_box", 0)),
        (home.get("crosses", 0), "传中", away.get("crosses", 0)),
        (home.get("corners", 0), "角球", away.get("corners", 0)),
        (home.get("dribbles", 0), "成功过人", away.get("dribbles", 0)),
        (home.get("carries", 0), "带球推进", away.get("carries", 0)),
        (home.get("progressive_carries", 0), "推进带球", away.get("progressive_carries", 0)),
        (home.get("tackles", 0), "成功抢断", away.get("tackles", 0)),
        (home.get("interceptions", 0), "拦截", away.get("interceptions", 0)),
        (home.get("blocks", 0), "封堵", away.get("blocks", 0)),
        (home.get("clearances", 0), "解围", away.get("clearances", 0)),
        (home.get("pressures", 0), "逼抢", away.get("pressures", 0)),
        (home.get("turnovers", 0), "失去稳定控制", away.get("turnovers", 0)),
        (home.get("offsides", 0), "越位", away.get("offsides", 0)),
        (home.get("saves", 0), "扑救", away.get("saves", 0)),
        ("{:.2f}".format(float(home.get("xg", 0) or 0)), "xG", "{:.2f}".format(float(away.get("xg", 0) or 0))),
        (
            "{:.2f}".format(float(home.get("post_shot_xg", 0) or 0)),
            "射正前xG代理",
            "{:.2f}".format(float(away.get("post_shot_xg", 0) or 0)),
        ),
        (home.get("key_passes", 0), "关键传球", away.get("key_passes", 0)),
        (
            int(home.get("passes_into_box", 0) or 0)
            + int(home.get("carries_into_box", 0) or 0),
            "禁区进入合计",
            int(away.get("passes_into_box", 0) or 0)
            + int(away.get("carries_into_box", 0) or 0),
        ),
        (home.get("big_chances", 0), "xG≥0.30机会", away.get("big_chances", 0)),
    ]
    lines.append("[数据统计]")
    lines.extend(_stat_line(*row) for row in rows)
    return "\n".join(lines)


def build_match_presentation(
    result: Any,
    home_name: str,
    away_name: str,
) -> MatchPresentation:
    """Build every user-facing match view from one Rust result contract."""
    seed = int(getattr(result, "presentation_seed", 0) or 0)
    raw_events = list(getattr(result, "events", []) or [])
    raw_events.sort(key=lambda item: int(item.get("seq", 0)))
    return MatchPresentation(
        events=_present_events(raw_events, seed),
        broadcasts=_build_broadcasts(raw_events, seed, home_name, away_name),
        report=_build_report(result, home_name, away_name, seed),
        stats_text=_build_stats_text(result, home_name, away_name),
    )
