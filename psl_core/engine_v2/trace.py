"""Debug trace output for match analysis (Phase 2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TraceEntry:
    """A single trace event."""
    tick: int
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchTrace:
    """Collects trace data for debugging and analysis."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    entries: List[TraceEntry] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True

    def log(self, tick: int, event_type: str, **kwargs):
        """Log a trace event."""
        if not self.enabled:
            return
        self.entries.append(TraceEntry(tick=tick, event_type=event_type, data=kwargs))

    def log_action(self, tick: int, team: str, player_name: str, action_type: str, **kwargs):
        """Log a player action."""
        self.log(tick, "action", team=team, player=player_name, action=action_type, **kwargs)

    def log_event(self, tick: int, event_type: str, **kwargs):
        """Log a match event (goal, save, aerial_contest, contested_won, etc.)."""
        self.log(tick, event_type, **kwargs)

    def log_decision(
        self,
        tick: int,
        team: str,
        player_idx: int,
        player_name: str,
        phase: str,
        chosen,
        alternatives: List = None,
        pos=None,
        goal=None,
    ):
        """Log a structured decision without mixing it into match events."""
        if not self.enabled:
            return
        payload = {
            "tick": tick,
            "team": team,
            "player_idx": player_idx,
            "player": player_name,
            "phase": phase,
            "chosen": chosen.to_dict() if hasattr(chosen, "to_dict") else chosen,
            "alternatives": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in (alternatives or [])
            ],
        }
        if pos is not None:
            payload["pos"] = list(pos)
        if goal is not None:
            payload["goal"] = goal
        self.decisions.append(payload)

    def to_dict(self) -> Dict:
        """Export trace as dictionary."""
        return {
            "trace_id": self.trace_id,
            "total_entries": len(self.entries),
            "entries": [
                {
                    "tick": e.tick,
                    "type": e.event_type,
                    **e.data,
                }
                for e in self.entries
            ],
            "decisions": self.decisions,
        }

    def summary(self) -> Dict:
        """Get a brief summary of the trace."""
        event_counts: Dict[str, int] = {}
        for e in self.entries:
            event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1
        return {
            "trace_id": self.trace_id,
            "total_entries": len(self.entries),
            "event_counts": event_counts,
        }

    def get_events_by_type(self, event_type: str) -> List[TraceEntry]:
        """Get all events of a specific type."""
        return [e for e in self.entries if e.event_type == event_type]

    def get_actions_by_type(self, action_type: str) -> List[TraceEntry]:
        """Get all action entries of a specific action type."""
        return [
            e for e in self.entries
            if e.event_type == "action" and e.data.get("action") == action_type
        ]
