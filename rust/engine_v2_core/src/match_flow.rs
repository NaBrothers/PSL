use crate::arrival::{resolve_first_touch, FirstTouchInput};
use crate::contested::{
    resolve_contested_owner, tick_contested_ball, ContestedOwnerInput, ContestedOwnerPlayerInput,
    ContestedTickInput,
};
use crate::execution::{
    execute_carry, execute_clear, execute_hold, execute_pass, execute_shot, CarryExecutionInput,
    ClearExecutionInput, ExecutionOpponent, HoldExecutionInput, PassExecutionInput,
    ShotExecutionInput,
};
use crate::goalkeeper::{goalkeeper_shape_anchor, GkShapeAnchorInput};
use crate::interactions::{resolve_duel, DefenderActionInput, DuelResolveInput};
use crate::offside::get_offside_line_from_xs;
use crate::physics::PitchBoundaryKind;
use crate::team_plan::TeamPlanSignals;

#[derive(Clone, Debug)]
pub struct GoalEventInput<'a> {
    pub scorer_name: &'a str,
    pub scoring_team_home: bool,
    pub home_score: i32,
    pub away_score: i32,
    pub last_passer_team_home: Option<bool>,
    pub last_passer_idx: i32,
    pub scorer_idx: i32,
    pub scoring_team_size: i32,
    pub assister_name: &'a str,
    pub assister_color: &'a str,
}

#[derive(Clone, Debug)]
pub struct GoalEventOutput {
    pub home_score: i32,
    pub away_score: i32,
    pub has_assist: bool,
    pub assister_idx: i32,
    pub assister_name: String,
    pub assister_color: String,
    pub event_text: String,
}

#[derive(Clone, Debug)]
pub struct ScoreGoalPlanInput<'a> {
    pub scorer_name: &'a str,
    pub scoring_team_home: bool,
    pub conceding_team_home: bool,
    pub home_score: i32,
    pub away_score: i32,
    pub last_passer_team_home: Option<bool>,
    pub last_passer_idx: i32,
    pub scorer_idx: i32,
    pub scoring_team_size: i32,
    pub assister_name: &'a str,
    pub assister_color: &'a str,
    pub tick: i32,
    pub tick_duration: f64,
}

#[derive(Clone, Debug)]
pub struct ScoreGoalPlanOutput {
    pub home_score: i32,
    pub away_score: i32,
    pub has_assist: bool,
    pub assister_idx: i32,
    pub assister_name: String,
    pub assister_color: String,
    pub minute: i32,
    pub event_text: String,
    pub pause_ms: i32,
    pub restart_team_home: bool,
    pub restart_ticks: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct KeyPassInput {
    pub shooter_team_home: bool,
    pub shooter_idx: i32,
    pub last_passer_team_home: Option<bool>,
    pub last_passer_idx: i32,
    pub team_size: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct KeyPassOutput {
    pub has_key_pass: bool,
    pub key_passer_idx: i32,
}

#[derive(Clone, Debug)]
pub struct GiveBallPlanInput {
    pub previous_holder_team_code: Option<u8>,
    pub previous_holder_idx: i32,
    pub new_holder_team_code: u8,
    pub new_holder_idx: i32,
    pub new_holder_pos: (f64, f64),
    pub receive_origin: Option<(f64, f64)>,
}

#[derive(Clone, Debug)]
pub struct GiveBallPlanOutput {
    pub clear_previous_holder: bool,
    pub previous_holder_team_code: Option<u8>,
    pub previous_holder_idx: i32,
    pub clear_offside_flags: bool,
    pub clear_team_goals: bool,
    pub new_holder_idx: i32,
    pub new_holder_team_code: u8,
    pub ball_pos: (f64, f64),
    pub last_receive_origin: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct PlayerMoveTickInput<'a> {
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub movement_intent: &'a str,
    pub state: &'a str,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Debug)]
pub struct PlayerMoveTickOutput {
    pub moved: bool,
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub distance_covered: f64,
    pub facing_direction: Option<f64>,
    pub desired_speed: f64,
}

#[derive(Clone, Debug)]
pub struct PlayerMoveSpeedInput<'a> {
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub speed_ability: i32,
    pub movement_intent: &'a str,
    pub state: &'a str,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
}

#[derive(Clone, Debug)]
pub struct PlayerMoveSpeedOutput {
    pub speed: f64,
}

#[derive(Clone, Debug)]
pub struct PlayerSetMovementTargetInput<'a> {
    pub current_target: (f64, f64),
    pub requested_target: (f64, f64),
    pub current_intent: &'a str,
    pub requested_intent: Option<&'a str>,
}

#[derive(Clone, Debug)]
pub struct PlayerSetMovementTargetOutput {
    pub target_pos: (f64, f64),
    pub movement_intent: String,
}

#[derive(Clone, Copy, Debug)]
pub struct PlayerSetMovementTargetRefOutput {
    pub target_pos: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct PlayerTickStunInput<'a> {
    pub state: &'a str,
    pub stun_ticks_remaining: i32,
}

#[derive(Clone, Debug)]
pub struct PlayerTickStunOutput {
    pub state: String,
    pub stun_ticks_remaining: i32,
}

#[derive(Clone, Debug)]
pub struct PlayerApplyStunInput {
    pub tackle_fail_stun_seconds: f64,
    pub tick_duration: f64,
}

#[derive(Clone, Debug)]
pub struct PlayerApplyStunOutput {
    pub state: String,
    pub stun_ticks_remaining: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotXgInput {
    pub explicit_xg: Option<f64>,
    pub on_target_prob: f64,
    pub goal_reward_constant: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotXgOutput {
    pub xg: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotLogXgInput {
    pub total_xg: f64,
    pub logged_xg_sum: f64,
    pub clamp_nonnegative: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotLogXgOutput {
    pub raw_xg: f64,
    pub rounded_xg: f64,
}

#[derive(Clone, Debug)]
pub struct ShotArrivalEventInput<'a> {
    pub shooter_name: &'a str,
    pub keeper_name: &'a str,
    pub outcome: &'a str,
}

#[derive(Clone, Debug)]
pub struct ShotArrivalEventOutput {
    pub pending_event_text: String,
    pub pause_ms: i32,
    pub trace_event: String,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotLogEntryInput<'a> {
    pub origin: (f64, f64),
    pub target: Option<(f64, f64)>,
    pub xg: f64,
    pub in_box: bool,
    pub outcome: &'a str,
}

#[derive(Clone, Debug)]
pub struct ShotLogEntryOutput {
    pub x: f64,
    pub y: f64,
    pub xg: f64,
    pub in_box: bool,
    pub outcome: String,
    pub target_x: Option<f64>,
    pub target_y: Option<f64>,
}

#[derive(Clone, Debug)]
pub struct ShotArrivalPlanInput<'a> {
    pub shooter_name: &'a str,
    pub keeper_name: &'a str,
    pub shot_origin: (f64, f64),
    pub shot_target: (f64, f64),
    pub attacking_right: bool,
    pub on_target: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub gk_pos: (f64, f64),
    pub gk_attributes: crate::goalkeeper::GkSaveAttributes,
    pub save_roll: f64,
    pub total_xg: f64,
    pub logged_xg_sum: f64,
}

#[derive(Clone, Debug)]
pub struct ShotArrivalPlanOutput {
    pub outcome_code: u8,
    pub in_box: bool,
    pub save_prob: f64,
    pub raw_xg: f64,
    pub rounded_xg: f64,
    pub psxg_delta: f64,
    pub shot_log: ShotLogEntryOutput,
    pub pending_event_text: String,
    pub pause_ms: i32,
    pub trace_event: String,
}

#[derive(Clone, Debug)]
pub struct OutOfBoundsPlanInput {
    pub boundary: PitchBoundaryKind,
    pub boundary_point: (f64, f64),
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub possession_team_home: bool,
    pub flight_type_code: u8,
    pub origin: (f64, f64),
    pub attacking_right: bool,
    pub total_xg: f64,
    pub logged_xg_sum: f64,
    pub goal_kick_restart_ticks: i32,
    pub throw_in_restart_ticks: i32,
}

#[derive(Clone, Debug)]
pub struct OutOfBoundsPlanOutput {
    pub reason: String,
    pub restart_team_home: bool,
    pub restart_ticks: i32,
    pub has_shot_log: bool,
    pub shot_log: ShotLogEntryOutput,
}

#[derive(Clone, Copy, Debug)]
pub struct PassPhaseOutcomeInput {
    pub pass_accuracy_error: bool,
    pub interception_present: bool,
    pub intercepted: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassPhaseOutcomeOutput {
    pub outcome_code: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct PassTraceInput {
    pub target: (f64, f64),
    pub intended_receiver_pos: Option<(f64, f64)>,
    pub is_long: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassTraceOutput {
    pub pass_type_code: u8,
    pub target_kind_code: u8,
}

#[derive(Clone, Debug)]
pub struct CarryPhasePlanInput<'a> {
    pub transition: Option<crate::execution_transition::CarrySegmentTransition>,
    pub holder_pos: (f64, f64),
    pub target: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub dribbling: f64,
    pub consecutive_carries: i32,
    pub control_readiness: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub carrier_speed: f64,
    pub carry_error_divisor: f64,
    pub opponents: &'a [ExecutionOpponent],
    pub defender_responses: &'a [DefenderActionInput],
    pub error_roll: f64,
    pub containment_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Debug)]
pub struct CarryPhasePlanOutput {
    pub transition: crate::execution_transition::CarrySegmentTransition,
    pub carry_speed: f64,
    pub carry_difficulty: f64,
    pub new_pos: (f64, f64),
    pub boundary_crossing: Option<crate::physics::PitchBoundaryCrossing>,
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
    pub contact_load: f64,
    pub error_chance: f64,
    pub is_error: bool,
    pub loose_pos: (f64, f64),
    pub constrained_control: bool,
    pub constrained_control_probability: f64,
    pub constrained_control_position: (f64, f64),
    pub randoms_used: usize,
}

#[derive(Clone, Debug)]
pub struct PassPhasePlanInput {
    pub transition: Option<crate::execution_transition::PassActionTransition>,
    pub passer_pos: (f64, f64),
    pub ideal_target: (f64, f64),
    pub passing: f64,
    pub is_long: bool,
    pub lane_risk: f64,
    pub retention_probability: f64,
    pub technical_probability: f64,
    pub technical_roll: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub ball_pass_speed: f64,
    pub ball_long_pass_speed: f64,
    pub tick_duration: f64,
    pub random_1: f64,
    pub random_2: f64,
    pub intended_receiver_pos: Option<(f64, f64)>,
}

#[derive(Clone, Debug)]
pub struct PassPhasePlanOutput {
    pub transition: crate::execution_transition::PassActionTransition,
    pub target: (f64, f64),
    pub speed: f64,
    pub ticks_needed: i32,
    pub flight_type_code: u8,
    pub pass_type_code: u8,
    pub target_kind_code: u8,
    pub flight_from_yx: (f64, f64),
    pub flight_to_yx: (f64, f64),
    pub retention_probability: f64,
    pub technical_probability: f64,
    pub technical_roll: f64,
    pub delivery_miss: bool,
    pub randoms_used: usize,
}

#[derive(Clone, Debug)]
pub struct ShotPhasePlanInput<'a> {
    pub shooter_name: &'a str,
    pub shooter_pos: (f64, f64),
    pub explicit_xg: Option<f64>,
    pub on_target_prob: f64,
    pub goal_reward_constant: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub goal_width: f64,
    pub ball_shot_speed: f64,
    pub tick_duration: f64,
    pub random_1: f64,
    pub random_2: f64,
    pub random_3: f64,
}

#[derive(Clone, Debug)]
pub struct ShotPhasePlanOutput {
    pub shot_xg: f64,
    pub on_target: bool,
    pub target: (f64, f64),
    pub speed: f64,
    pub distance: f64,
    pub ticks_needed: i32,
    pub flight_type_code: u8,
    pub flight_from_yx: (f64, f64),
    pub flight_to_yx: (f64, f64),
    pub pending_event_text: String,
    pub randoms_used: usize,
}

#[derive(Clone, Debug)]
pub struct ClearPhasePlanInput {
    pub clearer_pos: (f64, f64),
    pub target: (f64, f64),
    pub ball_long_pass_speed: f64,
    pub tick_duration: f64,
}

#[derive(Clone, Debug)]
pub struct ClearPhasePlanOutput {
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub speed: f64,
    pub ticks_needed: i32,
    pub flight_type_code: u8,
}

#[derive(Clone, Debug)]
pub struct HoldPhasePlanInput<'a> {
    pub transition: Option<crate::execution_transition::ControlActionTransition>,
    pub holder_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub dribbling: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub carry_error_divisor: f64,
    pub opponents: &'a [ExecutionOpponent],
    pub opportunity_target: Option<(f64, f64)>,
    pub error_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Debug)]
pub struct HoldPhasePlanOutput {
    pub transition: crate::execution_transition::ControlActionTransition,
    pub new_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
    pub pressure: f64,
    pub nearest_dist: f64,
    pub trace_pressure: f64,
    pub trace_nearest_dist: Option<f64>,
    pub error_chance: f64,
    pub is_error: bool,
    pub loose_pos: (f64, f64),
    pub randoms_used: usize,
}

#[derive(Clone, Debug)]
pub struct PassReceivePlanInput {
    pub receiver_pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub receiver_iq: f64,
    pub receiver_offside_flagged: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub first_touch_error_divisor: f64,
    pub error_roll: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Debug)]
pub struct PassReceivePlanOutput {
    pub outcome_code: u8,
    pub contact_pos: (f64, f64),
    pub loose_pos: (f64, f64),
    pub contact_offset: f64,
    pub contact_kind_code: u8,
    pub first_touch_error_chance: f64,
    pub first_touch_error: bool,
    pub randoms_used: usize,
}

#[derive(Clone, Debug)]
pub struct PassArrivalPlanInput<'a> {
    pub target_pos: (f64, f64),
    pub flight_origin: (f64, f64),
    pub flight_speed: f64,
    pub flight_ticks_total: i32,
    pub contest_radius: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub target_occupation_weight: f64,
    pub receivers: &'a [crate::arrival::ArrivalPlayerInput],
    pub opponents: &'a [crate::arrival::ArrivalPlayerInput],
}

#[derive(Clone, Debug)]
pub struct PassArrivalPlanOutput {
    pub outcome_code: u8,
    pub receiver_index: Option<usize>,
    pub opponent_index: Option<usize>,
    pub contact_pos: (f64, f64),
    pub contact_tick: i32,
    pub loose_velocity: (f64, f64),
    pub receiver_score: f64,
    pub receiver_control: f64,
    pub opponent_score: f64,
    pub opponent_control: f64,
    pub loose_control: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassControlTransitionInput {
    pub retained_possession: bool,
    pub receiver_index: Option<usize>,
    pub opponent_index: Option<usize>,
    pub opponent_control: f64,
    pub loose_control: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassControlTransitionOutput {
    pub outcome_code: u8,
    pub receiver_index: Option<usize>,
    pub opponent_index: Option<usize>,
}

#[derive(Clone, Debug)]
pub struct ClearanceArrivalPlanInput<'a> {
    pub target_pos: (f64, f64),
    pub passer_team_home: bool,
    pub home_players: &'a [crate::arrival::ClearancePlayerInput],
    pub away_players: &'a [crate::arrival::ClearancePlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct ClearanceArrivalPlanOutput {
    pub winner_code: u8,
    pub player_index: Option<usize>,
    pub passer_completed: bool,
    pub home_distance: f64,
    pub away_distance: f64,
}

#[derive(Clone, Debug)]
pub struct ContestedTickPlanInput<'a> {
    pub position: (f64, f64),
    pub loose_velocity: (f64, f64),
    pub contested_ticks: i32,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub contest_radius: f64,
    pub home_players: &'a [ContestedOwnerPlayerInput],
    pub away_players: &'a [ContestedOwnerPlayerInput],
}

#[derive(Clone, Debug)]
pub struct ContestedTickPlanOutput {
    pub position: (f64, f64),
    pub loose_velocity: (f64, f64),
    pub contested_ticks: i32,
    pub winner_code: Option<u8>,
    pub player_index: Option<usize>,
    pub distance: f64,
    pub immediate_win: bool,
    pub forced_win: bool,
}

#[derive(Clone, Debug)]
pub struct DuelPhasePlanInput<'a> {
    pub holder_pos: (f64, f64),
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacker_dribbling: f64,
    pub defender_tackling: f64,
    pub defender_defence: f64,
    pub holder_action: &'a str,
    pub defender_action: &'a str,
    pub contact_quality: f64,
    pub attacker_uniform: f64,
    pub defender_uniform: f64,
    pub loose_x_roll: f64,
    pub loose_y_roll: f64,
}

#[derive(Clone, Debug)]
pub struct DuelPhasePlanOutput {
    pub outcome_code: u8,
    pub loose_pos: (f64, f64),
    pub randoms_used: usize,
}

pub fn carry_phase_plan(input: &CarryPhasePlanInput<'_>) -> CarryPhasePlanOutput {
    let carry = execute_carry(&CarryExecutionInput {
        transition: input.transition,
        holder_pos: input.holder_pos,
        target: input.target,
        velocity: input.velocity,
        speed_ability: input.speed_ability,
        dribbling: input.dribbling,
        consecutive_carries: input.consecutive_carries,
        control_readiness: input.control_readiness,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        carrier_speed: input.carrier_speed,
        carry_error_divisor: input.carry_error_divisor,
        opponents: input.opponents,
        defender_responses: input.defender_responses,
        error_roll: input.error_roll,
        containment_roll: input.containment_roll,
        loose_x_roll: input.loose_x_roll,
        loose_y_roll: input.loose_y_roll,
    });
    CarryPhasePlanOutput {
        transition: carry.transition,
        carry_speed: carry.carry_speed,
        carry_difficulty: carry.carry_difficulty,
        new_pos: carry.new_pos,
        boundary_crossing: carry.boundary_crossing,
        velocity: carry.velocity,
        facing_direction: carry.facing_direction,
        distance_covered: carry.distance_covered,
        contact_load: carry.contact_load,
        error_chance: carry.error_chance,
        is_error: carry.is_error,
        loose_pos: carry.loose_pos,
        constrained_control: carry.constrained_control,
        constrained_control_probability: carry.constrained_control_probability,
        constrained_control_position: carry.constrained_control_position,
        randoms_used: 2 + if carry.is_error { 2 } else { 0 },
    }
}

pub fn duel_phase_plan(input: &DuelPhasePlanInput<'_>) -> DuelPhasePlanOutput {
    let outcome = resolve_duel(&DuelResolveInput {
        attacker_dribbling: input.attacker_dribbling,
        defender_tackling: input.defender_tackling,
        defender_defence: input.defender_defence,
        holder_action: input.holder_action,
        defender_action: input.defender_action,
        contact_quality: input.contact_quality,
        attacker_uniform: input.attacker_uniform,
        defender_uniform: input.defender_uniform,
    });
    let outcome_code = match outcome {
        "attacker_wins" => 0,
        "defender_wins" => 1,
        _ => 2,
    };
    let loose_pos = pitch_clamp(
        (
            input.holder_pos.0 + (-3.0 + 6.0 * input.loose_x_roll),
            input.holder_pos.1 + (-2.0 + 4.0 * input.loose_y_roll),
        ),
        input.pitch_length,
        input.pitch_width,
    );
    DuelPhasePlanOutput {
        outcome_code,
        loose_pos,
        randoms_used: 2 + if outcome_code == 2 { 2 } else { 0 },
    }
}

pub fn pass_receive_plan(input: &PassReceivePlanInput) -> PassReceivePlanOutput {
    let first_touch = resolve_first_touch(&FirstTouchInput {
        target_pos: input.target_pos,
        iq: input.receiver_iq,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        first_touch_error_divisor: input.first_touch_error_divisor,
        error_roll: input.error_roll,
        loose_x_roll: input.loose_x_roll,
        loose_y_roll: input.loose_y_roll,
    });
    let contact_pos = input.receiver_pos;
    let contact_offset = crate::physics::distance(contact_pos, input.target_pos);
    let contact_kind_code = if contact_offset > 4.0 { 1 } else { 0 };
    let outcome_code = if input.receiver_offside_flagged { 2 } else { 0 };
    PassReceivePlanOutput {
        outcome_code,
        contact_pos,
        loose_pos: first_touch.loose_pos,
        contact_offset,
        contact_kind_code,
        first_touch_error_chance: first_touch.error_chance,
        first_touch_error: first_touch.is_error,
        randoms_used: 1 + if first_touch.is_error { 2 } else { 0 },
    }
}

pub fn pass_arrival_plan(input: &PassArrivalPlanInput<'_>) -> PassArrivalPlanOutput {
    let arrival = crate::arrival::resolve_pass_arrival(&crate::arrival::PassArrivalInput {
        flight_origin: input.flight_origin,
        target_pos: input.target_pos,
        flight_ticks_total: input.flight_ticks_total,
        passer_team_is_receiver_team: true,
        contest_radius: input.contest_radius,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        target_occupation_weight: input.target_occupation_weight,
        receivers: input.receivers,
        opponents: input.opponents,
    });
    PassArrivalPlanOutput {
        outcome_code: arrival.winner_code,
        receiver_index: arrival.receiver_index,
        opponent_index: arrival.opponent_index,
        contact_pos: arrival.contact_pos,
        contact_tick: arrival.contact_tick,
        loose_velocity: crate::physics::residual_ball_velocity(
            input.flight_origin,
            arrival.contact_pos,
            input.flight_speed,
            0.26,
        ),
        receiver_score: arrival.receiver_score,
        receiver_control: arrival.receiver_control,
        opponent_score: arrival.opponent_score,
        opponent_control: arrival.opponent_control,
        loose_control: arrival.loose_control,
    }
}

pub fn pass_control_transition(input: &PassControlTransitionInput) -> PassControlTransitionOutput {
    if input.retained_possession {
        if let Some(receiver_index) = input.receiver_index {
            return PassControlTransitionOutput {
                outcome_code: 0,
                receiver_index: Some(receiver_index),
                opponent_index: None,
            };
        }
    }

    if input.opponent_index.is_some() && input.opponent_control > input.loose_control {
        PassControlTransitionOutput {
            outcome_code: 1,
            receiver_index: None,
            opponent_index: input.opponent_index,
        }
    } else {
        PassControlTransitionOutput {
            outcome_code: 2,
            receiver_index: None,
            opponent_index: None,
        }
    }
}

pub fn clearance_arrival_plan(input: &ClearanceArrivalPlanInput<'_>) -> ClearanceArrivalPlanOutput {
    let arrival =
        crate::arrival::resolve_clearance_arrival(&crate::arrival::ClearanceArrivalInput {
            target_pos: input.target_pos,
            home_players: input.home_players,
            away_players: input.away_players,
        });
    ClearanceArrivalPlanOutput {
        winner_code: arrival.winner_code,
        player_index: arrival.player_index,
        passer_completed: (arrival.winner_code == 0 && input.passer_team_home)
            || (arrival.winner_code == 1 && !input.passer_team_home),
        home_distance: arrival.home_distance,
        away_distance: arrival.away_distance,
    }
}

pub fn contested_tick_plan(input: &ContestedTickPlanInput<'_>) -> ContestedTickPlanOutput {
    let tick = tick_contested_ball(&ContestedTickInput {
        position: input.position,
        loose_velocity: input.loose_velocity,
        contested_ticks: input.contested_ticks,
    });
    let ball_pos = pitch_clamp(tick.position, input.pitch_length, input.pitch_width);
    let owner = resolve_contested_owner(&ContestedOwnerInput {
        ball_pos,
        contest_radius: input.contest_radius,
        contested_ticks: tick.contested_ticks,
        home_players: input.home_players,
        away_players: input.away_players,
    });
    ContestedTickPlanOutput {
        position: ball_pos,
        loose_velocity: tick.loose_velocity,
        contested_ticks: tick.contested_ticks,
        winner_code: owner.winner_code,
        player_index: owner.player_index,
        distance: owner.distance,
        immediate_win: owner.immediate_win,
        forced_win: owner.forced_win,
    }
}

pub fn pass_phase_outcome(input: &PassPhaseOutcomeInput) -> PassPhaseOutcomeOutput {
    let outcome_code = if input.pass_accuracy_error {
        1
    } else if input.interception_present && input.intercepted {
        2
    } else {
        0
    };
    PassPhaseOutcomeOutput { outcome_code }
}

pub fn pass_trace_payload(input: &PassTraceInput) -> PassTraceOutput {
    let target_kind_code = if let Some(receiver_pos) = input.intended_receiver_pos {
        if crate::physics::distance(input.target, receiver_pos) > 4.0 {
            1
        } else {
            0
        }
    } else {
        0
    };
    PassTraceOutput {
        pass_type_code: if input.is_long { 1 } else { 0 },
        target_kind_code,
    }
}

pub fn pass_phase_plan(input: &PassPhasePlanInput) -> PassPhasePlanOutput {
    let pass = execute_pass(&PassExecutionInput {
        transition: input.transition,
        passer_pos: input.passer_pos,
        ideal_target: input.ideal_target,
        passing: input.passing,
        is_long: input.is_long,
        lane_risk: input.lane_risk,
        retention_probability: input.retention_probability,
        technical_probability: input.technical_probability,
        technical_roll: input.technical_roll,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        ball_pass_speed: input.ball_pass_speed,
        ball_long_pass_speed: input.ball_long_pass_speed,
        tick_duration: input.tick_duration,
        random_1: input.random_1,
        random_2: input.random_2,
    });
    let trace = pass_trace_payload(&PassTraceInput {
        target: pass.target,
        intended_receiver_pos: input.intended_receiver_pos,
        is_long: input.is_long,
    });
    let flight = build_ball_flight_frame(&BallFlightFrameInput {
        from_pos: input.passer_pos,
        to_pos: pass.target,
        flight_type: "pass",
        on_target: false,
    });
    PassPhasePlanOutput {
        transition: pass.transition,
        target: pass.target,
        speed: pass.speed,
        ticks_needed: pass.ticks_needed,
        flight_type_code: pass.flight_type_code,
        pass_type_code: trace.pass_type_code,
        target_kind_code: trace.target_kind_code,
        flight_from_yx: flight.from_yx,
        flight_to_yx: flight.to_yx,
        retention_probability: pass.retention_probability,
        technical_probability: pass.technical_probability,
        technical_roll: pass.technical_roll,
        delivery_miss: pass.delivery_miss,
        randoms_used: pass.randoms_used,
    }
}

pub fn shot_phase_plan(input: &ShotPhasePlanInput<'_>) -> ShotPhasePlanOutput {
    let xg = shot_xg_value(&ShotXgInput {
        explicit_xg: input.explicit_xg,
        on_target_prob: input.on_target_prob,
        goal_reward_constant: input.goal_reward_constant,
    });
    let shot = execute_shot(&ShotExecutionInput {
        shooter_pos: input.shooter_pos,
        on_target_prob: input.on_target_prob,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        goal_width: input.goal_width,
        ball_shot_speed: input.ball_shot_speed,
        tick_duration: input.tick_duration,
        random_1: input.random_1,
        random_2: input.random_2,
        random_3: input.random_3,
    });
    let flight = build_ball_flight_frame(&BallFlightFrameInput {
        from_pos: input.shooter_pos,
        to_pos: shot.target,
        flight_type: "shot",
        on_target: shot.on_target,
    });
    ShotPhasePlanOutput {
        shot_xg: xg.xg,
        on_target: shot.on_target,
        target: shot.target,
        speed: shot.speed,
        distance: shot.distance,
        ticks_needed: shot.ticks_needed,
        flight_type_code: shot.flight_type_code,
        flight_from_yx: flight.from_yx,
        flight_to_yx: flight.to_yx,
        pending_event_text: format!(
            "{} {} shoots!",
            if shot.on_target {
                "SHOT ON TARGET"
            } else {
                "SHOT"
            },
            input.shooter_name
        ),
        randoms_used: shot.randoms_used,
    }
}

pub fn clear_phase_plan(input: &ClearPhasePlanInput) -> ClearPhasePlanOutput {
    let clear = execute_clear(&ClearExecutionInput {
        clearer_pos: input.clearer_pos,
        target: input.target,
        ball_long_pass_speed: input.ball_long_pass_speed,
        tick_duration: input.tick_duration,
    });
    ClearPhasePlanOutput {
        origin: clear.origin,
        target: clear.target,
        speed: clear.speed,
        ticks_needed: clear.ticks_needed,
        flight_type_code: clear.flight_type_code,
    }
}

pub fn hold_phase_plan(input: &HoldPhasePlanInput<'_>) -> HoldPhasePlanOutput {
    let hold = execute_hold(&HoldExecutionInput {
        transition: input.transition,
        holder_pos: input.holder_pos,
        velocity: input.velocity,
        speed_ability: input.speed_ability,
        dribbling: input.dribbling,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        carry_error_divisor: input.carry_error_divisor,
        opponents: input.opponents,
        opportunity_target: input.opportunity_target,
        error_roll: input.error_roll,
        loose_x_roll: input.loose_x_roll,
        loose_y_roll: input.loose_y_roll,
    });
    HoldPhasePlanOutput {
        transition: hold.transition,
        new_pos: hold.new_pos,
        velocity: hold.velocity,
        facing_direction: hold.facing_direction,
        distance_covered: hold.distance_covered,
        pressure: hold.pressure,
        nearest_dist: hold.nearest_dist,
        trace_pressure: hold.trace_pressure,
        trace_nearest_dist: hold.trace_nearest_dist,
        error_chance: hold.error_chance,
        is_error: hold.is_error,
        loose_pos: hold.loose_pos,
        randoms_used: hold.randoms_used,
    }
}

pub fn shot_xg_value(input: &ShotXgInput) -> ShotXgOutput {
    let raw = input
        .explicit_xg
        .unwrap_or(input.on_target_prob * input.goal_reward_constant * 0.5);
    ShotXgOutput {
        xg: raw.clamp(0.01, 0.95),
    }
}

pub fn shot_log_xg(input: &ShotLogXgInput) -> ShotLogXgOutput {
    let mut raw = input.total_xg - input.logged_xg_sum;
    if input.clamp_nonnegative {
        raw = raw.max(0.0);
    }
    ShotLogXgOutput {
        raw_xg: raw,
        rounded_xg: (raw * 100.0).round() / 100.0,
    }
}

pub fn shot_arrival_event(input: &ShotArrivalEventInput<'_>) -> ShotArrivalEventOutput {
    match input.outcome {
        "off_target" => ShotArrivalEventOutput {
            pending_event_text: format!("{}'s shot goes wide!", input.shooter_name),
            pause_ms: 0,
            trace_event: "off_target".to_string(),
        },
        "saved" => ShotArrivalEventOutput {
            pending_event_text: format!(
                "{} saves {}'s shot!",
                input.keeper_name, input.shooter_name
            ),
            pause_ms: 1000,
            trace_event: "save".to_string(),
        },
        _ => ShotArrivalEventOutput {
            pending_event_text: String::new(),
            pause_ms: 0,
            trace_event: input.outcome.to_string(),
        },
    }
}

pub fn shot_log_entry(input: &ShotLogEntryInput<'_>) -> ShotLogEntryOutput {
    ShotLogEntryOutput {
        x: round_one(input.origin.0),
        y: round_one(input.origin.1),
        xg: input.xg,
        in_box: input.in_box,
        outcome: input.outcome.to_string(),
        target_x: input.target.map(|target| round_one(target.0)),
        target_y: input.target.map(|target| round_one(target.1)),
    }
}

pub fn shot_arrival_plan(input: &ShotArrivalPlanInput<'_>) -> ShotArrivalPlanOutput {
    let arrival = crate::arrival::resolve_shot_arrival(&crate::arrival::ShotArrivalInput {
        shot_origin: input.shot_origin,
        shot_target: input.shot_target,
        attacking_right: input.attacking_right,
        on_target: input.on_target,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        gk_pos: input.gk_pos,
        gk_attributes: input.gk_attributes,
        save_roll: input.save_roll,
    });
    let outcome = match arrival.outcome_code {
        1 => "saved",
        2 => "goal",
        _ => "off_target",
    };
    let xg = shot_log_xg(&ShotLogXgInput {
        total_xg: input.total_xg,
        logged_xg_sum: input.logged_xg_sum,
        clamp_nonnegative: false,
    });
    let event = shot_arrival_event(&ShotArrivalEventInput {
        shooter_name: input.shooter_name,
        keeper_name: input.keeper_name,
        outcome,
    });
    let target = if input.on_target {
        Some(input.shot_target)
    } else {
        None
    };
    let shot_log = shot_log_entry(&ShotLogEntryInput {
        origin: input.shot_origin,
        target,
        xg: xg.rounded_xg,
        in_box: arrival.in_box,
        outcome,
    });
    ShotArrivalPlanOutput {
        outcome_code: arrival.outcome_code,
        in_box: arrival.in_box,
        save_prob: arrival.save_prob,
        raw_xg: xg.raw_xg,
        rounded_xg: xg.rounded_xg,
        psxg_delta: if input.on_target {
            xg.raw_xg.max(0.0)
        } else {
            0.0
        },
        shot_log,
        pending_event_text: event.pending_event_text,
        pause_ms: event.pause_ms,
        trace_event: event.trace_event,
    }
}

pub fn out_of_bounds_plan(input: &OutOfBoundsPlanInput) -> OutOfBoundsPlanOutput {
    let (reason, restart_team_home) = crate::physics::out_of_bounds_restart(
        input.boundary,
        input.boundary_point,
        input.pitch_length,
        input.possession_team_home,
        input.attacking_right,
    );
    let restart_ticks = if reason == "goal_kick" {
        input.goal_kick_restart_ticks
    } else {
        input.throw_in_restart_ticks
    };
    let has_shot_log = input.flight_type_code == 3;
    let shot_log = if has_shot_log {
        let xg = shot_log_xg(&ShotLogXgInput {
            total_xg: input.total_xg,
            logged_xg_sum: input.logged_xg_sum,
            clamp_nonnegative: true,
        });
        shot_log_entry(&ShotLogEntryInput {
            origin: input.origin,
            target: None,
            xg: xg.rounded_xg,
            in_box: crate::physics::is_attacking_box_pos(
                input.origin,
                input.attacking_right,
                input.pitch_length,
                input.pitch_width,
            ),
            outcome: "off_target",
        })
    } else {
        shot_log_entry(&ShotLogEntryInput {
            origin: input.origin,
            target: None,
            xg: 0.0,
            in_box: false,
            outcome: "",
        })
    };
    OutOfBoundsPlanOutput {
        reason: reason.to_string(),
        restart_team_home,
        restart_ticks,
        has_shot_log,
        shot_log,
    }
}

pub fn key_pass_for_shot(input: &KeyPassInput) -> KeyPassOutput {
    let has_key_pass = input.last_passer_team_home == Some(input.shooter_team_home)
        && input.last_passer_idx >= 0
        && input.last_passer_idx < input.team_size
        && input.last_passer_idx != input.shooter_idx;
    KeyPassOutput {
        has_key_pass,
        key_passer_idx: if has_key_pass {
            input.last_passer_idx
        } else {
            -1
        },
    }
}

pub fn build_goal_event(input: &GoalEventInput<'_>) -> GoalEventOutput {
    let has_assist = input.last_passer_team_home == Some(input.scoring_team_home)
        && input.last_passer_idx != input.scorer_idx
        && input.last_passer_idx >= 0
        && input.last_passer_idx < input.scoring_team_size;
    let home_score = input.home_score + if input.scoring_team_home { 1 } else { 0 };
    let away_score = input.away_score + if input.scoring_team_home { 0 } else { 1 };
    let assist_text = if has_assist {
        format!(" (assist: {})", input.assister_name)
    } else {
        String::new()
    };
    GoalEventOutput {
        home_score,
        away_score,
        has_assist,
        assister_idx: if has_assist {
            input.last_passer_idx
        } else {
            -1
        },
        assister_name: if has_assist {
            input.assister_name.to_string()
        } else {
            String::new()
        },
        assister_color: if has_assist {
            input.assister_color.to_string()
        } else {
            String::new()
        },
        event_text: format!(
            "GOAL! {} scores!{} [{}-{}]",
            input.scorer_name, assist_text, home_score, away_score
        ),
    }
}

pub fn score_goal_plan(input: &ScoreGoalPlanInput<'_>) -> ScoreGoalPlanOutput {
    let event = build_goal_event(&GoalEventInput {
        scorer_name: input.scorer_name,
        scoring_team_home: input.scoring_team_home,
        home_score: input.home_score,
        away_score: input.away_score,
        last_passer_team_home: input.last_passer_team_home,
        last_passer_idx: input.last_passer_idx,
        scorer_idx: input.scorer_idx,
        scoring_team_size: input.scoring_team_size,
        assister_name: input.assister_name,
        assister_color: input.assister_color,
    });
    let total_seconds = input.tick as f64 * input.tick_duration;
    ScoreGoalPlanOutput {
        home_score: event.home_score,
        away_score: event.away_score,
        has_assist: event.has_assist,
        assister_idx: event.assister_idx,
        assister_name: event.assister_name,
        assister_color: event.assister_color,
        minute: (total_seconds / 60.0).floor().min(90.0) as i32,
        event_text: event.event_text,
        pause_ms: 3000,
        restart_team_home: input.conceding_team_home,
        restart_ticks: 3,
    }
}

pub fn give_ball_plan(input: &GiveBallPlanInput) -> GiveBallPlanOutput {
    let has_previous_holder =
        input.previous_holder_team_code.is_some() && input.previous_holder_idx >= 0;
    let clear_offside_flags = input
        .previous_holder_team_code
        .map(|team_code| team_code != input.new_holder_team_code)
        .unwrap_or(false);
    GiveBallPlanOutput {
        clear_previous_holder: has_previous_holder,
        previous_holder_team_code: input.previous_holder_team_code,
        previous_holder_idx: input.previous_holder_idx,
        clear_offside_flags,
        clear_team_goals: input.previous_holder_team_code != Some(input.new_holder_team_code),
        new_holder_idx: input.new_holder_idx,
        new_holder_team_code: input.new_holder_team_code,
        ball_pos: input.new_holder_pos,
        last_receive_origin: input.receive_origin.unwrap_or(input.new_holder_pos),
    }
}

fn movement_intent_base(intent: &str) -> f64 {
    match intent {
        "idle" => 0.08,
        "support" => 0.36,
        "attack_run" => 0.56,
        "recover_shape" => 0.42,
        "defend_shape" => 0.30,
        "press" => 0.58,
        "contest" => 0.78,
        "mark" => 0.32,
        "block_lane" => 0.30,
        _ => 0.36,
    }
}

pub fn player_move_speed(input: &PlayerMoveSpeedInput<'_>) -> PlayerMoveSpeedOutput {
    let max_speed = crate::physics::player_speed(
        input.speed_ability,
        input.player_max_speed,
        input.player_min_speed,
    );
    let dist_to_target = crate::physics::distance(input.pos, input.target_pos);
    let urgency = 1.0 - (-dist_to_target / 14.0).exp();
    let mut intent_base = movement_intent_base(input.movement_intent);
    if input.state == "pressing" {
        intent_base = intent_base.max(0.58);
    }
    let mut speed = max_speed * (intent_base + (0.28 * urgency));
    if dist_to_target < 1.0 {
        speed *= 0.20;
    }
    PlayerMoveSpeedOutput {
        speed: speed.clamp(0.2, max_speed * 0.92),
    }
}

pub fn player_move_tick(input: &PlayerMoveTickInput<'_>) -> PlayerMoveTickOutput {
    if input.state == "on_ball" || input.state == "stunned" {
        return PlayerMoveTickOutput {
            moved: false,
            pos: input.pos,
            velocity: input.velocity,
            distance_covered: 0.0,
            facing_direction: None,
            desired_speed: 0.0,
        };
    }

    let desired_speed = player_move_speed(&PlayerMoveSpeedInput {
        pos: input.pos,
        target_pos: input.target_pos,
        speed_ability: input.speed_ability,
        movement_intent: input.movement_intent,
        state: input.state,
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
    })
    .speed;

    let movement = crate::physics::advance_player_motion(&crate::physics::PlayerMotionInput {
        pos: input.pos,
        target: input.target_pos,
        velocity: input.velocity,
        speed_ability: input.speed_ability,
        desired_speed,
        acceleration_scale: if matches!(input.movement_intent, "press" | "contest" | "attack_run") {
            1.15
        } else {
            1.0
        },
        player_max_speed: input.player_max_speed,
        player_min_speed: input.player_min_speed,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    });
    PlayerMoveTickOutput {
        moved: movement.distance_covered > 1e-6,
        pos: movement.pos,
        velocity: movement.velocity,
        distance_covered: movement.distance_covered,
        facing_direction: movement.facing_direction,
        desired_speed,
    }
}

pub fn player_set_movement_target(
    input: &PlayerSetMovementTargetInput<'_>,
) -> PlayerSetMovementTargetOutput {
    let target = player_set_movement_target_ref(input);
    PlayerSetMovementTargetOutput {
        target_pos: target.target_pos,
        movement_intent: input
            .requested_intent
            .unwrap_or(input.current_intent)
            .to_string(),
    }
}

pub fn player_set_movement_target_ref<'a>(
    input: &PlayerSetMovementTargetInput<'a>,
) -> PlayerSetMovementTargetRefOutput {
    let movement_intent = input.requested_intent.unwrap_or(input.current_intent);
    if input.current_target == (0.0, 0.0) {
        return PlayerSetMovementTargetRefOutput {
            target_pos: input.requested_target,
        };
    }
    let jump = crate::physics::distance(input.current_target, input.requested_target);
    let mut blend: f64 = if jump < 4.0 {
        0.75
    } else if jump < 14.0 {
        0.45
    } else {
        0.22
    };
    if movement_intent == "attack_run" {
        blend = (blend + 0.54).min(0.92);
    } else if matches!(movement_intent, "press" | "contest") {
        blend = (blend + 0.30).min(0.78);
    } else if matches!(movement_intent, "defend_shape" | "mark" | "block_lane") {
        blend *= 0.85;
    }
    PlayerSetMovementTargetRefOutput {
        target_pos: (
            input.current_target.0 * (1.0 - blend) + input.requested_target.0 * blend,
            input.current_target.1 * (1.0 - blend) + input.requested_target.1 * blend,
        ),
    }
}

pub fn goal_kick_spot(attacking_right: bool, pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        if attacking_right {
            6.0
        } else {
            pitch_length - 6.0
        },
        pitch_width / 2.0,
    )
}

pub fn must_leave_penalty_area_for_goal_kick(
    player_team_is_restart_team: bool,
    player_x: f64,
    restart_attacking_right: bool,
    pitch_length: f64,
) -> bool {
    if player_team_is_restart_team {
        return false;
    }
    if restart_attacking_right {
        player_x < 16.5
    } else {
        player_x > pitch_length - 16.5
    }
}

#[derive(Clone, Copy, Debug)]
pub struct KickoffPlayerInput<'a> {
    pub index: usize,
    pub team_is_restart: bool,
    pub attacking_right: bool,
    pub base_pos: (f64, f64),
    pub current_pos: (f64, f64),
    pub is_goalkeeper: bool,
    pub position: &'a str,
}

#[derive(Clone, Copy, Debug)]
pub struct KickoffShapeInput<'a> {
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub players: &'a [KickoffPlayerInput<'a>],
}

#[derive(Clone, Debug)]
pub struct KickoffShapeOutput {
    pub targets: Vec<(usize, (f64, f64))>,
    pub kicker_index: Option<usize>,
}

#[derive(Clone, Copy, Debug)]
pub struct GoalKickPlayerInput {
    pub index: usize,
    pub team_is_restart: bool,
    pub team_attacking_right: bool,
    pub restart_attacking_right: bool,
    pub base_pos: (f64, f64),
    pub is_goalkeeper: bool,
    pub is_attacker: bool,
    pub is_midfielder: bool,
    pub is_defender: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct GoalKickShapeInput<'a> {
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub players: &'a [GoalKickPlayerInput],
}

#[derive(Clone, Debug)]
pub struct GoalKickShapeOutput {
    pub targets: Vec<(usize, (f64, f64))>,
}

#[derive(Clone, Copy, Debug)]
pub struct RestartPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Debug)]
pub struct RestartPlayInput<'a> {
    pub reason: &'a str,
    pub ball_pos: (f64, f64),
    pub restart_attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub corner_y_roll: f64,
    pub players: &'a [RestartPlayerInput],
}

#[derive(Clone, Debug)]
pub struct RestartPlayOutput {
    pub ball_pos: (f64, f64),
    pub receiver_index: Option<usize>,
    pub set_receiver_pos: bool,
    pub pending_cut: bool,
}

#[derive(Clone, Debug)]
pub struct RestartPlayPlanInput<'a> {
    pub reason: &'a str,
    pub ball_pos: (f64, f64),
    pub restart_attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub corner_y_roll: f64,
    pub players: &'a [RestartPlayerInput],
}

#[derive(Clone, Debug)]
pub struct RestartPlayPlanOutput {
    pub ball_pos: (f64, f64),
    pub receiver_index: Option<usize>,
    pub set_receiver_pos: bool,
    pub pending_cut: bool,
    pub reset_last_passer: bool,
    pub clear_offside_flags: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct RestartShapePlayerInput<'a> {
    pub index: usize,
    pub team_code: u8,
    pub team_is_restart: bool,
    pub team_attacking_right: bool,
    pub restart_attacking_right: bool,
    pub base_pos: (f64, f64),
    pub current_pos: (f64, f64),
    pub is_goalkeeper: bool,
    pub is_attacker: bool,
    pub is_midfielder: bool,
    pub is_defender: bool,
    pub position: &'a str,
}

#[derive(Clone, Debug)]
pub struct RestartShapePlanInput<'a> {
    pub reason: &'a str,
    pub force: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub players: &'a [RestartShapePlayerInput<'a>],
}

#[derive(Clone, Debug)]
pub struct RestartShapePlanPlayerOutput {
    pub team_code: u8,
    pub index: usize,
    pub target: (f64, f64),
    pub snap: bool,
}

#[derive(Clone, Debug)]
pub struct RestartShapePlanOutput {
    pub has_shape: bool,
    pub ball_pos: (f64, f64),
    pub players: Vec<RestartShapePlanPlayerOutput>,
}

#[derive(Clone, Copy, Debug)]
pub struct FlightMovementPlayerInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub is_passer: bool,
    pub is_stunned: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct FlightMovementPlanInput<'a> {
    pub target_pos: (f64, f64),
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub contested_race_radius: f64,
    pub attack_players: &'a [FlightMovementPlayerInput],
    pub defense_players: &'a [FlightMovementPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct FlightMovementPlanPlayerOutput {
    pub team_code: u8,
    pub index: usize,
    pub action_code: u8,
    pub target: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct FlightMovementPlanOutput {
    pub players: Vec<FlightMovementPlanPlayerOutput>,
}

#[derive(Clone, Copy, Debug)]
pub struct DefensivePressureAdjustDefenderInput<'a> {
    pub index: usize,
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub movement_intent: &'a str,
}

#[derive(Clone, Debug)]
pub struct DefensivePressureAdjustInput<'a> {
    pub holder_pos: (f64, f64),
    pub holder_consecutive_carries: i32,
    pub holder_team_attacking_right: bool,
    pub opp_team_attacking_right: bool,
    pub holder_action_type: &'a str,
    pub ball_is_held_by_holder: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub tackle_range: f64,
    pub press_radius: f64,
    pub defenders: &'a [DefensivePressureAdjustDefenderInput<'a>],
}

#[derive(Clone, Copy, Debug)]
pub struct DefensivePressureAdjustOutput {
    pub index: usize,
    pub target_pos: (f64, f64),
    pub movement_intent_code: u8,
}

#[derive(Clone, Debug)]
pub struct DefensivePressureAdjustPlanOutput {
    pub targets: Vec<DefensivePressureAdjustOutput>,
}

#[derive(Clone, Debug)]
pub struct DefenseZoneAttackerInput {
    pub pos: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct DefenseZoneHelperInput<'a> {
    pub defender_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attackers: &'a [DefenseZoneAttackerInput],
}

#[derive(Clone, Debug)]
pub struct DefenseZoneHelperOutput {
    pub score: f64,
    pub target: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct TackleScoreInput {
    pub tackling: f64,
    pub dribbling: f64,
    pub dist_to_ball: f64,
    pub tackle_range: f64,
}

#[derive(Clone, Debug)]
pub struct TackleScoreOutput {
    pub score: f64,
    pub success_rate: f64,
}

#[derive(Clone, Debug)]
pub struct PassControlInput {
    pub score: f64,
    pub contest_radius: f64,
}

#[derive(Clone, Debug)]
pub struct PassControlOutput {
    pub control: f64,
}

#[derive(Clone, Debug)]
pub struct PassLooseControlInput {
    pub teammate_control: f64,
    pub opponent_control: f64,
}

#[derive(Clone, Debug)]
pub struct PassLooseControlOutput {
    pub control: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamShapePlayerInput {
    pub index: usize,
    pub base_pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamShapeOpponentInput {
    pub pos: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Debug)]
pub struct TeamShapePlanInput<'a> {
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub phase: &'a str,
    pub plan_signals: TeamPlanSignals,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub players: &'a [TeamShapePlayerInput],
    pub opponents: &'a [TeamShapeOpponentInput],
}

#[derive(Clone, Copy, Debug)]
pub struct TeamShapePlayerOutput {
    pub index: usize,
    pub tactical_anchor: (f64, f64),
}

#[derive(Clone, Debug)]
pub struct TeamShapePlanOutput {
    pub anchors: Vec<TeamShapePlayerOutput>,
}

#[derive(Clone, Debug)]
pub struct TeamPhaseUpdateInput {
    pub has_possession: bool,
    pub ball_contested: bool,
    pub had_possession_last_tick: bool,
    pub ticks_since_possession_change: i32,
    pub transition_ticks: i32,
}

#[derive(Clone, Debug)]
pub struct TeamPhaseUpdateOutput {
    pub phase_code: u8,
    pub ticks_since_possession_change: i32,
    pub had_possession_last_tick: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct BallFlightFrameInput<'a> {
    pub from_pos: (f64, f64),
    pub to_pos: (f64, f64),
    pub flight_type: &'a str,
    pub on_target: bool,
}

#[derive(Clone, Debug)]
pub struct BallFlightFrameOutput {
    pub from_yx: (f64, f64),
    pub to_yx: (f64, f64),
    pub flight_type: String,
    pub on_target: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct FlightTickInput {
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub ticks_elapsed: i32,
    pub ticks_total: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct FlightTickOutput {
    pub position: (f64, f64),
    pub ticks_elapsed: i32,
    pub complete: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PassStatInput {
    pub origin: (f64, f64),
    pub target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassStatOutput {
    pub crosses_attempted: i32,
    pub crosses_completed: i32,
    pub progressive_passes: i32,
    pub long_passes: i32,
    pub completed_long_passes: i32,
    pub passes_into_final_third: i32,
    pub passes_into_box: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct CarryStatInput {
    pub old_pos: (f64, f64),
    pub new_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct CarryStatOutput {
    pub progressive_carries: i32,
    pub carries_into_final_third: i32,
    pub carries_into_box: i32,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

fn is_forward_position(position: &str) -> bool {
    matches!(
        position,
        "ST" | "CF" | "LW" | "RW" | "LF" | "RF" | "LS" | "RS"
    )
}

fn round_one(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

pub fn build_ball_flight_frame(input: &BallFlightFrameInput<'_>) -> BallFlightFrameOutput {
    BallFlightFrameOutput {
        from_yx: (round_one(input.from_pos.1), round_one(input.from_pos.0)),
        to_yx: (round_one(input.to_pos.1), round_one(input.to_pos.0)),
        flight_type: input.flight_type.to_string(),
        on_target: input.on_target,
    }
}

pub fn tick_ball_flight(input: &FlightTickInput) -> FlightTickOutput {
    let ticks_elapsed = input.ticks_elapsed + 1;
    let progress = if input.ticks_total <= 0 {
        1.0
    } else {
        (ticks_elapsed as f64 / input.ticks_total as f64).min(1.0)
    };
    FlightTickOutput {
        position: (
            input.origin.0 + (input.target.0 - input.origin.0) * progress,
            input.origin.1 + (input.target.1 - input.origin.1) * progress,
        ),
        ticks_elapsed,
        complete: ticks_elapsed >= input.ticks_total,
    }
}

pub fn kickoff_shape_targets(input: &KickoffShapeInput<'_>) -> KickoffShapeOutput {
    let half_x = input.pitch_length / 2.0;
    let center = (half_x, input.pitch_width / 2.0);
    let mut targets = Vec::with_capacity(input.players.len());
    let mut restart_forward: Option<(usize, f64)> = None;
    let mut restart_closest: Option<(usize, f64)> = None;

    for player in input.players {
        let progress = if player.attacking_right {
            player.base_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - player.base_pos.0) / input.pitch_length
        };
        let compressed_progress = progress * 0.48;
        let x = if player.attacking_right {
            (compressed_progress * input.pitch_length).clamp(0.5, half_x - 1.0)
        } else {
            (input.pitch_length - compressed_progress * input.pitch_length)
                .clamp(half_x + 1.0, input.pitch_length - 0.5)
        };
        let target = pitch_clamp(
            (x, player.base_pos.1),
            input.pitch_length,
            input.pitch_width,
        );
        targets.push((player.index, target));

        if player.team_is_restart && !player.is_goalkeeper {
            let dist = crate::physics::distance(player.current_pos, center);
            if restart_closest.map(|(_, best)| dist < best).unwrap_or(true) {
                restart_closest = Some((player.index, dist));
            }
            if is_forward_position(player.position)
                && restart_forward.map(|(_, best)| dist < best).unwrap_or(true)
            {
                restart_forward = Some((player.index, dist));
            }
        }
    }

    let kicker_index = restart_forward.or(restart_closest).map(|(idx, _)| idx);
    if let Some(kicker) = kicker_index {
        targets.retain(|(idx, _)| *idx != kicker);
        targets.push((kicker, center));
    }
    KickoffShapeOutput {
        targets,
        kicker_index,
    }
}

fn goal_kick_target_progress(
    base_progress: f64,
    attacking: bool,
    is_gk: bool,
    pitch_length: f64,
) -> f64 {
    if is_gk {
        return 6.0 / pitch_length;
    }
    if attacking {
        if base_progress < 0.28 {
            return 0.18 + base_progress * 0.42;
        }
        if base_progress < 0.52 {
            return 0.34 + (base_progress - 0.28) / 0.24 * 0.18;
        }
        if base_progress < 0.70 {
            return 0.52 + (base_progress - 0.52) / 0.18 * 0.12;
        }
        return 0.64 + (base_progress - 0.70) / 0.30 * 0.12;
    }
    base_progress
}

fn defending_distance_from_restart_goal(player: GoalKickPlayerInput, pitch_length: f64) -> f64 {
    if player.is_goalkeeper {
        return pitch_length - 6.0;
    }
    if player.is_attacker {
        return 34.0;
    }
    if player.is_midfielder {
        return 48.0;
    }
    if player.is_defender {
        return 63.0;
    }
    70.0
}

pub fn goal_kick_shape_targets(input: &GoalKickShapeInput<'_>) -> GoalKickShapeOutput {
    let mut targets = Vec::with_capacity(input.players.len());
    let ball_side = if input
        .players
        .first()
        .map(|p| p.restart_attacking_right)
        .unwrap_or(true)
    {
        -1.0
    } else {
        1.0
    };
    for player in input.players {
        let attacking = player.team_is_restart;
        let base_progress = if player.team_attacking_right {
            player.base_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - player.base_pos.0) / input.pitch_length
        };
        let base_width = player.base_pos.1 - input.pitch_width / 2.0;
        let target = if attacking {
            let progress = goal_kick_target_progress(
                base_progress,
                true,
                player.is_goalkeeper,
                input.pitch_length,
            );
            let x = if player.team_attacking_right {
                progress * input.pitch_length
            } else {
                (1.0 - progress) * input.pitch_length
            };
            let y = input.pitch_width / 2.0 + base_width * 1.08;
            pitch_clamp((x, y), input.pitch_length, input.pitch_width)
        } else {
            let distance_from_goal =
                defending_distance_from_restart_goal(*player, input.pitch_length);
            let x = if player.restart_attacking_right {
                distance_from_goal
            } else {
                input.pitch_length - distance_from_goal
            };
            let y = input.pitch_width / 2.0 + base_width * 0.92 + ball_side * 2.2;
            pitch_clamp((x, y), input.pitch_length, input.pitch_width)
        };
        targets.push((player.index, target));
    }
    GoalKickShapeOutput { targets }
}

pub fn restart_shape_plan(input: &RestartShapePlanInput<'_>) -> RestartShapePlanOutput {
    if input.players.is_empty() {
        return RestartShapePlanOutput {
            has_shape: false,
            ball_pos: (0.0, 0.0),
            players: Vec::new(),
        };
    }
    let restart_attacking_right = input.players[0].restart_attacking_right;
    if input.reason == "goal_kick" {
        let goal_kick_players: Vec<GoalKickPlayerInput> = input
            .players
            .iter()
            .enumerate()
            .map(|(ordinal, player)| GoalKickPlayerInput {
                index: ordinal,
                team_is_restart: player.team_is_restart,
                team_attacking_right: player.team_attacking_right,
                restart_attacking_right: player.restart_attacking_right,
                base_pos: player.base_pos,
                is_goalkeeper: player.is_goalkeeper,
                is_attacker: player.is_attacker,
                is_midfielder: player.is_midfielder,
                is_defender: player.is_defender,
            })
            .collect();
        let shape = goal_kick_shape_targets(&GoalKickShapeInput {
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            players: &goal_kick_players,
        });
        let mut outputs = Vec::new();
        for (ordinal, target) in shape.targets {
            if let Some(player) = input.players.get(ordinal) {
                if player.team_is_restart && player.is_goalkeeper {
                    continue;
                }
                let must_leave_box = must_leave_penalty_area_for_goal_kick(
                    player.team_is_restart,
                    player.current_pos.0,
                    restart_attacking_right,
                    input.pitch_length,
                );
                let snap = input.force
                    && (must_leave_box
                        || crate::physics::distance(player.current_pos, target) > 16.0);
                outputs.push(RestartShapePlanPlayerOutput {
                    team_code: player.team_code,
                    index: player.index,
                    target,
                    snap,
                });
            }
        }
        let gk_spot = goal_kick_spot(
            restart_attacking_right,
            input.pitch_length,
            input.pitch_width,
        );
        if let Some(gk) = input
            .players
            .iter()
            .find(|player| player.team_is_restart && player.is_goalkeeper)
        {
            outputs.push(RestartShapePlanPlayerOutput {
                team_code: gk.team_code,
                index: gk.index,
                target: gk_spot,
                snap: input.force && crate::physics::distance(gk.current_pos, gk_spot) > 16.0,
            });
        }
        return RestartShapePlanOutput {
            has_shape: true,
            ball_pos: gk_spot,
            players: outputs,
        };
    }
    if input.reason == "kickoff" {
        let kickoff_players: Vec<KickoffPlayerInput<'_>> = input
            .players
            .iter()
            .enumerate()
            .map(|(ordinal, player)| KickoffPlayerInput {
                index: ordinal,
                team_is_restart: player.team_is_restart,
                attacking_right: player.team_attacking_right,
                base_pos: player.base_pos,
                current_pos: player.current_pos,
                is_goalkeeper: player.is_goalkeeper,
                position: player.position,
            })
            .collect();
        let shape = kickoff_shape_targets(&KickoffShapeInput {
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            players: &kickoff_players,
        });
        let outputs = shape
            .targets
            .into_iter()
            .filter_map(|(ordinal, target)| {
                input
                    .players
                    .iter()
                    .enumerate()
                    .find(|(player_ordinal, _)| *player_ordinal == ordinal)
                    .map(|(_, player)| player)
                    .map(|player| RestartShapePlanPlayerOutput {
                        team_code: player.team_code,
                        index: player.index,
                        target,
                        snap: input.force
                            && crate::physics::distance(player.current_pos, target) > 16.0,
                    })
            })
            .collect();
        return RestartShapePlanOutput {
            has_shape: true,
            ball_pos: (input.pitch_length / 2.0, input.pitch_width / 2.0),
            players: outputs,
        };
    }
    RestartShapePlanOutput {
        has_shape: false,
        ball_pos: (0.0, 0.0),
        players: Vec::new(),
    }
}

pub fn flight_movement_plan(input: &FlightMovementPlanInput<'_>) -> FlightMovementPlanOutput {
    let mut outputs = Vec::with_capacity(input.attack_players.len() + input.defense_players.len());
    for player in input.attack_players {
        if player.is_stunned {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 0,
                index: player.index,
                action_code: 3,
                target: player.pos,
            });
            continue;
        }
        let dist_to_target = crate::physics::distance(player.pos, input.target_pos);
        if !player.is_passer && dist_to_target < input.contested_race_radius * 1.35 {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 0,
                index: player.index,
                action_code: 1,
                target: input.target_pos,
            });
        } else {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 0,
                index: player.index,
                action_code: 0,
                target: pitch_clamp(
                    (
                        player.tactical_anchor.0 * 0.86 + input.target_pos.0 * 0.14,
                        player.tactical_anchor.1 * 0.88 + input.target_pos.1 * 0.12,
                    ),
                    input.pitch_length,
                    input.pitch_width,
                ),
            });
        }
    }
    for player in input.defense_players {
        if player.is_stunned {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 1,
                index: player.index,
                action_code: 3,
                target: player.pos,
            });
            continue;
        }
        let dist_to_target = crate::physics::distance(player.pos, input.target_pos);
        if dist_to_target < input.contested_race_radius * 1.25 {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 1,
                index: player.index,
                action_code: 2,
                target: input.target_pos,
            });
        } else {
            outputs.push(FlightMovementPlanPlayerOutput {
                team_code: 1,
                index: player.index,
                action_code: 0,
                target: pitch_clamp(
                    (
                        player.tactical_anchor.0 * 0.88 + input.target_pos.0 * 0.12,
                        player.tactical_anchor.1 * 0.90 + input.target_pos.1 * 0.10,
                    ),
                    input.pitch_length,
                    input.pitch_width,
                ),
            });
        }
    }
    FlightMovementPlanOutput { players: outputs }
}

pub fn defensive_pressure_adjust_plan(
    input: &DefensivePressureAdjustInput<'_>,
) -> DefensivePressureAdjustPlanOutput {
    if input.holder_action_type != "carry" && input.holder_action_type != "hold" {
        return DefensivePressureAdjustPlanOutput {
            targets: Vec::new(),
        };
    }
    if !input.ball_is_held_by_holder {
        return DefensivePressureAdjustPlanOutput {
            targets: Vec::new(),
        };
    }
    let holder_progress = if input.holder_team_attacking_right {
        input.holder_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.holder_pos.0) / input.pitch_length
    };
    if holder_progress < 0.66
        && input.holder_consecutive_carries < 2
        && input.holder_action_type != "hold"
    {
        return DefensivePressureAdjustPlanOutput {
            targets: Vec::new(),
        };
    }
    if input.defenders.is_empty() {
        return DefensivePressureAdjustPlanOutput {
            targets: Vec::new(),
        };
    }
    let nearest_dist = input
        .defenders
        .iter()
        .map(|defender| crate::physics::distance(defender.pos, input.holder_pos))
        .fold(f64::INFINITY, f64::min);
    let pressure_range = input.tackle_range.max(input.press_radius * 0.70);
    let close_count = input
        .defenders
        .iter()
        .filter(|defender| {
            crate::physics::distance(defender.pos, input.holder_pos) < pressure_range
        })
        .count();
    let centrality = 1.0
        - ((input.holder_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
            .min(1.0);
    let stale_threat = ((input.holder_consecutive_carries - 1) as f64 / 3.0).clamp(0.0, 1.0)
        * ((holder_progress - 0.62) / 0.24).clamp(0.0, 1.0)
        * (0.55 + 0.45 * centrality);
    if stale_threat <= 0.0 {
        return DefensivePressureAdjustPlanOutput {
            targets: Vec::new(),
        };
    }

    let goal_side = if input.opp_team_attacking_right {
        -1.0
    } else {
        1.0
    };
    let mut targets = Vec::new();
    for defender in input.defenders {
        let d = crate::physics::distance(defender.pos, input.holder_pos);
        if d > input.press_radius * 1.25 {
            continue;
        }
        let target_d = crate::physics::distance(defender.target_pos, input.holder_pos);
        let distance_responsibility = (1.0 - (d - nearest_dist).max(0.0) / 11.0).clamp(0.0, 1.0);
        let crowd_factor = 1.0 / (1.0 + close_count.saturating_sub(1) as f64 * 0.45);
        let intent_factor = match defender.movement_intent {
            "press" => 1.0,
            "block_lane" | "mark" => 0.72,
            _ => 0.55,
        };
        let adjust = stale_threat * distance_responsibility * crowd_factor * intent_factor;
        if adjust <= 0.08 {
            continue;
        }

        let contain_depth = 2.2 + 1.5 * stale_threat;
        let y_offset = (defender.pos.1 - input.holder_pos.1).clamp(-4.0, 4.0) * 0.35;
        let pressure_target = pitch_clamp(
            (
                input.holder_pos.0 + goal_side * contain_depth,
                input.holder_pos.1 + y_offset,
            ),
            input.pitch_length,
            input.pitch_width,
        );
        if crate::physics::distance(pressure_target, input.holder_pos) >= target_d {
            continue;
        }
        let blend = (0.18 + 0.42 * adjust).min(0.55);
        let target_pos = (
            defender.target_pos.0 * (1.0 - blend) + pressure_target.0 * blend,
            defender.target_pos.1 * (1.0 - blend) + pressure_target.1 * blend,
        );
        let movement_intent_code = if matches!(
            defender.movement_intent,
            "defend_shape" | "block_lane" | "mark"
        ) {
            1
        } else {
            0
        };
        targets.push(DefensivePressureAdjustOutput {
            index: defender.index,
            target_pos,
            movement_intent_code,
        });
    }
    DefensivePressureAdjustPlanOutput { targets }
}

pub fn score_mark_runner_zone(input: &DefenseZoneHelperInput<'_>) -> DefenseZoneHelperOutput {
    if input.attackers.is_empty() {
        return DefenseZoneHelperOutput {
            score: 0.0,
            target: input.tactical_anchor,
        };
    }
    let mut best_threat = 0.0;
    let mut best_target = None;
    for attacker in input.attackers {
        let dist_to_ball = crate::physics::distance(attacker.pos, input.ball_pos);
        let ball_proximity = (1.0 - dist_to_ball / 30.0).max(0.2);
        let advance = if input.attacking_right {
            1.0 - attacker.pos.0 / input.pitch_length
        } else {
            attacker.pos.0 / input.pitch_length
        };
        let threat = ball_proximity * 0.6 + advance * 0.4;
        if threat > best_threat {
            best_threat = threat;
            best_target = Some(attacker.pos);
        }
    }
    let Some(target) = best_target else {
        return DefenseZoneHelperOutput {
            score: 0.0,
            target: input.tactical_anchor,
        };
    };
    let mark_x = if input.attacking_right {
        target.0 - 1.5
    } else {
        target.0 + 1.5
    };
    DefenseZoneHelperOutput {
        score: best_threat * 0.6,
        target: pitch_clamp((mark_x, target.1), input.pitch_length, input.pitch_width),
    }
}

pub fn score_block_lane_zone(input: &DefenseZoneHelperInput<'_>) -> DefenseZoneHelperOutput {
    if input.attackers.is_empty() {
        return DefenseZoneHelperOutput {
            score: 0.0,
            target: input.tactical_anchor,
        };
    }
    let target = input
        .attackers
        .iter()
        .min_by(|a, b| {
            crate::physics::distance(input.defender_pos, a.pos)
                .partial_cmp(&crate::physics::distance(input.defender_pos, b.pos))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|attacker| attacker.pos)
        .unwrap_or(input.tactical_anchor);
    let lane_target = pitch_clamp(
        (
            (input.ball_pos.0 + target.0) / 2.0,
            (input.ball_pos.1 + target.1) / 2.0,
        ),
        input.pitch_length,
        input.pitch_width,
    );
    let dist_opp_to_ball = crate::physics::distance(target, input.ball_pos);
    let threat = if dist_opp_to_ball > 40.0 {
        0.2
    } else {
        (1.0 - dist_opp_to_ball / 40.0).max(0.2)
    };
    DefenseZoneHelperOutput {
        score: threat * 0.5,
        target: lane_target,
    }
}

pub fn score_tackle(input: &TackleScoreInput) -> TackleScoreOutput {
    let dist_factor = (1.0 - input.dist_to_ball / (input.tackle_range * 0.9).max(0.1)).max(0.0);
    let mut success_rate = input.tackling / (input.tackling + input.dribbling + 1.0) * dist_factor;
    success_rate = success_rate.clamp(0.0, 0.75);
    let score = (success_rate * 1.8 - (1.0 - success_rate) * 0.35).max(0.0);
    TackleScoreOutput {
        score,
        success_rate,
    }
}

pub fn score_block_lane_legacy(input: &DefenseZoneHelperInput<'_>) -> DefenseZoneHelperOutput {
    score_block_lane_zone(input)
}

pub fn score_mark_runner_legacy(input: &DefenseZoneHelperInput<'_>) -> DefenseZoneHelperOutput {
    if input.attackers.is_empty() {
        return DefenseZoneHelperOutput {
            score: 0.0,
            target: input.tactical_anchor,
        };
    }
    let target = input
        .attackers
        .iter()
        .min_by(|a, b| {
            crate::physics::distance(input.defender_pos, a.pos)
                .partial_cmp(&crate::physics::distance(input.defender_pos, b.pos))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|attacker| attacker.pos)
        .unwrap_or(input.tactical_anchor);
    let dist_to_ball = crate::physics::distance(target, input.ball_pos);
    let threat = (1.0 - dist_to_ball / 30.0).max(0.2);
    let mark_x = if input.attacking_right {
        target.0 - 1.5
    } else {
        target.0 + 1.5
    };
    DefenseZoneHelperOutput {
        score: threat * 0.6,
        target: pitch_clamp((mark_x, target.1), input.pitch_length, input.pitch_width),
    }
}

pub fn pass_control_strength(input: &PassControlInput) -> PassControlOutput {
    if input.score.is_infinite() {
        return PassControlOutput { control: 0.0 };
    }
    let scale = (input.contest_radius * 1.55).max(0.1);
    PassControlOutput {
        control: 1.0 / (1.0 + (input.score.max(0.0) / scale).powi(2)),
    }
}

pub fn pass_loose_control_strength(input: &PassLooseControlInput) -> PassLooseControlOutput {
    let strongest = input
        .teammate_control
        .clamp(0.0, 1.0)
        .max(input.opponent_control.clamp(0.0, 1.0));
    let balance = 1.0 - (input.teammate_control.max(0.0) - input.opponent_control.max(0.0)).abs();
    PassLooseControlOutput {
        control: (1.0 - strongest).max(0.0) * (0.25 + 0.20 * balance.clamp(0.0, 1.0)),
    }
}

pub fn team_shape_plan(input: &TeamShapePlanInput<'_>) -> TeamShapePlanOutput {
    let mut anchors = vec![
        TeamShapePlayerOutput {
            index: 0,
            tactical_anchor: (0.0, 0.0),
        };
        input.players.len()
    ];
    let len = team_shape_plan_into(input, &mut anchors);
    anchors.truncate(len);
    TeamShapePlanOutput { anchors }
}

pub fn team_shape_plan_into(
    input: &TeamShapePlanInput<'_>,
    output: &mut [TeamShapePlayerOutput],
) -> usize {
    assert!(
        output.len() >= input.players.len(),
        "team shape output buffer is smaller than the player set"
    );
    if input.players.is_empty() {
        return 0;
    }
    let ball_progress = if input.attacking_right {
        input.ball_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.ball_pos.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let side_shift = input.ball_pos.1 - input.pitch_width / 2.0;
    let is_defending = matches!(input.phase, "defending" | "transition_def" | "contesting");
    let is_transition_def = input.phase == "transition_def";
    let plan = input.plan_signals;

    let offside_line = (!input.opponents.is_empty()).then(|| {
        get_offside_line_from_xs(
            input.opponents.iter().map(|player| player.pos.0),
            input.attacking_right,
            input.pitch_length,
        )
    });

    let mut output_len = 0;
    for player in input.players {
        let base = player.base_pos;
        let base_progress = if input.attacking_right {
            base.0 / input.pitch_length
        } else {
            (input.pitch_length - base.0) / input.pitch_length
        };
        let base_width_offset = base.1 - input.pitch_width / 2.0;
        let (mut progress, y) = if player.is_goalkeeper {
            let coverage_target = goalkeeper_shape_anchor(&GkShapeAnchorInput {
                ball_pos: input.ball_pos,
                base_pos: player.base_pos,
                attacking_right: input.attacking_right,
                team_depth_scale: plan.depth_scale,
                pitch_length: input.pitch_length,
                pitch_width: input.pitch_width,
            });
            let progress = if input.attacking_right {
                coverage_target.0 / input.pitch_length
            } else {
                (input.pitch_length - coverage_target.0) / input.pitch_length
            };
            (progress, coverage_target.1)
        } else if is_defending {
            let mut block_center = 0.18 + 0.50 * ball_progress;
            if is_transition_def {
                block_center += 0.06;
            }
            let line_offset = (base_progress - 0.50) * (0.72 * plan.depth_scale);
            (
                (block_center + line_offset).clamp(0.05, 0.92),
                input.pitch_width / 2.0
                    + base_width_offset * (0.92 * plan.width_scale)
                    + side_shift * (0.14 * (1.0 - 0.55 * plan.compactness)),
            )
        } else {
            let advance_pressure = (ball_progress - base_progress).max(0.0);
            let width_ratio = (base_width_offset.abs() / (input.pitch_width / 2.0)).min(1.0);
            let role_side = base_width_offset / (input.pitch_width / 2.0).max(1.0);
            let ball_side = side_shift / (input.pitch_width / 2.0).max(1.0);
            let same_side = (role_side * ball_side).clamp(0.0, 1.0);
            let weak_side = (-role_side * ball_side).clamp(0.0, 1.0);
            let advanced_role = ((base_progress - 0.42) / 0.38).clamp(0.0, 1.0);
            let support_role = ((base_progress - 0.22) / 0.42).clamp(0.0, 1.0);
            let second_line_role = crate::physics::smoothstep(0.42, 0.54, base_progress)
                * (1.0 - crate::physics::smoothstep(0.62, 0.74, base_progress));
            let final_third_pressure = (ball_progress - 0.50).max(0.0);
            let push = advance_pressure * (0.18 + 0.30 * advanced_role + 0.14 * width_ratio);
            let box_arrival = final_third_pressure * (0.58 * advanced_role + 0.20 * width_ratio);
            let wide_midfield_support = final_third_pressure
                * width_ratio
                * (1.0 - advanced_role)
                * crate::physics::smoothstep(0.38, 0.58, base_progress)
                * 0.34;
            let wide_midfield_outlet = crate::physics::smoothstep(0.56, 0.74, ball_progress)
                * width_ratio
                * (1.0 - advanced_role)
                * crate::physics::smoothstep(0.38, 0.58, base_progress)
                * 0.16;
            let second_line_arrival = final_third_pressure
                * (1.0 - advanced_role)
                * crate::physics::smoothstep(0.38, 0.58, base_progress)
                * (0.10 + 0.10 * (1.0 - width_ratio));
            let arc_support_pressure = crate::physics::smoothstep(0.78, 0.90, ball_progress)
                * second_line_role
                * (1.0 - 0.45 * crate::physics::smoothstep(0.56, 0.84, width_ratio));
            let arc_support_arrival =
                arc_support_pressure * (0.075 + 0.055 * (1.0 - width_ratio) + 0.035 * weak_side);
            let weak_side_arrival = final_third_pressure
                * width_ratio
                * weak_side
                * crate::physics::smoothstep(0.38, 0.68, base_progress)
                * (0.10 + 0.18 * advanced_role);
            let wide_arrival_depth = crate::physics::smoothstep(0.70, 0.88, ball_progress)
                * width_ratio
                * crate::physics::smoothstep(0.44, 0.64, base_progress)
                * (0.20 + 0.18 * weak_side + 0.10 * same_side);
            let line_stretch = (ball_progress - 0.66).max(0.0) * (0.10 + 0.16 * advanced_role);
            let mut progress = base_progress
                + push
                + box_arrival
                + wide_midfield_support
                + wide_midfield_outlet
                + second_line_arrival
                + arc_support_arrival
                + weak_side_arrival
                + wide_arrival_depth
                + line_stretch
                + 0.015
                + 0.045 * advanced_role;

            let cover_cap = 0.54 + ball_progress * (0.08 + 0.08 * support_role);
            if advanced_role < 0.35 {
                let wide_support_cap = final_third_pressure
                    * width_ratio
                    * crate::physics::smoothstep(0.38, 0.58, base_progress)
                    * 0.18;
                let second_line_cap = final_third_pressure
                    * crate::physics::smoothstep(0.38, 0.58, base_progress)
                    * (0.08 + 0.10 * (1.0 - width_ratio) + 0.08 * weak_side);
                let arc_support_cap = arc_support_pressure
                    * (0.070 + 0.060 * (1.0 - width_ratio) + 0.035 * weak_side);
                let wide_arrival_cap = crate::physics::smoothstep(0.70, 0.88, ball_progress)
                    * width_ratio
                    * crate::physics::smoothstep(0.44, 0.64, base_progress)
                    * (0.10 + 0.12 * weak_side + 0.06 * same_side);
                progress = progress.min(
                    cover_cap
                        + wide_support_cap
                        + wide_midfield_outlet
                        + second_line_cap
                        + arc_support_cap
                        + wide_arrival_cap,
                );
            }
            progress =
                (base_progress + (progress - base_progress) * plan.depth_scale).clamp(0.08, 0.94);
            let mut width_expansion = 1.00
                + (0.16 * same_side + 0.05 * (1.0 - same_side - weak_side)) * ball_progress
                + (0.14 * same_side + 0.04 * (1.0 - same_side - weak_side)) * advanced_role
                - 0.26 * weak_side * crate::physics::smoothstep(0.62, 0.88, ball_progress);
            width_expansion = width_expansion.clamp(0.62, 1.32);
            let overlap_width = base_width_offset * width_expansion;
            let half_space_pressure = crate::physics::smoothstep(0.58, 0.82, ball_progress);
            let half_space_pull = -base_width_offset
                * half_space_pressure
                * (0.16 + 0.48 * weak_side + 0.08 * (1.0 - same_side));
            let far_post_tuck = -base_width_offset
                * (crate::physics::smoothstep(0.72, 0.88, ball_progress)
                    * width_ratio
                    * weak_side
                    * (0.16 + 0.12 * advanced_role));
            let second_line_tuck = -base_width_offset
                * (final_third_pressure
                    * (1.0 - advanced_role)
                    * crate::physics::smoothstep(0.38, 0.58, base_progress)
                    * (0.16 + 0.22 * weak_side));
            let arc_support_tuck = -base_width_offset
                * arc_support_pressure
                * (0.10 + 0.18 * (1.0 - width_ratio) + 0.08 * weak_side);
            let wide_midfield_half_space_tuck = -base_width_offset
                * (crate::physics::smoothstep(0.66, 0.80, ball_progress)
                    * width_ratio
                    * (1.0 - advanced_role)
                    * crate::physics::smoothstep(0.38, 0.58, base_progress)
                    * (0.62 + 0.42 * same_side + 0.18 * weak_side));
            let mut y = input.pitch_width / 2.0
                + overlap_width
                + half_space_pull
                + far_post_tuck
                + second_line_tuck
                + arc_support_tuck
                + wide_midfield_half_space_tuck
                + side_shift * (0.12 + 0.08 * width_ratio) * (1.0 - 0.45 * plan.switch_bias);
            let wide_midfield_half_space = crate::physics::smoothstep(0.66, 0.80, ball_progress)
                * width_ratio
                * (1.0 - advanced_role)
                * crate::physics::smoothstep(0.38, 0.58, base_progress);
            if wide_midfield_half_space > 0.0 {
                let target_offset = base_width_offset * 0.42;
                let target_y = input.pitch_width / 2.0 + target_offset;
                y = y * (1.0 - 0.75 * wide_midfield_half_space)
                    + target_y * (0.75 * wide_midfield_half_space);
            }
            (
                progress,
                input.pitch_width / 2.0 + (y - input.pitch_width / 2.0) * plan.width_scale,
            )
        };

        if !is_defending {
            if let Some(line) = offside_line {
                if !player.is_goalkeeper {
                    let line_progress = if input.attacking_right {
                        line / input.pitch_length
                    } else {
                        (input.pitch_length - line) / input.pitch_length
                    };
                    let buffer = 0.060 - 0.020 * ((base_progress - 0.42) / 0.38).clamp(0.0, 1.0);
                    let onside_progress = line_progress - buffer;
                    if progress > onside_progress {
                        progress = (progress * 0.15 + onside_progress * 0.85)
                            .min(onside_progress)
                            .clamp(0.10, 0.94);
                    }
                }
            }
        }

        let x = if input.attacking_right {
            progress * input.pitch_length
        } else {
            (1.0 - progress) * input.pitch_length
        };
        output[output_len] = TeamShapePlayerOutput {
            index: player.index,
            tactical_anchor: pitch_clamp((x, y), input.pitch_length, input.pitch_width),
        };
        output_len += 1;
    }
    output_len
}

pub fn team_phase_update(input: &TeamPhaseUpdateInput) -> TeamPhaseUpdateOutput {
    if input.ball_contested {
        return TeamPhaseUpdateOutput {
            phase_code: 4,
            ticks_since_possession_change: input.ticks_since_possession_change,
            had_possession_last_tick: input.had_possession_last_tick,
        };
    }
    let ticks_since_possession_change = if input.has_possession != input.had_possession_last_tick {
        0
    } else {
        input.ticks_since_possession_change + 1
    };
    let phase_code = if input.has_possession {
        if ticks_since_possession_change < input.transition_ticks {
            1
        } else {
            0
        }
    } else if ticks_since_possession_change < input.transition_ticks {
        3
    } else {
        2
    };
    TeamPhaseUpdateOutput {
        phase_code,
        ticks_since_possession_change,
        had_possession_last_tick: input.has_possession,
    }
}

pub fn player_tick_stun(input: &PlayerTickStunInput<'_>) -> PlayerTickStunOutput {
    if input.stun_ticks_remaining > 0 {
        let ticks = input.stun_ticks_remaining - 1;
        PlayerTickStunOutput {
            state: if ticks <= 0 {
                "off_ball".to_string()
            } else {
                input.state.to_string()
            },
            stun_ticks_remaining: ticks,
        }
    } else {
        PlayerTickStunOutput {
            state: input.state.to_string(),
            stun_ticks_remaining: input.stun_ticks_remaining,
        }
    }
}

pub fn player_apply_stun(input: &PlayerApplyStunInput) -> PlayerApplyStunOutput {
    PlayerApplyStunOutput {
        state: "stunned".to_string(),
        stun_ticks_remaining: (input.tackle_fail_stun_seconds / input.tick_duration)
            .ceil()
            .max(1.0) as i32
            + 1,
    }
}

fn closest_restart_player(
    players: &[RestartPlayerInput],
    pos: (f64, f64),
    exclude_gk: bool,
) -> Option<usize> {
    let mut best = None;
    let mut best_dist = f64::INFINITY;
    for player in players {
        if exclude_gk && player.is_goalkeeper {
            continue;
        }
        let dist = crate::physics::distance(player.pos, pos);
        if dist < best_dist {
            best_dist = dist;
            best = Some(player.index);
        }
    }
    best
}

pub fn restart_play_decision(input: &RestartPlayInput<'_>) -> RestartPlayOutput {
    let center = (input.pitch_length / 2.0, input.pitch_width / 2.0);
    match input.reason {
        "kickoff" => RestartPlayOutput {
            ball_pos: center,
            receiver_index: closest_restart_player(input.players, center, true),
            set_receiver_pos: true,
            pending_cut: true,
        },
        "goal_kick" => {
            let spot = goal_kick_spot(
                input.restart_attacking_right,
                input.pitch_length,
                input.pitch_width,
            );
            let receiver = input
                .players
                .iter()
                .find(|player| player.is_goalkeeper)
                .map(|player| player.index);
            RestartPlayOutput {
                ball_pos: spot,
                receiver_index: receiver,
                set_receiver_pos: true,
                pending_cut: false,
            }
        }
        "corner" => {
            let y = if input.corner_y_roll < 0.5 {
                0.5
            } else {
                input.pitch_width - 0.5
            };
            let pos = if input.restart_attacking_right {
                (input.pitch_length - 0.5, y)
            } else {
                (0.5, y)
            };
            RestartPlayOutput {
                ball_pos: pos,
                receiver_index: closest_restart_player(input.players, pos, true),
                set_receiver_pos: true,
                pending_cut: false,
            }
        }
        "throw_in" | "offside" => {
            let pos = pitch_clamp(input.ball_pos, input.pitch_length, input.pitch_width);
            RestartPlayOutput {
                ball_pos: pos,
                receiver_index: closest_restart_player(input.players, pos, true),
                set_receiver_pos: false,
                pending_cut: false,
            }
        }
        _ => {
            let pos = pitch_clamp(input.ball_pos, input.pitch_length, input.pitch_width);
            RestartPlayOutput {
                ball_pos: pos,
                receiver_index: closest_restart_player(input.players, pos, true),
                set_receiver_pos: false,
                pending_cut: false,
            }
        }
    }
}

pub fn restart_play_plan(input: &RestartPlayPlanInput<'_>) -> RestartPlayPlanOutput {
    let restart = restart_play_decision(&RestartPlayInput {
        reason: input.reason,
        ball_pos: input.ball_pos,
        restart_attacking_right: input.restart_attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        corner_y_roll: input.corner_y_roll,
        players: input.players,
    });
    RestartPlayPlanOutput {
        ball_pos: restart.ball_pos,
        receiver_index: restart.receiver_index,
        set_receiver_pos: restart.set_receiver_pos,
        pending_cut: restart.pending_cut,
        reset_last_passer: true,
        clear_offside_flags: true,
    }
}

pub fn track_pass_stats(input: &PassStatInput) -> PassStatOutput {
    let dist = crate::physics::distance(input.origin, input.target);
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let progress = (input.target.0 - input.origin.0) * forward_dir;
    let target_progress = if input.attacking_right {
        input.target.0 / input.pitch_length
    } else {
        (input.pitch_length - input.target.0) / input.pitch_length
    };
    let origin_wide = (input.origin.1 - input.pitch_width / 2.0).abs() > input.pitch_width * 0.28;
    let target_in_box = target_progress > (1.0 - 16.5 / input.pitch_length)
        && (input.target.1 - input.pitch_width / 2.0).abs() < 20.2;
    let crosses = origin_wide && target_in_box && progress > 3.0;
    let passes_into_final_third = if input.attacking_right {
        input.target.0 > input.pitch_length * 2.0 / 3.0
    } else {
        input.target.0 < input.pitch_length / 3.0
    };
    let passes_into_box = if input.attacking_right {
        input.target.0 > input.pitch_length - 16.5
            && (input.target.1 - input.pitch_width / 2.0).abs() < 20.2
    } else {
        input.target.0 < 16.5 && (input.target.1 - input.pitch_width / 2.0).abs() < 20.2
    };
    PassStatOutput {
        crosses_attempted: if crosses { 1 } else { 0 },
        crosses_completed: if crosses { 1 } else { 0 },
        progressive_passes: if progress > 10.0 { 1 } else { 0 },
        long_passes: if dist > 30.0 { 1 } else { 0 },
        completed_long_passes: if dist > 30.0 { 1 } else { 0 },
        passes_into_final_third: if passes_into_final_third { 1 } else { 0 },
        passes_into_box: if passes_into_box { 1 } else { 0 },
    }
}

pub fn track_carry_stats(input: &CarryStatInput) -> CarryStatOutput {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let progress = (input.new_pos.0 - input.old_pos.0) * forward_dir;
    let carries_into_final_third = if input.attacking_right {
        input.new_pos.0 > input.pitch_length * 2.0 / 3.0
            && input.old_pos.0 <= input.pitch_length * 2.0 / 3.0
    } else {
        input.new_pos.0 < input.pitch_length / 3.0 && input.old_pos.0 >= input.pitch_length / 3.0
    };
    let carries_into_box = if input.attacking_right {
        input.new_pos.0 > input.pitch_length - 16.5
            && (input.new_pos.1 - input.pitch_width / 2.0).abs() < 20.2
            && input.old_pos.0 <= input.pitch_length - 16.5
    } else {
        input.new_pos.0 < 16.5
            && (input.new_pos.1 - input.pitch_width / 2.0).abs() < 20.2
            && input.old_pos.0 >= 16.5
    };
    CarryStatOutput {
        progressive_carries: if progress > 5.0 { 1 } else { 0 },
        carries_into_final_third: if carries_into_final_third { 1 } else { 0 },
        carries_into_box: if carries_into_box { 1 } else { 0 },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retained_pass_control_is_not_reversed_by_arrival_geometry() {
        let transition = pass_control_transition(&PassControlTransitionInput {
            retained_possession: true,
            receiver_index: Some(4),
            opponent_index: Some(2),
            opponent_control: 0.95,
            loose_control: 0.02,
        });

        assert_eq!(transition.outcome_code, 0);
        assert_eq!(transition.receiver_index, Some(4));
        assert_eq!(transition.opponent_index, None);
    }

    #[test]
    fn failed_pass_control_uses_arrival_only_for_failure_shape() {
        let interception = pass_control_transition(&PassControlTransitionInput {
            retained_possession: false,
            receiver_index: Some(4),
            opponent_index: Some(2),
            opponent_control: 0.70,
            loose_control: 0.20,
        });
        let loose = pass_control_transition(&PassControlTransitionInput {
            retained_possession: false,
            receiver_index: Some(4),
            opponent_index: Some(2),
            opponent_control: 0.20,
            loose_control: 0.70,
        });

        assert_eq!(interception.outcome_code, 1);
        assert_eq!(interception.opponent_index, Some(2));
        assert_eq!(loose.outcome_code, 2);
        assert_eq!(loose.receiver_index, None);
        assert_eq!(loose.opponent_index, None);
    }

    #[test]
    fn pass_receipt_preserves_the_player_contact_position() {
        let receive = pass_receive_plan(&PassReceivePlanInput {
            receiver_pos: (42.0, 30.0),
            target_pos: (44.0, 31.5),
            receiver_iq: 100.0,
            receiver_offside_flagged: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            first_touch_error_divisor: 700.0,
            error_roll: 1.0,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        });

        assert_eq!(receive.contact_pos, (42.0, 30.0));
        assert!(!receive.first_touch_error);
        assert!(receive.contact_offset > 0.0);
    }

    #[test]
    fn pass_phase_separates_technical_delivery_from_candidate_retention() {
        let clean_execution = pass_phase_plan(&PassPhasePlanInput {
            transition: None,
            passer_pos: (20.0, 34.0),
            ideal_target: (35.0, 40.0),
            passing: 80.0,
            is_long: false,
            lane_risk: 0.25,
            retention_probability: 0.60,
            technical_probability: 0.80,
            technical_roll: 0.79,
            pitch_length: 105.0,
            pitch_width: 68.0,
            ball_pass_speed: 18.0,
            ball_long_pass_speed: 22.0,
            tick_duration: 2.0,
            random_1: 0.25,
            random_2: 0.75,
            intended_receiver_pos: Some((35.0, 40.0)),
        });
        let lower_retention = pass_phase_plan(&PassPhasePlanInput {
            retention_probability: 0.30,
            ..retained_input()
        });
        let delivery_miss = pass_phase_plan(&PassPhasePlanInput {
            technical_roll: 0.81,
            ..retained_input()
        });

        assert!(!clean_execution.delivery_miss);
        assert!(!lower_retention.delivery_miss);
        assert!(delivery_miss.delivery_miss);
        assert_eq!(clean_execution.target, lower_retention.target);
        assert_eq!(clean_execution.randoms_used, 2);
        assert_eq!(delivery_miss.randoms_used, 2);
    }

    fn retained_input() -> PassPhasePlanInput {
        PassPhasePlanInput {
            transition: None,
            passer_pos: (20.0, 34.0),
            ideal_target: (35.0, 40.0),
            passing: 80.0,
            is_long: false,
            lane_risk: 0.25,
            retention_probability: 0.60,
            technical_probability: 0.80,
            technical_roll: 0.79,
            pitch_length: 105.0,
            pitch_width: 68.0,
            ball_pass_speed: 18.0,
            ball_long_pass_speed: 22.0,
            tick_duration: 2.0,
            random_1: 0.25,
            random_2: 0.75,
            intended_receiver_pos: Some((35.0, 40.0)),
        }
    }

    fn gk_shape_player(index: usize) -> TeamShapePlayerInput {
        TeamShapePlayerInput {
            index,
            base_pos: (0.5, 34.0),
            is_goalkeeper: index == 0,
        }
    }

    #[test]
    fn goalkeeper_shape_anchor_tracks_team_depth_and_ball_side_in_every_phase() {
        let players = [gk_shape_player(0), gk_shape_player(1)];
        let opponents = [TeamShapeOpponentInput {
            pos: (80.0, 34.0),
            is_goalkeeper: false,
        }];

        for phase in ["attacking", "defending", "transition_def", "contesting"] {
            let shape = team_shape_plan(&TeamShapePlanInput {
                ball_pos: (88.0, 60.0),
                attacking_right: true,
                phase,
                plan_signals: TeamPlanSignals::default(),
                pitch_length: 105.0,
                pitch_width: 68.0,
                players: &players,
                opponents: &opponents,
            });
            let goalkeeper = shape
                .anchors
                .iter()
                .find(|player| player.index == 0)
                .expect("goalkeeper anchor");
            assert!(
                goalkeeper.tactical_anchor.0 > 7.0 && goalkeeper.tactical_anchor.0 < 12.0,
                "{phase}: goalkeeper must advance from its fixed goal-line position with the team's depth, anchor={:?}",
                goalkeeper.tactical_anchor
            );
            assert!(
                goalkeeper.tactical_anchor.1 > 34.5,
                "{phase}: goalkeeper must shift toward the ball side while preserving goal coverage, anchor={:?}",
                goalkeeper.tactical_anchor
            );
        }
    }

    #[test]
    fn attacking_shape_uses_goalkeeper_in_the_offside_boundary() {
        let players = [
            TeamShapePlayerInput {
                index: 0,
                base_pos: (5.0, 34.0),
                is_goalkeeper: true,
            },
            TeamShapePlayerInput {
                index: 1,
                base_pos: (88.0, 34.0),
                is_goalkeeper: false,
            },
        ];
        let opponents = [
            TeamShapeOpponentInput {
                pos: (100.0, 34.0),
                is_goalkeeper: true,
            },
            TeamShapeOpponentInput {
                pos: (92.0, 18.0),
                is_goalkeeper: false,
            },
            TeamShapeOpponentInput {
                pos: (78.0, 50.0),
                is_goalkeeper: false,
            },
        ];
        let shape = team_shape_plan(&TeamShapePlanInput {
            ball_pos: (95.0, 34.0),
            attacking_right: true,
            phase: "attacking",
            plan_signals: TeamPlanSignals::default(),
            pitch_length: 105.0,
            pitch_width: 68.0,
            players: &players,
            opponents: &opponents,
        });
        let attacker = shape
            .anchors
            .iter()
            .find(|player| player.index == 1)
            .expect("attacker anchor");

        assert!(
            attacker.tactical_anchor.0 > 86.0,
            "the goalkeeper plus defender establish a 92m line, so the shape must not cap the run at the old 78m line"
        );
    }

    #[test]
    fn tackle_stun_blocks_the_next_decision_window_before_expiring() {
        let applied = player_apply_stun(&PlayerApplyStunInput {
            tackle_fail_stun_seconds: 1.5,
            tick_duration: 2.0,
        });
        assert_eq!(applied.state, "stunned");
        assert_eq!(applied.stun_ticks_remaining, 2);

        let current_tick_end = player_tick_stun(&PlayerTickStunInput {
            state: applied.state.as_str(),
            stun_ticks_remaining: applied.stun_ticks_remaining,
        });
        assert_eq!(current_tick_end.state, "stunned");
        assert_eq!(current_tick_end.stun_ticks_remaining, 1);

        let next_tick_end = player_tick_stun(&PlayerTickStunInput {
            state: current_tick_end.state.as_str(),
            stun_ticks_remaining: current_tick_end.stun_ticks_remaining,
        });
        assert_eq!(next_tick_end.state, "off_ball");
        assert_eq!(next_tick_end.stun_ticks_remaining, 0);
    }
}
