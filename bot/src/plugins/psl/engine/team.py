from model.formation import Formation
from model.npc_formation import NpcFormation
from model.user import User
from engine.player import Player
from utils.const import Const
class Team:
  def __init__(self, user, npc=-1, difficulty=0):
    # 教练
    self.coach = user
    self.npc = npc
    self.difficulty = difficulty
    if npc == -1:
      self.players = self.getPlayers()
    else:
      self.coach = User([
        0,
        0,
        Const.NPC[npc]["name"] + " " + difficulty,
        0,
        0,
        Const.NPC[npc]["formation"],
        False
      ]
      )
      self.players = self.getNpcPlayers()
    self.point = 0
    self.control = 0
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.shots_in_box = 0
    self.shots_outside_box = 0
    self.open_play_xg = 0
    self.set_piece_xg = 0
    self.npxg = 0
    self.post_shot_xg = 0
    self.goals_prevented = 0
    self.psxg_faced = 0
    self.passes = 0
    self.successful_passes = 0
    self.progressive_passes = 0
    self.passes_into_final_third = 0
    self.passes_into_box = 0
    self.long_passes = 0
    self.completed_long_passes = 0
    self.short_passes = 0
    self.completed_short_passes = 0
    self.crosses = 0
    self.successful_crosses = 0
    self.corners = 0
    self.final_third_entries = 0
    self.box_entries = 0
    self.dribbles = 0
    self.carries = 0
    self.progressive_carries = 0
    self.carries_into_final_third = 0
    self.carries_into_box = 0
    self.take_ons = 0
    self.successful_take_ons = 0
    self.assists = 0
    self.tackles = 0
    self.tackle_attempts = 0
    self.interceptions = 0
    self.blocks = 0
    self.clearances = 0
    self.pressures = 0
    self.successful_pressures = 0
    self.defensive_actions = 0
    self.offsides_forced = 0
    self.turnovers = 0
    self.offsides = 0
    self.avg_possession_duration = 0
    self.saves = 0
    self.xg = 0
    self.adjusted_xg = 0
    self.xt = 0
    self.key_passes = 0
    self.box_touches = 0
    self.big_chances = 0
    self.possessions = 0
    self.goals_detailed = []
    self.position_stats = {}
    self.zone_stats = self.empty_zone_stats()
    self.player_stats = []

  # 返回包含NpcPlayer的列表
  def getNpcPlayers(self):
    formation = NpcFormation(self.npc, self.difficulty)
    players = []
    for i in range(0, 11):
      player = Player(formation.cards[i],
                      Const.FORMATION[formation.formation]["positions"][i],
                      formation.coordinates[i][0],
                      formation.coordinates[i][1],
                      Const.NPC[self.npc]["name"])
      players.append(player)
    return players

  # 返回包含Player的列表
  def getPlayers(self):
    formation = Formation.getFormation(self.coach)
    players = []
    for i in range(0, 11):
      player = Player(formation.cards[i],
                      Const.FORMATION[formation.formation]["positions"][i],
                      formation.coordinates[i][0],
                      formation.coordinates[i][1],
                      self.coach.name)
      players.append(player)
    return players
    
  def getStats(self):
    self.shoots = 0
    self.shoots_in_target = 0
    self.goals = 0
    self.passes = 0
    self.successful_passes = 0
    self.progressive_passes = 0
    self.passes_into_final_third = 0
    self.passes_into_box = 0
    self.long_passes = 0
    self.completed_long_passes = 0
    self.short_passes = 0
    self.completed_short_passes = 0
    self.crosses = 0
    self.successful_crosses = 0
    self.dribbles = 0
    self.carries = 0
    self.progressive_carries = 0
    self.carries_into_final_third = 0
    self.carries_into_box = 0
    self.take_ons = 0
    self.successful_take_ons = 0
    self.assists = 0
    self.tackles = 0
    self.tackle_attempts = 0
    self.interceptions = 0
    self.blocks = 0
    self.clearances = 0
    self.pressures = 0
    self.successful_pressures = 0
    self.defensive_actions = 0
    self.turnovers = 0
    self.offsides = 0
    self.saves = 0
    self.post_shot_xg = 0
    self.psxg_faced = 0
    self.goals_prevented = 0
    self.goals_detailed = []
    self.player_stats = []
    self.position_stats = {}
    for player in self.players:
      self.shoots += player.shoots
      self.shoots_in_target += player.shoots_in_target
      self.goals += player.goals
      self.passes += player.passes
      self.successful_passes += player.successful_passes
      self.progressive_passes += player.progressive_passes
      self.passes_into_final_third += player.passes_into_final_third
      self.passes_into_box += player.passes_into_box
      self.long_passes += player.long_passes
      self.completed_long_passes += player.completed_long_passes
      self.short_passes += player.short_passes
      self.completed_short_passes += player.completed_short_passes
      self.crosses += player.crosses
      self.successful_crosses += player.successful_crosses
      self.dribbles += player.dribbles
      self.carries += player.carries
      self.progressive_carries += player.progressive_carries
      self.carries_into_final_third += player.carries_into_final_third
      self.carries_into_box += player.carries_into_box
      self.take_ons += player.take_ons
      self.successful_take_ons += player.successful_take_ons
      self.assists += player.assists
      self.tackles += player.tackles
      self.tackle_attempts += player.tackle_attempts
      self.interceptions += player.interceptions
      self.blocks += player.blocks
      self.clearances += player.clearances
      self.pressures += player.pressures
      self.successful_pressures += player.successful_pressures
      self.turnovers += player.turnovers
      self.offsides += player.offsides
      self.saves += player.saves
      self.post_shot_xg += player.post_shot_xg
      self.psxg_faced += player.psxg_faced
      self.goals_prevented += player.goals_prevented
      if player.goals_detailed:
        self.goals_detailed.append((player.getName(), player.goals_detailed))
      self.player_stats.append(self.player_stat_dict(player))
      group = self.position_group(player.position)
      if group not in self.position_stats:
        self.position_stats[group] = self.empty_position_stat()
      self.add_position_stat(self.position_stats[group], player)
    self.defensive_actions = self.tackles + self.interceptions + self.blocks + self.clearances
    self.avg_possession_duration = 0 if self.possessions == 0 else self.control / self.possessions

  def player_stat_dict(self, player):
    return {
      "name": player.getName(False),
      "position": player.position,
      "goals": player.goals,
      "assists": player.assists,
      "shots": player.shoots,
      "shots_on_target": player.shoots_in_target,
      "xg": round(player.xg, 3),
      "npxg": round(player.npxg, 3),
      "post_shot_xg": round(player.post_shot_xg, 3),
      "big_chances": player.big_chances,
      "big_chances_missed": player.big_chances_missed,
      "passes": player.passes,
      "completed_passes": player.successful_passes,
      "key_passes": player.key_passes,
      "xa": round(player.xa, 3),
      "progressive_passes": player.progressive_passes,
      "passes_into_final_third": player.passes_into_final_third,
      "passes_into_box": player.passes_into_box,
      "long_passes": player.long_passes,
      "completed_long_passes": player.completed_long_passes,
      "crosses": player.crosses,
      "successful_crosses": player.successful_crosses,
      "carries": player.carries,
      "progressive_carries": player.progressive_carries,
      "carries_into_final_third": player.carries_into_final_third,
      "carries_into_box": player.carries_into_box,
      "take_ons": player.take_ons,
      "successful_take_ons": player.successful_take_ons,
      "tackles_attempted": player.tackle_attempts,
      "tackles_won": player.tackles,
      "interceptions": player.interceptions,
      "blocks": player.blocks,
      "clearances": player.clearances,
      "pressures": player.pressures,
      "successful_pressures": player.successful_pressures,
      "turnovers": player.turnovers,
      "dispossessed": player.dispossessed,
      "offsides": player.offsides,
      "saves": player.saves,
      "goals_conceded": player.goals_conceded,
      "psxg_faced": round(player.psxg_faced, 3),
      "goals_prevented": round(player.goals_prevented, 3),
    }

  def position_group(self, position):
    if position == "GK":
      return "GK"
    if position in ("LCB", "CB", "RCB"):
      return "CB"
    if position in ("LB", "RB", "LWB", "RWB"):
      return "FB"
    if "DM" in position:
      return "DM"
    if position in ("LCM", "CM", "RCM"):
      return "CM"
    if position in ("CAM", "LAM", "RAM"):
      return "AM"
    if position in ("LM", "RM", "LW", "RW"):
      return "W"
    return "ST"

  def empty_position_stat(self):
    return {
      "players": 0, "shots": 0, "xg": 0, "passes": 0, "completed_passes": 0,
      "key_passes": 0, "progressive_passes": 0, "carries": 0,
      "progressive_carries": 0, "take_ons": 0, "successful_take_ons": 0,
      "tackles": 0, "interceptions": 0, "blocks": 0, "pressures": 0,
      "successful_pressures": 0, "saves": 0,
    }

  def add_position_stat(self, stat, player):
    stat["players"] += 1
    stat["shots"] += player.shoots
    stat["xg"] = round(stat["xg"] + player.xg, 3)
    stat["passes"] += player.passes
    stat["completed_passes"] += player.successful_passes
    stat["key_passes"] += player.key_passes
    stat["progressive_passes"] += player.progressive_passes
    stat["carries"] += player.carries
    stat["progressive_carries"] += player.progressive_carries
    stat["take_ons"] += player.take_ons
    stat["successful_take_ons"] += player.successful_take_ons
    stat["tackles"] += player.tackles
    stat["interceptions"] += player.interceptions
    stat["blocks"] += player.blocks
    stat["pressures"] += player.pressures
    stat["successful_pressures"] += player.successful_pressures
    stat["saves"] += player.saves

  def empty_zone_stats(self):
    return {
      "left_channel_attacks": 0,
      "center_channel_attacks": 0,
      "right_channel_attacks": 0,
      "final_third_entries": 0,
      "box_entries": 0,
      "shots_in_box": 0,
      "shots_outside_box": 0,
    }
