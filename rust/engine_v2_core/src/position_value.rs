use crate::physics::{distance, smoothstep};

#[derive(Debug, Clone)]
pub struct PositionValueInput<'a> {
    pub x: f64,
    pub y: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(f64, f64)],
    pub runner_formation_pos: Option<(f64, f64)>,
}

#[derive(Debug, Clone)]
pub struct DefensivePositionValueInput<'a> {
    pub pos: (f64, f64),
    pub ball_pos: (f64, f64),
    pub own_goal_x: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attackers: &'a [(f64, f64)],
    pub teammates: &'a [(f64, f64)],
    pub formation_pos: (f64, f64),
}

pub fn protection_value(pos: (f64, f64), ball_pos: (f64, f64), own_goal_x: f64) -> f64 {
    let ball_to_goal_x = own_goal_x - ball_pos.0;
    let pos_to_goal_x = own_goal_x - pos.0;
    if ball_to_goal_x.abs() < 1.0 {
        return 0.5;
    }
    let coverage = pos_to_goal_x / ball_to_goal_x;
    if coverage < 0.0 || coverage > 1.0 {
        return 0.2;
    }
    0.4 + 0.6 * (1.0 - (coverage - 0.4).abs() * 2.0)
}

pub fn position_value(input: &PositionValueInput<'_>) -> f64 {
    let x = input.x;
    let y = input.y;
    let length = input.pitch_length;
    let width = input.pitch_width;

    let x_progress = if input.attacking_right {
        x / length
    } else {
        1.0 - (x / length)
    };

    let goal_proximity = 0.1 + 0.9 * x_progress.powf(1.3);

    let mut opp_count = 0.0;
    for (ox, oy) in input.opponent_positions {
        let dx = x - ox;
        let dy = y - oy;
        let d2 = dx * dx + dy * dy;
        if d2 < 225.0 {
            let d = d2.sqrt();
            opp_count += (1.0 - d / 15.0).powf(0.7);
        }
    }
    let defender_weight = if x_progress > 0.7 { 1.2 } else { 0.8 };
    let space_factor = 1.0 / (1.0 + opp_count * defender_weight);

    let mut tm_count = 0.0;
    for (tx, ty) in input.teammate_positions {
        let dx = x - tx;
        let dy = y - ty;
        if dx * dx + dy * dy < 64.0 {
            tm_count += 1.0;
        }
    }
    let crowding_factor = 1.0 / (1.0 + tm_count * 0.25);

    let goal_y = width / 2.0;
    let dist_to_goal = if input.attacking_right {
        distance((x, y), (length, goal_y))
    } else {
        distance((x, y), (0.0, goal_y))
    };
    let box_danger = 1.0 - smoothstep(12.0, 24.0, dist_to_goal);
    let shot_zone_bonus = 0.86 + 0.64 * box_danger;

    let goal_x = if input.attacking_right { length } else { 0.0 };
    let dx_to_goal = goal_x - x;
    let dy_to_goal = goal_y - y;
    let dist_to_goal_center = (dx_to_goal * dx_to_goal + dy_to_goal * dy_to_goal).sqrt();
    let mut zone_weight = if dist_to_goal_center > 1.0 {
        let directness = dx_to_goal.abs() / dist_to_goal_center;
        0.3 + 0.7 * directness
    } else {
        1.0
    };

    if x_progress > 0.85 {
        let y_center_dist = (y - width / 2.0).abs() / (width / 2.0);
        if y_center_dist > 0.5 {
            let mut box_presence: f64 = 0.0;
            for (tx, ty) in input.teammate_positions {
                let tm_progress = if input.attacking_right {
                    tx / length
                } else {
                    1.0 - (tx / length)
                };
                if tm_progress > 0.78 {
                    let centrality = 1.0 - ((ty - width / 2.0).abs() / (width / 2.0)).min(1.0);
                    box_presence = box_presence.max(centrality);
                }
            }
            let creation_value = smoothstep(0.20, 0.75, box_presence);
            zone_weight *= 0.40 + 0.38 * creation_value;
        }
    }

    if dist_to_goal > 28.0 {
        zone_weight *= 0.72 + 0.28 * (1.0 - smoothstep(28.0, 52.0, dist_to_goal));
    }

    let mut value = goal_proximity * space_factor * crowding_factor * shot_zone_bonus * zone_weight;

    if let Some((rx, ry)) = input.runner_formation_pos {
        let role_dist = distance((x, y), (rx, ry));
        let role_distance_factor = (1.0 - role_dist / 30.0).max(0.2);
        value *= role_distance_factor;
    }

    value.clamp(0.01, 1.0)
}

pub fn defensive_position_value(input: &DefensivePositionValueInput<'_>) -> f64 {
    let (px, py) = input.pos;
    let width = input.pitch_width;
    let mut value = protection_value(input.pos, input.ball_pos, input.own_goal_x);
    let goal_y = width / 2.0;
    let ball_goal_dist = distance(input.ball_pos, (input.own_goal_x, goal_y));
    let box_danger = 1.0 - smoothstep(20.0, 42.0, ball_goal_dist);
    let pos_goal_dist = distance(input.pos, (input.own_goal_x, goal_y));
    let centrality = 1.0 - ((py - goal_y).abs() / (width / 2.0)).min(1.0);
    let box_cover = (1.0 - smoothstep(10.0, 28.0, pos_goal_dist)) * (0.45 + 0.55 * centrality);
    value *= 1.0 + box_danger * box_cover * 0.65;

    let shot_dx = input.own_goal_x - input.ball_pos.0;
    let shot_dy = goal_y - input.ball_pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    if shot_len > 1.0 {
        let nx = shot_dx / shot_len;
        let ny = shot_dy / shot_len;
        let relx = px - input.ball_pos.0;
        let rely = py - input.ball_pos.1;
        let proj = relx * nx + rely * ny;
        if proj > 1.0 && proj < shot_len - 1.0 {
            let perp = (relx * ny - rely * nx).abs();
            let lane_value = 1.0 - smoothstep(2.4, 9.0, perp);
            let lane_depth = 1.0 - ((proj / shot_len - 0.38).abs() / 0.46).min(1.0);
            let ball_centrality =
                1.0 - ((input.ball_pos.1 - goal_y).abs() / (width / 2.0)).min(1.0);
            let shot_lane_threat =
                (1.0 - smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * ball_centrality);
            value *= 1.0 + shot_lane_threat * lane_value * (0.42 + 0.58 * lane_depth) * 0.86;
        }
    }

    let form_dist = distance(input.pos, input.formation_pos);
    let shape_factor = (1.0 - form_dist / 28.0).max(0.25);
    value *= 0.55 + 0.45 * shape_factor;

    if !input.attackers.is_empty() {
        let nearest_att = input
            .attackers
            .iter()
            .min_by(|a, b| {
                let da = distance(input.pos, **a);
                let db = distance(input.pos, **b);
                da.partial_cmp(&db).unwrap()
            })
            .copied()
            .unwrap();
        let att_dist = distance(input.pos, nearest_att);
        let mark_factor = (1.0 - (att_dist - 4.0).abs() / 18.0).max(0.35);
        value *= 0.70 + 0.30 * mark_factor;

        let dx = nearest_att.0 - input.ball_pos.0;
        let dy = nearest_att.1 - input.ball_pos.1;
        let seg_len = (dx * dx + dy * dy).sqrt();
        if seg_len > 1.0 {
            let nx = dx / seg_len;
            let ny = dy / seg_len;
            let relx = px - input.ball_pos.0;
            let rely = py - input.ball_pos.1;
            let proj = relx * nx + rely * ny;
            if proj > 1.0 && proj < seg_len - 1.0 {
                let perp = (relx * ny - rely * nx).abs();
                let lane_factor = (1.0 - perp / 10.0).max(0.0);
                value *= 1.0 + 0.25 * lane_factor;
            }
        }
    }

    let mut crowd = 0.0;
    for teammate in input.teammates {
        let d = distance(input.pos, *teammate);
        if d < 12.0 {
            crowd += 1.0 - d / 12.0;
        }
    }
    value *= 1.0 / (1.0 + crowd * 0.75);

    let ball_dist = distance(input.pos, input.ball_pos);
    if ball_dist < 6.0 {
        value *= 0.94;
    }

    value.clamp(0.01, 1.2)
}

pub fn receive_reachability(
    target_pos: (f64, f64),
    runner_pos: (f64, f64),
    runner_speed: f64,
    opponent_positions: &[(f64, f64)],
    opponent_speeds: &[f64],
    ball_pos: (f64, f64),
    ball_speed: f64,
    receive_reachability_scale: f64,
) -> f64 {
    let dist_runner = distance(runner_pos, target_pos);
    let time_runner = dist_runner / runner_speed.max(0.1);
    let _time_ball = distance(ball_pos, target_pos) / ball_speed.max(0.1);

    let mut time_def = f64::INFINITY;
    for (idx, opponent_pos) in opponent_positions.iter().enumerate() {
        let d = distance(*opponent_pos, target_pos);
        let opp_speed = opponent_speeds.get(idx).copied().unwrap_or(4.0);
        let t = d / opp_speed.max(0.1);
        if t < time_def {
            time_def = t;
        }
    }

    let advantage = time_def - time_runner;
    (0.5 + advantage * receive_reachability_scale).clamp(0.0, 1.0)
}

pub fn space_creation_value(
    target_pos: (f64, f64),
    opponent_positions: &[(f64, f64)],
    space_creation_radius: f64,
) -> f64 {
    let mut drawn_defenders = 0;
    for opponent_pos in opponent_positions {
        if distance(*opponent_pos, target_pos) < space_creation_radius {
            drawn_defenders += 1;
        }
    }
    (1.0 + drawn_defenders as f64 * 0.1).min(1.3)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn central_advanced_space_is_more_valuable_than_deep_space() {
        let opponents = [(82.0, 28.0), (82.0, 40.0)];
        let teammates = [(70.0, 34.0), (78.0, 18.0)];
        let deep = position_value(&PositionValueInput {
            x: 35.0,
            y: 34.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            opponent_positions: &opponents,
            teammate_positions: &teammates,
            runner_formation_pos: None,
        });
        let advanced = position_value(&PositionValueInput {
            x: 76.0,
            y: 34.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            opponent_positions: &opponents,
            teammate_positions: &teammates,
            runner_formation_pos: None,
        });
        assert!(advanced > deep);
    }

    #[test]
    fn role_distance_decay_lowers_far_runner_value() {
        let opponents = [(82.0, 28.0), (82.0, 40.0)];
        let teammates = [(70.0, 34.0)];
        let no_role = position_value(&PositionValueInput {
            x: 80.0,
            y: 34.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            opponent_positions: &opponents,
            teammate_positions: &teammates,
            runner_formation_pos: None,
        });
        let role_limited = position_value(&PositionValueInput {
            x: 80.0,
            y: 34.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            opponent_positions: &opponents,
            teammate_positions: &teammates,
            runner_formation_pos: Some((45.0, 34.0)),
        });
        assert!(role_limited < no_role);
    }
}
