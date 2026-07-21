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
    pub gk_saving: f64,
    pub gk_positioning: f64,
    pub gk_reaction: f64,
    pub is_goalkeeper: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct DetectionResult {
    pub defender_index: Option<usize>,
    pub distance: f64,
    pub contact_probability: f64,
    pub contact_quality: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct PassReleaseContactTransition {
    pub contact: DetectionResult,
    pub released_probability: f64,
    pub opposing_control_probability: f64,
    pub unresolved_probability: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct ControlContactTransition {
    pub contact: DetectionResult,
    pub retained_probability: f64,
    pub opposing_control_probability: f64,
    pub unresolved_probability: f64,
}

impl ControlContactTransition {
    pub fn contact_occurs(self, roll: f64) -> bool {
        self.contact.defender_index.is_some()
            && roll.clamp(0.0, 1.0) < self.contact.contact_probability
    }
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

pub const PLAYER_BODY_SEPARATION: f64 = 0.9;

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
pub struct DuelResolveInput<'a> {
    pub attacker_dribbling: f64,
    pub defender_tackling: f64,
    pub defender_defence: f64,
    pub holder_action: &'a str,
    pub defender_action: &'a str,
    pub contact_quality: f64,
    pub attacker_uniform: f64,
    pub defender_uniform: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct DuelOutcomeTransition {
    attacker_dribbling: f64,
    defender_tackling: f64,
    defender_defence: f64,
    holder_action: &'static str,
    defender_action: &'static str,
    contact_quality: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DuelOutcome {
    AttackerWins,
    DefenderWins,
    LooseBall,
}

#[derive(Debug, Clone, Copy)]
pub struct DuelOutcomeProbabilities {
    pub attacker_wins: f64,
    pub defender_wins: f64,
    pub loose_ball: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct GoalkeeperSmotherTransition {
    attacker_control: f64,
    goalkeeper_saving: f64,
    goalkeeper_positioning: f64,
    goalkeeper_reaction: f64,
    goalkeeper_speed: f64,
    contact_quality: f64,
}

impl DuelOutcomeTransition {
    pub fn new(
        attacker_dribbling: f64,
        defender: DefenderActionInput,
        holder_action: &'static str,
        contact_quality: f64,
    ) -> Self {
        assert_ne!(
            defender.action, "smother",
            "goalkeeper smothers must use GoalkeeperSmotherTransition"
        );
        Self {
            attacker_dribbling,
            defender_tackling: defender.tackling,
            defender_defence: defender.defence,
            holder_action,
            defender_action: defender.action,
            contact_quality,
        }
    }

    fn margin(self, attacker_uniform: f64, defender_uniform: f64) -> f64 {
        duel_margin(&DuelResolveInput {
            attacker_dribbling: self.attacker_dribbling,
            defender_tackling: self.defender_tackling,
            defender_defence: self.defender_defence,
            holder_action: self.holder_action,
            defender_action: self.defender_action,
            contact_quality: self.contact_quality,
            attacker_uniform,
            defender_uniform,
        })
    }

    pub fn sample(self, attacker_uniform: f64, defender_uniform: f64) -> DuelOutcome {
        match duel_outcome_code_from_margin(
            self.margin(attacker_uniform, defender_uniform),
            self.contact_quality,
            self.defender_action,
        ) {
            0 => DuelOutcome::AttackerWins,
            1 => DuelOutcome::DefenderWins,
            _ => DuelOutcome::LooseBall,
        }
    }

    pub fn probabilities(self) -> DuelOutcomeProbabilities {
        let margin_without_rolls = self.margin(0.0, 0.0);
        let contest_band = duel_contest_margin_band(self.contact_quality, self.defender_action);
        let attacker_wins = uniform_difference_cdf(-contest_band - margin_without_rolls, 12.0);
        let defender_wins = 1.0 - uniform_difference_cdf(contest_band - margin_without_rolls, 12.0);
        DuelOutcomeProbabilities {
            attacker_wins,
            defender_wins,
            loose_ball: (1.0 - attacker_wins - defender_wins).max(0.0),
        }
    }
}

impl GoalkeeperSmotherTransition {
    pub fn new(
        attacker_control: f64,
        goalkeeper: DefenderActionInput,
        contact_quality: f64,
    ) -> Self {
        assert!(
            goalkeeper.is_goalkeeper && goalkeeper.action == "smother",
            "smother transitions require a goalkeeper committed to smother"
        );
        Self {
            attacker_control,
            goalkeeper_saving: goalkeeper.gk_saving,
            goalkeeper_positioning: goalkeeper.gk_positioning,
            goalkeeper_reaction: goalkeeper.gk_reaction,
            goalkeeper_speed: goalkeeper.speed,
            contact_quality,
        }
    }

    fn margin_without_rolls(self) -> f64 {
        let handling = self.goalkeeper_saving * 0.46
            + self.goalkeeper_reaction * 0.32
            + self.goalkeeper_positioning * 0.22;
        let control_margin = (handling - self.attacker_control) * 0.30;
        let contact_margin = (self.contact_quality.clamp(0.0, 1.0) - 0.5) * 15.0;
        let arrival_margin = ((self.goalkeeper_speed / 100.0).clamp(0.0, 1.0) - 0.5) * 3.0;
        control_margin + contact_margin + arrival_margin + 8.0
    }

    fn contest_band(self) -> f64 {
        (2.2 + 3.8 * self.contact_quality.clamp(0.0, 1.0)).clamp(2.2, 6.0)
    }

    pub fn sample(self, attacker_uniform: f64, goalkeeper_uniform: f64) -> DuelOutcome {
        let margin = self.margin_without_rolls() + goalkeeper_uniform - attacker_uniform;
        let contest_band = self.contest_band();
        if margin > contest_band {
            DuelOutcome::DefenderWins
        } else if margin < -contest_band {
            DuelOutcome::AttackerWins
        } else {
            DuelOutcome::LooseBall
        }
    }

    pub fn probabilities(self) -> DuelOutcomeProbabilities {
        let margin = self.margin_without_rolls();
        let contest_band = self.contest_band();
        let attacker_wins = uniform_difference_cdf(-contest_band - margin, 12.0);
        let defender_wins = 1.0 - uniform_difference_cdf(contest_band - margin, 12.0);
        DuelOutcomeProbabilities {
            attacker_wins,
            defender_wins,
            loose_ball: (1.0 - attacker_wins - defender_wins).max(0.0),
        }
    }

    pub fn margin(self, attacker_uniform: f64, goalkeeper_uniform: f64) -> f64 {
        self.margin_without_rolls() + goalkeeper_uniform - attacker_uniform
    }
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

pub fn duel_margin(input: &DuelResolveInput<'_>) -> f64 {
    assert_ne!(
        input.defender_action, "smother",
        "goalkeeper smothers must not use the outfield duel margin"
    );
    let defender_skill = input.defender_tackling * 0.78 + input.defender_defence * 0.22;
    let skill_margin = (defender_skill - input.attacker_dribbling) * 0.34;
    let contact_margin = (input.contact_quality.clamp(0.0, 1.0) - 0.5) * 12.0;
    let commitment_margin = match input.defender_action {
        "tackle" => 2.2,
        "approach" => -3.4,
        _ => -4.0,
    };
    let release_vulnerability = match input.holder_action {
        "pass" => 2.2,
        "reorient" => 2.4,
        "hold" | "shield" => 1.2,
        _ => 0.0,
    };
    skill_margin
        + contact_margin
        + commitment_margin
        + release_vulnerability
        + input.defender_uniform
        - input.attacker_uniform
}

pub fn duel_contest_margin_band(contact_quality: f64, defender_action: &str) -> f64 {
    let commitment = engagement_profile(defender_action).outcome_commitment;
    (1.5 + 3.5 * contact_quality.clamp(0.0, 1.0) * commitment).clamp(1.5, 5.0)
}

pub fn duel_outcome_code_from_margin(
    margin: f64,
    contact_quality: f64,
    defender_action: &str,
) -> u8 {
    let contest_band = duel_contest_margin_band(contact_quality, defender_action);
    if margin > contest_band {
        1
    } else if margin < -contest_band {
        0
    } else {
        2
    }
}

pub fn resolve_duel(input: &DuelResolveInput<'_>) -> &'static str {
    let margin = duel_margin(input);
    match duel_outcome_code_from_margin(margin, input.contact_quality, input.defender_action) {
        0 => "attacker_wins",
        1 => "defender_wins",
        _ => "loose_ball",
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
    outcome_commitment: f64,
    records_tackle_attempt: bool,
    containment_weight: f64,
    containment_reach_scale: f64,
}

const CONTACT_ENGAGEMENT_PROFILES: [ContactEngagementProfile; 8] = [
    ContactEngagementProfile {
        action: "smother",
        reach_scale: 1.32,
        engagement_weight: 0.92,
        outcome_commitment: 0.94,
        records_tackle_attempt: false,
        containment_weight: 0.88,
        containment_reach_scale: 1.42,
    },
    ContactEngagementProfile {
        action: "tackle",
        reach_scale: 1.08,
        engagement_weight: 0.86,
        outcome_commitment: 1.0,
        records_tackle_attempt: true,
        containment_weight: 0.28,
        containment_reach_scale: 0.95,
    },
    ContactEngagementProfile {
        action: "approach",
        reach_scale: 0.94,
        engagement_weight: 0.36,
        outcome_commitment: 0.56,
        records_tackle_attempt: false,
        containment_weight: 0.46,
        containment_reach_scale: 1.15,
    },
    ContactEngagementProfile {
        action: "close_down",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        outcome_commitment: 0.0,
        records_tackle_attempt: false,
        containment_weight: 0.42,
        containment_reach_scale: 1.20,
    },
    ContactEngagementProfile {
        action: "block_lane",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        outcome_commitment: 0.0,
        records_tackle_attempt: false,
        containment_weight: 0.84,
        containment_reach_scale: 1.28,
    },
    ContactEngagementProfile {
        action: "mark_runner",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        outcome_commitment: 0.0,
        records_tackle_attempt: false,
        containment_weight: 0.60,
        containment_reach_scale: 1.16,
    },
    ContactEngagementProfile {
        action: "pursuit",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        outcome_commitment: 0.0,
        records_tackle_attempt: false,
        containment_weight: 0.38,
        containment_reach_scale: 1.08,
    },
    ContactEngagementProfile {
        action: "hold_position",
        reach_scale: 0.0,
        engagement_weight: 0.0,
        outcome_commitment: 0.0,
        records_tackle_attempt: false,
        containment_weight: 0.34,
        containment_reach_scale: 1.0,
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
            outcome_commitment: 0.0,
            records_tackle_attempt: false,
            containment_weight: 0.0,
            containment_reach_scale: 0.0,
        })
}

pub fn defender_action_physical_reach(tackle_range: f64, action: &str) -> f64 {
    let profile = engagement_profile(action);
    (0.75 + 0.36 * tackle_range.max(0.0)) * profile.reach_scale
}

pub fn records_tackle_attempt(action: &str) -> bool {
    engagement_profile(action).records_tackle_attempt
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

fn moving_circle_first_contact_time(
    left_start: (f64, f64),
    left_end: (f64, f64),
    right_start: (f64, f64),
    right_end: (f64, f64),
    minimum_separation: f64,
) -> Option<f64> {
    let relative_start = (left_start.0 - right_start.0, left_start.1 - right_start.1);
    let relative_velocity = (
        (left_end.0 - left_start.0) - (right_end.0 - right_start.0),
        (left_end.1 - left_start.1) - (right_end.1 - right_start.1),
    );
    let velocity_norm =
        relative_velocity.0 * relative_velocity.0 + relative_velocity.1 * relative_velocity.1;
    if velocity_norm <= 1e-12 {
        return None;
    }
    let radius = minimum_separation.max(0.0);
    let start_clearance =
        relative_start.0 * relative_start.0 + relative_start.1 * relative_start.1 - radius * radius;
    let approach = relative_start.0 * relative_velocity.0 + relative_start.1 * relative_velocity.1;
    if start_clearance <= 0.0 {
        return (approach < 0.0).then_some(0.0);
    }
    let discriminant = approach * approach - velocity_norm * start_clearance;
    if discriminant < 0.0 {
        return None;
    }
    let contact_time = (-approach - discriminant.sqrt()) / velocity_norm;
    (contact_time >= 0.0 && contact_time <= 1.0).then_some(contact_time)
}

pub fn carrier_body_collision_position(
    carrier_start: (f64, f64),
    carrier_end: (f64, f64),
    defenders: &[DefenderActionInput],
) -> (f64, f64) {
    let carrier_delta = (
        carrier_end.0 - carrier_start.0,
        carrier_end.1 - carrier_start.1,
    );
    let carrier_distance =
        (carrier_delta.0 * carrier_delta.0 + carrier_delta.1 * carrier_delta.1).sqrt();
    if carrier_distance <= 1e-9 {
        return carrier_end;
    }
    let carrier_direction = (
        carrier_delta.0 / carrier_distance,
        carrier_delta.1 / carrier_distance,
    );
    let mut first_contact_time: f64 = 1.0;
    for defender in defenders {
        let Some(contact_time) = moving_circle_first_contact_time(
            carrier_start,
            carrier_end,
            defender.pos,
            defender.new_pos,
            PLAYER_BODY_SEPARATION,
        ) else {
            continue;
        };
        let carrier_at_contact = (
            carrier_start.0 + carrier_delta.0 * contact_time,
            carrier_start.1 + carrier_delta.1 * contact_time,
        );
        let defender_at_contact = (
            defender.pos.0 + (defender.new_pos.0 - defender.pos.0) * contact_time,
            defender.pos.1 + (defender.new_pos.1 - defender.pos.1) * contact_time,
        );
        let defender_forward_offset = (defender_at_contact.0 - carrier_at_contact.0)
            * carrier_direction.0
            + (defender_at_contact.1 - carrier_at_contact.1) * carrier_direction.1;
        if defender_forward_offset >= -1e-9 {
            first_contact_time = first_contact_time.min(contact_time);
        }
    }
    (
        carrier_start.0 + carrier_delta.0 * first_contact_time,
        carrier_start.1 + carrier_delta.1 * first_contact_time,
    )
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
    let intervention_timing = if defender.is_goalkeeper && defender.action == "smother" {
        0.55 * defender.gk_positioning + 0.45 * defender.gk_reaction
    } else {
        defender.defence
    };
    let intervention_control = if defender.is_goalkeeper && defender.action == "smother" {
        defender.gk_saving
    } else {
        defender.defence
    };
    let anticipation = 0.68
        + 0.18 * (defender.speed / 100.0).clamp(0.0, 1.0)
        + 0.14 * (intervention_timing / 100.0).clamp(0.0, 1.0);
    let probability =
        (profile.containment_weight * corridor_occupation * forward_coverage * anticipation)
            .clamp(0.0, 0.98);
    let control_gap = 0.52
        + 0.42 * (intervention_control / 100.0).clamp(0.0, 1.0)
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

pub fn control_interference_probability(
    control_pos: (f64, f64),
    defenders: &[DefenderActionInput],
) -> f64 {
    let mut no_interference_probability = 1.0;
    for defender in defenders {
        let profile = engagement_profile(defender.action);
        if profile.containment_weight <= 0.0 {
            continue;
        }
        let defender_pos = defender.new_pos;
        let separation = distance(control_pos, defender_pos);
        let interference_radius = PLAYER_BODY_SEPARATION + 3.60 * profile.containment_reach_scale;
        let spatial_occupation = 1.0
            - smoothstep(
                PLAYER_BODY_SEPARATION * 0.72,
                interference_radius,
                separation,
            );
        let intervention_reading = if defender.is_goalkeeper && defender.action == "smother" {
            0.55 * defender.gk_positioning + 0.45 * defender.gk_reaction
        } else {
            defender.defence
        };
        let ability = 0.60
            + 0.22 * (intervention_reading / 100.0).clamp(0.0, 1.0)
            + 0.18 * (defender.speed / 100.0).clamp(0.0, 1.0);
        let action_presence = 0.30 + 0.70 * profile.containment_weight;
        let probability = (spatial_occupation * ability * action_presence).clamp(0.0, 0.90);
        no_interference_probability *= 1.0 - probability;
    }
    (1.0 - no_interference_probability).clamp(0.0, 1.0)
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

fn canonical_duel_holder_action(holder_action: &str) -> &'static str {
    match holder_action {
        "carry" => "carry",
        "pass" => "pass",
        "reorient" => "reorient",
        "hold" | "shield" => "hold",
        _ => panic!("unsupported duel holder action: {holder_action}"),
    }
}

fn duel_outcome_probabilities(
    attacker_dribbling: f64,
    defender: &DefenderActionInput,
    holder_action: &str,
    contact_quality: f64,
) -> (f64, f64, f64) {
    let probabilities = if defender.is_goalkeeper && defender.action == "smother" {
        GoalkeeperSmotherTransition::new(attacker_dribbling, *defender, contact_quality)
            .probabilities()
    } else {
        DuelOutcomeTransition::new(
            attacker_dribbling,
            *defender,
            canonical_duel_holder_action(holder_action),
            contact_quality,
        )
        .probabilities()
    };
    (
        probabilities.attacker_wins,
        probabilities.defender_wins,
        probabilities.loose_ball,
    )
}

pub fn control_contact_transition(
    holder_pos: (f64, f64),
    holder_action: &str,
    control_target: (f64, f64),
    control_step_distance: f64,
    attacker_dribbling: f64,
    defenders: &[DefenderActionInput],
    tackle_range: f64,
) -> ControlContactTransition {
    let contact = detect_duel(&DuelDetectionInput {
        holder_pos,
        holder_action,
        carry_target: control_target,
        carrier_step_distance: control_step_distance,
        defenders,
        tackle_range,
    });
    let Some(defender) = contact.defender_index.and_then(|defender_index| {
        defenders
            .iter()
            .find(|defender| defender.index == defender_index)
    }) else {
        return ControlContactTransition {
            contact,
            retained_probability: 1.0,
            opposing_control_probability: 0.0,
            unresolved_probability: 0.0,
        };
    };
    let (_, defender_wins, loose_ball) = duel_outcome_probabilities(
        attacker_dribbling,
        defender,
        holder_action,
        contact.contact_quality,
    );
    let contact_probability = contact.contact_probability.clamp(0.0, 1.0);
    let opposing_control_probability = contact_probability * defender_wins;
    let unresolved_probability = contact_probability * loose_ball;
    ControlContactTransition {
        contact,
        retained_probability: (1.0 - opposing_control_probability - unresolved_probability)
            .clamp(0.0, 1.0),
        opposing_control_probability,
        unresolved_probability,
    }
}

pub fn carry_contact_transition(
    holder_pos: (f64, f64),
    carry_target: (f64, f64),
    carrier_step_distance: f64,
    attacker_dribbling: f64,
    defenders: &[DefenderActionInput],
    tackle_range: f64,
) -> ControlContactTransition {
    control_contact_transition(
        holder_pos,
        "carry",
        carry_target,
        carrier_step_distance,
        attacker_dribbling,
        defenders,
        tackle_range,
    )
}

pub fn pass_release_contact_transition(
    holder_pos: (f64, f64),
    pass_target: (f64, f64),
    release_step_distance: f64,
    attacker_dribbling: f64,
    defenders: &[DefenderActionInput],
    tackle_range: f64,
) -> PassReleaseContactTransition {
    let contact = detect_duel(&DuelDetectionInput {
        holder_pos,
        holder_action: "pass",
        carry_target: pass_target,
        carrier_step_distance: release_step_distance,
        defenders,
        tackle_range,
    });
    let Some(defender) = contact.defender_index.and_then(|defender_index| {
        defenders
            .iter()
            .find(|defender| defender.index == defender_index)
    }) else {
        return PassReleaseContactTransition {
            contact,
            released_probability: 1.0,
            opposing_control_probability: 0.0,
            unresolved_probability: 0.0,
        };
    };
    let (_, defender_wins, loose_ball) = duel_outcome_probabilities(
        attacker_dribbling,
        defender,
        "pass",
        contact.contact_quality,
    );
    let contact_probability = contact.contact_probability.clamp(0.0, 1.0);
    let opposing_control_probability = contact_probability * defender_wins;
    let unresolved_probability = contact_probability * loose_ball;
    PassReleaseContactTransition {
        contact,
        released_probability: (1.0 - opposing_control_probability - unresolved_probability)
            .clamp(0.0, 1.0),
        opposing_control_probability,
        unresolved_probability,
    }
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
                gk_saving: defender.gk_saving,
                gk_positioning: defender.gk_positioning,
                gk_reaction: defender.gk_reaction,
                is_goalkeeper: defender.is_goalkeeper,
            }
        })
        .collect()
}

pub fn detect_duel(input: &DuelDetectionInput<'_>) -> DetectionResult {
    let base_exposure: f64 = match input.holder_action {
        "carry" | "dribble" => 1.0,
        "hold" | "shield" => 0.68,
        "reorient" => 0.58,
        "pass" => 0.42,
        _ => 0.0,
    };
    if base_exposure <= 0.0 {
        return DetectionResult {
            defender_index: None,
            distance: 0.0,
            contact_probability: 0.0,
            contact_quality: 0.0,
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
        contact_quality: 0.0,
    };
    for defender in input.defenders {
        let profile = engagement_profile(defender.action);
        if profile.engagement_weight <= 0.0 {
            continue;
        }
        let physical_reach = defender_action_physical_reach(input.tackle_range, defender.action);
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
        let intervention_timing = if defender.is_goalkeeper && defender.action == "smother" {
            0.55 * defender.gk_positioning + 0.45 * defender.gk_reaction
        } else {
            defender.defence
        };
        let defensive_timing = 0.76 + 0.24 * (intervention_timing / 100.0).clamp(0.0, 1.0);
        let exposure_multiplier = if defender.action == "tackle" {
            base_exposure.max(0.78)
        } else {
            base_exposure
        };
        let contact_probability = (exposure_multiplier
            * profile.engagement_weight
            * (0.18 + 0.82 * proximity)
            * (0.70 + 0.30 * convergence)
            * speed_factor
            * defensive_timing)
            .clamp(0.0, 0.95);
        let contact_quality = ((0.18 + 0.58 * proximity + 0.24 * convergence)
            * (0.54 + 0.46 * profile.outcome_commitment))
            .clamp(0.0, 1.0);
        if contact_probability > best_contact.contact_probability {
            best_contact = DetectionResult {
                defender_index: Some(defender.index),
                distance: closest_distance,
                contact_probability,
                contact_quality,
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
        let contact = carry_contact_transition(
            holder_pos,
            input.carry_target,
            step_distance,
            input.attacker_dribbling,
            &projected_defenders,
            input.tackle_range,
        );
        peak_contact_probability =
            peak_contact_probability.max(contact.contact.contact_probability);
        let entering_probability = unconstrained_control_probability;
        let opposing_increment = entering_probability * contact.opposing_control_probability;
        let unresolved_increment = entering_probability * contact.unresolved_probability;
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
                .find(|defender| Some(defender.index) == contact.contact.defender_index)
                .map(|defender| defender.pos.0)
                .unwrap_or(carrier_end.0);
        weighted_opposing_position.1 += opposing_increment
            * projected_defenders
                .iter()
                .find(|defender| Some(defender.index) == contact.contact.defender_index)
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
                contact_quality: 0.0,
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
            contact_quality: 0.0,
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
                contact_quality: 0.0,
            };
        }
    }
    DetectionResult {
        defender_index: None,
        distance: 0.0,
        contact_probability: 0.0,
        contact_quality: 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        carrier_body_collision_position, carry_containment_transition, carry_survival_transition,
        carry_survival_transition_with_defender_responses, control_interference_probability,
        detect_duel, duel_outcome_probabilities, pass_release_contact_transition, resolve_duel,
        track_defensive_pressures, track_defensive_pressures_into, CarryContainmentInput,
        CarrySurvivalInput, DefenderActionInput, DefensivePressureInput, DuelDetectionInput,
        DuelOutcome, DuelResolveInput, GoalkeeperSmotherTransition, PLAYER_BODY_SEPARATION,
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
            gk_saving: 0.0,
            gk_positioning: 0.0,
            gk_reaction: 0.0,
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
    fn high_quality_tackle_can_dispossess_a_strong_dribbler_at_pass_release() {
        let outcome = resolve_duel(&DuelResolveInput {
            attacker_dribbling: 105.0,
            defender_tackling: 86.0,
            defender_defence: 83.0,
            holder_action: "pass",
            defender_action: "tackle",
            contact_quality: 1.0,
            attacker_uniform: 0.0,
            defender_uniform: 6.0,
        });

        assert_eq!(
            outcome, "defender_wins",
            "a committed, well-timed tackle during the exposed pass release must retain a meaningful defensive outcome against elite dribbling"
        );
    }

    #[test]
    fn committed_tackle_keeps_a_contact_window_during_pass_release() {
        let defender = defender(1, (0.0, 0.0), (0.2, 0.0), "tackle");
        let pass_contact = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "pass",
            carry_target: (12.0, 0.0),
            carrier_step_distance: 0.5,
            defenders: &[defender],
            tackle_range: 6.0,
        });

        assert_eq!(pass_contact.defender_index, Some(1));
        assert!(
            pass_contact.contact_probability >= 0.40,
            "a committed tackle already in contact must challenge a pass release instead of being suppressed by the generic pass exposure factor: {pass_contact:?}"
        );
    }

    #[test]
    fn poor_contact_does_not_turn_attribute_advantage_into_an_instant_tackle() {
        let poor_contact = resolve_duel(&DuelResolveInput {
            attacker_dribbling: 70.0,
            defender_tackling: 100.0,
            defender_defence: 100.0,
            holder_action: "carry",
            defender_action: "approach",
            contact_quality: 0.0,
            attacker_uniform: 0.0,
            defender_uniform: 0.0,
        });
        let committed_contact = resolve_duel(&DuelResolveInput {
            attacker_dribbling: 70.0,
            defender_tackling: 100.0,
            defender_defence: 100.0,
            holder_action: "carry",
            defender_action: "tackle",
            contact_quality: 1.0,
            attacker_uniform: 0.0,
            defender_uniform: 0.0,
        });

        assert_eq!(poor_contact, "loose_ball");
        assert_eq!(committed_contact, "defender_wins");
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
    fn positioned_defenders_create_a_distance_decaying_carry_interference_field() {
        let near = [defender(3, (3.0, 1.4), (3.0, 1.4), "hold_position")];
        let far = [defender(3, (3.0, 5.5), (3.0, 5.5), "hold_position")];
        let near_field = carry_containment_transition(&CarryContainmentInput {
            holder_pos: (0.0, 0.0),
            carrier_end: (6.0, 0.0),
            defenders: &near,
        });
        let far_field = carry_containment_transition(&CarryContainmentInput {
            holder_pos: (0.0, 0.0),
            carrier_end: (6.0, 0.0),
            defenders: &far,
        });

        assert!(near_field.constrained_control_probability > 0.0);
        assert!(
            near_field.constrained_control_probability > far_field.constrained_control_probability
        );
    }

    #[test]
    fn multiple_defender_interference_fields_combine_with_diminishing_returns() {
        let left = defender(3, (3.0, -1.5), (3.0, -1.2), "block_lane");
        let right = defender(4, (3.0, 1.5), (3.0, 1.2), "block_lane");
        let single = carry_containment_transition(&CarryContainmentInput {
            holder_pos: (0.0, 0.0),
            carrier_end: (6.0, 0.0),
            defenders: &[left],
        });
        let double = carry_containment_transition(&CarryContainmentInput {
            holder_pos: (0.0, 0.0),
            carrier_end: (6.0, 0.0),
            defenders: &[left, right],
        });

        assert!(double.constrained_control_probability > single.constrained_control_probability);
        assert!(
            double.constrained_control_probability < 2.0 * single.constrained_control_probability
        );
        assert!(double.constrained_control_probability < 1.0);
    }

    #[test]
    fn reception_interference_is_distance_decaying_and_combines_with_diminishing_returns() {
        let left = defender(3, (40.0, 32.7), (40.0, 32.7), "mark_runner");
        let right = defender(4, (40.0, 35.3), (40.0, 35.3), "mark_runner");
        let outer_field = defender(5, (40.0, 38.2), (40.0, 38.2), "hold_position");
        let far = defender(6, (40.0, 40.0), (40.0, 40.0), "hold_position");
        let single = control_interference_probability((40.0, 34.0), &[left]);
        let double = control_interference_probability((40.0, 34.0), &[left, right]);
        let outer = control_interference_probability((40.0, 34.0), &[outer_field]);
        let distant = control_interference_probability((40.0, 34.0), &[far]);

        assert!(outer > 0.0);
        assert!(single > distant);
        assert!(outer > distant);
        assert!(double > single);
        assert!(double < 2.0 * single);
        assert!(double < 1.0);
    }

    #[test]
    fn body_occupation_stops_a_carrier_before_a_stationary_defender() {
        let defenders = [defender(3, (3.0, 0.0), (3.0, 0.0), "hold_position")];

        let blocked_position = carrier_body_collision_position((0.0, 0.0), (5.0, 0.0), &defenders);

        assert!((blocked_position.0 - (3.0 - PLAYER_BODY_SEPARATION)).abs() <= 1e-9);
        assert_eq!(blocked_position.1, 0.0);
    }

    #[test]
    fn swept_body_collision_detects_crossing_paths_between_tick_endpoints() {
        let defenders = [defender(4, (2.5, 2.0), (2.5, -2.0), "hold_position")];

        let blocked_position = carrier_body_collision_position((0.0, 0.0), (5.0, 0.0), &defenders);

        assert!(
            blocked_position.0 < 2.5,
            "continuous collision detection must stop paths that intersect mid-tick even when both endpoints are clear"
        );
        assert_eq!(blocked_position.1, 0.0);
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
    fn pass_release_has_a_short_contact_window_only_for_engaging_defenders() {
        let tackler = [defender(5, (2.5, 1.2), (1.8, 0.3), "tackle")];
        let pass = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "pass",
            carry_target: (12.0, 0.0),
            carrier_step_distance: 0.55,
            defenders: &tackler,
            tackle_range: 6.0,
        });
        let carry = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "carry",
            carry_target: (12.0, 0.0),
            carrier_step_distance: 0.55,
            defenders: &tackler,
            tackle_range: 6.0,
        });
        let close_down = [defender(6, (2.5, 1.2), (1.8, 0.3), "close_down")];
        let containment_only = detect_duel(&DuelDetectionInput {
            holder_pos: (0.0, 0.0),
            holder_action: "pass",
            carry_target: (12.0, 0.0),
            carrier_step_distance: 0.55,
            defenders: &close_down,
            tackle_range: 6.0,
        });

        assert_eq!(pass.defender_index, Some(5));
        assert!(pass.contact_probability > 0.0);
        assert!(pass.contact_probability < carry.contact_probability);
        assert_eq!(containment_only.defender_index, None);
        assert_eq!(containment_only.contact_probability, 0.0);
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
    fn goalkeeper_smother_contests_a_carry_and_preserves_probability_mass() {
        let goalkeeper = [DefenderActionInput {
            index: 1,
            pos: (102.65, 35.24),
            new_pos: (101.75, 34.45),
            action: "smother",
            speed: 82.0,
            defence: 84.0,
            tackling: 78.0,
            gk_saving: 78.0,
            gk_positioning: 84.0,
            gk_reaction: 86.0,
            is_goalkeeper: true,
        }];
        let transition = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (99.77, 30.74),
            carry_target: (104.5, 37.12),
            carrier_step_distance: 3.0,
            attacker_dribbling: 88.0,
            defenders: &goalkeeper,
            tackle_range: 6.0,
            segment_count: 2,
        });
        let probability_mass = transition.retained_control_probability
            + transition.opposing_control_probability
            + transition.unresolved_probability;
        let mut unrelated_outfield_attributes = goalkeeper;
        unrelated_outfield_attributes[0].tackling = 1.0;
        unrelated_outfield_attributes[0].defence = 1.0;
        let unchanged_transition = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (99.77, 30.74),
            carry_target: (104.5, 37.12),
            carrier_step_distance: 3.0,
            attacker_dribbling: 88.0,
            defenders: &unrelated_outfield_attributes,
            tackle_range: 6.0,
            segment_count: 2,
        });

        assert!((probability_mass - 1.0).abs() < 1e-9);
        assert_eq!(
            transition.retained_control_probability,
            unchanged_transition.retained_control_probability
        );
        assert_eq!(
            transition.opposing_control_probability,
            unchanged_transition.opposing_control_probability
        );
        assert_eq!(
            transition.unresolved_probability,
            unchanged_transition.unresolved_probability
        );
        assert_eq!(
            transition.peak_contact_probability,
            unchanged_transition.peak_contact_probability
        );
        assert_eq!(
            transition.peak_containment_probability,
            unchanged_transition.peak_containment_probability
        );
        assert!(transition.peak_contact_probability > 0.0);
        assert!(transition.peak_containment_probability > 0.0);
        assert!(transition.retained_control_probability < 1.0);
        assert!(transition.opposing_control_probability > 0.0);
        assert!(crate::distance(transition.constrained_control_position, (104.5, 37.12)) > 0.5);
        let contact_quality = transition.peak_contact_probability;
        let baseline = duel_outcome_probabilities(88.0, &goalkeeper[0], "carry", contact_quality);
        let unrelated_outfield_attributes = unrelated_outfield_attributes[0];
        let unchanged = duel_outcome_probabilities(
            88.0,
            &unrelated_outfield_attributes,
            "carry",
            contact_quality,
        );
        assert_eq!(baseline, unchanged);
    }

    #[test]
    fn goalkeeper_smother_dominates_a_carry_started_inside_hand_control_range() {
        let goalkeeper = [DefenderActionInput {
            index: 0,
            pos: (102.23435314992551, 33.907401995425786),
            new_pos: (101.40816367949262, 34.461003364433864),
            action: "smother",
            speed: 37.0,
            defence: 84.9,
            tackling: 80.0,
            gk_saving: 80.0,
            gk_positioning: 84.0,
            gk_reaction: 86.0,
            is_goalkeeper: true,
        }];
        let transition = carry_survival_transition(&CarrySurvivalInput {
            holder_pos: (101.2480674577346, 34.50490559332317),
            carry_target: (106.0, 33.20181156745394),
            carrier_step_distance: 6.0,
            attacker_dribbling: 106.0,
            defenders: &goalkeeper,
            tackle_range: 6.0,
            segment_count: 1,
        });

        assert!(
            transition.unconstrained_control_probability < 0.25,
            "a keeper already within hand-control range must usually stop the carrier before the goal line: {transition:?}"
        );
        assert!(
            transition.opposing_control_probability > transition.unconstrained_control_probability,
            "close frontal smothering should favor goalkeeper control over an untouched carry: {transition:?}"
        );
    }

    #[test]
    fn goalkeeper_smother_probabilities_match_live_sampling_and_ignore_tackle_attributes() {
        let mut goalkeeper = DefenderActionInput {
            index: 0,
            pos: (102.2, 34.0),
            new_pos: (101.2, 34.0),
            action: "smother",
            speed: 82.0,
            defence: 12.0,
            tackling: 8.0,
            gk_saving: 86.0,
            gk_positioning: 84.0,
            gk_reaction: 88.0,
            is_goalkeeper: true,
        };
        let transition = GoalkeeperSmotherTransition::new(92.0, goalkeeper, 0.76);
        let expected = transition.probabilities();
        goalkeeper.defence = 99.0;
        goalkeeper.tackling = 99.0;
        let unchanged = GoalkeeperSmotherTransition::new(92.0, goalkeeper, 0.76).probabilities();
        assert_eq!(expected.attacker_wins, unchanged.attacker_wins);
        assert_eq!(expected.defender_wins, unchanged.defender_wins);
        assert_eq!(expected.loose_ball, unchanged.loose_ball);

        let samples = 401usize;
        let mut attacker_wins = 0usize;
        let mut defender_wins = 0usize;
        let mut loose = 0usize;
        for attacker_index in 0..samples {
            for goalkeeper_index in 0..samples {
                let attacker_uniform =
                    -12.0 + 24.0 * (attacker_index as f64 + 0.5) / samples as f64;
                let goalkeeper_uniform =
                    -12.0 + 24.0 * (goalkeeper_index as f64 + 0.5) / samples as f64;
                match transition.sample(attacker_uniform, goalkeeper_uniform) {
                    DuelOutcome::AttackerWins => attacker_wins += 1,
                    DuelOutcome::DefenderWins => defender_wins += 1,
                    DuelOutcome::LooseBall => loose += 1,
                }
            }
        }
        let total = (samples * samples) as f64;
        assert!((attacker_wins as f64 / total - expected.attacker_wins).abs() < 0.003);
        assert!((defender_wins as f64 / total - expected.defender_wins).abs() < 0.003);
        assert!((loose as f64 / total - expected.loose_ball).abs() < 0.003);
    }

    #[test]
    fn analytical_duel_probabilities_match_the_live_uniform_resolution_grid() {
        let defender = DefenderActionInput {
            index: 0,
            pos: (1.0, 0.0),
            new_pos: (0.5, 0.0),
            action: "tackle",
            speed: 78.0,
            defence: 82.0,
            tackling: 86.0,
            gk_saving: 0.0,
            gk_positioning: 0.0,
            gk_reaction: 0.0,
            is_goalkeeper: false,
        };
        let contact_quality = 0.72;
        let expected = duel_outcome_probabilities(79.0, &defender, "carry", contact_quality);
        let samples = 401usize;
        let mut attacker_wins = 0usize;
        let mut defender_wins = 0usize;
        let mut loose = 0usize;
        for attacker_index in 0..samples {
            for defender_index in 0..samples {
                let attacker_uniform =
                    -12.0 + 24.0 * (attacker_index as f64 + 0.5) / samples as f64;
                let defender_uniform =
                    -12.0 + 24.0 * (defender_index as f64 + 0.5) / samples as f64;
                match resolve_duel(&DuelResolveInput {
                    attacker_dribbling: 79.0,
                    defender_tackling: defender.tackling,
                    defender_defence: defender.defence,
                    holder_action: "carry",
                    defender_action: defender.action,
                    contact_quality,
                    attacker_uniform,
                    defender_uniform,
                }) {
                    "attacker_wins" => attacker_wins += 1,
                    "defender_wins" => defender_wins += 1,
                    _ => loose += 1,
                }
            }
        }
        let total = (samples * samples) as f64;
        let observed = (
            attacker_wins as f64 / total,
            defender_wins as f64 / total,
            loose as f64 / total,
        );

        assert!((observed.0 - expected.0).abs() < 0.003);
        assert!((observed.1 - expected.1).abs() < 0.003);
        assert!((observed.2 - expected.2).abs() < 0.003);
    }

    #[test]
    fn pass_release_transition_matches_live_contact_and_duel_sampling_grid() {
        let defender = DefenderActionInput {
            index: 3,
            pos: (0.8, 0.2),
            new_pos: (0.2, 0.0),
            action: "tackle",
            speed: 81.0,
            defence: 84.0,
            tackling: 87.0,
            gk_saving: 0.0,
            gk_positioning: 0.0,
            gk_reaction: 0.0,
            is_goalkeeper: false,
        };
        let transition =
            pass_release_contact_transition((0.0, 0.0), (12.0, 1.0), 0.54, 78.0, &[defender], 6.0);
        let samples = 121usize;
        let mut released = 0usize;
        let mut opposing = 0usize;
        let mut unresolved = 0usize;
        for contact_index in 0..samples {
            let contact_roll = (contact_index as f64 + 0.5) / samples as f64;
            for attacker_index in 0..samples {
                let attacker_uniform =
                    -12.0 + 24.0 * (attacker_index as f64 + 0.5) / samples as f64;
                for defender_index in 0..samples {
                    let defender_uniform =
                        -12.0 + 24.0 * (defender_index as f64 + 0.5) / samples as f64;
                    if contact_roll >= transition.contact.contact_probability {
                        released += 1;
                        continue;
                    }
                    match resolve_duel(&DuelResolveInput {
                        attacker_dribbling: 78.0,
                        defender_tackling: defender.tackling,
                        defender_defence: defender.defence,
                        holder_action: "pass",
                        defender_action: defender.action,
                        contact_quality: transition.contact.contact_quality,
                        attacker_uniform,
                        defender_uniform,
                    }) {
                        "attacker_wins" => released += 1,
                        "defender_wins" => opposing += 1,
                        _ => unresolved += 1,
                    }
                }
            }
        }
        let total = samples.pow(3) as f64;
        let observed = (
            released as f64 / total,
            opposing as f64 / total,
            unresolved as f64 / total,
        );

        assert!((observed.0 - transition.released_probability).abs() < 0.006);
        assert!((observed.1 - transition.opposing_control_probability).abs() < 0.006);
        assert!((observed.2 - transition.unresolved_probability).abs() < 0.006);
        assert!(
            (transition.released_probability
                + transition.opposing_control_probability
                + transition.unresolved_probability
                - 1.0)
                .abs()
                < 1e-9
        );
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
                duration_seconds: 2.0,
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
