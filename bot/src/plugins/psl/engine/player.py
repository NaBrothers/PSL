class Player:
  """Bot-facing player data adapted to and from the Rust match contract."""

  def __init__(self, card, position, default_x, default_y, coach):
    self.name = card.getNameWithColor()
    self.card = card
    self.coach = coach
    self.position = position
    self.ability = card.get_engine_abilities()
    self.x = default_x
    self.y = default_y
    self.default_x = default_x
    self.default_y = default_y
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.xg = 0
    self.npxg = 0
    self.post_shot_xg = 0
    self.big_chances = 0
    self.big_chances_missed = 0
    self.shots_in_box = 0
    self.shots_outside_box = 0
    self.passes = 0
    self.successful_passes = 0
    self.assists = 0
    self.key_passes = 0
    self.xa = 0
    self.progressive_passes = 0
    self.passes_into_final_third = 0
    self.passes_into_box = 0
    self.long_passes = 0
    self.completed_long_passes = 0
    self.short_passes = 0
    self.completed_short_passes = 0
    self.crosses = 0
    self.successful_crosses = 0
    self.tackles = 0
    self.tackle_attempts = 0
    self.interceptions = 0
    self.blocks = 0
    self.clearances = 0
    self.pressures = 0
    self.successful_pressures = 0
    self.saves = 0
    self.goals_conceded = 0
    self.psxg_faced = 0
    self.goals_prevented = 0
    self.dribbles = 0
    self.carries = 0
    self.progressive_carries = 0
    self.current_carry_progress = 0
    self.carries_into_final_third = 0
    self.carries_into_box = 0
    self.take_ons = 0
    self.successful_take_ons = 0
    self.turnovers = 0
    self.dispossessed = 0
    self.offsides = 0
    self.goals_detailed = []
    self.shot_log = []
    self.pass_connections = {}
    self.position_samples = []

  def getName(self, color = True):
    if color:
      return self.position + " " + self.name
    return self.card.player.Name
