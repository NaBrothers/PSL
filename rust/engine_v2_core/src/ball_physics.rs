use crate::physics::{angle_between_points, angle_diff, distance, smoothstep};

const REFERENCE_TICK_DURATION_SECONDS: f64 = 2.0;
const BALL_CONTACT_SUBSTEP_SECONDS: f64 = 0.5;
const REFERENCE_FREE_BALL_ROLLING_DECELERATION: f64 = 0.9;
const REFERENCE_FREE_BALL_DRAG: f64 = 0.04;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BallMotionState {
    pub position: (f64, f64),
    pub velocity: (f64, f64),
}

impl BallMotionState {
    pub fn stationary(position: (f64, f64)) -> Self {
        Self {
            position,
            velocity: (0.0, 0.0),
        }
    }

    pub fn speed(self) -> f64 {
        vector_length(self.velocity)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct FreeBallMotionInput {
    pub state: BallMotionState,
    pub elapsed_ticks: f64,
    pub rolling_deceleration: f64,
    pub drag: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PlayerBallContactInput {
    pub index: usize,
    pub team_home: bool,
    pub position: (f64, f64),
    pub velocity: (f64, f64),
    pub facing_direction: f64,
    pub dribbling: f64,
    pub iq: f64,
    pub speed: f64,
    pub tackling: f64,
    pub defence: f64,
    pub gk_saving: f64,
    pub gk_positioning: f64,
    pub gk_reaction: f64,
    pub can_use_hands: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BallControlClaim {
    pub player_index: Option<usize>,
    pub confidence: f64,
}

impl Default for BallControlClaim {
    fn default() -> Self {
        Self {
            player_index: None,
            confidence: 0.0,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct BallControlContest {
    pub home: BallControlClaim,
    pub away: BallControlClaim,
}

#[derive(Clone, Copy, Debug)]
pub struct BallContactTickInput<'a> {
    pub motion: BallMotionState,
    pub previous_motion: BallMotionState,
    pub previous_control: BallControlContest,
    pub players: &'a [PlayerBallContactInput],
    pub elapsed_ticks: f64,
    pub control_elapsed_seconds: f64,
    pub control_radius: f64,
    pub impulse_scale: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StableBallController {
    pub player_index: usize,
    pub team_home: bool,
    pub confidence: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct BallContactTickOutput {
    pub motion: BallMotionState,
    pub control: BallControlContest,
    pub stable_controller: Option<StableBallController>,
    pub strongest_contact: Option<StableBallController>,
}

#[derive(Clone, Copy)]
struct ContactEvaluation {
    player: PlayerBallContactInput,
    quality: f64,
    impulse_access: f64,
    relative_speed: f64,
}

fn vector_length(vector: (f64, f64)) -> f64 {
    (vector.0 * vector.0 + vector.1 * vector.1).sqrt()
}

fn vector_scale(vector: (f64, f64), scale: f64) -> (f64, f64) {
    (vector.0 * scale, vector.1 * scale)
}

fn vector_add(left: (f64, f64), right: (f64, f64)) -> (f64, f64) {
    (left.0 + right.0, left.1 + right.1)
}

fn vector_sub(left: (f64, f64), right: (f64, f64)) -> (f64, f64) {
    (left.0 - right.0, left.1 - right.1)
}

fn vector_dot(left: (f64, f64), right: (f64, f64)) -> f64 {
    left.0 * right.0 + left.1 * right.1
}

fn normalized(vector: (f64, f64)) -> (f64, f64) {
    let length = vector_length(vector);
    if length <= 1e-9 {
        (0.0, 0.0)
    } else {
        vector_scale(vector, 1.0 / length)
    }
}

fn pitch_clamp(position: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        position.0.clamp(0.0, pitch_length),
        position.1.clamp(0.0, pitch_width),
    )
}

pub fn release_ball_velocity(origin: (f64, f64), target: (f64, f64), speed: f64) -> (f64, f64) {
    vector_scale(normalized(vector_sub(target, origin)), speed.max(0.0))
}

pub fn pass_average_speed(distance: f64, configured_speed: f64, tick_duration: f64) -> f64 {
    let distance = distance.max(0.0);
    let configured_speed = configured_speed.max(0.0);
    let _tick_duration = tick_duration.max(f64::EPSILON);
    if distance <= f64::EPSILON || configured_speed <= f64::EPSILON {
        return 0.0;
    }
    configured_speed
}

pub fn ball_contact_substep_ticks(tick_duration: f64) -> f64 {
    BALL_CONTACT_SUBSTEP_SECONDS / tick_duration.max(f64::EPSILON)
}

pub fn free_ball_rolling_deceleration(tick_duration: f64) -> f64 {
    REFERENCE_FREE_BALL_ROLLING_DECELERATION
        * (tick_duration.max(0.0) / REFERENCE_TICK_DURATION_SECONDS).powi(2)
}

pub fn free_ball_drag(tick_duration: f64) -> f64 {
    REFERENCE_FREE_BALL_DRAG * tick_duration.max(0.0) / REFERENCE_TICK_DURATION_SECONDS
}

pub fn flight_terminal_velocity(
    origin: (f64, f64),
    target: (f64, f64),
    speed: f64,
    retained_speed: f64,
) -> (f64, f64) {
    release_ball_velocity(origin, target, speed * retained_speed.clamp(0.0, 1.0))
}

pub fn free_ball_unclamped_position(input: &FreeBallMotionInput) -> (f64, f64) {
    let elapsed_ticks = input.elapsed_ticks.max(0.0);
    let speed = input.state.speed();
    if elapsed_ticks <= 1e-9 || speed <= 1e-6 {
        return input.state.position;
    }
    let drag = input.drag.max(0.0);
    let deceleration = input.rolling_deceleration.max(0.0);
    let speed_after_drag = if drag <= 1e-9 {
        speed
    } else {
        speed * (-drag * elapsed_ticks).exp()
    };
    let end_speed = (speed_after_drag - deceleration * elapsed_ticks).max(0.0);
    let average_speed = 0.5 * (speed + end_speed);
    vector_add(
        input.state.position,
        vector_scale(
            normalized(input.state.velocity),
            average_speed * elapsed_ticks,
        ),
    )
}

pub fn advance_free_ball(input: &FreeBallMotionInput) -> BallMotionState {
    let elapsed_ticks = input.elapsed_ticks.max(0.0);
    if elapsed_ticks <= 1e-9 {
        return input.state;
    }
    let speed = input.state.speed();
    if speed <= 1e-6 {
        return BallMotionState::stationary(input.state.position);
    }
    let drag = input.drag.max(0.0);
    let deceleration = input.rolling_deceleration.max(0.0);
    let speed_after_drag = if drag <= 1e-9 {
        speed
    } else {
        speed * (-drag * elapsed_ticks).exp()
    };
    let end_speed = (speed_after_drag - deceleration * elapsed_ticks).max(0.0);
    let direction = normalized(input.state.velocity);
    let unclamped_position = free_ball_unclamped_position(input);
    let position = pitch_clamp(unclamped_position, input.pitch_length, input.pitch_width);
    let hit_boundary = distance(position, unclamped_position) > 1e-9;
    BallMotionState {
        position,
        velocity: if hit_boundary {
            (0.0, 0.0)
        } else {
            vector_scale(direction, end_speed)
        },
    }
}

fn closest_relative_approach(
    ball: BallMotionState,
    player: PlayerBallContactInput,
    elapsed_ticks: f64,
) -> (f64, (f64, f64), f64) {
    let relative_position = vector_sub(ball.position, player.position);
    let relative_velocity = vector_sub(ball.velocity, player.velocity);
    let velocity_squared = vector_dot(relative_velocity, relative_velocity);
    let contact_time = if velocity_squared <= 1e-9 {
        0.0
    } else {
        (-vector_dot(relative_position, relative_velocity) / velocity_squared)
            .clamp(0.0, elapsed_ticks.max(0.0))
    };
    let ball_position = vector_add(ball.position, vector_scale(ball.velocity, contact_time));
    let player_position = vector_add(player.position, vector_scale(player.velocity, contact_time));
    (
        distance(ball_position, player_position),
        ball_position,
        vector_length(relative_velocity),
    )
}

fn raw_contact_quality(
    previous_motion: BallMotionState,
    contact_velocity: (f64, f64),
    player: PlayerBallContactInput,
    elapsed_ticks: f64,
    velocity_scale: f64,
    control_radius: f64,
) -> (f64, f64, (f64, f64), f64) {
    let radius = if player.can_use_hands {
        control_radius.max(1.8)
    } else {
        control_radius.max(0.6)
    };
    let (separation, contact_position, _) =
        closest_relative_approach(previous_motion, player, elapsed_ticks);
    let relative_speed =
        vector_length(vector_sub(contact_velocity, player.velocity)) * velocity_scale;
    let proximity = 1.0 - smoothstep(radius * 0.35, radius * 1.45, separation.max(0.0));
    if proximity <= 1e-9 {
        return (0.0, 0.0, contact_position, relative_speed);
    }
    let impulse_access = 1.0 - smoothstep(radius, radius * 1.45, separation.max(0.0));
    let facing_target = angle_between_points(player.position, contact_position);
    let facing_alignment = 1.0 - angle_diff(player.facing_direction, facing_target).abs() / 180.0;
    let velocity_match = 1.0 / (1.0 + (relative_speed / 7.5).powi(2));
    let dribbling = player.dribbling.clamp(0.0, 100.0) / 100.0;
    let iq = player.iq.clamp(0.0, 100.0) / 100.0;
    let speed = player.speed.clamp(0.0, 100.0) / 100.0;
    let goalkeeper_control =
        (0.45 * player.gk_saving + 0.30 * player.gk_positioning + 0.25 * player.gk_reaction)
            .clamp(0.0, 100.0)
            / 100.0;
    let technique = if player.can_use_hands {
        goalkeeper_control
    } else {
        0.72 * dribbling + 0.28 * iq
    };
    let body_adjustment = 0.58 * speed + 0.42 * iq;
    let hand_bonus = if player.can_use_hands { 0.14 } else { 0.0 };
    let quality = proximity
        * (0.34 + 0.66 * velocity_match)
        * (0.48 + 0.52 * facing_alignment.max(0.0))
        * (0.42 + 0.42 * technique + 0.16 * body_adjustment + hand_bonus);
    (
        quality.clamp(0.0, 1.0),
        impulse_access.clamp(0.0, 1.0),
        contact_position,
        relative_speed,
    )
}

fn evaluated_contacts(input: &BallContactTickInput<'_>) -> Vec<ContactEvaluation> {
    let tick_duration = if input.elapsed_ticks > 1e-9 {
        input.control_elapsed_seconds / input.elapsed_ticks
    } else {
        REFERENCE_TICK_DURATION_SECONDS
    };
    let velocity_scale = REFERENCE_TICK_DURATION_SECONDS / tick_duration.max(f64::EPSILON);
    let mut raw = Vec::with_capacity(input.players.len());
    for player in input.players {
        let (quality, impulse_access, contact_position, relative_speed) = raw_contact_quality(
            input.previous_motion,
            input.motion.velocity,
            *player,
            input.elapsed_ticks,
            velocity_scale,
            input.control_radius,
        );
        if quality <= 1e-9 {
            continue;
        }
        let opposing_interference = input
            .players
            .iter()
            .filter(|opponent| opponent.team_home != player.team_home)
            .map(|opponent| {
                let separation = distance(opponent.position, contact_position);
                let body_access =
                    1.0 - smoothstep(input.control_radius, input.control_radius * 3.0, separation);
                let defensive_contact =
                    (0.58 * opponent.tackling + 0.42 * opponent.defence).clamp(0.0, 100.0) / 100.0;
                body_access.max(0.0) * (0.45 + 0.55 * defensive_contact)
            })
            .fold(0.0_f64, f64::max);
        raw.push(ContactEvaluation {
            player: *player,
            quality: (quality * (1.0 - 0.46 * opposing_interference)).clamp(0.0, 1.0),
            impulse_access,
            relative_speed,
        });
    }
    raw
}

fn update_claim(
    previous: BallControlClaim,
    contact: Option<ContactEvaluation>,
    elapsed_ticks: f64,
) -> BallControlClaim {
    let elapsed_ticks = elapsed_ticks.max(0.0);
    let absent_decay = (-0.72 * elapsed_ticks).exp();
    let Some(contact) = contact else {
        let confidence = previous.confidence * absent_decay;
        return BallControlClaim {
            player_index: (confidence > 0.02)
                .then_some(previous.player_index)
                .flatten(),
            confidence,
        };
    };
    let retention_decay = if previous.player_index == Some(contact.player.index) {
        0.10
    } else {
        0.28
    };
    let retained = previous.confidence * (-retention_decay * elapsed_ticks).exp();
    let relative_control = 1.0 / (1.0 + (contact.relative_speed / 5.0).powi(2));
    let exposure = 1.0 - (-1.15 * elapsed_ticks).exp();
    let gain = contact.quality * (0.34 + 0.66 * relative_control) * (1.0 - retained) * exposure;
    BallControlClaim {
        player_index: Some(contact.player.index),
        confidence: (retained + gain).clamp(0.0, 1.0),
    }
}

fn contact_adjusted_motion(
    motion: BallMotionState,
    contacts: &[ContactEvaluation],
    elapsed_ticks: f64,
    impulse_scale: f64,
) -> BallMotionState {
    let total_quality = contacts.iter().map(|contact| contact.quality).sum::<f64>();
    if total_quality <= 1e-9 {
        return motion;
    }
    let impulse_quality = contacts
        .iter()
        .map(|contact| contact.quality * contact.impulse_access)
        .sum::<f64>();
    if impulse_quality <= 1e-9 {
        return motion;
    }
    let weighted_player_velocity = contacts.iter().fold((0.0, 0.0), |velocity, contact| {
        vector_add(
            velocity,
            vector_scale(contact.player.velocity, contact.quality / total_quality),
        )
    });
    let best_technique = contacts
        .iter()
        .map(|contact| {
            if contact.player.can_use_hands {
                (0.45 * contact.player.gk_saving
                    + 0.30 * contact.player.gk_positioning
                    + 0.25 * contact.player.gk_reaction)
                    .clamp(0.0, 100.0)
                    / 100.0
            } else {
                (0.72 * contact.player.dribbling + 0.28 * contact.player.iq).clamp(0.0, 100.0)
                    / 100.0
            }
        })
        .fold(0.0_f64, f64::max);
    let contact_strength = (1.0
        - (-1.15 * impulse_quality * impulse_scale.max(0.0) * elapsed_ticks.max(0.0)).exp())
    .clamp(0.0, 0.94);
    let cushion = (0.42 - 0.28 * best_technique).clamp(0.08, 0.42);
    let player_velocity_coupling = (impulse_quality / 0.45).clamp(0.0, 1.0).powi(2);
    let desired_velocity = vector_add(
        vector_scale(motion.velocity, cushion),
        vector_scale(
            weighted_player_velocity,
            (1.0 - cushion) * player_velocity_coupling,
        ),
    );
    BallMotionState {
        position: motion.position,
        velocity: vector_add(
            vector_scale(motion.velocity, 1.0 - contact_strength),
            vector_scale(desired_velocity, contact_strength),
        ),
    }
}

pub fn resolve_ball_contacts(input: &BallContactTickInput<'_>) -> BallContactTickOutput {
    let contacts = evaluated_contacts(input);
    let tick_duration = if input.elapsed_ticks > 1e-9 {
        input.control_elapsed_seconds / input.elapsed_ticks
    } else {
        REFERENCE_TICK_DURATION_SECONDS
    };
    let velocity_scale = REFERENCE_TICK_DURATION_SECONDS / tick_duration.max(f64::EPSILON);
    let reference_elapsed_ticks = input.control_elapsed_seconds / REFERENCE_TICK_DURATION_SECONDS;
    let strongest_home = contacts
        .iter()
        .filter(|contact| contact.player.team_home)
        .copied()
        .max_by(|left, right| left.quality.total_cmp(&right.quality));
    let strongest_away = contacts
        .iter()
        .filter(|contact| !contact.player.team_home)
        .copied()
        .max_by(|left, right| left.quality.total_cmp(&right.quality));
    let control = BallControlContest {
        home: update_claim(
            input.previous_control.home,
            strongest_home,
            input.control_elapsed_seconds,
        ),
        away: update_claim(
            input.previous_control.away,
            strongest_away,
            input.control_elapsed_seconds,
        ),
    };
    let motion = contact_adjusted_motion(
        input.motion,
        &contacts,
        reference_elapsed_ticks,
        input.impulse_scale,
    );
    let strongest_contact = contacts
        .iter()
        .copied()
        .max_by(|left, right| left.quality.total_cmp(&right.quality))
        .map(|contact| StableBallController {
            player_index: contact.player.index,
            team_home: contact.player.team_home,
            confidence: contact.quality,
        });
    let stable_controller = {
        let (team_home, winner, opponent) = if control.home.confidence >= control.away.confidence {
            (true, control.home, control.away)
        } else {
            (false, control.away, control.home)
        };
        let relative_speed = winner
            .player_index
            .and_then(|player_index| {
                contacts
                    .iter()
                    .find(|candidate| {
                        candidate.player.team_home == team_home
                            && candidate.player.index == player_index
                    })
                    .map(|candidate| {
                        vector_length(vector_sub(motion.velocity, candidate.player.velocity))
                            * velocity_scale
                    })
            })
            .unwrap_or(f64::INFINITY);
        let winning_contact = winner.player_index.and_then(|player_index| {
            contacts.iter().find(|candidate| {
                candidate.player.team_home == team_home && candidate.player.index == player_index
            })
        });
        let opposing_contact_quality = contacts
            .iter()
            .filter(|candidate| candidate.player.team_home != team_home)
            .map(|candidate| candidate.quality)
            .fold(0.0_f64, f64::max);
        let cushioned_first_control = winning_contact.is_some_and(|contact| {
            contact.quality >= 0.40
                && winner.confidence >= 0.05
                && relative_speed <= 2.5
                && opposing_contact_quality <= contact.quality * 0.20
        });
        let open_ball_control = winner.confidence >= 0.72
            && winner.confidence - opponent.confidence >= 0.12
            && relative_speed <= 6.5;
        let unopposed_control =
            opponent.confidence <= 0.08 && winner.confidence >= 0.60 && relative_speed <= 4.5;
        let combined_confidence = winner.confidence + opponent.confidence;
        let shielded_contested_control = combined_confidence >= 1.35
            && winner.confidence >= 0.72
            && winner.confidence - opponent.confidence >= 0.08
            && relative_speed <= 3.0;
        let pinned_ball_control = motion.speed() * velocity_scale <= 0.45
            && combined_confidence >= 0.90
            && winner.confidence >= 0.45
            && winner.confidence - opponent.confidence > f64::EPSILON
            && relative_speed <= 2.0;
        let stable = cushioned_first_control
            || open_ball_control
            || unopposed_control
            || shielded_contested_control
            || pinned_ball_control;
        if stable {
            winner
                .player_index
                .map(|player_index| StableBallController {
                    player_index,
                    team_home,
                    confidence: winner.confidence,
                })
        } else {
            None
        }
    };
    BallContactTickOutput {
        motion,
        control,
        stable_controller,
        strongest_contact,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn configured_pass_speed_is_the_flight_curve_average_speed() {
        let short = pass_average_speed(8.0, 24.0, 2.0);
        let medium = pass_average_speed(20.0, 24.0, 2.0);
        let long = pass_average_speed(40.0, 24.0, 2.0);

        assert_eq!(short, 24.0);
        assert_eq!(medium, 24.0);
        assert_eq!(long, 24.0);
    }

    #[test]
    fn short_pass_terminal_speed_follows_the_continuous_flight_curve() {
        let short_speed = pass_average_speed(8.0, 24.0, 2.0);
        let terminal = flight_terminal_velocity((0.0, 0.0), (8.0, 0.0), short_speed, 0.24);

        assert!((terminal.0 - 5.76).abs() <= 1e-9);
        assert_eq!(terminal.1, 0.0);
    }

    #[test]
    fn configured_pass_speed_is_invariant_to_tick_resolution() {
        let distance = 24.0;
        let two_second_speed = pass_average_speed(distance, 24.0, 2.0);
        let one_second_speed = pass_average_speed(distance, 12.0, 1.0);
        let two_second_flight_seconds = distance / two_second_speed * 2.0;
        let one_second_flight_seconds = distance / one_second_speed;

        assert!((two_second_flight_seconds - 2.0).abs() <= 1e-9);
        assert!((one_second_flight_seconds - 2.0).abs() <= 1e-9);
    }

    fn player(index: usize, team_home: bool, position: (f64, f64)) -> PlayerBallContactInput {
        PlayerBallContactInput {
            index,
            team_home,
            position,
            velocity: (0.0, 0.0),
            facing_direction: 0.0,
            dribbling: 80.0,
            iq: 80.0,
            speed: 80.0,
            tackling: 75.0,
            defence: 75.0,
            gk_saving: 50.0,
            gk_positioning: 50.0,
            gk_reaction: 50.0,
            can_use_hands: false,
        }
    }

    #[test]
    fn rolling_motion_decelerates_without_a_velocity_discontinuity() {
        let initial = BallMotionState {
            position: (30.0, 34.0),
            velocity: (6.0, 0.0),
        };
        let first = advance_free_ball(&FreeBallMotionInput {
            state: initial,
            elapsed_ticks: 0.5,
            rolling_deceleration: 0.9,
            drag: 0.04,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });
        let second = advance_free_ball(&FreeBallMotionInput {
            state: first,
            elapsed_ticks: 0.5,
            rolling_deceleration: 0.9,
            drag: 0.04,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert!(initial.speed() > first.speed());
        assert!(first.speed() > second.speed());
        assert!(first.position.0 > initial.position.0);
        assert!(second.position.0 > first.position.0);
    }

    #[test]
    fn flight_terminal_velocity_is_not_limited_by_the_old_free_ball_speed_cap() {
        let velocity = flight_terminal_velocity((10.0, 20.0), (40.0, 20.0), 30.0, 0.78);

        assert!((vector_length(velocity) - 23.4).abs() <= 1e-9);
    }

    #[test]
    fn free_ball_uses_the_real_pitch_line_instead_of_a_player_safety_margin() {
        let initial = BallMotionState {
            position: (0.73, 57.06),
            velocity: (-2.79, 4.40),
        };
        let input = FreeBallMotionInput {
            state: initial,
            elapsed_ticks: 0.25,
            rolling_deceleration: 0.9,
            drag: 0.04,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };
        let unclamped = free_ball_unclamped_position(&input);
        let motion = advance_free_ball(&input);

        assert!(unclamped.0 > 0.0);
        assert!(motion.position.0 < 0.5);
        assert!(motion.speed() > 0.0);
    }

    #[test]
    fn a_fast_glancing_contact_does_not_instantly_bind_the_ball() {
        let previous_motion = BallMotionState {
            position: (40.0, 34.0),
            velocity: (12.0, 0.0),
        };
        let motion = advance_free_ball(&FreeBallMotionInput {
            state: previous_motion,
            elapsed_ticks: 0.25,
            rolling_deceleration: 0.0,
            drag: 0.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });
        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion,
            previous_control: BallControlContest::default(),
            players: &[player(4, true, (42.0, 34.5))],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 1.0,
        });

        assert!(output.strongest_contact.is_some());
        assert!(output.stable_controller.is_none());
        assert!(output.control.home.confidence > 0.0);
        assert!(output.motion.speed() < motion.speed());
    }

    #[test]
    fn an_extended_reach_glance_cannot_absorb_the_pass() {
        let previous_motion = BallMotionState {
            position: (40.0, 34.0),
            velocity: (12.0, 0.0),
        };
        let motion = advance_free_ball(&FreeBallMotionInput {
            state: previous_motion,
            elapsed_ticks: 0.25,
            rolling_deceleration: 0.0,
            drag: 0.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });
        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion,
            previous_control: BallControlContest::default(),
            players: &[player(4, true, (42.0, 35.65))],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 4.0,
        });

        assert!(output.strongest_contact.is_some());
        assert!(output.stable_controller.is_none());
        assert!(
            output.motion.speed() >= motion.speed() * 0.90,
            "an edge-of-reach touch may deflect the ball but cannot behave like a cushioned trap: {output:?}"
        );
    }

    #[test]
    fn contact_impulse_is_consistent_across_substeps() {
        let receiver = PlayerBallContactInput {
            velocity: (1.5, 0.0),
            ..player(6, true, (41.5, 34.0))
        };
        let contact = ContactEvaluation {
            player: receiver,
            quality: 0.48,
            impulse_access: 1.0,
            relative_speed: 7.5,
        };
        let initial = BallMotionState {
            position: (41.25, 34.0),
            velocity: (9.0, 0.0),
        };
        let whole = contact_adjusted_motion(initial, &[contact], 1.0, 1.0);
        let mut subdivided = initial;
        for _ in 0..4 {
            subdivided = contact_adjusted_motion(subdivided, &[contact], 0.25, 1.0);
        }

        assert!(
            (whole.velocity.0 - subdivided.velocity.0).abs() <= 0.15,
            "subdividing one contact tick must not multiply its impulse: whole={whole:?}, subdivided={subdivided:?}"
        );
    }

    #[test]
    fn a_weak_glancing_touch_cannot_launch_the_ball_at_the_players_running_speed() {
        let contact = ContactEvaluation {
            player: PlayerBallContactInput {
                velocity: (0.0, 8.0),
                ..player(6, true, (41.5, 34.0))
            },
            quality: 0.20,
            impulse_access: 1.0,
            relative_speed: 12.0,
        };
        let initial = BallMotionState {
            position: (41.25, 34.0),
            velocity: (10.0, 0.0),
        };

        let adjusted = contact_adjusted_motion(initial, &[contact], 0.25, 20.0);

        assert!(
            adjusted.velocity.0 >= 4.0,
            "a weak glancing touch may cushion the ball but must preserve continuous forward motion: {adjusted:?}"
        );
        assert!(
            adjusted.velocity.1.abs() <= 1.5,
            "a weak glancing touch must not couple the ball to the player's full lateral running speed: {adjusted:?}"
        );
    }

    #[test]
    fn an_unopposed_cushioned_touch_can_establish_control_immediately() {
        let mut receiver = player(6, true, (41.5, 34.0));
        receiver.velocity = (1.5, 0.0);
        receiver.facing_direction = 180.0;
        receiver.dribbling = 86.0;
        receiver.iq = 84.0;
        let previous_motion = BallMotionState {
            position: (40.25, 34.0),
            velocity: (4.0, 0.0),
        };
        let motion = BallMotionState {
            position: (41.25, 34.0),
            velocity: (4.0, 0.0),
        };

        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion,
            previous_control: BallControlContest::default(),
            players: &[receiver],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.5,
            control_radius: 1.2,
            impulse_scale: 4.0,
        });

        assert!(output.motion.speed() < motion.speed());
        assert_eq!(
            output
                .stable_controller
                .map(|controller| controller.player_index),
            Some(receiver.index),
            "contact={:?}, claim={:?}, motion={:?}",
            output.strongest_contact,
            output.control,
            output.motion
        );
    }

    #[test]
    fn a_marginal_cushion_must_build_control_before_binding_the_ball() {
        let mut receiver = player(6, true, (41.5, 34.7));
        receiver.velocity = (1.5, 0.0);
        receiver.facing_direction = 180.0;
        let previous_motion = BallMotionState {
            position: (39.0, 34.0),
            velocity: (9.0, 0.0),
        };
        let motion = BallMotionState {
            position: (41.25, 34.0),
            velocity: (9.0, 0.0),
        };

        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion,
            previous_control: BallControlContest::default(),
            players: &[receiver],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 4.0,
        });

        assert!(output.strongest_contact.is_some());
        assert!(output.control.home.confidence > 0.0);
        assert!(output.control.home.confidence < 0.20);
        assert!(output.stable_controller.is_none());
    }

    #[test]
    fn repeated_matched_contacts_build_stable_control() {
        let mut player = PlayerBallContactInput {
            velocity: (2.4, 0.0),
            ..player(6, true, (50.0, 34.0))
        };
        let mut motion = BallMotionState {
            position: (50.5, 34.0),
            velocity: (2.4, 0.0),
        };
        let mut control = BallControlContest::default();
        let mut controller = None;
        for _ in 0..16 {
            let previous_motion = motion;
            motion = advance_free_ball(&FreeBallMotionInput {
                state: motion,
                elapsed_ticks: 0.25,
                rolling_deceleration: 0.0,
                drag: 0.0,
                pitch_length: 105.0,
                pitch_width: 68.0,
            });
            let output = resolve_ball_contacts(&BallContactTickInput {
                motion,
                previous_motion,
                previous_control: control,
                players: &[player],
                elapsed_ticks: 0.25,
                control_elapsed_seconds: 0.25,
                control_radius: 1.2,
                impulse_scale: 1.0,
            });
            motion = output.motion;
            control = output.control;
            controller = output.stable_controller;
            player.position = vector_add(player.position, vector_scale(player.velocity, 0.25));
        }

        assert!(control.home.confidence > 0.72);
        assert_eq!(
            controller.map(|controller| controller.player_index),
            Some(player.index)
        );
    }

    #[test]
    fn low_speed_body_advantage_settles_before_the_ball_is_fully_pinned() {
        let home = player(7, true, (50.0, 34.0));
        let away = player(10, false, (50.8, 34.0));
        let previous_motion = BallMotionState {
            position: (50.4, 34.0),
            velocity: (1.0, 0.0),
        };
        let output = resolve_ball_contacts(&BallContactTickInput {
            motion: previous_motion,
            previous_motion,
            previous_control: BallControlContest {
                home: BallControlClaim {
                    player_index: Some(home.index),
                    confidence: 0.82,
                },
                away: BallControlClaim {
                    player_index: Some(away.index),
                    confidence: 0.70,
                },
            },
            players: &[home, away],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 4.0,
        });

        assert_eq!(
            output
                .stable_controller
                .map(|controller| { (controller.team_home, controller.player_index,) }),
            Some((true, home.index))
        );
    }

    #[test]
    fn moving_shielded_control_depends_on_relative_not_ground_speed() {
        let home = PlayerBallContactInput {
            velocity: (5.0, 0.0),
            ..player(7, true, (50.0, 34.0))
        };
        let away = PlayerBallContactInput {
            velocity: (4.5, 0.0),
            facing_direction: 180.0,
            ..player(10, false, (50.8, 34.0))
        };
        let motion = BallMotionState {
            position: (50.4, 34.0),
            velocity: (5.2, 0.0),
        };
        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion: motion,
            previous_control: BallControlContest {
                home: BallControlClaim {
                    player_index: Some(home.index),
                    confidence: 0.82,
                },
                away: BallControlClaim {
                    player_index: Some(away.index),
                    confidence: 0.70,
                },
            },
            players: &[home, away],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 4.0,
        });

        assert!(
            output.motion.speed() > 1.2,
            "the ball and controller should still be moving together"
        );
        assert_eq!(
            output
                .stable_controller
                .map(|controller| (controller.team_home, controller.player_index)),
            Some((true, home.index))
        );
    }

    #[test]
    fn continuous_teammate_contact_preserves_team_control_momentum() {
        let first = player(4, true, (50.0, 34.0));
        let second = player(6, true, (50.0, 34.0));
        let previous = BallControlClaim {
            player_index: Some(first.index),
            confidence: 0.64,
        };

        let switched = update_claim(
            previous,
            Some(ContactEvaluation {
                player: second,
                quality: 0.55,
                impulse_access: 1.0,
                relative_speed: 0.4,
            }),
            0.25,
        );
        let absent = update_claim(previous, None, 0.25);

        assert_eq!(switched.player_index, Some(second.index));
        assert!(
            switched.confidence > previous.confidence,
            "continuous team contact should keep accumulating control: {switched:?}"
        );
        assert!(
            switched.confidence > absent.confidence,
            "a teammate taking over the strongest contact is not a loss of team contact"
        );
    }

    #[test]
    fn opposing_contact_reduces_control_and_changes_the_impulse() {
        let motion = BallMotionState {
            position: (60.0, 34.0),
            velocity: (4.0, 0.0),
        };
        let home = PlayerBallContactInput {
            velocity: (2.0, 0.0),
            ..player(8, true, (60.3, 34.0))
        };
        let away = PlayerBallContactInput {
            velocity: (-1.0, 0.0),
            facing_direction: 180.0,
            tackling: 90.0,
            defence: 90.0,
            ..player(3, false, (60.5, 34.0))
        };
        let isolated = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion: motion,
            previous_control: BallControlContest::default(),
            players: &[home],
            elapsed_ticks: 0.5,
            control_elapsed_seconds: 0.5,
            control_radius: 1.2,
            impulse_scale: 1.0,
        });
        let opposed = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion: motion,
            previous_control: BallControlContest::default(),
            players: &[home, away],
            elapsed_ticks: 0.5,
            control_elapsed_seconds: 0.5,
            control_radius: 1.2,
            impulse_scale: 1.0,
        });

        assert!(opposed.control.home.confidence < isolated.control.home.confidence);
        assert!(opposed.control.away.confidence > 0.0);
        assert!(opposed.motion.velocity.0 < isolated.motion.velocity.0);
        assert!(opposed.stable_controller.is_none());
    }

    #[test]
    fn sustained_small_advantage_settles_a_pinned_two_player_ball() {
        let mut motion = BallMotionState {
            position: (60.0, 34.0),
            velocity: (0.02, 0.0),
        };
        let home = PlayerBallContactInput {
            velocity: (0.0, 0.0),
            ..player(8, true, (59.8, 34.0))
        };
        let away = PlayerBallContactInput {
            velocity: (0.0, 0.0),
            facing_direction: 180.0,
            ..player(3, false, (60.25, 34.0))
        };
        let mut control = BallControlContest {
            home: BallControlClaim {
                player_index: Some(home.index),
                confidence: 0.77,
            },
            away: BallControlClaim {
                player_index: Some(away.index),
                confidence: 0.71,
            },
        };
        let mut controller = None;
        for _ in 0..16 {
            let previous_motion = motion;
            let output = resolve_ball_contacts(&BallContactTickInput {
                motion,
                previous_motion,
                previous_control: control,
                players: &[home, away],
                elapsed_ticks: 0.25,
                control_elapsed_seconds: 0.25,
                control_radius: 1.2,
                impulse_scale: 1.0,
            });
            motion = output.motion;
            control = output.control;
            controller = output.stable_controller;
            if controller.is_some() {
                break;
            }
        }

        assert_eq!(
            controller.map(|controller| (controller.team_home, controller.player_index)),
            Some((true, home.index))
        );
    }

    #[test]
    fn pinned_ball_uses_combined_contact_evidence_instead_of_two_absolute_winners() {
        let motion = BallMotionState {
            position: (60.0, 34.0),
            velocity: (0.02, 0.0),
        };
        let home = player(8, true, (59.8, 34.0));
        let away = PlayerBallContactInput {
            facing_direction: 180.0,
            ..player(3, false, (60.25, 34.0))
        };
        let output = resolve_ball_contacts(&BallContactTickInput {
            motion,
            previous_motion: motion,
            previous_control: BallControlContest {
                home: BallControlClaim {
                    player_index: Some(home.index),
                    confidence: 0.52,
                },
                away: BallControlClaim {
                    player_index: Some(away.index),
                    confidence: 0.48,
                },
            },
            players: &[home, away],
            elapsed_ticks: 0.25,
            control_elapsed_seconds: 0.25,
            control_radius: 1.2,
            impulse_scale: 1.0,
        });

        assert_eq!(
            output
                .stable_controller
                .map(|controller| (controller.team_home, controller.player_index)),
            Some((true, home.index))
        );
    }
}
