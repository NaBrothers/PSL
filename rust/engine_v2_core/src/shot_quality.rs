use std::cell::RefCell;
use std::collections::HashMap;

use crate::goalkeeper::{
    compute_gk_save_probability_for_attributes, compute_gk_save_probability_with_context,
    gk_save_context_for_goal, GkSaveAttributes,
};
use crate::physics::{angle_to_goal, distance, smoothstep};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ShotQualityCacheKey {
    pub tick: i32,
    pub team_home: bool,
    pub player_index: usize,
    pub x10: i64,
    pub y10: i64,
    pub attacking_right: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShotContestIntent {
    Press,
    BlockLane,
    MarkRunner,
    RecoverShape,
    HoldPosition,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotContestDefender {
    pub index: usize,
    pub pos: (f64, f64),
    pub projected_pos: (f64, f64),
    pub speed: f64,
    pub defence: f64,
    pub intent: ShotContestIntent,
    pub engagement_weight: f64,
    pub engagement_reach: f64,
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotContestEstimate {
    pub body_release_probability: f64,
    pub release_probability: f64,
    pub block_probability: f64,
    pub blocker_index: Option<usize>,
    pub block_point: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct ShotContestResolution {
    pub blocked: bool,
    pub blocker_index: Option<usize>,
    pub block_point: (f64, f64),
}

#[derive(Debug, Clone)]
pub struct ShotQualityInput<'a> {
    pub x: f64,
    pub y: f64,
    pub finishing: f64,
    pub long_shot: f64,
    pub opponents: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub cache: Option<&'a ShotQualityCache>,
    pub cache_key: Option<ShotQualityCacheKey>,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotOutcomeEstimate {
    pub body_release_probability: f64,
    pub release_probability: f64,
    pub block_probability: f64,
    pub blocker_index: Option<usize>,
    pub block_point: (f64, f64),
    pub on_target_prob: f64,
    pub save_prob: f64,
    pub open_goal_window: f64,
    pub xg: f64,
}

pub type ShotQualityCache = RefCell<HashMap<ShotQualityCacheKey, ShotOutcomeEstimate>>;

pub fn calibrated_shot_execution_probabilities(
    expected_goal_probability: f64,
    modeled_on_target_probability: f64,
    league_accuracy_scale: f64,
) -> (f64, f64) {
    let expected_goal_probability = expected_goal_probability.clamp(0.0, 1.0);
    let on_target = (modeled_on_target_probability.clamp(0.0, 1.0)
        * league_accuracy_scale.max(0.0))
    .clamp(expected_goal_probability, 0.995);
    let save_probability = if on_target <= f64::EPSILON {
        0.0
    } else {
        (1.0 - expected_goal_probability / on_target).clamp(0.0, 1.0)
    };
    (on_target, save_probability)
}

fn outside_penalty_area(pos: (f64, f64), input: &ShotQualityInput<'_>) -> bool {
    let progress = if input.attacking_right {
        pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - pos.0) / input.pitch_length.max(1.0)
    };
    progress <= 1.0 - 16.5 / input.pitch_length.max(1.0)
        || (pos.1 - input.pitch_width / 2.0).abs() >= 20.2
}

pub fn shot_contest_intent(action: &str) -> ShotContestIntent {
    match action {
        "close_down" | "tackle" | "approach" => ShotContestIntent::Press,
        "block_lane" => ShotContestIntent::BlockLane,
        "mark_runner" => ShotContestIntent::MarkRunner,
        "defend_shape" | "recover_shape" => ShotContestIntent::RecoverShape,
        _ => ShotContestIntent::HoldPosition,
    }
}

pub fn shot_contest_engagement(action: &str, tackle_range: f64) -> (f64, f64) {
    let contact_reach = 0.75 + 0.36 * tackle_range.max(0.0);
    match action {
        "tackle" => (0.86, contact_reach * 1.08),
        "approach" => (0.36, contact_reach * 0.94),
        _ => (0.0, 0.0),
    }
}

fn shot_contest_intent_weight(intent: ShotContestIntent) -> f64 {
    match intent {
        ShotContestIntent::Press => 0.92,
        ShotContestIntent::BlockLane => 1.0,
        ShotContestIntent::MarkRunner => 0.72,
        ShotContestIntent::RecoverShape => 0.54,
        ShotContestIntent::HoldPosition => 0.42,
    }
}

fn line_projection_from_geometry(
    origin: (f64, f64),
    point: (f64, f64),
    dx: f64,
    dy: f64,
    length_sq: f64,
    shot_length: f64,
) -> f64 {
    if length_sq <= 1e-9 {
        0.0
    } else {
        ((point.0 - origin.0) * dx + (point.1 - origin.1) * dy) / shot_length
    }
}

fn line_perpendicular_distance_from_geometry(
    origin: (f64, f64),
    point: (f64, f64),
    dx: f64,
    dy: f64,
    normalization_length: f64,
) -> f64 {
    (((point.0 - origin.0) * dy - (point.1 - origin.1) * dx) / normalization_length).abs()
}

fn interpolate_point(start: (f64, f64), end: (f64, f64), fraction: f64) -> (f64, f64) {
    let fraction = fraction.clamp(0.0, 1.0);
    (
        start.0 + (end.0 - start.0) * fraction,
        start.1 + (end.1 - start.1) * fraction,
    )
}

fn estimate_shot_contest_for_defenders<I>(
    origin: (f64, f64),
    target: (f64, f64),
    defenders: I,
) -> ShotContestEstimate
where
    I: IntoIterator<Item = ShotContestDefender>,
{
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let shot_length_sq = dx * dx + dy * dy;
    let shot_length = shot_length_sq.sqrt();
    if shot_length <= 1e-6 {
        return ShotContestEstimate {
            body_release_probability: 1.0,
            release_probability: 1.0,
            block_probability: 0.0,
            blocker_index: None,
            block_point: origin,
        };
    }

    let nx = dx / shot_length;
    let ny = dy / shot_length;
    let perpendicular_normalization_length = shot_length.max(1.0);
    let contest_limit = (shot_length * 0.62).min(20.0);
    let mut body_release_probability = 1.0;
    let mut release_probability = 1.0;
    let mut strongest_block = (0.0, None, origin);

    for defender in defenders {
        if defender.is_goalkeeper {
            continue;
        }
        let projected_pos = interpolate_point(defender.pos, defender.projected_pos, 0.42);
        if defender.intent == ShotContestIntent::Press && defender.engagement_weight > 0.0 {
            let current_distance = distance(origin, defender.pos);
            let projected_distance = distance(origin, projected_pos);
            let closest_distance = current_distance.min(projected_distance);
            let engagement_reach = defender.engagement_reach.max(0.0);
            if engagement_reach > 0.0 && closest_distance < engagement_reach {
                let proximity =
                    1.0 - smoothstep(engagement_reach * 0.34, engagement_reach, closest_distance);
                let convergence = smoothstep(
                    -engagement_reach * 0.20,
                    engagement_reach * 0.70,
                    current_distance - projected_distance,
                );
                let defensive_timing = (0.76 + 0.24 * (defender.defence / 100.0).clamp(0.0, 1.0))
                    * (0.78 + 0.22 * (defender.speed / 100.0).clamp(0.0, 1.0));
                let release_disruption = (defender.engagement_weight
                    * (0.18 + 0.82 * proximity)
                    * (0.70 + 0.30 * convergence)
                    * defensive_timing)
                    .clamp(0.0, 0.95);
                body_release_probability *= 1.0 - release_disruption;
            }
        }
        let start_projection = line_projection_from_geometry(
            origin,
            defender.pos,
            dx,
            dy,
            shot_length_sq,
            shot_length,
        );
        let projected_projection = line_projection_from_geometry(
            origin,
            projected_pos,
            dx,
            dy,
            shot_length_sq,
            shot_length,
        );
        let lane_projection =
            ((start_projection + projected_projection) * 0.5).clamp(0.0, shot_length);
        if lane_projection <= 0.55 || lane_projection >= contest_limit {
            continue;
        }

        let current_perp = line_perpendicular_distance_from_geometry(
            origin,
            defender.pos,
            dx,
            dy,
            perpendicular_normalization_length,
        );
        let projected_perp = line_perpendicular_distance_from_geometry(
            origin,
            projected_pos,
            dx,
            dy,
            perpendicular_normalization_length,
        );
        let nearest_perp = current_perp.min(projected_perp);
        let lane_coverage = 1.0 - smoothstep(1.0, 4.0, nearest_perp);
        if lane_coverage <= 0.0 {
            continue;
        }
        let closure = smoothstep(-0.25, 1.65, current_perp - projected_perp);
        let line_access = smoothstep(0.75, 3.0, lane_projection)
            * (1.0 - smoothstep(contest_limit * 0.72, contest_limit, lane_projection));
        let intent = shot_contest_intent_weight(defender.intent);
        let defensive_ability = (0.46 + 0.54 * (defender.defence / 100.0).clamp(0.0, 1.0))
            * (0.66 + 0.34 * (defender.speed / 100.0).clamp(0.0, 1.0));
        let block_probability = (lane_coverage
            * line_access
            * (0.18 + 0.45 * intent)
            * (0.66 + 0.34 * closure)
            * defensive_ability)
            .clamp(0.0, 0.88);
        release_probability *= 1.0 - block_probability;

        if block_probability > strongest_block.0 {
            strongest_block = (
                block_probability,
                Some(defender.index),
                (
                    origin.0 + nx * lane_projection,
                    origin.1 + ny * lane_projection,
                ),
            );
        }
    }

    let release_probability = release_probability.clamp(0.0, 1.0);
    ShotContestEstimate {
        body_release_probability: body_release_probability.clamp(0.0, 1.0),
        release_probability,
        block_probability: 1.0 - release_probability,
        blocker_index: strongest_block.1,
        block_point: strongest_block.2,
    }
}

pub fn estimate_shot_contest(
    origin: (f64, f64),
    target: (f64, f64),
    defenders: &[ShotContestDefender],
) -> ShotContestEstimate {
    estimate_shot_contest_for_defenders(origin, target, defenders.iter().copied())
}

pub fn resolve_shot_contest(
    estimate: ShotContestEstimate,
    random_value: f64,
) -> ShotContestResolution {
    let blocked = random_value < estimate.block_probability;
    ShotContestResolution {
        blocked,
        blocker_index: if blocked {
            estimate.blocker_index
        } else {
            None
        },
        block_point: estimate.block_point,
    }
}

pub fn estimate_shot_outcome(input: &ShotQualityInput<'_>) -> ShotOutcomeEstimate {
    if input.gk_attributes.is_none() {
        if let (Some(cache), Some(cache_key)) = (input.cache, input.cache_key) {
            if let Some(cached) = cache.borrow().get(&cache_key).copied() {
                return cached;
            }
        }
    }

    let pos = (input.x, input.y);
    let goal = goal_target(input);
    let dist = distance(pos, goal);
    let ability = if dist > 25.0 {
        input.long_shot
    } else if dist > 18.0 {
        (input.finishing + input.long_shot) / 2.0
    } else {
        input.finishing
    };

    let dist_factor = if dist <= input.shot_ideal_distance {
        1.0
    } else if dist <= 30.0 {
        (1.0 - (dist - input.shot_ideal_distance) * 0.070).max(0.18)
    } else {
        0.45 * (-(dist - 30.0) / 14.0).exp()
    };

    let visible_goal_angle = angle_to_goal(pos, goal, 7.32);
    let angle_factor = smoothstep(0.0, std::f64::consts::FRAC_PI_4, visible_goal_angle);

    let contest = if let Some(defenders) = input.contest_defenders {
        estimate_shot_contest(pos, goal, defenders)
    } else {
        estimate_shot_contest_for_defenders(
            pos,
            goal,
            input
                .opponents
                .iter()
                .enumerate()
                .map(|(index, pos)| ShotContestDefender {
                    index,
                    pos: *pos,
                    projected_pos: *pos,
                    speed: 50.0,
                    defence: 50.0,
                    intent: ShotContestIntent::HoldPosition,
                    engagement_weight: 0.0,
                    engagement_reach: 0.0,
                    is_goalkeeper: false,
                }),
        )
    };

    let mut on_target =
        input.shot_on_target_base * (0.4 + 0.6 * ability) * dist_factor * angle_factor;
    let outside_box = outside_penalty_area(pos, input);
    if outside_box {
        let outside_penalty = 0.76 + 0.24 * smoothstep(21.0, 32.0, dist);
        on_target *= outside_penalty;
    }
    on_target = on_target.clamp(0.0, 0.78);
    let save_prob = expected_goalkeeper_save_probability(input);
    let open_goal_window = (1.0 - smoothstep(3.0, 10.0, dist))
        * angle_factor
        * (1.0 - smoothstep(0.04, 0.32, save_prob));
    on_target += (0.995 - on_target).max(0.0) * open_goal_window;
    on_target = on_target.clamp(0.0, 0.995);
    let xg_cap = 0.65 + 0.345 * open_goal_window;
    let xg = (on_target * (1.0 - save_prob)).clamp(0.0, xg_cap);
    let outcome = ShotOutcomeEstimate {
        body_release_probability: contest.body_release_probability,
        release_probability: contest.release_probability,
        block_probability: contest.block_probability,
        blocker_index: contest.blocker_index,
        block_point: contest.block_point,
        on_target_prob: on_target,
        save_prob,
        open_goal_window,
        xg,
    };
    if input.gk_attributes.is_none() {
        if let (Some(cache), Some(cache_key)) = (input.cache, input.cache_key) {
            cache.borrow_mut().insert(cache_key, outcome);
        }
    }
    outcome
}

pub fn shot_quality_at(input: &ShotQualityInput<'_>) -> f64 {
    estimate_shot_outcome(input).xg
}

pub fn expected_goalkeeper_save_probability(input: &ShotQualityInput<'_>) -> f64 {
    let goal_y_min = (input.pitch_width - 7.32) / 2.0;
    let goal_y_max = (input.pitch_width + 7.32) / 2.0;
    let samples = [0.10, 0.30, 0.50, 0.70, 0.90];
    let target_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let attributes = input.gk_attributes.unwrap_or_else(|| GkSaveAttributes {
        gk_saving: 50.0,
        gk_positioning: 50.0,
        gk_reaction: 50.0,
        gk_position_error_factor: 0.05,
        gk_reaction_delay_factor: 0.005,
        gk_save_base: input.gk_save_base,
    });
    let gk_pos = input.gk_pos.unwrap_or_else(|| {
        (
            if input.attacking_right {
                input.pitch_length - 4.5
            } else {
                4.5
            },
            input.pitch_width / 2.0,
        )
    });
    let gk_context = gk_save_context_for_goal(attributes, gk_pos, target_x);
    let mut total = 0.0;
    for sample in samples {
        let target_y = goal_y_min + 0.5 + (goal_y_max - goal_y_min - 1.0) * sample;
        total += compute_gk_save_probability_with_context(
            gk_context,
            (input.x, input.y),
            (target_x, target_y),
        );
    }
    total / samples.len() as f64
}

pub fn estimate_goalkeeper_save_probability(
    input: &ShotQualityInput<'_>,
    shot_target: (f64, f64),
) -> f64 {
    let attributes = input.gk_attributes.unwrap_or_else(|| GkSaveAttributes {
        gk_saving: 50.0,
        gk_positioning: 50.0,
        gk_reaction: 50.0,
        gk_position_error_factor: 0.05,
        gk_reaction_delay_factor: 0.005,
        gk_save_base: input.gk_save_base,
    });
    let gk_pos = input.gk_pos.unwrap_or_else(|| {
        (
            if input.attacking_right {
                input.pitch_length - 4.5
            } else {
                4.5
            },
            input.pitch_width / 2.0,
        )
    });
    compute_gk_save_probability_for_attributes(
        attributes,
        gk_pos,
        (input.x, input.y),
        shot_target,
        input.pitch_length,
    )
}

fn goal_target(input: &ShotQualityInput<'_>) -> (f64, f64) {
    if input.attacking_right {
        (input.pitch_length, input.pitch_width / 2.0)
    } else {
        (0.0, input.pitch_width / 2.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        execute_shot, resolve_shot_arrival, GkSaveAttributes, ShotArrivalInput, ShotExecutionInput,
    };

    fn test_goalkeeper_attributes() -> GkSaveAttributes {
        GkSaveAttributes {
            gk_saving: 84.0,
            gk_positioning: 82.0,
            gk_reaction: 86.0,
            gk_position_error_factor: 0.05,
            gk_reaction_delay_factor: 0.005,
            gk_save_base: 0.66,
        }
    }

    #[test]
    fn closer_central_shot_has_higher_quality() {
        let opponents = [(88.0, 30.0), (88.0, 38.0)];
        let close = shot_quality_at(&ShotQualityInput {
            x: 90.0,
            y: 34.0,
            finishing: 0.8,
            long_shot: 0.72,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            cache: None,
            cache_key: None,
        });
        let far = shot_quality_at(&ShotQualityInput {
            x: 62.0,
            y: 34.0,
            finishing: 0.8,
            long_shot: 0.72,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            cache: None,
            cache_key: None,
        });
        assert!(close > far);
    }

    #[test]
    fn execution_accuracy_can_change_without_changing_expected_goals() {
        let xg = 0.12;
        let (on_target, save_probability) = calibrated_shot_execution_probabilities(xg, 0.36, 1.25);

        assert!((on_target - 0.45).abs() < 1e-12);
        assert!((on_target * (1.0 - save_probability) - xg).abs() < 1e-12);
    }

    #[test]
    fn shot_contest_rewards_defenders_closing_the_shot_lane() {
        let origin = (85.0, 34.0);
        let target = (105.0, 34.0);
        let holding = [ShotContestDefender {
            index: 4,
            pos: (92.0, 38.0),
            projected_pos: (92.0, 38.0),
            speed: 78.0,
            defence: 82.0,
            intent: ShotContestIntent::BlockLane,
            engagement_weight: 0.0,
            engagement_reach: 0.0,
            is_goalkeeper: false,
        }];
        let closing = [ShotContestDefender {
            projected_pos: (92.0, 34.0),
            ..holding[0]
        }];
        let holding_estimate = estimate_shot_contest(origin, target, &holding);
        let closing_estimate = estimate_shot_contest(origin, target, &closing);

        assert!(
            closing_estimate.block_probability > holding_estimate.block_probability,
            "a defender moving into the lane must increase the shot block probability"
        );
        assert_eq!(closing_estimate.blocker_index, Some(4));
        assert!(closing_estimate.block_point.0 > origin.0);
        assert!(closing_estimate.block_point.0 < target.0);
    }

    #[test]
    fn lane_block_probability_is_not_already_folded_into_conditional_xg() {
        let opponents = [];
        let blocker = [ShotContestDefender {
            index: 4,
            pos: (94.0, 34.0),
            projected_pos: (94.0, 34.0),
            speed: 82.0,
            defence: 88.0,
            intent: ShotContestIntent::BlockLane,
            engagement_weight: 0.0,
            engagement_reach: 0.0,
            is_goalkeeper: false,
        }];
        let input = ShotQualityInput {
            x: 88.0,
            y: 34.0,
            finishing: 0.86,
            long_shot: 0.80,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: Some(test_goalkeeper_attributes()),
            gk_pos: Some((102.0, 34.0)),
            contest_defenders: None,
            cache: None,
            cache_key: None,
        };
        let clear_lane = estimate_shot_outcome(&input);
        let blocked_lane = estimate_shot_outcome(&ShotQualityInput {
            contest_defenders: Some(&blocker),
            ..input
        });

        assert!(blocked_lane.release_probability < clear_lane.release_probability);
        assert_eq!(blocked_lane.on_target_prob, clear_lane.on_target_prob);
        assert_eq!(blocked_lane.save_prob, clear_lane.save_prob);
        assert_eq!(blocked_lane.xg, clear_lane.xg);
    }

    #[test]
    fn shot_contest_ignores_defenders_outside_the_lane() {
        let origin = (85.0, 34.0);
        let target = (105.0, 34.0);
        let in_lane = [ShotContestDefender {
            index: 4,
            pos: (92.0, 34.0),
            projected_pos: (92.0, 34.0),
            speed: 78.0,
            defence: 82.0,
            intent: ShotContestIntent::BlockLane,
            engagement_weight: 0.0,
            engagement_reach: 0.0,
            is_goalkeeper: false,
        }];
        let outside_lane = [ShotContestDefender {
            pos: (92.0, 44.0),
            projected_pos: (92.0, 44.0),
            ..in_lane[0]
        }];
        let in_lane_estimate = estimate_shot_contest(origin, target, &in_lane);
        let outside_lane_estimate = estimate_shot_contest(origin, target, &outside_lane);

        assert!(in_lane_estimate.block_probability > 0.05);
        assert!(outside_lane_estimate.block_probability < 0.001);
    }

    #[test]
    fn fallback_contest_matches_explicit_default_defenders() {
        let opponents = [(88.0, 34.0), (92.0, 37.0), (97.0, 30.0)];
        let explicit_defenders = opponents
            .iter()
            .enumerate()
            .map(|(index, pos)| ShotContestDefender {
                index,
                pos: *pos,
                projected_pos: *pos,
                speed: 50.0,
                defence: 50.0,
                intent: ShotContestIntent::HoldPosition,
                engagement_weight: 0.0,
                engagement_reach: 0.0,
                is_goalkeeper: false,
            })
            .collect::<Vec<_>>();
        let input = ShotQualityInput {
            x: 84.0,
            y: 34.0,
            finishing: 0.82,
            long_shot: 0.76,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.74,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            cache: None,
            cache_key: None,
        };
        let fallback = estimate_shot_outcome(&input);
        let explicit = estimate_shot_outcome(&ShotQualityInput {
            contest_defenders: Some(&explicit_defenders),
            ..input
        });

        assert_eq!(
            fallback.body_release_probability,
            explicit.body_release_probability
        );
        assert_eq!(fallback.release_probability, explicit.release_probability);
        assert_eq!(fallback.block_probability, explicit.block_probability);
        assert_eq!(fallback.blocker_index, explicit.blocker_index);
        assert_eq!(fallback.block_point, explicit.block_point);
        assert_eq!(fallback.on_target_prob, explicit.on_target_prob);
        assert_eq!(fallback.save_prob, explicit.save_prob);
        assert_eq!(fallback.xg, explicit.xg);
    }

    #[test]
    fn shot_contest_resolution_uses_the_estimated_probability() {
        let estimate = estimate_shot_contest(
            (85.0, 34.0),
            (105.0, 34.0),
            &[ShotContestDefender {
                index: 4,
                pos: (92.0, 34.0),
                projected_pos: (92.0, 34.0),
                speed: 78.0,
                defence: 82.0,
                intent: ShotContestIntent::BlockLane,
                engagement_weight: 0.0,
                engagement_reach: 0.0,
                is_goalkeeper: false,
            }],
        );
        assert!(estimate.block_probability > 0.05);

        let blocked = resolve_shot_contest(estimate, estimate.block_probability * 0.5);
        let released = resolve_shot_contest(
            estimate,
            estimate.block_probability + (1.0 - estimate.block_probability) * 0.5,
        );

        assert!(blocked.blocked);
        assert_eq!(blocked.blocker_index, estimate.blocker_index);
        assert!(!released.blocked);
        assert_eq!(released.blocker_index, None);
    }

    #[test]
    fn close_press_disrupts_the_shot_release_without_becoming_a_lane_block() {
        let origin = (85.0, 34.0);
        let target = (105.0, 34.0);
        let press = [ShotContestDefender {
            index: 4,
            pos: (83.9, 34.4),
            projected_pos: (84.4, 34.1),
            speed: 82.0,
            defence: 84.0,
            intent: ShotContestIntent::Press,
            engagement_weight: 0.36,
            engagement_reach: 2.8,
            is_goalkeeper: false,
        }];
        let lane_only = [ShotContestDefender {
            intent: ShotContestIntent::BlockLane,
            engagement_weight: 0.0,
            engagement_reach: 0.0,
            ..press[0]
        }];
        let press_estimate = estimate_shot_contest(origin, target, &press);
        let lane_estimate = estimate_shot_contest(origin, target, &lane_only);

        assert!(
            press_estimate.body_release_probability < lane_estimate.body_release_probability,
            "a nearby press must reduce the ability to get the shot away"
        );
        assert!(
            (press_estimate.block_probability - lane_estimate.block_probability).abs() < 1e-12,
            "the engagement branch must not masquerade as a separate lane block"
        );
    }

    #[test]
    fn shot_outcome_decays_continuously_with_distance() {
        let opponents = [];
        let input = |x| ShotQualityInput {
            x,
            y: 34.0,
            finishing: 0.85,
            long_shot: 0.85,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            cache: None,
            cache_key: None,
        };
        let close = estimate_shot_outcome(&input(86.0));
        let long = estimate_shot_outcome(&input(55.0));
        let extreme = estimate_shot_outcome(&input(14.0));

        assert!(close.xg > long.xg);
        assert!(long.xg > extreme.xg);
        assert!(extreme.on_target_prob < 0.01);
    }

    #[test]
    fn extreme_range_shot_has_near_zero_continuous_probability() {
        let opponents = [];
        let input = ShotQualityInput {
            x: 12.0,
            y: 34.0,
            finishing: 0.90,
            long_shot: 0.99,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: Some(test_goalkeeper_attributes()),
            gk_pos: Some((100.5, 34.0)),
            contest_defenders: None,
            cache: None,
            cache_key: None,
        };
        let outcome = estimate_shot_outcome(&input);

        assert!(
            outcome.on_target_prob < 0.01,
            "near-full-pitch shots must decay below one percent without a fixed floor"
        );
        assert!(
            outcome.xg < 0.002,
            "near-full-pitch shots must retain only a near-zero continuous xG"
        );
    }

    #[test]
    fn expected_goalkeeper_save_probability_matches_individual_target_estimates() {
        let opponents = [];
        for (gk_attributes, gk_pos, attacking_right) in [
            (
                Some(test_goalkeeper_attributes()),
                Some((100.5, 31.8)),
                true,
            ),
            (None, None, false),
        ] {
            let input = ShotQualityInput {
                x: if attacking_right { 81.3 } else { 23.7 },
                y: 26.4,
                finishing: 0.83,
                long_shot: 0.77,
                opponents: &opponents,
                pitch_length: 105.0,
                pitch_width: 68.0,
                attacking_right,
                shot_ideal_distance: 20.0,
                shot_on_target_base: 0.52,
                gk_save_base: 0.66,
                gk_attributes,
                gk_pos,
                contest_defenders: None,
                cache: None,
                cache_key: None,
            };
            let goal_y_min = (input.pitch_width - 7.32) / 2.0;
            let goal_y_max = (input.pitch_width + 7.32) / 2.0;
            let target_x = if input.attacking_right {
                input.pitch_length
            } else {
                0.0
            };
            let expected = [0.10, 0.30, 0.50, 0.70, 0.90]
                .into_iter()
                .map(|sample| {
                    let target_y = goal_y_min + 0.5 + (goal_y_max - goal_y_min - 1.0) * sample;
                    estimate_goalkeeper_save_probability(&input, (target_x, target_y))
                })
                .sum::<f64>()
                / 5.0;

            assert_eq!(expected_goalkeeper_save_probability(&input), expected);
        }
    }

    #[test]
    fn decision_xg_matches_shared_execution_probability() {
        let opponents = [];
        let origin = (40.0, 29.0);
        let attributes = test_goalkeeper_attributes();
        let gk_pos = (100.5, 34.0);
        let input = ShotQualityInput {
            x: origin.0,
            y: origin.1,
            finishing: 0.82,
            long_shot: 0.88,
            opponents: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: attributes.gk_save_base,
            gk_attributes: Some(attributes),
            gk_pos: Some(gk_pos),
            contest_defenders: None,
            cache: None,
            cache_key: None,
        };
        let estimate = estimate_shot_outcome(&input);
        let target_samples = 401usize;
        let save_samples = 401usize;
        let mut successful_on_target_outcomes = 0usize;

        for target_sample in 0..target_samples {
            let target_roll = (target_sample as f64 + 0.5) / target_samples as f64;
            let shot = execute_shot(&ShotExecutionInput {
                shooter_pos: origin,
                on_target_prob: 1.0,
                attacking_right: true,
                pitch_length: 105.0,
                pitch_width: 68.0,
                goal_width: 7.32,
                ball_shot_speed: 28.0,
                tick_duration: 2.0,
                random_1: 0.0,
                random_2: target_roll,
                random_3: 0.5,
            });
            for save_sample in 0..save_samples {
                let save_roll = (save_sample as f64 + 0.5) / save_samples as f64;
                let arrival = resolve_shot_arrival(&ShotArrivalInput {
                    shot_origin: origin,
                    shot_target: shot.target,
                    on_target: true,
                    attacking_right: true,
                    pitch_length: 105.0,
                    pitch_width: 68.0,
                    gk_pos,
                    gk_attributes: attributes,
                    save_roll,
                });
                if arrival.outcome_code == 2 {
                    successful_on_target_outcomes += 1;
                }
            }
        }

        let execution_xg = estimate.on_target_prob * successful_on_target_outcomes as f64
            / (target_samples * save_samples) as f64;
        assert!(
            (estimate.xg - execution_xg).abs() < 0.003,
            "decision xG={} must agree with execute_shot + resolve_shot_arrival xG={}",
            estimate.xg,
            execution_xg
        );
    }

    #[test]
    fn shot_arrival_uses_current_goalkeeper_position_with_static_attributes() {
        let attributes = test_goalkeeper_attributes();
        let input = |gk_pos| ShotArrivalInput {
            shot_origin: (82.0, 34.0),
            shot_target: (105.0, 36.5),
            on_target: true,
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            gk_pos,
            gk_attributes: attributes,
            save_roll: 0.5,
        };
        let set_position = resolve_shot_arrival(&input((100.5, 36.5)));
        let moved_away = resolve_shot_arrival(&input((100.5, 26.0)));

        assert!(
            set_position.save_prob > moved_away.save_prob,
            "arrival must use the keeper's current position, while ability remains static"
        );
    }
}
