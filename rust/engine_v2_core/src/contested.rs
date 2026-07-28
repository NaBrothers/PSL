use crate::physics::{distance, player_speed, smoothstep};

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
    pub can_use_hands: bool,
    pub is_stunned: bool,
    pub speed: i32,
    pub iq: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ContestedSharedClaim {
    pub owner_index: usize,
    pub target: (f64, f64),
    pub occupancy_radius: f64,
    pub commitment: f64,
    pub declared_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTargetsInput<'a> {
    pub ball_pos: (f64, f64),
    pub ball_speed: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub contested_race_radius: f64,
    pub players: &'a [ContestedTargetPlayerInput],
    pub shared_claims: &'a [ContestedSharedClaim],
}

#[derive(Clone, Copy, Debug)]
pub struct ContestedTargetOutput {
    pub index: usize,
    pub target: (f64, f64),
    pub intent_code: u8,
    pub value: f64,
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
    if player.is_goalkeeper && (!player.can_use_hands || input.ball_speed > 4.5) {
        return Some(ContestedTargetOutput {
            index: player.index,
            target: player.tactical_anchor,
            intent_code: 0,
            value: 0.0,
        });
    }

    let dist_to_ball = distance(player.pos, input.ball_pos);
    let speed = player_speed(player.speed, input.player_max_speed, input.player_min_speed);
    let nearest_teammate_distance = input
        .players
        .iter()
        .filter(|teammate| !teammate.is_goalkeeper || teammate.can_use_hands)
        .map(|teammate| distance(teammate.pos, input.ball_pos))
        .fold(f64::INFINITY, f64::min);
    let nearby_teammates = input
        .players
        .iter()
        .filter(|teammate| {
            teammate.index != player.index
                && !teammate.is_goalkeeper
                && distance(teammate.pos, input.ball_pos) < dist_to_ball + 1.5
        })
        .count();
    let teammate_body_occupation = input
        .players
        .iter()
        .filter(|teammate| teammate.index != player.index && !teammate.is_goalkeeper)
        .map(|teammate| {
            let teammate_distance = distance(teammate.pos, input.ball_pos);
            let occupies_contact_space =
                1.0 - smoothstep(0.65, input.contested_race_radius * 0.22, teammate_distance);
            let access_precedence = smoothstep(-0.35, 2.25, dist_to_ball - teammate_distance);
            occupies_contact_space * access_precedence
        })
        .sum::<f64>();
    let iq = player.iq / 100.0;
    let race_reach =
        input.contested_race_radius * (0.84 + 0.22 * speed / input.player_max_speed.max(0.1));
    let mut first_ball_value = (1.0 - dist_to_ball / race_reach.max(1.0)).max(0.0);
    first_ball_value = first_ball_value * first_ball_value * (3.0 - 2.0 * first_ball_value);
    let stranded_ball = smoothstep(
        race_reach * 0.82,
        race_reach * 1.05,
        nearest_teammate_distance,
    ) * (1.0 - smoothstep(0.25, 3.0, input.ball_speed));
    let relative_access = (-(dist_to_ball - nearest_teammate_distance).max(0.0) / 4.0).exp();
    first_ball_value = first_ball_value.max(0.68 * stranded_ball * relative_access);
    let uncoordinated_contest_score = first_ball_value * (1.08 + 0.34 * iq);
    let shared_claim_pressure = input
        .shared_claims
        .iter()
        .filter(|claim| claim.owner_index != player.index)
        .filter_map(|claim| {
            let owner = input
                .players
                .iter()
                .find(|teammate| teammate.index == claim.owner_index)?;
            let target_relevance = 1.0
                - smoothstep(
                    claim.occupancy_radius.max(1.0) * 0.35,
                    claim.occupancy_radius.max(1.0) * 1.35,
                    distance(claim.target, input.ball_pos),
                );
            let owner_speed =
                player_speed(owner.speed, input.player_max_speed, input.player_min_speed);
            let owner_arrival_ticks =
                distance(owner.pos, input.ball_pos) / owner_speed.max(input.player_min_speed);
            let player_arrival_ticks = dist_to_ball / speed.max(input.player_min_speed);
            let arrival_precedence =
                smoothstep(-0.18, 0.10, player_arrival_ticks - owner_arrival_ticks);
            let value_support = 0.55
                + 0.45
                    * smoothstep(
                        -0.18,
                        0.18,
                        claim.declared_value - uncoordinated_contest_score,
                    );
            Some(
                target_relevance.max(0.0)
                    * claim.commitment.clamp(0.0, 1.0)
                    * arrival_precedence
                    * value_support,
            )
        })
        .sum::<f64>();
    let unclaimed_contact_space = (1.0 - shared_claim_pressure).clamp(0.0, 1.0);
    let contest_score =
        first_ball_value * (1.08 + 0.34 * iq) * unclaimed_contact_space * unclaimed_contact_space
            / (1.0 + nearby_teammates as f64 * 0.35 + teammate_body_occupation * 8.0);

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
        + (teammate_body_occupation * 0.30).min(0.30)
        + (shared_claim_pressure * 0.34).min(0.34)
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
        value: contest_score.max(support_score),
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

#[cfg(test)]
mod tests {
    use super::*;

    fn player(
        index: usize,
        pos: (f64, f64),
        tactical_anchor: (f64, f64),
        is_goalkeeper: bool,
        can_use_hands: bool,
    ) -> ContestedTargetPlayerInput {
        ContestedTargetPlayerInput {
            index,
            pos,
            tactical_anchor,
            is_goalkeeper,
            can_use_hands,
            is_stunned: false,
            speed: 85,
            iq: 85.0,
        }
    }

    #[test]
    fn goalkeeper_competes_for_a_reachable_loose_ball_inside_hand_control_space() {
        let goalkeeper = player(0, (3.4, 34.0), (4.8, 34.0), true, true);
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (1.8, 33.4),
            ball_speed: 0.8,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &[goalkeeper],
            shared_claims: &[],
        });

        assert_eq!(outputs.len(), 1);
        assert_eq!(outputs[0].intent_code, 1);
        assert_eq!(outputs[0].target, (1.8, 33.4));
    }

    #[test]
    fn goalkeeper_without_hand_control_keeps_goal_coverage() {
        let goalkeeper = player(0, (3.4, 34.0), (4.8, 34.0), true, false);
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (17.0, 34.0),
            ball_speed: 0.8,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &[goalkeeper],
            shared_claims: &[],
        });

        assert_eq!(outputs.len(), 1);
        assert_eq!(outputs[0].intent_code, 0);
        assert_eq!(outputs[0].target, goalkeeper.tactical_anchor);
    }

    #[test]
    fn goalkeeper_keeps_coverage_for_a_fast_loose_ball() {
        let goalkeeper = player(0, (4.0, 34.0), (4.8, 34.0), true, true);
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (6.0, 34.0),
            ball_speed: 8.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &[goalkeeper],
            shared_claims: &[],
        });

        assert_eq!(outputs.len(), 1);
        assert_eq!(outputs[0].intent_code, 0);
    }

    #[test]
    fn nearest_players_recover_a_stopped_ball_outside_the_nominal_race_radius() {
        let nearest = player(4, (16.0, 34.0), (28.0, 30.0), false, false);
        let secondary = player(5, (21.0, 34.0), (32.0, 38.0), false, false);
        let distant = player(6, (38.0, 34.0), (40.0, 34.0), false, false);
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (0.5, 34.0),
            ball_speed: 0.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &[nearest, secondary, distant],
            shared_claims: &[],
        });

        assert_eq!(outputs[0].intent_code, 1);
        assert_eq!(outputs[0].target, (0.5, 34.0));
        assert_eq!(outputs[2].intent_code, 0);
    }

    #[test]
    fn occupied_contact_space_discourages_a_second_teammate_from_collapsing_on_the_ball() {
        let first = player(4, (50.4, 34.0), (44.0, 28.0), false, false);
        let second = player(5, (51.4, 34.0), (46.0, 40.0), false, false);
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (50.0, 34.0),
            ball_speed: 0.4,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &[first, second],
            shared_claims: &[],
        });

        assert_eq!(outputs[0].intent_code, 1);
        assert_eq!(outputs[0].target, (50.0, 34.0));
        assert_eq!(outputs[1].intent_code, 0);
        assert_ne!(outputs[1].target, (50.0, 34.0));
    }

    #[test]
    fn communicated_pursuit_claim_discourages_a_slower_teammate_before_body_occupation() {
        let declared = player(4, (44.0, 34.0), (42.0, 28.0), false, false);
        let slower = player(5, (40.0, 34.0), (40.0, 42.0), false, false);
        let players = [declared, slower];
        let claims = [ContestedSharedClaim {
            owner_index: declared.index,
            target: (50.0, 34.0),
            occupancy_radius: 3.2,
            commitment: 0.9,
            declared_value: 0.72,
        }];
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (50.0, 34.0),
            ball_speed: 0.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &players,
            shared_claims: &claims,
        });

        assert_eq!(outputs[0].intent_code, 1);
        assert_eq!(outputs[1].intent_code, 0);
    }

    #[test]
    fn faster_teammate_can_override_a_stale_pursuit_claim() {
        let mut declared = player(4, (39.0, 34.0), (42.0, 28.0), false, false);
        declared.speed = 62;
        let mut faster = player(5, (44.5, 34.0), (40.0, 42.0), false, false);
        faster.speed = 96;
        let players = [declared, faster];
        let claims = [ContestedSharedClaim {
            owner_index: declared.index,
            target: (50.0, 34.0),
            occupancy_radius: 3.2,
            commitment: 0.9,
            declared_value: 0.72,
        }];
        let outputs = select_contested_targets(&ContestedTargetsInput {
            ball_pos: (50.0, 34.0),
            ball_speed: 0.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            contested_race_radius: 15.0,
            players: &players,
            shared_claims: &claims,
        });

        assert_eq!(outputs[1].intent_code, 1);
        assert_eq!(outputs[1].target, (50.0, 34.0));
    }
}
