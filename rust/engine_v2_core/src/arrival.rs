use crate::goalkeeper::{compute_gk_save_probability_for_attributes, GkSaveAttributes};
use crate::physics::{distance, player_speed, smoothstep};

#[derive(Clone, Copy, Debug)]
pub struct ArrivalPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub current_goal_pos: Option<(f64, f64)>,
    pub speed: i32,
    pub is_passer: bool,
    pub is_intended: bool,
    pub is_passer_team: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassArrivalInput<'a> {
    pub target_pos: (f64, f64),
    pub flight_ticks_total: i32,
    pub passer_team_is_receiver_team: bool,
    pub contest_radius: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub target_occupation_weight: f64,
    pub receivers: &'a [ArrivalPlayerInput],
    pub opponents: &'a [ArrivalPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct PassArrivalOutput {
    pub winner_code: u8,
    pub receiver_index: Option<usize>,
    pub receiver_score: f64,
    pub receiver_control: f64,
    pub opponent_index: Option<usize>,
    pub opponent_score: f64,
    pub opponent_control: f64,
    pub loose_control: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotArrivalInput {
    pub shot_origin: (f64, f64),
    pub shot_target: (f64, f64),
    pub on_target: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub gk_pos: (f64, f64),
    pub gk_attributes: GkSaveAttributes,
    pub save_roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotArrivalOutput {
    pub in_box: bool,
    pub save_prob: f64,
    pub outcome_code: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct ClearancePlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct ClearanceArrivalInput<'a> {
    pub target_pos: (f64, f64),
    pub home_players: &'a [ClearancePlayerInput],
    pub away_players: &'a [ClearancePlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct ClearanceArrivalOutput {
    pub winner_code: u8,
    pub player_index: Option<usize>,
    pub home_distance: f64,
    pub away_distance: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct FirstTouchInput {
    pub target_pos: (f64, f64),
    pub iq: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub first_touch_error_divisor: f64,
    pub error_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct FirstTouchOutput {
    pub error_chance: f64,
    pub is_error: bool,
    pub loose_pos: (f64, f64),
}

fn pass_arrival_score(
    player: ArrivalPlayerInput,
    target: (f64, f64),
    flight_ticks: i32,
    team_side_is_passer: bool,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
    target_occupation_weight: f64,
) -> f64 {
    let speed = player_speed(player.speed, player_max_speed_value, player_min_speed_value);
    let mut target_bias = 0.0;
    if player.is_intended {
        target_bias += 0.75;
    }
    target_bias += (1.0 - distance(player.target_pos, target) / 16.0).max(0.0) * 0.55;
    if let Some(goal_pos) = player.current_goal_pos {
        target_bias += (1.0 - distance(goal_pos, target) / 16.0).max(0.0) * 0.65;
    }
    let committed_run = smoothstep(0.12, 0.82, target_bias);
    let movement_share = 0.24 + 0.52 * committed_run;
    let raw_dist = distance(player.pos, target);
    let effective_dist = (raw_dist - speed * flight_ticks.max(0) as f64 * movement_share).max(0.0);
    let occupation_weight = target_occupation_weight.max(0.0) * (1.0 - 0.55 * committed_run);
    let mut score = effective_dist + raw_dist * occupation_weight;
    if !team_side_is_passer {
        score += target_bias.max(0.0) * 0.18;
    }
    score
}

fn pass_control_strength(score: f64, contest_radius: f64) -> f64 {
    if score.is_infinite() {
        return 0.0;
    }
    let scale = (contest_radius * 1.55).max(0.1);
    1.0 / (1.0 + (score.max(0.0) / scale).powi(2))
}

fn pass_loose_control_strength(teammate_control: f64, opponent_control: f64) -> f64 {
    let strongest = teammate_control
        .clamp(0.0, 1.0)
        .max(opponent_control.clamp(0.0, 1.0));
    let balance = 1.0 - (teammate_control.max(0.0) - opponent_control.max(0.0)).abs();
    (1.0 - strongest).max(0.0) * (0.25 + 0.20 * balance.clamp(0.0, 1.0))
}

fn best_arrival_player(
    players: &[ArrivalPlayerInput],
    target: (f64, f64),
    flight_ticks: i32,
    team_side_is_passer: bool,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
    target_occupation_weight: f64,
) -> (Option<usize>, f64) {
    let mut best_index = None;
    let mut best_score = f64::INFINITY;
    for player in players {
        if player.is_passer {
            continue;
        }
        let score = pass_arrival_score(
            *player,
            target,
            flight_ticks,
            team_side_is_passer,
            player_max_speed_value,
            player_min_speed_value,
            target_occupation_weight,
        );
        if score < best_score {
            best_score = score;
            best_index = Some(player.index);
        }
    }
    (best_index, best_score)
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn resolve_first_touch(input: &FirstTouchInput) -> FirstTouchOutput {
    let error_chance = (100.0 - input.iq) / input.first_touch_error_divisor;
    let is_error = input.error_roll < error_chance;
    let loose_pos = pitch_clamp(
        (
            input.target_pos.0 + (-4.0 + 8.0 * input.loose_x_roll),
            input.target_pos.1 + (-4.0 + 8.0 * input.loose_y_roll),
        ),
        input.pitch_length,
        input.pitch_width,
    );
    FirstTouchOutput {
        error_chance,
        is_error,
        loose_pos,
    }
}

pub fn resolve_pass_arrival(input: &PassArrivalInput<'_>) -> PassArrivalOutput {
    let (receiver_index, receiver_score) = best_arrival_player(
        input.receivers,
        input.target_pos,
        input.flight_ticks_total,
        input.passer_team_is_receiver_team,
        input.player_max_speed,
        input.player_min_speed,
        input.target_occupation_weight,
    );
    let (opponent_index, opponent_score) = best_arrival_player(
        input.opponents,
        input.target_pos,
        input.flight_ticks_total,
        false,
        input.player_max_speed,
        input.player_min_speed,
        input.target_occupation_weight,
    );
    let receiver_control = pass_control_strength(receiver_score, input.contest_radius);
    let opponent_control = pass_control_strength(opponent_score, input.contest_radius);
    let loose_control = pass_loose_control_strength(receiver_control, opponent_control);
    let winner_code = if opponent_control >= receiver_control && opponent_control >= loose_control {
        1
    } else if receiver_control >= opponent_control && receiver_control >= loose_control {
        0
    } else {
        2
    };
    PassArrivalOutput {
        winner_code,
        receiver_index,
        receiver_score,
        receiver_control,
        opponent_index,
        opponent_score,
        opponent_control,
        loose_control,
    }
}

pub fn resolve_shot_arrival(input: &ShotArrivalInput) -> ShotArrivalOutput {
    let progress = if input.attacking_right {
        input.shot_origin.0 / input.pitch_length
    } else {
        (input.pitch_length - input.shot_origin.0) / input.pitch_length
    };
    let in_box = progress > 1.0 - 16.5 / input.pitch_length
        && (input.shot_origin.1 - input.pitch_width / 2.0).abs() < 20.2;
    if !input.on_target {
        return ShotArrivalOutput {
            in_box,
            save_prob: 0.0,
            outcome_code: 0,
        };
    }
    let save_prob = compute_gk_save_probability_for_attributes(
        input.gk_attributes,
        input.gk_pos,
        input.shot_origin,
        input.shot_target,
        input.pitch_length,
    );
    ShotArrivalOutput {
        in_box,
        save_prob,
        outcome_code: if input.save_roll < save_prob { 1 } else { 2 },
    }
}

fn closest_clearance_player(
    players: &[ClearancePlayerInput],
    target: (f64, f64),
) -> (Option<usize>, f64) {
    let mut best_index = None;
    let mut best_distance = f64::INFINITY;
    for player in players {
        let d = distance(player.pos, target);
        if d < best_distance {
            best_distance = d;
            best_index = Some(player.index);
        }
    }
    (best_index, best_distance)
}

pub fn resolve_clearance_arrival(input: &ClearanceArrivalInput<'_>) -> ClearanceArrivalOutput {
    let (home_index, home_distance) =
        closest_clearance_player(input.home_players, input.target_pos);
    let (away_index, away_distance) =
        closest_clearance_player(input.away_players, input.target_pos);
    if home_distance < away_distance {
        ClearanceArrivalOutput {
            winner_code: 0,
            player_index: home_index,
            home_distance,
            away_distance,
        }
    } else {
        ClearanceArrivalOutput {
            winner_code: 1,
            player_index: away_index,
            home_distance,
            away_distance,
        }
    }
}
