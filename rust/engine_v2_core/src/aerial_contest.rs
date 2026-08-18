use crate::action_value::{second_ball_player_access, SecondBallPlayerInput};

#[derive(Clone, Copy, Debug)]
pub struct AerialContestPlayerInput {
    pub player_index: usize,
    pub team_attacking: bool,
    pub movement: SecondBallPlayerInput,
    pub heading: f64,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct AerialContestOutput {
    pub attacking_first_contact_probability: f64,
    pub defending_first_contact_probability: f64,
    pub loose_probability: f64,
    pub contact_quality: f64,
}

pub fn aerial_player_first_contact_probability(
    players: &[AerialContestPlayerInput],
    player_index: usize,
    team_attacking: bool,
    ball_pos: (f64, f64),
    contest_radius: f64,
) -> f64 {
    let accesses = players.iter().map(|player| {
        second_ball_player_access(&player.movement, ball_pos, contest_radius)
            * (player.heading / 100.0).clamp(0.0, 1.0)
    });
    let total_access = accesses.clone().sum::<f64>();
    if total_access <= 1e-9 {
        return 0.0;
    }
    let player_access = players
        .iter()
        .zip(accesses)
        .filter(|(player, _)| {
            player.player_index == player_index && player.team_attacking == team_attacking
        })
        .map(|(_, access)| access)
        .sum::<f64>();
    (1.0 - (-total_access).exp()).clamp(0.0, 1.0) * player_access / total_access
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AerialDeliveryTarget {
    pub receiver_index: usize,
    pub target: (f64, f64),
    pub contest: AerialContestOutput,
}

pub fn aerial_contest(
    players: &[AerialContestPlayerInput],
    ball_pos: (f64, f64),
    contest_radius: f64,
) -> AerialContestOutput {
    let mut attacking_access = 0.0;
    let mut defending_access = 0.0;
    for player in players {
        let access = second_ball_player_access(&player.movement, ball_pos, contest_radius)
            * (player.heading / 100.0).clamp(0.0, 1.0);
        if player.team_attacking {
            attacking_access += access;
        } else {
            defending_access += access;
        }
    }
    let total_access = attacking_access + defending_access;
    if total_access <= 1e-9 {
        return AerialContestOutput {
            loose_probability: 1.0,
            ..AerialContestOutput::default()
        };
    }
    let resolved_probability = (1.0 - (-total_access).exp()).clamp(0.0, 1.0);
    let competitive_overlap =
        4.0 * attacking_access * defending_access / total_access.powi(2).max(f64::EPSILON);
    AerialContestOutput {
        attacking_first_contact_probability: resolved_probability * attacking_access / total_access,
        defending_first_contact_probability: resolved_probability * defending_access / total_access,
        loose_probability: 1.0 - resolved_probability,
        contact_quality: (resolved_probability * competitive_overlap).clamp(0.0, 1.0),
    }
}

pub fn best_aerial_delivery_target(
    players: &[AerialContestPlayerInput],
    contest_radius: f64,
) -> Option<AerialDeliveryTarget> {
    best_aerial_delivery_target_by(players, contest_radius, |delivery| {
        delivery.contest.attacking_first_contact_probability
    })
}

pub fn best_aerial_delivery_target_by(
    players: &[AerialContestPlayerInput],
    contest_radius: f64,
    mut outcome_value: impl FnMut(&AerialDeliveryTarget) -> f64,
) -> Option<AerialDeliveryTarget> {
    players
        .iter()
        .enumerate()
        .filter(|(_, player)| player.team_attacking)
        .map(|(_, receiver)| {
            let target = receiver.movement.projected_pos;
            AerialDeliveryTarget {
                receiver_index: receiver.player_index,
                target,
                contest: aerial_contest(players, target, contest_radius),
            }
        })
        .max_by(|left, right| {
            outcome_value(left)
                .total_cmp(&outcome_value(right))
                .then_with(|| right.receiver_index.cmp(&left.receiver_index))
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn player(
        team_attacking: bool,
        projected_pos: (f64, f64),
        speed: f64,
        heading: f64,
    ) -> AerialContestPlayerInput {
        AerialContestPlayerInput {
            player_index: 0,
            team_attacking,
            movement: SecondBallPlayerInput {
                pos: projected_pos,
                projected_pos,
                speed,
            },
            heading,
        }
    }

    #[test]
    fn aerial_probabilities_close_and_symmetric_geometry_is_symmetric() {
        let result = aerial_contest(
            &[
                player(true, (1.0, 0.0), 1.0, 80.0),
                player(false, (-1.0, 0.0), 1.0, 80.0),
            ],
            (0.0, 0.0),
            2.5,
        );
        let total = result.attacking_first_contact_probability
            + result.defending_first_contact_probability
            + result.loose_probability;
        assert!((total - 1.0).abs() < 1e-12);
        assert!(result.contact_quality > 0.0);
        assert!(
            (result.attacking_first_contact_probability
                - result.defending_first_contact_probability)
                .abs()
                < 1e-12
        );
    }

    #[test]
    fn aerial_contact_quality_requires_competing_team_access() {
        let contested = aerial_contest(
            &[
                player(true, (0.4, 0.0), 1.0, 80.0),
                player(false, (-0.4, 0.0), 1.0, 80.0),
            ],
            (0.0, 0.0),
            2.5,
        );
        let uncontested = aerial_contest(
            &[
                player(true, (0.4, 0.0), 1.0, 80.0),
                player(false, (-8.0, 0.0), 1.0, 80.0),
            ],
            (0.0, 0.0),
            2.5,
        );

        assert!(contested.contact_quality > uncontested.contact_quality);
        assert!(uncontested.contact_quality < contested.contact_quality * 0.02);
    }

    #[test]
    fn better_heading_or_closer_access_monotonically_improves_first_contact() {
        let baseline = aerial_contest(
            &[
                player(true, (2.0, 0.0), 1.0, 60.0),
                player(false, (-1.0, 0.0), 1.0, 75.0),
            ],
            (0.0, 0.0),
            2.5,
        );
        let improved = aerial_contest(
            &[
                player(true, (1.0, 0.0), 1.0, 90.0),
                player(false, (-1.0, 0.0), 1.0, 75.0),
            ],
            (0.0, 0.0),
            2.5,
        );
        assert!(
            improved.attacking_first_contact_probability
                > baseline.attacking_first_contact_probability
        );
    }

    #[test]
    fn zero_heading_access_leaves_a_loose_ball() {
        let result = aerial_contest(
            &[
                player(true, (0.0, 0.0), 1.0, 0.0),
                player(false, (0.0, 0.0), 1.0, 0.0),
            ],
            (0.0, 0.0),
            2.5,
        );
        assert_eq!(
            result,
            AerialContestOutput {
                loose_probability: 1.0,
                ..AerialContestOutput::default()
            }
        );
    }

    #[test]
    fn delivery_target_is_an_actual_attacking_players_projected_position() {
        let players = [
            AerialContestPlayerInput {
                player_index: 7,
                ..player(true, (3.0, 0.0), 1.0, 55.0)
            },
            player(false, (3.2, 0.0), 1.0, 90.0),
            AerialContestPlayerInput {
                player_index: 9,
                ..player(true, (0.0, 4.0), 1.0, 90.0)
            },
        ];

        let selected = best_aerial_delivery_target(&players, 2.5).expect("attacking target");

        assert_eq!(selected.target, players[2].movement.projected_pos);
        assert_eq!(selected.receiver_index, 9);
    }

    #[test]
    fn delivery_target_is_absent_without_an_attacking_player() {
        assert!(
            best_aerial_delivery_target(&[player(false, (0.0, 0.0), 1.0, 90.0)], 2.5).is_none()
        );
    }

    #[test]
    fn delivery_target_can_trade_safe_contact_for_higher_outcome_value() {
        let players = [
            AerialContestPlayerInput {
                player_index: 4,
                ..player(true, (0.0, 1.0), 1.0, 99.0)
            },
            AerialContestPlayerInput {
                player_index: 8,
                ..player(true, (8.0, 0.0), 1.0, 70.0)
            },
            player(false, (7.0, 0.0), 1.0, 80.0),
        ];

        let safest = best_aerial_delivery_target(&players, 2.5).expect("safe target");
        let valuable = best_aerial_delivery_target_by(&players, 2.5, |delivery| {
            if delivery.receiver_index == 8 {
                1.0
            } else {
                0.0
            }
        })
        .expect("valuable target");

        assert_eq!(safest.receiver_index, 4);
        assert_eq!(valuable.receiver_index, 8);
    }
}
