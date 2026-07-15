#[derive(Clone, Copy, Debug)]
pub struct OpponentLineInput {
    pub x: f64,
    pub is_goalkeeper: bool,
}

pub fn get_offside_line(
    opponents: &[OpponentLineInput],
    attacking_right: bool,
    pitch_length: f64,
) -> f64 {
    get_offside_line_from_xs(
        opponents.iter().map(|player| player.x),
        attacking_right,
        pitch_length,
    )
}

pub(crate) fn get_offside_line_from_xs(
    opponent_xs: impl IntoIterator<Item = f64>,
    attacking_right: bool,
    pitch_length: f64,
) -> f64 {
    let ahead_of = |candidate: f64, current: f64| {
        if attacking_right {
            candidate
                .partial_cmp(&current)
                .is_some_and(|ordering| ordering == std::cmp::Ordering::Greater)
        } else {
            candidate
                .partial_cmp(&current)
                .is_some_and(|ordering| ordering == std::cmp::Ordering::Less)
        }
    };
    let mut closest_to_goal = None;
    let mut second_closest_to_goal = None;
    for x in opponent_xs {
        match closest_to_goal {
            None => closest_to_goal = Some(x),
            Some(first) if ahead_of(x, first) => {
                second_closest_to_goal = Some(first);
                closest_to_goal = Some(x);
            }
            _ => match second_closest_to_goal {
                None => second_closest_to_goal = Some(x),
                Some(second) if ahead_of(x, second) => second_closest_to_goal = Some(x),
                _ => {}
            },
        }
    }
    second_closest_to_goal
        .or(closest_to_goal)
        .unwrap_or(if attacking_right { pitch_length } else { 0.0 })
}

pub fn is_offside_position(
    pos: (f64, f64),
    attacking_right: bool,
    offside_line: f64,
    pitch_length: f64,
    ball_x: Option<f64>,
) -> bool {
    if attacking_right {
        if pos.0 <= pitch_length / 2.0 {
            return false;
        }
        if let Some(ball_x) = ball_x {
            if pos.0 <= ball_x {
                return false;
            }
        }
        pos.0 > offside_line
    } else {
        if pos.0 >= pitch_length / 2.0 {
            return false;
        }
        if let Some(ball_x) = ball_x {
            if pos.0 >= ball_x {
                return false;
            }
        }
        pos.0 < offside_line
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn offside_line_uses_second_last_opponent_including_goalkeeper() {
        let opponents = vec![
            OpponentLineInput {
                x: 104.0,
                is_goalkeeper: true,
            },
            OpponentLineInput {
                x: 88.0,
                is_goalkeeper: false,
            },
            OpponentLineInput {
                x: 80.0,
                is_goalkeeper: false,
            },
            OpponentLineInput {
                x: 92.0,
                is_goalkeeper: false,
            },
        ];
        assert_eq!(get_offside_line(&opponents, true, 105.0), 92.0);
        assert_eq!(get_offside_line(&opponents, false, 105.0), 88.0);
    }

    #[test]
    fn goalkeeper_position_changes_the_onside_boundary_in_both_directions() {
        let right_attacking = vec![
            OpponentLineInput {
                x: 100.0,
                is_goalkeeper: true,
            },
            OpponentLineInput {
                x: 92.0,
                is_goalkeeper: false,
            },
            OpponentLineInput {
                x: 74.0,
                is_goalkeeper: false,
            },
        ];
        let left_attacking = vec![
            OpponentLineInput {
                x: 5.0,
                is_goalkeeper: true,
            },
            OpponentLineInput {
                x: 13.0,
                is_goalkeeper: false,
            },
            OpponentLineInput {
                x: 31.0,
                is_goalkeeper: false,
            },
        ];

        assert_eq!(get_offside_line(&right_attacking, true, 105.0), 92.0);
        assert!(!is_offside_position(
            (90.0, 34.0),
            true,
            get_offside_line(&right_attacking, true, 105.0),
            105.0,
            Some(70.0),
        ));
        assert_eq!(get_offside_line(&left_attacking, false, 105.0), 13.0);
        assert!(!is_offside_position(
            (15.0, 34.0),
            false,
            get_offside_line(&left_attacking, false, 105.0),
            105.0,
            Some(35.0),
        ));
    }

    #[test]
    fn offside_position_requires_opponent_half_and_ahead_of_ball() {
        assert!(!is_offside_position(
            (53.0, 34.0),
            true,
            50.0,
            105.0,
            Some(60.0)
        ));
        assert!(is_offside_position(
            (82.0, 34.0),
            true,
            80.0,
            105.0,
            Some(70.0)
        ));
        assert!(!is_offside_position(
            (82.0, 34.0),
            true,
            80.0,
            105.0,
            Some(84.0)
        ));
        assert!(is_offside_position(
            (20.0, 34.0),
            false,
            22.0,
            105.0,
            Some(30.0)
        ));
    }
}
