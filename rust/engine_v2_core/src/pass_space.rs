use std::collections::HashSet;

use crate::offside::is_offside_position;
use crate::pass_value::{expected_pass_value, ExpectedPassInput};
use crate::physics::distance;
use crate::position_value::{position_value, PositionValueInput};
use crate::shot_quality::ShotQualityCache;
use crate::vision::VisionContext;

#[derive(Clone, Copy, Debug)]
pub struct PassSpacePlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub is_goalkeeper: bool,
    pub is_defender: bool,
    pub is_midfielder: bool,
    pub is_wide: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct GenericPassSpaceCandidate {
    pub score: f64,
    pub target: (f64, f64),
    pub visibility: f64,
    pub position_value: f64,
}

#[derive(Debug)]
pub struct GenericPassSpaceInput<'a> {
    pub passer_index: usize,
    pub passer_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub vision: VisionContext,
    pub teammates: &'a [PassSpacePlayer],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverGoalInput<'a> {
    pub goal_type: &'a str,
    pub target_pos: (f64, f64),
    pub value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassTarget {
    pub target: (f64, f64),
    pub arrival: f64,
}

#[derive(Clone, Copy, Debug)]
struct RawPassTargetMeta {
    target: (f64, f64),
    arrival: f64,
    tactical_space: bool,
    tactical_space_prior: f64,
    tactical_space_value: f64,
    tactical_space_visibility: f64,
    expected_arrival_confidence: f64,
    expected_arrival_fit: f64,
}

impl From<RawPassTarget> for RawPassTargetMeta {
    fn from(value: RawPassTarget) -> Self {
        Self {
            target: value.target,
            arrival: value.arrival,
            tactical_space: false,
            tactical_space_prior: 0.0,
            tactical_space_value: 0.0,
            tactical_space_visibility: 0.0,
            expected_arrival_confidence: 0.0,
            expected_arrival_fit: 0.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct ReceiverBaseTargetsOutput {
    pub targets: Vec<RawPassTarget>,
    pub receiver_visibility: f64,
    pub target_visibility: f64,
    pub low_visibility: bool,
    pub receiver_goal_fit: f64,
}

#[derive(Debug)]
pub struct ReceiverBaseTargetsInput<'a> {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub receiver_goal: Option<ReceiverGoalInput<'a>>,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ValueFieldRawTarget {
    pub target: (f64, f64),
    pub arrival: f64,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

#[derive(Debug)]
pub struct ValueFieldTargetsInput<'a> {
    pub receiver: PassSpacePlayer,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub is_defender: bool,
    pub generic_candidates: &'a [GenericPassSpaceCandidate],
}

#[derive(Debug)]
pub struct StaleReleaseTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub consecutive_carries: i32,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct LayoffTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct SecondLineTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub receiver_base: (f64, f64),
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct BoxDeliveryTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct DeliverySpaceTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverSpatialCandidate {
    pub score: f64,
    pub target: (f64, f64),
    pub receiver_arrival: f64,
    pub position_value: f64,
    pub point_visibility: f64,
}

#[derive(Debug)]
pub struct ReceiverSpatialCandidatesInput<'a> {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub low_visibility: bool,
    pub front_center: Option<(f64, f64)>,
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct PassRiskPlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub speed: i32,
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassPreValueInput<'a> {
    pub passer_index: usize,
    pub passer_pos: (f64, f64),
    pub receiver: PassRiskPlayer,
    pub target: (f64, f64),
    pub initial_receiver_arrival: f64,
    pub receiver_visibility: f64,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
    pub receiver_goal_fit: f64,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_passing: f64,
    pub long_passing: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub opponents: &'a [PassRiskPlayer],
    pub teammates: &'a [PassRiskPlayer],
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassPreValueOutput {
    pub valid: bool,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub continuity: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub receiver_time: f64,
    pub defender_time: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
}

#[derive(Debug)]
pub struct RawPassValueInput<'a> {
    pub prevalue: RawPassPreValueInput<'a>,
    pub tick: i32,
    pub passer_team_home: bool,
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
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub current_value: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassValueOutput {
    pub valid: bool,
    pub score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
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
    pub adjusted_score: f64,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverPassCandidate {
    pub target: (f64, f64),
    pub score: f64,
    pub raw_score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
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
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub tactical_space: bool,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

#[derive(Debug)]
pub struct ReceiverPassBatchInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_short_passing: f64,
    pub passer_long_passing: f64,
    pub passer_consecutive_carries: i32,
    pub receiver_space: PassSpacePlayer,
    pub receiver_risk: PassRiskPlayer,
    pub receiver_index: usize,
    pub receiver_team_home: bool,
    pub receiver_finishing: f64,
    pub receiver_long_shot: f64,
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub receiver_goal: Option<ReceiverGoalInput<'a>>,
    pub is_receiver_defender: bool,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub current_value: f64,
    pub front_center: Option<(f64, f64)>,
    pub generic_candidates: &'a [GenericPassSpaceCandidate],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub teammate_xy_positions: &'a [(f64, f64)],
    pub risk_opponents: &'a [PassRiskPlayer],
    pub risk_teammates: &'a [PassRiskPlayer],
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Clone, Copy, Debug)]
pub struct PassTeamPlayer<'a> {
    pub space: PassSpacePlayer,
    pub risk: PassRiskPlayer,
    pub finishing: f64,
    pub long_shot: f64,
    pub base: (f64, f64),
    pub is_defender: bool,
    pub goal: Option<ReceiverGoalInput<'a>>,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPassCandidate {
    pub receiver_index: usize,
    pub target: (f64, f64),
    pub score: f64,
    pub raw_score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
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
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub tactical_space: bool,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

#[derive(Debug)]
pub struct TeamPassBatchInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_short_passing: f64,
    pub passer_long_passing: f64,
    pub passer_consecutive_carries: i32,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub current_value: f64,
    pub players: &'a [PassTeamPlayer<'a>],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions_for_value: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices_for_value: &'a [usize],
    pub teammate_xy_positions: &'a [(f64, f64)],
    pub risk_opponents: &'a [PassRiskPlayer],
    pub risk_teammates: &'a [PassRiskPlayer],
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

fn dedupe_key(pos: (f64, f64)) -> (i64, i64) {
    ((pos.0 * 10.0).round() as i64, (pos.1 * 10.0).round() as i64)
}

pub fn generic_pass_space_candidates(
    input: &GenericPassSpaceInput<'_>,
) -> Vec<GenericPassSpaceCandidate> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let mut front_anchors = Vec::new();
    for tm in input.teammates {
        if tm.index == input.passer_index || tm.is_goalkeeper {
            continue;
        }
        let anchor_progress = if input.attacking_right {
            tm.tactical_anchor.0 / input.pitch_length
        } else {
            (input.pitch_length - tm.tactical_anchor.0) / input.pitch_length
        };
        if anchor_progress > 0.58 {
            front_anchors.push(tm.tactical_anchor);
        }
    }

    let mut generic_centers = vec![input.passer_pos];
    if !front_anchors.is_empty() {
        generic_centers.push((
            front_anchors.iter().map(|pos| pos.0).sum::<f64>() / front_anchors.len() as f64,
            front_anchors.iter().map(|pos| pos.1).sum::<f64>() / front_anchors.len() as f64,
        ));
    }

    let visible_anchors: Vec<(f64, f64)> = input
        .teammates
        .iter()
        .filter(|tm| tm.index != input.passer_index && !tm.is_goalkeeper)
        .filter(|tm| {
            input
                .vision
                .confidence(input.passer_pos, tm.tactical_anchor)
                > 0.0
        })
        .map(|tm| tm.tactical_anchor)
        .collect();
    if !visible_anchors.is_empty() {
        generic_centers.push((
            visible_anchors.iter().map(|pos| pos.0).sum::<f64>() / visible_anchors.len() as f64,
            visible_anchors.iter().map(|pos| pos.1).sum::<f64>() / visible_anchors.len() as f64,
        ));
    }

    let mut seen = HashSet::new();
    let mut candidates = Vec::new();
    for center in generic_centers {
        for radius in [8.0, 16.0, 28.0, 40.0] {
            for angle_deg in [
                -150.0_f64, -105.0, -60.0, -25.0, 0.0, 25.0, 60.0, 105.0, 150.0,
            ] {
                let angle = angle_deg.to_radians();
                let target = pitch_clamp(
                    (
                        center.0 + angle.cos() * radius * forward_dir,
                        center.1 + angle.sin() * radius,
                    ),
                    input.pitch_length,
                    input.pitch_width,
                );
                let key = dedupe_key(target);
                if seen.contains(&key) {
                    continue;
                }
                seen.insert(key);

                let visibility = input.vision.confidence(input.passer_pos, target);
                if visibility <= 0.0 {
                    continue;
                }
                if is_offside_position(
                    target,
                    input.attacking_right,
                    input.offside_line,
                    input.pitch_length,
                    Some(input.passer_pos.0),
                ) {
                    continue;
                }
                let pass_distance = distance(input.passer_pos, target);
                if pass_distance < 6.0 || pass_distance > 55.0 {
                    continue;
                }
                let pv = position_value(&PositionValueInput {
                    x: target.0,
                    y: target.1,
                    pitch_length: input.pitch_length,
                    pitch_width: input.pitch_width,
                    attacking_right: input.attacking_right,
                    opponent_positions: input.opponent_positions,
                    teammate_positions: input.teammate_positions,
                    runner_formation_pos: None,
                });
                let forward_gain = ((target.0 - input.passer_pos.0) * forward_dir).max(0.0)
                    / input.pitch_length.max(1.0);
                let distance_fit = 1.0 - (pass_distance - 34.0).max(0.0) / 30.0;
                let score = pv
                    * (0.45 + 0.55 * visibility)
                    * (0.72 + 0.28 * forward_gain)
                    * distance_fit.max(0.25);
                candidates.push(GenericPassSpaceCandidate {
                    score,
                    target,
                    visibility,
                    position_value: pv,
                });
            }
        }
    }

    candidates.sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    candidates.truncate(10);
    candidates
}

pub fn receiver_base_pass_targets(
    input: &ReceiverBaseTargetsInput<'_>,
) -> ReceiverBaseTargetsOutput {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let tm = input.receiver;
    let receiver_visibility = input.vision.confidence(input.passer_pos, tm.pos);
    let mut target_visibility = receiver_visibility
        .max(input.vision.confidence(input.passer_pos, tm.target_pos))
        .max(
            input
                .vision
                .confidence(input.passer_pos, tm.tactical_anchor),
        );
    let mut low_visibility = target_visibility < 0.18;
    let mut receiver_goal_fit = 0.0;
    let mut targets = vec![RawPassTarget {
        target: tm.pos,
        arrival: 1.0,
    }];

    if let Some(goal) = input.receiver_goal {
        if goal.goal_type == "arc_arrival_for_cutback" || goal.goal_type == "attack_far_post" {
            let goal_visibility = input.vision.confidence(input.passer_pos, goal.target_pos);
            let goal_dist = distance(tm.pos, goal.target_pos);
            let target_progress_hint = if input.attacking_right {
                goal.target_pos.0 / input.pitch_length
            } else {
                (input.pitch_length - goal.target_pos.0) / input.pitch_length
            };
            let carrier_progress_hint = if input.attacking_right {
                input.passer_pos.0 / input.pitch_length
            } else {
                (input.pitch_length - input.passer_pos.0) / input.pitch_length
            };
            let support_depth = carrier_progress_hint - target_progress_hint;
            let target_centrality_hint = 1.0
                - ((goal.target_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                    .min(1.0);
            if goal.goal_type == "arc_arrival_for_cutback" {
                receiver_goal_fit = crate::physics::smoothstep(0.56, 0.84, target_progress_hint)
                    * (1.0 - crate::physics::smoothstep(0.86, 0.96, target_progress_hint))
                    * (1.0 - crate::physics::smoothstep(0.18, 0.34, support_depth.abs()))
                    * crate::physics::smoothstep(0.42, 0.84, target_centrality_hint)
                    * (1.0 - crate::physics::smoothstep(18.0, 42.0, goal_dist))
                    * crate::physics::smoothstep(0.005, 0.080, goal.value);
            } else {
                receiver_goal_fit = crate::physics::smoothstep(0.76, 0.94, target_progress_hint)
                    * crate::physics::smoothstep(0.22, 0.76, target_centrality_hint)
                    * (1.0 - crate::physics::smoothstep(16.0, 42.0, goal_dist))
                    * crate::physics::smoothstep(0.005, 0.080, goal.value);
            }
            receiver_goal_fit *= 0.35 + 0.65 * goal_visibility;
            target_visibility = target_visibility.max(goal_visibility);
            low_visibility = target_visibility < 0.18;
            if receiver_goal_fit > 0.0 {
                targets.push(RawPassTarget {
                    target: goal.target_pos,
                    arrival: 0.62 + 0.22 * receiver_goal_fit,
                });
            }
        }
    }

    let future_x = tm.pos.0 + (tm.target_pos.0 - tm.pos.0) * 0.5;
    let future_y = tm.pos.1 + (tm.target_pos.1 - tm.pos.1) * 0.5;
    targets.push(RawPassTarget {
        target: pitch_clamp((future_x, future_y), input.pitch_length, input.pitch_width),
        arrival: 0.92,
    });

    let support_x = tm.pos.0 * 0.65 + input.passer_pos.0 * 0.35;
    let support_y = tm.pos.1 * 0.70 + input.passer_pos.1 * 0.30;
    targets.push(RawPassTarget {
        target: pitch_clamp(
            (support_x, support_y),
            input.pitch_length,
            input.pitch_width,
        ),
        arrival: 0.88,
    });

    let switch_y = tm.pos.1 * 0.45 + (input.pitch_width - input.passer_pos.1) * 0.55;
    if !low_visibility {
        targets.push(RawPassTarget {
            target: pitch_clamp((support_x, switch_y), input.pitch_length, input.pitch_width),
            arrival: 0.76,
        });
    }

    let tm_width_ratio = ((tm.tactical_anchor.1 - input.pitch_width / 2.0).abs()
        / (input.pitch_width / 2.0))
        .min(1.0);
    let tm_progress_hint = if input.attacking_right {
        tm.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - tm.tactical_anchor.0) / input.pitch_length
    };
    if !low_visibility && tm_width_ratio > 0.50 && tm_progress_hint > 0.56 {
        let wide_lane_y = tm.tactical_anchor.1 * 0.72 + tm.pos.1 * 0.28;
        let wide_lane_x = if input.attacking_right {
            tm.pos.0.max(tm.tactical_anchor.0)
        } else {
            tm.pos.0.min(tm.tactical_anchor.0)
        };
        targets.push(RawPassTarget {
            target: pitch_clamp(
                (wide_lane_x + forward_dir * 4.0, wide_lane_y),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: 0.78,
        });
    }

    let move_progress = (tm.target_pos.0 - tm.pos.0) * forward_dir;
    if !low_visibility && move_progress > 1.0 {
        let lead_x = tm.pos.0 + forward_dir * (4.0 + move_progress).min(12.0);
        let lead_y = tm.pos.1 + (tm.target_pos.1 - tm.pos.1) * 0.35;
        targets.push(RawPassTarget {
            target: pitch_clamp((lead_x, lead_y), input.pitch_length, input.pitch_width),
            arrival: 0.82,
        });
    }

    ReceiverBaseTargetsOutput {
        targets,
        receiver_visibility,
        target_visibility,
        low_visibility,
        receiver_goal_fit,
    }
}

pub fn value_field_raw_targets(input: &ValueFieldTargetsInput<'_>) -> Vec<ValueFieldRawTarget> {
    let role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let role_fit = crate::physics::smoothstep(0.38, 0.76, role_progress)
        * if input.is_defender { 0.55 } else { 1.0 };
    let mut results = Vec::new();
    for candidate in input.generic_candidates {
        let goal_fit = if let Some(goal_target) = input.receiver_goal_target {
            1.0 - distance(goal_target, candidate.target) / 18.0
        } else {
            0.0
        };
        let arrival_fit = 0.0_f64
            .max(1.0 - distance(input.receiver.pos, candidate.target) / 28.0)
            .max(1.0 - distance(input.receiver.target_pos, candidate.target) / 24.0)
            .max(1.0 - distance(input.receiver.tactical_anchor, candidate.target) / 22.0)
            .max(goal_fit);
        let expected_arrival =
            (candidate.score * (0.30 + 0.48 * arrival_fit + 0.22 * role_fit) * 1.35)
                .clamp(0.0, 1.0);
        if expected_arrival < 0.18 {
            continue;
        }
        results.push(ValueFieldRawTarget {
            target: candidate.target,
            arrival: expected_arrival.max(0.42),
            tactical_space_prior: candidate.score,
            tactical_space_value: candidate.position_value,
            tactical_space_visibility: candidate.visibility,
            expected_arrival_confidence: expected_arrival,
            expected_arrival_fit: arrival_fit,
        });
    }
    results
}

pub fn stale_release_targets(input: &StaleReleaseTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let mut targets = Vec::new();
    if input.low_visibility
        || input.consecutive_carries < 3
        || carrier_progress <= 0.62
        || input.receiver.is_defender
    {
        return targets;
    }
    let outlet_dist = distance(input.receiver.pos, input.passer_pos);
    if outlet_dist <= 4.0 || outlet_dist >= 34.0 {
        return targets;
    }

    let stale_release = ((input.consecutive_carries - 2) as f64 / 4.0).min(1.0);
    let support_weight = if input.receiver.is_midfielder || input.receiver.is_wide {
        1.0
    } else {
        0.72
    };
    let outlet_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.35;
    let outlet_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.35;
    targets.push(RawPassTarget {
        target: pitch_clamp((outlet_x, outlet_y), input.pitch_length, input.pitch_width),
        arrival: 0.86 * support_weight,
    });
    targets.push(RawPassTarget {
        target: input.receiver.pos,
        arrival: 0.90 * support_weight,
    });

    let lateral_sign = if input.receiver.pos.1 >= input.passer_pos.1 {
        1.0
    } else {
        -1.0
    };
    let release_depth = 4.0 + 6.0 * stale_release;
    let release_width =
        ((input.receiver.pos.1 - input.passer_pos.1).abs() * 0.50 + 4.0).clamp(4.0, 12.0);
    let release_x = input.passer_pos.0 - forward_dir * release_depth;
    let release_y = input.passer_pos.1 + lateral_sign * release_width;
    if distance((release_x, release_y), input.receiver.pos) < 28.0 {
        targets.push(RawPassTarget {
            target: pitch_clamp(
                (release_x, release_y),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: 0.80 * support_weight,
        });
    }

    let anchor_x = input.receiver.tactical_anchor.0 * 0.55 + input.receiver.pos.0 * 0.45;
    let anchor_y = input.receiver.tactical_anchor.1 * 0.70 + input.receiver.pos.1 * 0.30;
    if distance((anchor_x, anchor_y), input.passer_pos) < 34.0 {
        targets.push(RawPassTarget {
            target: pitch_clamp((anchor_x, anchor_y), input.pitch_length, input.pitch_width),
            arrival: 0.78 * support_weight,
        });
    }
    targets
}

pub fn layoff_targets(input: &LayoffTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let mut targets = Vec::new();
    if input.low_visibility || carrier_progress <= 0.80 || input.receiver.is_defender {
        return targets;
    }
    let side_sign = if input.receiver.tactical_anchor.1 >= input.pitch_width / 2.0 {
        1.0
    } else {
        -1.0
    };
    let raw_targets = [
        (
            input.passer_pos.0 - forward_dir * 5.0,
            input.pitch_width / 2.0,
            0.76,
        ),
        (
            input.passer_pos.0 - forward_dir * 7.0,
            input.passer_pos.1 + side_sign * 5.0,
            0.70,
        ),
        (
            input.passer_pos.0 - forward_dir * 9.0,
            input.receiver.tactical_anchor.1 * 0.45 + input.pitch_width / 2.0 * 0.55,
            0.66,
        ),
    ];
    for (x, y, arrival) in raw_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 34.0 {
            targets.push(RawPassTarget { target, arrival });
        }
    }
    targets
}

pub fn second_line_targets(input: &SecondLineTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let receiver_base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length
    };
    let receiver_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let second_line_role = (0.42..=0.68).contains(&receiver_base_progress)
        && !input.receiver.is_defender
        && receiver_progress_hint > 0.60;
    if input.low_visibility || carrier_progress <= 0.68 || !second_line_role {
        return Vec::new();
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let arc_x = goal_side_x - forward_dir * 24.0;
    let support_x =
        input.receiver.tactical_anchor.0 * 0.42 + input.receiver.target_pos.0 * 0.26 + arc_x * 0.32;
    let support_y = input.receiver.tactical_anchor.1 * 0.40
        + input.receiver.target_pos.1 * 0.20
        + input.pitch_width / 2.0 * 0.40;
    let target = pitch_clamp(
        (support_x, support_y),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(target, input.receiver.pos) < 30.0 {
        vec![RawPassTarget {
            target,
            arrival: 0.72,
        }]
    } else {
        Vec::new()
    }
}

pub fn box_delivery_targets(input: &BoxDeliveryTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let carrier_width =
        (input.passer_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    if input.low_visibility
        || carrier_progress <= 0.68
        || carrier_width <= 0.34
        || input.receiver.is_defender
    {
        return Vec::new();
    }

    let target_role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    if target_role_progress <= 0.54 {
        return Vec::new();
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let box_edge_x = goal_side_x - forward_dir * 15.5;
    let raw_cutback_x = input.passer_pos.0 + forward_dir * 7.0;
    let cutback_x = if input.attacking_right {
        box_edge_x.min(raw_cutback_x)
    } else {
        box_edge_x.max(raw_cutback_x)
    };
    let near_box_x = goal_side_x - forward_dir * 12.0;
    let center_y = input.pitch_width / 2.0;
    let carrier_side = if input.passer_pos.1 >= center_y {
        1.0
    } else {
        -1.0
    };
    let delivery_targets = [
        (cutback_x, center_y, 0.66),
        (
            cutback_x,
            center_y + carrier_side * input.pitch_width * 0.10,
            0.62,
        ),
        (near_box_x, center_y, 0.54),
        (
            near_box_x,
            center_y + carrier_side * input.pitch_width * 0.12,
            0.50,
        ),
    ];
    let mut targets = Vec::new();
    for (x, y, arrival) in delivery_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 32.0 {
            targets.push(RawPassTarget { target, arrival });
        }
    }

    let runner_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.65;
    let runner_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.65;
    let runner_target = pitch_clamp(
        (runner_x, runner_y + (center_y - runner_y) * 0.35),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(runner_target, input.receiver.pos) < 18.0 {
        targets.push(RawPassTarget {
            target: runner_target,
            arrival: 0.74,
        });
    }
    targets
}

pub fn delivery_space_targets(input: &DeliverySpaceTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let receiver_forward = 0.0_f64
        .max((input.receiver.tactical_anchor.0 - input.receiver.pos.0) * forward_dir)
        .max((input.receiver.target_pos.0 - input.receiver.pos.0) * forward_dir);
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let target_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let delivery_pressure = carrier_progress.max(target_progress_hint);
    let central_pull = input.pitch_width / 2.0 - input.receiver.pos.1;
    if input.low_visibility
        || delivery_pressure <= 0.70
        || !(receiver_forward > 0.5 || target_progress_hint > 0.76)
    {
        return Vec::new();
    }

    let mut targets = Vec::new();
    for (depth_scale, center_scale, arrival_base) in
        [(0.45, 0.35, 0.74), (0.75, 0.55, 0.66), (1.05, 0.72, 0.58)]
    {
        let run_depth = 3.0 + (receiver_forward + 6.0).min(12.0) * depth_scale;
        targets.push(RawPassTarget {
            target: pitch_clamp(
                (
                    input.receiver.pos.0 + forward_dir * run_depth,
                    input.receiver.pos.1 + central_pull * center_scale,
                ),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: arrival_base,
        });
    }

    if carrier_progress > 0.82
        && (input.passer_pos.1 - input.pitch_width / 2.0).abs() > input.pitch_width * 0.14
    {
        for (depth_scale, center_scale, arrival_base) in [(0.20, 0.58, 0.70), (-0.15, 0.70, 0.64)] {
            let support_depth = (receiver_forward + 4.0).min(9.0) * depth_scale;
            let mut target_x = input.receiver.pos.0 + forward_dir * support_depth;
            target_x = if input.attacking_right {
                target_x.min(input.passer_pos.0 - 0.5)
            } else {
                target_x.max(input.passer_pos.0 + 0.5)
            };
            targets.push(RawPassTarget {
                target: pitch_clamp(
                    (target_x, input.receiver.pos.1 + central_pull * center_scale),
                    input.pitch_length,
                    input.pitch_width,
                ),
                arrival: arrival_base,
            });
        }
    }
    targets
}

pub fn receiver_spatial_candidates(
    input: &ReceiverSpatialCandidatesInput<'_>,
) -> Vec<ReceiverSpatialCandidate> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let tm_anchor_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let tm_width_factor = ((input.receiver.tactical_anchor.1 - input.pitch_width / 2.0).abs()
        / (input.pitch_width / 2.0))
        .min(1.0);
    let search_radius = 6.0 + 10.0 * tm_anchor_progress + 3.0 * tm_width_factor;
    let mut candidates = Vec::new();

    if !input.low_visibility {
        let sample_angles = [
            -150.0_f64, -105.0, -60.0, -25.0, 0.0, 25.0, 60.0, 105.0, 150.0,
        ];
        let sample_radii = [search_radius * 0.55, search_radius];
        for center in [
            input.receiver.pos,
            input.receiver.target_pos,
            input.receiver.tactical_anchor,
        ] {
            for radius in sample_radii {
                for angle_deg in sample_angles {
                    let angle = angle_deg.to_radians();
                    let pos = pitch_clamp(
                        (
                            center.0 + angle.cos() * radius * forward_dir,
                            center.1 + angle.sin() * radius,
                        ),
                        input.pitch_length,
                        input.pitch_width,
                    );
                    let point_visibility = input.vision.confidence(input.passer_pos, pos);
                    if point_visibility <= 0.0 {
                        continue;
                    }
                    if is_offside_position(
                        pos,
                        input.attacking_right,
                        input.offside_line,
                        input.pitch_length,
                        Some(input.passer_pos.0),
                    ) {
                        continue;
                    }
                    let d_from_receiver = distance(pos, input.receiver.pos);
                    if d_from_receiver > search_radius * 1.50 {
                        continue;
                    }
                    let pv = position_value(&PositionValueInput {
                        x: pos.0,
                        y: pos.1,
                        pitch_length: input.pitch_length,
                        pitch_width: input.pitch_width,
                        attacking_right: input.attacking_right,
                        opponent_positions: input.opponent_positions,
                        teammate_positions: input.teammate_positions,
                        runner_formation_pos: Some(input.receiver.tactical_anchor),
                    });
                    let receiver_arrival =
                        (1.0 - d_from_receiver / (search_radius * 1.65)).max(0.25);
                    let score = pv * receiver_arrival * (0.55 + 0.45 * point_visibility);
                    candidates.push(ReceiverSpatialCandidate {
                        score,
                        target: pos,
                        receiver_arrival,
                        position_value: pv,
                        point_visibility,
                    });
                }
            }
        }

        if let Some(front_center) = input.front_center {
            if tm_anchor_progress > 0.50 {
                for angle_deg in [-60.0_f64, -25.0, 0.0, 25.0, 60.0] {
                    let angle = angle_deg.to_radians();
                    let radius = search_radius * 0.85;
                    let pos = pitch_clamp(
                        (
                            front_center.0 + angle.cos() * radius * forward_dir,
                            front_center.1 + angle.sin() * radius,
                        ),
                        input.pitch_length,
                        input.pitch_width,
                    );
                    let point_visibility = input.vision.confidence(input.passer_pos, pos);
                    if point_visibility <= 0.0 {
                        continue;
                    }
                    if is_offside_position(
                        pos,
                        input.attacking_right,
                        input.offside_line,
                        input.pitch_length,
                        Some(input.passer_pos.0),
                    ) {
                        continue;
                    }
                    let d_from_receiver = distance(pos, input.receiver.pos);
                    let pv = position_value(&PositionValueInput {
                        x: pos.0,
                        y: pos.1,
                        pitch_length: input.pitch_length,
                        pitch_width: input.pitch_width,
                        attacking_right: input.attacking_right,
                        opponent_positions: input.opponent_positions,
                        teammate_positions: input.teammate_positions,
                        runner_formation_pos: Some(input.receiver.tactical_anchor),
                    });
                    let receiver_arrival =
                        (1.0 - d_from_receiver / (search_radius * 1.90)).max(0.22);
                    let score = pv * receiver_arrival * (0.55 + 0.45 * point_visibility);
                    candidates.push(ReceiverSpatialCandidate {
                        score,
                        target: pos,
                        receiver_arrival,
                        position_value: pv,
                        point_visibility,
                    });
                }
            }
        }
    }

    candidates.sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    candidates.truncate(3);
    candidates
}

pub fn evaluate_raw_pass_target_prevalue(
    input: &RawPassPreValueInput<'_>,
) -> RawPassPreValueOutput {
    let mut receiver_arrival = input.initial_receiver_arrival;
    let d = distance(input.passer_pos, input.target);
    let target_kind_space = distance(input.target, input.receiver.pos) > 4.0;
    let invalid = RawPassPreValueOutput {
        valid: false,
        receiver_arrival,
        base_accuracy: 0.0,
        continuity: 0.0,
        perception: 0.0,
        perception_multiplier: 0.0,
        arrival_margin: 0.0,
        receiver_time: 0.0,
        defender_time: f64::INFINITY,
        defender_first_risk: 0.0,
        target_occupation_risk: 0.0,
        nearest_teammate_to_target: 0.0,
        nearest_opp_to_target: 0.0,
        box_space_pressure: 0.0,
        goal_target_fit: 0.0,
        is_long: false,
        target_kind_space,
        distance: d,
    };
    if d < 3.0 || d > 55.0 {
        return invalid;
    }
    let perception = input.vision.confidence(input.passer_pos, input.target);
    if perception <= 0.0 && target_kind_space {
        return invalid;
    }
    if is_offside_position(
        input.target,
        input.attacking_right,
        input.offside_line,
        input.pitch_length,
        Some(input.passer_pos.0),
    ) {
        receiver_arrival *= 0.25;
    }

    let tm_speed = crate::physics::player_speed(
        input.receiver.speed,
        input.player_max_speed,
        input.player_min_speed,
    );
    let receiver_time = distance(input.receiver.pos, input.target) / tm_speed.max(0.1);
    let mut defender_time = f64::INFINITY;
    let mut nearest_opp_to_target = f64::INFINITY;
    for opp in input.opponents {
        nearest_opp_to_target = nearest_opp_to_target.min(distance(opp.pos, input.target));
        let mut opp_speed =
            crate::physics::player_speed(opp.speed, input.player_max_speed, input.player_min_speed);
        if opp.is_goalkeeper {
            let goal_x = if input.attacking_right {
                input.pitch_length
            } else {
                0.0
            };
            let goal_dist = (input.target.0 - goal_x).abs();
            if goal_dist > 24.0 {
                continue;
            }
            opp_speed *= 1.18;
        }
        defender_time = defender_time.min(distance(opp.pos, input.target) / opp_speed.max(0.1));
    }
    let nearest_teammate_to_target = input
        .teammates
        .iter()
        .filter(|tm| tm.index != input.passer_index && !tm.is_goalkeeper)
        .map(|tm| distance(tm.pos, input.target))
        .fold(distance(input.receiver.pos, input.target), f64::min);

    let arrival_margin = defender_time - receiver_time;
    if arrival_margin < 0.0 {
        receiver_arrival *= (1.0 + arrival_margin / 3.5).max(0.10);
    } else {
        receiver_arrival *= 0.78 + 0.22 * (arrival_margin / 4.0).min(1.0);
    }

    let defender_first_risk = crate::physics::smoothstep(0.2, 3.8, -arrival_margin);
    let target_occupation_risk =
        crate::physics::smoothstep(0.6, 4.0, nearest_teammate_to_target - nearest_opp_to_target)
            .max(
                (1.0 - crate::physics::smoothstep(0.8, 3.2, nearest_opp_to_target))
                    * crate::physics::smoothstep(2.5, 7.0, nearest_teammate_to_target),
            );
    let target_progress_for_risk = if input.attacking_right {
        input.target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality_for_risk = 1.0
        - ((input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let box_space_pressure = crate::physics::smoothstep(0.78, 0.90, target_progress_for_risk)
        * crate::physics::smoothstep(0.45, 0.85, target_centrality_for_risk)
        * crate::physics::smoothstep(4.0, 16.0, distance(input.receiver.pos, input.target));
    if box_space_pressure > 0.0 {
        let required_margin = 0.8 + 1.8 * box_space_pressure;
        let margin_factor = ((arrival_margin + 1.2) / required_margin).clamp(0.24, 1.0);
        receiver_arrival *= 1.0 - box_space_pressure * (1.0 - margin_factor);
    }
    if defender_first_risk > 0.0 {
        receiver_arrival *= 1.0 - 0.62 * defender_first_risk;
    }
    if target_occupation_risk > 0.0 {
        receiver_arrival *= 1.0 - 0.72 * target_occupation_risk;
    }

    let is_long = d > 30.0;
    let passing = if is_long {
        input.long_passing
    } else {
        input.short_passing
    } / 100.0;
    let base = if is_long {
        input.long_pass_base_success
    } else {
        input.short_pass_base_success
    };
    let dist_factor = (1.0 - (d - 10.0).max(0.0) / 65.0).max(0.35);
    let base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor;

    let mut goal_target_fit = 0.0;
    if let Some(goal_target) = input.receiver_goal_target {
        goal_target_fit =
            (1.0 - distance(input.target, goal_target) / 14.0).max(0.0) * input.receiver_goal_fit;
        if goal_target_fit > 0.0 {
            receiver_arrival = (receiver_arrival * (1.0 + 0.10 * goal_target_fit)).min(1.0);
        }
    }

    let mut continuity = if distance(input.target, input.receiver.pos) <= 4.0 {
        0.075
    } else {
        0.045
    };
    continuity += 0.065 * goal_target_fit * (input.receiver_goal_value * 2.4).clamp(0.0, 1.0);
    let perception_floor = if target_kind_space { 0.0 } else { 0.35 };
    let perception_multiplier = 0.48
        + 0.52
            * perception
                .max(perception_floor)
                .max(input.receiver_visibility * 0.55);
    receiver_arrival *= perception_multiplier;

    RawPassPreValueOutput {
        valid: true,
        receiver_arrival,
        base_accuracy,
        continuity,
        perception,
        perception_multiplier,
        arrival_margin,
        receiver_time,
        defender_time,
        defender_first_risk,
        target_occupation_risk,
        nearest_teammate_to_target,
        nearest_opp_to_target,
        box_space_pressure,
        goal_target_fit,
        is_long,
        target_kind_space,
        distance: d,
    }
}

pub fn score_raw_pass_target(input: &RawPassValueInput<'_>) -> RawPassValueOutput {
    let pre = evaluate_raw_pass_target_prevalue(&input.prevalue);
    if !pre.valid {
        return RawPassValueOutput {
            valid: false,
            score: 0.0,
            success_prob: 0.0,
            risk_cost: 0.0,
            current_value: input.current_value,
            effective_current_value: input.current_value,
            delta: 0.0,
            after_value: 0.0,
            effective_delta: 0.0,
            progress_gain: 0.0,
            continuity: 0.0,
            lane_risk: 0.0,
            receiver_pressure: 0.0,
            turnover_consequence: 0.0,
            high_threat_space: 0.0,
            final_third_combination: 0.0,
            second_line_arrival_value: 0.0,
            second_line_cutback_value: 0.0,
            layoff_support_value: 0.0,
            short_combination_value: 0.0,
            layoff_retention_value: 0.0,
            adjusted_score: 0.0,
            receiver_arrival: pre.receiver_arrival,
            base_accuracy: pre.base_accuracy,
            defender_first_risk: pre.defender_first_risk,
            target_occupation_risk: pre.target_occupation_risk,
            goal_target_fit: pre.goal_target_fit,
            is_long: pre.is_long,
            target_kind_space: pre.target_kind_space,
            distance: pre.distance,
            perception: pre.perception,
            perception_multiplier: pre.perception_multiplier,
            arrival_margin: pre.arrival_margin,
            nearest_teammate_to_target: pre.nearest_teammate_to_target,
            nearest_opp_to_target: pre.nearest_opp_to_target,
            box_space_pressure: pre.box_space_pressure,
        };
    }

    let value = expected_pass_value(&ExpectedPassInput {
        tick: input.tick,
        passer_index: input.prevalue.passer_index,
        passer_team_home: input.passer_team_home,
        passer_pos: input.prevalue.passer_pos,
        passer_finishing: input.passer_finishing,
        passer_long_shot: input.passer_long_shot,
        passer_consecutive_carries: input.passer_consecutive_carries,
        receiver_index: input.receiver_index,
        receiver_team_home: input.receiver_team_home,
        receiver_finishing: input.receiver_finishing,
        receiver_long_shot: input.receiver_long_shot,
        receiver_anchor: input.receiver_anchor,
        receiver_base: input.receiver_base,
        receiver_goal_type: input.receiver_goal_type,
        receiver_goal_target: input.receiver_goal_target,
        receiver_goal_value: input.receiver_goal_value,
        target: input.prevalue.target,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.prevalue.pitch_length,
        pitch_width: input.prevalue.pitch_width,
        attacking_right: input.prevalue.attacking_right,
        interception_reach: input.interception_reach,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        current_value: input.current_value,
        base_accuracy: pre.base_accuracy,
        receiver_arrival: pre.receiver_arrival,
        continuity: pre.continuity,
        shot_quality_cache: input.shot_quality_cache,
    });
    let mut adjusted_score = value.score;
    if pre.defender_first_risk > 0.0 {
        adjusted_score *= 1.0 - 0.58 * pre.defender_first_risk;
    }
    if pre.target_occupation_risk > 0.0 {
        adjusted_score *= 1.0 - 0.68 * pre.target_occupation_risk;
    }

    RawPassValueOutput {
        valid: adjusted_score > 0.0,
        score: value.score,
        success_prob: value.success_prob,
        risk_cost: value.risk_cost,
        current_value: value.current_value,
        effective_current_value: value.effective_current_value,
        delta: value.delta,
        after_value: value.after_value,
        effective_delta: value.effective_delta,
        progress_gain: value.progress_gain,
        continuity: value.continuity,
        lane_risk: value.lane_risk,
        receiver_pressure: value.receiver_pressure,
        turnover_consequence: value.turnover_consequence,
        high_threat_space: value.high_threat_space,
        final_third_combination: value.final_third_combination,
        second_line_arrival_value: value.second_line_arrival_value,
        second_line_cutback_value: value.second_line_cutback_value,
        layoff_support_value: value.layoff_support_value,
        short_combination_value: value.short_combination_value,
        layoff_retention_value: value.layoff_retention_value,
        adjusted_score,
        receiver_arrival: pre.receiver_arrival,
        base_accuracy: pre.base_accuracy,
        defender_first_risk: pre.defender_first_risk,
        target_occupation_risk: pre.target_occupation_risk,
        goal_target_fit: pre.goal_target_fit,
        is_long: pre.is_long,
        target_kind_space: pre.target_kind_space,
        distance: pre.distance,
        perception: pre.perception,
        perception_multiplier: pre.perception_multiplier,
        arrival_margin: pre.arrival_margin,
        nearest_teammate_to_target: pre.nearest_teammate_to_target,
        nearest_opp_to_target: pre.nearest_opp_to_target,
        box_space_pressure: pre.box_space_pressure,
    }
}

pub fn receiver_pass_candidates_batch(
    input: &ReceiverPassBatchInput<'_>,
) -> Vec<ReceiverPassCandidate> {
    let base = receiver_base_pass_targets(&ReceiverBaseTargetsInput {
        passer_pos: input.passer_pos,
        receiver: input.receiver_space,
        receiver_goal: input.receiver_goal,
        vision: input.vision,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    });
    let receiver_goal_target = input.receiver_goal.map(|goal| goal.target_pos);
    let receiver_goal_value = input.receiver_goal.map(|goal| goal.value).unwrap_or(0.0);
    let receiver_goal_type = input.receiver_goal.map(|goal| goal.goal_type);

    let mut raw_targets: Vec<RawPassTargetMeta> = base
        .targets
        .into_iter()
        .map(RawPassTargetMeta::from)
        .collect();
    raw_targets.extend(
        stale_release_targets(&StaleReleaseTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            consecutive_carries: input.passer_consecutive_carries,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        })
        .into_iter()
        .map(RawPassTargetMeta::from),
    );
    raw_targets.extend(
        layoff_targets(&LayoffTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        })
        .into_iter()
        .map(RawPassTargetMeta::from),
    );
    raw_targets.extend(
        second_line_targets(&SecondLineTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            receiver_base: input.receiver_base,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        })
        .into_iter()
        .map(RawPassTargetMeta::from),
    );
    raw_targets.extend(
        box_delivery_targets(&BoxDeliveryTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        })
        .into_iter()
        .map(RawPassTargetMeta::from),
    );
    raw_targets.extend(
        delivery_space_targets(&DeliverySpaceTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        })
        .into_iter()
        .map(RawPassTargetMeta::from),
    );
    for target in value_field_raw_targets(&ValueFieldTargetsInput {
        receiver: input.receiver_space,
        receiver_goal_target,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        is_defender: input.is_receiver_defender,
        generic_candidates: input.generic_candidates,
    }) {
        raw_targets.push(RawPassTargetMeta {
            target: target.target,
            arrival: target.arrival,
            tactical_space: true,
            tactical_space_prior: target.tactical_space_prior,
            tactical_space_value: target.tactical_space_value,
            tactical_space_visibility: target.tactical_space_visibility,
            expected_arrival_confidence: target.expected_arrival_confidence,
            expected_arrival_fit: target.expected_arrival_fit,
        });
    }
    for target in receiver_spatial_candidates(&ReceiverSpatialCandidatesInput {
        passer_pos: input.passer_pos,
        receiver: input.receiver_space,
        vision: input.vision,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        offside_line: input.offside_line,
        low_visibility: base.low_visibility,
        front_center: input.front_center,
        opponent_positions: input.opponent_positions,
        teammate_positions: input.teammate_xy_positions,
    }) {
        raw_targets.push(RawPassTargetMeta {
            target: target.target,
            arrival: target.receiver_arrival,
            tactical_space: false,
            tactical_space_prior: 0.0,
            tactical_space_value: 0.0,
            tactical_space_visibility: 0.0,
            expected_arrival_confidence: 0.0,
            expected_arrival_fit: 0.0,
        });
    }

    let mut candidates = Vec::new();
    for raw in raw_targets {
        let value = score_raw_pass_target(&RawPassValueInput {
            prevalue: RawPassPreValueInput {
                passer_index: input.passer_index,
                passer_pos: input.passer_pos,
                receiver: input.receiver_risk,
                target: raw.target,
                initial_receiver_arrival: raw.arrival,
                receiver_visibility: base.receiver_visibility,
                receiver_goal_target,
                receiver_goal_value,
                receiver_goal_fit: base.receiver_goal_fit,
                vision: input.vision,
                attacking_right: input.attacking_right,
                pitch_length: input.pitch_length,
                pitch_width: input.pitch_width,
                offside_line: input.offside_line,
                player_max_speed: input.player_max_speed,
                player_min_speed: input.player_min_speed,
                short_passing: input.passer_short_passing,
                long_passing: input.passer_long_passing,
                short_pass_base_success: input.short_pass_base_success,
                long_pass_base_success: input.long_pass_base_success,
                opponents: input.risk_opponents,
                teammates: input.risk_teammates,
            },
            tick: input.tick,
            passer_team_home: input.passer_team_home,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_consecutive_carries: input.passer_consecutive_carries,
            receiver_index: input.receiver_index,
            receiver_team_home: input.receiver_team_home,
            receiver_finishing: input.receiver_finishing,
            receiver_long_shot: input.receiver_long_shot,
            receiver_anchor: input.receiver_anchor,
            receiver_base: input.receiver_base,
            receiver_goal_type,
            receiver_goal_target,
            receiver_goal_value,
            teammate_positions: input.teammate_positions,
            teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
            opponent_positions: input.opponent_positions,
            interception_reach: input.interception_reach,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            current_value: input.current_value,
            shot_quality_cache: input.shot_quality_cache,
        });
        if !value.valid || value.adjusted_score <= 0.0 {
            continue;
        }
        candidates.push(ReceiverPassCandidate {
            target: raw.target,
            score: value.adjusted_score,
            raw_score: value.score,
            success_prob: value.success_prob,
            risk_cost: value.risk_cost,
            current_value: value.current_value,
            effective_current_value: value.effective_current_value,
            delta: value.delta,
            after_value: value.after_value,
            effective_delta: value.effective_delta,
            progress_gain: value.progress_gain,
            continuity: value.continuity,
            lane_risk: value.lane_risk,
            receiver_pressure: value.receiver_pressure,
            turnover_consequence: value.turnover_consequence,
            high_threat_space: value.high_threat_space,
            final_third_combination: value.final_third_combination,
            second_line_arrival_value: value.second_line_arrival_value,
            second_line_cutback_value: value.second_line_cutback_value,
            layoff_support_value: value.layoff_support_value,
            short_combination_value: value.short_combination_value,
            layoff_retention_value: value.layoff_retention_value,
            receiver_arrival: value.receiver_arrival,
            base_accuracy: value.base_accuracy,
            goal_target_fit: value.goal_target_fit,
            is_long: value.is_long,
            target_kind_space: value.target_kind_space,
            distance: value.distance,
            perception: value.perception,
            perception_multiplier: value.perception_multiplier,
            arrival_margin: value.arrival_margin,
            defender_first_risk: value.defender_first_risk,
            target_occupation_risk: value.target_occupation_risk,
            nearest_teammate_to_target: value.nearest_teammate_to_target,
            nearest_opp_to_target: value.nearest_opp_to_target,
            box_space_pressure: value.box_space_pressure,
            tactical_space: raw.tactical_space,
            tactical_space_prior: raw.tactical_space_prior,
            tactical_space_value: raw.tactical_space_value,
            tactical_space_visibility: raw.tactical_space_visibility,
            expected_arrival_confidence: raw.expected_arrival_confidence,
            expected_arrival_fit: raw.expected_arrival_fit,
        });
    }
    candidates
}

pub fn team_pass_candidates_batch(input: &TeamPassBatchInput<'_>) -> Vec<TeamPassCandidate> {
    let generic_candidates = generic_pass_space_candidates(&GenericPassSpaceInput {
        passer_index: input.passer_index,
        passer_pos: input.passer_pos,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        offside_line: input.offside_line,
        vision: input.vision,
        teammates: &input
            .players
            .iter()
            .map(|player| player.space)
            .collect::<Vec<_>>(),
        opponent_positions: input.opponent_positions,
        teammate_positions: input.teammate_xy_positions,
    });

    let front_anchors: Vec<(f64, f64)> = input
        .players
        .iter()
        .filter(|player| player.space.index != input.passer_index && !player.space.is_goalkeeper)
        .filter(|player| {
            let progress = if input.attacking_right {
                player.space.tactical_anchor.0 / input.pitch_length
            } else {
                (input.pitch_length - player.space.tactical_anchor.0) / input.pitch_length
            };
            progress > 0.58
        })
        .map(|player| player.space.tactical_anchor)
        .collect();
    let front_center = if front_anchors.is_empty() {
        None
    } else {
        Some((
            front_anchors.iter().map(|pos| pos.0).sum::<f64>() / front_anchors.len() as f64,
            front_anchors.iter().map(|pos| pos.1).sum::<f64>() / front_anchors.len() as f64,
        ))
    };

    let mut results = Vec::new();
    for player in input.players {
        if player.space.index == input.passer_index || player.space.is_goalkeeper {
            continue;
        }
        let receiver_candidates = receiver_pass_candidates_batch(&ReceiverPassBatchInput {
            tick: input.tick,
            passer_index: input.passer_index,
            passer_team_home: input.passer_team_home,
            passer_pos: input.passer_pos,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_short_passing: input.passer_short_passing,
            passer_long_passing: input.passer_long_passing,
            passer_consecutive_carries: input.passer_consecutive_carries,
            receiver_space: player.space,
            receiver_risk: player.risk,
            receiver_index: player.space.index,
            receiver_team_home: input.passer_team_home,
            receiver_finishing: player.finishing,
            receiver_long_shot: player.long_shot,
            receiver_anchor: player.space.tactical_anchor,
            receiver_base: player.base,
            receiver_goal: player.goal,
            is_receiver_defender: player.is_defender,
            vision: input.vision,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            offside_line: input.offside_line,
            player_max_speed: input.player_max_speed,
            player_min_speed: input.player_min_speed,
            short_pass_base_success: input.short_pass_base_success,
            long_pass_base_success: input.long_pass_base_success,
            interception_reach: input.interception_reach,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            current_value: input.current_value,
            front_center,
            generic_candidates: &generic_candidates,
            opponent_positions: input.opponent_positions,
            teammate_positions: input.teammate_positions_for_value,
            teammate_goalkeeper_indices: input.teammate_goalkeeper_indices_for_value,
            teammate_xy_positions: input.teammate_xy_positions,
            risk_opponents: input.risk_opponents,
            risk_teammates: input.risk_teammates,
            shot_quality_cache: input.shot_quality_cache,
        });
        for candidate in receiver_candidates {
            results.push(TeamPassCandidate {
                receiver_index: player.space.index,
                target: candidate.target,
                score: candidate.score,
                raw_score: candidate.raw_score,
                success_prob: candidate.success_prob,
                risk_cost: candidate.risk_cost,
                current_value: candidate.current_value,
                effective_current_value: candidate.effective_current_value,
                delta: candidate.delta,
                after_value: candidate.after_value,
                effective_delta: candidate.effective_delta,
                progress_gain: candidate.progress_gain,
                continuity: candidate.continuity,
                lane_risk: candidate.lane_risk,
                receiver_pressure: candidate.receiver_pressure,
                turnover_consequence: candidate.turnover_consequence,
                high_threat_space: candidate.high_threat_space,
                final_third_combination: candidate.final_third_combination,
                second_line_arrival_value: candidate.second_line_arrival_value,
                second_line_cutback_value: candidate.second_line_cutback_value,
                layoff_support_value: candidate.layoff_support_value,
                short_combination_value: candidate.short_combination_value,
                layoff_retention_value: candidate.layoff_retention_value,
                receiver_arrival: candidate.receiver_arrival,
                base_accuracy: candidate.base_accuracy,
                goal_target_fit: candidate.goal_target_fit,
                is_long: candidate.is_long,
                target_kind_space: candidate.target_kind_space,
                distance: candidate.distance,
                perception: candidate.perception,
                perception_multiplier: candidate.perception_multiplier,
                arrival_margin: candidate.arrival_margin,
                defender_first_risk: candidate.defender_first_risk,
                target_occupation_risk: candidate.target_occupation_risk,
                nearest_teammate_to_target: candidate.nearest_teammate_to_target,
                nearest_opp_to_target: candidate.nearest_opp_to_target,
                box_space_pressure: candidate.box_space_pressure,
                tactical_space: candidate.tactical_space,
                tactical_space_prior: candidate.tactical_space_prior,
                tactical_space_value: candidate.tactical_space_value,
                tactical_space_visibility: candidate.tactical_space_visibility,
                expected_arrival_confidence: candidate.expected_arrival_confidence,
                expected_arrival_fit: candidate.expected_arrival_fit,
            });
        }
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generic_pass_space_candidates_are_sorted_and_limited() {
        let teammates = [
            PassSpacePlayer {
                index: 0,
                pos: (50.0, 34.0),
                target_pos: (50.0, 34.0),
                tactical_anchor: (50.0, 34.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: true,
                is_wide: false,
            },
            PassSpacePlayer {
                index: 1,
                pos: (70.0, 22.0),
                target_pos: (76.0, 20.0),
                tactical_anchor: (76.0, 20.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: true,
            },
            PassSpacePlayer {
                index: 2,
                pos: (72.0, 44.0),
                target_pos: (78.0, 46.0),
                tactical_anchor: (78.0, 46.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: true,
            },
        ];
        let opponents = [(82.0, 30.0), (86.0, 40.0)];
        let teammate_positions = [(70.0, 22.0), (72.0, 44.0)];
        let result = generic_pass_space_candidates(&GenericPassSpaceInput {
            passer_index: 0,
            passer_pos: (50.0, 34.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            offside_line: 90.0,
            vision: VisionContext {
                facing: 0.0,
                fov: 180.0,
                half_fov: 90.0,
                max_distance: 50.0,
            },
            teammates: &teammates,
            opponent_positions: &opponents,
            teammate_positions: &teammate_positions,
        });
        assert!(result.len() <= 10);
        assert!(result.windows(2).all(|pair| pair[0].score >= pair[1].score));
    }
}
