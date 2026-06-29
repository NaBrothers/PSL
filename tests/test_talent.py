"""Tests for the talent system (psl_core/talent.py and integration)."""

import json
import random
import pytest

from psl_core.talent import (
    generate_talents,
    revealed_count_for_star,
    get_talent_grade,
    get_talent_grade_color,
    get_average_grade,
    ability_to_talent_index,
    get_talent_multiplier_for_ability,
    format_talents_bot,
    get_talent_display,
    FIELD_TALENT_DIMS,
    GK_TALENT_DIMS,
)
from psl_core.card import compute_abilities


class TestGenerateTalents:
    def test_structure(self):
        t = generate_talents()
        assert "t" in t and len(t["t"]) == 6
        assert "o" in t and len(t["o"]) == 6
        assert "r" in t and t["r"] == 1
        assert "rc" in t and t["rc"] == 0

    def test_range(self):
        rng = random.Random(42)
        for _ in range(100):
            t = generate_talents(rng=rng)
            for val in t["t"]:
                assert 0.5 <= val <= 1.5

    def test_order_is_permutation(self):
        t = generate_talents()
        assert sorted(t["o"]) == [0, 1, 2, 3, 4, 5]

    def test_custom_params(self):
        t = generate_talents(mean=1.2, std=0.1, t_min=0.8, t_max=1.4)
        for val in t["t"]:
            assert 0.8 <= val <= 1.4


class TestRevealedCountForStar:
    def test_star_1(self):
        assert revealed_count_for_star(1) == 1

    def test_star_6(self):
        assert revealed_count_for_star(6) == 6

    def test_star_10(self):
        assert revealed_count_for_star(10) == 6

    def test_star_0(self):
        assert revealed_count_for_star(0) == 0


class TestGetTalentGrade:
    def test_grade_sss(self):
        assert get_talent_grade(1.5) == "SSS"
        assert get_talent_grade(1.47) == "SSS"

    def test_grade_ss(self):
        assert get_talent_grade(1.46) == "SS"
        assert get_talent_grade(1.4) == "SS"

    def test_grade_s(self):
        assert get_talent_grade(1.39) == "S"
        assert get_talent_grade(1.3) == "S"

    def test_grade_a(self):
        assert get_talent_grade(1.29) == "A"
        assert get_talent_grade(1.1) == "A"

    def test_grade_b(self):
        assert get_talent_grade(1.09) == "B"
        assert get_talent_grade(0.9) == "B"

    def test_grade_c(self):
        assert get_talent_grade(0.89) == "C"
        assert get_talent_grade(0.7) == "C"

    def test_grade_d(self):
        assert get_talent_grade(0.69) == "D"
        assert get_talent_grade(0.5) == "D"


class TestAbilityToTalentIndex:
    def test_field_finishing(self):
        assert ability_to_talent_index("Finishing", False) == 0

    def test_field_speed(self):
        assert ability_to_talent_index("Speed", False) == 4

    def test_field_dribbling(self):
        assert ability_to_talent_index("Dribbling", False) == 2

    def test_gk_saving(self):
        assert ability_to_talent_index("GK_Saving", True) == 0

    def test_gk_positioning(self):
        assert ability_to_talent_index("GK_Positioning", True) == 1

    def test_unknown_ability(self):
        assert ability_to_talent_index("NonExistent", False) == -1


class TestComputeAbilitiesWithTalents:
    COMMON_STATS = dict(
        position="ST", height=180,
        heading_accuracy=80, jumping=80, strength=80,
        long_shots=80, shot_power=80, finishing=90,
        long_passing=70, short_passing=85, dribbling=88,
        ball_control=90, balance=80, sliding_tackle=30,
        standing_tackle=35, defensive_awareness=30,
        aggression=60, interceptions=30, sprint_speed=90,
        acceleration=92, composure=85, gk_handling=10,
        gk_diving=10, gk_positioning=10, gk_reflexes=10,
        reactions=85,
    )

    def test_backward_compat_no_talents(self):
        r1 = compute_abilities(star=5, style="hunter", ext_abilities={}, **self.COMMON_STATS)
        r2 = compute_abilities(star=5, style="hunter", ext_abilities={}, talents=None, **self.COMMON_STATS)
        assert r1 == r2

    def test_talent_only_affects_star_bonus(self):
        talents = {"t": [1.5, 1.5, 1.5, 1.5, 1.5, 1.5], "o": [0,1,2,3,4,5], "r": 6, "rc": 0}
        r_with = compute_abilities(star=1, style="hunter", ext_abilities={}, talents=talents, **self.COMMON_STATS)
        r_without = compute_abilities(star=1, style="hunter", ext_abilities={}, **self.COMMON_STATS)
        # star 1 has bonus 0, so talent multiplier changes nothing
        assert r_with == r_without

    def test_talent_amplifies_star_bonus(self):
        talents_high = {"t": [1.5, 1.5, 1.5, 1.5, 1.5, 1.5], "o": [0,1,2,3,4,5], "r": 6, "rc": 0}
        talents_low = {"t": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5], "o": [0,1,2,3,4,5], "r": 6, "rc": 0}
        r_high = compute_abilities(star=10, style="hunter", ext_abilities={}, talents=talents_high, **self.COMMON_STATS)
        r_low = compute_abilities(star=10, style="hunter", ext_abilities={}, talents=talents_low, **self.COMMON_STATS)
        # star 10 bonus is 21; high=31, low=10 -> diff of 21 per dimension
        assert r_high["Finishing"] > r_low["Finishing"]
        assert r_high["Speed"] > r_low["Speed"]

    def test_display_mode_hides_unrevealed(self):
        # star=1 -> only 1 dim revealed (order[0]=0, so shooting is revealed)
        talents = {"t": [1.5, 0.5, 1.0, 1.0, 1.0, 1.0], "o": [0,1,2,3,4,5], "r": 1, "rc": 0}
        r_display = compute_abilities(star=2, style="hunter", ext_abilities={}, talents=talents, talent_mode="display", **self.COMMON_STATS)
        r_engine = compute_abilities(star=2, style="hunter", ext_abilities={}, talents=talents, talent_mode="engine", **self.COMMON_STATS)
        # Dimension 0 (shooting) is revealed at star 2 (revealed=2, order[0]=0 and order[1]=1)
        # Actually star=2 reveals 2 dims, so both 0 and 1 are revealed. Use star=1.
        # star=1 -> revealed=1, only order[0]=0 (shooting)
        r_display1 = compute_abilities(star=3, style="hunter", ext_abilities={}, talents=talents, talent_mode="display", **self.COMMON_STATS)
        r_engine1 = compute_abilities(star=3, style="hunter", ext_abilities={}, talents=talents, talent_mode="engine", **self.COMMON_STATS)
        # star=3 reveals 3 dims: order[0..2] = 0,1,2. Dim 3 (defending) is unrevealed.
        # defending maps to Tackling/Defence. t[3]=1.0, so no diff. Use a better example:
        talents2 = {"t": [1.5, 0.5, 1.0, 0.5, 1.0, 1.0], "o": [0,1,2,3,4,5], "r": 0, "rc": 0}
        r_d = compute_abilities(star=2, style="hunter", ext_abilities={}, talents=talents2, talent_mode="display", **self.COMMON_STATS)
        r_e = compute_abilities(star=2, style="hunter", ext_abilities={}, talents=talents2, talent_mode="engine", **self.COMMON_STATS)
        # star=2 -> revealed=2, order[0:2]=[0,1]. Dim 3 (defending, Tackling/Defence) unrevealed.
        # display: Tackling uses mult=1.0, engine uses mult=0.5
        assert r_d["Tackling"] > r_e["Tackling"]


class TestTalentDisplay:
    def test_get_talent_display(self):
        talents = {"t": [1.4, 0.8, 1.0, 0.6, 1.2, 0.9], "o": [0,3,1,5,4,2], "r": 3, "rc": 0}
        display = get_talent_display(talents, False, star=3)
        assert len(display) == 6
        # Fixed order: shooting, passing, dribbling, defending, speed, iq
        assert display[0]["revealed"] is True
        assert display[0]["grade"] == "SS"  # t[0]=1.4
        assert display[1]["revealed"] is True
        assert display[1]["grade"] == "C"  # t[1]=0.8
        assert display[2]["revealed"] is False  # dribbling not in revealed set
        assert display[3]["revealed"] is True
        assert display[3]["grade"] == "D"  # t[3]=0.6

    def test_format_bot(self):
        talents = {"t": [1.4, 0.8, 1.0, 0.6, 1.2, 0.9], "o": [0,3,1,5,4,2], "r": 0, "rc": 0}
        s = format_talents_bot(talents, False, star=2)
        assert "天赋(2/6)" in s
        assert "???×4" in s

    def test_average_grade(self):
        talents = {"t": [1.4, 0.8, 1.0, 0.6, 1.2, 0.9], "o": [0,1,2,3,4,5], "r": 0, "rc": 0}
        avg = get_average_grade(talents, star=2)
        # avg of t[0]=1.4 and t[1]=0.8 = 1.1 -> grade A
        assert avg == "A"

    def test_average_grade_no_revealed(self):
        talents = {"t": [1.4, 0.8, 1.0, 0.6, 1.2, 0.9], "o": [0,1,2,3,4,5], "r": 0, "rc": 0}
        assert get_average_grade(talents, star=0) is None
