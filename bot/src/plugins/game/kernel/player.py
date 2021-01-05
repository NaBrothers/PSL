from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.cqhttp import Bot, Event
from game.utils.database import *
from game.model.user import *
from game.model.card import *
from game.utils.image import *
from game.kernel.account import check_account

error_text = '''球员 ID：查看球员详细信息
球员 强化 主卡ID 副卡ID：升级球员卡，星级加一，保留主卡特性
球员 比较 ID ID：对比两个球员卡的能力
'''

player_menu = on_startswith(msg="球员", rule=to_me(), priority=1)


@player_menu.handle()
async def player_menu_handler(bot: Bot, event: Event, state: dict):
    user = await check_account(player_menu, event)
    args = str(event.message).split(" ")
    if len(args) == 4 and args[1] == "强化" and args[2].isdecimal() and args[3].isdecimal():
        await player_upgrade(user, args[2], args[3])
    elif len(args) == 4 and args[1] == "比较" and args[2].isdecimal() and args[3].isdecimal():
        await player_compare(args[2], args[3])
    elif len(args) == 2 and args[1].isdecimal():
        await player_detail(args[1])
    else:
        await player_menu.finish("格式错误！\n" + toImage(error_text), **{"at_sender": True})


async def player_detail(id):
    card = Card.getCardByID(id)
    if card == None:
        await player_menu.finish("找不到该球员！输入\"背包\"查看拥有的球员卡", **{"at_sender": True})
        return
    # img = getImage("/avatars/" + str(card.player.ID) + ".png")
    ret = ""
    ret += card.player.Position + " " + card.getNameWithColor() + " " + \
        str(card.overall) + "\n"
    for i in range(card.star):
        ret += "★"
    ret += " " + card.getStyle() + "\n"
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
    ret += printAbilityName(card, "GK扑救", "GK_Saving")+"\t" + printAbility(card, "GK_Saving") + "\t" + \
        printAbilityName(card, "GK站位", "GK_Positioning") + \
        "\t" + printAbility(card, "GK_Positioning") + "\n"
    ret += printAbilityName(card, "GK反应", "GK_Reaction") + \
        "\t" + printAbility(card, "GK_Reaction") + "\n"
    await player_menu.finish(toImage(ret), **{"at_sender": True})


def printAbilityName(card, name, ability):
    if card.player.Position in Const.GOALKEEPER:
        if ability in Const.GK_STYLE[card.style].keys():
            return "/~x" + name + "/"
    else:
        if ability in Const.STYLE[card.style].keys():
            return "/~x" + name + "/"
    return name


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


async def player_upgrade(user, id1, id2):
    card1 = Card.getCardByID(id1)
    card2 = Card.getCardByID(id2)
    if card1 == None or card1.user.qq != user.qq:
        await player_menu.finish("找不到主卡！", **{"at_sender": True})
        return
    if card2 == None or card1.user.qq != user.qq:
        await player_menu.finish("找不到副卡！", **{"at_sender": True})
        return
    ret = ""
    ret += "主卡：" + "[" + str(card1.id) + "] " + card1.format() + \
        "\n" + "副卡：" + "[" + str(card2.id) + "] " + card2.format() + "\n"
    if card1.player.ID != card2.player.ID:
        await player_menu.finish("强化失败：主卡和副卡球员不匹配" + toImage(ret), **{"at_sender": True})
        return
    if card1.star != 1 and card2.star != 1 and abs(card1.star - card2.star) != 1:
        await player_menu.finish("强化失败：主卡和副卡星级不匹配" + toImage(ret), **{"at_sender": True})
        return
    if card1.star == 10 or card2.star == 10:
        await player_menu.finish("强化失败：已达到星级上线" + toImage(ret), **{"at_sender": True})
        return
    target_star = max(card1.star, card2.star) + 1
    cost = Const.STARS[target_star]["cost"]
    if cost > user.money:
        await player_menu.finish("强化失败：余额不足" + toImage(ret + "需要球币：" + str(cost) + "\n剩余球币：" + str(user.money)), **{"at_sender": True})
        return
    cursor = g_database.cursor()
    cursor.execute("update cards set star = " +
                   str(target_star) + " where id = " + str(card1.id))
    cursor.execute("delete from cards where id = " + str(card2.id))
    user.spend(cost)
    card1 = Card.getCardByID(id1)
    ret += "=== 强化结果 ===\n" + \
        "[" + str(card1.id) + "] " + card1.format() + "\n"
    await player_menu.finish("强化成功！" + toImage(ret + "花费球币：" + str(cost) + "\n剩余球币：" + str(user.money)), **{"at_sender": True})


def printDifference(card1, card2, ability):
    diff = card2.ability[ability] - card1.ability[ability]
    ret = "/~"
    if diff > 0:
        ret += "g▲" + str(diff).ljust(3)
    elif diff < 0:
        ret += "r▼" + str(-diff).ljust(3)
    else:
        ret += "w  " + "".ljust(3)
    ret += "/"
    return ret


async def player_compare(id1, id2):
    card1 = Card.getCardByID(id1)
    card2 = Card.getCardByID(id2)
    if card1 == None:
        await player_menu.finish("找不到球员1！", **{"at_sender": True})
        return
    if card2 == None:
        await player_menu.finish("找不到球员2！", **{"at_sender": True})
        return
    ret = ""
    ret += "球员1：" + "[" + str(card1.id) + "] " + card1.format() + \
        "\n" + "球员2：" + "[" + str(card2.id) + "] " + card2.format() + "\n"
    ret += "终结\t" + printAbility(card1, "Finishing") + "\t" + printAbility(
        card2, "Finishing") + "\t" + printDifference(card1, card2, "Finishing") + "\t"
    ret += "远射\t" + printAbility(card1, "Long_Shot") + "\t" + printAbility(
        card2, "Long_Shot") + "\t" + printDifference(card1, card2, "Long_Shot") + "\n"
    ret += "短传\t" + printAbility(card1, "Short_Passing") + "\t" + printAbility(
        card2, "Short_Passing") + "\t" + printDifference(card1, card2, "Short_Passing") + "\t"
    ret += "长传\t" + printAbility(card1, "Long_Passing") + "\t" + printAbility(
        card2, "Long_Passing") + "\t" + printDifference(card1, card2, "Long_Passing") + "\n"
    ret += "盘带\t" + printAbility(card1, "Dribbling") + "\t" + printAbility(
        card2, "Dribbling") + "\t" + printDifference(card1, card2, "Dribbling") + "\t"
    ret += "速度\t" + printAbility(card1, "Speed") + "\t" + printAbility(
        card2, "Speed") + "\t" + printDifference(card1, card2, "Speed") + "\n"
    ret += "抢断\t" + printAbility(card1, "Tackling") + "\t" + printAbility(
        card2, "Tackling") + "\t" + printDifference(card1, card2, "Tackling") + "\t"
    ret += "防守\t" + printAbility(card1, "Defence") + "\t" + printAbility(
        card2, "Defence") + "\t" + printDifference(card1, card2, "Defence") + "\n"
    ret += "头球\t" + printAbility(card1, "Heading") + "\t" + printAbility(
        card2, "Heading") + "\t" + printDifference(card1, card2, "Heading") + "\t"
    ret += "球商\t" + printAbility(card1, "IQ") + "\t" + printAbility(
        card2, "IQ") + "\t" + printDifference(card1, card2, "IQ") + "\n"
    ret += "GK扑救\t" + printAbility(card1, "GK_Saving") + "\t" + printAbility(
        card2, "GK_Saving") + "\t" + printDifference(card1, card2, "GK_Saving") + "\t"
    ret += "GK站位\t" + printAbility(card1, "GK_Positioning") + "\t" + printAbility(
        card2, "GK_Positioning") + "\t" + printDifference(card1, card2, "GK_Positioning") + "\n"
    ret += "GK反应\t" + printAbility(card1, "GK_Reaction") + "\t" + printAbility(
        card2, "GK_Reaction") + "\t" + printDifference(card1, card2, "GK_Reaction") + "\t"
    await player_menu.finish(toImage(ret), **{"at_sender": True})
