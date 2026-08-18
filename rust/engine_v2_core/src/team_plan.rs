use crate::physics::{distance, smoothstep};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TeamPlanKind {
    BuildUp,
    Advance,
    Recycle,
    Switch,
    FinalThird,
    DefendBlock,
    DefendPress,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanState {
    pub kind: TeamPlanKind,
    pub commitment: f64,
    pub value: f64,
}

impl Default for TeamPlanState {
    fn default() -> Self {
        Self {
            kind: TeamPlanKind::BuildUp,
            commitment: 0.0,
            value: 0.0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanSignals {
    pub forward_bias: f64,
    pub recycle_bias: f64,
    pub switch_bias: f64,
    pub width_scale: f64,
    pub depth_scale: f64,
    pub tempo: f64,
    pub risk_budget: f64,
    pub compactness: f64,
    pub press_intensity: f64,
}

impl Default for TeamPlanSignals {
    fn default() -> Self {
        Self {
            forward_bias: 0.5,
            recycle_bias: 0.5,
            switch_bias: 0.5,
            width_scale: 1.0,
            depth_scale: 1.0,
            tempo: 0.5,
            risk_budget: 0.5,
            compactness: 0.5,
            press_intensity: 0.5,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanPlayerInput {
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanOpponentInput {
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Debug)]
pub struct TeamPlanUpdateInput<'a> {
    pub current: TeamPlanState,
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub possession_probability: f64,
    pub phase: &'a str,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub players: &'a [TeamPlanPlayerInput],
    pub opponents: &'a [TeamPlanOpponentInput],
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanFeatures {
    pub ball_progress: f64,
    pub centrality: f64,
    pub ball_pressure: f64,
    pub ball_crowding: f64,
    pub backward_outlets: f64,
    pub forward_outlets: f64,
    pub weak_side_outlets: f64,
    pub team_width: f64,
    pub defensive_threat: f64,
    pub transition: f64,
    pub possession_probability: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanCandidate {
    pub kind: TeamPlanKind,
    pub raw_value: f64,
    pub switch_cost: f64,
    pub value: f64,
}

#[derive(Clone, Debug)]
pub struct TeamPlanUpdateOutput {
    pub state: TeamPlanState,
    pub signals: TeamPlanSignals,
    pub features: TeamPlanFeatures,
    pub candidates: Vec<TeamPlanCandidate>,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanActionInput {
    pub signals: TeamPlanSignals,
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub success_probability: f64,
    pub continuation_probability: f64,
    pub risk: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanActionUtility {
    pub forward_progress: f64,
    pub recycle_value: f64,
    pub switch_value: f64,
    pub retention: f64,
    pub alignment: f64,
    pub multiplier: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanProjectionPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub target_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub speed_ability: i32,
    pub desired_speed: f64,
    pub acceleration_scale: f64,
    pub is_mobile: bool,
}

#[derive(Clone, Debug)]
pub struct TeamPlanFormationProjectionInput<'a> {
    pub signals: TeamPlanSignals,
    pub duration_ticks: i32,
    pub elapsed_fraction: f64,
    pub controlled_player_index: Option<usize>,
    pub controlled_player_pos: Option<(f64, f64)>,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub players: &'a [TeamPlanProjectionPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPlanProjectionPlayerOutput {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct TeamPlanFormationProjection {
    pub players: Vec<TeamPlanProjectionPlayerOutput>,
}

const MAX_TEAM_PLAN_PLAYERS: usize = 11;

#[derive(Clone, Copy)]
struct TeamPlanProfile {
    kind: TeamPlanKind,
    intercept: f64,
    possession: f64,
    ball_progress: f64,
    centrality: f64,
    pressure: f64,
    crowding: f64,
    backward_outlets: f64,
    forward_outlets: f64,
    weak_side_outlets: f64,
    team_width: f64,
    defensive_threat: f64,
    transition: f64,
    switch_inertia: f64,
    signals: TeamPlanSignals,
}

const TEAM_PLAN_PROFILES: [TeamPlanProfile; 7] = [
    TeamPlanProfile {
        kind: TeamPlanKind::BuildUp,
        intercept: 0.10,
        possession: 0.85,
        ball_progress: -0.55,
        centrality: 0.04,
        pressure: -0.20,
        crowding: -0.10,
        backward_outlets: 0.52,
        forward_outlets: 0.18,
        weak_side_outlets: 0.32,
        team_width: -0.06,
        defensive_threat: -0.32,
        transition: -0.18,
        switch_inertia: 0.16,
        signals: TeamPlanSignals {
            forward_bias: 0.34,
            recycle_bias: 0.72,
            switch_bias: 0.50,
            width_scale: 1.12,
            depth_scale: 0.84,
            tempo: 0.42,
            risk_budget: 0.34,
            compactness: 0.54,
            press_intensity: 0.34,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::Advance,
        intercept: -0.05,
        possession: 0.88,
        ball_progress: 0.28,
        centrality: 0.10,
        pressure: -0.14,
        crowding: -0.16,
        backward_outlets: 0.08,
        forward_outlets: 0.70,
        weak_side_outlets: 0.18,
        team_width: 0.04,
        defensive_threat: -0.36,
        transition: 0.20,
        switch_inertia: 0.13,
        signals: TeamPlanSignals {
            forward_bias: 0.68,
            recycle_bias: 0.30,
            switch_bias: 0.34,
            width_scale: 1.04,
            depth_scale: 1.02,
            tempo: 0.66,
            risk_budget: 0.62,
            compactness: 0.46,
            press_intensity: 0.52,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::Recycle,
        intercept: -0.16,
        possession: 0.78,
        ball_progress: -0.12,
        centrality: 0.08,
        pressure: 0.76,
        crowding: 0.48,
        backward_outlets: 0.68,
        forward_outlets: -0.22,
        weak_side_outlets: 0.28,
        team_width: 0.10,
        defensive_threat: -0.44,
        transition: -0.24,
        switch_inertia: 0.23,
        signals: TeamPlanSignals {
            forward_bias: 0.16,
            recycle_bias: 0.92,
            switch_bias: 0.56,
            width_scale: 1.20,
            depth_scale: 0.76,
            tempo: 0.36,
            risk_budget: 0.24,
            compactness: 0.58,
            press_intensity: 0.30,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::Switch,
        intercept: -0.14,
        possession: 0.78,
        ball_progress: 0.02,
        centrality: -0.04,
        pressure: 0.60,
        crowding: 0.50,
        backward_outlets: 0.34,
        forward_outlets: 0.00,
        weak_side_outlets: 1.25,
        team_width: 0.48,
        defensive_threat: -0.38,
        transition: -0.08,
        switch_inertia: 0.19,
        signals: TeamPlanSignals {
            forward_bias: 0.32,
            recycle_bias: 0.66,
            switch_bias: 0.96,
            width_scale: 1.32,
            depth_scale: 0.86,
            tempo: 0.48,
            risk_budget: 0.46,
            compactness: 0.48,
            press_intensity: 0.40,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::FinalThird,
        intercept: -0.34,
        possession: 0.84,
        ball_progress: 1.12,
        centrality: 0.22,
        pressure: -0.16,
        crowding: -0.12,
        backward_outlets: -0.12,
        forward_outlets: 0.56,
        weak_side_outlets: 0.20,
        team_width: -0.02,
        defensive_threat: -0.62,
        transition: 0.14,
        switch_inertia: 0.12,
        signals: TeamPlanSignals {
            forward_bias: 0.86,
            recycle_bias: 0.22,
            switch_bias: 0.28,
            width_scale: 0.98,
            depth_scale: 1.16,
            tempo: 0.74,
            risk_budget: 0.76,
            compactness: 0.42,
            press_intensity: 0.62,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::DefendBlock,
        intercept: 0.02,
        possession: -1.14,
        ball_progress: -0.42,
        centrality: 0.10,
        pressure: 0.12,
        crowding: 0.08,
        backward_outlets: -0.08,
        forward_outlets: -0.04,
        weak_side_outlets: -0.06,
        team_width: -0.18,
        defensive_threat: 0.78,
        transition: -0.04,
        switch_inertia: 0.24,
        signals: TeamPlanSignals {
            forward_bias: 0.18,
            recycle_bias: 0.42,
            switch_bias: 0.24,
            width_scale: 0.84,
            depth_scale: 0.82,
            tempo: 0.40,
            risk_budget: 0.28,
            compactness: 0.88,
            press_intensity: 0.28,
        },
    },
    TeamPlanProfile {
        kind: TeamPlanKind::DefendPress,
        intercept: -0.18,
        possession: -0.96,
        ball_progress: 0.14,
        centrality: 0.26,
        pressure: 0.38,
        crowding: 0.26,
        backward_outlets: -0.10,
        forward_outlets: -0.06,
        weak_side_outlets: -0.12,
        team_width: -0.04,
        defensive_threat: 0.20,
        transition: 0.42,
        switch_inertia: 0.13,
        signals: TeamPlanSignals {
            forward_bias: 0.28,
            recycle_bias: 0.34,
            switch_bias: 0.22,
            width_scale: 0.94,
            depth_scale: 0.96,
            tempo: 0.66,
            risk_budget: 0.48,
            compactness: 0.66,
            press_intensity: 0.80,
        },
    },
];

pub fn team_plan_signals(kind: TeamPlanKind) -> TeamPlanSignals {
    TEAM_PLAN_PROFILES
        .iter()
        .find(|profile| profile.kind == kind)
        .map(|profile| profile.signals)
        .unwrap_or_default()
}

pub fn team_plan_action_utility(input: &TeamPlanActionInput) -> TeamPlanActionUtility {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let length = input.pitch_length.max(1.0);
    let width = input.pitch_width.max(1.0);
    let half_width = width / 2.0;
    let signed_progress =
        ((input.target.0 - input.origin.0) * forward_dir / length).clamp(-1.0, 1.0);
    let forward_progress = smoothstep(-0.02, 0.16, signed_progress);
    let backward_progress = smoothstep(-0.02, 0.16, -signed_progress);
    let lateral_change = ((input.target.1 - input.origin.1).abs() / half_width).clamp(0.0, 1.0);
    let origin_side = (input.origin.1 - half_width) / half_width;
    let target_side = (input.target.1 - half_width) / half_width;
    let cross_field = (-origin_side * target_side).clamp(0.0, 1.0);
    let retention = (input.success_probability * input.continuation_probability).clamp(0.0, 1.0);
    let recycle_value = backward_progress * retention;
    let switch_value = lateral_change * cross_field * retention;
    let risk = input.risk.clamp(0.0, 1.0);
    let alignment = (0.22 * retention
        + 0.34 * input.signals.forward_bias * forward_progress
        + 0.30 * input.signals.recycle_bias * recycle_value
        + 0.34 * input.signals.switch_bias * switch_value
        - 0.26 * (1.0 - input.signals.risk_budget) * risk)
        .clamp(-0.25, 1.25);
    TeamPlanActionUtility {
        forward_progress,
        recycle_value,
        switch_value,
        retention,
        alignment,
        multiplier: (0.76 + alignment).clamp(0.55, 1.70),
    }
}

pub fn team_plan_movement_target(
    local_target: (f64, f64),
    tactical_anchor: (f64, f64),
    signals: TeamPlanSignals,
) -> (f64, f64) {
    let base_formation_adherence = (0.10
        + 0.26 * signals.recycle_bias.clamp(0.0, 1.0)
        + 0.26 * signals.switch_bias.clamp(0.0, 1.0)
        + 0.16 * signals.compactness.clamp(0.0, 1.0)
        + 0.12 * (1.0 - signals.forward_bias.clamp(0.0, 1.0)))
    .clamp(0.0, 0.82);
    let task_extent = distance(local_target, tactical_anchor);
    let task_compliance = smoothstep(0.0, 14.0, task_extent);
    let formation_adherence = base_formation_adherence * (0.42 + 0.58 * task_compliance);
    (
        local_target.0 * (1.0 - formation_adherence) + tactical_anchor.0 * formation_adherence,
        local_target.1 * (1.0 - formation_adherence) + tactical_anchor.1 * formation_adherence,
    )
}

pub fn project_team_plan_formation_into(
    input: &TeamPlanFormationProjectionInput<'_>,
    output: &mut [TeamPlanProjectionPlayerOutput],
) -> usize {
    project_team_plan_formation_into_with_target_provider(input, output, |player, _| {
        team_plan_movement_target(player.target_pos, player.tactical_anchor, input.signals)
    })
}

pub(crate) fn project_team_plan_formation_into_with_prepared_targets(
    input: &TeamPlanFormationProjectionInput<'_>,
    movement_targets: &[(f64, f64)],
    output: &mut [TeamPlanProjectionPlayerOutput],
) -> usize {
    assert_eq!(
        movement_targets.len(),
        input.players.len(),
        "prepared formation movement targets must align with the player set"
    );
    project_team_plan_formation_into_with_target_provider(input, output, |_, index| {
        movement_targets[index]
    })
}

fn project_team_plan_formation_into_with_target_provider(
    input: &TeamPlanFormationProjectionInput<'_>,
    output: &mut [TeamPlanProjectionPlayerOutput],
    mut movement_target: impl FnMut(&TeamPlanProjectionPlayerInput, usize) -> (f64, f64),
) -> usize {
    assert!(
        output.len() >= input.players.len(),
        "projection output buffer is smaller than the player set"
    );
    let duration_ticks = input.duration_ticks.max(0);
    for (output_index, player) in input.players.iter().enumerate() {
        if input.controlled_player_index == Some(player.index) {
            output[output_index] = TeamPlanProjectionPlayerOutput {
                index: player.index,
                pos: input.controlled_player_pos.unwrap_or(player.pos),
                velocity: (0.0, 0.0),
            };
            continue;
        }

        let target = movement_target(player, output_index);
        let mut pos = player.pos;
        let mut velocity = player.velocity;
        if player.is_mobile {
            for tick_index in 0..duration_ticks {
                let motion_input = crate::physics::PlayerMotionInput {
                        pos,
                        target,
                        velocity,
                        speed_ability: player.speed_ability,
                        desired_speed: player.desired_speed,
                        acceleration_scale: player.acceleration_scale,
                        player_max_speed: input.player_max_speed,
                        player_min_speed: input.player_min_speed,
                        pitch_length: input.pitch_length,
                        pitch_width: input.pitch_width,
                    };
                let final_tick = tick_index + 1 == duration_ticks;
                let elapsed_fraction = if final_tick {
                    input.elapsed_fraction.clamp(0.0, 1.0)
                } else {
                    1.0
                };
                let movement = if elapsed_fraction >= 1.0 {
                    crate::physics::advance_player_motion(&motion_input)
                } else {
                    crate::physics::advance_player_motion_fraction(
                        &motion_input,
                        elapsed_fraction,
                    )
                };
                pos = movement.pos;
                velocity = movement.velocity;
            }
        }
        output[output_index] = TeamPlanProjectionPlayerOutput {
            index: player.index,
            pos,
            velocity,
        };
    }
    input.players.len()
}

pub fn project_team_plan_formation(
    input: &TeamPlanFormationProjectionInput<'_>,
) -> TeamPlanFormationProjection {
    let mut players = vec![
        TeamPlanProjectionPlayerOutput {
            index: 0,
            pos: (0.0, 0.0),
            velocity: (0.0, 0.0),
        };
        input.players.len()
    ];
    let player_count = project_team_plan_formation_into(input, &mut players);
    players.truncate(player_count);
    TeamPlanFormationProjection { players }
}

fn normalized_outlet_value(
    player: TeamPlanPlayerInput,
    ball_pos: (f64, f64),
    forward_dir: f64,
    opposing_positions: &[(f64, f64)],
    direction: f64,
) -> f64 {
    let progress = (player.pos.0 - ball_pos.0) * forward_dir * direction;
    let directional_fit = if direction.abs() < f64::EPSILON {
        1.0
    } else {
        smoothstep(1.0, 13.0, progress)
    };
    let range = distance(player.pos, ball_pos);
    let distance_fit = smoothstep(4.0, 11.0, range) * (1.0 - smoothstep(36.0, 60.0, range));
    let nearest_opp = opposing_positions
        .iter()
        .map(|opponent| distance(player.pos, *opponent))
        .fold(30.0, f64::min);
    let openness = smoothstep(2.0, 11.0, nearest_opp);
    let goalkeeper_weight = if player.is_goalkeeper { 0.58 } else { 1.0 };
    directional_fit * distance_fit * openness * goalkeeper_weight
}

pub fn team_plan_features(input: &TeamPlanUpdateInput<'_>) -> TeamPlanFeatures {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let half_width = (input.pitch_width / 2.0).max(1.0);
    let ball_progress = ((input.ball_pos.0 / input.pitch_length) * forward_dir
        + if input.attacking_right { 0.0 } else { 1.0 })
    .clamp(0.0, 1.0);
    let centrality = 1.0 - ((input.ball_pos.1 - half_width).abs() / half_width).min(1.0);
    assert!(
        input.players.len() <= MAX_TEAM_PLAN_PLAYERS
            && input.opponents.len() <= MAX_TEAM_PLAN_PLAYERS,
        "team plan expects at most {MAX_TEAM_PLAN_PLAYERS} players per team"
    );
    let mut opposing_position_buffer = [(0.0, 0.0); MAX_TEAM_PLAN_PLAYERS];
    let mut opposing_count = 0;
    for opponent in input.opponents {
        if !opponent.is_goalkeeper {
            opposing_position_buffer[opposing_count] = opponent.pos;
            opposing_count += 1;
        }
    }
    let opposing_positions = &opposing_position_buffer[..opposing_count];
    let ball_pressure = opposing_positions
        .iter()
        .map(|opponent| (-distance(*opponent, input.ball_pos) / 8.0).exp())
        .sum::<f64>()
        .min(2.0)
        / 2.0;
    let mut ball_crowding_sum = 0.0;
    let mut min_y = input.pitch_width / 2.0;
    let mut max_y = input.pitch_width / 2.0;
    for player in input.players {
        if player.is_goalkeeper {
            continue;
        }
        ball_crowding_sum += (-distance(player.pos, input.ball_pos) / 7.0).exp();
        min_y = min_y.min(player.pos.1);
        max_y = max_y.max(player.pos.1);
    }
    let ball_crowding = ball_crowding_sum.min(3.0) / 3.0;
    let backward_outlets = input
        .players
        .iter()
        .copied()
        .map(|player| {
            normalized_outlet_value(
                player,
                input.ball_pos,
                forward_dir,
                opposing_positions,
                -1.0,
            )
        })
        .sum::<f64>()
        .min(2.5)
        / 2.5;
    let forward_outlets = input
        .players
        .iter()
        .copied()
        .map(|player| {
            normalized_outlet_value(player, input.ball_pos, forward_dir, opposing_positions, 1.0)
        })
        .sum::<f64>()
        .min(2.5)
        / 2.5;
    let ball_side = (input.ball_pos.1 - half_width) / half_width;
    let weak_side_outlets = input
        .players
        .iter()
        .copied()
        .map(|player| {
            let side = (player.pos.1 - half_width) / half_width;
            let weak_side = (-side * ball_side).clamp(0.0, 1.0);
            let outlet = normalized_outlet_value(
                player,
                input.ball_pos,
                forward_dir,
                opposing_positions,
                0.0,
            );
            weak_side * outlet
        })
        .sum::<f64>()
        .min(1.8)
        / 1.8;
    let team_width = ((max_y - min_y) / input.pitch_width.max(1.0)).clamp(0.0, 1.0);
    let defensive_threat =
        (1.0 - ball_progress) * (0.50 + 0.50 * centrality) * (0.55 + 0.45 * ball_pressure);
    let transition = if matches!(
        input.phase,
        "transition_atk" | "transition_def" | "contesting"
    ) {
        1.0
    } else {
        0.0
    };
    TeamPlanFeatures {
        ball_progress,
        centrality,
        ball_pressure,
        ball_crowding,
        backward_outlets,
        forward_outlets,
        weak_side_outlets,
        team_width,
        defensive_threat,
        transition,
        possession_probability: input.possession_probability.clamp(0.0, 1.0),
    }
}

fn profile_value(profile: TeamPlanProfile, features: TeamPlanFeatures) -> f64 {
    let possession_alignment = features.possession_probability * 2.0 - 1.0;
    profile.intercept
        + profile.possession * possession_alignment
        + profile.ball_progress * features.ball_progress
        + profile.centrality * features.centrality
        + profile.pressure * features.ball_pressure
        + profile.crowding * features.ball_crowding
        + profile.backward_outlets * features.backward_outlets
        + profile.forward_outlets * features.forward_outlets
        + profile.weak_side_outlets * features.weak_side_outlets
        + profile.team_width * features.team_width
        + profile.defensive_threat * features.defensive_threat
        + profile.transition * features.transition
}

fn current_plan_inertia(current: TeamPlanState) -> f64 {
    TEAM_PLAN_PROFILES
        .iter()
        .find(|profile| profile.kind == current.kind)
        .map(|profile| profile.switch_inertia)
        .unwrap_or(0.15)
}

fn team_plan_candidate(
    profile: TeamPlanProfile,
    current: TeamPlanState,
    current_inertia: f64,
    features: TeamPlanFeatures,
) -> TeamPlanCandidate {
    let raw_value = profile_value(profile, features);
    let switch_cost = if profile.kind == current.kind {
        0.0
    } else {
        current_inertia * (0.30 + 0.70 * current.commitment.clamp(0.0, 1.0))
    };
    TeamPlanCandidate {
        kind: profile.kind,
        raw_value,
        switch_cost,
        value: raw_value - switch_cost,
    }
}

fn team_plan_state(
    current: TeamPlanState,
    selected: TeamPlanCandidate,
    best_raw_value: f64,
) -> TeamPlanState {
    let retained = if selected.kind == current.kind {
        1.0
    } else {
        0.0
    };
    let evidence = (selected.raw_value - best_raw_value + 1.0).clamp(0.0, 1.0);
    let commitment =
        (current.commitment * (0.45 + 0.40 * retained) + 0.20 * retained + 0.14 * evidence)
            .clamp(0.0, 1.0);
    TeamPlanState {
        kind: selected.kind,
        commitment,
        value: selected.raw_value,
    }
}

fn blend_team_plan_signals(
    candidates: &[TeamPlanCandidate],
    selected: TeamPlanCandidate,
) -> TeamPlanSignals {
    let temperature = 0.18;
    let mut total_weight = 0.0;
    let mut forward_bias = 0.0;
    let mut recycle_bias = 0.0;
    let mut switch_bias = 0.0;
    let mut width_scale = 0.0;
    let mut depth_scale = 0.0;
    let mut tempo = 0.0;
    let mut risk_budget = 0.0;
    let mut compactness = 0.0;
    let mut press_intensity = 0.0;
    for candidate in candidates {
        let weight = ((candidate.value - selected.value) / temperature).exp();
        let signals = team_plan_signals(candidate.kind);
        total_weight += weight;
        forward_bias += weight * signals.forward_bias;
        recycle_bias += weight * signals.recycle_bias;
        switch_bias += weight * signals.switch_bias;
        width_scale += weight * signals.width_scale;
        depth_scale += weight * signals.depth_scale;
        tempo += weight * signals.tempo;
        risk_budget += weight * signals.risk_budget;
        compactness += weight * signals.compactness;
        press_intensity += weight * signals.press_intensity;
    }
    if total_weight <= 1e-12 {
        return team_plan_signals(selected.kind);
    }
    TeamPlanSignals {
        forward_bias: forward_bias / total_weight,
        recycle_bias: recycle_bias / total_weight,
        switch_bias: switch_bias / total_weight,
        width_scale: width_scale / total_weight,
        depth_scale: depth_scale / total_weight,
        tempo: tempo / total_weight,
        risk_budget: risk_budget / total_weight,
        compactness: compactness / total_weight,
        press_intensity: press_intensity / total_weight,
    }
}

pub fn select_team_plan(input: &TeamPlanUpdateInput<'_>) -> (TeamPlanState, TeamPlanSignals) {
    let features = team_plan_features(input);
    let current_inertia = current_plan_inertia(input.current);
    let mut candidates = [TeamPlanCandidate {
        kind: TeamPlanKind::BuildUp,
        raw_value: 0.0,
        switch_cost: 0.0,
        value: 0.0,
    }; TEAM_PLAN_PROFILES.len()];
    let mut selected = None;
    let mut best_raw_value = f64::NEG_INFINITY;
    for (index, profile) in TEAM_PLAN_PROFILES.iter().copied().enumerate() {
        let candidate = team_plan_candidate(profile, input.current, current_inertia, features);
        candidates[index] = candidate;
        if selected
            .map(|current: TeamPlanCandidate| {
                candidate
                    .value
                    .partial_cmp(&current.value)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    != std::cmp::Ordering::Less
            })
            .unwrap_or(true)
        {
            selected = Some(candidate);
        }
        best_raw_value = best_raw_value.max(candidate.raw_value);
    }
    let selected = selected.expect("team plan profiles must not be empty");
    let state = team_plan_state(input.current, selected, best_raw_value);
    (state, blend_team_plan_signals(&candidates, selected))
}

pub fn update_team_plan(input: &TeamPlanUpdateInput<'_>) -> TeamPlanUpdateOutput {
    let features = team_plan_features(input);
    let current_inertia = current_plan_inertia(input.current);
    let candidates: Vec<TeamPlanCandidate> = TEAM_PLAN_PROFILES
        .iter()
        .map(|profile| team_plan_candidate(*profile, input.current, current_inertia, features))
        .collect();
    let selected = candidates
        .iter()
        .max_by(|left, right| {
            left.value
                .partial_cmp(&right.value)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .copied()
        .unwrap_or(TeamPlanCandidate {
            kind: input.current.kind,
            raw_value: input.current.value,
            switch_cost: 0.0,
            value: input.current.value,
        });
    let best_raw_value = candidates
        .iter()
        .map(|candidate| candidate.raw_value)
        .fold(selected.raw_value, f64::max);
    let state = team_plan_state(input.current, selected, best_raw_value);
    TeamPlanUpdateOutput {
        state,
        signals: blend_team_plan_signals(&candidates, selected),
        features,
        candidates,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn player(pos: (f64, f64)) -> TeamPlanPlayerInput {
        TeamPlanPlayerInput {
            pos,
            is_goalkeeper: false,
        }
    }

    fn opponent(pos: (f64, f64)) -> TeamPlanOpponentInput {
        TeamPlanOpponentInput {
            pos,
            is_goalkeeper: false,
        }
    }

    #[test]
    fn congested_ball_side_with_weak_side_outlet_selects_switch() {
        let players = [
            TeamPlanPlayerInput {
                pos: (6.0, 34.0),
                is_goalkeeper: true,
            },
            player((43.0, 10.0)),
            player((48.0, 24.0)),
            player((60.0, 59.0)),
            player((72.0, 51.0)),
            player((77.0, 16.0)),
        ];
        let opponents = [
            opponent((60.0, 9.0)),
            opponent((63.0, 12.0)),
            opponent((66.0, 15.0)),
            opponent((74.0, 28.0)),
            opponent((78.0, 40.0)),
        ];
        let output = update_team_plan(&TeamPlanUpdateInput {
            current: TeamPlanState::default(),
            ball_pos: (64.0, 9.0),
            attacking_right: true,
            possession_probability: 1.0,
            phase: "attacking",
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        });
        assert_eq!(
            output.state.kind,
            TeamPlanKind::Switch,
            "features={:?}, candidates={:?}",
            output.features,
            output.candidates
        );
        assert!(output.features.ball_pressure > 0.55);
        assert!(output.features.weak_side_outlets > 0.20);
        assert!(output.signals.width_scale > 1.2);
        assert!(
            output.signals.switch_bias > 0.85,
            "the dominant switch plan must retain a strong switch tendency: features={:?}, signals={:?}, candidates={:?}",
            output.features,
            output.signals,
            output.candidates,
        );
        assert!(
            output.signals.switch_bias < team_plan_signals(TeamPlanKind::Switch).switch_bias,
            "continuous planning should retain secondary build-up and recycle evidence"
        );
    }

    #[test]
    fn plan_switch_requires_materially_better_state_value() {
        let players = [
            TeamPlanPlayerInput {
                pos: (6.0, 34.0),
                is_goalkeeper: true,
            },
            player((31.0, 18.0)),
            player((35.0, 48.0)),
            player((48.0, 15.0)),
            player((52.0, 53.0)),
            player((62.0, 34.0)),
        ];
        let opponents = [
            opponent((54.0, 25.0)),
            opponent((58.0, 43.0)),
            opponent((68.0, 34.0)),
            opponent((75.0, 18.0)),
        ];
        let first = update_team_plan(&TeamPlanUpdateInput {
            current: TeamPlanState::default(),
            ball_pos: (35.0, 34.0),
            attacking_right: true,
            possession_probability: 1.0,
            phase: "attacking",
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        });
        let committed = TeamPlanState {
            kind: first.state.kind,
            commitment: 0.92,
            value: first.state.value,
        };
        let second = update_team_plan(&TeamPlanUpdateInput {
            current: committed,
            ball_pos: (38.0, 35.0),
            attacking_right: true,
            possession_probability: 1.0,
            phase: "attacking",
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        });
        assert_eq!(second.state.kind, committed.kind);
        assert!(second.state.commitment > 0.7);
    }

    #[test]
    fn nearby_match_states_produce_continuous_mixed_plan_signals() {
        let players = [
            TeamPlanPlayerInput {
                pos: (7.0, 34.0),
                is_goalkeeper: true,
            },
            player((31.0, 18.0)),
            player((35.0, 48.0)),
            player((48.0, 15.0)),
            player((52.0, 53.0)),
            player((62.0, 34.0)),
        ];
        let opponents = [
            opponent((54.0, 25.0)),
            opponent((58.0, 43.0)),
            opponent((68.0, 34.0)),
            opponent((75.0, 18.0)),
        ];
        let input = TeamPlanUpdateInput {
            current: TeamPlanState::default(),
            ball_pos: (52.0, 31.0),
            attacking_right: true,
            possession_probability: 1.0,
            phase: "possession",
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        };
        let first = update_team_plan(&input);
        let second = update_team_plan(&TeamPlanUpdateInput {
            ball_pos: (52.2, 31.0),
            ..input
        });
        let signal_distance = (first.signals.forward_bias - second.signals.forward_bias).abs()
            + (first.signals.recycle_bias - second.signals.recycle_bias).abs()
            + (first.signals.switch_bias - second.signals.switch_bias).abs()
            + (first.signals.press_intensity - second.signals.press_intensity).abs();

        assert!(signal_distance > 0.0);
        assert!(
            signal_distance < 0.05,
            "small spatial evidence changes must not cause a profile-sized tactical jump"
        );
        let dominant = team_plan_signals(first.state.kind);
        assert!(
            (first.signals.forward_bias - dominant.forward_bias).abs() > 1e-6
                || (first.signals.recycle_bias - dominant.recycle_bias).abs() > 1e-6
                || (first.signals.switch_bias - dominant.switch_bias).abs() > 1e-6,
            "the plan label may stay discrete, but its executable signals must be mixed"
        );
    }

    #[test]
    fn losing_possession_prefers_compact_defensive_plan() {
        let players = [
            TeamPlanPlayerInput {
                pos: (6.0, 34.0),
                is_goalkeeper: true,
            },
            player((22.0, 22.0)),
            player((24.0, 45.0)),
            player((34.0, 34.0)),
            player((43.0, 15.0)),
            player((46.0, 53.0)),
        ];
        let opponents = [
            opponent((30.0, 28.0)),
            opponent((34.0, 38.0)),
            opponent((40.0, 34.0)),
            opponent((47.0, 20.0)),
        ];
        let output = update_team_plan(&TeamPlanUpdateInput {
            current: TeamPlanState::default(),
            ball_pos: (31.0, 34.0),
            attacking_right: true,
            possession_probability: 0.0,
            phase: "defending",
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        });
        assert_eq!(output.state.kind, TeamPlanKind::DefendBlock);
        assert!(output.signals.compactness > 0.8);
        assert!(output.signals.width_scale < 0.9);
    }

    #[test]
    fn switch_plan_rewards_retained_cross_field_control_more_than_direct_progress() {
        let signals = team_plan_signals(TeamPlanKind::Switch);
        let switch = team_plan_action_utility(&TeamPlanActionInput {
            signals,
            origin: (60.0, 9.0),
            target: (62.0, 57.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            success_probability: 0.88,
            continuation_probability: 0.90,
            risk: 0.12,
        });
        let direct = team_plan_action_utility(&TeamPlanActionInput {
            signals,
            origin: (60.0, 9.0),
            target: (79.0, 13.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            success_probability: 0.72,
            continuation_probability: 0.72,
            risk: 0.38,
        });
        assert!(switch.switch_value > 0.3);
        assert!(switch.multiplier > direct.multiplier);
    }

    #[test]
    fn recycle_plan_rewards_safe_backward_control_under_pressure() {
        let signals = team_plan_signals(TeamPlanKind::Recycle);
        let recycle = team_plan_action_utility(&TeamPlanActionInput {
            signals,
            origin: (64.0, 12.0),
            target: (49.0, 21.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            success_probability: 0.93,
            continuation_probability: 0.95,
            risk: 0.08,
        });
        let forced = team_plan_action_utility(&TeamPlanActionInput {
            signals,
            origin: (64.0, 12.0),
            target: (82.0, 20.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            success_probability: 0.54,
            continuation_probability: 0.48,
            risk: 0.56,
        });
        assert!(recycle.recycle_value > 0.5);
        assert!(recycle.multiplier > forced.multiplier);
    }

    #[test]
    fn formation_projection_advances_support_toward_the_plan_without_moving_controller() {
        let signals = team_plan_signals(TeamPlanKind::Recycle);
        let players = [
            TeamPlanProjectionPlayerInput {
                index: 0,
                pos: (48.0, 34.0),
                velocity: (0.0, 0.0),
                target_pos: (48.0, 34.0),
                tactical_anchor: (48.0, 34.0),
                speed_ability: 80,
                desired_speed: 4.5,
                acceleration_scale: 1.0,
                is_mobile: true,
            },
            TeamPlanProjectionPlayerInput {
                index: 1,
                pos: (50.0, 34.0),
                velocity: (0.0, 0.0),
                target_pos: (62.0, 54.0),
                tactical_anchor: (58.0, 58.0),
                speed_ability: 84,
                desired_speed: 5.0,
                acceleration_scale: 1.0,
                is_mobile: true,
            },
        ];
        let one_tick = project_team_plan_formation(&TeamPlanFormationProjectionInput {
            signals,
            duration_ticks: 1,
            elapsed_fraction: 1.0,
            controlled_player_index: Some(0),
            controlled_player_pos: Some((49.5, 34.0)),
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            players: &players,
        });
        let three_ticks = project_team_plan_formation(&TeamPlanFormationProjectionInput {
            duration_ticks: 3,
            ..TeamPlanFormationProjectionInput {
                signals,
                duration_ticks: 1,
                elapsed_fraction: 1.0,
                controlled_player_index: Some(0),
                controlled_player_pos: Some((49.5, 34.0)),
                pitch_length: 105.0,
                pitch_width: 68.0,
                player_max_speed: 8.0,
                player_min_speed: 2.5,
                players: &players,
            }
        });
        let one_support = one_tick.players[1].pos;
        let three_support = three_ticks.players[1].pos;

        assert_eq!(three_ticks.players[0].pos, (49.5, 34.0));
        assert!(three_support.0 > one_support.0);
        assert!(three_support.1 > one_support.1);
    }

    #[test]
    fn prepared_formation_targets_preserve_reference_projection() {
        let signals = team_plan_signals(TeamPlanKind::Switch);
        let players = [
            TeamPlanProjectionPlayerInput {
                index: 0,
                pos: (48.0, 34.0),
                velocity: (0.7, -0.2),
                target_pos: (62.0, 20.0),
                tactical_anchor: (54.0, 26.0),
                speed_ability: 80,
                desired_speed: 4.5,
                acceleration_scale: 1.0,
                is_mobile: true,
            },
            TeamPlanProjectionPlayerInput {
                index: 1,
                pos: (40.0, 52.0),
                velocity: (-0.3, 0.5),
                target_pos: (31.0, 58.0),
                tactical_anchor: (36.0, 55.0),
                speed_ability: 74,
                desired_speed: 4.0,
                acceleration_scale: 1.15,
                is_mobile: true,
            },
            TeamPlanProjectionPlayerInput {
                index: 2,
                pos: (27.0, 34.0),
                velocity: (0.0, 0.0),
                target_pos: (27.0, 34.0),
                tactical_anchor: (27.0, 34.0),
                speed_ability: 70,
                desired_speed: 3.5,
                acceleration_scale: 1.0,
                is_mobile: false,
            },
        ];
        let input = TeamPlanFormationProjectionInput {
            signals,
            duration_ticks: 3,
            elapsed_fraction: 1.0,
            controlled_player_index: Some(0),
            controlled_player_pos: Some((49.0, 34.5)),
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            players: &players,
        };
        let targets = players
            .iter()
            .map(|player| {
                team_plan_movement_target(player.target_pos, player.tactical_anchor, signals)
            })
            .collect::<Vec<_>>();
        let mut reference = [TeamPlanProjectionPlayerOutput {
            index: 0,
            pos: (0.0, 0.0),
            velocity: (0.0, 0.0),
        }; 3];
        let mut prepared = reference;
        let reference_len = project_team_plan_formation_into(&input, &mut reference);
        let prepared_len =
            project_team_plan_formation_into_with_prepared_targets(&input, &targets, &mut prepared);

        assert_eq!(prepared_len, reference_len);
        for (actual, expected) in prepared[..prepared_len]
            .iter()
            .zip(reference[..reference_len].iter())
        {
            assert_eq!(actual.index, expected.index);
            assert_eq!(actual.pos.0.to_bits(), expected.pos.0.to_bits());
            assert_eq!(actual.pos.1.to_bits(), expected.pos.1.to_bits());
            assert_eq!(actual.velocity.0.to_bits(), expected.velocity.0.to_bits());
            assert_eq!(actual.velocity.1.to_bits(), expected.velocity.1.to_bits());
        }
    }

    #[test]
    fn projected_and_live_movement_share_the_same_plan_constrained_target() {
        let signals = team_plan_signals(TeamPlanKind::Recycle);
        let local_target = (72.0, 14.0);
        let tactical_anchor = (54.0, 56.0);
        let target = team_plan_movement_target(local_target, tactical_anchor, signals);
        let desired_speed = crate::player_move_speed(&crate::PlayerMoveSpeedInput {
            pos: (48.0, 34.0),
            target_pos: target,
            speed_ability: 80,
            movement_intent: "support",
            state: "off_ball",
            player_max_speed: 8.0,
            player_min_speed: 2.5,
        })
        .speed;
        let player = TeamPlanProjectionPlayerInput {
            index: 0,
            pos: (48.0, 34.0),
            velocity: (0.0, 0.0),
            target_pos: local_target,
            tactical_anchor,
            speed_ability: 80,
            desired_speed,
            acceleration_scale: 1.0,
            is_mobile: true,
        };
        let projection = project_team_plan_formation(&TeamPlanFormationProjectionInput {
            signals,
            duration_ticks: 1,
            elapsed_fraction: 1.0,
            controlled_player_index: None,
            controlled_player_pos: None,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            players: &[player],
        });
        let live = crate::physics::advance_player_motion(&crate::physics::PlayerMotionInput {
            pos: player.pos,
            target,
            velocity: player.velocity,
            speed_ability: player.speed_ability,
            desired_speed,
            acceleration_scale: player.acceleration_scale,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert_eq!(projection.players[0].pos, live.pos);
        assert_eq!(projection.players[0].velocity, live.velocity);
    }

    #[test]
    fn projected_formation_uses_the_same_fractional_motion_budget_as_live() {
        let signals = team_plan_signals(TeamPlanKind::Recycle);
        let target = (72.0, 14.0);
        let player = TeamPlanProjectionPlayerInput {
            index: 0,
            pos: (48.0, 34.0),
            velocity: (0.0, 0.0),
            target_pos: target,
            tactical_anchor: target,
            speed_ability: 80,
            desired_speed: 4.5,
            acceleration_scale: 1.0,
            is_mobile: true,
        };
        let elapsed_fraction = 0.37;
        let projection = project_team_plan_formation(&TeamPlanFormationProjectionInput {
            signals,
            duration_ticks: 1,
            elapsed_fraction,
            controlled_player_index: None,
            controlled_player_pos: None,
            pitch_length: 105.0,
            pitch_width: 68.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            players: &[player],
        });
        let live = crate::physics::advance_player_motion_fraction(
            &crate::physics::PlayerMotionInput {
                pos: player.pos,
                target,
                velocity: player.velocity,
                speed_ability: player.speed_ability,
                desired_speed: player.desired_speed,
                acceleration_scale: player.acceleration_scale,
                player_max_speed: 8.0,
                player_min_speed: 2.5,
                pitch_length: 105.0,
                pitch_width: 68.0,
            },
            elapsed_fraction,
        );

        assert_eq!(projection.players[0].pos, live.pos);
        assert_eq!(projection.players[0].velocity, live.velocity);
    }

    #[test]
    fn distant_local_responsibility_remains_coupled_to_the_shape_anchor() {
        let signals = team_plan_signals(TeamPlanKind::DefendPress);
        let local_target = (74.0, 18.0);
        let tactical_anchor = (36.0, 50.0);
        let target = team_plan_movement_target(local_target, tactical_anchor, signals);

        assert!(
            distance(target, tactical_anchor) < distance(local_target, tactical_anchor),
            "target={target:?}, local={local_target:?}, anchor={tactical_anchor:?}"
        );
    }
}
