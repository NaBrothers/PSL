use crate::physics::{distance, player_speed, smoothstep};
use crate::shot_quality::{
    estimate_shot_outcome, shot_quality_at, ShotQualityCache, ShotQualityInput,
};
use crate::state_value::{shot_quality_cache_key, state_value, StateValueInput};

#[derive(Debug, Clone)]
pub struct HoldInput {
    pub iq: f64,
    pub is_midfielder: bool,
    pub is_defender: bool,
    pub hold_ticks: i32,
    pub possession_ticks: i32,
    pub current_pv: f64,
    pub pressure: i32,
    pub nearest_pressure: f64,
    pub developing_runs: f64,
    pub best_pass_score: f64,
    pub shoot_score: f64,
    pub opportunity_wait_value: f64,
}

#[derive(Debug, Clone)]
pub struct HoldOutput {
    pub score: f64,
    pub pressure_factor: f64,
    pub useful_development: f64,
    pub no_clear_release: f64,
    pub opportunity_wait: f64,
    pub poor_options_bonus: f64,
    pub hold_multiplier: f64,
    pub role_multiplier: f64,
    pub shot_interrupt: f64,
    pub opportunity_cost: f64,
}

#[derive(Debug, Clone)]
pub struct ClearInput {
    pub x_progress: f64,
    pub pressure: i32,
    pub clear_reward_base: f64,
}

#[derive(Debug, Clone)]
pub struct ClearOutput {
    pub score: f64,
    pub danger: f64,
    pub pressure_factor: f64,
}

#[derive(Debug, Clone)]
pub struct ShotSupportPlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub target: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone)]
pub struct ShotInput<'a> {
    pub tick: i32,
    pub shooter_index: usize,
    pub shooter_team_home: bool,
    pub shooter_pos: (f64, f64),
    pub finishing: f64,
    pub long_shot: f64,
    pub possession_ticks: i32,
    pub consecutive_carries: i32,
    pub last_receive_origin: (f64, f64),
    pub dist_to_goal: f64,
    pub angle_factor: f64,
    pub pressure_factor: f64,
    pub lane_factor: f64,
    pub dist_factor: f64,
    pub current_state_value: f64,
    pub teammates: &'a [ShotSupportPlayer],
    pub opponents: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<crate::goalkeeper::GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub shot_ideal_distance: f64,
    pub goal_reward_constant: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Debug, Clone)]
pub struct ShotOutput {
    pub score: f64,
    pub on_target_prob: f64,
    pub xg: f64,
    pub save_estimate: f64,
    pub risk_cost: f64,
    pub opportunity_cost: f64,
    pub shot_readiness: f64,
    pub open_medium_window: f64,
    pub clean_second_line_shot: f64,
    pub possession_loss_multiplier: f64,
    pub support_release_window: f64,
}

#[derive(Debug, Clone)]
pub struct CarrySupportPlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub base: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone)]
pub struct CarryInput<'a> {
    pub tick: i32,
    pub carrier_index: usize,
    pub carrier_team_home: bool,
    pub carrier_pos: (f64, f64),
    pub target: (f64, f64),
    pub finishing: f64,
    pub long_shot: f64,
    pub consecutive_carries: i32,
    pub possession_ticks: i32,
    pub target_pv: f64,
    pub current_pv: f64,
    pub current_state_value: f64,
    pub path_feasibility: f64,
    pub teammates: &'a [CarrySupportPlayer],
    pub opponents: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub carrier_speed: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Debug, Clone)]
pub struct CarryOutput {
    pub score: f64,
    pub after_value: f64,
    pub risk_cost: f64,
    pub continuity: f64,
    pub pv_gain: f64,
    pub current_shot: f64,
    pub target_shot: f64,
    pub future_shot_gain: f64,
    pub carry_to_shoot_window: f64,
    pub wide_second_line_carry_window: f64,
    pub byline_carry_window: f64,
    pub half_space_entry: f64,
    pub lane_gain: f64,
    pub progress_gain: f64,
    pub effective_gain: f64,
    pub near_goal_multiplier: f64,
    pub shooting_window_multiplier: f64,
    pub possession_multiplier: f64,
    pub final_third_stale_multiplier: f64,
    pub release_pressure: f64,
    pub support_nearby: f64,
    pub pressure_draw: f64,
    pub space_manipulation: f64,
}

#[derive(Debug, Clone)]
pub struct CarryTargetGenerationInput {
    pub carrier_pos: (f64, f64),
    pub speed: i32,
    pub dribbling: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub carrier_speed: f64,
    pub nearest_opponent_distance: f64,
}

#[derive(Debug, Clone)]
pub struct CarryTargetGenerationOutput {
    pub offsets: Vec<(f64, f64)>,
}

#[derive(Debug, Clone)]
pub struct CarryPathOpponentInput {
    pub pos: (f64, f64),
    pub speed: f64,
    pub defence: f64,
    pub tackling: f64,
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone)]
pub struct CarryPathInput<'a> {
    pub carrier_pos: (f64, f64),
    pub target: (f64, f64),
    pub dribbling: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub carrier_speed: f64,
    pub tackle_range: f64,
    pub opponents: &'a [CarryPathOpponentInput],
}

#[derive(Debug, Clone)]
pub struct CarryPathOutput {
    pub feasibility: f64,
    pub path_min_perp: f64,
    pub path_peak_threat: f64,
    pub path_peak_proj: f64,
    pub path_peak_final_third_control: f64,
    pub path_peak_control_factor: f64,
}

#[derive(Debug, Clone)]
pub struct CarryFinalizeInput {
    pub evaluator_score: f64,
    pub feasibility: f64,
    pub path_peak_threat: f64,
    pub path_peak_final_third_control: f64,
    pub consecutive_carries: i32,
}

#[derive(Debug, Clone)]
pub struct CarryFinalizeOutput {
    pub score: f64,
    pub conflict_cost: f64,
    pub repeated_load: f64,
    pub feasibility_loss: f64,
}

pub fn generate_carry_offsets(input: &CarryTargetGenerationInput) -> CarryTargetGenerationOutput {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let dribbling = input.dribbling / 100.0;
    let max_speed = player_speed(input.speed, input.player_max_speed, input.player_min_speed);
    let base_dist = input
        .carrier_speed
        .max(max_speed * (0.42 + 0.18 * dribbling));
    let mut offsets = vec![
        (forward_dir * base_dist, 0.0),
        (forward_dir * base_dist * 0.75, base_dist * 0.75),
        (forward_dir * base_dist * 0.75, -base_dist * 0.75),
        (0.0, base_dist),
        (0.0, -base_dist),
    ];
    let goal_center_y = input.pitch_width / 2.0;
    let center_pull = (goal_center_y - input.carrier_pos.1).clamp(-base_dist, base_dist);
    if center_pull.abs() > 0.25 {
        offsets.push((forward_dir * base_dist * 0.70, center_pull * 0.85));
        offsets.push((forward_dir * base_dist * 0.35, center_pull));
    }

    let goal_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let goal_dx = goal_x - input.carrier_pos.0;
    let goal_dy = goal_center_y - input.carrier_pos.1;
    let goal_dist = (goal_dx * goal_dx + goal_dy * goal_dy).sqrt().max(1.0);
    let goal_vec = (goal_dx / goal_dist, goal_dy / goal_dist);
    let forward_vec = (forward_dir, 0.0);
    let inside_vec_raw = (
        forward_dir * 0.45,
        if goal_center_y > input.carrier_pos.1 {
            1.0
        } else {
            -1.0
        },
    );
    let inside_len = (inside_vec_raw.0 * inside_vec_raw.0 + inside_vec_raw.1 * inside_vec_raw.1)
        .sqrt()
        .max(1.0);
    let inside_vec = (inside_vec_raw.0 / inside_len, inside_vec_raw.1 / inside_len);
    let width_t =
        ((input.carrier_pos.1 - goal_center_y).abs() / (input.pitch_width / 2.0)).min(1.0);
    let progress_t = if input.attacking_right {
        input.carrier_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.carrier_pos.0) / input.pitch_length
    };
    let shot_window_t = ((progress_t - 0.45) / 0.38).clamp(0.0, 1.0);
    for blend in [0.35, 0.65, 0.90] {
        let vx = forward_vec.0 * (1.0 - blend) + goal_vec.0 * blend;
        let vy = forward_vec.1 * (1.0 - blend) + goal_vec.1 * blend;
        let vlen = (vx * vx + vy * vy).sqrt().max(1.0);
        offsets.push((
            vx / vlen * base_dist * (1.0 + 0.25 * shot_window_t),
            vy / vlen * base_dist * (1.0 + 0.25 * width_t),
        ));
    }
    for scale in [0.85, 1.20] {
        offsets.push((
            inside_vec.0 * base_dist * scale * (0.75 + 0.35 * shot_window_t),
            inside_vec.1 * base_dist * scale * (0.55 + 0.55 * width_t),
        ));
    }
    let carry_horizon = base_dist * (1.55 + 0.45 * shot_window_t);
    for blend in [0.45, 0.75] {
        let vx = inside_vec.0 * (1.0 - blend) + goal_vec.0 * blend;
        let vy = inside_vec.1 * (1.0 - blend) + goal_vec.1 * blend;
        let vlen = (vx * vx + vy * vy).sqrt().max(1.0);
        offsets.push((
            vx / vlen * carry_horizon,
            vy / vlen * carry_horizon * (0.85 + 0.35 * width_t),
        ));
    }
    if progress_t > 0.68 && width_t > 0.28 {
        let side_sign = if input.carrier_pos.1 > goal_center_y {
            1.0
        } else {
            -1.0
        };
        let half_space_y = goal_center_y + side_sign * input.pitch_width * 0.14;
        let inner_channel_y = goal_center_y + side_sign * input.pitch_width * 0.08;
        let dx_to_half_space = forward_dir * base_dist * (1.82 + 0.58 * shot_window_t);
        let dy_to_half_space =
            (half_space_y - input.carrier_pos.1).clamp(-base_dist * 2.8, base_dist * 2.8);
        let dy_to_inner =
            (inner_channel_y - input.carrier_pos.1).clamp(-base_dist * 3.2, base_dist * 3.2);
        offsets.push((dx_to_half_space, dy_to_half_space));
        offsets.push((dx_to_half_space * 0.72, dy_to_half_space * 0.82));
        if progress_t > 0.72 {
            offsets.push((dx_to_half_space * 1.06, dy_to_inner));
            offsets.push((dx_to_half_space * 0.82, dy_to_inner * 0.74));
        }
    }
    if progress_t > 0.62 && width_t > 0.46 {
        let side_sign = if input.carrier_pos.1 > goal_center_y {
            1.0
        } else {
            -1.0
        };
        for (depth_scale, outward_scale) in [(1.35, 0.00), (1.95, 0.18), (2.45, 0.30)] {
            offsets.push((
                forward_dir * base_dist * depth_scale,
                side_sign * base_dist * outward_scale,
            ));
        }
    }
    if input.nearest_opponent_distance < 7.0 {
        offsets.push((-forward_dir * base_dist * 0.30, base_dist * 0.45));
        offsets.push((-forward_dir * base_dist * 0.30, -base_dist * 0.45));
    }

    CarryTargetGenerationOutput { offsets }
}

pub fn evaluate_carry_path(input: &CarryPathInput<'_>) -> CarryPathOutput {
    let dx = input.target.0 - input.carrier_pos.0;
    let dy = input.target.1 - input.carrier_pos.1;
    let move_len = (dx * dx + dy * dy).sqrt();
    let mut feasibility: f64 = 1.0;
    let my_speed = input.carrier_speed.max(0.1);
    let time_i_carry = move_len / my_speed;
    let mut path_min_perp: f64 = 99.0;
    let mut path_peak_threat: f64 = 0.0;
    let mut path_peak_proj: f64 = 0.0;
    let mut path_peak_final_third_control: f64 = 0.0;
    let mut path_peak_control_factor: f64 = 0.0;

    if move_len < 0.1 {
        return CarryPathOutput {
            feasibility,
            path_min_perp,
            path_peak_threat,
            path_peak_proj,
            path_peak_final_third_control,
            path_peak_control_factor,
        };
    }

    for opp in input.opponents {
        if opp.is_goalkeeper {
            continue;
        }
        let opp_dx = opp.pos.0 - input.carrier_pos.0;
        let opp_dy = opp.pos.1 - input.carrier_pos.1;
        let perp_dist = (opp_dx * (dy / move_len) - opp_dy * (dx / move_len)).abs();
        let proj = (opp_dx * dx + opp_dy * dy) / (move_len * move_len);
        if !(-0.5..=2.0).contains(&proj) {
            continue;
        }
        path_min_perp = path_min_perp.min(perp_dist);

        let def_speed = (opp.speed / 100.0) * input.player_max_speed;
        let time_def_reaches = perp_dist / def_speed.max(0.1);
        let intent_factor = 0.62;
        let speed_factor = 0.82 + 0.36 * (opp.speed / 100.0);
        let defence_factor = 0.82 + 0.30 * (opp.defence / 100.0);
        let control_range = input.tackle_range * intent_factor * speed_factor * defence_factor;
        let duel_control = (1.0 - perp_dist / control_range.max(0.1)).max(0.0)
            * ((proj + 0.10) / 1.10).clamp(0.0, 1.0)
            * ((1.10 - proj) / 1.10).clamp(0.0, 1.0);
        if duel_control > 0.0 {
            let my_drib = input.dribbling / 100.0;
            let def_tack = opp.tackling / 100.0;
            let control_factor = def_tack / (my_drib + def_tack + 0.01);
            feasibility *= (1.0 - duel_control * control_factor * 0.46).max(0.34);
            path_peak_threat = path_peak_threat.max(duel_control);
        }

        let target_progress = if input.attacking_right {
            input.target.0 / input.pitch_length
        } else {
            (input.pitch_length - input.target.0) / input.pitch_length
        };
        let central_lane = 1.0
            - ((input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                .min(1.0);
        let final_third_control = ((target_progress - 0.72) / 0.18).clamp(0.0, 1.0)
            * central_lane
            * (1.0 - perp_dist / 5.8).max(0.0)
            * ((proj + 0.15) / 1.15).clamp(0.0, 1.0)
            * ((1.15 - proj) / 1.15).clamp(0.0, 1.0);
        if final_third_control > 0.0 {
            let my_drib = input.dribbling / 100.0;
            let def_tack = opp.tackling / 100.0;
            let control_factor = def_tack / (my_drib + def_tack + 0.01);
            if final_third_control > path_peak_final_third_control {
                path_peak_final_third_control = final_third_control;
                path_peak_proj = proj;
                path_peak_control_factor = control_factor;
            }
            feasibility *= (1.0 - final_third_control * control_factor * 0.34).max(0.48);
        }

        if time_def_reaches < time_i_carry {
            let threat = (1.0 - time_def_reaches / time_i_carry).max(0.0);
            let my_drib = input.dribbling / 100.0;
            let def_tack = opp.tackling / 100.0;
            let skill_factor = my_drib / (my_drib + def_tack + 0.01);
            let reduction = threat * (1.0 - skill_factor);
            if threat > path_peak_threat {
                path_peak_threat = threat;
                path_peak_proj = proj;
            }
            feasibility *= (1.0 - reduction).max(0.2);
        }
    }

    CarryPathOutput {
        feasibility,
        path_min_perp,
        path_peak_threat,
        path_peak_proj,
        path_peak_final_third_control,
        path_peak_control_factor,
    }
}

pub fn finalize_carry_score(input: &CarryFinalizeInput) -> CarryFinalizeOutput {
    let conflict_load = input
        .path_peak_threat
        .max(input.path_peak_final_third_control);
    let repeated_load = smoothstep(0.0, 3.0, input.consecutive_carries.max(0) as f64);
    let feasibility_loss = smoothstep(0.0, 0.55, 1.0 - input.feasibility);
    let conflict_cost = conflict_load.powf(1.35)
        * (0.020
            + 0.115 * repeated_load
            + 0.075 * feasibility_loss
            + 0.105 * repeated_load * feasibility_loss);
    CarryFinalizeOutput {
        score: (input.evaluator_score - conflict_cost).max(0.0),
        conflict_cost,
        repeated_load,
        feasibility_loss,
    }
}

pub fn evaluate_hold(input: &HoldInput) -> HoldOutput {
    let pressure_factor = (1.0 / (1.0 + input.pressure as f64 * 0.55))
        * (1.0 - input.nearest_pressure * 0.82).max(0.18);
    let poor_options_bonus = (0.055 - input.best_pass_score).max(0.0) * 0.24;
    let low_pressure_wait = 1.0 - smoothstep(0.10, 0.45, input.nearest_pressure);
    let useful_development = (input.developing_runs / 2.0).min(1.0) * low_pressure_wait;
    let shot_quality_window = smoothstep(0.08, 0.18, input.shoot_score);
    let no_clear_release = (1.0 - smoothstep(0.055, 0.125, input.shoot_score))
        * (1.0 - smoothstep(0.070, 0.170, input.best_pass_score))
        * low_pressure_wait;
    let opportunity_wait =
        input.opportunity_wait_value.clamp(0.0, 1.0) * (1.0 - 0.70 * shot_quality_window);
    let mut settle_value = 0.010
        + input.current_pv * 0.025
        + useful_development * 0.018
        + opportunity_wait * 0.026
        + no_clear_release * 0.024
        + poor_options_bonus;
    let role_multiplier = 1.0
        + if input.is_midfielder { 0.06 } else { 0.0 }
        + if input.is_defender { 0.03 } else { 0.0 };
    settle_value *= role_multiplier;

    let mut score = settle_value * (0.65 + 0.45 * input.iq) * pressure_factor;
    let shot_interrupt = shot_quality_window;
    score *= 1.0 - 0.55 * shot_interrupt;
    let opportunity_cost =
        (input.best_pass_score - 0.075).max(0.0) * 0.38 * (1.0 - 0.55 * no_clear_release);
    let hold_multiplier = 1.0
        / (1.0
            + input.hold_ticks.max(0) as f64 * 0.62
            + (input.possession_ticks - 2).max(0) as f64 * 0.38);
    score *= hold_multiplier;
    score = (score - opportunity_cost).max(0.0);

    HoldOutput {
        score,
        pressure_factor,
        useful_development,
        no_clear_release,
        opportunity_wait,
        poor_options_bonus,
        hold_multiplier,
        role_multiplier,
        shot_interrupt,
        opportunity_cost,
    }
}

pub fn evaluate_clear(input: &ClearInput) -> ClearOutput {
    let danger = (1.0 - input.x_progress / 0.45).max(0.0);
    let pressure_factor = 1.0 - (-(input.pressure as f64) / 2.0).exp();
    let score = (danger * pressure_factor * input.clear_reward_base).max(0.0);
    ClearOutput {
        score,
        danger,
        pressure_factor,
    }
}

pub fn evaluate_shot(input: &ShotInput<'_>) -> ShotOutput {
    let shot_outcome = estimate_shot_outcome(&ShotQualityInput {
        x: input.shooter_pos.0,
        y: input.shooter_pos.1,
        finishing: input.finishing,
        long_shot: input.long_shot,
        opponents: input.opponents,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.map(|_| {
            shot_quality_cache_key(
                input.tick,
                input.shooter_team_home,
                input.shooter_index,
                input.shooter_pos,
                input.attacking_right,
            )
        }),
    });
    let on_target_prob = shot_outcome.on_target_prob;
    let save_estimate = shot_outcome.save_prob;
    let xg = shot_outcome.xg;
    let mut score = xg * input.goal_reward_constant;
    let mut low_quality_multiplier = 0.30 + 0.70 * smoothstep(0.035, 0.13, xg);
    let first_time_window = (1.0 - smoothstep(2.0, 5.0, input.possession_ticks.max(0) as f64))
        * (1.0 - smoothstep(1.0, 3.0, input.consecutive_carries.max(0) as f64));
    let receive_origin_progress = if input.attacking_right {
        input.last_receive_origin.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.last_receive_origin.0) / input.pitch_length.max(1.0)
    };
    let shooter_progress = if input.attacking_right {
        input.shooter_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.shooter_pos.0) / input.pitch_length.max(1.0)
    };
    let receive_drop = (receive_origin_progress - shooter_progress).max(0.0);
    let shooter_centrality = 1.0
        - ((input.shooter_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
            .min(1.0);
    let layoff_second_line_window = first_time_window
        * smoothstep(0.035, 0.095, xg)
        * smoothstep(0.035, 0.14, receive_drop)
        * smoothstep(0.55, 0.90, shooter_centrality)
        * smoothstep(0.70, 0.98, input.pressure_factor * input.lane_factor)
        * (1.0 - smoothstep(30.0, 42.0, input.dist_to_goal));
    let open_medium_window = first_time_window
        * smoothstep(0.030, 0.095, xg)
        * smoothstep(0.56, 0.86, input.angle_factor)
        * smoothstep(0.70, 0.98, input.pressure_factor * input.lane_factor)
        * (1.0 - smoothstep(30.0, 42.0, input.dist_to_goal));
    low_quality_multiplier =
        low_quality_multiplier.max(0.38 + 0.34 * open_medium_window.max(layoff_second_line_window));
    score *= low_quality_multiplier;
    let second_line_window = smoothstep(0.038, 0.090, xg)
        * (1.0 - smoothstep(24.0, 36.0, input.dist_to_goal))
        * smoothstep(0.58, 0.88, input.angle_factor)
        * smoothstep(0.78, 0.98, input.pressure_factor * input.lane_factor);
    let clean_second_line_shot = first_time_window
        * second_line_window
        * smoothstep(0.55, 0.88, input.angle_factor)
        * smoothstep(0.72, 0.98, input.pressure_factor * input.lane_factor);
    let second_line_bonus = 1.0 + 0.72 * first_time_window * second_line_window;
    score *= second_line_bonus;
    let close_bonus = (1.0 - smoothstep(14.0, 22.0, input.dist_to_goal))
        * smoothstep(0.55, 0.85, input.angle_factor)
        * smoothstep(0.08, 0.16, xg);
    let medium_bonus = (1.0 - smoothstep(20.0, 30.0, input.dist_to_goal))
        * smoothstep(0.45, 0.75, input.angle_factor)
        * smoothstep(0.06, 0.13, xg);
    let shot_quality_bonus = 1.0
        + 0.60 * close_bonus
        + 0.42 * medium_bonus
        + 0.30 * open_medium_window
        + 0.26 * layoff_second_line_window;
    score *= shot_quality_bonus;
    let shot_readiness = smoothstep(0.045, 0.16, xg)
        .max(open_medium_window * 0.48)
        .max(layoff_second_line_window * 0.58);
    let distance_cost = smoothstep(24.0, 44.0, input.dist_to_goal);
    let mut possession_value_cost =
        (input.current_state_value - xg).max(0.0) * (1.0 - shot_readiness) * 0.18;
    possession_value_cost *= 1.0
        - 0.55 * clean_second_line_shot
        - 0.34 * open_medium_window
        - 0.40 * layoff_second_line_window;
    let mut attracted_pressure = 0.0;
    for opp in input.opponents {
        let d = distance(input.shooter_pos, *opp);
        if d < 11.0 {
            attracted_pressure += 1.0 - d / 11.0;
        }
    }
    attracted_pressure = (attracted_pressure * 0.42).min(1.0);

    let mut support_nearby: f64 = 0.0;
    let mut developing_support: f64 = 0.0;
    let mut second_line_support: f64 = 0.0;
    let mut layoff_support: f64 = 0.0;
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let shooter_width =
        (input.shooter_pos.1 - input.pitch_width / 2.0).abs() / input.pitch_width.max(1.0) * 2.0;
    for tm in input.teammates {
        if tm.index == input.shooter_index || tm.is_goalkeeper {
            continue;
        }
        let tm_progress = if input.attacking_right {
            tm.pos.0 / input.pitch_length.max(1.0)
        } else {
            (input.pitch_length - tm.pos.0) / input.pitch_length.max(1.0)
        };
        let target_progress = if input.attacking_right {
            tm.target.0 / input.pitch_length.max(1.0)
        } else {
            (input.pitch_length - tm.target.0) / input.pitch_length.max(1.0)
        };
        let target_centrality = 1.0
            - ((tm.target.1 - input.pitch_width / 2.0).abs() / input.pitch_width.max(1.0) * 2.0)
                .min(1.0);
        let target_width =
            (tm.target.1 - input.pitch_width / 2.0).abs() / input.pitch_width.max(1.0) * 2.0;
        let d = distance(input.shooter_pos, tm.pos);
        let target_d = distance(input.shooter_pos, tm.target);
        support_nearby =
            support_nearby.max(smoothstep(6.0, 13.0, d) * (1.0 - smoothstep(24.0, 34.0, d)));
        let move_progress = (tm.target.0 - tm.pos.0) * forward_dir;
        let moving_into_window = smoothstep(0.0, 5.0, move_progress.max(0.0))
            * smoothstep(0.58, 0.76, target_progress)
            * (1.0 - smoothstep(0.86, 0.95, target_progress))
            * smoothstep(0.38, 0.82, target_centrality)
            * (1.0 - smoothstep(18.0, 32.0, target_d));
        developing_support = developing_support.max(moving_into_window);
        let depth_gap = (input.shooter_pos.0 - tm.target.0) * forward_dir;
        let second_line_candidate = smoothstep(0.66, 0.84, shooter_progress)
            * smoothstep(0.60, 0.82, target_progress)
            * (1.0 - smoothstep(0.84, 0.95, target_progress))
            * smoothstep(4.0, 13.0, depth_gap)
            * (1.0 - smoothstep(24.0, 36.0, depth_gap))
            * smoothstep(0.42, 0.88, target_centrality)
            * (1.0 - smoothstep(20.0, 34.0, target_d));
        second_line_support = second_line_support.max(second_line_candidate);
        let lateral_gap = (tm.target.1 - input.shooter_pos.1).abs();
        let layoff_candidate = smoothstep(0.70, 0.90, shooter_progress)
            * smoothstep(5.0, 14.0, target_d)
            * (1.0 - smoothstep(24.0, 36.0, target_d))
            * smoothstep(0.15, 0.58, shooter_width.max(target_width))
            * smoothstep(0.18, 0.64, lateral_gap / (input.pitch_width / 2.0).max(1.0))
            * smoothstep(0.35, 0.82, target_centrality);
        layoff_support = layoff_support.max(layoff_candidate);
        let _ = tm_progress;
    }
    let repeated_carry_pressure = smoothstep(1.0, 3.0, input.consecutive_carries.max(0) as f64)
        * smoothstep(0.18, 0.65, attracted_pressure)
        * (1.0 - smoothstep(0.16, 0.28, xg));
    let stale_shot_pressure = smoothstep(2.0, 5.0, input.consecutive_carries.max(0) as f64)
        * (0.45 + 0.55 * smoothstep(0.08, 0.55, attracted_pressure))
        * (1.0 - smoothstep(0.20, 0.34, xg));
    let support_release_window = support_nearby.max(0.0) * developing_support;
    let support_release_window = support_release_window
        .max(second_line_support)
        .max(layoff_support)
        * (1.0 - shot_readiness * 0.72)
        * (1.0 - smoothstep(0.13, 0.26, xg));
    let opportunity_cost = (1.0 - shot_readiness) * 0.18
        + distance_cost * 0.11
        + possession_value_cost
        + repeated_carry_pressure * 0.12
        + stale_shot_pressure * 0.16
        + support_release_window * 0.15;
    let possession_loss_multiplier = (1.0 - opportunity_cost).max(0.35);
    let abandonment_cost = opportunity_cost * (0.012 + 0.050 * (1.0 - shot_readiness));
    score = score * possession_loss_multiplier - abandonment_cost;

    ShotOutput {
        score,
        on_target_prob,
        xg,
        save_estimate,
        risk_cost: 1.0 - possession_loss_multiplier,
        opportunity_cost,
        shot_readiness,
        open_medium_window,
        clean_second_line_shot,
        possession_loss_multiplier,
        support_release_window,
    }
}

fn clamp_pitch(pos: (f64, f64), length: f64, width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, length - 0.5),
        pos.1.clamp(0.5, width - 0.5),
    )
}

pub fn evaluate_carry(input: &CarryInput<'_>) -> CarryOutput {
    let teammate_positions: Vec<(usize, f64, f64)> = input
        .teammates
        .iter()
        .map(|tm| (tm.index, tm.pos.0, tm.pos.1))
        .collect();
    let teammate_goalkeeper_indices: Vec<usize> = input
        .teammates
        .iter()
        .filter(|tm| tm.is_goalkeeper)
        .map(|tm| tm.index)
        .collect();
    let after_value = state_value(&StateValueInput {
        pos: input.target,
        player_index: input.carrier_index,
        player_team_home: input.carrier_team_home,
        tick: input.tick,
        finishing: input.finishing,
        long_shot: input.long_shot,
        teammate_positions: &teammate_positions,
        teammate_goalkeeper_indices: &teammate_goalkeeper_indices,
        opponent_positions: input.opponents,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        shot_quality_cache: input.shot_quality_cache,
    });
    let current_shot = shot_quality_at(&ShotQualityInput {
        x: input.carrier_pos.0,
        y: input.carrier_pos.1,
        finishing: input.finishing,
        long_shot: input.long_shot,
        opponents: input.opponents,
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
                input.carrier_team_home,
                input.carrier_index,
                input.carrier_pos,
                input.attacking_right,
            )
        }),
    });
    let target_shot = shot_quality_at(&ShotQualityInput {
        x: input.target.0,
        y: input.target.1,
        finishing: input.finishing,
        long_shot: input.long_shot,
        opponents: input.opponents,
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
                input.carrier_team_home,
                input.carrier_index,
                input.target,
                input.attacking_right,
            )
        }),
    });
    let shot_quality_gain = (target_shot - current_shot).max(0.0);
    let risk_cost = (1.0 - input.path_feasibility) * 0.10;
    let pv_gain = input.target_pv - input.current_pv;

    let goal_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let goal_y = input.pitch_width / 2.0;
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let old_goal_dist = distance(input.carrier_pos, (goal_x, goal_y));
    let new_goal_dist = distance(input.target, (goal_x, goal_y));
    let old_angle_width = (input.carrier_pos.1 - goal_y).abs();
    let new_angle_width = (input.target.1 - goal_y).abs();
    let width_base = (input.pitch_width / 2.0).max(1.0);
    let lane_gain = (old_angle_width - new_angle_width).max(0.0) / width_base;
    let progress_gain = ((input.target.0 - input.carrier_pos.0) * forward_dir).max(0.0)
        / input.pitch_length.max(1.0);
    let step = input.carrier_speed * 1.75;
    let step = step.clamp(3.0, 7.5);
    let to_goal_x = goal_x - input.target.0;
    let to_goal_y = goal_y - input.target.1;
    let to_goal_len = (to_goal_x * to_goal_x + to_goal_y * to_goal_y)
        .sqrt()
        .max(1.0);
    let future_points = [
        (
            input.target.0 + to_goal_x / to_goal_len * step,
            input.target.1 + to_goal_y / to_goal_len * step,
        ),
        (
            input.target.0 + forward_dir * step * 0.70,
            input.target.1 + (goal_y - input.target.1) * 0.55,
        ),
        (
            input.target.0 + forward_dir * step * 0.45,
            input.target.1 + (goal_y - input.target.1) * 0.85,
        ),
    ];
    let mut future_shot = target_shot;
    for point in future_points {
        let fpos = clamp_pitch(point, input.pitch_length, input.pitch_width);
        future_shot = future_shot.max(shot_quality_at(&ShotQualityInput {
            x: fpos.0,
            y: fpos.1,
            finishing: input.finishing,
            long_shot: input.long_shot,
            opponents: input.opponents,
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
                    input.carrier_team_home,
                    input.carrier_index,
                    fpos,
                    input.attacking_right,
                )
            }),
        }));
    }
    let future_shot_gain = (future_shot - current_shot).max(0.0);
    let old_progress = if input.attacking_right {
        input.carrier_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.carrier_pos.0) / input.pitch_length.max(1.0)
    };
    let old_width_ratio = old_angle_width / width_base;
    let new_width_ratio = new_angle_width / width_base;
    let target_progress = if input.attacking_right {
        input.target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality = 1.0
        - ((input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let half_space_entry = smoothstep(0.58, 0.78, old_progress)
        * (1.0 - smoothstep(0.84, 0.92, old_progress))
        * smoothstep(0.20, 0.50, old_width_ratio)
        * smoothstep(0.025, 0.18, old_width_ratio - new_width_ratio)
        * (0.35 + 0.65 * smoothstep(0.006, 0.050, future_shot_gain));
    let mut carry_to_shoot_window = future_shot_gain
        * (0.24
            + 0.62 * smoothstep(0.02, 0.22, lane_gain)
            + 0.26 * smoothstep(0.00, 0.08, progress_gain)
            + 0.42 * half_space_entry);
    let wide_cut_in_window = smoothstep(0.50, 0.86, old_width_ratio)
        * smoothstep(0.62, 0.84, old_progress)
        * smoothstep(0.03, 0.14, future_shot_gain);
    carry_to_shoot_window *= 1.0 + 0.55 * wide_cut_in_window + 0.75 * half_space_entry;
    let effective_gain = pv_gain
        .max(shot_quality_gain * 0.90)
        .max(carry_to_shoot_window * 1.55);
    let wide_second_line_carry_window = smoothstep(0.62, 0.80, old_progress)
        * smoothstep(0.46, 0.82, old_width_ratio)
        * smoothstep(0.18, 0.58, new_width_ratio)
        * smoothstep(0.04, 0.13, future_shot_gain)
        * (1.0 - smoothstep(1.0, 3.0, input.consecutive_carries.max(0) as f64));
    let byline_carry_window = smoothstep(0.58, 0.80, old_progress)
        * smoothstep(0.48, 0.86, old_width_ratio)
        * smoothstep(0.72, 0.92, target_progress)
        * smoothstep(0.50, 0.90, new_width_ratio)
        * smoothstep(0.010, 0.085, progress_gain)
        * smoothstep(0.42, 0.86, input.path_feasibility)
        * (1.0 - smoothstep(0.88, 0.98, old_progress));

    let mut continuity = input.current_pv * (0.012 + 0.055 * smoothstep(0.00, 0.12, pv_gain));
    continuity += shot_quality_gain * (0.55 + 0.70 * smoothstep(0.02, 0.14, shot_quality_gain));
    continuity += carry_to_shoot_window * (0.95 + 0.60 * smoothstep(0.03, 0.15, future_shot_gain));
    continuity += wide_second_line_carry_window
        * (0.010 + 0.14 * future_shot_gain + 0.014 * smoothstep(0.02, 0.12, lane_gain));
    continuity += half_space_entry
        * (0.030
            + 0.095 * smoothstep(0.025, 0.18, lane_gain)
            + 0.22 * future_shot_gain
            + 0.030 * smoothstep(0.00, 0.08, progress_gain));
    continuity += byline_carry_window
        * (0.045
            + 0.090 * smoothstep(0.02, 0.12, progress_gain)
            + 0.040 * smoothstep(0.45, 0.90, old_width_ratio));
    let mut score = (input.path_feasibility
        * (after_value - input.current_state_value + continuity)
        - risk_cost)
        .max(0.0);

    let near_goal_pressure = 1.0 - smoothstep(16.0, 26.0, old_goal_dist);
    let angle_worsening = (new_angle_width - old_angle_width).max(0.0);
    let distance_worsening = (new_goal_dist - old_goal_dist).max(0.0);
    let wide_penalty = 1.0 - near_goal_pressure * 0.45 * smoothstep(0.0, 8.0, angle_worsening);
    let too_close_penalty =
        1.0 - near_goal_pressure * 0.55 * (1.0 - smoothstep(3.0, 8.0, new_goal_dist));
    let backwards_penalty =
        1.0 - near_goal_pressure * 0.35 * smoothstep(0.0, 6.0, distance_worsening);
    let low_gain_penalty =
        1.0 - near_goal_pressure * 0.35 * (1.0 - smoothstep(0.02, 0.10, effective_gain));
    let near_goal_multiplier =
        (wide_penalty * too_close_penalty * backwards_penalty * low_gain_penalty).max(0.08);
    score *= near_goal_multiplier;
    let extra_touch_gain = shot_quality_gain.max(future_shot_gain);
    let shot_window = smoothstep(0.07, 0.14, current_shot)
        * (1.0 - smoothstep(18.0, 28.0, old_goal_dist))
        * (1.0 - smoothstep(7.0, 18.0, old_angle_width));
    let extra_touch_improvement = smoothstep(0.03, 0.09, extra_touch_gain);
    let shooting_window_multiplier =
        (1.0 - 0.50 * shot_window * (1.0 - extra_touch_improvement)).max(0.45);
    score *= shooting_window_multiplier;

    let stale_ticks = (input.possession_ticks - 2).max(0) as f64;
    let low_gain_pressure = 1.0 - smoothstep(0.03, 0.12, effective_gain);
    let possession_multiplier = 1.0 / (1.0 + stale_ticks * 0.20 * low_gain_pressure);
    let low_gain_multiplier = 0.65 + 0.35 * smoothstep(0.0, 0.06, effective_gain);
    let final_third_carry =
        smoothstep(0.72, 0.88, target_progress) * smoothstep(0.35, 0.75, target_centrality);
    let mut support_nearby: f64 = 0.0;
    for tm in input.teammates {
        if tm.index == input.carrier_index || tm.is_goalkeeper {
            continue;
        }
        let d = distance(tm.pos, input.carrier_pos);
        if d > 6.0 && d < 26.0 {
            let base_progress = if input.attacking_right {
                tm.base.0 / input.pitch_length.max(1.0)
            } else {
                (input.pitch_length - tm.base.0) / input.pitch_length.max(1.0)
            };
            let carrier_support_depth = 1.0 - smoothstep(0.86, 0.98, base_progress);
            support_nearby = support_nearby
                .max((1.0 - (d - 18.0).abs() / 12.0) * (0.42 + 0.58 * carrier_support_depth));
        }
    }
    let support_release_cost = 1.0 + 0.55 * support_nearby;
    let repeated_carry_load = smoothstep(2.0, 5.0, input.consecutive_carries.max(0) as f64);
    let release_pressure = final_third_carry
        * repeated_carry_load
        * support_release_cost
        * (0.62 + 0.38 * (1.0 - smoothstep(0.12, 0.28, effective_gain)));
    let origin_width =
        (input.carrier_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let lateral_shift =
        (input.target.1 - input.carrier_pos.1).abs() / (input.pitch_width / 2.0).max(1.0);
    let pressure_draw = smoothstep(0.54, 0.86, old_progress)
        * smoothstep(0.18, 0.72, origin_width.max(old_width_ratio))
        * smoothstep(0.04, 0.30, lateral_shift)
        * (0.45 + 0.55 * smoothstep(0.02, 0.14, lane_gain.max(future_shot_gain)));
    let space_manipulation = pressure_draw
        .max(half_space_entry * 0.85)
        .max(wide_second_line_carry_window * 0.72)
        .max(smoothstep(0.04, 0.18, lane_gain) * smoothstep(0.58, 0.86, old_progress));
    let final_third_stale_multiplier =
        1.0 / (1.0 + (input.consecutive_carries - 1).max(0) as f64 * 0.56 * release_pressure);
    score *= possession_multiplier * low_gain_multiplier * final_third_stale_multiplier;

    CarryOutput {
        score,
        after_value,
        risk_cost,
        continuity,
        pv_gain,
        current_shot,
        target_shot,
        future_shot_gain,
        carry_to_shoot_window,
        wide_second_line_carry_window,
        byline_carry_window,
        half_space_entry,
        lane_gain,
        progress_gain,
        effective_gain,
        near_goal_multiplier,
        shooting_window_multiplier,
        possession_multiplier,
        final_third_stale_multiplier,
        release_pressure,
        support_nearby,
        pressure_draw,
        space_manipulation,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::goalkeeper::GkSaveAttributes;

    #[test]
    fn hold_score_decreases_under_pressure() {
        let calm = evaluate_hold(&HoldInput {
            iq: 0.8,
            is_midfielder: true,
            is_defender: false,
            hold_ticks: 0,
            possession_ticks: 1,
            current_pv: 0.4,
            pressure: 0,
            nearest_pressure: 0.0,
            developing_runs: 1.0,
            best_pass_score: 0.02,
            shoot_score: 0.02,
            opportunity_wait_value: 0.4,
        });
        let pressed = evaluate_hold(&HoldInput {
            pressure: 2,
            nearest_pressure: 0.8,
            ..HoldInput {
                iq: 0.8,
                is_midfielder: true,
                is_defender: false,
                hold_ticks: 0,
                possession_ticks: 1,
                current_pv: 0.4,
                pressure: 0,
                nearest_pressure: 0.0,
                developing_runs: 1.0,
                best_pass_score: 0.02,
                shoot_score: 0.02,
                opportunity_wait_value: 0.4,
            }
        });
        assert!(calm.score > pressed.score);
    }

    #[test]
    fn meaningless_extreme_range_shot_has_negative_utility() {
        let teammates = [];
        let opponents = [];
        let shot = evaluate_shot(&ShotInput {
            tick: 1,
            shooter_index: 1,
            shooter_team_home: true,
            shooter_pos: (12.0, 34.0),
            finishing: 0.90,
            long_shot: 0.99,
            possession_ticks: 4,
            consecutive_carries: 1,
            last_receive_origin: (12.0, 34.0),
            dist_to_goal: 93.0,
            angle_factor: 1.0,
            pressure_factor: 1.0,
            lane_factor: 1.0,
            dist_factor: 0.01,
            current_state_value: 0.20,
            teammates: &teammates,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: Some(GkSaveAttributes {
                gk_saving: 84.0,
                gk_positioning: 82.0,
                gk_reaction: 86.0,
                gk_position_error_factor: 0.05,
                gk_reaction_delay_factor: 0.005,
                gk_save_base: 0.66,
            }),
            gk_pos: Some((100.5, 34.0)),
            shot_ideal_distance: 20.0,
            goal_reward_constant: 1.0,
            shot_quality_cache: None,
        });

        assert!(
            shot.score < 0.0,
            "a near-full-pitch shot should lose to preserving possession without a distance ban"
        );
    }
}
