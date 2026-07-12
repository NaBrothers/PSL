pub fn distance(a: (f64, f64), b: (f64, f64)) -> f64 {
    let dx = b.0 - a.0;
    let dy = b.1 - a.1;
    (dx * dx + dy * dy).sqrt()
}

pub fn direction(origin: (f64, f64), target: (f64, f64)) -> (f64, f64) {
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let dist = (dx * dx + dy * dy).sqrt();
    if dist < 1e-6 {
        return (0.0, 0.0);
    }
    (dx / dist, dy / dist)
}

pub fn move_toward(pos: (f64, f64), target: (f64, f64), max_dist: f64) -> (f64, f64) {
    let dx = target.0 - pos.0;
    let dy = target.1 - pos.1;
    let dist = (dx * dx + dy * dy).sqrt();
    if dist <= max_dist || dist < 1e-6 {
        return target;
    }
    let ratio = max_dist / dist;
    (pos.0 + dx * ratio, pos.1 + dy * ratio)
}

pub fn interpolate(a: (f64, f64), b: (f64, f64), t: f64) -> (f64, f64) {
    (a.0 + (b.0 - a.0) * t, a.1 + (b.1 - a.1) * t)
}

pub fn angle_to_goal(pos: (f64, f64), goal_center: (f64, f64), goal_width: f64) -> f64 {
    let dx = goal_center.0 - pos.0;
    let dy_top = goal_center.1 + goal_width / 2.0 - pos.1;
    let dy_bot = goal_center.1 - goal_width / 2.0 - pos.1;
    let angle_top = dy_top.atan2(dx);
    let angle_bot = dy_bot.atan2(dx);
    (angle_top - angle_bot).abs()
}

pub fn player_speed(speed_ability: i32, max_speed: f64, min_speed: f64) -> f64 {
    let t = speed_ability.clamp(0, 99) as f64 / 99.0;
    min_speed + t * (max_speed - min_speed)
}

pub fn clamp(value: f64, lo: f64, hi: f64) -> f64 {
    lo.max(hi.min(value))
}

pub fn angle_between_points(origin: (f64, f64), target: (f64, f64)) -> f64 {
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    dy.atan2(dx).to_degrees()
}

pub fn angle_diff(a1: f64, a2: f64) -> f64 {
    let mut diff = a2 - a1;
    while diff > 180.0 {
        diff -= 360.0;
    }
    while diff < -180.0 {
        diff += 360.0;
    }
    diff
}

pub fn is_in_fov(facing_angle: f64, target_angle: f64, half_fov: f64) -> bool {
    angle_diff(facing_angle, target_angle).abs() <= half_fov
}

pub fn midpoint(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    ((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0)
}

pub fn point_along(origin: (f64, f64), angle_deg: f64, dist: f64) -> (f64, f64) {
    let rad = angle_deg.to_radians();
    (origin.0 + dist * rad.cos(), origin.1 + dist * rad.sin())
}

pub fn smoothstep(edge0: f64, edge1: f64, value: f64) -> f64 {
    let denom = (edge1 - edge0).max(1e-6);
    let t = ((value - edge0) / denom).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

pub fn is_attacking_box_pos(
    pos: (f64, f64),
    attacking_right: bool,
    pitch_length: f64,
    pitch_width: f64,
) -> bool {
    let progress = if attacking_right {
        pos.0 / pitch_length
    } else {
        (pitch_length - pos.0) / pitch_length
    };
    progress > 1.0 - 16.5 / pitch_length && (pos.1 - pitch_width / 2.0).abs() < 20.2
}

pub fn residual_ball_velocity(
    origin: (f64, f64),
    target: (f64, f64),
    speed: f64,
    factor: f64,
) -> (f64, f64) {
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let length = (dx * dx + dy * dy).sqrt().max(0.1);
    let residual = (speed * factor).clamp(0.7, 6.0);
    (dx / length * residual, dy / length * residual)
}

pub fn out_of_bounds_restart(
    x: f64,
    pitch_length: f64,
    passer_team_home: bool,
) -> (&'static str, bool) {
    let restart_home = !passer_team_home;
    if x < 0.0 || x > pitch_length {
        ("goal_kick", restart_home)
    } else {
        ("throw_in", restart_home)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn move_toward_matches_python_edge_behavior() {
        assert_eq!(move_toward((1.0, 2.0), (1.0, 2.0), -3.0), (1.0, 2.0));
        assert_eq!(move_toward((0.0, 0.0), (3.0, 4.0), 5.0), (3.0, 4.0));
        assert_eq!(move_toward((0.0, 0.0), (3.0, 4.0), 2.5), (1.5, 2.0));
    }

    #[test]
    fn angle_diff_uses_python_loop_boundaries() {
        assert_eq!(angle_diff(0.0, 180.0), 180.0);
        assert_eq!(angle_diff(0.0, -180.0), -180.0);
        assert_eq!(angle_diff(10.0, 370.0), 0.0);
        assert_eq!(angle_diff(170.0, -170.0), 20.0);
    }
}
