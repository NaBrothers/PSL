"""Match service - orchestrates engine, presentation, and output.

This is the primary entry point for running matches. It:
1. Loads team data (via existing Team class for now)
2. Runs the pure simulation engine
3. Formats output via presentation layer
4. Returns structured data that adapters can send however they want
"""

from dataclasses import dataclass, field
from typing import List, Optional
from engine.types import MatchResult


@dataclass
class MatchOutput:
    """Everything an adapter needs to display a match result."""
    result: MatchResult
    report_text: str
    stats_text: str
    broadcast_lines: List[str] = field(default_factory=list)


class MatchService:
    def run_match(self, user1, user2, npc=-1, difficulty=0, seed=None) -> MatchOutput:
        """Run a complete match and return formatted output. No IO."""
        from engine.game import Game
        game = Game(None, user1, user2, npc=npc, difficulty=difficulty, seed=seed)
        result = game.run_simulation()
        presentation = game.match_presentation

        return MatchOutput(
            result=result,
            report_text="[比赛战报]\n" + presentation.report,
            stats_text=presentation.stats_text,
            broadcast_lines=[
                "\n".join(lines) for lines in presentation.broadcasts
            ],
        )

    def run_match_with_broadcasts(self, user1, user2, npc=-1, difficulty=0, seed=None) -> MatchOutput:
        """Run a match with live broadcast lines (for normal mode display)."""
        output = self.run_match(user1, user2, npc=npc, difficulty=difficulty, seed=seed)
        return output
