use std::cell::RefCell;
use std::collections::HashMap;

use crate::goalkeeper::{compute_gk_save_probability_for_attributes, GkSaveAttributes};
use crate::physics::{distance, smoothstep};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ShotQualityCacheKey {
    pub tick: i32,
    pub team_home: bool,
    pub player_index: usize,
    pub x10: i64,
    pub y10: i64,
    pub attacking_right: bool,
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
    pub cache: Option<&'a ShotQualityCache>,
    pub cache_key: Option<ShotQualityCacheKey>,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotOutcomeEstimate {
    pub on_target_prob: f64,
    pub save_prob: f64,
    pub xg: f64,
}

pub type ShotQualityCache = RefCell<HashMap<ShotQualityCacheKey, ShotOutcomeEstimate>>;

fn outside_penalty_area(pos: (f64, f64), input: &ShotQualityInput<'_>) -> bool {
    let progress = if input.attacking_right {
        pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - pos.0) / input.pitch_length.max(1.0)
    };
    progress <= 1.0 - 16.5 / input.pitch_length.max(1.0)
        || (pos.1 - input.pitch_width / 2.0).abs() >= 20.2
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

    let dx = (goal.0 - pos.0).abs();
    let dy = (goal.1 - pos.1).abs();
    let directness = dx / (dx * dx + dy * dy).sqrt().max(1.0);
    let angle_factor = directness.clamp(0.15, 1.0);

    let mut pressure_factor: f64 = 1.0;
    let mut lane_factor: f64 = 1.0;
    let shot_len = ((goal.0 - pos.0).powi(2) + (goal.1 - pos.1).powi(2))
        .sqrt()
        .max(1.0);
    let nx = (goal.0 - pos.0) / shot_len;
    let ny = (goal.1 - pos.1) / shot_len;
    for opp in input.opponents {
        let d = distance(pos, *opp);
        if d < 8.0 {
            pressure_factor *= (1.0 - (8.0 - d) * 0.035).max(0.72);
        }
        let ox = opp.0 - pos.0;
        let oy = opp.1 - pos.1;
        let proj = ox * nx + oy * ny;
        if proj > 1.0 && proj < shot_len - 1.0 {
            let perp = (ox * ny - oy * nx).abs();
            if perp < 4.5 {
                lane_factor *= (1.0 - (4.5 - perp) * 0.05).max(0.65);
            }
        }
    }

    let mut on_target = input.shot_on_target_base
        * (0.4 + 0.6 * ability)
        * dist_factor
        * angle_factor
        * pressure_factor
        * lane_factor;
    let outside_box = outside_penalty_area(pos, input);
    if outside_box {
        let outside_penalty = 0.76 + 0.24 * smoothstep(21.0, 32.0, dist);
        on_target *= outside_penalty;
    }
    on_target = on_target.clamp(0.0, 0.78);
    let save_prob = expected_goalkeeper_save_probability(input);
    let xg = (on_target * (1.0 - save_prob)).clamp(0.0, 0.65);
    let outcome = ShotOutcomeEstimate {
        on_target_prob: on_target,
        save_prob,
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
    let mut total = 0.0;
    for sample in samples {
        let target_y = goal_y_min + 0.5 + (goal_y_max - goal_y_min - 1.0) * sample;
        let target_x = if input.attacking_right {
            input.pitch_length
        } else {
            0.0
        };
        total += estimate_goalkeeper_save_probability(input, (target_x, target_y));
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
            cache: None,
            cache_key: None,
        });
        assert!(close > far);
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
