"""Player operations service - upgrade and breakthrough."""

import sys
import os
import json
import random
from dataclasses import dataclass

BOT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bot", "src", "plugins", "psl")
if BOT_SRC not in sys.path:
    sys.path.insert(0, BOT_SRC)


class PlayerOpsError(Exception):
    pass


class PlayerOpsService:
    def __init__(self, db):
        self.db = db

    def upgrade(self, qq: int, main_id: int, sub_id: int) -> dict:
        from model.card import Card
        card1 = Card.getCardByID(main_id)
        card2 = Card.getCardByID(sub_id)
        if card1 is None or card1.user.qq != qq:
            raise PlayerOpsError("Main card not found or not owned")
        if card2 is None or card2.user.qq != qq:
            raise PlayerOpsError("Sub card not found or not owned")
        if card1.player.ID != card2.player.ID:
            raise PlayerOpsError("Cards must be same player")
        if (card1.star != 1 or card2.star != 1) and abs(card1.star - card2.star) != 1:
            raise PlayerOpsError("Star level mismatch")
        if card1.star == 10 or card2.star == 10:
            raise PlayerOpsError("Max star reached")

        target_star = max(card1.star, card2.star) + 1
        cost = int(max(card1.price, card2.price) * 0.1)

        from model.user import User
        user = User.getUserByQQ(qq)
        if user.money < cost:
            raise PlayerOpsError(f"Insufficient funds: need {cost}, have {user.money}")

        card1.set("star", target_star)
        card1.set("appearance", max(card1.appearance, card2.appearance))
        card1.set("goal", max(card1.goal, card2.goal))
        card1.set("assist", max(card1.assist, card2.assist))
        card1.set("tackle", max(card1.tackle, card2.tackle))
        card1.set("save", max(card1.save, card2.save))
        card1.set("total_appearance", card1.total_appearance + card2.total_appearance)
        card1.set("total_goal", card1.total_goal + card2.total_goal)
        card1.set("total_assist", card1.total_assist + card2.total_assist)
        card1.set("total_tackle", card1.total_tackle + card2.total_tackle)
        card1.set("total_save", card1.total_save + card2.total_save)

        from utils.database import g_database
        cursor = g_database.cursor()
        cursor.execute("delete from cards where id = " + str(card2.id))
        cursor.close()

        if card2.locked:
            card1.set("locked", True)
        user.spend(cost)

        return {"success": True, "new_star": target_star, "cost": cost, "remaining_money": user.money}

    def breach(self, qq: int, main_id: int, sub_id: int) -> dict:
        from model.card import Card
        from utils.const import Const
        card1 = Card.getCardByID(main_id)
        card2 = Card.getCardByID(sub_id)
        if card1 is None or card1.user.qq != qq:
            raise PlayerOpsError("Main card not found or not owned")
        if card2 is None or card2.user.qq != qq:
            raise PlayerOpsError("Sub card not found or not owned")
        if card1.player.ID != card2.player.ID:
            raise PlayerOpsError("Cards must be same player")

        for ability in card2.ext_abilities.keys():
            if ability in card1.ext_abilities:
                card1.ext_abilities[ability] += card2.ext_abilities[ability]
            else:
                card1.ext_abilities[ability] = card2.ext_abilities[ability]

        if card2.player.Position in Const.GOALKEEPER:
            random_ability = random.choice(list(Const.GK_ABILITIES))
        else:
            random_ability = random.choice(list(Const.ABILITIES))

        base_amount = Const.STARS[card2.star]["count"]
        addition_amount = 0
        abilities = Const.GK_STYLE[card2.style].keys() if card2.player.Position in Const.GOALKEEPER else Const.STYLE[card2.style].keys()
        if random_ability in abilities:
            addition_amount = Const.STARS[card2.star]["ability"]

        if random_ability in card1.ext_abilities:
            card1.ext_abilities[random_ability] += base_amount + addition_amount
        else:
            card1.ext_abilities[random_ability] = base_amount + addition_amount

        card1.set("ext_abilities", json.dumps(card1.ext_abilities))
        card1.set("breach", card1.breach + card2.breach + Const.STARS[card2.star]["count"])
        card1.set("total_appearance", card1.total_appearance + card2.total_appearance)
        card1.set("total_goal", card1.total_goal + card2.total_goal)
        card1.set("total_assist", card1.total_assist + card2.total_assist)
        card1.set("total_tackle", card1.total_tackle + card2.total_tackle)
        card1.set("total_save", card1.total_save + card2.total_save)

        from utils.database import g_database
        cursor = g_database.cursor()
        cursor.execute("delete from cards where id = " + str(card2.id))
        cursor.close()

        if card2.locked:
            card1.set("locked", True)

        ability_name = Const.GK_ABILITIES.get(random_ability, Const.ABILITIES.get(random_ability, random_ability))
        return {
            "success": True,
            "boosted_ability": ability_name,
            "boost_amount": base_amount + addition_amount,
            "style_bonus": addition_amount > 0,
        }
