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
    let mut def_xs: Vec<f64> = opponents
        .iter()
        .filter(|player| !player.is_goalkeeper)
        .map(|player| player.x)
        .collect();
    if attacking_right {
        def_xs.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
        if def_xs.len() >= 2 {
            def_xs[1]
        } else if let Some(value) = def_xs.first() {
            *value
        } else {
            pitch_length
        }
    } else {
        def_xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        if def_xs.len() >= 2 {
            def_xs[1]
        } else if let Some(value) = def_xs.first() {
            *value
        } else {
            0.0
        }
    }
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
    fn offside_line_uses_second_last_outfield_player() {
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
        assert_eq!(get_offside_line(&opponents, true, 105.0), 88.0);
        assert_eq!(get_offside_line(&opponents, false, 105.0), 88.0);
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
