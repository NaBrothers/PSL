use crate::decision::softmax_select_index;
use crate::match_flow::{
    score_block_lane_zone, score_mark_runner_zone, DefenseZoneAttackerInput, DefenseZoneHelperInput,
};
use crate::physics::{distance, smoothstep};
use crate::position_value::{defensive_position_value, DefensivePositionValueInput};

#[derive(Clone, Copy, Debug)]
pub struct DefenseTeammateInput {
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
}

#[derive(Debug)]
pub struct DefenseScoreInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub base_ref: (f64, f64),
    pub ball_pos: (f64, f64),
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub ball_carrier_consecutive_carries: i32,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub press_radius: f64,
    pub tackle_range: f64,
    pub carrier_speed: f64,
    pub candidates: &'a [(f64, f64)],
    pub attackers: &'a [(f64, f64)],
    pub local_attackers: &'a [(f64, f64)],
    pub dangerous_receivers: &'a [(f64, f64)],
    pub teammates: &'a [DefenseTeammateInput],
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseScoreOutput {
    pub score: f64,
    pub target: (f64, f64),
    pub base_score: f64,
    pub press_value: f64,
    pub pressure_responsibility: f64,
    pub carrier_threat: f64,
    pub shot_lane_closure: f64,
    pub best_mark_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseRandomSample {
    pub angle_unit: f64,
    pub radius_unit: f64,
}

#[derive(Debug)]
pub struct DefenseRawInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub carrier_speed: f64,
    pub carrier_stale_threat: f64,
    pub field_press_context: f64,
    pub shot_danger: f64,
    pub local_attackers: &'a [(f64, f64)],
    pub dangerous_receivers: &'a [(f64, f64)],
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub shot_lane_threat: f64,
    pub random_samples: &'a [DefenseRandomSample],
}

#[derive(Debug)]
pub struct DefenseChoiceInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub base_ref: (f64, f64),
    pub ball_pos: (f64, f64),
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub ball_carrier_consecutive_carries: i32,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub press_radius: f64,
    pub tackle_range: f64,
    pub carrier_speed: f64,
    pub iq: f64,
    pub attackers: &'a [(f64, f64)],
    pub teammates: &'a [DefenseTeammateInput],
    pub random_samples: &'a [DefenseRandomSample],
    pub score_noises: &'a [f64],
    pub roll_by_count: &'a [f64],
    pub fallback_index_by_count: &'a [usize],
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseGoalCandidate {
    pub action_type: &'static str,
    pub target: (f64, f64),
    pub value: f64,
}

#[derive(Clone, Debug)]
pub struct DefenseChoiceOutput {
    pub action_type: &'static str,
    pub target: (f64, f64),
    pub score: f64,
    pub candidate_count: usize,
    pub local_attackers_count: usize,
    pub dangerous_receivers_count: usize,
    pub raw_targets: Vec<(f64, f64)>,
    pub candidate_targets: Vec<(f64, f64)>,
    pub candidate_scores: Vec<f64>,
    pub goal_candidates: Vec<DefenseGoalCandidate>,
    pub used_roll: bool,
    pub used_random_choice: bool,
    pub pressure_responsibility: f64,
    pub shot_danger: f64,
    pub carrier_stale_threat: f64,
    pub base_score: f64,
    pub press_value: f64,
    pub carrier_threat: f64,
    pub shot_lane_closure: f64,
    pub best_mark_value: f64,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

fn shot_lane_closure(
    point: (f64, f64),
    ball_pos: (f64, f64),
    own_goal_x: f64,
    pitch_width: f64,
) -> f64 {
    let goal_y = pitch_width / 2.0;
    let shot_dx = own_goal_x - ball_pos.0;
    let shot_dy = goal_y - ball_pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    if shot_len <= 1.0 {
        return 0.0;
    }
    let nx = shot_dx / shot_len;
    let ny = shot_dy / shot_len;
    let relx = point.0 - ball_pos.0;
    let rely = point.1 - ball_pos.1;
    let proj = relx * nx + rely * ny;
    if proj <= 0.5 || proj >= shot_len - 0.5 {
        return 0.0;
    }
    let perp = (relx * ny - rely * nx).abs();
    let lane = 1.0 - smoothstep(1.8, 7.5, perp);
    let depth = 1.0 - ((proj / shot_len) - 0.40).abs().min(0.52) / 0.52;
    lane.max(0.0) * (0.42 + 0.58 * depth.max(0.0))
}

pub fn generate_defense_raw_candidates(input: &DefenseRawInput<'_>) -> Vec<(f64, f64)> {
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let goal_y = input.pitch_width / 2.0;
    let shot_dx = own_goal_x - input.ball_pos.0;
    let shot_dy = goal_y - input.ball_pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    let mut sampled_points = vec![
        input.anchor,
        pitch_clamp(
            (
                input.anchor.0 * 0.85 + input.ball_pos.0 * 0.15,
                input.anchor.1 * 0.72 + input.ball_pos.1 * 0.28,
            ),
            input.pitch_length,
            input.pitch_width,
        ),
    ];

    if !input.local_attackers.is_empty() {
        let attackers: Vec<DefenseZoneAttackerInput> = input
            .local_attackers
            .iter()
            .map(|pos| DefenseZoneAttackerInput { pos: *pos })
            .collect();
        let zone_input = DefenseZoneHelperInput {
            defender_pos: input.defender_pos,
            tactical_anchor: input.anchor,
            ball_pos: input.ball_pos,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attackers: &attackers,
        };
        sampled_points.push(score_mark_runner_zone(&zone_input).target);
        sampled_points.push(score_block_lane_zone(&zone_input).target);
    }

    let goal_side = if input.attacking_right { -1.0 } else { 1.0 };
    for receiver in input.dangerous_receivers {
        let receiver_progress = if !input.attacking_right {
            receiver.0 / input.pitch_length.max(1.0)
        } else {
            (input.pitch_length - receiver.0) / input.pitch_length.max(1.0)
        };
        let receiver_centrality = 1.0
            - ((receiver.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
        let receiver_ball_dist = distance(*receiver, input.ball_pos);
        let receive_threat = smoothstep(0.58, 0.90, receiver_progress)
            * (0.42 + 0.58 * receiver_centrality)
            * (1.0 - smoothstep(28.0, 46.0, receiver_ball_dist));
        if receive_threat <= 0.02 {
            continue;
        }
        let mark_gap = 2.4 + 1.2 * receive_threat;
        let lateral_gap = (input.defender_pos.1 - receiver.1).clamp(-2.8, 2.8) * 0.22;
        sampled_points.push(pitch_clamp(
            (receiver.0 + goal_side * mark_gap, receiver.1 + lateral_gap),
            input.pitch_length,
            input.pitch_width,
        ));
    }

    if input.ball_carrier_pos.is_some() {
        let lead = input.carrier_speed * 0.45;
        sampled_points.push(pitch_clamp(
            (input.ball_pos.0 + goal_side * lead, input.ball_pos.1),
            input.pitch_length,
            input.pitch_width,
        ));
        let contain_depth = 2.2 + 1.6 * input.carrier_stale_threat;
        let contain_width = 3.0 + 2.0 * input.carrier_stale_threat;
        for oy in [-contain_width, 0.0, contain_width] {
            sampled_points.push(pitch_clamp(
                (
                    input.ball_pos.0 + goal_side * contain_depth,
                    input.ball_pos.1 + oy,
                ),
                input.pitch_length,
                input.pitch_width,
            ));
        }
        let lateral_sign = if input.defender_pos.1 < input.ball_pos.1 {
            -1.0
        } else {
            1.0
        };
        let angle_width = 5.5 + 3.0 * input.field_press_context;
        let angle_depth = 3.2 + 1.4 * input.field_press_context.max(input.shot_danger);
        sampled_points.push(pitch_clamp(
            (
                input.ball_pos.0 + goal_side * angle_depth,
                input.ball_pos.1 + lateral_sign * angle_width,
            ),
            input.pitch_length,
            input.pitch_width,
        ));
        if shot_len > 1.0 && input.shot_lane_threat > 0.05 {
            let nx = shot_dx / shot_len;
            let ny = shot_dy / shot_len;
            for lane_fraction in [0.30, 0.46] {
                let lane_depth = (shot_len * lane_fraction).clamp(2.5, 10.5);
                let lane_x = input.ball_pos.0 + nx * lane_depth;
                let lane_y = input.ball_pos.1 + ny * lane_depth;
                let side_offset = (input.defender_pos.1 - lane_y).clamp(-3.2, 3.2) * 0.45;
                sampled_points.push(pitch_clamp(
                    (lane_x, lane_y + side_offset),
                    input.pitch_length,
                    input.pitch_width,
                ));
            }
        }
    }

    for sample in input.random_samples {
        let angle = sample.angle_unit * std::f64::consts::TAU;
        let radius = sample.radius_unit.powf(0.7) * (8.0 + input.shot_danger * 4.0);
        sampled_points.push(pitch_clamp(
            (
                input.anchor.0 + angle.cos() * radius,
                input.anchor.1 + angle.sin() * radius,
            ),
            input.pitch_length,
            input.pitch_width,
        ));
    }
    sampled_points
}

pub fn score_defense_candidates(input: &DefenseScoreInput<'_>) -> Vec<DefenseScoreOutput> {
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let own_goal = (own_goal_x, input.pitch_width / 2.0);
    let dist_to_ball = distance(input.defender_pos, input.ball_pos);
    let ball_goal_dist = distance(input.ball_pos, own_goal);
    let central_threat = 1.0
        - ((input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let shot_danger = (1.0 - ball_goal_dist / 32.0).max(0.0) * (0.55 + 0.45 * central_threat);
    let mut carrier_progress = 0.0;
    let mut carrier_stale_threat = 0.0;
    if input.ball_carrier_pos.is_some() {
        carrier_progress = if !input.attacking_right {
            input.ball_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - input.ball_pos.0) / input.pitch_length
        };
        carrier_stale_threat = ((input.ball_carrier_consecutive_carries - 1) as f64 / 3.0)
            .clamp(0.0, 1.0)
            * ((carrier_progress - 0.62) / 0.24).clamp(0.0, 1.0)
            * (0.55 + 0.45 * central_threat);
    }

    let role_progress = if input.attacking_right {
        input.base_ref.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.base_ref.0) / input.pitch_length.max(1.0)
    };
    let advanced_pressure_role = smoothstep(0.36, 0.82, role_progress);
    let midfield_pressure_role = smoothstep(0.30, 0.56, role_progress)
        * (1.0 - smoothstep(0.74, 0.92, role_progress))
        * 0.72;
    let pressure_role = 0.12_f64
        .max(advanced_pressure_role)
        .max(midfield_pressure_role);
    let field_press_context = smoothstep(0.16, 0.50, carrier_progress)
        * (1.0 - smoothstep(0.82, 0.96, carrier_progress))
        * (0.58 + 0.42 * central_threat)
        * pressure_role;

    let defenders_closer_to_ball = input
        .teammates
        .iter()
        .filter(|tm| distance(tm.pos, input.ball_pos) < dist_to_ball - 1.0)
        .count();
    let close_defenders_near_ball = input
        .teammates
        .iter()
        .filter(|tm| {
            distance(tm.pos, input.ball_pos) < (input.press_radius * 0.72).max(input.tackle_range)
        })
        .count();
    let nearest_def_dist = input
        .teammates
        .iter()
        .map(|tm| distance(tm.pos, input.ball_pos))
        .fold(dist_to_ball, f64::min);
    let current_lane_closure = shot_lane_closure(
        input.defender_pos,
        input.ball_pos,
        own_goal_x,
        input.pitch_width,
    );
    let shot_lane_threat =
        (1.0 - smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * central_threat);
    let attacker_positions = input.attackers;
    let teammate_positions: Vec<(f64, f64)> = input.teammates.iter().map(|tm| tm.pos).collect();

    input
        .candidates
        .iter()
        .map(|point| {
            let base_score = defensive_position_value(&DefensivePositionValueInput {
                pos: *point,
                ball_pos: input.ball_pos,
                own_goal_x,
                pitch_length: input.pitch_length,
                pitch_width: input.pitch_width,
                attackers: attacker_positions,
                teammates: &teammate_positions,
                formation_pos: input.anchor,
            });
            let dist_point_ball = distance(*point, input.ball_pos);
            let press_value = (1.0 - dist_point_ball / input.press_radius.max(0.1)).max(0.0);
            let cover_cost = (defenders_closer_to_ball as f64 * 0.16
                + input.local_attackers.len() as f64 * 0.08)
                .min(0.75);
            let nearest_gap = (dist_to_ball - nearest_def_dist).max(0.0);
            let first_presser_share = 1.0 / (1.0 + (defenders_closer_to_ball as f64).powf(1.55));
            let swarm_cost = 1.0 / (1.0 + close_defenders_near_ball as f64 * 0.72);
            let mut distance_responsibility = (1.0 - nearest_gap / 10.0).max(0.08);
            let pressure_responsibility =
                first_presser_share * swarm_cost * distance_responsibility;
            distance_responsibility =
                (1.0 - (dist_to_ball - nearest_def_dist).max(0.0) / 18.0).max(0.25);
            let carrier_threat = 0.35
                + 0.65
                    * shot_danger
                        .max(carrier_stale_threat)
                        .max(field_press_context * 0.86);
            let press_reward =
                press_value * pressure_responsibility * distance_responsibility * carrier_threat;
            let mut score = base_score * (1.0 + press_reward * 2.45) * (1.0 - cover_cost * 0.28);
            let mut lane_closure = 0.0;
            if shot_lane_threat > 0.0 {
                lane_closure =
                    shot_lane_closure(*point, input.ball_pos, own_goal_x, input.pitch_width);
                let lane_improvement = (lane_closure - current_lane_closure).max(0.0);
                score *= 1.0 + shot_lane_threat * (lane_closure * 0.26 + lane_improvement * 0.74);
                if lane_closure > 0.12 {
                    let mut lane_redundancy = 0.0;
                    for teammate in input.teammates {
                        for teammate_point in [teammate.pos, teammate.target_pos] {
                            let td = distance(teammate_point, *point);
                            if td < 9.5 {
                                lane_redundancy += shot_lane_closure(
                                    teammate_point,
                                    input.ball_pos,
                                    own_goal_x,
                                    input.pitch_width,
                                ) * (1.0 - td / 9.5);
                            }
                        }
                    }
                    score *= 1.0 / (1.0 + lane_redundancy * 3.2);
                }
            }
            if press_value > 0.35 && pressure_responsibility < 0.22 {
                score *= 0.78 + pressure_responsibility;
            }

            let mut best_mark_value: f64 = 0.0;
            for receiver in input.dangerous_receivers {
                let receiver_progress = if !input.attacking_right {
                    receiver.0 / input.pitch_length.max(1.0)
                } else {
                    (input.pitch_length - receiver.0) / input.pitch_length.max(1.0)
                };
                let receiver_centrality = 1.0
                    - ((receiver.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                        .min(1.0);
                let receiver_ball_dist = distance(*receiver, input.ball_pos);
                let mark_dist = distance(*point, *receiver);
                let useful_distance = 1.0 - smoothstep(3.2, 10.5, mark_dist);
                let goal_side_progress =
                    (point.0 - receiver.0) * if !input.attacking_right { 1.0 } else { -1.0 };
                let goal_side_fit = smoothstep(0.0, 2.2, goal_side_progress)
                    * (1.0 - smoothstep(6.5, 12.0, goal_side_progress));
                let receive_threat = smoothstep(0.58, 0.90, receiver_progress)
                    * (0.42 + 0.58 * receiver_centrality)
                    * (1.0 - smoothstep(28.0, 46.0, receiver_ball_dist));
                best_mark_value = best_mark_value
                    .max(receive_threat * useful_distance * (0.48 + 0.52 * goal_side_fit));
            }
            if best_mark_value > 0.0 {
                score *= 1.0 + best_mark_value * 0.90;
            }

            if let Some(ball_carrier_pos) = input.ball_carrier_pos {
                if distance(*point, ball_carrier_pos) < input.tackle_range {
                    score *= 1.0 + carrier_threat * pressure_responsibility * 0.75;
                }
            }
            DefenseScoreOutput {
                score: score.max(0.0),
                target: *point,
                base_score,
                press_value,
                pressure_responsibility,
                carrier_threat,
                shot_lane_closure: lane_closure,
                best_mark_value,
            }
        })
        .collect()
}

fn python_round_1_key(value: f64) -> i64 {
    if !value.is_finite() {
        return (value * 10.0).round_ties_even() as i64;
    }

    let sign = if value.is_sign_negative() { -1 } else { 1 };
    let abs_value = value.abs();
    let lower = (abs_value * 10.0).floor() as i64;
    let midpoint = (lower as f64 + 0.5) / 10.0;
    let rounded = if abs_value < midpoint {
        lower
    } else if abs_value > midpoint {
        lower + 1
    } else if lower % 2 == 0 {
        lower
    } else {
        lower + 1
    };
    sign * rounded
}

fn defense_action_type(
    raw_target: (f64, f64),
    input: &DefenseChoiceInput<'_>,
    dist_to_ball: f64,
    shot_danger: f64,
    pressure_responsibility: f64,
    dangerous_receivers: &[(f64, f64)],
    local_attackers: &[(f64, f64)],
) -> &'static str {
    let Some(carrier_pos) = input.ball_carrier_pos else {
        if dangerous_receivers
            .iter()
            .any(|receiver| distance(raw_target, *receiver) < 5.4)
        {
            return "mark_runner";
        }
        if local_attackers
            .iter()
            .any(|attacker| distance(raw_target, *attacker) < 5.0)
        {
            return "mark_runner";
        }
        return if local_attackers.is_empty() {
            "hold_position"
        } else {
            "block_lane"
        };
    };

    if dist_to_ball < input.tackle_range * (0.55 + shot_danger * 0.15)
        && distance(raw_target, carrier_pos) < input.tackle_range * (0.75 + shot_danger * 0.15)
        && pressure_responsibility > 0.25
    {
        "tackle"
    } else if distance(raw_target, carrier_pos) < input.press_radius
        && (pressure_responsibility > 0.18 || shot_danger > 0.72)
    {
        "approach"
    } else if dangerous_receivers
        .iter()
        .any(|receiver| distance(raw_target, *receiver) < 5.4)
    {
        "mark_runner"
    } else if local_attackers
        .iter()
        .any(|attacker| distance(raw_target, *attacker) < 5.0)
    {
        "mark_runner"
    } else if local_attackers.is_empty() {
        "hold_position"
    } else {
        "block_lane"
    }
}

fn unique_points(points: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut seen: Vec<(i64, i64)> = Vec::new();
    let mut unique = Vec::new();
    for point in points {
        let key = (python_round_1_key(point.0), python_round_1_key(point.1));
        if seen.contains(&key) {
            continue;
        }
        seen.push(key);
        unique.push(*point);
    }
    unique
}

pub fn choose_defense_action(input: &DefenseChoiceInput<'_>) -> Option<DefenseChoiceOutput> {
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let own_goal = (own_goal_x, input.pitch_width / 2.0);
    let dist_to_ball = distance(input.defender_pos, input.ball_pos);
    let ball_goal_dist = distance(input.ball_pos, own_goal);
    let central_threat = 1.0
        - ((input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let shot_danger = (1.0 - ball_goal_dist / 32.0).max(0.0) * (0.55 + 0.45 * central_threat);

    let mut carrier_progress = 0.0;
    let mut carrier_stale_threat = 0.0;
    if input.ball_carrier_pos.is_some() {
        carrier_progress = if !input.attacking_right {
            input.ball_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - input.ball_pos.0) / input.pitch_length
        };
        carrier_stale_threat = ((input.ball_carrier_consecutive_carries - 1) as f64 / 3.0)
            .clamp(0.0, 1.0)
            * ((carrier_progress - 0.62) / 0.24).clamp(0.0, 1.0)
            * (0.55 + 0.45 * central_threat);
    }

    let role_progress = if input.attacking_right {
        input.base_ref.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.base_ref.0) / input.pitch_length.max(1.0)
    };
    let advanced_pressure_role = smoothstep(0.36, 0.82, role_progress);
    let midfield_pressure_role = smoothstep(0.30, 0.56, role_progress)
        * (1.0 - smoothstep(0.74, 0.92, role_progress))
        * 0.72;
    let pressure_role = 0.12_f64
        .max(advanced_pressure_role)
        .max(midfield_pressure_role);
    let field_press_context = smoothstep(0.16, 0.50, carrier_progress)
        * (1.0 - smoothstep(0.82, 0.96, carrier_progress))
        * (0.58 + 0.42 * central_threat)
        * pressure_role;

    let local_attackers: Vec<(f64, f64)> = input
        .attackers
        .iter()
        .copied()
        .filter(|attacker| {
            distance(*attacker, input.anchor) < 24.0
                || distance(*attacker, input.defender_pos) < 16.0
        })
        .collect();
    let dangerous_receivers: Vec<(f64, f64)> = input
        .attackers
        .iter()
        .copied()
        .filter(|attacker| {
            if let Some(carrier_pos) = input.ball_carrier_pos {
                if distance(*attacker, carrier_pos) < 1e-9 {
                    return false;
                }
            }
            distance(*attacker, input.ball_pos) < 34.0
                || distance(*attacker, input.anchor) < 28.0
                || distance(*attacker, input.defender_pos) < 18.0
        })
        .collect();
    let shot_lane_threat =
        (1.0 - smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * central_threat);
    let raw_points = generate_defense_raw_candidates(&DefenseRawInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        ball_pos: input.ball_pos,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        carrier_speed: input.carrier_speed,
        carrier_stale_threat,
        field_press_context,
        shot_danger,
        local_attackers: &local_attackers,
        dangerous_receivers: &dangerous_receivers,
        ball_carrier_pos: input.ball_carrier_pos,
        shot_lane_threat,
        random_samples: input.random_samples,
    });
    let candidates = unique_points(&raw_points);
    if candidates.is_empty() {
        return None;
    }

    let scored = score_defense_candidates(&DefenseScoreInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        base_ref: input.base_ref,
        ball_pos: input.ball_pos,
        ball_carrier_pos: input.ball_carrier_pos,
        ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        press_radius: input.press_radius,
        tackle_range: input.tackle_range,
        carrier_speed: input.carrier_speed,
        candidates: &candidates,
        attackers: input.attackers,
        local_attackers: &local_attackers,
        dangerous_receivers: &dangerous_receivers,
        teammates: input.teammates,
    });
    if scored.is_empty() {
        return None;
    }

    let noisy_scores: Vec<f64> = scored
        .iter()
        .enumerate()
        .map(|(idx, candidate)| {
            let noise = input.score_noises.get(idx).copied().unwrap_or(0.0);
            candidate.score * (1.0 + noise)
        })
        .collect();
    let count = noisy_scores.len();
    let max_score = noisy_scores
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let mut used_roll = false;
    let mut used_random_choice = false;
    let chosen_index = if count == 1 {
        0
    } else if max_score < 0.001 {
        used_random_choice = true;
        input
            .fallback_index_by_count
            .get(count)
            .copied()
            .unwrap_or(0)
            % count
    } else {
        let roll = input.roll_by_count.get(count).copied().unwrap_or(0.0);
        let selection = softmax_select_index(&noisy_scores, input.iq, roll, 0)?;
        used_roll = selection.total_weight >= 1e-10;
        selection.index.min(scored.len() - 1)
    };
    let chosen = scored[chosen_index];
    let raw_target = chosen.target;
    let chosen_score = noisy_scores[chosen_index];

    let defenders_closer_to_ball = input
        .teammates
        .iter()
        .filter(|tm| distance(tm.pos, input.ball_pos) < dist_to_ball - 1.0)
        .count();
    let close_defenders_near_ball = input
        .teammates
        .iter()
        .filter(|tm| {
            distance(tm.pos, input.ball_pos) < (input.press_radius * 0.72).max(input.tackle_range)
        })
        .count();
    let chosen_press_responsibility = 1.0
        / (1.0
            + (defenders_closer_to_ball as f64).powf(1.55)
            + close_defenders_near_ball as f64 * 0.72);

    let action_type = defense_action_type(
        raw_target,
        input,
        dist_to_ball,
        shot_danger,
        chosen_press_responsibility,
        &dangerous_receivers,
        &local_attackers,
    );
    let goal_candidates = scored
        .iter()
        .map(|candidate| DefenseGoalCandidate {
            action_type: defense_action_type(
                candidate.target,
                input,
                dist_to_ball,
                shot_danger,
                chosen_press_responsibility,
                &dangerous_receivers,
                &local_attackers,
            ),
            target: candidate.target,
            value: candidate.score,
        })
        .collect();

    Some(DefenseChoiceOutput {
        action_type,
        target: raw_target,
        score: chosen_score,
        candidate_count: count,
        local_attackers_count: local_attackers.len(),
        dangerous_receivers_count: dangerous_receivers.len(),
        raw_targets: raw_points,
        candidate_targets: candidates,
        candidate_scores: scored.iter().map(|candidate| candidate.score).collect(),
        goal_candidates,
        used_roll,
        used_random_choice,
        pressure_responsibility: chosen_press_responsibility,
        shot_danger,
        carrier_stale_threat,
        base_score: chosen.base_score,
        press_value: chosen.press_value,
        carrier_threat: chosen.carrier_threat,
        shot_lane_closure: chosen.shot_lane_closure,
        best_mark_value: chosen.best_mark_value,
    })
}
