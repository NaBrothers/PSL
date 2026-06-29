"""Player operations service - upgrade and breakthrough."""

import sys
import os
import json
import random
from dataclasses import dataclass

from psl_core.constants import STARS, STYLE, GK_STYLE, GOALKEEPER, ABILITIES, GK_ABILITIES
from psl_core.talent import revealed_count_for_star, get_talent_grade, get_dims

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
        from server.services.game_config import GameConfigService
        import server.database
        config = GameConfigService(server.database.db)
        cost_pct = config.get("upgrade.cost_percent") or 0.1
        cost = int(max(card1.price, card2.price) * cost_pct)

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

        card2.remove()

        if card2.locked:
            card1.set("locked", True)
        user.spend(cost)

        talent_revealed = None
        card1.ensure_talents()
        old_reveal = revealed_count_for_star(target_star - 1)
        new_reveal = revealed_count_for_star(target_star)
        if new_reveal > old_reveal:
            is_gk = card1.player.Position in GOALKEEPER
            dims = get_dims(is_gk)
            order = card1.talents_data["o"]
            newly_revealed_dim = order[new_reveal - 1]
            mult = card1.talents_data["t"][newly_revealed_dim]
            talent_revealed = {
                "dimension_name": dims[newly_revealed_dim]["name"],
                "grade": get_talent_grade(mult),
                "dim_index": newly_revealed_dim,
            }

        result = {"success": True, "new_star": target_star, "cost": cost, "remaining_money": user.money}
        if talent_revealed:
            result["talent_revealed"] = talent_revealed
        return result

    def breach(self, qq: int, main_id: int, sub_id: int) -> dict:
        from model.card import Card
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

        if card2.player.Position in GOALKEEPER:
            random_ability = random.choice(list(GK_ABILITIES))
        else:
            random_ability = random.choice(list(ABILITIES))

        base_amount = STARS[card2.star]["count"]
        addition_amount = 0
        abilities = GK_STYLE[card2.style].keys() if card2.player.Position in GOALKEEPER else STYLE[card2.style].keys()
        if random_ability in abilities:
            addition_amount = STARS[card2.star]["ability"]

        if random_ability in card1.ext_abilities:
            card1.ext_abilities[random_ability] += base_amount + addition_amount
        else:
            card1.ext_abilities[random_ability] = base_amount + addition_amount

        card1.set("ext_abilities", json.dumps(card1.ext_abilities))
        card1.set("breach", card1.breach + card2.breach + STARS[card2.star]["count"])
        card1.set("total_appearance", card1.total_appearance + card2.total_appearance)
        card1.set("total_goal", card1.total_goal + card2.total_goal)
        card1.set("total_assist", card1.total_assist + card2.total_assist)
        card1.set("total_tackle", card1.total_tackle + card2.total_tackle)
        card1.set("total_save", card1.total_save + card2.total_save)

        card2.remove()

        if card2.locked:
            card1.set("locked", True)

        ability_name = GK_ABILITIES.get(random_ability, ABILITIES.get(random_ability, random_ability))
        return {
            "success": True,
            "boosted_ability": ability_name,
            "boost_amount": base_amount + addition_amount,
            "style_bonus": addition_amount > 0,
        }

    def reroll_talent(self, qq: int, card_id: int, dim_index: int) -> dict:
        from model.card import Card
        from model.user import User
        from server.services.game_config import GameConfigService
        import server.database

        config = GameConfigService(server.database.db)
        reroll_cost = int(config.get("talent.reroll_cost"))
        reroll_max = int(config.get("talent.reroll_max"))

        card = Card.getCardByID(card_id)
        if card is None or card.user.qq != qq:
            raise PlayerOpsError("Card not found or not owned")

        card.ensure_talents()
        talents = card.talents_data

        if talents["rc"] >= reroll_max:
            raise PlayerOpsError(f"Reroll limit reached ({reroll_max})")

        order = talents["o"]
        revealed = talents["r"]
        reveal_position = None
        for i in range(revealed):
            if order[i] == dim_index:
                reveal_position = i
                break
        if reveal_position is None:
            raise PlayerOpsError("Dimension not yet revealed")

        user = User.getUserByQQ(qq)
        if user.money < reroll_cost:
            raise PlayerOpsError(f"Insufficient funds: need {reroll_cost}, have {user.money}")

        t_min = float(config.get("talent.min"))
        t_max = float(config.get("talent.max"))
        mean = float(config.get("talent.mean"))
        std = float(config.get("talent.std"))
        new_mult = round(max(t_min, min(t_max, random.gauss(mean, std))), 2)
        talents["t"][dim_index] = new_mult
        talents["rc"] += 1

        card.set("Talents", json.dumps(talents))
        card.talents_data = talents
        user.spend(reroll_cost)

        is_gk = card.player.Position in GOALKEEPER
        dims = get_dims(is_gk)
        new_grade = get_talent_grade(new_mult)

        return {
            "success": True,
            "dimension_name": dims[dim_index]["name"],
            "new_grade": new_grade,
            "reroll_count": talents["rc"],
            "reroll_max": reroll_max,
            "cost": reroll_cost,
            "remaining_money": user.money,
        }
