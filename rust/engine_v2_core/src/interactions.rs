use std::borrow::Cow;

use crate::physics::{distance, smoothstep};

#[derive(Debug, Clone, Copy)]
pub struct DefenderActionInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub new_pos: (f64, f64),
    pub action: &'static str,
    pub speed: f64,
    pub defence: f64,
    pub tackling: f64,
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone)]
pub struct DetectionResult {
    pub defender_index: Option<usize>,
    pub distance: f64,
    pub contact_probability: f64,
}

#[derive(Debug, Clone)]
pub struct DuelDetectionInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub carry_target: (f64, f64),
    pub carrier_step_distance: f64,
    pub defenders: &'a [DefenderActionInput],
    pub tackle_range: f64,
}

#[derive(Debug, Clone)]
pub struct CarrySurvivalInput<'a> {
    pub holder_pos: (f64, f64),
    pub carry_target: (f64, f64),
    pub carrier_step_distance: f64,
    pub attacker_dribbling: f64,
    pub defenders: &'a [DefenderActionInput],
    pub tackle_range: f64,
    pub segment_count: i32,
}

#[derive(Debug, Clone)]
pub struct CarryContainmentInput<'a> {
    pub holder_pos: (f64, f64),
    pub carrier_end: (f64, f64),
    pub defenders: &'a [DefenderActionInput],
}

#[derive(Debug, Clone, Copy)]
pub struct CarryContainmentTransition {
    pub constrained_control_probability: f64,
    pub constrained_control_position: (f64, f64),
}

#[derive(Debug, Clone, Copy)]
pub struct CarrySurvivalTransition {
    pub retained_control_probability: f64,
    pub unconstrained_control_probability: f64,
    pub constrained_control_probability: f64,
    pub opposing_control_probability: f64,
    pub unresolved_probability: f64,
    pub unconstrained_control_position: (f64, f64),
    pub constrained_control_position: (f64, f64),
    pub opposing_control_position: (f64, f64),
    pub peak_contact_probability: f64,
    pub peak_containment_probability: f64,
    pub segment_count: i32,
}

#[derive(Debug, Clone)]
pub struct WastedTackleInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub defenders: &'a [DefenderActionInput],
    pub tackle_range: f64,
}

#[derive(Debug, Clone)]
pub struct InterceptionDetectionInput<'a> {
    pub pass_origin: (f64, f64),
    pub pass_target: (f64, f64),
    pub defenders: &'a [DefenderActionInput],
    pub interception_reach: f64,
}

#[derive(Debug, Clone)]
pub struct DuelResolveInput {
    pub attacker_dribbling: f64,
    pub defender_tackling: f64,
    pub attacker_uniform: f64,
    pub defender_uniform: f64,
}

#[derive(Debug, Clone)]
pub struct InterceptionResolveInput {
    pub defender_defence: f64,
    pub passer_ability: f64,
    pub distance: f64,
    pub interception_reach: f64,
    pub random_value: f64,
}

#[derive(Debug, Clone)]
pub struct DefensivePressureInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_action: &'a str,
    pub defenders: &'a [DefenderActionInput],
    pub press_radius: f64,
    pub duel_detected: bool,
    pub interception_detected: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DefensivePressureOutput {
    pub defender_index: usize,
    pub successful: bool,
}

pub fn resolve_duel(input: &DuelResolveInput) -> &'static str {
    let atk_roll = input.attacker_dribbling + input.attacker_uniform;
    let def_roll = input.defender_tackling + input.defender_uniform;
    let diff = def_roll - atk_roll;
    if diff > 8.0 {
        "defender_wins"
    } else if diff < -8.0 {
        "attacker_wins"
    } else {
        "loose_ball"
    }
}

pub fn interception_chance(input: &InterceptionResolveInput) -> f64 {
    let base_chance = input.defender_defence / 200.0;
    let proximity_factor = (1.0 - input.distance / input.interception_reach).max(0.3);
    let pass_quality = input.passer_ability / 150.0;
    (base_chance * proximity_factor * (1.0 - pass_quality * 0.4)).clamp(0.05, 0.60)
}

pub fn resolve_interception(input: &InterceptionResolveInput) -> bool {
    input.random_value < interception_chance(input)
}

#[derive(Clone, Copy)]
struct ContactEngagementProfile {
    action: &'static str,
    reach_scale: f64,
    engagement_weight: f64,
    containment_weight: f64,
    containment_reach_scale: f64,
}

const CONTACT_ENGAGEMENT_PROFILES: [ContactEngagementProfile; 5] = [
    ContactEngagementProfile {
        action: "tackle",
        reach_scale: 1.08,
        engagement_weight: 0.86,
        containment_weight: 0.28,
        containment_reach_scale: 0.95,
    },
    ContactEngagementProfile {
        action: "approach",
        reach_scale: 0.94,
        engagement_weight: 0.36,
        containment_weight: 0.46,
        containment_reach_scale: 1.15,
    },
    ContactEngagementProfile {
        action: "close_down",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        containment_weight: 0.42,
        containment_reach_scale: 1.20,
    },
    ContactEngagementProfile {
        action: "block_lane",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        containment_weight: 0.84,
        containment_reach_scale: 1.28,
    },
    ContactEngagementProfile {
        action: "mark_runner",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        containment_weight: 0.60,
        containment_reach_scale: 1.16,
    },
];

fn engagement_profile(action: &str) -> ContactEngagementProfile {
    CONTACT_ENGAGEMENT_PROFILES
        .iter()
        .find(|profile| profile.action == action)
        .copied()
        .unwrap_or(ContactEngagementProfile {
            action: "hold_position",
            reach_scale: 0.0,
            engagement_weight: 0.0,
            containment_weight: 0.0,
            containment_reach_scale: 0.0,
        })
}

fn step_toward(origin: (f64, f64), target: (f64, f64), step_distance: f64) -> (f64, f64) {
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let distance = (dx * dx + dy * dy).sqrt();
    if distance <= 1e-9 {
        return origin;
    }
    let distance_ratio = (step_distance.max(0.0) / distance).min(1.0);
    (
        origin.0 + dx * distance_ratio,
        origin.1 + dy * distance_ratio,
    )
}

fn simultaneous_closest_distance(
    left_start: (f64, f64),
    left_end: (f64, f64),
    right_start: (f64, f64),
    right_end: (f64, f64),
) -> f64 {
    let relative_start = (left_start.0 - right_start.0, left_start.1 - right_start.1);
    let relative_velocity = (
        (left_end.0 - left_start.0) - (right_end.0 - right_start.0),
        (left_end.1 - left_start.1) - (right_end.1 - right_start.1),
    );
    let velocity_norm =
        relative_velocity.0 * relative_velocity.0 + relative_velocity.1 * relative_velocity.1;
    let time = if velocity_norm <= 1e-9 {
        0.0
    } else {
        (-(relative_start.0 * relative_velocity.0 + relative_start.1 * relative_velocity.1)
            / velocity_norm)
            .clamp(0.0, 1.0)
    };
    let separation = (
        relative_start.0 + relative_velocity.0 * time,
        relative_start.1 + relative_velocity.1 * time,
    );
    (separation.0 * separation.0 + separation.1 * separation.1).sqrt()
}

#[derive(Clone, Copy)]
struct CarryContainment {
    probability: f64,
    constrained_position: (f64, f64),
}

fn defender_carry_containment(
    carrier_start: (f64, f64),
    carrier_end: (f64, f64),
    defender: &DefenderActionInput,
) -> CarryContainment {
    if defender.is_goalkeeper {
        return CarryContainment {
            probability: 0.0,
            constrained_position: carrier_end,
        };
    }
    let profile = engagement_profile(defender.action);
    if profile.containment_weight <= 0.0 {
        return CarryContainment {
            probability: 0.0,
            constrained_position: carrier_end,
        };
    }
    let path_delta = (
        carrier_end.0 - carrier_start.0,
        carrier_end.1 - carrier_start.1,
    );
    let path_distance = (path_delta.0 * path_delta.0 + path_delta.1 * path_delta.1).sqrt();
    if path_distance <= 1e-9 {
        return CarryContainment {
            probability: 0.0,
            constrained_position: carrier_start,
        };
    }
    let direction = (path_delta.0 / path_distance, path_delta.1 / path_distance);
    let defender_midpoint = (
        (defender.pos.0 + defender.new_pos.0) * 0.5,
        (defender.pos.1 + defender.new_pos.1) * 0.5,
    );
    let midpoint_offset = (
        defender_midpoint.0 - carrier_start.0,
        defender_midpoint.1 - carrier_start.1,
    );
    let forward_occupation = midpoint_offset.0 * direction.0 + midpoint_offset.1 * direction.1;
    let closest_distance =
        simultaneous_closest_distance(carrier_start, carrier_end, defender.pos, defender.new_pos);
    let corridor_width = 1.15 + 1.50 * profile.containment_reach_scale;
    let corridor_occupation =
        1.0 - smoothstep(corridor_width * 0.28, corridor_width, closest_distance);
    let forward_coverage = smoothstep(
        -path_distance * 0.45,
        path_distance * 0.38,
        forward_occupation,
    );
    let anticipation = 0.68
        + 0.18 * (defender.speed / 100.0).clamp(0.0, 1.0)
        + 0.14 * (defender.defence / 100.0).clamp(0.0, 1.0);
    let probability =
        (profile.containment_weight * corridor_occupation * forward_coverage * anticipation)
            .clamp(0.0, 0.98);
    let control_gap = 0.52
        + 0.42 * (defender.defence / 100.0).clamp(0.0, 1.0)
        + 0.18 * (defender.speed / 100.0).clamp(0.0, 1.0);
    let constrained_progress = (forward_occupation - control_gap).clamp(0.0, path_distance);

    CarryContainment {
        probability,
        constrained_position: (
            carrier_start.0 + direction.0 * constrained_progress,
            carrier_start.1 + direction.1 * constrained_progress,
        ),
    }
}

pub fn carry_containment_transition(
    input: &CarryContainmentInput<'_>,
) -> CarryContainmentTransition {
    let mut no_containment_probability = 1.0;
    let mut weighted_position = (0.0, 0.0);
    let mut position_weight = 0.0;
    for defender in input.defenders {
        let containment = defender_carry_containment(input.holder_pos, input.carrier_end, defender);
        no_containment_probability *= 1.0 - containment.probability;
        weighted_position.0 += containment.probability * containment.constrained_position.0;
        weighted_position.1 += containment.probability * containment.constrained_position.1;
        position_weight += containment.probability;
    }
    let probability = (1.0 - no_containment_probability).clamp(0.0, 1.0);
    let constrained_position = if position_weight > 1e-9 {
        (
            weighted_position.0 / position_weight,
            weighted_position.1 / position_weight,
        )
    } else {
        input.carrier_end
    };

    CarryContainmentTransition {
        constrained_control_probability: probability,
        constrained_control_position: constrained_position,
    }
}

fn uniform_difference_cdf(value: f64, bound: f64) -> f64 {
    let bound = bound.max(1e-9);
    if value <= -2.0 * bound {
        0.0
    } else if value >= 2.0 * bound {
        1.0
    } else if value < 0.0 {
        (value + 2.0 * bound).powi(2) / (8.0 * bound * bound)
    } else {
        1.0 - (2.0 * bound - value).powi(2) / (8.0 * bound * bound)
    }
}

fn duel_outcome_probabilities(attacker_dribbling: f64, defender_tackling: f64) -> (f64, f64, f64) {
    let skill_delta = defender_tackling - attacker_dribbling;
    let attacker_wins = uniform_difference_cdf(-8.0 - skill_delta, 12.0);
    let defender_wins = 1.0 - uniform_difference_cdf(8.0 - skill_delta, 12.0);
    let loose_ball = (1.0 - attacker_wins - defender_wins).max(0.0);
    (attacker_wins, defender_wins, loose_ball)
}

fn projected_defender_actions(
    defenders: &[DefenderActionInput],
    segment: i32,
) -> Vec<DefenderActionInput> {
    let segment = segment.max(0) as f64;
    defenders
        .iter()
        .map(|defender| {
            let movement = (
                defender.new_pos.0 - defender.pos.0,
                defender.new_pos.1 - defender.pos.1,
            );
            let pos = (
                defender.pos.0 + movement.0 * segment,
                defender.pos.1 + movement.1 * segment,
            );
            DefenderActionInput {
                index: defender.index,
                pos,
                new_pos: (pos.0 + movement.0, pos.1 + movement.1),
                action: defender.action,
                speed: defender.speed,
                defence: defender.defence,
                tackling: defender.tackling,
                is_goalkeeper: defender.is_goalkeeper,
            }
        })
        .collect()
}

pub fn detect_duel(input: &DuelDetectionInput<'_>) -> DetectionResult {
    let exposure_multiplier = match input.holder_action {
        "carry" | "dribble" => 1.0,
        "hold" | "shield" => 0.68,
        "reorient" => 0.58,
        _ => 0.0,
    };
    if exposure_multiplier <= 0.0 {
        return DetectionResult {
            defender_index: None,
            distance: 0.0,
            contact_probability: 0.0,
        };
    }
    let carrier_end = step_toward(
        input.holder_pos,
        input.carry_target,
        input.carrier_step_distance,
    );
    let mut best_contact = DetectionResult {
        defender_index: None,
        distance: 0.0,
        contact_probability: 0.0,
    };
    for defender in input.defenders {
        if defender.is_goalkeeper {
            continue;
        }
        let profile = engagement_profile(defender.action);
        if profile.engagement_weight <= 0.0 {
            continue;
        }
        let physical_reach = (0.75 + 0.36 * input.tackle_range.max(0.0)) * profile.reach_scale;
        if physical_reach <= 0.0 {
            continue;
        }
        let closest_distance = simultaneous_closest_distance(
            input.holder_pos,
            carrier_end,
            defender.pos,
            defender.new_pos,
        );
        if closest_distance >= physical_reach {
            continue;
        }
        let proximity = 1.0 - smoothstep(physical_reach * 0.34, physical_reach, closest_distance);
        let start_distance = distance(input.holder_pos, defender.pos);
        let end_distance = distance(carrier_end, defender.new_pos);
        let convergence = smoothstep(
            -physical_reach * 0.20,
            physical_reach * 0.70,
            start_distance - end_distance,
        );
        let speed_factor = 0.78 + 0.22 * (defender.speed / 100.0).clamp(0.0, 1.0);
        let defensive_timing = 0.76 + 0.24 * (defender.defence / 100.0).clamp(0.0, 1.0);
        let contact_probability = (exposure_multiplier
            * profile.engagement_weight
            * (0.18 + 0.82 * proximity)
            * (0.70 + 0.30 * convergence)
            * speed_factor
            * defensive_timing)
            .clamp(0.0, 0.95);
        if contact_probability > best_contact.contact_probability {
            best_contact = DetectionResult {
                defender_index: Some(defender.index),
                distance: closest_distance,
                contact_probability,
            };
        }
    }
    best_contact
}

fn carry_survival_transition_with_defender_provider<'a>(
    input: &CarrySurvivalInput<'_>,
    mut defenders_for_segment: impl FnMut(i32) -> Cow<'a, [DefenderActionInput]>,
) -> CarrySurvivalTransition {
    let step_distance = input.carrier_step_distance.max(0.1);
    let carry_distance = distance(input.holder_pos, input.carry_target);
    let geometric_segments = (carry_distance / step_distance).ceil().max(1.0) as i32;
    let segment_count = input.segment_count.max(1).min(geometric_segments.max(1));
    let mut unconstrained_control_probability = 1.0;
    let mut constrained_control_probability = 0.0;
    let mut opposing_control_probability = 0.0;
    let mut unresolved_probability = 0.0;
    let mut weighted_constrained_position = (0.0, 0.0);
    let mut weighted_opposing_position = (0.0, 0.0);
    let mut peak_contact_probability: f64 = 0.0;
    let mut peak_containment_probability: f64 = 0.0;

    for segment in 0..segment_count {
        let holder_pos = step_toward(
            input.holder_pos,
            input.carry_target,
            step_distance * segment as f64,
        );
        let carrier_end = step_toward(
            input.holder_pos,
            input.carry_target,
            step_distance * (segment + 1) as f64,
        );
        let projected_defenders = defenders_for_segment(segment);
        let duel = detect_duel(&DuelDetectionInput {
            holder_pos,
            holder_action: "carry",
            carry_target: input.carry_target,
            carrier_step_distance: step_distance,
            defenders: &projected_defenders,
            tackle_range: input.tackle_range,
        });
        peak_contact_probability = peak_contact_probability.max(duel.contact_probability);
        let entering_probability = unconstrained_control_probability;
        let (opposing_increment, unresolved_increment) = duel
            .defender_index
            .and_then(|defender_idx| {
                projected_defenders
                    .iter()
                    .find(|defender| defender.index == defender_idx)
            })
            .map(|defender| {
                let (_, defender_wins, loose_ball) =
                    duel_outcome_probabilities(input.attacker_dribbling, defender.tackling);
                (
                    entering_probability * duel.contact_probability * defender_wins,
                    entering_probability * duel.contact_probability * loose_ball,
                )
            })
            .unwrap_or((0.0, 0.0));
        let surviving_after_contact =
            entering_probability - opposing_increment - unresolved_increment;
        let containment = carry_containment_transition(&CarryContainmentInput {
            holder_pos,
            carrier_end,
            defenders: &projected_defenders,
        });
        peak_containment_probability =
            peak_containment_probability.max(containment.constrained_control_probability);
        let constrained_increment =
            surviving_after_contact * containment.constrained_control_probability;

        opposing_control_probability += opposing_increment;
        unresolved_probability += unresolved_increment;
        constrained_control_probability += constrained_increment;
        weighted_opposing_position.0 += opposing_increment
            * projected_defenders
                .iter()
                .find(|defender| Some(defender.index) == duel.defender_index)
                .map(|defender| defender.pos.0)
                .unwrap_or(carrier_end.0);
        weighted_opposing_position.1 += opposing_increment
            * projected_defenders
                .iter()
                .find(|defender| Some(defender.index) == duel.defender_index)
                .map(|defender| defender.pos.1)
                .unwrap_or(carrier_end.1);
        weighted_constrained_position.0 +=
            constrained_increment * containment.constrained_control_position.0;
        weighted_constrained_position.1 +=
            constrained_increment * containment.constrained_control_position.1;
        unconstrained_control_probability = surviving_after_contact - constrained_increment;
    }

    let unconstrained_control_position = step_toward(
        input.holder_pos,
        input.carry_target,
        step_distance * segment_count as f64,
    );
    let constrained_control_position = if constrained_control_probability > 1e-9 {
        (
            weighted_constrained_position.0 / constrained_control_probability,
            weighted_constrained_position.1 / constrained_control_probability,
        )
    } else {
        unconstrained_control_position
    };
    let opposing_control_position = if opposing_control_probability > 1e-9 {
        (
            weighted_opposing_position.0 / opposing_control_probability,
            weighted_opposing_position.1 / opposing_control_probability,
        )
    } else {
        unconstrained_control_position
    };
    let probability_mass = unconstrained_control_probability
        + constrained_control_probability
        + opposing_control_probability
        + unresolved_probability;
    let normalization = probability_mass.max(1e-9);
    let unconstrained_control_probability =
        (unconstrained_control_probability / normalization).clamp(0.0, 1.0);
    let constrained_control_probability =
        (constrained_control_probability / normalization).clamp(0.0, 1.0);

    CarrySurvivalTransition {
        retained_control_probability: (unconstrained_control_probability
            + constrained_control_probability)
            .clamp(0.0, 1.0),
        unconstrained_control_probability,
        constrained_control_probability,
        opposing_control_probability: (opposing_control_probability / normalization)
            .clamp(0.0, 1.0),
        unresolved_probability: (unresolved_probability / normalization).clamp(0.0, 1.0),
        unconstrained_control_position,
        constrained_control_position,
        opposing_control_position,
        peak_contact_probability,
        peak_containment_probability,
        segment_count,
    }
}

pub fn carry_survival_transition(input: &CarrySurvivalInput<'_>) -> CarrySurvivalTransition {
    carry_survival_transition_with_defender_provider(input, |segment| {
        Cow::Owned(projected_defender_actions(input.defenders, segment))
    })
}

pub fn carry_survival_transition_with_defender_responses(
    input: &CarrySurvivalInput<'_>,
    defender_responses: &[Vec<DefenderActionInput>],
) -> CarrySurvivalTransition {
    carry_survival_transition_with_defender_provider(input, |segment| {
        defender_responses
            .get(segment.max(0) as usize)
            .map(|responses| Cow::Borrowed(responses.as_slice()))
            .unwrap_or_else(|| Cow::Owned(projected_defender_actions(input.defenders, segment)))
    })
}

pub fn carry_survival_transition_with_defender_response_slices(
    input: &CarrySurvivalInput<'_>,
    defender_responses: &[&[DefenderActionInput]],
) -> CarrySurvivalTransition {
    carry_survival_transition_with_defender_provider(input, |segment| {
        Cow::Borrowed(
            defender_responses
                .get(segment.max(0) as usize)
                .copied()
                .unwrap_or(&[]),
        )
    })
}

pub fn track_defensive_pressures_into(
    input: &DefensivePressureInput<'_>,
    output: &mut [DefensivePressureOutput],
) -> usize {
    let successful_action = matches!(input.holder_action, "pass" | "shoot" | "clear");
    let pressure_range = input.press_radius * 0.55;
    let mut count = 0;
    for defender in input.defenders {
        if defender.is_goalkeeper {
            continue;
        }
        let d_now = distance(defender.pos, input.holder_pos);
        let d_next = distance(defender.new_pos, input.holder_pos);
        let min_dist = d_now.min(d_next);
        let is_pressure = (matches!(defender.action, "approach" | "tackle")
            && min_dist < pressure_range)
            || (matches!(defender.action, "block_lane" | "mark_runner")
                && min_dist < pressure_range * 0.72);
        if !is_pressure {
            continue;
        }
        assert!(
            count < output.len(),
            "defensive pressure output buffer is too small"
        );
        output[count] = DefensivePressureOutput {
            defender_index: defender.index,
            successful: input.duel_detected
                || input.interception_detected
                || defender.action == "tackle"
                || successful_action,
        };
        count += 1;
    }
    count
}

pub fn track_defensive_pressures(
    input: &DefensivePressureInput<'_>,
) -> Vec<DefensivePressureOutput> {
    let mut outputs = vec![
        DefensivePressureOutput {
            defender_index: 0,
            successful: false,
        };
        input.defenders.len()
    ];
    let count = track_defensive_pressures_into(input, &mut outputs);
    outputs.truncate(count);
    outputs
}

pub fn detect_wasted_tackle(input: &WastedTackleInput<'_>) -> Vec<DetectionResult> {
    if input.holder_action == "carry" || input.holder_action == "dribble" {
        return Vec::new();
    }
    let mut results = Vec::new();
    for defender in input.defenders {
        if defender.action != "tackle" {
            continue;
        }
        let d = distance(input.holder_pos, defender.pos);
        if d < input.tackle_range * 1.5 {
            results.push(DetectionResult {
                defender_index: Some(defender.index),
                distance: d,
                contact_probability: 0.0,
            });
        }
    }
    results
}

pub fn detect_interception(input: &InterceptionDetectionInput<'_>) -> DetectionResult {
    let dx = input.pass_target.0 - input.pass_origin.0;
    let dy = input.pass_target.1 - input.pass_origin.1;
    let pass_length = (dx * dx + dy * dy).sqrt();
    if pass_length < 1.0 {
        return DetectionResult {
            defender_index: None,
            distance: 0.0,
            contact_probability: 0.0,
        };
    }
    let nx = dx / pass_length;
    let ny = dy / pass_length;

    for defender in input.defenders {
        let px = defender.new_pos.0 - input.pass_origin.0;
        let py = defender.new_pos.1 - input.pass_origin.1;
        let proj = px * nx + py * ny;
        if proj < 2.0 || proj > pass_length - 2.0 {
            continue;
        }
        let perp = (px * ny - py * nx).abs();
        if perp < input.interception_reach {
            return DetectionResult {
                defender_index: Some(defender.index),
                distance: perp,
                contact_probability: 0.0,
            };
        }
    }
    DetectionResult {
        defender_index: None,
        distance: 0.0,
        contact_probability: 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        carry_containment_transition, carry_survival_transition,
        carry_survival_transition_with_defender_responses, detect_duel, track_defensive_pressures,
        track_defensive_pressures_into, CarryContainmentInput, CarrySurvivalInput,
        DefenderActionInput, DefensivePressureInput, DuelDetectionInput,
    };
    use crate::{temporal_option_value, PossessionTransition, TemporalOptionValueInput};

    fn defender(
        index: usize,
        pos: (f64, f64),
        new_pos: (f64, f64),
        action: &'static str,
    ) -> DefenderActionInput {
        DefenderActionInput {
            index,
            pos,
            new_pos,
            action,
            speed: 80.0,
            defence: 80.0,
            tackling: 80.0,
            is_goalkeeper: false,
        }
    }

    #[test]
    fn fixed_pressure_output_matches_vec_api() {
        let mut goalkeeper = defender(0, (2.0, 0.0), (1.0, 0.0), "tackle");
        goalkeeper.is_goalkeeper = true;
        let defenders = [
            goalkeeper,
            defender(1, (5.0, 0.0), (3.0, 0.0), "tackle"),
            defender(2, (5.8, 1.0), (4.9, 0.8), "approach"),
            defender(3, (3.8, 2.2), (3.4, 1.5), "block_lane"),
            defender(4, (14.0, 0.0), (13.0, 0.0), "mark_runner"),
        ];
        let input = DefensivePressureInput {
            holder_pos: (0.0, 0.0),
            holder_action: "pass",
            defenders: &defenders,
            press_radius: 12.0,
            duel_detected: false,
            interception_detected: true,
        };
        let expected = track_defensive_pressures(&input);
        let mut output = [super::DefensivePressureOutput {
            defender_index: 0,
            successful: false,
        }; 5];
        let count = track_defensive_pressures_into(&input, &mut output);

        assert_eq!(&output[..count], expected.as_slice());
    }

    #[test]
    fn lane_blocking_is_pressure_not_an_instant_ball_contact() {
        let defenders = [defender(3, (5.5, 1.1), (5.5, 1.1), "block_lane")];
        let result = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            defenders: &defenders,
            tackle_range: 6.0,
        });

        assert_eq!(result.defender_index, None);
        assert_eq!(result.contact_probability, 0.0);
    }

    #[test]
    fn close_down_constrains_the_dribble_without_creating_contact() {
        let defenders = [defender(3, (5.0, 0.0), (3.0, 0.0), "close_down")];
        let duel = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            defenders: &defenders,
            tackle_range: 6.0,
        });
        let containment = carry_containment_transition(&CarryContainmentInput {
            holder_pos: (0.0, 0.0),
            carrier_end: (3.0, 0.0),
            defenders: &defenders,
        });

        assert_eq!(duel.defender_index, None);
        assert_eq!(duel.contact_probability, 0.0);
        assert!(
            containment.constrained_control_probability > 0.0,
            "a close-down that occupies the carrier's path must constrain progress"
        );
    }

    #[test]
    fn distant_future_path_crossing_is_not_a_current_tick_duel() {
        let defenders = [defender(4, (8.0, 0.0), (7.0, 0.0), "tackle")];
        let result = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (20.0, 0.0),
            carrier_step_distance: 3.0,
            defenders: &defenders,
            tackle_range: 6.0,
        });

        assert_eq!(result.defender_index, None);
    }

    #[test]
    fn converging_tackler_creates_a_probabilistic_contact() {
        let defenders = [defender(5, (3.0, 2.0), (2.4, 0.4), "tackle")];
        let result = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            defenders: &defenders,
            tackle_range: 6.0,
        });

        assert_eq!(result.defender_index, Some(5));
        assert!(result.distance < 1.7);
        assert!(result.contact_probability > 0.2);
    }

    #[test]
    fn shielding_exposes_the_holder_without_becoming_a_dribble_contact() {
        let defenders = [defender(5, (2.5, 1.2), (1.8, 0.3), "tackle")];
        let carry = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (6.0, 0.0),
            carrier_step_distance: 1.2,
            defenders: &defenders,
            tackle_range: 6.0,
        });
        let shield = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "hold",
            carry_target: (0.0, 0.0),
            carrier_step_distance: 0.45,
            defenders: &defenders,
            tackle_range: 6.0,
        });

        assert_eq!(shield.defender_index, Some(5));
        assert!(shield.contact_probability > 0.0);
        assert!(shield.contact_probability < carry.contact_probability);
    }

    #[test]
    fn carry_survival_uses_contact_outcomes_and_preserves_probability_mass() {
        let defenders = [defender(5, (3.0, 2.0), (2.4, 0.4), "tackle")];
        let detection = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            defenders: &defenders,
            tackle_range: 6.0,
        });
        let transition = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (0.0, 0.0),
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            attacker_dribbling: 70.0,
            defenders: &defenders,
            tackle_range: 6.0,
            segment_count: 1,
        });
        let probability_mass = transition.retained_control_probability
            + transition.opposing_control_probability
            + transition.unresolved_probability;

        assert!((probability_mass - 1.0).abs() < 1e-9);
        assert!((transition.peak_contact_probability - detection.contact_probability).abs() < 1e-9);
        assert!(transition.retained_control_probability < 1.0);
        assert!(transition.opposing_control_probability > 0.0);
        assert!(transition.unresolved_probability > 0.0);
    }

    #[test]
    fn contact_risk_lowers_the_carry_temporal_value() {
        let defenders = [defender(5, (3.0, 2.0), (2.4, 0.4), "tackle")];
        let safe = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (0.0, 0.0),
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            attacker_dribbling: 70.0,
            defenders: &[],
            tackle_range: 6.0,
            segment_count: 1,
        });
        let contested = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (0.0, 0.0),
            carry_target: (10.0, 0.0),
            carrier_step_distance: 3.0,
            attacker_dribbling: 70.0,
            defenders: &defenders,
            tackle_range: 6.0,
            segment_count: 1,
        });
        let value_for = |retained: f64, opposing: f64| {
            temporal_option_value(&TemporalOptionValueInput {
                current_control_value: 0.16,
                transition: PossessionTransition {
                    goal_probability: 0.0,
                    retained_control_probability: retained,
                    retained_control_value: 0.24,
                    opposing_control_probability: opposing,
                    opposing_control_value: 0.18,
                },
                duration_ticks: 1,
                tempo: 0.56,
                risk_budget: 0.48,
            })
        };
        let safe_value = value_for(
            safe.retained_control_probability,
            safe.opposing_control_probability,
        );
        let contested_value = value_for(
            contested.retained_control_probability,
            contested.opposing_control_probability,
        );

        assert!(contested_value.score < safe_value.score);
        assert!(contested.peak_contact_probability > safe.peak_contact_probability);
    }

    #[test]
    fn responsive_defenders_reduce_long_carry_survival_without_turning_lane_blockers_into_tacklers()
    {
        let stale_defenders = [defender(6, (14.0, 7.0), (14.0, 7.0), "tackle")];
        let input = CarrySurvivalInput {
            holder_pos: (0.0, 0.0),
            carry_target: (15.0, 0.0),
            carrier_step_distance: 3.0,
            attacker_dribbling: 70.0,
            defenders: &stale_defenders,
            tackle_range: 6.0,
            segment_count: 5,
        };
        let stale = carry_survival_transition(&input);
        let responsive_defenders = vec![
            vec![defender(6, (14.0, 7.0), (12.0, 5.0), "tackle")],
            vec![defender(6, (12.0, 5.0), (8.0, 0.0), "tackle")],
            vec![defender(6, (8.0, 0.0), (7.0, 0.0), "tackle")],
            vec![defender(6, (7.0, 0.0), (9.0, 0.0), "tackle")],
            vec![defender(6, (9.0, 0.0), (12.0, 0.0), "tackle")],
        ];
        let responsive =
            carry_survival_transition_with_defender_responses(&input, &responsive_defenders);
        let lane_blocker_responses = responsive_defenders
            .iter()
            .map(|segment| {
                segment
                    .iter()
                    .map(|response| {
                        defender(response.index, response.pos, response.new_pos, "block_lane")
                    })
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        let lane_blocker =
            carry_survival_transition_with_defender_responses(&input, &lane_blocker_responses);

        assert!(stale.retained_control_probability > 0.999);
        assert!(
            responsive.retained_control_probability + 0.10 < stale.retained_control_probability,
            "closed-loop response must expose future carry contact: stale={stale:?}, responsive={responsive:?}"
        );
        assert!(responsive.opposing_control_probability > 0.0);
        assert_eq!(lane_blocker.peak_contact_probability, 0.0);
        assert_eq!(lane_blocker.opposing_control_probability, 0.0);
        assert_eq!(lane_blocker.unresolved_probability, 0.0);
        assert!(
            lane_blocker.constrained_control_probability > 0.0,
            "lane blocking must move retained control into a constrained state: {lane_blocker:?}"
        );
        assert!(
            lane_blocker.unconstrained_control_probability + 0.10
                < stale.unconstrained_control_probability,
            "lane blocking must reduce completed carry progression without fabricating contact: stale={stale:?}, lane={lane_blocker:?}"
        );
        assert!(
            lane_blocker.constrained_control_position.0
                < lane_blocker.unconstrained_control_position.0,
            "contained control must end before the requested target: {lane_blocker:?}"
        );
    }
}
