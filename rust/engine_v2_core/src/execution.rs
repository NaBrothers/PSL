use crate::interactions::{
    carry_containment_transition, CarryContainmentInput, DefenderActionInput,
};
use crate::physics::{
    advance_player_motion, distance, player_speed, segment_pitch_boundary_crossing,
    PitchBoundaryCrossing, PlayerMotionInput,
};

#[derive(Clone, Copy, Debug)]
pub struct ExecutionOpponent {
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct CarryExecutionInput<'a> {
    pub transition: Option<crate::execution_transition::CarrySegmentTransition>,
    pub holder_pos: (f64, f64),
    pub target: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub dribbling: f64,
    pub consecutive_carries: i32,
    pub control_readiness: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub carrier_speed: f64,
    pub carry_error_divisor: f64,
    pub opponents: &'a [ExecutionOpponent],
    pub defender_responses: &'a [DefenderActionInput],
    pub error_roll: f64,
    pub containment_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct CarryExecutionOutput {
    pub transition: crate::execution_transition::CarrySegmentTransition,
    pub carry_speed: f64,
    pub carry_difficulty: f64,
    pub new_pos: (f64, f64),
    pub boundary_crossing: Option<PitchBoundaryCrossing>,
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
    pub contact_load: f64,
    pub error_chance: f64,
    pub is_error: bool,
    pub loose_pos: (f64, f64),
    pub constrained_control: bool,
    pub constrained_control_probability: f64,
    pub constrained_control_position: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct PassExecutionInput {
    pub transition: Option<crate::execution_transition::PassActionTransition>,
    pub passer_pos: (f64, f64),
    pub ideal_target: (f64, f64),
    pub passing: f64,
    pub is_long: bool,
    pub lane_risk: f64,
    pub retention_probability: f64,
    pub technical_probability: f64,
    pub technical_roll: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub ball_pass_speed: f64,
    pub ball_long_pass_speed: f64,
    pub tick_duration: f64,
    pub random_1: f64,
    pub random_2: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassExecutionOutput {
    pub transition: crate::execution_transition::PassActionTransition,
    pub target: (f64, f64),
    pub error_radius: f64,
    pub used_target_error: bool,
    pub randoms_used: usize,
    pub speed: f64,
    pub ticks_needed: i32,
    pub flight_type_code: u8,
    pub retention_probability: f64,
    pub technical_probability: f64,
    pub technical_roll: f64,
    pub delivery_miss: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotExecutionInput {
    pub shooter_pos: (f64, f64),
    pub on_target_prob: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub goal_width: f64,
    pub ball_shot_speed: f64,
    pub tick_duration: f64,
    pub random_1: f64,
    pub random_2: f64,
    pub random_3: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotExecutionOutput {
    pub on_target: bool,
    pub target: (f64, f64),
    pub speed: f64,
    pub distance: f64,
    pub ticks_needed: i32,
    pub randoms_used: usize,
    pub flight_type_code: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct ClearExecutionInput {
    pub clearer_pos: (f64, f64),
    pub target: (f64, f64),
    pub ball_long_pass_speed: f64,
    pub tick_duration: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ClearExecutionOutput {
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub speed: f64,
    pub ticks_needed: i32,
    pub flight_type_code: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct ClearTargetInput {
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub depth_roll: f64,
    pub lateral_roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ClearTargetOutput {
    pub target: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct HoldExecutionInput<'a> {
    pub transition: Option<crate::execution_transition::ControlActionTransition>,
    pub holder_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub dribbling: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub carry_error_divisor: f64,
    pub opponents: &'a [ExecutionOpponent],
    pub opportunity_target: Option<(f64, f64)>,
    pub error_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldExecutionOutput {
    pub transition: crate::execution_transition::ControlActionTransition,
    pub new_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
    pub pressure: f64,
    pub nearest_dist: f64,
    pub trace_pressure: f64,
    pub trace_nearest_dist: Option<f64>,
    pub error_chance: f64,
    pub is_error: bool,
    pub loose_pos: (f64, f64),
    pub randoms_used: usize,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn execute_carry(input: &CarryExecutionInput<'_>) -> CarryExecutionOutput {
    let base_speed = player_speed(
        input.speed_ability,
        input.player_max_speed,
        input.player_min_speed,
    );
    let dribbling_factor = input.dribbling / 100.0;
    let control_factor = 0.42 + 0.34 * dribbling_factor;

    let dx = input.target.0 - input.holder_pos.0;
    let dy = input.target.1 - input.holder_pos.1;
    let path_len = (dx * dx + dy * dy).sqrt().max(0.1);
    let nx = dx / path_len;
    let ny = dy / path_len;

    let mut path_pressure = 0.0;
    let mut close_pressure = 0.0;
    for opp in input.opponents {
        if opp.is_goalkeeper {
            continue;
        }
        let ox = opp.pos.0 - input.holder_pos.0;
        let oy = opp.pos.1 - input.holder_pos.1;
        let dist = (ox * ox + oy * oy).sqrt();
        if dist < 8.0 {
            close_pressure += 1.0 - dist / 8.0;
        }

        let proj = ox * nx + oy * ny;
        if -1.0 < proj && proj < path_len + 4.0 {
            let perp = (ox * ny - oy * nx).abs();
            if perp < 7.0 {
                path_pressure += (1.0 - perp / 7.0) * (1.0 - proj.max(0.0) / (path_len + 8.0));
            }
        }
    }

    let pressure = (path_pressure * 0.45 + close_pressure * 0.35).min(1.0);
    let space_factor = 1.0 - pressure;
    let urgency = (path_len / 12.0).min(1.0);
    let control_readiness = input.control_readiness.clamp(0.0, 1.0);
    let control_mobility = 0.38 + 0.62 * control_readiness;
    let personal_carry_cap = base_speed * (0.58 + 0.24 * dribbling_factor);
    let speed = (base_speed
        * control_factor
        * (0.70 + 0.45 * space_factor)
        * (0.75 + 0.25 * urgency)
        * control_mobility)
        .clamp(0.8, personal_carry_cap);
    let unsettled_control_difficulty =
        (1.0 - control_readiness).powf(1.35) * (0.72 + 0.58 * pressure);
    let difficulty = 1.0
        + pressure * 1.4
        + (speed - input.carrier_speed).max(0.0) * 0.18
        + unsettled_control_difficulty;

    let motion = advance_player_motion(&PlayerMotionInput {
        pos: input.holder_pos,
        target: input.target,
        velocity: input.velocity,
        speed_ability: input.speed_ability,
        desired_speed: speed,
        acceleration_scale: 0.46 + 0.54 * control_readiness,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    });
    let containment = carry_containment_transition(&CarryContainmentInput {
        holder_pos: input.holder_pos,
        carrier_end: motion.pos,
        defenders: input.defender_responses,
    });
    let unconstrained_control_pos = motion.unclamped_pos;
    let containment_transition =
        crate::execution_transition::BinaryExecutionTransition::from_success_probability(
            containment.constrained_control_probability,
        );
    let unconstrained_new_pos = pitch_clamp(
        unconstrained_control_pos,
        input.pitch_length,
        input.pitch_width,
    );
    let constrained_new_pos = pitch_clamp(
        containment.constrained_control_position,
        input.pitch_length,
        input.pitch_width,
    );
    let branch_motion = |new_pos: (f64, f64)| {
        let nominal_distance = motion.distance_covered.max(1e-9);
        let distance_covered = distance(input.holder_pos, new_pos);
        let progress_ratio = (distance_covered / nominal_distance).clamp(0.0, 1.0);
        (
            distance_covered,
            (
                motion.velocity.0 * progress_ratio,
                motion.velocity.1 * progress_ratio,
            ),
        )
    };
    let (_, unconstrained_velocity) = branch_motion(unconstrained_new_pos);
    let (_, constrained_velocity) = branch_motion(constrained_new_pos);
    let error_chance_at = |new_pos: (f64, f64)| {
        let progress = if input.attacking_right {
            new_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - new_pos.0) / input.pitch_length
        };
        let centrality = 1.0
            - ((new_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
        let final_third_control =
            ((progress - 0.72) / 0.18).clamp(0.0, 1.0) * centrality.clamp(0.0, 1.0);
        let stale_carry_difficulty =
            1.0 + (input.consecutive_carries - 1).max(0) as f64 * 0.24 * final_third_control;
        ((100.0 - input.dribbling) / input.carry_error_divisor)
            * difficulty
            * stale_carry_difficulty
    };
    let computed_transition = crate::execution_transition::CarrySegmentTransition::new(
        containment_transition,
        unconstrained_control_pos,
        unconstrained_new_pos,
        unconstrained_velocity,
        containment.constrained_control_position,
        constrained_new_pos,
        constrained_velocity,
        error_chance_at(unconstrained_new_pos),
        error_chance_at(constrained_new_pos),
    );
    let transition = input.transition.unwrap_or(computed_transition);
    let sample = transition.sample(input.error_roll, input.containment_roll);
    let boundary_crossing = segment_pitch_boundary_crossing(
        input.holder_pos,
        sample.end_pos,
        input.pitch_length,
        input.pitch_width,
    );
    let new_pos = sample.control_pos;
    let (distance_covered, _) = branch_motion(new_pos);
    let velocity = sample.velocity;
    let progress_ratio = (distance_covered / motion.distance_covered.max(1e-9)).clamp(0.0, 1.0);
    let error_chance = if sample.constrained_control {
        transition
            .constrained
            .technical_survival
            .failure_probability
    } else {
        transition
            .unconstrained
            .technical_survival
            .failure_probability
    };
    let is_error = sample.technical_error;
    let loose_pos = crate::execution_transition::RectangularLooseBallTransition {
        center: new_pos,
        radius_x: 3.0,
        radius_y: 2.0,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    }
    .sample(input.loose_x_roll, input.loose_y_roll);

    CarryExecutionOutput {
        transition,
        carry_speed: speed * progress_ratio,
        carry_difficulty: difficulty,
        new_pos,
        boundary_crossing,
        velocity,
        facing_direction: motion.facing_direction,
        distance_covered,
        contact_load: pressure,
        error_chance,
        is_error,
        loose_pos,
        constrained_control: sample.constrained_control,
        constrained_control_probability: containment.constrained_control_probability,
        constrained_control_position: containment.constrained_control_position,
    }
}

pub fn execute_pass(input: &PassExecutionInput) -> PassExecutionOutput {
    let retention_probability = input.retention_probability.clamp(0.0, 1.0);
    let technical_probability = input.technical_probability.clamp(0.0, 1.0);
    let computed_transition = crate::execution_transition::PassActionTransition {
        release: crate::interactions::PassReleaseContactTransition {
            contact: crate::interactions::DetectionResult {
                defender_index: None,
                distance: f64::INFINITY,
                contact_probability: 0.0,
                contact_quality: 0.0,
            },
            released_probability: 1.0,
            opposing_control_probability: 0.0,
            unresolved_probability: 0.0,
        },
        execution: crate::execution_transition::PassExecutionTransition::new(
            technical_probability,
            0.0,
        ),
        spatial: crate::execution_transition::PassSpatialTransition::new(
            input.passer_pos,
            input.ideal_target,
            input.passing,
            input.pitch_length,
            input.pitch_width,
        ),
    };
    let transition = input.transition.unwrap_or(computed_transition);
    let delivery_miss = matches!(
        transition.execution.delivery.sample(input.technical_roll),
        crate::execution_transition::BinaryExecutionOutcome::Failure
    );
    let spatial = transition
        .spatial
        .sample(!delivery_miss, input.random_1, input.random_2);
    let target = spatial.target;

    let speed = if input.is_long {
        input.ball_long_pass_speed
    } else {
        input.ball_pass_speed
    };
    let dist = distance(input.passer_pos, target);
    let ticks_needed = (dist / speed.max(0.1)).ceil().max(1.0) as i32;

    PassExecutionOutput {
        transition,
        target,
        error_radius: spatial.error_radius,
        used_target_error: spatial.used_target_error,
        randoms_used: 2,
        speed,
        ticks_needed,
        flight_type_code: if input.is_long { 1 } else { 0 },
        retention_probability,
        technical_probability,
        technical_roll: input.technical_roll,
        delivery_miss,
    }
}

pub fn execute_shot(input: &ShotExecutionInput) -> ShotExecutionOutput {
    let on_target = input.random_1 < input.on_target_prob;
    let goal_y_min = (input.pitch_width - input.goal_width) / 2.0;
    let goal_y_max = (input.pitch_width + input.goal_width) / 2.0;
    let target = if on_target {
        let low = goal_y_min + 0.5;
        let high = goal_y_max - 0.5;
        let target_y = low + (high - low) * input.random_2;
        if input.attacking_right {
            (input.pitch_length, target_y)
        } else {
            (0.0, target_y)
        }
    } else {
        let x_offset = 0.5 + input.random_2 * 2.5;
        let target_x = if input.attacking_right {
            input.pitch_length + x_offset
        } else {
            -x_offset
        };
        let low = goal_y_min - 5.0;
        let high = goal_y_max + 5.0;
        let target_y = low + (high - low) * input.random_3;
        (target_x, target_y)
    };
    let dist = distance(input.shooter_pos, target);
    let ticks_needed = (dist / input.ball_shot_speed.max(0.1)).ceil().max(1.0) as i32;
    ShotExecutionOutput {
        on_target,
        target,
        speed: input.ball_shot_speed,
        distance: dist,
        ticks_needed,
        randoms_used: if on_target { 2 } else { 3 },
        flight_type_code: 3,
    }
}

pub fn execute_clear(input: &ClearExecutionInput) -> ClearExecutionOutput {
    let dist = distance(input.clearer_pos, input.target);
    ClearExecutionOutput {
        origin: input.clearer_pos,
        target: input.target,
        speed: input.ball_long_pass_speed,
        ticks_needed: (dist / input.ball_long_pass_speed.max(0.1)).ceil().max(1.0) as i32,
        flight_type_code: 2,
    }
}

pub fn generate_clear_target(input: &ClearTargetInput) -> ClearTargetOutput {
    let depth = 15.0 + input.depth_roll * 15.0;
    let lateral = -20.0 + input.lateral_roll * 40.0;
    let raw = if input.attacking_right {
        (input.player_pos.0 + depth, input.player_pos.1 + lateral)
    } else {
        (input.player_pos.0 - depth, input.player_pos.1 + lateral)
    };
    ClearTargetOutput {
        target: pitch_clamp(raw, input.pitch_length, input.pitch_width),
    }
}

pub fn execute_hold(input: &HoldExecutionInput<'_>) -> HoldExecutionOutput {
    let mut pressure_x = 0.0;
    let mut pressure_y = 0.0;
    let mut pressure = 0.0;
    let mut nearest_dist = f64::INFINITY;
    for opp in input.opponents {
        if opp.is_goalkeeper {
            continue;
        }
        let dx = input.holder_pos.0 - opp.pos.0;
        let dy = input.holder_pos.1 - opp.pos.1;
        let d = (dx * dx + dy * dy).sqrt().max(0.1);
        nearest_dist = nearest_dist.min(d);
        if d < 8.0 {
            let w = 1.0 - d / 8.0;
            pressure += w;
            pressure_x += (dx / d) * w;
            pressure_y += (dy / d) * w;
        }
    }

    let mut opportunity_x = 0.0;
    let mut opportunity_y = 0.0;
    if let Some(target) = input.opportunity_target {
        let to_target_x = target.0 - input.holder_pos.0;
        let to_target_y = target.1 - input.holder_pos.1;
        let target_len = (to_target_x * to_target_x + to_target_y * to_target_y)
            .sqrt()
            .max(0.1);
        opportunity_x = to_target_x / target_len * 0.22;
        opportunity_y = to_target_y / target_len * 0.52;
    }

    let mut desired_target = input.holder_pos;
    let mut desired_speed = 0.0;
    if pressure > 0.0 || input.opportunity_target.is_some() {
        let norm = (pressure_x * pressure_x + pressure_y * pressure_y)
            .sqrt()
            .max(0.1);
        let away_x = if pressure > 0.0 {
            pressure_x / norm
        } else {
            0.0
        };
        let away_y = if pressure > 0.0 {
            pressure_y / norm
        } else {
            0.0
        };
        let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
        let adjust_x =
            away_x * 0.70 + opportunity_x + forward_dir * if pressure > 0.0 { 0.12 } else { 0.04 };
        let adjust_y = away_y * 0.70 + opportunity_y;
        let adjust_norm = (adjust_x * adjust_x + adjust_y * adjust_y).sqrt().max(0.1);
        let dribbling_factor = input.dribbling / 100.0;
        let max_adjust = 0.45 + 1.15 * dribbling_factor;
        let scan_bonus = if input.opportunity_target.is_some() {
            0.35
        } else {
            0.0
        };
        let move_dist = max_adjust.min(0.35 + pressure * 0.55 + scan_bonus);
        desired_target = pitch_clamp(
            (
                input.holder_pos.0 + adjust_x / adjust_norm * move_dist,
                input.holder_pos.1 + adjust_y / adjust_norm * move_dist,
            ),
            input.pitch_length,
            input.pitch_width,
        );
        desired_speed = move_dist;
    }
    let motion = advance_player_motion(&PlayerMotionInput {
        pos: input.holder_pos,
        target: desired_target,
        velocity: input.velocity,
        speed_ability: input.speed_ability,
        desired_speed,
        acceleration_scale: 0.7,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    });
    let computed_error_chance =
        (pressure - 0.6).max(0.0) * (100.0 - input.dribbling) / (input.carry_error_divisor * 1.8);
    let computed_transition = crate::execution_transition::ControlActionTransition {
        contact: crate::interactions::ControlContactTransition {
            contact: crate::interactions::DetectionResult {
                defender_index: None,
                distance: f64::INFINITY,
                contact_probability: 0.0,
                contact_quality: 0.0,
            },
            retained_probability: 1.0,
            opposing_control_probability: 0.0,
            unresolved_probability: 0.0,
        },
        new_pos: motion.pos,
        velocity: motion.velocity,
        facing_direction: motion.facing_direction,
        distance_covered: motion.distance_covered,
        pressure,
        nearest_dist,
        technical_error:
            crate::execution_transition::BinaryExecutionTransition::from_success_probability(
                computed_error_chance,
            ),
    };
    let transition = input.transition.unwrap_or(computed_transition);
    let new_pos = transition.new_pos;
    let error_chance = transition.technical_error.success_probability;
    let is_error = matches!(
        transition.technical_error.sample(input.error_roll),
        crate::execution_transition::BinaryExecutionOutcome::Success
    );
    let loose_pos = crate::execution_transition::RectangularLooseBallTransition {
        center: new_pos,
        radius_x: 2.0,
        radius_y: 2.0,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    }
    .sample(input.loose_x_roll, input.loose_y_roll);
    HoldExecutionOutput {
        transition,
        new_pos,
        velocity: transition.velocity,
        facing_direction: transition.facing_direction,
        distance_covered: transition.distance_covered,
        pressure: transition.pressure,
        nearest_dist: transition.nearest_dist,
        trace_pressure: (transition.pressure * 100.0).round() / 100.0,
        trace_nearest_dist: if transition.nearest_dist < 999.0 {
            Some((transition.nearest_dist * 10.0).round() / 10.0)
        } else {
            None
        },
        error_chance,
        is_error,
        loose_pos,
        randoms_used: 1 + if is_error { 2 } else { 0 },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pass_input(retention_probability: f64, technical_probability: f64) -> PassExecutionInput {
        PassExecutionInput {
            transition: None,
            passer_pos: (30.0, 34.0),
            ideal_target: (48.0, 34.0),
            passing: 82.0,
            is_long: false,
            lane_risk: 0.40,
            retention_probability,
            technical_probability,
            technical_roll: 0.85,
            pitch_length: 105.0,
            pitch_width: 68.0,
            ball_pass_speed: 18.0,
            ball_long_pass_speed: 22.0,
            tick_duration: 2.0,
            random_1: 0.25,
            random_2: 0.50,
        }
    }

    #[test]
    fn pass_delivery_samples_technical_probability_not_candidate_retention_estimate() {
        let low_retention = execute_pass(&pass_input(0.40, 0.90));
        let high_retention = execute_pass(&pass_input(0.80, 0.90));
        let low_technique = execute_pass(&pass_input(0.80, 0.70));

        assert!(!low_retention.delivery_miss);
        assert!(!high_retention.delivery_miss);
        assert!(low_technique.delivery_miss);
        assert_eq!(low_retention.target, high_retention.target);
        assert_ne!(high_retention.target, low_technique.target);
        assert_eq!(low_retention.retention_probability, 0.40);
        assert_eq!(high_retention.retention_probability, 0.80);
    }

    #[test]
    fn pass_execution_samples_the_projected_transition_object_instead_of_rebuilding_it() {
        let baseline = pass_input(1.0, 1.0);
        let frozen = crate::execution_transition::PassActionTransition {
            release: crate::interactions::PassReleaseContactTransition {
                contact: crate::interactions::DetectionResult {
                    defender_index: Some(4),
                    distance: 0.8,
                    contact_probability: 0.7,
                    contact_quality: 0.6,
                },
                released_probability: 0.3,
                opposing_control_probability: 0.5,
                unresolved_probability: 0.2,
            },
            execution: crate::execution_transition::PassExecutionTransition::new(0.20, 0.0),
            spatial: crate::execution_transition::PassSpatialTransition::new(
                baseline.passer_pos,
                (70.0, 50.0),
                0.0,
                baseline.pitch_length,
                baseline.pitch_width,
            ),
        };
        let output = execute_pass(&PassExecutionInput {
            transition: Some(frozen),
            technical_roll: 0.50,
            technical_probability: 1.0,
            passing: 100.0,
            random_1: 0.0,
            random_2: 1.0,
            ..baseline
        });

        assert!(output.delivery_miss);
        assert_eq!(output.transition.release.contact.defender_index, Some(4));
        assert_eq!(
            output.transition.execution.delivery.success_probability,
            0.20
        );
        assert_ne!(output.target, baseline.ideal_target);
    }

    #[test]
    fn ball_speed_is_measured_per_tick_like_player_speed() {
        let two_second_ticks = execute_pass(&PassExecutionInput {
            ideal_target: (66.0, 34.0),
            technical_roll: 0.0,
            random_1: 0.5,
            random_2: 0.5,
            ..pass_input(1.0, 1.0)
        });
        let one_second_ticks = execute_pass(&PassExecutionInput {
            ideal_target: (66.0, 34.0),
            technical_roll: 0.0,
            tick_duration: 1.0,
            random_1: 0.5,
            random_2: 0.5,
            ..pass_input(1.0, 1.0)
        });

        assert_eq!(two_second_ticks.ticks_needed, 2);
        assert_eq!(one_second_ticks.ticks_needed, 2);
        assert_eq!(two_second_ticks.target, one_second_ticks.target);
        assert_eq!(two_second_ticks.ticks_needed, one_second_ticks.ticks_needed);
    }

    #[test]
    fn control_execution_samples_the_projected_transition_object_instead_of_rebuilding_it() {
        let frozen = crate::execution_transition::ControlActionTransition {
            contact: crate::interactions::ControlContactTransition {
                contact: crate::interactions::DetectionResult {
                    defender_index: Some(2),
                    distance: 0.6,
                    contact_probability: 0.8,
                    contact_quality: 0.7,
                },
                retained_probability: 0.2,
                opposing_control_probability: 0.6,
                unresolved_probability: 0.2,
            },
            new_pos: (44.0, 31.0),
            velocity: (1.2, -0.4),
            facing_direction: Some(341.0),
            distance_covered: 1.4,
            pressure: 0.9,
            nearest_dist: 0.6,
            technical_error:
                crate::execution_transition::BinaryExecutionTransition::from_success_probability(
                    0.75,
                ),
        };
        let output = execute_hold(&HoldExecutionInput {
            transition: Some(frozen),
            holder_pos: (10.0, 10.0),
            velocity: (0.0, 0.0),
            speed_ability: 100,
            dribbling: 100.0,
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            carry_error_divisor: 10_000.0,
            opponents: &[],
            opportunity_target: None,
            error_roll: 0.50,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        });

        assert_eq!(output.new_pos, frozen.new_pos);
        assert_eq!(output.velocity, frozen.velocity);
        assert_eq!(output.facing_direction, frozen.facing_direction);
        assert!(output.is_error);
        assert_eq!(output.transition.contact.contact.defender_index, Some(2));
    }

    fn carry_input<'a>(defender_responses: &'a [DefenderActionInput]) -> CarryExecutionInput<'a> {
        CarryExecutionInput {
            transition: None,
            holder_pos: (20.0, 34.0),
            target: (80.0, 34.0),
            velocity: (0.0, 0.0),
            speed_ability: 99,
            dribbling: 99.0,
            consecutive_carries: 0,
            control_readiness: 1.0,
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            carrier_speed: 3.0,
            carry_error_divisor: 400.0,
            opponents: &[],
            defender_responses,
            error_roll: 1.0,
            containment_roll: 1.0,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        }
    }

    #[test]
    fn carry_accelerates_from_rest_and_returns_the_new_velocity() {
        let output = execute_carry(&carry_input(&[]));

        assert!(output.velocity.0 > 0.0);
        assert!(output.distance_covered > 0.0);
        assert!(output.distance_covered < output.carry_speed);
    }

    #[test]
    fn unsettled_control_limits_immediate_carry_mobility_and_increases_difficulty() {
        let settled = execute_carry(&carry_input(&[]));
        let unsettled = execute_carry(&CarryExecutionInput {
            control_readiness: 0.25,
            ..carry_input(&[])
        });

        assert!(unsettled.carry_speed < settled.carry_speed);
        assert!(unsettled.distance_covered < settled.distance_covered);
        assert!(unsettled.carry_difficulty > settled.carry_difficulty);
        assert!(unsettled.error_chance > settled.error_chance);
    }

    #[test]
    fn lane_blocking_samples_constrained_and_unconstrained_control_as_distinct_branches() {
        let block_lane = [DefenderActionInput {
            index: 3,
            pos: (21.4, 34.2),
            new_pos: (22.2, 34.1),
            action: "block_lane",
            speed: 80.0,
            defence: 80.0,
            tackling: 80.0,
            is_goalkeeper: false,
        }];
        let free = execute_carry(&carry_input(&[]));
        let mut contained_input = carry_input(&block_lane);
        contained_input.containment_roll = 0.0;
        let contained = execute_carry(&contained_input);
        let unconstrained = execute_carry(&carry_input(&block_lane));

        assert!(!contained.is_error);
        assert!(contained.constrained_control);
        assert!(!unconstrained.constrained_control);
        assert!(contained.constrained_control_probability > 0.0);
        assert_eq!(
            contained.constrained_control_probability.to_bits(),
            unconstrained.constrained_control_probability.to_bits()
        );
        assert!(contained.distance_covered < free.distance_covered);
        assert!(contained.new_pos.0 < free.new_pos.0);
        assert_eq!(unconstrained.new_pos, free.new_pos);
    }

    #[test]
    fn carry_execution_samples_the_projected_transition_object_instead_of_rebuilding_it() {
        let frozen = crate::execution_transition::CarrySegmentTransition::new(
            crate::execution_transition::BinaryExecutionTransition::from_success_probability(1.0),
            (24.0, 34.0),
            (24.0, 34.0),
            (3.0, 0.0),
            (21.5, 35.0),
            (21.5, 35.0),
            (0.8, 0.4),
            0.0,
            1.0,
        );
        let output = execute_carry(&CarryExecutionInput {
            transition: Some(frozen),
            containment_roll: 0.99,
            error_roll: 0.0,
            ..carry_input(&[])
        });

        assert!(output.constrained_control);
        assert!(output.is_error);
        assert_eq!(output.new_pos, frozen.constrained.control_pos);
        assert_eq!(output.velocity, frozen.constrained.velocity);
        assert_eq!(
            output.transition.constrained.control_pos,
            frozen.constrained.control_pos
        );
    }

    #[test]
    fn unconstrained_carry_across_goal_line_reports_a_continuous_crossing() {
        let mut input = carry_input(&[]);
        input.holder_pos = (104.0, 34.0);
        input.target = (116.0, 34.0);
        input.velocity = (4.0, 0.0);

        let output = execute_carry(&input);
        let crossing = output
            .boundary_crossing
            .expect("an unimpeded path through the goal line must end play");

        assert_eq!(crossing.kind, crate::physics::PitchBoundaryKind::GoalLine);
        assert_eq!(crossing.point, (105.0, 34.0));
        assert_eq!(output.new_pos.0, 104.5);
    }

    #[test]
    fn containment_prevents_an_intended_crossing_from_becoming_a_dead_ball() {
        let block_lane = [DefenderActionInput {
            index: 3,
            pos: (104.1, 34.0),
            new_pos: (104.3, 34.0),
            action: "block_lane",
            speed: 90.0,
            defence: 90.0,
            tackling: 90.0,
            is_goalkeeper: false,
        }];
        let mut input = carry_input(&block_lane);
        input.holder_pos = (103.8, 34.0);
        input.target = (116.0, 34.0);
        input.velocity = (4.0, 0.0);
        input.containment_roll = 0.0;

        let output = execute_carry(&input);

        assert!(output.constrained_control);
        assert!(output.constrained_control_probability > 0.0);
        assert!(output.boundary_crossing.is_none());
        assert!(output.new_pos.0 < 105.0);
    }
}
