from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.image import toImage
from game.kernel.account import check_account
from game.engine.game import Game
from game.model.user import User
game_matcher = on_startswith(msg="比赛", rule=to_me(), priority=1)

@game_matcher.handle()
async def game_matcher_handler(bot: Bot, event: Event, state: dict):
    await check_account(help_menu, event)
    user1 = User()
    user2 = User()
    game = Game(game_matcher, user1, user2)
    game.start()
