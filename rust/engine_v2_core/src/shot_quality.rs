use std::cell::RefCell;
use std::collections::HashMap;

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

pub type ShotQualityCache = RefCell<HashMap<ShotQualityCacheKey, f64>>;

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
    pub cache: Option<&'a ShotQualityCache>,
    pub cache_key: Option<ShotQualityCacheKey>,
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

pub fn shot_quality_at(input: &ShotQualityInput<'_>) -> f64 {
    if let (Some(cache), Some(cache_key)) = (input.cache, input.cache_key) {
        if let Some(cached) = cache.borrow().get(&cache_key).copied() {
            return cached;
        }
    }

    let pos = (input.x, input.y);
    let goal = if input.attacking_right {
        (input.pitch_length, input.pitch_width / 2.0)
    } else {
        (0.0, input.pitch_width / 2.0)
    };
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
    let min_on_target = if dist < 25.0 { 0.13 } else { 0.055 };
    on_target = on_target.clamp(min_on_target, 0.78);

    let mut save_estimate = input.gk_save_base;
    save_estimate += (1.0 - angle_factor) * 0.12;
    save_estimate += (1.0 - pressure_factor * lane_factor) * 0.10;
    save_estimate -= ((dist - 16.0).max(0.0) * 0.0035).min(0.12);
    if !outside_box && dist < 18.0 && (pos.1 - goal.1).abs() < 12.0 {
        save_estimate -= 0.12;
    }
    save_estimate = save_estimate.clamp(0.35, 0.90);

    let result = (on_target * (1.0 - save_estimate)).clamp(0.0, 0.65);
    if let (Some(cache), Some(cache_key)) = (input.cache, input.cache_key) {
        cache.borrow_mut().insert(cache_key, result);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

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
            cache: None,
            cache_key: None,
        });
        assert!(close > far);
    }
}
