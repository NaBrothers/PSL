use serde::{Deserialize, Serialize};
use serde_json::json;
use std::cell::RefCell;
use std::collections::HashMap;

use crate::shot_quality::ShotQualityCache;
use crate::{
    angle_to_goal, apply_specialized_on_ball_bias, apply_support_opportunity_cost,
    build_defensive_goal, build_off_ball_attack_goal, build_vision_context, carry_phase_plan,
    choose_defense_action, choose_off_ball_attack_target, clear_phase_plan, clearance_arrival_plan,
    detect_duel, detect_interception, distance, duel_phase_plan, evaluate_arc_arrival_goal,
    evaluate_attack_far_post_goal, evaluate_byline_delivery_goal, evaluate_carry,
    evaluate_carry_path, evaluate_clear, evaluate_cut_inside_goal, evaluate_drive_byline_goal,
    evaluate_hold, evaluate_hold_opportunity_goal, evaluate_layoff_goal,
    evaluate_release_support_goal, evaluate_shot, evaluate_through_ball_goal,
    evaluate_wide_hold_overlap_goal, expected_pass_value, finalize_carry_score,
    generate_carry_offsets, gk_position_adjust, hold_phase_plan, kickoff_shape_targets,
    out_of_bounds_plan, pass_arrival_plan, pass_phase_plan, pass_receive_plan, player_apply_stun,
    player_move_speed, player_move_tick, player_set_movement_target, player_speed,
    player_tick_stun, position_value, restart_play_plan, restart_shape_plan, score_goal_plan,
    select_best_arriving_support, select_best_byline_carry, select_best_layoff,
    select_best_overlap, select_contested_targets, select_goal_candidate_with_gaussians,
    select_goal_deterministic, select_hold_support, select_on_ball_candidate, shot_arrival_plan,
    shot_phase_plan, shot_quality_at, softmax_select_index, state_value,
    team_pass_candidates_batch, team_shape_plan, tick_ball_flight, tick_contested_ball,
    track_carry_stats, track_defensive_pressures, track_pass_stats, ArcArrivalGoalInput,
    ArrivalPlayerInput, ArrivingSupportPassInput, ArrivingSupportSelectionInput,
    AttackFarPostGoalInput, BylineCarryInput, BylineCarrySelectionInput, BylineDeliveryGoalInput,
    BylineSupportTeammateInput, CarryFinalizeInput, CarryInput, CarryPathInput,
    CarryPathOpponentInput, CarryPhasePlanInput, CarryStatInput, CarrySupportPlayer,
    CarryTargetGenerationInput, ClearInput, ClearPhasePlanInput, ClearanceArrivalPlanInput,
    ClearancePlayerInput, ContestedTargetPlayerInput, ContestedTargetsInput, ContestedTickInput,
    CutInsideGoalInput, DefenderActionInput, DefenseChoiceInput, DefenseRandomSample,
    DefenseTeammateInput, DefensiveGoalBuildInput, DefensivePressureInput, DriveBylineGoalInput,
    DuelDetectionInput, DuelPhasePlanInput, ExecutionOpponent, ExpectedPassInput, FlightTickInput,
    GkPositionAdjustInput, GoalInput, GoalSwitchCostInput, HoldInput, HoldOpportunityGoalInput,
    HoldPhasePlanInput, HoldSupportCarryInput, HoldSupportHoldInput, HoldSupportPassInput,
    HoldSupportSelectionInput, InterceptionDetectionInput, KickoffPlayerInput, KickoffShapeInput,
    LayoffGoalInput, LayoffPassInput, LayoffSelectionInput, OffBallAttackChoiceInput,
    OffBallAttackGoalBuildInput, OffBallRawGenerationInput, OffBallTeammateInput,
    OnBallGenericCandidateInput, OnBallGenericGoalInput, OnBallSelectionCandidateInput,
    OnBallSelectionInput, OnBallSelectionOutput, OnBallSpecializedBiasCandidateInput,
    OnBallSpecializedBiasInput, OutOfBoundsPlanInput, OverlapPassInput, OverlapSelectionInput,
    PassArrivalPlanInput, PassPhasePlanInput, PassReceivePlanInput, PassRiskPlayer,
    PassSpacePlayer, PassStatInput, PassTeamPlayer, PlayerApplyStunInput, PlayerMoveSpeedInput,
    PlayerMoveTickInput, PlayerSetMovementTargetInput, PlayerTickStunInput, PositionValueInput,
    RandomPolarSample, ReleaseSupportGoalInput, RestartPlayPlanInput, RestartPlayerInput,
    RestartShapePlanInput, RestartShapePlayerInput, ScoreGoalPlanInput, ShotArrivalPlanInput,
    ShotInput, ShotLogEntryOutput, ShotPhasePlanInput, ShotQualityInput, ShotSupportPlayer,
    StateValueInput, SupportOpportunityCarryInput, SupportOpportunityInput,
    SupportOpportunityPassInput, TeamPassBatchInput, TeamPhaseUpdateInput, TeamShapeOpponentInput,
    TeamShapePlanInput, TeamShapePlayerInput, ThroughBallGoalInput, VisionContextInput,
    WideHoldOverlapGoalInput,
};

#[derive(Clone, Copy)]
struct Formation {
    positions: [&'static str; 11],
    coordinates: [(f64, f64); 11],
}

#[derive(Clone)]
struct RunnerPlayer {
    name: String,
    position: String,
    color: String,
    base_pos: (f64, f64),
    tactical_anchor: (f64, f64),
    pos: (f64, f64),
    target_pos: (f64, f64),
    velocity: (f64, f64),
    facing_direction: f64,
    last_receive_origin: (f64, f64),
    state: String,
    stun_ticks_remaining: i32,
    movement_intent: String,
    last_def_target: (f64, f64),
    last_def_action: String,
    last_pressure_tick: i32,
    goal_type: Option<String>,
    goal_phase: Option<String>,
    goal_target: (f64, f64),
    goal_value: f64,
    goal_created_tick: i32,
    goal_action_code: u8,
    finishing: f64,
    long_shot: f64,
    short_passing: f64,
    long_passing: f64,
    dribbling: f64,
    tackling: f64,
    defence: f64,
    speed: f64,
    iq: f64,
    gk_saving: f64,
    gk_positioning: f64,
    gk_reaction: f64,
    shots: i32,
    xg: f64,
    goals: i32,
    assists: i32,
    shots_on_target: i32,
    saves: i32,
    goals_conceded: i32,
    psxg_faced: f64,
    shot_log: Vec<serde_json::Value>,
    holds: i32,
    passes_attempted: i32,
    passes_completed: i32,
    key_passes: i32,
    progressive_passes: i32,
    passes_into_final_third: i32,
    passes_into_box: i32,
    long_passes: i32,
    completed_long_passes: i32,
    crosses_attempted: i32,
    crosses_completed: i32,
    carries_attempted: i32,
    carries_completed: i32,
    dribbles_attempted: i32,
    dribbles_completed: i32,
    progressive_carries: i32,
    carries_into_final_third: i32,
    carries_into_box: i32,
    clearances: i32,
    blocks: i32,
    interceptions: i32,
    pressures: i32,
    successful_pressures: i32,
    tackles_attempted: i32,
    tackles_won: i32,
    turnovers: i32,
    dispossessed: i32,
    offsides: i32,
    distance_covered: f64,
    position_samples: Vec<serde_json::Value>,
    hold_ticks: i32,
    possession_ticks: i32,
    consecutive_carries: i32,
}

#[derive(Clone, Copy, Debug)]
enum RunnerHeldAction {
    Hold {
        opportunity_target: Option<(f64, f64)>,
    },
    Carry {
        target: (f64, f64),
    },
    Pass {
        receiver_idx: usize,
        target: (f64, f64),
        is_long: bool,
        lane_risk: f64,
    },
    Clear {
        target: (f64, f64),
    },
    Shoot {
        target: (f64, f64),
        xg: f64,
        on_target_prob: f64,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RunnerFlightKind {
    Pass,
    Clearance,
    Shot,
}

#[derive(Clone, Copy, Debug)]
struct RunnerEvaluatedAction {
    action: RunnerHeldAction,
    score: f64,
    success_prob: f64,
    receiver_pressure: f64,
    high_threat_space: f64,
    final_third_combination: f64,
    second_line_arrival_value: f64,
    second_line_cutback_value: f64,
    layoff_support_value: f64,
    short_combination_value: f64,
    layoff_retention_value: f64,
    receiver_goal_fit: f64,
    target_kind_space: bool,
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
    opportunity_wait: f64,
    opportunity_wait_value: f64,
    no_clear_release: f64,
    raw_score: f64,
    debug_final_score: f64,
    debug_hold_ticks: i32,
    debug_possession_ticks: i32,
    debug_best_pass_score: f64,
    debug_shoot_score: f64,
    debug_current_pv: f64,
    debug_effective_current_value: f64,
    debug_delta: f64,
    debug_after_value: f64,
    debug_effective_delta: f64,
    debug_continuity: f64,
    debug_risk_cost: f64,
    debug_base_accuracy: f64,
    debug_receiver_arrival: f64,
    debug_lane_risk: f64,
    debug_turnover_consequence: f64,
    debug_defender_first_risk: f64,
    debug_target_occupation_risk: f64,
    debug_nearest_pressure: f64,
    debug_developing_runs: f64,
    debug_hold_multiplier: f64,
    debug_path_min_perp: f64,
    debug_path_peak_threat: f64,
    debug_path_peak_proj: f64,
    debug_path_peak_final_third_control: f64,
    debug_path_peak_control_factor: f64,
    debug_path_conflict_cost: f64,
}

#[derive(Clone, Debug)]
struct RunnerSpecializedGoal {
    goal_type: &'static str,
    phase: &'static str,
    target: (f64, f64),
    value: f64,
    created_tick: i32,
    action_code: u8,
}

#[derive(Clone, Debug)]
struct RunnerGoalSummary {
    goal_type: String,
    target: (f64, f64),
    value: f64,
}

#[derive(Clone, Debug)]
struct RunnerGoalSwitchResult {
    summary: RunnerGoalSummary,
    switched: bool,
    switch_cost: f64,
    value_advantage: f64,
    reason: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RunnerBallState {
    Held,
    InFlight,
    Dead,
    Contested,
}

#[derive(Clone, Debug)]
struct RunnerBall {
    state: RunnerBallState,
    position: (f64, f64),
    holder_idx: Option<usize>,
    holder_team_home: Option<bool>,
    flight: Option<RunnerFlight>,
    loose_velocity: (f64, f64),
    contested_ticks: i32,
}

#[derive(Clone, Debug)]
struct RunnerFlight {
    kind: RunnerFlightKind,
    origin: (f64, f64),
    target: (f64, f64),
    ticks_elapsed: i32,
    ticks_total: i32,
    passer_idx: usize,
    passer_team_home: bool,
    intended_receiver_idx: Option<usize>,
    offside_indices: Vec<usize>,
    last_passer_team_home: Option<bool>,
    last_passer_idx: i32,
    on_target: bool,
    speed: f64,
}

#[derive(Clone, Debug)]
struct RunnerMatchState {
    ball: RunnerBall,
    home_score: i32,
    away_score: i32,
    goals: Vec<serde_json::Value>,
    home_possession_ticks: i32,
    away_possession_ticks: i32,
    neutral_ticks: i32,
    dead_reason: Option<String>,
    restart_team_home: Option<bool>,
    restart_ticks_remaining: i32,
    last_passer_team_home: Option<bool>,
    last_passer_idx: i32,
    pass_network: HashMap<String, i32>,
    held_action_cursor: usize,
    pending_on_ball_goal_event: Option<serde_json::Value>,
    pending_ball_flight: Option<serde_json::Value>,
    pending_replay_frames: Vec<serde_json::Value>,
    trace_entries: Vec<serde_json::Value>,
    trace_decisions: Vec<serde_json::Value>,
    shot_quality_cache: ShotQualityCache,
    home_phase_code: u8,
    away_phase_code: u8,
    home_had_possession_last_tick: bool,
    away_had_possession_last_tick: bool,
    home_ticks_since_possession_change: i32,
    away_ticks_since_possession_change: i32,
    rng_trace_enabled: bool,
}

#[derive(Clone, Debug)]
struct RunnerRuntimeConfig {
    pitch_length: f64,
    pitch_width: f64,
    tick_duration: f64,
    total_ticks: i32,
    half_ticks: i32,
    frame_interval: i32,
    transition_ticks: i32,
    goal_kick_restart_ticks: i32,
    throw_in_restart_ticks: i32,
    player_max_speed: f64,
    player_min_speed: f64,
    ball_pass_speed: f64,
    ball_long_pass_speed: f64,
    ball_shot_speed: f64,
    goal_width: f64,
    contest_radius: f64,
    contested_race_radius: f64,
    press_radius: f64,
    tackle_range: f64,
    interception_reach: f64,
    short_pass_base_success: f64,
    long_pass_base_success: f64,
    shot_ideal_distance: f64,
    shot_on_target_base: f64,
    gk_save_base: f64,
    gk_position_error_factor: f64,
    gk_reaction_delay_factor: f64,
    clear_reward_base: f64,
    carrier_speed: f64,
    iq_noise_scale: f64,
    goal_noise_scale: f64,
    vision_base_fov: f64,
    vision_iq_bonus_factor: f64,
    vision_base_distance: f64,
    vision_iq_distance_bonus_factor: f64,
    vision_max_distance: f64,
    pass_to_space_ball_speed: f64,
    receive_reachability_scale: f64,
    space_creation_radius: f64,
    find_space_radius: f64,
    pass_error_divisor: f64,
    first_touch_error_divisor: f64,
    carry_error_divisor: f64,
    tackle_fail_stun_seconds: f64,
    target_occupation_weight: f64,
    runner_shot_threshold: f64,
    runner_forced_action: Option<String>,
    runner_forced_actions: Vec<String>,
    runner_force_defender_lane: bool,
    runner_forced_pass_target: Option<(f64, f64)>,
    runner_forced_clear_target: Option<(f64, f64)>,
    runner_force_receiver_offside: bool,
    runner_force_specialized_goal: Option<String>,
    trace_detail: String,
    trace_top_k: usize,
}

#[derive(Debug, Deserialize)]
pub struct MatchV2RunRequest {
    pub home_cards: Vec<serde_json::Value>,
    pub away_cards: Vec<serde_json::Value>,
    pub home_formation: String,
    pub away_formation: String,
    #[serde(default)]
    pub config: serde_json::Value,
    #[serde(default)]
    pub seed: Option<u64>,
}

#[derive(Debug, Serialize)]
pub struct MatchV2RunResponse {
    pub home_score: i32,
    pub away_score: i32,
    pub goals: Vec<serde_json::Value>,
    pub home_stats: serde_json::Value,
    pub away_stats: serde_json::Value,
    pub home_player_stats: Vec<serde_json::Value>,
    pub away_player_stats: Vec<serde_json::Value>,
    pub home_ratings: Vec<serde_json::Value>,
    pub away_ratings: Vec<serde_json::Value>,
    pub replay_url: Option<String>,
    pub trace_id: String,
    pub replay: Vec<serde_json::Value>,
    pub trace: serde_json::Value,
    pub engine: String,
    pub contract_version: i32,
}

fn formation_data(key: &str) -> Formation {
    match key {
        "433" => Formation {
            positions: [
                "GK", "LB", "LCB", "RCB", "RB", "LCM", "CM", "RCM", "LW", "ST", "RW",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (28.0, 80.0),
                (42.0, 80.0),
                (56.0, 72.0),
                (22.0, 52.0),
                (34.0, 52.0),
                (44.0, 52.0),
                (14.0, 20.0),
                (34.0, 20.0),
                (56.0, 20.0),
            ],
        },
        "343" => Formation {
            positions: [
                "GK", "LCB", "CB", "RCB", "LM", "LCM", "RCM", "RM", "LW", "ST", "RW",
            ],
            coordinates: [
                (34.0, 100.0),
                (22.0, 80.0),
                (34.0, 80.0),
                (44.0, 80.0),
                (14.0, 52.0),
                (28.0, 52.0),
                (42.0, 52.0),
                (56.0, 52.0),
                (14.0, 20.0),
                (34.0, 20.0),
                (56.0, 20.0),
            ],
        },
        "4231" => Formation {
            positions: [
                "GK", "LB", "LCB", "RCB", "RB", "LDM", "RDM", "LM", "RM", "CAM", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (28.0, 80.0),
                (42.0, 80.0),
                (56.0, 72.0),
                (28.0, 64.0),
                (40.0, 64.0),
                (14.0, 42.0),
                (56.0, 42.0),
                (34.0, 34.0),
                (34.0, 20.0),
            ],
        },
        "352" => Formation {
            positions: [
                "GK", "LCB", "CB", "RCB", "LDM", "RDM", "LM", "RM", "CAM", "CF", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (22.0, 80.0),
                (34.0, 80.0),
                (46.0, 80.0),
                (28.0, 64.0),
                (40.0, 64.0),
                (14.0, 50.0),
                (56.0, 50.0),
                (34.0, 36.0),
                (27.0, 24.0),
                (41.0, 24.0),
            ],
        },
        "532" => Formation {
            positions: [
                "GK", "LB", "LCB", "CB", "RCB", "RB", "CDM", "LCM", "RCM", "CF", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (22.0, 80.0),
                (34.0, 80.0),
                (46.0, 80.0),
                (56.0, 72.0),
                (34.0, 64.0),
                (27.0, 50.0),
                (41.0, 50.0),
                (27.0, 24.0),
                (41.0, 24.0),
            ],
        },
        "4141" => Formation {
            positions: [
                "GK", "LB", "LCB", "RCB", "RB", "CDM", "LM", "LCM", "RCM", "RM", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (28.0, 80.0),
                (42.0, 80.0),
                (56.0, 72.0),
                (34.0, 64.0),
                (14.0, 48.0),
                (28.0, 50.0),
                (40.0, 50.0),
                (56.0, 48.0),
                (34.0, 20.0),
            ],
        },
        "451" => Formation {
            positions: [
                "GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "CM", "RCM", "RM", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (28.0, 80.0),
                (42.0, 80.0),
                (56.0, 72.0),
                (14.0, 50.0),
                (24.0, 52.0),
                (34.0, 54.0),
                (44.0, 52.0),
                (56.0, 50.0),
                (34.0, 20.0),
            ],
        },
        _ => Formation {
            positions: [
                "GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "CF", "ST",
            ],
            coordinates: [
                (34.0, 100.0),
                (14.0, 72.0),
                (28.0, 80.0),
                (42.0, 80.0),
                (56.0, 72.0),
                (14.0, 52.0),
                (28.0, 52.0),
                (42.0, 52.0),
                (56.0, 52.0),
                (27.0, 24.0),
                (41.0, 24.0),
            ],
        },
    }
}

#[cfg(test)]
mod tests {
    use super::RunnerRng;

    #[test]
    fn runner_rng_matches_python_random_seed_for_known_sequence() {
        let mut rng = RunnerRng::new(20260708);
        let expected = [
            0.03745044616550175,
            0.5373435693444919,
            0.42743285789357766,
            0.36923587014317016,
            0.2655924554793485,
            0.024004317727937985,
            0.6547114417572446,
            0.7083697411687409,
            0.5148515095807112,
            0.5818085255195788,
        ];
        for expected_value in expected {
            assert!((rng.random() - expected_value).abs() < 1e-15);
        }
    }

    #[test]
    fn runner_rng_gauss_matches_python_random_seed_for_known_sequence() {
        let mut rng = RunnerRng::new(20260708);
        let expected = [
            1.2073731435999857,
            0.2894670856190923,
            -0.8619500061098534,
            0.4227159413127983,
            -0.021562136205345174,
        ];
        for expected_value in expected {
            assert!((rng.gauss(0.0, 1.0) - expected_value).abs() < 1e-15);
        }
    }
}

fn config_f64(config: &serde_json::Value, key: &str, default: f64) -> f64 {
    config
        .get(key)
        .and_then(|value| value.as_f64())
        .unwrap_or(default)
}

fn config_i32(config: &serde_json::Value, key: &str, default: i32) -> i32 {
    config
        .get(key)
        .and_then(|value| value.as_i64())
        .map(|value| value as i32)
        .unwrap_or(default)
}

fn config_string(config: &serde_json::Value, key: &str) -> Option<String> {
    config
        .get(key)
        .and_then(|value| value.as_str())
        .map(|value| value.to_string())
}

#[derive(Clone)]
struct RunnerRng {
    mt: [u32; 624],
    index: usize,
    gauss_next: Option<f64>,
    draws: usize,
}

impl RunnerRng {
    fn new(seed: u64) -> Self {
        let mut rng = Self {
            mt: [0; 624],
            index: 624,
            gauss_next: None,
            draws: 0,
        };
        let mut key = vec![seed as u32];
        let high = (seed >> 32) as u32;
        if high != 0 {
            key.push(high);
        }
        rng.init_by_array(&key);
        rng
    }

    fn init_genrand(&mut self, seed: u32) {
        self.mt[0] = seed;
        for i in 1..624 {
            let prev = self.mt[i - 1];
            self.mt[i] = 1812433253u32
                .wrapping_mul(prev ^ (prev >> 30))
                .wrapping_add(i as u32);
        }
        self.index = 624;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19650218);
        let mut i = 1usize;
        let mut j = 0usize;
        let mut k = 624usize.max(key.len());
        while k > 0 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ ((prev ^ (prev >> 30)).wrapping_mul(1664525)))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= 624 {
                self.mt[0] = self.mt[623];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
            k -= 1;
        }
        k = 623;
        while k > 0 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ ((prev ^ (prev >> 30)).wrapping_mul(1566083941)))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= 624 {
                self.mt[0] = self.mt[623];
                i = 1;
            }
            k -= 1;
        }
        self.mt[0] = 0x8000_0000;
        self.index = 624;
    }

    fn twist(&mut self) {
        const N: usize = 624;
        const M: usize = 397;
        const MATRIX_A: u32 = 0x9908_b0df;
        const UPPER_MASK: u32 = 0x8000_0000;
        const LOWER_MASK: u32 = 0x7fff_ffff;
        for kk in 0..(N - M) {
            let y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk + 1] & LOWER_MASK);
            self.mt[kk] = self.mt[kk + M] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
        }
        for kk in (N - M)..(N - 1) {
            let y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk + 1] & LOWER_MASK);
            self.mt[kk] = self.mt[kk + M - N] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
        }
        let y = (self.mt[N - 1] & UPPER_MASK) | (self.mt[0] & LOWER_MASK);
        self.mt[N - 1] = self.mt[M - 1] ^ (y >> 1) ^ if y & 1 != 0 { MATRIX_A } else { 0 };
        self.index = 0;
    }

    fn gen_u32(&mut self) -> u32 {
        if self.index >= 624 {
            self.twist();
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    fn random(&mut self) -> f64 {
        self.draws += 1;
        let a = (self.gen_u32() >> 5) as u64;
        let b = (self.gen_u32() >> 6) as u64;
        ((a << 26) + b) as f64 / 9_007_199_254_740_992.0
    }

    fn uniform(&mut self, low: f64, high: f64) -> f64 {
        low + (high - low) * self.random()
    }

    fn getrandbits(&mut self, k: u32) -> u64 {
        if k == 0 {
            return 0;
        }
        if k <= 32 {
            return (self.gen_u32() >> (32 - k)) as u64;
        }
        let mut bits_left = k;
        let mut shift = 0u32;
        let mut value = 0u64;
        while bits_left > 0 {
            let take = bits_left.min(32);
            let chunk = if take == 32 {
                self.gen_u32() as u64
            } else {
                (self.gen_u32() >> (32 - take)) as u64
            };
            value |= chunk << shift;
            shift += take;
            bits_left -= take;
        }
        value
    }

    fn randbelow(&mut self, n: usize) -> usize {
        if n <= 1 {
            return 0;
        }
        let k = usize::BITS - n.leading_zeros();
        loop {
            let value = self.getrandbits(k) as usize;
            if value < n {
                return value;
            }
        }
    }

    fn gauss(&mut self, mu: f64, sigma: f64) -> f64 {
        if let Some(next) = self.gauss_next.take() {
            return mu + next * sigma;
        }
        let x2pi = self.random() * std::f64::consts::TAU;
        let g2rad = (-2.0 * (1.0 - self.random()).ln()).sqrt();
        let z = x2pi.cos() * g2rad;
        self.gauss_next = Some(x2pi.sin() * g2rad);
        mu + z * sigma
    }
}

fn iq_score_noises(
    rng: &mut RunnerRng,
    count: usize,
    iq: f64,
    config: &RunnerRuntimeConfig,
) -> Vec<f64> {
    let noise_scale = crate::goal::iq_decision_noise(iq) * config.iq_noise_scale;
    (0..count).map(|_| rng.gauss(0.0, noise_scale)).collect()
}

fn goal_noise_sigma(input: &GoalSwitchCostInput, goal_noise_scale: f64) -> f64 {
    let base = goal_noise_scale.max(0.0);
    if base <= 0.0 {
        return 0.0;
    }
    let iq_instability = crate::goal::iq_decision_noise(input.iq);
    let pressure = input.pressure_interrupt.clamp(0.0, 1.0);
    base * (0.25 + iq_instability) * (1.0 + 0.35 * pressure)
}

fn runner_goal_gaussians(
    rng: &mut RunnerRng,
    count: usize,
    input: &GoalSwitchCostInput,
    goal_noise_scale: f64,
) -> Vec<f64> {
    let sigma = goal_noise_sigma(input, goal_noise_scale);
    if sigma <= 0.0 {
        vec![0.0; count]
    } else {
        (0..count).map(|_| rng.gauss(0.0, sigma)).collect()
    }
}

fn select_runner_goal_with_noise(
    current_goal: Option<&GoalInput<'_>>,
    candidate_goal: &GoalInput<'_>,
    context: &GoalSwitchCostInput,
    goal_noise_scale: f64,
    rng: &mut RunnerRng,
) -> crate::GoalSelectionOutput {
    if current_goal.is_none() {
        return select_goal_deterministic(current_goal, candidate_goal, context);
    }
    let current = current_goal.unwrap();
    let current_phase = current.phase.or_else(|| {
        if current.goal_type.starts_with("defend_") {
            Some("defend")
        } else {
            None
        }
    });
    let candidate_phase = candidate_goal.phase;
    if current.goal_type == candidate_goal.goal_type
        && matches!(candidate_phase, Some("finish") | Some("release"))
        && candidate_phase != current_phase
    {
        return select_goal_deterministic(current_goal, candidate_goal, context);
    }
    if current.goal_type == "cut_inside_to_shoot"
        && candidate_goal.goal_type == "cut_inside_to_shoot"
        && current_phase == Some("drive")
        && candidate_phase == Some("drive")
    {
        return select_goal_deterministic(current_goal, candidate_goal, context);
    }
    if current.goal_type == "hold_for_opportunity"
        && candidate_goal.goal_type == "hold_for_opportunity"
        && current_phase == Some("scan")
        && candidate_phase == Some("scan")
    {
        return select_goal_deterministic(current_goal, candidate_goal, context);
    }
    if current_phase == Some("defend") && candidate_phase == Some("defend") {
        return select_goal_deterministic(current_goal, candidate_goal, context);
    }

    let sigma = goal_noise_sigma(context, goal_noise_scale);
    let switch_noise_input = if sigma > 0.0 {
        rng.gauss(0.0, sigma)
    } else {
        0.0
    };
    let switch_noise =
        crate::goal::goal_selection_noise_from_gauss(context, goal_noise_scale, switch_noise_input);
    let switch_cost = crate::goal::goal_switch_cost(context);
    let advantage = candidate_goal.value - current.value;
    let noisy_advantage = advantage + switch_noise;
    if noisy_advantage > switch_cost {
        crate::GoalSelectionOutput {
            selected: "candidate".to_string(),
            switched: true,
            switch_cost,
            value_advantage: advantage,
            noisy_value_advantage: noisy_advantage,
            reason: "candidate_clears_switch_cost".to_string(),
        }
    } else {
        crate::GoalSelectionOutput {
            selected: "current".to_string(),
            switched: false,
            switch_cost,
            value_advantage: advantage,
            noisy_value_advantage: noisy_advantage,
            reason: "current_goal_within_switch_cost".to_string(),
        }
    }
}

fn random_attack_samples(rng: &mut RunnerRng, count: usize) -> Vec<RandomPolarSample> {
    (0..count)
        .map(|_| RandomPolarSample {
            angle_unit: rng.random(),
            radius_unit: rng.random(),
        })
        .collect()
}

fn random_defense_samples(rng: &mut RunnerRng, count: usize) -> Vec<DefenseRandomSample> {
    (0..count)
        .map(|_| DefenseRandomSample {
            angle_unit: rng.random(),
            radius_unit: rng.random(),
        })
        .collect()
}

fn preview_randoms<const N: usize>(rng: &RunnerRng) -> [f64; N] {
    let mut preview = rng.clone();
    let mut values = [0.0; N];
    for value in &mut values {
        *value = preview.random();
    }
    values
}

fn advance_randoms(rng: &mut RunnerRng, count: usize) {
    for _ in 0..count {
        let _ = rng.random();
    }
}

fn preview_next_random(rng: &RunnerRng) -> f64 {
    let mut preview = rng.clone();
    preview.random()
}

fn push_rng_trace(state: &mut RunnerMatchState, tick: i32, label: &str, rng: &RunnerRng) {
    if !state.rng_trace_enabled {
        return;
    }
    state.trace_entries.push(json!({
        "tick": tick,
        "type": "event",
        "event": "rng",
        "label": label,
        "draws": rng.draws,
        "next": preview_next_random(rng),
        "gauss_cached": rng.gauss_next.is_some()
    }));
}

fn push_rng_trace_for_player(
    state: &mut RunnerMatchState,
    tick: i32,
    label: &str,
    player_name: &str,
    rng: &RunnerRng,
) {
    if !state.rng_trace_enabled {
        return;
    }
    state.trace_entries.push(json!({
        "tick": tick,
        "type": "event",
        "event": "rng",
        "label": label,
        "player": player_name,
        "draws": rng.draws,
        "next": preview_next_random(rng),
        "gauss_cached": rng.gauss_next.is_some()
    }));
}

fn runtime_config(config: &serde_json::Value) -> RunnerRuntimeConfig {
    let total_ticks = config_i32(config, "total_ticks", 2700);
    RunnerRuntimeConfig {
        pitch_length: config_f64(config, "pitch_length", 105.0),
        pitch_width: config_f64(config, "pitch_width", 68.0),
        tick_duration: config_f64(config, "tick_duration", 2.0),
        total_ticks,
        half_ticks: config_i32(config, "half_ticks", total_ticks / 2),
        frame_interval: config_i32(config, "frame_interval", 2),
        transition_ticks: config_i32(config, "transition_ticks", 3),
        goal_kick_restart_ticks: config_i32(config, "goal_kick_restart_ticks", 8),
        throw_in_restart_ticks: config_i32(config, "throw_in_restart_ticks", 4),
        player_max_speed: config_f64(config, "player_max_speed", 5.5),
        player_min_speed: config_f64(config, "player_min_speed", 2.5),
        ball_pass_speed: config_f64(config, "ball_pass_speed", 18.0),
        ball_long_pass_speed: config_f64(config, "ball_long_pass_speed", 22.0),
        ball_shot_speed: config_f64(config, "ball_shot_speed", 28.0),
        goal_width: config_f64(config, "goal_width", 7.32),
        contest_radius: config_f64(config, "contest_radius", 2.5),
        contested_race_radius: config_f64(config, "contested_race_radius", 15.0),
        press_radius: config_f64(config, "press_radius", 12.0),
        tackle_range: config_f64(config, "tackle_range", 6.0),
        interception_reach: config_f64(config, "interception_reach", 3.5),
        short_pass_base_success: config_f64(config, "short_pass_base_success", 0.80),
        long_pass_base_success: config_f64(config, "long_pass_base_success", 0.55),
        shot_ideal_distance: config_f64(config, "shot_ideal_distance", 20.0),
        shot_on_target_base: config_f64(config, "shot_on_target_base", 0.50),
        gk_save_base: config_f64(config, "gk_save_base", 0.78),
        gk_position_error_factor: config_f64(config, "gk_position_error_factor", 0.05),
        gk_reaction_delay_factor: config_f64(config, "gk_reaction_delay_factor", 0.005),
        clear_reward_base: config_f64(config, "clear_reward_base", 0.3),
        carrier_speed: config_f64(config, "carrier_speed", 3.0),
        iq_noise_scale: config_f64(config, "iq_noise_scale", 0.3),
        goal_noise_scale: config_f64(config, "goal_noise_scale", 0.008),
        vision_base_fov: config_f64(config, "vision_base_fov", 180.0),
        vision_iq_bonus_factor: config_f64(config, "vision_iq_bonus_factor", 0.5),
        vision_base_distance: config_f64(config, "vision_base_distance", 42.0),
        vision_iq_distance_bonus_factor: config_f64(
            config,
            "vision_iq_distance_bonus_factor",
            0.35,
        ),
        vision_max_distance: config_f64(config, "vision_max_distance", 65.0),
        pass_to_space_ball_speed: config_f64(config, "pass_to_space_ball_speed", 18.0),
        receive_reachability_scale: config_f64(config, "receive_reachability_scale", 1.0),
        space_creation_radius: config_f64(config, "space_creation_radius", 10.0),
        find_space_radius: config_f64(config, "find_space_radius", 15.0),
        pass_error_divisor: config_f64(config, "pass_error_divisor", 800.0),
        first_touch_error_divisor: config_f64(config, "first_touch_error_divisor", 700.0),
        carry_error_divisor: config_f64(config, "carry_error_divisor", 900.0),
        tackle_fail_stun_seconds: config_f64(config, "tackle_fail_stun_seconds", 1.5),
        target_occupation_weight: config_f64(config, "target_occupation_weight", 0.18),
        runner_shot_threshold: config_f64(config, "runner_shot_threshold", 0.18),
        runner_forced_action: config_string(config, "runner_forced_action"),
        runner_forced_actions: config
            .get("runner_forced_actions")
            .and_then(|value| value.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|value| value.to_string()))
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default(),
        runner_force_defender_lane: config
            .get("runner_force_defender_lane")
            .and_then(|value| value.as_bool())
            .unwrap_or(false),
        runner_forced_pass_target: config
            .get("runner_forced_pass_target")
            .and_then(|value| value.as_array())
            .and_then(|items| {
                if items.len() >= 2 {
                    Some((
                        items[0].as_f64().unwrap_or(0.0),
                        items[1].as_f64().unwrap_or(0.0),
                    ))
                } else {
                    None
                }
            }),
        runner_forced_clear_target: config
            .get("runner_forced_clear_target")
            .and_then(|value| value.as_array())
            .and_then(|items| {
                if items.len() >= 2 {
                    Some((
                        items[0].as_f64().unwrap_or(0.0),
                        items[1].as_f64().unwrap_or(0.0),
                    ))
                } else {
                    None
                }
            }),
        runner_force_receiver_offside: config
            .get("runner_force_receiver_offside")
            .and_then(|value| value.as_bool())
            .unwrap_or(false),
        runner_force_specialized_goal: config_string(config, "runner_force_specialized_goal"),
        trace_detail: config_string(config, "trace_detail").unwrap_or_else(|| "off".to_string()),
        trace_top_k: config_i32(config, "trace_top_k", 5).max(0) as usize,
    }
}

fn pitch_clamp(pos: (f64, f64), length: f64, width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, length - 0.5),
        pos.1.clamp(0.5, width - 0.5),
    )
}

fn formation_to_pitch(
    coord: (f64, f64),
    attacking_right: bool,
    length: f64,
    width: f64,
) -> (f64, f64) {
    let depth_pct = (100.0 - coord.1) / 100.0;
    let x = if attacking_right {
        depth_pct * length
    } else {
        (1.0 - depth_pct) * length
    };
    pitch_clamp((x, coord.0), length, width)
}

fn card_string(card: &serde_json::Value, key: &str, default: String) -> String {
    card.get(key)
        .and_then(|value| value.as_str())
        .map(|value| value.to_string())
        .unwrap_or(default)
}

fn card_ability(card: &serde_json::Value, key: &str, default: f64) -> f64 {
    card.get(key)
        .and_then(|value| value.as_f64())
        .or_else(|| {
            card.get("abilities")
                .and_then(|abilities| abilities.get(key))
                .and_then(|value| value.as_f64())
        })
        .unwrap_or(default)
}

fn build_players(
    cards: &[serde_json::Value],
    formation: Formation,
    attacking_right: bool,
    length: f64,
    width: f64,
) -> Vec<RunnerPlayer> {
    (0..11)
        .map(|idx| {
            let empty = serde_json::Value::Null;
            let card = cards.get(idx).unwrap_or(&empty);
            let pos =
                formation_to_pitch(formation.coordinates[idx], attacking_right, length, width);
            RunnerPlayer {
                name: card_string(card, "name", format!("Player {}", idx + 1)),
                position: formation.positions[idx].to_string(),
                color: card_string(card, "color", "gold".to_string()),
                base_pos: pos,
                tactical_anchor: pos,
                pos,
                target_pos: pos,
                velocity: (0.0, 0.0),
                facing_direction: 0.0,
                last_receive_origin: pos,
                state: "off_ball".to_string(),
                stun_ticks_remaining: 0,
                movement_intent: "support".to_string(),
                last_def_target: (0.0, 0.0),
                last_def_action: String::new(),
                last_pressure_tick: -9999,
                goal_type: None,
                goal_phase: None,
                goal_target: pos,
                goal_value: 0.0,
                goal_created_tick: 0,
                goal_action_code: 3,
                finishing: card_ability(card, "Finishing", 50.0),
                long_shot: card_ability(card, "Long_Shot", 50.0),
                short_passing: card_ability(card, "Short_Passing", 50.0),
                long_passing: card_ability(card, "Long_Passing", 50.0),
                dribbling: card_ability(card, "Dribbling", 50.0),
                tackling: card_ability(card, "Tackling", 50.0),
                defence: card_ability(card, "Defence", 50.0),
                speed: card_ability(card, "Speed", 50.0),
                iq: card_ability(card, "IQ", 50.0),
                gk_saving: card_ability(card, "GK_Saving", 50.0),
                gk_positioning: card_ability(card, "GK_Positioning", 50.0),
                gk_reaction: card_ability(card, "GK_Reaction", 50.0),
                shots: 0,
                xg: 0.0,
                goals: 0,
                assists: 0,
                shots_on_target: 0,
                saves: 0,
                goals_conceded: 0,
                psxg_faced: 0.0,
                shot_log: Vec::new(),
                holds: 0,
                passes_attempted: 0,
                passes_completed: 0,
                key_passes: 0,
                progressive_passes: 0,
                passes_into_final_third: 0,
                passes_into_box: 0,
                long_passes: 0,
                completed_long_passes: 0,
                crosses_attempted: 0,
                crosses_completed: 0,
                carries_attempted: 0,
                carries_completed: 0,
                dribbles_attempted: 0,
                dribbles_completed: 0,
                progressive_carries: 0,
                carries_into_final_third: 0,
                carries_into_box: 0,
                clearances: 0,
                blocks: 0,
                interceptions: 0,
                pressures: 0,
                successful_pressures: 0,
                tackles_attempted: 0,
                tackles_won: 0,
                turnovers: 0,
                dispossessed: 0,
                offsides: 0,
                distance_covered: 0.0,
                position_samples: Vec::new(),
                hold_ticks: 0,
                possession_ticks: 0,
                consecutive_carries: 0,
            }
        })
        .collect()
}

fn replay_header(
    home: &[RunnerPlayer],
    away: &[RunnerPlayer],
    home_formation: &str,
    away_formation: &str,
    width: f64,
    length: f64,
) -> serde_json::Value {
    json!({
        "type": "header",
        "home": {
            "name": "Home Team",
            "players": home.iter().map(|p| json!({"name": p.name, "pos": p.position, "color": p.color})).collect::<Vec<_>>()
        },
        "away": {
            "name": "Away Team",
            "players": away.iter().map(|p| json!({"name": p.name, "pos": p.position, "color": p.color})).collect::<Vec<_>>()
        },
        "formation_home": home_formation,
        "formation_away": away_formation,
        "field": {"width": width, "length": length}
    })
}

fn frame(
    tick: i32,
    tick_duration: f64,
    half: i32,
    home: &[RunnerPlayer],
    away: &[RunnerPlayer],
    ball_pos: (f64, f64),
    ball_holder_idx: Option<usize>,
    ball_team: Option<&str>,
    score: (i32, i32),
    cut: Option<bool>,
    ball_flight: serde_json::Value,
    event_text: Option<&str>,
    pause_ms: Option<i32>,
) -> serde_json::Value {
    let player_goal_payload = |player: &RunnerPlayer| -> serde_json::Value {
        player.goal_type.as_ref().map(|goal_type| {
            json!({
                "goal_type": goal_type,
                "target_pos": [round_one(player.goal_target.0), round_one(player.goal_target.1)],
                "value": round_two(player.goal_value),
                "context": {
                    "phase": player.goal_phase.clone().unwrap_or_default(),
                    "action_code": player.goal_action_code
                }
            })
        }).unwrap_or(serde_json::Value::Null)
    };
    json!({
        "type": "frame",
        "t": round_one(tick as f64 * tick_duration),
        "half": half,
        "home": home.iter().map(|p| json!([round_one(p.pos.1), round_one(p.pos.0)])).collect::<Vec<_>>(),
        "away": away.iter().map(|p| json!([round_one(p.pos.1), round_one(p.pos.0)])).collect::<Vec<_>>(),
        "home_player_goals": home.iter().map(player_goal_payload).collect::<Vec<_>>(),
        "away_player_goals": away.iter().map(player_goal_payload).collect::<Vec<_>>(),
        "ball": [round_one(ball_pos.1), round_one(ball_pos.0)],
        "ball_holder": ball_holder_idx.map(|idx| json!(idx)).unwrap_or(serde_json::Value::Null),
        "ball_team": ball_team.map(|side| json!(side)).unwrap_or(serde_json::Value::Null),
        "score": [score.0, score.1],
        "ball_flight": ball_flight,
        "event_text": event_text.map(|value| json!(value)).unwrap_or(serde_json::Value::Null),
        "pause_ms": pause_ms.map(|value| json!(value)).unwrap_or(serde_json::Value::Null),
        "cut": cut.map(|value| json!(value)).unwrap_or(serde_json::Value::Null)
    })
}

fn ball_state_name(state: RunnerBallState) -> &'static str {
    match state {
        RunnerBallState::Held => "held",
        RunnerBallState::InFlight => "in_flight",
        RunnerBallState::Dead => "dead",
        RunnerBallState::Contested => "contested",
    }
}

fn replay_ball_flight(flight: Option<&RunnerFlight>) -> serde_json::Value {
    let Some(flight) = flight else {
        return serde_json::Value::Null;
    };
    let flight_type = match flight.kind {
        RunnerFlightKind::Pass => "pass",
        RunnerFlightKind::Clearance => "clear",
        RunnerFlightKind::Shot => "shot",
    };
    json!({
        "from": [round_one(flight.origin.1), round_one(flight.origin.0)],
        "to": [round_one(flight.target.1), round_one(flight.target.0)],
        "type": flight_type,
        "on_target": flight.on_target,
    })
}

fn queue_replay_frame(
    state: &mut RunnerMatchState,
    tick: i32,
    half: i32,
    home: &[RunnerPlayer],
    away: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
    ball_flight: serde_json::Value,
    event_text: Option<&str>,
    pause_ms: Option<i32>,
    ball_holder_idx: Option<usize>,
    ball_team: Option<&str>,
) {
    state.pending_replay_frames.push(frame(
        tick,
        config.tick_duration,
        half,
        home,
        away,
        state.ball.position,
        ball_holder_idx.or(state.ball.holder_idx),
        ball_team.or_else(|| {
            state
                .ball
                .holder_team_home
                .map(|home| if home { "home" } else { "away" })
        }),
        (state.home_score, state.away_score),
        None,
        ball_flight,
        event_text,
        pause_ms,
    ));
}

fn sample_player_positions(players: &mut [RunnerPlayer]) {
    for player in players {
        player
            .position_samples
            .push(json!([round_one(player.pos.0), round_one(player.pos.1)]));
    }
}

fn all_ball_states() -> [RunnerBallState; 4] {
    [
        RunnerBallState::Held,
        RunnerBallState::InFlight,
        RunnerBallState::Dead,
        RunnerBallState::Contested,
    ]
}

fn round_one(value: f64) -> f64 {
    (value * 10.0).round_ties_even() / 10.0
}

fn round_two(value: f64) -> f64 {
    (value * 100.0).round_ties_even() / 100.0
}

fn round_rating(value: f64) -> f64 {
    format!("{:.1}", value)
        .parse::<f64>()
        .unwrap_or_else(|_| round_one(value))
}

fn player_rating(player: &RunnerPlayer, team_conceded: i32) -> f64 {
    let mut base = 6.0;
    base += player.goals as f64 * 1.0;
    base += player.assists as f64 * 0.5;
    if player.shots > 0 {
        base += (player.shots_on_target as f64 * 0.15).min(0.5);
    }
    if player.passes_attempted > 5 {
        let pass_rate = player.passes_completed as f64 / player.passes_attempted as f64;
        base += (pass_rate - 0.7) * 1.5;
    }
    if player.tackles_attempted > 0 {
        let tackle_rate = player.tackles_won as f64 / player.tackles_attempted as f64;
        base += tackle_rate * 0.3;
    }
    base += player.interceptions as f64 * 0.1;
    if player.position == "GK" {
        base += player.saves as f64 * 0.3;
        base -= team_conceded as f64 * 0.2;
    }
    if player.dribbles_attempted > 0 {
        let dribble_rate = player.dribbles_completed as f64 / player.dribbles_attempted as f64;
        base += dribble_rate * 0.2;
    }
    if player.carries_attempted > 0 {
        let carry_rate = player.carries_completed as f64 / player.carries_attempted as f64;
        base += carry_rate * 0.15;
    }
    if player.crosses_attempted > 0 {
        let cross_rate = player.crosses_completed as f64 / player.crosses_attempted as f64;
        base += cross_rate * 0.2;
    }
    round_rating(base.clamp(1.0, 10.0))
}

fn team_ratings(players: &[RunnerPlayer], team_conceded: i32) -> Vec<serde_json::Value> {
    players
        .iter()
        .map(|player| {
            json!({
                "name": player.name,
                "position": player.position,
                "rating": player_rating(player, team_conceded)
            })
        })
        .collect()
}

fn player_stat_skeleton(
    players: &[RunnerPlayer],
    _team_home: bool,
    _pass_network: &HashMap<String, i32>,
) -> Vec<serde_json::Value> {
    players
        .iter()
        .enumerate()
        .map(|(_idx, player)| {
            let _ability_read = player.finishing
                + player.long_shot
                + player.short_passing
                + player.long_passing
                + player.dribbling
                + player.speed
                + player.iq
                + player.gk_saving
                + player.gk_positioning
                + player.gk_reaction
                + player.holds as f64;
            json!({
                "name": player.name,
                "colored_name": player.name,
                "position": player.position,
                "goals": player.goals,
                "assists": player.assists,
                "shots": player.shots,
                "shots_on_target": player.shots_on_target,
                "xg": round_two(player.xg),
                "npxg": round_two(player.xg),
                "post_shot_xg": round_two(player.xg * 0.8),
                "big_chances": player.shot_log.iter().filter(|shot| shot.get("xg").and_then(|value| value.as_f64()).unwrap_or(0.0) > 0.3).count(),
                "big_chances_missed": player.shot_log.iter().filter(|shot| {
                    shot.get("xg").and_then(|value| value.as_f64()).unwrap_or(0.0) > 0.3
                        && shot.get("outcome").and_then(|value| value.as_str()).unwrap_or("") != "goal"
                }).count(),
                "passes": player.passes_attempted,
                "completed_passes": player.passes_completed,
                "key_passes": player.key_passes,
                "xa": round_two(player.key_passes as f64 * 0.12),
                "progressive_passes": player.progressive_passes,
                "passes_into_final_third": player.passes_into_final_third,
                "passes_into_box": player.passes_into_box,
                "long_passes": player.long_passes,
                "completed_long_passes": player.completed_long_passes,
                "crosses": player.crosses_attempted,
                "successful_crosses": player.crosses_completed,
                "carries": player.carries_attempted,
                "carries_completed": player.carries_completed,
                "progressive_carries": player.progressive_carries,
                "carries_into_final_third": player.carries_into_final_third,
                "carries_into_box": player.carries_into_box,
                "take_ons": player.dribbles_attempted,
                "successful_take_ons": player.dribbles_completed,
                "tackles_attempted": player.tackles_attempted,
                "tackles_won": player.tackles_won,
                "interceptions": player.interceptions,
                "blocks": player.blocks,
                "clearances": player.clearances,
                "pressures": player.pressures,
                "successful_pressures": player.successful_pressures,
                "turnovers": player.turnovers,
                "dispossessed": player.dispossessed,
                "offsides": player.offsides,
                "saves": player.saves,
                "goals_conceded": player.goals_conceded,
                "psxg_faced": round_two(player.psxg_faced),
                "goals_prevented": if player.position == "GK" { round_two(player.psxg_faced - player.goals_conceded as f64) } else { 0.0 },
                "rating": player_rating(player, player.goals_conceded),
                "shot_log": player.shot_log,
                "pass_network": {},
                "position_samples": player.position_samples,
                "distance_covered": round_one(player.distance_covered)
            })
        })
        .collect()
}

fn team_stats(players: &[RunnerPlayer], possession: f64) -> serde_json::Value {
    let passes = players
        .iter()
        .map(|player| player.passes_attempted)
        .sum::<i32>();
    let completed = players
        .iter()
        .map(|player| player.passes_completed)
        .sum::<i32>();
    json!({
        "shots": players.iter().map(|player| player.shots).sum::<i32>(),
        "shots_on_target": players.iter().map(|player| player.shots_on_target).sum::<i32>(),
        "passes": passes,
        "passes_completed": completed,
        "pass_success_rate": if passes > 0 { round_one(completed as f64 / passes as f64 * 100.0) } else { 0.0 },
        "tackles": players.iter().map(|player| player.tackles_won).sum::<i32>(),
        "tackles_won": players.iter().map(|player| player.tackles_won).sum::<i32>(),
        "interceptions": players.iter().map(|player| player.interceptions).sum::<i32>(),
        "clearances": players.iter().map(|player| player.clearances).sum::<i32>(),
        "dribbles": players.iter().map(|player| player.dribbles_completed).sum::<i32>(),
        "dribbles_completed": players.iter().map(|player| player.dribbles_completed).sum::<i32>(),
        "saves": players.iter().map(|player| player.saves).sum::<i32>(),
        "goals": players.iter().map(|player| player.goals).sum::<i32>(),
        "distance_covered": players.iter().map(|player| player.distance_covered).sum::<f64>(),
        "carries": players.iter().map(|player| player.carries_attempted).sum::<i32>(),
        "carries_completed": players.iter().map(|player| player.carries_completed).sum::<i32>(),
        "crosses": players.iter().map(|player| player.crosses_attempted).sum::<i32>(),
        "crosses_completed": players.iter().map(|player| player.crosses_completed).sum::<i32>(),
        "headers": 0,
        "headers_won": 0,
        "possession": possession
    })
}

fn shot_log_sum(player: &RunnerPlayer) -> f64 {
    player
        .shot_log
        .iter()
        .map(|entry| {
            entry
                .get("xg")
                .and_then(|value| value.as_f64())
                .unwrap_or(0.0)
        })
        .sum()
}

fn shot_log_json(entry: &ShotLogEntryOutput) -> serde_json::Value {
    let mut value = json!({
        "x": entry.x,
        "y": entry.y,
        "xg": entry.xg,
        "in_box": entry.in_box,
        "outcome": entry.outcome,
    });
    if let serde_json::Value::Object(ref mut map) = value {
        if let Some(target_x) = entry.target_x {
            map.insert("target_x".to_string(), json!(target_x));
        }
        if let Some(target_y) = entry.target_y {
            map.insert("target_y".to_string(), json!(target_y));
        }
    }
    value
}

fn reset_positions(
    players: &mut [RunnerPlayer],
    formation: Formation,
    attacking_right: bool,
    length: f64,
    width: f64,
) {
    for (idx, player) in players.iter_mut().enumerate() {
        let pos = formation_to_pitch(formation.coordinates[idx], attacking_right, length, width);
        player.base_pos = pos;
        player.tactical_anchor = pos;
        player.pos = pos;
        player.target_pos = pos;
        player.velocity = (0.0, 0.0);
        player.state = "off_ball".to_string();
        player.movement_intent = "support".to_string();
        player.goal_type = None;
        player.goal_phase = None;
        player.goal_target = pos;
        player.goal_value = 0.0;
        player.goal_created_tick = 0;
        player.goal_action_code = 3;
    }
}

fn reset_formation_slots(
    players: &mut [RunnerPlayer],
    formation: Formation,
    attacking_right: bool,
    length: f64,
    width: f64,
) {
    for (idx, player) in players.iter_mut().enumerate() {
        let pos = formation_to_pitch(formation.coordinates[idx], attacking_right, length, width);
        player.base_pos = pos;
        player.tactical_anchor = pos;
        player.pos = pos;
        player.target_pos = pos;
    }
}

fn reset_players_to_current_formation_slots(players: &mut [RunnerPlayer]) {
    for player in players.iter_mut() {
        let pos = player.base_pos;
        player.tactical_anchor = pos;
        player.pos = pos;
        player.target_pos = pos;
    }
}

fn clear_player_goal(player: &mut RunnerPlayer) {
    player.goal_type = None;
    player.goal_phase = None;
    player.goal_target = player.pos;
    player.goal_value = 0.0;
    player.goal_created_tick = 0;
    player.goal_action_code = 3;
}

fn clear_team_goals(players: &mut [RunnerPlayer]) {
    for player in players {
        clear_player_goal(player);
    }
}

fn sync_goals_with_possession(
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    holder_team_home: Option<bool>,
) {
    match holder_team_home {
        Some(true) => clear_team_goals(away),
        Some(false) => clear_team_goals(home),
        None => {
            clear_team_goals(home);
            clear_team_goals(away);
        }
    }
}

fn attacking_right_for(holder_home: bool, home_attacking_right: bool) -> bool {
    if holder_home {
        home_attacking_right
    } else {
        !home_attacking_right
    }
}

fn phase_name(phase_code: u8) -> &'static str {
    match phase_code {
        1 => "transition_atk",
        2 => "defending",
        3 => "transition_def",
        4 => "contesting",
        _ => "attacking",
    }
}

fn update_team_phases(state: &mut RunnerMatchState, config: &RunnerRuntimeConfig) {
    let ball_contested = state.ball.state == RunnerBallState::Contested;
    let home_update = crate::team_phase_update(&TeamPhaseUpdateInput {
        has_possession: state.ball.state == RunnerBallState::Held
            && state.ball.holder_team_home == Some(true),
        ball_contested,
        had_possession_last_tick: state.home_had_possession_last_tick,
        ticks_since_possession_change: state.home_ticks_since_possession_change,
        transition_ticks: config.transition_ticks,
    });
    state.home_phase_code = home_update.phase_code;
    state.home_had_possession_last_tick = home_update.had_possession_last_tick;
    state.home_ticks_since_possession_change = home_update.ticks_since_possession_change;

    let away_update = crate::team_phase_update(&TeamPhaseUpdateInput {
        has_possession: state.ball.state == RunnerBallState::Held
            && state.ball.holder_team_home == Some(false),
        ball_contested,
        had_possession_last_tick: state.away_had_possession_last_tick,
        ticks_since_possession_change: state.away_ticks_since_possession_change,
        transition_ticks: config.transition_ticks,
    });
    state.away_phase_code = away_update.phase_code;
    state.away_had_possession_last_tick = away_update.had_possession_last_tick;
    state.away_ticks_since_possession_change = away_update.ticks_since_possession_change;
}

fn execution_opponents(players: &[RunnerPlayer]) -> Vec<ExecutionOpponent> {
    players
        .iter()
        .map(|player| ExecutionOpponent {
            pos: player.pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect()
}

fn arrival_players(
    players: &[RunnerPlayer],
    passer_idx: usize,
    intended_receiver_idx: Option<usize>,
) -> Vec<ArrivalPlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| ArrivalPlayerInput {
            index: idx,
            pos: player.pos,
            target_pos: player.target_pos,
            current_goal_pos: player.goal_type.as_ref().map(|_| player.goal_target),
            speed: player.speed.round() as i32,
            is_passer: idx == passer_idx,
            is_intended: intended_receiver_idx == Some(idx),
            is_passer_team: true,
        })
        .collect()
}

fn opponent_arrival_players(players: &[RunnerPlayer]) -> Vec<ArrivalPlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| ArrivalPlayerInput {
            index: idx,
            pos: player.pos,
            target_pos: player.target_pos,
            current_goal_pos: player.goal_type.as_ref().map(|_| player.goal_target),
            speed: player.speed.round() as i32,
            is_passer: false,
            is_intended: false,
            is_passer_team: false,
        })
        .collect()
}

fn clearance_players(players: &[RunnerPlayer]) -> Vec<ClearancePlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| ClearancePlayerInput {
            index: idx,
            pos: player.pos,
        })
        .collect()
}

fn contested_target_players(players: &[RunnerPlayer]) -> Vec<ContestedTargetPlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| ContestedTargetPlayerInput {
            index: idx,
            pos: player.pos,
            tactical_anchor: player.tactical_anchor,
            is_goalkeeper: player.position == "GK",
            is_stunned: player.state == "stunned",
            speed: player.speed.round() as i32,
            iq: player.iq,
        })
        .collect()
}

fn give_ball(state: &mut RunnerMatchState, idx: usize, team_home: bool, pos: (f64, f64)) {
    state.ball.state = RunnerBallState::Held;
    state.ball.position = pos;
    state.ball.holder_idx = Some(idx);
    state.ball.holder_team_home = Some(team_home);
    state.ball.flight = None;
    state.ball.loose_velocity = (0.0, 0.0);
    state.ball.contested_ticks = 0;
}

fn give_ball_to_player(
    state: &mut RunnerMatchState,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    idx: usize,
    team_home: bool,
    pos: (f64, f64),
    receive_origin: Option<(f64, f64)>,
) {
    if let (Some(prev_idx), Some(prev_home)) = (state.ball.holder_idx, state.ball.holder_team_home)
    {
        if prev_home {
            if let Some(player) = home.get_mut(prev_idx) {
                player.state = "off_ball".to_string();
                clear_player_goal(player);
            }
        } else if let Some(player) = away.get_mut(prev_idx) {
            player.state = "off_ball".to_string();
            clear_player_goal(player);
        }
    }
    let mut ball_pos = pos;
    if team_home {
        if let Some(player) = home.get_mut(idx) {
            player.state = "on_ball".to_string();
            player.hold_ticks = 0;
            player.possession_ticks = 0;
            player.consecutive_carries = 0;
            player.last_receive_origin = receive_origin.unwrap_or(player.pos);
            ball_pos = player.pos;
            clear_player_goal(player);
        }
    } else if let Some(player) = away.get_mut(idx) {
        player.state = "on_ball".to_string();
        player.hold_ticks = 0;
        player.possession_ticks = 0;
        player.consecutive_carries = 0;
        player.last_receive_origin = receive_origin.unwrap_or(player.pos);
        ball_pos = player.pos;
        clear_player_goal(player);
    }
    if state.ball.holder_team_home != Some(team_home) {
        clear_team_goals(home);
        clear_team_goals(away);
    }
    give_ball(state, idx, team_home, ball_pos);
}

fn tick_player_stun(player: &mut RunnerPlayer) {
    if player.state != "stunned" {
        return;
    }
    let stun = player_tick_stun(&PlayerTickStunInput {
        state: player.state.as_str(),
        stun_ticks_remaining: player.stun_ticks_remaining,
    });
    player.state = stun.state;
    player.stun_ticks_remaining = stun.stun_ticks_remaining;
}

fn tick_stunned_players(players: &mut [RunnerPlayer]) {
    for player in players {
        tick_player_stun(player);
    }
}

fn apply_stun_to_player(player: &mut RunnerPlayer, config: &RunnerRuntimeConfig) {
    let stun = player_apply_stun(&PlayerApplyStunInput {
        tackle_fail_stun_seconds: config.tackle_fail_stun_seconds,
        tick_duration: config.tick_duration,
    });
    player.state = stun.state;
    player.stun_ticks_remaining = stun.stun_ticks_remaining;
}

fn set_dead_ball(
    state: &mut RunnerMatchState,
    reason: &str,
    restart_team_home: bool,
    restart_ticks: i32,
    ball_pos: (f64, f64),
) {
    state.ball.state = RunnerBallState::Dead;
    state.ball.position = ball_pos;
    state.ball.holder_idx = None;
    state.ball.holder_team_home = None;
    state.ball.flight = None;
    state.ball.loose_velocity = (0.0, 0.0);
    state.dead_reason = Some(reason.to_string());
    state.restart_team_home = Some(restart_team_home);
    state.restart_ticks_remaining = restart_ticks.max(0);
}

fn set_dead_ball_and_clear_goals(
    state: &mut RunnerMatchState,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    reason: &str,
    restart_team_home: bool,
    restart_ticks: i32,
    ball_pos: (f64, f64),
) {
    clear_team_goals(home);
    clear_team_goals(away);
    set_dead_ball(state, reason, restart_team_home, restart_ticks, ball_pos);
}

fn set_contested(state: &mut RunnerMatchState, pos: (f64, f64), loose_velocity: (f64, f64)) {
    state.ball.state = RunnerBallState::Contested;
    state.ball.position = pos;
    state.ball.holder_idx = None;
    state.ball.holder_team_home = None;
    state.ball.flight = None;
    state.ball.loose_velocity = loose_velocity;
    state.ball.contested_ticks = 0;
}

fn set_contested_and_clear_goals(
    state: &mut RunnerMatchState,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    pos: (f64, f64),
    loose_velocity: (f64, f64),
) {
    clear_team_goals(home);
    clear_team_goals(away);
    set_contested(state, pos, loose_velocity);
}

fn restart_players(players: &[RunnerPlayer]) -> Vec<RestartPlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| RestartPlayerInput {
            index: idx,
            pos: player.pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect()
}

fn restart_shape_players(
    players: &[RunnerPlayer],
    team_code: u8,
    team_is_restart: bool,
    team_attacking_right: bool,
    restart_attacking_right: bool,
) -> Vec<RestartShapePlayerInput<'_>> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| RestartShapePlayerInput {
            index: idx,
            team_code,
            team_is_restart,
            team_attacking_right,
            restart_attacking_right,
            base_pos: player.base_pos,
            current_pos: player.pos,
            is_goalkeeper: player.position == "GK",
            is_attacker: is_attacker_position(player.position.as_str()),
            is_midfielder: is_midfielder_position(player.position.as_str()),
            is_defender: is_defender_position(player.position.as_str()),
            position: player.position.as_str(),
        })
        .collect()
}

fn carry_target(
    holder: &RunnerPlayer,
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> (f64, f64) {
    let dir = if attacking_right { 1.0 } else { -1.0 };
    let center_pull = (config.pitch_width / 2.0 - holder.pos.1).clamp(-4.0, 4.0);
    pitch_clamp(
        (holder.pos.0 + dir * 12.0, holder.pos.1 + center_pull * 0.35),
        config.pitch_length,
        config.pitch_width,
    )
}

fn goal_target(attacking_right: bool, config: &RunnerRuntimeConfig) -> (f64, f64) {
    (
        if attacking_right {
            config.pitch_length
        } else {
            0.0
        },
        config.pitch_width / 2.0,
    )
}

fn clear_target(
    holder: &RunnerPlayer,
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> (f64, f64) {
    let dir = if attacking_right { 1.0 } else { -1.0 };
    let center_y = config.pitch_width / 2.0;
    pitch_clamp(
        (
            holder.pos.0 + dir * 34.0,
            holder.pos.1 + (center_y - holder.pos.1) * 0.25,
        ),
        config.pitch_length,
        config.pitch_width,
    )
}

fn choose_pass_receiver(
    holder_idx: usize,
    holder: &RunnerPlayer,
    teammates: &[RunnerPlayer],
    attacking_right: bool,
) -> Option<usize> {
    let dir = if attacking_right { 1.0 } else { -1.0 };
    let mut best: Option<(usize, f64)> = None;
    for (idx, teammate) in teammates.iter().enumerate() {
        if idx == holder_idx || teammate.position == "GK" {
            continue;
        }
        let forward = (teammate.pos.0 - holder.pos.0) * dir;
        let dist = ((teammate.pos.0 - holder.pos.0).powi(2)
            + (teammate.pos.1 - holder.pos.1).powi(2))
        .sqrt();
        let forward_bonus = if forward > 1.0 { 14.0 } else { 0.0 };
        let score = dist - forward_bonus;
        if best
            .map(|(_, best_score)| score < best_score)
            .unwrap_or(true)
        {
            best = Some((idx, score));
        }
    }
    best.map(|(idx, _)| idx)
}

fn opponent_positions(players: &[RunnerPlayer]) -> Vec<(f64, f64)> {
    players
        .iter()
        .filter(|player| player.position != "GK")
        .map(|player| player.pos)
        .collect()
}

fn teammate_positions(players: &[RunnerPlayer], holder_idx: usize) -> Vec<(usize, f64, f64)> {
    players
        .iter()
        .enumerate()
        .filter(|(idx, _)| *idx != holder_idx)
        .map(|(idx, player)| (idx, player.pos.0, player.pos.1))
        .collect()
}

fn all_teammate_positions(players: &[RunnerPlayer]) -> Vec<(usize, f64, f64)> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| (idx, player.pos.0, player.pos.1))
        .collect()
}

fn teammate_goalkeeper_indices(players: &[RunnerPlayer]) -> Vec<usize> {
    players
        .iter()
        .enumerate()
        .filter(|(_, player)| player.position == "GK")
        .map(|(idx, _)| idx)
        .collect()
}

fn teammate_xy_positions(players: &[RunnerPlayer], holder_idx: usize) -> Vec<(f64, f64)> {
    players
        .iter()
        .enumerate()
        .filter(|(idx, _)| *idx != holder_idx)
        .map(|(_, player)| player.pos)
        .collect()
}

fn runner_state_value(
    holder_idx: usize,
    holder: &RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> f64 {
    state_value(&StateValueInput {
        pos: holder.pos,
        player_index: holder_idx,
        player_team_home: holder_home,
        tick,
        finishing: holder.finishing / 100.0,
        long_shot: holder.long_shot / 100.0,
        teammate_positions: &teammate_positions(teammates, holder_idx),
        teammate_goalkeeper_indices: &teammate_goalkeeper_indices(teammates),
        opponent_positions: &opponent_positions(opponents),
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        attacking_right,
        shot_ideal_distance: config.shot_ideal_distance,
        shot_on_target_base: config.shot_on_target_base,
        gk_save_base: config.gk_save_base,
        shot_quality_cache: Some(shot_quality_cache),
    })
}

fn runner_position_value(
    pos: (f64, f64),
    teammates: &[RunnerPlayer],
    excluded_teammate_idx: Option<usize>,
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> f64 {
    position_value(&PositionValueInput {
        x: pos.0,
        y: pos.1,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        attacking_right,
        opponent_positions: &opponent_positions(opponents),
        teammate_positions: &teammates
            .iter()
            .enumerate()
            .filter(|(idx, _)| Some(*idx) != excluded_teammate_idx)
            .map(|(_, player)| player.pos)
            .collect::<Vec<_>>(),
        runner_formation_pos: None,
    })
}

fn offside_line(
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> f64 {
    let mut xs: Vec<f64> = opponents
        .iter()
        .filter(|player| player.position != "GK")
        .map(|player| player.pos.0)
        .collect();
    if xs.is_empty() {
        return if attacking_right {
            config.pitch_length
        } else {
            0.0
        };
    }
    if attacking_right {
        xs.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    } else {
        xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    }
    xs.get(1).copied().unwrap_or(xs[0])
}

fn flag_offside_indices(
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    passer_idx: usize,
    pass_origin: (f64, f64),
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> Vec<usize> {
    let line = offside_line(opponents, attacking_right, config);
    teammates
        .iter()
        .enumerate()
        .filter(|(idx, player)| {
            *idx != passer_idx
                && player.position != "GK"
                && crate::offside::is_offside_position(
                    player.pos,
                    attacking_right,
                    line,
                    config.pitch_length,
                    Some(pass_origin.0),
                )
        })
        .map(|(idx, _)| idx)
        .collect()
}

fn record_pass_network(
    state: &mut RunnerMatchState,
    team_home: bool,
    passer_idx: usize,
    receiver_idx: usize,
) {
    let key = format!(
        "{}:{}:{}",
        if team_home { "home" } else { "away" },
        passer_idx,
        receiver_idx
    );
    *state.pass_network.entry(key).or_insert(0) += 1;
}

fn build_carry_candidates(
    holder_idx: usize,
    holder: &RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    current_state_value: f64,
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> Vec<RunnerEvaluatedAction> {
    let current_pv = runner_position_value(
        holder.pos,
        teammates,
        Some(holder_idx),
        opponents,
        attacking_right,
        config,
    );
    let offsets = generate_carry_offsets(&CarryTargetGenerationInput {
        carrier_pos: holder.pos,
        speed: holder.speed.round() as i32,
        dribbling: holder.dribbling,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        player_max_speed: config.player_max_speed,
        player_min_speed: config.player_min_speed,
        carrier_speed: config.carrier_speed,
        nearest_opponent_distance: opponents
            .iter()
            .filter(|player| player.position != "GK")
            .map(|player| distance(holder.pos, player.pos))
            .fold(f64::INFINITY, f64::min),
    })
    .offsets;
    let carry_support: Vec<CarrySupportPlayer> = teammates
        .iter()
        .enumerate()
        .map(|(idx, player)| CarrySupportPlayer {
            index: idx,
            pos: player.pos,
            base: player.base_pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect();
    let path_opponents: Vec<CarryPathOpponentInput> = opponents
        .iter()
        .map(|player| CarryPathOpponentInput {
            pos: player.pos,
            speed: player.speed,
            defence: player.defence,
            tackling: player.tackling,
            is_goalkeeper: player.position == "GK",
        })
        .collect();
    let opponent_xy = opponent_positions(opponents);
    let mut seen = std::collections::HashSet::new();
    let mut actions = Vec::new();
    for (dx, dy) in offsets {
        let target = pitch_clamp(
            (holder.pos.0 + dx, holder.pos.1 + dy),
            config.pitch_length,
            config.pitch_width,
        );
        let key = (
            (target.0 * 10.0).round() as i64,
            (target.1 * 10.0).round() as i64,
        );
        if !seen.insert(key) {
            continue;
        }
        let path_target = (holder.pos.0 + dx, holder.pos.1 + dy);
        let path = evaluate_carry_path(&CarryPathInput {
            carrier_pos: holder.pos,
            target: path_target,
            dribbling: holder.dribbling,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            player_max_speed: config.player_max_speed,
            carrier_speed: config.carrier_speed,
            tackle_range: config.tackle_range,
            opponents: &path_opponents,
        });
        let target_pv = runner_position_value(
            target,
            teammates,
            Some(holder_idx),
            opponents,
            attacking_right,
            config,
        );
        let value = evaluate_carry(&CarryInput {
            tick,
            carrier_index: holder_idx,
            carrier_team_home: holder_home,
            carrier_pos: holder.pos,
            target,
            finishing: holder.finishing / 100.0,
            long_shot: holder.long_shot / 100.0,
            consecutive_carries: holder.consecutive_carries,
            possession_ticks: holder.possession_ticks,
            target_pv,
            current_pv,
            current_state_value,
            path_feasibility: path.feasibility,
            teammates: &carry_support,
            opponents: &opponent_xy,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            attacking_right,
            carrier_speed: config.carrier_speed,
            shot_ideal_distance: config.shot_ideal_distance,
            shot_on_target_base: config.shot_on_target_base,
            gk_save_base: config.gk_save_base,
            shot_quality_cache: Some(shot_quality_cache),
        });
        let final_score = finalize_carry_score(&CarryFinalizeInput {
            evaluator_score: value.score,
            feasibility: path.feasibility,
            path_peak_threat: path.path_peak_threat,
            path_peak_final_third_control: path.path_peak_final_third_control,
            consecutive_carries: holder.consecutive_carries,
        });
        actions.push(RunnerEvaluatedAction {
            action: RunnerHeldAction::Carry { target },
            score: final_score.score,
            success_prob: path.feasibility,
            receiver_pressure: 0.0,
            high_threat_space: 0.0,
            final_third_combination: 0.0,
            second_line_arrival_value: 0.0,
            second_line_cutback_value: 0.0,
            layoff_support_value: 0.0,
            short_combination_value: 0.0,
            layoff_retention_value: 0.0,
            receiver_goal_fit: 0.0,
            target_kind_space: false,
            progress_gain: value.progress_gain,
            xg: value.target_shot,
            pressure: 1.0 - path.feasibility,
            lateral_change: (target.1 - holder.pos.1).abs() / config.pitch_width.max(1.0),
            carry_to_shoot_window: value.carry_to_shoot_window,
            wide_second_line_carry_window: value.wide_second_line_carry_window,
            future_shot_gain: value.future_shot_gain,
            byline_carry_window: value.byline_carry_window,
            shot_readiness: 0.0,
            open_medium_window: 0.0,
            clean_second_line_shot: 0.0,
            space_manipulation: value.space_manipulation,
            pressure_draw: value.pressure_draw,
            opportunity_wait: 0.0,
            opportunity_wait_value: 0.0,
            no_clear_release: 0.0,
            raw_score: value.score,
            debug_final_score: final_score.score,
            debug_hold_ticks: 0,
            debug_possession_ticks: holder.possession_ticks,
            debug_best_pass_score: 0.0,
            debug_shoot_score: 0.0,
            debug_current_pv: current_state_value,
            debug_effective_current_value: current_state_value,
            debug_delta: value.after_value - current_state_value,
            debug_after_value: value.after_value,
            debug_effective_delta: value.effective_gain,
            debug_continuity: value.continuity,
            debug_risk_cost: value.risk_cost,
            debug_base_accuracy: 0.0,
            debug_receiver_arrival: 0.0,
            debug_lane_risk: 0.0,
            debug_turnover_consequence: 0.0,
            debug_defender_first_risk: 0.0,
            debug_target_occupation_risk: 0.0,
            debug_nearest_pressure: 0.0,
            debug_developing_runs: 0.0,
            debug_hold_multiplier: 0.0,
            debug_path_min_perp: if path.path_min_perp < 99.0 {
                path.path_min_perp
            } else {
                0.0
            },
            debug_path_peak_threat: path.path_peak_threat,
            debug_path_peak_proj: path.path_peak_proj,
            debug_path_peak_final_third_control: path.path_peak_final_third_control,
            debug_path_peak_control_factor: path.path_peak_control_factor,
            debug_path_conflict_cost: final_score.conflict_cost,
        });
    }
    actions
}

fn build_pass_candidates(
    holder_idx: usize,
    holder: &RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    current_state_value: f64,
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> Vec<RunnerEvaluatedAction> {
    let vision = build_vision_context(&VisionContextInput {
        iq: holder.iq,
        facing_direction: holder.facing_direction,
        attacking_right,
        vision_base_fov: config.vision_base_fov,
        vision_iq_bonus_factor: config.vision_iq_bonus_factor,
        vision_base_distance: config.vision_base_distance,
        vision_iq_distance_bonus_factor: config.vision_iq_distance_bonus_factor,
        vision_max_distance: config.vision_max_distance,
    });
    let players: Vec<PassTeamPlayer<'_>> = teammates
        .iter()
        .enumerate()
        .map(|(idx, player)| PassTeamPlayer {
            space: PassSpacePlayer {
                index: idx,
                pos: player.pos,
                target_pos: player.target_pos,
                tactical_anchor: player.tactical_anchor,
                is_goalkeeper: player.position == "GK",
                is_defender: is_defender_position(player.position.as_str()),
                is_midfielder: is_midfielder_position(player.position.as_str()),
                is_wide: is_wide_position(player.position.as_str()),
            },
            risk: PassRiskPlayer {
                index: idx,
                pos: player.pos,
                speed: player.speed.round() as i32,
                is_goalkeeper: player.position == "GK",
            },
            finishing: player.finishing / 100.0,
            long_shot: player.long_shot / 100.0,
            base: player.base_pos,
            is_defender: is_defender_position(player.position.as_str()),
            goal: player
                .goal_type
                .as_deref()
                .map(|goal_type| crate::ReceiverGoalInput {
                    goal_type,
                    target_pos: player.goal_target,
                    value: player.goal_value,
                }),
        })
        .collect();
    let risk_opponents: Vec<PassRiskPlayer> = opponents
        .iter()
        .enumerate()
        .map(|(idx, player)| PassRiskPlayer {
            index: idx,
            pos: player.pos,
            speed: player.speed.round() as i32,
            is_goalkeeper: player.position == "GK",
        })
        .collect();
    let risk_teammates: Vec<PassRiskPlayer> = teammates
        .iter()
        .enumerate()
        .map(|(idx, player)| PassRiskPlayer {
            index: idx,
            pos: player.pos,
            speed: player.speed.round() as i32,
            is_goalkeeper: player.position == "GK",
        })
        .collect();
    let opponent_xy = opponent_positions(opponents);
    let teammate_indexed = all_teammate_positions(teammates);
    let teammate_goalkeepers = teammate_goalkeeper_indices(teammates);
    let teammate_xy = teammate_xy_positions(teammates, holder_idx);
    let candidates = team_pass_candidates_batch(&TeamPassBatchInput {
        tick,
        passer_index: holder_idx,
        passer_team_home: holder_home,
        passer_pos: holder.pos,
        passer_finishing: holder.finishing / 100.0,
        passer_long_shot: holder.long_shot / 100.0,
        passer_short_passing: holder.short_passing,
        passer_long_passing: holder.long_passing,
        passer_consecutive_carries: holder.consecutive_carries,
        vision,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        offside_line: offside_line(opponents, attacking_right, config),
        player_max_speed: config.player_max_speed,
        player_min_speed: config.player_min_speed,
        short_pass_base_success: config.short_pass_base_success,
        long_pass_base_success: config.long_pass_base_success,
        interception_reach: config.interception_reach,
        shot_ideal_distance: config.shot_ideal_distance,
        shot_on_target_base: config.shot_on_target_base,
        gk_save_base: config.gk_save_base,
        current_value: current_state_value,
        players: &players,
        opponent_positions: &opponent_xy,
        teammate_positions_for_value: &teammate_indexed,
        teammate_goalkeeper_indices_for_value: &teammate_goalkeepers,
        teammate_xy_positions: &teammate_xy,
        risk_opponents: &risk_opponents,
        risk_teammates: &risk_teammates,
        shot_quality_cache: Some(shot_quality_cache),
    });
    let pass_candidates: Vec<_> = candidates
        .into_iter()
        .filter(|candidate| candidate.score > 0.0)
        .collect();
    let actions: Vec<RunnerEvaluatedAction> = pass_candidates
        .into_iter()
        .map(|candidate| RunnerEvaluatedAction {
            action: RunnerHeldAction::Pass {
                receiver_idx: candidate.receiver_index,
                target: candidate.target,
                is_long: candidate.is_long,
                lane_risk: candidate.lane_risk,
            },
            score: candidate.score,
            success_prob: candidate.success_prob,
            receiver_pressure: candidate.receiver_pressure,
            high_threat_space: candidate.high_threat_space,
            final_third_combination: candidate.final_third_combination,
            second_line_arrival_value: candidate.second_line_arrival_value,
            second_line_cutback_value: candidate.second_line_cutback_value,
            layoff_support_value: candidate.layoff_support_value,
            short_combination_value: candidate.short_combination_value,
            layoff_retention_value: candidate.layoff_retention_value,
            receiver_goal_fit: candidate.goal_target_fit,
            target_kind_space: candidate.target_kind_space,
            progress_gain: candidate.progress_gain,
            xg: 0.0,
            pressure: candidate.lane_risk,
            lateral_change: (candidate.target.1 - holder.pos.1).abs() / config.pitch_width.max(1.0),
            carry_to_shoot_window: 0.0,
            wide_second_line_carry_window: 0.0,
            future_shot_gain: 0.0,
            byline_carry_window: 0.0,
            shot_readiness: 0.0,
            open_medium_window: 0.0,
            clean_second_line_shot: 0.0,
            space_manipulation: 0.0,
            pressure_draw: 0.0,
            opportunity_wait: 0.0,
            opportunity_wait_value: 0.0,
            no_clear_release: 0.0,
            raw_score: candidate.raw_score,
            debug_final_score: candidate.score,
            debug_hold_ticks: 0,
            debug_possession_ticks: 0,
            debug_best_pass_score: 0.0,
            debug_shoot_score: 0.0,
            debug_current_pv: candidate.current_value,
            debug_effective_current_value: candidate.effective_current_value,
            debug_delta: candidate.delta,
            debug_after_value: candidate.after_value,
            debug_effective_delta: candidate.effective_delta,
            debug_continuity: candidate.continuity,
            debug_risk_cost: candidate.risk_cost,
            debug_base_accuracy: candidate.base_accuracy,
            debug_receiver_arrival: candidate.receiver_arrival,
            debug_lane_risk: candidate.lane_risk,
            debug_turnover_consequence: candidate.turnover_consequence,
            debug_defender_first_risk: candidate.defender_first_risk,
            debug_target_occupation_risk: candidate.target_occupation_risk,
            debug_nearest_pressure: 0.0,
            debug_developing_runs: 0.0,
            debug_hold_multiplier: 0.0,
            debug_path_min_perp: 0.0,
            debug_path_peak_threat: 0.0,
            debug_path_peak_proj: 0.0,
            debug_path_peak_final_third_control: 0.0,
            debug_path_peak_control_factor: 0.0,
            debug_path_conflict_cost: 0.0,
        })
        .collect();
    actions
}

fn apply_runner_support_opportunity_cost(
    carry_actions: &mut [RunnerEvaluatedAction],
    pass_actions: &[RunnerEvaluatedAction],
) {
    if carry_actions.is_empty() || pass_actions.is_empty() {
        return;
    }
    let pass_inputs: Vec<SupportOpportunityPassInput> = pass_actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Pass { .. }))
        .map(|action| SupportOpportunityPassInput {
            score: action.score,
            receiver_goal_fit: action.receiver_goal_fit,
            second_line_arrival_value: action.second_line_arrival_value,
            second_line_cutback_value: action.second_line_cutback_value,
            layoff_support_value: action.layoff_support_value,
        })
        .collect();
    if pass_inputs.is_empty() {
        return;
    }
    let carry_inputs: Vec<SupportOpportunityCarryInput> = carry_actions
        .iter()
        .map(|action| SupportOpportunityCarryInput {
            score: action.score,
            future_shot_gain: action.future_shot_gain,
            carry_to_shoot_window: action.carry_to_shoot_window,
            effective_gain: action.debug_effective_delta,
        })
        .collect();
    let output = apply_support_opportunity_cost(&SupportOpportunityInput {
        passes: &pass_inputs,
        carries: &carry_inputs,
    });
    for (idx, action) in carry_actions.iter_mut().enumerate() {
        if let Some(score) = output.adjusted_scores.get(idx) {
            action.score = *score;
        }
        let _ = output.costs.get(idx);
        action.no_clear_release = output.support_pressure;
    }
}

fn gk_fallback_pass_candidate(
    holder_idx: usize,
    holder: &RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    current_state_value: f64,
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> Option<RunnerEvaluatedAction> {
    let opponent_xy = opponent_positions(opponents);
    let teammate_indexed = all_teammate_positions(teammates);
    let teammate_goalkeepers = teammate_goalkeeper_indices(teammates);
    let mut best: Option<(RunnerEvaluatedAction, f64)> = None;

    for (idx, teammate) in teammates.iter().enumerate() {
        if idx == holder_idx || teammate.position == "GK" {
            continue;
        }
        let target = teammate.pos;
        let d = distance(holder.pos, target);
        if d < 4.0 || d > 70.0 {
            continue;
        }

        let is_long = d > 32.0;
        let passing = if is_long {
            holder.long_passing
        } else {
            holder.short_passing
        } / 100.0;
        let base = if is_long {
            config.long_pass_base_success
        } else {
            config.short_pass_base_success
        };
        let dist_factor = (1.0 - (d - 10.0).max(0.0) / 72.0).max(0.30);
        let base_accuracy = base * (0.35 + 0.65 * passing) * dist_factor;

        let value = expected_pass_value(&ExpectedPassInput {
            tick,
            passer_index: holder_idx,
            passer_team_home: holder_home,
            passer_pos: holder.pos,
            passer_finishing: holder.finishing / 100.0,
            passer_long_shot: holder.long_shot / 100.0,
            passer_consecutive_carries: holder.consecutive_carries,
            receiver_index: idx,
            receiver_team_home: holder_home,
            receiver_finishing: teammate.finishing / 100.0,
            receiver_long_shot: teammate.long_shot / 100.0,
            receiver_anchor: teammate.tactical_anchor,
            receiver_base: teammate.base_pos,
            receiver_goal_type: teammate.goal_type.as_deref(),
            receiver_goal_target: teammate.goal_type.as_ref().map(|_| teammate.goal_target),
            receiver_goal_value: teammate.goal_value,
            target,
            teammate_positions: &teammate_indexed,
            teammate_goalkeeper_indices: &teammate_goalkeepers,
            opponent_positions: &opponent_xy,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            attacking_right,
            interception_reach: config.interception_reach,
            shot_ideal_distance: config.shot_ideal_distance,
            shot_on_target_base: config.shot_on_target_base,
            gk_save_base: config.gk_save_base,
            current_value: current_state_value,
            base_accuracy,
            receiver_arrival: 1.0,
            continuity: 0.055,
            shot_quality_cache: Some(shot_quality_cache),
        });

        let safety = value.success_prob * (1.0 - value.receiver_pressure) * (1.0 - value.lane_risk);
        let rank = value.score + value.after_value * 0.12 + safety * 0.040 - value.risk_cost * 0.20;
        let action = RunnerEvaluatedAction {
            action: RunnerHeldAction::Pass {
                receiver_idx: idx,
                target,
                is_long,
                lane_risk: value.lane_risk,
            },
            score: rank,
            success_prob: value.success_prob,
            receiver_pressure: value.receiver_pressure,
            high_threat_space: 0.0,
            final_third_combination: 0.0,
            second_line_arrival_value: value.second_line_arrival_value,
            second_line_cutback_value: value.second_line_cutback_value,
            layoff_support_value: value.layoff_support_value,
            short_combination_value: value.short_combination_value,
            layoff_retention_value: value.layoff_retention_value,
            receiver_goal_fit: 0.0,
            target_kind_space: false,
            progress_gain: value.progress_gain,
            xg: 0.0,
            pressure: value.lane_risk,
            lateral_change: (target.1 - holder.pos.1).abs() / config.pitch_width.max(1.0),
            carry_to_shoot_window: 0.0,
            wide_second_line_carry_window: 0.0,
            future_shot_gain: 0.0,
            byline_carry_window: 0.0,
            shot_readiness: 0.0,
            open_medium_window: 0.0,
            clean_second_line_shot: 0.0,
            space_manipulation: 0.0,
            pressure_draw: 0.0,
            opportunity_wait: 0.0,
            opportunity_wait_value: 0.0,
            no_clear_release: 0.0,
            raw_score: value.score,
            debug_final_score: rank,
            debug_hold_ticks: 0,
            debug_possession_ticks: 0,
            debug_best_pass_score: 0.0,
            debug_shoot_score: 0.0,
            debug_current_pv: current_state_value,
            debug_effective_current_value: current_state_value,
            debug_delta: value.after_value - current_state_value,
            debug_after_value: value.after_value,
            debug_effective_delta: value.effective_delta,
            debug_continuity: value.continuity,
            debug_risk_cost: value.risk_cost,
            debug_base_accuracy: base_accuracy,
            debug_receiver_arrival: 1.0,
            debug_lane_risk: value.lane_risk,
            debug_turnover_consequence: value.turnover_consequence,
            debug_defender_first_risk: 0.0,
            debug_target_occupation_risk: 0.0,
            debug_nearest_pressure: 0.0,
            debug_developing_runs: 0.0,
            debug_hold_multiplier: 0.0,
            debug_path_min_perp: 0.0,
            debug_path_peak_threat: 0.0,
            debug_path_peak_proj: 0.0,
            debug_path_peak_final_third_control: 0.0,
            debug_path_peak_control_factor: 0.0,
            debug_path_conflict_cost: 0.0,
        };

        if best
            .as_ref()
            .map(|(_, best_rank)| rank > *best_rank)
            .unwrap_or(true)
        {
            best = Some((action, rank));
        }
    }

    best.map(|(action, _)| action)
}

fn choose_gk_held_action(
    holder_idx: usize,
    holder: &RunnerPlayer,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    holder_home: bool,
    attacking_right: bool,
    current_state_value: f64,
    config: &RunnerRuntimeConfig,
    state: &mut RunnerMatchState,
    tick: i32,
    rng: &mut RunnerRng,
) -> RunnerHeldAction {
    let mut actions = build_pass_candidates(
        holder_idx,
        holder,
        holder_home,
        teammates,
        opponents,
        current_state_value,
        attacking_right,
        tick,
        &state.shot_quality_cache,
        config,
    );
    if actions.is_empty() {
        if let Some(fallback) = gk_fallback_pass_candidate(
            holder_idx,
            holder,
            holder_home,
            teammates,
            opponents,
            current_state_value,
            attacking_right,
            tick,
            &state.shot_quality_cache,
            config,
        ) {
            actions.push(fallback);
        }
    }

    if config.trace_detail == "full" {
        let best_pass_score = actions
            .iter()
            .map(|action| action.score)
            .fold(0.0, f64::max);
        state.trace_entries.push(json!({
            "tick": tick,
            "type": "event",
            "event": "on_ball_candidate_counts",
            "team": if holder_home { "home" } else { "away" },
            "player_idx": holder_idx,
            "player": holder.name,
            "player_pos": [holder.pos.0, holder.pos.1],
            "holder_state": {
                "idx": holder_idx,
                "pos": [holder.pos.0, holder.pos.1],
                "target_pos": [holder.target_pos.0, holder.target_pos.1],
                "tactical_anchor": [holder.tactical_anchor.0, holder.tactical_anchor.1],
                "base_pos": [holder.base_pos.0, holder.base_pos.1],
                "position": holder.position,
                "speed": holder.speed,
                "short_passing": holder.short_passing,
                "long_passing": holder.long_passing,
                "hold_ticks": holder.hold_ticks,
                "possession_ticks": holder.possession_ticks,
                "consecutive_carries": holder.consecutive_carries,
                "facing_direction": holder.facing_direction,
                "iq": holder.iq,
            },
            "carry_count": 0,
            "pass_count": actions.len(),
            "shot_count": 0,
            "hold_count": 0,
            "clear_count": 0,
            "best_pass_score": best_pass_score,
            "best_action_score": best_pass_score,
            "current_state_value": current_state_value
        }));
    }

    if actions.is_empty() {
        return RunnerHeldAction::Clear {
            target: clear_target(holder, attacking_right, config),
        };
    }

    let scores: Vec<f64> = actions.iter().map(|action| action.score).collect();
    let dry_selection = softmax_select_index(&scores, holder.iq, 0.0, 0);
    let mut fallback_index = 0;
    let mut roll = 0.0;
    if let Some(selection) = dry_selection.as_ref() {
        if selection.temperature == 0.0 {
            fallback_index = rng.randbelow(actions.len());
        } else if selection.total_weight >= 1e-10 {
            roll = rng.random();
        }
    }
    let selection = softmax_select_index(&scores, holder.iq, roll, fallback_index);
    let index = selection
        .as_ref()
        .map(|value| value.index)
        .unwrap_or_else(|| {
            actions
                .iter()
                .enumerate()
                .max_by(|(_, a), (_, b)| {
                    a.score
                        .partial_cmp(&b.score)
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .map(|(idx, _)| idx)
                .unwrap_or(0)
        })
        .min(actions.len() - 1);
    record_on_ball_decision_trace(
        state,
        tick,
        holder_home,
        holder_idx,
        holder.name.as_str(),
        holder.pos,
        &actions,
        index,
        config,
    );
    actions[index].action
}

fn build_shot_candidate(
    holder_idx: usize,
    holder: &RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    current_state_value: f64,
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> Option<RunnerEvaluatedAction> {
    let goal = if attacking_right {
        (config.pitch_length, config.pitch_width / 2.0)
    } else {
        (0.0, config.pitch_width / 2.0)
    };
    let dist_to_goal = distance(holder.pos, goal);
    let angle_factor = (angle_to_goal(holder.pos, goal, config.goal_width) / 0.2).min(1.0);
    let mut pressure_factor = 1.0;
    let mut lane_factor = 1.0;
    let shot_dx = goal.0 - holder.pos.0;
    let shot_dy = goal.1 - holder.pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    if shot_len > 1.0 {
        let nx = shot_dx / shot_len;
        let ny = shot_dy / shot_len;
        for opponent in opponents.iter().filter(|player| player.position != "GK") {
            let d = distance(holder.pos, opponent.pos);
            if d < 8.0 {
                pressure_factor *= (1.0 - (8.0 - d) * 0.035).max(0.72);
            }
            let ox = opponent.pos.0 - holder.pos.0;
            let oy = opponent.pos.1 - holder.pos.1;
            let proj = ox * nx + oy * ny;
            if proj > 1.0 && proj < shot_len - 1.0 {
                let perp = (ox * ny - oy * nx).abs();
                if perp < 4.5 {
                    lane_factor *= (1.0 - (4.5 - perp) * 0.05).max(0.65);
                }
            }
        }
    }
    let shot_support: Vec<ShotSupportPlayer> = teammates
        .iter()
        .enumerate()
        .map(|(idx, player)| ShotSupportPlayer {
            index: idx,
            pos: player.pos,
            target: player.target_pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect();
    let opponent_xy = opponent_positions(opponents);
    let shot = evaluate_shot(&ShotInput {
        tick,
        shooter_index: holder_idx,
        shooter_team_home: holder_home,
        shooter_pos: holder.pos,
        finishing: holder.finishing / 100.0,
        long_shot: holder.long_shot / 100.0,
        possession_ticks: holder.possession_ticks,
        consecutive_carries: holder.consecutive_carries,
        last_receive_origin: holder.last_receive_origin,
        dist_to_goal,
        angle_factor,
        pressure_factor: pressure_factor.clamp(0.35, 1.0),
        lane_factor,
        dist_factor: if dist_to_goal <= config.shot_ideal_distance {
            1.0
        } else if dist_to_goal <= 30.0 {
            (1.0 - (dist_to_goal - config.shot_ideal_distance) * 0.070).max(0.18)
        } else {
            0.45 * (-(dist_to_goal - 30.0) / 14.0).exp()
        },
        current_state_value,
        teammates: &shot_support,
        opponents: &opponent_xy,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        attacking_right,
        shot_on_target_base: config.shot_on_target_base,
        gk_save_base: config.gk_save_base,
        shot_ideal_distance: config.shot_ideal_distance,
        goal_reward_constant: 1.0,
        shot_quality_cache: Some(shot_quality_cache),
    });
    if shot.score <= 0.0 {
        return None;
    }
    Some(RunnerEvaluatedAction {
        action: RunnerHeldAction::Shoot {
            target: goal,
            xg: shot.xg,
            on_target_prob: shot.on_target_prob,
        },
        score: shot.score,
        success_prob: shot.on_target_prob,
        receiver_pressure: 0.0,
        high_threat_space: 0.0,
        final_third_combination: 0.0,
        second_line_arrival_value: 0.0,
        second_line_cutback_value: 0.0,
        layoff_support_value: 0.0,
        short_combination_value: 0.0,
        layoff_retention_value: 0.0,
        receiver_goal_fit: 0.0,
        target_kind_space: false,
        progress_gain: 0.0,
        xg: shot.xg,
        pressure: 1.0 - shot.possession_loss_multiplier,
        lateral_change: 0.0,
        carry_to_shoot_window: 0.0,
        wide_second_line_carry_window: 0.0,
        future_shot_gain: 0.0,
        byline_carry_window: 0.0,
        shot_readiness: shot.shot_readiness,
        open_medium_window: shot.open_medium_window,
        clean_second_line_shot: shot.clean_second_line_shot,
        space_manipulation: 0.0,
        pressure_draw: 0.0,
        opportunity_wait: 0.0,
        opportunity_wait_value: 0.0,
        no_clear_release: 0.0,
        raw_score: shot.score,
        debug_final_score: shot.score,
        debug_hold_ticks: 0,
        debug_possession_ticks: 0,
        debug_best_pass_score: 0.0,
        debug_shoot_score: shot.score,
        debug_current_pv: current_state_value,
        debug_effective_current_value: current_state_value,
        debug_delta: shot.xg - current_state_value,
        debug_after_value: shot.xg,
        debug_effective_delta: 0.0,
        debug_continuity: 0.0,
        debug_risk_cost: shot.risk_cost,
        debug_base_accuracy: 0.0,
        debug_receiver_arrival: 0.0,
        debug_lane_risk: 0.0,
        debug_turnover_consequence: 0.0,
        debug_defender_first_risk: 0.0,
        debug_target_occupation_risk: 0.0,
        debug_nearest_pressure: 0.0,
        debug_developing_runs: 0.0,
        debug_hold_multiplier: 0.0,
        debug_path_min_perp: 0.0,
        debug_path_peak_threat: 0.0,
        debug_path_peak_proj: 0.0,
        debug_path_peak_final_third_control: 0.0,
        debug_path_peak_control_factor: 0.0,
        debug_path_conflict_cost: 0.0,
    })
}

fn runner_opportunity_wait_value(
    holder_idx: usize,
    holder: &RunnerPlayer,
    teammates: &[RunnerPlayer],
    shoot_score: f64,
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> f64 {
    let forward_dir = if attacking_right { 1.0 } else { -1.0 };
    let holder_progress = if attacking_right {
        holder.pos.0 / config.pitch_length.max(1.0)
    } else {
        (config.pitch_length - holder.pos.0) / config.pitch_length.max(1.0)
    };
    let holder_width =
        (holder.pos.1 - config.pitch_width / 2.0).abs() / (config.pitch_width / 2.0).max(1.0);
    let mut value: f64 = 0.0;
    for (idx, teammate) in teammates.iter().enumerate() {
        if idx == holder_idx || teammate.position == "GK" {
            continue;
        }
        let target = teammate.target_pos;
        let target_progress = if attacking_right {
            target.0 / config.pitch_length.max(1.0)
        } else {
            (config.pitch_length - target.0) / config.pitch_length.max(1.0)
        };
        let target_centrality = 1.0
            - ((target.1 - config.pitch_width / 2.0).abs() / (config.pitch_width / 2.0).max(1.0))
                .min(1.0);
        let target_width =
            (target.1 - config.pitch_width / 2.0).abs() / (config.pitch_width / 2.0).max(1.0);
        let target_dist = distance(holder.pos, target);
        let move_progress = (target.0 - teammate.pos.0) * forward_dir;
        let depth_gap = (holder.pos.0 - target.0) * forward_dir;
        let lateral_gap = (target.1 - holder.pos.1).abs() / (config.pitch_width / 2.0).max(1.0);
        let short_angle = crate::physics::smoothstep(0.66, 0.88, holder_progress)
            * crate::physics::smoothstep(5.0, 13.0, target_dist)
            * (1.0 - crate::physics::smoothstep(25.0, 36.0, target_dist))
            * crate::physics::smoothstep(0.10, 0.48, lateral_gap)
            * crate::physics::smoothstep(0.30, 0.82, target_centrality);
        let second_line = crate::physics::smoothstep(0.68, 0.88, holder_progress)
            * crate::physics::smoothstep(0.58, 0.82, target_progress)
            * (1.0 - crate::physics::smoothstep(0.84, 0.95, target_progress))
            * crate::physics::smoothstep(4.0, 14.0, depth_gap)
            * (1.0 - crate::physics::smoothstep(24.0, 36.0, depth_gap))
            * crate::physics::smoothstep(0.42, 0.88, target_centrality);
        let developing = crate::physics::smoothstep(0.0, 5.0, move_progress.max(0.0))
            * crate::physics::smoothstep(0.58, 0.84, target_progress)
            * (1.0 - crate::physics::smoothstep(0.88, 0.97, target_progress))
            * (1.0 - crate::physics::smoothstep(18.0, 32.0, target_dist));
        let width_release = crate::physics::smoothstep(0.18, 0.58, holder_width.max(target_width))
            * crate::physics::smoothstep(0.08, 0.40, lateral_gap)
            * (1.0 - crate::physics::smoothstep(22.0, 34.0, target_dist));
        value = value
            .max(short_angle.max(second_line) * (0.70 + 0.30 * developing) + width_release * 0.28);
    }
    value.clamp(0.0, 1.0) * (1.0 - 0.55 * crate::physics::smoothstep(0.08, 0.18, shoot_score))
}

fn build_hold_candidate(
    holder_idx: usize,
    holder: &RunnerPlayer,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    release_best: f64,
    shot_score: f64,
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> Option<RunnerEvaluatedAction> {
    let current_pv = runner_position_value(
        holder.pos,
        teammates,
        Some(holder_idx),
        opponents,
        attacking_right,
        config,
    );
    let pressure = opponents
        .iter()
        .filter(|player| player.position != "GK" && distance(holder.pos, player.pos) < 8.0)
        .count() as i32;
    let nearest_pressure = opponents
        .iter()
        .filter(|player| player.position != "GK")
        .map(|player| {
            let d = distance(holder.pos, player.pos);
            if d < 5.0 {
                1.0 - d / 5.0
            } else {
                0.0
            }
        })
        .fold(0.0, f64::max);
    let forward_dir = if attacking_right { 1.0 } else { -1.0 };
    let developing_runs = teammates
        .iter()
        .enumerate()
        .filter(|(idx, player)| *idx != holder_idx && player.position != "GK")
        .map(|(_, player)| {
            let move_progress = (player.target_pos.0 - player.pos.0) * forward_dir;
            if move_progress > 1.0 {
                (move_progress / 8.0).min(1.0)
            } else {
                0.0
            }
        })
        .fold(0.0, |acc, value| acc + value.min(1.0))
        .min(2.0);
    let opportunity_wait_value = runner_opportunity_wait_value(
        holder_idx,
        holder,
        teammates,
        shot_score,
        attacking_right,
        config,
    );
    let hold = evaluate_hold(&HoldInput {
        iq: holder.iq / 100.0,
        is_midfielder: is_midfielder_position(holder.position.as_str()),
        is_defender: is_defender_position(holder.position.as_str()),
        hold_ticks: holder.hold_ticks,
        possession_ticks: holder.possession_ticks,
        current_pv,
        pressure,
        nearest_pressure,
        developing_runs,
        best_pass_score: release_best,
        shoot_score: shot_score,
        opportunity_wait_value,
    });
    if hold.score <= 0.0 {
        return None;
    }
    Some(RunnerEvaluatedAction {
        action: RunnerHeldAction::Hold {
            opportunity_target: None,
        },
        score: hold.score,
        success_prob: 1.0,
        receiver_pressure: 0.0,
        high_threat_space: 0.0,
        final_third_combination: 0.0,
        second_line_arrival_value: 0.0,
        second_line_cutback_value: 0.0,
        layoff_support_value: 0.0,
        short_combination_value: 0.0,
        layoff_retention_value: 0.0,
        receiver_goal_fit: 0.0,
        target_kind_space: false,
        progress_gain: 0.0,
        xg: 0.0,
        pressure: hold.pressure_factor,
        lateral_change: 0.0,
        carry_to_shoot_window: 0.0,
        wide_second_line_carry_window: 0.0,
        future_shot_gain: 0.0,
        byline_carry_window: 0.0,
        shot_readiness: 0.0,
        open_medium_window: 0.0,
        clean_second_line_shot: 0.0,
        space_manipulation: 0.0,
        pressure_draw: 0.0,
        opportunity_wait: hold.opportunity_wait,
        opportunity_wait_value,
        no_clear_release: hold.no_clear_release,
        raw_score: hold.score,
        debug_final_score: hold.score,
        debug_hold_ticks: holder.hold_ticks,
        debug_possession_ticks: holder.possession_ticks,
        debug_best_pass_score: release_best,
        debug_shoot_score: shot_score,
        debug_current_pv: current_pv,
        debug_effective_current_value: current_pv,
        debug_delta: 0.0,
        debug_after_value: current_pv,
        debug_effective_delta: 0.0,
        debug_continuity: 0.0,
        debug_risk_cost: 0.0,
        debug_base_accuracy: 0.0,
        debug_receiver_arrival: 0.0,
        debug_lane_risk: 0.0,
        debug_turnover_consequence: 0.0,
        debug_defender_first_risk: 0.0,
        debug_target_occupation_risk: 0.0,
        debug_nearest_pressure: nearest_pressure,
        debug_developing_runs: developing_runs,
        debug_hold_multiplier: hold.hold_multiplier,
        debug_path_min_perp: 0.0,
        debug_path_peak_threat: 0.0,
        debug_path_peak_proj: 0.0,
        debug_path_peak_final_third_control: 0.0,
        debug_path_peak_control_factor: 0.0,
        debug_path_conflict_cost: 0.0,
    })
}

fn score_clear_candidate(
    holder: &RunnerPlayer,
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> f64 {
    let x_progress = if attacking_right {
        holder.pos.0 / config.pitch_length
    } else {
        (config.pitch_length - holder.pos.0) / config.pitch_length
    };
    let pressure = opponents
        .iter()
        .filter(|player| player.position != "GK" && distance(holder.pos, player.pos) < 8.0)
        .count() as i32;
    evaluate_clear(&ClearInput {
        x_progress,
        pressure,
        clear_reward_base: config.clear_reward_base,
    })
    .score
}

fn build_clear_candidate(
    holder: &RunnerPlayer,
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> Option<RunnerEvaluatedAction> {
    let x_progress = if attacking_right {
        holder.pos.0 / config.pitch_length
    } else {
        (config.pitch_length - holder.pos.0) / config.pitch_length
    };
    let pressure = opponents
        .iter()
        .filter(|player| player.position != "GK" && distance(holder.pos, player.pos) < 8.0)
        .count() as i32;
    let clear = evaluate_clear(&ClearInput {
        x_progress,
        pressure,
        clear_reward_base: config.clear_reward_base,
    });
    if clear.score <= 0.0 {
        return None;
    }
    let clear_target = if attacking_right {
        pitch_clamp(
            (
                holder.pos.0 + rng.uniform(15.0, 30.0),
                holder.pos.1 + rng.uniform(-20.0, 20.0),
            ),
            config.pitch_length,
            config.pitch_width,
        )
    } else {
        pitch_clamp(
            (
                holder.pos.0 - rng.uniform(15.0, 30.0),
                holder.pos.1 + rng.uniform(-20.0, 20.0),
            ),
            config.pitch_length,
            config.pitch_width,
        )
    };
    Some(RunnerEvaluatedAction {
        action: RunnerHeldAction::Clear {
            target: clear_target,
        },
        score: clear.score,
        success_prob: 1.0,
        receiver_pressure: 0.0,
        high_threat_space: 0.0,
        final_third_combination: 0.0,
        second_line_arrival_value: 0.0,
        second_line_cutback_value: 0.0,
        layoff_support_value: 0.0,
        short_combination_value: 0.0,
        layoff_retention_value: 0.0,
        receiver_goal_fit: 0.0,
        target_kind_space: false,
        progress_gain: 0.0,
        xg: 0.0,
        pressure: clear.pressure_factor,
        lateral_change: 0.0,
        carry_to_shoot_window: 0.0,
        wide_second_line_carry_window: 0.0,
        future_shot_gain: 0.0,
        byline_carry_window: 0.0,
        shot_readiness: 0.0,
        open_medium_window: 0.0,
        clean_second_line_shot: 0.0,
        space_manipulation: 0.0,
        pressure_draw: 0.0,
        opportunity_wait: 0.0,
        opportunity_wait_value: 0.0,
        no_clear_release: 0.0,
        raw_score: clear.score,
        debug_final_score: clear.score,
        debug_hold_ticks: 0,
        debug_possession_ticks: 0,
        debug_best_pass_score: 0.0,
        debug_shoot_score: 0.0,
        debug_current_pv: 0.0,
        debug_effective_current_value: 0.0,
        debug_delta: 0.0,
        debug_after_value: 0.0,
        debug_effective_delta: 0.0,
        debug_continuity: 0.0,
        debug_risk_cost: 0.0,
        debug_base_accuracy: 0.0,
        debug_receiver_arrival: 0.0,
        debug_lane_risk: 0.0,
        debug_turnover_consequence: 0.0,
        debug_defender_first_risk: 0.0,
        debug_target_occupation_risk: 0.0,
        debug_nearest_pressure: 0.0,
        debug_developing_runs: 0.0,
        debug_hold_multiplier: 0.0,
        debug_path_min_perp: 0.0,
        debug_path_peak_threat: 0.0,
        debug_path_peak_proj: 0.0,
        debug_path_peak_final_third_control: 0.0,
        debug_path_peak_control_factor: 0.0,
        debug_path_conflict_cost: 0.0,
    })
}

fn runner_action_code(action: RunnerHeldAction) -> u8 {
    match action {
        RunnerHeldAction::Carry { .. } => 0,
        RunnerHeldAction::Pass { .. } => 1,
        RunnerHeldAction::Shoot { .. } => 2,
        RunnerHeldAction::Hold { .. } => 3,
        RunnerHeldAction::Clear { .. } => 4,
    }
}

fn runner_action_target(action: RunnerHeldAction, holder_pos: (f64, f64)) -> Option<(f64, f64)> {
    match action {
        RunnerHeldAction::Carry { target } => Some(target),
        RunnerHeldAction::Pass { target, .. } => Some(target),
        RunnerHeldAction::Clear { target } => Some(target),
        RunnerHeldAction::Shoot { target, .. } => Some(target),
        RunnerHeldAction::Hold { .. } => Some(holder_pos),
    }
}

fn runner_action_name(action: RunnerHeldAction) -> &'static str {
    match action {
        RunnerHeldAction::Carry { .. } => "carry",
        RunnerHeldAction::Pass { .. } => "pass",
        RunnerHeldAction::Shoot { .. } => "shoot",
        RunnerHeldAction::Hold { .. } => "hold",
        RunnerHeldAction::Clear { .. } => "clear",
    }
}

fn runner_action_source(action: RunnerHeldAction) -> &'static str {
    match action {
        RunnerHeldAction::Carry { .. } => "carry",
        RunnerHeldAction::Pass { is_long, .. } => {
            if is_long {
                "long_pass"
            } else {
                "pass"
            }
        }
        RunnerHeldAction::Shoot { .. } => "shot",
        RunnerHeldAction::Hold { .. } => "hold",
        RunnerHeldAction::Clear { .. } => "clear",
    }
}

fn runner_action_components(action: &RunnerEvaluatedAction) -> serde_json::Value {
    json!({
        "current_value": action.debug_current_pv,
        "effective_current_value": action.debug_effective_current_value,
        "after_value": action.debug_after_value,
        "delta": action.debug_delta,
        "effective_delta": action.debug_effective_delta,
        "success_prob": action.success_prob,
        "risk_cost": action.debug_risk_cost,
        "final_score": action.debug_final_score,
        "raw_score": action.raw_score,
        "continuity": action.debug_continuity,
        "base_accuracy": action.debug_base_accuracy,
        "receiver_arrival": action.debug_receiver_arrival,
        "lane_risk": action.debug_lane_risk,
        "turnover_consequence": action.debug_turnover_consequence,
        "defender_first_risk": action.debug_defender_first_risk,
        "target_occupation_risk": action.debug_target_occupation_risk,
        "consecutive_carries": 0,
        "progress_gain": action.progress_gain,
        "receiver_pressure": action.receiver_pressure,
        "high_threat_space": action.high_threat_space,
        "target_kind": if action.target_kind_space { "space" } else { "feet" },
        "xg": action.xg,
        "shot_readiness": action.shot_readiness,
        "hold_ticks": action.debug_hold_ticks,
        "possession_ticks": action.debug_possession_ticks,
        "best_pass_score": action.debug_best_pass_score,
        "shoot_score": action.debug_shoot_score,
        "current_pv": action.debug_current_pv,
        "nearest_pressure": action.debug_nearest_pressure,
        "developing_runs": action.debug_developing_runs,
        "hold_multiplier": action.debug_hold_multiplier,
        "future_shot_gain": action.future_shot_gain,
        "carry_to_shoot_window": action.carry_to_shoot_window,
        "wide_second_line_carry_window": action.wide_second_line_carry_window,
        "byline_carry_window": action.byline_carry_window,
        "pressure_draw": action.pressure_draw,
        "space_manipulation": action.space_manipulation,
        "path_min_perp": action.debug_path_min_perp,
        "path_peak_threat": action.debug_path_peak_threat,
        "path_peak_proj": action.debug_path_peak_proj,
        "path_peak_final_third_control": action.debug_path_peak_final_third_control,
        "path_peak_control_factor": action.debug_path_peak_control_factor,
        "path_conflict_cost": action.debug_path_conflict_cost,
    })
}

fn runner_action_candidate_payload(
    action: &RunnerEvaluatedAction,
    holder_pos: (f64, f64),
) -> serde_json::Value {
    let target = runner_action_target(action.action, holder_pos);
    let details = match (action.action, target) {
        (RunnerHeldAction::Pass { receiver_idx, .. }, Some(pos)) => {
            if action.target_kind_space {
                json!({"target": [pos.0, pos.1], "intended_receiver": receiver_idx})
            } else {
                json!({"target": [pos.0, pos.1], "target_player_idx": receiver_idx})
            }
        }
        (RunnerHeldAction::Hold { opportunity_target }, Some(pos)) => {
            let mut details = json!({"target": [pos.0, pos.1]});
            if let Some(opportunity_target) = opportunity_target {
                details["opportunity_target"] = json!([opportunity_target.0, opportunity_target.1]);
            }
            details
        }
        (_, Some(pos)) => json!({"target": [pos.0, pos.1]}),
        _ => json!({}),
    };
    json!({
        "phase": "on_ball",
        "action_type": runner_action_name(action.action),
        "target": target.map(|pos| json!([pos.0, pos.1])).unwrap_or(serde_json::Value::Null),
        "value": {
            "score": action.score,
            "success_prob": action.success_prob,
            "risk_cost": action.debug_risk_cost,
            "current_value": action.debug_current_pv,
            "after_value": action.debug_after_value,
                "components": runner_action_components(action)
        },
        "details": details,
        "source": runner_action_source(action.action),
    })
}

fn record_on_ball_decision_trace(
    state: &mut RunnerMatchState,
    tick: i32,
    team_home: bool,
    player_idx: usize,
    player_name: &str,
    player_pos: (f64, f64),
    actions: &[RunnerEvaluatedAction],
    chosen_index: usize,
    config: &RunnerRuntimeConfig,
) {
    if config.trace_detail == "off" || actions.is_empty() {
        return;
    }
    let chosen_index = chosen_index.min(actions.len() - 1);
    let chosen = runner_action_candidate_payload(&actions[chosen_index], player_pos);
    let mut alternatives = Vec::new();
    if config.trace_detail != "chosen" {
        let mut indexed: Vec<(usize, &RunnerEvaluatedAction)> =
            actions.iter().enumerate().collect();
        indexed.sort_by(|(_, a), (_, b)| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let limit = if config.trace_detail == "top_candidates" {
            config.trace_top_k
        } else {
            usize::MAX
        };
        for (idx, action) in indexed {
            if idx == chosen_index {
                continue;
            }
            if alternatives.len() >= limit {
                break;
            }
            alternatives.push(runner_action_candidate_payload(action, player_pos));
        }
    }
    let goal_trace = state
        .pending_on_ball_goal_event
        .as_ref()
        .map(|event| {
            json!({
                "goal": {
                    "goal_type": event.get("goal_type").cloned().unwrap_or(serde_json::Value::Null),
                    "target_pos": event.get("target").cloned().unwrap_or(serde_json::Value::Null),
                    "value": event.get("value").cloned().unwrap_or(serde_json::Value::Null),
                    "context": {
                        "phase": event.get("phase").cloned().unwrap_or(serde_json::Value::Null),
                        "action_code": event.get("action_code").cloned().unwrap_or(serde_json::Value::Null),
                    },
                },
                "switched": event.get("switched").cloned().unwrap_or(serde_json::Value::Null),
                "reason": event.get("reason").cloned().unwrap_or(serde_json::Value::Null),
                "candidate_count": event.get("candidate_count").cloned().unwrap_or(serde_json::Value::Null),
                "candidates": event.get("candidates").cloned().unwrap_or(serde_json::Value::Null),
                "cut_candidate": event.get("cut_candidate").cloned().unwrap_or(serde_json::Value::Null),
                "candidate_choice": event.get("candidate_choice").cloned().unwrap_or(serde_json::Value::Null),
            })
        })
        .unwrap_or(serde_json::Value::Null);
    state.trace_decisions.push(json!({
        "tick": tick,
        "team": if team_home { "home" } else { "away" },
        "player_idx": player_idx,
        "player": player_name,
        "phase": "on_ball",
        "chosen": chosen,
        "alternatives": alternatives,
        "pos": [player_pos.0, player_pos.1],
        "goal": goal_trace,
    }));
}

fn runner_selection_candidate(action: &RunnerEvaluatedAction) -> OnBallSelectionCandidateInput {
    OnBallSelectionCandidateInput {
        score: action.score,
        action_code: runner_action_code(action.action),
        target_kind_space: action.target_kind_space,
        success_prob: action.success_prob,
        receiver_pressure: action.receiver_pressure,
        high_threat_space: action.high_threat_space,
    }
}

fn apply_selection_scores_to_actions(
    actions: &mut [RunnerEvaluatedAction],
    selection: &OnBallSelectionOutput,
) {
    for (action, score) in actions.iter_mut().zip(selection.noisy_scores.iter()) {
        action.score = *score;
    }
}

fn apply_runner_generic_goal_continuity(
    holder: &mut RunnerPlayer,
    actions: &mut [RunnerEvaluatedAction],
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) {
    if actions.is_empty() {
        return;
    }
    let candidates: Vec<OnBallGenericCandidateInput> = actions
        .iter()
        .map(|action| OnBallGenericCandidateInput {
            score: action.score,
            action_code: runner_action_code(action.action),
            target: runner_action_target(action.action, holder.pos),
            progress_gain: action.progress_gain,
            xg: action.xg,
            pressure: action.pressure,
            receiver_pressure: action.receiver_pressure,
            target_kind_space: action.target_kind_space,
            lateral_change: action.lateral_change,
        })
        .collect();
    let current_goal = holder.goal_type.as_deref().and_then(|goal_type| {
        if matches!(
            goal_type,
            "create_shot"
                | "progress_carry"
                | "protect_ball"
                | "recycle"
                | "switch_play"
                | "through_ball"
                | "clear_danger"
        ) {
            Some(OnBallGenericGoalInput {
                goal_type: Some(goal_type),
                target_pos: holder.goal_target,
                value: holder.goal_value,
                action_code: holder.goal_action_code,
            })
        } else {
            None
        }
    });

    let mut best_index = 0usize;
    let mut best_score = candidates[0].score;
    for (idx, candidate) in candidates.iter().enumerate().skip(1) {
        if candidate.score > best_score {
            best_index = idx;
            best_score = candidate.score;
        }
    }
    let best_candidate = candidates[best_index];
    let candidate_goal_type = match runner_action_code(actions[best_index].action) {
        2 => "create_shot",
        0 => {
            if best_candidate.progress_gain > 0.015 {
                "progress_carry"
            } else {
                "protect_ball"
            }
        }
        1 => {
            if best_candidate.progress_gain < -0.015 {
                "recycle"
            } else if best_candidate.target_kind_space {
                "through_ball"
            } else if best_candidate.lateral_change.abs() > 0.28 {
                "switch_play"
            } else {
                "recycle"
            }
        }
        3 => "protect_ball",
        4 => "clear_danger",
        _ => "protect_ball",
    };
    let candidate_target = best_candidate.target.unwrap_or(holder.pos);
    let candidate_value = best_candidate.score.max(0.0);
    let current_storage = current_goal.map(|goal| GoalInput {
        goal_type: goal.goal_type.unwrap_or(""),
        value: goal.value,
        phase: Some("execute"),
    });
    let candidate_goal = GoalInput {
        goal_type: candidate_goal_type,
        value: candidate_value,
        phase: Some("execute"),
    };
    let context = GoalSwitchCostInput {
        base: 0.020,
        context_stability: 1.0,
        role_discipline: 1.0,
        pressure_interrupt: 0.0,
        iq: holder.iq,
    };
    let selection = select_runner_goal_with_noise(
        current_storage.as_ref(),
        &candidate_goal,
        &context,
        config.goal_noise_scale,
        rng,
    );

    let selected_is_candidate = selection.selected == "candidate";
    let selected_goal_type = if selected_is_candidate {
        candidate_goal_type.to_string()
    } else {
        current_goal
            .and_then(|goal| goal.goal_type)
            .unwrap_or(candidate_goal_type)
            .to_string()
    };
    let selected_action_code = if selected_is_candidate {
        runner_action_code(actions[best_index].action)
    } else {
        current_goal
            .map(|goal| goal.action_code)
            .unwrap_or_else(|| runner_action_code(actions[best_index].action))
    };
    let selected_target = if selected_is_candidate {
        candidate_target
    } else {
        current_goal
            .map(|goal| goal.target_pos)
            .unwrap_or(candidate_target)
    };
    let selected_value = if selected_is_candidate {
        candidate_value
    } else {
        current_goal
            .map(|goal| goal.value)
            .unwrap_or(candidate_value)
    };

    let continuity_bias = 0.035_f64.max(0.0) * 0.35;
    for action in actions.iter_mut() {
        if continuity_bias > 0.0 && runner_action_code(action.action) == selected_action_code {
            let target_fit = runner_action_target(action.action, holder.pos)
                .map(|target| (1.0 - distance(target, selected_target) / 18.0).max(0.0))
                .unwrap_or(1.0);
            action.score += continuity_bias * selected_value.max(0.0) * (0.35 + 0.65 * target_fit);
        }
    }
    holder.goal_type = Some(selected_goal_type);
    holder.goal_phase = Some("execute".to_string());
    holder.goal_target = selected_target;
    holder.goal_value = selected_value;
    holder.goal_action_code = selected_action_code;
}

fn consume_runner_on_ball_selection_random(
    rng: &mut RunnerRng,
    actions_len: usize,
    dry_selection: Option<&OnBallSelectionOutput>,
) -> (f64, usize) {
    let mut fallback_index = 0;
    let mut roll = 0.0;
    if let Some(selection) = dry_selection {
        if selection.used_random_choice {
            fallback_index = rng.randbelow(actions_len);
        } else if selection.used_roll {
            roll = rng.random();
        }
    }
    (roll, fallback_index)
}

fn raw_softmax_selection(
    scores: &[f64],
    iq: f64,
    roll: f64,
    fallback_index: usize,
) -> (usize, bool, bool) {
    if scores.is_empty() {
        return (0, false, false);
    }
    if scores.len() == 1 {
        return (0, false, false);
    }
    let max_score = scores.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if max_score < 0.001 {
        return (fallback_index % scores.len(), false, true);
    }
    let selection = softmax_select_index(scores, iq, roll, 0);
    let Some(selection) = selection else {
        return (0, false, false);
    };
    (
        selection.index.min(scores.len() - 1),
        selection.total_weight >= 1e-10,
        false,
    )
}

fn consume_runner_raw_softmax_selection_random(
    rng: &mut RunnerRng,
    scores: &[f64],
    iq: f64,
) -> (f64, usize) {
    let (_, dry_used_roll, dry_used_random_choice) = raw_softmax_selection(scores, iq, 0.0, 0);
    if dry_used_random_choice {
        return (0.0, rng.randbelow(scores.len()));
    }
    if dry_used_roll {
        return (rng.random(), 0);
    }
    (0.0, 0)
}

fn is_runner_on_ball_specialized_goal(goal_type: &str) -> bool {
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

fn runner_progress_x(x: f64, pitch_length: f64, attacking_right: bool) -> f64 {
    if attacking_right {
        x / pitch_length.max(1.0)
    } else {
        (pitch_length - x) / pitch_length.max(1.0)
    }
}

fn runner_centrality_y(y: f64, pitch_width: f64) -> f64 {
    1.0 - ((y - pitch_width / 2.0).abs() / (pitch_width / 2.0).max(1.0)).min(1.0)
}

fn runner_attracted_pressure(holder: &RunnerPlayer, opponents: &[RunnerPlayer]) -> f64 {
    let mut pressure: f64 = 0.0;
    for opponent in opponents.iter().filter(|player| player.position != "GK") {
        let d = distance(holder.pos, opponent.pos);
        if d < 11.0 {
            pressure += 1.0 - d / 11.0;
        }
    }
    (pressure * 0.42).min(1.0)
}

fn byline_delivery_support_for_runner(
    holder_idx: usize,
    holder: &RunnerPlayer,
    teammates: &[RunnerPlayer],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> f64 {
    let carrier_progress = runner_progress_x(holder.pos.0, config.pitch_length, attacking_right);
    let carrier_width =
        (holder.pos.1 - config.pitch_width / 2.0).abs() / (config.pitch_width / 2.0).max(1.0);
    if carrier_progress < 0.58 || carrier_width < 0.38 {
        return 0.0;
    }

    let mut support: f64 = 0.0;
    for (idx, teammate) in teammates.iter().enumerate() {
        if idx == holder_idx || teammate.position == "GK" {
            continue;
        }
        for point in [teammate.pos, teammate.target_pos, teammate.tactical_anchor] {
            let progress = runner_progress_x(point.0, config.pitch_length, attacking_right);
            let centrality = runner_centrality_y(point.1, config.pitch_width);
            let depth_gap = (point.0 - holder.pos.0) * if attacking_right { 1.0 } else { -1.0 };
            let weak_side = if (point.1 - config.pitch_width / 2.0)
                * (holder.pos.1 - config.pitch_width / 2.0)
                < 0.0
            {
                1.0
            } else {
                0.0
            };
            let box_target = crate::physics::smoothstep(0.78, 0.94, progress)
                * crate::physics::smoothstep(0.45, 0.92, centrality)
                * (0.60 + 0.25 * weak_side);
            let cutback_target = crate::physics::smoothstep(0.62, 0.84, progress)
                * crate::physics::smoothstep(0.52, 0.92, centrality)
                * crate::physics::smoothstep(-12.0, 6.0, depth_gap)
                * (1.0 - crate::physics::smoothstep(18.0, 34.0, depth_gap.abs()))
                * (0.60 + 0.25 * weak_side);
            support = support.max(box_target).max(cutback_target);
        }
    }
    support.clamp(0.0, 1.0)
}

fn apply_runner_specialized_selected_goal_bias(
    actions: &mut [RunnerEvaluatedAction],
    holder: &mut RunnerPlayer,
    goal_type: &str,
    goal_phase: &str,
    goal_target: (f64, f64),
    goal_value: f64,
    goal_created_tick: i32,
    action_code: u8,
) {
    holder.goal_type = Some(goal_type.to_string());
    holder.goal_phase = Some(goal_phase.to_string());
    holder.goal_target = goal_target;
    holder.goal_value = goal_value.max(0.0);
    holder.goal_created_tick = goal_created_tick;
    holder.goal_action_code = action_code;

    let specialized: Vec<OnBallSpecializedBiasCandidateInput> = actions
        .iter()
        .map(|action| OnBallSpecializedBiasCandidateInput {
            score: action.score,
            action_code: runner_action_code(action.action),
            target: runner_action_target(action.action, holder.pos),
            carry_to_shoot_window: action.carry_to_shoot_window,
            wide_second_line_carry_window: action.wide_second_line_carry_window,
            future_shot_gain: action.future_shot_gain,
            byline_carry_window: action.byline_carry_window,
            xg: action.xg,
            shot_readiness: action.shot_readiness,
            open_medium_window: action.open_medium_window,
            clean_second_line_shot: action.clean_second_line_shot,
            space_manipulation: action.space_manipulation,
            pressure_draw: action.pressure_draw,
        })
        .collect();
    let bias = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
        candidates: &specialized,
        goal_type,
        goal_phase,
        goal_target,
        goal_value,
        bias: 0.035,
        consecutive_carries: holder.consecutive_carries,
    });
    for (action, score) in actions.iter_mut().zip(bias.biased_scores.iter()) {
        action.score = *score;
    }
    if goal_type == "hold_for_opportunity" {
        for action in actions.iter_mut() {
            if let RunnerHeldAction::Hold { opportunity_target } = &mut action.action {
                *opportunity_target = Some(goal_target);
            }
        }
    }
}

fn apply_runner_specialized_goal_bias(
    state: &mut RunnerMatchState,
    holder_idx: usize,
    holder: &mut RunnerPlayer,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    actions: &mut [RunnerEvaluatedAction],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
    tick: i32,
    rng: &mut RunnerRng,
) -> bool {
    if actions.is_empty() {
        return false;
    }
    let shot = actions
        .iter()
        .find(|action| matches!(action.action, RunnerHeldAction::Shoot { .. }));
    let mut goals = Vec::new();
    if let Some(goal_type) = config.runner_force_specialized_goal.as_deref() {
        let action_code = match goal_type {
            "through_ball_behind"
            | "release_pressure_with_layoff"
            | "release_to_arriving_support" => 1,
            "hold_for_opportunity" => 3,
            _ => 0,
        };
        let target = actions
            .iter()
            .find(|action| runner_action_code(action.action) == action_code)
            .and_then(|action| runner_action_target(action.action, holder.pos))
            .unwrap_or(holder.pos);
        let phase = match goal_type {
            "hold_for_opportunity" => "scan",
            "wide_byline_attack" => "drive",
            "cut_inside_to_shoot" => "drive",
            _ => "release",
        };
        goals.push(RunnerSpecializedGoal {
            goal_type: match goal_type {
                "cut_inside_to_shoot" => "cut_inside_to_shoot",
                "wide_byline_attack" => "wide_byline_attack",
                "through_ball_behind" => "through_ball_behind",
                "release_pressure_with_layoff" => "release_pressure_with_layoff",
                "release_to_arriving_support" => "release_to_arriving_support",
                "hold_for_opportunity" => "hold_for_opportunity",
                _ => "cut_inside_to_shoot",
            },
            phase,
            target,
            value: 1.0,
            created_tick: tick,
            action_code,
        });
    }
    let carry_refs: Vec<(&RunnerEvaluatedAction, (f64, f64))> = actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Carry { .. }))
        .filter_map(|action| {
            runner_action_target(action.action, holder.pos).map(|target| (action, target))
        })
        .collect();
    if carry_refs.is_empty() && config.runner_force_specialized_goal.is_none() {
        return false;
    }
    let current_cut_goal_age = if holder.goal_type.as_deref() == Some("cut_inside_to_shoot") {
        (tick - holder.goal_created_tick).max(0)
    } else {
        0
    };
    let mut current_cut_release = false;
    let mut cut_candidate_trace = serde_json::Value::Null;
    let mut best_carry: Option<&RunnerEvaluatedAction> = None;
    for action in actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Carry { .. }))
    {
        if best_carry
            .map(|current| action.score > current.score)
            .unwrap_or(true)
        {
            best_carry = Some(action);
        }
    }
    if let Some(best_carry) = best_carry {
        let cut = evaluate_cut_inside_goal(&CutInsideGoalInput {
            player_pos: holder.pos,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            best_carry_target: runner_action_target(best_carry.action, holder.pos),
            future_shot_gain: best_carry.future_shot_gain,
            carry_to_shoot_window: best_carry.carry_to_shoot_window,
            wide_second_line_carry_window: best_carry.wide_second_line_carry_window,
            current_shot: shot.map(|action| action.xg).unwrap_or(0.0),
            current_readiness: shot.map(|action| action.shot_readiness).unwrap_or(0.0),
            consecutive_carries: holder.consecutive_carries,
            goal_age_ticks: current_cut_goal_age,
        });
        cut_candidate_trace = json!({
            "target": runner_action_target(best_carry.action, holder.pos)
                .map(|target| json!([target.0, target.1]))
                .unwrap_or(serde_json::Value::Null),
            "score": best_carry.score,
            "raw_score": best_carry.raw_score,
            "debug_final_score": best_carry.debug_final_score,
            "future_shot_gain": best_carry.future_shot_gain,
            "carry_to_shoot_window": best_carry.carry_to_shoot_window,
            "wide_second_line_carry_window": best_carry.wide_second_line_carry_window,
            "current_shot": shot.map(|action| action.xg).unwrap_or(0.0),
            "current_readiness": shot.map(|action| action.shot_readiness).unwrap_or(0.0),
            "has_goal": cut.has_goal,
            "value": cut.value,
            "phase_code": cut.phase_code,
        });
        current_cut_release = cut.has_goal
            && holder.goal_type.as_deref() == Some("cut_inside_to_shoot")
            && cut.phase_code == 1;
        if cut.has_goal {
            let phase = match cut.phase_code {
                2 => "finish",
                1 => "release",
                _ => "drive",
            };
            goals.push(RunnerSpecializedGoal {
                goal_type: "cut_inside_to_shoot",
                phase,
                target: cut.target_pos,
                value: cut.value,
                created_tick: if holder.goal_type.as_deref() == Some("cut_inside_to_shoot") {
                    holder.goal_created_tick
                } else {
                    tick
                },
                action_code: if phase == "finish" { 2 } else { 0 },
            });
        }
    }
    let immediate_best_score = actions
        .iter()
        .map(|action| action.score)
        .fold(0.0, f64::max);
    let byline_teammates: Vec<BylineSupportTeammateInput> = teammates
        .iter()
        .enumerate()
        .map(|(idx, teammate)| BylineSupportTeammateInput {
            index: idx,
            pos: teammate.pos,
            target: teammate.target_pos,
            anchor: teammate.tactical_anchor,
            is_goalkeeper: teammate.position == "GK",
        })
        .collect();
    let byline_carries: Vec<BylineCarryInput> = carry_refs
        .iter()
        .map(|(action, target)| BylineCarryInput {
            score: action.score,
            target: *target,
            byline_carry_window: action.byline_carry_window,
        })
        .collect();
    let byline_selection = select_best_byline_carry(&BylineCarrySelectionInput {
        player_index: holder_idx,
        player_pos: holder.pos,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        teammates: &byline_teammates,
        carries: &byline_carries,
    });
    if !current_cut_release {
        if let Some(index) = byline_selection.index {
            if let Some((carry, target)) = carry_refs.get(index) {
                let byline = evaluate_drive_byline_goal(&DriveBylineGoalInput {
                    player_pos: holder.pos,
                    carry_target: *target,
                    attacking_right,
                    pitch_length: config.pitch_length,
                    pitch_width: config.pitch_width,
                    carry_score: byline_selection.score,
                    progress_gain: carry.progress_gain,
                    byline_carry_window: carry.byline_carry_window,
                    path_feasibility: carry.success_prob,
                    space_manipulation: carry.space_manipulation,
                    delivery_support: byline_selection.delivery_support,
                });
                if byline.has_goal {
                    goals.push(RunnerSpecializedGoal {
                        goal_type: "wide_byline_attack",
                        phase: "drive",
                        target: byline.target_pos,
                        value: byline.value,
                        created_tick: tick,
                        action_code: 0,
                    });
                }
            }
        }
    }

    let pass_refs: Vec<(&RunnerEvaluatedAction, (f64, f64))> = actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Pass { .. }))
        .filter_map(|action| {
            runner_action_target(action.action, holder.pos).map(|target| (action, target))
        })
        .collect();
    let overlap_passes: Vec<OverlapPassInput> = pass_refs
        .iter()
        .map(|(action, target)| OverlapPassInput {
            score: action.score,
            target: *target,
            receiver_pressure: action.receiver_pressure,
        })
        .collect();
    let best_overlap = select_best_overlap(&OverlapSelectionInput {
        player_pos: holder.pos,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        passes: &overlap_passes,
    });
    if best_overlap.index.is_some() {
        let wide_hold = evaluate_wide_hold_overlap_goal(&WideHoldOverlapGoalInput {
            player_pos: holder.pos,
            overlap_target: best_overlap.target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            overlap_value: best_overlap.value,
            immediate_best_score,
        });
        if wide_hold.has_goal {
            goals.push(RunnerSpecializedGoal {
                goal_type: "wide_hold_for_overlap",
                phase: "wait",
                target: wide_hold.target_pos,
                value: wide_hold.value,
                created_tick: tick,
                action_code: 3,
            });
        }
    }

    let mut best_through_ball: Option<RunnerSpecializedGoal> = None;
    let mut best_byline_delivery: Option<RunnerSpecializedGoal> = None;
    for (pass, target) in &pass_refs {
        let target_progress = runner_progress_x(target.0, config.pitch_length, attacking_right);
        let centrality = runner_centrality_y(target.1, config.pitch_width);
        let through = evaluate_through_ball_goal(&ThroughBallGoalInput {
            player_pos: holder.pos,
            pass_target: *target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            pass_score: pass.score,
            target_kind_space: pass.target_kind_space,
            target_progress,
            centrality,
            progress_gain: pass.progress_gain,
            high_threat_space: pass.high_threat_space,
            success_prob: pass.success_prob,
            receiver_pressure: pass.receiver_pressure,
            lane_risk: pass.pressure,
        });
        if through.has_goal
            && best_through_ball
                .as_ref()
                .map(|goal| through.value > goal.value)
                .unwrap_or(true)
        {
            best_through_ball = Some(RunnerSpecializedGoal {
                goal_type: "through_ball_behind",
                phase: "release",
                target: through.target_pos,
                value: through.value,
                created_tick: tick,
                action_code: 1,
            });
        }
        let delivery = evaluate_byline_delivery_goal(&BylineDeliveryGoalInput {
            player_pos: holder.pos,
            delivery_target: *target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            pass_score: pass.score,
            target_progress,
            centrality,
            high_threat_space: pass.high_threat_space,
            final_third_combination: pass.final_third_combination,
            success_prob: pass.success_prob,
            receiver_pressure: pass.receiver_pressure,
            lane_risk: pass.pressure,
        });
        if delivery.has_goal
            && best_byline_delivery
                .as_ref()
                .map(|goal| delivery.value > goal.value)
                .unwrap_or(true)
        {
            best_byline_delivery = Some(RunnerSpecializedGoal {
                goal_type: "wide_byline_attack",
                phase: "release",
                target: delivery.target_pos,
                value: delivery.value,
                created_tick: tick,
                action_code: 1,
            });
        }
    }
    if let Some(goal) = best_through_ball {
        goals.push(goal);
    }
    if let Some(goal) = best_byline_delivery {
        goals.push(goal);
    }

    let opponent_positions: Vec<(f64, f64)> = opponents
        .iter()
        .filter(|opponent| opponent.position != "GK")
        .map(|opponent| opponent.pos)
        .collect();
    let layoff_passes: Vec<LayoffPassInput> = pass_refs
        .iter()
        .map(|(action, target)| LayoffPassInput {
            score: action.score,
            target: *target,
            receiver_pressure: action.receiver_pressure,
        })
        .collect();
    let best_layoff = select_best_layoff(&LayoffSelectionInput {
        player_pos: holder.pos,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        passes: &layoff_passes,
        opponents: &opponent_positions,
    });
    if best_layoff.index.is_some() {
        let layoff = evaluate_layoff_goal(&LayoffGoalInput {
            player_pos: holder.pos,
            layoff_target: best_layoff.target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            attracted_pressure: best_layoff.attracted_pressure,
            layoff_value: best_layoff.value,
            immediate_best_score,
        });
        if layoff.has_goal {
            goals.push(RunnerSpecializedGoal {
                goal_type: "release_pressure_with_layoff",
                phase: "release",
                target: layoff.target_pos,
                value: layoff.value,
                created_tick: tick,
                action_code: 1,
            });
        }
    }

    let arriving_passes: Vec<ArrivingSupportPassInput> = pass_refs
        .iter()
        .map(|(action, target)| ArrivingSupportPassInput {
            score: action.score,
            target: *target,
            receiver_goal_fit: action.receiver_goal_fit,
            second_line_arrival_value: action.second_line_arrival_value,
            second_line_cutback_value: action.second_line_cutback_value,
            layoff_support_value: action.layoff_support_value,
        })
        .collect();
    let best_arriving_support = select_best_arriving_support(&ArrivingSupportSelectionInput {
        player_pos: holder.pos,
        passes: &arriving_passes,
        opponents: &opponent_positions,
    });
    if best_arriving_support.index.is_some() {
        let release = evaluate_release_support_goal(&ReleaseSupportGoalInput {
            player_pos: holder.pos,
            support_target: best_arriving_support.target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            support_value: best_arriving_support.support_value,
            receiver_goal_fit: best_arriving_support.receiver_goal_fit,
            current_shot: shot.map(|action| action.xg).unwrap_or(0.0),
            shot_readiness: shot
                .map(|action| {
                    action
                        .shot_readiness
                        .max(action.open_medium_window)
                        .max(action.clean_second_line_shot)
                })
                .unwrap_or(0.0),
            consecutive_carries: holder.consecutive_carries,
            attracted_pressure: best_arriving_support.attracted_pressure,
        });
        if release.has_goal {
            goals.push(RunnerSpecializedGoal {
                goal_type: "release_to_arriving_support",
                phase: "release",
                target: release.target_pos,
                value: release.value,
                created_tick: tick,
                action_code: 1,
            });
        }
    }
    let hold_passes: Vec<HoldSupportPassInput> = actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Pass { .. }))
        .filter_map(|action| {
            runner_action_target(action.action, holder.pos).map(|target| HoldSupportPassInput {
                score: action.score,
                target,
                layoff_support_value: action.layoff_support_value,
                short_combination_value: action.short_combination_value,
                second_line_cutback_value: action.second_line_cutback_value,
                layoff_retention_value: action.layoff_retention_value,
                receiver_goal_fit: action.receiver_goal_fit,
                second_line_arrival_value: action.second_line_arrival_value,
            })
        })
        .collect();
    let hold_carries: Vec<HoldSupportCarryInput> = actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Carry { .. }))
        .map(|action| HoldSupportCarryInput {
            carry_to_shoot_window: action.carry_to_shoot_window,
            wide_second_line_carry_window: action.wide_second_line_carry_window,
            future_shot_gain: action.future_shot_gain,
        })
        .collect();
    let hold_candidates: Vec<HoldSupportHoldInput> = actions
        .iter()
        .filter(|action| matches!(action.action, RunnerHeldAction::Hold { .. }))
        .map(|action| HoldSupportHoldInput {
            opportunity_wait: action.opportunity_wait,
            opportunity_wait_value: action.opportunity_wait_value,
            no_clear_release: action.no_clear_release,
        })
        .collect();
    let hold_support = select_hold_support(&HoldSupportSelectionInput {
        player_pos: holder.pos,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        passes: &hold_passes,
        carries: &hold_carries,
        holds: &hold_candidates,
        current_opportunity_goal: holder.goal_type.as_deref() == Some("hold_for_opportunity"),
    });
    if hold_support.has_support {
        let current_hold_goal_age = if holder.goal_type.as_deref() == Some("hold_for_opportunity") {
            (tick - holder.goal_created_tick).max(0)
        } else {
            0
        };
        let hold_goal = evaluate_hold_opportunity_goal(&HoldOpportunityGoalInput {
            player_pos: holder.pos,
            support_target: hold_support.target,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            support_value: hold_support.support_value,
            hold_value: hold_support.hold_support,
            current_shot: shot.map(|action| action.xg).unwrap_or(0.0),
            shot_readiness: shot
                .map(|action| {
                    action
                        .shot_readiness
                        .max(action.open_medium_window)
                        .max(action.clean_second_line_shot)
                })
                .unwrap_or(0.0),
            immediate_best_score: actions
                .iter()
                .map(|action| action.score)
                .fold(0.0, f64::max),
            goal_age_ticks: current_hold_goal_age,
        });
        if hold_goal.has_goal {
            goals.push(RunnerSpecializedGoal {
                goal_type: "hold_for_opportunity",
                phase: "scan",
                target: hold_goal.target_pos,
                value: hold_goal.value,
                created_tick: if holder.goal_type.as_deref() == Some("hold_for_opportunity") {
                    holder.goal_created_tick
                } else {
                    tick
                },
                action_code: 3,
            });
        }
    }
    let context = GoalSwitchCostInput {
        base: 0.035,
        context_stability: 1.0,
        role_discipline: 1.0,
        pressure_interrupt: 0.0,
        iq: holder.iq,
    };
    let goal_trace_candidates: Vec<serde_json::Value> = goals
        .iter()
        .map(|goal| {
            json!({
                "goal_type": goal.goal_type,
                "phase": goal.phase,
                "target": [goal.target.0, goal.target.1],
                "value": goal.value,
                "action_code": goal.action_code
            })
        })
        .collect();
    let candidate_values: Vec<f64> = goals.iter().map(|goal| goal.value).collect();
    let candidate_gaussians = runner_goal_gaussians(
        rng,
        candidate_values.len(),
        &context,
        config.goal_noise_scale,
    );
    let candidate_choice = select_goal_candidate_with_gaussians(
        &candidate_values,
        &candidate_gaussians,
        &context,
        config.goal_noise_scale,
    );
    let Some(goal) = candidate_choice
        .as_ref()
        .and_then(|choice| goals.get(choice.index))
        .cloned()
    else {
        let Some(current_goal_type) = holder.goal_type.clone() else {
            return false;
        };
        if !is_runner_on_ball_specialized_goal(current_goal_type.as_str()) {
            clear_player_goal(holder);
            return false;
        }
        let current_phase = holder.goal_phase.clone().unwrap_or_default();
        let current_target = holder.goal_target;
        let current_value = holder.goal_value;
        let current_action_code = holder.goal_action_code;
        let current_storage = GoalInput {
            goal_type: current_goal_type.as_str(),
            value: current_value,
            phase: Some(current_phase.as_str()),
        };
        let selection = select_runner_goal_with_noise(
            Some(&current_storage),
            &current_storage,
            &context,
            config.goal_noise_scale,
            rng,
        );
        apply_runner_specialized_selected_goal_bias(
            actions,
            holder,
            current_goal_type.as_str(),
            current_phase.as_str(),
            current_target,
            current_value,
            holder.goal_created_tick,
            current_action_code,
        );
        state.pending_on_ball_goal_event = Some(json!({
            "type": "event",
            "event": "on_ball_goal",
            "goal_type": current_goal_type,
            "phase": current_phase,
            "target": [round_one(current_target.0), round_one(current_target.1)],
            "value": round_two(current_value),
            "action_code": current_action_code,
            "switched": selection.switched,
            "reason": selection.reason,
            "candidate_count": goal_trace_candidates.len(),
            "candidates": goal_trace_candidates,
            "cut_candidate": cut_candidate_trace
        }));
        return true;
    };
    let current_storage = holder.goal_type.as_deref().map(|goal_type| GoalInput {
        goal_type,
        value: holder.goal_value,
        phase: holder.goal_phase.as_deref(),
    });
    let candidate_goal = GoalInput {
        goal_type: goal.goal_type,
        value: goal.value,
        phase: Some(goal.phase),
    };
    let selection = select_runner_goal_with_noise(
        current_storage.as_ref(),
        &candidate_goal,
        &context,
        config.goal_noise_scale,
        rng,
    );
    let selected_is_candidate = selection.selected == "candidate";
    let selected_goal_type = if selected_is_candidate {
        goal.goal_type.to_string()
    } else {
        holder
            .goal_type
            .clone()
            .unwrap_or_else(|| goal.goal_type.to_string())
    };
    let selected_phase = if selected_is_candidate {
        goal.phase.to_string()
    } else {
        holder
            .goal_phase
            .clone()
            .unwrap_or_else(|| goal.phase.to_string())
    };
    let selected_target = if selected_is_candidate {
        goal.target
    } else {
        holder.goal_target
    };
    let selected_value = if selected_is_candidate {
        goal.value
    } else {
        holder.goal_value
    };
    let selected_action_code = if selected_is_candidate {
        goal.action_code
    } else {
        holder.goal_action_code
    };
    let selected_created_tick = if selected_is_candidate {
        goal.created_tick
    } else {
        holder.goal_created_tick
    };
    apply_runner_specialized_selected_goal_bias(
        actions,
        holder,
        selected_goal_type.as_str(),
        selected_phase.as_str(),
        selected_target,
        selected_value,
        selected_created_tick,
        selected_action_code,
    );
    state.pending_on_ball_goal_event = Some(json!({
        "type": "event",
        "event": "on_ball_goal",
        "goal_type": selected_goal_type,
        "phase": selected_phase,
        "target": [round_one(selected_target.0), round_one(selected_target.1)],
        "value": round_two(selected_value),
        "action_code": selected_action_code,
        "switched": selection.switched,
        "reason": selection.reason,
        "candidate_count": goal_trace_candidates.len(),
        "candidates": goal_trace_candidates,
        "cut_candidate": cut_candidate_trace,
        "candidate_choice": candidate_choice.as_ref().map(|choice| json!({
            "index": choice.index,
            "candidate_noise": choice.candidate_noise,
            "noisy_value": choice.noisy_value
        }))
    }));
    true
}

fn choose_default_held_action(
    holder_idx: usize,
    holder: &mut RunnerPlayer,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    holder_home: bool,
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    state: &mut RunnerMatchState,
    tick: i32,
    rng: &mut RunnerRng,
) -> RunnerHeldAction {
    let attacking_right = attacking_right_for(holder_home, home_attacking_right);
    let current_state_value = runner_state_value(
        holder_idx,
        holder,
        holder_home,
        teammates,
        opponents,
        attacking_right,
        tick,
        &state.shot_quality_cache,
        config,
    );
    if holder.position == "GK" {
        return choose_gk_held_action(
            holder_idx,
            holder,
            teammates,
            opponents,
            holder_home,
            attacking_right,
            current_state_value,
            config,
            state,
            tick,
            rng,
        );
    }
    let mut actions = build_carry_candidates(
        holder_idx,
        holder,
        holder_home,
        teammates,
        opponents,
        current_state_value,
        attacking_right,
        tick,
        &state.shot_quality_cache,
        config,
    );
    let pass_actions = build_pass_candidates(
        holder_idx,
        holder,
        holder_home,
        teammates,
        opponents,
        current_state_value,
        attacking_right,
        tick,
        &state.shot_quality_cache,
        config,
    );
    apply_runner_support_opportunity_cost(&mut actions, &pass_actions);
    actions.extend(pass_actions);
    let shot = build_shot_candidate(
        holder_idx,
        holder,
        holder_home,
        teammates,
        opponents,
        current_state_value,
        attacking_right,
        tick,
        &state.shot_quality_cache,
        config,
    );
    let shot_score = shot.as_ref().map(|action| action.score).unwrap_or(0.0);
    if let Some(shot) = shot {
        actions.push(shot);
    }
    let clear_score = score_clear_candidate(holder, opponents, attacking_right, config);
    let release_best = actions
        .iter()
        .map(|action| action.score)
        .fold(clear_score, f64::max);
    if let Some(hold) = build_hold_candidate(
        holder_idx,
        holder,
        teammates,
        opponents,
        release_best,
        shot_score,
        attacking_right,
        config,
    ) {
        actions.push(hold);
    }
    if let Some(clear) = build_clear_candidate(holder, opponents, attacking_right, config, rng) {
        actions.push(clear);
    }
    if config.trace_detail == "full" {
        let best_score = |items: &[RunnerEvaluatedAction]| -> f64 {
            items.iter().map(|action| action.score).fold(0.0, f64::max)
        };
        let best_score_for = |code: u8| -> f64 {
            actions
                .iter()
                .filter(|action| runner_action_code(action.action) == code)
                .map(|action| action.score)
                .fold(0.0, f64::max)
        };
        state.trace_entries.push(json!({
            "tick": tick,
            "type": "event",
            "event": "on_ball_candidate_counts",
            "team": if holder_home { "home" } else { "away" },
            "player_idx": holder_idx,
            "player": holder.name,
            "player_pos": [holder.pos.0, holder.pos.1],
            "holder_state": {
                "idx": holder_idx,
                "pos": [holder.pos.0, holder.pos.1],
                "target_pos": [holder.target_pos.0, holder.target_pos.1],
                "tactical_anchor": [holder.tactical_anchor.0, holder.tactical_anchor.1],
                "base_pos": [holder.base_pos.0, holder.base_pos.1],
                "position": holder.position,
                "speed": holder.speed,
                "finishing": holder.finishing,
                "long_shot": holder.long_shot,
                "short_passing": holder.short_passing,
                "long_passing": holder.long_passing,
                "hold_ticks": holder.hold_ticks,
                "possession_ticks": holder.possession_ticks,
                "consecutive_carries": holder.consecutive_carries,
                "facing_direction": holder.facing_direction,
                "iq": holder.iq,
            },
            "opponents_state": opponents
                .iter()
                .enumerate()
                .map(|(idx, opponent)| json!({
                    "idx": idx,
                    "pos": [opponent.pos.0, opponent.pos.1],
                    "target_pos": [opponent.target_pos.0, opponent.target_pos.1],
                    "tactical_anchor": [opponent.tactical_anchor.0, opponent.tactical_anchor.1],
                    "base_pos": [opponent.base_pos.0, opponent.base_pos.1],
                    "position": opponent.position,
                    "speed": opponent.speed,
                }))
                .collect::<Vec<_>>(),
            "teammate_goals": teammates
                .iter()
                .enumerate()
                .filter(|(idx, _)| *idx != holder_idx)
                .map(|(idx, teammate)| json!({
                    "idx": idx,
                    "pos": [teammate.pos.0, teammate.pos.1],
                    "target_pos": [teammate.target_pos.0, teammate.target_pos.1],
                    "tactical_anchor": [teammate.tactical_anchor.0, teammate.tactical_anchor.1],
                    "base_pos": [teammate.base_pos.0, teammate.base_pos.1],
                    "position": teammate.position,
                    "speed": teammate.speed,
                    "finishing": teammate.finishing,
                    "long_shot": teammate.long_shot,
                    "goal_type": teammate.goal_type,
                    "goal_target": [teammate.goal_target.0, teammate.goal_target.1],
                    "goal_value": teammate.goal_value,
                }))
                .collect::<Vec<_>>(),
            "carry_count": actions.iter().filter(|action| matches!(action.action, RunnerHeldAction::Carry { .. })).count(),
            "pass_count": actions.iter().filter(|action| matches!(action.action, RunnerHeldAction::Pass { .. })).count(),
            "shot_count": actions.iter().filter(|action| matches!(action.action, RunnerHeldAction::Shoot { .. })).count(),
            "hold_count": actions.iter().filter(|action| matches!(action.action, RunnerHeldAction::Hold { .. })).count(),
            "clear_count": actions.iter().filter(|action| matches!(action.action, RunnerHeldAction::Clear { .. })).count(),
            "best_pass_score": best_score_for(1),
            "best_action_score": best_score(&actions),
            "current_state_value": current_state_value
        }));
    }
    if actions.is_empty() {
        return RunnerHeldAction::Hold {
            opportunity_target: None,
        };
    }
    let used_specialized_goal = apply_runner_specialized_goal_bias(
        state,
        holder_idx,
        holder,
        teammates,
        opponents,
        &mut actions,
        attacking_right,
        config,
        tick,
        rng,
    );
    let selection_candidates: Vec<OnBallSelectionCandidateInput> =
        actions.iter().map(runner_selection_candidate).collect();
    let noises = iq_score_noises(rng, actions.len(), holder.iq, config);
    let current_hold_goal = holder.goal_type.as_deref() == Some("hold_for_opportunity");
    let pre_generic_dry_selection = select_on_ball_candidate(&OnBallSelectionInput {
        candidates: &selection_candidates,
        current_goal_hold_for_opportunity: current_hold_goal,
        iq: holder.iq,
        score_noises: &noises,
        roll: 0.0,
        fallback_index: 0,
    });
    if !used_specialized_goal {
        let (pre_roll, pre_fallback_index) = consume_runner_on_ball_selection_random(
            rng,
            actions.len(),
            pre_generic_dry_selection.as_ref(),
        );
        let pre_selection = select_on_ball_candidate(&OnBallSelectionInput {
            candidates: &selection_candidates,
            current_goal_hold_for_opportunity: current_hold_goal,
            iq: holder.iq,
            score_noises: &noises,
            roll: pre_roll,
            fallback_index: pre_fallback_index,
        });
        if let Some(selection) = pre_selection.as_ref() {
            apply_selection_scores_to_actions(&mut actions, selection);
        }
        apply_runner_generic_goal_continuity(holder, &mut actions, config, rng);
    }
    let (selected_index, trace_actions) = if used_specialized_goal {
        let final_selection_candidates: Vec<OnBallSelectionCandidateInput> =
            actions.iter().map(runner_selection_candidate).collect();
        let final_current_hold_goal = holder.goal_type.as_deref() == Some("hold_for_opportunity");
        let dry_selection = select_on_ball_candidate(&OnBallSelectionInput {
            candidates: &final_selection_candidates,
            current_goal_hold_for_opportunity: final_current_hold_goal,
            iq: holder.iq,
            score_noises: &noises,
            roll: 0.0,
            fallback_index: 0,
        });
        let (roll, fallback_index) =
            consume_runner_on_ball_selection_random(rng, actions.len(), dry_selection.as_ref());
        let selection = select_on_ball_candidate(&OnBallSelectionInput {
            candidates: &final_selection_candidates,
            current_goal_hold_for_opportunity: final_current_hold_goal,
            iq: holder.iq,
            score_noises: &noises,
            roll,
            fallback_index,
        });
        let selected_index = selection
            .as_ref()
            .map(|value| value.index)
            .unwrap_or_else(|| {
                actions
                    .iter()
                    .enumerate()
                    .max_by(|(_, a), (_, b)| {
                        a.score
                            .partial_cmp(&b.score)
                            .unwrap_or(std::cmp::Ordering::Equal)
                    })
                    .map(|(idx, _)| idx)
                    .unwrap_or(0)
            });
        let mut trace_actions = actions.clone();
        if let Some(selection) = selection.as_ref() {
            for (action, score) in trace_actions.iter_mut().zip(selection.noisy_scores.iter()) {
                action.score = *score;
            }
        }
        (selected_index, trace_actions)
    } else {
        let scores: Vec<f64> = actions.iter().map(|action| action.score).collect();
        let (roll, fallback_index) =
            consume_runner_raw_softmax_selection_random(rng, &scores, holder.iq);
        let selected_index = raw_softmax_selection(&scores, holder.iq, roll, fallback_index).0;
        (selected_index, actions.clone())
    };
    let index = selected_index.min(actions.len() - 1);
    record_on_ball_decision_trace(
        state,
        tick,
        holder_home,
        holder_idx,
        holder.name.as_str(),
        holder.pos,
        &trace_actions,
        index,
        config,
    );
    actions[index].action
}

fn team_shape_players(players: &[RunnerPlayer]) -> Vec<TeamShapePlayerInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| TeamShapePlayerInput {
            index: idx,
            base_pos: player.base_pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect()
}

fn team_shape_opponents(players: &[RunnerPlayer]) -> Vec<TeamShapeOpponentInput> {
    players
        .iter()
        .map(|player| TeamShapeOpponentInput {
            pos: player.pos,
            is_goalkeeper: player.position == "GK",
        })
        .collect()
}

fn apply_team_shape_targets(
    players: &mut [RunnerPlayer],
    opponents: &[RunnerPlayer],
    ball_pos: (f64, f64),
    attacking_right: bool,
    phase: &str,
    intent: &str,
    holder_idx: Option<usize>,
    config: &RunnerRuntimeConfig,
) {
    let shape_players = team_shape_players(players);
    let shape_opponents = team_shape_opponents(opponents);
    let shape = team_shape_plan(&TeamShapePlanInput {
        ball_pos,
        attacking_right,
        phase,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        players: &shape_players,
        opponents: &shape_opponents,
    });
    for anchor in shape.anchors {
        if let Some(player) = players.get_mut(anchor.index) {
            player.tactical_anchor = anchor.tactical_anchor;
            if holder_idx == Some(anchor.index) {
                continue;
            }
            if player.target_pos == (0.0, 0.0) {
                player.target_pos = anchor.tactical_anchor;
                player.movement_intent = intent.to_string();
            }
        }
    }
}

fn runner_attack_teammates(players: &[RunnerPlayer]) -> Vec<OffBallTeammateInput> {
    players
        .iter()
        .enumerate()
        .map(|(idx, player)| OffBallTeammateInput {
            index: idx,
            pos: player.pos,
            target_pos: player.target_pos,
            tactical_anchor: player.tactical_anchor,
            is_goalkeeper: player.position == "GK",
        })
        .collect()
}

fn runner_defense_teammates(
    players: &[RunnerPlayer],
    exclude_idx: usize,
) -> Vec<DefenseTeammateInput> {
    players
        .iter()
        .enumerate()
        .filter(|(idx, player)| *idx != exclude_idx && player.position != "GK")
        .map(|(_, player)| DefenseTeammateInput {
            pos: player.pos,
            target_pos: player.target_pos,
        })
        .collect()
}

fn is_defender_position(position: &str) -> bool {
    matches!(position, "CB" | "LCB" | "RCB" | "LB" | "RB" | "LWB" | "RWB")
}

fn is_midfielder_position(position: &str) -> bool {
    matches!(
        position,
        "CM" | "LCM" | "RCM" | "CDM" | "LDM" | "RDM" | "CAM" | "RAM" | "LAM" | "LM" | "RM" | "AM"
    )
}

fn is_attacker_position(position: &str) -> bool {
    matches!(
        position,
        "ST" | "CF" | "LW" | "RW" | "LF" | "RF" | "LS" | "RS"
    )
}

fn is_wide_position(position: &str) -> bool {
    matches!(
        position,
        "LW" | "RW" | "LM" | "RM" | "LB" | "RB" | "LWB" | "RWB"
    )
}

fn apply_player_goal_switch_with_details(
    player: &mut RunnerPlayer,
    candidate_type: String,
    candidate_phase: &'static str,
    candidate_target: (f64, f64),
    candidate_value: f64,
    iq: f64,
    base: f64,
    pressure_interrupt: f64,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> RunnerGoalSwitchResult {
    let current_storage = player.goal_type.as_deref().map(|goal_type| GoalInput {
        goal_type,
        value: player.goal_value,
        phase: player.goal_phase.as_deref().or_else(|| {
            if goal_type.starts_with("defend_") {
                Some("defend")
            } else {
                None
            }
        }),
    });
    let candidate = GoalInput {
        goal_type: candidate_type.as_str(),
        value: candidate_value,
        phase: Some(candidate_phase),
    };
    let context = GoalSwitchCostInput {
        base,
        context_stability: 1.0,
        role_discipline: 1.0,
        pressure_interrupt,
        iq,
    };
    let selection = select_runner_goal_with_noise(
        current_storage.as_ref(),
        &candidate,
        &context,
        config.goal_noise_scale,
        rng,
    );
    if selection.selected == "candidate" {
        player.goal_type = Some(candidate_type);
        player.goal_phase = Some(candidate_phase.to_string());
        player.goal_target = candidate_target;
        player.goal_value = candidate_value.max(0.0);
        player.goal_action_code = 3;
    }
    RunnerGoalSwitchResult {
        summary: RunnerGoalSummary {
            goal_type: player.goal_type.clone().unwrap_or_default(),
            target: player.goal_target,
            value: player.goal_value,
        },
        switched: selection.switched,
        switch_cost: selection.switch_cost,
        value_advantage: selection.value_advantage,
        reason: selection.reason,
    }
}

fn apply_player_goal_switch(
    player: &mut RunnerPlayer,
    candidate_type: String,
    candidate_phase: &'static str,
    candidate_target: (f64, f64),
    candidate_value: f64,
    iq: f64,
    base: f64,
    pressure_interrupt: f64,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> RunnerGoalSummary {
    apply_player_goal_switch_with_details(
        player,
        candidate_type,
        candidate_phase,
        candidate_target,
        candidate_value,
        iq,
        base,
        pressure_interrupt,
        config,
        rng,
    )
    .summary
}

fn apply_arrival_goal_switch_with_details(
    player: &mut RunnerPlayer,
    candidate_type: &'static str,
    candidate_target: (f64, f64),
    candidate_value: f64,
    iq: f64,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> RunnerGoalSwitchResult {
    let current_storage = player.goal_type.as_deref().map(|goal_type| GoalInput {
        goal_type,
        value: player.goal_value,
        phase: player.goal_phase.as_deref().or_else(|| {
            if goal_type.starts_with("defend_") {
                Some("defend")
            } else {
                None
            }
        }),
    });
    let candidate = GoalInput {
        goal_type: candidate_type,
        value: candidate_value,
        phase: None,
    };
    let context = GoalSwitchCostInput {
        base: 0.035,
        context_stability: 1.0,
        role_discipline: 1.0,
        pressure_interrupt: 0.0,
        iq,
    };
    let selection = select_runner_goal_with_noise(
        current_storage.as_ref(),
        &candidate,
        &context,
        config.goal_noise_scale,
        rng,
    );
    if selection.selected == "candidate" {
        player.goal_type = Some(candidate_type.to_string());
        player.goal_phase = None;
        player.goal_target = candidate_target;
        player.goal_value = candidate_value.max(0.0);
        player.goal_action_code = 3;
    }
    RunnerGoalSwitchResult {
        summary: RunnerGoalSummary {
            goal_type: player.goal_type.clone().unwrap_or_default(),
            target: player.goal_target,
            value: player.goal_value,
        },
        switched: selection.switched,
        switch_cost: selection.switch_cost,
        value_advantage: selection.value_advantage,
        reason: selection.reason,
    }
}

fn off_ball_attack_movement_intent(
    player_pos: (f64, f64),
    anchor: (f64, f64),
    chosen_pos: (f64, f64),
    components: &crate::OffBallAttackChoiceComponents,
    current_goal: Option<crate::OffBallAttackGoalInput<'_>>,
    attacking_right: bool,
) -> &'static str {
    let forward_dir = if attacking_right { 1.0 } else { -1.0 };
    let move_progress = (chosen_pos.0 - player_pos.0) * forward_dir;
    let anchor_run = (anchor.0 - player_pos.0) * forward_dir;
    let support_urgency = components
        .second_line_support
        .max(components.inside_support * 0.72);
    let goal_arrival_urgency = current_goal
        .filter(|goal| {
            matches!(
                goal.goal_type,
                "arc_arrival_for_cutback" | "attack_far_post"
            )
        })
        .map(|goal| {
            let radius = if goal.goal_type == "arc_arrival_for_cutback" {
                14.0
            } else {
                18.0
            };
            (1.0 - distance(chosen_pos, goal.target_pos) / radius).max(0.0)
                * (goal.value * 4.0).clamp(0.0, 1.0)
        })
        .unwrap_or(0.0);
    if support_urgency > 0.10 || goal_arrival_urgency > 0.18 {
        "attack_run"
    } else if move_progress > 4.0 || anchor_run > 6.0 {
        "attack_run"
    } else if distance(chosen_pos, anchor) > 10.0 {
        "support"
    } else {
        "recover_shape"
    }
}

fn is_off_ball_attack_goal_type(goal_type: &str) -> bool {
    matches!(
        goal_type,
        "arc_arrival_for_cutback"
            | "attack_far_post"
            | "support_second_line"
            | "drop_between_lines"
            | "support_carrier"
            | "hold_width"
            | "run_behind"
            | "attack_box"
            | "recycle_support"
    )
}

fn attenuate_arrival_goal_for_teammate_occupancy(
    players: &[RunnerPlayer],
    player_idx: usize,
    goal_type: &'static str,
    target_pos: (f64, f64),
    value: f64,
) -> Option<f64> {
    if !matches!(goal_type, "arc_arrival_for_cutback" | "attack_far_post") {
        return Some(value);
    }
    let radius = if goal_type == "arc_arrival_for_cutback" {
        10.0
    } else {
        12.0
    };
    let mut redundancy = 0.0;
    for (teammate_idx, teammate) in players.iter().enumerate() {
        if teammate_idx == player_idx || teammate.goal_type.as_deref() != Some(goal_type) {
            continue;
        }
        let dist = distance(teammate.goal_target, target_pos);
        if dist < radius {
            let occupancy = (teammate.goal_value * 2.6).clamp(0.45, 1.0);
            redundancy += (1.0 - dist / radius) * occupancy;
        }
    }
    if redundancy <= 0.0 {
        return Some(value);
    }
    let pressure = if goal_type == "arc_arrival_for_cutback" {
        2.4
    } else {
        3.0
    };
    let adjusted_value = value / (1.0 + redundancy * pressure);
    let floor = if goal_type == "arc_arrival_for_cutback" {
        0.18
    } else {
        0.10
    };
    if adjusted_value < floor {
        None
    } else {
        Some(adjusted_value)
    }
}

fn apply_off_ball_attack_choices(
    players: &mut [RunnerPlayer],
    opponents: &[RunnerPlayer],
    state: &mut RunnerMatchState,
    tick: i32,
    team_home: bool,
    ball_pos: (f64, f64),
    attacking_right: bool,
    holder_idx: Option<usize>,
    active_indices: Option<&[bool]>,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> (i32, Option<RunnerGoalSummary>) {
    let mut selected_count = 0;
    let mut best_goal: Option<RunnerGoalSummary> = None;
    let opponent_xy = opponent_positions(opponents);
    let opponent_speeds: Vec<f64> = opponents
        .iter()
        .filter(|player| player.position != "GK")
        .map(|player| {
            player_speed(
                player.speed.round() as i32,
                config.player_max_speed,
                config.player_min_speed,
            )
        })
        .collect();
    let offside = offside_line(opponents, attacking_right, config);
    for idx in 0..players.len() {
        if holder_idx == Some(idx) {
            continue;
        }
        if active_indices
            .and_then(|indices| indices.get(idx))
            .map(|active| !*active)
            .unwrap_or(false)
        {
            continue;
        }
        if players[idx].position == "GK" {
            let anchor = players[idx].tactical_anchor;
            if let Some(player) = players.get_mut(idx) {
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: player.target_pos,
                    requested_target: anchor,
                    current_intent: player.movement_intent.as_str(),
                    requested_intent: Some("recover_shape"),
                });
                player.target_pos = movement_target.target_pos;
                player.movement_intent = movement_target.movement_intent;
            }
            continue;
        }
        let stale_goal = players[idx]
            .goal_type
            .as_deref()
            .map(|goal_type| !is_off_ball_attack_goal_type(goal_type))
            .unwrap_or(false);
        if stale_goal {
            players[idx].goal_type = None;
            players[idx].goal_phase = None;
            players[idx].goal_value = 0.0;
            players[idx].goal_action_code = 0;
        }
        let player = players[idx].clone();
        push_rng_trace_for_player(
            state,
            tick,
            format!("before_attack:{idx}").as_str(),
            player.name.as_str(),
            rng,
        );
        let teammate_xy: Vec<(f64, f64)> = players
            .iter()
            .enumerate()
            .filter(|(teammate_idx, _)| *teammate_idx != idx)
            .map(|(_, teammate)| teammate.pos)
            .collect();
        let teammates = runner_attack_teammates(players);
        let mut candidates = Vec::new();
        let mut goal_trace_json: Option<serde_json::Value> = None;
        let mut active_goal_type = players[idx].goal_type.clone();
        let mut active_goal_target = players[idx].goal_target;
        let mut active_goal_value = players[idx].goal_value;
        let anchor_samples = random_attack_samples(rng, 8);
        candidates.extend(crate::generate_off_ball_attack_anchor_candidates(
            &OffBallRawGenerationInput {
                anchor: player.tactical_anchor,
                ball_pos,
                attacking_right,
                pitch_width: config.pitch_width,
                pitch_length: config.pitch_length,
                is_defender: is_defender_position(player.position.as_str()),
                has_ball_carrier: holder_idx.is_some(),
                anchor_samples: &anchor_samples,
                support_samples: &[],
            },
        ));

        if holder_idx.is_some() {
            let arc_goal = evaluate_arc_arrival_goal(&ArcArrivalGoalInput {
                player_pos: player.pos,
                anchor_pos: player.tactical_anchor,
                ball_pos,
                base_pos: player.base_pos,
                attacking_right,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            });
            let far_goal = evaluate_attack_far_post_goal(&AttackFarPostGoalInput {
                player_pos: player.pos,
                anchor_pos: player.tactical_anchor,
                ball_pos,
                attacking_right,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
                goal_width: config.goal_width,
            });
            let mut arrival_goals = Vec::new();
            if arc_goal.has_goal {
                if let Some(value) = attenuate_arrival_goal_for_teammate_occupancy(
                    players,
                    idx,
                    "arc_arrival_for_cutback",
                    arc_goal.target_pos,
                    arc_goal.value,
                ) {
                    arrival_goals.push(("arc_arrival_for_cutback", arc_goal.target_pos, value));
                }
            }
            if far_goal.has_goal {
                if let Some(value) = attenuate_arrival_goal_for_teammate_occupancy(
                    players,
                    idx,
                    "attack_far_post",
                    far_goal.target_pos,
                    far_goal.value,
                ) {
                    arrival_goals.push(("attack_far_post", far_goal.target_pos, value));
                }
            }
            let arrival_context = GoalSwitchCostInput {
                base: 0.035,
                context_stability: 1.0,
                role_discipline: 1.0,
                pressure_interrupt: 0.0,
                iq: player.iq,
            };
            let arrival_values: Vec<f64> = arrival_goals.iter().map(|goal| goal.2).collect();
            let arrival_gaussians = runner_goal_gaussians(
                rng,
                arrival_values.len(),
                &arrival_context,
                config.goal_noise_scale,
            );
            let arrival_choice = select_goal_candidate_with_gaussians(
                &arrival_values,
                &arrival_gaussians,
                &arrival_context,
                config.goal_noise_scale,
            );
            if let Some((goal_type, target_pos, value)) = arrival_choice
                .as_ref()
                .and_then(|choice| arrival_goals.get(choice.index).copied())
            {
                if let Some(target_player) = players.get_mut(idx) {
                    let switch_result = apply_arrival_goal_switch_with_details(
                        target_player,
                        goal_type,
                        target_pos,
                        value,
                        player.iq,
                        config,
                        rng,
                    );
                    active_goal_type = target_player.goal_type.clone();
                    active_goal_target = target_player.goal_target;
                    active_goal_value = target_player.goal_value;
                    if matches!(
                        active_goal_type.as_deref(),
                        Some("arc_arrival_for_cutback" | "attack_far_post")
                    ) {
                        if crate::offside::is_offside_position(
                            active_goal_target,
                            attacking_right,
                            offside,
                            config.pitch_length,
                            Some(ball_pos.0),
                        ) {
                            let buffer = if active_goal_type.as_deref() == Some("attack_far_post") {
                                2.2
                            } else {
                                3.0
                            };
                            active_goal_target.0 = if attacking_right {
                                active_goal_target
                                    .0
                                    .min(offside - buffer)
                                    .min(config.pitch_length - 0.5)
                            } else {
                                active_goal_target.0.max(offside + buffer).max(0.5)
                            };
                            active_goal_target = pitch_clamp(
                                active_goal_target,
                                config.pitch_length,
                                config.pitch_width,
                            );
                            target_player.goal_target = active_goal_target;
                        }
                        candidates.push(crate::OffBallAttackCandidateInput {
                            pos: active_goal_target,
                            anchor_pos: active_goal_target,
                        });
                    }
                    goal_trace_json = Some(json!({
                        "goal": {
                            "goal_type": active_goal_type.clone().unwrap_or_default(),
                            "target_pos": [active_goal_target.0, active_goal_target.1],
                            "value": active_goal_value
                        },
                        "switched": switch_result.switched,
                        "switch_cost": switch_result.switch_cost,
                        "value_advantage": switch_result.value_advantage,
                        "reason": switch_result.reason,
                        "candidate_choice": {
                            "candidate_noise": arrival_choice.as_ref().map(|choice| choice.candidate_noise).unwrap_or(0.0),
                            "noisy_value": arrival_choice.as_ref().map(|choice| choice.noisy_value).unwrap_or(value)
                        },
                        "candidate": {
                            "goal_type": goal_type,
                            "target_pos": [target_pos.0, target_pos.1],
                            "value": value
                        }
                    }));
                }
            }

            let support_samples = random_attack_samples(rng, 5);
            candidates.extend(crate::generate_off_ball_attack_support_candidates(
                &OffBallRawGenerationInput {
                    anchor: player.tactical_anchor,
                    ball_pos,
                    attacking_right,
                    pitch_width: config.pitch_width,
                    pitch_length: config.pitch_length,
                    is_defender: is_defender_position(player.position.as_str()),
                    has_ball_carrier: true,
                    anchor_samples: &[],
                    support_samples: &support_samples,
                },
            ));
        }

        let current_goal = active_goal_type
            .as_deref()
            .filter(|goal_type| is_off_ball_attack_goal_type(goal_type))
            .map(|goal_type| crate::OffBallAttackGoalInput {
                goal_type,
                target_pos: active_goal_target,
                value: active_goal_value,
            });
        let noises = iq_score_noises(rng, candidates.len() + 1, player.iq, config);
        let mut stay_score = position_value(&PositionValueInput {
            x: player.pos.0,
            y: player.pos.1,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            attacking_right,
            opponent_positions: &opponent_xy,
            teammate_positions: &teammate_xy,
            runner_formation_pos: Some(player.tactical_anchor),
        });
        if crate::offside::is_offside_position(
            player.pos,
            attacking_right,
            offside,
            config.pitch_length,
            Some(ball_pos.0),
        ) {
            stay_score *= 0.15;
        }
        stay_score *= 0.18;
        let offball_debug_alternatives = if config.trace_detail == "full" {
            let scored = crate::score_off_ball_attack_candidates(&crate::OffBallAttackBatchInput {
                player_index: idx,
                player_pos: player.pos,
                player_speed: player.speed.round() as i32,
                anchor: player.tactical_anchor,
                ball_pos,
                attacking_right,
                offside_line: offside,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
                player_max_speed: config.player_max_speed,
                player_min_speed: config.player_min_speed,
                pass_to_space_ball_speed: config.pass_to_space_ball_speed,
                receive_reachability_scale: config.receive_reachability_scale,
                space_creation_radius: config.space_creation_radius,
                candidates: &candidates,
                opponent_positions: &opponent_xy,
                opponent_speeds: &opponent_speeds,
                teammate_positions: &teammate_xy,
                teammates: &teammates,
                current_goal,
            });
            let mut ranked = Vec::with_capacity(scored.len() + 1);
            ranked.push((
                stay_score * (1.0 + noises.first().copied().unwrap_or(0.0)),
                json!({
                    "phase": "off_ball_attack",
                    "action_type": "move",
                    "target": [player.pos.0, player.pos.1],
                    "value": {
                        "score": stay_score * (1.0 + noises.first().copied().unwrap_or(0.0)),
                        "base_score": stay_score,
                        "components": {"kind": "stay"}
                    }
                }),
            ));
            for (candidate_idx, value) in scored.iter().enumerate() {
                let score =
                    value.score * (1.0 + noises.get(candidate_idx + 1).copied().unwrap_or(0.0));
                ranked.push((
                    score,
                    json!({
                        "phase": "off_ball_attack",
                        "action_type": "move",
                        "target": [value.target.0, value.target.1],
                        "value": {
                            "score": score,
                            "base_score": value.score,
                            "components": {
                                "kind": "space",
                                "pv": value.pv,
                                "reach": value.reach,
                                "movement_reach": value.movement_reach,
                                "immediate_reach": value.immediate_reach,
                                "pass_feasibility": value.pass_feasibility,
                                "space_bonus": value.space_bonus,
                                "role_shape_factor": value.role_shape_factor,
                                "role_overlap_factor": value.role_overlap_factor,
                                "role_overlap": value.role_overlap,
                                "lane_factor": value.lane_factor,
                                "offside_penalty": value.offside_penalty,
                                "support_angle_value": value.support_angle_value,
                                "inside_support": value.inside_support,
                                "second_line_support": value.second_line_support,
                                "arrival_goal_fit": value.arrival_goal_fit,
                                "arrival_goal_multiplier": value.arrival_goal_multiplier,
                                "arrival_goal_bonus": value.arrival_goal_bonus,
                                "layoff_window": value.layoff_window,
                                "candidate_progress": value.candidate_progress,
                                "candidate_width": value.candidate_width,
                                "support_angle_dist": value.support_angle_dist,
                                "dist_to_ball": value.dist_to_ball
                            }
                        }
                    }),
                ));
            }
            ranked.sort_by(|(left, _), (right, _)| {
                right.partial_cmp(left).unwrap_or(std::cmp::Ordering::Equal)
            });
            Some(
                ranked
                    .into_iter()
                    .map(|(_, payload)| payload)
                    .collect::<Vec<_>>(),
            )
        } else {
            None
        };
        let choice_roll = preview_next_random(rng);
        if let Some(choice) = choose_off_ball_attack_target(&OffBallAttackChoiceInput {
            player_index: idx,
            player_pos: player.pos,
            player_speed: player.speed.round() as i32,
            anchor: player.tactical_anchor,
            ball_pos,
            attacking_right,
            offside_line: offside,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            player_max_speed: config.player_max_speed,
            player_min_speed: config.player_min_speed,
            pass_to_space_ball_speed: config.pass_to_space_ball_speed,
            receive_reachability_scale: config.receive_reachability_scale,
            space_creation_radius: config.space_creation_radius,
            iq: player.iq,
            stay_score,
            candidates: &candidates,
            opponent_positions: &opponent_xy,
            opponent_speeds: &opponent_speeds,
            teammate_positions: &teammate_xy,
            teammates: &teammates,
            current_goal,
            score_noises: &noises,
            roll: choice_roll,
        }) {
            if choice.used_roll {
                advance_randoms(rng, 1);
            }
            if choice.components.kind == 2 {
                if let Some(target_player) = players.get_mut(idx) {
                    let movement_target =
                        player_set_movement_target(&PlayerSetMovementTargetInput {
                            current_target: target_player.target_pos,
                            requested_target: player.tactical_anchor,
                            current_intent: target_player.movement_intent.as_str(),
                            requested_intent: Some("recover_shape"),
                        });
                    target_player.target_pos = movement_target.target_pos;
                    target_player.movement_intent = movement_target.movement_intent;
                }
            } else if let Some(target_player) = players.get_mut(idx) {
                let intent = off_ball_attack_movement_intent(
                    player.pos,
                    player.tactical_anchor,
                    choice.target,
                    &choice.components,
                    current_goal,
                    attacking_right,
                );
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: target_player.target_pos,
                    requested_target: choice.target,
                    current_intent: target_player.movement_intent.as_str(),
                    requested_intent: Some(intent),
                });
                target_player.target_pos = movement_target.target_pos;
                target_player.movement_intent = movement_target.movement_intent;
                let mut chosen_target = choice.target;
                let mut summary = RunnerGoalSummary {
                    goal_type: target_player.goal_type.clone().unwrap_or_default(),
                    target: target_player.goal_target,
                    value: target_player.goal_value,
                };
                if !matches!(
                    target_player.goal_type.as_deref(),
                    Some("arc_arrival_for_cutback" | "attack_far_post")
                ) {
                    let goal = build_off_ball_attack_goal(&OffBallAttackGoalBuildInput {
                        target_pos: choice.target,
                        value: choice.max_score,
                        second_line_support: choice.components.second_line_support,
                        inside_support: choice.components.inside_support,
                        support_angle_value: choice.components.support_angle_value,
                        layoff_window: choice.components.layoff_window,
                        candidate_progress: choice.components.candidate_progress,
                        candidate_width: choice.components.candidate_width,
                    });
                    let previous_target = target_player.target_pos;
                    let switch_result = apply_player_goal_switch_with_details(
                        target_player,
                        goal.goal_type.clone(),
                        "support",
                        goal.target_pos,
                        goal.value,
                        player.iq,
                        0.020,
                        0.0,
                        config,
                        rng,
                    );
                    if switch_result.reason == "current_goal_within_switch_cost" {
                        let goal_target = target_player.goal_target;
                        let retained_request = (
                            previous_target.0 * 0.55 + goal_target.0 * 0.45,
                            previous_target.1 * 0.55 + goal_target.1 * 0.45,
                        );
                        let retained_target =
                            player_set_movement_target(&PlayerSetMovementTargetInput {
                                current_target: previous_target,
                                requested_target: retained_request,
                                current_intent: target_player.movement_intent.as_str(),
                                requested_intent: Some(intent),
                            });
                        target_player.target_pos = retained_target.target_pos;
                        target_player.movement_intent = retained_target.movement_intent;
                        chosen_target = target_player.target_pos;
                    }
                    if target_player.goal_type.is_some() {
                        target_player.goal_target = target_player.target_pos;
                    }
                    summary = RunnerGoalSummary {
                        goal_type: target_player.goal_type.clone().unwrap_or_default(),
                        target: target_player.goal_target,
                        value: target_player.goal_value,
                    };
                    goal_trace_json = Some(json!({
                        "goal": {
                            "goal_type": summary.goal_type.clone(),
                            "target_pos": [summary.target.0, summary.target.1],
                            "value": summary.value
                        },
                        "switched": switch_result.switched,
                        "switch_cost": switch_result.switch_cost,
                        "value_advantage": switch_result.value_advantage,
                        "reason": switch_result.reason.clone(),
                        "candidate": {
                            "goal_type": goal.goal_type,
                            "target_pos": [goal.target_pos.0, goal.target_pos.1],
                            "value": goal.value
                        }
                    }));
                }
                if !summary.goal_type.is_empty()
                    && best_goal
                        .as_ref()
                        .map(|goal| summary.value > goal.value)
                        .unwrap_or(true)
                {
                    best_goal = Some(summary.clone());
                }
                if config.trace_detail == "full" {
                    state.trace_decisions.push(json!({
                        "tick": tick,
                        "team": if team_home { "home" } else { "away" },
                        "player_idx": idx,
                        "player": target_player.name.clone(),
                        "phase": "off_ball_attack",
                        "pos": [player.pos.0, player.pos.1],
                        "chosen": {
	                            "phase": "off_ball_attack",
	                            "action_type": "move",
	                            "target": [chosen_target.0, chosen_target.1],
	                            "value": {
                                "score": choice.max_score,
                                "selected_score": choice.score,
                                "stay_score": stay_score,
                                "candidate_count": choice.candidate_count,
                                "used_roll": choice.used_roll,
                                "roll": choice_roll,
                                "score_noises": noises,
                                "components": {
                                    "kind": choice.components.kind,
                                    "pv": choice.components.pv,
                                    "reach": choice.components.reach,
                                    "movement_reach": choice.components.movement_reach,
                                    "immediate_reach": choice.components.immediate_reach,
                                    "pass_feasibility": choice.components.pass_feasibility,
                                    "space_bonus": choice.components.space_bonus,
                                    "role_shape_factor": choice.components.role_shape_factor,
                                    "role_overlap_factor": choice.components.role_overlap_factor,
                                    "role_overlap": choice.components.role_overlap,
                                    "lane_factor": choice.components.lane_factor,
                                    "offside_penalty": choice.components.offside_penalty,
                                    "support_angle_value": choice.components.support_angle_value,
                                    "inside_support": choice.components.inside_support,
                                    "second_line_support": choice.components.second_line_support,
                                    "arrival_goal_fit": choice.components.arrival_goal_fit,
                                    "arrival_goal_multiplier": choice.components.arrival_goal_multiplier,
                                    "arrival_goal_bonus": choice.components.arrival_goal_bonus,
                                    "layoff_window": choice.components.layoff_window,
                                    "candidate_progress": choice.components.candidate_progress,
                                    "candidate_width": choice.components.candidate_width,
                                    "support_angle_dist": choice.components.support_angle_dist,
                                    "dist_to_ball": choice.components.dist_to_ball
                                }
                            }
                        },
                        "goal": goal_trace_json.clone().unwrap_or_else(|| json!({
                            "goal": {
                                "goal_type": summary.goal_type.clone(),
                                "target_pos": [summary.target.0, summary.target.1],
                                "value": summary.value
                            },
                            "switched": false,
                            "switch_cost": 0.0,
                            "value_advantage": 0.0,
                            "reason": "no_goal_update"
                        })),
                        "alternatives": offball_debug_alternatives.clone().unwrap_or_default()
                    }));
                }
                selected_count += 1;
            }
        }
        push_rng_trace_for_player(
            state,
            tick,
            format!("after_attack:{idx}").as_str(),
            player.name.as_str(),
            rng,
        );
    }
    (selected_count, best_goal)
}

fn apply_off_ball_defense_choices(
    defenders: &mut [RunnerPlayer],
    attackers: &[RunnerPlayer],
    ball_pos: (f64, f64),
    attacking_right: bool,
    carrier_pos: Option<(f64, f64)>,
    carrier_consecutive_carries: i32,
    active_indices: Option<&[bool]>,
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
    trace_decisions: &mut Vec<serde_json::Value>,
    tick: i32,
    defender_team_home: bool,
) -> (i32, Option<RunnerGoalSummary>, Vec<DefenderActionInput>) {
    let mut selected_count = 0;
    let mut best_goal: Option<RunnerGoalSummary> = None;
    let attacker_xy: Vec<(f64, f64)> = attackers
        .iter()
        .filter(|player| player.position != "GK")
        .map(|player| player.pos)
        .collect();
    for idx in 0..defenders.len() {
        if active_indices
            .and_then(|indices| indices.get(idx))
            .map(|active| !*active)
            .unwrap_or(false)
        {
            continue;
        }
        if defenders[idx].position == "GK" {
            let target = gk_position_adjust(&GkPositionAdjustInput {
                ball_pos,
                attacking_right,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            })
            .target;
            if let Some(player) = defenders.get_mut(idx) {
                player.target_pos = target;
            }
            continue;
        }
        let defender = defenders[idx].clone();
        let teammates = runner_defense_teammates(defenders, idx);
        let samples = random_defense_samples(rng, 3);
        let last_def_target = if defender.last_def_action.is_empty() {
            None
        } else {
            Some(defender.last_def_target)
        };
        let previous_goal_target = defender.goal_type.as_ref().and_then(|goal_type| {
            if goal_type.starts_with("defend_") {
                Some(defender.goal_target)
            } else {
                None
            }
        });
        let empty_score_noises: Vec<f64> = Vec::new();
        let empty_rolls: Vec<f64> = Vec::new();
        let empty_fallback_indices: Vec<usize> = Vec::new();
        let candidate_count = choose_defense_action(&DefenseChoiceInput {
            defender_pos: defender.pos,
            anchor: defender.tactical_anchor,
            base_ref: defender.base_pos,
            ball_pos,
            ball_carrier_pos: carrier_pos,
            ball_carrier_consecutive_carries: carrier_consecutive_carries,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            press_radius: config.press_radius,
            tackle_range: config.tackle_range,
            carrier_speed: config.carrier_speed,
            iq: defender.iq,
            last_def_target,
            previous_goal_target,
            attackers: &attacker_xy,
            teammates: &teammates,
            random_samples: &samples,
            score_noises: &empty_score_noises,
            roll_by_count: &empty_rolls,
            fallback_index_by_count: &empty_fallback_indices,
        })
        .map(|choice| choice.candidate_count)
        .unwrap_or(0);
        if candidate_count == 0 {
            continue;
        }
        let score_noises = iq_score_noises(rng, candidate_count, defender.iq, config);
        let branch_probe = choose_defense_action(&DefenseChoiceInput {
            defender_pos: defender.pos,
            anchor: defender.tactical_anchor,
            base_ref: defender.base_pos,
            ball_pos,
            ball_carrier_pos: carrier_pos,
            ball_carrier_consecutive_carries: carrier_consecutive_carries,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            press_radius: config.press_radius,
            tackle_range: config.tackle_range,
            carrier_speed: config.carrier_speed,
            iq: defender.iq,
            last_def_target,
            previous_goal_target,
            attackers: &attacker_xy,
            teammates: &teammates,
            random_samples: &samples,
            score_noises: &score_noises,
            roll_by_count: &empty_rolls,
            fallback_index_by_count: &empty_fallback_indices,
        });
        let mut roll_by_count = vec![0.0; candidate_count + 1];
        let mut fallback_index_by_count = vec![0; candidate_count + 1];
        if let Some(probe) = branch_probe.as_ref() {
            if probe.used_random_choice {
                fallback_index_by_count[candidate_count] = rng.randbelow(candidate_count);
            } else if probe.used_roll {
                roll_by_count[candidate_count] = rng.random();
            }
        }
        if let Some(choice) = choose_defense_action(&DefenseChoiceInput {
            defender_pos: defender.pos,
            anchor: defender.tactical_anchor,
            base_ref: defender.base_pos,
            ball_pos,
            ball_carrier_pos: carrier_pos,
            ball_carrier_consecutive_carries: carrier_consecutive_carries,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            press_radius: config.press_radius,
            tackle_range: config.tackle_range,
            carrier_speed: config.carrier_speed,
            iq: defender.iq,
            last_def_target,
            previous_goal_target,
            attackers: &attacker_xy,
            teammates: &teammates,
            random_samples: &samples,
            score_noises: &score_noises,
            roll_by_count: &roll_by_count,
            fallback_index_by_count: &fallback_index_by_count,
        }) {
            if let Some(target_defender) = defenders.get_mut(idx) {
                let smoothed_target = if target_defender.last_def_action.is_empty() {
                    choice.target
                } else {
                    (
                        target_defender.last_def_target.0 * 0.75 + choice.target.0 * 0.25,
                        target_defender.last_def_target.1 * 0.75 + choice.target.1 * 0.25,
                    )
                };
                let requested_intent = match choice.action_type {
                    "tackle" | "approach" => "press",
                    "mark_runner" => "mark",
                    "block_lane" => "block_lane",
                    _ => "defend_shape",
                };
                if choice.action_type == "approach" {
                    target_defender.state = "pressing".to_string();
                } else if target_defender.state == "pressing"
                    && !matches!(choice.action_type, "tackle" | "mark_runner" | "block_lane")
                {
                    target_defender.state = "off_ball".to_string();
                }
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: target_defender.target_pos,
                    requested_target: smoothed_target,
                    current_intent: target_defender.movement_intent.as_str(),
                    requested_intent: Some(requested_intent),
                });
                target_defender.target_pos = movement_target.target_pos;
                target_defender.movement_intent = movement_target.movement_intent;
                target_defender.last_def_target = target_defender.target_pos;
                target_defender.last_def_action = choice.action_type.to_string();
                let pressure = choice.pressure_responsibility;
                let threat = choice.shot_danger.max(choice.carrier_stale_threat);
                let goal = build_defensive_goal(&DefensiveGoalBuildInput {
                    action_type: choice.action_type,
                    target_pos: choice.target,
                    value: choice.score,
                    pressure,
                    threat,
                });
                let switch_result = apply_player_goal_switch_with_details(
                    target_defender,
                    goal.goal_type,
                    "defend",
                    target_defender.target_pos,
                    goal.value,
                    defender.iq,
                    0.022,
                    threat * 0.55,
                    config,
                    rng,
                );
                let summary = switch_result.summary;
                if matches!(config.trace_detail.as_str(), "top_candidates" | "full") {
                    trace_decisions.push(json!({
                        "tick": tick,
                        "team": if defender_team_home { "home" } else { "away" },
                        "player_idx": idx,
                        "player": defender.name,
                        "phase": "off_ball_defense",
                        "pos": [defender.pos.0, defender.pos.1],
                        "rng": {
                            "random_samples": samples.iter().map(|sample| json!([sample.angle_unit, sample.radius_unit])).collect::<Vec<_>>(),
                            "score_noises": score_noises,
                            "roll": roll_by_count.get(choice.candidate_count).copied().unwrap_or(0.0),
                            "fallback_index": fallback_index_by_count.get(choice.candidate_count).copied().unwrap_or(0),
                        },
                        "chosen": {
                            "phase": "off_ball_defense",
                            "action_type": choice.action_type,
                            "target": [target_defender.target_pos.0, target_defender.target_pos.1],
                            "raw_target": [choice.target.0, choice.target.1],
                            "smoothed_target": [smoothed_target.0, smoothed_target.1],
                            "value": {
                                "score": choice.score,
                                "candidate_count": choice.candidate_count,
                                "local_attackers_count": choice.local_attackers_count,
                                "dangerous_receivers_count": choice.dangerous_receivers_count,
                                "raw_targets": choice.raw_targets.iter().map(|target| json!([target.0, target.1])).collect::<Vec<_>>(),
                                "candidate_targets": choice.candidate_targets.iter().map(|target| json!([target.0, target.1])).collect::<Vec<_>>(),
                                "candidate_scores": choice.candidate_scores,
                                "used_roll": choice.used_roll,
                                "used_random_choice": choice.used_random_choice,
                                "debug_attackers": attacker_xy.iter().map(|target| json!([target.0, target.1])).collect::<Vec<_>>(),
                                "debug_teammates": teammates.iter().map(|target| json!([target.pos.0, target.pos.1, target.target_pos.0, target.target_pos.1])).collect::<Vec<_>>(),
                                "components": {
                                    "base_score": choice.base_score,
                                    "press_value": choice.press_value,
                                    "pressure_responsibility": choice.pressure_responsibility,
                                    "shot_danger": choice.shot_danger,
                                    "carrier_stale_threat": choice.carrier_stale_threat,
                                    "carrier_threat": choice.carrier_threat,
                                    "shot_lane_closure": choice.shot_lane_closure,
                                    "best_mark_value": choice.best_mark_value
                                }
                            }
                        },
                        "goal": {
                            "goal": {
                                "goal_type": summary.goal_type.clone(),
                                "target_pos": [summary.target.0, summary.target.1],
                                "value": summary.value,
                                "confidence": summary.value,
                                "created_tick": tick,
                                "last_updated_tick": tick,
                                "context": {
                                    "phase": "defend",
                                    "completion": "deny_space_or_recover_shape",
                                    "abort": "possession_or_threat_changed",
                                    "handoff": "defensive_space_value",
                                    "action": choice.action_type,
                                    "pressure": pressure,
                                    "threat": threat
                                }
                            },
                            "switched": switch_result.switched,
                            "switch_cost": switch_result.switch_cost,
                            "value_advantage": switch_result.value_advantage,
                            "switch_noise": 0.0,
                            "noisy_value_advantage": switch_result.value_advantage,
                            "reason": switch_result.reason
                        }
                    }));
                }
                if best_goal
                    .as_ref()
                    .map(|goal| summary.value > goal.value)
                    .unwrap_or(true)
                {
                    best_goal = Some(summary);
                }
                selected_count += 1;
            }
        }
    }
    let interaction_inputs = defender_phase1_inputs(defenders, config);
    (selected_count, best_goal, interaction_inputs)
}

fn update_held_tick_targets(
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    state: &mut RunnerMatchState,
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    tick: i32,
    rng: &mut RunnerRng,
) -> (i32, i32) {
    let home_phase = phase_name(state.home_phase_code);
    let away_phase = phase_name(state.away_phase_code);
    let (home_intent, away_intent) = match state.ball.holder_team_home {
        Some(true) => ("support", "defend_shape"),
        Some(false) => ("defend_shape", "support"),
        None => ("contest", "contest"),
    };
    apply_team_shape_targets(
        home,
        away,
        state.ball.position,
        home_attacking_right,
        home_phase,
        home_intent,
        if state.ball.holder_team_home == Some(true) {
            state.ball.holder_idx
        } else {
            None
        },
        config,
    );
    apply_team_shape_targets(
        away,
        home,
        state.ball.position,
        !home_attacking_right,
        away_phase,
        away_intent,
        if state.ball.holder_team_home == Some(false) {
            state.ball.holder_idx
        } else {
            None
        },
        config,
    );
    let mut attack_choices = 0;
    let mut attack_goal: Option<RunnerGoalSummary> = None;
    if state.ball.holder_team_home == Some(true) {
        let attack = apply_off_ball_attack_choices(
            home,
            away,
            state,
            tick,
            true,
            state.ball.position,
            home_attacking_right,
            state.ball.holder_idx,
            None,
            config,
            rng,
        );
        attack_choices += attack.0;
        attack_goal = attack.1;
    } else if state.ball.holder_team_home == Some(false) {
        let attack = apply_off_ball_attack_choices(
            away,
            home,
            state,
            tick,
            false,
            state.ball.position,
            !home_attacking_right,
            state.ball.holder_idx,
            None,
            config,
            rng,
        );
        attack_choices += attack.0;
        attack_goal = attack.1;
    }
    if let Some(goal) = attack_goal {
        state.trace_entries.push(json!({
            "type": "event",
            "event": "off_ball_goal",
            "tick": tick,
            "side": "attack",
            "goal_type": goal.goal_type,
            "target": [round_one(goal.target.0), round_one(goal.target.1)],
            "value": round_two(goal.value)
        }));
    }
    (attack_choices, 0)
}

fn update_held_tick_defense_targets(
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    state: &mut RunnerMatchState,
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    tick: i32,
    rng: &mut RunnerRng,
) -> (i32, Vec<DefenderActionInput>) {
    let carrier_pos = state.ball.holder_team_home.and_then(|holder_home| {
        state.ball.holder_idx.and_then(|idx| {
            if holder_home {
                home.get(idx).map(|player| player.pos)
            } else {
                away.get(idx).map(|player| player.pos)
            }
        })
    });
    let carrier_consecutive_carries = state
        .ball
        .holder_team_home
        .and_then(|holder_home| {
            state.ball.holder_idx.and_then(|idx| {
                if holder_home {
                    home.get(idx).map(|player| player.consecutive_carries)
                } else {
                    away.get(idx).map(|player| player.consecutive_carries)
                }
            })
        })
        .unwrap_or(0);
    let (defense_choices, defense_goal, defender_inputs) =
        if state.ball.holder_team_home == Some(true) {
            apply_off_ball_defense_choices(
                away,
                home,
                state.ball.position,
                !home_attacking_right,
                carrier_pos,
                carrier_consecutive_carries,
                None,
                config,
                rng,
                &mut state.trace_decisions,
                tick,
                false,
            )
        } else if state.ball.holder_team_home == Some(false) {
            apply_off_ball_defense_choices(
                home,
                away,
                state.ball.position,
                home_attacking_right,
                carrier_pos,
                carrier_consecutive_carries,
                None,
                config,
                rng,
                &mut state.trace_decisions,
                tick,
                true,
            )
        } else {
            (0, None, Vec::new())
        };
    if let Some(goal) = defense_goal {
        state.trace_entries.push(json!({
            "type": "event",
            "event": "off_ball_goal",
            "tick": tick,
            "side": "defense",
            "goal_type": goal.goal_type,
            "target": [round_one(goal.target.0), round_one(goal.target.1)],
            "value": round_two(goal.value)
        }));
    }
    (defense_choices, defender_inputs)
}

fn apply_held_tick_movement(
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    original_holder_home: bool,
    original_holder_idx: usize,
    config: &RunnerRuntimeConfig,
) {
    for (team_home, players) in [(true, home), (false, away)] {
        for (idx, player) in players.iter_mut().enumerate() {
            let is_holder = original_holder_home == team_home && original_holder_idx == idx;
            if is_holder {
                continue;
            }
            if player.state == "stunned" {
                tick_player_stun(player);
                continue;
            }
            let movement = player_move_tick(&PlayerMoveTickInput {
                pos: player.pos,
                target_pos: player.target_pos,
                velocity: player.velocity,
                speed_ability: player.speed.round() as i32,
                movement_intent: player.movement_intent.as_str(),
                state: player.state.as_str(),
                player_max_speed: config.player_max_speed,
                player_min_speed: config.player_min_speed,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            });
            player.pos = movement.pos;
            player.velocity = movement.velocity;
            if let Some(facing) = movement.facing_direction {
                player.facing_direction = facing;
            }
            player.distance_covered += movement.distance_covered;
        }
    }
}

fn adjust_defensive_pressure_targets_after_carry(
    defenders: &mut [RunnerPlayer],
    holder_pos: (f64, f64),
    holder_consecutive_carries: i32,
    holder_attacking_right: bool,
    defender_attacking_right: bool,
    holder_action_type: &str,
    config: &RunnerRuntimeConfig,
) {
    if !matches!(holder_action_type, "carry" | "hold") {
        return;
    }

    let holder_progress = if holder_attacking_right {
        holder_pos.0 / config.pitch_length
    } else {
        (config.pitch_length - holder_pos.0) / config.pitch_length
    };
    if holder_progress < 0.66 && holder_consecutive_carries < 2 && holder_action_type != "hold" {
        return;
    }

    let defender_indices: Vec<usize> = defenders
        .iter()
        .enumerate()
        .filter_map(|(idx, player)| {
            if player.position != "GK" && player.state != "stunned" {
                Some(idx)
            } else {
                None
            }
        })
        .collect();
    if defender_indices.is_empty() {
        return;
    }

    let nearest_dist = defender_indices
        .iter()
        .map(|idx| distance(defenders[*idx].pos, holder_pos))
        .fold(f64::INFINITY, f64::min);
    let close_count = defender_indices
        .iter()
        .filter(|idx| {
            distance(defenders[**idx].pos, holder_pos)
                < config.tackle_range.max(config.press_radius * 0.70)
        })
        .count();
    let centrality = 1.0
        - (holder_pos.1 - config.pitch_width / 2.0)
            .abs()
            .min(config.pitch_width / 2.0)
            / (config.pitch_width / 2.0);
    let stale_threat = ((holder_consecutive_carries - 1) as f64 / 3.0).clamp(0.0, 1.0)
        * ((holder_progress - 0.62) / 0.24).clamp(0.0, 1.0)
        * (0.55 + 0.45 * centrality.clamp(0.0, 1.0));
    if stale_threat <= 0.0 {
        return;
    }

    let goal_side = if defender_attacking_right { -1.0 } else { 1.0 };
    for idx in defender_indices {
        let Some(defender) = defenders.get_mut(idx) else {
            continue;
        };
        let d = distance(defender.pos, holder_pos);
        if d > config.press_radius * 1.25 {
            continue;
        }
        let target_d = distance(defender.target_pos, holder_pos);
        let distance_responsibility = (1.0 - (d - nearest_dist).max(0.0) / 11.0).clamp(0.0, 1.0);
        let crowd_factor = 1.0 / (1.0 + (close_count.saturating_sub(1)) as f64 * 0.45);
        let intent_factor = if defender.movement_intent == "press" {
            1.0
        } else if matches!(defender.movement_intent.as_str(), "block_lane" | "mark") {
            0.72
        } else {
            0.55
        };
        let adjust = stale_threat * distance_responsibility * crowd_factor * intent_factor;
        if adjust <= 0.08 {
            continue;
        }

        let contain_depth = 2.2 + 1.5 * stale_threat;
        let y_offset = (defender.pos.1 - holder_pos.1).clamp(-4.0, 4.0) * 0.35;
        let pressure_target = pitch_clamp(
            (
                holder_pos.0 + goal_side * contain_depth,
                holder_pos.1 + y_offset,
            ),
            config.pitch_length,
            config.pitch_width,
        );
        if distance(pressure_target, holder_pos) >= target_d {
            continue;
        }
        let blend = (0.18 + 0.42 * adjust).min(0.55);
        defender.target_pos = (
            defender.target_pos.0 * (1.0 - blend) + pressure_target.0 * blend,
            defender.target_pos.1 * (1.0 - blend) + pressure_target.1 * blend,
        );
        if matches!(
            defender.movement_intent.as_str(),
            "defend_shape" | "block_lane" | "mark"
        ) {
            defender.movement_intent = "press".to_string();
        }
    }
}

fn adjust_held_tick_defensive_pressure_after_carry(
    state: &RunnerMatchState,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    holder_home: bool,
    holder_idx: usize,
    holder_action_type: &str,
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
) {
    if !matches!(holder_action_type, "carry" | "hold") {
        return;
    }
    if state.ball.state != RunnerBallState::Held
        || state.ball.holder_team_home != Some(holder_home)
        || state.ball.holder_idx != Some(holder_idx)
    {
        return;
    }

    let holder_attacking_right = attacking_right_for(holder_home, home_attacking_right);
    let defender_attacking_right = !holder_attacking_right;
    if holder_home {
        let Some(holder) = home.get(holder_idx) else {
            return;
        };
        adjust_defensive_pressure_targets_after_carry(
            away,
            holder.pos,
            holder.consecutive_carries,
            holder_attacking_right,
            defender_attacking_right,
            holder_action_type,
            config,
        );
    } else {
        let Some(holder) = away.get(holder_idx) else {
            return;
        };
        adjust_defensive_pressure_targets_after_carry(
            home,
            holder.pos,
            holder.consecutive_carries,
            holder_attacking_right,
            defender_attacking_right,
            holder_action_type,
            config,
        );
    }
}

fn move_runner_player(player: &mut RunnerPlayer, config: &RunnerRuntimeConfig) {
    let movement = player_move_tick(&PlayerMoveTickInput {
        pos: player.pos,
        target_pos: player.target_pos,
        velocity: player.velocity,
        speed_ability: player.speed.round() as i32,
        movement_intent: player.movement_intent.as_str(),
        state: player.state.as_str(),
        player_max_speed: config.player_max_speed,
        player_min_speed: config.player_min_speed,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
    });
    player.pos = movement.pos;
    player.velocity = movement.velocity;
    if let Some(facing) = movement.facing_direction {
        player.facing_direction = facing;
    }
    player.distance_covered += movement.distance_covered;
}

fn move_contested_team(
    players: &mut [RunnerPlayer],
    opponents: &[RunnerPlayer],
    ball_pos: (f64, f64),
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) {
    apply_team_shape_targets(
        players,
        opponents,
        ball_pos,
        attacking_right,
        "contesting",
        "recover_shape",
        None,
        config,
    );
    let target_inputs = contested_target_players(players);
    let target_outputs = select_contested_targets(&ContestedTargetsInput {
        ball_pos,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        player_max_speed: config.player_max_speed,
        player_min_speed: config.player_min_speed,
        contested_race_radius: config.contested_race_radius,
        players: &target_inputs,
    });
    for output in target_outputs {
        if let Some(player) = players.get_mut(output.index) {
            if player.state == "stunned" {
                continue;
            }
            player.target_pos = output.target;
            player.movement_intent = if output.intent_code == 1 {
                "contest".to_string()
            } else {
                "recover_shape".to_string()
            };
        }
    }
    for player in players.iter_mut() {
        if player.state == "stunned" {
            continue;
        }
        move_runner_player(player, config);
    }
}

fn defender_actions_for_interaction(
    holder_pos: (f64, f64),
    action_target: (f64, f64),
    holder_action: &str,
    defenders: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
) -> Vec<DefenderActionInput> {
    let forced_lane_idx = if config.runner_force_defender_lane && holder_action == "pass" {
        defenders
            .iter()
            .enumerate()
            .filter(|(_, defender)| defender.position != "GK")
            .min_by(|(_, a), (_, b)| {
                distance(a.pos, action_target)
                    .partial_cmp(&distance(b.pos, action_target))
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .map(|(idx, _)| idx)
    } else {
        None
    };
    defenders
        .iter()
        .enumerate()
        .filter(|(_, defender)| defender.position != "GK")
        .map(|(idx, defender)| {
            let d_holder = distance(defender.pos, holder_pos);
            let d_target = distance(defender.pos, action_target);
            let action = if d_holder < config.tackle_range * 1.20 {
                "tackle"
            } else if holder_action == "pass" && d_target < config.interception_reach * 2.4 {
                "block_lane"
            } else if d_target < config.tackle_range * 1.75 || d_holder < 14.0 {
                "approach"
            } else {
                "block_lane"
            };
            let speed = player_speed(
                defender.speed.round() as i32,
                config.player_max_speed,
                config.player_min_speed,
            );
            let move_target = if holder_action == "pass" && action == "block_lane" {
                action_target
            } else {
                holder_pos
            };
            let new_pos = if forced_lane_idx == Some(idx) {
                (
                    holder_pos.0 * 0.52 + action_target.0 * 0.48,
                    holder_pos.1 * 0.52 + action_target.1 * 0.48,
                )
            } else if action == "block_lane" && d_target > config.interception_reach * 2.4 {
                defender.pos
            } else {
                crate::physics::move_toward(defender.pos, move_target, speed)
            };
            DefenderActionInput {
                index: idx,
                pos: defender.pos,
                new_pos: pitch_clamp(new_pos, config.pitch_length, config.pitch_width),
                action: action.to_string(),
                speed: defender.speed,
                defence: defender.defence,
                is_goalkeeper: defender.position == "GK",
            }
        })
        .collect()
}

fn defender_phase1_inputs(
    defenders: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
) -> Vec<DefenderActionInput> {
    defenders
        .iter()
        .enumerate()
        .map(|(idx, defender)| {
            let speed = player_move_speed(&PlayerMoveSpeedInput {
                pos: defender.pos,
                target_pos: defender.target_pos,
                speed_ability: defender.speed.round() as i32,
                movement_intent: defender.movement_intent.as_str(),
                state: defender.state.as_str(),
                player_max_speed: config.player_max_speed,
                player_min_speed: config.player_min_speed,
            })
            .speed;
            let new_pos = pitch_clamp(
                crate::physics::move_toward(defender.pos, defender.target_pos, speed),
                config.pitch_length,
                config.pitch_width,
            );
            DefenderActionInput {
                index: idx,
                pos: defender.pos,
                new_pos,
                action: if defender.last_def_action.is_empty() {
                    "hold_position".to_string()
                } else {
                    defender.last_def_action.clone()
                },
                speed: defender.speed,
                defence: defender.defence,
                is_goalkeeper: defender.position == "GK",
            }
        })
        .collect()
}

fn track_runner_pressures(
    tick: i32,
    defenders: &mut [RunnerPlayer],
    holder_pos: (f64, f64),
    holder_action: &str,
    defender_actions: &[DefenderActionInput],
    duel_detected: bool,
    interception_detected: bool,
    config: &RunnerRuntimeConfig,
) {
    let pressures = track_defensive_pressures(&DefensivePressureInput {
        holder_pos,
        holder_action,
        defenders: defender_actions,
        press_radius: config.press_radius,
        duel_detected,
        interception_detected,
    });
    for pressure in pressures {
        if let Some(defender) = defenders.get_mut(pressure.defender_index) {
            if tick - defender.last_pressure_tick < 3 {
                continue;
            }
            defender.last_pressure_tick = tick;
            defender.pressures += 1;
            if pressure.successful {
                defender.successful_pressures += 1;
            }
        }
    }
}

fn detect_runner_duel(
    holder_pos: (f64, f64),
    carry_target: (f64, f64),
    defenders: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
) -> Option<usize> {
    let defender_actions =
        defender_actions_for_interaction(holder_pos, carry_target, "carry", defenders, config);
    detect_duel(&DuelDetectionInput {
        holder_pos,
        holder_action: "carry",
        carry_target,
        defenders: &defender_actions,
        tackle_range: config.tackle_range,
    })
    .defender_index
}

fn resolve_runner_duel(
    state: &mut RunnerMatchState,
    tick: i32,
    holder_idx: usize,
    holder_home: bool,
    defender_idx: usize,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    rng: &mut RunnerRng,
) -> bool {
    push_rng_trace(state, tick, "before_duel_resolve", rng);
    let (holder_name, holder_pos, holder_dribbling) = if holder_home {
        home.get(holder_idx)
            .map(|player| (player.name.clone(), player.pos, player.dribbling))
            .unwrap_or_else(|| (String::new(), state.ball.position, 50.0))
    } else {
        away.get(holder_idx)
            .map(|player| (player.name.clone(), player.pos, player.dribbling))
            .unwrap_or_else(|| (String::new(), state.ball.position, 50.0))
    };
    let (defender_name, defender_tackling) = if holder_home {
        away.get(defender_idx)
            .map(|player| (player.name.clone(), player.tackling))
            .unwrap_or_else(|| (String::new(), 50.0))
    } else {
        home.get(defender_idx)
            .map(|player| (player.name.clone(), player.tackling))
            .unwrap_or_else(|| (String::new(), 50.0))
    };
    let attacker_uniform = rng.uniform(-12.0, 12.0);
    let defender_uniform = rng.uniform(-12.0, 12.0);
    let duel_diff = (defender_tackling + defender_uniform) - (holder_dribbling + attacker_uniform);
    let outcome_code = if duel_diff > 8.0 {
        1
    } else if duel_diff < -8.0 {
        0
    } else {
        2
    };
    let (loose_x_roll, loose_y_roll) = if outcome_code == 2 {
        (rng.random(), rng.random())
    } else {
        (0.5, 0.5)
    };
    push_rng_trace(state, tick, "after_duel_rolls", rng);
    let duel = duel_phase_plan(&DuelPhasePlanInput {
        holder_pos,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        attacker_dribbling: holder_dribbling,
        defender_tackling,
        attacker_uniform,
        defender_uniform,
        loose_x_roll,
        loose_y_roll,
    });
    match duel.outcome_code {
        0 => {
            if holder_home {
                if let Some(defender) = away.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                    apply_stun_to_player(defender, config);
                }
                if let Some(holder) = home.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.dribbles_completed += 1;
                }
            } else {
                if let Some(defender) = home.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                    apply_stun_to_player(defender, config);
                }
                if let Some(holder) = away.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.dribbles_completed += 1;
                }
            }
            state.ball.position = holder_pos;
            state.trace_entries.push(json!({
                "tick": tick,
                "type": "event",
                "event": "duel",
                "outcome": "attacker_wins",
                "winner": holder_name,
                "loser": defender_name,
                "rng": {
                    "attacker_uniform": attacker_uniform,
                    "defender_uniform": defender_uniform
                }
            }));
            true
        }
        1 => {
            if holder_home {
                if let Some(defender) = away.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                    defender.tackles_won += 1;
                }
                if let Some(holder) = home.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.dispossessed += 1;
                    holder.turnovers += 1;
                    holder.consecutive_carries = 0;
                }
                let defender_pos = away
                    .get(defender_idx)
                    .map(|player| player.pos)
                    .unwrap_or(holder_pos);
                give_ball_to_player(state, home, away, defender_idx, false, defender_pos, None);
            } else {
                if let Some(defender) = home.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                    defender.tackles_won += 1;
                }
                if let Some(holder) = away.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.dispossessed += 1;
                    holder.turnovers += 1;
                    holder.consecutive_carries = 0;
                }
                let defender_pos = home
                    .get(defender_idx)
                    .map(|player| player.pos)
                    .unwrap_or(holder_pos);
                give_ball_to_player(state, home, away, defender_idx, true, defender_pos, None);
            }
            state.trace_entries.push(json!({
                "tick": tick,
                "type": "event",
                "event": "tackle",
                "tackler": defender_name,
                "dispossessed": holder_name,
                "rng": {
                    "attacker_uniform": attacker_uniform,
                    "defender_uniform": defender_uniform
                }
            }));
            true
        }
        _ => {
            if holder_home {
                if let Some(defender) = away.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                }
                if let Some(holder) = home.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.consecutive_carries = 0;
                    holder.state = "off_ball".to_string();
                }
            } else {
                if let Some(defender) = home.get_mut(defender_idx) {
                    defender.tackles_attempted += 1;
                }
                if let Some(holder) = away.get_mut(holder_idx) {
                    holder.dribbles_attempted += 1;
                    holder.consecutive_carries = 0;
                    holder.state = "off_ball".to_string();
                }
            }
            set_contested_and_clear_goals(state, home, away, duel.loose_pos, (0.0, 0.0));
            state.trace_entries.push(json!({
                "tick": tick,
                "type": "event",
                "event": "duel",
                "outcome": "loose_ball",
                "holder": holder_name,
                "defender": defender_name,
                "rng": {
                    "attacker_uniform": attacker_uniform,
                    "defender_uniform": defender_uniform
                }
            }));
            true
        }
    }
}

fn apply_restart_shape(
    reason: &str,
    restart_team_home: bool,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    force: bool,
) -> (bool, (f64, f64)) {
    let restart_attacking_right = if restart_team_home {
        home_attacking_right
    } else {
        !home_attacking_right
    };
    let mut players = Vec::new();
    if restart_team_home {
        players.extend(restart_shape_players(
            home,
            0,
            true,
            home_attacking_right,
            restart_attacking_right,
        ));
        players.extend(restart_shape_players(
            away,
            1,
            false,
            !home_attacking_right,
            restart_attacking_right,
        ));
    } else {
        players.extend(restart_shape_players(
            away,
            1,
            true,
            !home_attacking_right,
            restart_attacking_right,
        ));
        players.extend(restart_shape_players(
            home,
            0,
            false,
            home_attacking_right,
            restart_attacking_right,
        ));
    }
    let shape = restart_shape_plan(&RestartShapePlanInput {
        reason,
        force,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        players: &players,
    });
    if !shape.has_shape {
        return (false, (0.0, 0.0));
    }
    for output in &shape.players {
        let team = if output.team_code == 0 {
            &mut *home
        } else {
            &mut *away
        };
        if let Some(player) = team.get_mut(output.index) {
            player.state = "off_ball".to_string();
            if force {
                player.target_pos = output.target;
                player.movement_intent = "recover_shape".to_string();
            } else {
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: player.target_pos,
                    requested_target: output.target,
                    current_intent: player.movement_intent.as_str(),
                    requested_intent: Some("recover_shape"),
                });
                player.target_pos = movement_target.target_pos;
                player.movement_intent = movement_target.movement_intent;
            }
            if output.snap {
                player.pos = output.target;
                player.velocity = (0.0, 0.0);
            } else {
                let movement = player_move_tick(&PlayerMoveTickInput {
                    pos: player.pos,
                    target_pos: player.target_pos,
                    velocity: player.velocity,
                    speed_ability: player.speed.round() as i32,
                    movement_intent: player.movement_intent.as_str(),
                    state: player.state.as_str(),
                    player_max_speed: config.player_max_speed,
                    player_min_speed: config.player_min_speed,
                    pitch_length: config.pitch_length,
                    pitch_width: config.pitch_width,
                });
                player.pos = movement.pos;
                player.velocity = movement.velocity;
                if let Some(facing) = movement.facing_direction {
                    player.facing_direction = facing;
                }
                player.distance_covered += movement.distance_covered;
            }
        }
    }
    (true, shape.ball_pos)
}

fn restart_dead_ball(
    state: &mut RunnerMatchState,
    tick: i32,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    rng: &mut RunnerRng,
) {
    let reason = state
        .dead_reason
        .clone()
        .unwrap_or_else(|| "kickoff".to_string());
    let restart_team_home = state.restart_team_home.unwrap_or(true);
    let restart_attacking_right = if restart_team_home {
        home_attacking_right
    } else {
        !home_attacking_right
    };
    let (has_shape, shape_ball_pos) = apply_restart_shape(
        reason.as_str(),
        restart_team_home,
        home,
        away,
        config,
        home_attacking_right,
        true,
    );
    if has_shape {
        state.ball.position = shape_ball_pos;
    }
    let restart_inputs = if restart_team_home {
        restart_players(home)
    } else {
        restart_players(away)
    };
    let corner_y_roll = if reason == "corner" {
        rng.random()
    } else {
        0.0
    };
    let restart = restart_play_plan(&RestartPlayPlanInput {
        reason: reason.as_str(),
        ball_pos: state.ball.position,
        restart_attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        corner_y_roll,
        players: &restart_inputs,
    });
    if let Some(receiver_idx) = restart.receiver_index {
        let team = if restart_team_home {
            &mut *home
        } else {
            &mut *away
        };
        if let Some(receiver) = team.get_mut(receiver_idx) {
            if restart.set_receiver_pos {
                receiver.pos = restart.ball_pos;
                receiver.target_pos = restart.ball_pos;
            }
            give_ball_to_player(
                state,
                home,
                away,
                receiver_idx,
                restart_team_home,
                restart.ball_pos,
                None,
            );
            state.dead_reason = None;
            state.restart_team_home = None;
            state.restart_ticks_remaining = 0;
            state.last_passer_team_home = None;
            state.last_passer_idx = -1;
            state.trace_entries.push(json!({
                "tick": tick,
                "type": "event",
                "event": "restart",
                "reason": reason,
                "team": if restart_team_home { "home" } else { "away" },
                "receiver_idx": receiver_idx
            }));
        }
    }
}

fn is_out_of_bounds(pos: (f64, f64), config: &RunnerRuntimeConfig) -> bool {
    pos.0 < 0.0 || pos.0 > config.pitch_length || pos.1 < 0.0 || pos.1 > config.pitch_width
}

fn flight_type_code(kind: RunnerFlightKind) -> u8 {
    match kind {
        RunnerFlightKind::Pass => 0,
        RunnerFlightKind::Clearance => 2,
        RunnerFlightKind::Shot => 3,
    }
}

fn handle_out_of_bounds_flight(
    state: &mut RunnerMatchState,
    tick: i32,
    flight: RunnerFlight,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
) {
    let (total_xg, logged_xg_sum) = if flight.kind == RunnerFlightKind::Shot {
        let shooter = if flight.passer_team_home {
            home.get(flight.passer_idx)
        } else {
            away.get(flight.passer_idx)
        };
        shooter
            .map(|player| (player.xg, shot_log_sum(player)))
            .unwrap_or((0.0, 0.0))
    } else {
        (0.0, 0.0)
    };
    let plan = out_of_bounds_plan(&OutOfBoundsPlanInput {
        out_x: flight.target.0,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        passer_team_home: flight.passer_team_home,
        flight_type_code: flight_type_code(flight.kind),
        origin: flight.origin,
        attacking_right: attacking_right_for(flight.passer_team_home, home_attacking_right),
        total_xg,
        logged_xg_sum,
        goal_kick_restart_ticks: config.goal_kick_restart_ticks,
        throw_in_restart_ticks: config.throw_in_restart_ticks,
    });
    if plan.has_shot_log {
        if flight.passer_team_home {
            if let Some(shooter) = home.get_mut(flight.passer_idx) {
                shooter.shot_log.push(shot_log_json(&plan.shot_log));
            }
        } else if let Some(shooter) = away.get_mut(flight.passer_idx) {
            shooter.shot_log.push(shot_log_json(&plan.shot_log));
        }
    }
    set_dead_ball_and_clear_goals(
        state,
        home,
        away,
        plan.reason.as_str(),
        plan.restart_team_home,
        plan.restart_ticks,
        flight.target,
    );
    state.trace_entries.push(json!({
        "tick": tick,
        "type": "event",
        "event": "out_of_bounds",
        "reason": plan.reason,
        "restart_team": if plan.restart_team_home { "home" } else { "away" },
        "restart_ticks": plan.restart_ticks
    }));
}

fn move_flight_players(
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    flight: RunnerFlight,
    state: &mut RunnerMatchState,
    tick: i32,
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    rng: &mut RunnerRng,
) {
    let target_pos = flight.target;
    let race_radius = config.contested_race_radius;
    if flight.passer_team_home {
        clear_team_goals(away);
        apply_team_shape_targets(
            home,
            away,
            target_pos,
            home_attacking_right,
            phase_name(state.home_phase_code),
            "recover_shape",
            None,
            config,
        );
        apply_team_shape_targets(
            away,
            home,
            target_pos,
            !home_attacking_right,
            phase_name(state.away_phase_code),
            "defend_shape",
            None,
            config,
        );
        for idx in 0..home.len() {
            if home[idx].state == "stunned" {
                tick_player_stun(&mut home[idx]);
                continue;
            }
            let dist_to_target = distance(home[idx].pos, target_pos);
            if idx != flight.passer_idx && dist_to_target < race_radius * 1.35 {
                let opponents = away.to_vec();
                let active = {
                    let mut indices = vec![false; home.len()];
                    indices[idx] = true;
                    indices
                };
                let _ = apply_off_ball_attack_choices(
                    home,
                    &opponents,
                    state,
                    tick,
                    true,
                    target_pos,
                    home_attacking_right,
                    None,
                    Some(&active),
                    config,
                    rng,
                );
            } else {
                let support_target = pitch_clamp(
                    (
                        home[idx].tactical_anchor.0 * 0.86 + target_pos.0 * 0.14,
                        home[idx].tactical_anchor.1 * 0.88 + target_pos.1 * 0.12,
                    ),
                    config.pitch_length,
                    config.pitch_width,
                );
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: home[idx].target_pos,
                    requested_target: support_target,
                    current_intent: home[idx].movement_intent.as_str(),
                    requested_intent: Some("recover_shape"),
                });
                home[idx].target_pos = movement_target.target_pos;
                home[idx].movement_intent = movement_target.movement_intent;
            }
            move_runner_player(&mut home[idx], config);
        }
        for idx in 0..away.len() {
            if away[idx].state == "stunned" {
                tick_player_stun(&mut away[idx]);
                continue;
            }
            if distance(away[idx].pos, target_pos) < race_radius * 1.25 {
                let attackers = home.to_vec();
                let active = {
                    let mut indices = vec![false; away.len()];
                    indices[idx] = true;
                    indices
                };
                let (_, _, _) = apply_off_ball_defense_choices(
                    away,
                    &attackers,
                    target_pos,
                    !home_attacking_right,
                    None,
                    0,
                    Some(&active),
                    config,
                    rng,
                    &mut state.trace_decisions,
                    tick,
                    false,
                );
            } else {
                let support_target = pitch_clamp(
                    (
                        away[idx].tactical_anchor.0 * 0.88 + target_pos.0 * 0.12,
                        away[idx].tactical_anchor.1 * 0.90 + target_pos.1 * 0.10,
                    ),
                    config.pitch_length,
                    config.pitch_width,
                );
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: away[idx].target_pos,
                    requested_target: support_target,
                    current_intent: away[idx].movement_intent.as_str(),
                    requested_intent: Some("defend_shape"),
                });
                away[idx].target_pos = movement_target.target_pos;
                away[idx].movement_intent = movement_target.movement_intent;
            }
            move_runner_player(&mut away[idx], config);
        }
    } else {
        clear_team_goals(home);
        apply_team_shape_targets(
            away,
            home,
            target_pos,
            !home_attacking_right,
            phase_name(state.away_phase_code),
            "recover_shape",
            None,
            config,
        );
        apply_team_shape_targets(
            home,
            away,
            target_pos,
            home_attacking_right,
            phase_name(state.home_phase_code),
            "defend_shape",
            None,
            config,
        );
        for idx in 0..away.len() {
            if away[idx].state == "stunned" {
                tick_player_stun(&mut away[idx]);
                continue;
            }
            let dist_to_target = distance(away[idx].pos, target_pos);
            if idx != flight.passer_idx && dist_to_target < race_radius * 1.35 {
                let opponents = home.to_vec();
                let active = {
                    let mut indices = vec![false; away.len()];
                    indices[idx] = true;
                    indices
                };
                let _ = apply_off_ball_attack_choices(
                    away,
                    &opponents,
                    state,
                    tick,
                    false,
                    target_pos,
                    !home_attacking_right,
                    None,
                    Some(&active),
                    config,
                    rng,
                );
            } else {
                let support_target = pitch_clamp(
                    (
                        away[idx].tactical_anchor.0 * 0.86 + target_pos.0 * 0.14,
                        away[idx].tactical_anchor.1 * 0.88 + target_pos.1 * 0.12,
                    ),
                    config.pitch_length,
                    config.pitch_width,
                );
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: away[idx].target_pos,
                    requested_target: support_target,
                    current_intent: away[idx].movement_intent.as_str(),
                    requested_intent: Some("recover_shape"),
                });
                away[idx].target_pos = movement_target.target_pos;
                away[idx].movement_intent = movement_target.movement_intent;
            }
            move_runner_player(&mut away[idx], config);
        }
        for idx in 0..home.len() {
            if home[idx].state == "stunned" {
                tick_player_stun(&mut home[idx]);
                continue;
            }
            if distance(home[idx].pos, target_pos) < race_radius * 1.25 {
                let attackers = away.to_vec();
                let active = {
                    let mut indices = vec![false; home.len()];
                    indices[idx] = true;
                    indices
                };
                let (_, _, _) = apply_off_ball_defense_choices(
                    home,
                    &attackers,
                    target_pos,
                    home_attacking_right,
                    None,
                    0,
                    Some(&active),
                    config,
                    rng,
                    &mut state.trace_decisions,
                    tick,
                    true,
                );
            } else {
                let support_target = pitch_clamp(
                    (
                        home[idx].tactical_anchor.0 * 0.88 + target_pos.0 * 0.12,
                        home[idx].tactical_anchor.1 * 0.90 + target_pos.1 * 0.10,
                    ),
                    config.pitch_length,
                    config.pitch_width,
                );
                let movement_target = player_set_movement_target(&PlayerSetMovementTargetInput {
                    current_target: home[idx].target_pos,
                    requested_target: support_target,
                    current_intent: home[idx].movement_intent.as_str(),
                    requested_intent: Some("defend_shape"),
                });
                home[idx].target_pos = movement_target.target_pos;
                home[idx].movement_intent = movement_target.movement_intent;
            }
            move_runner_player(&mut home[idx], config);
        }
    }
}

fn apply_kickoff(
    restart_side_home: bool,
    home_attacking_right: bool,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    pitch_length: f64,
    pitch_width: f64,
    state: Option<&mut RunnerMatchState>,
) -> (usize, &'static str, (f64, f64)) {
    let center = (pitch_length / 2.0, pitch_width / 2.0);
    let mut inputs = Vec::with_capacity(home.len() + away.len());
    for (idx, player) in home.iter().enumerate() {
        inputs.push(KickoffPlayerInput {
            index: idx,
            team_is_restart: restart_side_home,
            attacking_right: home_attacking_right,
            base_pos: player.base_pos,
            current_pos: player.pos,
            is_goalkeeper: player.position == "GK",
            position: player.position.as_str(),
        });
    }
    for (idx, player) in away.iter().enumerate() {
        inputs.push(KickoffPlayerInput {
            index: idx + 1000,
            team_is_restart: !restart_side_home,
            attacking_right: !home_attacking_right,
            base_pos: player.base_pos,
            current_pos: player.pos,
            is_goalkeeper: player.position == "GK",
            position: player.position.as_str(),
        });
    }
    let shape = kickoff_shape_targets(&KickoffShapeInput {
        pitch_length,
        pitch_width,
        players: &inputs,
    });
    for (idx, target) in shape.targets {
        if idx >= 1000 {
            if let Some(player) = away.get_mut(idx - 1000) {
                player.pos = target;
                player.target_pos = target;
                player.tactical_anchor = target;
            }
        } else if let Some(player) = home.get_mut(idx) {
            player.pos = target;
            player.target_pos = target;
            player.tactical_anchor = target;
        }
    }
    let kicker_external = shape
        .kicker_index
        .unwrap_or(if restart_side_home { 10 } else { 1010 });
    let (idx, team_home, team_name) = if kicker_external >= 1000 {
        (kicker_external - 1000, false, "away")
    } else {
        (kicker_external, true, "home")
    };
    if team_home {
        if let Some(player) = home.get_mut(idx) {
            player.pos = center;
            player.target_pos = center;
            player.tactical_anchor = center;
        }
    } else if let Some(player) = away.get_mut(idx) {
        player.pos = center;
        player.target_pos = center;
        player.tactical_anchor = center;
    }
    if let Some(state) = state {
        give_ball_to_player(state, home, away, idx, team_home, center, None);
    } else if team_home {
        if let Some(player) = home.get_mut(idx) {
            player.state = "on_ball".to_string();
            player.hold_ticks = 0;
            player.possession_ticks = 0;
            player.consecutive_carries = 0;
            player.last_receive_origin = player.pos;
            clear_player_goal(player);
        }
    } else if let Some(player) = away.get_mut(idx) {
        player.state = "on_ball".to_string();
        player.hold_ticks = 0;
        player.possession_ticks = 0;
        player.consecutive_carries = 0;
        player.last_receive_origin = player.pos;
        clear_player_goal(player);
    }
    (idx, team_name, center)
}

fn record_half_frames(
    frames: &mut Vec<serde_json::Value>,
    state: &mut RunnerMatchState,
    start_tick: i32,
    end_tick: i32,
    half: i32,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    rng: &mut RunnerRng,
) {
    let interval = config.frame_interval.max(1);
    for tick in start_tick..end_tick {
        tick_match(
            state,
            tick,
            half,
            home,
            away,
            config,
            home_attacking_right,
            rng,
        );
        frames.append(&mut state.pending_replay_frames);
        if (tick - start_tick) % interval == 0 {
            let pending_ball_flight = state
                .pending_ball_flight
                .take()
                .unwrap_or(serde_json::Value::Null);
            frames.push(frame(
                tick,
                config.tick_duration,
                half,
                home,
                away,
                state.ball.position,
                state.ball.holder_idx,
                state
                    .ball
                    .holder_team_home
                    .map(|home| if home { "home" } else { "away" }),
                (state.home_score, state.away_score),
                None,
                pending_ball_flight,
                None,
                None,
            ));
        }
        if tick % 10 == 0 {
            sample_player_positions(home);
            sample_player_positions(away);
        }
    }
}

fn possession_pct(home_ticks: i32, total_ticks: i32) -> f64 {
    if total_ticks <= 0 {
        50.0
    } else {
        round_one(home_ticks as f64 / total_ticks as f64 * 100.0)
    }
}

fn choose_held_action(
    holder_idx: usize,
    holder: &mut RunnerPlayer,
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    forced_action_override: Option<&str>,
    state: &mut RunnerMatchState,
    tick: i32,
    rng: &mut RunnerRng,
) -> RunnerHeldAction {
    let attacking_right = attacking_right_for(holder_home, home_attacking_right);
    let xg = shot_quality_at(&ShotQualityInput {
        x: holder.pos.0,
        y: holder.pos.1,
        finishing: holder.finishing / 100.0,
        long_shot: holder.long_shot / 100.0,
        opponents: &[],
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        attacking_right,
        shot_ideal_distance: config.shot_ideal_distance,
        shot_on_target_base: config.shot_on_target_base,
        gk_save_base: config.gk_save_base,
        cache: None,
        cache_key: None,
    });
    if let Some(action) = forced_action_override.or(config.runner_forced_action.as_deref()) {
        match action {
            "carry" => {
                return RunnerHeldAction::Carry {
                    target: carry_target(holder, attacking_right, config),
                }
            }
            "pass" => {
                if let Some(receiver_idx) =
                    choose_pass_receiver(holder_idx, holder, teammates, attacking_right)
                {
                    return RunnerHeldAction::Pass {
                        receiver_idx,
                        target: config
                            .runner_forced_pass_target
                            .unwrap_or(teammates[receiver_idx].pos),
                        is_long: false,
                        lane_risk: 0.0,
                    };
                }
            }
            "clear" => {
                return RunnerHeldAction::Clear {
                    target: config
                        .runner_forced_clear_target
                        .unwrap_or_else(|| clear_target(holder, attacking_right, config)),
                }
            }
            "hold" => {
                return RunnerHeldAction::Hold {
                    opportunity_target: None,
                }
            }
            "shot" => {
                let on_target_prob = (xg * 2.0).clamp(0.05, 0.78);
                return RunnerHeldAction::Shoot {
                    target: goal_target(attacking_right, config),
                    xg,
                    on_target_prob,
                };
            }
            _ => {}
        }
    }
    if config.runner_shot_threshold < 0.0 {
        let on_target_prob = (xg * 2.0).clamp(0.05, 0.78);
        return RunnerHeldAction::Shoot {
            target: goal_target(attacking_right, config),
            xg,
            on_target_prob,
        };
    }
    let selected = choose_default_held_action(
        holder_idx,
        holder,
        teammates,
        opponents,
        holder_home,
        config,
        home_attacking_right,
        state,
        tick,
        rng,
    );
    selected
}

fn tick_match(
    state: &mut RunnerMatchState,
    tick: i32,
    half: i32,
    home: &mut [RunnerPlayer],
    away: &mut [RunnerPlayer],
    config: &RunnerRuntimeConfig,
    home_attacking_right: bool,
    rng: &mut RunnerRng,
) {
    state.shot_quality_cache.borrow_mut().clear();
    let state_before = state.ball.state;
    push_rng_trace(state, tick, "tick_start", rng);
    if matches!(
        state.ball.state,
        RunnerBallState::Held | RunnerBallState::Contested
    ) {
        update_team_phases(state, config);
    }
    let mut held_attack_choices = 0;
    let mut held_defense_choices = 0;
    match state.ball.state {
        RunnerBallState::Held => {
            sync_goals_with_possession(home, away, state.ball.holder_team_home);
            tick_stunned_players(home);
            tick_stunned_players(away);
            if let (Some(holder_idx), Some(holder_home)) =
                (state.ball.holder_idx, state.ball.holder_team_home)
            {
                if holder_home {
                    if let Some(holder) = home.get_mut(holder_idx) {
                        holder.possession_ticks += 1;
                    }
                } else if let Some(holder) = away.get_mut(holder_idx) {
                    holder.possession_ticks += 1;
                }
                push_rng_trace(state, tick, "before_attack_targets", rng);
                let (attack_choices, _) = update_held_tick_targets(
                    home,
                    away,
                    state,
                    config,
                    home_attacking_right,
                    tick,
                    rng,
                );
                push_rng_trace(state, tick, "after_attack_targets", rng);
                held_attack_choices = attack_choices;
                let holder_snapshot = if holder_home {
                    home.get(holder_idx).cloned()
                } else {
                    away.get(holder_idx).cloned()
                };
                if let Some(holder_snapshot) = holder_snapshot {
                    let teammates_snapshot = if holder_home {
                        home.to_vec()
                    } else {
                        away.to_vec()
                    };
                    let opponents_snapshot = if holder_home {
                        away.to_vec()
                    } else {
                        home.to_vec()
                    };
                    let opponents = execution_opponents(&opponents_snapshot);
                    let attacking_right = attacking_right_for(holder_home, home_attacking_right);
                    let forced_action_override = config
                        .runner_forced_actions
                        .get(state.held_action_cursor)
                        .map(|value| value.as_str())
                        .filter(|value| !value.is_empty() && *value != "-");
                    state.held_action_cursor += 1;
                    push_rng_trace(state, tick, "before_holder_choice", rng);
                    let held_action = {
                        let holder = if holder_home {
                            home.get_mut(holder_idx)
                        } else {
                            away.get_mut(holder_idx)
                        };
                        let Some(holder) = holder else { return };
                        choose_held_action(
                            holder_idx,
                            holder,
                            holder_home,
                            &teammates_snapshot,
                            &opponents_snapshot,
                            config,
                            home_attacking_right,
                            forced_action_override,
                            state,
                            tick,
                            rng,
                        )
                    };
                    push_rng_trace(state, tick, "after_holder_choice", rng);
                    let (defense_choices, defender_phase1_inputs) = {
                        push_rng_trace(state, tick, "before_defense_targets", rng);
                        update_held_tick_defense_targets(
                            home,
                            away,
                            state,
                            config,
                            home_attacking_right,
                            tick,
                            rng,
                        )
                    };
                    push_rng_trace(state, tick, "after_defense_targets", rng);
                    held_defense_choices = defense_choices;
                    let holder_action_type = runner_action_name(held_action);
                    let mut duel_defender_idx: Option<usize> = None;
                    let mut interception_defender_idx: Option<usize> = None;
                    let mut interception_distance = 0.0;
                    match held_action {
                        RunnerHeldAction::Carry { target } => {
                            let duel = detect_duel(&DuelDetectionInput {
                                holder_pos: holder_snapshot.pos,
                                holder_action: "carry",
                                carry_target: target,
                                defenders: &defender_phase1_inputs,
                                tackle_range: config.tackle_range,
                            });
                            duel_defender_idx = duel.defender_index;
                        }
                        RunnerHeldAction::Pass { target, .. } => {
                            let interception = detect_interception(&InterceptionDetectionInput {
                                pass_origin: holder_snapshot.pos,
                                pass_target: target,
                                defenders: &defender_phase1_inputs,
                                interception_reach: config.interception_reach,
                            });
                            interception_defender_idx = interception.defender_index;
                            interception_distance = interception.distance;
                        }
                        RunnerHeldAction::Hold { .. }
                        | RunnerHeldAction::Clear { .. }
                        | RunnerHeldAction::Shoot { .. } => {}
                    }
                    if holder_home {
                        track_runner_pressures(
                            tick,
                            away,
                            holder_snapshot.pos,
                            holder_action_type,
                            &defender_phase1_inputs,
                            duel_defender_idx.is_some(),
                            interception_defender_idx.is_some(),
                            config,
                        );
                    } else {
                        track_runner_pressures(
                            tick,
                            home,
                            holder_snapshot.pos,
                            holder_action_type,
                            &defender_phase1_inputs,
                            duel_defender_idx.is_some(),
                            interception_defender_idx.is_some(),
                            config,
                        );
                    }
                    'held_action_dispatch: {
                        match held_action {
                            RunnerHeldAction::Hold { opportunity_target } => {
                                let holder = if holder_home {
                                    home.get_mut(holder_idx)
                                } else {
                                    away.get_mut(holder_idx)
                                };
                                let Some(holder) = holder else { return };
                                holder.hold_ticks += 1;
                                holder.holds += 1;
                                holder.consecutive_carries = 0;
                                let hold_error_roll = rng.random();
                                let hold = hold_phase_plan(&HoldPhasePlanInput {
                                    holder_pos: holder.pos,
                                    dribbling: holder.dribbling,
                                    attacking_right,
                                    pitch_length: config.pitch_length,
                                    pitch_width: config.pitch_width,
                                    carry_error_divisor: config.carry_error_divisor,
                                    opponents: &opponents,
                                    opportunity_target,
                                    error_roll: hold_error_roll,
                                    loose_x_roll: 0.5,
                                    loose_y_roll: 0.5,
                                });
                                if hold.is_error {
                                    holder.distance_covered += hold.distance_covered;
                                    holder.pos = hold.new_pos;
                                    holder.turnovers += 1;
                                    holder.state = "off_ball".to_string();
                                    let player_name = holder.name.clone();
                                    let loose_pos = pitch_clamp(
                                        (
                                            hold.new_pos.0 + rng.uniform(-2.0, 2.0),
                                            hold.new_pos.1 + rng.uniform(-2.0, 2.0),
                                        ),
                                        config.pitch_length,
                                        config.pitch_width,
                                    );
                                    let _ = holder;
                                    set_contested_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        loose_pos,
                                        (0.0, 0.0),
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "error",
                                        "error_type": "shield",
                                        "player": player_name
                                    }));
                                    break 'held_action_dispatch;
                                }
                                holder.distance_covered += hold.distance_covered;
                                holder.pos = hold.new_pos;
                                state.ball.position = hold.new_pos;
                                state.trace_entries.push(json!({
                                "tick": tick,
                                "type": "action",
                                "team": if holder_home { "home" } else { "away" },
                                "player": holder.name,
                                "action": "hold",
                                "hold_ticks": holder.hold_ticks,
                                "pos": [round_one(holder.pos.0), round_one(holder.pos.1)],
                                "opportunity_target": opportunity_target.map(|target| json!([target.0, target.1])).unwrap_or(serde_json::Value::Null),
                                "pressure": hold.trace_pressure,
                                "nearest_def": hold.trace_nearest_dist.map(|value| json!(value)).unwrap_or(serde_json::Value::Null)
                            }));
                            }
                            RunnerHeldAction::Carry { target } => 'carry_action: {
                                if let Some(defender_idx) = duel_defender_idx {
                                    let consumed = resolve_runner_duel(
                                        state,
                                        tick,
                                        holder_idx,
                                        holder_home,
                                        defender_idx,
                                        home,
                                        away,
                                        config,
                                        rng,
                                    );
                                    if consumed {
                                        break 'carry_action;
                                    }
                                }
                                let holder = if holder_home {
                                    home.get_mut(holder_idx)
                                } else {
                                    away.get_mut(holder_idx)
                                };
                                let Some(holder) = holder else { return };
                                holder.carries_attempted += 1;
                                holder.hold_ticks = 0;
                                let old_pos = holder.pos;
                                let carry_error_roll = rng.random();
                                let carry = carry_phase_plan(&CarryPhasePlanInput {
                                    holder_pos: holder.pos,
                                    target,
                                    speed_ability: holder.speed.round() as i32,
                                    dribbling: holder.dribbling,
                                    consecutive_carries: holder.consecutive_carries,
                                    attacking_right,
                                    pitch_length: config.pitch_length,
                                    pitch_width: config.pitch_width,
                                    player_max_speed: config.player_max_speed,
                                    player_min_speed: config.player_min_speed,
                                    carrier_speed: config.carrier_speed,
                                    carry_error_divisor: config.carry_error_divisor,
                                    opponents: &opponents,
                                    error_roll: carry_error_roll,
                                    loose_x_roll: 0.5,
                                    loose_y_roll: 0.5,
                                });
                                if carry.is_error {
                                    holder.pos = carry.new_pos;
                                    holder.distance_covered += carry.distance_covered;
                                    holder.turnovers += 1;
                                    holder.consecutive_carries = 0;
                                    holder.state = "off_ball".to_string();
                                    let player_name = holder.name.clone();
                                    let loose_pos = pitch_clamp(
                                        (
                                            carry.new_pos.0 + rng.uniform(-3.0, 3.0),
                                            carry.new_pos.1 + rng.uniform(-2.0, 2.0),
                                        ),
                                        config.pitch_length,
                                        config.pitch_width,
                                    );
                                    let _ = holder;
                                    set_contested_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        loose_pos,
                                        (0.0, 0.0),
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "error",
                                        "error_type": "carry",
                                        "player": player_name
                                    }));
                                    break 'held_action_dispatch;
                                }
                                holder.pos = carry.new_pos;
                                holder.distance_covered += carry.distance_covered;
                                holder.carries_completed += 1;
                                holder.consecutive_carries += 1;
                                let carry_stats = track_carry_stats(&CarryStatInput {
                                    old_pos,
                                    new_pos: carry.new_pos,
                                    attacking_right,
                                    pitch_length: config.pitch_length,
                                    pitch_width: config.pitch_width,
                                });
                                holder.progressive_carries += carry_stats.progressive_carries;
                                holder.carries_into_final_third +=
                                    carry_stats.carries_into_final_third;
                                holder.carries_into_box += carry_stats.carries_into_box;
                                state.ball.position = carry.new_pos;
                                state.trace_entries.push(json!({
                                    "tick": tick,
                                    "type": "action",
                                    "team": if holder_home { "home" } else { "away" },
                                    "player": holder.name,
                                    "action": "carry",
                                    "from": [round_one(old_pos.0), round_one(old_pos.1)],
                                    "target": [round_one(target.0), round_one(target.1)],
                                    "pos": [round_one(holder.pos.0), round_one(holder.pos.1)],
                                    "distance": round_one(carry.distance_covered)
                                }));
                            }
                            RunnerHeldAction::Pass {
                                receiver_idx,
                                target,
                                is_long,
                                lane_risk,
                            } => {
                                let interception_present = interception_defender_idx.is_some();
                                let passer_name = holder_snapshot.name.clone();
                                let passer_pos = holder_snapshot.pos;
                                let passing = if is_long {
                                    holder_snapshot.long_passing
                                } else {
                                    holder_snapshot.short_passing
                                };
                                let interceptor_defence = interception_defender_idx
                                    .and_then(|idx| {
                                        if holder_home {
                                            away.get(idx).map(|defender| defender.defence)
                                        } else {
                                            home.get(idx).map(|defender| defender.defence)
                                        }
                                    })
                                    .unwrap_or(0.0);
                                let intended_receiver_pos = if holder_home {
                                    home.get(receiver_idx).map(|receiver| receiver.pos)
                                } else {
                                    away.get(receiver_idx).map(|receiver| receiver.pos)
                                };
                                let pass_randoms = preview_randoms::<5>(rng);
                                let pass = pass_phase_plan(&PassPhasePlanInput {
                                    passer_pos,
                                    ideal_target: target,
                                    passing,
                                    is_long,
                                    lane_risk,
                                    pitch_length: config.pitch_length,
                                    pitch_width: config.pitch_width,
                                    ball_pass_speed: config.ball_pass_speed,
                                    ball_long_pass_speed: config.ball_long_pass_speed,
                                    pass_error_divisor: config.pass_error_divisor,
                                    opponents: &opponents,
                                    random_1: pass_randoms[0],
                                    random_2: pass_randoms[1],
                                    random_3: pass_randoms[2],
                                    random_4: pass_randoms[3],
                                    random_5: pass_randoms[4],
                                    interception_present,
                                    interceptor_defence,
                                    interception_distance,
                                    interception_reach: config.interception_reach,
                                    intended_receiver_pos,
                                });
                                advance_randoms(rng, pass.randoms_used);
                                if holder_home {
                                    if let Some(holder) = home.get_mut(holder_idx) {
                                        holder.passes_attempted += 1;
                                        holder.hold_ticks = 0;
                                        holder.consecutive_carries = 0;
                                        holder.state = "off_ball".to_string();
                                        clear_player_goal(holder);
                                    }
                                } else if let Some(holder) = away.get_mut(holder_idx) {
                                    holder.passes_attempted += 1;
                                    holder.hold_ticks = 0;
                                    holder.consecutive_carries = 0;
                                    holder.state = "off_ball".to_string();
                                    clear_player_goal(holder);
                                }
                                if pass.outcome_code == 1 {
                                    if holder_home {
                                        if let Some(holder) = home.get_mut(holder_idx) {
                                            holder.turnovers += 1;
                                        }
                                    } else if let Some(holder) = away.get_mut(holder_idx) {
                                        holder.turnovers += 1;
                                    }
                                    set_contested_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        pass.stray_pos,
                                        (0.0, 0.0),
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "error",
                                        "error_type": "pass_accuracy",
                                        "player": passer_name
                                    }));
                                    break 'held_action_dispatch;
                                }
                                if pass.outcome_code == 2 {
                                    let interceptor_idx = interception_defender_idx.unwrap_or(0);
                                    let (interceptor_pos, interceptor_name) = if holder_home {
                                        if let Some(interceptor) = away.get_mut(interceptor_idx) {
                                            interceptor.interceptions += 1;
                                            (interceptor.pos, interceptor.name.clone())
                                        } else {
                                            (pass.target, String::new())
                                        }
                                    } else if let Some(interceptor) = home.get_mut(interceptor_idx)
                                    {
                                        interceptor.interceptions += 1;
                                        (interceptor.pos, interceptor.name.clone())
                                    } else {
                                        (pass.target, String::new())
                                    };
                                    give_ball_to_player(
                                        state,
                                        home,
                                        away,
                                        interceptor_idx,
                                        !holder_home,
                                        interceptor_pos,
                                        None,
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "interception",
                                        "team": if holder_home { "away" } else { "home" },
                                        "player": interceptor_name
                                    }));
                                    break 'held_action_dispatch;
                                }
                                state.ball.state = RunnerBallState::InFlight;
                                state.ball.position = passer_pos;
                                state.ball.holder_idx = None;
                                state.ball.holder_team_home = None;
                                state.ball.loose_velocity = (0.0, 0.0);
                                state.ball.contested_ticks = 0;
                                state.last_passer_team_home = Some(holder_home);
                                state.last_passer_idx = holder_idx as i32;
                                let mut offside_indices = if holder_home {
                                    flag_offside_indices(
                                        home,
                                        away,
                                        holder_idx,
                                        passer_pos,
                                        attacking_right,
                                        config,
                                    )
                                } else {
                                    flag_offside_indices(
                                        away,
                                        home,
                                        holder_idx,
                                        passer_pos,
                                        attacking_right,
                                        config,
                                    )
                                };
                                if config.runner_force_receiver_offside
                                    && !offside_indices.contains(&receiver_idx)
                                {
                                    offside_indices.push(receiver_idx);
                                }
                                state.ball.flight = Some(RunnerFlight {
                                    kind: RunnerFlightKind::Pass,
                                    origin: passer_pos,
                                    target: pass.target,
                                    ticks_elapsed: 0,
                                    ticks_total: pass.ticks_needed,
                                    passer_idx: holder_idx,
                                    passer_team_home: holder_home,
                                    intended_receiver_idx: Some(receiver_idx),
                                    offside_indices,
                                    last_passer_team_home: state.last_passer_team_home,
                                    last_passer_idx: state.last_passer_idx,
                                    on_target: false,
                                    speed: pass.speed,
                                });
                                state.pending_ball_flight =
                                    Some(replay_ball_flight(state.ball.flight.as_ref()));
                                state.trace_entries.push(json!({
                                "tick": tick,
                                "type": "action",
                                "team": if holder_home { "home" } else { "away" },
                                "player": passer_name,
                                "action": "pass",
                                "target_player": receiver_idx,
                                "target": [round_one(pass.target.0), round_one(pass.target.1)],
                                "pass_type": if is_long { "long" } else { "short" },
                                "target_kind": if pass.target_kind_code == 1 { "space" } else { "feet" }
                            }));
                            }
                            RunnerHeldAction::Clear { target } => {
                                let holder = if holder_home {
                                    home.get_mut(holder_idx)
                                } else {
                                    away.get_mut(holder_idx)
                                };
                                let Some(holder) = holder else { return };
                                holder.clearances += 1;
                                holder.passes_attempted += 1;
                                holder.hold_ticks = 0;
                                holder.consecutive_carries = 0;
                                holder.state = "off_ball".to_string();
                                clear_player_goal(holder);
                                let clear = clear_phase_plan(&ClearPhasePlanInput {
                                    clearer_pos: holder.pos,
                                    target,
                                    ball_long_pass_speed: config.ball_long_pass_speed,
                                });
                                state.ball.state = RunnerBallState::InFlight;
                                state.ball.position = holder.pos;
                                state.ball.holder_idx = None;
                                state.ball.holder_team_home = None;
                                state.ball.loose_velocity = (0.0, 0.0);
                                state.ball.contested_ticks = 0;
                                state.last_passer_team_home = Some(holder_home);
                                state.last_passer_idx = holder_idx as i32;
                                state.ball.flight = Some(RunnerFlight {
                                    kind: RunnerFlightKind::Clearance,
                                    origin: clear.origin,
                                    target: clear.target,
                                    ticks_elapsed: 0,
                                    ticks_total: clear.ticks_needed,
                                    passer_idx: holder_idx,
                                    passer_team_home: holder_home,
                                    intended_receiver_idx: None,
                                    offside_indices: Vec::new(),
                                    last_passer_team_home: state.last_passer_team_home,
                                    last_passer_idx: state.last_passer_idx,
                                    on_target: false,
                                    speed: clear.speed,
                                });
                                state.trace_entries.push(json!({
                                    "tick": tick,
                                    "type": "action",
                                    "team": if holder_home { "home" } else { "away" },
                                    "player": holder.name,
                                    "action": "clear",
                                    "target": [round_one(clear.target.0), round_one(clear.target.1)]
                                }));
                            }
                            RunnerHeldAction::Shoot {
                                xg, on_target_prob, ..
                            } => {
                                if state.last_passer_team_home == Some(holder_home)
                                    && state.last_passer_idx >= 0
                                    && state.last_passer_idx as usize != holder_idx
                                {
                                    if holder_home {
                                        if let Some(passer) =
                                            home.get_mut(state.last_passer_idx as usize)
                                        {
                                            passer.key_passes += 1;
                                        }
                                    } else if let Some(passer) =
                                        away.get_mut(state.last_passer_idx as usize)
                                    {
                                        passer.key_passes += 1;
                                    }
                                }
                                let holder = if holder_home {
                                    home.get_mut(holder_idx)
                                } else {
                                    away.get_mut(holder_idx)
                                };
                                let Some(holder) = holder else { return };
                                holder.shots += 1;
                                holder.xg += xg;
                                holder.hold_ticks = 0;
                                holder.consecutive_carries = 0;
                                holder.state = "off_ball".to_string();
                                clear_player_goal(holder);
                                let shot_randoms = preview_randoms::<3>(rng);
                                let shot = shot_phase_plan(&ShotPhasePlanInput {
                                    shooter_name: holder.name.as_str(),
                                    shooter_pos: holder.pos,
                                    explicit_xg: Some(xg),
                                    on_target_prob,
                                    goal_reward_constant: 1.0,
                                    attacking_right,
                                    pitch_length: config.pitch_length,
                                    pitch_width: config.pitch_width,
                                    goal_width: config.goal_width,
                                    ball_shot_speed: config.ball_shot_speed,
                                    random_1: shot_randoms[0],
                                    random_2: shot_randoms[1],
                                    random_3: shot_randoms[2],
                                });
                                advance_randoms(rng, shot.randoms_used);
                                if shot.on_target {
                                    holder.shots_on_target += 1;
                                }
                                state.last_passer_team_home = Some(holder_home);
                                state.last_passer_idx = holder_idx as i32;
                                state.ball.state = RunnerBallState::InFlight;
                                state.ball.position = holder.pos;
                                state.ball.holder_idx = None;
                                state.ball.holder_team_home = None;
                                state.ball.loose_velocity = (0.0, 0.0);
                                state.ball.contested_ticks = 0;
                                state.ball.flight = Some(RunnerFlight {
                                    kind: RunnerFlightKind::Shot,
                                    origin: holder.pos,
                                    target: shot.target,
                                    ticks_elapsed: 0,
                                    ticks_total: shot.ticks_needed,
                                    passer_idx: holder_idx,
                                    passer_team_home: holder_home,
                                    intended_receiver_idx: None,
                                    offside_indices: Vec::new(),
                                    last_passer_team_home: state.last_passer_team_home,
                                    last_passer_idx: state.last_passer_idx,
                                    on_target: shot.on_target,
                                    speed: shot.speed,
                                });
                                state.pending_ball_flight =
                                    Some(replay_ball_flight(state.ball.flight.as_ref()));
                                state.trace_entries.push(json!({
                                    "tick": tick,
                                    "type": "action",
                                    "team": if holder_home { "home" } else { "away" },
                                    "player": holder.name,
                                    "action": "shot",
                                    "xg": round_one(xg),
                                    "target": [round_one(shot.target.0), round_one(shot.target.1)]
                                }));
                            }
                        }
                    }
                    adjust_held_tick_defensive_pressure_after_carry(
                        state,
                        home,
                        away,
                        holder_home,
                        holder_idx,
                        holder_action_type,
                        config,
                        home_attacking_right,
                    );
                    apply_held_tick_movement(home, away, holder_home, holder_idx, config);
                }
            }
        }
        RunnerBallState::InFlight => {
            if let Some(mut flight) = state.ball.flight.clone() {
                let flight_tick = tick_ball_flight(&FlightTickInput {
                    origin: flight.origin,
                    target: flight.target,
                    ticks_elapsed: flight.ticks_elapsed,
                    ticks_total: flight.ticks_total,
                });
                flight.ticks_elapsed = flight_tick.ticks_elapsed;
                state.ball.position = flight_tick.position;
                if !flight_tick.complete {
                    state.ball.flight = Some(flight.clone());
                    move_flight_players(
                        home,
                        away,
                        flight,
                        state,
                        tick,
                        config,
                        home_attacking_right,
                        rng,
                    );
                } else {
                    if is_out_of_bounds(flight.target, config) {
                        handle_out_of_bounds_flight(
                            state,
                            tick,
                            flight,
                            home,
                            away,
                            config,
                            home_attacking_right,
                        );
                        push_rng_trace(state, tick, "tick_end", rng);
                        state.trace_entries.push(json!({
                            "tick": tick,
                            "type": "state",
                            "ball_state": ball_state_name(state.ball.state),
                            "holder_team": state.ball.holder_team_home.map(|home| if home { "home" } else { "away" })
                        }));
                        return;
                    }
                    match flight.kind {
                        RunnerFlightKind::Shot => {
                            let (shooter_name, shooter_color, shooter_xg, logged_xg_sum) = if flight
                                .passer_team_home
                            {
                                home.get(flight.passer_idx)
                                    .map(|player| {
                                        (
                                            player.name.clone(),
                                            player.color.clone(),
                                            player.xg,
                                            shot_log_sum(player),
                                        )
                                    })
                                    .unwrap_or_else(|| ("".to_string(), "".to_string(), 0.0, 0.0))
                            } else {
                                away.get(flight.passer_idx)
                                    .map(|player| {
                                        (
                                            player.name.clone(),
                                            player.color.clone(),
                                            player.xg,
                                            shot_log_sum(player),
                                        )
                                    })
                                    .unwrap_or_else(|| ("".to_string(), "".to_string(), 0.0, 0.0))
                            };
                            let gk = if flight.passer_team_home {
                                away.get(0)
                            } else {
                                home.get(0)
                            };
                            let keeper_name =
                                gk.map(|player| player.name.clone()).unwrap_or_default();
                            let gk_pos = gk
                                .map(|player| player.pos)
                                .unwrap_or((0.0, config.pitch_width / 2.0));
                            let gk_saving = gk.map(|player| player.gk_saving).unwrap_or(50.0);
                            let gk_positioning =
                                gk.map(|player| player.gk_positioning).unwrap_or(50.0);
                            let gk_reaction = gk.map(|player| player.gk_reaction).unwrap_or(50.0);
                            let save_roll = if flight.on_target { rng.random() } else { 0.0 };
                            let arrival = shot_arrival_plan(&ShotArrivalPlanInput {
                                shooter_name: shooter_name.as_str(),
                                keeper_name: keeper_name.as_str(),
                                shot_origin: flight.origin,
                                shot_target: flight.target,
                                attacking_right: attacking_right_for(
                                    flight.passer_team_home,
                                    home_attacking_right,
                                ),
                                on_target: flight.on_target,
                                pitch_length: config.pitch_length,
                                pitch_width: config.pitch_width,
                                gk_pos,
                                gk_saving,
                                gk_positioning,
                                gk_reaction,
                                gk_position_error_factor: config.gk_position_error_factor,
                                gk_reaction_delay_factor: config.gk_reaction_delay_factor,
                                gk_save_base: config.gk_save_base,
                                save_roll,
                                total_xg: shooter_xg,
                                logged_xg_sum,
                            });
                            match arrival.outcome_code {
                                1 => {
                                    let gk_pos = if flight.passer_team_home {
                                        away.get(0)
                                            .map(|player| player.pos)
                                            .unwrap_or(state.ball.position)
                                    } else {
                                        home.get(0)
                                            .map(|player| player.pos)
                                            .unwrap_or(state.ball.position)
                                    };
                                    if flight.passer_team_home {
                                        if let Some(gk) = away.get_mut(0) {
                                            gk.psxg_faced += arrival.psxg_delta;
                                            gk.saves += 1;
                                        }
                                    } else if let Some(gk) = home.get_mut(0) {
                                        gk.psxg_faced += arrival.psxg_delta;
                                        gk.saves += 1;
                                    }
                                    give_ball_to_player(
                                        state,
                                        home,
                                        away,
                                        0,
                                        !flight.passer_team_home,
                                        gk_pos,
                                        None,
                                    );
                                    queue_replay_frame(
                                        state,
                                        tick,
                                        half,
                                        home,
                                        away,
                                        config,
                                        replay_ball_flight(Some(&flight)),
                                        Some("SAVE"),
                                        Some(1200),
                                        Some(flight.passer_idx),
                                        Some(if flight.passer_team_home {
                                            "home"
                                        } else {
                                            "away"
                                        }),
                                    );
                                }
                                2 => {
                                    let goal_plan = score_goal_plan(&ScoreGoalPlanInput {
                                        scorer_name: shooter_name.as_str(),
                                        scoring_team_home: flight.passer_team_home,
                                        conceding_team_home: !flight.passer_team_home,
                                        home_score: state.home_score,
                                        away_score: state.away_score,
                                        last_passer_team_home: flight.last_passer_team_home,
                                        last_passer_idx: flight.last_passer_idx,
                                        scorer_idx: flight.passer_idx as i32,
                                        scoring_team_size: 11,
                                        assister_name: "",
                                        assister_color: "",
                                        tick,
                                        tick_duration: config.tick_duration,
                                    });
                                    state.home_score = goal_plan.home_score;
                                    state.away_score = goal_plan.away_score;
                                    if flight.passer_team_home {
                                        if goal_plan.has_assist && goal_plan.assister_idx >= 0 {
                                            if let Some(assister) =
                                                home.get_mut(goal_plan.assister_idx as usize)
                                            {
                                                assister.assists += 1;
                                            }
                                        }
                                        if let Some(scorer) = home.get_mut(flight.passer_idx) {
                                            scorer.goals += 1;
                                        }
                                        if let Some(gk) = away.get_mut(0) {
                                            gk.psxg_faced += arrival.psxg_delta;
                                            gk.goals_conceded += 1;
                                        }
                                    } else {
                                        if goal_plan.has_assist && goal_plan.assister_idx >= 0 {
                                            if let Some(assister) =
                                                away.get_mut(goal_plan.assister_idx as usize)
                                            {
                                                assister.assists += 1;
                                            }
                                        }
                                        if let Some(scorer) = away.get_mut(flight.passer_idx) {
                                            scorer.goals += 1;
                                        }
                                        if let Some(gk) = home.get_mut(0) {
                                            gk.psxg_faced += arrival.psxg_delta;
                                            gk.goals_conceded += 1;
                                        }
                                    }
                                    state.goals.push(json!({
                                "minute": goal_plan.minute,
                                "team_side": if flight.passer_team_home { "home" } else { "away" },
                                "scorer": shooter_name,
                                "assister": goal_plan.assister_name,
                                "scorer_color": shooter_color,
                                "assister_color": goal_plan.assister_color
                            }));
                                    queue_replay_frame(
                                        state,
                                        tick,
                                        half,
                                        home,
                                        away,
                                        config,
                                        replay_ball_flight(Some(&flight)),
                                        Some("GOAL"),
                                        Some(goal_plan.pause_ms),
                                        Some(flight.passer_idx),
                                        Some(if flight.passer_team_home {
                                            "home"
                                        } else {
                                            "away"
                                        }),
                                    );
                                    set_dead_ball_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        "kickoff",
                                        goal_plan.restart_team_home,
                                        goal_plan.restart_ticks,
                                        state.ball.position,
                                    );
                                    reset_players_to_current_formation_slots(home);
                                    reset_players_to_current_formation_slots(away);
                                    state.trace_entries.push(json!({
                                "tick": tick,
                                "type": "event",
                                "event": "goal",
                                "team": if flight.passer_team_home { "home" } else { "away" },
                                "scorer": shooter_name,
                                "minute": goal_plan.minute
                            }));
                                }
                                _ => {
                                    set_dead_ball_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        "goal_kick",
                                        !flight.passer_team_home,
                                        config.goal_kick_restart_ticks,
                                        state.ball.position,
                                    );
                                    queue_replay_frame(
                                        state,
                                        tick,
                                        half,
                                        home,
                                        away,
                                        config,
                                        replay_ball_flight(Some(&flight)),
                                        Some("MISS"),
                                        Some(1200),
                                        Some(flight.passer_idx),
                                        Some(if flight.passer_team_home {
                                            "home"
                                        } else {
                                            "away"
                                        }),
                                    );
                                }
                            }
                            if flight.passer_team_home {
                                if let Some(shooter) = home.get_mut(flight.passer_idx) {
                                    shooter.shot_log.push(shot_log_json(&arrival.shot_log));
                                }
                            } else if let Some(shooter) = away.get_mut(flight.passer_idx) {
                                shooter.shot_log.push(shot_log_json(&arrival.shot_log));
                            }
                            state.trace_entries.push(json!({
                                "tick": tick,
                                "type": "event",
                                "event": "shot_arrival",
                                "outcome": arrival.shot_log.outcome,
                                "speed": round_one(flight.speed),
                                "save_prob": arrival.save_prob,
                                "save_roll": save_roll,
                                "shot_origin": [flight.origin.0, flight.origin.1],
                                "shot_target": [flight.target.0, flight.target.1],
                                "gk_pos": [gk_pos.0, gk_pos.1]
                            }));
                        }
                        RunnerFlightKind::Pass => {
                            let receivers = if flight.passer_team_home {
                                arrival_players(
                                    home,
                                    flight.passer_idx,
                                    flight.intended_receiver_idx,
                                )
                            } else {
                                arrival_players(
                                    away,
                                    flight.passer_idx,
                                    flight.intended_receiver_idx,
                                )
                            };
                            let opponents = if flight.passer_team_home {
                                opponent_arrival_players(away)
                            } else {
                                opponent_arrival_players(home)
                            };
                            let arrival = pass_arrival_plan(&PassArrivalPlanInput {
                                target_pos: flight.target,
                                flight_origin: flight.origin,
                                flight_speed: flight.speed,
                                flight_ticks_total: flight.ticks_total,
                                contest_radius: config.contest_radius,
                                player_max_speed: config.player_max_speed,
                                player_min_speed: config.player_min_speed,
                                target_occupation_weight: config.target_occupation_weight,
                                receivers: &receivers,
                                opponents: &opponents,
                            });
                            match arrival.outcome_code {
                                0 => {
                                    let receiver_idx = arrival
                                        .receiver_index
                                        .unwrap_or(flight.intended_receiver_idx.unwrap_or(0));
                                    let receiver_offside_flagged =
                                        flight.offside_indices.contains(&receiver_idx);
                                    let (receive_pos, loose_pos, receive_ok, receiver_name) = {
                                        let team = if flight.passer_team_home {
                                            &mut *home
                                        } else {
                                            &mut *away
                                        };
                                        if let Some(receiver) = team.get_mut(receiver_idx) {
                                            let receive_randoms = preview_randoms::<3>(rng);
                                            let receive =
                                                pass_receive_plan(&PassReceivePlanInput {
                                                    receiver_pos: receiver.pos,
                                                    target_pos: flight.target,
                                                    receiver_iq: receiver.iq,
                                                    receiver_offside_flagged,
                                                    pitch_length: config.pitch_length,
                                                    pitch_width: config.pitch_width,
                                                    first_touch_error_divisor: config
                                                        .first_touch_error_divisor,
                                                    error_roll: receive_randoms[0],
                                                    loose_x_roll: receive_randoms[1],
                                                    loose_y_roll: receive_randoms[2],
                                                });
                                            advance_randoms(rng, receive.randoms_used);
                                            let name = receiver.name.clone();
                                            if receive.outcome_code == 0 {
                                                receiver.distance_covered +=
                                                    receive.distance_covered;
                                                receiver.pos = receive.receive_pos;
                                                receiver.target_pos = receive.receive_pos;
                                            }
                                            (
                                                receive.receive_pos,
                                                receive.loose_pos,
                                                receive.outcome_code == 0,
                                                name,
                                            )
                                        } else {
                                            (flight.target, flight.target, false, String::new())
                                        }
                                    };
                                    if receiver_offside_flagged {
                                        let team = if flight.passer_team_home {
                                            &mut *home
                                        } else {
                                            &mut *away
                                        };
                                        if let Some(receiver) = team.get_mut(receiver_idx) {
                                            receiver.offsides += 1;
                                        }
                                        set_dead_ball_and_clear_goals(
                                            state,
                                            home,
                                            away,
                                            "offside",
                                            !flight.passer_team_home,
                                            2,
                                            receive_pos,
                                        );
                                        state.trace_entries.push(json!({
                                            "tick": tick,
                                            "type": "event",
                                            "event": "offside",
                                            "player": receiver_name,
                                            "team": if flight.passer_team_home { "home" } else { "away" }
                                        }));
                                    } else if receive_ok {
                                        if flight.passer_team_home {
                                            if let Some(passer) = home.get_mut(flight.passer_idx) {
                                                passer.passes_completed += 1;
                                                let pass_stats = track_pass_stats(&PassStatInput {
                                                    origin: flight.origin,
                                                    target: receive_pos,
                                                    attacking_right: attacking_right_for(
                                                        flight.passer_team_home,
                                                        home_attacking_right,
                                                    ),
                                                    pitch_length: config.pitch_length,
                                                    pitch_width: config.pitch_width,
                                                });
                                                passer.crosses_attempted +=
                                                    pass_stats.crosses_attempted;
                                                passer.crosses_completed +=
                                                    pass_stats.crosses_completed;
                                                passer.long_passes += pass_stats.long_passes;
                                                passer.completed_long_passes +=
                                                    pass_stats.completed_long_passes;
                                                passer.progressive_passes +=
                                                    pass_stats.progressive_passes;
                                                passer.passes_into_final_third +=
                                                    pass_stats.passes_into_final_third;
                                                passer.passes_into_box +=
                                                    pass_stats.passes_into_box;
                                            }
                                        } else if let Some(passer) = away.get_mut(flight.passer_idx)
                                        {
                                            passer.passes_completed += 1;
                                            let pass_stats = track_pass_stats(&PassStatInput {
                                                origin: flight.origin,
                                                target: receive_pos,
                                                attacking_right: attacking_right_for(
                                                    flight.passer_team_home,
                                                    home_attacking_right,
                                                ),
                                                pitch_length: config.pitch_length,
                                                pitch_width: config.pitch_width,
                                            });
                                            passer.crosses_attempted +=
                                                pass_stats.crosses_attempted;
                                            passer.crosses_completed +=
                                                pass_stats.crosses_completed;
                                            passer.long_passes += pass_stats.long_passes;
                                            passer.completed_long_passes +=
                                                pass_stats.completed_long_passes;
                                            passer.progressive_passes +=
                                                pass_stats.progressive_passes;
                                            passer.passes_into_final_third +=
                                                pass_stats.passes_into_final_third;
                                            passer.passes_into_box += pass_stats.passes_into_box;
                                        }
                                        record_pass_network(
                                            state,
                                            flight.passer_team_home,
                                            flight.passer_idx,
                                            receiver_idx,
                                        );
                                        give_ball_to_player(
                                            state,
                                            home,
                                            away,
                                            receiver_idx,
                                            flight.passer_team_home,
                                            receive_pos,
                                            Some(flight.origin),
                                        );
                                        state.trace_entries.push(json!({
                                            "tick": tick,
                                            "type": "action",
                                            "team": if flight.passer_team_home { "home" } else { "away" },
                                            "player": receiver_name,
                                            "action": "receive",
                                            "pos": [round_one(receive_pos.0), round_one(receive_pos.1)]
                                        }));
                                    } else {
                                        set_contested_and_clear_goals(
                                            state,
                                            home,
                                            away,
                                            loose_pos,
                                            (0.0, 0.0),
                                        );
                                        state.trace_entries.push(json!({
                                            "tick": tick,
                                            "type": "event",
                                            "event": "first_touch_error",
                                            "player": receiver_name
                                        }));
                                    }
                                }
                                1 => {
                                    let opponent_idx = arrival.opponent_index.unwrap_or(0);
                                    let (winner_pos, winner_name) = {
                                        let team = if flight.passer_team_home {
                                            &mut *away
                                        } else {
                                            &mut *home
                                        };
                                        if let Some(winner) = team.get_mut(opponent_idx) {
                                            winner.interceptions += 1;
                                            (winner.pos, winner.name.clone())
                                        } else {
                                            (flight.target, String::new())
                                        }
                                    };
                                    give_ball_to_player(
                                        state,
                                        home,
                                        away,
                                        opponent_idx,
                                        !flight.passer_team_home,
                                        winner_pos,
                                        None,
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "interception",
                                        "team": if flight.passer_team_home { "away" } else { "home" },
                                        "player": winner_name
                                    }));
                                }
                                _ => {
                                    set_contested_and_clear_goals(
                                        state,
                                        home,
                                        away,
                                        flight.target,
                                        arrival.loose_velocity,
                                    );
                                    state.trace_entries.push(json!({
                                        "tick": tick,
                                        "type": "event",
                                        "event": "pass_loose",
                                        "target": [round_one(flight.target.0), round_one(flight.target.1)]
                                    }));
                                }
                            }
                        }
                        RunnerFlightKind::Clearance => {
                            let home_arrivals = clearance_players(home);
                            let away_arrivals = clearance_players(away);
                            let arrival = clearance_arrival_plan(&ClearanceArrivalPlanInput {
                                target_pos: flight.target,
                                passer_team_home: flight.passer_team_home,
                                home_players: &home_arrivals,
                                away_players: &away_arrivals,
                            });
                            let winner_home = arrival.winner_code == 0;
                            let winner_idx = arrival.player_index.unwrap_or(0);
                            let (winner_pos, winner_name) = {
                                let team = if winner_home { &mut *home } else { &mut *away };
                                if let Some(winner) = team.get_mut(winner_idx) {
                                    (winner.pos, winner.name.clone())
                                } else {
                                    (flight.target, String::new())
                                }
                            };
                            if arrival.passer_completed {
                                if flight.passer_team_home {
                                    if let Some(passer) = home.get_mut(flight.passer_idx) {
                                        passer.passes_completed += 1;
                                    }
                                } else if let Some(passer) = away.get_mut(flight.passer_idx) {
                                    passer.passes_completed += 1;
                                }
                            }
                            give_ball_to_player(
                                state,
                                home,
                                away,
                                winner_idx,
                                winner_home,
                                winner_pos,
                                None,
                            );
                            state.trace_entries.push(json!({
                                "tick": tick,
                                "type": "event",
                                "event": "clearance_arrival",
                                "team": if winner_home { "home" } else { "away" },
                                "player": winner_name,
                                "passer_completed": arrival.passer_completed
                            }));
                        }
                    }
                }
            }
        }
        RunnerBallState::Contested => {
            let ticked_ball = tick_contested_ball(&ContestedTickInput {
                position: state.ball.position,
                loose_velocity: state.ball.loose_velocity,
                contested_ticks: state.ball.contested_ticks,
            });
            state.ball.position = pitch_clamp(
                ticked_ball.position,
                config.pitch_length,
                config.pitch_width,
            );
            state.ball.loose_velocity = ticked_ball.loose_velocity;
            state.ball.contested_ticks = ticked_ball.contested_ticks;

            let mut best_winner: Option<(bool, usize, f64)> = None;
            for (idx, player) in home.iter().enumerate() {
                let d = distance(player.pos, state.ball.position);
                if best_winner
                    .map(|(_, _, best_dist)| d < best_dist)
                    .unwrap_or(true)
                {
                    best_winner = Some((true, idx, d));
                }
            }
            for (idx, player) in away.iter().enumerate() {
                let d = distance(player.pos, state.ball.position);
                if best_winner
                    .map(|(_, _, best_dist)| d < best_dist)
                    .unwrap_or(true)
                {
                    best_winner = Some((false, idx, d));
                }
            }

            if let Some((winner_home, player_idx, best_dist)) =
                best_winner.filter(|(_, _, best_dist)| *best_dist < config.contest_radius)
            {
                let winner_pos = if winner_home {
                    home.get(player_idx)
                        .map(|player| player.pos)
                        .unwrap_or(state.ball.position)
                } else {
                    away.get(player_idx)
                        .map(|player| player.pos)
                        .unwrap_or(state.ball.position)
                };
                give_ball_to_player(state, home, away, player_idx, winner_home, winner_pos, None);
                state.trace_entries.push(json!({
                    "tick": tick,
                    "type": "event",
                    "event": "contested_won",
                    "team": if winner_home { "home" } else { "away" },
                    "player_idx": player_idx,
                    "distance": round_one(best_dist)
                }));
            } else {
                move_contested_team(
                    home,
                    away,
                    state.ball.position,
                    home_attacking_right,
                    config,
                );
                move_contested_team(
                    away,
                    home,
                    state.ball.position,
                    !home_attacking_right,
                    config,
                );

                if state.ball.contested_ticks > 5 {
                    if let Some((winner_home, player_idx, _best_dist)) = best_winner {
                        let winner_pos = if winner_home {
                            home.get(player_idx)
                                .map(|player| player.pos)
                                .unwrap_or(state.ball.position)
                        } else {
                            away.get(player_idx)
                                .map(|player| player.pos)
                                .unwrap_or(state.ball.position)
                        };
                        give_ball_to_player(
                            state,
                            home,
                            away,
                            player_idx,
                            winner_home,
                            winner_pos,
                            None,
                        );
                    }
                }
            }
        }
        RunnerBallState::Dead => {
            clear_team_goals(home);
            clear_team_goals(away);
            if let (Some(reason), Some(team_home)) =
                (state.dead_reason.as_deref(), state.restart_team_home)
            {
                let (has_shape, shape_ball_pos) = apply_restart_shape(
                    reason,
                    team_home,
                    home,
                    away,
                    config,
                    home_attacking_right,
                    false,
                );
                if has_shape {
                    state.ball.position = shape_ball_pos;
                }
            }
            if state.restart_ticks_remaining > 0 {
                state.restart_ticks_remaining -= 1;
            }
            if state.restart_ticks_remaining <= 0 {
                restart_dead_ball(state, tick, home, away, config, home_attacking_right, rng);
            }
        }
    }
    push_rng_trace(state, tick, "tick_end", rng);
    match state_before {
        RunnerBallState::Held => match (state.ball.state, state.ball.holder_team_home) {
            (RunnerBallState::Held, Some(true)) => state.home_possession_ticks += 1,
            (RunnerBallState::Held, Some(false)) => state.away_possession_ticks += 1,
            _ => {}
        },
        RunnerBallState::Contested => state.neutral_ticks += 1,
        _ => {}
    }
    if state_before == RunnerBallState::Held {
        if let Some(mut event) = state.pending_on_ball_goal_event.take() {
            if let Some(payload) = event.as_object_mut() {
                payload.insert("tick".to_string(), json!(tick));
            }
            state.trace_entries.push(event);
        }
        if held_attack_choices > 0 || held_defense_choices > 0 {
            state.trace_entries.push(json!({
                "tick": tick,
                "type": "event",
                "event": "off_ball_choice",
                "attack_choices": held_attack_choices,
                "defense_choices": held_defense_choices,
                "attack_goal_choices": held_attack_choices,
                "defense_goal_choices": held_defense_choices
            }));
        }
    }
    state.trace_entries.push(json!({
        "tick": tick,
        "type": "state",
        "ball_state": ball_state_name(state.ball.state),
        "holder_team": state.ball.holder_team_home.map(|home| if home { "home" } else { "away" }),
        "home_phase": phase_name(state.home_phase_code),
        "away_phase": phase_name(state.away_phase_code),
        "home_ticks_since_possession_change": state.home_ticks_since_possession_change,
        "away_ticks_since_possession_change": state.away_ticks_since_possession_change,
        "home_had_possession_last_tick": state.home_had_possession_last_tick,
        "away_had_possession_last_tick": state.away_had_possession_last_tick
    }));
}

pub fn run_match_v2(request: MatchV2RunRequest) -> MatchV2RunResponse {
    let _ = all_ball_states();
    let config = runtime_config(&request.config);
    let mut rng = RunnerRng::new(request.seed.unwrap_or(0));
    let pitch_length = config.pitch_length;
    let pitch_width = config.pitch_width;
    let home_formation_data = formation_data(&request.home_formation);
    let away_formation_data = formation_data(&request.away_formation);
    let mut home_players = build_players(
        &request.home_cards,
        home_formation_data,
        true,
        pitch_length,
        pitch_width,
    );
    let mut away_players = build_players(
        &request.away_cards,
        away_formation_data,
        false,
        pitch_length,
        pitch_width,
    );
    let trace_id = format!(
        "rust-match-v2:{}:{}:{}:{}",
        request.home_formation,
        request.away_formation,
        request.home_cards.len(),
        request.away_cards.len()
    );
    let mut replay = vec![replay_header(
        &home_players,
        &away_players,
        &request.home_formation,
        &request.away_formation,
        pitch_width,
        pitch_length,
    )];
    let (mut holder_idx, mut holder_team, mut ball_pos) = apply_kickoff(
        true,
        true,
        &mut home_players,
        &mut away_players,
        pitch_length,
        pitch_width,
        None,
    );
    let mut state = RunnerMatchState {
        ball: RunnerBall {
            state: RunnerBallState::Held,
            position: ball_pos,
            holder_idx: Some(holder_idx),
            holder_team_home: Some(holder_team == "home"),
            flight: None,
            loose_velocity: (0.0, 0.0),
            contested_ticks: 0,
        },
        home_score: 0,
        away_score: 0,
        goals: Vec::new(),
        home_possession_ticks: 0,
        away_possession_ticks: 0,
        neutral_ticks: 0,
        dead_reason: None,
        restart_team_home: None,
        restart_ticks_remaining: 0,
        last_passer_team_home: None,
        last_passer_idx: -1,
        pass_network: HashMap::new(),
        held_action_cursor: 0,
        pending_on_ball_goal_event: None,
        pending_ball_flight: None,
        pending_replay_frames: Vec::new(),
        trace_entries: Vec::new(),
        trace_decisions: Vec::new(),
        shot_quality_cache: RefCell::new(HashMap::new()),
        home_phase_code: 1,
        away_phase_code: 3,
        home_had_possession_last_tick: false,
        away_had_possession_last_tick: false,
        home_ticks_since_possession_change: 99,
        away_ticks_since_possession_change: 99,
        rng_trace_enabled: request
            .config
            .get("rng_trace")
            .and_then(|value| value.as_bool())
            .unwrap_or_else(|| std::env::var("PSL_ENGINE_V2_RNG_TRACE").is_ok()),
    };
    replay.push(frame(
        0,
        config.tick_duration,
        1,
        &home_players,
        &away_players,
        ball_pos,
        Some(holder_idx),
        Some(holder_team),
        (0, 0),
        Some(true),
        serde_json::Value::Null,
        None,
        None,
    ));
    record_half_frames(
        &mut replay,
        &mut state,
        0,
        config.half_ticks,
        1,
        &mut home_players,
        &mut away_players,
        &config,
        true,
        &mut rng,
    );
    reset_formation_slots(
        &mut home_players,
        home_formation_data,
        false,
        pitch_length,
        pitch_width,
    );
    reset_formation_slots(
        &mut away_players,
        away_formation_data,
        true,
        pitch_length,
        pitch_width,
    );
    let kickoff = apply_kickoff(
        false,
        false,
        &mut home_players,
        &mut away_players,
        pitch_length,
        pitch_width,
        Some(&mut state),
    );
    holder_idx = kickoff.0;
    holder_team = kickoff.1;
    ball_pos = kickoff.2;
    state.ball = RunnerBall {
        state: RunnerBallState::Held,
        position: ball_pos,
        holder_idx: Some(holder_idx),
        holder_team_home: Some(holder_team == "home"),
        flight: None,
        loose_velocity: (0.0, 0.0),
        contested_ticks: 0,
    };
    state.dead_reason = None;
    state.restart_team_home = None;
    state.restart_ticks_remaining = 0;
    state.last_passer_team_home = None;
    state.last_passer_idx = -1;
    replay.push(frame(
        (config.half_ticks - 1).max(0),
        config.tick_duration,
        2,
        &home_players,
        &away_players,
        ball_pos,
        Some(holder_idx),
        Some(holder_team),
        (state.home_score, state.away_score),
        Some(true),
        serde_json::Value::Null,
        None,
        None,
    ));
    record_half_frames(
        &mut replay,
        &mut state,
        config.half_ticks,
        config.total_ticks,
        2,
        &mut home_players,
        &mut away_players,
        &config,
        false,
        &mut rng,
    );
    let possession_total =
        state.home_possession_ticks + state.away_possession_ticks + state.neutral_ticks;
    let home_possession = possession_pct(state.home_possession_ticks, possession_total);
    let away_possession = round_one(100.0 - home_possession);
    MatchV2RunResponse {
        home_score: state.home_score,
        away_score: state.away_score,
        goals: state.goals,
        home_stats: team_stats(&home_players, home_possession),
        away_stats: team_stats(&away_players, away_possession),
        home_player_stats: player_stat_skeleton(&home_players, true, &state.pass_network),
        away_player_stats: player_stat_skeleton(&away_players, false, &state.pass_network),
        home_ratings: team_ratings(&home_players, state.away_score),
        away_ratings: team_ratings(&away_players, state.home_score),
        replay_url: None,
        trace_id: if let Some(seed) = request.seed {
            format!("{trace_id}:seed:{seed}")
        } else {
            trace_id
        },
        replay,
        trace: serde_json::json!({
            "trace_id": "rust-match-v2",
            "entries": state.trace_entries,
            "decisions": state.trace_decisions,
            "total_entries": state.home_possession_ticks + state.away_possession_ticks + state.neutral_ticks
        }),
        engine: "rust_match_v2".to_string(),
        contract_version: 1,
    }
}
