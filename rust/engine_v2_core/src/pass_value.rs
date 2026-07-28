use crate::goalkeeper::GkSaveAttributes;
use crate::physics::{distance, smoothstep};
use crate::shot_quality::{
    shot_quality_at, ShotContestDefender, ShotQualityCache, ShotQualityInput,
};
use crate::state_value::{
    pass_receive_value_breakdown_with_context_and_precomputed_target_pressures,
    shot_quality_cache_key, PassReceiveTargetPressure, PassReceiveValueContext,
    PassReceiveValueInput, PlayerShotProfile,
};

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
    pub shot_profiles: &'a [PlayerShotProfile],
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub offside_line: f64,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
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
    pub after_direct_xg: f64,
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

#[derive(Debug, Clone, Copy)]
pub struct PasserPassValueContext {
    pub origin_progress: f64,
    pub attracted_pressure: f64,
    pub effective_current_value: f64,
    pub current_shot: f64,
    pub origin_width: f64,
}

#[derive(Debug, Clone)]
pub struct PasserPassValueContextInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_consecutive_carries: i32,
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub current_value: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

fn pass_lane_risk_with_distance(input: &PassLaneRiskInput<'_>) -> (f64, f64) {
    let (ox, oy) = input.origin;
    let (tx, ty) = input.target;
    let dx = tx - ox;
    let dy = ty - oy;
    let length = (dx * dx + dy * dy).sqrt();
    if length < 1.0 {
        return (1.0, length);
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
    ((risk * 0.28 * length_factor).clamp(0.0, 1.0), length)
}

pub fn pass_lane_risk(input: &PassLaneRiskInput<'_>) -> f64 {
    pass_lane_risk_with_distance(input).0
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

fn pass_turnover_consequence(
    origin: (f64, f64),
    target: (f64, f64),
    opponents: &[(f64, f64)],
    pitch_length: f64,
    pitch_width: f64,
    attacking_right: bool,
) -> f64 {
    let midpoint = ((origin.0 + target.0) * 0.5, (origin.1 + target.1) * 0.5);
    [midpoint, target]
        .into_iter()
        .map(|loss_pos| {
            turnover_consequence(&TurnoverConsequenceInput {
                loss_pos,
                opponents,
                pitch_length,
                pitch_width,
                attacking_right,
            })
        })
        .fold(0.0, f64::max)
}

#[derive(Clone, Copy)]
struct PassRiskEvaluation {
    lane_risk: f64,
    target_distance: f64,
    receiver_pressure: f64,
    target_local_pressure: f64,
    turnover_consequence: f64,
}

fn pass_risk_evaluation(
    origin: (f64, f64),
    target: (f64, f64),
    opponents: &[(f64, f64)],
    interception_reach: f64,
    loss_pos: (f64, f64),
    pitch_length: f64,
    pitch_width: f64,
    attacking_right: bool,
    precomputed_receiver_pressure: Option<f64>,
) -> PassRiskEvaluation {
    let (ox, oy) = origin;
    let (tx, ty) = target;
    let dx = tx - ox;
    let dy = ty - oy;
    let target_distance = (dx * dx + dy * dy).sqrt();
    let lane_is_degenerate = target_distance < 1.0;
    let (nx, ny) = if lane_is_degenerate {
        (0.0, 0.0)
    } else {
        (dx / target_distance, dy / target_distance)
    };
    let own_goal_x = if attacking_right { 0.0 } else { pitch_length };
    let own_goal = (own_goal_x, pitch_width / 2.0);
    let d_goal = distance(loss_pos, own_goal);
    let goal_danger = (1.0 - d_goal / 60.0).max(0.0);
    let central = 1.0 - ((loss_pos.1 - pitch_width / 2.0).abs() / (pitch_width / 2.0)).min(1.0);
    let mut lane_risk = 0.0;
    let mut receiver_pressure = 0.0;
    let mut target_local_pressure = 0.0;
    let mut nearby_opponents = 0.0;

    for opponent in opponents {
        if !lane_is_degenerate {
            let rel_x = opponent.0 - ox;
            let rel_y = opponent.1 - oy;
            let projection = rel_x * nx + rel_y * ny;
            if projection > 1.5 && projection < target_distance - 1.5 {
                let perpendicular = (rel_x * ny - rel_y * nx).abs();
                let reach = interception_reach * 1.8;
                if perpendicular < reach {
                    let lane_share = 1.0 - perpendicular / reach;
                    let centrality = 1.0 - (projection / target_distance - 0.5).abs() * 0.45;
                    lane_risk += lane_share * centrality;
                }
            }
        }
        let target_distance_to_opponent = distance(target, *opponent);
        if precomputed_receiver_pressure.is_none() && target_distance_to_opponent < 12.0 {
            receiver_pressure += 1.0 - target_distance_to_opponent / 12.0;
        }
        if target_distance_to_opponent < 18.0 {
            target_local_pressure += (1.0 - target_distance_to_opponent / 18.0).powf(1.25);
        }
        let loss_distance_to_opponent = distance(loss_pos, *opponent);
        if loss_distance_to_opponent < 18.0 {
            nearby_opponents += 1.0 - loss_distance_to_opponent / 18.0;
        }
    }

    let lane_risk = if lane_is_degenerate {
        1.0
    } else {
        let length_factor = 1.4_f64.min(target_distance / 35.0);
        (lane_risk * 0.28 * length_factor).clamp(0.0, 1.0)
    };
    let receiver_pressure =
        precomputed_receiver_pressure.unwrap_or_else(|| (receiver_pressure * 0.35).clamp(0.0, 1.0));
    let turnover_consequence =
        (goal_danger * 0.55 + central * 0.20 + (nearby_opponents * 0.25).min(1.0)).clamp(0.05, 1.0);

    PassRiskEvaluation {
        lane_risk,
        target_distance,
        receiver_pressure,
        target_local_pressure: (target_local_pressure * 0.30).clamp(0.0, 1.0),
        turnover_consequence,
    }
}

pub fn pass_retention_probability(
    base_accuracy: f64,
    receiver_arrival: f64,
    lane_risk: f64,
    receiver_pressure: f64,
) -> f64 {
    let technical = base_accuracy.clamp(0.0, 1.0);
    let arrival_factor = 0.55 + 0.45 * receiver_arrival.clamp(0.0, 1.0);
    let lane_factor = 1.0 - 0.50 * lane_risk.clamp(0.0, 1.0);
    let pressure_factor = 1.0 - 0.30 * receiver_pressure.clamp(0.0, 1.0);

    (technical * arrival_factor * lane_factor * pressure_factor).clamp(0.05, 0.98)
}

pub fn pass_technical_accuracy(
    base_success: f64,
    passing: f64,
    _distance: f64,
    _is_long: bool,
) -> f64 {
    let passing = (passing / 100.0).clamp(0.0, 1.0);
    let technical_accuracy =
        base_success.clamp(0.0, 1.0) + (1.0 - base_success.clamp(0.0, 1.0)) * passing;
    technical_accuracy.clamp(0.05, 0.995)
}

pub fn passer_pass_value_context(
    input: &PasserPassValueContextInput<'_>,
) -> PasserPassValueContext {
    let origin_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length.max(1.0)
    };
    let mut attracted_pressure = 0.0;
    for opponent in input.opponent_positions {
        let distance_to_passer = distance(input.passer_pos, *opponent);
        if distance_to_passer < 11.0 {
            attracted_pressure += 1.0 - distance_to_passer / 11.0;
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
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.and_then(|_| {
            input.gk_attributes.is_none().then(|| {
                shot_quality_cache_key(
                    input.tick,
                    input.passer_team_home,
                    input.passer_index,
                    input.passer_pos,
                    input.attacking_right,
                )
            })
        }),
    });
    let origin_width =
        (input.passer_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);

    PasserPassValueContext {
        origin_progress,
        attracted_pressure,
        effective_current_value,
        current_shot,
        origin_width,
    }
}

pub fn expected_pass_value(input: &ExpectedPassInput<'_>) -> ExpectedPassOutput {
    let passer_context = passer_pass_value_context(&PasserPassValueContextInput {
        tick: input.tick,
        passer_index: input.passer_index,
        passer_team_home: input.passer_team_home,
        passer_pos: input.passer_pos,
        passer_finishing: input.passer_finishing,
        passer_long_shot: input.passer_long_shot,
        passer_consecutive_carries: input.passer_consecutive_carries,
        opponent_positions: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        current_value: input.current_value,
        shot_quality_cache: input.shot_quality_cache,
    });
    expected_pass_value_with_passer_context(input, passer_context)
}

pub(crate) fn expected_pass_value_with_passer_context(
    input: &ExpectedPassInput<'_>,
    passer_context: PasserPassValueContext,
) -> ExpectedPassOutput {
    expected_pass_value_with_context(input, passer_context, None)
}

pub(crate) fn expected_pass_value_with_context(
    input: &ExpectedPassInput<'_>,
    passer_context: PasserPassValueContext,
    pass_receive_context: Option<&PassReceiveValueContext>,
) -> ExpectedPassOutput {
    expected_pass_value_with_optional_receiver_pressure(
        input,
        passer_context,
        pass_receive_context,
        None,
    )
}

pub(crate) fn expected_pass_value_with_context_and_precomputed_receiver_pressure(
    input: &ExpectedPassInput<'_>,
    passer_context: PasserPassValueContext,
    pass_receive_context: Option<&PassReceiveValueContext>,
    receiver_pressure: f64,
) -> ExpectedPassOutput {
    expected_pass_value_with_optional_receiver_pressure(
        input,
        passer_context,
        pass_receive_context,
        Some(receiver_pressure),
    )
}

fn expected_pass_value_with_optional_receiver_pressure(
    input: &ExpectedPassInput<'_>,
    passer_context: PasserPassValueContext,
    pass_receive_context: Option<&PassReceiveValueContext>,
    precomputed_receiver_pressure: Option<f64>,
) -> ExpectedPassOutput {
    let consequence_point = (
        (input.passer_pos.0 + input.target.0) / 2.0,
        (input.passer_pos.1 + input.target.1) / 2.0,
    );
    let mut risk = pass_risk_evaluation(
        input.passer_pos,
        input.target,
        input.opponent_positions,
        input.interception_reach,
        consequence_point,
        input.pitch_length,
        input.pitch_width,
        input.attacking_right,
        precomputed_receiver_pressure,
    );
    risk.turnover_consequence = pass_turnover_consequence(
        input.passer_pos,
        input.target,
        input.opponent_positions,
        input.pitch_length,
        input.pitch_width,
        input.attacking_right,
    );
    let success_prob = pass_retention_probability(
        input.base_accuracy,
        input.receiver_arrival,
        risk.lane_risk,
        risk.receiver_pressure,
    );

    let pass_receive_input = PassReceiveValueInput {
        pos: input.target,
        receiver_index: input.receiver_index,
        shot_profiles: input.shot_profiles,
        receiver_anchor: input.receiver_anchor,
        receiver_base: input.receiver_base,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        offside_line: input.offside_line,
        receiver_finishing: input.receiver_finishing,
        receiver_long_shot: input.receiver_long_shot,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        tick: input.tick,
        receiver_team_home: input.receiver_team_home,
        shot_quality_cache: input.shot_quality_cache,
        receiver_goal_type: input.receiver_goal_type,
        receiver_goal_target: input.receiver_goal_target,
        receiver_goal_value: input.receiver_goal_value,
    };
    let after_state = pass_receive_value_breakdown_with_context_and_precomputed_target_pressures(
        &pass_receive_input,
        pass_receive_context,
        PassReceiveTargetPressure {
            local: risk.target_local_pressure,
            receiver: risk.receiver_pressure,
        },
    );
    let after_value = after_state.value;
    let lane_risk = risk.lane_risk;
    let target_distance = risk.target_distance;
    let pressure = risk.receiver_pressure;
    let consequence = risk.turnover_consequence;
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
    let origin_progress = passer_context.origin_progress;
    let attracted_pressure = passer_context.attracted_pressure;
    let effective_current_value = passer_context.effective_current_value;
    let carry_count = input.passer_consecutive_carries.max(0) as f64;
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
    let origin_width = passer_context.origin_width;
    let current_shot = passer_context.current_shot;
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
    let risk_cost = (1.0 - success_prob) * (0.07 + 0.24 * consequence);
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
    let immediate_progress = progress_gain.max(0.0);
    let score = (success_prob * (0.018 + 0.18 * immediate_progress) - risk_cost).max(0.0);

    ExpectedPassOutput {
        score,
        success_prob,
        risk_cost,
        after_value,
        after_direct_xg: after_state.direct_xg,
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

    fn reference_pass_lane_risk(input: &PassLaneRiskInput<'_>) -> f64 {
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

    #[test]
    fn pass_lane_risk_distance_helper_preserves_reference_values() {
        for (origin, target, opponents) in [
            ((40.0, 34.0), (40.5, 34.0), &[(40.2, 34.0)][..]),
            (
                (40.0, 34.0),
                (70.0, 34.0),
                &[(55.0, 34.0), (61.0, 42.0)][..],
            ),
        ] {
            let input = PassLaneRiskInput {
                origin,
                target,
                opponents,
                interception_reach: 3.5,
            };
            let reference = reference_pass_lane_risk(&input);
            let (prepared, target_distance) = pass_lane_risk_with_distance(&input);

            assert_eq!(prepared.to_bits(), reference.to_bits());
            assert_eq!(
                target_distance.to_bits(),
                distance(origin, target).to_bits()
            );
        }
    }

    #[test]
    fn pass_risk_evaluation_preserves_independent_risk_components() {
        for (origin, target, opponents) in [
            (
                (40.0, 34.0),
                (40.5, 34.0),
                &[(40.2, 34.0), (44.0, 35.0)][..],
            ),
            (
                (40.0, 34.0),
                (70.0, 28.0),
                &[(55.0, 32.0), (65.0, 27.0), (35.0, 40.0)][..],
            ),
        ] {
            let loss_pos = ((origin.0 + target.0) / 2.0, (origin.1 + target.1) / 2.0);
            let prepared = pass_risk_evaluation(
                origin, target, opponents, 3.5, loss_pos, 105.0, 68.0, true, None,
            );
            let lane_input = PassLaneRiskInput {
                origin,
                target,
                opponents,
                interception_reach: 3.5,
            };
            let turnover_input = TurnoverConsequenceInput {
                loss_pos,
                opponents,
                pitch_length: 105.0,
                pitch_width: 68.0,
                attacking_right: true,
            };

            assert_eq!(
                prepared.lane_risk.to_bits(),
                pass_lane_risk(&lane_input).to_bits()
            );
            assert_eq!(
                prepared.target_distance.to_bits(),
                distance(origin, target).to_bits()
            );
            assert_eq!(
                prepared.receiver_pressure.to_bits(),
                receiver_pressure(target, opponents).to_bits()
            );
            assert_eq!(
                prepared.turnover_consequence.to_bits(),
                turnover_consequence(&turnover_input).to_bits()
            );
        }
    }

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

    #[test]
    fn pass_retention_calibration_rewards_clean_short_options_and_penalizes_risk() {
        let clean_short = pass_retention_probability(0.92, 0.90, 0.04, 0.06);
        let contested_long = pass_retention_probability(0.72, 0.45, 0.58, 0.62);
        let unreachable_delivery = pass_retention_probability(0.92, 0.0, 0.04, 0.06);

        assert!(clean_short > 0.80);
        assert!(contested_long < 0.55);
        assert!(unreachable_delivery < 0.55);
        assert!(clean_short > contested_long);
        assert!(clean_short > unreachable_delivery);
    }

    #[test]
    fn technical_accuracy_uses_ability_to_improve_the_base_rate() {
        let goalkeeper_short = pass_technical_accuracy(0.80, 60.0, 12.0, false);
        let defender_short = pass_technical_accuracy(0.80, 80.0, 12.0, false);
        let defender_long = pass_technical_accuracy(0.55, 80.0, 42.0, true);

        assert!(goalkeeper_short > 0.88);
        assert!(defender_short > goalkeeper_short);
        assert!(defender_long < defender_short);
    }

    #[test]
    fn technical_accuracy_does_not_duplicate_spatial_distance_error() {
        let short = pass_technical_accuracy(0.80, 80.0, 8.0, false);
        let distant = pass_technical_accuracy(0.80, 80.0, 28.0, false);

        assert!((short - distant).abs() <= f64::EPSILON);
    }

    #[test]
    fn pass_turnover_risk_keeps_the_more_dangerous_target_region() {
        let opponents = [(10.0, 34.0), (18.0, 31.0)];
        let combined =
            pass_turnover_consequence((45.0, 34.0), (12.0, 34.0), &opponents, 105.0, 68.0, true);
        let midpoint_only = turnover_consequence(&TurnoverConsequenceInput {
            loss_pos: (28.5, 34.0),
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        });

        assert!(
            combined > midpoint_only,
            "a backward pass into the defensive goal channel must retain its dangerous target-region turnover tail"
        );
    }

    #[test]
    fn local_pass_value_does_not_prepay_receiver_future_shooting() {
        let teammate_positions = [(1, 91.0, 39.0), (2, 95.0, 34.0), (3, 76.0, 22.0)];
        let opponents = [(100.0, 34.0), (84.0, 22.0), (88.0, 54.0)];
        let low_receiver_profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.30,
                long_shot: 0.30,
            },
            PlayerShotProfile {
                player_index: 2,
                finishing: 0.62,
                long_shot: 0.62,
            },
            PlayerShotProfile {
                player_index: 3,
                finishing: 0.58,
                long_shot: 0.58,
            },
        ];
        let high_receiver_profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.96,
                long_shot: 0.96,
            },
            PlayerShotProfile {
                player_index: 2,
                finishing: 0.62,
                long_shot: 0.62,
            },
            PlayerShotProfile {
                player_index: 3,
                finishing: 0.58,
                long_shot: 0.58,
            },
        ];
        let evaluate = |shot_profiles: &[PlayerShotProfile], receiver_finishing: f64| {
            expected_pass_value(&ExpectedPassInput {
                tick: 1,
                passer_index: 0,
                passer_team_home: true,
                passer_pos: (84.0, 31.0),
                passer_finishing: 0.78,
                passer_long_shot: 0.74,
                passer_consecutive_carries: 0,
                receiver_index: 1,
                receiver_team_home: true,
                receiver_finishing,
                receiver_long_shot: receiver_finishing,
                receiver_anchor: (91.0, 39.0),
                receiver_base: (84.0, 42.0),
                receiver_goal_type: None,
                receiver_goal_target: None,
                receiver_goal_value: 0.0,
                target: (91.0, 39.0),
                shot_profiles,
                teammate_positions: &teammate_positions,
                teammate_goalkeeper_indices: &[],
                opponent_positions: &opponents,
                pitch_length: 105.0,
                pitch_width: 68.0,
                attacking_right: true,
                offside_line: 105.0,
                interception_reach: 3.5,
                shot_ideal_distance: 20.0,
                shot_on_target_base: 0.52,
                gk_save_base: 0.66,
                gk_attributes: None,
                gk_pos: Some((100.0, 34.0)),
                contest_defenders: None,
                current_value: 0.08,
                base_accuracy: 0.91,
                receiver_arrival: 0.86,
                continuity: 0.055,
                shot_quality_cache: None,
            })
        };

        let low_receiver = evaluate(&low_receiver_profiles, 0.30);
        let high_receiver = evaluate(&high_receiver_profiles, 0.96);

        assert!(
            high_receiver.after_value > low_receiver.after_value,
            "the fixture must change the projected receipt state: low={low_receiver:?}, high={high_receiver:?}"
        );
        assert_eq!(
            high_receiver.score.to_bits(),
            low_receiver.score.to_bits(),
            "candidate-local pass value must not prepay receiver-side continuation or terminal value; Temporal evaluates that state after the pass"
        );
    }
}
