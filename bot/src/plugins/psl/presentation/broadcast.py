"""Format match events into batched broadcast messages.

Input: list[MatchEvent] (from MatchResult)
Output: list[str] - each string is one broadcast batch
"""

from typing import List
from engine.types import MatchResult, MatchEvent


BROADCAST_INTERVAL = 270


def format_broadcasts(result: MatchResult) -> List[str]:
    """Group events into time-windowed batches suitable for sequential display."""
    messages = []
    buffer = []
    last_time = 0

    for ev in result.events:
        game_time = ev.minute * 60 + ev.second
        if ev.importance >= 3 or game_time - last_time >= BROADCAST_INTERVAL:
            if buffer:
                messages.append("\n".join(buffer))
                buffer = []
            last_time = game_time

        if ev.importance >= 3:
            half = "上半时" if ev.minute < 45 else "下半时"
            minute = ev.minute if ev.minute < 45 else ev.minute - 45
            prefix = f"主{ev.home_score}:{ev.away_score}客 {half}{minute}:{ev.second}"
            buffer.append(f"{prefix} {ev.text}")

    if buffer:
        messages.append("\n".join(buffer))

    return messages
