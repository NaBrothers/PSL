use crate::goalkeeper::{compute_gk_save_probability_for_attributes, GkSaveAttributes};
use crate::match_flow::{player_move_tick, player_move_tick_fraction, PlayerMoveTickInput};
use crate::physics::{distance, smoothstep};

#[derive(Clone, Copy, Debug)]
pub struct ArrivalPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub target_pos: (f64, f64),
    pub current_goal_pos: Option<(f64, f64)>,
    pub movement_intent: &'static str,
    pub speed: i32,
    pub can_arrive: bool,
    pub is_passer: bool,
    pub is_intended: bool,
    pub is_passer_team: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassArrivalInput<'a> {
    pub flight_origin: (f64, f64),
    pub target_pos: (f64, f64),
    pub flight_ticks_total: i32,
    pub flight_speed: f64,
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
    pub contact_pos: (f64, f64),
    pub contact_tick: i32,
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
    if !player.can_arrive {
        return f64::INFINITY;
    }
    let mut target_bias = 0.0;
    if player.is_intended {
        target_bias += 0.75;
    }
    target_bias += (1.0 - distance(player.target_pos, target) / 16.0).max(0.0) * 0.55;
    if let Some(goal_pos) = player.current_goal_pos {
        target_bias += (1.0 - distance(goal_pos, target) / 16.0).max(0.0) * 0.65;
    }
    let committed_run = smoothstep(0.12, 0.82, target_bias);
    let movement_target = if player.is_intended || !team_side_is_passer {
        target
    } else {
        player.current_goal_pos.unwrap_or(player.target_pos)
    };
    let movement_intent = if player.is_intended {
        "attack_run"
    } else if !team_side_is_passer {
        "contest"
    } else {
        player.movement_intent
    };
    let raw_dist = distance(player.pos, target);
    let mut projected_pos = player.pos;
    let mut projected_velocity = player.velocity;
    for _ in 0..flight_ticks.max(0) {
        let movement = player_move_tick(&PlayerMoveTickInput {
            pos: projected_pos,
            velocity: projected_velocity,
            speed_ability: player.speed,
            target_pos: movement_target,
            movement_intent,
            state: "off_ball",
            player_max_speed: player_max_speed_value,
            player_min_speed: player_min_speed_value,
            pitch_length: f64::MAX,
            pitch_width: f64::MAX,
        });
        projected_pos = movement.pos;
        projected_velocity = movement.velocity;
    }
    let effective_dist = distance(projected_pos, target);
    let occupation_weight = target_occupation_weight.max(0.0) * (1.0 - 0.55 * committed_run);
    let mut score = effective_dist + raw_dist * occupation_weight;
    if player.is_intended {
        score *= 0.58;
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

fn projected_contact_distance(
    player: ArrivalPlayerInput,
    contact_pos: (f64, f64),
    completed_ticks: i32,
    current_tick_fraction: f64,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
) -> f64 {
    if !player.can_arrive || player.is_passer {
        return f64::INFINITY;
    }

    let movement_intent = if player.is_intended {
        "attack_run"
    } else {
        "contest"
    };
    let mut projected_pos = player.pos;
    let mut projected_velocity = player.velocity;
    let movement_input = |pos, velocity| PlayerMoveTickInput {
        pos,
        velocity,
        speed_ability: player.speed,
        target_pos: contact_pos,
        movement_intent,
        state: "off_ball",
        player_max_speed: player_max_speed_value,
        player_min_speed: player_min_speed_value,
        pitch_length: f64::MAX,
        pitch_width: f64::MAX,
    };
    for _ in 0..completed_ticks.max(0) {
        let movement = player_move_tick(&movement_input(projected_pos, projected_velocity));
        projected_pos = movement.pos;
        projected_velocity = movement.velocity;
    }
    if current_tick_fraction > 0.0 {
        let movement = player_move_tick_fraction(
            &movement_input(projected_pos, projected_velocity),
            current_tick_fraction,
        );
        projected_pos = movement.pos;
    }
    distance(projected_pos, contact_pos)
}

fn best_trajectory_contact_player(
    players: &[ArrivalPlayerInput],
    contact_pos: (f64, f64),
    completed_ticks: i32,
    current_tick_fraction: f64,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
    contest_radius: f64,
) -> (Option<usize>, f64, f64) {
    let mut best_index = None;
    let mut best_distance = f64::INFINITY;
    for player in players {
        let contact_distance = projected_contact_distance(
            *player,
            contact_pos,
            completed_ticks,
            current_tick_fraction,
            player_max_speed_value,
            player_min_speed_value,
        );
        if contact_distance < best_distance {
            best_distance = contact_distance;
            best_index = Some(player.index);
        }
    }
    let control = (best_distance <= contest_radius)
        .then(|| pass_control_strength(best_distance, contest_radius))
        .unwrap_or(0.0);
    (best_index, best_distance, control)
}

fn earliest_trajectory_contact(input: &PassArrivalInput<'_>) -> Option<PassArrivalOutput> {
    let flight_ticks = input.flight_ticks_total.max(0);
    if flight_ticks <= 1 || distance(input.flight_origin, input.target_pos) <= 1e-6 {
        return None;
    }

    let mut segment_start = input.flight_origin;
    for contact_tick in 1..flight_ticks {
        let segment_end =
            crate::match_flow::tick_ball_flight(&crate::match_flow::FlightTickInput {
                origin: input.flight_origin,
                target: input.target_pos,
                ticks_elapsed: contact_tick - 1,
                ticks_total: flight_ticks,
                speed: input.flight_speed,
            })
            .position;
        let segment_distance = distance(segment_start, segment_end);
        let sample_count = (segment_distance / 0.5).ceil().max(1.0) as i32;
        for sample in 1..=sample_count {
            let tick_fraction = sample as f64 / sample_count as f64;
            let contact_pos = (
                segment_start.0 + (segment_end.0 - segment_start.0) * tick_fraction,
                segment_start.1 + (segment_end.1 - segment_start.1) * tick_fraction,
            );
            let (opponent_index, opponent_score, opponent_control) = best_trajectory_contact_player(
                input.opponents,
                contact_pos,
                contact_tick - 1,
                tick_fraction,
                input.player_max_speed,
                input.player_min_speed,
                input.contest_radius,
            );
            if opponent_control > 0.0 {
                return Some(PassArrivalOutput {
                    winner_code: 1,
                    receiver_index: None,
                    receiver_score: f64::INFINITY,
                    receiver_control: 0.0,
                    opponent_index,
                    opponent_score,
                    opponent_control,
                    loose_control: pass_loose_control_strength(0.0, opponent_control),
                    contact_pos,
                    contact_tick,
                });
            }
        }
        segment_start = segment_end;
    }
    None
}

pub fn resolve_first_touch(input: &FirstTouchInput) -> FirstTouchOutput {
    let error_chance = (100.0 - input.iq) / input.first_touch_error_divisor;
    let is_error = matches!(
        crate::execution_transition::BinaryExecutionTransition::from_success_probability(
            error_chance,
        )
        .sample(input.error_roll),
        crate::execution_transition::BinaryExecutionOutcome::Success
    );
    let loose_pos = crate::execution_transition::RectangularLooseBallTransition {
        center: input.target_pos,
        radius_x: 4.0,
        radius_y: 4.0,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    }
    .sample(input.loose_x_roll, input.loose_y_roll);
    FirstTouchOutput {
        error_chance,
        is_error,
        loose_pos,
    }
}

pub fn resolve_pass_arrival(input: &PassArrivalInput<'_>) -> PassArrivalOutput {
    if let Some(contact) = earliest_trajectory_contact(input) {
        return contact;
    }
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
        contact_pos: input.target_pos,
        contact_tick: input.flight_ticks_total.max(0),
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

#[cfg(test)]
mod tests {
    use super::*;

    fn arrival_player(
        index: usize,
        pos: (f64, f64),
        is_passer: bool,
        is_intended: bool,
    ) -> ArrivalPlayerInput {
        ArrivalPlayerInput {
            index,
            pos,
            velocity: (0.0, 0.0),
            target_pos: pos,
            current_goal_pos: Some(pos),
            movement_intent: "support",
            speed: 80,
            can_arrive: true,
            is_passer,
            is_intended,
            is_passer_team: true,
        }
    }

    #[test]
    fn committed_receiver_can_control_a_ball_reached_during_flight() {
        let target = (5.0, 0.0);
        let receiver = arrival_player(1, (0.0, 0.0), false, true);
        let passer = arrival_player(0, (-10.0, 0.0), true, false);
        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 2,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[],
        });

        assert!(
            distance(receiver.pos, target) > 2.5,
            "the receiver starts outside the legacy static contest radius"
        );
        assert_eq!(arrival.winner_code, 0);
        assert_eq!(arrival.receiver_index, Some(receiver.index));
        assert!(arrival.receiver_control > arrival.loose_control);
    }

    #[test]
    fn defender_in_a_long_lateral_pass_corridor_cuts_it_out_before_the_target() {
        let target = (52.0, 62.0);
        let passer = arrival_player(0, (52.0, 6.0), true, false);
        let receiver = arrival_player(1, target, false, true);
        let interceptor = arrival_player(7, (52.0, 34.0), false, false);

        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 4,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[interceptor],
        });

        assert_eq!(arrival.winner_code, 1);
        assert_eq!(arrival.opponent_index, Some(interceptor.index));
        assert!(arrival.opponent_control > arrival.receiver_control);
    }

    #[test]
    fn teammate_in_a_pass_corridor_does_not_shorten_the_intended_pass() {
        let target = (52.0, 62.0);
        let passer = arrival_player(0, (52.0, 6.0), true, false);
        let receiver = arrival_player(1, target, false, true);
        let supporting_teammate = arrival_player(2, (52.0, 34.0), false, false);

        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 4,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver, supporting_teammate],
            opponents: &[],
        });

        assert_eq!(arrival.winner_code, 0);
        assert_eq!(arrival.receiver_index, Some(receiver.index));
        assert_eq!(arrival.contact_pos, target);
        assert_eq!(arrival.contact_tick, 4);
    }

    #[test]
    fn defender_contests_the_destination_during_the_pass_flight() {
        let target = (90.0, 34.0);
        let passer = arrival_player(0, (74.0, 34.0), true, false);
        let receiver = arrival_player(1, (88.0, 34.0), false, true);
        let mut defender = arrival_player(7, (91.0, 37.0), false, false);
        defender.is_passer_team = false;
        defender.target_pos = (82.0, 46.0);
        defender.current_goal_pos = Some(defender.target_pos);

        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 2,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[defender],
        });

        assert!(
            arrival.opponent_control > 0.0,
            "a nearby defender must react to the destination instead of continuing away from it"
        );
        assert!(
            arrival.opponent_score < distance(defender.target_pos, target),
            "the pass flight must let the defender close the destination"
        );
    }
}
