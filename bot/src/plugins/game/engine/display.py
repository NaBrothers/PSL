import random
from game.engine.player import Player


class Statement:
    SHOT_SHORT = [
        "【球员】眼睛盯着门将，【距离】米处找准角度拔脚怒射",
        "【球员】拼抢中失去重心，倒地之前将球捅了出去",
        "【球员】面对出击的门将，将球轻轻一挑",
        "【球员】面对出击的门将抬脚做出假动作，晃开角度，一脚【距离】米的射门",
        "【球员】背对球门脚后跟射门",
    ]

    SHOT_LONG = [
        "【球员】离球门【距离】米直接重炮轰门",
        "【球员】一脚【距离】米的搓射，皮球划出一个C字",
        "【球员】脚弓一抖，将球兜射出去",
        "【球员】面对守备左突右闪，晃出空当，一脚【距离】米的劲射",

    ]

    SHOT_HIGH = [
        "【球员】迎着来球，高高跃起，金头一甩，球重重砸向球门",
        "【球员】面对传中高高跃起，舒展身体倒挂金钩",
        "【球员】迎着来球一脚【距离】米的凌空斩，球路飘忽",
        "【球员】对着来球蝎子摆尾将球弹起攻门",
    ]

    SHOT_MISS = [
        "不是吧！球向着角旗区飞去",
        "皮球偏得离谱",
        "球如冲天炮般飞向看台",
        "看台观众得到了这个球",
        "球偏出左侧立柱",
        "球偏出右侧立柱",
        "球稍稍高出横梁",
        "就差一点点！球擦着立柱飞出",
        "球擦着横梁飞出，守门员惊出一身冷汗",
        "球弹在立柱上出了底线",
        "球重重砸向横梁弹了出去",

    ]

    GOAL = [
        "皮球应声入网",
        "球划出一道诡异的弧线，落入网窝",
        "【球员】鞭长莫及，皮球砸进球门",
        "【球员】黄油手了！皮球滚入网窝",
        "皮球砸在【球员】身上，折射入网",
        "此球只应天上有！【球员】望尘莫及",
        "皮球砸进死角",
        "球向着十分角飞去",
        "球轻轻滚进空门",
        "球在门线上被捞回来，但已经整体越过门线",

    ]

    DRIBBLING = [
        "【球员1】一个马赛回旋过掉了【球员2】",
        "【球员1】利用速度甩开了【球员2】",
        "【球员1】像坦克一般碾开了【球员2】",
        "【球员1】连踩数个单车，晃得【球员2】找不着北",
        "【球员1】将球轻轻一捅，从【球员2】双腿间穿过，精妙的穿裆过人！",
        "【球员1】漂亮的人球分过，【球员2】只能望球兴叹",
        "【球员1】一记绝妙的油炸丸子，轻巧地过掉了【球员2】",
    ]

    CONTROLLING = [
        "【球员】向【方位】大步趟球",
        "【球员】向【方位】边带球边观察队友",
        "【球员】向【方位】切入",

    ]

    TACKLING = [
        "【球员1】迎着来球凶狠放铲",
        "【球员1】卡住身位将球断下",
        "【球员1】提前预判拦截球路",
        "【球员1】跳起头球将球破坏出危险区域",
        "【球员1】从背后干净利落地将球铲下",
        "【球员1】一脚一字斩将球切出",
        "【球员1】利用强壮的身体将【球员2】撞开拿下皮球",

    ]

    SAVING = [
        "【球员】迅速横移，做出扑救",
        "【球员】高高跃起，将球摘下",
        "【球员】双拳出击，将球击出危险区域",
        "【球员】将球稳稳抱住，顺势倒地",
        "【球员】将球稳稳抱住，环顾四周",
        "球砸在门框上弹了回来，【球员】立刻将球压在身下",

    ]

    SAVING_FAILED = [
        "【球员】飞身扑救",
        "【球员】迅速倒地侧扑",
        "【球员】失去重心，无法做出有效扑救动作",
        "【球员】倒地用脚扑救",
        "【球员】呆若木鸡",
        "【球员】目送皮球飞过",
        "【球员】扑错方向了",

    ]

    INTERCEPTION = [
        "球被【球员】拦挡出去",
        "球打在【球员】身上偏出",
        "【球员】奋不顾身地封堵了这脚射门",
        "【球员】伸脚改变了球路",

    ]

    PASS_SHORT = [
        "【球员1】一脚短传给【球员2】",
        "【球员1】将球轻轻一捅，分给【球员2】",
        "【球员1】烫脚传球，立刻将球分给【球员2】",
        "【球员1】一脚【距离】米的直塞，传给【球员2】",
        "【球员1】脚后跟传给【球员2】",
        "【球员1】没有犹豫，立马传给了【球员2】",
        "【球员1】犹豫了一下，回传给【球员2】",
        "【球员1】没有找到好的机会，将球传给了【球员2】",
        "【球员1】巧妙地将球漏给【球员2】",
        "【球员1】穿针引线，球从防守队员夹缝中传给了【球员2】",

    ]

    PASS_LONG = [
        "【球员1】一记【距离】米的长传，将球分给无人防守的【球员2】",
        "【球员1】精确制导，皮球划过【距离】米的弧线飞向【球员2】",
        "【球员1】一脚秒到毫颠的【距离】米长传，直奔【球员2】而去",
        "【球员1】抬头观察了一下队友的位置，一个大脚传给【球员2】",
        "【球员1】发现【球员2】的位置极佳，没有犹豫，一脚【距离】米的长传直奔他而去",
        "【球员1】摆脱防守队员，一脚长传找到【球员2】",
        "【球员1】一记绝妙的挑球，绕开防守队员直接传给【球员2】",

    ]


class Display:
    def print_short_shot(player, distance):
        string = random.choice(Statement.SHOT_SHORT)
        string = string.replace("【球员】", player.coach +
                                " " + player.getName() + " ")
        string = string.replace("【距离】", str(distance))
        return string

    def print_long_shot(player, distance):
        string = random.choice(Statement.SHOT_LONG)
        string = string.replace("【球员】", player.coach +
                                " " + player.getName() + " ")
        string = string.replace("【距离】", str(distance))
        return string

    def print_miss_shot():
        string = random.choice(Statement.SHOT_MISS)
        return string

    def print_goal(player, gk):
        string1 = random.choice(Statement.SAVING_FAILED)
        string1 = string1.replace("【球员】", gk.coach + " " + gk.getName() + " ")
        string2 = random.choice(Statement.GOAL)
        string2 = string2.replace("【球员】", gk.coach + " " + gk.getName() + " ")
        string3 = player.coach + " " + player.getName() + " 破门了！！！"
        string = string1 + "\n" + string2 + "\n" + string3
        return string

    def print_dribbling(offence, defence):
        string = random.choice(Statement.DRIBBLING)
        string = string.replace(
            "【球员1】", offence.coach + " " + offence.getName() + " ")
        string = string.replace(
            "【球员2】", defence.coach + " " + defence.getName() + " ")
        return string

    def print_controlling(player, direction):
        string = random.choice(Statement.CONTROLLING)
        string = string.replace("【球员】", player.coach +
                                " " + player.getName() + " ")
        string = string.replace("【方位】", direction)
        return string

    def print_tackling(offence, defence):
        string = random.choice(Statement.TACKLING)
        string = string.replace(
            "【球员2】", offence.coach + " " + offence.getName() + " ")
        string = string.replace(
            "【球员1】", defence.coach + " " + defence.getName() + " ")
        return string

    def print_saving(gk):
        string = random.choice(Statement.SAVING)
        string = string.replace("【球员】", gk.coach + " " + gk.getName() + " ")
        return string

    def print_interception(player):
        string = random.choice(Statement.INTERCEPTION)
        string = string.replace("【球员】", player.coach +
                                " " + player.getName() + " ")
        return string

    def print_high_shot(player):
        string = random.choice(Statement.SHOT_HIGH)
        string = string.replace("【球员】", player.coach +
                                " " + player.getName() + " ")
        return string

    def print_short_pass(player1, player2, distance):
        string = random.choice(Statement.PASS_SHORT)
        string = string.replace("【球员1】", player1.coach + " " + player1.getName() + " ")
        string = string.replace("【球员2】", " " +player2.getName() + " ")
        string = string.replace("【距离】", str(distance))
        return string

    def print_long_pass(player1, player2, distance):
        string = random.choice(Statement.PASS_LONG)
        string = string.replace("【球员1】", player1.coach + " " + player1.getName() + " ")
        string = string.replace("【球员2】", " " +player2.getName() + " ")
        string = string.replace("【距离】", str(distance))
        return string
