use crate::physics::{distance, smoothstep};

pub const MAX_FIXED_TEAM_DEFENSE_PLAYERS: usize = 11;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DefenseTaskKind {
    CloseDown,
    Press,
    Mark,
    BlockLane,
    RecoverShape,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct DefenseResourceClaim {
    pub carrier_closure: f64,
    pub carrier_engagement: f64,
    pub cover: f64,
    pub lane_screen: f64,
    pub wide_balance: [f64; 2],
    pub outlet_coverage: [f64; MAX_FIXED_TEAM_DEFENSE_PLAYERS],
}

impl DefenseResourceClaim {
    fn clamped(self) -> Self {
        Self {
            carrier_closure: self.carrier_closure.clamp(0.0, 1.0),
            carrier_engagement: self.carrier_engagement.clamp(0.0, 1.0),
            cover: self.cover.clamp(0.0, 1.0),
            lane_screen: self.lane_screen.clamp(0.0, 1.0),
            wide_balance: [
                self.wide_balance[0].clamp(0.0, 1.0),
                self.wide_balance[1].clamp(0.0, 1.0),
            ],
            outlet_coverage: self
                .outlet_coverage
                .map(|coverage| coverage.clamp(0.0, 1.0)),
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct DefenseResourceDemand {
    pub carrier_closure: f64,
    pub carrier_engagement: f64,
    pub cover: f64,
    pub lane_screen: f64,
    pub wide_balance: [f64; 2],
    pub outlet_coverage: [f64; MAX_FIXED_TEAM_DEFENSE_PLAYERS],
}

impl DefenseResourceDemand {
    fn clamped(self) -> Self {
        Self {
            carrier_closure: self.carrier_closure.clamp(0.0, 1.0),
            carrier_engagement: self.carrier_engagement.clamp(0.0, 1.0),
            cover: self.cover.clamp(0.0, 1.0),
            lane_screen: self.lane_screen.clamp(0.0, 1.0),
            wide_balance: [
                self.wide_balance[0].clamp(0.0, 1.0),
                self.wide_balance[1].clamp(0.0, 1.0),
            ],
            outlet_coverage: self
                .outlet_coverage
                .map(|coverage| coverage.clamp(0.0, 1.0)),
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct DefenseTaskContinuity {
    pub active: bool,
    pub target: (f64, f64),
    pub commitment: f64,
    pub resource_claim: DefenseResourceClaim,
}

impl DefenseTaskContinuity {
    fn clamped(self) -> Self {
        Self {
            active: self.active,
            target: self.target,
            commitment: self.commitment.clamp(0.0, 1.0),
            resource_claim: self.resource_claim.clamped(),
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseCandidate {
    pub target: (f64, f64),
    pub projected_pos: (f64, f64),
    pub local_value: f64,
    pub residual_threat: f64,
    pub pressure_coverage: f64,
    pub resource_claim: DefenseResourceClaim,
    pub task_kind: DefenseTaskKind,
}

impl Default for TeamDefenseCandidate {
    fn default() -> Self {
        Self {
            target: (0.0, 0.0),
            projected_pos: (0.0, 0.0),
            local_value: 0.0,
            residual_threat: 1.0,
            pressure_coverage: 0.0,
            resource_claim: DefenseResourceClaim::default(),
            task_kind: DefenseTaskKind::RecoverShape,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefensePlayerInput<'a> {
    pub index: usize,
    pub anchor: (f64, f64),
    pub candidates: &'a [TeamDefenseCandidate],
}

#[derive(Clone, Debug)]
pub struct TeamDefenseAssignmentInput<'a> {
    pub players: &'a [TeamDefensePlayerInput<'a>],
    pub compactness: f64,
    pub immediate_threat: f64,
    pub press_intensity: f64,
    pub resource_demand: DefenseResourceDemand,
    pub local_candidate_indices: Option<&'a [usize]>,
    pub task_continuities: Option<&'a [DefenseTaskContinuity]>,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseAssignment {
    pub index: usize,
    pub candidate_index: usize,
    pub local_value: f64,
    pub residual_threat: f64,
    pub local_intent_cost: f64,
    pub task_retarget_cost: f64,
}

#[derive(Clone, Debug)]
pub struct TeamDefenseAssignmentOutput {
    pub assignments: Vec<TeamDefenseAssignment>,
    pub objective: f64,
    pub formation_scale: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseCoordinationSummary {
    pub objective: f64,
    pub formation_scale: f64,
}

#[derive(Clone, Copy, Debug)]
struct SupportedEngagementRequirement {
    engager_player_index: usize,
    engager_candidate_index: usize,
    cover_player_index: usize,
    cover_candidate_index: usize,
    minimum_supported_engagement: f64,
}

fn formation_scale(players: &[TeamDefensePlayerInput<'_>]) -> f64 {
    let mut nearest_distances = Vec::with_capacity(players.len());
    for (index, player) in players.iter().enumerate() {
        let nearest = players
            .iter()
            .enumerate()
            .filter(|(other_index, _)| *other_index != index)
            .map(|(_, other)| distance(player.anchor, other.anchor))
            .filter(|distance| *distance > 1e-6)
            .fold(f64::INFINITY, f64::min);
        if nearest.is_finite() {
            nearest_distances.push(nearest);
        }
    }
    if nearest_distances.is_empty() {
        return 1.0;
    }
    nearest_distances
        .sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    nearest_distances[nearest_distances.len() / 2].max(1.0)
}

fn formation_scale_fixed(players: &[TeamDefensePlayerInput<'_>]) -> f64 {
    assert!(
        players.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense coordination supports eleven players"
    );
    let mut nearest_distances = [0.0; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut nearest_count = 0;
    for (index, player) in players.iter().enumerate() {
        let nearest = players
            .iter()
            .enumerate()
            .filter(|(other_index, _)| *other_index != index)
            .map(|(_, other)| distance(player.anchor, other.anchor))
            .filter(|distance| *distance > 1e-6)
            .fold(f64::INFINITY, f64::min);
        if nearest.is_finite() {
            nearest_distances[nearest_count] = nearest;
            nearest_count += 1;
        }
    }
    if nearest_count == 0 {
        return 1.0;
    }
    nearest_distances[..nearest_count]
        .sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    nearest_distances[nearest_count / 2].max(1.0)
}

fn task_concentration(kind: DefenseTaskKind) -> f64 {
    match kind {
        DefenseTaskKind::CloseDown => 0.88,
        DefenseTaskKind::Press => 1.0,
        DefenseTaskKind::Mark => 0.86,
        DefenseTaskKind::BlockLane => 0.72,
        DefenseTaskKind::RecoverShape => 0.28,
    }
}

pub fn defense_resource_claim(
    task_kind: DefenseTaskKind,
    projected_pos: (f64, f64),
    ball_pos: (f64, f64),
    own_goal_x: f64,
    pitch_width: f64,
    carrier_closure: f64,
    pressure_coverage: f64,
) -> DefenseResourceClaim {
    let distance_to_ball = distance(projected_pos, ball_pos);
    let defensive_direction = (own_goal_x - ball_pos.0).signum();
    let goal_side_depth = (projected_pos.0 - ball_pos.0) * defensive_direction;
    let goal_side_fit = smoothstep(-1.2, 6.5, goal_side_depth);
    let local_cover_fit = (-distance_to_ball / 22.0).exp();
    let screen_role = match task_kind {
        DefenseTaskKind::CloseDown => 0.18,
        DefenseTaskKind::Press => 0.0,
        DefenseTaskKind::Mark => 0.76,
        DefenseTaskKind::BlockLane => 0.92,
        DefenseTaskKind::RecoverShape => 0.62,
    };
    let lane_role = match task_kind {
        DefenseTaskKind::CloseDown => 0.18,
        DefenseTaskKind::Press => 0.06,
        DefenseTaskKind::Mark => 0.66,
        DefenseTaskKind::BlockLane => 0.88,
        DefenseTaskKind::RecoverShape => 0.24,
    };
    let lateral_offset =
        ((projected_pos.1 - ball_pos.1).abs() / (pitch_width * 0.5).max(1.0)).clamp(0.0, 1.0);
    let lateral_fit = smoothstep(0.08, 0.62, lateral_offset);
    let balance_role = match task_kind {
        DefenseTaskKind::CloseDown => 0.18,
        DefenseTaskKind::Press => 0.08,
        DefenseTaskKind::Mark => 0.70,
        DefenseTaskKind::BlockLane => 0.76,
        DefenseTaskKind::RecoverShape => 0.64,
    };
    let mut wide_balance = [0.0; 2];
    if projected_pos.1 <= ball_pos.1 {
        wide_balance[0] = balance_role * lateral_fit;
    } else {
        wide_balance[1] = balance_role * lateral_fit;
    }
    DefenseResourceClaim {
        carrier_closure: if matches!(task_kind, DefenseTaskKind::CloseDown | DefenseTaskKind::Press)
        {
            carrier_closure
        } else {
            0.0
        },
        carrier_engagement: if task_kind == DefenseTaskKind::Press {
            pressure_coverage
        } else {
            0.0
        },
        cover: screen_role * goal_side_fit * local_cover_fit,
        lane_screen: lane_role * (0.34 + 0.66 * goal_side_fit) * local_cover_fit,
        wide_balance,
        outlet_coverage: [0.0; MAX_FIXED_TEAM_DEFENSE_PLAYERS],
    }
    .clamped()
}

pub fn defense_resource_claim_with_outlets(
    task_kind: DefenseTaskKind,
    projected_pos: (f64, f64),
    ball_pos: (f64, f64),
    own_goal_x: f64,
    pitch_width: f64,
    carrier_closure: f64,
    pressure_coverage: f64,
    outlets: &[(f64, f64)],
) -> DefenseResourceClaim {
    assert!(
        outlets.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "defense outlet coverage supports eleven visible attackers"
    );
    let mut claim = defense_resource_claim(
        task_kind,
        projected_pos,
        ball_pos,
        own_goal_x,
        pitch_width,
        carrier_closure,
        pressure_coverage,
    );
    let (lane_role, mark_role) = match task_kind {
        DefenseTaskKind::CloseDown => (0.18, 0.12),
        DefenseTaskKind::Press => (0.05, 0.04),
        DefenseTaskKind::Mark => (0.70, 0.86),
        DefenseTaskKind::BlockLane => (0.94, 0.48),
        DefenseTaskKind::RecoverShape => (0.42, 0.30),
    };
    for (outlet_index, outlet) in outlets.iter().enumerate() {
        let outlet_delta = (outlet.0 - ball_pos.0, outlet.1 - ball_pos.1);
        let outlet_distance =
            (outlet_delta.0 * outlet_delta.0 + outlet_delta.1 * outlet_delta.1).sqrt();
        if outlet_distance <= 1.2 {
            continue;
        }
        let direction = (
            outlet_delta.0 / outlet_distance,
            outlet_delta.1 / outlet_distance,
        );
        let candidate_delta = (
            projected_pos.0 - ball_pos.0,
            projected_pos.1 - ball_pos.1,
        );
        let forward_projection =
            candidate_delta.0 * direction.0 + candidate_delta.1 * direction.1;
        let perpendicular =
            (candidate_delta.0 * direction.1 - candidate_delta.1 * direction.0).abs();
        let line_between = smoothstep(
            outlet_distance * 0.05,
            outlet_distance * 0.28,
            forward_projection,
        ) * (1.0
            - smoothstep(
                outlet_distance * 0.78,
                outlet_distance * 1.05,
                forward_projection,
            ));
        let corridor_width = 1.7 + 0.075 * outlet_distance;
        let lane_access =
            line_between * (1.0 - smoothstep(corridor_width * 0.35, corridor_width, perpendicular));
        let mark_access = (-distance(projected_pos, *outlet) / 7.5).exp();
        claim.outlet_coverage[outlet_index] =
            (lane_role * lane_access).max(mark_role * mark_access).clamp(0.0, 1.0);
    }
    claim.clamped()
}

pub fn defense_resource_demand_from_visible_threats(
    ball_pos: (f64, f64),
    visible_attackers: &[(f64, f64)],
    own_goal_x: f64,
    pitch_length: f64,
    pitch_width: f64,
    immediate_threat: f64,
    press_intensity: f64,
    carrier_visible: bool,
) -> DefenseResourceDemand {
    let immediate_threat = immediate_threat.clamp(0.0, 1.0);
    let press_intensity = press_intensity.clamp(0.0, 1.0);
    let forward_to_own_goal = if own_goal_x <= 0.0 { -1.0 } else { 1.0 };
    let half_width = (pitch_width * 0.5).max(1.0);
    let mut lane_screen = 0.0_f64;
    let mut wide_balance = [0.06_f64; 2];
    let mut outlet_coverage = [0.0; MAX_FIXED_TEAM_DEFENSE_PLAYERS];

    for (attacker_index, attacker) in visible_attackers.iter().enumerate() {
        let own_goal_progress =
            ((attacker.0 - ball_pos.0) * forward_to_own_goal / pitch_length.max(1.0))
                .clamp(-1.0, 1.0);
        let goal_threat = 0.22 + 0.78 * smoothstep(-0.22, 0.38, own_goal_progress);
        let lateral_offset = ((attacker.1 - ball_pos.1).abs() / half_width).clamp(0.0, 1.0);
        let lateral_threat = smoothstep(0.08, 0.58, lateral_offset);
        let side = usize::from(attacker.1 > ball_pos.1);
        wide_balance[side] = wide_balance[side].max(goal_threat * lateral_threat);
        lane_screen = lane_screen.max(goal_threat * (0.26 + 0.74 * lateral_threat));
        let outlet_distance = distance(*attacker, ball_pos);
        let receiver_separation = smoothstep(2.0, 10.0, outlet_distance);
        outlet_coverage[attacker_index] = if outlet_distance > 1.2 {
            goal_threat * (0.24 + 0.76 * receiver_separation)
        } else {
            0.0
        };
    }

    let ball_side = ((ball_pos.1 - half_width) / half_width).clamp(-1.0, 1.0);
    if ball_side.abs() > 1e-6 {
        let weak_side = usize::from(ball_side < 0.0);
        wide_balance[weak_side] =
            wide_balance[weak_side].max(0.12 + 0.36 * ball_side.abs());
    }

    DefenseResourceDemand {
        carrier_closure: if carrier_visible {
            (0.22 + 0.78 * immediate_threat) * (0.30 + 0.70 * press_intensity)
        } else {
            0.0
        },
        carrier_engagement: if carrier_visible {
            (0.18 + 0.82 * immediate_threat) * (0.20 + 0.80 * press_intensity)
        } else {
            0.0
        },
        cover: if carrier_visible {
            (0.26 + 0.74 * immediate_threat) * (0.42 + 0.58 * press_intensity)
        } else {
            0.0
        },
        lane_screen: (0.12 + 0.88 * lane_screen).clamp(0.0, 1.0),
        wide_balance,
        outlet_coverage,
    }
    .clamped()
}

fn local_candidate_value(
    candidate: TeamDefenseCandidate,
    player: TeamDefensePlayerInput<'_>,
    scale: f64,
    compactness: f64,
) -> f64 {
    let anchor_stiffness = 0.05 + 0.10 * compactness;
    let role_departure = distance(candidate.projected_pos, player.anchor) / scale;
    candidate.local_value.max(0.0)
        - anchor_stiffness * role_departure * role_departure
        - 0.04 * candidate.residual_threat.clamp(0.0, 1.0)
}

fn best_local_candidate_index(player: TeamDefensePlayerInput<'_>) -> usize {
    player
        .candidates
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| {
            left.local_value
                .partial_cmp(&right.local_value)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(candidate_index, _)| candidate_index)
        .unwrap_or(0)
}

fn preferred_candidate_index(
    input: &TeamDefenseAssignmentInput<'_>,
    player_index: usize,
) -> usize {
    let player = input.players[player_index];
    input
        .local_candidate_indices
        .and_then(|indices| indices.get(player_index).copied())
        .filter(|candidate_index| *candidate_index < player.candidates.len())
        .unwrap_or_else(|| best_local_candidate_index(player))
}

fn resource_claim_distance(
    left: DefenseResourceClaim,
    right: DefenseResourceClaim,
) -> f64 {
    (left.carrier_closure - right.carrier_closure).abs()
        + (left.carrier_engagement - right.carrier_engagement).abs()
        + (left.cover - right.cover).abs()
        + (left.lane_screen - right.lane_screen).abs()
        + 0.5 * (left.wide_balance[0] - right.wide_balance[0]).abs()
        + 0.5 * (left.wide_balance[1] - right.wide_balance[1]).abs()
        + 0.35
            * left
                .outlet_coverage
                .iter()
                .zip(right.outlet_coverage)
                .map(|(left, right)| (left - right).abs())
                .sum::<f64>()
            / MAX_FIXED_TEAM_DEFENSE_PLAYERS as f64
}

fn local_intent_deviation_cost(
    input: &TeamDefenseAssignmentInput<'_>,
    player_index: usize,
    candidate_index: usize,
    scale: f64,
) -> f64 {
    let player = input.players[player_index];
    let Some(preferred_index) = input
        .local_candidate_indices
        .and_then(|indices| indices.get(player_index).copied())
        .filter(|preferred_index| *preferred_index < player.candidates.len())
    else {
        return 0.0;
    };
    if candidate_index == preferred_index {
        return 0.0;
    }
    let Some(preferred) = player.candidates.get(preferred_index).copied() else {
        return 0.0;
    };
    let Some(candidate) = player.candidates.get(candidate_index).copied() else {
        return 0.0;
    };
    let scale = scale.max(1.0);
    let projected_shift = smoothstep(
        0.08,
        0.72,
        distance(candidate.projected_pos, preferred.projected_pos) / scale,
    );
    let target_shift = smoothstep(
        0.10,
        0.95,
        distance(candidate.target, preferred.target) / scale,
    );
    let role_shift = smoothstep(
        0.04,
        0.68,
        resource_claim_distance(candidate.resource_claim, preferred.resource_claim),
    );
    let preference_strength =
        (preferred.local_value.max(0.0) / (preferred.local_value.max(0.0) + 0.16))
            .clamp(0.0, 1.0);
    (0.05 + 0.20 * preference_strength)
        * (0.60 * target_shift + 0.24 * projected_shift + 0.16 * role_shift)
}

fn task_retarget_cost(
    input: &TeamDefenseAssignmentInput<'_>,
    player_index: usize,
    candidate_index: usize,
    scale: f64,
) -> f64 {
    let Some(continuity) = input
        .task_continuities
        .and_then(|continuities| continuities.get(player_index).copied())
        .map(DefenseTaskContinuity::clamped)
        .filter(|continuity| continuity.active)
    else {
        return 0.0;
    };
    let Some(candidate) = input.players[player_index]
        .candidates
        .get(candidate_index)
        .copied()
    else {
        return 0.0;
    };
    let target_shift = smoothstep(
        0.08,
        0.90,
        distance(candidate.target, continuity.target) / scale.max(1.0),
    );
    let role_shift = smoothstep(
        0.04,
        0.68,
        resource_claim_distance(candidate.resource_claim, continuity.resource_claim),
    );
    let coordination_strength = continuity
        .resource_claim
        .carrier_closure
        .max(continuity.resource_claim.carrier_engagement)
        .max(continuity.resource_claim.cover)
        .max(continuity.resource_claim.lane_screen)
        .max(continuity.resource_claim.wide_balance[0])
        .max(continuity.resource_claim.wide_balance[1]);
    continuity.commitment
        * (0.05 + 0.19 * coordination_strength)
        * (0.80 * target_shift + 0.20 * role_shift)
}

fn pair_candidate_penalty(
    left_player: TeamDefensePlayerInput<'_>,
    left_candidate: TeamDefenseCandidate,
    right_player: TeamDefensePlayerInput<'_>,
    right_candidate: TeamDefenseCandidate,
    scale: f64,
    compactness: f64,
) -> f64 {
    let linkage_stiffness = 0.08 + 0.18 * compactness;
    let anchor_distance = distance(left_player.anchor, right_player.anchor);
    let neighborhood_weight = (-anchor_distance / scale).exp();
    let relative_anchor = (
        left_player.anchor.0 - right_player.anchor.0,
        left_player.anchor.1 - right_player.anchor.1,
    );
    let relative_position = (
        left_candidate.projected_pos.0 - right_candidate.projected_pos.0,
        left_candidate.projected_pos.1 - right_candidate.projected_pos.1,
    );
    let relative_deformation = distance(relative_position, relative_anchor) / scale;
    let linkage_penalty =
        linkage_stiffness * neighborhood_weight * relative_deformation * relative_deformation;

    let occupancy =
        (-(distance(left_candidate.projected_pos, right_candidate.projected_pos) / scale).powi(2))
            .exp();
    let occupancy_penalty = (0.14 + 0.20 * compactness) * occupancy;

    let target_overlap =
        (-(distance(left_candidate.target, right_candidate.target) / scale).powi(2)).exp();
    let task_overlap = task_concentration(left_candidate.task_kind)
        * task_concentration(right_candidate.task_kind);
    let overlap_penalty = (0.10 + 0.24 * compactness) * target_overlap * task_overlap;

    linkage_penalty + occupancy_penalty + overlap_penalty
}

fn resource_coverage(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    replacement: Option<(usize, usize)>,
) -> DefenseResourceClaim {
    let mut uncovered = DefenseResourceClaim {
        carrier_closure: 1.0,
        carrier_engagement: 1.0,
        cover: 1.0,
        lane_screen: 1.0,
        wide_balance: [1.0, 1.0],
        outlet_coverage: [1.0; MAX_FIXED_TEAM_DEFENSE_PLAYERS],
    };
    for (player_index, player) in input.players.iter().enumerate() {
        let candidate_index = replacement
            .filter(|(index, _)| *index == player_index)
            .map(|(_, candidate_index)| candidate_index)
            .unwrap_or_else(|| selections.get(player_index).copied().unwrap_or(0));
        let Some(candidate) = player.candidates.get(candidate_index) else {
            continue;
        };
        let claim = candidate.resource_claim.clamped();
        uncovered.carrier_closure *= 1.0 - claim.carrier_closure;
        uncovered.carrier_engagement *= 1.0 - claim.carrier_engagement;
        uncovered.cover *= 1.0 - claim.cover;
        uncovered.lane_screen *= 1.0 - claim.lane_screen;
        uncovered.wide_balance[0] *= 1.0 - claim.wide_balance[0];
        uncovered.wide_balance[1] *= 1.0 - claim.wide_balance[1];
        for outlet_index in 0..MAX_FIXED_TEAM_DEFENSE_PLAYERS {
            uncovered.outlet_coverage[outlet_index] *=
                1.0 - claim.outlet_coverage[outlet_index];
        }
    }
    DefenseResourceClaim {
        carrier_closure: 1.0 - uncovered.carrier_closure,
        carrier_engagement: 1.0 - uncovered.carrier_engagement,
        cover: 1.0 - uncovered.cover,
        lane_screen: 1.0 - uncovered.lane_screen,
        wide_balance: [
            1.0 - uncovered.wide_balance[0],
            1.0 - uncovered.wide_balance[1],
        ],
        outlet_coverage: uncovered
            .outlet_coverage
            .map(|uncovered| 1.0 - uncovered),
    }
}

fn resource_objective(
    input: &TeamDefenseAssignmentInput<'_>,
    coverage: DefenseResourceClaim,
) -> f64 {
    let demand = input.resource_demand.clamped();
    let compactness = input.compactness.clamp(0.0, 1.0);
    let press_intensity = input.press_intensity.clamp(0.0, 1.0);
    let closure_weight = 0.26 + 0.42 * press_intensity;
    let supported_engagement = coverage.carrier_engagement.min(coverage.cover);
    let unsupported_engagement = (coverage.carrier_engagement - coverage.cover).max(0.0);
    let engagement_weight = 0.32 + 0.68 * press_intensity;
    let cover_weight = 0.20 + 0.22 * (1.0 - press_intensity);
    let exposure_weight = 0.72 + 0.78 * (1.0 - press_intensity);
    let lane_weight = 0.34 + 0.24 * compactness;
    let balance_weight = 0.30 + 0.36 * (1.0 - compactness);
    let outlet_weight = 0.22 + 0.30 * (1.0 - compactness);
    let engagement_overcommitment =
        (coverage.carrier_engagement - demand.carrier_engagement).max(0.0);
    let closure_overcommitment =
        (coverage.carrier_closure - demand.carrier_closure).max(0.0);

    demand.carrier_closure * closure_weight * coverage.carrier_closure
        + demand.carrier_engagement * engagement_weight * supported_engagement
        + demand.cover * cover_weight * coverage.cover
        + demand.lane_screen * lane_weight * coverage.lane_screen
        + demand.wide_balance[0] * balance_weight * coverage.wide_balance[0]
        + demand.wide_balance[1] * balance_weight * coverage.wide_balance[1]
        + demand
            .outlet_coverage
            .iter()
            .zip(coverage.outlet_coverage)
            .map(|(demand, coverage)| demand * outlet_weight * coverage)
            .sum::<f64>()
        - demand.carrier_engagement * exposure_weight * unsupported_engagement
        - demand.carrier_engagement * 0.22 * engagement_overcommitment.powi(2)
        - demand.carrier_closure * 0.14 * closure_overcommitment.powi(2)
}

fn supported_engagement_requirement(
    input: &TeamDefenseAssignmentInput<'_>,
) -> Option<SupportedEngagementRequirement> {
    let demand = input.resource_demand.clamped();
    if demand.carrier_engagement <= 1e-6 || demand.cover <= 1e-6 {
        return None;
    }
    let mut best: Option<SupportedEngagementRequirement> = None;
    for (engager_player_index, engager_player) in input.players.iter().enumerate() {
        for (engager_candidate_index, engager_candidate) in engager_player.candidates.iter().enumerate()
        {
            let engagement = engager_candidate.resource_claim.carrier_engagement;
            if engagement <= 1e-6 {
                continue;
            }
            for (cover_player_index, cover_player) in input.players.iter().enumerate() {
                if engager_player_index == cover_player_index {
                    continue;
                }
                for (cover_candidate_index, cover_candidate) in
                    cover_player.candidates.iter().enumerate()
                {
                    let cover = cover_candidate.resource_claim.cover;
                    let supported_engagement = engagement.min(cover);
                    if supported_engagement <= 1e-6 {
                        continue;
                    }
                    let candidate = SupportedEngagementRequirement {
                        engager_player_index,
                        engager_candidate_index,
                        cover_player_index,
                        cover_candidate_index,
                        minimum_supported_engagement: supported_engagement
                            .min(demand.carrier_engagement)
                            .min(demand.cover),
                    };
                    if best
                        .map(|current| {
                            candidate.minimum_supported_engagement
                                > current.minimum_supported_engagement + 1e-9
                        })
                        .unwrap_or(true)
                    {
                        best = Some(candidate);
                    }
                }
            }
        }
    }
    best
}

fn selection_satisfies_supported_engagement(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    requirement: Option<SupportedEngagementRequirement>,
) -> bool {
    let Some(requirement) = requirement else {
        return true;
    };
    let coverage = resource_coverage(input, selections, None);
    coverage
        .carrier_engagement
        .min(coverage.cover)
        + 1e-9
        >= requirement.minimum_supported_engagement
}

fn selection_objective_with_supported_engagement(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    scale: f64,
    requirement: Option<SupportedEngagementRequirement>,
) -> f64 {
    if !selection_satisfies_supported_engagement(input, selections, requirement) {
        return f64::NEG_INFINITY;
    }
    let compactness = input.compactness.clamp(0.0, 1.0);
    let mut value = 0.0;

    for (player_index, player) in input.players.iter().enumerate() {
        let Some(candidate) = player.candidates.get(selections[player_index]) else {
            continue;
        };
        value += local_candidate_value(*candidate, *player, scale, compactness);
        value -= local_intent_deviation_cost(input, player_index, selections[player_index], scale);
        value -= task_retarget_cost(input, player_index, selections[player_index], scale);
    }

    value += resource_objective(input, resource_coverage(input, selections, None));

    for left_index in 0..input.players.len() {
        let left_player = &input.players[left_index];
        let Some(left_candidate) = left_player.candidates.get(selections[left_index]) else {
            continue;
        };
        for right_index in left_index + 1..input.players.len() {
            let right_player = &input.players[right_index];
            let Some(right_candidate) = right_player.candidates.get(selections[right_index]) else {
                continue;
            };
            value -= pair_candidate_penalty(
                *left_player,
                *left_candidate,
                *right_player,
                *right_candidate,
                scale,
                compactness,
            );
        }
    }
    value
}

fn selection_objective_after_change_with_supported_engagement(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    scale: f64,
    current_objective: f64,
    player_index: usize,
    candidate_index: usize,
    requirement: Option<SupportedEngagementRequirement>,
) -> f64 {
    let mut changed = [0usize; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    assert!(
        selections.len() <= changed.len(),
        "fixed defense responsibility checks support eleven players"
    );
    changed[..selections.len()].copy_from_slice(selections);
    changed[player_index] = candidate_index;
    if !selection_satisfies_supported_engagement(input, &changed[..selections.len()], requirement)
    {
        return f64::NEG_INFINITY;
    }
    let compactness = input.compactness.clamp(0.0, 1.0);
    let Some(player) = input.players.get(player_index).copied() else {
        return current_objective;
    };
    let Some(current_candidate) = player.candidates.get(selections[player_index]).copied() else {
        return current_objective;
    };
    let Some(candidate) = player.candidates.get(candidate_index).copied() else {
        return current_objective;
    };

    let local_delta = local_candidate_value(candidate, player, scale, compactness)
        - local_candidate_value(current_candidate, player, scale, compactness);
    let local_intent_delta =
        local_intent_deviation_cost(input, player_index, candidate_index, scale)
            - local_intent_deviation_cost(input, player_index, selections[player_index], scale);
    let task_retarget_delta = task_retarget_cost(input, player_index, candidate_index, scale)
        - task_retarget_cost(input, player_index, selections[player_index], scale);
    let resource_delta = resource_objective(
        input,
        resource_coverage(input, selections, Some((player_index, candidate_index))),
    ) - resource_objective(input, resource_coverage(input, selections, None));
    let pair_delta = input
        .players
        .iter()
        .enumerate()
        .filter(|(other_index, _)| *other_index != player_index)
        .filter_map(|(other_index, other)| {
            other
                .candidates
                .get(selections[other_index])
                .copied()
                .map(|other_candidate| {
                    pair_candidate_penalty(
                        player,
                        candidate,
                        *other,
                        other_candidate,
                        scale,
                        compactness,
                    ) - pair_candidate_penalty(
                        player,
                        current_candidate,
                        *other,
                        other_candidate,
                        scale,
                        compactness,
                    )
                })
        })
        .sum::<f64>();

    current_objective + local_delta - local_intent_delta - task_retarget_delta + resource_delta
        - pair_delta
}

pub fn coordinate_team_defense_into(
    input: &TeamDefenseAssignmentInput<'_>,
    assignments: &mut [TeamDefenseAssignment],
) -> TeamDefenseCoordinationSummary {
    assert!(
        input.players.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense coordination supports eleven players"
    );
    assert!(
        assignments.len() >= input.players.len(),
        "fixed defense assignment output is too small"
    );
    let player_count = input.players.len();
    let scale = formation_scale_fixed(input.players);
    let mut selections = [0usize; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    for (index, _) in input.players.iter().enumerate() {
        selections[index] = preferred_candidate_index(input, index);
    }
    let supported_engagement = supported_engagement_requirement(input);
    if !selection_satisfies_supported_engagement(
        input,
        &selections[..player_count],
        supported_engagement,
    ) {
        if let Some(requirement) = supported_engagement {
            selections[requirement.engager_player_index] = requirement.engager_candidate_index;
            selections[requirement.cover_player_index] = requirement.cover_candidate_index;
        }
    }

    let maximum_sweeps = player_count.saturating_mul(2).max(1);
    for _ in 0..maximum_sweeps {
        let mut changed = false;
        let mut current_objective = selection_objective_with_supported_engagement(
            input,
            &selections[..player_count],
            scale,
            supported_engagement,
        );
        for player_index in 0..player_count {
            let candidate_count = input.players[player_index].candidates.len();
            if candidate_count == 0 {
                continue;
            }
            let current_index = selections[player_index];
            let mut best_index = current_index;
            let mut best_value = current_objective;
            for candidate_index in 0..candidate_count {
                if candidate_index == current_index {
                    continue;
                }
                let candidate_value = selection_objective_after_change_with_supported_engagement(
                    input,
                    &selections[..player_count],
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                    supported_engagement,
                );
                if candidate_value > best_value + 1e-9 {
                    best_index = candidate_index;
                    best_value = candidate_value;
                }
            }
            selections[player_index] = best_index;
            changed |= best_index != current_index;
            current_objective = best_value;
        }
        if !changed {
            break;
        }
    }

    let objective = selection_objective_with_supported_engagement(
        input,
        &selections[..player_count],
        scale,
        supported_engagement,
    );
    for (player_index, player) in input.players.iter().enumerate() {
        let candidate_index = selections[player_index];
        let candidate =
            player
                .candidates
                .get(candidate_index)
                .copied()
                .unwrap_or(TeamDefenseCandidate {
                    target: player.anchor,
                    projected_pos: player.anchor,
                    local_value: 0.0,
                    residual_threat: 1.0,
                    pressure_coverage: 0.0,
                    resource_claim: DefenseResourceClaim::default(),
                    task_kind: DefenseTaskKind::RecoverShape,
                });
        assignments[player_index] = TeamDefenseAssignment {
            index: player.index,
            candidate_index,
            local_value: candidate.local_value,
            residual_threat: candidate.residual_threat,
            local_intent_cost: local_intent_deviation_cost(input, player_index, candidate_index, scale),
            task_retarget_cost: task_retarget_cost(input, player_index, candidate_index, scale),
        };
    }
    TeamDefenseCoordinationSummary {
        objective,
        formation_scale: scale,
    }
}

pub fn coordinate_team_defense(
    input: &TeamDefenseAssignmentInput<'_>,
) -> TeamDefenseAssignmentOutput {
    let scale = formation_scale(input.players);
    let mut selections = (0..input.players.len())
        .map(|player_index| preferred_candidate_index(input, player_index))
        .collect::<Vec<_>>();
    let supported_engagement = supported_engagement_requirement(input);
    if !selection_satisfies_supported_engagement(input, &selections, supported_engagement) {
        if let Some(requirement) = supported_engagement {
            selections[requirement.engager_player_index] = requirement.engager_candidate_index;
            selections[requirement.cover_player_index] = requirement.cover_candidate_index;
        }
    }

    let maximum_sweeps = input.players.len().saturating_mul(2).max(1);
    for _ in 0..maximum_sweeps {
        let mut changed = false;
        let mut current_objective =
            selection_objective_with_supported_engagement(input, &selections, scale, supported_engagement);
        for player_index in 0..input.players.len() {
            let candidate_count = input.players[player_index].candidates.len();
            if candidate_count == 0 {
                continue;
            }
            let current_index = selections[player_index];
            let mut best_index = current_index;
            let mut best_value = current_objective;
            for candidate_index in 0..candidate_count {
                if candidate_index == current_index {
                    continue;
                }
                let candidate_value = selection_objective_after_change_with_supported_engagement(
                    input,
                    &selections,
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                    supported_engagement,
                );
                if candidate_value > best_value + 1e-9 {
                    best_index = candidate_index;
                    best_value = candidate_value;
                }
            }
            selections[player_index] = best_index;
            changed |= best_index != current_index;
            current_objective = best_value;
        }
        if !changed {
            break;
        }
    }

    let objective =
        selection_objective_with_supported_engagement(input, &selections, scale, supported_engagement);
    let assignments =
        input
            .players
            .iter()
            .zip(selections)
            .enumerate()
            .map(|(player_index, (player, candidate_index))| {
                let candidate = player.candidates.get(candidate_index).copied().unwrap_or(
                    TeamDefenseCandidate {
                        target: player.anchor,
                        projected_pos: player.anchor,
                        local_value: 0.0,
                        residual_threat: 1.0,
                        pressure_coverage: 0.0,
                        resource_claim: DefenseResourceClaim::default(),
                        task_kind: DefenseTaskKind::RecoverShape,
                    },
                );
                TeamDefenseAssignment {
                    index: player.index,
                    candidate_index,
                    local_value: candidate.local_value,
                    residual_threat: candidate.residual_threat,
                    local_intent_cost: local_intent_deviation_cost(
                        input,
                        player_index,
                        candidate_index,
                        scale,
                    ),
                    task_retarget_cost: task_retarget_cost(input, player_index, candidate_index, scale),
                }
            })
            .collect();
    TeamDefenseAssignmentOutput {
        assignments,
        objective,
        formation_scale: scale,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        coordinate_team_defense, coordinate_team_defense_into, defense_resource_claim,
        defense_resource_claim_with_outlets, defense_resource_demand_from_visible_threats,
        formation_scale, selection_objective_after_change_with_supported_engagement,
        selection_objective_with_supported_engagement, supported_engagement_requirement,
        DefenseResourceClaim, DefenseResourceDemand, DefenseTaskContinuity, DefenseTaskKind,
        TeamDefenseAssignment, TeamDefenseAssignmentInput,
        TeamDefenseCandidate, TeamDefensePlayerInput, MAX_FIXED_TEAM_DEFENSE_PLAYERS,
    };

    fn candidate(
        target: (f64, f64),
        projected_pos: (f64, f64),
        local_value: f64,
        task_kind: DefenseTaskKind,
    ) -> TeamDefenseCandidate {
        TeamDefenseCandidate {
            target,
            projected_pos,
            local_value,
            residual_threat: 0.2,
            pressure_coverage: 0.0,
            resource_claim: DefenseResourceClaim::default(),
            task_kind,
        }
    }

    fn with_claim(
        mut candidate: TeamDefenseCandidate,
        resource_claim: DefenseResourceClaim,
    ) -> TeamDefenseCandidate {
        candidate.resource_claim = resource_claim;
        candidate
    }

    fn assignment_input<'a>(
        players: &'a [TeamDefensePlayerInput<'a>],
        compactness: f64,
        immediate_threat: f64,
    ) -> TeamDefenseAssignmentInput<'a> {
        TeamDefenseAssignmentInput {
            players,
            compactness,
            immediate_threat,
            press_intensity: 0.65,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: immediate_threat,
                cover: immediate_threat,
                lane_screen: 0.35,
                wide_balance: [0.30, 0.30],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: None,
            task_continuities: None,
        }
    }

    #[test]
    fn coordinates_a_single_press_without_collapsing_the_line() {
        let left = [
            candidate((58.0, 34.0), (46.0, 31.0), 1.10, DefenseTaskKind::Press),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let center = [
            candidate((58.0, 34.0), (47.0, 34.0), 1.04, DefenseTaskKind::Press),
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            candidate((58.0, 34.0), (46.0, 37.0), 0.98, DefenseTaskKind::Press),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&assignment_input(&players, 0.7, 0.0));
        let press_count = output
            .assignments
            .iter()
            .filter(|assignment| assignment.candidate_index == 0)
            .count();

        assert_eq!(press_count, 1);
        assert!(output.formation_scale > 1.0);
    }

    #[test]
    fn fixed_buffer_coordination_matches_vec_api() {
        let left = [
            candidate((58.0, 34.0), (46.0, 31.0), 1.10, DefenseTaskKind::Press),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 26.0), (46.0, 26.0), 0.82, DefenseTaskKind::BlockLane),
        ];
        let center = [
            candidate((58.0, 34.0), (47.0, 34.0), 1.04, DefenseTaskKind::Press),
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 34.0), (46.0, 34.0), 0.76, DefenseTaskKind::BlockLane),
        ];
        let right = [
            candidate((58.0, 34.0), (46.0, 37.0), 0.98, DefenseTaskKind::Press),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 42.0), (46.0, 42.0), 0.80, DefenseTaskKind::Mark),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];
        let input = assignment_input(&players, 0.7, 0.62);
        let vec_output = coordinate_team_defense(&input);
        let mut fixed_assignments = [TeamDefenseAssignment {
            index: 0,
            candidate_index: 0,
            local_value: 0.0,
            residual_threat: 0.0,
            local_intent_cost: 0.0,
            task_retarget_cost: 0.0,
        }; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
        let fixed_summary =
            coordinate_team_defense_into(&input, &mut fixed_assignments[..players.len()]);

        assert_eq!(
            fixed_assignments[..players.len()]
                .iter()
                .map(|assignment| assignment.index)
                .collect::<Vec<_>>(),
            vec_output
                .assignments
                .iter()
                .map(|assignment| assignment.index)
                .collect::<Vec<_>>()
        );
        assert_eq!(
            fixed_assignments[..players.len()]
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec_output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>()
        );
        for (fixed, allocated) in fixed_assignments[..players.len()]
            .iter()
            .zip(&vec_output.assignments)
        {
            assert_eq!(fixed.local_value, allocated.local_value);
            assert_eq!(fixed.residual_threat, allocated.residual_threat);
        }
        assert_eq!(fixed_summary.objective, vec_output.objective);
        assert_eq!(fixed_summary.formation_scale, vec_output.formation_scale);
    }

    #[test]
    fn preserves_separate_marks_when_their_threat_targets_are_distinct() {
        let left = [
            candidate((55.0, 18.0), (47.0, 19.0), 1.00, DefenseTaskKind::Mark),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.30,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            candidate((55.0, 50.0), (47.0, 49.0), 0.98, DefenseTaskKind::Mark),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.30,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&assignment_input(&players, 0.55, 0.0));

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![0, 0]
        );
    }

    #[test]
    fn assigns_one_reachable_press_when_immediate_threat_requires_coverage() {
        let left = [
            TeamDefenseCandidate {
                target: (56.0, 32.0),
                projected_pos: (48.0, 31.0),
                local_value: 0.48,
                residual_threat: 0.5,
                pressure_coverage: 0.68,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.68,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            with_claim(candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ), DefenseResourceClaim {
                cover: 0.74,
                lane_screen: 0.26,
                ..DefenseResourceClaim::default()
            }),
        ];
        let right = [
            TeamDefenseCandidate {
                target: (56.0, 36.0),
                projected_pos: (48.0, 37.0),
                local_value: 0.47,
                residual_threat: 0.5,
                pressure_coverage: 0.66,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.66,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            with_claim(candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ), DefenseResourceClaim {
                cover: 0.72,
                lane_screen: 0.24,
                ..DefenseResourceClaim::default()
            }),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.65,
            immediate_threat: 0.90,
            press_intensity: 0.80,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: 0.90,
                cover: 0.0,
                lane_screen: 0.0,
                wide_balance: [0.0, 0.0],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: None,
            task_continuities: None,
        });
        let press_count = output
            .assignments
            .iter()
            .filter(|assignment| assignment.candidate_index == 0)
            .count();

        assert_eq!(press_count, 1);
    }

    #[test]
    fn incremental_objective_matches_full_objective_for_each_candidate_swap() {
        let left = [
            TeamDefenseCandidate {
                target: (56.0, 32.0),
                projected_pos: (48.0, 31.0),
                local_value: 0.48,
                residual_threat: 0.5,
                pressure_coverage: 0.68,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.68,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((50.0, 26.0), (45.0, 25.0), 0.52, DefenseTaskKind::Mark),
        ];
        let center = [
            TeamDefenseCandidate {
                target: (56.0, 34.0),
                projected_pos: (49.0, 34.0),
                local_value: 0.46,
                residual_threat: 0.48,
                pressure_coverage: 0.71,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.71,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.55,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            TeamDefenseCandidate {
                target: (56.0, 36.0),
                projected_pos: (48.0, 37.0),
                local_value: 0.47,
                residual_threat: 0.5,
                pressure_coverage: 0.66,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.66,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((50.0, 42.0), (45.0, 43.0), 0.51, DefenseTaskKind::BlockLane),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];
        let input = assignment_input(&players, 0.65, 0.90);
        let selections = [1, 0, 2];
        let scale = formation_scale(&players);
        let requirement = supported_engagement_requirement(&input);
        let current_objective = selection_objective_with_supported_engagement(
            &input,
            &selections,
            scale,
            requirement,
        );

        for (player_index, player) in players.iter().enumerate() {
            for candidate_index in 0..player.candidates.len() {
                let incremental = selection_objective_after_change_with_supported_engagement(
                    &input,
                    &selections,
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                    requirement,
                );
                let mut changed = selections;
                changed[player_index] = candidate_index;
                let full =
                    selection_objective_with_supported_engagement(&input, &changed, scale, requirement);
                assert!(
                    (incremental.is_infinite() && full.is_infinite())
                        || (incremental - full).abs() <= 1e-10,
                    "player={player_index}, candidate={candidate_index}, incremental={incremental}, full={full}"
                );
            }
        }
    }

    #[test]
    fn supported_press_is_preferred_over_an_uncovered_press() {
        let press = [TeamDefenseCandidate {
            target: (58.0, 34.0),
            projected_pos: (49.0, 34.0),
            local_value: 0.82,
            residual_threat: 0.46,
            pressure_coverage: 0.86,
            resource_claim: DefenseResourceClaim {
                carrier_engagement: 0.86,
                ..DefenseResourceClaim::default()
            },
            task_kind: DefenseTaskKind::Press,
        }];
        let cover_or_recover = [
            TeamDefenseCandidate {
                target: (47.0, 34.0),
                projected_pos: (45.0, 34.0),
                local_value: 0.52,
                residual_threat: 0.34,
                pressure_coverage: 0.0,
                resource_claim: DefenseResourceClaim {
                    cover: 0.88,
                    lane_screen: 0.62,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::BlockLane,
            },
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.62,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 34.0),
                candidates: &press,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &cover_or_recover,
            },
        ];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.62,
            immediate_threat: 0.84,
            press_intensity: 0.76,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: 0.84,
                cover: 0.80,
                lane_screen: 0.40,
                wide_balance: [0.0, 0.20],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: None,
            task_continuities: None,
        });

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![0, 0]
        );
    }

    #[test]
    fn unsupported_press_is_rejected_when_no_cover_claim_exists() {
        let press_or_recover = [
            TeamDefenseCandidate {
                target: (58.0, 34.0),
                projected_pos: (49.0, 34.0),
                local_value: 0.70,
                residual_threat: 0.48,
                pressure_coverage: 0.88,
                resource_claim: DefenseResourceClaim {
                    carrier_engagement: 0.88,
                    ..DefenseResourceClaim::default()
                },
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.61,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let balance = [candidate(
            (40.0, 46.0),
            (40.0, 46.0),
            0.64,
            DefenseTaskKind::RecoverShape,
        )];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 34.0),
                candidates: &press_or_recover,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &balance,
            },
        ];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.72,
            immediate_threat: 0.82,
            press_intensity: 0.30,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: 0.86,
                cover: 0.82,
                lane_screen: 0.0,
                wide_balance: [0.0, 0.0],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: None,
            task_continuities: None,
        });

        assert_eq!(output.assignments[0].candidate_index, 1);
    }

    #[test]
    fn reachable_engager_with_cover_cannot_be_replaced_by_deeper_recovery() {
        let engager = [
            with_claim(
                candidate(
                    (61.0, 34.0),
                    (56.0, 34.0),
                    0.62,
                    DefenseTaskKind::Press,
                ),
                DefenseResourceClaim {
                    carrier_closure: 0.88,
                    carrier_engagement: 0.82,
                    ..DefenseResourceClaim::default()
                },
            ),
            with_claim(
                candidate(
                    (42.0, 34.0),
                    (42.0, 34.0),
                    0.92,
                    DefenseTaskKind::RecoverShape,
                ),
                DefenseResourceClaim {
                    lane_screen: 0.66,
                    ..DefenseResourceClaim::default()
                },
            ),
        ];
        let cover = [
            with_claim(
                candidate(
                    (53.0, 39.0),
                    (50.0, 38.0),
                    0.64,
                    DefenseTaskKind::BlockLane,
                ),
                DefenseResourceClaim {
                    cover: 0.88,
                    lane_screen: 0.72,
                    wide_balance: [0.0, 0.48],
                    ..DefenseResourceClaim::default()
                },
            ),
            with_claim(
                candidate(
                    (41.0, 49.0),
                    (41.0, 49.0),
                    0.90,
                    DefenseTaskKind::RecoverShape,
                ),
                DefenseResourceClaim {
                    wide_balance: [0.0, 0.76],
                    ..DefenseResourceClaim::default()
                },
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (46.0, 34.0),
                candidates: &engager,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (43.0, 48.0),
                candidates: &cover,
            },
        ];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.72,
            immediate_threat: 0.66,
            press_intensity: 0.72,
            resource_demand: DefenseResourceDemand {
                carrier_closure: 0.72,
                carrier_engagement: 0.74,
                cover: 0.74,
                lane_screen: 0.34,
                wide_balance: [0.0, 0.22],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: Some(&[1, 1]),
            task_continuities: None,
        });

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![0, 0],
            "when a reachable engager has a separate cover, the team must take the supported pressure responsibility"
        );
    }

    #[test]
    fn local_intent_is_not_rewritten_for_a_minor_resource_gain() {
        let candidates = [
            with_claim(
                candidate(
                    (58.0, 34.0),
                    (49.0, 34.0),
                    0.80,
                    DefenseTaskKind::Press,
                ),
                DefenseResourceClaim {
                    carrier_engagement: 0.72,
                    cover: 0.72,
                    ..DefenseResourceClaim::default()
                },
            ),
            with_claim(
                candidate(
                    (42.0, 18.0),
                    (42.0, 18.0),
                    0.79,
                    DefenseTaskKind::BlockLane,
                ),
                DefenseResourceClaim {
                    carrier_engagement: 0.67,
                    cover: 0.67,
                    lane_screen: 0.36,
                    ..DefenseResourceClaim::default()
                },
            ),
        ];
        let players = [TeamDefensePlayerInput {
            index: 0,
            anchor: (40.0, 22.0),
            candidates: &candidates,
        }];
        let local_candidate_indices = [1];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.55,
            immediate_threat: 0.38,
            press_intensity: 0.46,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: 0.42,
                cover: 0.42,
                lane_screen: 0.12,
                wide_balance: [0.0, 0.0],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: Some(&local_candidate_indices),
            task_continuities: None,
        });

        assert_eq!(output.assignments[0].candidate_index, 1);
        assert_eq!(output.assignments[0].local_intent_cost, 0.0);
    }

    #[test]
    fn press_cover_complementarity_can_override_local_choices() {
        let engager = [
            candidate(
                (42.0, 22.0),
                (42.0, 22.0),
                0.73,
                DefenseTaskKind::RecoverShape,
            ),
            with_claim(
                candidate(
                    (58.0, 34.0),
                    (49.0, 34.0),
                    0.70,
                    DefenseTaskKind::Press,
                ),
                DefenseResourceClaim {
                    carrier_engagement: 0.90,
                    ..DefenseResourceClaim::default()
                },
            ),
        ];
        let cover = [
            candidate(
                (42.0, 46.0),
                (42.0, 46.0),
                0.74,
                DefenseTaskKind::RecoverShape,
            ),
            with_claim(
                candidate(
                    (48.0, 38.0),
                    (47.0, 37.0),
                    0.70,
                    DefenseTaskKind::BlockLane,
                ),
                DefenseResourceClaim {
                    cover: 0.92,
                    lane_screen: 0.68,
                    ..DefenseResourceClaim::default()
                },
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &engager,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &cover,
            },
        ];
        let local_candidate_indices = [0, 0];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.52,
            immediate_threat: 0.92,
            press_intensity: 0.86,
            resource_demand: DefenseResourceDemand {
                carrier_engagement: 0.94,
                cover: 0.92,
                lane_screen: 0.48,
                wide_balance: [0.0, 0.0],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: Some(&local_candidate_indices),
            task_continuities: None,
        });

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![1, 1]
        );
        assert!(output.assignments[0].local_intent_cost > 0.0);
        assert!(output.assignments[1].local_intent_cost > 0.0);
    }

    #[test]
    fn committed_task_resists_uncompensated_retargeting() {
        let candidates = [
            candidate(
                (45.0, 18.0),
                (44.0, 19.0),
                0.78,
                DefenseTaskKind::BlockLane,
            ),
            candidate(
                (57.0, 36.0),
                (48.0, 35.0),
                0.82,
                DefenseTaskKind::Mark,
            ),
        ];
        let players = [TeamDefensePlayerInput {
            index: 0,
            anchor: (40.0, 22.0),
            candidates: &candidates,
        }];
        let local_candidate_indices = [0];
        let continuities = [DefenseTaskContinuity {
            active: true,
            target: candidates[0].target,
            commitment: 1.0,
            resource_claim: candidates[0].resource_claim,
        }];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.50,
            immediate_threat: 0.20,
            press_intensity: 0.30,
            resource_demand: DefenseResourceDemand::default(),
            local_candidate_indices: Some(&local_candidate_indices),
            task_continuities: Some(&continuities),
        });

        assert_eq!(output.assignments[0].candidate_index, 0);
        assert_eq!(output.assignments[0].task_retarget_cost, 0.0);
    }

    #[test]
    fn visible_wide_threats_create_separate_balance_claims() {
        let ball_pos = (58.0, 34.0);
        let threats = [(52.0, 11.0), (53.0, 57.0)];
        let demand = defense_resource_demand_from_visible_threats(
            ball_pos,
            &threats,
            0.0,
            105.0,
            68.0,
            0.56,
            0.54,
            true,
        );
        assert!(demand.wide_balance[0] > 0.35);
        assert!(demand.wide_balance[1] > 0.35);

        let left = [TeamDefenseCandidate {
            target: (50.0, 13.0),
            projected_pos: (46.0, 13.0),
            local_value: 0.64,
            residual_threat: 0.32,
            pressure_coverage: 0.0,
            resource_claim: defense_resource_claim(
                DefenseTaskKind::Mark,
                (46.0, 13.0),
                ball_pos,
                0.0,
                68.0,
                0.0,
                0.0,
            ),
            task_kind: DefenseTaskKind::Mark,
        }];
        let right = [TeamDefenseCandidate {
            target: (50.0, 55.0),
            projected_pos: (46.0, 55.0),
            local_value: 0.63,
            residual_threat: 0.33,
            pressure_coverage: 0.0,
            resource_claim: defense_resource_claim(
                DefenseTaskKind::Mark,
                (46.0, 55.0),
                ball_pos,
                0.0,
                68.0,
                0.0,
                0.0,
            ),
            task_kind: DefenseTaskKind::Mark,
        }];
        let center = [candidate(
            (44.0, 34.0),
            (44.0, 34.0),
            0.48,
            DefenseTaskKind::RecoverShape,
        )];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 17.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 51.0),
                candidates: &right,
            },
        ];
        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.56,
            immediate_threat: 0.56,
            press_intensity: 0.54,
            resource_demand: demand,
            local_candidate_indices: None,
            task_continuities: None,
        });

        assert_eq!(output.assignments[0].candidate_index, 0);
        assert_eq!(output.assignments[2].candidate_index, 0);
    }

    #[test]
    fn outlet_coverage_requires_a_real_lane_or_receiver_relationship() {
        let ball_pos = (58.0, 18.0);
        let weak_side_outlet = (53.0, 54.0);
        let ball_side_block = defense_resource_claim_with_outlets(
            DefenseTaskKind::BlockLane,
            (52.0, 20.0),
            ball_pos,
            0.0,
            68.0,
            0.0,
            0.0,
            &[weak_side_outlet],
        );
        let weak_side_mark = defense_resource_claim_with_outlets(
            DefenseTaskKind::Mark,
            (53.5, 52.5),
            ball_pos,
            0.0,
            68.0,
            0.0,
            0.0,
            &[weak_side_outlet],
        );

        assert!(
            ball_side_block.outlet_coverage[0] < 0.08,
            "a ball-side block away from the outlet pass line must not claim weak-side coverage: {ball_side_block:?}"
        );
        assert!(
            weak_side_mark.outlet_coverage[0] > 0.50,
            "a defender near the visible weak-side receiver must provide outlet coverage: {weak_side_mark:?}"
        );
    }

    #[test]
    fn close_down_claims_space_without_claiming_ball_contact() {
        let claim = defense_resource_claim(
            DefenseTaskKind::CloseDown,
            (55.0, 34.0),
            (60.0, 34.0),
            0.0,
            68.0,
            0.78,
            0.94,
        );

        assert_eq!(claim.carrier_closure, 0.78);
        assert_eq!(claim.carrier_engagement, 0.0);
    }

    #[test]
    fn central_closure_does_not_replace_visible_wide_outlet_coverage() {
        let close_down_claim = DefenseResourceClaim {
            carrier_closure: 0.88,
            ..DefenseResourceClaim::default()
        };
        let left_mark_claim = DefenseResourceClaim {
            outlet_coverage: [0.92, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ..DefenseResourceClaim::default()
        };
        let right_mark_claim = DefenseResourceClaim {
            outlet_coverage: [0.0, 0.92, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ..DefenseResourceClaim::default()
        };
        let center = [with_claim(
            candidate((60.0, 34.0), (55.0, 34.0), 0.78, DefenseTaskKind::CloseDown),
            close_down_claim,
        )];
        let left = [
            with_claim(
                candidate((60.0, 34.0), (55.0, 34.0), 0.75, DefenseTaskKind::CloseDown),
                close_down_claim,
            ),
            with_claim(
                candidate((55.0, 9.0), (54.0, 10.0), 0.64, DefenseTaskKind::Mark),
                left_mark_claim,
            ),
        ];
        let right = [
            with_claim(
                candidate((60.0, 34.0), (55.0, 34.0), 0.75, DefenseTaskKind::CloseDown),
                close_down_claim,
            ),
            with_claim(
                candidate((55.0, 59.0), (54.0, 58.0), 0.64, DefenseTaskKind::Mark),
                right_mark_claim,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (48.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (48.0, 16.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (48.0, 52.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.58,
            immediate_threat: 0.62,
            press_intensity: 0.66,
            resource_demand: DefenseResourceDemand {
                carrier_closure: 0.82,
                outlet_coverage: [0.90, 0.90, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                ..DefenseResourceDemand::default()
            },
            local_candidate_indices: None,
            task_continuities: None,
        });

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![0, 1, 1],
            "one defender can close the carrier while the remaining defenders keep visible wide outlets covered"
        );
    }
}
