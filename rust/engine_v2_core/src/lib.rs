#![recursion_limit = "256"]

pub mod action_timing;
pub mod action_value;
pub mod arrival;
pub mod contested;
pub mod decision;
pub mod defense_coordination;
pub mod execution;
pub mod goal;
pub mod goalkeeper;
pub mod interactions;
pub mod match_clock;
pub mod match_flow;
pub mod match_runner;
pub mod off_ball_attack;
pub mod off_ball_defense;
pub mod offside;
pub mod on_ball;
pub mod pass_space;
pub mod pass_value;
pub mod physics;
pub mod position_value;
pub mod possession_control;
pub mod shot_quality;
pub mod state_value;
pub mod tactical_task;
pub mod team_plan;
pub mod vision;

pub use action_timing::{
    action_timing_plan, should_continue_action, ActionTimingInput, ActionTimingPlan,
    TemporalActionKind,
};
pub use action_value::{
    action_outcome_value, estimate_second_ball_control, second_ball_player_access,
    shot_possession_transition, temporal_option_value, ActionOutcomeValueInput,
    ActionOutcomeValueOutput, PossessionTransition, SecondBallControlEstimate,
    SecondBallControlInput, SecondBallPlayerInput, ShotPossessionTransitionInput,
    TemporalOptionValueInput, TemporalOptionValueOutput,
};
pub use arrival::{
    resolve_clearance_arrival, resolve_first_touch, resolve_pass_arrival, resolve_shot_arrival,
    ArrivalPlayerInput, ClearanceArrivalInput, ClearanceArrivalOutput, ClearancePlayerInput,
    FirstTouchInput, FirstTouchOutput, PassArrivalInput, PassArrivalOutput, ShotArrivalInput,
    ShotArrivalOutput,
};
pub use contested::{
    resolve_contested_owner, select_contested_targets, select_contested_targets_into,
    tick_contested_ball, ContestedOwnerInput, ContestedOwnerOutput, ContestedOwnerPlayerInput,
    ContestedTargetOutput, ContestedTargetPlayerInput, ContestedTargetsInput, ContestedTickInput,
    ContestedTickOutput,
};
pub use decision::{
    apply_iq_noise_score, apply_support_opportunity_cost, apply_support_opportunity_cost_into,
    select_best_arriving_support, select_best_byline_carry, select_best_layoff,
    select_best_overlap, select_hold_support, select_on_ball_candidate, softmax_select_index,
    softmax_select_index_signed, softmax_select_index_with_temperature, ArrivingSupportPassInput,
    ArrivingSupportSelectionInput, ArrivingSupportSelectionOutput, BylineCarryInput,
    BylineCarrySelectionInput, BylineCarrySelectionOutput, BylineSupportTeammateInput,
    HoldSupportCarryInput, HoldSupportHoldInput, HoldSupportPassInput, HoldSupportSelectionInput,
    HoldSupportSelectionOutput, IqNoiseScoreInput, IqNoiseScoreOutput, LayoffPassInput,
    LayoffSelectionInput, LayoffSelectionOutput, OnBallSelectionCandidateInput,
    OnBallSelectionInput, OnBallSelectionOutput, OverlapPassInput, OverlapSelectionInput,
    OverlapSelectionOutput, SoftmaxSelectionOutput, SupportOpportunityCarryInput,
    SupportOpportunityInput, SupportOpportunityOutput, SupportOpportunityPassInput,
};
pub use defense_coordination::{
    coordinate_team_defense, coordinate_team_defense_into, defense_resource_claim,
    defense_resource_claim_with_outlets, defense_resource_demand_from_visible_threats,
    DefenseResourceClaim, DefenseResourceDemand, DefenseTaskContinuity, DefenseTaskKind,
    TeamDefenseAssignment, TeamDefenseAssignmentInput, TeamDefenseAssignmentOutput,
    TeamDefenseCandidate, TeamDefenseCoordinationSummary, TeamDefensePlayerInput,
    MAX_FIXED_TEAM_DEFENSE_PLAYERS,
};
pub use execution::{
    execute_carry, execute_clear, execute_hold, execute_pass, execute_shot, generate_clear_target,
    CarryExecutionInput, CarryExecutionOutput, ClearExecutionInput, ClearExecutionOutput,
    ClearTargetInput, ClearTargetOutput, ExecutionOpponent, HoldExecutionInput,
    HoldExecutionOutput, PassExecutionInput, PassExecutionOutput, ShotExecutionInput,
    ShotExecutionOutput,
};
pub use goal::{
    apply_generic_on_ball_goal_continuity, apply_specialized_on_ball_bias, build_defensive_goal,
    build_off_ball_attack_goal, evaluate_arc_arrival_goal, evaluate_attack_far_post_goal,
    evaluate_byline_delivery_goal, evaluate_cut_inside_goal, evaluate_drive_byline_goal,
    evaluate_hold_opportunity_goal, evaluate_layoff_goal, evaluate_release_support_goal,
    evaluate_through_ball_goal, evaluate_wide_hold_overlap_goal, goal_selection_noise_from_gauss,
    goal_switch_cost, iq_decision_noise, iq_temperature_factor,
    select_goal_candidate_with_gaussians, select_goal_deterministic, ArcArrivalGoalInput,
    ArcArrivalGoalOutput, AttackFarPostGoalInput, AttackFarPostGoalOutput, BylineDeliveryGoalInput,
    BylineGoalOutput, CutInsideGoalInput, CutInsideGoalOutput, DefensiveGoalBuildInput,
    DefensiveGoalBuildOutput, DriveBylineGoalInput, GoalCandidateChoiceOutput, GoalInput,
    GoalSelectionOutput, GoalSwitchCostInput, HoldOpportunityGoalInput, HoldOpportunityGoalOutput,
    LayoffGoalInput, LayoffGoalOutput, OffBallAttackGoalBuildInput, OffBallAttackGoalBuildOutput,
    OnBallGenericCandidateInput, OnBallGenericContinuityInput, OnBallGenericContinuityOutput,
    OnBallGenericGoalInput, OnBallSpecializedBiasCandidateInput, OnBallSpecializedBiasInput,
    OnBallSpecializedBiasOutput, ReleaseSupportGoalInput, ReleaseSupportGoalOutput,
    ThroughBallGoalInput, ThroughBallGoalOutput, WideHoldOverlapGoalInput,
    WideHoldOverlapGoalOutput,
};
pub use goalkeeper::{
    choose_distribution, choose_fallback_target, compute_gk_save_probability,
    compute_gk_save_probability_for_attributes, goalkeeper_positioning_target,
    goalkeeper_shape_anchor, should_rush_out, GkDistributionInput, GkDistributionOutput,
    GkFallbackTargetInput, GkFallbackTargetOutput, GkPositioningInput, GkPositioningOutput,
    GkRushInput, GkSaveAttributes, GkSaveInput, GkShapeAnchorInput,
};
pub use interactions::{
    carry_survival_transition, carry_survival_transition_with_defender_response_slices,
    carry_survival_transition_with_defender_responses, detect_duel, detect_interception,
    detect_wasted_tackle, duel_margin, interception_chance, resolve_duel, resolve_interception,
    track_defensive_pressures, track_defensive_pressures_into, CarrySurvivalInput,
    CarrySurvivalTransition, DefenderActionInput, DefensivePressureInput, DefensivePressureOutput,
    DetectionResult, DuelDetectionInput, DuelResolveInput, InterceptionDetectionInput,
    InterceptionResolveInput, WastedTackleInput,
};
pub use match_clock::{MatchClock, MatchClockPhase, MatchClockSnapshot};
pub use match_flow::{
    build_ball_flight_frame, build_goal_event, carry_phase_plan, clear_phase_plan,
    clearance_arrival_plan, contested_tick_plan, defensive_pressure_adjust_plan, duel_phase_plan,
    flight_movement_plan, give_ball_plan, goal_kick_shape_targets,
    goal_kick_spot, hold_phase_plan, key_pass_for_shot, kickoff_shape_targets,
    must_leave_penalty_area_for_goal_kick, out_of_bounds_plan, pass_arrival_plan,
    pass_control_strength, pass_control_transition, pass_loose_control_strength,
    pass_phase_outcome, pass_phase_plan, pass_receive_plan, pass_trace_payload, player_apply_stun,
    player_move_speed, player_move_tick, player_set_movement_target,
    player_set_movement_target_ref, player_tick_stun, restart_play_decision, restart_play_plan,
    restart_shape_plan, score_block_lane_legacy, score_block_lane_zone, score_goal_plan,
    score_mark_runner_legacy, score_mark_runner_zone, score_tackle, shot_arrival_event,
    shot_arrival_plan, shot_log_entry, shot_log_xg, shot_phase_plan, shot_xg_value,
    team_phase_update, team_shape_plan, team_shape_plan_into, tick_ball_flight, track_carry_stats,
    track_pass_stats, BallFlightFrameInput, BallFlightFrameOutput, CarryPhasePlanInput,
    CarryPhasePlanOutput, CarryStatInput, CarryStatOutput, ClearPhasePlanInput,
    ClearPhasePlanOutput, ClearanceArrivalPlanInput, ClearanceArrivalPlanOutput,
    ContestedTickPlanInput, ContestedTickPlanOutput, DefenseZoneAttackerInput,
    DefenseZoneHelperInput, DefenseZoneHelperOutput, DefensivePressureAdjustDefenderInput,
    DefensivePressureAdjustInput, DefensivePressureAdjustOutput, DefensivePressureAdjustPlanOutput,
    DuelPhasePlanInput, DuelPhasePlanOutput, FlightMovementPlanInput, FlightMovementPlanOutput,
    FlightMovementPlanPlayerOutput, FlightMovementPlayerInput, FlightTickInput, FlightTickOutput,
    GiveBallPlanInput, GiveBallPlanOutput, GoalEventInput, GoalEventOutput, GoalKickPlayerInput,
    GoalKickShapeInput, GoalKickShapeOutput,
    HoldPhasePlanInput, HoldPhasePlanOutput, KeyPassInput, KeyPassOutput, KickoffPlayerInput,
    KickoffShapeInput, KickoffShapeOutput, OutOfBoundsPlanInput, OutOfBoundsPlanOutput,
    PassArrivalPlanInput, PassArrivalPlanOutput, PassControlInput, PassControlOutput,
    PassControlTransitionInput, PassControlTransitionOutput, PassLooseControlInput,
    PassLooseControlOutput, PassPhaseOutcomeInput, PassPhaseOutcomeOutput, PassPhasePlanInput,
    PassPhasePlanOutput, PassReceivePlanInput, PassReceivePlanOutput, PassStatInput,
    PassStatOutput, PassTraceInput, PassTraceOutput, PlayerApplyStunInput, PlayerApplyStunOutput,
    PlayerMoveSpeedInput, PlayerMoveSpeedOutput, PlayerMoveTickInput, PlayerMoveTickOutput,
    PlayerSetMovementTargetInput, PlayerSetMovementTargetOutput, PlayerSetMovementTargetRefOutput,
    PlayerTickStunInput, PlayerTickStunOutput, RestartPlayInput, RestartPlayOutput,
    RestartPlayPlanInput, RestartPlayPlanOutput, RestartPlayerInput, RestartShapePlanInput,
    RestartShapePlanOutput, RestartShapePlanPlayerOutput, RestartShapePlayerInput,
    ScoreGoalPlanInput, ScoreGoalPlanOutput, ShotArrivalEventInput, ShotArrivalEventOutput,
    ShotArrivalPlanInput, ShotArrivalPlanOutput, ShotLogEntryInput, ShotLogEntryOutput,
    ShotLogXgInput, ShotLogXgOutput, ShotPhasePlanInput, ShotPhasePlanOutput, ShotXgInput,
    ShotXgOutput, TackleScoreInput, TackleScoreOutput, TeamPhaseUpdateInput, TeamPhaseUpdateOutput,
    TeamShapeOpponentInput, TeamShapePlanInput, TeamShapePlanOutput, TeamShapePlayerInput,
    TeamShapePlayerOutput,
};
pub use match_runner::{run_match_v2, MatchV2RunRequest, MatchV2RunResponse};
pub use off_ball_attack::{
    choose_off_ball_attack_target, choose_off_ball_attack_target_from_scored,
    generate_off_ball_attack_anchor_candidates, generate_off_ball_attack_anchor_candidates_into,
    generate_off_ball_attack_raw_candidates, generate_off_ball_attack_raw_candidates_into,
    generate_off_ball_attack_support_candidates, generate_off_ball_attack_support_candidates_into,
    off_ball_attack_components_from_scored, score_off_ball_attack_candidates,
    score_off_ball_attack_candidates_into,
    OffBallAttackBatchInput, OffBallAttackCandidateInput, OffBallAttackCandidateOutput,
    OffBallAttackChoiceComponents, OffBallAttackChoiceInput, OffBallAttackChoiceOutput,
    OffBallAttackGoalInput, OffBallRawGenerationInput, OffBallTeammateInput, RandomPolarSample,
    MAX_FIXED_OFF_BALL_ATTACK_CANDIDATES,
};
pub use off_ball_defense::{
    best_fixed_team_defense_candidate, choose_defense_action, generate_defense_raw_candidates,
    prepare_defense_choice, prepared_defense_choice_random_branch, score_defense_candidates,
    select_prepared_defense_action, DefenseChoiceInput, DefenseChoiceOutput, DefensePreparedChoice,
    DefenseRandomSample, DefenseRawInput, DefenseScoreInput, DefenseScoreOutput,
    DefenseTeammateInput,
};
pub use offside::{get_offside_line, is_offside_position, OpponentLineInput};
pub use on_ball::{
    carry_batch_value_context, evaluate_carry, evaluate_carry_path, evaluate_carry_with_context,
    evaluate_clear, evaluate_hold, evaluate_shot, finalize_carry_score, generate_carry_offsets,
    generate_carry_offsets_into, CarryBatchValueContext, CarryBatchValueContextInput,
    CarryFinalizeInput, CarryFinalizeOutput, CarryInput, CarryOutput, CarryPathInput,
    CarryPathOpponentInput, CarryPathOutput, CarrySupportPlayer, CarryTargetGenerationInput,
    CarryTargetGenerationOutput, ClearInput, ClearOutput, HoldInput, HoldOutput, ShotInput,
    ShotOutput, MAX_CARRY_TARGET_OFFSETS,
};
pub use pass_space::{
    box_delivery_targets, delivery_space_targets, evaluate_raw_pass_target_prevalue,
    generic_pass_space_candidates, layoff_targets, receiver_base_pass_targets,
    receiver_pass_candidates_batch, receiver_spatial_candidates, score_raw_pass_target,
    second_line_targets, stale_release_targets, team_pass_candidates_batch,
    team_pass_candidates_batch_into, team_pass_candidates_batch_into_with_workspace,
    value_field_raw_targets, BoxDeliveryTargetsInput,
    DeliverySpaceTargetsInput, GenericPassSpaceCandidate, GenericPassSpaceInput,
    LayoffTargetsInput, PassRiskPlayer, PassSpacePlayer, PassTeamPlayer, RawPassPreValueInput,
    RawPassPreValueOutput, RawPassTarget, RawPassValueInput, RawPassValueOutput,
    ReceiverBaseTargetsInput, ReceiverBaseTargetsOutput, ReceiverGoalInput, ReceiverPassBatchInput,
    ReceiverPassCandidate, ReceiverSpatialCandidate, ReceiverSpatialCandidatesInput,
    SecondLineTargetsInput, StaleReleaseTargetsInput, TeamPassBatchInput, TeamPassCandidate,
    TeamPassWorkspace,
    ValueFieldRawTarget, ValueFieldTargetsInput, EMPTY_TEAM_PASS_CANDIDATE,
    MAX_PASS_CANDIDATES_PER_RECEIVER, MAX_TEAM_PASS_CANDIDATES,
};
pub use pass_value::{
    expected_pass_value, pass_lane_risk, pass_retention_probability, receiver_pressure,
    turnover_consequence, ExpectedPassInput, ExpectedPassOutput, PassLaneRiskInput,
    TurnoverConsequenceInput,
};
pub use physics::{
    angle_between_points, angle_diff, angle_to_goal, clamp, direction, distance, interpolate,
    is_attacking_box_pos, is_in_fov, midpoint, move_toward, out_of_bounds_restart, player_speed,
    point_along, residual_ball_velocity, segment_pitch_boundary_crossing, smoothstep,
    PitchBoundaryCrossing, PitchBoundaryKind,
};
pub use position_value::{
    defensive_position_value, position_value, protection_value, receive_reachability,
    space_creation_value, DefensivePositionValueInput, PositionValueInput,
};
pub use possession_control::{
    continuation_control_readiness, observe_possession_control, shot_release_readiness,
    transition_possession_control, PossessionControlObservation, PossessionControlState,
    PossessionControlTransitionInput,
};
pub use shot_quality::{
    estimate_goalkeeper_save_probability, estimate_shot_contest, estimate_shot_outcome,
    expected_goalkeeper_save_probability, resolve_shot_contest, shot_contest_intent,
    shot_quality_at, ShotContestDefender, ShotContestEstimate, ShotContestIntent,
    ShotContestResolution, ShotOutcomeEstimate, ShotQualityInput,
};
pub use state_value::{
    pass_receive_value, pass_receive_value_breakdown, possession_state_value,
    possession_state_value_with_context, possession_value_context, state_value,
    PassReceiveValueBreakdown, PassReceiveValueInput, PlayerShotProfile, PossessionStateValue,
    PossessionValueContext, StateValueInput,
};
pub use tactical_task::{
    accept_task, coordinate_team_spatial_tasks_into, formation_debt, observe_entities_into,
    spatial_claim_conflict, spatial_claim_for_task, task_intent_from_goal, task_motion_target,
    task_policy_utility, update_player_belief, BelievedEntity, GoalProposal, PlayerBelief,
    PlayerObservation, SpatialClaim, TacticalTask, TacticalTaskCoordination, TacticalTaskIntent,
    TacticalTaskPhase, TaskAcceptance, TaskAcceptanceInput, TaskMotionInput,
    TeamSpatialAssignment, TeamSpatialAssignmentInput, TeamSpatialCandidate,
    TeamSpatialCoordinationSummary, TeamSpatialPlayerInput, VisibleEntity,
    MAX_FIXED_TEAM_TACTICAL_TASKS, MAX_PLAYER_OBSERVED_ENTITIES, MAX_TASK_OUTLET_COVERAGE,
};
pub use team_plan::{
    project_team_plan_formation, project_team_plan_formation_into, select_team_plan,
    team_plan_action_utility, team_plan_features, team_plan_movement_target, team_plan_signals,
    update_team_plan, TeamPlanActionInput, TeamPlanActionUtility, TeamPlanCandidate,
    TeamPlanFeatures, TeamPlanFormationProjection, TeamPlanFormationProjectionInput, TeamPlanKind,
    TeamPlanOpponentInput, TeamPlanPlayerInput, TeamPlanProjectionPlayerInput,
    TeamPlanProjectionPlayerOutput, TeamPlanSignals, TeamPlanState, TeamPlanUpdateInput,
    TeamPlanUpdateOutput,
};
pub use vision::{
    build_vision_context, compute_facing_direction, compute_fov, compute_player_facing,
    compute_vision_distance, get_visible_target_indices, is_target_visible, VisionContext,
    VisionContextInput,
};
