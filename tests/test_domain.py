"""Tests for pure domain models - no DB required."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "bot" / "src" / "plugins" / "psl"
for path in (ROOT, PLUGIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from domain.player import PlayerData
from domain.card import CardData
from domain.user import UserData
from domain.formation import FormationData
from domain.constants import STARS, STYLE, GK_STYLE, REAL_ABILITY
from utils.const import Const


def make_player(**kwargs):
    defaults = dict(
        id=1, name="Test Player", age=30, overall=90, position="ST",
        height="183", weight="180lbs", nationality="Argentina", club="Barcelona",
        crossing=80, finishing=93, heading_accuracy=70, short_passing=91,
        volleys=85, dribbling=96, curve=93, fk_accuracy=94, long_passing=91,
        ball_control=96, acceleration=91, sprint_speed=80, agility=91,
        reactions=94, balance=95, shot_power=86, jumping=68, stamina=72,
        strength=69, long_shots=92, aggression=44, interceptions=40,
        positioning=94, vision=95, penalties=75, composure=96,
        defensive_awareness=32, standing_tackle=37, sliding_tackle=26,
        gk_diving=6, gk_handling=11, gk_kicking=15, gk_positioning=14, gk_reflexes=8,
    )
    defaults.update(kwargs)
    return PlayerData(**defaults)


def make_card(player=None, star=3, style="sniper", ext=None, breach=0):
    if player is None:
        player = make_player()
    return CardData(
        id=1, player=player, user_qq=10001, star=star, style=style,
        ext_abilities=ext or {}, breach=breach,
    )


class TestPlayerData:
    def test_price_positive_for_high_overall(self):
        p = make_player(overall=93)
        assert p.price > 0

    def test_price_increases_with_overall(self):
        p1 = make_player(overall=80)
        p2 = make_player(overall=90)
        assert p2.price > p1.price


class TestCardData:
    def test_ability_includes_star_bonus(self):
        card1 = make_card(star=1)
        card5 = make_card(star=5)
        for key in card1.ability:
            assert card5.ability[key] >= card1.ability[key]

    def test_ability_includes_style_bonus(self):
        card_sniper = make_card(style="sniper")
        card_anchor = make_card(style="anchor")
        # sniper boosts Finishing, anchor boosts Defence
        assert card_sniper.ability["Finishing"] > card_anchor.ability["Finishing"]
        assert card_anchor.ability["Defence"] > card_sniper.ability["Defence"]

    def test_ext_abilities_add_correctly(self):
        card = make_card(ext={"Speed": 5, "Finishing": 3})
        card_plain = make_card()
        assert card.ability["Speed"] == card_plain.ability["Speed"] + 5
        assert card.ability["Finishing"] == card_plain.ability["Finishing"] + 3

    def test_overall_includes_star(self):
        card = make_card(star=3)
        assert card.overall == 90 + STARS[3]["ability"]

    def test_price_scales_with_star(self):
        card1 = make_card(star=1)
        card5 = make_card(star=5)
        assert card5.price > card1.price

    def test_price_scales_with_breach(self):
        card0 = make_card(breach=0)
        card3 = make_card(breach=3)
        assert card3.price > card0.price

    def test_color_rainbow_for_high_overall(self):
        card = make_card(star=8)  # 90 + 8 - 1 = 97 => rainbow
        name = card.get_name_with_color()
        assert name.startswith("/~$")

    def test_color_pink_for_94_plus(self):
        card = make_card(star=5)  # 90 + 5 - 1 = 94 => pink
        name = card.get_name_with_color()
        assert name.startswith("/~f")

    def test_get_real_overall_position_matters(self):
        card = make_card()  # high finishing player
        st_ov = card.get_real_overall("ST")
        gk_ov = card.get_real_overall("GK")
        assert st_ov > gk_ov + 10

    def test_get_style_name(self):
        card = make_card(style="sniper")
        assert card.get_style_name() == "狙击手"

    def test_gk_style(self):
        gk_player = make_player(position="GK", gk_diving=88, gk_handling=90, gk_positioning=85, gk_reflexes=91)
        card = CardData(id=1, player=gk_player, user_qq=1, star=3, style="wall")
        assert card.ability["GK_Saving"] > 0
        assert card.get_style_name() == "铁壁"


class TestFormationData:
    def test_all_engine_formations_have_valid_shape(self):
        for name, data in Const.FORMATION.items():
            positions = data["positions"]
            coords = data["coordinates"]
            assert len(positions) == 11, name
            assert len(coords) == 11, name
            assert positions[0] == "GK", name
            assert coords[0][1] == 100, name
            assert all(0 <= x <= 68 and 0 <= y <= 105 for x, y in coords), name
            for position, (_, y) in zip(positions, coords):
                if position in Const.GUARD:
                    assert y >= 70, (name, position, y)
                if position in ("ST", "CF", "LW", "RW"):
                    assert y <= 28, (name, position, y)

    def test_is_valid_all_cards(self):
        cards = [make_card() for _ in range(11)]
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]
        coords = [(0, 0)] * 11
        f = FormationData("442", cards, positions, coords)
        assert f.is_valid()

    def test_is_valid_with_none(self):
        cards = [make_card() for _ in range(10)] + [None]
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]
        coords = [(0, 0)] * 11
        f = FormationData("442", cards, positions, coords)
        assert not f.is_valid()

    def test_get_abilities_reasonable(self):
        cards = [make_card() for _ in range(11)]
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]
        coords = [(0, 0)] * 11
        f = FormationData("442", cards, positions, coords)
        total, fwd, mid, grd = f.get_abilities()
        assert total > 0
        assert fwd > 0
        assert mid > 0
        assert grd > 0


class TestUserData:
    def test_creation(self):
        u = UserData(id=1, qq=10001, name="Test", money=5000)
        assert u.money == 5000
        assert u.formation == "442"
