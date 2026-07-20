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

#[derive(Clone, Copy, Debug)]
pub struct PlayerMotionInput {
    pub pos: (f64, f64),
    pub target: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub desired_speed: f64,
    pub acceleration_scale: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PlayerMotionOutput {
    pub pos: (f64, f64),
    pub unclamped_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub distance_covered: f64,
    pub facing_direction: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PitchBoundaryKind {
    GoalLine,
    TouchLine,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PitchBoundaryCrossing {
    pub point: (f64, f64),
    pub kind: PitchBoundaryKind,
}

pub fn segment_pitch_boundary_crossing(
    origin: (f64, f64),
    target: (f64, f64),
    pitch_length: f64,
    pitch_width: f64,
) -> Option<PitchBoundaryCrossing> {
    let dx = target.0 - origin.0;
    let dy = target.1 - origin.1;
    let mut crossings = Vec::with_capacity(2);
    if dx > 1e-9 && target.0 > pitch_length {
        let t = (pitch_length - origin.0) / dx;
        crossings.push((
            t,
            PitchBoundaryCrossing {
                point: (pitch_length, origin.1 + dy * t),
                kind: PitchBoundaryKind::GoalLine,
            },
        ));
    } else if dx < -1e-9 && target.0 < 0.0 {
        let t = -origin.0 / dx;
        crossings.push((
            t,
            PitchBoundaryCrossing {
                point: (0.0, origin.1 + dy * t),
                kind: PitchBoundaryKind::GoalLine,
            },
        ));
    }
    if dy > 1e-9 && target.1 > pitch_width {
        let t = (pitch_width - origin.1) / dy;
        crossings.push((
            t,
            PitchBoundaryCrossing {
                point: (origin.0 + dx * t, pitch_width),
                kind: PitchBoundaryKind::TouchLine,
            },
        ));
    } else if dy < -1e-9 && target.1 < 0.0 {
        let t = -origin.1 / dy;
        crossings.push((
            t,
            PitchBoundaryCrossing {
                point: (origin.0 + dx * t, 0.0),
                kind: PitchBoundaryKind::TouchLine,
            },
        ));
    }
    crossings
        .into_iter()
        .filter(|(t, crossing)| {
            *t >= 0.0
                && *t <= 1.0
                && crossing.point.0 >= -1e-9
                && crossing.point.0 <= pitch_length + 1e-9
                && crossing.point.1 >= -1e-9
                && crossing.point.1 <= pitch_width + 1e-9
        })
        .min_by(|(left, _), (right, _)| {
            left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(_, crossing)| crossing)
}

fn speed_ability_progress(speed_ability: i32) -> f64 {
    let ability = speed_ability.max(0) as f64;
    let regulation = (ability / 99.0).min(1.0);
    let elite_bonus = 1.0 - (-(ability - 99.0).max(0.0) / 55.0).exp();
    regulation + 0.18 * elite_bonus
}

pub fn player_speed(speed_ability: i32, max_speed: f64, min_speed: f64) -> f64 {
    min_speed + speed_ability_progress(speed_ability) * (max_speed - min_speed)
}

fn player_acceleration(speed_ability: i32, max_speed: f64, min_speed: f64) -> f64 {
    let top_speed = player_speed(speed_ability, max_speed, min_speed);
    let ability_progress = speed_ability_progress(speed_ability);
    top_speed * (0.34 + 0.25 * ability_progress)
}

pub fn advance_player_motion(input: &PlayerMotionInput) -> PlayerMotionOutput {
    advance_player_motion_fraction(input, 1.0)
}

pub fn advance_player_motion_fraction(
    input: &PlayerMotionInput,
    tick_fraction: f64,
) -> PlayerMotionOutput {
    let tick_fraction = tick_fraction.clamp(0.0, 1.0);
    if tick_fraction <= 1e-9 {
        return PlayerMotionOutput {
            pos: input.pos,
            unclamped_pos: input.pos,
            velocity: input.velocity,
            distance_covered: 0.0,
            facing_direction: None,
        };
    }
    let max_speed = player_speed(
        input.speed_ability,
        input.player_max_speed,
        input.player_min_speed,
    );
    let accel = player_acceleration(
        input.speed_ability,
        input.player_max_speed,
        input.player_min_speed,
    ) * input.acceleration_scale.clamp(0.2, 1.5);
    let brake_accel = accel * 1.28;
    let target_distance = distance(input.pos, input.target);
    let target_direction = direction(input.pos, input.target);
    let mut current_velocity = input.velocity;
    let current_speed =
        (current_velocity.0 * current_velocity.0 + current_velocity.1 * current_velocity.1).sqrt();
    if current_speed > max_speed * 1.05 {
        let ratio = max_speed * 1.05 / current_speed;
        current_velocity.0 *= ratio;
        current_velocity.1 *= ratio;
    }

    let forward_speed = if target_distance > 1e-6 {
        current_velocity.0 * target_direction.0 + current_velocity.1 * target_direction.1
    } else {
        0.0
    };
    let stopping_speed = (2.0 * brake_accel * target_distance.max(0.0)).sqrt();
    let arrival_speed = (2.0 * target_distance - forward_speed.max(0.0)).max(0.0);
    let desired_speed = input
        .desired_speed
        .clamp(0.0, max_speed * 0.98)
        .min(stopping_speed)
        .min(arrival_speed);
    let desired_velocity = (
        target_direction.0 * desired_speed,
        target_direction.1 * desired_speed,
    );

    let alignment = if current_speed > 1e-6 && target_distance > 1e-6 {
        (current_velocity.0 * target_direction.0 + current_velocity.1 * target_direction.1)
            / current_speed
    } else {
        1.0
    }
    .clamp(-1.0, 1.0);
    let turn_severity = if desired_speed <= 1e-6 {
        1.0
    } else {
        (1.0 - alignment) * 0.5
    };
    let velocity_response = (accel + (brake_accel - accel) * turn_severity) * tick_fraction;
    let mut delta_velocity = (
        desired_velocity.0 - current_velocity.0,
        desired_velocity.1 - current_velocity.1,
    );
    let delta_speed =
        (delta_velocity.0 * delta_velocity.0 + delta_velocity.1 * delta_velocity.1).sqrt();
    if delta_speed > velocity_response {
        let ratio = velocity_response / delta_speed;
        delta_velocity.0 *= ratio;
        delta_velocity.1 *= ratio;
    }

    let mut velocity = (
        current_velocity.0 + delta_velocity.0,
        current_velocity.1 + delta_velocity.1,
    );
    let velocity_length = (velocity.0 * velocity.0 + velocity.1 * velocity.1).sqrt();
    if velocity_length > max_speed * 0.98 {
        let ratio = max_speed * 0.98 / velocity_length;
        velocity.0 *= ratio;
        velocity.1 *= ratio;
    }

    let displacement = (
        (current_velocity.0 + velocity.0) * 0.5 * tick_fraction,
        (current_velocity.1 + velocity.1) * 0.5 * tick_fraction,
    );
    let along_target = displacement.0 * target_direction.0 + displacement.1 * target_direction.1;
    if target_distance > 1e-6 && along_target >= target_distance {
        let pos = (
            input.target.0.clamp(0.5, input.pitch_length - 0.5),
            input.target.1.clamp(0.5, input.pitch_width - 0.5),
        );
        return PlayerMotionOutput {
            pos,
            unclamped_pos: input.target,
            velocity: if pos == input.target {
                (0.0, 0.0)
            } else {
                (0.0, 0.0)
            },
            distance_covered: distance(input.pos, pos),
            facing_direction: if distance(input.pos, pos) > 0.1 {
                Some(angle_between_points(input.pos, pos))
            } else {
                None
            },
        };
    }

    let unclamped_pos = (input.pos.0 + displacement.0, input.pos.1 + displacement.1);
    let pos = (
        unclamped_pos.0.clamp(0.5, input.pitch_length - 0.5),
        unclamped_pos.1.clamp(0.5, input.pitch_width - 0.5),
    );
    if pos.0 != unclamped_pos.0 {
        velocity.0 = 0.0;
    }
    if pos.1 != unclamped_pos.1 {
        velocity.1 = 0.0;
    }
    let distance_covered = distance(input.pos, pos);
    let facing_direction = if distance_covered > 0.1 {
        Some(angle_between_points(input.pos, pos))
    } else {
        None
    };
    PlayerMotionOutput {
        pos,
        unclamped_pos,
        velocity,
        distance_covered,
        facing_direction,
    }
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
    boundary: PitchBoundaryKind,
    boundary_point: (f64, f64),
    pitch_length: f64,
    possession_team_home: bool,
    attacking_right: bool,
) -> (&'static str, bool) {
    let restart_home = !possession_team_home;
    if boundary == PitchBoundaryKind::TouchLine {
        return ("throw_in", restart_home);
    }
    let attacking_goal_x = if attacking_right { pitch_length } else { 0.0 };
    if (boundary_point.0 - attacking_goal_x).abs() <= 1e-6 {
        ("goal_kick", restart_home)
    } else {
        ("corner", restart_home)
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

    #[test]
    fn elite_speed_keeps_a_diminishing_bonus_above_99() {
        let speed_99 = player_speed(99, 5.5, 2.5);
        let speed_130 = player_speed(130, 5.5, 2.5);
        let speed_220 = player_speed(220, 5.5, 2.5);

        assert!(speed_130 > speed_99);
        assert!(speed_220 > speed_130);
        assert!(speed_220 < 6.1);
    }

    #[test]
    fn motion_accelerates_from_rest_instead_of_jumping_to_cruise_speed() {
        let output = advance_player_motion(&PlayerMotionInput {
            pos: (20.0, 34.0),
            target: (80.0, 34.0),
            velocity: (0.0, 0.0),
            speed_ability: 99,
            desired_speed: 5.0,
            acceleration_scale: 1.0,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert!(output.velocity.0 > 0.0);
        assert!(output.velocity.0 < 5.0);
        assert!(output.distance_covered < output.velocity.0);
    }

    #[test]
    fn fractional_motion_preserves_the_requested_tick_budget() {
        let input = PlayerMotionInput {
            pos: (20.0, 30.0),
            target: (80.0, 30.0),
            velocity: (2.0, 0.0),
            speed_ability: 80,
            desired_speed: 6.0,
            acceleration_scale: 1.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };

        let stopped = advance_player_motion_fraction(&input, 0.0);
        let half = advance_player_motion_fraction(&input, 0.5);
        let full = advance_player_motion(&input);

        assert_eq!(stopped.pos, input.pos);
        assert_eq!(stopped.velocity, input.velocity);
        assert_eq!(stopped.distance_covered, 0.0);
        assert!(half.distance_covered > 0.0);
        assert!(half.distance_covered < full.distance_covered);
        assert!(half.distance_covered <= player_speed(80, 8.0, 2.5) * 0.5);
    }

    #[test]
    fn motion_brakes_before_reversing_a_full_turn() {
        let output = advance_player_motion(&PlayerMotionInput {
            pos: (50.0, 34.0),
            target: (10.0, 34.0),
            velocity: (4.5, 0.0),
            speed_ability: 99,
            desired_speed: 5.0,
            acceleration_scale: 1.0,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert!(output.pos.0 > 50.0);
        assert!(output.velocity.0 > -1.0);
        assert!(output.velocity.0 > -5.0);
    }

    #[test]
    fn motion_stops_at_a_nearby_target_without_overshooting() {
        let output = advance_player_motion(&PlayerMotionInput {
            pos: (50.0, 34.0),
            target: (52.0, 34.0),
            velocity: (4.0, 0.0),
            speed_ability: 99,
            desired_speed: 5.0,
            acceleration_scale: 1.0,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert_eq!(output.pos, (52.0, 34.0));
        assert_eq!(output.velocity, (0.0, 0.0));
    }

    #[test]
    fn boundary_crossing_selects_the_first_line_on_a_diagonal_path() {
        let crossing = segment_pitch_boundary_crossing((101.0, 65.0), (110.0, 72.0), 105.0, 68.0)
            .expect("the path must leave the pitch");

        assert_eq!(crossing.kind, PitchBoundaryKind::TouchLine);
        assert_eq!(crossing.point.1, 68.0);
        assert!(crossing.point.0 < 105.0);
    }

    #[test]
    fn restart_rule_distinguishes_goal_kicks_corners_and_throw_ins() {
        assert_eq!(
            out_of_bounds_restart(
                PitchBoundaryKind::GoalLine,
                (105.0, 34.0),
                105.0,
                true,
                true,
            ),
            ("goal_kick", false)
        );
        assert_eq!(
            out_of_bounds_restart(PitchBoundaryKind::GoalLine, (0.0, 34.0), 105.0, true, true,),
            ("corner", false)
        );
        assert_eq!(
            out_of_bounds_restart(
                PitchBoundaryKind::TouchLine,
                (63.0, 68.0),
                105.0,
                true,
                true,
            ),
            ("throw_in", false)
        );
    }
}
