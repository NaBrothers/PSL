import math


def clamp(value, minimum=0.0, maximum=1.0):
  return max(minimum, min(maximum, value))


def logistic_probability(attack, defence, scale=12.0, floor=0.03, ceiling=0.97):
  if scale <= 0:
    scale = 12.0
  value = 1.0 / (1.0 + math.exp(-(attack - defence) / scale))
  return clamp(value, floor, ceiling)


def contest_success(rng, attack, defence, scale=12.0, floor=0.03, ceiling=0.97):
  return rng.random() < logistic_probability(attack, defence, scale, floor, ceiling)


def shot_on_target_probability(distance, shoot_ability, pressure=0):
  angle_factor = clamp(1.0 - distance / 55.0, 0.08, 0.92)
  ability_factor = logistic_probability(shoot_ability, 78 + pressure * 4, scale=16, floor=0.15, ceiling=0.9)
  return clamp(angle_factor * 0.55 + ability_factor * 0.45, 0.05, 0.92)


def shot_goal_probability(shoot_ability, gk_ability, distance, shoot_place):
  distance_penalty = distance * 0.75
  placement_bonus = max(0, shoot_place - 1.5) * 1.8
  attack = shoot_ability + placement_bonus - distance_penalty
  defence = gk_ability
  return logistic_probability(attack, defence, scale=14, floor=0.03, ceiling=0.85)
