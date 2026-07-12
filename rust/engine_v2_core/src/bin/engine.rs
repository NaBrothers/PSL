use std::io::{self, BufRead};

use psl_engine_v2_core::{
    angle_between_points, angle_diff, angle_to_goal, apply_generic_on_ball_goal_continuity,
    apply_iq_noise_score, apply_specialized_on_ball_bias, apply_support_opportunity_cost,
    box_delivery_targets, build_ball_flight_frame, build_defensive_goal, build_goal_event,
    build_off_ball_attack_goal, carry_phase_plan, choose_defense_action, choose_distribution,
    choose_fallback_target, choose_off_ball_attack_target, clamp, clear_phase_plan,
    clearance_arrival_plan, compute_facing_direction, compute_fov, compute_gk_save_probability,
    compute_player_facing, compute_vision_distance, contested_tick_plan, defensive_position_value,
    defensive_pressure_adjust_plan, delivery_space_targets, detect_duel, detect_interception,
    detect_wasted_tackle, direction, distance, duel_phase_plan, evaluate_arc_arrival_goal,
    evaluate_attack_far_post_goal, evaluate_byline_delivery_goal, evaluate_carry,
    evaluate_carry_path, evaluate_clear, evaluate_cut_inside_goal, evaluate_drive_byline_goal,
    evaluate_hold, evaluate_hold_opportunity_goal, evaluate_layoff_goal,
    evaluate_raw_pass_target_prevalue, evaluate_release_support_goal, evaluate_shot,
    evaluate_through_ball_goal, evaluate_wide_hold_overlap_goal, execute_carry, execute_clear,
    execute_hold, execute_pass, execute_shot, expected_pass_value, finalize_carry_score,
    flight_movement_plan, generate_carry_offsets, generate_clear_target,
    generate_defense_raw_candidates, generate_off_ball_attack_raw_candidates,
    generic_pass_space_candidates, get_offside_line, get_visible_target_indices, give_ball_plan,
    gk_position_adjust, goal_kick_shape_targets, goal_kick_spot, goal_selection_noise_from_gauss,
    goal_switch_cost, hold_phase_plan, interception_chance, interpolate, iq_temperature_factor,
    is_attacking_box_pos, is_in_fov, is_offside_position, is_target_visible, key_pass_for_shot,
    kickoff_shape_targets, layoff_targets, midpoint, move_toward,
    must_leave_penalty_area_for_goal_kick, out_of_bounds_plan, out_of_bounds_restart,
    pass_arrival_plan, pass_control_strength, pass_lane_risk, pass_loose_control_strength,
    pass_phase_outcome, pass_phase_plan, pass_receive_plan, pass_receive_value,
    pass_receive_value_breakdown, pass_trace_payload, player_apply_stun, player_move_speed,
    player_move_tick, player_set_movement_target, player_speed, player_tick_stun, point_along,
    position_value, receive_reachability, receiver_base_pass_targets,
    receiver_pass_candidates_batch, receiver_pressure, receiver_spatial_candidates,
    residual_ball_velocity, resolve_clearance_arrival, resolve_contested_owner, resolve_duel,
    resolve_first_touch, resolve_interception, resolve_pass_arrival, resolve_shot_arrival,
    restart_play_decision, restart_play_plan, restart_shape_plan, run_match_v2,
    score_block_lane_legacy, score_block_lane_zone, score_defense_candidates, score_goal_plan,
    score_mark_runner_legacy, score_mark_runner_zone, score_off_ball_attack_candidates,
    score_raw_pass_target, score_tackle, second_line_targets, select_best_arriving_support,
    select_best_byline_carry, select_best_layoff, select_best_overlap, select_contested_targets,
    select_goal_candidate_with_gaussians, select_goal_deterministic, select_hold_support,
    select_on_ball_candidate, shot_arrival_event, shot_arrival_plan, shot_log_entry, shot_log_xg,
    shot_phase_plan, shot_quality_at, shot_xg_value, should_rush_out, smoothstep,
    softmax_select_index, softmax_select_index_with_temperature, space_creation_value,
    stale_release_targets, state_value, team_pass_candidates_batch, team_phase_update,
    team_shape_plan, tick_ball_flight, tick_contested_ball, track_carry_stats,
    track_defensive_pressures, track_pass_stats, turnover_consequence, value_field_raw_targets,
    ArcArrivalGoalInput, ArrivalPlayerInput, ArrivingSupportPassInput,
    ArrivingSupportSelectionInput, AttackFarPostGoalInput, BallFlightFrameInput,
    BoxDeliveryTargetsInput, BylineCarryInput, BylineCarrySelectionInput, BylineDeliveryGoalInput,
    BylineSupportTeammateInput, CarryExecutionInput, CarryFinalizeInput, CarryInput,
    CarryPathInput, CarryPathOpponentInput, CarryPhasePlanInput, CarryStatInput,
    CarrySupportPlayer, CarryTargetGenerationInput, ClearExecutionInput, ClearInput,
    ClearPhasePlanInput, ClearTargetInput, ClearanceArrivalInput, ClearanceArrivalPlanInput,
    ClearancePlayerInput, ContestedOwnerInput, ContestedOwnerPlayerInput,
    ContestedTargetPlayerInput, ContestedTargetsInput, ContestedTickInput, ContestedTickPlanInput,
    CutInsideGoalInput, DefenderActionInput, DefenseChoiceInput, DefenseRandomSample,
    DefenseRawInput, DefenseScoreInput, DefenseTeammateInput, DefenseZoneAttackerInput,
    DefenseZoneHelperInput, DefensiveGoalBuildInput, DefensivePositionValueInput,
    DefensivePressureAdjustDefenderInput, DefensivePressureAdjustInput, DefensivePressureInput,
    DeliverySpaceTargetsInput, DriveBylineGoalInput, DuelDetectionInput, DuelPhasePlanInput,
    DuelResolveInput, ExecutionOpponent, ExpectedPassInput, FirstTouchInput,
    FlightMovementPlanInput, FlightMovementPlayerInput, FlightTickInput, GenericPassSpaceCandidate,
    GenericPassSpaceInput, GiveBallPlanInput, GkDistributionInput, GkFallbackTargetInput,
    GkPositionAdjustInput, GkRushInput, GkSaveInput, GoalEventInput, GoalInput,
    GoalKickPlayerInput, GoalKickShapeInput, GoalSwitchCostInput, HoldExecutionInput, HoldInput,
    HoldOpportunityGoalInput, HoldPhasePlanInput, HoldSupportCarryInput, HoldSupportHoldInput,
    HoldSupportPassInput, HoldSupportSelectionInput, InterceptionDetectionInput,
    InterceptionResolveInput, IqNoiseScoreInput, KeyPassInput, KickoffPlayerInput,
    KickoffShapeInput, LayoffGoalInput, LayoffPassInput, LayoffSelectionInput, LayoffTargetsInput,
    MatchV2RunRequest, OffBallAttackBatchInput, OffBallAttackCandidateInput,
    OffBallAttackChoiceInput, OffBallAttackGoalBuildInput, OffBallAttackGoalInput,
    OffBallRawGenerationInput, OffBallTeammateInput, OnBallGenericCandidateInput,
    OnBallGenericContinuityInput, OnBallGenericGoalInput, OnBallSelectionCandidateInput,
    OnBallSelectionInput, OnBallSpecializedBiasCandidateInput, OnBallSpecializedBiasInput,
    OpponentLineInput, OutOfBoundsPlanInput, OverlapPassInput, OverlapSelectionInput,
    PassArrivalInput, PassArrivalPlanInput, PassControlInput, PassExecutionInput,
    PassLaneRiskInput, PassLooseControlInput, PassPhaseOutcomeInput, PassPhasePlanInput,
    PassReceivePlanInput, PassReceiveValueInput, PassRiskPlayer, PassSpacePlayer, PassStatInput,
    PassTeamPlayer, PassTraceInput, PlayerApplyStunInput, PlayerMoveSpeedInput,
    PlayerMoveTickInput, PlayerSetMovementTargetInput, PlayerTickStunInput, PositionValueInput,
    RandomPolarSample, RawPassPreValueInput, RawPassValueInput, ReceiverBaseTargetsInput,
    ReceiverGoalInput, ReceiverPassBatchInput, ReceiverSpatialCandidatesInput,
    ReleaseSupportGoalInput, RestartPlayInput, RestartPlayPlanInput, RestartPlayerInput,
    RestartShapePlanInput, RestartShapePlayerInput, ScoreGoalPlanInput, SecondLineTargetsInput,
    ShotArrivalEventInput, ShotArrivalInput, ShotArrivalPlanInput, ShotExecutionInput, ShotInput,
    ShotLogEntryInput, ShotLogXgInput, ShotPhasePlanInput, ShotQualityInput, ShotSupportPlayer,
    ShotXgInput, StaleReleaseTargetsInput, StateValueInput, SupportOpportunityCarryInput,
    SupportOpportunityInput, SupportOpportunityPassInput, TackleScoreInput, TeamPhaseUpdateInput,
    TeamShapeOpponentInput, TeamShapePlanInput, TeamShapePlayerInput, ThroughBallGoalInput,
    TurnoverConsequenceInput, ValueFieldTargetsInput, VisionContext, VisionContextInput,
    WastedTackleInput, WideHoldOverlapGoalInput,
};

fn parse_positions(raw: &str) -> Result<Vec<(f64, f64)>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let (x, y) = part
                .split_once(',')
                .ok_or_else(|| format!("invalid position: {part}"))?;
            Ok((
                x.parse::<f64>().map_err(|err| err.to_string())?,
                y.parse::<f64>().map_err(|err| err.to_string())?,
            ))
        })
        .collect()
}

fn parse_defense_zone_attackers(raw: &str) -> Result<Vec<DefenseZoneAttackerInput>, String> {
    Ok(parse_positions(raw)?
        .into_iter()
        .map(|pos| DefenseZoneAttackerInput { pos })
        .collect())
}

fn parse_runner(x: &str, y: &str) -> Result<Option<(f64, f64)>, String> {
    if x == "-" || y == "-" {
        return Ok(None);
    }
    Ok(Some((
        x.parse::<f64>().map_err(|err| err.to_string())?,
        y.parse::<f64>().map_err(|err| err.to_string())?,
    )))
}

fn parse_indexed_positions(raw: &str) -> Result<Vec<(usize, f64, f64)>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid indexed position: {part}"));
            }
            Ok((
                fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                fields[2].parse::<f64>().map_err(|err| err.to_string())?,
            ))
        })
        .collect()
}

fn format_usize_list(values: &[usize]) -> String {
    if values.is_empty() {
        return "-".to_string();
    }
    values
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn parse_opponent_line_inputs(raw: &str) -> Result<Vec<OpponentLineInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 2 {
                return Err(format!("invalid opponent line input: {part}"));
            }
            Ok(OpponentLineInput {
                x: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                is_goalkeeper: fields[1] == "1",
            })
        })
        .collect()
}

fn parse_pass_space_players(raw: &str) -> Result<Vec<PassSpacePlayer>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 11 {
                return Err(format!("invalid pass space player: {part}"));
            }
            Ok(PassSpacePlayer {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tactical_anchor: (
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[7] == "1",
                is_defender: fields[8] == "1",
                is_midfielder: fields[9] == "1",
                is_wide: fields[10] == "1",
            })
        })
        .collect()
}

fn parse_generic_pass_space_candidates(
    raw: &str,
) -> Result<Vec<GenericPassSpaceCandidate>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 5 {
                return Err(format!("invalid generic pass space candidate: {part}"));
            }
            Ok(GenericPassSpaceCandidate {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                visibility: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                position_value: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_pass_risk_players(raw: &str) -> Result<Vec<PassRiskPlayer>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 5 {
                return Err(format!("invalid pass risk player: {part}"));
            }
            Ok(PassRiskPlayer {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                speed: fields[3].parse::<i32>().map_err(|err| err.to_string())?,
                is_goalkeeper: fields[4] == "1",
            })
        })
        .collect()
}

fn parse_pass_team_players(raw: &str) -> Result<Vec<PassTeamPlayer<'static>>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 20 {
                return Err(format!("invalid pass team player: {part}"));
            }
            let goal = if fields[17] == "-" {
                None
            } else {
                Some(ReceiverGoalInput {
                    goal_type: Box::leak(fields[17].to_string().into_boxed_str()),
                    target_pos: (
                        fields[18].parse::<f64>().map_err(|err| err.to_string())?,
                        fields[19].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: fields[16].parse::<f64>().map_err(|err| err.to_string())?,
                })
            };
            Ok(PassTeamPlayer {
                space: PassSpacePlayer {
                    index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                    pos: (
                        fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                        fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    target_pos: (
                        fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                        fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    tactical_anchor: (
                        fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                        fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    is_goalkeeper: fields[7] == "1",
                    is_defender: fields[13] == "1",
                    is_midfielder: fields[14] == "1",
                    is_wide: fields[15] == "1",
                },
                risk: PassRiskPlayer {
                    index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                    pos: (
                        fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                        fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    speed: fields[8].parse::<i32>().map_err(|err| err.to_string())?,
                    is_goalkeeper: fields[7] == "1",
                },
                finishing: fields[9].parse::<f64>().map_err(|err| err.to_string())?,
                long_shot: fields[10].parse::<f64>().map_err(|err| err.to_string())?,
                base: (
                    fields[11].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[12].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_defender: fields[13] == "1",
                goal,
            })
        })
        .collect()
}

fn parse_f64_list(raw: &str) -> Result<Vec<f64>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(',')
        .map(|part| part.parse::<f64>().map_err(|err| err.to_string()))
        .collect()
}

fn parse_usize_list(raw: &str) -> Result<Vec<usize>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(',')
        .map(|part| part.parse::<usize>().map_err(|err| err.to_string()))
        .collect()
}

fn parse_on_ball_selection_candidates(
    raw: &str,
) -> Result<Vec<OnBallSelectionCandidateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 6 {
                return Err(format!("invalid on-ball selection candidate: {part}"));
            }
            Ok(OnBallSelectionCandidateInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                action_code: fields[1].parse::<u8>().map_err(|err| err.to_string())?,
                target_kind_space: fields[2] == "1",
                success_prob: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_pressure: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                high_threat_space: fields[5].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_on_ball_generic_candidates(raw: &str) -> Result<Vec<OnBallGenericCandidateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 10 {
                return Err(format!("invalid on-ball generic candidate: {part}"));
            }
            Ok(OnBallGenericCandidateInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                action_code: fields[1].parse::<u8>().map_err(|err| err.to_string())?,
                target: parse_runner(fields[2], fields[3])?,
                progress_gain: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                xg: fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                pressure: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_pressure: fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                target_kind_space: fields[8] == "1",
                lateral_change: fields[9].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_on_ball_specialized_candidates(
    raw: &str,
) -> Result<Vec<OnBallSpecializedBiasCandidateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 14 {
                return Err(format!("invalid on-ball specialized candidate: {part}"));
            }
            Ok(OnBallSpecializedBiasCandidateInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                action_code: fields[1].parse::<u8>().map_err(|err| err.to_string())?,
                target: parse_runner(fields[2], fields[3])?,
                carry_to_shoot_window: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                wide_second_line_carry_window: fields[5]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                future_shot_gain: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                byline_carry_window: fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                xg: fields[8].parse::<f64>().map_err(|err| err.to_string())?,
                shot_readiness: fields[9].parse::<f64>().map_err(|err| err.to_string())?,
                open_medium_window: fields[10].parse::<f64>().map_err(|err| err.to_string())?,
                clean_second_line_shot: fields[11].parse::<f64>().map_err(|err| err.to_string())?,
                space_manipulation: fields[12].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_draw: fields[13].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

#[derive(Clone, Debug)]
struct OnBallFullCandidate {
    score: f64,
    action_code: u8,
    target: Option<(f64, f64)>,
    target_kind_space: bool,
    success_prob: f64,
    receiver_pressure: f64,
    high_threat_space: f64,
    progress_gain: f64,
    xg: f64,
    pressure: f64,
    lateral_change: f64,
    carry_to_shoot_window: f64,
    wide_second_line_carry_window: f64,
    future_shot_gain: f64,
    byline_carry_window: f64,
    shot_readiness: f64,
    open_medium_window: f64,
    clean_second_line_shot: f64,
    space_manipulation: f64,
    pressure_draw: f64,
    target_progress: f64,
    centrality: f64,
    final_third_combination: f64,
    lane_risk: f64,
    second_line_arrival_value: f64,
    second_line_cutback_value: f64,
    layoff_support_value: f64,
    short_combination_value: f64,
    layoff_retention_value: f64,
    receiver_goal_fit: f64,
    opportunity_wait: f64,
    opportunity_wait_value: f64,
    no_clear_release: f64,
    path_feasibility: f64,
}

#[derive(Clone, Debug)]
struct OnBallFullGoal {
    goal_type: String,
    target_pos: (f64, f64),
    value: f64,
    confidence: f64,
    phase: String,
    created_tick: i32,
    candidate_noise: f64,
    candidate_noisy_value: f64,
}

fn parse_on_ball_full_candidates(raw: &str) -> Result<Vec<OnBallFullCandidate>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 35 {
                return Err(format!("invalid on-ball full candidate: {part}"));
            }
            Ok(OnBallFullCandidate {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                action_code: fields[1].parse::<u8>().map_err(|err| err.to_string())?,
                target: parse_runner(fields[2], fields[3])?,
                target_kind_space: fields[4] == "1",
                success_prob: fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_pressure: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                high_threat_space: fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                progress_gain: fields[8].parse::<f64>().map_err(|err| err.to_string())?,
                xg: fields[9].parse::<f64>().map_err(|err| err.to_string())?,
                pressure: fields[10].parse::<f64>().map_err(|err| err.to_string())?,
                lateral_change: fields[11].parse::<f64>().map_err(|err| err.to_string())?,
                carry_to_shoot_window: fields[12].parse::<f64>().map_err(|err| err.to_string())?,
                wide_second_line_carry_window: fields[13]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                future_shot_gain: fields[14].parse::<f64>().map_err(|err| err.to_string())?,
                byline_carry_window: fields[15].parse::<f64>().map_err(|err| err.to_string())?,
                shot_readiness: fields[16].parse::<f64>().map_err(|err| err.to_string())?,
                open_medium_window: fields[17].parse::<f64>().map_err(|err| err.to_string())?,
                clean_second_line_shot: fields[18].parse::<f64>().map_err(|err| err.to_string())?,
                space_manipulation: fields[19].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_draw: fields[20].parse::<f64>().map_err(|err| err.to_string())?,
                target_progress: fields[21].parse::<f64>().map_err(|err| err.to_string())?,
                centrality: fields[22].parse::<f64>().map_err(|err| err.to_string())?,
                final_third_combination: fields[23]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                lane_risk: fields[24].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_arrival_value: fields[25]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                second_line_cutback_value: fields[26]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                layoff_support_value: fields[27].parse::<f64>().map_err(|err| err.to_string())?,
                short_combination_value: fields[28]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                layoff_retention_value: fields[29].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_fit: fields[30].parse::<f64>().map_err(|err| err.to_string())?,
                opportunity_wait: fields[31].parse::<f64>().map_err(|err| err.to_string())?,
                opportunity_wait_value: fields[32].parse::<f64>().map_err(|err| err.to_string())?,
                no_clear_release: fields[33].parse::<f64>().map_err(|err| err.to_string())?,
                path_feasibility: fields[34].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn full_selection_candidates(
    candidates: &[OnBallFullCandidate],
) -> Vec<OnBallSelectionCandidateInput> {
    candidates
        .iter()
        .map(|candidate| OnBallSelectionCandidateInput {
            score: candidate.score,
            action_code: candidate.action_code,
            target_kind_space: candidate.target_kind_space,
            success_prob: candidate.success_prob,
            receiver_pressure: candidate.receiver_pressure,
            high_threat_space: candidate.high_threat_space,
        })
        .collect()
}

fn full_generic_candidates(
    candidates: &[OnBallFullCandidate],
    scores: &[f64],
) -> Vec<OnBallGenericCandidateInput> {
    candidates
        .iter()
        .enumerate()
        .map(|(idx, candidate)| OnBallGenericCandidateInput {
            score: scores.get(idx).copied().unwrap_or(candidate.score),
            action_code: candidate.action_code,
            target: candidate.target,
            progress_gain: candidate.progress_gain,
            xg: candidate.xg,
            pressure: candidate.pressure,
            receiver_pressure: candidate.receiver_pressure,
            target_kind_space: candidate.target_kind_space,
            lateral_change: candidate.lateral_change,
        })
        .collect()
}

fn full_specialized_candidates(
    candidates: &[OnBallFullCandidate],
    scores: &[f64],
) -> Vec<OnBallSpecializedBiasCandidateInput> {
    candidates
        .iter()
        .enumerate()
        .map(|(idx, candidate)| OnBallSpecializedBiasCandidateInput {
            score: scores.get(idx).copied().unwrap_or(candidate.score),
            action_code: candidate.action_code,
            target: candidate.target,
            carry_to_shoot_window: candidate.carry_to_shoot_window,
            wide_second_line_carry_window: candidate.wide_second_line_carry_window,
            future_shot_gain: candidate.future_shot_gain,
            byline_carry_window: candidate.byline_carry_window,
            xg: candidate.xg,
            shot_readiness: candidate.shot_readiness,
            open_medium_window: candidate.open_medium_window,
            clean_second_line_shot: candidate.clean_second_line_shot,
            space_manipulation: candidate.space_manipulation,
            pressure_draw: candidate.pressure_draw,
        })
        .collect()
}

fn parse_support_opportunity_passes(raw: &str) -> Result<Vec<SupportOpportunityPassInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 5 {
                return Err(format!("invalid support opportunity pass: {part}"));
            }
            Ok(SupportOpportunityPassInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_fit: fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_arrival_value: fields[2]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                second_line_cutback_value: fields[3]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                layoff_support_value: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_support_opportunity_carries(
    raw: &str,
) -> Result<Vec<SupportOpportunityCarryInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid support opportunity carry: {part}"));
            }
            Ok(SupportOpportunityCarryInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                future_shot_gain: fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                carry_to_shoot_window: fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                effective_gain: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_overlap_passes(raw: &str) -> Result<Vec<OverlapPassInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid overlap pass: {part}"));
            }
            Ok(OverlapPassInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_pressure: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_layoff_passes(raw: &str) -> Result<Vec<LayoffPassInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid layoff pass: {part}"));
            }
            Ok(LayoffPassInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_pressure: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_arriving_support_passes(raw: &str) -> Result<Vec<ArrivingSupportPassInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 7 {
                return Err(format!("invalid arriving-support pass: {part}"));
            }
            Ok(ArrivingSupportPassInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_goal_fit: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_arrival_value: fields[4]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                second_line_cutback_value: fields[5]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                layoff_support_value: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_hold_support_passes(raw: &str) -> Result<Vec<HoldSupportPassInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 8 {
                return Err(format!("invalid hold-support pass: {part}"));
            }
            Ok(HoldSupportPassInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                layoff_support_value: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                short_combination_value: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_cutback_value: fields[5]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                layoff_retention_value: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_fit: fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_arrival_value: 0.0,
            })
        })
        .collect()
}

fn parse_hold_support_carries(raw: &str) -> Result<Vec<HoldSupportCarryInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid hold-support carry: {part}"));
            }
            Ok(HoldSupportCarryInput {
                carry_to_shoot_window: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                wide_second_line_carry_window: fields[1]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                future_shot_gain: fields[2].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_hold_support_holds(raw: &str) -> Result<Vec<HoldSupportHoldInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid hold-support hold: {part}"));
            }
            Ok(HoldSupportHoldInput {
                opportunity_wait: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                opportunity_wait_value: fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                no_clear_release: fields[2].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_off_ball_candidates(raw: &str) -> Result<Vec<OffBallAttackCandidateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid off-ball candidate: {part}"));
            }
            Ok(OffBallAttackCandidateInput {
                pos: (
                    fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                anchor_pos: (
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
            })
        })
        .collect()
}

fn parse_random_polar_samples(raw: &str) -> Result<Vec<RandomPolarSample>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 2 {
                return Err(format!("invalid random polar sample: {part}"));
            }
            Ok(RandomPolarSample {
                angle_unit: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                radius_unit: fields[1].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_off_ball_teammates(raw: &str) -> Result<Vec<OffBallTeammateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 8 {
                return Err(format!("invalid off-ball teammate: {part}"));
            }
            Ok(OffBallTeammateInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tactical_anchor: (
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[7] == "1",
            })
        })
        .collect()
}

fn parse_defense_teammates(raw: &str) -> Result<Vec<DefenseTeammateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid defense teammate: {part}"));
            }
            Ok(DefenseTeammateInput {
                pos: (
                    fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
            })
        })
        .collect()
}

fn parse_defense_random_samples(raw: &str) -> Result<Vec<DefenseRandomSample>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 2 {
                return Err(format!("invalid defense random sample: {part}"));
            }
            Ok(DefenseRandomSample {
                angle_unit: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                radius_unit: fields[1].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn format_team_pass_candidates(
    values: &[psl_engine_v2_core::TeamPassCandidate],
    detailed: bool,
) -> String {
    if values.is_empty() {
        return "-".to_string();
    }
    values
        .iter()
        .map(|value| {
            if detailed {
                format!(
                    "{},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{},{},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{},{:.15},{:.15},{:.15},{:.15},{:.15}",
                    value.receiver_index,
                    value.target.0,
                    value.target.1,
                    value.score,
                    value.raw_score,
                    value.success_prob,
                    value.risk_cost,
                    value.after_value,
                    value.effective_delta,
                    value.continuity,
                    value.lane_risk,
                    value.receiver_pressure,
                    value.turnover_consequence,
                    value.receiver_arrival,
                    value.base_accuracy,
                    value.goal_target_fit,
                    value.distance,
                    if value.is_long { "1" } else { "0" },
                    if value.target_kind_space { "1" } else { "0" },
                    value.perception,
                    value.perception_multiplier,
                    value.arrival_margin,
                    value.defender_first_risk,
                    value.target_occupation_risk,
                    value.nearest_teammate_to_target,
                    value.nearest_opp_to_target,
                    value.box_space_pressure,
                    if value.tactical_space { "1" } else { "0" },
                    value.tactical_space_prior,
                    value.tactical_space_value,
                    value.tactical_space_visibility,
                    value.expected_arrival_confidence,
                    value.expected_arrival_fit
                )
            } else {
                format!(
                    "{},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{},{}",
                    value.receiver_index,
                    value.target.0,
                    value.target.1,
                    value.score,
                    value.raw_score,
                    value.success_prob,
                    value.receiver_arrival,
                    value.base_accuracy,
                    value.goal_target_fit,
                    value.distance,
                    if value.is_long { "1" } else { "0" },
                    if value.target_kind_space { "1" } else { "0" }
                )
            }
        })
        .collect::<Vec<_>>()
        .join(";")
}

fn parse_shot_support(raw: &str) -> Result<Vec<ShotSupportPlayer>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 6 {
                return Err(format!("invalid shot support player: {part}"));
            }
            Ok(ShotSupportPlayer {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[5] == "1",
            })
        })
        .collect()
}

fn parse_carry_support(raw: &str) -> Result<Vec<CarrySupportPlayer>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 6 {
                return Err(format!("invalid carry support player: {part}"));
            }
            Ok(CarrySupportPlayer {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                base: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[5] == "1",
            })
        })
        .collect()
}

fn parse_carry_path_opponents(raw: &str) -> Result<Vec<CarryPathOpponentInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 6 {
                return Err(format!("invalid carry path opponent: {part}"));
            }
            Ok(CarryPathOpponentInput {
                pos: (
                    fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                speed: fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                defence: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                tackling: fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                is_goalkeeper: fields[5] == "1",
            })
        })
        .collect()
}

fn parse_defender_actions(raw: &str) -> Result<Vec<DefenderActionInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 8 && fields.len() != 9 {
                return Err(format!("invalid defender action: {part}"));
            }
            Ok(DefenderActionInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                new_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                action: fields[5].to_string(),
                speed: fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                defence: fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                is_goalkeeper: fields.get(8).copied() == Some("1"),
            })
        })
        .collect()
}

fn parse_execution_opponents(raw: &str) -> Result<Vec<ExecutionOpponent>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid execution opponent: {part}"));
            }
            Ok(ExecutionOpponent {
                pos: (
                    fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[2] == "1",
            })
        })
        .collect()
}

fn parse_arrival_players(raw: &str) -> Result<Vec<ArrivalPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 11 {
                return Err(format!("invalid arrival player: {part}"));
            }
            let current_goal_pos = parse_runner(fields[5], fields[6])?;
            Ok(ArrivalPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                current_goal_pos,
                speed: fields[7].parse::<i32>().map_err(|err| err.to_string())?,
                is_passer: fields[8] == "1",
                is_intended: fields[9] == "1",
                is_passer_team: fields[10] == "1",
            })
        })
        .collect()
}

fn parse_clearance_players(raw: &str) -> Result<Vec<ClearancePlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid clearance player: {part}"));
            }
            Ok(ClearancePlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
            })
        })
        .collect()
}

fn parse_contested_owner_players(raw: &str) -> Result<Vec<ContestedOwnerPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid contested owner player: {part}"));
            }
            Ok(ContestedOwnerPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
            })
        })
        .collect()
}

fn parse_contested_target_players(raw: &str) -> Result<Vec<ContestedTargetPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 9 {
                return Err(format!("invalid contested target player: {part}"));
            }
            Ok(ContestedTargetPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tactical_anchor: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[5] == "1",
                is_stunned: fields[6] == "1",
                speed: fields[7].parse::<i32>().map_err(|err| err.to_string())?,
                iq: fields[8].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_byline_teammates(raw: &str) -> Result<Vec<BylineSupportTeammateInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 8 {
                return Err(format!("invalid byline teammate: {part}"));
            }
            Ok(BylineSupportTeammateInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                anchor: (
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[7] == "1",
            })
        })
        .collect()
}

fn parse_byline_carries(raw: &str) -> Result<Vec<BylineCarryInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid byline carry: {part}"));
            }
            Ok(BylineCarryInput {
                score: fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                target: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                byline_carry_window: fields[3].parse::<f64>().map_err(|err| err.to_string())?,
            })
        })
        .collect()
}

fn parse_kickoff_players(raw: &str) -> Result<Vec<KickoffPlayerInput<'static>>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 9 {
                return Err(format!("invalid kickoff player: {part}"));
            }
            let position = match fields[8] {
                "ST" => "ST",
                "CF" => "CF",
                "LW" => "LW",
                "RW" => "RW",
                "LF" => "LF",
                "RF" => "RF",
                "LS" => "LS",
                "RS" => "RS",
                "GK" => "GK",
                "CM" => "CM",
                "LCM" => "LCM",
                "RCM" => "RCM",
                "CDM" => "CDM",
                "CAM" => "CAM",
                "LM" => "LM",
                "RM" => "RM",
                "CB" => "CB",
                "LCB" => "LCB",
                "RCB" => "RCB",
                "LB" => "LB",
                "RB" => "RB",
                "LWB" => "LWB",
                "RWB" => "RWB",
                _ => "CM",
            };
            Ok(KickoffPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                team_is_restart: fields[1] == "1",
                attacking_right: fields[2] == "1",
                base_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                current_pos: (
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[7] == "1",
                position,
            })
        })
        .collect()
}

fn parse_goal_kick_players(raw: &str) -> Result<Vec<GoalKickPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 10 {
                return Err(format!("invalid goal-kick player: {part}"));
            }
            Ok(GoalKickPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                team_is_restart: fields[1] == "1",
                team_attacking_right: fields[2] == "1",
                restart_attacking_right: fields[3] == "1",
                base_pos: (
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[6] == "1",
                is_attacker: fields[7] == "1",
                is_midfielder: fields[8] == "1",
                is_defender: fields[9] == "1",
            })
        })
        .collect()
}

fn parse_restart_players(raw: &str) -> Result<Vec<RestartPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid restart player: {part}"));
            }
            Ok(RestartPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[3] == "1",
            })
        })
        .collect()
}

fn parse_restart_shape_players(raw: &str) -> Result<Vec<RestartShapePlayerInput<'static>>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 14 {
                return Err(format!("invalid restart shape player: {part}"));
            }
            let position: &'static str = Box::leak(fields[13].to_string().into_boxed_str());
            Ok(RestartShapePlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                team_code: fields[1].parse::<u8>().map_err(|err| err.to_string())?,
                team_is_restart: fields[2] == "1",
                team_attacking_right: fields[3] == "1",
                restart_attacking_right: fields[4] == "1",
                base_pos: (
                    fields[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                current_pos: (
                    fields[7].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[8].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[9] == "1",
                is_attacker: fields[10] == "1",
                is_midfielder: fields[11] == "1",
                is_defender: fields[12] == "1",
                position,
            })
        })
        .collect()
}

fn parse_flight_movement_players(raw: &str) -> Result<Vec<FlightMovementPlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 7 {
                return Err(format!("invalid flight movement player: {part}"));
            }
            Ok(FlightMovementPlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tactical_anchor: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_passer: fields[5] == "1",
                is_stunned: fields[6] == "1",
            })
        })
        .collect()
}

fn parse_defensive_pressure_adjust_players(
    raw: &str,
) -> Result<Vec<DefensivePressureAdjustDefenderInput<'static>>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 6 {
                return Err(format!(
                    "invalid defensive pressure adjust defender: {part}"
                ));
            }
            let movement_intent: &'static str = Box::leak(fields[5].to_string().into_boxed_str());
            Ok(DefensivePressureAdjustDefenderInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    fields[3].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                movement_intent,
            })
        })
        .collect()
}

fn parse_team_shape_players(raw: &str) -> Result<Vec<TeamShapePlayerInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 4 {
                return Err(format!("invalid team shape player: {part}"));
            }
            Ok(TeamShapePlayerInput {
                index: fields[0].parse::<usize>().map_err(|err| err.to_string())?,
                base_pos: (
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[3] == "1",
            })
        })
        .collect()
}

fn parse_team_shape_opponents(raw: &str) -> Result<Vec<TeamShapeOpponentInput>, String> {
    if raw == "-" || raw.is_empty() {
        return Ok(Vec::new());
    }
    raw.split(';')
        .map(|part| {
            let fields: Vec<&str> = part.split(',').collect();
            if fields.len() != 3 {
                return Err(format!("invalid team shape opponent: {part}"));
            }
            Ok(TeamShapeOpponentInput {
                pos: (
                    fields[0].parse::<f64>().map_err(|err| err.to_string())?,
                    fields[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                is_goalkeeper: fields[2] == "1",
            })
        })
        .collect()
}

fn phase_from_cut_inside_code(code: u8) -> &'static str {
    match code {
        1 => "release",
        2 => "finish",
        _ => "drive",
    }
}

fn phase_from_byline_code(code: u8) -> &'static str {
    match code {
        1 => "release",
        _ => "drive",
    }
}

fn current_goal_allowed_for_specialized(goal_type: &str) -> bool {
    matches!(
        goal_type,
        "cut_inside_to_shoot"
            | "wide_byline_attack"
            | "wide_hold_for_overlap"
            | "through_ball_behind"
            | "release_pressure_with_layoff"
            | "hold_for_opportunity"
            | "release_to_arriving_support"
    )
}

fn current_goal_allowed_for_generic(goal_type: &str) -> bool {
    matches!(
        goal_type,
        "create_shot"
            | "progress_carry"
            | "protect_ball"
            | "recycle"
            | "switch_play"
            | "through_ball"
            | "clear_danger"
    )
}

fn goal_output_fields(goal: &OnBallFullGoal) -> (String, f64, f64, f64) {
    (
        goal.goal_type.clone(),
        goal.target_pos.0,
        goal.target_pos.1,
        goal.value,
    )
}

fn main() -> Result<(), String> {
    let mode = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "position_value".to_string());
    let stdin = io::stdin();
    for line in stdin.lock().lines() {
        let line = line.map_err(|err| err.to_string())?;
        if line.trim().is_empty() {
            continue;
        }
        if mode == "match_v2_run" {
            let request: MatchV2RunRequest =
                serde_json::from_str(&line).map_err(|err| err.to_string())?;
            let response = run_match_v2(request);
            println!(
                "{}",
                serde_json::to_string(&response).map_err(|err| err.to_string())?
            );
            continue;
        }
        if mode == "physics" {
            let parts: Vec<&str> = line.split('\t').collect();
            let op = parts
                .first()
                .ok_or_else(|| "missing physics op".to_string())?;
            match *op {
                "distance" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = distance(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!("{}\t{value:.15}", parts[5]);
                }
                "direction" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = direction(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[5], value.0, value.1);
                }
                "move_toward" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = move_toward(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[6], value.0, value.1);
                }
                "interpolate" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = interpolate(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[6], value.0, value.1);
                }
                "angle_to_goal" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = angle_to_goal(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[6]);
                }
                "player_speed" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = player_speed(
                        parts[1].parse::<i32>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[4]);
                }
                "clamp" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = clamp(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[4]);
                }
                "angle_between_points" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = angle_between_points(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!("{}\t{value:.15}", parts[5]);
                }
                "angle_diff" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = angle_diff(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[3]);
                }
                "is_in_fov" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = is_in_fov(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{}", parts[4], if value { "1" } else { "0" });
                }
                "midpoint" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = midpoint(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[5], value.0, value.1);
                }
                "point_along" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = point_along(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[5], value.0, value.1);
                }
                "smoothstep" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = smoothstep(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[4]);
                }
                "is_attacking_box" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let value = is_attacking_box_pos(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right,
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{}", parts[6], if value { "1" } else { "0" });
                }
                "residual_ball_velocity" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = residual_ball_velocity(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[7], value.0, value.1);
                }
                "out_of_bounds_restart" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let passer_home = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid passer_home: {other}")),
                    };
                    let (reason, restart_home) = out_of_bounds_restart(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        passer_home,
                    );
                    println!(
                        "{}\t{}\t{}",
                        parts[4],
                        reason,
                        if restart_home { "home" } else { "away" }
                    );
                }
                "out_of_bounds_plan" => {
                    if parts.len() != 14 {
                        return Err(format!(
                            "expected 14 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let passer_team_home = match parts[4] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid passer_home: {other}")),
                    };
                    let attacking_right = match parts[8] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let output = out_of_bounds_plan(&OutOfBoundsPlanInput {
                        out_x: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        passer_team_home,
                        flight_type_code: parts[5].parse::<u8>().map_err(|err| err.to_string())?,
                        origin: (
                            parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right,
                        total_xg: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                        logged_xg_sum: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                        goal_kick_restart_ticks: parts[11]
                            .parse::<i32>()
                            .map_err(|err| err.to_string())?,
                        throw_in_restart_ticks: parts[12]
                            .parse::<i32>()
                            .map_err(|err| err.to_string())?,
                    });
                    println!(
                        "{}\t{}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}",
                        parts[13],
                        output.reason,
                        if output.restart_team_home {
                            "home"
                        } else {
                            "away"
                        },
                        output.restart_ticks,
                        if output.has_shot_log { "1" } else { "0" },
                        output.shot_log.x,
                        output.shot_log.y,
                        output.shot_log.xg,
                        if output.shot_log.in_box { "1" } else { "0" },
                        output.shot_log.outcome,
                        output
                            .shot_log
                            .target_x
                            .map(|value| format!("{value:.15}"))
                            .unwrap_or_else(|| "-".to_string()),
                    );
                }
                "player_move_speed" => {
                    if parts.len() != 10 {
                        return Err(format!(
                            "expected 10 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = player_move_speed(&PlayerMoveSpeedInput {
                        pos: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        target_pos: (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        speed_ability: parts[5].parse::<i32>().map_err(|err| err.to_string())?,
                        movement_intent: parts[6],
                        state: parts[7],
                        player_max_speed: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                        player_min_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!("player_move_speed\t{:.15}", output.speed);
                }
                "player_move_tick" => {
                    if parts.len() != 14 {
                        return Err(format!(
                            "expected 14 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = player_move_tick(&PlayerMoveTickInput {
                        pos: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        target_pos: (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        velocity: (
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        speed_ability: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                        movement_intent: parts[8],
                        state: parts[9],
                        player_max_speed: parts[10]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        player_min_speed: parts[11]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        pitch_length: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "player_move_tick\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}",
                        if output.moved { "1" } else { "0" },
                        output.pos.0,
                        output.pos.1,
                        output.velocity.0,
                        output.velocity.1,
                        output.distance_covered,
                        output
                            .facing_direction
                            .map(|value| format!("{value:.15}"))
                            .unwrap_or_else(|| "-".to_string()),
                        output.desired_speed,
                    );
                }
                "player_set_movement_target" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let requested_intent = if parts[6] == "-" {
                        None
                    } else {
                        Some(parts[6])
                    };
                    let output = player_set_movement_target(&PlayerSetMovementTargetInput {
                        current_target: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        requested_target: (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        current_intent: parts[5],
                        requested_intent,
                    });
                    println!(
                        "{}\t{:.15}\t{:.15}\t{}",
                        parts[7], output.target_pos.0, output.target_pos.1, output.movement_intent,
                    );
                }
                "player_tick_stun" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = player_tick_stun(&PlayerTickStunInput {
                        state: parts[1],
                        stun_ticks_remaining: parts[2]
                            .parse::<i32>()
                            .map_err(|err| err.to_string())?,
                    });
                    println!(
                        "{}\t{}\t{}",
                        parts[3], output.state, output.stun_ticks_remaining,
                    );
                }
                "player_apply_stun" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = player_apply_stun(&PlayerApplyStunInput {
                        tackle_fail_stun_seconds: parts[1]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        tick_duration: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "{}\t{}\t{}",
                        parts[3], output.state, output.stun_ticks_remaining,
                    );
                }
                "score_tackle" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = score_tackle(&TackleScoreInput {
                        tackling: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        dribbling: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        dist_to_ball: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        tackle_range: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "{}\t{:.15}\t{:.15}",
                        parts[5], output.score, output.success_rate
                    );
                }
                "gk_position_adjust" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = gk_position_adjust(&GkPositionAdjustInput {
                        ball_pos: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right: parts[3] == "1",
                        pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "{}\t{:.15}\t{:.15}",
                        parts[6], output.target.0, output.target.1
                    );
                }
                "pass_control_strength" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = pass_control_strength(&PassControlInput {
                        score: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        contest_radius: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!("{}\t{:.15}", parts[3], output.control);
                }
                "pass_loose_control_strength" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let output = pass_loose_control_strength(&PassLooseControlInput {
                        teammate_control: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        opponent_control: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!("{}\t{:.15}", parts[3], output.control);
                }
                other => return Err(format!("unknown physics op: {other}")),
            }
            continue;
        }
        if mode == "vision" {
            let parts: Vec<&str> = line.split('\t').collect();
            let op = parts
                .first()
                .ok_or_else(|| "missing vision op".to_string())?;
            match *op {
                "compute_facing_direction" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let last_target = parse_runner(parts[5], parts[6])?;
                    let value = compute_facing_direction(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        last_target,
                    );
                    println!("{}\t{value:.15}", parts[7]);
                }
                "compute_fov" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = compute_fov(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[4]);
                }
                "compute_vision_distance" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = compute_vision_distance(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[5]);
                }
                "compute_player_facing" => {
                    if parts.len() != 4 {
                        return Err(format!(
                            "expected 4 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[2] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let value = compute_player_facing(
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        attacking_right,
                    );
                    println!("{}\t{value:.15}", parts[3]);
                }
                "context" => {
                    if parts.len() != 14 {
                        return Err(format!(
                            "expected 14 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let context = psl_engine_v2_core::build_vision_context(&VisionContextInput {
                        iq: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        facing_direction: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        attacking_right,
                        vision_base_fov: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        vision_iq_bonus_factor: parts[5]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        vision_base_distance: parts[6]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        vision_iq_distance_bonus_factor: parts[7]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                        vision_max_distance: parts[8]
                            .parse::<f64>()
                            .map_err(|err| err.to_string())?,
                    });
                    let confidence = context.confidence(
                        (
                            parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!(
                        "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}",
                        parts[13],
                        context.facing,
                        context.fov,
                        context.half_fov,
                        context.max_distance,
                        confidence,
                        if context.visible(
                            (
                                parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                                parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                            ),
                            (
                                parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                                parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                            ),
                        ) {
                            "1"
                        } else {
                            "0"
                        }
                    );
                }
                "context_confidence" => {
                    if parts.len() != 10 {
                        return Err(format!(
                            "expected 9 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let context = VisionContext {
                        facing: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        fov: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        half_fov: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        max_distance: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    };
                    let confidence = context.confidence(
                        (
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                    );
                    println!("{}\t{confidence:.15}", parts[9]);
                }
                "visible_indices" => {
                    if parts.len() != 11 {
                        return Err(format!(
                            "expected 11 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let teammates = parse_indexed_positions(parts[8])?;
                    let value = get_visible_target_indices(
                        parts[1].parse::<usize>().map_err(|err| err.to_string())?,
                        (
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        &teammates,
                        (
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{}", parts[10], format_usize_list(&value));
                }
                "is_target_visible" => {
                    if parts.len() != 11 {
                        return Err(format!(
                            "expected 11 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let value = is_target_visible(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        (
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        (
                            parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{}", parts[10], if value { "1" } else { "0" });
                }
                other => return Err(format!("unknown vision op: {other}")),
            }
            continue;
        }
        if mode == "goal_event" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 11 {
                return Err(format!(
                    "expected 11 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let last_passer_team_home = match parts[5] {
                "-" => None,
                "home" => Some(true),
                "away" => Some(false),
                other => return Err(format!("invalid last_passer_team: {other}")),
            };
            let output = build_goal_event(&GoalEventInput {
                scorer_name: parts[0],
                scoring_team_home: parts[1] == "home",
                home_score: parts[2].parse::<i32>().map_err(|err| err.to_string())?,
                away_score: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                scorer_idx: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                last_passer_team_home,
                last_passer_idx: parts[6].parse::<i32>().map_err(|err| err.to_string())?,
                scoring_team_size: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                assister_name: parts[8],
                assister_color: parts[9],
            });
            println!(
                "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                parts[10],
                output.home_score,
                output.away_score,
                if output.has_assist { "1" } else { "0" },
                output.assister_idx,
                output.assister_name,
                output.assister_color,
                output.event_text,
            );
            continue;
        }
        if mode == "team_shape_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let players = parse_team_shape_players(parts[7])?;
            let opponents = parse_team_shape_opponents(parts[8])?;
            let output = team_shape_plan(&TeamShapePlanInput {
                ball_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                phase: parts[3],
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                players: &players,
                opponents: &opponents,
            });
            let payload = if output.anchors.is_empty() {
                "-".to_string()
            } else {
                output
                    .anchors
                    .iter()
                    .map(|anchor| {
                        format!(
                            "{},{:.15},{:.15}",
                            anchor.index, anchor.tactical_anchor.0, anchor.tactical_anchor.1
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[9], payload);
            continue;
        }
        if mode == "team_phase_update" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = team_phase_update(&TeamPhaseUpdateInput {
                has_possession: parts[0] == "1",
                ball_contested: parts[1] == "1",
                had_possession_last_tick: parts[2] == "1",
                ticks_since_possession_change: parts[3]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                transition_ticks: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{}\t{}",
                parts[5],
                output.phase_code,
                output.ticks_since_possession_change,
                if output.had_possession_last_tick {
                    "1"
                } else {
                    "0"
                },
            );
            continue;
        }
        if mode == "score_goal_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let last_passer_team_home = match parts[6] {
                "-" => None,
                "home" => Some(true),
                "away" => Some(false),
                other => return Err(format!("invalid last_passer_team: {other}")),
            };
            let output = score_goal_plan(&ScoreGoalPlanInput {
                scorer_name: parts[0],
                scoring_team_home: parts[1] == "home",
                conceding_team_home: parts[2] == "home",
                home_score: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                away_score: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                scorer_idx: parts[5].parse::<i32>().map_err(|err| err.to_string())?,
                last_passer_team_home,
                last_passer_idx: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                scoring_team_size: parts[8].parse::<i32>().map_err(|err| err.to_string())?,
                assister_name: parts[9],
                assister_color: parts[10],
                tick: parts[11].parse::<i32>().map_err(|err| err.to_string())?,
                tick_duration: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                parts[13],
                output.home_score,
                output.away_score,
                if output.has_assist { "1" } else { "0" },
                output.assister_idx,
                output.assister_name,
                output.assister_color,
                output.minute,
                output.event_text,
                output.pause_ms,
                if output.restart_team_home {
                    "home"
                } else {
                    "away"
                },
                output.restart_ticks,
            );
            continue;
        }
        if mode == "give_ball_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let previous_holder_team_code = match parts[0] {
                "-" => None,
                value => Some(value.parse::<u8>().map_err(|err| err.to_string())?),
            };
            let receive_origin = parse_runner(parts[6], parts[7])?;
            let output = give_ball_plan(&GiveBallPlanInput {
                previous_holder_team_code,
                previous_holder_idx: parts[1].parse::<i32>().map_err(|err| err.to_string())?,
                new_holder_team_code: parts[2].parse::<u8>().map_err(|err| err.to_string())?,
                new_holder_idx: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                new_holder_pos: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receive_origin,
            });
            println!(
                "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[9],
                if output.clear_previous_holder {
                    "1"
                } else {
                    "0"
                },
                output
                    .previous_holder_team_code
                    .map(|code| code.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.previous_holder_idx,
                if output.clear_offside_flags { "1" } else { "0" },
                if output.clear_team_goals { "1" } else { "0" },
                output.new_holder_team_code,
                output.new_holder_idx,
                output.ball_pos.0,
                output.ball_pos.1,
                output.last_receive_origin.0,
                output.last_receive_origin.1,
            );
            continue;
        }
        if mode == "ball_flight_frame" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = build_ball_flight_frame(&BallFlightFrameInput {
                from_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                to_pos: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                flight_type: parts[4],
                on_target: parts[5] == "1",
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}",
                parts[6],
                output.from_yx.0,
                output.from_yx.1,
                output.to_yx.0,
                output.to_yx.1,
                output.flight_type,
                if output.on_target { "1" } else { "0" },
            );
            continue;
        }
        if mode == "flight_tick" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = tick_ball_flight(&FlightTickInput {
                origin: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ticks_elapsed: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                ticks_total: parts[5].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{}\t{}",
                parts[6],
                output.position.0,
                output.position.1,
                output.ticks_elapsed,
                if output.complete { "1" } else { "0" },
            );
            continue;
        }
        if mode == "flight_movement_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attack_players = parse_flight_movement_players(parts[6])?;
            let defense_players = parse_flight_movement_players(parts[7])?;
            let output = flight_movement_plan(&FlightMovementPlanInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                contested_race_radius: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                attack_players: &attack_players,
                defense_players: &defense_players,
            });
            let payload = if output.players.is_empty() {
                "-".to_string()
            } else {
                output
                    .players
                    .iter()
                    .map(|player| {
                        format!(
                            "{},{},{},{:.15},{:.15}",
                            player.team_code,
                            player.index,
                            player.action_code,
                            player.target.0,
                            player.target.1,
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[8], payload);
            continue;
        }
        if mode == "key_pass" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let last_passer_team_home = match parts[2] {
                "-" => None,
                "home" => Some(true),
                "away" => Some(false),
                other => return Err(format!("invalid last_passer_team: {other}")),
            };
            let output = key_pass_for_shot(&KeyPassInput {
                shooter_team_home: parts[0] == "home",
                shooter_idx: parts[1].parse::<i32>().map_err(|err| err.to_string())?,
                last_passer_team_home,
                last_passer_idx: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                team_size: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{}",
                parts[5],
                if output.has_key_pass { "1" } else { "0" },
                output.key_passer_idx,
            );
            continue;
        }
        if mode == "pass_phase_outcome" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = pass_phase_outcome(&PassPhaseOutcomeInput {
                pass_accuracy_error: parts[0] == "1",
                interception_present: parts[1] == "1",
                intercepted: parts[2] == "1",
            });
            println!("{}\t{}", parts[3], output.outcome_code);
            continue;
        }
        if mode == "pass_trace_payload" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver_pos = parse_runner(parts[2], parts[3])?;
            let output = pass_trace_payload(&PassTraceInput {
                target: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                intended_receiver_pos: receiver_pos,
                is_long: parts[4] == "1",
            });
            println!(
                "{}\t{}\t{}",
                parts[5], output.pass_type_code, output.target_kind_code,
            );
            continue;
        }
        if mode == "pass_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 25 {
                return Err(format!(
                    "expected 25 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_execution_opponents(parts[11])?;
            let intended_receiver_pos = parse_runner(parts[22], parts[23])?;
            let output = pass_phase_plan(&PassPhasePlanInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ideal_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passing: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                is_long: parts[5] == "1",
                lane_risk: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ball_pass_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                ball_long_pass_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                pass_error_divisor: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                random_1: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                random_2: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                random_3: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                random_4: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                random_5: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                interception_present: parts[18] == "1",
                interceptor_defence: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                interception_distance: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                interception_reach: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                intended_receiver_pos,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}",
                parts[24],
                output.outcome_code,
                output.target.0,
                output.target.1,
                output.stray_pos.0,
                output.stray_pos.1,
                output.speed,
                output.ticks_needed,
                output.flight_type_code,
                output.pass_type_code,
                output.target_kind_code,
                output.flight_from_yx.0,
                output.flight_from_yx.1,
                output.flight_to_yx.0,
                output.flight_to_yx.1,
                output.randoms_used,
            );
            continue;
        }
        if mode == "shot_xg" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let explicit_xg = if parts[0] == "-" {
                None
            } else {
                Some(parts[0].parse::<f64>().map_err(|err| err.to_string())?)
            };
            let output = shot_xg_value(&ShotXgInput {
                explicit_xg,
                on_target_prob: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                goal_reward_constant: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!("{}\t{:.15}", parts[3], output.xg);
            continue;
        }
        if mode == "shot_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 15 {
                return Err(format!(
                    "expected 15 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let explicit_xg = if parts[3] == "-" {
                None
            } else {
                Some(parts[3].parse::<f64>().map_err(|err| err.to_string())?)
            };
            let output = shot_phase_plan(&ShotPhasePlanInput {
                shooter_name: parts[0],
                shooter_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                explicit_xg,
                on_target_prob: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                goal_reward_constant: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right: parts[6] == "1",
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                goal_width: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                ball_shot_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                random_1: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                random_2: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                random_3: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}",
                parts[14],
                output.shot_xg,
                if output.on_target { "1" } else { "0" },
                output.target.0,
                output.target.1,
                output.speed,
                output.distance,
                output.ticks_needed,
                output.flight_type_code,
                output.flight_from_yx.0,
                output.flight_from_yx.1,
                output.flight_to_yx.0,
                output.flight_to_yx.1,
                output.randoms_used,
                output.pending_event_text,
            );
            continue;
        }
        if mode == "shot_log_xg" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = shot_log_xg(&ShotLogXgInput {
                total_xg: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                logged_xg_sum: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                clamp_nonnegative: parts[2] == "1",
            });
            println!(
                "{}\t{:.15}\t{:.15}",
                parts[3], output.raw_xg, output.rounded_xg
            );
            continue;
        }
        if mode == "shot_arrival_event" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = shot_arrival_event(&ShotArrivalEventInput {
                shooter_name: parts[0],
                keeper_name: parts[1],
                outcome: parts[2],
            });
            println!(
                "{}\t{}\t{}\t{}",
                parts[3], output.pending_event_text, output.pause_ms, output.trace_event,
            );
            continue;
        }
        if mode == "shot_log_entry" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let target = parse_runner(parts[2], parts[3])?;
            let output = shot_log_entry(&ShotLogEntryInput {
                origin: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target,
                xg: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                in_box: parts[5] == "1",
                outcome: parts[6],
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{}",
                parts[7],
                output.x,
                output.y,
                output.xg,
                if output.in_box { "1" } else { "0" },
                output.outcome,
                output
                    .target_x
                    .map(|value| format!("{value:.15}"))
                    .unwrap_or_else(|| "-".to_string()),
                output
                    .target_y
                    .map(|value| format!("{value:.15}"))
                    .unwrap_or_else(|| "-".to_string()),
            );
            continue;
        }
        if mode == "restart_helper" {
            let parts: Vec<&str> = line.split('\t').collect();
            let op = parts
                .first()
                .ok_or_else(|| "missing restart op".to_string())?;
            match *op {
                "goal_kick_spot" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[1] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let value = goal_kick_spot(
                        attacking_right,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{:.15}\t{:.15}", parts[4], value.0, value.1);
                }
                "must_leave_goal_kick_box" => {
                    if parts.len() != 6 {
                        return Err(format!(
                            "expected 6 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let player_team_is_restart_team = parts[1] == "1";
                    let restart_attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let value = must_leave_penalty_area_for_goal_kick(
                        player_team_is_restart_team,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        restart_attacking_right,
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{}", parts[5], if value { "1" } else { "0" });
                }
                "kickoff_shape" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let players = parse_kickoff_players(parts[3])?;
                    let output = kickoff_shape_targets(&KickoffShapeInput {
                        pitch_length: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        players: &players,
                    });
                    let payload = if output.targets.is_empty() {
                        "-".to_string()
                    } else {
                        output
                            .targets
                            .iter()
                            .map(|(idx, target)| {
                                format!("{},{:.15},{:.15}", idx, target.0, target.1)
                            })
                            .collect::<Vec<_>>()
                            .join(";")
                    };
                    println!(
                        "{}\t{}\t{}",
                        parts[4],
                        output
                            .kicker_index
                            .map(|idx| idx.to_string())
                            .unwrap_or_else(|| "-".to_string()),
                        payload,
                    );
                }
                "goal_kick_shape" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let players = parse_goal_kick_players(parts[3])?;
                    let output = goal_kick_shape_targets(&GoalKickShapeInput {
                        pitch_length: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        players: &players,
                    });
                    let payload = if output.targets.is_empty() {
                        "-".to_string()
                    } else {
                        output
                            .targets
                            .iter()
                            .map(|(idx, target)| {
                                format!("{},{:.15},{:.15}", idx, target.0, target.1)
                            })
                            .collect::<Vec<_>>()
                            .join(";")
                    };
                    println!("{}\t{}", parts[4], payload);
                }
                "restart_play" => {
                    if parts.len() != 9 {
                        return Err(format!(
                            "expected 9 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let players = parse_restart_players(parts[7])?;
                    let output = restart_play_decision(&RestartPlayInput {
                        reason: parts[1],
                        ball_pos: (
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        restart_attacking_right: attacking_right,
                        pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        corner_y_roll: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                        players: &players,
                    });
                    println!(
                        "restart_play\t{:.15}\t{:.15}\t{}\t{}\t{}",
                        output.ball_pos.0,
                        output.ball_pos.1,
                        output
                            .receiver_index
                            .map(|idx| idx.to_string())
                            .unwrap_or_else(|| "-".to_string()),
                        if output.set_receiver_pos { "1" } else { "0" },
                        if output.pending_cut { "1" } else { "0" },
                    );
                }
                "restart_play_plan" => {
                    if parts.len() != 9 {
                        return Err(format!(
                            "expected 9 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let players = parse_restart_players(parts[7])?;
                    let output = restart_play_plan(&RestartPlayPlanInput {
                        reason: parts[1],
                        ball_pos: (
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        restart_attacking_right: attacking_right,
                        pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        corner_y_roll: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                        players: &players,
                    });
                    println!(
                        "restart_play_plan\t{:.15}\t{:.15}\t{}\t{}\t{}\t{}\t{}",
                        output.ball_pos.0,
                        output.ball_pos.1,
                        output
                            .receiver_index
                            .map(|idx| idx.to_string())
                            .unwrap_or_else(|| "-".to_string()),
                        if output.set_receiver_pos { "1" } else { "0" },
                        if output.pending_cut { "1" } else { "0" },
                        if output.reset_last_passer { "1" } else { "0" },
                        if output.clear_offside_flags { "1" } else { "0" },
                    );
                }
                "restart_shape_plan" => {
                    if parts.len() != 7 {
                        return Err(format!(
                            "expected 7 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let players = parse_restart_shape_players(parts[5])?;
                    let output = restart_shape_plan(&RestartShapePlanInput {
                        reason: parts[1],
                        force: parts[2] == "1",
                        pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        players: &players,
                    });
                    let payload = if output.players.is_empty() {
                        "-".to_string()
                    } else {
                        output
                            .players
                            .iter()
                            .map(|player| {
                                format!(
                                    "{},{},{:.15},{:.15},{}",
                                    player.team_code,
                                    player.index,
                                    player.target.0,
                                    player.target.1,
                                    if player.snap { "1" } else { "0" },
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(";")
                    };
                    println!(
                        "{}\t{}\t{:.15}\t{:.15}\t{}",
                        parts[6],
                        if output.has_shape { "1" } else { "0" },
                        output.ball_pos.0,
                        output.ball_pos.1,
                        payload,
                    );
                }
                other => return Err(format!("unknown restart op: {other}")),
            }
            continue;
        }
        if mode == "match_stats" {
            let parts: Vec<&str> = line.split('\t').collect();
            let op = parts
                .first()
                .ok_or_else(|| "missing stats op".to_string())?;
            match *op {
                "pass" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[5] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let output = track_pass_stats(&PassStatInput {
                        origin: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        target: (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right,
                        pitch_length: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "pass\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                        output.crosses_attempted,
                        output.crosses_completed,
                        output.progressive_passes,
                        output.long_passes,
                        output.completed_long_passes,
                        output.passes_into_final_third,
                        output.passes_into_box,
                    );
                }
                "carry" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[5] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let output = track_carry_stats(&CarryStatInput {
                        old_pos: (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        new_pos: (
                            parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right,
                        pitch_length: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                        pitch_width: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    });
                    println!(
                        "carry\t{}\t{}\t{}",
                        output.progressive_carries,
                        output.carries_into_final_third,
                        output.carries_into_box,
                    );
                }
                other => return Err(format!("unknown stats op: {other}")),
            }
            continue;
        }
        if mode == "offside" {
            let parts: Vec<&str> = line.split('\t').collect();
            let op = parts
                .first()
                .ok_or_else(|| "missing offside op".to_string())?;
            match *op {
                "line" => {
                    if parts.len() != 5 {
                        return Err(format!(
                            "expected 5 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[1] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let opponents = parse_opponent_line_inputs(parts[3])?;
                    let value = get_offside_line(
                        &opponents,
                        attacking_right,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    );
                    println!("{}\t{value:.15}", parts[4]);
                }
                "position" => {
                    if parts.len() != 8 {
                        return Err(format!(
                            "expected 8 tab-separated fields, got {}",
                            parts.len()
                        ));
                    }
                    let attacking_right = match parts[3] {
                        "1" | "true" | "True" => true,
                        "0" | "false" | "False" => false,
                        other => return Err(format!("invalid attacking_right: {other}")),
                    };
                    let ball_x = if parts[6] == "-" {
                        None
                    } else {
                        Some(parts[6].parse::<f64>().map_err(|err| err.to_string())?)
                    };
                    let value = is_offside_position(
                        (
                            parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                            parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        ),
                        attacking_right,
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                        ball_x,
                    );
                    println!("{}\t{}", parts[7], if value { "1" } else { "0" });
                }
                other => return Err(format!("unknown offside op: {other}")),
            }
            continue;
        }
        if mode == "pass_space_generic" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 15 {
                return Err(format!(
                    "expected 15 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[3] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let teammates = parse_pass_space_players(parts[11])?;
            let opponents = parse_positions(parts[12])?;
            let teammate_positions = parse_positions(parts[13])?;
            let values = generic_pass_space_candidates(&GenericPassSpaceInput {
                passer_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                passer_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                offside_line: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                vision: VisionContext {
                    facing: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                },
                teammates: &teammates,
                opponent_positions: &opponents,
                teammate_positions: &teammate_positions,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15}",
                            value.score,
                            value.target.0,
                            value.target.1,
                            value.visibility,
                            value.position_value
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[14], payload);
            continue;
        }
        if mode == "pass_receiver_base_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 17 {
                return Err(format!(
                    "expected 17 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let receiver = parse_pass_space_players(parts[9])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let receiver_goal = if parts[12] == "-" {
                None
            } else {
                Some(ReceiverGoalInput {
                    goal_type: parts[12],
                    target_pos: (
                        parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                })
            };
            let output = receiver_base_pass_targets(&ReceiverBaseTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                receiver_goal,
                vision: VisionContext {
                    facing: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                },
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let targets = if output.targets.is_empty() {
                "-".to_string()
            } else {
                output
                    .targets
                    .iter()
                    .map(|target| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            target.target.0, target.target.1, target.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}",
                parts[16],
                targets,
                output.receiver_visibility,
                output.target_visibility,
                if output.low_visibility { "1" } else { "0" },
                output.receiver_goal_fit,
            );
            continue;
        }
        if mode == "pass_value_field_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[0])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let receiver_goal_target = parse_runner(parts[5], parts[6])?;
            let generic_candidates = parse_generic_pass_space_candidates(parts[7])?;
            let values = value_field_raw_targets(&ValueFieldTargetsInput {
                receiver,
                receiver_goal_target,
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                is_defender: parts[4] == "1",
                generic_candidates: &generic_candidates,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15}",
                            value.target.0,
                            value.target.1,
                            value.arrival,
                            value.tactical_space_prior,
                            value.tactical_space_value,
                            value.tactical_space_visibility,
                            value.expected_arrival_confidence,
                            value.expected_arrival_fit
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[8], payload);
            continue;
        }
        if mode == "pass_stale_release_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[2])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[5] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let values = stale_release_targets(&StaleReleaseTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                low_visibility: parts[3] == "1",
                consecutive_carries: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            value.target.0, value.target.1, value.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[8], payload);
            continue;
        }
        if mode == "pass_layoff_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[2])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let values = layoff_targets(&LayoffTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                low_visibility: parts[3] == "1",
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            value.target.0, value.target.1, value.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[7], payload);
            continue;
        }
        if mode == "pass_second_line_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[2])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let values = second_line_targets(&SecondLineTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                receiver_base: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                low_visibility: parts[5] == "1",
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            value.target.0, value.target.1, value.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[9], payload);
            continue;
        }
        if mode == "pass_box_delivery_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[2])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let values = box_delivery_targets(&BoxDeliveryTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                low_visibility: parts[3] == "1",
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            value.target.0, value.target.1, value.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[7], payload);
            continue;
        }
        if mode == "pass_delivery_space_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[2])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let values = delivery_space_targets(&DeliverySpaceTargetsInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                low_visibility: parts[3] == "1",
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15}",
                            value.target.0, value.target.1, value.arrival
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[7], payload);
            continue;
        }
        if mode == "pass_receiver_spatial_candidates" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 19 {
                return Err(format!(
                    "expected 19 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_space_players(parts[0])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[3] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let front_center = parse_runner(parts[12], parts[13])?;
            let opponents = parse_positions(parts[16])?;
            let teammates = parse_positions(parts[17])?;
            let values = receiver_spatial_candidates(&ReceiverSpatialCandidatesInput {
                passer_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                vision: VisionContext {
                    facing: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                },
                attacking_right,
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                offside_line: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                low_visibility: parts[7] == "1",
                front_center,
                opponent_positions: &opponents,
                teammate_positions: &teammates,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15},{:.15}",
                            value.score,
                            value.target.0,
                            value.target.1,
                            value.receiver_arrival,
                            value.position_value,
                            value.point_visibility
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[18], payload);
            continue;
        }
        if mode == "pass_raw_prevalue" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 29 {
                return Err(format!(
                    "expected 29 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_risk_players(parts[3])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[10] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let receiver_goal_target = parse_runner(parts[18], parts[19])?;
            let opponents = parse_pass_risk_players(parts[26])?;
            let teammates = parse_pass_risk_players(parts[27])?;
            let value = evaluate_raw_pass_target_prevalue(&RawPassPreValueInput {
                passer_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                passer_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver,
                target: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                initial_receiver_arrival: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_visibility: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_target,
                receiver_goal_value: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_fit: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                vision: VisionContext {
                    facing: parts[22].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[23].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[24].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[25].parse::<f64>().map_err(|err| err.to_string())?,
                },
                attacking_right,
                pitch_length: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                offside_line: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                short_passing: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                long_passing: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                short_pass_base_success: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                long_pass_base_success: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                teammates: &teammates,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}",
                parts[28],
                if value.valid { "1" } else { "0" },
                value.receiver_arrival,
                value.base_accuracy,
                value.continuity,
                value.perception,
                value.perception_multiplier,
                value.arrival_margin,
                value.receiver_time,
                value.defender_time,
                value.defender_first_risk,
                value.target_occupation_risk,
                value.nearest_teammate_to_target,
                value.nearest_opp_to_target,
                value.box_space_pressure,
                value.goal_target_fit,
                if value.is_long { "1" } else { "0" },
                if value.target_kind_space { "1" } else { "0" },
                value.distance,
            );
            continue;
        }
        if mode == "pass_raw_value" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 49 {
                return Err(format!(
                    "expected 49 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver = parse_pass_risk_players(parts[3])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver".to_string())?;
            let attacking_right = match parts[10] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let receiver_goal_target_for_prevalue = parse_runner(parts[18], parts[19])?;
            let prevalue_opponents = parse_pass_risk_players(parts[26])?;
            let prevalue_teammates = parse_pass_risk_players(parts[27])?;
            let receiver_goal_type = if parts[39] == "-" {
                None
            } else {
                Some(parts[39])
            };
            let receiver_goal_target = parse_runner(parts[40], parts[41])?;
            let teammate_positions = parse_indexed_positions(parts[42])?;
            let opponent_positions = parse_positions(parts[43])?;
            let teammate_goalkeeper_indices = prevalue_teammates
                .iter()
                .filter(|player| player.is_goalkeeper)
                .map(|player| player.index)
                .collect::<Vec<_>>();
            let value = score_raw_pass_target(&RawPassValueInput {
                prevalue: RawPassPreValueInput {
                    passer_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                    passer_pos: (
                        parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    receiver,
                    target: (
                        parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    initial_receiver_arrival: parts[6]
                        .parse::<f64>()
                        .map_err(|err| err.to_string())?,
                    receiver_visibility: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    receiver_goal_target: receiver_goal_target_for_prevalue,
                    receiver_goal_value: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                    receiver_goal_fit: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                    vision: VisionContext {
                        facing: parts[22].parse::<f64>().map_err(|err| err.to_string())?,
                        fov: parts[23].parse::<f64>().map_err(|err| err.to_string())?,
                        half_fov: parts[24].parse::<f64>().map_err(|err| err.to_string())?,
                        max_distance: parts[25].parse::<f64>().map_err(|err| err.to_string())?,
                    },
                    attacking_right,
                    pitch_length: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                    pitch_width: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                    offside_line: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                    player_max_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                    player_min_speed: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                    short_passing: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                    long_passing: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    short_pass_base_success: parts[16]
                        .parse::<f64>()
                        .map_err(|err| err.to_string())?,
                    long_pass_base_success: parts[17]
                        .parse::<f64>()
                        .map_err(|err| err.to_string())?,
                    opponents: &prevalue_opponents,
                    teammates: &prevalue_teammates,
                },
                tick: 0,
                passer_team_home: true,
                passer_finishing: parts[29].parse::<f64>().map_err(|err| err.to_string())?,
                passer_long_shot: parts[30].parse::<f64>().map_err(|err| err.to_string())?,
                passer_consecutive_carries: parts[31]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                receiver_index: parts[32].parse::<usize>().map_err(|err| err.to_string())?,
                receiver_team_home: true,
                receiver_finishing: parts[33].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_long_shot: parts[34].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_anchor: (
                    parts[35].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[36].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_base: (
                    parts[37].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[38].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_goal_type,
                receiver_goal_target,
                receiver_goal_value: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                teammate_positions: &teammate_positions,
                teammate_goalkeeper_indices: &teammate_goalkeeper_indices,
                opponent_positions: &opponent_positions,
                interception_reach: parts[44].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[45].parse::<f64>().map_err(|err| err.to_string())?,
                shot_on_target_base: parts[46].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[47].parse::<f64>().map_err(|err| err.to_string())?,
                current_value: parts[28].parse::<f64>().map_err(|err| err.to_string())?,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}",
                parts[48],
                if value.valid { "1" } else { "0" },
                value.adjusted_score,
                value.score,
                value.success_prob,
                value.risk_cost,
                value.after_value,
                value.effective_delta,
                value.continuity,
                value.lane_risk,
                value.receiver_pressure,
                value.turnover_consequence,
                value.receiver_arrival,
                value.base_accuracy,
                value.defender_first_risk,
                value.target_occupation_risk,
                value.goal_target_fit,
                if value.is_long { "1" } else { "0" },
                if value.target_kind_space { "1" } else { "0" },
                value.distance,
            );
            continue;
        }
        if mode == "pass_receiver_batch" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 48 {
                return Err(format!(
                    "expected 48 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receiver_space = parse_pass_space_players(parts[3])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver_space".to_string())?;
            let receiver_risk = parse_pass_risk_players(parts[4])?
                .into_iter()
                .next()
                .ok_or_else(|| "missing receiver_risk".to_string())?;
            let attacking_right = match parts[11] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let receiver_goal = if parts[31] == "-" {
                None
            } else {
                Some(ReceiverGoalInput {
                    goal_type: parts[31],
                    target_pos: (
                        parts[32].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[33].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[34].parse::<f64>().map_err(|err| err.to_string())?,
                })
            };
            let front_center = parse_runner(parts[35], parts[36])?;
            let generic_candidates = parse_generic_pass_space_candidates(parts[37])?;
            let teammate_positions = parse_indexed_positions(parts[38])?;
            let opponent_positions = parse_positions(parts[39])?;
            let teammate_xy_positions = parse_positions(parts[40])?;
            let risk_opponents = parse_pass_risk_players(parts[41])?;
            let risk_teammates = parse_pass_risk_players(parts[42])?;
            let values = receiver_pass_candidates_batch(&ReceiverPassBatchInput {
                tick: 0,
                passer_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                passer_team_home: true,
                passer_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passer_finishing: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                passer_long_shot: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                passer_short_passing: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                passer_long_passing: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                passer_consecutive_carries: parts[9]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                receiver_space,
                receiver_risk,
                receiver_index: parts[10].parse::<usize>().map_err(|err| err.to_string())?,
                receiver_team_home: true,
                receiver_finishing: parts[24].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_long_shot: parts[25].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_anchor: (
                    parts[26].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[27].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_base: (
                    parts[28].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[29].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_goal,
                is_receiver_defender: parts[30] == "1",
                vision: VisionContext {
                    facing: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[22].parse::<f64>().map_err(|err| err.to_string())?,
                },
                attacking_right,
                pitch_length: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                offside_line: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                short_pass_base_success: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                long_pass_base_success: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                interception_reach: parts[43].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[44].parse::<f64>().map_err(|err| err.to_string())?,
                shot_on_target_base: parts[45].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[46].parse::<f64>().map_err(|err| err.to_string())?,
                current_value: parts[23].parse::<f64>().map_err(|err| err.to_string())?,
                front_center,
                generic_candidates: &generic_candidates,
                opponent_positions: &opponent_positions,
                teammate_positions: &teammate_positions,
                teammate_goalkeeper_indices: &[],
                teammate_xy_positions: &teammate_xy_positions,
                risk_opponents: &risk_opponents,
                risk_teammates: &risk_teammates,
                shot_quality_cache: None,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{},{}",
                            value.target.0,
                            value.target.1,
                            value.score,
                            value.raw_score,
                            value.success_prob,
                            value.receiver_arrival,
                            value.base_accuracy,
                            value.goal_target_fit,
                            value.distance,
                            if value.is_long { "1" } else { "0" },
                            if value.target_kind_space { "1" } else { "0" }
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[47], payload);
            continue;
        }
        if mode == "pass_team_batch" || mode == "pass_team_batch_details" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 36 {
                return Err(format!(
                    "expected 36 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[9] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let players = parse_pass_team_players(parts[24])?;
            let teammate_positions_for_value = parse_indexed_positions(parts[25])?;
            let opponent_positions = parse_positions(parts[26])?;
            let teammate_xy_positions = parse_positions(parts[27])?;
            let risk_opponents = parse_pass_risk_players(parts[28])?;
            let risk_teammates = parse_pass_risk_players(parts[29])?;
            let values = team_pass_candidates_batch(&psl_engine_v2_core::TeamPassBatchInput {
                tick: 0,
                passer_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                passer_team_home: true,
                passer_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passer_finishing: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                passer_long_shot: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                passer_short_passing: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                passer_long_passing: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                passer_consecutive_carries: parts[7]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                vision: VisionContext {
                    facing: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                    fov: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                    half_fov: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                    max_distance: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                },
                attacking_right,
                pitch_length: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                offside_line: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                short_pass_base_success: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                long_pass_base_success: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                interception_reach: parts[30].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[31].parse::<f64>().map_err(|err| err.to_string())?,
                shot_on_target_base: parts[32].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[33].parse::<f64>().map_err(|err| err.to_string())?,
                current_value: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                players: &players,
                opponent_positions: &opponent_positions,
                teammate_positions_for_value: &teammate_positions_for_value,
                teammate_goalkeeper_indices_for_value: &[],
                teammate_xy_positions: &teammate_xy_positions,
                risk_opponents: &risk_opponents,
                risk_teammates: &risk_teammates,
                shot_quality_cache: None,
            });
            let payload = format_team_pass_candidates(&values, mode == "pass_team_batch_details");
            println!("{}\t{}", parts[35], payload);
            continue;
        }
        if mode == "off_ball_attack_raw" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let anchor_samples = parse_random_polar_samples(parts[9])?;
            let support_samples = parse_random_polar_samples(parts[10])?;
            let values = generate_off_ball_attack_raw_candidates(&OffBallRawGenerationInput {
                anchor: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                is_defender: parts[7] == "1",
                has_ball_carrier: parts[8] == "1",
                anchor_samples: &anchor_samples,
                support_samples: &support_samples,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15}",
                            value.pos.0, value.pos.1, value.anchor_pos.0, value.anchor_pos.1
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[11], payload);
            continue;
        }
        if mode == "off_ball_arrival_goals" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let player_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let anchor_pos = (
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let ball_pos = (
                parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                parts[5].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let base_pos = (
                parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                parts[7].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let attacking_right = match parts[8] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let pitch_length = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let goal_width = parts[11].parse::<f64>().map_err(|err| err.to_string())?;
            let arc = evaluate_arc_arrival_goal(&ArcArrivalGoalInput {
                player_pos,
                anchor_pos,
                ball_pos,
                base_pos,
                attacking_right,
                pitch_length,
                pitch_width,
            });
            let far = evaluate_attack_far_post_goal(&AttackFarPostGoalInput {
                player_pos,
                anchor_pos,
                ball_pos,
                attacking_right,
                pitch_length,
                pitch_width,
                goal_width,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[13],
                if arc.has_goal { "1" } else { "0" },
                arc.target_pos.0,
                arc.target_pos.1,
                arc.value,
                arc.confidence,
                arc.ball_progress,
                arc.ball_width,
                arc.anchor_progress,
                arc.base_progress,
                arc.anchor_width,
                arc.target_dist,
                if far.has_goal { "1" } else { "0" },
                far.target_pos.0,
                far.target_pos.1,
                far.value,
                far.confidence,
                far.ball_progress,
                far.ball_width,
                far.weak_side,
                far.player_progress,
                far.anchor_progress,
                far.target_dist,
            );
            continue;
        }
        if mode == "off_ball_attack_score" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 27 {
                return Err(format!(
                    "expected 27 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let candidates = parse_off_ball_candidates(parts[14])?;
            let opponents = parse_positions(parts[15])?;
            let opponent_speeds = parse_f64_list(parts[16])?;
            let teammate_positions = parse_positions(parts[17])?;
            let teammates = parse_off_ball_teammates(parts[18])?;
            let current_goal = if parts[19] == "-" {
                None
            } else {
                Some(OffBallAttackGoalInput {
                    goal_type: parts[19],
                    target_pos: (
                        parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[22].parse::<f64>().map_err(|err| err.to_string())?,
                })
            };
            let values = score_off_ball_attack_candidates(&OffBallAttackBatchInput {
                player_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                player_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                player_speed: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                anchor: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                offside_line: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                pass_to_space_ball_speed: parts[23]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                receive_reachability_scale: parts[24]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                space_creation_radius: parts[25].parse::<f64>().map_err(|err| err.to_string())?,
                candidates: &candidates,
                opponent_positions: &opponents,
                opponent_speeds: &opponent_speeds,
                teammate_positions: &teammate_positions,
                teammates: &teammates,
                current_goal,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15}",
                            value.score,
                            value.target.0,
                            value.target.1,
                            value.pv,
                            value.reach,
                            value.movement_reach,
                            value.immediate_reach,
                            value.pass_feasibility,
                            value.space_bonus,
                            value.role_shape_factor,
                            value.role_overlap_factor,
                            value.role_overlap,
                            value.lane_factor,
                            value.offside_penalty,
                            value.support_angle_value,
                            value.inside_support,
                            value.second_line_support,
                            value.arrival_goal_fit,
                            value.arrival_goal_multiplier,
                            value.arrival_goal_bonus,
                            value.layoff_window,
                            value.candidate_progress,
                            value.candidate_width,
                            value.support_angle_dist,
                            value.dist_to_ball
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[26], payload);
            continue;
        }
        if mode == "off_ball_attack_goal_build" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 16 {
                return Err(format!(
                    "expected 16 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = build_off_ball_attack_goal(&OffBallAttackGoalBuildInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                value: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                second_line_support: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                inside_support: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                support_angle_value: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                layoff_window: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                candidate_progress: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                candidate_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let current_goal = if parts[9] == "-" {
                None
            } else {
                Some(GoalInput {
                    goal_type: parts[9],
                    value: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                    phase: Some("support"),
                })
            };
            let candidate_goal = GoalInput {
                goal_type: &output.goal_type,
                value: output.value,
                phase: Some("support"),
            };
            let context = GoalSwitchCostInput {
                base: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                context_stability: 1.0,
                role_discipline: 1.0,
                pressure_interrupt: 0.0,
                iq: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
            };
            let selection =
                select_goal_deterministic(current_goal.as_ref(), &candidate_goal, &context);
            let selected_is_candidate = selection.selected == "candidate";
            let selected_type = if selected_is_candidate {
                output.goal_type.as_str()
            } else {
                parts[9]
            };
            let selected_x = if selected_is_candidate {
                output.target_pos.0
            } else {
                parts[10].parse::<f64>().map_err(|err| err.to_string())?
            };
            let selected_y = if selected_is_candidate {
                output.target_pos.1
            } else {
                parts[11].parse::<f64>().map_err(|err| err.to_string())?
            };
            let selected_value = if selected_is_candidate {
                output.value
            } else {
                parts[12].parse::<f64>().map_err(|err| err.to_string())?
            };
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}",
                "offball_goal",
                output.goal_type,
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.box_arrival,
                output.second_line_support,
                output.inside_support,
                output.support_angle_value,
                output.layoff_window,
                output.candidate_progress,
                output.candidate_width,
                selected_type,
                selected_x,
                selected_y,
                selected_value,
                if selection.switched { "1" } else { "0" },
                selection.switch_cost,
                selection.value_advantage,
                selection.noisy_value_advantage,
                selection.reason,
            );
            continue;
        }
        if mode == "defensive_goal_build" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 15 {
                return Err(format!(
                    "expected 15 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = build_defensive_goal(&DefensiveGoalBuildInput {
                action_type: parts[0],
                target_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                value: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pressure: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                threat: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let current_goal = if parts[6] == "-" {
                None
            } else {
                Some(GoalInput {
                    goal_type: parts[6],
                    value: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    phase: Some("defend"),
                })
            };
            let candidate_goal = GoalInput {
                goal_type: &output.goal_type,
                value: output.value,
                phase: Some("defend"),
            };
            let context = GoalSwitchCostInput {
                base: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                context_stability: 1.0,
                role_discipline: 1.0,
                pressure_interrupt: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            };
            let selection =
                select_goal_deterministic(current_goal.as_ref(), &candidate_goal, &context);
            let selected_is_candidate = selection.selected == "candidate";
            let selected_type = if selected_is_candidate {
                output.goal_type.as_str()
            } else {
                parts[6]
            };
            let selected_x = if selected_is_candidate {
                output.target_pos.0
            } else {
                parts[7].parse::<f64>().map_err(|err| err.to_string())?
            };
            let selected_y = if selected_is_candidate {
                output.target_pos.1
            } else {
                parts[8].parse::<f64>().map_err(|err| err.to_string())?
            };
            let selected_value = if selected_is_candidate {
                output.value
            } else {
                parts[9].parse::<f64>().map_err(|err| err.to_string())?
            };
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}\t{:.15}\t{}",
                parts[14],
                output.goal_type,
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.action_type,
                output.pressure,
                output.threat,
                selected_type,
                selected_x,
                selected_y,
                selected_value,
                if selection.switched { "1" } else { "0" },
                selection.switch_cost,
                selection.value_advantage,
                selection.noisy_value_advantage,
                selection.reason,
            );
            continue;
        }
        if mode == "off_ball_attack_choice" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 31 {
                return Err(format!(
                    "expected 31 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let candidates = parse_off_ball_candidates(parts[14])?;
            let opponents = parse_positions(parts[15])?;
            let opponent_speeds = parse_f64_list(parts[16])?;
            let teammate_positions = parse_positions(parts[17])?;
            let teammates = parse_off_ball_teammates(parts[18])?;
            let current_goal = if parts[19] == "-" {
                None
            } else {
                Some(OffBallAttackGoalInput {
                    goal_type: parts[19],
                    target_pos: (
                        parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[22].parse::<f64>().map_err(|err| err.to_string())?,
                })
            };
            let score_noises = parse_f64_list(parts[27])?;
            let output = choose_off_ball_attack_target(&OffBallAttackChoiceInput {
                player_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                player_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                player_speed: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                anchor: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                offside_line: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                pass_to_space_ball_speed: parts[23]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                receive_reachability_scale: parts[24]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                space_creation_radius: parts[25].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[26].parse::<f64>().map_err(|err| err.to_string())?,
                stay_score: parts[28].parse::<f64>().map_err(|err| err.to_string())?,
                roll: parts[29].parse::<f64>().map_err(|err| err.to_string())?,
                candidates: &candidates,
                opponent_positions: &opponents,
                opponent_speeds: &opponent_speeds,
                teammate_positions: &teammate_positions,
                teammates: &teammates,
                current_goal,
                score_noises: &score_noises,
            });
            if let Some(output) = output {
                let components = output.components;
                let fields = vec![
                    format!("{:.15}", output.target.0),
                    format!("{:.15}", output.target.1),
                    format!("{:.15}", output.score),
                    format!("{:.15}", output.max_score),
                    output.candidate_count.to_string(),
                    if output.used_roll {
                        "1".to_string()
                    } else {
                        "0".to_string()
                    },
                    components.kind.to_string(),
                    format!("{:.15}", components.pv),
                    format!("{:.15}", components.reach),
                    format!("{:.15}", components.movement_reach),
                    format!("{:.15}", components.immediate_reach),
                    format!("{:.15}", components.pass_feasibility),
                    format!("{:.15}", components.space_bonus),
                    format!("{:.15}", components.role_shape_factor),
                    format!("{:.15}", components.role_overlap_factor),
                    format!("{:.15}", components.role_overlap),
                    format!("{:.15}", components.lane_factor),
                    format!("{:.15}", components.offside_penalty),
                    format!("{:.15}", components.support_angle_value),
                    format!("{:.15}", components.inside_support),
                    format!("{:.15}", components.second_line_support),
                    format!("{:.15}", components.arrival_goal_fit),
                    format!("{:.15}", components.arrival_goal_multiplier),
                    format!("{:.15}", components.arrival_goal_bonus),
                    format!("{:.15}", components.layoff_window),
                    format!("{:.15}", components.candidate_progress),
                    format!("{:.15}", components.candidate_width),
                    format!("{:.15}", components.support_angle_dist),
                    format!("{:.15}", components.dist_to_ball),
                ];
                println!("{}\t{}", parts[30], fields.join("\t"));
            } else {
                println!("{}\t-", parts[30]);
            }
            continue;
        }
        if mode == "off_ball_defense_score" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 25 {
                return Err(format!(
                    "expected 25 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[8] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let ball_carrier_pos = parse_runner(parts[9], parts[10])?;
            let last_def_target = parse_runner(parts[17], parts[18])?;
            let candidates = parse_positions(parts[19])?;
            let attackers = parse_positions(parts[20])?;
            let local_attackers = parse_positions(parts[21])?;
            let dangerous_receivers = parse_positions(parts[22])?;
            let teammates = parse_defense_teammates(parts[23])?;
            let values = score_defense_candidates(&DefenseScoreInput {
                defender_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                anchor: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                base_ref: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_carrier_pos,
                ball_carrier_consecutive_carries: parts[11]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                press_radius: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                tackle_range: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                last_def_target,
                candidates: &candidates,
                attackers: &attackers,
                local_attackers: &local_attackers,
                dangerous_receivers: &dangerous_receivers,
                teammates: &teammates,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15},{:.15}",
                            value.score,
                            value.target.0,
                            value.target.1,
                            value.base_score,
                            value.press_value,
                            value.pressure_responsibility,
                            value.carrier_threat,
                            value.shot_lane_closure,
                            value.best_mark_value
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[24], payload);
            continue;
        }
        if mode == "off_ball_defense_raw" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 22 {
                return Err(format!(
                    "expected 22 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let ball_carrier_pos = parse_runner(parts[9], parts[10])?;
            let local_attackers = parse_positions(parts[16])?;
            let dangerous_receivers = parse_positions(parts[17])?;
            let random_samples = parse_defense_random_samples(parts[18])?;
            let last_def_target = parse_runner(parts[19], parts[20])?;
            let values = generate_defense_raw_candidates(&DefenseRawInput {
                defender_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                anchor: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ball_carrier_pos,
                carrier_speed: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_stale_threat: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                field_press_context: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                shot_danger: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                shot_lane_threat: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                local_attackers: &local_attackers,
                dangerous_receivers: &dangerous_receivers,
                random_samples: &random_samples,
                last_def_target,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| format!("{:.15},{:.15}", value.0, value.1))
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[21], payload);
            continue;
        }
        if mode == "off_ball_defense_choice" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 29 {
                return Err(format!(
                    "expected 29 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[8] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let ball_carrier_pos = parse_runner(parts[9], parts[10])?;
            let last_def_target = parse_runner(parts[18], parts[19])?;
            let previous_goal_target = parse_runner(parts[20], parts[21])?;
            let attackers = parse_positions(parts[22])?;
            let teammates = parse_defense_teammates(parts[23])?;
            let random_samples = parse_defense_random_samples(parts[24])?;
            let score_noises = parse_f64_list(parts[25])?;
            let rolls = parse_f64_list(parts[26])?;
            let fallback_indices = parse_usize_list(parts[27])?;
            let output = choose_defense_action(&DefenseChoiceInput {
                defender_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                anchor: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                base_ref: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_carrier_pos,
                ball_carrier_consecutive_carries: parts[11]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                press_radius: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                tackle_range: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                last_def_target,
                previous_goal_target,
                attackers: &attackers,
                teammates: &teammates,
                random_samples: &random_samples,
                score_noises: &score_noises,
                roll_by_count: &rolls,
                fallback_index_by_count: &fallback_indices,
            });
            if let Some(output) = output {
                println!(
                    "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                    parts[28],
                    output.action_type,
                    output.target.0,
                    output.target.1,
                    output.score,
                    output.candidate_count,
                    if output.used_roll { "1" } else { "0" },
                    if output.used_random_choice { "1" } else { "0" },
                    output.pressure_responsibility,
                    output.shot_danger,
                    output.carrier_stale_threat,
                    match output.previous_goal_score {
                        Some(value) => format!("{value:.15}"),
                        None => "-".to_string(),
                    },
                    output.base_score,
                    output.press_value,
                    output.carrier_threat,
                    output.shot_lane_closure,
                    output.best_mark_value
                );
            } else {
                println!("{}\t-", parts[28]);
            }
            continue;
        }
        if mode == "shot_quality" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let x = parts[0].parse::<f64>().map_err(|err| err.to_string())?;
            let y = parts[1].parse::<f64>().map_err(|err| err.to_string())?;
            let finishing = parts[2].parse::<f64>().map_err(|err| err.to_string())?;
            let long_shot = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_length = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[5].parse::<f64>().map_err(|err| err.to_string())?;
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let shot_ideal_distance = parts[7].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_on_target_base = parts[8].parse::<f64>().map_err(|err| err.to_string())?;
            let gk_save_base = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[10])?;
            let value = shot_quality_at(&ShotQualityInput {
                x,
                y,
                finishing,
                long_shot,
                opponents: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                shot_ideal_distance,
                shot_on_target_base,
                gk_save_base,
                cache: None,
                cache_key: None,
            });
            println!("{}\t{value:.15}", parts[11]);
            continue;
        }

        if mode == "goal_switch_cost" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = goal_switch_cost(&GoalSwitchCostInput {
                base: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                context_stability: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                role_discipline: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_interrupt: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!("{}\t{value:.15}", parts[5]);
            continue;
        }

        if mode == "iq_temperature" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = iq_temperature_factor(
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            );
            println!("{}\t{value:.15}", parts[4]);
            continue;
        }
        if mode == "iq_noise_score" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = apply_iq_noise_score(&IqNoiseScoreInput {
                score: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                iq_noise_scale: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                gaussian: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}",
                parts[4], output.score, output.noise_scale
            );
            continue;
        }

        if mode == "gk_save" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = compute_gk_save_probability(&GkSaveInput {
                gk_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                shot_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                shot_origin: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                gk_saving: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                gk_positioning: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                gk_reaction: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                gk_position_error_factor: parts[10]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_reaction_delay_factor: parts[11]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_save_base: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!("{}\t{value:.15}", parts[13]);
            continue;
        }

        if mode == "gk_rush" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = should_rush_out(&GkRushInput {
                gk_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacker_pos: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                gk_positioning: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                gk_rush_distance: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!("{}\t{}", parts[7], if value { "1" } else { "0" });
            continue;
        }

        if mode == "gk_distribution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let value = choose_distribution(&GkDistributionInput {
                gk_y: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                short_passing: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                long_passing: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                decision_noise: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                target_x_sample: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                target_y_sample: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}",
                parts[9], value.distribution_type, value.target.0, value.target.1
            );
            continue;
        }

        if mode == "gk_fallback_target" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[0] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let value = choose_fallback_target(&GkFallbackTargetInput {
                attacking_right,
                pitch_length: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}",
                parts[3], value.target.0, value.target.1
            );
            continue;
        }

        if mode == "select_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let current_storage;
            let current_goal = if parts[0] == "-" {
                None
            } else {
                current_storage = GoalInput {
                    goal_type: parts[0],
                    value: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    phase: if parts[2] == "-" {
                        None
                    } else {
                        Some(parts[2])
                    },
                };
                Some(&current_storage)
            };
            let candidate_goal = GoalInput {
                goal_type: parts[3],
                value: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                phase: if parts[5] == "-" {
                    None
                } else {
                    Some(parts[5])
                },
            };
            let context = GoalSwitchCostInput {
                base: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                context_stability: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                role_discipline: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_interrupt: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
            };
            let value = select_goal_deterministic(current_goal, &candidate_goal, &context);
            println!(
                "{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}",
                parts[11],
                value.selected,
                if value.switched { "1" } else { "0" },
                value.switch_cost,
                value.value_advantage,
                value.noisy_value_advantage,
                value.reason,
            );
            continue;
        }

        if mode == "select_goal_candidate" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let values = parse_f64_list(parts[0])?;
            let gaussians = parse_f64_list(parts[1])?;
            let context = GoalSwitchCostInput {
                base: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                context_stability: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                role_discipline: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_interrupt: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                iq: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            };
            let goal_noise_scale = parts[7].parse::<f64>().map_err(|err| err.to_string())?;
            let choice = select_goal_candidate_with_gaussians(
                &values,
                &gaussians,
                &context,
                goal_noise_scale,
            );
            if let Some(choice) = choice {
                println!(
                    "{}\t{}\t{:.15}\t{:.15}",
                    parts[8], choice.index, choice.candidate_noise, choice.noisy_value
                );
            } else {
                println!("{}\t-\t0.000000000000000\t0.000000000000000", parts[8]);
            }
            continue;
        }

        if mode == "softmax_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let scores = parse_f64_list(parts[0])?;
            let output = softmax_select_index(
                &scores,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<usize>().map_err(|err| err.to_string())?,
            );
            if let Some(output) = output {
                println!(
                    "{}\t{}\t{:.15}\t{:.15}",
                    parts[4], output.index, output.temperature, output.total_weight
                );
            } else {
                println!("{}\t-\t0.000000000000000\t0.000000000000000", parts[4]);
            }
            continue;
        }
        if mode == "on_ball_full_decision" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 30 {
                return Err(format!(
                    "expected 30 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let player_index = parts[0].parse::<usize>().map_err(|err| err.to_string())?;
            let player_pos = (
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let attacking_right = parts[3] == "1";
            let pitch_length = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[5].parse::<f64>().map_err(|err| err.to_string())?;
            let iq = parts[6].parse::<f64>().map_err(|err| err.to_string())?;
            let consecutive_carries = parts[7].parse::<i32>().map_err(|err| err.to_string())?;
            let tick = parts[8].parse::<i32>().map_err(|err| err.to_string())?;
            let goal_continuity_enabled = parts[9] == "1";
            let goal_cut_inside_bias = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let goal_noise_scale = parts[11].parse::<f64>().map_err(|err| err.to_string())?;
            let current_goal_type = parts[12];
            let current_goal = if current_goal_type == "-" {
                None
            } else {
                Some(OnBallFullGoal {
                    goal_type: current_goal_type.to_string(),
                    target_pos: (
                        parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                    confidence: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                    phase: parts[18].to_string(),
                    created_tick: parts[17].parse::<i32>().map_err(|err| err.to_string())?,
                    candidate_noise: 0.0,
                    candidate_noisy_value: parts[15]
                        .parse::<f64>()
                        .map_err(|err| err.to_string())?,
                })
            };
            let candidates = parse_on_ball_full_candidates(parts[19])?;
            let byline_teammates = parse_byline_teammates(parts[20])?;
            let opponent_positions = parse_positions(parts[21])?;
            let score_noises = parse_f64_list(parts[22])?;
            let selection_roll = parts[23].parse::<f64>().map_err(|err| err.to_string())?;
            let fallback_index = parts[24].parse::<usize>().map_err(|err| err.to_string())?;
            let goal_candidate_noises = parse_f64_list(parts[25])?;
            let switch_noise_input = parts[26].parse::<f64>().map_err(|err| err.to_string())?;
            let generic_roll = parts[27].parse::<f64>().map_err(|err| err.to_string())?;
            let generic_fallback_index =
                parts[28].parse::<usize>().map_err(|err| err.to_string())?;

            if candidates.is_empty() {
                println!("{}\t-", parts[29]);
                continue;
            }

            let mut working_scores: Vec<f64> =
                candidates.iter().map(|candidate| candidate.score).collect();
            let immediate_best_score = working_scores.iter().copied().fold(0.0, f64::max);
            let mut selected_goal: Option<OnBallFullGoal> = None;
            let mut goal_trace_switched = false;
            let mut goal_trace_switch_cost = 0.0;
            let mut goal_trace_value_advantage = 0.0;
            let mut goal_trace_switch_noise = 0.0;
            let mut goal_trace_noisy_advantage = 0.0;
            let mut goal_trace_reason = "-".to_string();
            let mut candidate_choice_noise = 0.0;
            let mut candidate_choice_noisy_value = 0.0;
            let mut selected_goal_action_code: i32 = -1;
            let mut opportunity_indices: Vec<usize> = Vec::new();
            let mut goal_noise_count = 0usize;
            let mut switch_noise_used = false;

            if goal_continuity_enabled {
                let mut goal_candidates: Vec<OnBallFullGoal> = Vec::new();
                let best_carry = candidates
                    .iter()
                    .filter(|candidate| candidate.action_code == 0)
                    .max_by(|left, right| {
                        left.score
                            .partial_cmp(&right.score)
                            .unwrap_or(std::cmp::Ordering::Equal)
                    });

                if let Some(best_carry) = best_carry {
                    let current_cut_goal = current_goal
                        .as_ref()
                        .filter(|goal| goal.goal_type == "cut_inside_to_shoot");
                    let cut_goal_age_ticks = current_cut_goal
                        .map(|goal| (tick - goal.created_tick).max(0))
                        .unwrap_or(0);
                    let shot = candidates
                        .iter()
                        .find(|candidate| candidate.action_code == 2);
                    let cut = evaluate_cut_inside_goal(&CutInsideGoalInput {
                        player_pos,
                        attacking_right,
                        pitch_length,
                        pitch_width,
                        best_carry_target: best_carry.target,
                        future_shot_gain: best_carry.future_shot_gain,
                        carry_to_shoot_window: best_carry.carry_to_shoot_window,
                        wide_second_line_carry_window: best_carry.wide_second_line_carry_window,
                        current_shot: shot.map(|candidate| candidate.xg).unwrap_or(0.0),
                        current_readiness: shot
                            .map(|candidate| candidate.shot_readiness)
                            .unwrap_or(0.0),
                        consecutive_carries,
                        goal_age_ticks: cut_goal_age_ticks,
                    });
                    let current_cut_release = cut.has_goal
                        && current_cut_goal.is_some()
                        && phase_from_cut_inside_code(cut.phase_code) == "release";
                    if cut.has_goal {
                        goal_candidates.push(OnBallFullGoal {
                            goal_type: "cut_inside_to_shoot".to_string(),
                            target_pos: cut.target_pos,
                            value: cut.value,
                            confidence: cut.confidence,
                            phase: phase_from_cut_inside_code(cut.phase_code).to_string(),
                            created_tick: current_cut_goal
                                .map(|goal| goal.created_tick)
                                .unwrap_or(tick),
                            candidate_noise: 0.0,
                            candidate_noisy_value: cut.value,
                        });
                    }

                    let byline_full_candidates: Vec<&OnBallFullCandidate> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 0)
                        .filter(|candidate| candidate.target.is_some())
                        .collect();
                    let byline_carries: Vec<BylineCarryInput> = byline_full_candidates
                        .iter()
                        .filter_map(|candidate| {
                            candidate.target.map(|target| BylineCarryInput {
                                score: candidate.score,
                                target,
                                byline_carry_window: candidate.byline_carry_window,
                            })
                        })
                        .collect();
                    let byline_selection = select_best_byline_carry(&BylineCarrySelectionInput {
                        player_index,
                        player_pos,
                        attacking_right,
                        pitch_length,
                        pitch_width,
                        teammates: &byline_teammates,
                        carries: &byline_carries,
                    });
                    if !current_cut_release && byline_selection.index.is_some() {
                        let selected_byline =
                            byline_full_candidates[byline_selection.index.unwrap()];
                        let byline = evaluate_drive_byline_goal(&DriveBylineGoalInput {
                            player_pos,
                            carry_target: byline_selection.target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            carry_score: byline_selection.score,
                            progress_gain: selected_byline.progress_gain,
                            byline_carry_window: selected_byline.byline_carry_window,
                            path_feasibility: selected_byline.path_feasibility,
                            space_manipulation: selected_byline.space_manipulation,
                            delivery_support: byline_selection.delivery_support,
                        });
                        if byline.has_goal {
                            goal_candidates.push(OnBallFullGoal {
                                goal_type: "wide_byline_attack".to_string(),
                                target_pos: byline.target_pos,
                                value: byline.value,
                                confidence: byline.confidence,
                                phase: phase_from_byline_code(byline.phase_code).to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: byline.value,
                            });
                        }
                    }

                    let overlap_passes: Vec<OverlapPassInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 1)
                        .filter_map(|candidate| {
                            candidate.target.map(|target| OverlapPassInput {
                                score: candidate.score,
                                target,
                                receiver_pressure: candidate.receiver_pressure,
                            })
                        })
                        .collect();
                    let overlap = select_best_overlap(&OverlapSelectionInput {
                        player_pos,
                        attacking_right,
                        pitch_length,
                        pitch_width,
                        passes: &overlap_passes,
                    });
                    if overlap.index.is_some() {
                        let wide = evaluate_wide_hold_overlap_goal(&WideHoldOverlapGoalInput {
                            player_pos,
                            overlap_target: overlap.target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            overlap_value: overlap.value,
                            immediate_best_score,
                        });
                        if wide.has_goal {
                            goal_candidates.push(OnBallFullGoal {
                                goal_type: "wide_hold_for_overlap".to_string(),
                                target_pos: wide.target_pos,
                                value: wide.value,
                                confidence: wide.confidence,
                                phase: "wait".to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: wide.value,
                            });
                        }
                    }

                    let mut best_through: Option<OnBallFullGoal> = None;
                    let mut best_byline_delivery: Option<OnBallFullGoal> = None;
                    for pass in candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 1)
                    {
                        let Some(target) = pass.target else {
                            continue;
                        };
                        let through = evaluate_through_ball_goal(&ThroughBallGoalInput {
                            player_pos,
                            pass_target: target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            pass_score: pass.score,
                            target_kind_space: pass.target_kind_space,
                            target_progress: pass.target_progress,
                            centrality: pass.centrality,
                            progress_gain: pass.progress_gain,
                            high_threat_space: pass.high_threat_space,
                            success_prob: pass.success_prob,
                            receiver_pressure: pass.receiver_pressure,
                            lane_risk: pass.lane_risk,
                        });
                        if through.has_goal {
                            let goal = OnBallFullGoal {
                                goal_type: "through_ball_behind".to_string(),
                                target_pos: through.target_pos,
                                value: through.value,
                                confidence: through.confidence,
                                phase: "release".to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: through.value,
                            };
                            if best_through
                                .as_ref()
                                .map(|current| goal.value > current.value)
                                .unwrap_or(true)
                            {
                                best_through = Some(goal);
                            }
                        }

                        let delivery = evaluate_byline_delivery_goal(&BylineDeliveryGoalInput {
                            player_pos,
                            delivery_target: target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            pass_score: pass.score,
                            target_progress: pass.target_progress,
                            centrality: pass.centrality,
                            high_threat_space: pass.high_threat_space,
                            final_third_combination: pass.final_third_combination,
                            success_prob: pass.success_prob,
                            receiver_pressure: pass.receiver_pressure,
                            lane_risk: pass.lane_risk,
                        });
                        if delivery.has_goal {
                            let goal = OnBallFullGoal {
                                goal_type: "wide_byline_attack".to_string(),
                                target_pos: delivery.target_pos,
                                value: delivery.value,
                                confidence: delivery.confidence,
                                phase: "release".to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: delivery.value,
                            };
                            if best_byline_delivery
                                .as_ref()
                                .map(|current| goal.value > current.value)
                                .unwrap_or(true)
                            {
                                best_byline_delivery = Some(goal);
                            }
                        }
                    }
                    if let Some(goal) = best_through {
                        goal_candidates.push(goal);
                    }
                    if let Some(goal) = best_byline_delivery {
                        goal_candidates.push(goal);
                    }

                    let layoff_passes: Vec<LayoffPassInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 1)
                        .filter_map(|candidate| {
                            candidate.target.map(|target| LayoffPassInput {
                                score: candidate.score,
                                target,
                                receiver_pressure: candidate.receiver_pressure,
                            })
                        })
                        .collect();
                    let layoff = select_best_layoff(&LayoffSelectionInput {
                        player_pos,
                        attacking_right,
                        pitch_length,
                        pitch_width,
                        passes: &layoff_passes,
                        opponents: &opponent_positions,
                    });
                    if layoff.index.is_some() {
                        let layoff_goal = evaluate_layoff_goal(&LayoffGoalInput {
                            player_pos,
                            layoff_target: layoff.target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            attracted_pressure: layoff.attracted_pressure,
                            layoff_value: layoff.value,
                            immediate_best_score,
                        });
                        if layoff_goal.has_goal {
                            goal_candidates.push(OnBallFullGoal {
                                goal_type: "release_pressure_with_layoff".to_string(),
                                target_pos: layoff_goal.target_pos,
                                value: layoff_goal.value,
                                confidence: layoff_goal.confidence,
                                phase: "release".to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: layoff_goal.value,
                            });
                        }
                    }

                    let arriving_passes: Vec<ArrivingSupportPassInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 1)
                        .filter_map(|candidate| {
                            candidate.target.map(|target| ArrivingSupportPassInput {
                                score: candidate.score,
                                target,
                                receiver_goal_fit: candidate.receiver_goal_fit,
                                second_line_arrival_value: candidate.second_line_arrival_value,
                                second_line_cutback_value: candidate.second_line_cutback_value,
                                layoff_support_value: candidate.layoff_support_value,
                            })
                        })
                        .collect();
                    let arriving = select_best_arriving_support(&ArrivingSupportSelectionInput {
                        player_pos,
                        passes: &arriving_passes,
                        opponents: &opponent_positions,
                    });
                    if arriving.index.is_some() {
                        let shot = candidates
                            .iter()
                            .find(|candidate| candidate.action_code == 2);
                        let shot_readiness = shot
                            .map(|candidate| {
                                candidate
                                    .shot_readiness
                                    .max(candidate.open_medium_window)
                                    .max(candidate.clean_second_line_shot)
                            })
                            .unwrap_or(0.0);
                        let release = evaluate_release_support_goal(&ReleaseSupportGoalInput {
                            player_pos,
                            support_target: arriving.target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            support_value: arriving.support_value,
                            receiver_goal_fit: arriving.receiver_goal_fit,
                            current_shot: shot.map(|candidate| candidate.xg).unwrap_or(0.0),
                            shot_readiness,
                            consecutive_carries,
                            attracted_pressure: arriving.attracted_pressure,
                        });
                        if release.has_goal {
                            goal_candidates.push(OnBallFullGoal {
                                goal_type: "release_to_arriving_support".to_string(),
                                target_pos: release.target_pos,
                                value: release.value,
                                confidence: release.confidence,
                                phase: "release".to_string(),
                                created_tick: tick,
                                candidate_noise: 0.0,
                                candidate_noisy_value: release.value,
                            });
                        }
                    }

                    let hold_passes: Vec<HoldSupportPassInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 1)
                        .filter_map(|candidate| {
                            candidate.target.map(|target| HoldSupportPassInput {
                                score: candidate.score,
                                target,
                                layoff_support_value: candidate.layoff_support_value,
                                short_combination_value: candidate.short_combination_value,
                                second_line_cutback_value: candidate.second_line_cutback_value,
                                layoff_retention_value: candidate.layoff_retention_value,
                                receiver_goal_fit: candidate.receiver_goal_fit,
                                second_line_arrival_value: candidate.second_line_arrival_value,
                            })
                        })
                        .collect();
                    let hold_carries: Vec<HoldSupportCarryInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 0)
                        .map(|candidate| HoldSupportCarryInput {
                            carry_to_shoot_window: candidate.carry_to_shoot_window,
                            wide_second_line_carry_window: candidate.wide_second_line_carry_window,
                            future_shot_gain: candidate.future_shot_gain,
                        })
                        .collect();
                    let holds: Vec<HoldSupportHoldInput> = candidates
                        .iter()
                        .filter(|candidate| candidate.action_code == 3)
                        .map(|candidate| HoldSupportHoldInput {
                            opportunity_wait: candidate.opportunity_wait,
                            opportunity_wait_value: candidate.opportunity_wait_value,
                            no_clear_release: candidate.no_clear_release,
                        })
                        .collect();
                    let current_opportunity_goal = current_goal
                        .as_ref()
                        .map(|goal| goal.goal_type == "hold_for_opportunity")
                        .unwrap_or(false);
                    let hold_support = select_hold_support(&HoldSupportSelectionInput {
                        player_pos,
                        attacking_right,
                        pitch_length,
                        pitch_width,
                        passes: &hold_passes,
                        carries: &hold_carries,
                        holds: &holds,
                        current_opportunity_goal,
                    });
                    if hold_support.has_support {
                        let opportunity_age = current_goal
                            .as_ref()
                            .filter(|goal| goal.goal_type == "hold_for_opportunity")
                            .map(|goal| (tick - goal.created_tick).max(0))
                            .unwrap_or(0);
                        let shot = candidates
                            .iter()
                            .find(|candidate| candidate.action_code == 2);
                        let shot_readiness = shot
                            .map(|candidate| {
                                candidate
                                    .shot_readiness
                                    .max(candidate.open_medium_window)
                                    .max(candidate.clean_second_line_shot)
                            })
                            .unwrap_or(0.0);
                        let hold_goal = evaluate_hold_opportunity_goal(&HoldOpportunityGoalInput {
                            player_pos,
                            support_target: hold_support.target,
                            attacking_right,
                            pitch_length,
                            pitch_width,
                            support_value: hold_support.support_value,
                            hold_value: hold_support.hold_support,
                            current_shot: shot.map(|candidate| candidate.xg).unwrap_or(0.0),
                            shot_readiness,
                            immediate_best_score,
                            goal_age_ticks: opportunity_age,
                        });
                        if hold_goal.has_goal {
                            goal_candidates.push(OnBallFullGoal {
                                goal_type: "hold_for_opportunity".to_string(),
                                target_pos: hold_goal.target_pos,
                                value: hold_goal.value,
                                confidence: hold_goal.confidence,
                                phase: "scan".to_string(),
                                created_tick: current_goal
                                    .as_ref()
                                    .filter(|goal| goal.goal_type == "hold_for_opportunity")
                                    .map(|goal| goal.created_tick)
                                    .unwrap_or(tick),
                                candidate_noise: 0.0,
                                candidate_noisy_value: hold_goal.value,
                            });
                        }
                    }
                }

                let context = GoalSwitchCostInput {
                    base: 0.035,
                    context_stability: 1.0,
                    role_discipline: 1.0,
                    pressure_interrupt: 0.0,
                    iq,
                };
                let mut candidate_goal: Option<OnBallFullGoal> = None;
                if !goal_candidates.is_empty() {
                    goal_noise_count = goal_candidates.len();
                    let values = goal_candidates
                        .iter()
                        .map(|goal| goal.value)
                        .collect::<Vec<_>>();
                    if let Some(choice) = select_goal_candidate_with_gaussians(
                        &values,
                        &goal_candidate_noises,
                        &context,
                        goal_noise_scale,
                    ) {
                        candidate_goal = goal_candidates.get(choice.index).cloned();
                        if let Some(goal) = candidate_goal.as_mut() {
                            goal.candidate_noise = choice.candidate_noise;
                            goal.candidate_noisy_value = choice.noisy_value;
                            candidate_choice_noise = choice.candidate_noise;
                            candidate_choice_noisy_value = choice.noisy_value;
                        }
                    }
                } else if let Some(current) = current_goal.as_ref() {
                    if current_goal_allowed_for_specialized(&current.goal_type) {
                        candidate_goal = Some(current.clone());
                    }
                }

                if let Some(candidate_goal) = candidate_goal {
                    let (
                        selected,
                        switched,
                        switch_cost,
                        value_advantage,
                        switch_noise,
                        noisy_advantage,
                        reason,
                    ) = if current_goal.is_none() {
                        (
                            candidate_goal.clone(),
                            true,
                            0.0,
                            candidate_goal.value,
                            0.0,
                            candidate_goal.value,
                            "no_current_goal".to_string(),
                        )
                    } else {
                        let current = current_goal.as_ref().unwrap();
                        let current_phase = if current.phase == "-" {
                            ""
                        } else {
                            current.phase.as_str()
                        };
                        let candidate_phase = candidate_goal.phase.as_str();
                        let advantage = candidate_goal.value - current.value;
                        if current.goal_type == candidate_goal.goal_type
                            && matches!(candidate_phase, "finish" | "release")
                            && candidate_phase != current_phase
                        {
                            (
                                candidate_goal.clone(),
                                false,
                                0.0,
                                advantage,
                                0.0,
                                advantage,
                                "current_goal_phase_updated".to_string(),
                            )
                        } else if current.goal_type == "cut_inside_to_shoot"
                            && candidate_goal.goal_type == "cut_inside_to_shoot"
                            && current_phase == "drive"
                            && candidate_phase == "drive"
                        {
                            (
                                candidate_goal.clone(),
                                false,
                                0.0,
                                advantage,
                                0.0,
                                advantage,
                                "current_goal_drive_updated".to_string(),
                            )
                        } else if current.goal_type == "hold_for_opportunity"
                            && candidate_goal.goal_type == "hold_for_opportunity"
                            && current_phase == "scan"
                            && candidate_phase == "scan"
                        {
                            (
                                candidate_goal.clone(),
                                false,
                                0.0,
                                advantage,
                                0.0,
                                advantage,
                                "current_goal_scan_updated".to_string(),
                            )
                        } else {
                            let switch_cost = goal_switch_cost(&context);
                            let switch_noise = goal_selection_noise_from_gauss(
                                &context,
                                goal_noise_scale,
                                switch_noise_input,
                            );
                            switch_noise_used = goal_noise_scale > 0.0;
                            let noisy_advantage = advantage + switch_noise;
                            if noisy_advantage > switch_cost {
                                (
                                    candidate_goal.clone(),
                                    true,
                                    switch_cost,
                                    advantage,
                                    switch_noise,
                                    noisy_advantage,
                                    "candidate_clears_switch_cost".to_string(),
                                )
                            } else {
                                (
                                    current.clone(),
                                    false,
                                    switch_cost,
                                    advantage,
                                    switch_noise,
                                    noisy_advantage,
                                    "current_goal_within_switch_cost".to_string(),
                                )
                            }
                        }
                    };
                    goal_trace_switched = switched;
                    goal_trace_switch_cost = switch_cost;
                    goal_trace_value_advantage = value_advantage;
                    goal_trace_switch_noise = switch_noise;
                    goal_trace_noisy_advantage = noisy_advantage;
                    goal_trace_reason = reason;
                    selected_goal = Some(selected.clone());

                    if current_goal_allowed_for_specialized(&selected.goal_type) {
                        let specialized = full_specialized_candidates(&candidates, &working_scores);
                        let bias = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
                            candidates: &specialized,
                            goal_type: &selected.goal_type,
                            goal_phase: &selected.phase,
                            goal_target: selected.target_pos,
                            goal_value: selected.value,
                            bias: goal_cut_inside_bias.max(0.0),
                            consecutive_carries,
                        });
                        if bias.biased_scores.len() == working_scores.len() {
                            working_scores = bias.biased_scores;
                        }
                        opportunity_indices = bias.opportunity_target_indices;
                    }
                }
            }

            let selection_candidates = full_selection_candidates(&candidates)
                .into_iter()
                .enumerate()
                .map(|(idx, mut candidate)| {
                    candidate.score = working_scores.get(idx).copied().unwrap_or(candidate.score);
                    candidate
                })
                .collect::<Vec<_>>();
            let current_hold_goal = selected_goal
                .as_ref()
                .or(current_goal.as_ref())
                .map(|goal| goal.goal_type == "hold_for_opportunity")
                .unwrap_or(false);
            let selection = select_on_ball_candidate(&OnBallSelectionInput {
                candidates: &selection_candidates,
                current_goal_hold_for_opportunity: current_hold_goal,
                iq,
                score_noises: &score_noises,
                roll: selection_roll,
                fallback_index,
            })
            .ok_or_else(|| "on-ball full selection failed".to_string())?;
            let mut chosen_index = selection.index;
            let mut final_scores = selection.noisy_scores.clone();
            let mut generic_used_roll = false;
            let mut generic_used_random_choice = false;

            if goal_continuity_enabled && selected_goal.is_none() {
                let generic_candidates = full_generic_candidates(&candidates, &final_scores);
                let generic_current = current_goal.as_ref().and_then(|goal| {
                    if current_goal_allowed_for_generic(&goal.goal_type) {
                        let action_code = match goal.goal_type.as_str() {
                            "create_shot" => 2,
                            "progress_carry" | "protect_ball" => 0,
                            "through_ball" | "recycle" | "switch_play" => 1,
                            "clear_danger" => 4,
                            _ => 3,
                        };
                        Some(OnBallGenericGoalInput {
                            goal_type: Some(goal.goal_type.as_str()),
                            target_pos: goal.target_pos,
                            value: goal.value,
                            action_code,
                        })
                    } else {
                        None
                    }
                });
                if let Some(generic) =
                    apply_generic_on_ball_goal_continuity(&OnBallGenericContinuityInput {
                        candidates: &generic_candidates,
                        current_goal: generic_current,
                        iq,
                        goal_cut_inside_bias,
                    })
                {
                    final_scores = generic.biased_scores;
                    if let Some(generic_selection) = softmax_select_index(
                        &final_scores,
                        iq,
                        generic_roll,
                        generic_fallback_index,
                    ) {
                        chosen_index = generic_selection.index.min(final_scores.len() - 1);
                        generic_used_roll = generic_selection.total_weight >= 1e-10;
                    } else if !final_scores.is_empty() {
                        chosen_index = generic_fallback_index % final_scores.len();
                        generic_used_random_choice = true;
                    }
                    selected_goal = Some(OnBallFullGoal {
                        goal_type: generic.selected_goal_type,
                        target_pos: generic.selected_target,
                        value: generic.selected_value,
                        confidence: generic.selected_value.clamp(0.0, 1.0),
                        phase: "execute".to_string(),
                        created_tick: tick,
                        candidate_noise: 0.0,
                        candidate_noisy_value: generic.candidate_value,
                    });
                    selected_goal_action_code = generic.selected_action_code as i32;
                    goal_trace_switched = generic.switched;
                    goal_trace_switch_cost = generic.switch_cost;
                    goal_trace_value_advantage = generic.value_advantage;
                    goal_trace_switch_noise = 0.0;
                    goal_trace_noisy_advantage = generic.value_advantage;
                    goal_trace_reason = generic.reason;
                    candidate_choice_noise = 0.0;
                    candidate_choice_noisy_value = generic.candidate_value;
                }
            }

            let final_scores_payload = if final_scores.is_empty() {
                "-".to_string()
            } else {
                final_scores
                    .iter()
                    .map(|value| format!("{value:.15}"))
                    .collect::<Vec<_>>()
                    .join(",")
            };
            let adjusted_scores_payload = if selection.adjusted_scores.is_empty() {
                "-".to_string()
            } else {
                selection
                    .adjusted_scores
                    .iter()
                    .map(|value| format!("{value:.15}"))
                    .collect::<Vec<_>>()
                    .join(",")
            };
            let opportunity_indices_payload = if opportunity_indices.is_empty() {
                "-".to_string()
            } else {
                opportunity_indices
                    .iter()
                    .map(|idx| idx.to_string())
                    .collect::<Vec<_>>()
                    .join(",")
            };
            if let Some(goal) = selected_goal {
                let (goal_type, goal_x, goal_y, goal_value) = goal_output_fields(&goal);
                println!(
                    "{}\t{}\t{}\t{}\t{}\t{}\t1\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{}\t{}\t{}",
                    parts[29],
                    chosen_index,
                    candidates[chosen_index].action_code,
                    final_scores_payload,
                    adjusted_scores_payload,
                    opportunity_indices_payload,
                    goal_type,
                    goal_x,
                    goal_y,
                    goal_value,
                    goal.confidence,
                    goal.phase,
                    goal.created_tick,
                    if goal_trace_switched { "1" } else { "0" },
                    goal_trace_switch_cost,
                    goal_trace_value_advantage,
                    goal_trace_switch_noise,
                    goal_trace_noisy_advantage,
                    goal_trace_reason,
                    candidate_choice_noise,
                    candidate_choice_noisy_value,
                    selected_goal_action_code,
                    if selection.used_roll { "1" } else { "0" },
                    if selection.used_random_choice { "1" } else { "0" },
                    if generic_used_roll { "1" } else { "0" },
                    if generic_used_random_choice { "1" } else { "0" },
                    goal_noise_count,
                    if switch_noise_used { "1" } else { "0" },
                );
            } else {
                println!(
                    "{}\t{}\t{}\t{}\t{}\t{}\t0\t-\t0.000000000000000\t0.000000000000000\t0.000000000000000\t0.000000000000000\t-\t0\t0\t0.000000000000000\t0.000000000000000\t0.000000000000000\t0.000000000000000\t0.000000000000000\t-\t0.000000000000000\t0.000000000000000\t-1\t{}\t{}\t0\t0\t{}\t0",
                    parts[29],
                    chosen_index,
                    candidates[chosen_index].action_code,
                    final_scores_payload,
                    adjusted_scores_payload,
                    opportunity_indices_payload,
                    if selection.used_roll { "1" } else { "0" },
                    if selection.used_random_choice { "1" } else { "0" },
                    goal_noise_count,
                );
            }
            continue;
        }
        if mode == "on_ball_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let candidates = parse_on_ball_selection_candidates(parts[0])?;
            let score_noises = parse_f64_list(parts[3])?;
            let fallback_index = parts[5].parse::<usize>().map_err(|err| err.to_string())?;
            let output = select_on_ball_candidate(&OnBallSelectionInput {
                candidates: &candidates,
                current_goal_hold_for_opportunity: parts[1] == "1",
                iq: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                score_noises: &score_noises,
                roll: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                fallback_index,
            });
            if let Some(output) = output {
                println!(
                    "{}\t{}\t{}\t{}\t{}\t{}",
                    parts[6],
                    output.index,
                    if output.used_roll { "1" } else { "0" },
                    if output.used_random_choice { "1" } else { "0" },
                    output
                        .adjusted_scores
                        .iter()
                        .map(|value| format!("{value:.15}"))
                        .collect::<Vec<_>>()
                        .join(","),
                    output
                        .noisy_scores
                        .iter()
                        .map(|value| format!("{value:.15}"))
                        .collect::<Vec<_>>()
                        .join(",")
                );
            } else {
                println!("{}\t-\t0\t0\t-\t-", parts[6]);
            }
            continue;
        }
        if mode == "on_ball_generic_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let candidates = parse_on_ball_generic_candidates(parts[0])?;
            let current_goal = if parts[1] == "-" {
                None
            } else {
                Some(OnBallGenericGoalInput {
                    goal_type: Some(parts[1]),
                    target_pos: (
                        parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                        parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    ),
                    value: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    action_code: parts[5].parse::<u8>().map_err(|err| err.to_string())?,
                })
            };
            let output = apply_generic_on_ball_goal_continuity(&OnBallGenericContinuityInput {
                candidates: &candidates,
                current_goal,
                iq: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                goal_cut_inside_bias: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
            });
            if let Some(output) = output {
                println!(
                    "{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}\t{}",
                    parts[9],
                    output.selected_goal_type,
                    output.selected_action_code,
                    output.selected_target.0,
                    output.selected_target.1,
                    output.selected_value,
                    output.candidate_goal_type,
                    output.candidate_action_code,
                    output.candidate_target.0,
                    output.candidate_target.1,
                    output.candidate_value,
                    if output.switched { "1" } else { "0" },
                    output.switch_cost,
                    output.value_advantage,
                    output.reason,
                    output
                        .biased_scores
                        .iter()
                        .map(|value| format!("{value:.15}"))
                        .collect::<Vec<_>>()
                        .join(",")
                );
            } else {
                println!("{}\t-", parts[9]);
            }
            continue;
        }
        if mode == "on_ball_specialized_bias" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let candidates = parse_on_ball_specialized_candidates(parts[0])?;
            let output = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
                candidates: &candidates,
                goal_type: parts[1],
                goal_phase: parts[2],
                goal_target: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                goal_value: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                bias: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
            });
            let biased = output
                .biased_scores
                .iter()
                .map(|value| format!("{value:.15}"))
                .collect::<Vec<_>>()
                .join(",");
            let opportunity_indices = if output.opportunity_target_indices.is_empty() {
                "-".to_string()
            } else {
                output
                    .opportunity_target_indices
                    .iter()
                    .map(|idx| idx.to_string())
                    .collect::<Vec<_>>()
                    .join(",")
            };
            println!("{}\t{}\t{}", parts[8], biased, opportunity_indices);
            continue;
        }
        if mode == "cut_inside_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 15 {
                return Err(format!(
                    "expected 15 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let best_carry_target = parse_runner(parts[5], parts[6])?;
            let output = evaluate_cut_inside_goal(&CutInsideGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                best_carry_target,
                future_shot_gain: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                carry_to_shoot_window: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                wide_second_line_carry_window: parts[9]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                current_shot: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                current_readiness: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[12].parse::<i32>().map_err(|err| err.to_string())?,
                goal_age_ticks: parts[13].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[14],
                if output.has_goal { "1" } else { "0" },
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.phase_code,
                output.progress,
                output.width,
                output.finish_window,
                output.drive_staleness,
            );
            continue;
        }
        if mode == "drive_byline_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_drive_byline_goal(&DriveBylineGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                carry_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                carry_score: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                progress_gain: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                byline_carry_window: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                path_feasibility: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                space_manipulation: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                delivery_support: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[13],
                if output.has_goal { "1" } else { "0" },
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.phase_code,
                output.origin_progress,
                output.origin_width,
                output.target_progress,
                output.target_width_or_centrality,
            );
            continue;
        }
        if mode == "byline_delivery_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 16 {
                return Err(format!(
                    "expected 16 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_byline_delivery_goal(&BylineDeliveryGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                delivery_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pass_score: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                target_progress: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                centrality: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                high_threat_space: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                final_third_combination: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                success_prob: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_pressure: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                lane_risk: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[15],
                if output.has_goal { "1" } else { "0" },
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.phase_code,
                output.origin_progress,
                output.origin_width,
                output.target_progress,
                output.target_width_or_centrality,
            );
            continue;
        }
        if mode == "through_ball_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 16 {
                return Err(format!(
                    "expected 16 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_through_ball_goal(&ThroughBallGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                pass_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pass_score: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                target_kind_space: parts[8] == "1",
                target_progress: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                centrality: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                progress_gain: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                high_threat_space: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                success_prob: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_pressure: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                lane_risk: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                "through_ball",
                if output.has_goal { "1" } else { "0" },
                output.target_pos.0,
                output.target_pos.1,
                output.value,
                output.confidence,
                output.origin_progress,
            );
            continue;
        }
        if mode == "wide_overlap_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 11 {
                return Err(format!(
                    "expected 11 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_wide_hold_overlap_goal(&WideHoldOverlapGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                overlap_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                overlap_value: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                immediate_best_score: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let fields = vec![
                if output.has_goal {
                    "1".to_string()
                } else {
                    "0".to_string()
                },
                format!("{:.15}", output.target_pos.0),
                format!("{:.15}", output.target_pos.1),
                format!("{:.15}", output.value),
                format!("{:.15}", output.confidence),
                format!("{:.15}", output.progress),
                format!("{:.15}", output.width),
                format!("{:.15}", output.target_progress),
                format!("{:.15}", output.target_width),
                format!("{:.15}", output.forward_gap),
                format!("{:.15}", output.same_lane),
            ];
            println!("{}\t{}", parts[10], fields.join("\t"));
            continue;
        }
        if mode == "layoff_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 11 {
                return Err(format!(
                    "expected 11 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_layoff_goal(&LayoffGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                layoff_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                attracted_pressure: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                layoff_value: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                immediate_best_score: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let fields = vec![
                if output.has_goal {
                    "1".to_string()
                } else {
                    "0".to_string()
                },
                format!("{:.15}", output.target_pos.0),
                format!("{:.15}", output.target_pos.1),
                format!("{:.15}", output.value),
                format!("{:.15}", output.confidence),
                format!("{:.15}", output.progress),
                format!("{:.15}", output.target_progress),
                format!("{:.15}", output.target_centrality),
                format!("{:.15}", output.pass_distance),
                format!("{:.15}", output.backward_depth),
            ];
            println!("{}\t{}", parts[10], fields.join("\t"));
            continue;
        }
        if mode == "release_support_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_release_support_goal(&ReleaseSupportGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                support_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                support_value: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_goal_fit: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                current_shot: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                shot_readiness: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[11].parse::<i32>().map_err(|err| err.to_string())?,
                attracted_pressure: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            let fields = vec![
                if output.has_goal {
                    "1".to_string()
                } else {
                    "0".to_string()
                },
                format!("{:.15}", output.target_pos.0),
                format!("{:.15}", output.target_pos.1),
                format!("{:.15}", output.value),
                format!("{:.15}", output.confidence),
                format!("{:.15}", output.progress),
                format!("{:.15}", output.target_progress),
                format!("{:.15}", output.target_centrality),
                format!("{:.15}", output.pass_distance),
                format!("{:.15}", output.layer_gap),
                format!("{:.15}", output.release_maturity),
            ];
            println!("{}\t{}", parts[13], fields.join("\t"));
            continue;
        }
        if mode == "hold_opportunity_goal" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = evaluate_hold_opportunity_goal(&HoldOpportunityGoalInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                support_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                support_value: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                hold_value: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                current_shot: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                shot_readiness: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                immediate_best_score: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                goal_age_ticks: parts[12].parse::<i32>().map_err(|err| err.to_string())?,
            });
            let fields = vec![
                if output.has_goal {
                    "1".to_string()
                } else {
                    "0".to_string()
                },
                format!("{:.15}", output.target_pos.0),
                format!("{:.15}", output.target_pos.1),
                format!("{:.15}", output.value),
                format!("{:.15}", output.confidence),
                format!("{:.15}", output.progress),
                format!("{:.15}", output.target_progress),
                format!("{:.15}", output.target_centrality),
                format!("{:.15}", output.pass_distance),
                format!("{:.15}", output.lateral_gap),
                format!("{:.15}", output.opportunity_window),
                format!("{:.15}", output.stale),
            ];
            println!("{}\t{}", parts[13], fields.join("\t"));
            continue;
        }
        if mode == "support_opportunity_cost" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let passes = parse_support_opportunity_passes(parts[0])?;
            let carries = parse_support_opportunity_carries(parts[1])?;
            let output = apply_support_opportunity_cost(&SupportOpportunityInput {
                passes: &passes,
                carries: &carries,
            });
            let scores = output
                .adjusted_scores
                .iter()
                .map(|value| format!("{value:.15}"))
                .collect::<Vec<_>>()
                .join(",");
            let costs = output
                .costs
                .iter()
                .map(|value| format!("{value:.15}"))
                .collect::<Vec<_>>()
                .join(",");
            println!(
                "{}\t{:.15}\t{}\t{}",
                parts[3], output.support_pressure, scores, costs
            );
            continue;
        }
        if mode == "overlap_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let passes = parse_overlap_passes(parts[5])?;
            let output = select_best_overlap(&OverlapSelectionInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                passes: &passes,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}",
                parts[6],
                output
                    .index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.value,
                output.target.0,
                output.target.1,
            );
            continue;
        }
        if mode == "byline_carry_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let teammates = parse_byline_teammates(parts[5])?;
            let carries = parse_byline_carries(parts[6])?;
            let output = select_best_byline_carry(&BylineCarrySelectionInput {
                player_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                player_pos: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                teammates: &teammates,
                carries: &carries,
            });
            println!(
                "{}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                "byline_carry",
                output.delivery_support,
                output
                    .index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.value,
                output.score,
                output.target.0,
                output.target.1,
            );
            continue;
        }
        if mode == "layoff_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let passes = parse_layoff_passes(parts[5])?;
            let opponents = parse_positions(parts[6])?;
            let output = select_best_layoff(&LayoffSelectionInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                passes: &passes,
                opponents: &opponents,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[7],
                output
                    .index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.value,
                output.target.0,
                output.target.1,
                output.attracted_pressure,
            );
            continue;
        }
        if mode == "arriving_support_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let passes = parse_arriving_support_passes(parts[2])?;
            let opponents = parse_positions(parts[3])?;
            let output = select_best_arriving_support(&ArrivingSupportSelectionInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passes: &passes,
                opponents: &opponents,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[4],
                output
                    .index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.fit,
                output.target.0,
                output.target.1,
                output.support_value,
                output.receiver_goal_fit,
                output.attracted_pressure,
            );
            continue;
        }
        if mode == "hold_support_select" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let passes = parse_hold_support_passes(parts[5])?;
            let carries = parse_hold_support_carries(parts[6])?;
            let holds = parse_hold_support_holds(parts[7])?;
            let output = select_hold_support(&HoldSupportSelectionInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                passes: &passes,
                carries: &carries,
                holds: &holds,
                current_opportunity_goal: parts[8] == "1",
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[9],
                if output.has_support { "1" } else { "0" },
                output.target.0,
                output.target.1,
                output.fit,
                output.support_value,
                output.hold_support,
                output.no_clear_release,
                output.clear_carry_plan,
                output.support_plan_quality,
                output.carry_interrupt,
            );
            continue;
        }
        if mode == "softmax_select_temp" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let scores = parse_f64_list(parts[0])?;
            let output = softmax_select_index_with_temperature(
                &scores,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<usize>().map_err(|err| err.to_string())?,
            );
            if let Some(output) = output {
                println!(
                    "{}\t{}\t{:.15}\t{:.15}",
                    parts[4], output.index, output.temperature, output.total_weight
                );
            } else {
                println!("{}\t-\t0.000000000000000\t0.000000000000000", parts[4]);
            }
            continue;
        }

        if mode == "defensive_position" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = defensive_position_value(&DefensivePositionValueInput {
                pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                own_goal_x: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                attackers: &parse_positions(parts[7])?,
                teammates: &parse_positions(parts[8])?,
                formation_pos: (
                    parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                ),
            });
            println!("{}\t{value:.15}", parts[11]);
            continue;
        }

        if mode == "receive_reachability" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_positions(parts[7])?;
            let opponent_speeds = parse_f64_list(parts[8])?;
            let value = receive_reachability(
                (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                &opponents,
                &opponent_speeds,
                (
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                parts[10].parse::<f64>().map_err(|err| err.to_string())?,
            );
            println!("{}\t{value:.15}", parts[11]);
            continue;
        }

        if mode == "space_creation" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_positions(parts[2])?;
            let value = space_creation_value(
                (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                &opponents,
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            );
            println!("{}\t{value:.15}", parts[4]);
            continue;
        }

        if mode == "pass_lane_risk" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let origin = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let target = (
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let interception_reach = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[5])?;
            let value = pass_lane_risk(&PassLaneRiskInput {
                origin,
                target,
                opponents: &opponents,
                interception_reach,
            });
            println!("{}\t{value:.15}", parts[6]);
            continue;
        }

        if mode == "receiver_pressure" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let target = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let opponents = parse_positions(parts[2])?;
            let value = receiver_pressure(target, &opponents);
            println!("{}\t{value:.15}", parts[3]);
            continue;
        }

        if mode == "turnover_consequence" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let loss_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let pitch_length = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[5])?;
            let value = turnover_consequence(&TurnoverConsequenceInput {
                loss_pos,
                opponents: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
            });
            println!("{}\t{value:.15}", parts[6]);
            continue;
        }

        if mode == "state_value" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let player_index = parts[2].parse::<usize>().map_err(|err| err.to_string())?;
            let finishing = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
            let long_shot = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_length = parts[5].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[6].parse::<f64>().map_err(|err| err.to_string())?;
            let attacking_right = match parts[7] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let shot_ideal_distance = parts[8].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_on_target_base = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let gk_save_base = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[11])?;
            let teammates = parse_indexed_positions(parts[12])?;
            let value = state_value(&StateValueInput {
                pos,
                player_index,
                player_team_home: true,
                tick: 0,
                finishing,
                long_shot,
                teammate_positions: &teammates,
                teammate_goalkeeper_indices: &[],
                opponent_positions: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                shot_ideal_distance,
                shot_on_target_base,
                gk_save_base,
                shot_quality_cache: None,
            });
            println!("{}\t{value:.15}", parts[13]);
            continue;
        }

        if mode == "pass_receive_value" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 22 {
                return Err(format!(
                    "expected 22 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let receiver_index = parts[2].parse::<usize>().map_err(|err| err.to_string())?;
            let finishing = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
            let long_shot = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let receiver_anchor = (
                parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let receiver_base = (
                parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let pitch_length = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let attacking_right = match parts[11] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let shot_ideal_distance = parts[12].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_on_target_base = parts[13].parse::<f64>().map_err(|err| err.to_string())?;
            let gk_save_base = parts[14].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[15])?;
            let teammates = parse_indexed_positions(parts[16])?;
            let receiver_goal_type = if parts[17] == "-" {
                None
            } else {
                Some(parts[17])
            };
            let receiver_goal_target = parse_runner(parts[18], parts[19])?;
            let receiver_goal_value = parts[20].parse::<f64>().map_err(|err| err.to_string())?;
            let value = pass_receive_value(&PassReceiveValueInput {
                pos,
                receiver_index,
                receiver_team_home: true,
                tick: 0,
                finishing,
                long_shot,
                receiver_anchor,
                receiver_base,
                teammate_positions: &teammates,
                teammate_goalkeeper_indices: &[],
                opponent_positions: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                shot_ideal_distance,
                shot_on_target_base,
                gk_save_base,
                receiver_goal_type,
                receiver_goal_target,
                receiver_goal_value,
                shot_quality_cache: None,
            });
            println!("{}\t{value:.15}", parts[21]);
            continue;
        }

        if mode == "pass_receive_breakdown" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 23 {
                return Err(format!(
                    "expected 23 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let receiver_index = parts[2].parse::<usize>().map_err(|err| err.to_string())?;
            let finishing = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
            let long_shot = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let receiver_anchor = (
                parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let receiver_base = (
                parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let pitch_length = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let attacking_right = match parts[11] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let shot_ideal_distance = parts[12].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_on_target_base = parts[13].parse::<f64>().map_err(|err| err.to_string())?;
            let gk_save_base = parts[14].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[15])?;
            let teammates = parse_indexed_positions(parts[16])?;
            let receiver_goal_type = if parts[17] == "-" {
                None
            } else {
                Some(parts[17])
            };
            let receiver_goal_target = parse_runner(parts[18], parts[19])?;
            let receiver_goal_value = parts[20].parse::<f64>().map_err(|err| err.to_string())?;
            let teammate_goalkeeper_indices = parse_usize_list(parts[21])?;
            let value = pass_receive_value_breakdown(&PassReceiveValueInput {
                pos,
                receiver_index,
                receiver_team_home: true,
                tick: 0,
                finishing,
                long_shot,
                receiver_anchor,
                receiver_base,
                teammate_positions: &teammates,
                teammate_goalkeeper_indices: &teammate_goalkeeper_indices,
                opponent_positions: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                shot_ideal_distance,
                shot_on_target_base,
                gk_save_base,
                receiver_goal_type,
                receiver_goal_target,
                receiver_goal_value,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[22],
                value.value,
                value.spatial,
                value.progress,
                value.outlet,
                value.shot,
                value.wide_creation,
                value.inside_arrival,
                value.second_line_arrival,
                value.receiver_goal_arrival,
                value.pressure,
                value.centrality,
                value.width_value,
                value.target_width,
                value.anchor_width,
                value.base_progress,
                value.box_presence,
            );
            continue;
        }

        if mode == "expected_pass" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 32 {
                return Err(format!(
                    "expected 32 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let passer_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let target = (
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let passer_finishing = parts[4].parse::<f64>().map_err(|err| err.to_string())?;
            let passer_long_shot = parts[5].parse::<f64>().map_err(|err| err.to_string())?;
            let passer_consecutive_carries =
                parts[6].parse::<i32>().map_err(|err| err.to_string())?;
            let receiver_index = parts[7].parse::<usize>().map_err(|err| err.to_string())?;
            let receiver_finishing = parts[8].parse::<f64>().map_err(|err| err.to_string())?;
            let receiver_long_shot = parts[9].parse::<f64>().map_err(|err| err.to_string())?;
            let receiver_anchor = (
                parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                parts[11].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let receiver_base = (
                parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                parts[13].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let attacking_right = match parts[14] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let pitch_length = parts[15].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[16].parse::<f64>().map_err(|err| err.to_string())?;
            let interception_reach = parts[17].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_ideal_distance = parts[18].parse::<f64>().map_err(|err| err.to_string())?;
            let shot_on_target_base = parts[19].parse::<f64>().map_err(|err| err.to_string())?;
            let gk_save_base = parts[20].parse::<f64>().map_err(|err| err.to_string())?;
            let current_value = parts[21].parse::<f64>().map_err(|err| err.to_string())?;
            let base_accuracy = parts[22].parse::<f64>().map_err(|err| err.to_string())?;
            let receiver_arrival = parts[23].parse::<f64>().map_err(|err| err.to_string())?;
            let continuity = parts[24].parse::<f64>().map_err(|err| err.to_string())?;
            let opponents = parse_positions(parts[25])?;
            let teammates = parse_indexed_positions(parts[26])?;
            let receiver_goal_type = if parts[27] == "-" {
                None
            } else {
                Some(parts[27])
            };
            let receiver_goal_target = parse_runner(parts[28], parts[29])?;
            let receiver_goal_value = parts[30].parse::<f64>().map_err(|err| err.to_string())?;
            let value = expected_pass_value(&ExpectedPassInput {
                tick: 0,
                passer_index: 0,
                passer_team_home: true,
                passer_pos,
                passer_finishing,
                passer_long_shot,
                passer_consecutive_carries,
                receiver_index,
                receiver_team_home: true,
                receiver_finishing,
                receiver_long_shot,
                receiver_anchor,
                receiver_base,
                receiver_goal_type,
                receiver_goal_target,
                receiver_goal_value,
                target,
                teammate_positions: &teammates,
                teammate_goalkeeper_indices: &[],
                opponent_positions: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                interception_reach,
                shot_ideal_distance,
                shot_on_target_base,
                gk_save_base,
                current_value,
                base_accuracy,
                receiver_arrival,
                continuity,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[31],
                value.score,
                value.success_prob,
                value.risk_cost,
                value.after_value,
                value.effective_delta,
                value.continuity,
                value.lane_risk,
                value.receiver_pressure,
                value.turnover_consequence,
            );
            continue;
        }

        if mode == "hold" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 13 {
                return Err(format!(
                    "expected 13 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = evaluate_hold(&HoldInput {
                iq: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                is_midfielder: parts[1] == "1",
                is_defender: parts[2] == "1",
                hold_ticks: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                possession_ticks: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                current_pv: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pressure: parts[6].parse::<i32>().map_err(|err| err.to_string())?,
                nearest_pressure: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                developing_runs: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                best_pass_score: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                shoot_score: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                opportunity_wait_value: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[12],
                value.score,
                value.pressure_factor,
                value.useful_development,
                value.no_clear_release,
                value.opportunity_wait,
                value.opportunity_cost,
            );
            continue;
        }

        if mode == "clear" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 4 {
                return Err(format!(
                    "expected 4 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let value = evaluate_clear(&ClearInput {
                x_progress: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                pressure: parts[1].parse::<i32>().map_err(|err| err.to_string())?,
                clear_reward_base: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}",
                parts[3], value.score, value.danger, value.pressure_factor,
            );
            continue;
        }

        if mode == "shot_eval" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 25 {
                return Err(format!(
                    "expected 25 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[17] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_positions(parts[22])?;
            let teammates = parse_shot_support(parts[23])?;
            let value = evaluate_shot(&ShotInput {
                tick: 0,
                shooter_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                shooter_team_home: true,
                shooter_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                finishing: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                long_shot: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                possession_ticks: parts[5].parse::<i32>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[6].parse::<i32>().map_err(|err| err.to_string())?,
                last_receive_origin: (
                    parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                dist_to_goal: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                angle_factor: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                pressure_factor: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                lane_factor: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                dist_factor: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                current_state_value: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                shot_on_target_base: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
                goal_reward_constant: parts[21].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                teammates: &teammates,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[24],
                value.score,
                value.on_target_prob,
                value.xg,
                value.save_estimate,
                value.risk_cost,
                value.opportunity_cost,
                value.shot_readiness,
                value.possession_loss_multiplier,
                value.support_release_window,
            );
            continue;
        }

        if mode == "shot_option" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 20 {
                return Err(format!(
                    "expected 20 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[5] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let shooter_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let pitch_length = parts[6].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[7].parse::<f64>().map_err(|err| err.to_string())?;
            let goal_width = parts[8].parse::<f64>().map_err(|err| err.to_string())?;
            let goal_center = if attacking_right {
                (pitch_length, pitch_width / 2.0)
            } else {
                (0.0, pitch_width / 2.0)
            };
            let dist_to_goal = distance(shooter_pos, goal_center);
            let dist_factor =
                if dist_to_goal <= parts[9].parse::<f64>().map_err(|err| err.to_string())? {
                    1.0
                } else if dist_to_goal <= 30.0 {
                    let excess =
                        dist_to_goal - parts[9].parse::<f64>().map_err(|err| err.to_string())?;
                    (1.0 - excess * 0.070).max(0.18)
                } else {
                    0.45 * (-(dist_to_goal - 30.0) / 14.0).exp()
                };
            let angle = angle_to_goal(shooter_pos, goal_center, goal_width);
            let angle_factor = (angle / 0.2).min(1.0);
            let opponents = parse_positions(parts[18])?;
            let mut pressure_factor: f64 = 1.0;
            let mut lane_factor: f64 = 1.0;
            let shot_dx = goal_center.0 - shooter_pos.0;
            let shot_dy = goal_center.1 - shooter_pos.1;
            let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
            if shot_len > 1.0 {
                let nx = shot_dx / shot_len;
                let ny = shot_dy / shot_len;
                for opp in &opponents {
                    let d = distance(shooter_pos, *opp);
                    if d < 8.0 {
                        pressure_factor *= (1.0 - (8.0 - d) * 0.035).max(0.72);
                    }
                    let ox = opp.0 - shooter_pos.0;
                    let oy = opp.1 - shooter_pos.1;
                    let proj = ox * nx + oy * ny;
                    if 1.0 < proj && proj < shot_len - 1.0 {
                        let perp = (ox * ny - oy * nx).abs();
                        if perp < 4.5 {
                            lane_factor *= (1.0 - (4.5 - perp) * 0.05).max(0.65);
                        }
                    }
                }
            }
            let teammates = parse_shot_support(parts[19])?;
            let value = evaluate_shot(&ShotInput {
                tick: 0,
                shooter_index: parts[2].parse::<usize>().map_err(|err| err.to_string())?,
                shooter_team_home: true,
                shooter_pos,
                finishing: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                long_shot: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                possession_ticks: parts[10].parse::<i32>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[11].parse::<i32>().map_err(|err| err.to_string())?,
                last_receive_origin: (
                    parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                dist_to_goal,
                angle_factor,
                pressure_factor,
                lane_factor,
                dist_factor,
                current_state_value: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                teammates: &teammates,
                opponents: &opponents,
                pitch_length,
                pitch_width,
                attacking_right,
                shot_on_target_base: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                goal_reward_constant: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                "shot_option",
                value.score,
                value.on_target_prob,
                value.xg,
                value.save_estimate,
                value.risk_cost,
                value.opportunity_cost,
                value.shot_readiness,
                value.possession_loss_multiplier,
                value.support_release_window,
                goal_center.0,
                goal_center.1,
            );
            continue;
        }

        if mode == "carry_eval" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 23 {
                return Err(format!(
                    "expected 23 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[15] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_positions(parts[20])?;
            let teammates = parse_carry_support(parts[21])?;
            let value = evaluate_carry(&CarryInput {
                tick: 0,
                carrier_index: parts[0].parse::<usize>().map_err(|err| err.to_string())?,
                carrier_team_home: true,
                carrier_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                finishing: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                long_shot: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                possession_ticks: parts[8].parse::<i32>().map_err(|err| err.to_string())?,
                target_pv: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                current_pv: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                current_state_value: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                path_feasibility: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                carrier_speed: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                shot_ideal_distance: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                shot_on_target_base: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                gk_save_base: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                teammates: &teammates,
                shot_quality_cache: None,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[22],
                value.score,
                value.after_value,
                value.risk_cost,
                value.continuity,
                value.pv_gain,
                value.future_shot_gain,
                value.carry_to_shoot_window,
                value.effective_gain,
                value.near_goal_multiplier,
                value.release_pressure,
                value.space_manipulation,
            );
            continue;
        }

        if mode == "carry_offsets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = generate_carry_offsets(&CarryTargetGenerationInput {
                carrier_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                speed: parts[2].parse::<i32>().map_err(|err| err.to_string())?,
                dribbling: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                nearest_opponent_distance: parts[10]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
            });
            let payload = output
                .offsets
                .iter()
                .map(|value| format!("{:.15},{:.15}", value.0, value.1))
                .collect::<Vec<_>>()
                .join(";");
            println!("{}\t{}", parts[11], payload);
            continue;
        }

        if mode == "carry_path" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 13 {
                return Err(format!(
                    "expected 13 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_carry_path_opponents(parts[11])?;
            let output = evaluate_carry_path(&CarryPathInput {
                carrier_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                dribbling: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                tackle_range: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[12],
                output.feasibility,
                output.path_min_perp,
                output.path_peak_threat,
                output.path_peak_proj,
                output.path_peak_final_third_control,
                output.path_peak_control_factor,
            );
            continue;
        }

        if mode == "carry_finalize" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = finalize_carry_score(&CarryFinalizeInput {
                evaluator_score: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                feasibility: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                path_peak_threat: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                path_peak_final_third_control: parts[3]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                consecutive_carries: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[5],
                output.score,
                output.conflict_cost,
                output.repeated_load,
                output.feasibility_loss,
            );
            continue;
        }

        if mode == "carry_options" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 24 {
                return Err(format!(
                    "expected 24 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[9] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_carry_path_opponents(parts[21])?;
            let teammates = parse_carry_support(parts[22])?;
            let opponent_positions: Vec<(f64, f64)> = opponents
                .iter()
                .filter(|opp| !opp.is_goalkeeper)
                .map(|opp| opp.pos)
                .collect();
            let carrier_index = parts[0].parse::<usize>().map_err(|err| err.to_string())?;
            let teammate_positions: Vec<(f64, f64)> = teammates
                .iter()
                .filter(|tm| tm.index != carrier_index)
                .map(|tm| tm.pos)
                .collect();
            let carrier_pos = (
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                parts[2].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let pitch_length = parts[10].parse::<f64>().map_err(|err| err.to_string())?;
            let pitch_width = parts[11].parse::<f64>().map_err(|err| err.to_string())?;
            let current_pv = position_value(&PositionValueInput {
                x: carrier_pos.0,
                y: carrier_pos.1,
                pitch_length,
                pitch_width,
                attacking_right,
                opponent_positions: &opponent_positions,
                teammate_positions: &teammate_positions,
                runner_formation_pos: None,
            });
            let nearest_opp = opponents
                .iter()
                .filter(|opp| !opp.is_goalkeeper)
                .map(|opp| distance(carrier_pos, opp.pos))
                .fold(99.0, f64::min);
            let offsets = generate_carry_offsets(&CarryTargetGenerationInput {
                carrier_pos,
                speed: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                dribbling: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length,
                pitch_width,
                player_max_speed: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                nearest_opponent_distance: nearest_opp,
            });
            let mut seen: Vec<(i64, i64)> = Vec::new();
            let mut outputs = Vec::new();
            for offset in offsets.offsets {
                let target = (
                    (carrier_pos.0 + offset.0).clamp(0.5, pitch_length - 0.5),
                    (carrier_pos.1 + offset.1).clamp(0.5, pitch_width - 0.5),
                );
                let key = (
                    (target.0 * 10.0).round() as i64,
                    (target.1 * 10.0).round() as i64,
                );
                if seen.contains(&key) {
                    continue;
                }
                seen.push(key);
                let target_pv = position_value(&PositionValueInput {
                    x: target.0,
                    y: target.1,
                    pitch_length,
                    pitch_width,
                    attacking_right,
                    opponent_positions: &opponent_positions,
                    teammate_positions: &teammate_positions,
                    runner_formation_pos: None,
                });
                let path = evaluate_carry_path(&CarryPathInput {
                    carrier_pos,
                    target,
                    dribbling: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    attacking_right,
                    pitch_length,
                    pitch_width,
                    player_max_speed: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                    carrier_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                    tackle_range: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                    opponents: &opponents,
                });
                let carry = evaluate_carry(&CarryInput {
                    tick: 0,
                    carrier_index,
                    carrier_team_home: true,
                    carrier_pos,
                    target,
                    finishing: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    long_shot: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                    consecutive_carries: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                    possession_ticks: parts[8].parse::<i32>().map_err(|err| err.to_string())?,
                    target_pv,
                    current_pv,
                    current_state_value: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                    path_feasibility: path.feasibility,
                    pitch_length,
                    pitch_width,
                    attacking_right,
                    carrier_speed: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                    shot_ideal_distance: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                    shot_on_target_base: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                    gk_save_base: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                    opponents: &opponent_positions,
                    teammates: &teammates,
                    shot_quality_cache: None,
                });
                let final_score = finalize_carry_score(&CarryFinalizeInput {
                    evaluator_score: carry.score,
                    feasibility: path.feasibility,
                    path_peak_threat: path.path_peak_threat,
                    path_peak_final_third_control: path.path_peak_final_third_control,
                    consecutive_carries: parts[7].parse::<i32>().map_err(|err| err.to_string())?,
                });
                outputs.push(
                    vec![
                        format!("{:.15}", final_score.score),
                        format!("{:.15}", target.0),
                        format!("{:.15}", target.1),
                        format!("{:.15}", path.feasibility),
                        format!("{:.15}", carry.risk_cost),
                        format!("{:.15}", carry.after_value),
                        format!("{:.15}", carry.continuity),
                        format!("{:.15}", carry.pv_gain),
                        format!("{:.15}", carry.future_shot_gain),
                        format!("{:.15}", carry.carry_to_shoot_window),
                        format!("{:.15}", carry.wide_second_line_carry_window),
                        format!("{:.15}", carry.byline_carry_window),
                        format!("{:.15}", carry.half_space_entry),
                        format!("{:.15}", carry.lane_gain),
                        format!("{:.15}", carry.progress_gain),
                        format!("{:.15}", carry.effective_gain),
                        format!("{:.15}", carry.near_goal_multiplier),
                        format!("{:.15}", carry.shooting_window_multiplier),
                        format!("{:.15}", carry.possession_multiplier),
                        format!("{:.15}", carry.final_third_stale_multiplier),
                        format!("{:.15}", carry.release_pressure),
                        format!("{:.15}", carry.support_nearby),
                        format!("{:.15}", carry.pressure_draw),
                        format!("{:.15}", carry.space_manipulation),
                        format!(
                            "{:.15}",
                            if path.path_min_perp < 99.0 {
                                path.path_min_perp
                            } else {
                                0.0
                            }
                        ),
                        format!("{:.15}", path.path_peak_threat),
                        format!("{:.15}", path.path_peak_proj),
                        format!("{:.15}", path.path_peak_final_third_control),
                        format!("{:.15}", final_score.conflict_cost),
                    ]
                    .join(","),
                );
            }
            println!(
                "{}\t{}",
                parts[23],
                if outputs.is_empty() {
                    "-".to_string()
                } else {
                    outputs.join(";")
                }
            );
            continue;
        }

        if mode == "detect_duel" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let defenders = parse_defender_actions(parts[6])?;
            let value = detect_duel(&DuelDetectionInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                holder_action: parts[2],
                carry_target: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tackle_range: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                defenders: &defenders,
            });
            println!(
                "{}\t{}\t{:.15}",
                parts[7],
                value
                    .defender_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                value.distance
            );
            continue;
        }

        if mode == "carry_execution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 19 {
                return Err(format!(
                    "expected 19 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_execution_opponents(parts[16])?;
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = execute_carry(&CarryExecutionInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                speed_ability: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                dribbling: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                carry_error_divisor: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[13].parse::<i32>().map_err(|err| err.to_string())?,
                error_roll: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                loose_y_roll: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}",
                parts[18],
                output.carry_speed,
                output.carry_difficulty,
                output.new_pos.0,
                output.new_pos.1,
                output.distance_covered,
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                output.loose_pos.0,
                output.loose_pos.1,
            );
            continue;
        }
        if mode == "carry_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 19 {
                return Err(format!(
                    "expected 19 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_execution_opponents(parts[16])?;
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = carry_phase_plan(&CarryPhasePlanInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                speed_ability: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                dribbling: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                carrier_speed: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                carry_error_divisor: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                consecutive_carries: parts[13].parse::<i32>().map_err(|err| err.to_string())?,
                error_roll: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                loose_y_roll: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}",
                parts[18],
                output.carry_speed,
                output.carry_difficulty,
                output.new_pos.0,
                output.new_pos.1,
                output.distance_covered,
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                output.loose_pos.0,
                output.loose_pos.1,
                output.randoms_used,
            );
            continue;
        }

        if mode == "pass_execution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 19 {
                return Err(format!(
                    "expected 19 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let opponents = parse_execution_opponents(parts[11])?;
            let output = execute_pass(&PassExecutionInput {
                passer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ideal_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passing: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                is_long: parts[5] == "1",
                lane_risk: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                ball_pass_speed: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                ball_long_pass_speed: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                pass_error_divisor: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                random_1: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                random_2: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                random_3: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                random_4: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
                random_5: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}\t{}",
                parts[18],
                output.target.0,
                output.target.1,
                output.error_radius,
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                if output.used_target_error { "1" } else { "0" },
                output.randoms_used,
                output.stray_pos.0,
                output.stray_pos.1,
                output.ticks_needed,
                output.speed,
                output.flight_type_code,
            );
            continue;
        }

        if mode == "shot_execution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 13 {
                return Err(format!(
                    "expected 13 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[3] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = execute_shot(&ShotExecutionInput {
                shooter_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                on_target_prob: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                goal_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                ball_shot_speed: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                random_1: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                random_2: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                random_3: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{}\t{}\t{:.15}\t{:.15}\t{}",
                parts[12],
                if output.on_target { "1" } else { "0" },
                output.target.0,
                output.target.1,
                output.ticks_needed,
                output.randoms_used,
                output.speed,
                output.distance,
                output.flight_type_code,
            );
            continue;
        }

        if mode == "clear_execution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = execute_clear(&ClearExecutionInput {
                clearer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_long_pass_speed: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}",
                parts[5],
                output.speed,
                output.ticks_needed,
                output.origin.0,
                output.origin.1,
                output.target.0,
                output.target.1,
                output.flight_type_code,
            );
            continue;
        }
        if mode == "clear_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = clear_phase_plan(&ClearPhasePlanInput {
                clearer_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_long_pass_speed: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}",
                parts[5],
                output.origin.0,
                output.origin.1,
                output.target.0,
                output.target.1,
                output.speed,
                output.ticks_needed,
                output.flight_type_code,
            );
            continue;
        }

        if mode == "clear_target" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 8 {
                return Err(format!(
                    "expected 8 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[2] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = generate_clear_target(&ClearTargetInput {
                player_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                depth_roll: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                lateral_roll: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}",
                parts[7], output.target.0, output.target.1,
            );
            continue;
        }

        if mode == "hold_execution" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[3] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_execution_opponents(parts[7])?;
            let opportunity_target = parse_runner(parts[8], parts[9])?;
            let output = execute_hold(&HoldExecutionInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                dribbling: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                carry_error_divisor: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                opportunity_target,
                error_roll: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                loose_y_roll: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}\t{}",
                parts[13],
                output.new_pos.0,
                output.new_pos.1,
                output.distance_covered,
                output.pressure,
                output.nearest_dist,
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                output.loose_pos.0,
                output.loose_pos.1,
                output.randoms_used,
                output.trace_pressure,
                output.trace_nearest_dist.map(|value| format!("{value:.15}")).unwrap_or_else(|| "-".to_string()),
            );
            continue;
        }
        if mode == "hold_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[3] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let opponents = parse_execution_opponents(parts[7])?;
            let opportunity_target = parse_runner(parts[8], parts[9])?;
            let output = hold_phase_plan(&HoldPhasePlanInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                dribbling: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                attacking_right,
                pitch_length: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                carry_error_divisor: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                opponents: &opponents,
                opportunity_target,
                error_roll: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                loose_y_roll: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}\t{}",
                parts[13],
                output.new_pos.0,
                output.new_pos.1,
                output.distance_covered,
                output.pressure,
                output.nearest_dist,
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                output.loose_pos.0,
                output.loose_pos.1,
                output.randoms_used,
                output.trace_pressure,
                output.trace_nearest_dist.map(|value| format!("{value:.15}")).unwrap_or_else(|| "-".to_string()),
            );
            continue;
        }

        if mode == "pass_arrival" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receivers = parse_arrival_players(parts[7])?;
            let opponents = parse_arrival_players(parts[8])?;
            let output = resolve_pass_arrival(&PassArrivalInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                flight_ticks_total: parts[2].parse::<i32>().map_err(|err| err.to_string())?,
                passer_team_is_receiver_team: true,
                contest_radius: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                target_occupation_weight: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                receivers: &receivers,
                opponents: &opponents,
            });
            println!(
                "{}\t{}\t{}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}",
                parts[9],
                output.winner_code,
                output
                    .receiver_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.receiver_score,
                output.receiver_control,
                output
                    .opponent_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.opponent_score,
                output.opponent_control,
                output.loose_control,
            );
            continue;
        }
        if mode == "pass_arrival_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let receivers = parse_arrival_players(parts[11])?;
            let opponents = parse_arrival_players(parts[12])?;
            let output = pass_arrival_plan(&PassArrivalPlanInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                flight_origin: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                flight_speed: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                flight_ticks_total: parts[5].parse::<i32>().map_err(|err| err.to_string())?,
                contest_radius: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                target_occupation_weight: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                receivers: &receivers,
                opponents: &opponents,
            });
            println!(
                "{}\t{}\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}",
                parts[13],
                output.outcome_code,
                output
                    .receiver_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output
                    .opponent_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.loose_velocity.0,
                output.loose_velocity.1,
                output.receiver_score,
                output.receiver_control,
                output.opponent_score,
                output.opponent_control,
                output.loose_control,
            );
            continue;
        }

        if mode == "first_touch" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = resolve_first_touch(&FirstTouchInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                iq: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_length: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                first_touch_error_divisor: parts[5]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                error_roll: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                loose_y_roll: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "first_touch\t{:.15}\t{}\t{:.15}\t{:.15}",
                output.error_chance,
                if output.is_error { "1" } else { "0" },
                output.loose_pos.0,
                output.loose_pos.1,
            );
            continue;
        }
        if mode == "pass_receive_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 13 {
                return Err(format!(
                    "expected 13 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = pass_receive_plan(&PassReceivePlanInput {
                receiver_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                target_pos: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                receiver_iq: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                receiver_offside_flagged: parts[5] == "1",
                pitch_length: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                first_touch_error_divisor: parts[8]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                error_roll: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                loose_y_roll: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{}",
                parts[12],
                output.outcome_code,
                output.receive_pos.0,
                output.receive_pos.1,
                output.loose_pos.0,
                output.loose_pos.1,
                output.distance_covered,
                output.receive_kind_code,
                output.first_touch_error_chance,
                output.randoms_used,
            );
            continue;
        }

        if mode == "shot_arrival" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 18 {
                return Err(format!(
                    "expected 18 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[4] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = resolve_shot_arrival(&ShotArrivalInput {
                shot_origin: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                shot_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                on_target: parts[5] == "1",
                pitch_length: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                gk_pos: (
                    parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                gk_saving: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                gk_positioning: parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                gk_reaction: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                gk_position_error_factor: parts[13]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_reaction_delay_factor: parts[14]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_save_base: parts[15].parse::<f64>().map_err(|err| err.to_string())?,
                save_roll: parts[16].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{}",
                parts[17],
                if output.in_box { "1" } else { "0" },
                output.save_prob,
                output.outcome_code,
            );
            continue;
        }
        if mode == "shot_arrival_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 21 {
                return Err(format!(
                    "expected 21 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attacking_right = match parts[6] {
                "1" | "true" | "True" => true,
                "0" | "false" | "False" => false,
                other => return Err(format!("invalid attacking_right: {other}")),
            };
            let output = shot_arrival_plan(&ShotArrivalPlanInput {
                shooter_name: parts[0],
                keeper_name: parts[1],
                shot_origin: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                shot_target: (
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right,
                on_target: parts[7] == "1",
                pitch_length: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                gk_pos: (
                    parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[11].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                gk_saving: parts[12].parse::<f64>().map_err(|err| err.to_string())?,
                gk_positioning: parts[13].parse::<f64>().map_err(|err| err.to_string())?,
                gk_reaction: parts[14].parse::<f64>().map_err(|err| err.to_string())?,
                gk_position_error_factor: parts[15]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_reaction_delay_factor: parts[16]
                    .parse::<f64>()
                    .map_err(|err| err.to_string())?,
                gk_save_base: parts[17].parse::<f64>().map_err(|err| err.to_string())?,
                save_roll: parts[18].parse::<f64>().map_err(|err| err.to_string())?,
                total_xg: parts[19].parse::<f64>().map_err(|err| err.to_string())?,
                logged_xg_sum: parts[20].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "shot_arrival_plan\t{}\t{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}",
                output.outcome_code,
                if output.in_box { "1" } else { "0" },
                output.save_prob,
                output.raw_xg,
                output.rounded_xg,
                output.psxg_delta,
                output.shot_log.x,
                output.shot_log.y,
                output.shot_log.outcome,
                output.shot_log.target_x.map(|value| format!("{value:.15}")).unwrap_or_else(|| "-".to_string()),
                output.shot_log.target_y.map(|value| format!("{value:.15}")).unwrap_or_else(|| "-".to_string()),
                output.pause_ms,
                output.trace_event,
                output.pending_event_text,
                if output.shot_log.in_box { "1" } else { "0" },
            );
            continue;
        }

        if mode == "clearance_arrival" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let home_players = parse_clearance_players(parts[2])?;
            let away_players = parse_clearance_players(parts[3])?;
            let output = resolve_clearance_arrival(&ClearanceArrivalInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                home_players: &home_players,
                away_players: &away_players,
            });
            println!(
                "{}\t{}\t{}\t{:.15}\t{:.15}",
                parts[5],
                output.winner_code,
                output
                    .player_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.home_distance,
                output.away_distance,
            );
            continue;
        }
        if mode == "clearance_arrival_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let home_players = parse_clearance_players(parts[2])?;
            let away_players = parse_clearance_players(parts[3])?;
            let output = clearance_arrival_plan(&ClearanceArrivalPlanInput {
                target_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                passer_team_home: parts[4] == "1",
                home_players: &home_players,
                away_players: &away_players,
            });
            println!(
                "{}\t{}\t{}\t{}\t{:.15}\t{:.15}",
                parts[6],
                output.winner_code,
                output
                    .player_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                if output.passer_completed { "1" } else { "0" },
                output.home_distance,
                output.away_distance,
            );
            continue;
        }

        if mode == "contested_owner" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let home_players = parse_contested_owner_players(parts[4])?;
            let away_players = parse_contested_owner_players(parts[5])?;
            let output = resolve_contested_owner(&ContestedOwnerInput {
                ball_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                contest_radius: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                contested_ticks: parts[3].parse::<i32>().map_err(|err| err.to_string())?,
                home_players: &home_players,
                away_players: &away_players,
            });
            println!(
                "{}\t{}\t{}\t{:.15}\t{}\t{}",
                parts[6],
                output
                    .winner_code
                    .map(|code| code.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output
                    .player_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.distance,
                if output.immediate_win { "1" } else { "0" },
                if output.forced_win { "1" } else { "0" },
            );
            continue;
        }

        if mode == "contested_tick" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = tick_contested_ball(&ContestedTickInput {
                position: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                loose_velocity: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                contested_ticks: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}",
                parts[5],
                output.position.0,
                output.position.1,
                output.loose_velocity.0,
                output.loose_velocity.1,
                output.contested_ticks,
            );
            continue;
        }
        if mode == "contested_tick_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 11 {
                return Err(format!(
                    "expected 11 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let home_players = parse_contested_owner_players(parts[8])?;
            let away_players = parse_contested_owner_players(parts[9])?;
            let output = contested_tick_plan(&ContestedTickPlanInput {
                position: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                loose_velocity: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                contested_ticks: parts[4].parse::<i32>().map_err(|err| err.to_string())?,
                pitch_length: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                contest_radius: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                home_players: &home_players,
                away_players: &away_players,
            });
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}\t{:.15}\t{}\t{}\t{}\t{:.15}\t{}\t{}",
                parts[10],
                output.position.0,
                output.position.1,
                output.loose_velocity.0,
                output.loose_velocity.1,
                output.contested_ticks,
                output
                    .winner_code
                    .map(|code| code.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output
                    .player_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                output.distance,
                if output.immediate_win { "1" } else { "0" },
                if output.forced_win { "1" } else { "0" },
            );
            continue;
        }

        if mode == "contested_targets" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 9 {
                return Err(format!(
                    "expected 9 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let players = parse_contested_target_players(parts[7])?;
            let outputs = select_contested_targets(&ContestedTargetsInput {
                ball_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                player_max_speed: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                player_min_speed: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                contested_race_radius: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                players: &players,
            });
            let payload = if outputs.is_empty() {
                "-".to_string()
            } else {
                outputs
                    .iter()
                    .map(|output| {
                        format!(
                            "{},{:.15},{:.15},{}",
                            output.index, output.target.0, output.target.1, output.intent_code
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[8], payload);
            continue;
        }

        if mode == "detect_interactions" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 10 {
                return Err(format!(
                    "expected 10 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let holder_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let action = parts[2];
            let target = (
                parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let tackle_range = parts[5].parse::<f64>().map_err(|err| err.to_string())?;
            let interception_reach = parts[6].parse::<f64>().map_err(|err| err.to_string())?;
            let defenders = parse_defender_actions(parts[7])?;
            let duel = detect_duel(&DuelDetectionInput {
                holder_pos,
                holder_action: action,
                carry_target: target,
                tackle_range,
                defenders: &defenders,
            });
            let interception = detect_interception(&InterceptionDetectionInput {
                pass_origin: holder_pos,
                pass_target: target,
                interception_reach,
                defenders: &defenders,
            });
            let wasted = detect_wasted_tackle(&WastedTackleInput {
                holder_pos,
                holder_action: action,
                tackle_range,
                defenders: &defenders,
            });
            let wasted_payload = if wasted.is_empty() {
                "-".to_string()
            } else {
                wasted
                    .iter()
                    .map(|value| {
                        format!(
                            "{}:{:.15}",
                            value.defender_index.unwrap_or(usize::MAX),
                            value.distance
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!(
                "{}\t{}\t{:.15}\t{}\t{:.15}\t{}",
                parts[9],
                duel.defender_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                duel.distance,
                interception
                    .defender_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                interception.distance,
                wasted_payload
            );
            continue;
        }

        if mode == "defensive_pressures" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let holder_pos = (
                parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                parts[1].parse::<f64>().map_err(|err| err.to_string())?,
            );
            let defenders = parse_defender_actions(parts[4])?;
            let outputs = track_defensive_pressures(&DefensivePressureInput {
                holder_pos,
                holder_action: parts[2],
                press_radius: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                defenders: &defenders,
                duel_detected: parts[5] == "1",
                interception_detected: parts[6] == "1",
            });
            let payload = if outputs.is_empty() {
                "-".to_string()
            } else {
                outputs
                    .iter()
                    .map(|output| {
                        format!(
                            "{}:{}",
                            output.defender_index,
                            if output.successful { "1" } else { "0" }
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("pressures\t{}", payload);
            continue;
        }
        if mode == "defensive_pressure_adjust" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 14 {
                return Err(format!(
                    "expected 14 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let defenders = parse_defensive_pressure_adjust_players(parts[12])?;
            let output = defensive_pressure_adjust_plan(&DefensivePressureAdjustInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                holder_consecutive_carries: parts[2]
                    .parse::<i32>()
                    .map_err(|err| err.to_string())?,
                holder_team_attacking_right: parts[3] == "1",
                opp_team_attacking_right: parts[4] == "1",
                holder_action_type: parts[5],
                ball_is_held_by_holder: parts[6] == "1",
                pitch_length: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                tackle_range: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                press_radius: parts[10].parse::<f64>().map_err(|err| err.to_string())?,
                defenders: &defenders,
            });
            let payload = if output.targets.is_empty() {
                "-".to_string()
            } else {
                output
                    .targets
                    .iter()
                    .map(|target| {
                        format!(
                            "{},{:.15},{:.15},{}",
                            target.index,
                            target.target_pos.0,
                            target.target_pos.1,
                            target.movement_intent_code,
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[13], payload);
            continue;
        }
        if mode == "defense_zone_helper" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 12 {
                return Err(format!(
                    "expected 12 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let attackers = parse_defense_zone_attackers(parts[10])?;
            let input = DefenseZoneHelperInput {
                defender_pos: (
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                tactical_anchor: (
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                ball_pos: (
                    parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                attacking_right: parts[7] == "1",
                pitch_length: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
                attackers: &attackers,
            };
            let output = match parts[0] {
                "mark" => score_mark_runner_zone(&input),
                "block" => score_block_lane_zone(&input),
                "mark_legacy" => score_mark_runner_legacy(&input),
                "block_legacy" => score_block_lane_legacy(&input),
                other => return Err(format!("unknown defense zone helper: {other}")),
            };
            println!(
                "{}\t{:.15}\t{:.15}\t{:.15}",
                parts[11], output.score, output.target.0, output.target.1
            );
            continue;
        }

        if mode == "detect_interception" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 7 {
                return Err(format!(
                    "expected 7 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let defenders = parse_defender_actions(parts[5])?;
            let value = detect_interception(&InterceptionDetectionInput {
                pass_origin: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                pass_target: (
                    parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                interception_reach: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                defenders: &defenders,
            });
            println!(
                "{}\t{}\t{:.15}",
                parts[6],
                value
                    .defender_index
                    .map(|idx| idx.to_string())
                    .unwrap_or_else(|| "-".to_string()),
                value.distance
            );
            continue;
        }

        if mode == "detect_wasted_tackle" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let defenders = parse_defender_actions(parts[4])?;
            let values = detect_wasted_tackle(&WastedTackleInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                holder_action: parts[2],
                tackle_range: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                defenders: &defenders,
            });
            let payload = if values.is_empty() {
                "-".to_string()
            } else {
                values
                    .iter()
                    .map(|value| {
                        format!(
                            "{}:{:.15}",
                            value.defender_index.unwrap_or(usize::MAX),
                            value.distance
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(";")
            };
            println!("{}\t{}", parts[5], payload);
            continue;
        }

        if mode == "resolve_duel" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 5 {
                return Err(format!(
                    "expected 5 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let outcome = resolve_duel(&DuelResolveInput {
                attacker_dribbling: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                defender_tackling: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                attacker_uniform: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                defender_uniform: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!("{}\t{}", parts[4], outcome);
            continue;
        }
        if mode == "duel_phase_plan" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 11 {
                return Err(format!(
                    "expected 11 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let output = duel_phase_plan(&DuelPhasePlanInput {
                holder_pos: (
                    parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                    parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                ),
                pitch_length: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                pitch_width: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                attacker_dribbling: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
                defender_tackling: parts[5].parse::<f64>().map_err(|err| err.to_string())?,
                attacker_uniform: parts[6].parse::<f64>().map_err(|err| err.to_string())?,
                defender_uniform: parts[7].parse::<f64>().map_err(|err| err.to_string())?,
                loose_x_roll: parts[8].parse::<f64>().map_err(|err| err.to_string())?,
                loose_y_roll: parts[9].parse::<f64>().map_err(|err| err.to_string())?,
            });
            println!(
                "{}\t{}\t{:.15}\t{:.15}\t{}",
                parts[10],
                output.outcome_code,
                output.loose_pos.0,
                output.loose_pos.1,
                output.randoms_used,
            );
            continue;
        }

        if mode == "resolve_interception" {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() != 6 {
                return Err(format!(
                    "expected 6 tab-separated fields, got {}",
                    parts.len()
                ));
            }
            let input = InterceptionResolveInput {
                defender_defence: parts[0].parse::<f64>().map_err(|err| err.to_string())?,
                passer_ability: parts[1].parse::<f64>().map_err(|err| err.to_string())?,
                distance: parts[2].parse::<f64>().map_err(|err| err.to_string())?,
                interception_reach: parts[3].parse::<f64>().map_err(|err| err.to_string())?,
                random_value: parts[4].parse::<f64>().map_err(|err| err.to_string())?,
            };
            println!(
                "{}\t{}\t{:.15}",
                parts[5],
                if resolve_interception(&input) {
                    "1"
                } else {
                    "0"
                },
                interception_chance(&input)
            );
            continue;
        }

        if mode != "position_value" {
            return Err(format!("unknown mode: {mode}"));
        }
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() != 10 {
            return Err(format!(
                "expected 10 tab-separated fields, got {}",
                parts.len()
            ));
        }
        let x = parts[0].parse::<f64>().map_err(|err| err.to_string())?;
        let y = parts[1].parse::<f64>().map_err(|err| err.to_string())?;
        let pitch_length = parts[2].parse::<f64>().map_err(|err| err.to_string())?;
        let pitch_width = parts[3].parse::<f64>().map_err(|err| err.to_string())?;
        let attacking_right = match parts[4] {
            "1" | "true" | "True" => true,
            "0" | "false" | "False" => false,
            other => return Err(format!("invalid attacking_right: {other}")),
        };
        let runner_formation_pos = parse_runner(parts[5], parts[6])?;
        let opponent_positions = parse_positions(parts[7])?;
        let teammate_positions = parse_positions(parts[8])?;
        let value = position_value(&PositionValueInput {
            x,
            y,
            pitch_length,
            pitch_width,
            attacking_right,
            opponent_positions: &opponent_positions,
            teammate_positions: &teammate_positions,
            runner_formation_pos,
        });
        println!("{}\t{value:.15}", parts[9]);
    }
    Ok(())
}
