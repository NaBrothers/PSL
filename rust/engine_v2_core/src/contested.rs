use crate::physics::{distance, player_speed};

#[derive(Clone, Copy, Debug)]
pub struct ContestedOwnerPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedOwnerInput<'a> {
    pub ball_pos: (f64, f64),
    pub contest_radius: f64,
    pub contested_ticks: i32,
    pub home_players: &'a [ContestedOwnerPlayerInput],
    pub away_players: &'a [ContestedOwnerPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedOwnerOutput {
    pub winner_code: Option<u8>,
    pub player_index: Option<usize>,
    pub distance: f64,
    pub immediate_win: bool,
    pub forced_win: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTargetPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub is_goalkeeper: bool,
    pub is_stunned: bool,
    pub speed: i32,
    pub iq: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTargetsInput<'a> {
    pub ball_pos: (f64, f64),
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub contested_race_radius: f64,
    pub players: &'a [ContestedTargetPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTargetOutput {
    pub index: usize,
    pub target: (f64, f64),
    pub intent_code: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTickInput {
    pub position: (f64, f64),
    pub loose_velocity: (f64, f64),
    pub contested_ticks: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTickOutput {
    pub position: (f64, f64),
    pub loose_velocity: (f64, f64),
    pub contested_ticks: i32,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn resolve_contested_owner(input: &ContestedOwnerInput<'_>) -> ContestedOwnerOutput {
    let mut winner_code = None;
    let mut player_index = None;
    let mut best_dist = f64::INFINITY;

    for player in input.home_players {
        let d = distance(player.pos, input.ball_pos);
        if d < best_dist {
            best_dist = d;
            player_index = Some(player.index);
            winner_code = Some(0);
        }
    }
    for player in input.away_players {
        let d = distance(player.pos, input.ball_pos);
        if d < best_dist {
            best_dist = d;
            player_index = Some(player.index);
            winner_code = Some(1);
        }
    }

    let immediate_win = winner_code.is_some() && best_dist < input.contest_radius;
    let forced_win = !immediate_win && winner_code.is_some() && input.contested_ticks > 5;
    ContestedOwnerOutput {
        winner_code: if immediate_win || forced_win {
            winner_code
        } else {
            None
        },
        player_index: if immediate_win || forced_win {
            player_index
        } else {
            None
        },
        distance: best_dist,
        immediate_win,
        forced_win,
    }
}

pub fn tick_contested_ball(input: &ContestedTickInput) -> ContestedTickOutput {
    let contested_ticks = input.contested_ticks + 1;
    let (vx, vy) = input.loose_velocity;
    if vx.abs() > 0.01 || vy.abs() > 0.01 {
        ContestedTickOutput {
            position: (input.position.0 + vx, input.position.1 + vy),
            loose_velocity: (vx * 0.74, vy * 0.74),
            contested_ticks,
        }
    } else {
        ContestedTickOutput {
            position: input.position,
            loose_velocity: (0.0, 0.0),
            contested_ticks,
        }
    }
}

fn contested_target_for_player(
    input: &ContestedTargetsInput<'_>,
    player: &ContestedTargetPlayerInput,
) -> Option<ContestedTargetOutput> {
    if player.is_stunned {
        return None;
    }
    if player.is_goalkeeper {
        return Some(ContestedTargetOutput {
            index: player.index,
            target: player.tactical_anchor,
            intent_code: 0,
        });
    }

    let dist_to_ball = distance(player.pos, input.ball_pos);
    let speed = player_speed(player.speed, input.player_max_speed, input.player_min_speed);
    let nearby_teammates = input
        .players
        .iter()
        .filter(|teammate| {
            teammate.index != player.index
                && !teammate.is_goalkeeper
                && distance(teammate.pos, input.ball_pos) < dist_to_ball + 1.5
        })
        .count();
    let iq = player.iq / 100.0;
    let race_reach =
        input.contested_race_radius * (0.84 + 0.22 * speed / input.player_max_speed.max(0.1));
    let mut first_ball_value = (1.0 - dist_to_ball / race_reach.max(1.0)).max(0.0);
    first_ball_value = first_ball_value * first_ball_value * (3.0 - 2.0 * first_ball_value);
    let contest_score =
        first_ball_value * (1.08 + 0.34 * iq) / (1.0 + nearby_teammates as f64 * 0.35);

    let support_pos = pitch_clamp(
        (
            player.tactical_anchor.0 * 0.88 + input.ball_pos.0 * 0.12,
            player.tactical_anchor.1 * 0.90 + input.ball_pos.1 * 0.10,
        ),
        input.pitch_length,
        input.pitch_width,
    );
    let support_dist = distance(player.pos, support_pos);
    let support_score = 0.05
        + (nearby_teammates as f64 * 0.08).min(0.24)
        + (support_dist / 80.0).min(0.08)
        + (1.0 - first_ball_value) * 0.08;

    Some(ContestedTargetOutput {
        index: player.index,
        target: if contest_score > support_score {
            input.ball_pos
        } else {
            support_pos
        },
        intent_code: u8::from(contest_score > support_score),
    })
}

pub fn select_contested_targets_into(
    input: &ContestedTargetsInput<'_>,
    output: &mut [ContestedTargetOutput],
) -> usize {
    assert!(
        output.len() >= input.players.len(),
        "contested target output buffer is too small"
    );
    let mut output_count = 0;
    for player in input.players {
        if let Some(target) = contested_target_for_player(input, player) {
            output[output_count] = target;
            output_count += 1;
        }
    }
    output_count
}

pub fn select_contested_targets(input: &ContestedTargetsInput<'_>) -> Vec<ContestedTargetOutput> {
    let mut outputs = Vec::with_capacity(input.players.len());
    for player in input.players {
        if let Some(target) = contested_target_for_player(input, player) {
            outputs.push(target);
        }
    }
    outputs
}
