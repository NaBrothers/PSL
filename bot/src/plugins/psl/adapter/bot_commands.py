"""Bot adapter - thin layer between NoneBot framework and service layer.

This module demonstrates how NoneBot command handlers should be structured
after the refactoring is complete. Each handler:
1. Parses the command arguments
2. Calls the appropriate service method
3. Formats and sends the result via bot framework

The old kernel/*.py files can be gradually migrated to use this pattern.
"""

import asyncio
from utils.image import toImage
from engine.const import Const


async def handle_match_quick(matcher, user1, user2, seed=None):
    """Handle a quick match command - report + stats only."""
    from service.match_service import MatchService

    svc = MatchService()
    output = svc.run_match(user1, user2, seed=seed)

    await matcher.send(toImage(output.report_text))
    await matcher.send(toImage(output.stats_text))


async def handle_match_normal(matcher, user1, user2, seed=None):
    """Handle a normal match - full broadcast flow.

    For now this still delegates to the old Game.start() which handles
    the live broadcast batching. Once the broadcast logic is fully
    migrated to the presentation layer, this can use MatchService directly.
    """
    from engine.game import Game

    game = Game(matcher, user1, user2, seed=seed)
    await game.start(Const.MODE_NORMAL)


async def handle_match_silence(matcher, user1, user2, npc=-1, difficulty=0, seed=None):
    """Handle a silent match (used by league/challenge internally)."""
    from service.match_service import MatchService

    svc = MatchService()
    output = svc.run_match(user1, user2, npc=npc, difficulty=difficulty, seed=seed)
    return output.result
