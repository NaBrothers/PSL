import math
from dataclasses import dataclass


def clamp(value, minimum=0.0, maximum=1.0):
  return max(minimum, min(maximum, value))


def logistic_probability(attack, defence, scale=12.0, floor=0.03, ceiling=0.97):
  if scale <= 0:
    scale = 12.0
  value = 1.0 / (1.0 + math.exp(-(attack - defence) / scale))
  return clamp(value, floor, ceiling)


def contest_success(rng, attack, defence, scale=12.0, floor=0.03, ceiling=0.97):
  return rng.random() < logistic_probability(attack, defence, scale, floor, ceiling)


@dataclass
class ShotContext:
  distance: float
  angle: float
  shoot_ability: float
  pressure: int = 0
  assist_quality: float = 0
  is_header: bool = False
  raw_xg: float = 0
  goal_probability: float = 0
  on_target_probability: float = 0


def shot_on_target_probability(distance, shoot_ability, pressure=0):
  angle_factor = clamp(1.0 - distance / 38.0, 0.02, 0.55)
  ability_factor = logistic_probability(shoot_ability, 96 + pressure * 5, scale=20, floor=0.04, ceiling=0.48)
  return clamp(angle_factor * 0.22 + ability_factor * 0.14 - pressure * 0.045, 0.02, 0.38)


def shot_goal_probability(shoot_ability, gk_ability, distance, shoot_place):
  distance_penalty = distance * 0.75
  placement_bonus = max(0, shoot_place - 1.5) * 1.8
  attack = shoot_ability + placement_bonus - distance_penalty
  defence = gk_ability
  return logistic_probability(attack, defence, scale=14, floor=0.03, ceiling=0.85)


def expected_goals(distance, angle, pressure=0, assist_quality=0, is_header=False):
  distance_score = clamp(1.0 - distance / 38.0, 0.01, 0.85)
  angle_score = clamp(angle / 45.0, 0.05, 1.0)
  pressure_penalty = clamp(1.0 - pressure * 0.10, 0.35, 1.0)
  assist_bonus = clamp(1.0 + assist_quality * 0.06, 1.0, 1.25)
  header_penalty = 0.68 if is_header else 1.0
  xg = 0.14 * distance_score + 0.07 * angle_score
  return clamp(xg * pressure_penalty * assist_bonus * header_penalty, 0.005, 0.24)


def build_shot_context(distance, angle, shoot_ability, pressure=0, assist_quality=0, is_header=False):
  raw_xg = expected_goals(distance, angle, pressure, assist_quality, is_header)
  finishing_adjustment = clamp(0.75 + logistic_probability(shoot_ability, 84, scale=24, floor=0.0, ceiling=1.0) * 0.55, 0.75, 1.3)
  goal_probability = clamp(raw_xg * finishing_adjustment, 0.003, 0.45)
  on_target_probability = shot_on_target_probability(distance, shoot_ability, pressure)
  return ShotContext(distance, angle, shoot_ability, pressure, assist_quality, is_header, raw_xg, goal_probability, on_target_probability)


def pass_success_probability(pass_ability, distance, pressure=0, is_long=False):
  base = logistic_probability(pass_ability, 48 + pressure * 1.5, scale=18, floor=0.82, ceiling=0.99)
  distance_penalty = distance * (0.001 if is_long else 0.00035)
  long_penalty = 0.015 if is_long else 0.0
  return clamp(base - distance_penalty - long_penalty, 0.72, 0.99)


def expected_threat(y, action_quality=1.0):
  progress = clamp(1.0 - y / 105.0, 0.0, 1.0)
  return clamp(progress * progress * action_quality, 0.0, 1.0)
