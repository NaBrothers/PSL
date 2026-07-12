use crate::decision::softmax_select_index_with_temperature;
use crate::goal::iq_temperature_factor;
use crate::offside::is_offside_position;
use crate::physics::{distance, player_speed, smoothstep};
use crate::position_value::{
    position_value, receive_reachability, space_creation_value, PositionValueInput,
};

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackCandidateInput {
    pub pos: (f64, f64),
    pub anchor_pos: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallTeammateInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackGoalInput<'a> {
    pub goal_type: &'a str,
    pub target_pos: (f64, f64),
    pub value: f64,
}

#[derive(Debug)]
pub struct OffBallAttackBatchInput<'a> {
    pub player_index: usize,
    pub player_pos: (f64, f64),
    pub player_speed: i32,
    pub anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub offside_line: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pass_to_space_ball_speed: f64,
    pub receive_reachability_scale: f64,
    pub space_creation_radius: f64,
    pub candidates: &'a [OffBallAttackCandidateInput],
    pub opponent_positions: &'a [(f64, f64)],
    pub opponent_speeds: &'a [f64],
    pub teammate_positions: &'a [(f64, f64)],
    pub teammates: &'a [OffBallTeammateInput],
    pub current_goal: Option<OffBallAttackGoalInput<'a>>,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackCandidateOutput {
    pub score: f64,
    pub target: (f64, f64),
    pub pv: f64,
    pub reach: f64,
    pub movement_reach: f64,
    pub immediate_reach: f64,
    pub pass_feasibility: f64,
    pub space_bonus: f64,
    pub role_shape_factor: f64,
    pub role_overlap_factor: f64,
    pub role_overlap: f64,
    pub lane_factor: f64,
    pub offside_penalty: f64,
    pub support_angle_value: f64,
    pub inside_support: f64,
    pub second_line_support: f64,
    pub arrival_goal_fit: f64,
    pub arrival_goal_multiplier: f64,
    pub arrival_goal_bonus: f64,
    pub layoff_window: f64,
    pub candidate_progress: f64,
    pub candidate_width: f64,
    pub support_angle_dist: f64,
    pub dist_to_ball: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct RandomPolarSample {
    pub angle_unit: f64,
    pub radius_unit: f64,
}

#[derive(Debug)]
pub struct OffBallRawGenerationInput<'a> {
    pub anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_width: f64,
    pub pitch_length: f64,
    pub is_defender: bool,
    pub has_ball_carrier: bool,
    pub anchor_samples: &'a [RandomPolarSample],
    pub support_samples: &'a [RandomPolarSample],
}

#[derive(Debug)]
pub struct OffBallAttackChoiceInput<'a> {
    pub player_index: usize,
    pub player_pos: (f64, f64),
    pub player_speed: i32,
    pub anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub offside_line: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pass_to_space_ball_speed: f64,
    pub receive_reachability_scale: f64,
    pub space_creation_radius: f64,
    pub iq: f64,
    pub stay_score: f64,
    pub candidates: &'a [OffBallAttackCandidateInput],
    pub opponent_positions: &'a [(f64, f64)],
    pub opponent_speeds: &'a [f64],
    pub teammate_positions: &'a [(f64, f64)],
    pub teammates: &'a [OffBallTeammateInput],
    pub current_goal: Option<OffBallAttackGoalInput<'a>>,
    pub score_noises: &'a [f64],
    pub roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackChoiceOutput {
    pub target: (f64, f64),
    pub score: f64,
    pub max_score: f64,
    pub candidate_count: usize,
    pub used_roll: bool,
    pub components: OffBallAttackChoiceComponents,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackChoiceComponents {
    // 0 = stay, 1 = space, 2 = low-value recover-shape fallback.
    pub kind: u8,
    pub pv: f64,
    pub reach: f64,
    pub movement_reach: f64,
    pub immediate_reach: f64,
    pub pass_feasibility: f64,
    pub space_bonus: f64,
    pub role_shape_factor: f64,
    pub role_overlap_factor: f64,
    pub role_overlap: f64,
    pub lane_factor: f64,
    pub offside_penalty: f64,
    pub support_angle_value: f64,
    pub inside_support: f64,
    pub second_line_support: f64,
    pub arrival_goal_fit: f64,
    pub arrival_goal_multiplier: f64,
    pub arrival_goal_bonus: f64,
    pub layoff_window: f64,
    pub candidate_progress: f64,
    pub candidate_width: f64,
    pub support_angle_dist: f64,
    pub dist_to_ball: f64,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn generate_off_ball_attack_anchor_candidates(
    input: &OffBallRawGenerationInput<'_>,
) -> Vec<OffBallAttackCandidateInput> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let role_progress = if input.attacking_right {
        input.anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.anchor.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let search_radius = 10.0 + 16.0 * role_progress;

    let mut raw_candidates = Vec::new();
    raw_candidates.push(OffBallAttackCandidateInput {
        pos: input.anchor,
        anchor_pos: input.anchor,
    });
    let anchor_progress = (input.anchor.0 - input.ball_pos.0) * forward_dir;
    if anchor_progress > 0.0 {
        raw_candidates.push(OffBallAttackCandidateInput {
            pos: (
                input.anchor.0 + forward_dir * 10.0_f64.min(anchor_progress * 0.45),
                input.anchor.1,
            ),
            anchor_pos: input.anchor,
        });
    }
    for sample in input.anchor_samples {
        let angle = sample.angle_unit * std::f64::consts::TAU;
        let radius = sample.radius_unit.powf(0.65) * search_radius;
        raw_candidates.push(OffBallAttackCandidateInput {
            pos: (
                input.anchor.0 + angle.cos() * radius,
                input.anchor.1 + angle.sin() * radius,
            ),
            anchor_pos: input.anchor,
        });
    }

    raw_candidates
}

pub fn generate_off_ball_attack_support_candidates(
    input: &OffBallRawGenerationInput<'_>,
) -> Vec<OffBallAttackCandidateInput> {
    if !input.has_ball_carrier {
        return Vec::new();
    }

    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let role_progress = if input.attacking_right {
        input.anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.anchor.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let width_signed = (input.anchor.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0);
    let width_factor = width_signed.abs().min(1.0);
    let mut raw_candidates = Vec::new();
    let support_pull = smoothstep(0.38, 0.64, role_progress);
    let support_depth = (role_progress - 0.46) * 34.0;
    let ball_support_x = input.ball_pos.0 + forward_dir * support_depth;
    let ball_support_y =
        input.ball_pos.1 * (1.0 - 0.30 * width_factor) + input.anchor.1 * (0.30 * width_factor);
    let support_center = (
        input.anchor.0 * (1.0 - support_pull) + ball_support_x * support_pull,
        input.anchor.1 * (1.0 - support_pull) + ball_support_y * support_pull,
    );
    for sample in input.support_samples {
        let angle = sample.angle_unit * std::f64::consts::TAU;
        let radius = sample.radius_unit.powf(0.7) * (7.0 + 15.0 * role_progress);
        raw_candidates.push(OffBallAttackCandidateInput {
            pos: (
                support_center.0 + angle.cos() * radius,
                support_center.1 + angle.sin() * radius,
            ),
            anchor_pos: (
                input.anchor.0 * 0.35 + support_center.0 * 0.65,
                input.anchor.1 * 0.50 + support_center.1 * 0.50,
            ),
        });
    }

    let ball_progress = if input.attacking_right {
        input.ball_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.ball_pos.0) / input.pitch_length
    };
    if ball_progress > 0.68 && !input.is_defender {
        let side_sign = if input.anchor.1 >= input.pitch_width / 2.0 {
            1.0
        } else {
            -1.0
        };
        let weak_side = (-width_signed
            * ((input.ball_pos.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0)))
            .clamp(0.0, 1.0);
        let support_centers = [
            (
                support_center.0 * 0.55 + input.ball_pos.0 * 0.45,
                support_center.1 * 0.55 + input.ball_pos.1 * 0.45,
            ),
            (
                input.anchor.0 * 0.35 + input.ball_pos.0 * 0.65,
                input.anchor.1 * 0.45 + input.ball_pos.1 * 0.55,
            ),
        ];
        let angle_bias = (input.pitch_width / 2.0 - input.ball_pos.1).atan2(10.0);
        let support_angles = [
            angle_bias - 1.65,
            angle_bias - 0.95,
            angle_bias - 0.35,
            angle_bias,
            angle_bias + 0.35,
            angle_bias + 0.95,
            angle_bias + 1.65,
        ];
        let support_radii = [
            6.0,
            10.0 + 3.0 * smoothstep(0.72, 0.88, ball_progress),
            15.0 + 5.0 * smoothstep(0.70, 0.90, ball_progress),
        ];
        for center in support_centers {
            for radius in support_radii {
                for angle in support_angles {
                    let sx = center.0 - forward_dir * angle.cos() * radius;
                    let sy = center.1 + angle.sin() * radius;
                    raw_candidates.push(OffBallAttackCandidateInput {
                        pos: (sx, sy),
                        anchor_pos: (sx, sy),
                    });
                }
            }
        }
        if width_factor > 0.38 && role_progress > 0.58 {
            let arrival_t = ((ball_progress - 0.68) / 0.20).clamp(0.0, 1.0);
            let arrival_depth = 6.0 + 7.0 * arrival_t;
            let center_lane = input.pitch_width / 2.0;
            let half_space =
                center_lane + side_sign * input.pitch_width * (0.06 + 0.06 * (1.0 - weak_side));
            let central_arrival_x = input.ball_pos.0 - forward_dir * arrival_depth;
            for sy in [half_space, center_lane] {
                raw_candidates.push(OffBallAttackCandidateInput {
                    pos: (central_arrival_x, sy),
                    anchor_pos: (central_arrival_x, sy),
                });
            }
            if weak_side > 0.18 {
                let far_post_x = input.ball_pos.0 + forward_dir * (2.0 + 4.0 * arrival_t);
                let far_post_y = center_lane + side_sign * input.pitch_width * 0.08;
                raw_candidates.push(OffBallAttackCandidateInput {
                    pos: (far_post_x, far_post_y),
                    anchor_pos: (far_post_x, far_post_y),
                });
            }
        }
    }

    raw_candidates
}

pub fn generate_off_ball_attack_raw_candidates(
    input: &OffBallRawGenerationInput<'_>,
) -> Vec<OffBallAttackCandidateInput> {
    let mut raw_candidates = generate_off_ball_attack_anchor_candidates(input);
    raw_candidates.extend(generate_off_ball_attack_support_candidates(input));
    raw_candidates
}

pub fn score_off_ball_attack_candidates(
    input: &OffBallAttackBatchInput<'_>,
) -> Vec<OffBallAttackCandidateOutput> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let role_progress = if input.attacking_right {
        input.anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.anchor.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let width_signed = (input.anchor.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0);
    let width_factor = width_signed.abs().min(1.0);
    let max_speed = player_speed(
        input.player_speed,
        input.player_max_speed,
        input.player_min_speed,
    );

    let mut outputs = Vec::new();
    for candidate in input.candidates {
        let pos = pitch_clamp(candidate.pos, input.pitch_length, input.pitch_width);
        let anchor_pos = candidate.anchor_pos;
        let pv = position_value(&PositionValueInput {
            x: pos.0,
            y: pos.1,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            opponent_positions: input.opponent_positions,
            teammate_positions: input.teammate_positions,
            runner_formation_pos: Some(anchor_pos),
        });

        let move_dist = distance(pos, input.player_pos);
        let candidate_progress = if input.attacking_right {
            pos.0 / input.pitch_length
        } else {
            (input.pitch_length - pos.0) / input.pitch_length
        };
        let carrier_progress_hint = if input.attacking_right {
            input.ball_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - input.ball_pos.0) / input.pitch_length
        };
        let final_third_support_window = ((carrier_progress_hint - 0.68) / 0.22).clamp(0.0, 1.0)
            * ((candidate_progress - 0.66) / 0.18).clamp(0.0, 1.0);
        let movement_window =
            max_speed * (4.0 + 3.0 * role_progress + 4.6 * final_third_support_window);
        let movement_reach = 1.0 / (1.0 + (move_dist / movement_window.max(1.0)).powf(1.45));
        let immediate_reach = receive_reachability(
            pos,
            input.player_pos,
            max_speed,
            input.opponent_positions,
            input.opponent_speeds,
            input.ball_pos,
            input.pass_to_space_ball_speed,
            input.receive_reachability_scale,
        );
        let reach = 0.35 + 0.45 * movement_reach + 0.20 * immediate_reach;

        let mut pass_feasibility = 1.0;
        let dx = pos.0 - input.ball_pos.0;
        let dy = pos.1 - input.ball_pos.1;
        let path_len = (dx * dx + dy * dy).sqrt();
        if path_len > 1.0 {
            let nx = dx / path_len;
            let ny = dy / path_len;
            for opp in input.opponent_positions {
                let px = opp.0 - input.ball_pos.0;
                let py = opp.1 - input.ball_pos.1;
                let proj = px * nx + py * ny;
                if proj > 2.0 && proj < path_len - 2.0 {
                    let perp = (px * ny - py * nx).abs();
                    if perp < 4.0 {
                        pass_feasibility *= 0.5;
                    }
                }
            }
        }
        let dist_to_ball = distance(pos, input.ball_pos);
        if dist_to_ball > 25.0 {
            pass_feasibility *= (1.0 - (dist_to_ball - 25.0) / 35.0).max(0.1);
        }

        let space_bonus =
            space_creation_value(pos, input.opponent_positions, input.space_creation_radius);
        let role_dist = distance(pos, input.anchor);
        let role_limit = 14.0 + 22.0 * role_progress;
        let role_t = (role_dist / (role_limit * 1.8).max(1.0)).min(1.0);
        let mut role_shape_factor = 0.22 + 0.78 * (1.0 - role_t * role_t * (3.0 - 2.0 * role_t));
        let mut inside_support = 0.0;
        if width_factor > 0.35 {
            let anchor_width = (input.anchor.1 - input.pitch_width / 2.0).abs();
            let pos_width = (pos.1 - input.pitch_width / 2.0).abs();
            inside_support = ((carrier_progress_hint - 0.68) / 0.22).clamp(0.0, 1.0)
                * ((candidate_progress - 0.66) / 0.18).clamp(0.0, 1.0)
                * ((anchor_width - pos_width).max(0.0) / anchor_width.max(1.0)).min(1.0);
            role_shape_factor = role_shape_factor.max(0.48 + 0.28 * inside_support);
        }

        let ahead_of_ball = (pos.0 - input.ball_pos.0) * forward_dir;
        let ahead_t = (ahead_of_ball / 18.0).clamp(0.0, 1.0);
        let support_run_factor = ahead_t * ahead_t * (3.0 - 2.0 * ahead_t);
        let carrier_progress = if input.attacking_right {
            input.ball_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - input.ball_pos.0) / input.pitch_length
        };
        let support_angle_dist = distance(pos, input.ball_pos);
        let support_angle_value = ((carrier_progress - 0.68) / 0.22).clamp(0.0, 1.0)
            * (1.0
                - ((pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0)
                    * 0.35)
            * (1.0 - (support_angle_dist - 16.0).abs() / 18.0).max(0.0);
        let cutback_depth = (input.ball_pos.0 - pos.0) * forward_dir;
        let carrier_width =
            (input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
        let candidate_width = (pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
        let second_line_support = ((carrier_progress - 0.66) / 0.20).clamp(0.0, 1.0)
            * ((candidate_progress - 0.60) / 0.14).clamp(0.0, 1.0)
            * (1.0 - ((candidate_progress - 0.82) / 0.10).clamp(0.0, 1.0))
            * ((cutback_depth - 5.0) / 8.0).clamp(0.0, 1.0)
            * (1.0 - ((cutback_depth - 24.0) / 12.0).clamp(0.0, 1.0))
            * ((carrier_width - candidate_width + 0.04) / 0.34).clamp(0.0, 1.0)
            * (1.0 - candidate_width * 0.35);
        let layoff_window = ((carrier_progress - 0.70) / 0.18).clamp(0.0, 1.0)
            * (1.0 - (support_angle_dist - 14.0).abs() / 10.0).max(0.0)
            * (0.65
                + 0.35
                    * (1.0
                        - ((pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                            .min(1.0)));
        if second_line_support > 0.0 {
            role_shape_factor = role_shape_factor.max(0.58 + 0.24 * second_line_support);
        }

        let mut arrival_goal_fit = 0.0;
        let mut arrival_goal_multiplier = 1.0;
        let mut arrival_goal_bonus = 0.0;
        if let Some(goal) = input.current_goal {
            if goal.goal_type == "arc_arrival_for_cutback" || goal.goal_type == "attack_far_post" {
                let radius = if goal.goal_type == "arc_arrival_for_cutback" {
                    11.0
                } else {
                    15.0
                };
                arrival_goal_fit = (1.0 - distance(pos, goal.target_pos) / radius).max(0.0);
                if arrival_goal_fit > 0.0 {
                    let arrival_strength = (goal.value * 2.5).clamp(0.0, 1.0);
                    arrival_goal_multiplier += arrival_goal_fit
                        * arrival_strength
                        * if goal.goal_type == "attack_far_post" {
                            5.0
                        } else {
                            1.25
                        };
                    arrival_goal_bonus = arrival_goal_fit
                        * goal.value.max(0.0)
                        * if goal.goal_type == "attack_far_post" {
                            2.25
                        } else {
                            0.55
                        };
                }
            }
        }

        let mut role_overlap = 0.0;
        for teammate in input.teammates {
            if teammate.index == input.player_index || teammate.is_goalkeeper {
                continue;
            }
            let anchor_dist = distance(pos, teammate.tactical_anchor);
            let own_anchor_dist = distance(pos, input.anchor);
            if anchor_dist < 12.0 && anchor_dist + 2.0 < own_anchor_dist {
                role_overlap += (1.0 - anchor_dist / 12.0).powf(1.15);
            }
            let current_dist = distance(pos, teammate.pos);
            if current_dist < 8.0 {
                role_overlap += 0.45 * (1.0 - current_dist / 8.0);
            }
        }
        let role_overlap_factor = 1.0 / (1.0 + role_overlap * 0.72);
        let target_width_signed = (pos.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0);
        let cross_lane = (-width_signed * target_width_signed).max(0.0);
        let lane_factor = (1.0 - 0.88 * width_factor * cross_lane).max(0.12);
        let mut offside_penalty = 1.0;
        if is_offside_position(
            pos,
            input.attacking_right,
            input.offside_line,
            input.pitch_length,
            Some(input.ball_pos.0),
        ) {
            offside_penalty = 0.08;
        } else if input.attacking_right && pos.0 > input.offside_line - 3.0 {
            offside_penalty *= 0.45;
        } else if !input.attacking_right && pos.0 < input.offside_line + 3.0 {
            offside_penalty *= 0.45;
        }

        let score = (pv
            * reach
            * pass_feasibility
            * space_bonus
            * offside_penalty
            * role_shape_factor
            * lane_factor
            * role_overlap_factor
            * arrival_goal_multiplier
            * (1.0
                + 0.18 * role_progress * support_run_factor
                + 0.82 * support_angle_value
                + 1.35 * layoff_window
                + 0.70 * inside_support
                + 1.45 * second_line_support))
            + arrival_goal_bonus;
        outputs.push(OffBallAttackCandidateOutput {
            score,
            target: pos,
            pv,
            reach,
            movement_reach,
            immediate_reach,
            pass_feasibility,
            space_bonus,
            role_shape_factor,
            role_overlap_factor,
            role_overlap,
            lane_factor,
            offside_penalty,
            support_angle_value,
            inside_support,
            second_line_support,
            arrival_goal_fit,
            arrival_goal_multiplier,
            arrival_goal_bonus,
            layoff_window,
            candidate_progress,
            candidate_width,
            support_angle_dist,
            dist_to_ball,
        });
    }
    outputs
}

pub fn choose_off_ball_attack_target(
    input: &OffBallAttackChoiceInput<'_>,
) -> Option<OffBallAttackChoiceOutput> {
    let scored = score_off_ball_attack_candidates(&OffBallAttackBatchInput {
        player_index: input.player_index,
        player_pos: input.player_pos,
        player_speed: input.player_speed,
        anchor: input.anchor,
        ball_pos: input.ball_pos,
        attacking_right: input.attacking_right,
        offside_line: input.offside_line,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        pass_to_space_ball_speed: input.pass_to_space_ball_speed,
        receive_reachability_scale: input.receive_reachability_scale,
        space_creation_radius: input.space_creation_radius,
        candidates: input.candidates,
        opponent_positions: input.opponent_positions,
        opponent_speeds: input.opponent_speeds,
        teammate_positions: input.teammate_positions,
        teammates: input.teammates,
        current_goal: input.current_goal,
    });
    let candidate_count = scored.len() + 1;
    let mut scores = Vec::with_capacity(candidate_count);
    scores.push(input.stay_score * (1.0 + input.score_noises.first().copied().unwrap_or(0.0)));
    for (idx, value) in scored.iter().enumerate() {
        scores.push(value.score * (1.0 + input.score_noises.get(idx + 1).copied().unwrap_or(0.0)));
    }
    let max_score = scores.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if max_score < 0.01 {
        return Some(OffBallAttackChoiceOutput {
            target: input.anchor,
            score: max_score,
            max_score,
            candidate_count,
            used_roll: false,
            components: OffBallAttackChoiceComponents {
                kind: 2,
                pv: 0.0,
                reach: 0.0,
                movement_reach: 0.0,
                immediate_reach: 0.0,
                pass_feasibility: 0.0,
                space_bonus: 0.0,
                role_shape_factor: 0.0,
                role_overlap_factor: 0.0,
                role_overlap: 0.0,
                lane_factor: 0.0,
                offside_penalty: 0.0,
                support_angle_value: 0.0,
                inside_support: 0.0,
                second_line_support: 0.0,
                arrival_goal_fit: 0.0,
                arrival_goal_multiplier: 0.0,
                arrival_goal_bonus: 0.0,
                layoff_window: 0.0,
                candidate_progress: 0.0,
                candidate_width: 0.0,
                support_angle_dist: 0.0,
                dist_to_ball: 0.0,
            },
        });
    }
    let min_score = scores.iter().copied().fold(f64::INFINITY, f64::min);
    let score_spread = (max_score - min_score).max(0.0);
    let temperature = ((0.004 + score_spread * 0.22)
        * iq_temperature_factor(input.iq, 0.35, 0.95, 0.28))
    .clamp(0.003, 0.05);
    let selection = softmax_select_index_with_temperature(&scores, temperature, input.roll, 0)?;
    let used_roll = candidate_count > 1 && selection.total_weight >= 1e-10;
    let index = selection.index.min(candidate_count - 1);
    if index == 0 {
        return Some(OffBallAttackChoiceOutput {
            target: input.player_pos,
            score: scores[0],
            max_score,
            candidate_count,
            used_roll,
            components: OffBallAttackChoiceComponents {
                kind: 0,
                pv: 0.0,
                reach: 0.0,
                movement_reach: 0.0,
                immediate_reach: 0.0,
                pass_feasibility: 0.0,
                space_bonus: 0.0,
                role_shape_factor: 0.0,
                role_overlap_factor: 0.0,
                role_overlap: 0.0,
                lane_factor: 0.0,
                offside_penalty: 0.0,
                support_angle_value: 0.0,
                inside_support: 0.0,
                second_line_support: 0.0,
                arrival_goal_fit: 0.0,
                arrival_goal_multiplier: 0.0,
                arrival_goal_bonus: 0.0,
                layoff_window: 0.0,
                candidate_progress: 0.0,
                candidate_width: 0.0,
                support_angle_dist: 0.0,
                dist_to_ball: 0.0,
            },
        });
    }
    let value = scored[index - 1];
    Some(OffBallAttackChoiceOutput {
        target: value.target,
        score: scores[index],
        max_score,
        candidate_count,
        used_roll,
        components: OffBallAttackChoiceComponents {
            kind: 1,
            pv: value.pv,
            reach: value.reach,
            movement_reach: value.movement_reach,
            immediate_reach: value.immediate_reach,
            pass_feasibility: value.pass_feasibility,
            space_bonus: value.space_bonus,
            role_shape_factor: value.role_shape_factor,
            role_overlap_factor: value.role_overlap_factor,
            role_overlap: value.role_overlap,
            lane_factor: value.lane_factor,
            offside_penalty: value.offside_penalty,
            support_angle_value: value.support_angle_value,
            inside_support: value.inside_support,
            second_line_support: value.second_line_support,
            arrival_goal_fit: value.arrival_goal_fit,
            arrival_goal_multiplier: value.arrival_goal_multiplier,
            arrival_goal_bonus: value.arrival_goal_bonus,
            layoff_window: value.layoff_window,
            candidate_progress: value.candidate_progress,
            candidate_width: value.candidate_width,
            support_angle_dist: value.support_angle_dist,
            dist_to_ball: value.dist_to_ball,
        },
    })
}
