use crate::contested::{
    select_contested_targets_into, ContestedSharedClaim, ContestedTargetOutput,
    ContestedTargetPlayerInput, ContestedTargetsInput,
};
use crate::match_flow::{player_move_tick_fraction, PlayerMoveTickInput};
use crate::physics::{distance, player_speed};
use crate::team_plan::{team_plan_movement_target, TeamPlanSignals};

pub const FREE_BALL_TEAM_SIZE: usize = 11;

#[derive(Clone, Copy, Debug)]
pub struct FreeBallPursuitPlayerInput<'a> {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub fallback_target: (f64, f64),
    pub fallback_intent: &'a str,
    pub is_goalkeeper: bool,
    pub can_use_hands: bool,
    pub is_stunned: bool,
    pub speed: i32,
    pub iq: f64,
    pub state: &'a str,
}

#[derive(Clone, Copy, Debug)]
pub struct FreeBallPursuitConfig {
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub contested_race_radius: f64,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct FreeBallPursuitOutput {
    pub index: usize,
    pub target: (f64, f64),
    pub intent_code: u8,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
}

fn coordinated_targets_into(
    players: &[ContestedTargetPlayerInput],
    ball_pos: (f64, f64),
    ball_speed: f64,
    config: &FreeBallPursuitConfig,
    outputs: &mut [ContestedTargetOutput; FREE_BALL_TEAM_SIZE],
) -> usize {
    let initial_count = select_contested_targets_into(
        &ContestedTargetsInput {
            ball_pos,
            ball_speed,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            player_max_speed: config.player_max_speed,
            player_min_speed: config.player_min_speed,
            contested_race_radius: config.contested_race_radius,
            players,
            shared_claims: &[],
        },
        outputs,
    );
    let primary = outputs[..initial_count]
        .iter()
        .filter(|output| output.intent_code == 1)
        .min_by(|left, right| {
            let arrival_ticks = |output: &ContestedTargetOutput| {
                players
                    .iter()
                    .find(|player| player.index == output.index)
                    .map(|player| {
                        distance(player.pos, ball_pos)
                            / player_speed(
                                player.speed,
                                config.player_max_speed,
                                config.player_min_speed,
                            )
                            .max(config.player_min_speed)
                    })
                    .unwrap_or(f64::INFINITY)
            };
            arrival_ticks(left)
                .total_cmp(&arrival_ticks(right))
                .then_with(|| right.value.total_cmp(&left.value))
        })
        .copied();
    let Some(primary) = primary else {
        return initial_count;
    };
    let claims = [ContestedSharedClaim {
        owner_index: primary.index,
        target: primary.target,
        occupancy_radius: crate::spatial_claim_for_task(
            players
                .iter()
                .find(|player| player.index == primary.index)
                .map(|player| player.pos)
                .unwrap_or(primary.target),
            primary.target,
            crate::TacticalTaskIntent::Pursuit,
            true,
        )
        .occupancy_radius,
        commitment: 1.0,
        declared_value: primary.value,
    }];
    select_contested_targets_into(
        &ContestedTargetsInput {
            ball_pos,
            ball_speed,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            player_max_speed: config.player_max_speed,
            player_min_speed: config.player_min_speed,
            contested_race_radius: config.contested_race_radius,
            players,
            shared_claims: &claims,
        },
        outputs,
    )
}

pub fn free_ball_team_pursuit_tick_into(
    players: &[FreeBallPursuitPlayerInput<'_>],
    ball_pos: (f64, f64),
    ball_velocity: (f64, f64),
    plan_signals: TeamPlanSignals,
    tick_fraction: f64,
    config: &FreeBallPursuitConfig,
    outputs: &mut [FreeBallPursuitOutput; FREE_BALL_TEAM_SIZE],
) -> usize {
    assert!(players.len() <= FREE_BALL_TEAM_SIZE);
    let mut contested_players = [ContestedTargetPlayerInput {
        index: 0,
        pos: (0.0, 0.0),
        tactical_anchor: (0.0, 0.0),
        is_goalkeeper: false,
        can_use_hands: false,
        is_stunned: false,
        speed: 0,
        iq: 0.0,
    }; FREE_BALL_TEAM_SIZE];
    for (slot, player) in players.iter().enumerate() {
        contested_players[slot] = ContestedTargetPlayerInput {
            index: player.index,
            pos: player.pos,
            tactical_anchor: player.tactical_anchor,
            is_goalkeeper: player.is_goalkeeper,
            can_use_hands: player.can_use_hands,
            is_stunned: player.is_stunned,
            speed: player.speed,
            iq: player.iq,
        };
    }
    let mut targets = [ContestedTargetOutput {
        index: 0,
        target: (0.0, 0.0),
        intent_code: 0,
        value: 0.0,
    }; FREE_BALL_TEAM_SIZE];
    let target_count = coordinated_targets_into(
        &contested_players[..players.len()],
        ball_pos,
        (ball_velocity.0 * ball_velocity.0 + ball_velocity.1 * ball_velocity.1).sqrt(),
        config,
        &mut targets,
    );
    for (slot, player) in players.iter().enumerate() {
        let selected = targets[..target_count]
            .iter()
            .find(|target| target.index == player.index);
        let intent_code = selected.map_or(0, |target| target.intent_code);
        let local_target = selected.map_or(player.fallback_target, |target| target.target);
        let target = if intent_code == 1 {
            local_target
        } else if player.is_goalkeeper {
            player.fallback_target
        } else {
            team_plan_movement_target(local_target, player.tactical_anchor, plan_signals)
        };
        let movement_intent = if intent_code == 1 {
            "contest"
        } else {
            player.fallback_intent
        };
        let movement = player_move_tick_fraction(
            &PlayerMoveTickInput {
                pos: player.pos,
                target_pos: target,
                velocity: player.velocity,
                speed_ability: player.speed,
                movement_intent,
                state: player.state,
                player_max_speed: config.player_max_speed,
                player_min_speed: config.player_min_speed,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            },
            tick_fraction.clamp(0.0, 1.0),
        );
        outputs[slot] = FreeBallPursuitOutput {
            index: player.index,
            target,
            intent_code,
            pos: movement.pos,
            velocity: movement.velocity,
            facing_direction: movement.facing_direction,
            distance_covered: movement.distance_covered,
        };
    }
    players.len()
}
