use crate::physics::{distance, smoothstep};
use crate::shot_quality::{shot_quality_at, ShotQualityCache, ShotQualityInput};
use crate::state_value::{pass_receive_value, shot_quality_cache_key, PassReceiveValueInput};

#[derive(Debug, Clone)]
pub struct PassLaneRiskInput<'a> {
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub opponents: &'a [(f64, f64)],
    pub interception_reach: f64,
}

#[derive(Debug, Clone)]
pub struct TurnoverConsequenceInput<'a> {
    pub loss_pos: (f64, f64),
    pub opponents: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
}

#[derive(Debug, Clone)]
pub struct ExpectedPassInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_consecutive_carries: i32,
    pub receiver_index: usize,
    pub receiver_team_home: bool,
    pub receiver_finishing: f64,
    pub receiver_long_shot: f64,
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub receiver_goal_type: Option<&'a str>,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
    pub target: (f64, f64),
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub current_value: f64,
    pub base_accuracy: f64,
    pub receiver_arrival: f64,
    pub continuity: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Debug, Clone)]
pub struct ExpectedPassOutput {
    pub score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub after_value: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub effective_delta: f64,
    pub progress_gain: f64,
    pub continuity: f64,
    pub lane_risk: f64,
    pub receiver_pressure: f64,
    pub turnover_consequence: f64,
    pub high_threat_space: f64,
    pub final_third_combination: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
    pub short_combination_value: f64,
    pub layoff_retention_value: f64,
}

pub fn pass_lane_risk(input: &PassLaneRiskInput<'_>) -> f64 {
    let (ox, oy) = input.origin;
    let (tx, ty) = input.target;
    let dx = tx - ox;
    let dy = ty - oy;
    let length = (dx * dx + dy * dy).sqrt();
    if length < 1.0 {
        return 1.0;
    }

    let nx = dx / length;
    let ny = dy / length;
    let mut risk = 0.0;
    for opp in input.opponents {
        let rel_x = opp.0 - ox;
        let rel_y = opp.1 - oy;
        let proj = rel_x * nx + rel_y * ny;
        if proj <= 1.5 || proj >= length - 1.5 {
            continue;
        }
        let perp = (rel_x * ny - rel_y * nx).abs();
        let reach = input.interception_reach * 1.8;
        if perp < reach {
            let lane_share = 1.0 - perp / reach;
            let centrality = 1.0 - (proj / length - 0.5).abs() * 0.45;
            risk += lane_share * centrality;
        }
    }
    let length_factor = 1.4_f64.min(length / 35.0);
    (risk * 0.28 * length_factor).clamp(0.0, 1.0)
}

pub fn receiver_pressure(target: (f64, f64), opponents: &[(f64, f64)]) -> f64 {
    let mut pressure = 0.0;
    for opp in opponents {
        let d = distance(target, *opp);
        if d < 12.0 {
            pressure += 1.0 - d / 12.0;
        }
    }
    (pressure * 0.35).clamp(0.0, 1.0)
}

pub fn turnover_consequence(input: &TurnoverConsequenceInput<'_>) -> f64 {
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let own_goal = (own_goal_x, input.pitch_width / 2.0);
    let d_goal = distance(input.loss_pos, own_goal);
    let goal_danger = (1.0 - d_goal / 60.0).max(0.0);
    let central = 1.0
        - ((input.loss_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);

    let mut nearby_opps = 0.0;
    for opp in input.opponents {
        let d = distance(input.loss_pos, *opp);
        if d < 18.0 {
            nearby_opps += 1.0 - d / 18.0;
        }
    }

    (goal_danger * 0.55 + central * 0.20 + (nearby_opps * 0.25).min(1.0)).clamp(0.05, 1.0)
}

pub fn expected_pass_value(input: &ExpectedPassInput<'_>) -> ExpectedPassOutput {
    let lane_risk = pass_lane_risk(&PassLaneRiskInput {
        origin: input.passer_pos,
        target: input.target,
        opponents: input.opponent_positions,
        interception_reach: input.interception_reach,
    });
    let pressure = receiver_pressure(input.target, input.opponent_positions);
    let success_prob = (input.base_accuracy
        * input.receiver_arrival
        * (1.0 - lane_risk * 0.92)
        * (1.0 - pressure * 0.55))
        .clamp(0.02, 0.95);

    let after_value = pass_receive_value(&PassReceiveValueInput {
        pos: input.target,
        receiver_index: input.receiver_index,
        receiver_team_home: input.receiver_team_home,
        tick: input.tick,
        finishing: input.receiver_finishing,
        long_shot: input.receiver_long_shot,
        receiver_anchor: input.receiver_anchor,
        receiver_base: input.receiver_base,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        receiver_goal_type: input.receiver_goal_type,
        receiver_goal_target: input.receiver_goal_target,
        receiver_goal_value: input.receiver_goal_value,
        shot_quality_cache: input.shot_quality_cache,
    });
    let consequence_point = (
        (input.passer_pos.0 + input.target.0) / 2.0,
        (input.passer_pos.1 + input.target.1) / 2.0,
    );
    let consequence = turnover_consequence(&TurnoverConsequenceInput {
        loss_pos: consequence_point,
        opponents: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
    });
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let progress_gain =
        (input.target.0 - input.passer_pos.0) * forward_dir / input.pitch_length.max(1.0);
    let lateral_change = (input.target.1 - input.passer_pos.1).abs() / input.pitch_width.max(1.0);
    let target_progress = if input.attacking_right {
        input.target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.target.0) / input.pitch_length.max(1.0)
    };
    let centrality = 1.0
        - ((input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let width_value = 1.0 - centrality;
    let target_width = (input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let anchor_width =
        (input.receiver_anchor.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let receiver_base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length.max(1.0)
    };
    let origin_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length.max(1.0)
    };
    let mut attracted_pressure = 0.0;
    for opp in input.opponent_positions {
        let d = distance(input.passer_pos, *opp);
        if d < 11.0 {
            attracted_pressure += 1.0 - d / 11.0;
        }
    }
    attracted_pressure = (attracted_pressure * 0.42).min(1.0);
    let carry_count = input.passer_consecutive_carries.max(0) as f64;
    let pressured_possession = smoothstep(0.78, 0.92, origin_progress)
        * smoothstep(0.18, 0.65, attracted_pressure)
        * smoothstep(1.0, 3.0, carry_count);
    let stale_possession = smoothstep(0.62, 0.86, origin_progress)
        * smoothstep(1.0, 4.0, carry_count)
        * (0.38 + 0.62 * smoothstep(0.08, 0.55, attracted_pressure));
    let effective_current_value =
        input.current_value * (1.0 - 0.22 * pressured_possession - 0.18 * stale_possession);
    let delta = after_value - effective_current_value;
    let high_threat_space = smoothstep(0.72, 0.90, target_progress)
        * smoothstep(0.24, 0.52, centrality)
        * smoothstep(0.04, 0.18, delta.max(0.0))
        * (1.0 - smoothstep(0.45, 0.85, pressure));
    let final_third_combination = smoothstep(0.78, 0.92, origin_progress)
        * smoothstep(0.70, 0.84, target_progress)
        * smoothstep(0.35, 0.70, centrality)
        * smoothstep(0.04, 0.18, delta.max(0.0))
        * (1.0 - smoothstep(0.35, 0.80, pressure));
    let cutback_value = final_third_combination
        * (0.035 + 0.18 * delta.max(0.0) + 0.050 * smoothstep(0.08, 0.38, lateral_change));
    let layoff_retention_space = smoothstep(0.80, 0.92, origin_progress)
        * smoothstep(0.56, 0.76, target_progress)
        * smoothstep(0.24, 0.72, centrality)
        * smoothstep(-0.55, -0.18, delta)
        * (1.0 - smoothstep(0.42, 0.86, pressure));
    let layoff_retention_value = layoff_retention_space
        * (0.035 + 0.070 * success_prob + 0.030 * smoothstep(0.04, 0.24, lateral_change));
    let target_distance = distance(input.passer_pos, input.target);
    let pressure_release_space = smoothstep(0.78, 0.92, origin_progress)
        * smoothstep(0.18, 0.65, attracted_pressure)
        * smoothstep(1.0, 3.0, carry_count)
        * smoothstep(6.0, 14.0, target_distance)
        * (1.0 - smoothstep(24.0, 34.0, target_distance))
        * (1.0 - smoothstep(0.40, 0.86, pressure));
    let pressure_release_value = pressure_release_space
        * (0.075 + 0.120 * success_prob + 0.055 * smoothstep(0.06, 0.30, lateral_change));
    let stale_release_space = smoothstep(0.62, 0.86, origin_progress)
        * smoothstep(1.0, 4.0, carry_count)
        * smoothstep(4.0, 12.0, target_distance)
        * (1.0 - smoothstep(30.0, 44.0, target_distance))
        * (1.0 - smoothstep(0.45, 0.88, pressure))
        * (0.58 + 0.42 * smoothstep(0.04, 0.28, lateral_change))
        * (0.62 + 0.38 * smoothstep(0.0, 0.18, (-progress_gain).max(0.0)));
    let stale_release_value = stale_release_space
        * (0.085
            + 0.185 * success_prob
            + 0.055 * smoothstep(0.04, 0.26, lateral_change)
            + 0.040 * smoothstep(0.0, 0.22, (-delta).max(0.0)));
    let wide_creation_space = smoothstep(0.56, 0.78, target_progress)
        * smoothstep(0.32, 0.68, width_value)
        * smoothstep(0.02, 0.12, delta.max(0.0))
        * (1.0 - smoothstep(0.42, 0.86, pressure));
    let inside_arrival_space = smoothstep(0.64, 0.84, target_progress)
        * smoothstep(0.38, 0.76, centrality)
        * (1.0 - smoothstep(0.86, 0.96, target_progress))
        * smoothstep(0.12, 0.50, (anchor_width - target_width).max(0.0))
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let second_line_arrival_space = smoothstep(0.64, 0.84, target_progress)
        * smoothstep(0.42, 0.84, centrality)
        * (1.0 - smoothstep(0.84, 0.95, target_progress))
        * smoothstep(
            0.04,
            0.24,
            (target_progress - receiver_base_progress).max(0.0),
        )
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let receiver_goal_arrival_space = crate::state_value::receiver_goal_arrival_space(
        input.receiver_goal_type,
        input.receiver_goal_target,
        input.receiver_goal_value,
        input.target,
        target_progress,
        centrality,
        pressure,
    );
    let origin_width =
        (input.passer_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let current_shot = shot_quality_at(&ShotQualityInput {
        x: input.passer_pos.0,
        y: input.passer_pos.1,
        finishing: input.passer_finishing,
        long_shot: input.passer_long_shot,
        opponents: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: None,
        gk_pos: None,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.map(|_| {
            shot_quality_cache_key(
                input.tick,
                input.passer_team_home,
                input.passer_index,
                input.passer_pos,
                input.attacking_right,
            )
        }),
    });
    let second_line_cutback_space = smoothstep(0.62, 0.82, origin_progress)
        * smoothstep(0.38, 0.74, origin_width)
        * smoothstep(0.68, 0.82, target_progress)
        * (1.0 - smoothstep(0.84, 0.94, target_progress))
        * smoothstep(0.62, 0.92, centrality)
        * smoothstep(
            0.06,
            0.26,
            (target_progress - receiver_base_progress).max(0.0),
        )
        * (1.0 - smoothstep(0.32, 0.78, pressure));
    let high_central_holder =
        smoothstep(0.72, 0.90, origin_progress) * smoothstep(0.54, 0.94, centrality);
    let layoff_depth =
        (input.passer_pos.0 - input.target.0) * if input.attacking_right { 1.0 } else { -1.0 };
    let poor_current_shot = 1.0 - smoothstep(0.075, 0.145, current_shot);
    let support_lane_change = smoothstep(0.05, 0.30, lateral_change);
    let layoff_support_space = high_central_holder
        * smoothstep(0.54, 0.82, target_progress)
        * (1.0 - smoothstep(0.84, 0.95, target_progress))
        * smoothstep(2.0, 12.0, layoff_depth)
        * (1.0 - smoothstep(24.0, 36.0, layoff_depth))
        * smoothstep(0.28, 0.86, centrality)
        * (0.55 + 0.45 * support_lane_change)
        * (1.0 - smoothstep(0.36, 0.82, pressure))
        * (0.55 + 0.45 * poor_current_shot);
    let short_combination_space = smoothstep(0.68, 0.90, origin_progress)
        * smoothstep(5.0, 13.0, target_distance)
        * (1.0 - smoothstep(24.0, 34.0, target_distance))
        * smoothstep(0.08, 0.44, lateral_change)
        * (1.0 - smoothstep(0.42, 0.86, pressure))
        * (0.55 + 0.45 * poor_current_shot);
    let wide_creation_value = wide_creation_space
        * (0.030
            + 0.11 * delta.max(0.0)
            + 0.045 * smoothstep(0.08, 0.32, lateral_change)
            + 0.035 * smoothstep(0.02, 0.14, progress_gain.max(0.0)));
    let inside_arrival_value = inside_arrival_space
        * (0.018 + 0.038 * success_prob + 0.020 * smoothstep(0.02, 0.12, delta.max(0.0)));
    let second_line_arrival_value = second_line_arrival_space
        * (0.016 + 0.034 * success_prob + 0.018 * smoothstep(0.02, 0.12, delta.max(0.0)));
    let receiver_goal_arrival_value = receiver_goal_arrival_space
        * (0.030 + 0.060 * success_prob + 0.030 * smoothstep(0.0, 0.12, delta.max(0.0)));
    let second_line_cutback_value = second_line_cutback_space
        * (0.034
            + 0.050 * success_prob
            + 0.020 * smoothstep(0.04, 0.22, lateral_change)
            + 0.070 * delta.max(0.0));
    let layoff_support_value = layoff_support_space
        * (0.052
            + 0.084 * success_prob
            + 0.040 * support_lane_change
            + 0.058 * smoothstep(0.0, 0.18, (-progress_gain).max(0.0))
            + 0.045 * poor_current_shot);
    let short_combination_value = short_combination_space
        * (0.032
            + 0.064 * success_prob
            + 0.034 * smoothstep(0.04, 0.22, lateral_change)
            + 0.026 * poor_current_shot);
    let chance_creation_value = high_threat_space
        * (0.045 + 0.16 * delta.max(0.0) + 0.08 * progress_gain.max(0.0))
        + cutback_value
        + wide_creation_value
        + inside_arrival_value
        + second_line_arrival_value
        + receiver_goal_arrival_value
        + second_line_cutback_value
        + layoff_support_value
        + short_combination_value
        + layoff_retention_value
        + pressure_release_value
        + stale_release_value;
    let success_quality = smoothstep(0.10, 0.38, success_prob);
    let mut risk_budget = high_threat_space
        * (0.030
            + 0.070 * smoothstep(0.05, 0.22, delta.max(0.0))
            + 0.035 * smoothstep(0.02, 0.12, progress_gain.max(0.0)))
        + final_third_combination * (0.020 + 0.050 * smoothstep(0.05, 0.20, delta.max(0.0)))
        + wide_creation_space * (0.018 + 0.045 * smoothstep(0.04, 0.16, delta.max(0.0)))
        + inside_arrival_space * (0.012 + 0.022 * success_prob)
        + second_line_arrival_space * (0.010 + 0.020 * success_prob)
        + receiver_goal_arrival_space * (0.014 + 0.026 * success_prob)
        + second_line_cutback_space * (0.022 + 0.044 * success_prob)
        + layoff_support_space * (0.024 + 0.048 * success_prob)
        + short_combination_space * (0.014 + 0.030 * success_prob)
        + layoff_retention_space * (0.025 + 0.035 * success_prob)
        + pressure_release_space * (0.040 + 0.075 * success_prob)
        + stale_release_space * (0.045 + 0.085 * success_prob);
    risk_budget *= 0.20 + 0.80 * success_quality;
    let risk_cost = ((1.0 - success_prob) * (0.07 + 0.24 * consequence) - risk_budget).max(0.0);
    let safe_retain_value = success_prob * (1.0 - lane_risk) * (1.0 - pressure);
    let negative_delta = (-delta).max(0.0);
    let effective_delta = delta + negative_delta * safe_retain_value * 0.72;
    let recycle_value =
        safe_retain_value * (0.022 + 0.038 * smoothstep(0.04, 0.26, lateral_change));
    let progression_value = safe_retain_value * progress_gain.max(0.0) * 0.18;
    let rhythm_value = safe_retain_value * 0.018;
    let mut final_continuity = input.continuity * (0.25 + 0.75 * smoothstep(-0.08, 0.02, delta));
    final_continuity += (delta.max(0.0) * 0.40).min(0.070);
    let safe_receiver_bonus = 1.0 - smoothstep(0.15, 0.45, pressure);
    let safe_lane_bonus = 1.0 - smoothstep(0.15, 0.45, lane_risk);
    final_continuity += 0.030 * safe_receiver_bonus * safe_lane_bonus;
    final_continuity += (layoff_support_space + short_combination_space)
        * safe_retain_value
        * (0.030 + 0.055 * poor_current_shot);
    final_continuity += recycle_value + progression_value + rhythm_value + chance_creation_value;
    let mut score = (success_prob * (effective_delta + final_continuity) - risk_cost).max(0.0);
    let positive_delta_bonus = 1.0 + 0.45 * smoothstep(0.04, 0.16, delta);
    score *= positive_delta_bonus;
    let current_shot_window = smoothstep(0.065, 0.155, current_shot)
        * smoothstep(0.68, 0.88, origin_progress)
        * (1.0 - smoothstep(0.35, 0.78, attracted_pressure));
    let pass_can_pay_for_window = high_threat_space
        .max(final_third_combination)
        .max(pressure_release_space * 0.70)
        .max(stale_release_space * 0.55)
        * success_quality;
    let shoot_window_release_cost = current_shot_window
        * (0.026
            + 0.20 * current_shot
            + 0.035 * smoothstep(0.0, 0.10, (-progress_gain).max(0.0))
            + 0.025 * smoothstep(0.0, 0.22, (-delta).max(0.0)))
        * (1.0 - 0.72 * smoothstep(0.18, 0.75, pass_can_pay_for_window));
    score = (score - shoot_window_release_cost).max(0.0);

    ExpectedPassOutput {
        score,
        success_prob,
        risk_cost,
        after_value,
        current_value: input.current_value,
        effective_current_value,
        delta,
        effective_delta,
        progress_gain,
        continuity: final_continuity,
        lane_risk,
        receiver_pressure: pressure,
        turnover_consequence: consequence,
        high_threat_space,
        final_third_combination,
        second_line_arrival_value,
        second_line_cutback_value,
        layoff_support_value,
        short_combination_value,
        layoff_retention_value,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lane_risk_increases_when_defender_is_on_path() {
        let clear = pass_lane_risk(&PassLaneRiskInput {
            origin: (40.0, 34.0),
            target: (70.0, 34.0),
            opponents: &[(55.0, 50.0)],
            interception_reach: 3.5,
        });
        let blocked = pass_lane_risk(&PassLaneRiskInput {
            origin: (40.0, 34.0),
            target: (70.0, 34.0),
            opponents: &[(55.0, 34.0)],
            interception_reach: 3.5,
        });
        assert!(blocked > clear);
    }
}
