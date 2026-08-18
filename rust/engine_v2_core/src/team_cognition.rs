use crate::{BelievedEntity, TeamPlanOpponentInput, TeamPlanPlayerInput};

pub const MAX_TEAM_COGNITION_PLAYERS: usize = 11;
const MIN_SHARED_OBSERVATION_CONFIDENCE: f64 = 0.08;
const CONTROL_PROXIMITY_SCALE: f64 = 3.2;

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanCognition {
    pub ball_pos: (f64, f64),
    pub ball_confidence: f64,
    pub possession_probability: f64,
    pub opponent_count: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamCognitionPlayerInput<'a> {
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
    pub ball_pos: (f64, f64),
    pub ball_confidence: f64,
    pub believed_entities: &'a [BelievedEntity],
}

pub fn compile_shared_opponent_beliefs(
    players: &[TeamCognitionPlayerInput<'_>],
    output: &mut [BelievedEntity; MAX_TEAM_COGNITION_PLAYERS],
) -> usize {
    let mut confidence_by_index = [0.0; MAX_TEAM_COGNITION_PLAYERS];
    for player in players {
        for entity in player.believed_entities {
            if entity.is_teammate || entity.confidence < MIN_SHARED_OBSERVATION_CONFIDENCE {
                continue;
            }
            let Some(opponent_index) = entity.index.checked_sub(MAX_TEAM_COGNITION_PLAYERS) else {
                continue;
            };
            if opponent_index >= MAX_TEAM_COGNITION_PLAYERS
                || entity.confidence <= confidence_by_index[opponent_index]
            {
                continue;
            }
            confidence_by_index[opponent_index] = entity.confidence;
            output[opponent_index] = *entity;
        }
    }
    let mut count = 0;
    for opponent_index in 0..MAX_TEAM_COGNITION_PLAYERS {
        if confidence_by_index[opponent_index] <= 0.0 {
            continue;
        }
        output.swap(count, opponent_index);
        confidence_by_index.swap(count, opponent_index);
        count += 1;
    }
    count
}

pub fn compile_team_plan_inputs(
    players: &[TeamCognitionPlayerInput<'_>],
    fallback_ball_pos: (f64, f64),
    player_inputs: &mut [TeamPlanPlayerInput; MAX_TEAM_COGNITION_PLAYERS],
    opponent_inputs: &mut [TeamPlanOpponentInput; MAX_TEAM_COGNITION_PLAYERS],
) -> TeamPlanCognition {
    compile_team_plan_inputs_with_control(
        players,
        fallback_ball_pos,
        player_inputs,
        opponent_inputs,
        None,
    )
}

pub fn compile_team_plan_inputs_with_control(
    players: &[TeamCognitionPlayerInput<'_>],
    fallback_ball_pos: (f64, f64),
    player_inputs: &mut [TeamPlanPlayerInput; MAX_TEAM_COGNITION_PLAYERS],
    opponent_inputs: &mut [TeamPlanOpponentInput; MAX_TEAM_COGNITION_PLAYERS],
    control_confidence: Option<(f64, f64)>,
) -> TeamPlanCognition {
    assert!(
        players.len() <= MAX_TEAM_COGNITION_PLAYERS,
        "team cognition expects at most eleven players"
    );
    let mut shared_opponents = [BelievedEntity {
        index: 0,
        pos: (0.0, 0.0),
        velocity: (0.0, 0.0),
        confidence: 0.0,
        is_teammate: false,
        is_goalkeeper: false,
    }; MAX_TEAM_COGNITION_PLAYERS];
    let opponent_count = compile_shared_opponent_beliefs(players, &mut shared_opponents);
    let mut ball_weight = 0.0;
    let mut ball_confidence = 0.0_f64;
    let mut ball_x = 0.0;
    let mut ball_y = 0.0;
    for (player_index, player) in players.iter().enumerate() {
        player_inputs[player_index] = TeamPlanPlayerInput {
            pos: player.pos,
            is_goalkeeper: player.is_goalkeeper,
        };
        if player.ball_confidence >= MIN_SHARED_OBSERVATION_CONFIDENCE {
            ball_weight += player.ball_confidence;
            ball_confidence = ball_confidence.max(player.ball_confidence);
            ball_x += player.ball_pos.0 * player.ball_confidence;
            ball_y += player.ball_pos.1 * player.ball_confidence;
        }
    }
    let ball_pos = if ball_weight > 1e-9 {
        (ball_x / ball_weight, ball_y / ball_weight)
    } else {
        fallback_ball_pos
    };
    let mut opponent_confidence = [0.0; MAX_TEAM_COGNITION_PLAYERS];
    for (index, entity) in shared_opponents[..opponent_count].iter().enumerate() {
        opponent_inputs[index] = TeamPlanOpponentInput {
            pos: entity.pos,
            is_goalkeeper: entity.is_goalkeeper,
        };
        opponent_confidence[index] = entity.confidence;
    }
    let ball_confidence = ball_confidence.clamp(0.0, 1.0);
    let proximity_probability = shared_possession_probability(
        ball_pos,
        ball_confidence,
        &player_inputs[..players.len()],
        &opponent_inputs[..opponent_count],
        &opponent_confidence[..opponent_count],
    );
    let possession_probability = possession_probability_with_control(
        proximity_probability,
        ball_confidence,
        control_confidence,
    );
    TeamPlanCognition {
        ball_pos,
        ball_confidence,
        possession_probability,
        opponent_count,
    }
}

fn possession_probability_with_control(
    proximity_probability: f64,
    observation_confidence: f64,
    control_confidence: Option<(f64, f64)>,
) -> f64 {
    let Some((own_confidence, opponent_confidence)) = control_confidence else {
        return proximity_probability.clamp(0.0, 1.0);
    };
    let own_confidence = own_confidence.clamp(0.0, 1.0);
    let opponent_confidence = opponent_confidence.clamp(0.0, 1.0);
    let evidence_strength =
        own_confidence.max(opponent_confidence) * observation_confidence.clamp(0.0, 1.0);
    if evidence_strength <= 1e-9 {
        return proximity_probability.clamp(0.0, 1.0);
    }
    let control_margin =
        (own_confidence - opponent_confidence) / (own_confidence + opponent_confidence + 0.20);
    let control_probability = (0.5 + 0.5 * control_margin).clamp(0.0, 1.0);
    (proximity_probability * (1.0 - evidence_strength) + control_probability * evidence_strength)
        .clamp(0.0, 1.0)
}

fn control_proximity(distance: f64) -> f64 {
    let normalized = distance / CONTROL_PROXIMITY_SCALE;
    (-normalized * normalized).exp()
}

fn shared_possession_probability(
    ball_pos: (f64, f64),
    ball_confidence: f64,
    players: &[TeamPlanPlayerInput],
    opponents: &[TeamPlanOpponentInput],
    opponent_confidences: &[f64],
) -> f64 {
    if ball_confidence <= 0.0 {
        return 0.5;
    }
    let team_control = players
        .iter()
        .map(|player| {
            let dx = player.pos.0 - ball_pos.0;
            let dy = player.pos.1 - ball_pos.1;
            control_proximity((dx * dx + dy * dy).sqrt())
        })
        .fold(0.0_f64, f64::max);
    let opponent_control = opponents
        .iter()
        .zip(opponent_confidences)
        .map(|(opponent, confidence)| {
            let dx = opponent.pos.0 - ball_pos.0;
            let dy = opponent.pos.1 - ball_pos.1;
            confidence.clamp(0.0, 1.0) * control_proximity((dx * dx + dy * dy).sqrt())
        })
        .fold(0.0_f64, f64::max);
    let uncertainty = 0.25 + 0.75 * (1.0 - ball_confidence);
    let control_margin =
        (team_control - opponent_control) / (team_control + opponent_control + uncertainty);
    (0.5 + 0.5 * ball_confidence * control_margin).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    const EMPTY_PLAYER: TeamPlanPlayerInput = TeamPlanPlayerInput {
        pos: (0.0, 0.0),
        is_goalkeeper: false,
    };
    const EMPTY_OPPONENT: TeamPlanOpponentInput = TeamPlanOpponentInput {
        pos: (0.0, 0.0),
        is_goalkeeper: false,
    };

    #[test]
    fn shared_cognition_merges_observations_without_revealing_hidden_opponents() {
        let first_entities = [BelievedEntity {
            index: 14,
            pos: (61.0, 31.0),
            velocity: (0.0, 0.0),
            confidence: 0.45,
            is_teammate: false,
            is_goalkeeper: false,
        }];
        let second_entities = [BelievedEntity {
            index: 14,
            pos: (62.0, 32.0),
            velocity: (0.0, 0.0),
            confidence: 0.80,
            is_teammate: false,
            is_goalkeeper: false,
        }];
        let players = [
            TeamCognitionPlayerInput {
                pos: (48.0, 30.0),
                is_goalkeeper: false,
                ball_pos: (56.0, 34.0),
                ball_confidence: 0.25,
                believed_entities: &first_entities,
            },
            TeamCognitionPlayerInput {
                pos: (50.0, 38.0),
                is_goalkeeper: false,
                ball_pos: (58.0, 34.0),
                ball_confidence: 0.75,
                believed_entities: &second_entities,
            },
        ];
        let mut player_inputs = [EMPTY_PLAYER; MAX_TEAM_COGNITION_PLAYERS];
        let mut opponent_inputs = [EMPTY_OPPONENT; MAX_TEAM_COGNITION_PLAYERS];

        let cognition = compile_team_plan_inputs(
            &players,
            (52.5, 34.0),
            &mut player_inputs,
            &mut opponent_inputs,
        );

        assert_eq!(cognition.opponent_count, 1);
        assert_eq!(opponent_inputs[0].pos, (62.0, 32.0));
        assert_eq!(cognition.ball_pos, (57.5, 34.0));
        assert!((cognition.ball_confidence - 0.75).abs() <= 1e-12);

        let mut shared = [BelievedEntity {
            index: 0,
            pos: (0.0, 0.0),
            velocity: (0.0, 0.0),
            confidence: 0.0,
            is_teammate: false,
            is_goalkeeper: false,
        }; MAX_TEAM_COGNITION_PLAYERS];
        let shared_count = compile_shared_opponent_beliefs(&players, &mut shared);
        assert_eq!(shared_count, 1);
        assert_eq!(shared[0].index, second_entities[0].index);
        assert_eq!(shared[0].pos, second_entities[0].pos);
        assert_eq!(shared[0].velocity, second_entities[0].velocity);
        assert_eq!(shared[0].confidence, second_entities[0].confidence);
    }

    #[test]
    fn shared_possession_is_neutral_without_ball_observations() {
        let players = [TeamCognitionPlayerInput {
            pos: (88.0, 8.0),
            is_goalkeeper: false,
            ball_pos: (17.0, 61.0),
            ball_confidence: 0.0,
            believed_entities: &[],
        }];
        let mut player_inputs = [EMPTY_PLAYER; MAX_TEAM_COGNITION_PLAYERS];
        let mut opponent_inputs = [EMPTY_OPPONENT; MAX_TEAM_COGNITION_PLAYERS];

        let cognition = compile_team_plan_inputs(
            &players,
            (52.5, 34.0),
            &mut player_inputs,
            &mut opponent_inputs,
        );

        assert_eq!(cognition.ball_pos, (52.5, 34.0));
        assert_eq!(cognition.ball_confidence, 0.0);
        assert_eq!(cognition.possession_probability, 0.5);
    }

    #[test]
    fn shared_possession_follows_observed_control_proximity() {
        let opponent_near_ball = [BelievedEntity {
            index: 11,
            pos: (60.2, 34.0),
            velocity: (0.0, 0.0),
            confidence: 1.0,
            is_teammate: false,
            is_goalkeeper: false,
        }];
        let mut player_inputs = [EMPTY_PLAYER; MAX_TEAM_COGNITION_PLAYERS];
        let mut opponent_inputs = [EMPTY_OPPONENT; MAX_TEAM_COGNITION_PLAYERS];
        let own_control = compile_team_plan_inputs(
            &[TeamCognitionPlayerInput {
                pos: (60.0, 34.0),
                is_goalkeeper: false,
                ball_pos: (60.0, 34.0),
                ball_confidence: 1.0,
                believed_entities: &[],
            }],
            (52.5, 34.0),
            &mut player_inputs,
            &mut opponent_inputs,
        );
        let opponent_control = compile_team_plan_inputs(
            &[TeamCognitionPlayerInput {
                pos: (45.0, 34.0),
                is_goalkeeper: false,
                ball_pos: (60.0, 34.0),
                ball_confidence: 1.0,
                believed_entities: &opponent_near_ball,
            }],
            (52.5, 34.0),
            &mut player_inputs,
            &mut opponent_inputs,
        );

        assert!(own_control.possession_probability > 0.75);
        assert!(opponent_control.possession_probability < 0.25);
    }

    #[test]
    fn control_confidence_corrects_existing_possession_estimate_continuously() {
        let baseline = 0.5;
        let weak_claim = possession_probability_with_control(baseline, 1.0, Some((0.20, 0.0)));
        let strong_claim = possession_probability_with_control(baseline, 1.0, Some((0.80, 0.0)));

        assert!(weak_claim > baseline);
        assert!(strong_claim > weak_claim);
    }

    #[test]
    fn equal_control_confidence_preserves_contested_neutrality() {
        assert_eq!(
            possession_probability_with_control(0.5, 1.0, Some((0.78, 0.78))),
            0.5
        );
    }

    #[test]
    fn hidden_control_does_not_bypass_team_observation() {
        assert_eq!(
            possession_probability_with_control(0.32, 0.0, Some((0.90, 0.0))),
            0.32
        );
    }
}
