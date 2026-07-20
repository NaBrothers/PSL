use crate::goalkeeper::GkSaveAttributes;
use crate::offside::is_offside_position;
use crate::pass_value::{
    expected_pass_value_with_context,
    expected_pass_value_with_context_and_precomputed_receiver_pressure, passer_pass_value_context,
    ExpectedPassInput, PasserPassValueContext, PasserPassValueContextInput,
};
use crate::physics::distance;
use crate::position_value::{position_value, PositionValueInput};
use crate::shot_quality::{ShotContestDefender, ShotQualityCache};
use crate::state_value::{
    pass_receive_team_value_context, pass_receive_value_context,
    pass_receive_value_context_with_team_context, PassReceiveTeamValueContext,
    PassReceiveValueContext, PassReceiveValueInput, PlayerShotProfile,
};
use crate::vision::VisionContext;

#[derive(Clone, Copy, Debug)]
pub struct PassSpacePlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub tactical_anchor: (f64, f64),
    pub is_goalkeeper: bool,
    pub is_defender: bool,
    pub is_midfielder: bool,
    pub is_wide: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct GenericPassSpaceCandidate {
    pub score: f64,
    pub target: (f64, f64),
    pub visibility: f64,
    pub position_value: f64,
}

#[derive(Debug)]
pub struct GenericPassSpaceInput<'a> {
    pub passer_index: usize,
    pub passer_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub vision: VisionContext,
    pub teammates: &'a [PassSpacePlayer],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverGoalInput<'a> {
    pub goal_type: &'a str,
    pub target_pos: (f64, f64),
    pub value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassTarget {
    pub target: (f64, f64),
    pub arrival: f64,
}

#[derive(Clone, Copy, Debug)]
struct RawPassTargetMeta {
    target: (f64, f64),
    arrival: f64,
    tactical_space: bool,
    tactical_space_prior: f64,
    tactical_space_value: f64,
    tactical_space_visibility: f64,
    expected_arrival_confidence: f64,
    expected_arrival_fit: f64,
}

impl From<RawPassTarget> for RawPassTargetMeta {
    fn from(value: RawPassTarget) -> Self {
        Self {
            target: value.target,
            arrival: value.arrival,
            tactical_space: false,
            tactical_space_prior: 0.0,
            tactical_space_value: 0.0,
            tactical_space_visibility: 0.0,
            expected_arrival_confidence: 0.0,
            expected_arrival_fit: 0.0,
        }
    }
}

const EMPTY_RAW_PASS_TARGET: RawPassTarget = RawPassTarget {
    target: (0.0, 0.0),
    arrival: 0.0,
};

const EMPTY_RAW_PASS_TARGET_META: RawPassTargetMeta = RawPassTargetMeta {
    target: (0.0, 0.0),
    arrival: 0.0,
    tactical_space: false,
    tactical_space_prior: 0.0,
    tactical_space_value: 0.0,
    tactical_space_visibility: 0.0,
    expected_arrival_confidence: 0.0,
    expected_arrival_fit: 0.0,
};

const EMPTY_VALUE_FIELD_RAW_TARGET: ValueFieldRawTarget = ValueFieldRawTarget {
    target: (0.0, 0.0),
    arrival: 0.0,
    tactical_space_prior: 0.0,
    tactical_space_value: 0.0,
    tactical_space_visibility: 0.0,
    expected_arrival_confidence: 0.0,
    expected_arrival_fit: 0.0,
};

const EMPTY_RECEIVER_SPATIAL_CANDIDATE: ReceiverSpatialCandidate = ReceiverSpatialCandidate {
    score: 0.0,
    target: (0.0, 0.0),
    receiver_arrival: 0.0,
    position_value: 0.0,
    point_visibility: 0.0,
};

const EMPTY_RECEIVER_PASS_CANDIDATE: ReceiverPassCandidate = ReceiverPassCandidate {
    target: (0.0, 0.0),
    score: 0.0,
    raw_score: 0.0,
    success_prob: 0.0,
    risk_cost: 0.0,
    current_value: 0.0,
    effective_current_value: 0.0,
    delta: 0.0,
    after_value: 0.0,
    after_direct_xg: 0.0,
    effective_delta: 0.0,
    progress_gain: 0.0,
    continuity: 0.0,
    lane_risk: 0.0,
    receiver_pressure: 0.0,
    turnover_consequence: 0.0,
    high_threat_space: 0.0,
    final_third_combination: 0.0,
    second_line_arrival_value: 0.0,
    second_line_cutback_value: 0.0,
    layoff_support_value: 0.0,
    short_combination_value: 0.0,
    layoff_retention_value: 0.0,
    receiver_arrival: 0.0,
    base_accuracy: 0.0,
    goal_target_fit: 0.0,
    is_long: false,
    target_kind_space: false,
    distance: 0.0,
    perception: 0.0,
    perception_multiplier: 0.0,
    arrival_margin: 0.0,
    defender_first_risk: 0.0,
    target_occupation_risk: 0.0,
    nearest_teammate_to_target: 0.0,
    nearest_opp_to_target: 0.0,
    box_space_pressure: 0.0,
    tactical_space: false,
    tactical_space_prior: 0.0,
    tactical_space_value: 0.0,
    tactical_space_visibility: 0.0,
    expected_arrival_confidence: 0.0,
    expected_arrival_fit: 0.0,
};

fn append_raw_pass_targets(
    output: &mut [RawPassTargetMeta],
    output_count: &mut usize,
    targets: &[RawPassTarget],
) {
    assert!(
        output.len() - *output_count >= targets.len(),
        "raw pass target buffer exceeds its fixed capacity"
    );
    for target in targets {
        output[*output_count] = (*target).into();
        *output_count += 1;
    }
}

#[derive(Clone, Debug)]
pub struct ReceiverBaseTargetsOutput {
    pub targets: Vec<RawPassTarget>,
    pub receiver_visibility: f64,
    pub target_visibility: f64,
    pub low_visibility: bool,
    pub receiver_goal_fit: f64,
}

#[derive(Debug)]
pub struct ReceiverBaseTargetsInput<'a> {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub receiver_goal: Option<ReceiverGoalInput<'a>>,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ValueFieldRawTarget {
    pub target: (f64, f64),
    pub arrival: f64,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

#[derive(Debug)]
pub struct ValueFieldTargetsInput<'a> {
    pub receiver: PassSpacePlayer,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub is_defender: bool,
    pub generic_candidates: &'a [GenericPassSpaceCandidate],
}

#[derive(Debug)]
pub struct StaleReleaseTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub consecutive_carries: i32,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct LayoffTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct SecondLineTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub receiver_base: (f64, f64),
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct BoxDeliveryTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug)]
pub struct DeliverySpaceTargetsInput {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub low_visibility: bool,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverSpatialCandidate {
    pub score: f64,
    pub target: (f64, f64),
    pub receiver_arrival: f64,
    pub position_value: f64,
    pub point_visibility: f64,
}

#[derive(Debug)]
pub struct ReceiverSpatialCandidatesInput<'a> {
    pub passer_pos: (f64, f64),
    pub receiver: PassSpacePlayer,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub low_visibility: bool,
    pub front_center: Option<(f64, f64)>,
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct PassRiskPlayer {
    pub index: usize,
    pub pos: (f64, f64),
    pub speed: i32,
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassPreValueInput<'a> {
    pub passer_index: usize,
    pub passer_pos: (f64, f64),
    pub receiver: PassRiskPlayer,
    pub target: (f64, f64),
    pub initial_receiver_arrival: f64,
    pub receiver_visibility: f64,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
    pub receiver_goal_fit: f64,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_passing: f64,
    pub long_passing: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub opponents: &'a [PassRiskPlayer],
    pub teammates: &'a [PassRiskPlayer],
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassPreValueOutput {
    pub valid: bool,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub continuity: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub receiver_time: f64,
    pub defender_time: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
}

#[derive(Debug)]
pub struct RawPassValueInput<'a> {
    pub prevalue: RawPassPreValueInput<'a>,
    pub tick: i32,
    pub passer_team_home: bool,
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_consecutive_carries: i32,
    pub receiver_index: usize,
    pub receiver_team_home: bool,
    pub receiver_finishing: f64,
    pub receiver_long_shot: f64,
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub receiver_goal_type: Option<&'a str>,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
    pub shot_profiles: &'a [PlayerShotProfile],
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub current_value: f64,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

struct RawPassBatchValueContext<'a> {
    passer: PasserPassValueContext,
    receive: Option<&'a PassReceiveValueContext>,
}

const MAX_PASS_RISK_PLAYERS: usize = 11;

#[derive(Clone, Copy, Debug)]
struct RawPassOpponentMotion {
    speed: f64,
    is_goalkeeper: bool,
}

const EMPTY_RAW_PASS_OPPONENT_MOTION: RawPassOpponentMotion = RawPassOpponentMotion {
    speed: 0.0,
    is_goalkeeper: false,
};

#[derive(Clone, Copy, Debug)]
struct RawPassPreValueMotionContext<'a> {
    receiver_speed: f64,
    opponent_motion: &'a [RawPassOpponentMotion],
}

#[derive(Clone, Copy, Debug)]
struct RawPassPreValueGeometry {
    all_opponents_receiver_pressure: f64,
    outfield_opponents_receiver_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
enum RawPassReceiverPressureReuse {
    AllOpponents,
    OutfieldOpponents,
}

#[derive(Clone, Copy, Debug)]
pub struct RawPassValueOutput {
    pub valid: bool,
    pub score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
    pub after_direct_xg: f64,
    pub effective_delta: f64,
    pub progress_gain: f64,
    pub continuity: f64,
    pub lane_risk: f64,
    pub receiver_pressure: f64,
    pub turnover_consequence: f64,
    pub high_threat_space: f64,
    pub final_third_combination: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
    pub short_combination_value: f64,
    pub layoff_retention_value: f64,
    pub adjusted_score: f64,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReceiverPassCandidate {
    pub target: (f64, f64),
    pub score: f64,
    pub raw_score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
    pub after_direct_xg: f64,
    pub effective_delta: f64,
    pub progress_gain: f64,
    pub continuity: f64,
    pub lane_risk: f64,
    pub receiver_pressure: f64,
    pub turnover_consequence: f64,
    pub high_threat_space: f64,
    pub final_third_combination: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
    pub short_combination_value: f64,
    pub layoff_retention_value: f64,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub tactical_space: bool,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

#[derive(Debug)]
pub struct ReceiverPassBatchInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_short_passing: f64,
    pub passer_long_passing: f64,
    pub passer_consecutive_carries: i32,
    pub receiver_space: PassSpacePlayer,
    pub receiver_risk: PassRiskPlayer,
    pub receiver_index: usize,
    pub receiver_team_home: bool,
    pub receiver_finishing: f64,
    pub receiver_long_shot: f64,
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub receiver_goal: Option<ReceiverGoalInput<'a>>,
    pub is_receiver_defender: bool,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub current_value: f64,
    pub front_center: Option<(f64, f64)>,
    pub generic_candidates: &'a [GenericPassSpaceCandidate],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub shot_profiles: &'a [PlayerShotProfile],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub teammate_xy_positions: &'a [(f64, f64)],
    pub risk_opponents: &'a [PassRiskPlayer],
    pub risk_teammates: &'a [PassRiskPlayer],
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

#[derive(Clone, Copy, Debug)]
pub struct PassTeamPlayer<'a> {
    pub space: PassSpacePlayer,
    pub risk: PassRiskPlayer,
    pub finishing: f64,
    pub long_shot: f64,
    pub base: (f64, f64),
    pub is_defender: bool,
    pub goal: Option<ReceiverGoalInput<'a>>,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamPassCandidate {
    pub receiver_index: usize,
    pub target: (f64, f64),
    pub score: f64,
    pub raw_score: f64,
    pub success_prob: f64,
    pub risk_cost: f64,
    pub current_value: f64,
    pub effective_current_value: f64,
    pub delta: f64,
    pub after_value: f64,
    pub after_direct_xg: f64,
    pub effective_delta: f64,
    pub progress_gain: f64,
    pub continuity: f64,
    pub lane_risk: f64,
    pub receiver_pressure: f64,
    pub turnover_consequence: f64,
    pub high_threat_space: f64,
    pub final_third_combination: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
    pub short_combination_value: f64,
    pub layoff_retention_value: f64,
    pub receiver_arrival: f64,
    pub base_accuracy: f64,
    pub goal_target_fit: f64,
    pub is_long: bool,
    pub target_kind_space: bool,
    pub distance: f64,
    pub perception: f64,
    pub perception_multiplier: f64,
    pub arrival_margin: f64,
    pub defender_first_risk: f64,
    pub target_occupation_risk: f64,
    pub nearest_teammate_to_target: f64,
    pub nearest_opp_to_target: f64,
    pub box_space_pressure: f64,
    pub tactical_space: bool,
    pub tactical_space_prior: f64,
    pub tactical_space_value: f64,
    pub tactical_space_visibility: f64,
    pub expected_arrival_confidence: f64,
    pub expected_arrival_fit: f64,
}

pub const EMPTY_TEAM_PASS_CANDIDATE: TeamPassCandidate = TeamPassCandidate {
    receiver_index: 0,
    target: (0.0, 0.0),
    score: 0.0,
    raw_score: 0.0,
    success_prob: 0.0,
    risk_cost: 0.0,
    current_value: 0.0,
    effective_current_value: 0.0,
    delta: 0.0,
    after_value: 0.0,
    after_direct_xg: 0.0,
    effective_delta: 0.0,
    progress_gain: 0.0,
    continuity: 0.0,
    lane_risk: 0.0,
    receiver_pressure: 0.0,
    turnover_consequence: 0.0,
    high_threat_space: 0.0,
    final_third_combination: 0.0,
    second_line_arrival_value: 0.0,
    second_line_cutback_value: 0.0,
    layoff_support_value: 0.0,
    short_combination_value: 0.0,
    layoff_retention_value: 0.0,
    receiver_arrival: 0.0,
    base_accuracy: 0.0,
    goal_target_fit: 0.0,
    is_long: false,
    target_kind_space: false,
    distance: 0.0,
    perception: 0.0,
    perception_multiplier: 0.0,
    arrival_margin: 0.0,
    defender_first_risk: 0.0,
    target_occupation_risk: 0.0,
    nearest_teammate_to_target: 0.0,
    nearest_opp_to_target: 0.0,
    box_space_pressure: 0.0,
    tactical_space: false,
    tactical_space_prior: 0.0,
    tactical_space_value: 0.0,
    tactical_space_visibility: 0.0,
    expected_arrival_confidence: 0.0,
    expected_arrival_fit: 0.0,
};

#[derive(Debug)]
pub struct TeamPassBatchInput<'a> {
    pub tick: i32,
    pub passer_index: usize,
    pub passer_team_home: bool,
    pub passer_pos: (f64, f64),
    pub passer_finishing: f64,
    pub passer_long_shot: f64,
    pub passer_short_passing: f64,
    pub passer_long_passing: f64,
    pub passer_consecutive_carries: i32,
    pub vision: VisionContext,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub offside_line: f64,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub short_pass_base_success: f64,
    pub long_pass_base_success: f64,
    pub interception_reach: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub current_value: f64,
    pub players: &'a [PassTeamPlayer<'a>],
    pub space_players: &'a [PassSpacePlayer],
    pub opponent_positions: &'a [(f64, f64)],
    pub teammate_positions_for_value: &'a [(usize, f64, f64)],
    pub shot_profiles_for_value: &'a [PlayerShotProfile],
    pub teammate_goalkeeper_indices_for_value: &'a [usize],
    pub teammate_xy_positions: &'a [(f64, f64)],
    pub risk_opponents: &'a [PassRiskPlayer],
    pub risk_teammates: &'a [PassRiskPlayer],
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

fn dedupe_key(pos: (f64, f64)) -> (i64, i64) {
    ((pos.0 * 10.0).round() as i64, (pos.1 * 10.0).round() as i64)
}

const MAX_GENERIC_PASS_SPACE_CANDIDATES: usize = 108;
const MAX_SELECTED_GENERIC_PASS_SPACE_CANDIDATES: usize = 10;
const MAX_RECEIVER_BASE_PASS_TARGETS: usize = 7;
const MAX_STALE_RELEASE_TARGETS: usize = 4;
const MAX_LAYOFF_TARGETS: usize = 3;
const MAX_SECOND_LINE_TARGETS: usize = 1;
const MAX_BOX_DELIVERY_TARGETS: usize = 5;
const MAX_DELIVERY_SPACE_TARGETS: usize = 5;
const MAX_RECEIVER_SPATIAL_CANDIDATES: usize = 59;
pub const MAX_PASS_CANDIDATES_PER_RECEIVER: usize = MAX_RECEIVER_BASE_PASS_TARGETS
    + MAX_STALE_RELEASE_TARGETS
    + MAX_LAYOFF_TARGETS
    + MAX_SECOND_LINE_TARGETS
    + MAX_BOX_DELIVERY_TARGETS
    + MAX_DELIVERY_SPACE_TARGETS
    + MAX_SELECTED_GENERIC_PASS_SPACE_CANDIDATES
    + 3;
pub const MAX_TEAM_PASS_CANDIDATES: usize = (11 - 1) * MAX_PASS_CANDIDATES_PER_RECEIVER;

#[derive(Clone, Copy)]
struct ReceiverBaseTargetsSummary {
    target_count: usize,
    receiver_visibility: f64,
    target_visibility: f64,
    low_visibility: bool,
    receiver_goal_fit: f64,
}

#[derive(Clone, Debug)]
struct ReceiverPassWorkspace {
    target_buffer: [RawPassTarget; MAX_RECEIVER_BASE_PASS_TARGETS],
    raw_targets: [RawPassTargetMeta; MAX_PASS_CANDIDATES_PER_RECEIVER],
    value_field_targets: [ValueFieldRawTarget; MAX_SELECTED_GENERIC_PASS_SPACE_CANDIDATES],
    spatial_candidates: [ReceiverSpatialCandidate; MAX_RECEIVER_SPATIAL_CANDIDATES],
    opponent_motion: [RawPassOpponentMotion; MAX_PASS_RISK_PLAYERS],
    candidates: [ReceiverPassCandidate; MAX_PASS_CANDIDATES_PER_RECEIVER],
}

impl ReceiverPassWorkspace {
    fn new() -> Self {
        Self {
            target_buffer: [EMPTY_RAW_PASS_TARGET; MAX_RECEIVER_BASE_PASS_TARGETS],
            raw_targets: [EMPTY_RAW_PASS_TARGET_META; MAX_PASS_CANDIDATES_PER_RECEIVER],
            value_field_targets: [EMPTY_VALUE_FIELD_RAW_TARGET;
                MAX_SELECTED_GENERIC_PASS_SPACE_CANDIDATES],
            spatial_candidates: [EMPTY_RECEIVER_SPATIAL_CANDIDATE; MAX_RECEIVER_SPATIAL_CANDIDATES],
            opponent_motion: [EMPTY_RAW_PASS_OPPONENT_MOTION; MAX_PASS_RISK_PLAYERS],
            candidates: [EMPTY_RECEIVER_PASS_CANDIDATE; MAX_PASS_CANDIDATES_PER_RECEIVER],
        }
    }
}

#[derive(Clone, Debug)]
pub struct TeamPassWorkspace {
    generic_candidates: [GenericPassSpaceCandidate; MAX_GENERIC_PASS_SPACE_CANDIDATES],
    receiver: ReceiverPassWorkspace,
}

impl TeamPassWorkspace {
    pub fn new() -> Self {
        Self {
            generic_candidates: [GenericPassSpaceCandidate {
                score: 0.0,
                target: (0.0, 0.0),
                visibility: 0.0,
                position_value: 0.0,
            }; MAX_GENERIC_PASS_SPACE_CANDIDATES],
            receiver: ReceiverPassWorkspace::new(),
        }
    }
}

impl Default for TeamPassWorkspace {
    fn default() -> Self {
        Self::new()
    }
}

pub fn generic_pass_space_candidates(
    input: &GenericPassSpaceInput<'_>,
) -> Vec<GenericPassSpaceCandidate> {
    let mut candidates = [GenericPassSpaceCandidate {
        score: 0.0,
        target: (0.0, 0.0),
        visibility: 0.0,
        position_value: 0.0,
    }; MAX_GENERIC_PASS_SPACE_CANDIDATES];
    let len = generic_pass_space_candidates_into(input, &mut candidates);
    candidates[..len].to_vec()
}

fn generic_pass_space_candidates_into(
    input: &GenericPassSpaceInput<'_>,
    output: &mut [GenericPassSpaceCandidate],
) -> usize {
    assert!(
        output.len() >= MAX_GENERIC_PASS_SPACE_CANDIDATES,
        "generic pass space output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let mut front_anchor_sum = (0.0, 0.0);
    let mut front_anchor_count = 0;
    let mut visible_anchor_sum = (0.0, 0.0);
    let mut visible_anchor_count = 0;
    for tm in input.teammates {
        if tm.index == input.passer_index || tm.is_goalkeeper {
            continue;
        }
        let anchor_progress = if input.attacking_right {
            tm.tactical_anchor.0 / input.pitch_length
        } else {
            (input.pitch_length - tm.tactical_anchor.0) / input.pitch_length
        };
        if anchor_progress > 0.58 {
            front_anchor_sum.0 += tm.tactical_anchor.0;
            front_anchor_sum.1 += tm.tactical_anchor.1;
            front_anchor_count += 1;
        }
        if input
            .vision
            .confidence(input.passer_pos, tm.tactical_anchor)
            > 0.0
        {
            visible_anchor_sum.0 += tm.tactical_anchor.0;
            visible_anchor_sum.1 += tm.tactical_anchor.1;
            visible_anchor_count += 1;
        }
    }

    let mut generic_centers = [input.passer_pos; 3];
    let mut generic_center_count = 1;
    if front_anchor_count > 0 {
        generic_centers[generic_center_count] = (
            front_anchor_sum.0 / front_anchor_count as f64,
            front_anchor_sum.1 / front_anchor_count as f64,
        );
        generic_center_count += 1;
    }
    if visible_anchor_count > 0 {
        generic_centers[generic_center_count] = (
            visible_anchor_sum.0 / visible_anchor_count as f64,
            visible_anchor_sum.1 / visible_anchor_count as f64,
        );
        generic_center_count += 1;
    }

    let mut seen = [(0, 0); MAX_GENERIC_PASS_SPACE_CANDIDATES];
    let mut seen_count = 0;
    let mut candidate_count = 0;
    for center in &generic_centers[..generic_center_count] {
        for radius in [8.0, 16.0, 28.0, 40.0] {
            for angle_deg in [
                -150.0_f64, -105.0, -60.0, -25.0, 0.0, 25.0, 60.0, 105.0, 150.0,
            ] {
                let angle = angle_deg.to_radians();
                let target = pitch_clamp(
                    (
                        center.0 + angle.cos() * radius * forward_dir,
                        center.1 + angle.sin() * radius,
                    ),
                    input.pitch_length,
                    input.pitch_width,
                );
                let key = dedupe_key(target);
                if seen[..seen_count].contains(&key) {
                    continue;
                }
                seen[seen_count] = key;
                seen_count += 1;

                let visibility = input.vision.confidence(input.passer_pos, target);
                if visibility <= 0.0 {
                    continue;
                }
                if is_offside_position(
                    target,
                    input.attacking_right,
                    input.offside_line,
                    input.pitch_length,
                    Some(input.passer_pos.0),
                ) {
                    continue;
                }
                let pass_distance = distance(input.passer_pos, target);
                if pass_distance < 6.0 || pass_distance > 55.0 {
                    continue;
                }
                let pv = position_value(&PositionValueInput {
                    x: target.0,
                    y: target.1,
                    pitch_length: input.pitch_length,
                    pitch_width: input.pitch_width,
                    attacking_right: input.attacking_right,
                    opponent_positions: input.opponent_positions,
                    teammate_positions: input.teammate_positions,
                    skip_teammate_index: None,
                    runner_formation_pos: None,
                });
                let forward_gain = ((target.0 - input.passer_pos.0) * forward_dir).max(0.0)
                    / input.pitch_length.max(1.0);
                let distance_fit = 1.0 - (pass_distance - 34.0).max(0.0) / 30.0;
                let score = pv
                    * (0.45 + 0.55 * visibility)
                    * (0.72 + 0.28 * forward_gain)
                    * distance_fit.max(0.25);
                output[candidate_count] = GenericPassSpaceCandidate {
                    score,
                    target,
                    visibility,
                    position_value: pv,
                };
                candidate_count += 1;
            }
        }
    }

    output[..candidate_count].sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    candidate_count.min(MAX_SELECTED_GENERIC_PASS_SPACE_CANDIDATES)
}

pub fn receiver_base_pass_targets(
    input: &ReceiverBaseTargetsInput<'_>,
) -> ReceiverBaseTargetsOutput {
    let mut targets = [RawPassTarget {
        target: (0.0, 0.0),
        arrival: 0.0,
    }; MAX_RECEIVER_BASE_PASS_TARGETS];
    let summary = receiver_base_pass_targets_into(input, &mut targets);
    ReceiverBaseTargetsOutput {
        targets: targets[..summary.target_count].to_vec(),
        receiver_visibility: summary.receiver_visibility,
        target_visibility: summary.target_visibility,
        low_visibility: summary.low_visibility,
        receiver_goal_fit: summary.receiver_goal_fit,
    }
}

fn receiver_base_pass_targets_into(
    input: &ReceiverBaseTargetsInput<'_>,
    targets: &mut [RawPassTarget],
) -> ReceiverBaseTargetsSummary {
    assert!(
        targets.len() >= MAX_RECEIVER_BASE_PASS_TARGETS,
        "receiver base target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let tm = input.receiver;
    let receiver_visibility = input.vision.confidence(input.passer_pos, tm.pos);
    let mut target_visibility = receiver_visibility
        .max(input.vision.confidence(input.passer_pos, tm.target_pos))
        .max(
            input
                .vision
                .confidence(input.passer_pos, tm.tactical_anchor),
        );
    let mut low_visibility = target_visibility < 0.18;
    let mut receiver_goal_fit = 0.0;
    let mut target_count = 0;
    targets[target_count] = RawPassTarget {
        target: tm.pos,
        arrival: 1.0,
    };
    target_count += 1;

    if let Some(goal) = input.receiver_goal {
        if goal.goal_type == "arc_arrival_for_cutback" || goal.goal_type == "attack_far_post" {
            let goal_visibility = input.vision.confidence(input.passer_pos, goal.target_pos);
            let goal_dist = distance(tm.pos, goal.target_pos);
            let target_progress_hint = if input.attacking_right {
                goal.target_pos.0 / input.pitch_length
            } else {
                (input.pitch_length - goal.target_pos.0) / input.pitch_length
            };
            let carrier_progress_hint = if input.attacking_right {
                input.passer_pos.0 / input.pitch_length
            } else {
                (input.pitch_length - input.passer_pos.0) / input.pitch_length
            };
            let support_depth = carrier_progress_hint - target_progress_hint;
            let target_centrality_hint = 1.0
                - ((goal.target_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                    .min(1.0);
            if goal.goal_type == "arc_arrival_for_cutback" {
                receiver_goal_fit = crate::physics::smoothstep(0.56, 0.84, target_progress_hint)
                    * (1.0 - crate::physics::smoothstep(0.86, 0.96, target_progress_hint))
                    * (1.0 - crate::physics::smoothstep(0.18, 0.34, support_depth.abs()))
                    * crate::physics::smoothstep(0.42, 0.84, target_centrality_hint)
                    * (1.0 - crate::physics::smoothstep(18.0, 42.0, goal_dist))
                    * crate::physics::smoothstep(0.005, 0.080, goal.value);
            } else {
                receiver_goal_fit = crate::physics::smoothstep(0.76, 0.94, target_progress_hint)
                    * crate::physics::smoothstep(0.22, 0.76, target_centrality_hint)
                    * (1.0 - crate::physics::smoothstep(16.0, 42.0, goal_dist))
                    * crate::physics::smoothstep(0.005, 0.080, goal.value);
            }
            receiver_goal_fit *= 0.35 + 0.65 * goal_visibility;
            target_visibility = target_visibility.max(goal_visibility);
            low_visibility = target_visibility < 0.18;
            if receiver_goal_fit > 0.0 {
                targets[target_count] = RawPassTarget {
                    target: goal.target_pos,
                    arrival: 0.62 + 0.22 * receiver_goal_fit,
                };
                target_count += 1;
            }
        }
    }

    let future_x = tm.pos.0 + (tm.target_pos.0 - tm.pos.0) * 0.5;
    let future_y = tm.pos.1 + (tm.target_pos.1 - tm.pos.1) * 0.5;
    targets[target_count] = RawPassTarget {
        target: pitch_clamp((future_x, future_y), input.pitch_length, input.pitch_width),
        arrival: 0.92,
    };
    target_count += 1;

    let support_x = tm.pos.0 * 0.65 + input.passer_pos.0 * 0.35;
    let support_y = tm.pos.1 * 0.70 + input.passer_pos.1 * 0.30;
    targets[target_count] = RawPassTarget {
        target: pitch_clamp(
            (support_x, support_y),
            input.pitch_length,
            input.pitch_width,
        ),
        arrival: 0.88,
    };
    target_count += 1;

    let switch_y = tm.pos.1 * 0.45 + (input.pitch_width - input.passer_pos.1) * 0.55;
    if !low_visibility {
        targets[target_count] = RawPassTarget {
            target: pitch_clamp((support_x, switch_y), input.pitch_length, input.pitch_width),
            arrival: 0.76,
        };
        target_count += 1;
    }

    let tm_width_ratio = ((tm.tactical_anchor.1 - input.pitch_width / 2.0).abs()
        / (input.pitch_width / 2.0))
        .min(1.0);
    let tm_progress_hint = if input.attacking_right {
        tm.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - tm.tactical_anchor.0) / input.pitch_length
    };
    if !low_visibility && tm_width_ratio > 0.50 && tm_progress_hint > 0.56 {
        let wide_lane_y = tm.tactical_anchor.1 * 0.72 + tm.pos.1 * 0.28;
        let wide_lane_x = if input.attacking_right {
            tm.pos.0.max(tm.tactical_anchor.0)
        } else {
            tm.pos.0.min(tm.tactical_anchor.0)
        };
        targets[target_count] = RawPassTarget {
            target: pitch_clamp(
                (wide_lane_x + forward_dir * 4.0, wide_lane_y),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: 0.78,
        };
        target_count += 1;
    }

    let move_progress = (tm.target_pos.0 - tm.pos.0) * forward_dir;
    if !low_visibility && move_progress > 1.0 {
        let lead_x = tm.pos.0 + forward_dir * (4.0 + move_progress).min(12.0);
        let lead_y = tm.pos.1 + (tm.target_pos.1 - tm.pos.1) * 0.35;
        targets[target_count] = RawPassTarget {
            target: pitch_clamp((lead_x, lead_y), input.pitch_length, input.pitch_width),
            arrival: 0.82,
        };
        target_count += 1;
    }

    ReceiverBaseTargetsSummary {
        target_count,
        receiver_visibility,
        target_visibility,
        low_visibility,
        receiver_goal_fit,
    }
}

pub fn value_field_raw_targets(input: &ValueFieldTargetsInput<'_>) -> Vec<ValueFieldRawTarget> {
    let role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let role_fit = crate::physics::smoothstep(0.38, 0.76, role_progress)
        * if input.is_defender { 0.55 } else { 1.0 };
    let mut results = Vec::new();
    for candidate in input.generic_candidates {
        let goal_fit = if let Some(goal_target) = input.receiver_goal_target {
            1.0 - distance(goal_target, candidate.target) / 18.0
        } else {
            0.0
        };
        let arrival_fit = 0.0_f64
            .max(1.0 - distance(input.receiver.pos, candidate.target) / 28.0)
            .max(1.0 - distance(input.receiver.target_pos, candidate.target) / 24.0)
            .max(1.0 - distance(input.receiver.tactical_anchor, candidate.target) / 22.0)
            .max(goal_fit);
        let expected_arrival =
            (candidate.score * (0.30 + 0.48 * arrival_fit + 0.22 * role_fit) * 1.35)
                .clamp(0.0, 1.0);
        if expected_arrival < 0.18 {
            continue;
        }
        results.push(ValueFieldRawTarget {
            target: candidate.target,
            arrival: expected_arrival.max(0.42),
            tactical_space_prior: candidate.score,
            tactical_space_value: candidate.position_value,
            tactical_space_visibility: candidate.visibility,
            expected_arrival_confidence: expected_arrival,
            expected_arrival_fit: arrival_fit,
        });
    }
    results
}

fn value_field_raw_targets_into(
    input: &ValueFieldTargetsInput<'_>,
    output: &mut [ValueFieldRawTarget],
) -> usize {
    assert!(
        output.len() >= input.generic_candidates.len(),
        "value-field target output buffer is too small"
    );
    let role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let role_fit = crate::physics::smoothstep(0.38, 0.76, role_progress)
        * if input.is_defender { 0.55 } else { 1.0 };
    let mut count = 0;
    for candidate in input.generic_candidates {
        let goal_fit = if let Some(goal_target) = input.receiver_goal_target {
            1.0 - distance(goal_target, candidate.target) / 18.0
        } else {
            0.0
        };
        let arrival_fit = 0.0_f64
            .max(1.0 - distance(input.receiver.pos, candidate.target) / 28.0)
            .max(1.0 - distance(input.receiver.target_pos, candidate.target) / 24.0)
            .max(1.0 - distance(input.receiver.tactical_anchor, candidate.target) / 22.0)
            .max(goal_fit);
        let expected_arrival =
            (candidate.score * (0.30 + 0.48 * arrival_fit + 0.22 * role_fit) * 1.35)
                .clamp(0.0, 1.0);
        if expected_arrival < 0.18 {
            continue;
        }
        output[count] = ValueFieldRawTarget {
            target: candidate.target,
            arrival: expected_arrival.max(0.42),
            tactical_space_prior: candidate.score,
            tactical_space_value: candidate.position_value,
            tactical_space_visibility: candidate.visibility,
            expected_arrival_confidence: expected_arrival,
            expected_arrival_fit: arrival_fit,
        };
        count += 1;
    }
    count
}

pub fn stale_release_targets(input: &StaleReleaseTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let mut targets = Vec::new();
    if input.low_visibility
        || input.consecutive_carries < 3
        || carrier_progress <= 0.62
        || input.receiver.is_defender
    {
        return targets;
    }
    let outlet_dist = distance(input.receiver.pos, input.passer_pos);
    if outlet_dist <= 4.0 || outlet_dist >= 34.0 {
        return targets;
    }

    let stale_release = ((input.consecutive_carries - 2) as f64 / 4.0).min(1.0);
    let support_weight = if input.receiver.is_midfielder || input.receiver.is_wide {
        1.0
    } else {
        0.72
    };
    let outlet_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.35;
    let outlet_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.35;
    targets.push(RawPassTarget {
        target: pitch_clamp((outlet_x, outlet_y), input.pitch_length, input.pitch_width),
        arrival: 0.86 * support_weight,
    });
    targets.push(RawPassTarget {
        target: input.receiver.pos,
        arrival: 0.90 * support_weight,
    });

    let lateral_sign = if input.receiver.pos.1 >= input.passer_pos.1 {
        1.0
    } else {
        -1.0
    };
    let release_depth = 4.0 + 6.0 * stale_release;
    let release_width =
        ((input.receiver.pos.1 - input.passer_pos.1).abs() * 0.50 + 4.0).clamp(4.0, 12.0);
    let release_x = input.passer_pos.0 - forward_dir * release_depth;
    let release_y = input.passer_pos.1 + lateral_sign * release_width;
    if distance((release_x, release_y), input.receiver.pos) < 28.0 {
        targets.push(RawPassTarget {
            target: pitch_clamp(
                (release_x, release_y),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: 0.80 * support_weight,
        });
    }

    let anchor_x = input.receiver.tactical_anchor.0 * 0.55 + input.receiver.pos.0 * 0.45;
    let anchor_y = input.receiver.tactical_anchor.1 * 0.70 + input.receiver.pos.1 * 0.30;
    if distance((anchor_x, anchor_y), input.passer_pos) < 34.0 {
        targets.push(RawPassTarget {
            target: pitch_clamp((anchor_x, anchor_y), input.pitch_length, input.pitch_width),
            arrival: 0.78 * support_weight,
        });
    }
    targets
}

fn stale_release_targets_into(
    input: &StaleReleaseTargetsInput,
    output: &mut [RawPassTarget],
) -> usize {
    assert!(
        output.len() >= MAX_STALE_RELEASE_TARGETS,
        "stale-release target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    if input.low_visibility
        || input.consecutive_carries < 3
        || carrier_progress <= 0.62
        || input.receiver.is_defender
    {
        return 0;
    }
    let outlet_dist = distance(input.receiver.pos, input.passer_pos);
    if outlet_dist <= 4.0 || outlet_dist >= 34.0 {
        return 0;
    }

    let stale_release = ((input.consecutive_carries - 2) as f64 / 4.0).min(1.0);
    let support_weight = if input.receiver.is_midfielder || input.receiver.is_wide {
        1.0
    } else {
        0.72
    };
    let outlet_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.35;
    let outlet_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.35;
    let mut count = 0;
    output[count] = RawPassTarget {
        target: pitch_clamp((outlet_x, outlet_y), input.pitch_length, input.pitch_width),
        arrival: 0.86 * support_weight,
    };
    count += 1;
    output[count] = RawPassTarget {
        target: input.receiver.pos,
        arrival: 0.90 * support_weight,
    };
    count += 1;

    let lateral_sign = if input.receiver.pos.1 >= input.passer_pos.1 {
        1.0
    } else {
        -1.0
    };
    let release_depth = 4.0 + 6.0 * stale_release;
    let release_width =
        ((input.receiver.pos.1 - input.passer_pos.1).abs() * 0.50 + 4.0).clamp(4.0, 12.0);
    let release_x = input.passer_pos.0 - forward_dir * release_depth;
    let release_y = input.passer_pos.1 + lateral_sign * release_width;
    if distance((release_x, release_y), input.receiver.pos) < 28.0 {
        output[count] = RawPassTarget {
            target: pitch_clamp(
                (release_x, release_y),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: 0.80 * support_weight,
        };
        count += 1;
    }

    let anchor_x = input.receiver.tactical_anchor.0 * 0.55 + input.receiver.pos.0 * 0.45;
    let anchor_y = input.receiver.tactical_anchor.1 * 0.70 + input.receiver.pos.1 * 0.30;
    if distance((anchor_x, anchor_y), input.passer_pos) < 34.0 {
        output[count] = RawPassTarget {
            target: pitch_clamp((anchor_x, anchor_y), input.pitch_length, input.pitch_width),
            arrival: 0.78 * support_weight,
        };
        count += 1;
    }
    count
}

pub fn layoff_targets(input: &LayoffTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let mut targets = Vec::new();
    if input.low_visibility || carrier_progress <= 0.80 || input.receiver.is_defender {
        return targets;
    }
    let side_sign = if input.receiver.tactical_anchor.1 >= input.pitch_width / 2.0 {
        1.0
    } else {
        -1.0
    };
    let raw_targets = [
        (
            input.passer_pos.0 - forward_dir * 5.0,
            input.pitch_width / 2.0,
            0.76,
        ),
        (
            input.passer_pos.0 - forward_dir * 7.0,
            input.passer_pos.1 + side_sign * 5.0,
            0.70,
        ),
        (
            input.passer_pos.0 - forward_dir * 9.0,
            input.receiver.tactical_anchor.1 * 0.45 + input.pitch_width / 2.0 * 0.55,
            0.66,
        ),
    ];
    for (x, y, arrival) in raw_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 34.0 {
            targets.push(RawPassTarget { target, arrival });
        }
    }
    targets
}

fn layoff_targets_into(input: &LayoffTargetsInput, output: &mut [RawPassTarget]) -> usize {
    assert!(
        output.len() >= MAX_LAYOFF_TARGETS,
        "layoff target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    if input.low_visibility || carrier_progress <= 0.80 || input.receiver.is_defender {
        return 0;
    }
    let side_sign = if input.receiver.tactical_anchor.1 >= input.pitch_width / 2.0 {
        1.0
    } else {
        -1.0
    };
    let raw_targets = [
        (
            input.passer_pos.0 - forward_dir * 5.0,
            input.pitch_width / 2.0,
            0.76,
        ),
        (
            input.passer_pos.0 - forward_dir * 7.0,
            input.passer_pos.1 + side_sign * 5.0,
            0.70,
        ),
        (
            input.passer_pos.0 - forward_dir * 9.0,
            input.receiver.tactical_anchor.1 * 0.45 + input.pitch_width / 2.0 * 0.55,
            0.66,
        ),
    ];
    let mut count = 0;
    for (x, y, arrival) in raw_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 34.0 {
            output[count] = RawPassTarget { target, arrival };
            count += 1;
        }
    }
    count
}

pub fn second_line_targets(input: &SecondLineTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let receiver_base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length
    };
    let receiver_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let second_line_role = (0.42..=0.68).contains(&receiver_base_progress)
        && !input.receiver.is_defender
        && receiver_progress_hint > 0.60;
    if input.low_visibility || carrier_progress <= 0.68 || !second_line_role {
        return Vec::new();
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let arc_x = goal_side_x - forward_dir * 24.0;
    let support_x =
        input.receiver.tactical_anchor.0 * 0.42 + input.receiver.target_pos.0 * 0.26 + arc_x * 0.32;
    let support_y = input.receiver.tactical_anchor.1 * 0.40
        + input.receiver.target_pos.1 * 0.20
        + input.pitch_width / 2.0 * 0.40;
    let target = pitch_clamp(
        (support_x, support_y),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(target, input.receiver.pos) < 30.0 {
        vec![RawPassTarget {
            target,
            arrival: 0.72,
        }]
    } else {
        Vec::new()
    }
}

fn second_line_targets_into(input: &SecondLineTargetsInput, output: &mut [RawPassTarget]) -> usize {
    assert!(
        output.len() >= MAX_SECOND_LINE_TARGETS,
        "second-line target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let receiver_base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length
    };
    let receiver_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let second_line_role = (0.42..=0.68).contains(&receiver_base_progress)
        && !input.receiver.is_defender
        && receiver_progress_hint > 0.60;
    if input.low_visibility || carrier_progress <= 0.68 || !second_line_role {
        return 0;
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let arc_x = goal_side_x - forward_dir * 24.0;
    let support_x =
        input.receiver.tactical_anchor.0 * 0.42 + input.receiver.target_pos.0 * 0.26 + arc_x * 0.32;
    let support_y = input.receiver.tactical_anchor.1 * 0.40
        + input.receiver.target_pos.1 * 0.20
        + input.pitch_width / 2.0 * 0.40;
    let target = pitch_clamp(
        (support_x, support_y),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(target, input.receiver.pos) >= 30.0 {
        return 0;
    }
    output[0] = RawPassTarget {
        target,
        arrival: 0.72,
    };
    1
}

pub fn box_delivery_targets(input: &BoxDeliveryTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let carrier_width =
        (input.passer_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    if input.low_visibility
        || carrier_progress <= 0.68
        || carrier_width <= 0.34
        || input.receiver.is_defender
    {
        return Vec::new();
    }

    let target_role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    if target_role_progress <= 0.54 {
        return Vec::new();
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let box_edge_x = goal_side_x - forward_dir * 15.5;
    let raw_cutback_x = input.passer_pos.0 + forward_dir * 7.0;
    let cutback_x = if input.attacking_right {
        box_edge_x.min(raw_cutback_x)
    } else {
        box_edge_x.max(raw_cutback_x)
    };
    let near_box_x = goal_side_x - forward_dir * 12.0;
    let center_y = input.pitch_width / 2.0;
    let carrier_side = if input.passer_pos.1 >= center_y {
        1.0
    } else {
        -1.0
    };
    let delivery_targets = [
        (cutback_x, center_y, 0.66),
        (
            cutback_x,
            center_y + carrier_side * input.pitch_width * 0.10,
            0.62,
        ),
        (near_box_x, center_y, 0.54),
        (
            near_box_x,
            center_y + carrier_side * input.pitch_width * 0.12,
            0.50,
        ),
    ];
    let mut targets = Vec::new();
    for (x, y, arrival) in delivery_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 32.0 {
            targets.push(RawPassTarget { target, arrival });
        }
    }

    let runner_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.65;
    let runner_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.65;
    let runner_target = pitch_clamp(
        (runner_x, runner_y + (center_y - runner_y) * 0.35),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(runner_target, input.receiver.pos) < 18.0 {
        targets.push(RawPassTarget {
            target: runner_target,
            arrival: 0.74,
        });
    }
    targets
}

fn box_delivery_targets_into(
    input: &BoxDeliveryTargetsInput,
    output: &mut [RawPassTarget],
) -> usize {
    assert!(
        output.len() >= MAX_BOX_DELIVERY_TARGETS,
        "box-delivery target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let carrier_width =
        (input.passer_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    if input.low_visibility
        || carrier_progress <= 0.68
        || carrier_width <= 0.34
        || input.receiver.is_defender
    {
        return 0;
    }

    let target_role_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    if target_role_progress <= 0.54 {
        return 0;
    }

    let goal_side_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let box_edge_x = goal_side_x - forward_dir * 15.5;
    let raw_cutback_x = input.passer_pos.0 + forward_dir * 7.0;
    let cutback_x = if input.attacking_right {
        box_edge_x.min(raw_cutback_x)
    } else {
        box_edge_x.max(raw_cutback_x)
    };
    let near_box_x = goal_side_x - forward_dir * 12.0;
    let center_y = input.pitch_width / 2.0;
    let carrier_side = if input.passer_pos.1 >= center_y {
        1.0
    } else {
        -1.0
    };
    let delivery_targets = [
        (cutback_x, center_y, 0.66),
        (
            cutback_x,
            center_y + carrier_side * input.pitch_width * 0.10,
            0.62,
        ),
        (near_box_x, center_y, 0.54),
        (
            near_box_x,
            center_y + carrier_side * input.pitch_width * 0.12,
            0.50,
        ),
    ];
    let mut count = 0;
    for (x, y, arrival) in delivery_targets {
        let target = pitch_clamp((x, y), input.pitch_length, input.pitch_width);
        if distance(target, input.receiver.pos) < 32.0 {
            output[count] = RawPassTarget { target, arrival };
            count += 1;
        }
    }

    let runner_x =
        input.receiver.pos.0 + (input.receiver.target_pos.0 - input.receiver.pos.0) * 0.65;
    let runner_y =
        input.receiver.pos.1 + (input.receiver.target_pos.1 - input.receiver.pos.1) * 0.65;
    let runner_target = pitch_clamp(
        (runner_x, runner_y + (center_y - runner_y) * 0.35),
        input.pitch_length,
        input.pitch_width,
    );
    if distance(runner_target, input.receiver.pos) < 18.0 {
        output[count] = RawPassTarget {
            target: runner_target,
            arrival: 0.74,
        };
        count += 1;
    }
    count
}

pub fn delivery_space_targets(input: &DeliverySpaceTargetsInput) -> Vec<RawPassTarget> {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let receiver_forward = 0.0_f64
        .max((input.receiver.tactical_anchor.0 - input.receiver.pos.0) * forward_dir)
        .max((input.receiver.target_pos.0 - input.receiver.pos.0) * forward_dir);
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let target_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let delivery_pressure = carrier_progress.max(target_progress_hint);
    let central_pull = input.pitch_width / 2.0 - input.receiver.pos.1;
    if input.low_visibility
        || delivery_pressure <= 0.70
        || !(receiver_forward > 0.5 || target_progress_hint > 0.76)
    {
        return Vec::new();
    }

    let mut targets = Vec::new();
    for (depth_scale, center_scale, arrival_base) in
        [(0.45, 0.35, 0.74), (0.75, 0.55, 0.66), (1.05, 0.72, 0.58)]
    {
        let run_depth = 3.0 + (receiver_forward + 6.0).min(12.0) * depth_scale;
        targets.push(RawPassTarget {
            target: pitch_clamp(
                (
                    input.receiver.pos.0 + forward_dir * run_depth,
                    input.receiver.pos.1 + central_pull * center_scale,
                ),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: arrival_base,
        });
    }

    if carrier_progress > 0.82
        && (input.passer_pos.1 - input.pitch_width / 2.0).abs() > input.pitch_width * 0.14
    {
        for (depth_scale, center_scale, arrival_base) in [(0.20, 0.58, 0.70), (-0.15, 0.70, 0.64)] {
            let support_depth = (receiver_forward + 4.0).min(9.0) * depth_scale;
            let mut target_x = input.receiver.pos.0 + forward_dir * support_depth;
            target_x = if input.attacking_right {
                target_x.min(input.passer_pos.0 - 0.5)
            } else {
                target_x.max(input.passer_pos.0 + 0.5)
            };
            targets.push(RawPassTarget {
                target: pitch_clamp(
                    (target_x, input.receiver.pos.1 + central_pull * center_scale),
                    input.pitch_length,
                    input.pitch_width,
                ),
                arrival: arrival_base,
            });
        }
    }
    targets
}

fn delivery_space_targets_into(
    input: &DeliverySpaceTargetsInput,
    output: &mut [RawPassTarget],
) -> usize {
    assert!(
        output.len() >= MAX_DELIVERY_SPACE_TARGETS,
        "delivery-space target output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let receiver_forward = 0.0_f64
        .max((input.receiver.tactical_anchor.0 - input.receiver.pos.0) * forward_dir)
        .max((input.receiver.target_pos.0 - input.receiver.pos.0) * forward_dir);
    let carrier_progress = if input.attacking_right {
        input.passer_pos.0 / input.pitch_length
    } else {
        (input.pitch_length - input.passer_pos.0) / input.pitch_length
    };
    let target_progress_hint = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    };
    let delivery_pressure = carrier_progress.max(target_progress_hint);
    let central_pull = input.pitch_width / 2.0 - input.receiver.pos.1;
    if input.low_visibility
        || delivery_pressure <= 0.70
        || !(receiver_forward > 0.5 || target_progress_hint > 0.76)
    {
        return 0;
    }

    let mut count = 0;
    for (depth_scale, center_scale, arrival_base) in
        [(0.45, 0.35, 0.74), (0.75, 0.55, 0.66), (1.05, 0.72, 0.58)]
    {
        let run_depth = 3.0 + (receiver_forward + 6.0).min(12.0) * depth_scale;
        output[count] = RawPassTarget {
            target: pitch_clamp(
                (
                    input.receiver.pos.0 + forward_dir * run_depth,
                    input.receiver.pos.1 + central_pull * center_scale,
                ),
                input.pitch_length,
                input.pitch_width,
            ),
            arrival: arrival_base,
        };
        count += 1;
    }

    if carrier_progress > 0.82
        && (input.passer_pos.1 - input.pitch_width / 2.0).abs() > input.pitch_width * 0.14
    {
        for (depth_scale, center_scale, arrival_base) in [(0.20, 0.58, 0.70), (-0.15, 0.70, 0.64)] {
            let support_depth = (receiver_forward + 4.0).min(9.0) * depth_scale;
            let mut target_x = input.receiver.pos.0 + forward_dir * support_depth;
            target_x = if input.attacking_right {
                target_x.min(input.passer_pos.0 - 0.5)
            } else {
                target_x.max(input.passer_pos.0 + 0.5)
            };
            output[count] = RawPassTarget {
                target: pitch_clamp(
                    (target_x, input.receiver.pos.1 + central_pull * center_scale),
                    input.pitch_length,
                    input.pitch_width,
                ),
                arrival: arrival_base,
            };
            count += 1;
        }
    }
    count
}

pub fn receiver_spatial_candidates(
    input: &ReceiverSpatialCandidatesInput<'_>,
) -> Vec<ReceiverSpatialCandidate> {
    let mut candidates = [EMPTY_RECEIVER_SPATIAL_CANDIDATE; MAX_RECEIVER_SPATIAL_CANDIDATES];
    let candidate_count = receiver_spatial_candidates_into(input, &mut candidates);
    candidates[..candidate_count].to_vec()
}

fn receiver_spatial_candidates_into(
    input: &ReceiverSpatialCandidatesInput<'_>,
    candidates: &mut [ReceiverSpatialCandidate],
) -> usize {
    assert!(
        candidates.len() >= MAX_RECEIVER_SPATIAL_CANDIDATES,
        "receiver spatial candidate output buffer is too small"
    );
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let tm_anchor_progress = if input.attacking_right {
        input.receiver.tactical_anchor.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver.tactical_anchor.0) / input.pitch_length
    }
    .clamp(0.0, 1.0);
    let tm_width_factor = ((input.receiver.tactical_anchor.1 - input.pitch_width / 2.0).abs()
        / (input.pitch_width / 2.0))
        .min(1.0);
    let search_radius = 6.0 + 10.0 * tm_anchor_progress + 3.0 * tm_width_factor;
    let mut candidate_count = 0;

    if !input.low_visibility {
        let sample_angles = [
            -150.0_f64, -105.0, -60.0, -25.0, 0.0, 25.0, 60.0, 105.0, 150.0,
        ];
        let sample_radii = [search_radius * 0.55, search_radius];
        for center in [
            input.receiver.pos,
            input.receiver.target_pos,
            input.receiver.tactical_anchor,
        ] {
            for radius in sample_radii {
                for angle_deg in sample_angles {
                    let angle = angle_deg.to_radians();
                    let pos = pitch_clamp(
                        (
                            center.0 + angle.cos() * radius * forward_dir,
                            center.1 + angle.sin() * radius,
                        ),
                        input.pitch_length,
                        input.pitch_width,
                    );
                    let point_visibility = input.vision.confidence(input.passer_pos, pos);
                    if point_visibility <= 0.0 {
                        continue;
                    }
                    if is_offside_position(
                        pos,
                        input.attacking_right,
                        input.offside_line,
                        input.pitch_length,
                        Some(input.passer_pos.0),
                    ) {
                        continue;
                    }
                    let d_from_receiver = distance(pos, input.receiver.pos);
                    if d_from_receiver > search_radius * 1.50 {
                        continue;
                    }
                    let pv = position_value(&PositionValueInput {
                        x: pos.0,
                        y: pos.1,
                        pitch_length: input.pitch_length,
                        pitch_width: input.pitch_width,
                        attacking_right: input.attacking_right,
                        opponent_positions: input.opponent_positions,
                        teammate_positions: input.teammate_positions,
                        skip_teammate_index: None,
                        runner_formation_pos: Some(input.receiver.tactical_anchor),
                    });
                    let receiver_arrival =
                        (1.0 - d_from_receiver / (search_radius * 1.65)).max(0.25);
                    let score = pv * receiver_arrival * (0.55 + 0.45 * point_visibility);
                    candidates[candidate_count] = ReceiverSpatialCandidate {
                        score,
                        target: pos,
                        receiver_arrival,
                        position_value: pv,
                        point_visibility,
                    };
                    candidate_count += 1;
                }
            }
        }

        if let Some(front_center) = input.front_center {
            if tm_anchor_progress > 0.50 {
                for angle_deg in [-60.0_f64, -25.0, 0.0, 25.0, 60.0] {
                    let angle = angle_deg.to_radians();
                    let radius = search_radius * 0.85;
                    let pos = pitch_clamp(
                        (
                            front_center.0 + angle.cos() * radius * forward_dir,
                            front_center.1 + angle.sin() * radius,
                        ),
                        input.pitch_length,
                        input.pitch_width,
                    );
                    let point_visibility = input.vision.confidence(input.passer_pos, pos);
                    if point_visibility <= 0.0 {
                        continue;
                    }
                    if is_offside_position(
                        pos,
                        input.attacking_right,
                        input.offside_line,
                        input.pitch_length,
                        Some(input.passer_pos.0),
                    ) {
                        continue;
                    }
                    let d_from_receiver = distance(pos, input.receiver.pos);
                    let pv = position_value(&PositionValueInput {
                        x: pos.0,
                        y: pos.1,
                        pitch_length: input.pitch_length,
                        pitch_width: input.pitch_width,
                        attacking_right: input.attacking_right,
                        opponent_positions: input.opponent_positions,
                        teammate_positions: input.teammate_positions,
                        skip_teammate_index: None,
                        runner_formation_pos: Some(input.receiver.tactical_anchor),
                    });
                    let receiver_arrival =
                        (1.0 - d_from_receiver / (search_radius * 1.90)).max(0.22);
                    let score = pv * receiver_arrival * (0.55 + 0.45 * point_visibility);
                    candidates[candidate_count] = ReceiverSpatialCandidate {
                        score,
                        target: pos,
                        receiver_arrival,
                        position_value: pv,
                        point_visibility,
                    };
                    candidate_count += 1;
                }
            }
        }
    }

    candidates[..candidate_count].sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    candidate_count.min(3)
}

fn raw_pass_prevalue_motion_context<'a>(
    receiver: PassRiskPlayer,
    opponents: &[PassRiskPlayer],
    player_max_speed: f64,
    player_min_speed: f64,
    opponent_motion: &'a mut [RawPassOpponentMotion],
) -> Option<RawPassPreValueMotionContext<'a>> {
    let opponent_motion = opponent_motion.get_mut(..opponents.len())?;
    for (motion, opponent) in opponent_motion.iter_mut().zip(opponents) {
        *motion = RawPassOpponentMotion {
            speed: crate::physics::player_speed(opponent.speed, player_max_speed, player_min_speed),
            is_goalkeeper: opponent.is_goalkeeper,
        };
    }
    Some(RawPassPreValueMotionContext {
        receiver_speed: crate::physics::player_speed(
            receiver.speed,
            player_max_speed,
            player_min_speed,
        ),
        opponent_motion,
    })
}

fn raw_pass_receiver_pressure_reuse(
    risk_opponents: &[PassRiskPlayer],
    opponent_positions: &[(f64, f64)],
) -> Option<RawPassReceiverPressureReuse> {
    if risk_opponents.len() == opponent_positions.len()
        && risk_opponents
            .iter()
            .zip(opponent_positions)
            .all(|(risk_opponent, &opponent_position)| risk_opponent.pos == opponent_position)
    {
        return Some(RawPassReceiverPressureReuse::AllOpponents);
    }

    let mut opponent_position_index = 0;
    for risk_opponent in risk_opponents {
        if risk_opponent.is_goalkeeper {
            continue;
        }
        let opponent_position = opponent_positions.get(opponent_position_index)?;
        if risk_opponent.pos != *opponent_position {
            return None;
        }
        opponent_position_index += 1;
    }
    (opponent_position_index == opponent_positions.len())
        .then_some(RawPassReceiverPressureReuse::OutfieldOpponents)
}

pub fn evaluate_raw_pass_target_prevalue(
    input: &RawPassPreValueInput<'_>,
) -> RawPassPreValueOutput {
    evaluate_raw_pass_target_prevalue_with_motion_context(input, None)
}

fn evaluate_raw_pass_target_prevalue_with_motion_context(
    input: &RawPassPreValueInput<'_>,
    motion_context: Option<&RawPassPreValueMotionContext<'_>>,
) -> RawPassPreValueOutput {
    evaluate_raw_pass_target_prevalue_with_motion_context_and_geometry(input, motion_context, false)
        .0
}

fn evaluate_raw_pass_target_prevalue_with_motion_context_and_geometry(
    input: &RawPassPreValueInput<'_>,
    motion_context: Option<&RawPassPreValueMotionContext<'_>>,
    collect_receiver_pressure: bool,
) -> (RawPassPreValueOutput, Option<RawPassPreValueGeometry>) {
    let mut receiver_arrival = input.initial_receiver_arrival;
    let d = distance(input.passer_pos, input.target);
    let receiver_to_target_distance = distance(input.receiver.pos, input.target);
    let target_kind_space = receiver_to_target_distance > 4.0;
    let invalid = RawPassPreValueOutput {
        valid: false,
        receiver_arrival,
        base_accuracy: 0.0,
        continuity: 0.0,
        perception: 0.0,
        perception_multiplier: 0.0,
        arrival_margin: 0.0,
        receiver_time: 0.0,
        defender_time: f64::INFINITY,
        defender_first_risk: 0.0,
        target_occupation_risk: 0.0,
        nearest_teammate_to_target: 0.0,
        nearest_opp_to_target: 0.0,
        box_space_pressure: 0.0,
        goal_target_fit: 0.0,
        is_long: false,
        target_kind_space,
        distance: d,
    };
    if d < 3.0 || d > 55.0 {
        return (invalid, None);
    }
    let perception = input.vision.confidence(input.passer_pos, input.target);
    if perception <= 0.0 && target_kind_space {
        return (invalid, None);
    }
    if is_offside_position(
        input.target,
        input.attacking_right,
        input.offside_line,
        input.pitch_length,
        Some(input.passer_pos.0),
    ) {
        receiver_arrival *= 0.25;
    }

    let tm_speed = motion_context.map_or_else(
        || {
            crate::physics::player_speed(
                input.receiver.speed,
                input.player_max_speed,
                input.player_min_speed,
            )
        },
        |context| context.receiver_speed,
    );
    let receiver_time = receiver_to_target_distance / tm_speed.max(0.1);
    let mut defender_time = f64::INFINITY;
    let mut nearest_opp_to_target = f64::INFINITY;
    let mut all_opponents_receiver_pressure = 0.0;
    let mut outfield_opponents_receiver_pressure = 0.0;
    if let Some(context) = motion_context {
        debug_assert_eq!(context.opponent_motion.len(), input.opponents.len());
        for (opp, motion) in input.opponents.iter().zip(context.opponent_motion) {
            let opponent_to_target_distance = distance(opp.pos, input.target);
            nearest_opp_to_target = nearest_opp_to_target.min(opponent_to_target_distance);
            if collect_receiver_pressure && opponent_to_target_distance < 12.0 {
                let pressure_contribution = 1.0 - opponent_to_target_distance / 12.0;
                all_opponents_receiver_pressure += pressure_contribution;
                if !opp.is_goalkeeper {
                    outfield_opponents_receiver_pressure += pressure_contribution;
                }
            }
            let mut opp_speed = motion.speed;
            if motion.is_goalkeeper {
                let goal_x = if input.attacking_right {
                    input.pitch_length
                } else {
                    0.0
                };
                let goal_dist = (input.target.0 - goal_x).abs();
                if goal_dist > 24.0 {
                    continue;
                }
                opp_speed *= 1.18;
            }
            defender_time = defender_time.min(opponent_to_target_distance / opp_speed.max(0.1));
        }
    } else {
        for opp in input.opponents {
            let opponent_to_target_distance = distance(opp.pos, input.target);
            nearest_opp_to_target = nearest_opp_to_target.min(opponent_to_target_distance);
            if collect_receiver_pressure && opponent_to_target_distance < 12.0 {
                let pressure_contribution = 1.0 - opponent_to_target_distance / 12.0;
                all_opponents_receiver_pressure += pressure_contribution;
                if !opp.is_goalkeeper {
                    outfield_opponents_receiver_pressure += pressure_contribution;
                }
            }
            let mut opp_speed = crate::physics::player_speed(
                opp.speed,
                input.player_max_speed,
                input.player_min_speed,
            );
            if opp.is_goalkeeper {
                let goal_x = if input.attacking_right {
                    input.pitch_length
                } else {
                    0.0
                };
                let goal_dist = (input.target.0 - goal_x).abs();
                if goal_dist > 24.0 {
                    continue;
                }
                opp_speed *= 1.18;
            }
            defender_time = defender_time.min(opponent_to_target_distance / opp_speed.max(0.1));
        }
    }
    let nearest_teammate_to_target = input
        .teammates
        .iter()
        .filter(|tm| tm.index != input.passer_index && !tm.is_goalkeeper)
        .map(|tm| distance(tm.pos, input.target))
        .fold(receiver_to_target_distance, f64::min);

    let arrival_margin = defender_time - receiver_time;
    if arrival_margin < 0.0 {
        receiver_arrival *= (1.0 + arrival_margin / 3.5).max(0.10);
    } else {
        receiver_arrival *= 0.78 + 0.22 * (arrival_margin / 4.0).min(1.0);
    }

    let defender_first_risk = crate::physics::smoothstep(0.2, 3.8, -arrival_margin);
    let target_occupation_risk =
        crate::physics::smoothstep(0.6, 4.0, nearest_teammate_to_target - nearest_opp_to_target)
            .max(
                (1.0 - crate::physics::smoothstep(0.8, 3.2, nearest_opp_to_target))
                    * crate::physics::smoothstep(2.5, 7.0, nearest_teammate_to_target),
            );
    let target_progress_for_risk = if input.attacking_right {
        input.target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality_for_risk = 1.0
        - ((input.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let box_space_pressure = crate::physics::smoothstep(0.78, 0.90, target_progress_for_risk)
        * crate::physics::smoothstep(0.45, 0.85, target_centrality_for_risk)
        * crate::physics::smoothstep(4.0, 16.0, receiver_to_target_distance);
    if box_space_pressure > 0.0 {
        let required_margin = 0.8 + 1.8 * box_space_pressure;
        let margin_factor = ((arrival_margin + 1.2) / required_margin).clamp(0.24, 1.0);
        receiver_arrival *= 1.0 - box_space_pressure * (1.0 - margin_factor);
    }
    if defender_first_risk > 0.0 {
        receiver_arrival *= 1.0 - 0.62 * defender_first_risk;
    }
    if target_occupation_risk > 0.0 {
        receiver_arrival *= 1.0 - 0.72 * target_occupation_risk;
    }

    let is_long = d > 30.0;
    let passing = if is_long {
        input.long_passing
    } else {
        input.short_passing
    } / 100.0;
    let base = if is_long {
        input.long_pass_base_success
    } else {
        input.short_pass_base_success
    };
    let technical_accuracy = base + (1.0 - base) * passing;
    let distance_factor = if is_long {
        (1.0 - (d - 30.0).max(0.0) / 60.0).max(0.72)
    } else {
        (1.0 - (d - 8.0).max(0.0) / 100.0).max(0.82)
    };
    let base_accuracy = technical_accuracy * distance_factor;

    let mut goal_target_fit = 0.0;
    if let Some(goal_target) = input.receiver_goal_target {
        goal_target_fit =
            (1.0 - distance(input.target, goal_target) / 14.0).max(0.0) * input.receiver_goal_fit;
        if goal_target_fit > 0.0 {
            receiver_arrival = (receiver_arrival * (1.0 + 0.10 * goal_target_fit)).min(1.0);
        }
    }

    let mut continuity = if receiver_to_target_distance <= 4.0 {
        0.075
    } else {
        0.045
    };
    continuity += 0.065 * goal_target_fit * (input.receiver_goal_value * 2.4).clamp(0.0, 1.0);
    let perception_floor = if target_kind_space { 0.0 } else { 0.35 };
    let perception_multiplier = 0.48
        + 0.52
            * perception
                .max(perception_floor)
                .max(input.receiver_visibility * 0.55);
    receiver_arrival *= perception_multiplier;

    (
        RawPassPreValueOutput {
            valid: true,
            receiver_arrival,
            base_accuracy,
            continuity,
            perception,
            perception_multiplier,
            arrival_margin,
            receiver_time,
            defender_time,
            defender_first_risk,
            target_occupation_risk,
            nearest_teammate_to_target,
            nearest_opp_to_target,
            box_space_pressure,
            goal_target_fit,
            is_long,
            target_kind_space,
            distance: d,
        },
        collect_receiver_pressure.then_some(RawPassPreValueGeometry {
            all_opponents_receiver_pressure: (all_opponents_receiver_pressure * 0.35)
                .clamp(0.0, 1.0),
            outfield_opponents_receiver_pressure: (outfield_opponents_receiver_pressure * 0.35)
                .clamp(0.0, 1.0),
        }),
    )
}

pub fn score_raw_pass_target(input: &RawPassValueInput<'_>) -> RawPassValueOutput {
    let batch_context = RawPassBatchValueContext {
        passer: passer_pass_value_context(&PasserPassValueContextInput {
            tick: input.tick,
            passer_index: input.prevalue.passer_index,
            passer_team_home: input.passer_team_home,
            passer_pos: input.prevalue.passer_pos,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_consecutive_carries: input.passer_consecutive_carries,
            opponent_positions: input.opponent_positions,
            pitch_length: input.prevalue.pitch_length,
            pitch_width: input.prevalue.pitch_width,
            attacking_right: input.prevalue.attacking_right,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            gk_attributes: input.gk_attributes,
            gk_pos: input.gk_pos,
            contest_defenders: input.contest_defenders,
            current_value: input.current_value,
            shot_quality_cache: input.shot_quality_cache,
        }),
        receive: None,
    };
    score_raw_pass_target_with_batch_context(input, &batch_context, None, None)
}

fn score_raw_pass_target_with_batch_context(
    input: &RawPassValueInput<'_>,
    batch_context: &RawPassBatchValueContext<'_>,
    motion_context: Option<&RawPassPreValueMotionContext<'_>>,
    receiver_pressure_reuse: Option<RawPassReceiverPressureReuse>,
) -> RawPassValueOutput {
    let (pre, geometry) = evaluate_raw_pass_target_prevalue_with_motion_context_and_geometry(
        &input.prevalue,
        motion_context,
        receiver_pressure_reuse.is_some(),
    );
    if !pre.valid {
        return RawPassValueOutput {
            valid: false,
            score: 0.0,
            success_prob: 0.0,
            risk_cost: 0.0,
            current_value: input.current_value,
            effective_current_value: input.current_value,
            delta: 0.0,
            after_value: 0.0,
            after_direct_xg: 0.0,
            effective_delta: 0.0,
            progress_gain: 0.0,
            continuity: 0.0,
            lane_risk: 0.0,
            receiver_pressure: 0.0,
            turnover_consequence: 0.0,
            high_threat_space: 0.0,
            final_third_combination: 0.0,
            second_line_arrival_value: 0.0,
            second_line_cutback_value: 0.0,
            layoff_support_value: 0.0,
            short_combination_value: 0.0,
            layoff_retention_value: 0.0,
            adjusted_score: 0.0,
            receiver_arrival: pre.receiver_arrival,
            base_accuracy: pre.base_accuracy,
            defender_first_risk: pre.defender_first_risk,
            target_occupation_risk: pre.target_occupation_risk,
            goal_target_fit: pre.goal_target_fit,
            is_long: pre.is_long,
            target_kind_space: pre.target_kind_space,
            distance: pre.distance,
            perception: pre.perception,
            perception_multiplier: pre.perception_multiplier,
            arrival_margin: pre.arrival_margin,
            nearest_teammate_to_target: pre.nearest_teammate_to_target,
            nearest_opp_to_target: pre.nearest_opp_to_target,
            box_space_pressure: pre.box_space_pressure,
        };
    }

    let expected_input = ExpectedPassInput {
        tick: input.tick,
        passer_index: input.prevalue.passer_index,
        passer_team_home: input.passer_team_home,
        passer_pos: input.prevalue.passer_pos,
        passer_finishing: input.passer_finishing,
        passer_long_shot: input.passer_long_shot,
        passer_consecutive_carries: input.passer_consecutive_carries,
        receiver_index: input.receiver_index,
        receiver_team_home: input.receiver_team_home,
        receiver_finishing: input.receiver_finishing,
        receiver_long_shot: input.receiver_long_shot,
        receiver_anchor: input.receiver_anchor,
        receiver_base: input.receiver_base,
        receiver_goal_type: input.receiver_goal_type,
        receiver_goal_target: input.receiver_goal_target,
        receiver_goal_value: input.receiver_goal_value,
        target: input.prevalue.target,
        shot_profiles: input.shot_profiles,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.prevalue.pitch_length,
        pitch_width: input.prevalue.pitch_width,
        attacking_right: input.prevalue.attacking_right,
        interception_reach: input.interception_reach,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        current_value: input.current_value,
        base_accuracy: pre.base_accuracy,
        receiver_arrival: pre.receiver_arrival,
        continuity: pre.continuity,
        shot_quality_cache: input.shot_quality_cache,
    };
    let precomputed_receiver_pressure =
        geometry
            .zip(receiver_pressure_reuse)
            .map(|(geometry, reuse)| match reuse {
                RawPassReceiverPressureReuse::AllOpponents => {
                    geometry.all_opponents_receiver_pressure
                }
                RawPassReceiverPressureReuse::OutfieldOpponents => {
                    geometry.outfield_opponents_receiver_pressure
                }
            });
    let value = if let Some(receiver_pressure) = precomputed_receiver_pressure {
        expected_pass_value_with_context_and_precomputed_receiver_pressure(
            &expected_input,
            batch_context.passer,
            batch_context.receive,
            receiver_pressure,
        )
    } else {
        expected_pass_value_with_context(
            &expected_input,
            batch_context.passer,
            batch_context.receive,
        )
    };
    let mut adjusted_score = value.score;
    if pre.defender_first_risk > 0.0 {
        adjusted_score *= 1.0 - 0.58 * pre.defender_first_risk;
    }
    if pre.target_occupation_risk > 0.0 {
        adjusted_score *= 1.0 - 0.68 * pre.target_occupation_risk;
    }

    RawPassValueOutput {
        valid: true,
        score: value.score,
        success_prob: value.success_prob,
        risk_cost: value.risk_cost,
        current_value: value.current_value,
        effective_current_value: value.effective_current_value,
        delta: value.delta,
        after_value: value.after_value,
        after_direct_xg: value.after_direct_xg,
        effective_delta: value.effective_delta,
        progress_gain: value.progress_gain,
        continuity: value.continuity,
        lane_risk: value.lane_risk,
        receiver_pressure: value.receiver_pressure,
        turnover_consequence: value.turnover_consequence,
        high_threat_space: value.high_threat_space,
        final_third_combination: value.final_third_combination,
        second_line_arrival_value: value.second_line_arrival_value,
        second_line_cutback_value: value.second_line_cutback_value,
        layoff_support_value: value.layoff_support_value,
        short_combination_value: value.short_combination_value,
        layoff_retention_value: value.layoff_retention_value,
        adjusted_score,
        receiver_arrival: pre.receiver_arrival,
        base_accuracy: pre.base_accuracy,
        defender_first_risk: pre.defender_first_risk,
        target_occupation_risk: pre.target_occupation_risk,
        goal_target_fit: pre.goal_target_fit,
        is_long: pre.is_long,
        target_kind_space: pre.target_kind_space,
        distance: pre.distance,
        perception: pre.perception,
        perception_multiplier: pre.perception_multiplier,
        arrival_margin: pre.arrival_margin,
        nearest_teammate_to_target: pre.nearest_teammate_to_target,
        nearest_opp_to_target: pre.nearest_opp_to_target,
        box_space_pressure: pre.box_space_pressure,
    }
}

pub fn receiver_pass_candidates_batch(
    input: &ReceiverPassBatchInput<'_>,
) -> Vec<ReceiverPassCandidate> {
    let batch_context = RawPassBatchValueContext {
        passer: passer_pass_value_context(&PasserPassValueContextInput {
            tick: input.tick,
            passer_index: input.passer_index,
            passer_team_home: input.passer_team_home,
            passer_pos: input.passer_pos,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_consecutive_carries: input.passer_consecutive_carries,
            opponent_positions: input.opponent_positions,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            gk_attributes: input.gk_attributes,
            gk_pos: input.gk_pos,
            contest_defenders: input.contest_defenders,
            current_value: input.current_value,
            shot_quality_cache: input.shot_quality_cache,
        }),
        receive: None,
    };
    let mut workspace = ReceiverPassWorkspace::new();
    let candidate_count =
        receiver_pass_candidates_batch_into(input, &mut workspace, &batch_context, None);
    workspace.candidates[..candidate_count].to_vec()
}

fn receiver_pass_candidates_batch_into(
    input: &ReceiverPassBatchInput<'_>,
    workspace: &mut ReceiverPassWorkspace,
    batch_context: &RawPassBatchValueContext<'_>,
    team_value_context: Option<&PassReceiveTeamValueContext>,
) -> usize {
    let ReceiverPassWorkspace {
        target_buffer,
        raw_targets,
        value_field_targets,
        spatial_candidates,
        opponent_motion,
        candidates,
    } = workspace;
    assert!(
        candidates.len() >= MAX_PASS_CANDIDATES_PER_RECEIVER,
        "receiver pass candidate output buffer is too small"
    );
    let base_input = ReceiverBaseTargetsInput {
        passer_pos: input.passer_pos,
        receiver: input.receiver_space,
        receiver_goal: input.receiver_goal,
        vision: input.vision,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
    };
    let base = receiver_base_pass_targets_into(&base_input, target_buffer);
    let receiver_goal_target = input.receiver_goal.map(|goal| goal.target_pos);
    let receiver_goal_value = input.receiver_goal.map(|goal| goal.value).unwrap_or(0.0);
    let receiver_goal_type = input.receiver_goal.map(|goal| goal.goal_type);

    let mut raw_target_count = 0;
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..base.target_count],
    );
    let stale_release_count = stale_release_targets_into(
        &StaleReleaseTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            consecutive_carries: input.passer_consecutive_carries,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        },
        target_buffer,
    );
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..stale_release_count],
    );
    let layoff_count = layoff_targets_into(
        &LayoffTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        },
        target_buffer,
    );
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..layoff_count],
    );
    let second_line_count = second_line_targets_into(
        &SecondLineTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            receiver_base: input.receiver_base,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        },
        target_buffer,
    );
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..second_line_count],
    );
    let box_delivery_count = box_delivery_targets_into(
        &BoxDeliveryTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        },
        target_buffer,
    );
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..box_delivery_count],
    );
    let delivery_space_count = delivery_space_targets_into(
        &DeliverySpaceTargetsInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            low_visibility: base.low_visibility,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
        },
        target_buffer,
    );
    append_raw_pass_targets(
        raw_targets,
        &mut raw_target_count,
        &target_buffer[..delivery_space_count],
    );
    let value_field_count = value_field_raw_targets_into(
        &ValueFieldTargetsInput {
            receiver: input.receiver_space,
            receiver_goal_target,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            is_defender: input.is_receiver_defender,
            generic_candidates: input.generic_candidates,
        },
        value_field_targets,
    );
    assert!(
        raw_targets.len() - raw_target_count >= value_field_count,
        "raw pass target buffer exceeds its fixed capacity"
    );
    for target in &value_field_targets[..value_field_count] {
        raw_targets[raw_target_count] = RawPassTargetMeta {
            target: target.target,
            arrival: target.arrival,
            tactical_space: true,
            tactical_space_prior: target.tactical_space_prior,
            tactical_space_value: target.tactical_space_value,
            tactical_space_visibility: target.tactical_space_visibility,
            expected_arrival_confidence: target.expected_arrival_confidence,
            expected_arrival_fit: target.expected_arrival_fit,
        };
        raw_target_count += 1;
    }
    let spatial_candidate_count = receiver_spatial_candidates_into(
        &ReceiverSpatialCandidatesInput {
            passer_pos: input.passer_pos,
            receiver: input.receiver_space,
            vision: input.vision,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            offside_line: input.offside_line,
            low_visibility: base.low_visibility,
            front_center: input.front_center,
            opponent_positions: input.opponent_positions,
            teammate_positions: input.teammate_xy_positions,
        },
        spatial_candidates,
    );
    assert!(
        raw_targets.len() - raw_target_count >= spatial_candidate_count,
        "raw pass target buffer exceeds its fixed capacity"
    );
    for target in &spatial_candidates[..spatial_candidate_count] {
        raw_targets[raw_target_count] = RawPassTargetMeta {
            target: target.target,
            arrival: target.receiver_arrival,
            tactical_space: false,
            tactical_space_prior: 0.0,
            tactical_space_value: 0.0,
            tactical_space_visibility: 0.0,
            expected_arrival_confidence: 0.0,
            expected_arrival_fit: 0.0,
        };
        raw_target_count += 1;
    }

    let mut candidate_count = 0;
    let receiver_context = PassReceiveValueInput {
        pos: input.receiver_space.pos,
        receiver_index: input.receiver_index,
        shot_profiles: input.shot_profiles,
        receiver_anchor: input.receiver_anchor,
        receiver_base: input.receiver_base,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        receiver_finishing: input.receiver_finishing,
        receiver_long_shot: input.receiver_long_shot,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        tick: input.tick,
        receiver_team_home: input.receiver_team_home,
        shot_quality_cache: input.shot_quality_cache,
        receiver_goal_type,
        receiver_goal_target,
        receiver_goal_value,
    };
    let receive_context = team_value_context.map_or_else(
        || pass_receive_value_context(&receiver_context),
        |team_context| {
            pass_receive_value_context_with_team_context(&receiver_context, team_context)
        },
    );
    let receiver_batch_context = RawPassBatchValueContext {
        passer: batch_context.passer,
        receive: Some(&receive_context),
    };
    let motion_context = raw_pass_prevalue_motion_context(
        input.receiver_risk,
        input.risk_opponents,
        input.player_max_speed,
        input.player_min_speed,
        opponent_motion,
    );
    let receiver_pressure_reuse =
        raw_pass_receiver_pressure_reuse(input.risk_opponents, input.opponent_positions);
    for raw in &raw_targets[..raw_target_count] {
        let value = score_raw_pass_target_with_batch_context(
            &RawPassValueInput {
                prevalue: RawPassPreValueInput {
                    passer_index: input.passer_index,
                    passer_pos: input.passer_pos,
                    receiver: input.receiver_risk,
                    target: raw.target,
                    initial_receiver_arrival: raw.arrival,
                    receiver_visibility: base.receiver_visibility,
                    receiver_goal_target,
                    receiver_goal_value,
                    receiver_goal_fit: base.receiver_goal_fit,
                    vision: input.vision,
                    attacking_right: input.attacking_right,
                    pitch_length: input.pitch_length,
                    pitch_width: input.pitch_width,
                    offside_line: input.offside_line,
                    player_max_speed: input.player_max_speed,
                    player_min_speed: input.player_min_speed,
                    short_passing: input.passer_short_passing,
                    long_passing: input.passer_long_passing,
                    short_pass_base_success: input.short_pass_base_success,
                    long_pass_base_success: input.long_pass_base_success,
                    opponents: input.risk_opponents,
                    teammates: input.risk_teammates,
                },
                tick: input.tick,
                passer_team_home: input.passer_team_home,
                passer_finishing: input.passer_finishing,
                passer_long_shot: input.passer_long_shot,
                passer_consecutive_carries: input.passer_consecutive_carries,
                receiver_index: input.receiver_index,
                receiver_team_home: input.receiver_team_home,
                receiver_finishing: input.receiver_finishing,
                receiver_long_shot: input.receiver_long_shot,
                receiver_anchor: input.receiver_anchor,
                receiver_base: input.receiver_base,
                receiver_goal_type,
                receiver_goal_target,
                receiver_goal_value,
                shot_profiles: input.shot_profiles,
                teammate_positions: input.teammate_positions,
                teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
                opponent_positions: input.opponent_positions,
                interception_reach: input.interception_reach,
                shot_ideal_distance: input.shot_ideal_distance,
                shot_on_target_base: input.shot_on_target_base,
                gk_save_base: input.gk_save_base,
                gk_attributes: input.gk_attributes,
                gk_pos: input.gk_pos,
                contest_defenders: input.contest_defenders,
                current_value: input.current_value,
                shot_quality_cache: input.shot_quality_cache,
            },
            &receiver_batch_context,
            motion_context.as_ref(),
            receiver_pressure_reuse,
        );
        if !value.valid {
            continue;
        }
        candidates[candidate_count] = ReceiverPassCandidate {
            target: raw.target,
            score: value.adjusted_score,
            raw_score: value.score,
            success_prob: value.success_prob,
            risk_cost: value.risk_cost,
            current_value: value.current_value,
            effective_current_value: value.effective_current_value,
            delta: value.delta,
            after_value: value.after_value,
            after_direct_xg: value.after_direct_xg,
            effective_delta: value.effective_delta,
            progress_gain: value.progress_gain,
            continuity: value.continuity,
            lane_risk: value.lane_risk,
            receiver_pressure: value.receiver_pressure,
            turnover_consequence: value.turnover_consequence,
            high_threat_space: value.high_threat_space,
            final_third_combination: value.final_third_combination,
            second_line_arrival_value: value.second_line_arrival_value,
            second_line_cutback_value: value.second_line_cutback_value,
            layoff_support_value: value.layoff_support_value,
            short_combination_value: value.short_combination_value,
            layoff_retention_value: value.layoff_retention_value,
            receiver_arrival: value.receiver_arrival,
            base_accuracy: value.base_accuracy,
            goal_target_fit: value.goal_target_fit,
            is_long: value.is_long,
            target_kind_space: value.target_kind_space,
            distance: value.distance,
            perception: value.perception,
            perception_multiplier: value.perception_multiplier,
            arrival_margin: value.arrival_margin,
            defender_first_risk: value.defender_first_risk,
            target_occupation_risk: value.target_occupation_risk,
            nearest_teammate_to_target: value.nearest_teammate_to_target,
            nearest_opp_to_target: value.nearest_opp_to_target,
            box_space_pressure: value.box_space_pressure,
            tactical_space: raw.tactical_space,
            tactical_space_prior: raw.tactical_space_prior,
            tactical_space_value: raw.tactical_space_value,
            tactical_space_visibility: raw.tactical_space_visibility,
            expected_arrival_confidence: raw.expected_arrival_confidence,
            expected_arrival_fit: raw.expected_arrival_fit,
        };
        candidate_count += 1;
    }
    candidate_count
}

pub fn team_pass_candidates_batch(input: &TeamPassBatchInput<'_>) -> Vec<TeamPassCandidate> {
    let mut candidates = [EMPTY_TEAM_PASS_CANDIDATE; MAX_TEAM_PASS_CANDIDATES];
    let candidate_count = team_pass_candidates_batch_into(input, &mut candidates);
    candidates[..candidate_count].to_vec()
}

pub fn team_pass_candidates_batch_into(
    input: &TeamPassBatchInput<'_>,
    results: &mut [TeamPassCandidate],
) -> usize {
    let mut workspace = TeamPassWorkspace::new();
    team_pass_candidates_batch_into_with_workspace(input, results, &mut workspace)
}

pub fn team_pass_candidates_batch_into_with_workspace(
    input: &TeamPassBatchInput<'_>,
    results: &mut [TeamPassCandidate],
    workspace: &mut TeamPassWorkspace,
) -> usize {
    team_pass_candidates_batch_into_internal(input, results, workspace, true)
}

fn team_pass_candidates_batch_into_internal(
    input: &TeamPassBatchInput<'_>,
    results: &mut [TeamPassCandidate],
    workspace: &mut TeamPassWorkspace,
    reuse_team_value_context: bool,
) -> usize {
    let max_candidate_count =
        input.players.len().saturating_sub(1) * MAX_PASS_CANDIDATES_PER_RECEIVER;
    assert!(
        results.len() >= max_candidate_count,
        "team pass candidate output buffer is too small"
    );
    let TeamPassWorkspace {
        generic_candidates,
        receiver,
    } = workspace;
    let generic_candidate_count = generic_pass_space_candidates_into(
        &GenericPassSpaceInput {
            passer_index: input.passer_index,
            passer_pos: input.passer_pos,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            offside_line: input.offside_line,
            vision: input.vision,
            teammates: input.space_players,
            opponent_positions: input.opponent_positions,
            teammate_positions: input.teammate_xy_positions,
        },
        generic_candidates,
    );
    let generic_candidates = &generic_candidates[..generic_candidate_count];

    let mut front_anchor_sum = (0.0, 0.0);
    let mut front_anchor_count = 0;
    for player in input.players {
        if player.space.index == input.passer_index || player.space.is_goalkeeper {
            continue;
        }
        let progress = if input.attacking_right {
            player.space.tactical_anchor.0 / input.pitch_length
        } else {
            (input.pitch_length - player.space.tactical_anchor.0) / input.pitch_length
        };
        if progress > 0.58 {
            front_anchor_sum.0 += player.space.tactical_anchor.0;
            front_anchor_sum.1 += player.space.tactical_anchor.1;
            front_anchor_count += 1;
        }
    }
    let front_center = if front_anchor_count == 0 {
        None
    } else {
        Some((
            front_anchor_sum.0 / front_anchor_count as f64,
            front_anchor_sum.1 / front_anchor_count as f64,
        ))
    };
    let batch_context = RawPassBatchValueContext {
        passer: passer_pass_value_context(&PasserPassValueContextInput {
            tick: input.tick,
            passer_index: input.passer_index,
            passer_team_home: input.passer_team_home,
            passer_pos: input.passer_pos,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_consecutive_carries: input.passer_consecutive_carries,
            opponent_positions: input.opponent_positions,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            gk_attributes: input.gk_attributes,
            gk_pos: input.gk_pos,
            contest_defenders: input.contest_defenders,
            current_value: input.current_value,
            shot_quality_cache: input.shot_quality_cache,
        }),
        receive: None,
    };
    let team_value_context = reuse_team_value_context.then(|| {
        pass_receive_team_value_context(&PassReceiveValueInput {
            pos: input.passer_pos,
            receiver_index: input.passer_index,
            shot_profiles: input.shot_profiles_for_value,
            receiver_anchor: input.passer_pos,
            receiver_base: input.passer_pos,
            teammate_positions: input.teammate_positions_for_value,
            teammate_goalkeeper_indices: input.teammate_goalkeeper_indices_for_value,
            opponent_positions: input.opponent_positions,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attacking_right: input.attacking_right,
            receiver_finishing: input.passer_finishing,
            receiver_long_shot: input.passer_long_shot,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            gk_attributes: input.gk_attributes,
            gk_pos: input.gk_pos,
            contest_defenders: input.contest_defenders,
            tick: input.tick,
            receiver_team_home: input.passer_team_home,
            shot_quality_cache: input.shot_quality_cache,
            receiver_goal_type: None,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
        })
    });

    let mut result_count = 0;
    for player in input.players {
        if player.space.index == input.passer_index {
            continue;
        }
        let receiver_input = ReceiverPassBatchInput {
            tick: input.tick,
            passer_index: input.passer_index,
            passer_team_home: input.passer_team_home,
            passer_pos: input.passer_pos,
            passer_finishing: input.passer_finishing,
            passer_long_shot: input.passer_long_shot,
            passer_short_passing: input.passer_short_passing,
            passer_long_passing: input.passer_long_passing,
            passer_consecutive_carries: input.passer_consecutive_carries,
            receiver_space: player.space,
            receiver_risk: player.risk,
            receiver_index: player.space.index,
            receiver_team_home: input.passer_team_home,
            receiver_finishing: player.finishing,
            receiver_long_shot: player.long_shot,
            receiver_anchor: player.space.tactical_anchor,
            receiver_base: player.base,
            receiver_goal: player.goal,
            is_receiver_defender: player.is_defender,
            vision: input.vision,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            offside_line: input.offside_line,
            player_max_speed: input.player_max_speed,
            player_min_speed: input.player_min_speed,
            short_pass_base_success: input.short_pass_base_success,
            long_pass_base_success: input.long_pass_base_success,
            interception_reach: input.interception_reach,
            shot_ideal_distance: input.shot_ideal_distance,
            shot_on_target_base: input.shot_on_target_base,
            gk_save_base: input.gk_save_base,
            gk_attributes: input.gk_attributes,
            gk_pos: input.gk_pos,
            contest_defenders: input.contest_defenders,
            current_value: input.current_value,
            front_center,
            generic_candidates,
            opponent_positions: input.opponent_positions,
            teammate_positions: input.teammate_positions_for_value,
            shot_profiles: input.shot_profiles_for_value,
            teammate_goalkeeper_indices: input.teammate_goalkeeper_indices_for_value,
            teammate_xy_positions: input.teammate_xy_positions,
            risk_opponents: input.risk_opponents,
            risk_teammates: input.risk_teammates,
            shot_quality_cache: input.shot_quality_cache,
        };
        let receiver_candidate_count = receiver_pass_candidates_batch_into(
            &receiver_input,
            receiver,
            &batch_context,
            team_value_context.as_ref(),
        );
        for candidate in &receiver.candidates[..receiver_candidate_count] {
            results[result_count] = TeamPassCandidate {
                receiver_index: player.space.index,
                target: candidate.target,
                score: candidate.score,
                raw_score: candidate.raw_score,
                success_prob: candidate.success_prob,
                risk_cost: candidate.risk_cost,
                current_value: candidate.current_value,
                effective_current_value: candidate.effective_current_value,
                delta: candidate.delta,
                after_value: candidate.after_value,
                after_direct_xg: candidate.after_direct_xg,
                effective_delta: candidate.effective_delta,
                progress_gain: candidate.progress_gain,
                continuity: candidate.continuity,
                lane_risk: candidate.lane_risk,
                receiver_pressure: candidate.receiver_pressure,
                turnover_consequence: candidate.turnover_consequence,
                high_threat_space: candidate.high_threat_space,
                final_third_combination: candidate.final_third_combination,
                second_line_arrival_value: candidate.second_line_arrival_value,
                second_line_cutback_value: candidate.second_line_cutback_value,
                layoff_support_value: candidate.layoff_support_value,
                short_combination_value: candidate.short_combination_value,
                layoff_retention_value: candidate.layoff_retention_value,
                receiver_arrival: candidate.receiver_arrival,
                base_accuracy: candidate.base_accuracy,
                goal_target_fit: candidate.goal_target_fit,
                is_long: candidate.is_long,
                target_kind_space: candidate.target_kind_space,
                distance: candidate.distance,
                perception: candidate.perception,
                perception_multiplier: candidate.perception_multiplier,
                arrival_margin: candidate.arrival_margin,
                defender_first_risk: candidate.defender_first_risk,
                target_occupation_risk: candidate.target_occupation_risk,
                nearest_teammate_to_target: candidate.nearest_teammate_to_target,
                nearest_opp_to_target: candidate.nearest_opp_to_target,
                box_space_pressure: candidate.box_space_pressure,
                tactical_space: candidate.tactical_space,
                tactical_space_prior: candidate.tactical_space_prior,
                tactical_space_value: candidate.tactical_space_value,
                tactical_space_visibility: candidate.tactical_space_visibility,
                expected_arrival_confidence: candidate.expected_arrival_confidence,
                expected_arrival_fit: candidate.expected_arrival_fit,
            };
            result_count += 1;
        }
    }
    result_count
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_raw_pass_prevalue_bits_equal(
        left: RawPassPreValueOutput,
        right: RawPassPreValueOutput,
    ) {
        assert_eq!(left.valid, right.valid);
        assert_eq!(left.is_long, right.is_long);
        assert_eq!(left.target_kind_space, right.target_kind_space);
        for (left_value, right_value) in [
            (left.receiver_arrival, right.receiver_arrival),
            (left.base_accuracy, right.base_accuracy),
            (left.continuity, right.continuity),
            (left.perception, right.perception),
            (left.perception_multiplier, right.perception_multiplier),
            (left.arrival_margin, right.arrival_margin),
            (left.receiver_time, right.receiver_time),
            (left.defender_time, right.defender_time),
            (left.defender_first_risk, right.defender_first_risk),
            (left.target_occupation_risk, right.target_occupation_risk),
            (
                left.nearest_teammate_to_target,
                right.nearest_teammate_to_target,
            ),
            (left.nearest_opp_to_target, right.nearest_opp_to_target),
            (left.box_space_pressure, right.box_space_pressure),
            (left.goal_target_fit, right.goal_target_fit),
            (left.distance, right.distance),
        ] {
            assert_eq!(left_value.to_bits(), right_value.to_bits());
        }
    }

    fn assert_expected_pass_output_bits_equal(
        left: crate::pass_value::ExpectedPassOutput,
        right: crate::pass_value::ExpectedPassOutput,
    ) {
        for (left_value, right_value) in [
            (left.score, right.score),
            (left.success_prob, right.success_prob),
            (left.risk_cost, right.risk_cost),
            (left.after_value, right.after_value),
            (left.after_direct_xg, right.after_direct_xg),
            (left.current_value, right.current_value),
            (left.effective_current_value, right.effective_current_value),
            (left.delta, right.delta),
            (left.effective_delta, right.effective_delta),
            (left.progress_gain, right.progress_gain),
            (left.continuity, right.continuity),
            (left.lane_risk, right.lane_risk),
            (left.receiver_pressure, right.receiver_pressure),
            (left.turnover_consequence, right.turnover_consequence),
            (left.high_threat_space, right.high_threat_space),
            (left.final_third_combination, right.final_third_combination),
            (
                left.second_line_arrival_value,
                right.second_line_arrival_value,
            ),
            (
                left.second_line_cutback_value,
                right.second_line_cutback_value,
            ),
            (left.layoff_support_value, right.layoff_support_value),
            (left.short_combination_value, right.short_combination_value),
            (left.layoff_retention_value, right.layoff_retention_value),
        ] {
            assert_eq!(left_value.to_bits(), right_value.to_bits());
        }
    }

    #[test]
    fn raw_pass_prevalue_motion_context_preserves_reference_values() {
        let receiver = PassRiskPlayer {
            index: 4,
            pos: (58.0, 31.0),
            speed: 87,
            is_goalkeeper: false,
        };
        let opponents = [
            PassRiskPlayer {
                index: 0,
                pos: (102.0, 34.0),
                speed: 49,
                is_goalkeeper: true,
            },
            PassRiskPlayer {
                index: 1,
                pos: (75.0, 27.0),
                speed: 80,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 2,
                pos: (84.0, 42.0),
                speed: 73,
                is_goalkeeper: false,
            },
        ];
        let teammates = [
            PassRiskPlayer {
                index: 0,
                pos: (14.0, 35.0),
                speed: 61,
                is_goalkeeper: false,
            },
            receiver,
            PassRiskPlayer {
                index: 8,
                pos: (71.0, 48.0),
                speed: 84,
                is_goalkeeper: false,
            },
        ];

        for target in [(66.0, 25.0), (89.0, 36.0)] {
            let input = RawPassPreValueInput {
                passer_index: 0,
                passer_pos: (44.0, 34.0),
                receiver,
                target,
                initial_receiver_arrival: 0.84,
                receiver_visibility: 0.73,
                receiver_goal_target: Some((86.0, 35.0)),
                receiver_goal_value: 0.58,
                receiver_goal_fit: 0.66,
                vision: VisionContext {
                    facing: 0.0,
                    fov: 220.0,
                    half_fov: 110.0,
                    max_distance: 65.0,
                },
                attacking_right: true,
                pitch_length: 105.0,
                pitch_width: 68.0,
                offside_line: 94.0,
                player_max_speed: 8.1,
                player_min_speed: 2.5,
                short_passing: 81.0,
                long_passing: 77.0,
                short_pass_base_success: 0.79,
                long_pass_base_success: 0.55,
                opponents: &opponents,
                teammates: &teammates,
            };
            let direct = evaluate_raw_pass_target_prevalue(&input);
            let mut opponent_motion = [EMPTY_RAW_PASS_OPPONENT_MOTION; MAX_PASS_RISK_PLAYERS];
            let motion_context = raw_pass_prevalue_motion_context(
                receiver,
                &opponents,
                input.player_max_speed,
                input.player_min_speed,
                &mut opponent_motion,
            )
            .expect("fixed workspace accepts an eleven-player opponent snapshot");
            let prepared = evaluate_raw_pass_target_prevalue_with_motion_context(
                &input,
                Some(&motion_context),
            );

            assert_raw_pass_prevalue_bits_equal(direct, prepared);
        }
    }

    #[test]
    fn prepared_outfield_pressure_preserves_expected_pass_value() {
        let receiver = PassRiskPlayer {
            index: 4,
            pos: (62.0, 24.0),
            speed: 87,
            is_goalkeeper: false,
        };
        let risk_opponents = [
            PassRiskPlayer {
                index: 0,
                pos: (69.0, 23.0),
                speed: 46,
                is_goalkeeper: true,
            },
            PassRiskPlayer {
                index: 1,
                pos: (66.0, 25.0),
                speed: 78,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 2,
                pos: (73.0, 39.0),
                speed: 75,
                is_goalkeeper: false,
            },
        ];
        let opponent_positions = [risk_opponents[1].pos, risk_opponents[2].pos];
        let teammates = [
            PassRiskPlayer {
                index: 1,
                pos: (45.0, 34.0),
                speed: 73,
                is_goalkeeper: false,
            },
            receiver,
            PassRiskPlayer {
                index: 7,
                pos: (57.0, 42.0),
                speed: 80,
                is_goalkeeper: false,
            },
        ];
        let prevalue = RawPassPreValueInput {
            passer_index: 1,
            passer_pos: (45.0, 34.0),
            receiver,
            target: (67.0, 22.0),
            initial_receiver_arrival: 0.86,
            receiver_visibility: 0.88,
            receiver_goal_target: Some((77.0, 20.0)),
            receiver_goal_value: 0.56,
            receiver_goal_fit: 0.64,
            vision: VisionContext {
                facing: 0.0,
                fov: 220.0,
                half_fov: 110.0,
                max_distance: 65.0,
            },
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            offside_line: 93.0,
            player_max_speed: 8.1,
            player_min_speed: 2.5,
            short_passing: 82.0,
            long_passing: 77.0,
            short_pass_base_success: 0.79,
            long_pass_base_success: 0.55,
            opponents: &risk_opponents,
            teammates: &teammates,
        };
        let (pre, geometry) = evaluate_raw_pass_target_prevalue_with_motion_context_and_geometry(
            &prevalue, None, true,
        );
        assert!(pre.valid);
        assert!(matches!(
            raw_pass_receiver_pressure_reuse(&risk_opponents, &opponent_positions),
            Some(RawPassReceiverPressureReuse::OutfieldOpponents)
        ));

        let shot_profiles = [PlayerShotProfile {
            player_index: receiver.index,
            finishing: 0.79,
            long_shot: 0.72,
        }];
        let teammate_positions = [
            (1, 45.0, 34.0),
            (receiver.index, receiver.pos.0, receiver.pos.1),
            (7, 57.0, 42.0),
        ];
        let expected_input = ExpectedPassInput {
            tick: 41,
            passer_index: prevalue.passer_index,
            passer_team_home: true,
            passer_pos: prevalue.passer_pos,
            passer_finishing: 0.74,
            passer_long_shot: 0.69,
            passer_consecutive_carries: 2,
            receiver_index: receiver.index,
            receiver_team_home: true,
            receiver_finishing: 0.79,
            receiver_long_shot: 0.72,
            receiver_anchor: (63.0, 23.0),
            receiver_base: (58.0, 22.0),
            receiver_goal_type: Some("support"),
            receiver_goal_target: prevalue.receiver_goal_target,
            receiver_goal_value: prevalue.receiver_goal_value,
            target: prevalue.target,
            shot_profiles: &shot_profiles,
            teammate_positions: &teammate_positions,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponent_positions,
            pitch_length: prevalue.pitch_length,
            pitch_width: prevalue.pitch_width,
            attacking_right: prevalue.attacking_right,
            interception_reach: 3.5,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            current_value: 0.29,
            base_accuracy: pre.base_accuracy,
            receiver_arrival: pre.receiver_arrival,
            continuity: pre.continuity,
            shot_quality_cache: None,
        };
        let passer_context = passer_pass_value_context(&PasserPassValueContextInput {
            tick: expected_input.tick,
            passer_index: expected_input.passer_index,
            passer_team_home: expected_input.passer_team_home,
            passer_pos: expected_input.passer_pos,
            passer_finishing: expected_input.passer_finishing,
            passer_long_shot: expected_input.passer_long_shot,
            passer_consecutive_carries: expected_input.passer_consecutive_carries,
            opponent_positions: expected_input.opponent_positions,
            pitch_length: expected_input.pitch_length,
            pitch_width: expected_input.pitch_width,
            attacking_right: expected_input.attacking_right,
            shot_ideal_distance: expected_input.shot_ideal_distance,
            shot_on_target_base: expected_input.shot_on_target_base,
            gk_save_base: expected_input.gk_save_base,
            gk_attributes: expected_input.gk_attributes,
            gk_pos: expected_input.gk_pos,
            contest_defenders: expected_input.contest_defenders,
            current_value: expected_input.current_value,
            shot_quality_cache: expected_input.shot_quality_cache,
        });
        let direct = expected_pass_value_with_context(&expected_input, passer_context, None);
        let prepared = expected_pass_value_with_context_and_precomputed_receiver_pressure(
            &expected_input,
            passer_context,
            None,
            geometry
                .expect("valid prevalue produces geometry")
                .outfield_opponents_receiver_pressure,
        );

        assert_expected_pass_output_bits_equal(direct, prepared);
    }

    #[test]
    fn generic_pass_space_candidates_are_sorted_and_limited() {
        let teammates = [
            PassSpacePlayer {
                index: 0,
                pos: (50.0, 34.0),
                target_pos: (50.0, 34.0),
                tactical_anchor: (50.0, 34.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: true,
                is_wide: false,
            },
            PassSpacePlayer {
                index: 1,
                pos: (70.0, 22.0),
                target_pos: (76.0, 20.0),
                tactical_anchor: (76.0, 20.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: true,
            },
            PassSpacePlayer {
                index: 2,
                pos: (72.0, 44.0),
                target_pos: (78.0, 46.0),
                tactical_anchor: (78.0, 46.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: true,
            },
        ];
        let opponents = [(82.0, 30.0), (86.0, 40.0)];
        let teammate_positions = [(70.0, 22.0), (72.0, 44.0)];
        let result = generic_pass_space_candidates(&GenericPassSpaceInput {
            passer_index: 0,
            passer_pos: (50.0, 34.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            offside_line: 90.0,
            vision: VisionContext {
                facing: 0.0,
                fov: 180.0,
                half_fov: 90.0,
                max_distance: 50.0,
            },
            teammates: &teammates,
            opponent_positions: &opponents,
            teammate_positions: &teammate_positions,
        });
        assert!(result.len() <= 10);
        assert!(result.windows(2).all(|pair| pair[0].score >= pair[1].score));
    }

    #[test]
    fn geometrically_valid_recycle_survives_zero_legacy_shaping() {
        let risk_players = [PassRiskPlayer {
            index: 1,
            pos: (12.0, 34.0),
            speed: 80,
            is_goalkeeper: false,
        }];
        let prevalue = RawPassPreValueInput {
            passer_index: 0,
            passer_pos: (24.0, 34.0),
            receiver: risk_players[0],
            target: (12.0, 34.0),
            initial_receiver_arrival: 0.90,
            receiver_visibility: 1.0,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
            receiver_goal_fit: 0.0,
            vision: VisionContext {
                facing: 0.0,
                fov: 240.0,
                half_fov: 120.0,
                max_distance: 65.0,
            },
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            offside_line: 90.0,
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            short_passing: 80.0,
            long_passing: 80.0,
            short_pass_base_success: 0.80,
            long_pass_base_success: 0.55,
            opponents: &[],
            teammates: &risk_players,
        };
        let pre = evaluate_raw_pass_target_prevalue(&prevalue);
        let value = score_raw_pass_target(&RawPassValueInput {
            prevalue,
            tick: 1,
            passer_team_home: true,
            passer_finishing: 0.7,
            passer_long_shot: 0.7,
            passer_consecutive_carries: 0,
            receiver_index: 1,
            receiver_team_home: true,
            receiver_finishing: 0.7,
            receiver_long_shot: 0.7,
            receiver_anchor: (12.0, 34.0),
            receiver_base: (12.0, 34.0),
            receiver_goal_type: None,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
            shot_profiles: &[],
            teammate_positions: &[(1, 12.0, 34.0)],
            teammate_goalkeeper_indices: &[],
            opponent_positions: &[],
            interception_reach: 3.5,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            current_value: 0.65,
            shot_quality_cache: None,
        });

        assert!(pre.valid);
        assert!(value.score <= 1e-12);
        assert!(value.adjusted_score <= 1e-12);
        assert!(value.valid);
    }

    fn assert_team_pass_candidate_bits_equal(left: TeamPassCandidate, right: TeamPassCandidate) {
        assert_eq!(left.receiver_index, right.receiver_index);
        assert_eq!(left.target.0.to_bits(), right.target.0.to_bits());
        assert_eq!(left.target.1.to_bits(), right.target.1.to_bits());
        assert_eq!(left.is_long, right.is_long);
        assert_eq!(left.target_kind_space, right.target_kind_space);
        assert_eq!(left.tactical_space, right.tactical_space);
        for (left_value, right_value) in [
            (left.score, right.score),
            (left.raw_score, right.raw_score),
            (left.success_prob, right.success_prob),
            (left.risk_cost, right.risk_cost),
            (left.current_value, right.current_value),
            (left.effective_current_value, right.effective_current_value),
            (left.delta, right.delta),
            (left.after_value, right.after_value),
            (left.after_direct_xg, right.after_direct_xg),
            (left.effective_delta, right.effective_delta),
            (left.progress_gain, right.progress_gain),
            (left.continuity, right.continuity),
            (left.lane_risk, right.lane_risk),
            (left.receiver_pressure, right.receiver_pressure),
            (left.turnover_consequence, right.turnover_consequence),
            (left.high_threat_space, right.high_threat_space),
            (left.final_third_combination, right.final_third_combination),
            (
                left.second_line_arrival_value,
                right.second_line_arrival_value,
            ),
            (
                left.second_line_cutback_value,
                right.second_line_cutback_value,
            ),
            (left.layoff_support_value, right.layoff_support_value),
            (left.short_combination_value, right.short_combination_value),
            (left.layoff_retention_value, right.layoff_retention_value),
            (left.receiver_arrival, right.receiver_arrival),
            (left.base_accuracy, right.base_accuracy),
            (left.goal_target_fit, right.goal_target_fit),
            (left.distance, right.distance),
            (left.perception, right.perception),
            (left.perception_multiplier, right.perception_multiplier),
            (left.arrival_margin, right.arrival_margin),
            (left.defender_first_risk, right.defender_first_risk),
            (left.target_occupation_risk, right.target_occupation_risk),
            (
                left.nearest_teammate_to_target,
                right.nearest_teammate_to_target,
            ),
            (left.nearest_opp_to_target, right.nearest_opp_to_target),
            (left.box_space_pressure, right.box_space_pressure),
            (left.tactical_space_prior, right.tactical_space_prior),
            (left.tactical_space_value, right.tactical_space_value),
            (
                left.tactical_space_visibility,
                right.tactical_space_visibility,
            ),
            (
                left.expected_arrival_confidence,
                right.expected_arrival_confidence,
            ),
            (left.expected_arrival_fit, right.expected_arrival_fit),
        ] {
            assert_eq!(left_value.to_bits(), right_value.to_bits());
        }
    }

    #[test]
    fn team_pass_workspace_preserves_candidates_across_reuse() {
        let space_players = [
            PassSpacePlayer {
                index: 0,
                pos: (6.0, 34.0),
                target_pos: (6.0, 34.0),
                tactical_anchor: (6.0, 34.0),
                is_goalkeeper: true,
                is_defender: false,
                is_midfielder: false,
                is_wide: false,
            },
            PassSpacePlayer {
                index: 1,
                pos: (48.0, 34.0),
                target_pos: (51.0, 34.0),
                tactical_anchor: (48.0, 34.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: true,
                is_wide: false,
            },
            PassSpacePlayer {
                index: 2,
                pos: (69.0, 17.0),
                target_pos: (75.0, 14.0),
                tactical_anchor: (72.0, 16.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: true,
            },
            PassSpacePlayer {
                index: 3,
                pos: (78.0, 43.0),
                target_pos: (84.0, 45.0),
                tactical_anchor: (81.0, 43.0),
                is_goalkeeper: false,
                is_defender: false,
                is_midfielder: false,
                is_wide: false,
            },
            PassSpacePlayer {
                index: 4,
                pos: (38.0, 49.0),
                target_pos: (42.0, 51.0),
                tactical_anchor: (39.0, 49.0),
                is_goalkeeper: false,
                is_defender: true,
                is_midfielder: false,
                is_wide: false,
            },
        ];
        let risk_teammates = [
            PassRiskPlayer {
                index: 0,
                pos: space_players[0].pos,
                speed: 42,
                is_goalkeeper: true,
            },
            PassRiskPlayer {
                index: 1,
                pos: space_players[1].pos,
                speed: 74,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 2,
                pos: space_players[2].pos,
                speed: 85,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 3,
                pos: space_players[3].pos,
                speed: 88,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 4,
                pos: space_players[4].pos,
                speed: 69,
                is_goalkeeper: false,
            },
        ];
        let players = [
            PassTeamPlayer {
                space: space_players[0],
                risk: risk_teammates[0],
                finishing: 0.12,
                long_shot: 0.08,
                base: (6.0, 34.0),
                is_defender: false,
                goal: None,
            },
            PassTeamPlayer {
                space: space_players[1],
                risk: risk_teammates[1],
                finishing: 0.72,
                long_shot: 0.78,
                base: (46.0, 34.0),
                is_defender: false,
                goal: None,
            },
            PassTeamPlayer {
                space: space_players[2],
                risk: risk_teammates[2],
                finishing: 0.81,
                long_shot: 0.70,
                base: (66.0, 19.0),
                is_defender: false,
                goal: Some(ReceiverGoalInput {
                    goal_type: "support",
                    target_pos: (78.0, 14.0),
                    value: 0.42,
                }),
            },
            PassTeamPlayer {
                space: space_players[3],
                risk: risk_teammates[3],
                finishing: 0.90,
                long_shot: 0.67,
                base: (75.0, 43.0),
                is_defender: false,
                goal: Some(ReceiverGoalInput {
                    goal_type: "receive",
                    target_pos: (87.0, 42.0),
                    value: 0.71,
                }),
            },
            PassTeamPlayer {
                space: space_players[4],
                risk: risk_teammates[4],
                finishing: 0.43,
                long_shot: 0.52,
                base: (36.0, 48.0),
                is_defender: true,
                goal: None,
            },
        ];
        let opponent_positions = [(88.0, 19.0), (86.0, 35.0), (91.0, 49.0)];
        let risk_opponents = [
            PassRiskPlayer {
                index: 0,
                pos: (101.0, 34.0),
                speed: 44,
                is_goalkeeper: true,
            },
            PassRiskPlayer {
                index: 1,
                pos: opponent_positions[0],
                speed: 77,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 2,
                pos: opponent_positions[1],
                speed: 80,
                is_goalkeeper: false,
            },
            PassRiskPlayer {
                index: 3,
                pos: opponent_positions[2],
                speed: 75,
                is_goalkeeper: false,
            },
        ];
        let teammate_positions = [
            (0, space_players[0].pos.0, space_players[0].pos.1),
            (1, space_players[1].pos.0, space_players[1].pos.1),
            (2, space_players[2].pos.0, space_players[2].pos.1),
            (3, space_players[3].pos.0, space_players[3].pos.1),
            (4, space_players[4].pos.0, space_players[4].pos.1),
        ];
        let shot_profiles = [
            PlayerShotProfile {
                player_index: 0,
                finishing: players[0].finishing,
                long_shot: players[0].long_shot,
            },
            PlayerShotProfile {
                player_index: 1,
                finishing: players[1].finishing,
                long_shot: players[1].long_shot,
            },
            PlayerShotProfile {
                player_index: 2,
                finishing: players[2].finishing,
                long_shot: players[2].long_shot,
            },
            PlayerShotProfile {
                player_index: 3,
                finishing: players[3].finishing,
                long_shot: players[3].long_shot,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: players[4].finishing,
                long_shot: players[4].long_shot,
            },
        ];
        let teammate_xy_positions = [
            space_players[0].pos,
            space_players[2].pos,
            space_players[3].pos,
            space_players[4].pos,
        ];
        let teammate_goalkeeper_indices = [0];
        let input = TeamPassBatchInput {
            tick: 731,
            passer_index: 1,
            passer_team_home: true,
            passer_pos: space_players[1].pos,
            passer_finishing: players[1].finishing,
            passer_long_shot: players[1].long_shot,
            passer_short_passing: 83.0,
            passer_long_passing: 79.0,
            passer_consecutive_carries: 4,
            vision: VisionContext {
                facing: 0.0,
                fov: 210.0,
                half_fov: 105.0,
                max_distance: 62.0,
            },
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            offside_line: 93.0,
            player_max_speed: 8.1,
            player_min_speed: 2.5,
            short_pass_base_success: 0.78,
            long_pass_base_success: 0.54,
            interception_reach: 3.5,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.52,
            gk_save_base: 0.66,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            current_value: 0.29,
            players: &players,
            space_players: &space_players,
            opponent_positions: &opponent_positions,
            teammate_positions_for_value: &teammate_positions,
            shot_profiles_for_value: &shot_profiles,
            teammate_goalkeeper_indices_for_value: &teammate_goalkeeper_indices,
            teammate_xy_positions: &teammate_xy_positions,
            risk_opponents: &risk_opponents,
            risk_teammates: &risk_teammates,
            shot_quality_cache: None,
        };
        let mut direct_results = [EMPTY_TEAM_PASS_CANDIDATE; MAX_TEAM_PASS_CANDIDATES];
        let mut direct_workspace = TeamPassWorkspace::new();
        let direct_count = team_pass_candidates_batch_into_internal(
            &input,
            &mut direct_results,
            &mut direct_workspace,
            false,
        );
        let mut shared_results = [EMPTY_TEAM_PASS_CANDIDATE; MAX_TEAM_PASS_CANDIDATES];
        let shared_count = team_pass_candidates_batch_into(&input, &mut shared_results);
        let mut workspace_results = [EMPTY_TEAM_PASS_CANDIDATE; MAX_TEAM_PASS_CANDIDATES];
        let mut reused_results = [EMPTY_TEAM_PASS_CANDIDATE; MAX_TEAM_PASS_CANDIDATES];
        let mut workspace = TeamPassWorkspace::new();
        let workspace_count = team_pass_candidates_batch_into_with_workspace(
            &input,
            &mut workspace_results,
            &mut workspace,
        );
        let reused_count = team_pass_candidates_batch_into_with_workspace(
            &input,
            &mut reused_results,
            &mut workspace,
        );

        assert!(direct_count > 0);
        assert_eq!(shared_count, direct_count);
        assert_eq!(workspace_count, direct_count);
        assert_eq!(reused_count, direct_count);
        for candidate_index in 0..direct_count {
            assert_team_pass_candidate_bits_equal(
                direct_results[candidate_index],
                shared_results[candidate_index],
            );
            assert_team_pass_candidate_bits_equal(
                direct_results[candidate_index],
                workspace_results[candidate_index],
            );
            assert_team_pass_candidate_bits_equal(
                direct_results[candidate_index],
                reused_results[candidate_index],
            );
        }
    }
}
