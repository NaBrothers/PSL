use crate::physics::{distance, smoothstep};
use crate::team_plan::{team_plan_action_utility, TeamPlanActionInput, TeamPlanSignals};
use crate::vision::VisionContext;

pub const MAX_PLAYER_OBSERVED_ENTITIES: usize = 22;
pub const MAX_TASK_OUTLET_COVERAGE: usize = 11;
pub const MAX_FIXED_TEAM_TACTICAL_TASKS: usize = 11;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TacticalTaskIntent {
    Receive,
    Support,
    Carry,
    Control,
    CloseDown,
    Press,
    Cover,
    Screen,
    Recover,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TacticalTaskPhase {
    Proposed,
    Active,
    Recovering,
    Cancelled,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TacticalTaskCoordination {
    pub commitment: f64,
    pub carrier_closure: f64,
    pub carrier_engagement: f64,
    pub cover: f64,
    pub lane_screen: f64,
    pub wide_balance: [f64; 2],
    pub outlet_coverage: [f64; MAX_TASK_OUTLET_COVERAGE],
}

impl TacticalTaskCoordination {
    pub fn active(&self) -> bool {
        self.commitment > 1e-6
    }

    fn clamped(self) -> Self {
        Self {
            commitment: self.commitment.clamp(0.0, 1.0),
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

#[derive(Clone, Copy, Debug)]
pub struct SpatialClaim {
    pub active: bool,
    pub target: (f64, f64),
    pub origin: (f64, f64),
    pub occupancy_radius: f64,
    pub corridor_half_width: f64,
    pub depth_band: i8,
    pub width_band: i8,
}

impl Default for SpatialClaim {
    fn default() -> Self {
        Self {
            active: false,
            target: (0.0, 0.0),
            origin: (0.0, 0.0),
            occupancy_radius: 0.0,
            corridor_half_width: 0.0,
            depth_band: 0,
            width_band: 0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamSpatialCandidate {
    pub target: (f64, f64),
    pub local_value: f64,
    pub claim: SpatialClaim,
}

impl Default for TeamSpatialCandidate {
    fn default() -> Self {
        Self {
            target: (0.0, 0.0),
            local_value: f64::NEG_INFINITY,
            claim: SpatialClaim::default(),
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TeamSpatialPlayerInput<'a> {
    pub index: usize,
    pub candidates: &'a [TeamSpatialCandidate],
    pub preferred_candidate_index: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamSpatialAssignmentInput<'a> {
    pub players: &'a [TeamSpatialPlayerInput<'a>],
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TeamSpatialAssignment {
    pub index: usize,
    pub candidate_index: usize,
    pub local_value: f64,
    pub displaced_from_preference: bool,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TeamSpatialCoordinationSummary {
    pub conflicts_before: usize,
    pub conflicts_after: usize,
    pub displaced_count: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct TacticalTask {
    pub intent: TacticalTaskIntent,
    pub phase: TacticalTaskPhase,
    pub raw_target: (f64, f64),
    pub accepted_tick: i32,
    pub expires_tick: i32,
    pub commitment: f64,
    pub local_value: f64,
    pub policy_utility: f64,
    pub formation_debt: f64,
    pub interruption: f64,
    pub coordination: TacticalTaskCoordination,
    pub spatial_claim: SpatialClaim,
}

impl TacticalTask {
    pub fn inactive(target: (f64, f64)) -> Self {
        Self {
            intent: TacticalTaskIntent::Recover,
            phase: TacticalTaskPhase::Cancelled,
            raw_target: target,
            accepted_tick: 0,
            expires_tick: 0,
            commitment: 0.0,
            local_value: 0.0,
            policy_utility: 0.0,
            formation_debt: 0.0,
            interruption: 1.0,
            coordination: TacticalTaskCoordination::default(),
            spatial_claim: SpatialClaim::default(),
        }
    }

    pub fn active(&self, tick: i32) -> bool {
        self.phase == TacticalTaskPhase::Active && tick <= self.expires_tick
    }
}

fn intent_space_scale(intent: TacticalTaskIntent) -> (f64, f64) {
    match intent {
        TacticalTaskIntent::Receive => (4.4, 2.1),
        TacticalTaskIntent::Support => (4.2, 2.0),
        TacticalTaskIntent::Carry => (3.4, 1.7),
        TacticalTaskIntent::Control => (3.2, 1.6),
        TacticalTaskIntent::CloseDown => (2.8, 1.4),
        TacticalTaskIntent::Press => (2.6, 1.3),
        TacticalTaskIntent::Cover => (3.8, 1.8),
        TacticalTaskIntent::Screen => (3.6, 1.8),
        TacticalTaskIntent::Recover => (3.9, 1.8),
    }
}

fn spatial_band(value: f64) -> i8 {
    if value < -14.0 {
        -2
    } else if value < -4.0 {
        -1
    } else if value <= 6.0 {
        0
    } else if value <= 18.0 {
        1
    } else {
        2
    }
}

pub fn spatial_claim_for_task(
    origin: (f64, f64),
    target: (f64, f64),
    intent: TacticalTaskIntent,
    attacking_right: bool,
) -> SpatialClaim {
    let (base_radius, base_half_width) = intent_space_scale(intent);
    let target_distance = distance(origin, target);
    let forward_direction = if attacking_right { 1.0 } else { -1.0 };
    let depth = (target.0 - origin.0) * forward_direction;
    SpatialClaim {
        active: true,
        target,
        origin,
        occupancy_radius: base_radius + (0.035 * target_distance).min(0.9),
        corridor_half_width: base_half_width + (0.020 * target_distance).min(0.5),
        depth_band: spatial_band(depth),
        width_band: spatial_band(target.1 - origin.1),
    }
}

pub fn spatial_claim_conflict(left: SpatialClaim, right: SpatialClaim) -> bool {
    if !left.active || !right.active {
        return false;
    }
    let target_distance = distance(left.target, right.target);
    let occupied_distance = left.occupancy_radius + right.occupancy_radius;
    if target_distance < occupied_distance {
        return true;
    }
    let same_depth_band = left.depth_band == right.depth_band;
    let same_width_band = left.width_band == right.width_band;
    if !(same_depth_band && same_width_band) {
        return false;
    }
    let left_route = (
        left.target.0 - left.origin.0,
        left.target.1 - left.origin.1,
    );
    let right_route = (
        right.target.0 - right.origin.0,
        right.target.1 - right.origin.1,
    );
    let left_length = (left_route.0 * left_route.0 + left_route.1 * left_route.1).sqrt();
    let right_length = (right_route.0 * right_route.0 + right_route.1 * right_route.1).sqrt();
    if left_length <= 1e-6 || right_length <= 1e-6 {
        return target_distance < occupied_distance * 1.4;
    }
    let route_alignment =
        (left_route.0 * right_route.0 + left_route.1 * right_route.1) / (left_length * right_length);
    let corridor_width = left.corridor_half_width + right.corridor_half_width;
    route_alignment > 0.90 && target_distance < occupied_distance * 1.65 + corridor_width
}

fn team_spatial_conflict_count(
    input: &TeamSpatialAssignmentInput<'_>,
    selections: &[usize],
    replacement: Option<(usize, usize)>,
) -> usize {
    let mut conflicts = 0;
    for left_index in 0..input.players.len() {
        let left_player = input.players[left_index];
        let left_selection = replacement
            .filter(|(player_index, _)| *player_index == left_index)
            .map(|(_, candidate_index)| candidate_index)
            .unwrap_or_else(|| selections.get(left_index).copied().unwrap_or(0));
        let Some(left_candidate) = left_player.candidates.get(left_selection).copied() else {
            continue;
        };
        for right_index in left_index + 1..input.players.len() {
            let right_player = input.players[right_index];
            let right_selection = replacement
                .filter(|(player_index, _)| *player_index == right_index)
                .map(|(_, candidate_index)| candidate_index)
                .unwrap_or_else(|| selections.get(right_index).copied().unwrap_or(0));
            let Some(right_candidate) = right_player.candidates.get(right_selection).copied() else {
                continue;
            };
            conflicts += usize::from(spatial_claim_conflict(
                left_candidate.claim,
                right_candidate.claim,
            ));
        }
    }
    conflicts
}

fn preferred_team_spatial_candidate(player: TeamSpatialPlayerInput<'_>) -> usize {
    player
        .candidates
        .get(player.preferred_candidate_index)
        .map(|_| player.preferred_candidate_index)
        .unwrap_or(0)
}

pub fn coordinate_team_spatial_tasks_into(
    input: &TeamSpatialAssignmentInput<'_>,
    assignments: &mut [TeamSpatialAssignment],
) -> TeamSpatialCoordinationSummary {
    assert!(
        input.players.len() <= MAX_FIXED_TEAM_TACTICAL_TASKS,
        "fixed team spatial coordination supports eleven players"
    );
    assert!(
        assignments.len() >= input.players.len(),
        "fixed team spatial assignment output is too small"
    );

    let player_count = input.players.len();
    let mut selections = [0usize; MAX_FIXED_TEAM_TACTICAL_TASKS];
    for (player_index, player) in input.players.iter().copied().enumerate() {
        selections[player_index] = preferred_team_spatial_candidate(player);
    }
    let conflicts_before =
        team_spatial_conflict_count(input, &selections[..player_count], None);

    let mut order = [0usize; MAX_FIXED_TEAM_TACTICAL_TASKS];
    for player_index in 0..player_count {
        order[player_index] = player_index;
    }
    for left_index in 0..player_count {
        let mut best_index = left_index;
        for right_index in left_index + 1..player_count {
            let left_player = input.players[order[best_index]];
            let right_player = input.players[order[right_index]];
            let left_value = left_player
                .candidates
                .get(selections[order[best_index]])
                .map(|candidate| candidate.local_value)
                .unwrap_or(f64::NEG_INFINITY);
            let right_value = right_player
                .candidates
                .get(selections[order[right_index]])
                .map(|candidate| candidate.local_value)
                .unwrap_or(f64::NEG_INFINITY);
            if right_value > left_value + 1e-9
                || ((right_value - left_value).abs() <= 1e-9
                    && right_player.index < left_player.index)
            {
                best_index = right_index;
            }
        }
        order.swap(left_index, best_index);
    }

    let mut committed = [false; MAX_FIXED_TEAM_TACTICAL_TASKS];
    for order_index in 0..player_count {
        let player_index = order[order_index];
        let player = input.players[player_index];
        if player.candidates.is_empty() {
            continue;
        }
        let preferred = selections[player_index];
        let mut best_candidate_index = preferred;
        let mut best_conflicts = 0usize;
        for other_index in 0..player_count {
            if !committed[other_index] {
                continue;
            }
            let other_player = input.players[other_index];
            let Some(candidate) = player.candidates.get(preferred).copied() else {
                continue;
            };
            let Some(other_candidate) = other_player
                .candidates
                .get(selections[other_index])
                .copied()
            else {
                continue;
            };
            best_conflicts +=
                usize::from(spatial_claim_conflict(candidate.claim, other_candidate.claim));
        }
        let mut best_value = player
            .candidates
            .get(preferred)
            .map(|candidate| candidate.local_value)
            .unwrap_or(f64::NEG_INFINITY);
        for candidate_index in 0..player.candidates.len() {
            let candidate = player.candidates[candidate_index];
            let mut conflicts = 0usize;
            for other_index in 0..player_count {
                if !committed[other_index] {
                    continue;
                }
                let other_player = input.players[other_index];
                let Some(other_candidate) = other_player
                    .candidates
                    .get(selections[other_index])
                    .copied()
                else {
                    continue;
                };
                conflicts +=
                    usize::from(spatial_claim_conflict(candidate.claim, other_candidate.claim));
            }
            if conflicts < best_conflicts
                || (conflicts == best_conflicts
                    && candidate.local_value > best_value + 1e-9)
            {
                best_candidate_index = candidate_index;
                best_conflicts = conflicts;
                best_value = candidate.local_value;
            }
        }
        selections[player_index] = best_candidate_index;
        committed[player_index] = true;
    }

    let maximum_sweeps = player_count.saturating_mul(2).max(1);
    for _ in 0..maximum_sweeps {
        let mut changed = false;
        let current_conflicts =
            team_spatial_conflict_count(input, &selections[..player_count], None);
        for player_index in 0..player_count {
            let player = input.players[player_index];
            let current_index = selections[player_index];
            let mut best_index = current_index;
            let mut best_conflicts = current_conflicts;
            let mut best_value = player
                .candidates
                .get(current_index)
                .map(|candidate| candidate.local_value)
                .unwrap_or(f64::NEG_INFINITY);
            for candidate_index in 0..player.candidates.len() {
                if candidate_index == current_index {
                    continue;
                }
                let conflicts = team_spatial_conflict_count(
                    input,
                    &selections[..player_count],
                    Some((player_index, candidate_index)),
                );
                let value = player.candidates[candidate_index].local_value;
                if conflicts < best_conflicts
                    || (conflicts == best_conflicts
                        && conflicts < current_conflicts
                        && value > best_value + 1e-9)
                {
                    best_index = candidate_index;
                    best_conflicts = conflicts;
                    best_value = value;
                }
            }
            if best_index != current_index {
                selections[player_index] = best_index;
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }

    let conflicts_after =
        team_spatial_conflict_count(input, &selections[..player_count], None);
    let mut displaced_count = 0;
    for player_index in 0..player_count {
        let player = input.players[player_index];
        let candidate_index = selections[player_index];
        let local_value = player
            .candidates
            .get(candidate_index)
            .map(|candidate| candidate.local_value)
            .unwrap_or(f64::NEG_INFINITY);
        let displaced_from_preference =
            candidate_index != preferred_team_spatial_candidate(player);
        displaced_count += usize::from(displaced_from_preference);
        assignments[player_index] = TeamSpatialAssignment {
            index: player.index,
            candidate_index,
            local_value,
            displaced_from_preference,
        };
    }
    TeamSpatialCoordinationSummary {
        conflicts_before,
        conflicts_after,
        displaced_count,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct GoalProposal<'a> {
    pub goal_type: &'a str,
    pub phase: &'a str,
    pub raw_target: (f64, f64),
    pub local_value: f64,
    pub accepted_tick: i32,
    pub expected_duration_ticks: i32,
    pub pressure_interrupt: f64,
    pub coordination: TacticalTaskCoordination,
}

#[derive(Clone, Copy, Debug)]
pub struct VisibleEntity {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub confidence: f64,
    pub is_teammate: bool,
    pub is_goalkeeper: bool,
}

#[cfg(test)]
const EMPTY_VISIBLE_ENTITY: VisibleEntity = VisibleEntity {
    index: 0,
    pos: (0.0, 0.0),
    velocity: (0.0, 0.0),
    confidence: 0.0,
    is_teammate: false,
    is_goalkeeper: false,
};

#[derive(Clone, Copy, Debug)]
pub struct PlayerObservation<'a> {
    pub self_index: usize,
    pub self_pos: (f64, f64),
    pub facing_direction: f64,
    pub ball_pos: (f64, f64),
    pub ball_confidence: f64,
    pub visible_entities: &'a [VisibleEntity],
}

#[derive(Clone, Copy, Debug)]
pub struct BelievedEntity {
    pub index: usize,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub confidence: f64,
    pub is_teammate: bool,
    pub is_goalkeeper: bool,
}

const EMPTY_BELIEVED_ENTITY: BelievedEntity = BelievedEntity {
    index: 0,
    pos: (0.0, 0.0),
    velocity: (0.0, 0.0),
    confidence: 0.0,
    is_teammate: false,
    is_goalkeeper: false,
};

#[derive(Clone, Copy, Debug)]
pub struct PlayerBelief {
    pub ball_pos: (f64, f64),
    pub ball_confidence: f64,
    entities: [BelievedEntity; MAX_PLAYER_OBSERVED_ENTITIES],
    entity_count: usize,
}

impl Default for PlayerBelief {
    fn default() -> Self {
        Self {
            ball_pos: (0.0, 0.0),
            ball_confidence: 0.0,
            entities: [EMPTY_BELIEVED_ENTITY; MAX_PLAYER_OBSERVED_ENTITIES],
            entity_count: 0,
        }
    }
}

impl PlayerBelief {
    pub fn entities(&self) -> &[BelievedEntity] {
        &self.entities[..self.entity_count]
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TaskAcceptanceInput<'a> {
    pub current: TacticalTask,
    pub proposal: GoalProposal<'a>,
    pub tactical_anchor: (f64, f64),
    pub observation: &'a PlayerObservation<'a>,
    pub belief: &'a PlayerBelief,
    pub plan_signals: TeamPlanSignals,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TaskAcceptance {
    pub task: TacticalTask,
    pub accepted: bool,
    pub candidate_value: f64,
    pub retained_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TaskMotionInput {
    pub task: TacticalTask,
    pub player_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub tick: i32,
    pub plan_signals: TeamPlanSignals,
}

pub fn observe_entities_into(
    self_index: usize,
    self_pos: (f64, f64),
    ball_pos: (f64, f64),
    vision: VisionContext,
    entities: &[(usize, (f64, f64), (f64, f64), bool, bool)],
    output: &mut [VisibleEntity],
) -> (f64, usize) {
    let ball_confidence = vision.confidence(self_pos, ball_pos);
    let mut count = 0;
    for (index, pos, velocity, is_teammate, is_goalkeeper) in entities {
        if *index == self_index {
            continue;
        }
        let confidence = vision.confidence(self_pos, *pos);
        if confidence <= 0.0 {
            continue;
        }
        if count == output.len() {
            break;
        }
        output[count] = VisibleEntity {
            index: *index,
            pos: *pos,
            velocity: *velocity,
            confidence,
            is_teammate: *is_teammate,
            is_goalkeeper: *is_goalkeeper,
        };
        count += 1;
    }
    (ball_confidence, count)
}

pub fn update_player_belief(
    belief: &mut PlayerBelief,
    observation: &PlayerObservation<'_>,
    iq: f64,
) {
    let inference = smoothstep(40.0, 95.0, iq);
    let retained_confidence = 0.08 + 0.22 * inference;
    let previous = *belief;
    let mut entities = [EMPTY_BELIEVED_ENTITY; MAX_PLAYER_OBSERVED_ENTITIES];
    let mut entity_count = 0;
    for visible in observation.visible_entities {
        if entity_count == entities.len() {
            break;
        }
        let confidence = (visible.confidence * (0.64 + 0.36 * inference)).clamp(0.0, 1.0);
        entities[entity_count] = BelievedEntity {
            index: visible.index,
            pos: visible.pos,
            velocity: visible.velocity,
            confidence,
            is_teammate: visible.is_teammate,
            is_goalkeeper: visible.is_goalkeeper,
        };
        entity_count += 1;
    }
    for remembered in previous.entities() {
        if entities[..entity_count]
            .iter()
            .any(|entity| entity.index == remembered.index)
        {
            continue;
        }
        let confidence = remembered.confidence * retained_confidence;
        if confidence >= 0.08 && entity_count < entities.len() {
            entities[entity_count] = BelievedEntity {
                index: remembered.index,
                pos: remembered.pos,
                velocity: remembered.velocity,
                confidence,
                is_teammate: remembered.is_teammate,
                is_goalkeeper: remembered.is_goalkeeper,
            };
            entity_count += 1;
        }
    }
    let ball_visible = observation.ball_confidence > 0.0;
    let (ball_pos, ball_confidence) = if ball_visible {
        (
            observation.ball_pos,
            (observation.ball_confidence * (0.68 + 0.32 * inference)).clamp(0.0, 1.0),
        )
    } else {
        (
            previous.ball_pos,
            (previous.ball_confidence * retained_confidence).clamp(0.0, 1.0),
        )
    };
    *belief = PlayerBelief {
        ball_pos,
        ball_confidence,
        entities,
        entity_count,
    };
}

pub fn task_intent_from_goal(goal_type: &str, phase: &str) -> TacticalTaskIntent {
    if goal_type.starts_with("defend_close_down") {
        TacticalTaskIntent::CloseDown
    } else if goal_type.starts_with("defend_press")
        || matches!(goal_type, "defend" if phase == "press")
    {
        TacticalTaskIntent::Press
    } else if goal_type.starts_with("defend_cover_lane") {
        TacticalTaskIntent::Screen
    } else if goal_type.starts_with("defend_protect") {
        TacticalTaskIntent::Cover
    } else if goal_type.starts_with("defend_mark") || goal_type.starts_with("defend_recover") {
        TacticalTaskIntent::Recover
    } else if goal_type.contains("arrival") || goal_type.contains("far_post") {
        TacticalTaskIntent::Receive
    } else if goal_type.contains("carry") || goal_type.contains("byline") {
        TacticalTaskIntent::Carry
    } else if matches!(
        goal_type,
        "recycle" | "switch_play" | "protect_ball" | "hold_for_opportunity"
    ) {
        TacticalTaskIntent::Control
    } else {
        TacticalTaskIntent::Support
    }
}

fn intent_commitment(intent: TacticalTaskIntent) -> f64 {
    match intent {
        TacticalTaskIntent::Receive => 0.78,
        TacticalTaskIntent::Support => 0.62,
        TacticalTaskIntent::Carry => 0.72,
        TacticalTaskIntent::Control => 0.56,
        TacticalTaskIntent::CloseDown => 0.70,
        TacticalTaskIntent::Press => 0.82,
        TacticalTaskIntent::Cover => 0.68,
        TacticalTaskIntent::Screen => 0.64,
        TacticalTaskIntent::Recover => 0.34,
    }
}

fn target_support_from_belief(
    target: (f64, f64),
    belief: &PlayerBelief,
    is_teammate: bool,
) -> f64 {
    belief
        .entities()
        .iter()
        .filter(|entity| entity.is_teammate == is_teammate)
        .map(|entity| {
            entity.confidence * (1.0 - distance(target, entity.pos) / 28.0).max(0.0)
        })
        .fold(0.0, f64::max)
}

pub fn formation_debt(
    raw_target: (f64, f64),
    tactical_anchor: (f64, f64),
    intent: TacticalTaskIntent,
    belief: &PlayerBelief,
    plan_signals: TeamPlanSignals,
) -> f64 {
    let displacement = distance(raw_target, tactical_anchor);
    let base_debt = smoothstep(6.0, 26.0, displacement);
    let teammate_cover = target_support_from_belief(tactical_anchor, belief, true);
    let target_pressure = target_support_from_belief(raw_target, belief, false);
    let tactical_exception = match intent {
        TacticalTaskIntent::Receive | TacticalTaskIntent::Support => {
            0.50 * teammate_cover + 0.22 * plan_signals.switch_bias
        }
        TacticalTaskIntent::Carry | TacticalTaskIntent::Control => 0.18 * plan_signals.risk_budget,
        TacticalTaskIntent::CloseDown => 0.24 * plan_signals.press_intensity,
        TacticalTaskIntent::Press => 0.30 * plan_signals.press_intensity,
        TacticalTaskIntent::Cover | TacticalTaskIntent::Screen => 0.20 * teammate_cover,
        TacticalTaskIntent::Recover => 0.0,
    };
    (base_debt * (0.30 + 0.70 * plan_signals.compactness) * (1.0 - tactical_exception)
        + 0.10 * target_pressure)
        .clamp(0.0, 1.0)
}

pub fn task_policy_utility(
    origin: (f64, f64),
    target: (f64, f64),
    intent: TacticalTaskIntent,
    plan_signals: TeamPlanSignals,
    attacking_right: bool,
    pitch_length: f64,
    pitch_width: f64,
    belief: &PlayerBelief,
) -> f64 {
    let nearest_support = target_support_from_belief(target, belief, true);
    let nearest_pressure = target_support_from_belief(target, belief, false);
    let action = team_plan_action_utility(&TeamPlanActionInput {
        signals: plan_signals,
        origin,
        target,
        attacking_right,
        pitch_length,
        pitch_width,
        success_probability: (0.52 + 0.34 * nearest_support - 0.20 * nearest_pressure)
            .clamp(0.15, 0.96),
        continuation_probability: (0.48 + 0.30 * belief.ball_confidence + 0.22 * nearest_support)
            .clamp(0.10, 0.96),
        risk: (0.62 * nearest_pressure + 0.18 * (1.0 - belief.ball_confidence)).clamp(0.0, 1.0),
    });
    let intent_alignment = match intent {
        TacticalTaskIntent::Receive | TacticalTaskIntent::Support => {
            0.30 * action.switch_value + 0.22 * action.recycle_value + 0.18 * nearest_support
        }
        TacticalTaskIntent::Carry => 0.32 * action.forward_progress + 0.18 * plan_signals.tempo,
        TacticalTaskIntent::Control => 0.34 * action.recycle_value + 0.22 * action.retention,
        TacticalTaskIntent::CloseDown => {
            0.34 * plan_signals.press_intensity + 0.16 * nearest_pressure
        }
        TacticalTaskIntent::Press => 0.42 * plan_signals.press_intensity + 0.20 * nearest_pressure,
        TacticalTaskIntent::Cover | TacticalTaskIntent::Screen => 0.30 * plan_signals.compactness,
        TacticalTaskIntent::Recover => 0.16 * plan_signals.compactness,
    };
    (0.50 * action.alignment + intent_alignment).clamp(-0.30, 1.20)
}

pub fn accept_task(input: &TaskAcceptanceInput<'_>) -> TaskAcceptance {
    let intent = task_intent_from_goal(input.proposal.goal_type, input.proposal.phase);
    let coordination = input.proposal.coordination.clamped();
    let policy_utility = task_policy_utility(
        input.observation.self_pos,
        input.proposal.raw_target,
        intent,
        input.plan_signals,
        input.attacking_right,
        input.pitch_length,
        input.pitch_width,
        input.belief,
    );
    let spatial_claim = spatial_claim_for_task(
        input.observation.self_pos,
        input.proposal.raw_target,
        intent,
        input.attacking_right,
    );
    let debt = formation_debt(
        input.proposal.raw_target,
        input.tactical_anchor,
        intent,
        input.belief,
        input.plan_signals,
    );
    let confidence = (0.42 + 0.58 * input.observation.ball_confidence).clamp(0.0, 1.0);
    let candidate_value = input.proposal.local_value * confidence + policy_utility * 0.18 - debt * 0.26;
    let active_current = input.current.active(input.proposal.accepted_tick);
    let same_intent = active_current && input.current.intent == intent;
    let retained_value = if active_current {
        input.current.local_value
            + input.current.policy_utility * 0.18
            - input.current.formation_debt * 0.26
            + input.current.commitment * 0.06
    } else {
        f64::NEG_INFINITY
    };
    let coordinated_reassignment = coordination.active();
    let accepted = same_intent
        || !active_current
        || coordinated_reassignment
        || candidate_value > retained_value + 0.035;
    let retained_coordination = if coordination.active() {
        coordination
    } else {
        input.current.coordination
    };
    let task = if same_intent {
        TacticalTask {
            intent,
            phase: TacticalTaskPhase::Active,
            raw_target: input.proposal.raw_target,
            accepted_tick: input.current.accepted_tick,
            expires_tick: input
                .current
                .expires_tick
                .max(input.proposal.accepted_tick + input.proposal.expected_duration_ticks.clamp(1, 12)),
            commitment: (0.60 * input.current.commitment
                + 0.40
                    * intent_commitment(intent)
                    * (0.58 + 0.42 * confidence)
                    * (1.0 - 0.30 * input.proposal.pressure_interrupt.clamp(0.0, 1.0)))
                .clamp(0.0, 1.0),
            local_value: input.proposal.local_value.max(0.0),
            policy_utility,
            formation_debt: debt,
            interruption: input.proposal.pressure_interrupt.clamp(0.0, 1.0),
            coordination: retained_coordination,
            spatial_claim,
        }
    } else if accepted {
        TacticalTask {
            intent,
            phase: TacticalTaskPhase::Active,
            raw_target: input.proposal.raw_target,
            accepted_tick: input.proposal.accepted_tick,
            expires_tick: input.proposal.accepted_tick
                + input.proposal.expected_duration_ticks.clamp(1, 12),
            commitment: (intent_commitment(intent) * (0.58 + 0.42 * confidence)
                * (1.0 - 0.30 * input.proposal.pressure_interrupt.clamp(0.0, 1.0)))
                .clamp(0.0, 1.0),
            local_value: input.proposal.local_value.max(0.0),
            policy_utility,
            formation_debt: debt,
            interruption: input.proposal.pressure_interrupt.clamp(0.0, 1.0),
            coordination,
            spatial_claim,
        }
    } else {
        input.current
    };
    TaskAcceptance {
        task,
        accepted,
        candidate_value,
        retained_value,
    }
}

pub fn task_motion_target(input: &TaskMotionInput) -> (f64, f64) {
    if !input.task.active(input.tick) {
        return input.tactical_anchor;
    }
    let remaining = (input.task.expires_tick - input.tick).max(0) as f64;
    let time_pressure = 1.0 - smoothstep(0.0, 5.0, remaining);
    let commitment = (input.task.commitment * (0.72 + 0.28 * time_pressure)).clamp(0.0, 1.0);
    let structural_pull = (1.0 - commitment)
        * input.task.formation_debt
        * (0.08 + 0.18 * input.plan_signals.compactness)
        * (1.0 - 0.55 * input.task.policy_utility.max(0.0));
    let target = (
        input.task.raw_target.0 * (1.0 - structural_pull)
            + input.tactical_anchor.0 * structural_pull,
        input.task.raw_target.1 * (1.0 - structural_pull)
            + input.tactical_anchor.1 * structural_pull,
    );
    let _ = input.player_pos;
    target
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::team_plan::team_plan_signals;
    use crate::team_plan::TeamPlanKind;
    use crate::vision::{build_vision_context, VisionContextInput};

    fn vision(iq: f64) -> VisionContext {
        build_vision_context(&VisionContextInput {
            iq,
            facing_direction: 0.0,
            attacking_right: true,
            vision_base_fov: 150.0,
            vision_iq_bonus_factor: 0.5,
            vision_base_distance: 32.0,
            vision_iq_distance_bonus_factor: 0.35,
            vision_max_distance: 65.0,
        })
    }

    fn observation<'a>(entities: &'a [VisibleEntity]) -> PlayerObservation<'a> {
        PlayerObservation {
            self_index: 0,
            self_pos: (45.0, 34.0),
            facing_direction: 0.0,
            ball_pos: (52.0, 34.0),
            ball_confidence: 1.0,
            visible_entities: entities,
        }
    }

    #[test]
    fn invisible_entities_do_not_enter_belief() {
        let entities = [
            (1, (55.0, 34.0), (0.0, 0.0), true, false),
            (2, (28.0, 34.0), (0.0, 0.0), false, false),
        ];
        let mut visible = [EMPTY_VISIBLE_ENTITY; MAX_PLAYER_OBSERVED_ENTITIES];
        let (_, count) =
            observe_entities_into(0, (45.0, 34.0), (52.0, 34.0), vision(55.0), &entities, &mut visible);
        let mut belief = PlayerBelief::default();
        update_player_belief(&mut belief, &observation(&visible[..count]), 55.0);
        assert!(belief.entities().iter().any(|entity| entity.index == 1));
        assert!(!belief.entities().iter().any(|entity| entity.index == 2));
    }

    #[test]
    fn higher_iq_improves_use_of_visible_clues_without_revealing_hidden_entities() {
        let visible = [VisibleEntity {
            index: 1,
            pos: (60.0, 34.0),
            velocity: (0.0, 0.0),
            confidence: 0.42,
            is_teammate: true,
            is_goalkeeper: false,
        }];
        let observation = observation(&visible);
        let mut low = PlayerBelief::default();
        let mut high = PlayerBelief::default();
        update_player_belief(&mut low, &observation, 45.0);
        update_player_belief(&mut high, &observation, 92.0);
        assert!(high.entities()[0].confidence > low.entities()[0].confidence);
        assert_eq!(high.entities().len(), low.entities().len());
    }

    #[test]
    fn hidden_ball_retains_last_belief_without_observing_its_real_position() {
        let mut belief = PlayerBelief {
            ball_pos: (52.0, 34.0),
            ball_confidence: 0.9,
            ..PlayerBelief::default()
        };
        let hidden_ball = PlayerObservation {
            ball_pos: (86.0, 12.0),
            ball_confidence: 0.0,
            ..observation(&[])
        };

        update_player_belief(&mut belief, &hidden_ball, 82.0);

        assert_eq!(belief.ball_pos, (52.0, 34.0));
        assert!(belief.ball_confidence > 0.0);
        assert!(belief.ball_confidence < 0.9);
    }

    #[test]
    fn task_preserves_raw_target_when_motion_target_is_resolved() {
        let task = TacticalTask {
            intent: TacticalTaskIntent::Receive,
            phase: TacticalTaskPhase::Active,
            raw_target: (78.0, 14.0),
            accepted_tick: 10,
            expires_tick: 18,
            commitment: 0.92,
            local_value: 0.82,
            policy_utility: 0.62,
            formation_debt: 0.44,
            interruption: 0.0,
            coordination: TacticalTaskCoordination::default(),
            spatial_claim: SpatialClaim::default(),
        };
        let movement_target = task_motion_target(&TaskMotionInput {
            task,
            player_pos: (52.0, 28.0),
            tactical_anchor: (58.0, 28.0),
            tick: 12,
            plan_signals: team_plan_signals(TeamPlanKind::Recycle),
        });
        assert_ne!(movement_target, task.raw_target);
        assert_eq!(task.raw_target, (78.0, 14.0));
    }

    #[test]
    fn expired_task_returns_to_the_current_structural_target() {
        let task = TacticalTask {
            intent: TacticalTaskIntent::Press,
            phase: TacticalTaskPhase::Active,
            raw_target: (74.0, 30.0),
            accepted_tick: 10,
            expires_tick: 13,
            commitment: 0.9,
            local_value: 0.9,
            policy_utility: 0.3,
            formation_debt: 0.2,
            interruption: 0.0,
            coordination: TacticalTaskCoordination::default(),
            spatial_claim: SpatialClaim::default(),
        };
        let anchor = (48.0, 34.0);

        assert_eq!(
            task_motion_target(&TaskMotionInput {
                task,
                player_pos: (52.0, 34.0),
                tactical_anchor: anchor,
                tick: 14,
                plan_signals: team_plan_signals(TeamPlanKind::DefendBlock),
            }),
            anchor
        );
    }

    #[test]
    fn high_value_support_is_not_rejected_only_for_anchor_distance() {
        let visible = [
            VisibleEntity {
                index: 1,
                pos: (53.0, 34.0),
                velocity: (0.0, 0.0),
                confidence: 1.0,
                is_teammate: true,
                is_goalkeeper: false,
            },
            VisibleEntity {
                index: 2,
                pos: (69.0, 18.0),
                velocity: (0.0, 0.0),
                confidence: 0.7,
                is_teammate: false,
                is_goalkeeper: false,
            },
        ];
        let observation = observation(&visible);
        let mut belief = PlayerBelief::default();
        update_player_belief(&mut belief, &observation, 82.0);
        let accepted = accept_task(&TaskAcceptanceInput {
            current: TacticalTask::inactive((47.0, 34.0)),
            proposal: GoalProposal {
                goal_type: "support_carrier",
                phase: "support",
                raw_target: (76.0, 12.0),
                local_value: 1.18,
                accepted_tick: 20,
                expected_duration_ticks: 7,
                pressure_interrupt: 0.08,
                coordination: TacticalTaskCoordination::default(),
            },
            tactical_anchor: (47.0, 34.0),
            observation: &observation,
            belief: &belief,
            plan_signals: team_plan_signals(TeamPlanKind::Recycle),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });
        assert!(accepted.accepted);
        assert_eq!(accepted.task.raw_target, (76.0, 12.0));
        assert!(accepted.task.formation_debt > 0.0);
    }

    fn spatial_candidate(
        origin: (f64, f64),
        target: (f64, f64),
        local_value: f64,
    ) -> TeamSpatialCandidate {
        TeamSpatialCandidate {
            target,
            local_value,
            claim: spatial_claim_for_task(
                origin,
                target,
                TacticalTaskIntent::Support,
                true,
            ),
        }
    }

    #[test]
    fn coordinated_support_claims_split_congested_box_edge_targets() {
        let origin = (72.0, 34.0);
        let shared_arc = (86.0, 34.0);
        let first = [
            spatial_candidate(origin, shared_arc, 1.00),
            spatial_candidate(origin, (78.0, 12.0), 0.62),
        ];
        let second = [
            spatial_candidate(origin, shared_arc, 0.96),
            spatial_candidate(origin, (76.0, 52.0), 0.66),
        ];
        let third = [
            spatial_candidate(origin, shared_arc, 0.92),
            spatial_candidate(origin, (91.0, 17.0), 0.61),
        ];
        let fourth = [
            spatial_candidate(origin, shared_arc, 0.88),
            spatial_candidate(origin, (68.0, 43.0), 0.67),
        ];
        let fifth = [
            spatial_candidate(origin, shared_arc, 0.84),
            spatial_candidate(origin, (90.0, 63.0), 0.64),
        ];
        let players = [
            TeamSpatialPlayerInput {
                index: 0,
                candidates: &first,
                preferred_candidate_index: 0,
            },
            TeamSpatialPlayerInput {
                index: 1,
                candidates: &second,
                preferred_candidate_index: 0,
            },
            TeamSpatialPlayerInput {
                index: 2,
                candidates: &third,
                preferred_candidate_index: 0,
            },
            TeamSpatialPlayerInput {
                index: 3,
                candidates: &fourth,
                preferred_candidate_index: 0,
            },
            TeamSpatialPlayerInput {
                index: 4,
                candidates: &fifth,
                preferred_candidate_index: 0,
            },
        ];
        let mut assignments = [TeamSpatialAssignment::default();
            MAX_FIXED_TEAM_TACTICAL_TASKS];
        let input = TeamSpatialAssignmentInput { players: &players };

        let summary = coordinate_team_spatial_tasks_into(
            &input,
            &mut assignments[..players.len()],
        );

        assert_eq!(summary.conflicts_before, 10);
        assert_eq!(summary.conflicts_after, 0);
        assert_eq!(assignments[0].candidate_index, 0);
        assert_eq!(summary.displaced_count, 4);
        for left_index in 0..players.len() {
            for right_index in left_index + 1..players.len() {
                let left = players[left_index].candidates[assignments[left_index].candidate_index];
                let right =
                    players[right_index].candidates[assignments[right_index].candidate_index];
                assert!(
                    !spatial_claim_conflict(left.claim, right.claim),
                    "coordinated support claims must not occupy the same run space: {left:?} {right:?}"
                );
            }
        }
    }

    #[test]
    fn uncommitted_claim_does_not_displace_an_available_support_lane() {
        let origin = (72.0, 34.0);
        let committed = spatial_candidate(origin, (86.0, 34.0), 0.96);
        let alternate = spatial_candidate(origin, (77.0, 52.0), 0.60);
        let inactive = TeamSpatialCandidate {
            target: (86.0, 34.0),
            local_value: 1.20,
            claim: SpatialClaim::default(),
        };
        let primary = [committed];
        let secondary = [inactive, alternate];
        let players = [
            TeamSpatialPlayerInput {
                index: 0,
                candidates: &primary,
                preferred_candidate_index: 0,
            },
            TeamSpatialPlayerInput {
                index: 1,
                candidates: &secondary,
                preferred_candidate_index: 0,
            },
        ];
        let mut assignments = [TeamSpatialAssignment::default();
            MAX_FIXED_TEAM_TACTICAL_TASKS];

        let summary = coordinate_team_spatial_tasks_into(
            &TeamSpatialAssignmentInput { players: &players },
            &mut assignments[..players.len()],
        );

        assert_eq!(summary.conflicts_after, 0);
        assert_eq!(assignments[0].candidate_index, 0);
        assert_eq!(assignments[1].candidate_index, 0);
        assert!(!assignments[1].displaced_from_preference);
    }
}
