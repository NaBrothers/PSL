from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.card import *
from game.utils.image import *
from game.kernel.account import check_account

player_detail = on_startswith(msg="球员", rule=to_me(), priority=1)


@player_detail.handle()
async def player_detail_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(player_detail, event)
    args = str(event.message).split(" ")
    if len(args) == 2 and args[1].isdecimal():
        card = Card.getCardByID(args[1])
        if card == None:
            await player_detail.finish("找不到该球员！输入\"背包\"查看拥有的球员卡", **{"at_sender": True})
            return
        # img = getImage("/avatars/" + str(card.player.ID) + ".png")
        ret = ""
        ret += card.player.Position + " " + card.getNameWithColor() + " " + \
            str(card.overall) + "\n"
        for i in range(card.star):
            ret += "★"
        ret += " " + Const.STYLE[card.style]["name"] + "\n"
        ret += str(card.player.Age) + "岁 " + str(Card.tocm(card.player.Height)
                                                 ) + "cm " + str(Card.tokg(card.player.Weight)) + "kg" + "\n"
        ret += printAbilityName(card, "终结", "Finishing")+"\t" + printAbility(card, "Finishing") + \
            "\t" + printAbilityName(card, "远射", "Long_Shot")+"\t" + \
            printAbility(card, "Long_Shot") + "\n"
        ret += printAbilityName(card, "短传", "Short_Passing")+"\t" + printAbility(card, "Short_Passing") + \
            "\t" + printAbilityName(card, "长传", "Long_Passing")+"\t" + \
            printAbility(card, "Long_Passing") + "\n"
        ret += printAbilityName(card, "盘带", "Dribbling")+"\t" + printAbility(card, "Dribbling") + \
            "\t" + printAbilityName(card, "速度", "Speed")+"\t" + \
            printAbility(card, "Speed") + "\n"
        ret += printAbilityName(card, "抢断", "Tackling")+"\t" + printAbility(card, "Tackling") + \
            "\t" + printAbilityName(card, "防守", "Defence")+"\t" + \
            printAbility(card, "Defence") + "\n"
        ret += printAbilityName(card, "头球", "Heading")+"\t" + printAbility(card, "Heading") + \
            "\t" + printAbilityName(card, "球商", "IQ")+"\t" + \
            printAbility(card, "IQ") + "\n"
        ret += printAbilityName(card, "守门", "GK")+"\t" + \
            printAbility(card, "GK") + "\n"
        await player_detail.finish(toImage(ret), **{"at_sender": True})
    else:
        await player_detail.finish("格式：球员 ID", **{"at_sender": True})


def printAbilityName(card, name, ability):
    if ability in Const.STYLE[card.style].keys():
        return "/~x" + name + "/"
    else:
        return name
    pass


def printAbility(card, ability):

    if card.ability[ability] >= 110:
        ret = ""
        colors = ["r", "g", "b"]
        letters = list(str(card.ability[ability]))
        for i in range(len(letters)):
            ret += "/~"
            ret += colors[i % 3]
            ret += letters[i]
        ret += "/"
        return ret

    ret = "/~"
    if card.ability[ability] >= 100:
        ret += "f"
    elif card.ability[ability] >= 95:
        ret += "r"
    elif card.ability[ability] >= 90:
        ret += "o"
    elif card.ability[ability] >= 88:
        ret += "p"
    elif card.ability[ability] >= 85:
        ret += "b"
    elif card.ability[ability] >= 82:
        ret += "g"
    else:
        ret += "w"
    ret += str(card.ability[ability])
    ret += "/"
    return ret
