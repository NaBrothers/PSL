import random
from engine.player import Player


class Statement:
    SHOT_SHORT = [
        "【球员】眼睛盯着门将，找准角度拔脚怒射",
        "【球员】拼抢中失去重心，倒地之前将球捅了出去",
        "【球员】面对出击的门将，将球轻轻一挑",
        "【球员】面对出击的门将抬脚做出假动作，晃开角度射门",
        "【球员】背对球门脚后跟射门",
        "【球员】要进球了",
        "【球员】倚住防守球员，一脚巧射",
        "【球员】试着在角度不大的情况下打门",
        "没人盯防【球员】",
        "【球员】拍马赶到，抢点射门",
        "【球员】反越位成功，直接面对门将射门",
        "【球员】小角度射门",
        "【球员】觅得破门良机",
        "【球员】抢在防守球员之前将球射出",
        "虽然角度很偏，但【球员】仍然打出了一记高质量的射门",
        "【球员】打出了角度极为刁钻的射门",
        "【球员】处于一个相当有威胁的位置",
        "【球员】抬脚射门",
        "【球员】试着在角度不大的情况下打门",
    ]

    SHOT_LONG = [
        "【球员】离球门很远的距离直接重炮轰门",
        "【球员】一脚搓射，皮球划出一个C字",
        "【球员】脚弓一抖，将球兜射出去",
        "【球员】面对守备左突右闪，晃出空挡一脚劲射",
        "【球员】一记凌空抽射",
        "【球员】侧身凌空射门",
        "【球员】化身云中飞人，球到人到",
        "【球员】踢出一记远距离的弧线球",
        "【球员】尝试直接起脚射门",
        "虽然距离很远，但【球员】仍然打出了一记高质量的射门",
    ]

    SHOT_HIGH = [
        "【球员】迎着来球，高高跃起，金头一甩，球重重砸向球门",
        "【球员】面对传中高高跃起，舒展身体倒挂金钩",
        "【球员】迎着来球一脚凌空斩，球路飘忽",
        "【球员】对着来球蝎子摆尾将球弹起攻门",
        "【球员】头球攻门",
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
        "如果这球进了，那将是一次精彩的个人表演",
        "射门不够干脆，打偏了",
        "但是他将球打偏了",
        "但是他的射门与球员相距甚远",
        "他望着远去的皮球拍了拍胸脯",
        "他看着皮球飞出底线庆幸球打偏了",
        "他把球打到了边网上",
        "这本该是一个精彩进球",
        "他错失良机，懊悔不已",
        "但是没有打正球门",
        "球打歪了！",
        "观众们都为这个没有打进的球扼腕叹息",
        "球滚进球网，但同时哨声响起！犯规在先，进球无效",
        "这球看起来就跟进了一样",
        "他的表演毁于最后一脚",
        "他错失了绝佳机会",
        "我的奶奶来都能打进这个进球！",

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
        "这球进了！一连串的配合和最后一击都是如此完美！",
    ]

    DRIBBLING = [
        "【球员1】一个马赛回旋过掉了【球员2】",
        "【球员1】利用速度甩开了【球员2】",
        "【球员1】像坦克一般碾开了【球员2】",
        "【球员1】连踩数个单车，晃得【球员2】找不着北",
        "【球员1】将球轻轻一捅，从【球员2】双腿间穿过，精妙的穿裆过人！",
        "【球员1】漂亮的人球分过，【球员2】只能望球兴叹",
        "【球员1】一记绝妙的油炸丸子，轻巧地过掉了【球员2】",
        "前面一片无人区，【球员1】大步趟球",
        "【球员1】长驱直入，防守球员追到怀疑人生",
        "【球员1】和【球员2】做了次二过一配合",
        "【球员1】带球从【球员2】身边闪了过去",
        "【球员1】反越位成功，一路长驱直入",
        "【球员1】一骑绝尘",
        "【球员1】漂亮地摆脱了防守，为自己赢得了充裕的发挥空间",
        "【球员1】持续带球",
        "【球员1】眼前一片开阔地",
        "【球员1】抢在防守球员关门之前钻了出来",
        "【球员1】展现出扎实的盘带功夫",
        "【球员1】的控球令人赞叹",

    ]

    CONTROLLING = [
        "【球员】向【方位】大步趟球",
        "【球员】向【方位】边带球边观察队友",
        "【球员】向【方位】切入",
        "【球员】不着急着出球",
        "【球员】把节奏控制下来",
        "【球员】看上去无人能挡",
        "【球员】组织进攻",
        "【球员】开始反击",
        "【球员】干劲十足",
        "【球员】停下脚步观察队友跑位",
        "【球员】在观察场上局势",
        "【球员】开始拖延时间",

    ]

    TACKLING = [
        "【球员1】迎着来球凶狠放铲",
        "【球员1】卡住身位将球断下",
        "【球员1】提前预判拦截球路",
        "【球员1】跳起头球将球破坏出危险区域",
        "【球员1】从背后干净利落地将球铲下",
        "【球员1】一脚一字斩将球切出",
        "【球员1】利用强壮的身体将【球员2】撞开拿下皮球",
        "【球员1】抢断了【球员2】的球",
        "【球员1】很好地补位并把球铲断了",
        "【球员1】起跳高过【球员2】顶到球",
        "【球员1】在【球员2】头顶上将球顶走",
        "【球员1】迎球大脚解围",
        "【球员1】控制住球",
        "【球员1】中途将球截下",
        "【球员1】向【球员2】飞铲过去",
        "【球员2】在和【球员1】的拼抢中败下阵来",
        "【球员1】和【球员2】拼速度抢到这个球",
        "【球员1】的铲球非常漂亮，他轻松断下了【球员2】的球",
        "【球员1】的滑铲恰到好处",
        "【球员1】漂亮地将球踢出危险区域",
        "【球员1】包办了所有高空球的处理",
        "【球员2】在和【球员1】拼身体中失去优势",
        "【球员1】优秀的防守转换了球权",
        "【球员1】凭借良好的防守断下来球",
        "【球员1】跳的比【球员2】高",
        "【球员1】卡住了【球员2】",
        "【球员1】一次标准的铲球，轻松地将【球员2】的球断掉",
        "【球员1】破坏了这次传球",

    ]

    SAVING = [
        "【球员】迅速横移，做出扑救",
        "【球员】高高跃起，将球摘下",
        "【球员】双拳出击，将球击出危险区域",
        "【球员】将球稳稳抱住，顺势倒地",
        "【球员】将球稳稳抱住，环顾四周",
        "球砸在门框上弹了回来，【球员】立刻将球压在身下",
        "【球员】将球接住",
        "【球员】单手轻松将球没收",
        "【球员】将球托出横梁",
        "【球员】将球拍走",
        "【球员】漂亮地把球扑出",
        "【球员】稳妥地把球挡了出去",
        "【球员】一个精彩的侧扑将球接住",
        "【球员】做出漂亮扑救，他有身体化解了这次射门",
        "【球员】做出一个教科书般的扑救",
        "这球射的精彩，扑的更优秀",
        "【球员】扑出这记势大力沉的射门，手还隐隐作麻",
        "球打在门柱上弹了出去",

    ]

    SAVING_FAILED = [
        "【球员】飞身扑救",
        "【球员】迅速倒地侧扑",
        "【球员】失去重心，无法做出有效扑救动作",
        "【球员】倒地用脚扑救",
        "【球员】呆若木鸡",
        "【球员】目送皮球飞过",
        "【球员】扑错方向了",
        "【球员】故意漏出一侧空挡给对手，然而他已经无力阻止进球了",

    ]

    INTERCEPTION = [
        "球被【球员】拦挡出去",
        "球打在【球员】身上偏出",
        "【球员】奋不顾身地封堵了这脚射门",
        "【球员】伸脚改变了球路",
        "【球员】挡住了这记射门",
        "【球员】奉献了一次特里式防守",
        "【球员】最后一拼漂亮地将球铲走",
        "球砸在【球员】身上弹开了",

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
        "【球员1】将球向前传给跑位中的【球员2】",
        "【球员1】看到前面的【球员2】把球传了过去",
        "【球员1】第一时间将球传给前面的【球员2】",
        "【球员1】看到【距离】米外的【球员2】，将球传过去",
        "【球员1】传出一脚漂亮的球给到【球员2】",
        "【球员1】接球后迅速传给【球员2】",
        "【球员1】和【球员2】配合精妙绝伦，对方根本碰不到球",
        "【球员1】将球传给处于威胁位置的【球员2】",
        "【球员1】将球传给前来接应的【球员2】",
        "【球员1】一记传球",
        "【球员1】传给【球员2】",
        "【球员1】第一时间传出一记地滚球给到【球员2】",
        "【球员1】接球后迅速把球交给【球员2】",
        "【球员1】不等球落地直接传给【球员2】",

    ]

    PASS_LONG = [
        "【球员1】一记【距离】米的长传，将球分给无人防守的【球员2】",
        "【球员1】精确制导，皮球划过【距离】米的弧线飞向【球员2】",
        "【球员1】一脚秒到毫颠的【距离】米长传，直奔【球员2】而去",
        "【球员1】抬头观察了一下队友的位置，一个大脚传给【球员2】",
        "【球员1】发现【球员2】的位置极佳，没有犹豫，一脚【距离】米的长传直奔他而去",
        "【球员1】摆脱防守队员，一脚长传找到【球员2】",
        "【球员1】一记绝妙的挑球，绕开防守队员直接传给【球员2】",
        "【球员1】半高球传给边路的【球员2】",
        "【球员1】试图从边路传中到近门柱",
        "【球员1】试图从边路传中到远门柱",
        "【球员1】低平球传中到近门柱",
        "【球员1】低平球传中到远门柱",
        "【球员1】发现【球员2】在前面，第一时间传球给他",
        "【球员1】中距离传球找【球员2】",
        "【球员1】将球给到【球员2】前方",
        "【球员1】传中",
        "【球员1】轻描淡写地把球传到【球员2】脚下",
        "【球员1】把球踢到在边路附近游走的【球员2】",
        "【球员1】横传把球传进禁区",
        "【球员1】用高球踢向前面",

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

    def print_goal(player, gk, assister):
        string1 = random.choice(Statement.SAVING_FAILED)
        string1 = string1.replace("【球员】", gk.coach + " " + gk.getName() + " ")
        string2 = random.choice(Statement.GOAL)
        string2 = string2.replace("【球员】", gk.coach + " " + gk.getName() + " ")
        string3 = player.coach + " " + player.getName() + " 破门了！！！"
        if assister:
          string3 += "来自 " + assister.getName() + " 的助攻"
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
