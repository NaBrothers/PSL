use crate::pass_value::receiver_pressure;
use crate::physics::distance;
use crate::physics::smoothstep;
use crate::position_value::{position_value, PositionValueInput};
use crate::shot_quality::{
    shot_quality_at, ShotQualityCache, ShotQualityCacheKey, ShotQualityInput,
};

#[derive(Debug, Clone)]
pub struct StateValueInput<'a> {
    pub pos: (f64, f64),
    pub player_index: usize,
    pub player_team_home: bool,
    pub tick: i32,
    pub finishing: f64,
    pub long_shot: f64,
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Debug, Clone)]
pub struct PassReceiveValueInput<'a> {
    pub pos: (f64, f64),
    pub receiver_index: usize,
    pub receiver_team_home: bool,
    pub tick: i32,
    pub finishing: f64,
    pub long_shot: f64,
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub receiver_goal_type: Option<&'a str>,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

pub fn shot_quality_cache_key(
    tick: i32,
    team_home: bool,
    player_index: usize,
    pos: (f64, f64),
    attacking_right: bool,
) -> ShotQualityCacheKey {
    ShotQualityCacheKey {
        tick,
        team_home,
        player_index,
        x10: (pos.0 * 10.0).round() as i64,
        y10: (pos.1 * 10.0).round() as i64,
        attacking_right,
    }
}

#[derive(Debug, Clone, Copy)]
pub struct PassReceiveValueBreakdown {
    pub value: f64,
    pub spatial: f64,
    pub progress: f64,
    pub outlet: f64,
    pub shot: f64,
    pub wide_creation: f64,
    pub inside_arrival: f64,
    pub second_line_arrival: f64,
    pub receiver_goal_arrival: f64,
    pub pressure: f64,
    pub centrality: f64,
    pub width_value: f64,
    pub target_width: f64,
    pub anchor_width: f64,
    pub base_progress: f64,
    pub box_presence: f64,
}

pub fn receiver_goal_arrival_space(
    goal_type: Option<&str>,
    goal_target: Option<(f64, f64)>,
    goal_value_raw: f64,
    target: (f64, f64),
    target_progress: f64,
    centrality: f64,
    pressure: f64,
) -> f64 {
    let Some(goal_type) = goal_type else {
        return 0.0;
    };
    let goal_target = goal_target.unwrap_or(target);
    let goal_fit = (1.0 - distance(target, goal_target) / 15.0).max(0.0);
    let goal_value = (goal_value_raw * 4.0).clamp(0.0, 1.0);
    let low_pressure = 1.0 - smoothstep(0.35, 0.82, pressure);

    if goal_type == "arc_arrival_for_cutback" {
        return goal_fit
            * goal_value
            * smoothstep(0.62, 0.84, target_progress)
            * smoothstep(0.46, 0.88, centrality)
            * low_pressure;
    }

    if goal_type == "attack_far_post" {
        return goal_fit
            * goal_value
            * smoothstep(0.78, 0.94, target_progress)
            * smoothstep(0.28, 0.76, centrality)
            * low_pressure;
    }

    0.0
}

pub fn state_value(input: &StateValueInput<'_>) -> f64 {
    let tm_positions_without_player: Vec<(f64, f64)> = input
        .teammate_positions
        .iter()
        .filter(|(idx, _, _)| *idx != input.player_index)
        .map(|(_, x, y)| (*x, *y))
        .collect();
    let spatial = position_value(&PositionValueInput {
        x: input.pos.0,
        y: input.pos.1,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        opponent_positions: input.opponent_positions,
        teammate_positions: &tm_positions_without_player,
        runner_formation_pos: None,
    });
    let shot = shot_quality_at(&ShotQualityInput {
        x: input.pos.0,
        y: input.pos.1,
        finishing: input.finishing,
        long_shot: input.long_shot,
        opponents: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.map(|_| {
            shot_quality_cache_key(
                input.tick,
                input.player_team_home,
                input.player_index,
                input.pos,
                input.attacking_right,
            )
        }),
    });
    let progress = if input.attacking_right {
        input.pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.pos.0) / input.pitch_length
    };

    let mut outlet: f64 = 0.0;
    for (idx, x, y) in input.teammate_positions {
        if *idx == input.player_index || input.teammate_goalkeeper_indices.contains(idx) {
            continue;
        }
        let tm_pos = (*x, *y);
        let d = distance(input.pos, tm_pos);
        if d > 45.0 {
            continue;
        }
        let outlet_pv = position_value(&PositionValueInput {
            x: *x,
            y: *y,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            opponent_positions: input.opponent_positions,
            teammate_positions: &tm_positions_without_player,
            runner_formation_pos: None,
        });
        outlet = outlet.max(outlet_pv * (1.0 - d / 55.0).max(0.2));
    }

    (spatial * 0.46 + progress * 0.18 + outlet * 0.10 + shot * 2.05).clamp(0.01, 1.2)
}

pub fn pass_receive_value_breakdown(
    input: &PassReceiveValueInput<'_>,
) -> PassReceiveValueBreakdown {
    let tm_positions_without_receiver: Vec<(f64, f64)> = input
        .teammate_positions
        .iter()
        .filter(|(idx, _, _)| *idx != input.receiver_index)
        .map(|(_, x, y)| (*x, *y))
        .collect();
    let spatial = position_value(&PositionValueInput {
        x: input.pos.0,
        y: input.pos.1,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        opponent_positions: input.opponent_positions,
        teammate_positions: &tm_positions_without_receiver,
        runner_formation_pos: None,
    });
    let shot = shot_quality_at(&ShotQualityInput {
        x: input.pos.0,
        y: input.pos.1,
        finishing: input.finishing,
        long_shot: input.long_shot,
        opponents: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.map(|_| {
            shot_quality_cache_key(
                input.tick,
                input.receiver_team_home,
                input.receiver_index,
                input.pos,
                input.attacking_right,
            )
        }),
    });
    let progress = if input.attacking_right {
        input.pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.pos.0) / input.pitch_length
    };
    let pressure = receiver_pressure(input.pos, input.opponent_positions);
    let centrality =
        1.0 - ((input.pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let width_value = 1.0 - centrality;
    let target_width = (input.pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let anchor_width =
        (input.receiver_anchor.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length
    };
    let inside_arrival = smoothstep(0.64, 0.84, progress)
        * smoothstep(0.38, 0.76, centrality)
        * (1.0 - smoothstep(0.86, 0.96, progress))
        * smoothstep(0.12, 0.50, (anchor_width - target_width).max(0.0))
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let second_line_arrival = smoothstep(0.64, 0.84, progress)
        * smoothstep(0.42, 0.84, centrality)
        * (1.0 - smoothstep(0.84, 0.95, progress))
        * smoothstep(0.04, 0.24, (progress - base_progress).max(0.0))
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let receiver_goal_arrival = receiver_goal_arrival_space(
        input.receiver_goal_type,
        input.receiver_goal_target,
        input.receiver_goal_value,
        input.pos,
        progress,
        centrality,
        pressure,
    );
    let mut wide_creation = smoothstep(0.56, 0.78, progress)
        * smoothstep(0.38, 0.72, width_value)
        * (1.0 - smoothstep(0.35, 0.78, pressure));
    let mut box_presence: f64 = 0.0;
    for (idx, x, y) in input.teammate_positions {
        if *idx == input.receiver_index || input.teammate_goalkeeper_indices.contains(idx) {
            continue;
        }
        let tm_progress = if input.attacking_right {
            *x / input.pitch_length
        } else {
            (input.pitch_length - *x) / input.pitch_length
        };
        if tm_progress > 0.74 {
            let tm_centrality =
                1.0 - ((*y - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
            box_presence = box_presence.max(tm_centrality);
        }
    }
    wide_creation *= 0.55 + 0.45 * smoothstep(0.18, 0.70, box_presence);

    let mut outlet: f64 = 0.0;
    for (idx, x, y) in input.teammate_positions {
        if *idx == input.receiver_index || input.teammate_goalkeeper_indices.contains(idx) {
            continue;
        }
        let tm_pos = (*x, *y);
        let d = distance(input.pos, tm_pos);
        if d > 35.0 {
            continue;
        }
        let outlet_pv = position_value(&PositionValueInput {
            x: *x,
            y: *y,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            opponent_positions: input.opponent_positions,
            teammate_positions: &tm_positions_without_receiver,
            runner_formation_pos: None,
        });
        outlet = outlet.max(outlet_pv * (1.0 - d / 45.0).max(0.15));
    }

    let value = (spatial * 0.40
        + progress * 0.24
        + outlet * 0.12
        + shot * 2.15
        + wide_creation * 0.095
        + inside_arrival * 0.045
        + second_line_arrival * 0.040
        + receiver_goal_arrival * 0.075
        - pressure * 0.16)
        .clamp(0.01, 1.2);

    PassReceiveValueBreakdown {
        value,
        spatial,
        progress,
        outlet,
        shot,
        wide_creation,
        inside_arrival,
        second_line_arrival,
        receiver_goal_arrival,
        pressure,
        centrality,
        width_value,
        target_width,
        anchor_width,
        base_progress,
        box_presence,
    }
}

pub fn pass_receive_value(input: &PassReceiveValueInput<'_>) -> f64 {
    pass_receive_value_breakdown(input).value
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn advanced_state_is_more_valuable() {
        let opponents = [(82.0, 30.0), (82.0, 38.0)];
        let teammates = [(1, 55.0, 34.0), (2, 74.0, 24.0)];
        let deep = state_value(&StateValueInput {
            pos: (45.0, 34.0),
            player_index: 1,
            finishing: 0.76,
            long_shot: 0.72,
            player_team_home: true,
            tick: 0,
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            shot_quality_cache: None,
        });
        let advanced = state_value(&StateValueInput {
            pos: (78.0, 34.0),
            player_index: 1,
            finishing: 0.76,
            long_shot: 0.72,
            player_team_home: true,
            tick: 0,
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            shot_quality_cache: None,
        });
        assert!(advanced > deep);
    }
}
