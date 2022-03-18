from nonebot import on_startswith
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import Bot, Event
from utils.database import *
from model.user import *
from model.card import *
from utils.image import *
from kernel.account import check_account

error_text = '''球员 ID：查看球员详细信息
球员 强化 主卡ID 副卡ID：升级球员卡，星级加一，保留主卡特性
球员 突破 主卡ID 副卡ID：主卡随机提升一项能力，加成数值为副卡当前星级所需卡量，副卡特性提供额外加成
球员 比较 ID ID：对比两个球员卡的能力
球员 锁定 [ID]：锁定球员，不可回收或转会，再次输入可进行解锁
'''

player_menu = on_startswith(msg="球员", rule=to_me(), priority=1)


@player_menu.handle()
async def player_menu_handler(bot: Bot, event: Event):
    user = await check_account(player_menu, event)
    args = str(event.message).split(" ")
    if len(args) == 4 and args[1] == "强化" and args[2].isdecimal() and args[3].isdecimal():
        await player_upgrade(user, args[2], args[3])
    elif len(args) == 4 and args[1] == "突破" and args[2].isdecimal() and args[3].isdecimal():
        await player_breach(user, args[2], args[3])
    elif len(args) == 4 and args[1] == "比较" and args[2].isdecimal() and args[3].isdecimal():
        await player_compare(args[2], args[3])
    elif len(args) == 2 and args[1].isdecimal():
        await player_detail(args[1])
    elif len(args) == 3 and args[1] == "锁定" and args[2].isdecimal():
        await player_lock(args[2])
    else:
        await player_menu.finish("格式错误！\n" + toImage(error_text), **{"at_sender": True})


async def player_lock(id):
    card = Card.getCardByID(id)
    if card == None:
        await player_menu.finish("找不到该球员！输入\"背包\"查看拥有的球员卡", **{"at_sender": True})
    if card.locked == False:
      card.set("locked", True)
      await player_menu.finish("球员已锁定", **{"at_sender": True})
    else:
      card.set("locked", False)
      await player_menu.finish("球员已解锁", **{"at_sender": True})
    

async def player_detail(id):
    card = Card.getCardByID(id)
    if card == None:
        await player_menu.finish("找不到该球员！输入\"背包\"查看拥有的球员卡", **{"at_sender": True})
        return
    # img = getImage("/avatars/" + str(card.player.ID) + ".png")
    ret = ""
    ret += "[" + str(card.id) + "] " + card.player.Position + " " + card.getNameWithColor() + " " + \
        str(card.overall) + "\n"
    for i in range(card.star):
        ret += "★"
    ret += " " + "◆+" + str(card.breach) + " " + card.getStyle() + "\n"
    overalls = card.getOveralls()
    ret += overalls[0][0] + "：" + card.printRealOverall(overalls[0][0]) + " "
    ret += overalls[1][0] + "：" + card.printRealOverall(overalls[1][0]) + " "
    ret += overalls[2][0] + "：" + card.printRealOverall(overalls[2][0]) + "\n"

    ret += str(card.player.Age) + "岁 " + str(card.player.Height) + "cm " + str(card.player.Weight) + "kg" + " 身价 $" + str(card.price) + "\n\n"

    string = '''     \t\tST\t\t
     LRW\tCF\tLRW\t
     \t\tAM\t
     LRM\tCM\tLRM\t
     \t\tDM\t
     LRB\tCB\tLRB\t
     \t\tGK\t
'''
    for overall in overalls:
      string = string.replace(overall[0], card.printRealOverall(overall[0]))
    ret += string + "\n"
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
        "\t" + printAbility(card, "GK_Reaction") + "\n\n"
    ret += "赛季：\n"
    ret += "出场 " + str(card.appearance) + " 进球 " + str(card.goal) + " 助攻 " + str(
        card.assist) + " 抢断 " + str(card.tackle) + " 扑救 " + str(card.save) + "\n"
    ret += "生涯：\n"
    ret += "出场 " + str(card.total_appearance) + " 进球 " + str(card.total_goal) + " 助攻 " + str(
        card.total_assist) + " 抢断 " + str(card.total_tackle) + " 扑救 " + str(card.total_save) + "\n"
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
    else:
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

    if ability in card.ext_abilities:
        ret += "/~g(+" + str(card.ext_abilities[ability]) + ")/"
    return ret.ljust(8)


async def player_upgrade(user, id1, id2):
    card1 = Card.getCardByID(id1)
    card2 = Card.getCardByID(id2)
    if card1 == None or card1.user.qq != user.qq:
        await player_menu.finish("找不到主卡！", **{"at_sender": True})
        return
    if card2 == None or card2.user.qq != user.qq:
        await player_menu.finish("找不到副卡！", **{"at_sender": True})
        return
    ret = ""
    ret += "主卡：" + "[" + str(card1.id) + "] " + card1.format() + \
        "\n" + "副卡：" + "[" + str(card2.id) + "] " + card2.format() + "\n"
    if card1.player.ID != card2.player.ID:
        await player_menu.finish("强化失败：主卡和副卡球员不匹配" + toImage(ret), **{"at_sender": True})
        return
    if (card1.star != 1 or card2.star != 1) and abs(card1.star - card2.star) != 1:
        await player_menu.finish("强化失败：主卡和副卡星级不匹配" + toImage(ret), **{"at_sender": True})
        return
    if card1.star == 10 or card2.star == 10:
        await player_menu.finish("强化失败：已达到星级上线" + toImage(ret), **{"at_sender": True})
        return
    target_star = max(card1.star, card2.star) + 1
    cost = int(max(card1.price, card2.price) * 0.1)
    if cost > user.money:
        await player_menu.finish("强化失败：余额不足" + toImage(ret + "需要球币：" + str(cost) + "\n剩余球币：" + str(user.money)), **{"at_sender": True})
        return
    if card1.status != 0 and card1.status != 2:
        await player_menu.finish("强化失败：主卡状态" + Const.STATUS["card1.status"], **{"at_sender": True})
    if card2.status != 0 and card2.status != 2:
        await player_menu.finish("强化失败：副卡状态" + Const.STATUS["card2.status"], **{"at_sender": True})
    cursor = g_database.cursor()
    card1.set("star", target_star)
    card1.set("appearance", max(card1.appearance, card2.appearance))
    card1.set("goal", max(card1.goal, card2.goal))
    card1.set("assist", max(card1.assist, card2.assist))
    card1.set("tackle", max(card1.tackle, card2.tackle))
    card1.set("save", max(card1.save, card2.save))
    card1.set("total_appearance", card1.total_appearance+ card2.total_appearance)
    card1.set("total_goal", card1.total_goal+ card2.total_goal)
    card1.set("total_assist", card1.total_assist+ card2.total_assist)
    card1.set("total_tackle", card1.total_tackle+ card2.total_tackle)
    card1.set("total_save", card1.total_save+ card2.total_save)
    cursor.execute("delete from cards where id = " + str(card2.id))
    if card2.locked:
      card1.set("locked", "True")
    user.spend(cost)
    card1 = Card.getCardByID(card1.id)
    ret += "=== 强化结果 ===\n" + \
        "[" + str(card1.id) + "] " + card1.format() + "\n"
    await player_menu.finish("强化成功！" + toImage(ret + "花费球币：" + str(cost) + "\n剩余球币：" + str(user.money)), **{"at_sender": True})

async def player_breach(user, id1, id2):
    card1 = Card.getCardByID(id1)
    card2 = Card.getCardByID(id2)
    if card1 == None or card1.user.qq != user.qq:
        await player_menu.finish("找不到主卡！", **{"at_sender": True})
        return
    if card2 == None or card2.user.qq != user.qq:
        await player_menu.finish("找不到副卡！", **{"at_sender": True})
        return
    ret = ""
    ret += "主卡：" + "[" + str(card1.id) + "] " + card1.format() + \
        "\n" + "副卡：" + "[" + str(card2.id) + "] " + card2.format() + "\n"
    if card1.player.ID != card2.player.ID:
        await player_menu.finish("强化失败：主卡和副卡球员不匹配" + toImage(ret), **{"at_sender": True})
        return
    if card1.status != 0 and card1.status != 2:
        await player_menu.finish("强化失败：主卡状态" + Const.STATUS["card1.status"], **{"at_sender": True})
    if card2.status != 0 and card2.status != 2:
        await player_menu.finish("强化失败：副卡状态" + Const.STATUS["card2.status"], **{"at_sender": True})

    for ability in card2.ext_abilities.keys():
        if ability in card1.ext_abilities:
            card1.ext_abilities[ability] += card2.ext_abilities[ability]
        else:
            card1.ext_abilities[ability] = card2.ext_abilities[ability]

    randomAbility = ""
    if card2.player.Position in Const.GOALKEEPER:
        randomAbility = random.choice(list(Const.GK_ABILITIES))
    else:
        randomAbility = random.choice(list(Const.ABILITIES))

    baseAmount = Const.STARS[card2.star]["count"]
    additionAmount = 0

    abilities = Const.GK_STYLE[card2.style].keys() if card2.player.Position in Const.GOALKEEPER else Const.STYLE[card2.style].keys()
    if randomAbility in abilities:
        additionAmount = Const.STARS[card2.star]["ability"]

    if randomAbility in card1.ext_abilities:
        card1.ext_abilities[randomAbility] += baseAmount + additionAmount
    else:
        card1.ext_abilities[randomAbility] = baseAmount + additionAmount

    card1.set("ext_abilities", json.dumps(card1.ext_abilities))
    card1.set("breach", card1.breach + + card2.breach + Const.STARS[card2.star]["count"])
    card1.set("appearance", max(card1.appearance, card2.appearance))
    card1.set("goal", max(card1.goal, card2.goal))
    card1.set("assist", max(card1.assist, card2.assist))
    card1.set("tackle", max(card1.tackle, card2.tackle))
    card1.set("save", max(card1.save, card2.save))
    card1.set("total_appearance", card1.total_appearance+ card2.total_appearance)
    card1.set("total_goal", card1.total_goal+ card2.total_goal)
    card1.set("total_assist", card1.total_assist+ card2.total_assist)
    card1.set("total_tackle", card1.total_tackle+ card2.total_tackle)
    card1.set("total_save", card1.total_save+ card2.total_save)
    cursor = g_database.cursor()
    cursor.execute("delete from cards where id = " + str(card2.id))
    if card2.locked:
      card1.set("locked", "True")
    card1 = Card.getCardByID(card1.id)

    add_ret = ""
    if additionAmount > 0:
        add_ret = "\n触发了副卡特性「" + Const.STYLE[card2.style]["name"] +"」的被动，额外提升了/~g" + str(additionAmount) + "/点能力值！"

    ret += "=== 突破结果 ===\n" + "[" + str(card1.id) + "] " + card1.format() + "\n" + \
    "「/~r" + (Const.GK_ABILITIES[randomAbility] if card1.player.Position in Const.GOALKEEPER else Const.ABILITIES[randomAbility]) + "/」提升了/~g" + \
        str(baseAmount) + "/点能力值！" + add_ret
    await player_menu.finish("突破成功！" + toImage(ret), **{"at_sender": True})

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
