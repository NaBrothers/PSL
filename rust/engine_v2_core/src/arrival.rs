use crate::goalkeeper::{compute_gk_save_probability_for_attributes, GkSaveAttributes};
use crate::match_flow::{player_move_tick, PlayerMoveTickInput};
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
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassArrivalInput<'a> {
    pub flight_origin: (f64, f64),
    pub target_pos: (f64, f64),
    pub flight_ticks_total: f64,
    pub flight_speed: f64,
    pub passer_team_is_receiver_team: bool,
    pub contest_radius: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
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
    pub defensive_interference: f64,
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
    flight_ticks: f64,
    team_side_is_passer: bool,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
    target_occupation_weight: f64,
) -> (f64, f64) {
    if !player.can_arrive {
        return (f64::INFINITY, f64::INFINITY);
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
    let movement_target = if !team_side_is_passer {
        target
    } else if player.is_intended {
        player.target_pos
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
    let full_ticks = flight_ticks.max(0.0).floor() as i32;
    for _ in 0..full_ticks {
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
    let fractional_tick = flight_ticks.max(0.0) - full_ticks as f64;
    if fractional_tick > 1e-9 {
        let movement = crate::match_flow::player_move_tick_fraction(
            &PlayerMoveTickInput {
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
            },
            fractional_tick,
        );
        projected_pos = movement.pos;
    }
    let effective_dist = distance(projected_pos, target);
    let occupation_weight = target_occupation_weight.max(0.0) * (1.0 - 0.55 * committed_run);
    let mut score = effective_dist + raw_dist * occupation_weight;
    if player.is_intended {
        score *= 0.58;
    }
    (score, effective_dist)
}

fn pass_control_strength(contact_distance: f64, control_radius: f64) -> f64 {
    if contact_distance.is_infinite() || contact_distance > control_radius * 1.45 {
        return 0.0;
    }
    let scale = (control_radius * 1.55).max(0.1);
    1.0 / (1.0 + (contact_distance.max(0.0) / scale).powi(2))
}

fn arrival_control_radius(
    player: ArrivalPlayerInput,
    target: (f64, f64),
    contest_radius: f64,
    pitch_length: f64,
    pitch_width: f64,
) -> f64 {
    let physical_control_radius = contest_radius.min(1.35);
    let own_goal_x = if player.pos.0 <= pitch_length * 0.5 {
        0.0
    } else {
        pitch_length
    };
    let in_penalty_area =
        (target.0 - own_goal_x).abs() <= 16.5 && (target.1 - pitch_width * 0.5).abs() <= 20.2;
    if !player.is_goalkeeper {
        return physical_control_radius;
    }
    if in_penalty_area {
        physical_control_radius.max(1.8)
    } else {
        physical_control_radius
    }
}

fn arrival_control_strength(
    player: ArrivalPlayerInput,
    contact_distance: f64,
    target: (f64, f64),
    contest_radius: f64,
    pitch_length: f64,
    pitch_width: f64,
) -> f64 {
    let control_radius =
        arrival_control_radius(player, target, contest_radius, pitch_length, pitch_width);
    let base_control = pass_control_strength(contact_distance, control_radius);
    if player.is_goalkeeper
        && control_radius > contest_radius.min(1.35)
        && contact_distance <= control_radius * 1.45
    {
        let hand_control = 1.0 - (1.0 - base_control) * 0.12;
        let secure_reach = 1.0
            - smoothstep(
                control_radius * 0.35,
                control_radius,
                contact_distance.max(0.0),
            );
        (hand_control + 0.06 * secure_reach).min(1.0)
    } else {
        base_control
    }
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
    flight_ticks: f64,
    team_side_is_passer: bool,
    player_max_speed_value: f64,
    player_min_speed_value: f64,
    target_occupation_weight: f64,
) -> (Option<usize>, f64, f64) {
    let mut best_index = None;
    let mut best_score = f64::INFINITY;
    let mut best_contact_distance = f64::INFINITY;
    for player in players {
        if player.is_passer {
            continue;
        }
        let (score, contact_distance) = pass_arrival_score(
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
            best_contact_distance = contact_distance;
            best_index = Some(player.index);
        }
    }
    (best_index, best_score, best_contact_distance)
}

pub fn resolve_first_touch(input: &FirstTouchInput) -> FirstTouchOutput {
    let technical_error = (100.0 - input.iq) / input.first_touch_error_divisor;
    let error_chance = 1.0
        - (1.0 - technical_error.clamp(0.0, 1.0))
            * (1.0 - input.defensive_interference.clamp(0.0, 1.0));
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

#[cfg(test)]
mod first_touch_tests {
    use super::{resolve_first_touch, FirstTouchInput};

    fn first_touch(defensive_interference: f64) -> super::FirstTouchOutput {
        resolve_first_touch(&FirstTouchInput {
            target_pos: (40.0, 34.0),
            iq: 82.0,
            defensive_interference,
            pitch_length: 105.0,
            pitch_width: 68.0,
            first_touch_error_divisor: 700.0,
            error_roll: 1.0,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        })
    }

    #[test]
    fn defensive_interference_increases_first_touch_error_without_replacing_technique() {
        let unopposed = first_touch(0.0);
        let pressured = first_touch(0.35);

        assert!(pressured.error_chance > unopposed.error_chance);
        assert!(pressured.error_chance < 1.0);
    }
}

pub fn resolve_pass_arrival(input: &PassArrivalInput<'_>) -> PassArrivalOutput {
    let (receiver_index, receiver_score, receiver_contact_distance) = best_arrival_player(
        input.receivers,
        input.target_pos,
        input.flight_ticks_total,
        input.passer_team_is_receiver_team,
        input.player_max_speed,
        input.player_min_speed,
        input.target_occupation_weight,
    );
    let (opponent_index, opponent_score, opponent_contact_distance) = best_arrival_player(
        input.opponents,
        input.target_pos,
        input.flight_ticks_total,
        false,
        input.player_max_speed,
        input.player_min_speed,
        input.target_occupation_weight,
    );
    let receiver_player = receiver_index
        .and_then(|index| input.receivers.iter().find(|player| player.index == index))
        .copied();
    let opponent_player = opponent_index
        .and_then(|index| input.opponents.iter().find(|player| player.index == index))
        .copied();
    let receiver_control = receiver_player
        .map(|player| {
            arrival_control_strength(
                player,
                receiver_contact_distance,
                input.target_pos,
                input.contest_radius,
                input.pitch_length,
                input.pitch_width,
            )
        })
        .unwrap_or(0.0);
    let opponent_control = opponent_player
        .map(|player| {
            arrival_control_strength(
                player,
                opponent_contact_distance,
                input.target_pos,
                input.contest_radius,
                input.pitch_length,
                input.pitch_width,
            )
        })
        .unwrap_or(0.0);
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
        contact_tick: input.flight_ticks_total.max(0.0).ceil() as i32,
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
            is_goalkeeper: false,
        }
    }

    #[test]
    fn committed_receiver_can_control_a_ball_reached_during_flight() {
        let target = (5.0, 0.0);
        let mut receiver = arrival_player(1, (0.0, 0.0), false, true);
        receiver.target_pos = target;
        receiver.current_goal_pos = Some(target);
        let passer = arrival_player(0, (-10.0, 0.0), true, false);
        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 2.0,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
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
    fn sub_tick_arrival_projects_only_the_elapsed_flight_fraction() {
        let target = (65.0, 34.0);
        let mut receiver = arrival_player(1, (50.0, 34.0), false, true);
        receiver.velocity = (-4.0, 0.0);
        receiver.target_pos = target;
        receiver.current_goal_pos = Some(target);
        let movement_input = PlayerMoveTickInput {
            pos: receiver.pos,
            velocity: receiver.velocity,
            speed_ability: receiver.speed,
            target_pos: target,
            movement_intent: "attack_run",
            state: "off_ball",
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: f64::MAX,
            pitch_width: f64::MAX,
        };
        let half_tick_pos = crate::match_flow::player_move_tick_fraction(&movement_input, 0.5).pos;
        let full_tick_pos = player_move_tick(&movement_input).pos;
        let raw_distance = distance(receiver.pos, target);
        let occupation_weight = 0.18 * (1.0 - 0.55);
        let expected_half_tick_score =
            (distance(half_tick_pos, target) + raw_distance * occupation_weight) * 0.58;
        let full_tick_score =
            (distance(full_tick_pos, target) + raw_distance * occupation_weight) * 0.58;
        let (actual_score, actual_contact_distance) =
            pass_arrival_score(receiver, target, 0.5, true, 5.5, 2.5, 0.18);

        assert!((actual_score - expected_half_tick_score).abs() < 1e-9);
        assert!((actual_contact_distance - distance(half_tick_pos, target)).abs() < 1e-9);
        assert!(
            (actual_score - full_tick_score).abs() > 1e-3,
            "a half-tick pass must not grant the receiver a complete movement tick"
        );
    }

    #[test]
    fn intended_receiver_outside_the_physical_contact_envelope_has_no_control() {
        let target = (55.0, 34.0);
        let passer = arrival_player(0, (45.0, 34.0), true, false);
        let receiver = arrival_player(1, (52.8, 34.0), false, true);
        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 0.0,
            flight_speed: 20.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[],
        });

        assert_eq!(arrival.receiver_control, 0.0);
        assert_eq!(arrival.winner_code, 2);
    }

    #[test]
    fn intended_receiver_does_not_redirect_toward_a_hidden_delivery_error() {
        let declared_target = (50.0, 34.0);
        let sampled_miss_target = (50.0, 42.0);
        let passer = arrival_player(0, (18.0, 34.0), true, false);
        let mut receiver = arrival_player(1, declared_target, false, true);
        receiver.target_pos = declared_target;
        receiver.current_goal_pos = Some(declared_target);

        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: sampled_miss_target,
            flight_ticks_total: 3.0,
            flight_speed: 12.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[],
        });

        assert_eq!(arrival.receiver_control, 0.0);
        assert_eq!(arrival.winner_code, 2);
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
            flight_ticks_total: 4.0,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
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
            flight_ticks_total: 2.0,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
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

    #[test]
    fn goalkeeper_hand_control_wins_a_reachable_penalty_area_arrival() {
        let target = (102.8, 34.0);
        let passer = arrival_player(0, (92.0, 34.0), true, false);
        let receiver = arrival_player(1, (102.8, 34.0), false, true);
        let mut goalkeeper = arrival_player(0, (101.0, 34.0), false, false);
        goalkeeper.is_passer_team = false;
        goalkeeper.is_goalkeeper = true;

        let arrival = resolve_pass_arrival(&PassArrivalInput {
            flight_origin: passer.pos,
            target_pos: target,
            flight_ticks_total: 1.0,
            flight_speed: 18.0,
            passer_team_is_receiver_team: true,
            contest_radius: 2.5,
            player_max_speed: 5.5,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
            target_occupation_weight: 0.18,
            receivers: &[passer, receiver],
            opponents: &[goalkeeper],
        });

        assert_eq!(arrival.winner_code, 1);
        assert_eq!(arrival.opponent_index, Some(goalkeeper.index));
        assert!(
            arrival.opponent_control >= arrival.receiver_control,
            "a goalkeeper already inside hand-control range must beat a marginal feet-first arrival: {arrival:?}"
        );
    }
}
