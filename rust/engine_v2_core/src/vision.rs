use crate::physics::{angle_between_points, angle_diff, distance, is_in_fov};

#[derive(Clone, Copy, Debug)]
pub struct VisionContextInput {
    pub iq: f64,
    pub facing_direction: f64,
    pub attacking_right: bool,
    pub vision_base_fov: f64,
    pub vision_iq_bonus_factor: f64,
    pub vision_base_distance: f64,
    pub vision_iq_distance_bonus_factor: f64,
    pub vision_max_distance: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct VisionContext {
    pub facing: f64,
    pub fov: f64,
    pub half_fov: f64,
    pub max_distance: f64,
}

pub fn compute_facing_direction(
    player_pos: (f64, f64),
    ball_pos: (f64, f64),
    last_action_target: Option<(f64, f64)>,
) -> f64 {
    angle_between_points(player_pos, last_action_target.unwrap_or(ball_pos))
}

pub fn compute_fov(iq: f64, vision_base_fov: f64, vision_iq_bonus_factor: f64) -> f64 {
    let fov = vision_base_fov + (iq - 80.0) * vision_iq_bonus_factor;
    fov.clamp(150.0, 240.0)
}

pub fn compute_vision_distance(
    iq: f64,
    vision_base_distance: f64,
    vision_iq_distance_bonus_factor: f64,
    vision_max_distance: f64,
) -> f64 {
    let distance = vision_base_distance + (iq - 70.0).max(0.0) * vision_iq_distance_bonus_factor;
    distance.clamp(24.0, vision_max_distance)
}

pub fn compute_player_facing(facing_direction: f64, _attacking_right: bool) -> f64 {
    facing_direction
}

impl VisionContext {
    pub fn confidence(&self, origin: (f64, f64), target: (f64, f64)) -> f64 {
        let d = distance(origin, target);
        if d <= 0.1 {
            return 1.0;
        }
        let target_angle = angle_between_points(origin, target);
        let diff = angle_diff(self.facing, target_angle).abs();
        let angle_conf =
            1.0 - (diff - self.half_fov * 0.65).max(0.0) / (self.half_fov * 0.70).max(1.0);
        let dist_conf =
            1.0 - (d - self.max_distance * 0.72).max(0.0) / (self.max_distance * 0.45).max(1.0);
        angle_conf.min(dist_conf).clamp(0.0, 1.0)
    }

    pub fn visible(&self, origin: (f64, f64), target: (f64, f64)) -> bool {
        self.confidence(origin, target) > 0.0
    }
}

pub fn build_vision_context(input: &VisionContextInput) -> VisionContext {
    let fov = compute_fov(
        input.iq,
        input.vision_base_fov,
        input.vision_iq_bonus_factor,
    );
    VisionContext {
        facing: compute_player_facing(input.facing_direction, input.attacking_right),
        fov,
        half_fov: fov / 2.0,
        max_distance: compute_vision_distance(
            input.iq,
            input.vision_base_distance,
            input.vision_iq_distance_bonus_factor,
            input.vision_max_distance,
        ),
    }
}

pub fn get_visible_target_indices(
    passer_index: usize,
    passer_pos: (f64, f64),
    passer_iq: f64,
    teammates: &[(usize, f64, f64)],
    ball_pos: (f64, f64),
    vision_base_fov: f64,
    vision_iq_bonus_factor: f64,
) -> Vec<usize> {
    let facing = compute_facing_direction(passer_pos, ball_pos, None);
    let half_fov = compute_fov(passer_iq, vision_base_fov, vision_iq_bonus_factor) / 2.0;
    let mut visible = Vec::new();
    let mut fallback = Vec::new();

    for (idx, x, y) in teammates {
        if *idx == passer_index {
            continue;
        }
        fallback.push(*idx);
        let angle_to_tm = angle_between_points(passer_pos, (*x, *y));
        if is_in_fov(facing, angle_to_tm, half_fov) {
            visible.push(*idx);
        }
    }

    if visible.is_empty() {
        fallback
    } else {
        visible
    }
}

pub fn is_target_visible(
    passer_pos: (f64, f64),
    passer_iq: f64,
    target_pos: (f64, f64),
    ball_pos: (f64, f64),
    vision_base_fov: f64,
    vision_iq_bonus_factor: f64,
) -> bool {
    let facing = compute_facing_direction(passer_pos, ball_pos, None);
    let half_fov = compute_fov(passer_iq, vision_base_fov, vision_iq_bonus_factor) / 2.0;
    let angle_to_target = angle_between_points(passer_pos, target_pos);
    is_in_fov(facing, angle_to_target, half_fov)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fov_and_distance_are_clamped_like_python() {
        assert_eq!(compute_fov(20.0, 180.0, 0.5), 150.0);
        assert_eq!(compute_fov(80.0, 180.0, 0.5), 180.0);
        assert_eq!(compute_fov(260.0, 180.0, 0.5), 240.0);
        assert_eq!(compute_vision_distance(30.0, 20.0, 0.35, 65.0), 24.0);
        assert_eq!(compute_vision_distance(120.0, 42.0, 0.35, 65.0), 59.5);
        assert_eq!(compute_vision_distance(200.0, 42.0, 0.35, 65.0), 65.0);
    }

    #[test]
    fn visible_targets_falls_back_when_none_are_in_fov() {
        let teammates = vec![(0, 0.0, 0.0), (1, -10.0, 5.0), (2, -12.0, -5.0)];
        let result =
            get_visible_target_indices(0, (0.0, 0.0), 80.0, &teammates, (10.0, 0.0), 180.0, 0.5);
        assert_eq!(result, vec![1, 2]);
    }

    #[test]
    fn zero_degree_is_a_valid_explicit_facing_direction() {
        assert_eq!(compute_player_facing(0.0, false), 0.0);
    }
}
