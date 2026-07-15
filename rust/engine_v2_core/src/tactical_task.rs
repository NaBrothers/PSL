use crate::physics::{distance, smoothstep};
use crate::team_plan::{team_plan_action_utility, TeamPlanActionInput, TeamPlanSignals};
use crate::vision::VisionContext;

pub const MAX_PLAYER_OBSERVED_ENTITIES: usize = 22;
pub const MAX_TASK_OUTLET_COVERAGE: usize = 11;

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
        }
    }

    pub fn active(&self, tick: i32) -> bool {
        self.phase == TacticalTaskPhase::Active && tick <= self.expires_tick
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
}
