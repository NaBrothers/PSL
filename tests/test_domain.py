"""Tests for psl_core pure computation - no DB required."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psl_core.constants import STARS, STYLE, GK_STYLE, REAL_ABILITY, FORMATION, FORWARD, GUARD
from psl_core.card import (
    compute_abilities, compute_real_overall, compute_overall,
    compute_price, get_name_with_color, get_style_name,
)
from psl_core.formation import compute_formation_abilities


def make_abilities(star=3, style="sniper", position="ST", ext=None, **overrides):
    defaults = dict(
        height=183, heading_accuracy=70, jumping=68, strength=69,
        long_shots=92, shot_power=86, finishing=93, long_passing=91,
        short_passing=91, dribbling=96, ball_control=96, balance=95,
        sliding_tackle=26, standing_tackle=37, defensive_awareness=32,
        aggression=44, interceptions=40, sprint_speed=80, acceleration=91,
        composure=96, gk_handling=11, gk_diving=6, gk_positioning=14,
        gk_reflexes=8, reactions=94,
    )
    defaults.update(overrides)
    return compute_abilities(star=star, style=style, position=position, ext_abilities=ext, **defaults)


class TestComputeAbilities:
    def test_star_bonus_increases(self):
        a1 = make_abilities(star=1)
        a5 = make_abilities(star=5)
        for key in a1:
            assert a5[key] >= a1[key]

    def test_style_bonus_applied(self):
        a_sniper = make_abilities(style="sniper")
        a_anchor = make_abilities(style="anchor")
        assert a_sniper["Finishing"] > a_anchor["Finishing"]
        assert a_anchor["Defence"] > a_sniper["Defence"]

    def test_ext_abilities(self):
        a_plain = make_abilities()
        a_ext = make_abilities(ext={"Speed": 5, "Finishing": 3})
        assert a_ext["Speed"] == a_plain["Speed"] + 5
        assert a_ext["Finishing"] == a_plain["Finishing"] + 3

    def test_gk_style(self):
        a = compute_abilities(
            star=3, style="ironwall", position="GK",
            height=190, heading_accuracy=50, jumping=60, strength=70,
            long_shots=20, shot_power=50, finishing=20, long_passing=70,
            short_passing=40, dribbling=20, ball_control=30, balance=50,
            sliding_tackle=10, standing_tackle=10, defensive_awareness=15,
            aggression=20, interceptions=10, sprint_speed=50, acceleration=45,
            composure=70, gk_handling=90, gk_diving=88, gk_positioning=85,
            gk_reflexes=91, reactions=90,
        )
        assert a["GK_Saving"] > 0
        assert get_style_name("ironwall", "GK") == "铁壁"


class TestComputeOverall:
    def test_includes_star(self):
        assert compute_overall(90, 3) == 90 + STARS[3]["ability"]

    def test_increases_with_star(self):
        assert compute_overall(90, 5) > compute_overall(90, 1)


class TestComputePrice:
    def test_positive(self):
        assert compute_price(93, 1, 0) > 0

    def test_scales_with_star(self):
        assert compute_price(90, 5, 0) > compute_price(90, 1, 0)

    def test_scales_with_breach(self):
        assert compute_price(90, 3, 3) > compute_price(90, 3, 0)


class TestComputeRealOverall:
    def test_position_matters(self):
        a = make_abilities()
        st_ov = compute_real_overall(a, "ST")
        gk_ov = compute_real_overall(a, "GK")
        assert st_ov > gk_ov + 10

    def test_position_mapping(self):
        a = make_abilities()
        assert compute_real_overall(a, "RS") == compute_real_overall(a, "ST")
        assert compute_real_overall(a, "LW") == compute_real_overall(a, "RW")


class TestGetNameWithColor:
    def test_rainbow(self):
        assert get_name_with_color("X", 90, 8).startswith("/~$")  # 90+8-1=97

    def test_pink(self):
        assert get_name_with_color("X", 90, 5).startswith("/~f")  # 90+5-1=94


class TestFormation:
    def test_all_formations_valid_shape(self):
        for name, data in FORMATION.items():
            positions = data["positions"]
            coords = data["coordinates"]
            assert len(positions) == 11, name
            assert len(coords) == 11, name
            assert positions[0] == "GK", name
            assert coords[0][1] == 100, name
            assert all(0 <= x <= 68 and 0 <= y <= 105 for x, y in coords), name
            for position, (_, y) in zip(positions, coords):
                if position in GUARD:
                    assert y >= 70, (name, position, y)
                if position in ("ST", "CF", "LW", "RW"):
                    assert y <= 28, (name, position, y)

    def test_compute_abilities_reasonable(self):
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]
        real_overalls = [85] * 11
        total, fwd, mid, grd = compute_formation_abilities(positions, real_overalls)
        assert total == 85 * 11
        assert fwd > 0
        assert mid > 0
        assert grd > 0

    def test_none_cards_handled(self):
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]
        real_overalls = [85] * 10 + [None]
        total, fwd, mid, grd = compute_formation_abilities(positions, real_overalls)
        assert total == 85 * 10
