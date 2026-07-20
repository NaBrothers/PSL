use crate::goalkeeper::GkSaveAttributes;
use crate::physics::distance;
use crate::physics::smoothstep;
use crate::possession_control::{
    continuation_control_readiness, shot_release_readiness, PossessionControlState,
};
use crate::shot_quality::{
    estimate_shot_outcome, ShotContestDefender, ShotQualityCache, ShotQualityCacheKey,
    ShotQualityInput,
};

#[derive(Debug, Clone)]
pub struct StateValueInput<'a> {
    pub pos: (f64, f64),
    pub player_index: usize,
    pub shot_profiles: &'a [PlayerShotProfile],
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub finishing: f64,
    pub long_shot: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub tick: i32,
    pub team_home: bool,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
    pub control_state: Option<PossessionControlState>,
}

#[derive(Debug, Clone, Copy)]
pub struct PlayerShotProfile {
    pub player_index: usize,
    pub finishing: f64,
    pub long_shot: f64,
}

#[derive(Debug, Clone)]
pub struct PassReceiveValueInput<'a> {
    pub pos: (f64, f64),
    pub receiver_index: usize,
    pub shot_profiles: &'a [PlayerShotProfile],
    pub receiver_anchor: (f64, f64),
    pub receiver_base: (f64, f64),
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
    pub receiver_finishing: f64,
    pub receiver_long_shot: f64,
    pub shot_ideal_distance: f64,
    pub shot_on_target_base: f64,
    pub gk_save_base: f64,
    pub gk_attributes: Option<GkSaveAttributes>,
    pub gk_pos: Option<(f64, f64)>,
    pub contest_defenders: Option<&'a [ShotContestDefender]>,
    pub tick: i32,
    pub receiver_team_home: bool,
    pub shot_quality_cache: Option<&'a ShotQualityCache>,
    pub receiver_goal_type: Option<&'a str>,
    pub receiver_goal_target: Option<(f64, f64)>,
    pub receiver_goal_value: f64,
}

pub fn shot_quality_cache_key(
    tick: i32,
    team_home: bool,
    player_index: usize,
    pos: (f64, f64),
    attacking_right: bool,
) -> ShotQualityCacheKey {
    ShotQualityCacheKey {
        tick,
        team_home,
        player_index,
        x10: (pos.0 * 10.0).round() as i64,
        y10: (pos.1 * 10.0).round() as i64,
        attacking_right,
    }
}

#[derive(Debug, Clone, Copy)]
pub struct PossessionStateValue {
    pub value: f64,
    pub territory: f64,
    pub pressure_relief: f64,
    pub outlet_access: f64,
    pub support_width: f64,
    pub structure: f64,
    pub creation_access: f64,
    pub direct_xg: f64,
    pub one_link_xg: f64,
    pub continuation_xg: f64,
    pub control_residual: f64,
    pub continuation_value: f64,
    pub control_survival: f64,
    pub control_readiness: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct PossessionStateValueEvaluation {
    pub state: PossessionStateValue,
    pub raw_shot_xg: f64,
    raw_shot_finishing: f64,
    raw_shot_long_shot: f64,
}

impl PossessionStateValueEvaluation {
    pub fn raw_shot_matches_profile(&self, finishing: f64, long_shot: f64) -> bool {
        self.raw_shot_finishing.to_bits() == finishing.to_bits()
            && self.raw_shot_long_shot.to_bits() == long_shot.to_bits()
    }
}

#[derive(Debug, Clone, Copy)]
pub struct PassReceiveValueBreakdown {
    pub value: f64,
    pub territory: f64,
    pub pressure_relief: f64,
    pub outlet_access: f64,
    pub support_width: f64,
    pub structure: f64,
    pub creation_access: f64,
    pub role_balance: f64,
    pub recycle_access: f64,
    pub wide_creation: f64,
    pub inside_arrival: f64,
    pub second_line_arrival: f64,
    pub receiver_goal_arrival: f64,
    pub pressure: f64,
    pub centrality: f64,
    pub width_value: f64,
    pub target_width: f64,
    pub anchor_width: f64,
    pub base_progress: f64,
    pub box_presence: f64,
    pub direct_xg: f64,
    pub one_link_xg: f64,
    pub continuation_xg: f64,
    pub control_residual: f64,
    pub continuation_value: f64,
    pub control_survival: f64,
    pub control_readiness: f64,
}

fn attacking_progress(pos: (f64, f64), pitch_length: f64, attacking_right: bool) -> f64 {
    if attacking_right {
        pos.0 / pitch_length.max(1.0)
    } else {
        (pitch_length - pos.0) / pitch_length.max(1.0)
    }
    .clamp(0.0, 1.0)
}

fn centrality(y: f64, pitch_width: f64) -> f64 {
    (1.0 - ((y - pitch_width / 2.0).abs() / (pitch_width / 2.0).max(1.0))).clamp(0.0, 1.0)
}

fn local_pressure(pos: (f64, f64), opponents: &[(f64, f64)]) -> f64 {
    let mut pressure = 0.0;
    for opponent in opponents {
        let distance = distance(pos, *opponent);
        if distance < 18.0 {
            pressure += (1.0 - distance / 18.0).powf(1.25);
        }
    }
    (pressure * 0.30).clamp(0.0, 1.0)
}

#[derive(Clone, Copy)]
pub(crate) struct PassReceiveTargetPressure {
    pub(crate) local: f64,
    pub(crate) receiver: f64,
}

pub(crate) fn pass_receive_target_pressures(
    pos: (f64, f64),
    opponents: &[(f64, f64)],
) -> PassReceiveTargetPressure {
    let mut local_pressure = 0.0;
    let mut receiver_pressure = 0.0;
    for opponent in opponents {
        let distance = distance(pos, *opponent);
        if distance < 18.0 {
            local_pressure += (1.0 - distance / 18.0).powf(1.25);
        }
        if distance < 12.0 {
            receiver_pressure += 1.0 - distance / 12.0;
        }
    }
    PassReceiveTargetPressure {
        local: (local_pressure * 0.30).clamp(0.0, 1.0),
        receiver: (receiver_pressure * 0.35).clamp(0.0, 1.0),
    }
}

fn outlet_quality(
    origin: (f64, f64),
    target: (f64, f64),
    target_pressure: f64,
    pitch_length: f64,
    attacking_right: bool,
) -> f64 {
    let distance_to_target = distance(origin, target);
    outlet_quality_from_distance(
        origin,
        target,
        distance_to_target,
        target_pressure,
        pitch_length,
        attacking_right,
    )
}

fn outlet_quality_from_distance(
    origin: (f64, f64),
    target: (f64, f64),
    distance_to_target: f64,
    target_pressure: f64,
    pitch_length: f64,
    attacking_right: bool,
) -> f64 {
    let connection_range = smoothstep(3.0, 8.0, distance_to_target)
        * (1.0 - smoothstep(28.0, 48.0, distance_to_target));
    let direction = if attacking_right { 1.0 } else { -1.0 };
    let progression = ((target.0 - origin.0) * direction / pitch_length.max(1.0)).clamp(-1.0, 1.0);
    let progression_balance = 0.72 + 0.28 * smoothstep(-0.18, 0.18, progression);

    connection_range * (1.0 - target_pressure) * progression_balance
}

fn support_structure(
    pos: (f64, f64),
    teammates: &[(usize, f64, f64)],
    goalkeeper_indices: &[usize],
    pitch_length: f64,
    pitch_width: f64,
) -> (f64, f64) {
    let mut min_x = pos.0;
    let mut max_x = pos.0;
    let mut min_y = pos.1;
    let mut max_y = pos.1;
    let mut local_crowding = 0.0;
    let mut field_player_count = 0;
    for (index, x, y) in teammates {
        if goalkeeper_indices.contains(index) {
            continue;
        }
        field_player_count += 1;
        let teammate = (*x, *y);
        min_x = min_x.min(teammate.0);
        max_x = max_x.max(teammate.0);
        min_y = min_y.min(teammate.1);
        max_y = max_y.max(teammate.1);
        let teammate_distance = distance(pos, teammate);
        if teammate_distance < 12.0 {
            local_crowding += 1.0 - teammate_distance / 12.0;
        }
    }
    if field_player_count == 0 {
        return (0.0, 0.0);
    }

    let longitudinal_span = (max_x - min_x) / pitch_length.max(1.0);
    let lateral_span = (max_y - min_y) / pitch_width.max(1.0);
    let support_width = smoothstep(0.16, 0.42, lateral_span);
    let depth_layering = smoothstep(0.18, 0.52, longitudinal_span);
    let crowding_relief = 1.0 / (1.0 + local_crowding * 0.42);
    let structure =
        (0.38 * support_width + 0.42 * depth_layering + 0.20 * crowding_relief).clamp(0.0, 1.0);

    (support_width, structure)
}

#[derive(Clone, Copy)]
struct SupportStructureStatic {
    field_player_count: usize,
    min_x: f64,
    max_x: f64,
    min_y: f64,
    max_y: f64,
}

fn support_structure_static(
    teammates: &[(usize, f64, f64)],
    goalkeeper_indices: &[usize],
) -> SupportStructureStatic {
    let mut field_player_count = 0;
    let mut min_x = 0.0;
    let mut max_x = 0.0;
    let mut min_y = 0.0;
    let mut max_y = 0.0;
    for (index, x, y) in teammates {
        if goalkeeper_indices.contains(index) {
            continue;
        }
        if field_player_count == 0 {
            min_x = *x;
            max_x = *x;
            min_y = *y;
            max_y = *y;
        } else {
            min_x = min_x.min(*x);
            max_x = max_x.max(*x);
            min_y = min_y.min(*y);
            max_y = max_y.max(*y);
        }
        field_player_count += 1;
    }
    SupportStructureStatic {
        field_player_count,
        min_x,
        max_x,
        min_y,
        max_y,
    }
}

fn support_structure_with_static(
    pos: (f64, f64),
    teammates: &[(usize, f64, f64)],
    goalkeeper_indices: &[usize],
    pitch_length: f64,
    pitch_width: f64,
    static_structure: SupportStructureStatic,
) -> (f64, f64) {
    if static_structure.field_player_count == 0 {
        return (0.0, 0.0);
    }

    let mut local_crowding = 0.0;
    for (index, x, y) in teammates {
        if goalkeeper_indices.contains(index) {
            continue;
        }
        let teammate_distance = distance(pos, (*x, *y));
        if teammate_distance < 12.0 {
            local_crowding += 1.0 - teammate_distance / 12.0;
        }
    }

    let min_x = pos.0.min(static_structure.min_x);
    let max_x = pos.0.max(static_structure.max_x);
    let min_y = pos.1.min(static_structure.min_y);
    let max_y = pos.1.max(static_structure.max_y);
    let longitudinal_span = (max_x - min_x) / pitch_length.max(1.0);
    let lateral_span = (max_y - min_y) / pitch_width.max(1.0);
    let support_width = smoothstep(0.16, 0.42, lateral_span);
    let depth_layering = smoothstep(0.18, 0.52, longitudinal_span);
    let crowding_relief = 1.0 / (1.0 + local_crowding * 0.42);
    let structure =
        (0.38 * support_width + 0.42 * depth_layering + 0.20 * crowding_relief).clamp(0.0, 1.0);

    (support_width, structure)
}

fn terminal_shot_profile(input: &StateValueInput<'_>, player_index: usize) -> (f64, f64) {
    explicit_terminal_shot_profile(input, player_index)
        .unwrap_or((input.finishing, input.long_shot))
}

fn explicit_terminal_shot_profile(
    input: &StateValueInput<'_>,
    player_index: usize,
) -> Option<(f64, f64)> {
    input
        .shot_profiles
        .get(player_index)
        .filter(|profile| profile.player_index == player_index)
        .map(|profile| (profile.finishing, profile.long_shot))
        .or_else(|| {
            input
                .shot_profiles
                .iter()
                .find(|profile| profile.player_index == player_index)
                .map(|profile| (profile.finishing, profile.long_shot))
        })
}

#[derive(Clone, Copy)]
struct TerminalShotValue {
    raw_xg: f64,
    direct_xg: f64,
    finishing: f64,
    long_shot: f64,
}

#[derive(Clone, Copy)]
struct TerminalShotBaseValue {
    raw_xg: f64,
    body_release_xg: f64,
    finishing: f64,
    long_shot: f64,
}

fn terminal_shot_base_value_at(
    input: &StateValueInput<'_>,
    pos: (f64, f64),
    player_index: usize,
) -> TerminalShotBaseValue {
    let (finishing, long_shot) = terminal_shot_profile(input, player_index);
    let finishing = finishing.clamp(0.0, 1.0);
    let long_shot = long_shot.clamp(0.0, 1.0);
    let shot = estimate_shot_outcome(&ShotQualityInput {
        x: pos.0,
        y: pos.1,
        finishing,
        long_shot,
        opponents: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        cache: input.shot_quality_cache,
        cache_key: input.shot_quality_cache.and_then(|_| {
            input.gk_attributes.is_none().then(|| {
                shot_quality_cache_key(
                    input.tick,
                    input.team_home,
                    player_index,
                    pos,
                    input.attacking_right,
                )
            })
        }),
    });
    TerminalShotBaseValue {
        raw_xg: shot.xg,
        body_release_xg: shot.xg * shot.body_release_probability,
        finishing,
        long_shot,
    }
}

fn terminal_shot_value_at(
    input: &StateValueInput<'_>,
    pos: (f64, f64),
    player_index: usize,
    is_current_controller: bool,
) -> TerminalShotValue {
    let base = terminal_shot_base_value_at(input, pos, player_index);
    let controller_release_readiness = if is_current_controller {
        input
            .control_state
            .map(shot_release_readiness)
            .unwrap_or(1.0)
    } else {
        1.0
    };

    TerminalShotValue {
        raw_xg: base.raw_xg,
        direct_xg: (base.body_release_xg * controller_release_readiness).clamp(0.0, 1.0),
        finishing: base.finishing,
        long_shot: base.long_shot,
    }
}

fn terminal_xg_at(
    input: &StateValueInput<'_>,
    pos: (f64, f64),
    player_index: usize,
    is_current_controller: bool,
) -> f64 {
    terminal_shot_value_at(input, pos, player_index, is_current_controller).direct_xg
}

#[derive(Clone, Copy)]
struct PossessionNetworkNode {
    player_index: usize,
    pos: (f64, f64),
}

const MAX_POSSESSION_NETWORK_NODES: usize = 11;

#[derive(Clone, Copy)]
struct PassReceiveStaticNode {
    player_index: usize,
    pos: (f64, f64),
    pressure: f64,
    direct_xg: f64,
}

const EMPTY_PASS_RECEIVE_STATIC_NODE: PassReceiveStaticNode = PassReceiveStaticNode {
    player_index: 0,
    pos: (0.0, 0.0),
    pressure: 0.0,
    direct_xg: 0.0,
};

#[derive(Clone, Copy)]
struct PassReceiveTeammateStaticNode {
    player_index: usize,
    pos: (f64, f64),
    pressure: f64,
    is_goalkeeper: bool,
}

const EMPTY_PASS_RECEIVE_TEAMMATE_STATIC_NODE: PassReceiveTeammateStaticNode =
    PassReceiveTeammateStaticNode {
        player_index: 0,
        pos: (0.0, 0.0),
        pressure: 0.0,
        is_goalkeeper: false,
    };

#[derive(Clone, Copy, Debug)]
struct ControlledConnectionGeometry {
    link_range: f64,
    outlet: f64,
}

const EMPTY_CONTROLLED_CONNECTION_GEOMETRY: ControlledConnectionGeometry =
    ControlledConnectionGeometry {
        link_range: 0.0,
        outlet: 0.0,
    };

#[derive(Clone, Copy, Debug)]
struct PassReceiveTeamStaticNode {
    player_index: usize,
    pos: (f64, f64),
    pressure: f64,
    direct_xg: Option<f64>,
}

const EMPTY_PASS_RECEIVE_TEAM_STATIC_NODE: PassReceiveTeamStaticNode = PassReceiveTeamStaticNode {
    player_index: 0,
    pos: (0.0, 0.0),
    pressure: 0.0,
    direct_xg: None,
};

#[derive(Clone, Copy, Debug)]
pub(crate) struct PassReceiveTeamValueContext {
    static_nodes: [PassReceiveTeamStaticNode; MAX_POSSESSION_NETWORK_NODES],
    static_node_count: usize,
    static_connection_geometries: [[ControlledConnectionGeometry; MAX_POSSESSION_NETWORK_NODES];
        MAX_POSSESSION_NETWORK_NODES],
    opponent_positions: [(f64, f64); MAX_POSSESSION_NETWORK_NODES],
    opponent_count: usize,
}

impl PassReceiveTeamValueContext {
    fn matches_opponents(&self, opponents: &[(f64, f64)]) -> bool {
        self.opponent_count == opponents.len()
            && self.opponent_count <= self.opponent_positions.len()
            && self.opponent_positions[..self.opponent_count]
                .iter()
                .zip(opponents)
                .all(|(stored, current)| {
                    stored.0.to_bits() == current.0.to_bits()
                        && stored.1.to_bits() == current.1.to_bits()
                })
    }
}

#[derive(Clone, Copy)]
pub(crate) struct PossessionBellmanGeometry {
    source_pos: (f64, f64),
    source_pressure: f64,
    source_terminal_shot_base: TerminalShotBaseValue,
    support_width: f64,
    structure: f64,
    node_count: usize,
    teammate_static_nodes: [PassReceiveTeammateStaticNode; MAX_POSSESSION_NETWORK_NODES],
    teammate_static_node_count: usize,
    connection_probabilities: [[f64; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES],
    residual_values: [f64; MAX_POSSESSION_NETWORK_NODES],
    static_terminal_values: [f64; MAX_POSSESSION_NETWORK_NODES],
    one_link_xg: f64,
}

impl PossessionBellmanGeometry {
    fn applies_to(&self, input: &StateValueInput<'_>) -> bool {
        self.source_pos.0.to_bits() == input.pos.0.to_bits()
            && self.source_pos.1.to_bits() == input.pos.1.to_bits()
            && teammate_snapshot_matches(
                &self.teammate_static_nodes,
                self.teammate_static_node_count,
                input.teammate_positions,
                input.teammate_goalkeeper_indices,
            )
    }
}

#[derive(Clone, Copy)]
pub struct PassReceiveValueContext {
    receiver_index: usize,
    static_nodes: [PassReceiveStaticNode; MAX_POSSESSION_NETWORK_NODES],
    static_node_count: usize,
    teammate_static_nodes: [PassReceiveTeammateStaticNode; MAX_POSSESSION_NETWORK_NODES],
    teammate_static_node_count: usize,
    support_structure_static: SupportStructureStatic,
    static_connection_geometries: [[ControlledConnectionGeometry; MAX_POSSESSION_NETWORK_NODES];
        MAX_POSSESSION_NETWORK_NODES],
}

pub type PossessionValueContext = PassReceiveValueContext;

fn teammate_snapshot_matches(
    static_nodes: &[PassReceiveTeammateStaticNode; MAX_POSSESSION_NETWORK_NODES],
    static_node_count: usize,
    teammates: &[(usize, f64, f64)],
    goalkeeper_indices: &[usize],
) -> bool {
    static_node_count == teammates.len()
        && static_nodes[..static_node_count].iter().zip(teammates).all(
            |(stored, (player_index, x, y))| {
                stored.player_index == *player_index
                    && stored.pos.0.to_bits() == x.to_bits()
                    && stored.pos.1.to_bits() == y.to_bits()
                    && stored.is_goalkeeper == goalkeeper_indices.contains(player_index)
            },
        )
}

impl PassReceiveValueContext {
    fn matches_teammate_snapshot(&self, input: &StateValueInput<'_>) -> bool {
        teammate_snapshot_matches(
            &self.teammate_static_nodes,
            self.teammate_static_node_count,
            input.teammate_positions,
            input.teammate_goalkeeper_indices,
        )
    }
}

fn static_connection_geometries(
    input: &StateValueInput<'_>,
    static_nodes: &[PassReceiveStaticNode; MAX_POSSESSION_NETWORK_NODES],
    static_node_count: usize,
) -> [[ControlledConnectionGeometry; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES] {
    let mut static_connection_geometries = [[EMPTY_CONTROLLED_CONNECTION_GEOMETRY;
        MAX_POSSESSION_NETWORK_NODES];
        MAX_POSSESSION_NETWORK_NODES];
    for source_index in 0..static_node_count {
        let source = static_nodes[source_index];
        for target_index in 0..static_node_count {
            if source_index == target_index {
                continue;
            }
            let target = static_nodes[target_index];
            static_connection_geometries[source_index][target_index] =
                controlled_connection_geometry(
                    source.pos,
                    target.pos,
                    target.pressure,
                    input.pitch_length,
                    input.attacking_right,
                );
        }
    }
    static_connection_geometries
}

fn team_static_connection_geometries(
    static_nodes: &[PassReceiveTeamStaticNode; MAX_POSSESSION_NETWORK_NODES],
    static_node_count: usize,
    pitch_length: f64,
    attacking_right: bool,
) -> [[ControlledConnectionGeometry; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES] {
    let mut static_connection_geometries = [[EMPTY_CONTROLLED_CONNECTION_GEOMETRY;
        MAX_POSSESSION_NETWORK_NODES];
        MAX_POSSESSION_NETWORK_NODES];
    for source_index in 0..static_node_count {
        let source = static_nodes[source_index];
        for target_index in 0..static_node_count {
            if source_index == target_index {
                continue;
            }
            let target = static_nodes[target_index];
            static_connection_geometries[source_index][target_index] =
                controlled_connection_geometry(
                    source.pos,
                    target.pos,
                    target.pressure,
                    pitch_length,
                    attacking_right,
                );
        }
    }
    static_connection_geometries
}

fn teammate_static_nodes(
    input: &StateValueInput<'_>,
) -> (
    [PassReceiveTeammateStaticNode; MAX_POSSESSION_NETWORK_NODES],
    usize,
) {
    assert!(
        input.teammate_positions.len() <= MAX_POSSESSION_NETWORK_NODES,
        "pass receive context cannot contain more than {MAX_POSSESSION_NETWORK_NODES} teammates"
    );
    let mut static_nodes = [EMPTY_PASS_RECEIVE_TEAMMATE_STATIC_NODE; MAX_POSSESSION_NETWORK_NODES];
    for (node_index, (player_index, x, y)) in input.teammate_positions.iter().enumerate() {
        let pos = (*x, *y);
        static_nodes[node_index] = PassReceiveTeammateStaticNode {
            player_index: *player_index,
            pos,
            pressure: local_pressure(pos, input.opponent_positions),
            is_goalkeeper: input.teammate_goalkeeper_indices.contains(player_index),
        };
    }
    (static_nodes, input.teammate_positions.len())
}

fn context_teammate_node(
    context: &PassReceiveValueContext,
    teammate_offset: usize,
    player_index: usize,
    pos: (f64, f64),
    is_goalkeeper: bool,
) -> Option<PassReceiveTeammateStaticNode> {
    context
        .teammate_static_nodes
        .get(teammate_offset)
        .filter(|node| {
            teammate_offset < context.teammate_static_node_count
                && node.player_index == player_index
                && node.pos.0.to_bits() == pos.0.to_bits()
                && node.pos.1.to_bits() == pos.1.to_bits()
                && node.is_goalkeeper == is_goalkeeper
        })
        .copied()
}

fn context_teammate_pressure(
    context: &PassReceiveValueContext,
    teammate_offset: usize,
    player_index: usize,
    pos: (f64, f64),
) -> Option<f64> {
    context_teammate_node(context, teammate_offset, player_index, pos, false)
        .map(|node| node.pressure)
}

fn possession_network_nodes(
    input: &StateValueInput<'_>,
    nodes: &mut [PossessionNetworkNode; MAX_POSSESSION_NETWORK_NODES],
) -> usize {
    nodes[0] = PossessionNetworkNode {
        player_index: input.player_index,
        pos: input.pos,
    };
    let mut node_count = 1;
    for (player_index, x, y) in input.teammate_positions {
        if *player_index == input.player_index
            || input.teammate_goalkeeper_indices.contains(player_index)
        {
            continue;
        }
        assert!(
            node_count < nodes.len(),
            "possession network cannot contain more than {MAX_POSSESSION_NETWORK_NODES} players"
        );
        nodes[node_count] = PossessionNetworkNode {
            player_index: *player_index,
            pos: (*x, *y),
        };
        node_count += 1;
    }
    node_count
}

pub fn possession_value_context(input: &StateValueInput<'_>) -> PossessionValueContext {
    let (teammate_static_nodes, teammate_static_node_count) = teammate_static_nodes(input);
    let mut static_nodes = [EMPTY_PASS_RECEIVE_STATIC_NODE; MAX_POSSESSION_NETWORK_NODES];
    let mut static_node_count = 0;
    for (player_index, x, y) in input.teammate_positions {
        if *player_index == input.player_index
            || input.teammate_goalkeeper_indices.contains(player_index)
        {
            continue;
        }
        assert!(
            static_node_count < static_nodes.len(),
            "pass receive context cannot contain more than {MAX_POSSESSION_NETWORK_NODES} players"
        );
        let pos = (*x, *y);
        static_nodes[static_node_count] = PassReceiveStaticNode {
            player_index: *player_index,
            pos,
            pressure: local_pressure(pos, input.opponent_positions),
            direct_xg: terminal_xg_at(input, pos, *player_index, false),
        };
        static_node_count += 1;
    }
    PossessionValueContext {
        receiver_index: input.player_index,
        static_nodes,
        static_node_count,
        teammate_static_nodes,
        teammate_static_node_count,
        support_structure_static: support_structure_static(
            input.teammate_positions,
            input.teammate_goalkeeper_indices,
        ),
        static_connection_geometries: static_connection_geometries(
            input,
            &static_nodes,
            static_node_count,
        ),
    }
}

pub(crate) fn pass_receive_team_value_context(
    input: &PassReceiveValueInput<'_>,
) -> PassReceiveTeamValueContext {
    let state_input = state_value_input_from_pass_receive(input);
    assert!(
        state_input.teammate_positions.len() <= MAX_POSSESSION_NETWORK_NODES,
        "pass receive team context cannot contain more than {MAX_POSSESSION_NETWORK_NODES} players"
    );
    let mut static_nodes = [EMPTY_PASS_RECEIVE_TEAM_STATIC_NODE; MAX_POSSESSION_NETWORK_NODES];
    let mut opponent_positions = [(0.0, 0.0); MAX_POSSESSION_NETWORK_NODES];
    let opponent_count = state_input.opponent_positions.len();
    if opponent_count <= opponent_positions.len() {
        opponent_positions[..opponent_count].copy_from_slice(state_input.opponent_positions);
    }
    for (node_index, (player_index, x, y)) in state_input.teammate_positions.iter().enumerate() {
        let pos = (*x, *y);
        static_nodes[node_index] = PassReceiveTeamStaticNode {
            player_index: *player_index,
            pos,
            pressure: local_pressure(pos, state_input.opponent_positions),
            direct_xg: explicit_terminal_shot_profile(&state_input, *player_index)
                .map(|_| terminal_xg_at(&state_input, pos, *player_index, false)),
        };
    }
    PassReceiveTeamValueContext {
        static_nodes,
        static_node_count: state_input.teammate_positions.len(),
        static_connection_geometries: team_static_connection_geometries(
            &static_nodes,
            state_input.teammate_positions.len(),
            state_input.pitch_length,
            state_input.attacking_right,
        ),
        opponent_positions,
        opponent_count,
    }
}

pub(crate) fn pass_receive_value_context_with_team_context(
    input: &PassReceiveValueInput<'_>,
    team_context: &PassReceiveTeamValueContext,
) -> PassReceiveValueContext {
    let state_input = state_value_input_from_pass_receive(input);
    if team_context.static_node_count != state_input.teammate_positions.len() {
        return possession_value_context(&state_input);
    }

    let mut static_nodes = [EMPTY_PASS_RECEIVE_STATIC_NODE; MAX_POSSESSION_NETWORK_NODES];
    let mut teammate_static_nodes =
        [EMPTY_PASS_RECEIVE_TEAMMATE_STATIC_NODE; MAX_POSSESSION_NETWORK_NODES];
    let team_opponents_match = team_context.matches_opponents(state_input.opponent_positions);
    let mut all_team_nodes_match = team_opponents_match;
    let mut static_node_team_indices = [0; MAX_POSSESSION_NETWORK_NODES];
    let mut static_node_count = 0;
    for (source_index, (player_index, x, y)) in state_input.teammate_positions.iter().enumerate() {
        let pos = (*x, *y);
        let team_node = team_context.static_nodes[source_index];
        let matches_team_node = team_node.player_index == *player_index
            && team_node.pos.0.to_bits() == pos.0.to_bits()
            && team_node.pos.1.to_bits() == pos.1.to_bits();
        all_team_nodes_match &= matches_team_node;
        let pressure = if team_opponents_match && matches_team_node {
            team_node.pressure
        } else {
            local_pressure(pos, state_input.opponent_positions)
        };
        teammate_static_nodes[source_index] = PassReceiveTeammateStaticNode {
            player_index: *player_index,
            pos,
            pressure,
            is_goalkeeper: state_input
                .teammate_goalkeeper_indices
                .contains(player_index),
        };
        if *player_index == state_input.player_index
            || state_input
                .teammate_goalkeeper_indices
                .contains(player_index)
        {
            continue;
        }
        assert!(
            static_node_count < static_nodes.len(),
            "pass receive context cannot contain more than {MAX_POSSESSION_NETWORK_NODES} players"
        );
        static_nodes[static_node_count] = PassReceiveStaticNode {
            player_index: *player_index,
            pos,
            pressure,
            direct_xg: if team_opponents_match && matches_team_node {
                team_node
                    .direct_xg
                    .unwrap_or_else(|| terminal_xg_at(&state_input, pos, *player_index, false))
            } else {
                terminal_xg_at(&state_input, pos, *player_index, false)
            },
        };
        static_node_team_indices[static_node_count] = source_index;
        static_node_count += 1;
    }

    PossessionValueContext {
        receiver_index: state_input.player_index,
        static_nodes,
        static_node_count,
        teammate_static_nodes,
        teammate_static_node_count: state_input.teammate_positions.len(),
        support_structure_static: support_structure_static(
            state_input.teammate_positions,
            state_input.teammate_goalkeeper_indices,
        ),
        static_connection_geometries: if all_team_nodes_match {
            let mut static_connection_geometries = [[EMPTY_CONTROLLED_CONNECTION_GEOMETRY;
                MAX_POSSESSION_NETWORK_NODES];
                MAX_POSSESSION_NETWORK_NODES];
            for source_index in 0..static_node_count {
                for target_index in 0..static_node_count {
                    if source_index == target_index {
                        continue;
                    }
                    static_connection_geometries[source_index][target_index] = team_context
                        .static_connection_geometries[static_node_team_indices[source_index]]
                        [static_node_team_indices[target_index]];
                }
            }
            static_connection_geometries
        } else {
            static_connection_geometries(&state_input, &static_nodes, static_node_count)
        },
    }
}

pub fn pass_receive_value_context(input: &PassReceiveValueInput<'_>) -> PassReceiveValueContext {
    possession_value_context(&state_value_input_from_pass_receive(input))
}

fn controlled_connection_geometry(
    origin: (f64, f64),
    target: (f64, f64),
    target_pressure: f64,
    pitch_length: f64,
    attacking_right: bool,
) -> ControlledConnectionGeometry {
    let distance_to_target = distance(origin, target);
    let link_range = smoothstep(2.0, 5.0, distance_to_target)
        * (1.0 - smoothstep(42.0, 58.0, distance_to_target));
    let outlet = outlet_quality_from_distance(
        origin,
        target,
        distance_to_target,
        target_pressure,
        pitch_length,
        attacking_right,
    );
    ControlledConnectionGeometry { link_range, outlet }
}

fn controlled_connection_probability_from_geometry(
    geometry: ControlledConnectionGeometry,
    origin_pressure: f64,
    target_pressure: f64,
    structure: f64,
) -> f64 {
    let source_relief = 1.0 - origin_pressure;
    let target_relief = 1.0 - target_pressure;
    let collective_control =
        (0.44 + 0.28 * source_relief + 0.18 * target_relief + 0.10 * structure).clamp(0.0, 1.0);

    (geometry.link_range * geometry.outlet * collective_control).clamp(0.0, 1.0)
}

fn controlled_connection_probability(
    origin: (f64, f64),
    target: (f64, f64),
    origin_pressure: f64,
    target_pressure: f64,
    structure: f64,
    pitch_length: f64,
    attacking_right: bool,
) -> f64 {
    controlled_connection_probability_from_geometry(
        controlled_connection_geometry(
            origin,
            target,
            target_pressure,
            pitch_length,
            attacking_right,
        ),
        origin_pressure,
        target_pressure,
        structure,
    )
}

fn control_horizon_residual(
    pos: (f64, f64),
    pressure: f64,
    outlet_access: f64,
    structure: f64,
    support_width: f64,
    pitch_length: f64,
    attacking_right: bool,
) -> f64 {
    let territory = attacking_progress(pos, pitch_length, attacking_right);
    let territorial_opportunity = 0.012 + 0.090 * territory.powf(1.35);
    let pressure_relief = 1.0 - pressure;
    let collective_control = pressure_relief
        * (0.38 + 0.62 * outlet_access)
        * (0.45 + 0.35 * structure + 0.20 * support_width);

    (territorial_opportunity * collective_control).clamp(0.0, 0.18)
}

pub(crate) fn possession_bellman_geometry(
    input: &StateValueInput<'_>,
    context: &PossessionValueContext,
) -> PossessionBellmanGeometry {
    if !context.matches_teammate_snapshot(input) {
        let fallback_context = possession_value_context(input);
        return possession_bellman_geometry(input, &fallback_context);
    }
    let mut nodes = [PossessionNetworkNode {
        player_index: input.player_index,
        pos: input.pos,
    }; MAX_POSSESSION_NETWORK_NODES];
    let mut pressures = [0.0; MAX_POSSESSION_NETWORK_NODES];
    assert_eq!(
        context.receiver_index, input.player_index,
        "pass receive context receiver does not match state controller"
    );
    let node_count = context.static_node_count + 1;
    assert!(
        node_count <= nodes.len(),
        "pass receive context exceeds possession network capacity"
    );
    pressures[0] = local_pressure(input.pos, input.opponent_positions);
    for (offset, static_node) in context.static_nodes[..context.static_node_count]
        .iter()
        .enumerate()
    {
        let node_index = offset + 1;
        nodes[node_index] = PossessionNetworkNode {
            player_index: static_node.player_index,
            pos: static_node.pos,
        };
        pressures[node_index] = static_node.pressure;
    }

    let (support_width, structure) = support_structure_with_static(
        input.pos,
        input.teammate_positions,
        input.teammate_goalkeeper_indices,
        input.pitch_length,
        input.pitch_width,
        context.support_structure_static,
    );
    let mut connection_probabilities =
        [[0.0; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES];
    for source_index in 0..node_count {
        let source = nodes[source_index];
        for target_index in 0..node_count {
            if source_index == target_index {
                continue;
            }
            let target = nodes[target_index];
            connection_probabilities[source_index][target_index] =
                if source_index > 0 && target_index > 0 {
                    controlled_connection_probability_from_geometry(
                        context.static_connection_geometries[source_index - 1][target_index - 1],
                        pressures[source_index],
                        pressures[target_index],
                        structure,
                    )
                } else {
                    controlled_connection_probability(
                        source.pos,
                        target.pos,
                        pressures[source_index],
                        pressures[target_index],
                        structure,
                        input.pitch_length,
                        input.attacking_right,
                    )
                };
        }
    }

    let mut one_link_xg: f64 = 0.0;
    let mut residual_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
    let mut static_terminal_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
    for node_index in 0..node_count {
        let direct_xg = node_index
            .checked_sub(1)
            .map_or(0.0, |offset| context.static_nodes[offset].direct_xg);
        one_link_xg = one_link_xg.max(connection_probabilities[0][node_index] * direct_xg);
        let mut outlet_access: f64 = 0.0;
        for target_index in 0..node_count {
            outlet_access = outlet_access.max(connection_probabilities[node_index][target_index]);
        }
        residual_values[node_index] = control_horizon_residual(
            nodes[node_index].pos,
            pressures[node_index],
            outlet_access,
            structure,
            support_width,
            input.pitch_length,
            input.attacking_right,
        );
        static_terminal_values[node_index] =
            direct_xg + (1.0 - direct_xg) * residual_values[node_index];
    }

    PossessionBellmanGeometry {
        source_pos: input.pos,
        source_pressure: pressures[0],
        source_terminal_shot_base: terminal_shot_base_value_at(
            input,
            input.pos,
            input.player_index,
        ),
        support_width,
        structure,
        node_count,
        teammate_static_nodes: context.teammate_static_nodes,
        teammate_static_node_count: context.teammate_static_node_count,
        connection_probabilities,
        residual_values,
        static_terminal_values,
        one_link_xg,
    }
}

fn bellman_continuation_values(
    node_count: usize,
    direct_values: [f64; MAX_POSSESSION_NETWORK_NODES],
    terminal_values: [f64; MAX_POSSESSION_NETWORK_NODES],
    connection_probabilities: &[[f64; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES],
) -> (f64, f64) {
    let mut continuation_xg = direct_values;
    let mut continuation_values = terminal_values;
    for _ in 0..6 {
        let mut next_xg = direct_values;
        let mut next_values = terminal_values;
        for source_index in 0..node_count {
            for target_index in 0..node_count {
                if source_index == target_index {
                    continue;
                }
                next_xg[source_index] = next_xg[source_index].max(
                    connection_probabilities[source_index][target_index]
                        * continuation_xg[target_index],
                );
                next_values[source_index] = next_values[source_index].max(
                    connection_probabilities[source_index][target_index]
                        * continuation_values[target_index],
                );
            }
        }
        continuation_xg = next_xg;
        continuation_values = next_values;
    }
    (continuation_xg[0], continuation_values[0])
}

fn finite_horizon_continuation_value(
    input: &StateValueInput<'_>,
    structure: f64,
    support_width: f64,
    current_pressure: f64,
    current_direct_xg: f64,
    pass_receive_context: Option<&PassReceiveValueContext>,
    bellman_geometry: Option<&PossessionBellmanGeometry>,
) -> (f64, f64, f64, f64) {
    if let Some(context) = pass_receive_context {
        assert_eq!(
            context.receiver_index, input.player_index,
            "pass receive context receiver does not match state controller"
        );
        if let Some(geometry) = bellman_geometry.filter(|geometry| geometry.applies_to(input)) {
            let node_count = context.static_node_count + 1;
            assert_eq!(
                geometry.node_count, node_count,
                "compiled possession geometry node count does not match its context"
            );
            let mut direct_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
            direct_values[0] = current_direct_xg;
            for (offset, static_node) in context.static_nodes[..context.static_node_count]
                .iter()
                .enumerate()
            {
                direct_values[offset + 1] = static_node.direct_xg;
            }
            let mut terminal_values = geometry.static_terminal_values;
            terminal_values[0] =
                current_direct_xg + (1.0 - current_direct_xg) * geometry.residual_values[0];
            let (continuation_xg, continuation_value) = bellman_continuation_values(
                node_count,
                direct_values,
                terminal_values,
                &geometry.connection_probabilities,
            );
            return (
                geometry.one_link_xg,
                continuation_xg,
                geometry.residual_values[0],
                continuation_value,
            );
        }
    }

    let mut nodes = [PossessionNetworkNode {
        player_index: input.player_index,
        pos: input.pos,
    }; MAX_POSSESSION_NETWORK_NODES];
    let mut pressures = [0.0; MAX_POSSESSION_NETWORK_NODES];
    let mut direct_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
    let node_count = if let Some(context) = pass_receive_context {
        assert_eq!(
            context.receiver_index, input.player_index,
            "pass receive context receiver does not match state controller"
        );
        let node_count = context.static_node_count + 1;
        assert!(
            node_count <= nodes.len(),
            "pass receive context exceeds possession network capacity"
        );
        pressures[0] = current_pressure;
        direct_values[0] = current_direct_xg;
        for (offset, static_node) in context.static_nodes[..context.static_node_count]
            .iter()
            .enumerate()
        {
            let node_index = offset + 1;
            nodes[node_index] = PossessionNetworkNode {
                player_index: static_node.player_index,
                pos: static_node.pos,
            };
            pressures[node_index] = static_node.pressure;
            direct_values[node_index] = static_node.direct_xg;
        }
        node_count
    } else {
        let node_count = possession_network_nodes(input, &mut nodes);
        for source_index in 0..node_count {
            let source = nodes[source_index];
            pressures[source_index] = local_pressure(source.pos, input.opponent_positions);
            direct_values[source_index] = if source_index == 0 {
                current_direct_xg
            } else {
                terminal_xg_at(input, source.pos, source.player_index, false)
            };
        }
        node_count
    };
    let mut connection_probabilities =
        [[0.0; MAX_POSSESSION_NETWORK_NODES]; MAX_POSSESSION_NETWORK_NODES];
    for source_index in 0..node_count {
        let source = nodes[source_index];
        for target_index in 0..node_count {
            if source_index == target_index {
                continue;
            }
            let target = nodes[target_index];
            connection_probabilities[source_index][target_index] = pass_receive_context
                .filter(|_| source_index > 0 && target_index > 0)
                .map_or_else(
                    || {
                        controlled_connection_probability(
                            source.pos,
                            target.pos,
                            pressures[source_index],
                            pressures[target_index],
                            structure,
                            input.pitch_length,
                            input.attacking_right,
                        )
                    },
                    |context| {
                        controlled_connection_probability_from_geometry(
                            context.static_connection_geometries[source_index - 1]
                                [target_index - 1],
                            pressures[source_index],
                            pressures[target_index],
                            structure,
                        )
                    },
                );
        }
    }

    let mut one_link_xg: f64 = 0.0;
    let mut residual_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
    let mut terminal_values = [0.0; MAX_POSSESSION_NETWORK_NODES];
    for node_index in 0..node_count {
        one_link_xg =
            one_link_xg.max(connection_probabilities[0][node_index] * direct_values[node_index]);
        let mut outlet_access: f64 = 0.0;
        for target_index in 0..node_count {
            outlet_access = outlet_access.max(connection_probabilities[node_index][target_index]);
        }
        residual_values[node_index] = control_horizon_residual(
            nodes[node_index].pos,
            pressures[node_index],
            outlet_access,
            structure,
            support_width,
            input.pitch_length,
            input.attacking_right,
        );
        terminal_values[node_index] = direct_values[node_index]
            + (1.0 - direct_values[node_index]) * residual_values[node_index];
    }
    let (continuation_xg, continuation_value) = bellman_continuation_values(
        node_count,
        direct_values,
        terminal_values,
        &connection_probabilities,
    );

    (
        one_link_xg,
        continuation_xg,
        residual_values[0],
        continuation_value,
    )
}

pub fn possession_state_value(input: &StateValueInput<'_>) -> PossessionStateValue {
    possession_state_value_evaluation_with_pass_receive_context(input, None, None, None).state
}

pub fn possession_state_value_with_context(
    input: &StateValueInput<'_>,
    context: &PossessionValueContext,
) -> PossessionStateValue {
    possession_state_value_evaluation_with_pass_receive_context(input, Some(context), None, None)
        .state
}

pub(crate) fn possession_state_value_with_context_and_bellman_geometry(
    input: &StateValueInput<'_>,
    context: &PossessionValueContext,
    bellman_geometry: &PossessionBellmanGeometry,
) -> PossessionStateValue {
    possession_state_value_evaluation_with_pass_receive_context(
        input,
        Some(context),
        Some(bellman_geometry),
        None,
    )
    .state
}

pub fn possession_state_value_evaluation_with_context(
    input: &StateValueInput<'_>,
    context: &PossessionValueContext,
) -> PossessionStateValueEvaluation {
    possession_state_value_evaluation_with_pass_receive_context(input, Some(context), None, None)
}

fn possession_state_value_evaluation_with_pass_receive_context(
    input: &StateValueInput<'_>,
    pass_receive_context: Option<&PassReceiveValueContext>,
    bellman_geometry: Option<&PossessionBellmanGeometry>,
    current_pressure_override: Option<f64>,
) -> PossessionStateValueEvaluation {
    let territory = attacking_progress(input.pos, input.pitch_length, input.attacking_right);
    let bellman_geometry = bellman_geometry.filter(|geometry| geometry.applies_to(input));
    let current_pressure = bellman_geometry.map_or_else(
        || {
            current_pressure_override
                .unwrap_or_else(|| local_pressure(input.pos, input.opponent_positions))
        },
        |geometry| geometry.source_pressure,
    );
    let pressure_relief = 1.0 - current_pressure;
    let mut outlet_access = 0.0;
    let mut forward_access: f64 = 0.0;
    let mut recycle_access: f64 = 0.0;
    let direction = if input.attacking_right { 1.0 } else { -1.0 };
    let mut context_matches_teammate_snapshot = pass_receive_context.is_some_and(|context| {
        context.teammate_static_node_count == input.teammate_positions.len()
    });

    for (teammate_offset, (index, x, y)) in input.teammate_positions.iter().enumerate() {
        let target = (*x, *y);
        let is_goalkeeper = input.teammate_goalkeeper_indices.contains(index);
        let context_node = pass_receive_context.and_then(|context| {
            context_teammate_node(context, teammate_offset, *index, target, is_goalkeeper)
        });
        context_matches_teammate_snapshot &= context_node.is_some();
        if *index == input.player_index {
            continue;
        }
        let target_pressure = context_node
            .map(|node| node.pressure)
            .unwrap_or_else(|| local_pressure(target, input.opponent_positions));
        let quality = outlet_quality(
            input.pos,
            target,
            target_pressure,
            input.pitch_length,
            input.attacking_right,
        );
        outlet_access = 1.0 - (1.0 - outlet_access) * (1.0 - quality);
        let relative_progress =
            ((target.0 - input.pos.0) * direction / input.pitch_length.max(1.0)).clamp(-1.0, 1.0);
        forward_access = forward_access.max(quality * smoothstep(-0.04, 0.20, relative_progress));
        recycle_access = recycle_access.max(quality * smoothstep(0.03, 0.22, -relative_progress));
    }
    let pass_receive_context = pass_receive_context.filter(|_| context_matches_teammate_snapshot);

    let (support_width, structure) = bellman_geometry.map_or_else(
        || {
            pass_receive_context.map_or_else(
                || {
                    support_structure(
                        input.pos,
                        input.teammate_positions,
                        input.teammate_goalkeeper_indices,
                        input.pitch_length,
                        input.pitch_width,
                    )
                },
                |context| {
                    support_structure_with_static(
                        input.pos,
                        input.teammate_positions,
                        input.teammate_goalkeeper_indices,
                        input.pitch_length,
                        input.pitch_width,
                        context.support_structure_static,
                    )
                },
            )
        },
        |geometry| (geometry.support_width, geometry.structure),
    );
    let creation_access = (0.52 * forward_access
        + 0.24 * outlet_access
        + 0.14 * support_width
        + 0.10 * recycle_access)
        .clamp(0.0, 1.0);

    let terminal_shot_base = bellman_geometry.map_or_else(
        || terminal_shot_base_value_at(input, input.pos, input.player_index),
        |geometry| geometry.source_terminal_shot_base,
    );
    let control_readiness = input
        .control_state
        .map(continuation_control_readiness)
        .unwrap_or(1.0);
    let terminal_shot = TerminalShotValue {
        raw_xg: terminal_shot_base.raw_xg,
        direct_xg: (terminal_shot_base.body_release_xg
            * input
                .control_state
                .map(shot_release_readiness)
                .unwrap_or(1.0))
        .clamp(0.0, 1.0),
        finishing: terminal_shot_base.finishing,
        long_shot: terminal_shot_base.long_shot,
    };
    let direct_xg = terminal_shot.direct_xg;
    let control_survival =
        ((0.34 + 0.36 * pressure_relief + 0.18 * structure + 0.12 * outlet_access)
            * (0.32 + 0.68 * control_readiness))
            .clamp(0.0, 1.0);
    let (one_link_xg, continuation_xg, control_residual, continuation_value) =
        finite_horizon_continuation_value(
            input,
            structure,
            support_width,
            current_pressure,
            direct_xg,
            pass_receive_context,
            bellman_geometry,
        );
    let readiness_factor = 0.24 + 0.76 * control_readiness;
    let continuation_surplus = (continuation_value - direct_xg).max(0.0);
    let value = (direct_xg + continuation_surplus * readiness_factor).clamp(0.0002, 0.65);

    PossessionStateValueEvaluation {
        state: PossessionStateValue {
            value,
            territory,
            pressure_relief,
            outlet_access,
            support_width,
            structure,
            creation_access,
            direct_xg,
            one_link_xg,
            continuation_xg,
            control_residual,
            continuation_value,
            control_survival,
            control_readiness,
        },
        raw_shot_xg: terminal_shot.raw_xg,
        raw_shot_finishing: terminal_shot.finishing,
        raw_shot_long_shot: terminal_shot.long_shot,
    }
}

pub fn receiver_goal_arrival_space(
    goal_type: Option<&str>,
    goal_target: Option<(f64, f64)>,
    goal_value_raw: f64,
    target: (f64, f64),
    target_progress: f64,
    centrality: f64,
    pressure: f64,
) -> f64 {
    let Some(goal_type) = goal_type else {
        return 0.0;
    };
    let goal_target = goal_target.unwrap_or(target);
    let goal_fit = (1.0 - distance(target, goal_target) / 15.0).max(0.0);
    let goal_value = (goal_value_raw * 4.0).clamp(0.0, 1.0);
    let low_pressure = 1.0 - smoothstep(0.35, 0.82, pressure);

    if goal_type == "arc_arrival_for_cutback" {
        return goal_fit
            * goal_value
            * smoothstep(0.62, 0.84, target_progress)
            * smoothstep(0.46, 0.88, centrality)
            * low_pressure;
    }

    if goal_type == "attack_far_post" {
        return goal_fit
            * goal_value
            * smoothstep(0.78, 0.94, target_progress)
            * smoothstep(0.28, 0.76, centrality)
            * low_pressure;
    }

    0.0
}

pub fn state_value(input: &StateValueInput<'_>) -> f64 {
    possession_state_value(input).value
}

pub fn pass_receive_value_breakdown(
    input: &PassReceiveValueInput<'_>,
) -> PassReceiveValueBreakdown {
    pass_receive_value_breakdown_with_optional_target_pressures(input, None, None)
}

pub fn pass_receive_value_breakdown_with_context(
    input: &PassReceiveValueInput<'_>,
    pass_receive_context: Option<&PassReceiveValueContext>,
) -> PassReceiveValueBreakdown {
    pass_receive_value_breakdown_with_optional_target_pressures(input, pass_receive_context, None)
}

pub(crate) fn pass_receive_value_breakdown_with_context_and_precomputed_target_pressures(
    input: &PassReceiveValueInput<'_>,
    pass_receive_context: Option<&PassReceiveValueContext>,
    target_pressures: PassReceiveTargetPressure,
) -> PassReceiveValueBreakdown {
    pass_receive_value_breakdown_with_optional_target_pressures(
        input,
        pass_receive_context,
        Some(target_pressures),
    )
}

fn pass_receive_value_breakdown_with_optional_target_pressures(
    input: &PassReceiveValueInput<'_>,
    pass_receive_context: Option<&PassReceiveValueContext>,
    precomputed_target_pressures: Option<PassReceiveTargetPressure>,
) -> PassReceiveValueBreakdown {
    let target_pressures = precomputed_target_pressures
        .unwrap_or_else(|| pass_receive_target_pressures(input.pos, input.opponent_positions));
    let possession = possession_state_value_evaluation_with_pass_receive_context(
        &state_value_input_from_pass_receive(input),
        pass_receive_context,
        None,
        Some(target_pressures.local),
    )
    .state;
    let progress = attacking_progress(input.pos, input.pitch_length, input.attacking_right);
    let pressure = target_pressures.receiver;
    let centrality = centrality(input.pos.1, input.pitch_width);
    let width_value = 1.0 - centrality;
    let target_width = (input.pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let anchor_width =
        (input.receiver_anchor.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let base_progress = if input.attacking_right {
        input.receiver_base.0 / input.pitch_length
    } else {
        (input.pitch_length - input.receiver_base.0) / input.pitch_length
    };
    let inside_arrival = smoothstep(0.64, 0.84, progress)
        * smoothstep(0.38, 0.76, centrality)
        * (1.0 - smoothstep(0.86, 0.96, progress))
        * smoothstep(0.12, 0.50, (anchor_width - target_width).max(0.0))
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let second_line_arrival = smoothstep(0.64, 0.84, progress)
        * smoothstep(0.42, 0.84, centrality)
        * (1.0 - smoothstep(0.84, 0.95, progress))
        * smoothstep(0.04, 0.24, (progress - base_progress).max(0.0))
        * (1.0 - smoothstep(0.35, 0.82, pressure));
    let receiver_goal_arrival = receiver_goal_arrival_space(
        input.receiver_goal_type,
        input.receiver_goal_target,
        input.receiver_goal_value,
        input.pos,
        progress,
        centrality,
        pressure,
    );
    let mut wide_creation = smoothstep(0.56, 0.78, progress)
        * smoothstep(0.38, 0.72, width_value)
        * (1.0 - smoothstep(0.35, 0.78, pressure));
    let mut box_presence: f64 = 0.0;
    for (idx, x, y) in input.teammate_positions {
        if *idx == input.receiver_index || input.teammate_goalkeeper_indices.contains(idx) {
            continue;
        }
        let tm_progress = if input.attacking_right {
            *x / input.pitch_length
        } else {
            (input.pitch_length - *x) / input.pitch_length
        };
        if tm_progress > 0.74 {
            let tm_centrality =
                1.0 - ((*y - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
            box_presence = box_presence.max(tm_centrality);
        }
    }
    wide_creation *= 0.55 + 0.45 * smoothstep(0.18, 0.70, box_presence);

    let mut recycle_access: f64 = 0.0;
    for (teammate_offset, (idx, x, y)) in input.teammate_positions.iter().enumerate() {
        if *idx == input.receiver_index || input.teammate_goalkeeper_indices.contains(idx) {
            continue;
        }
        let tm_pos = (*x, *y);
        let teammate_pressure = pass_receive_context
            .and_then(|context| context_teammate_pressure(context, teammate_offset, *idx, tm_pos))
            .unwrap_or_else(|| local_pressure(tm_pos, input.opponent_positions));
        let direction = if input.attacking_right { 1.0 } else { -1.0 };
        let backward_progress =
            ((input.pos.0 - tm_pos.0) * direction / input.pitch_length.max(1.0)).clamp(-1.0, 1.0);
        recycle_access = recycle_access.max(
            outlet_quality(
                input.pos,
                tm_pos,
                teammate_pressure,
                input.pitch_length,
                input.attacking_right,
            ) * smoothstep(-0.03, 0.18, backward_progress),
        );
    }
    let role_distance = distance(input.pos, input.receiver_anchor);
    let role_balance = (0.38 + 0.62 * (1.0 - role_distance / 42.0).clamp(0.0, 1.0)).clamp(0.0, 1.0);

    let value = (possession.value * (0.86 + 0.14 * role_balance)).clamp(0.0002, 0.65);

    PassReceiveValueBreakdown {
        value,
        territory: possession.territory,
        pressure_relief: possession.pressure_relief,
        outlet_access: possession.outlet_access,
        support_width: possession.support_width,
        structure: possession.structure,
        creation_access: possession.creation_access,
        role_balance,
        recycle_access,
        wide_creation,
        inside_arrival,
        second_line_arrival,
        receiver_goal_arrival,
        pressure,
        centrality,
        width_value,
        target_width,
        anchor_width,
        base_progress,
        box_presence,
        direct_xg: possession.direct_xg,
        one_link_xg: possession.one_link_xg,
        continuation_xg: possession.continuation_xg,
        control_residual: possession.control_residual,
        continuation_value: possession.continuation_value,
        control_survival: possession.control_survival,
        control_readiness: possession.control_readiness,
    }
}

fn state_value_input_from_pass_receive<'a>(
    input: &PassReceiveValueInput<'a>,
) -> StateValueInput<'a> {
    StateValueInput {
        pos: input.pos,
        player_index: input.receiver_index,
        shot_profiles: input.shot_profiles,
        teammate_positions: input.teammate_positions,
        teammate_goalkeeper_indices: input.teammate_goalkeeper_indices,
        opponent_positions: input.opponent_positions,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attacking_right: input.attacking_right,
        finishing: input.receiver_finishing,
        long_shot: input.receiver_long_shot,
        shot_ideal_distance: input.shot_ideal_distance,
        shot_on_target_base: input.shot_on_target_base,
        gk_save_base: input.gk_save_base,
        gk_attributes: input.gk_attributes,
        gk_pos: input.gk_pos,
        contest_defenders: input.contest_defenders,
        tick: input.tick,
        team_home: input.receiver_team_home,
        shot_quality_cache: input.shot_quality_cache,
        control_state: None,
    }
}

pub fn pass_receive_value(input: &PassReceiveValueInput<'_>) -> f64 {
    pass_receive_value_breakdown(input).value
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reference_receiver_pressure(pos: (f64, f64), opponents: &[(f64, f64)]) -> f64 {
        let mut pressure = 0.0;
        for opponent in opponents {
            let distance = distance(pos, *opponent);
            if distance < 12.0 {
                pressure += 1.0 - distance / 12.0;
            }
        }
        (pressure * 0.35).clamp(0.0, 1.0)
    }

    #[test]
    fn target_pressures_preserve_independent_pressure_formulas() {
        for (pos, opponents) in [
            ((52.0, 34.0), &[][..]),
            ((52.0, 34.0), &[(52.0, 34.0)][..]),
            (
                (64.0, 23.0),
                &[(65.0, 23.0), (69.0, 25.0), (82.0, 40.0)][..],
            ),
        ] {
            let prepared = pass_receive_target_pressures(pos, opponents);

            assert_eq!(
                prepared.local.to_bits(),
                local_pressure(pos, opponents).to_bits()
            );
            assert_eq!(
                prepared.receiver.to_bits(),
                reference_receiver_pressure(pos, opponents).to_bits()
            );
        }
    }

    #[test]
    fn prepared_target_pressures_preserve_pass_receive_value() {
        let opponents = [(64.0, 23.0), (72.0, 29.0), (82.0, 41.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
        ];
        let profiles = [PlayerShotProfile {
            player_index: 1,
            finishing: 0.78,
            long_shot: 0.71,
        }];
        let input = PassReceiveValueInput {
            pos: (67.0, 22.0),
            receiver_index: 1,
            shot_profiles: &profiles,
            receiver_anchor: (60.0, 22.0),
            receiver_base: (54.0, 25.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            receiver_finishing: 0.78,
            receiver_long_shot: 0.71,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            receiver_team_home: true,
            shot_quality_cache: None,
            receiver_goal_type: Some("arc_arrival_for_cutback"),
            receiver_goal_target: Some((75.0, 21.0)),
            receiver_goal_value: 0.56,
        };
        let direct = pass_receive_value_breakdown_with_context(&input, None);
        let prepared = pass_receive_value_breakdown_with_context_and_precomputed_target_pressures(
            &input,
            None,
            pass_receive_target_pressures(input.pos, input.opponent_positions),
        );

        for (direct_value, prepared_value) in [
            (direct.value, prepared.value),
            (direct.territory, prepared.territory),
            (direct.pressure_relief, prepared.pressure_relief),
            (direct.outlet_access, prepared.outlet_access),
            (direct.support_width, prepared.support_width),
            (direct.structure, prepared.structure),
            (direct.creation_access, prepared.creation_access),
            (direct.role_balance, prepared.role_balance),
            (direct.recycle_access, prepared.recycle_access),
            (direct.wide_creation, prepared.wide_creation),
            (direct.inside_arrival, prepared.inside_arrival),
            (direct.second_line_arrival, prepared.second_line_arrival),
            (direct.receiver_goal_arrival, prepared.receiver_goal_arrival),
            (direct.pressure, prepared.pressure),
            (direct.direct_xg, prepared.direct_xg),
            (direct.one_link_xg, prepared.one_link_xg),
            (direct.continuation_xg, prepared.continuation_xg),
            (direct.control_residual, prepared.control_residual),
            (direct.continuation_value, prepared.continuation_value),
            (direct.control_survival, prepared.control_survival),
            (direct.control_readiness, prepared.control_readiness),
        ] {
            assert_eq!(direct_value.to_bits(), prepared_value.to_bits());
        }
    }

    fn state_input<'a>(
        pos: (f64, f64),
        player_index: usize,
        teammates: &'a [(usize, f64, f64)],
        opponents: &'a [(f64, f64)],
    ) -> StateValueInput<'a> {
        StateValueInput {
            pos,
            player_index,
            shot_profiles: &[],
            teammate_positions: teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            finishing: 0.80,
            long_shot: 0.74,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 0,
            team_home: true,
            shot_quality_cache: None,
            control_state: None,
        }
    }

    #[test]
    fn advanced_supported_state_is_more_valuable() {
        let opponents = [(91.0, 17.0), (91.0, 51.0)];
        let deep_teammates = [
            (1, 40.0, 20.0),
            (2, 50.0, 48.0),
            (3, 60.0, 34.0),
            (4, 35.0, 34.0),
        ];
        let advanced_teammates = [
            (1, 61.0, 18.0),
            (2, 64.0, 50.0),
            (3, 77.0, 24.0),
            (4, 80.0, 43.0),
        ];
        let deep = state_value(&state_input((45.0, 34.0), 0, &deep_teammates, &opponents));
        let advanced = state_value(&state_input(
            (72.0, 34.0),
            0,
            &advanced_teammates,
            &opponents,
        ));
        assert!(advanced > deep);
    }

    #[test]
    fn state_value_uses_terminal_geometry_and_finishing() {
        let opponents = [(65.0, 30.0), (69.0, 41.0)];
        let teammates = [
            (1, 42.0, 19.0),
            (2, 47.0, 48.0),
            (3, 30.0, 34.0),
            (4, 58.0, 34.0),
        ];
        let weak = possession_state_value(&state_input((45.0, 34.0), 0, &teammates, &opponents));
        let close = possession_state_value(&state_input((82.0, 34.0), 0, &teammates, &opponents));
        let mut clinical_input = state_input((45.0, 34.0), 0, &teammates, &opponents);
        clinical_input.finishing = 0.96;
        clinical_input.long_shot = 0.94;
        let clinical = possession_state_value(&clinical_input);

        assert!(close.direct_xg > weak.direct_xg);
        assert!(close.value > weak.value);
        assert!(clinical.value > weak.value);
    }

    #[test]
    fn current_controller_terminal_value_respects_release_readiness_only_for_that_player() {
        let opponents = [(101.0, 18.0), (101.0, 50.0)];
        let teammates = [(1, 94.0, 34.0), (2, 70.0, 18.0)];
        let ready = possession_state_value(&state_input((90.0, 34.0), 0, &teammates, &opponents));
        let mut unprepared_input = state_input((90.0, 34.0), 0, &teammates, &opponents);
        unprepared_input.control_state = Some(PossessionControlState {
            facing_direction: 0.0,
            pressure_load: 0.0,
            containment_load: 0.0,
            forward_control: 1.0,
            turn_readiness: 0.0,
            release_window: 1.0,
            shape_readiness: 1.0,
            release_preparation: 0.0,
            stagnation_load: 0.0,
        });
        let unprepared = possession_state_value(&unprepared_input);

        assert!(ready.direct_xg > unprepared.direct_xg);
        assert!(
            (ready.one_link_xg - unprepared.one_link_xg).abs() < 1e-12,
            "the receiver must not inherit the current controller's body preparation"
        );
    }

    #[test]
    fn possession_value_never_discounts_its_already_releasable_direct_shot_twice() {
        let opponents = [(101.0, 18.0), (101.0, 50.0)];
        let teammates = [(1, 94.0, 34.0), (2, 70.0, 18.0)];
        let mut input = state_input((90.0, 34.0), 0, &teammates, &opponents);
        input.control_state = Some(PossessionControlState {
            facing_direction: 0.0,
            pressure_load: 0.15,
            containment_load: 0.10,
            forward_control: 0.70,
            turn_readiness: 0.55,
            release_window: 0.75,
            shape_readiness: 0.40,
            release_preparation: 0.65,
            stagnation_load: 0.10,
        });
        let possession = possession_state_value(&input);

        assert!(
            possession.value + 1e-12 >= possession.direct_xg,
            "possession value must contain the already readiness-adjusted direct shot branch: {possession:?}"
        );
        assert!(
            possession.value <= possession.continuation_value + 1e-12,
            "readiness may discount only the continuation surplus: {possession:?}"
        );
    }

    #[test]
    fn structure_and_outlets_raise_controllable_state_value() {
        let opponents = [(62.0, 34.0), (68.0, 42.0)];
        let compressed = [(1, 48.0, 33.0), (2, 49.0, 35.0), (3, 47.0, 34.0)];
        let layered = [
            (1, 34.0, 17.0),
            (2, 37.0, 52.0),
            (3, 57.0, 24.0),
            (4, 62.0, 43.0),
        ];
        let compressed_value =
            possession_state_value(&state_input((45.0, 34.0), 0, &compressed, &opponents));
        let layered_value =
            possession_state_value(&state_input((45.0, 34.0), 0, &layered, &opponents));

        assert!(layered_value.support_width > compressed_value.support_width);
        assert!(layered_value.one_link_xg > compressed_value.one_link_xg);
        assert!(layered_value.value > compressed_value.value);
    }

    #[test]
    fn one_link_terminal_value_uses_receiver_shooting_profile() {
        let opponents = [(84.0, 26.0), (86.0, 42.0)];
        let teammates = [(1, 88.0, 34.0), (2, 56.0, 18.0)];
        let mut low_finisher = state_input((58.0, 34.0), 0, &teammates, &opponents);
        low_finisher.shot_profiles = &[PlayerShotProfile {
            player_index: 1,
            finishing: 0.30,
            long_shot: 0.30,
        }];
        let mut clinical_finisher = state_input((58.0, 34.0), 0, &teammates, &opponents);
        clinical_finisher.shot_profiles = &[PlayerShotProfile {
            player_index: 1,
            finishing: 0.95,
            long_shot: 0.95,
        }];

        let low_value = possession_state_value(&low_finisher);
        let clinical_value = possession_state_value(&clinical_finisher);

        assert!(clinical_value.one_link_xg > low_value.one_link_xg);
        assert!(clinical_value.value > low_value.value);
    }

    #[test]
    fn controllable_connection_chain_is_worth_more_than_its_first_link() {
        let opponents = [(76.0, 18.0), (76.0, 50.0)];
        let teammates = [
            (1, 26.0, 20.0),
            (2, 40.0, 48.0),
            (3, 56.0, 25.0),
            (4, 72.0, 43.0),
            (5, 86.0, 34.0),
        ];
        let possession =
            possession_state_value(&state_input((14.0, 34.0), 0, &teammates, &opponents));

        assert!(possession.continuation_xg > possession.one_link_xg);
        assert!(possession.continuation_value > possession.direct_xg);
        assert_eq!(possession.value, possession.continuation_value);
    }

    #[test]
    fn safe_controlled_recycle_beats_a_negligible_terminal_attempt() {
        use crate::{temporal_option_value, PossessionTransition, TemporalOptionValueInput};

        let opponents = [(76.0, 18.0), (76.0, 50.0)];
        let deep_teammates = [
            (1, 26.0, 20.0),
            (2, 40.0, 48.0),
            (3, 56.0, 25.0),
            (4, 72.0, 43.0),
            (5, 86.0, 34.0),
        ];
        let recycle_teammates = [
            (0, 14.0, 34.0),
            (2, 40.0, 48.0),
            (3, 56.0, 25.0),
            (4, 72.0, 43.0),
            (5, 86.0, 34.0),
        ];
        let deep =
            possession_state_value(&state_input((14.0, 34.0), 0, &deep_teammates, &opponents));
        let recycled = possession_state_value(&state_input(
            (26.0, 20.0),
            1,
            &recycle_teammates,
            &opponents,
        ));
        let recycle = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: deep.value,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.91,
                retained_control_value: recycled.value,
                opposing_control_probability: 0.09,
                opposing_control_value: 0.03,
            },
            duration_seconds: 2.0,
            tempo: 0.42,
            risk_budget: 0.34,
        });
        let terminal = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: deep.value,
            transition: PossessionTransition {
                goal_probability: deep.direct_xg,
                retained_control_probability: 0.0,
                retained_control_value: 0.0,
                opposing_control_probability: 1.0 - deep.direct_xg,
                opposing_control_value: 0.03,
            },
            duration_seconds: 8.0,
            tempo: 0.42,
            risk_budget: 0.34,
        });

        assert!(deep.direct_xg < 0.01);
        assert!(recycle.score > terminal.score);
    }

    #[test]
    fn support_network_increases_control_horizon_residual_without_a_terminal_shot() {
        let opponents = [(70.0, 12.0), (70.0, 56.0)];
        let isolated = [(1, 20.0, 34.0), (2, 24.0, 35.0), (3, 28.0, 33.0)];
        let connected = [
            (1, 20.0, 18.0),
            (2, 34.0, 50.0),
            (3, 49.0, 24.0),
            (4, 62.0, 43.0),
        ];
        let isolated_value =
            possession_state_value(&state_input((15.0, 34.0), 0, &isolated, &opponents));
        let connected_value =
            possession_state_value(&state_input((15.0, 34.0), 0, &connected, &opponents));

        assert!(connected_value.direct_xg < 0.01);
        assert!(connected_value.control_residual > isolated_value.control_residual);
        assert!(connected_value.value > isolated_value.value);
    }

    #[test]
    fn possession_value_context_preserves_bellman_value_for_multiple_targets() {
        let opponents = [(78.0, 16.0), (80.0, 34.0), (78.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 0,
                finishing: 0.82,
                long_shot: 0.74,
            },
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let base = StateValueInput {
            pos: (46.0, 34.0),
            player_index: 0,
            shot_profiles: &profiles,
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            finishing: 0.82,
            long_shot: 0.74,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            team_home: true,
            shot_quality_cache: None,
            control_state: None,
        };
        let context = possession_value_context(&base);

        for pos in [(46.0, 34.0), (53.0, 29.0), (61.0, 40.0)] {
            let input = StateValueInput { pos, ..base };
            let uncached = possession_state_value(&input);
            let cached = possession_state_value_with_context(&input, &context);

            macro_rules! assert_field {
                ($field:ident) => {
                    assert_eq!(
                        cached.$field.to_bits(),
                        uncached.$field.to_bits(),
                        stringify!($field)
                    );
                };
            }

            assert_field!(value);
            assert_field!(territory);
            assert_field!(pressure_relief);
            assert_field!(outlet_access);
            assert_field!(support_width);
            assert_field!(structure);
            assert_field!(creation_access);
            assert_field!(direct_xg);
            assert_field!(one_link_xg);
            assert_field!(continuation_xg);
            assert_field!(control_residual);
            assert_field!(continuation_value);
            assert_field!(control_survival);
            assert_field!(control_readiness);
        }
    }

    #[test]
    fn possession_value_context_recomputes_when_teammate_snapshot_changes() {
        let opponents = [(72.0, 18.0), (78.0, 34.0), (76.0, 50.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 57.0, 20.0),
            (2, 65.0, 44.0),
            (3, 74.0, 28.0),
            (4, 82.0, 48.0),
        ];
        let moved_teammates = [
            (0, 46.0, 34.0),
            (1, 52.0, 14.0),
            (2, 70.0, 54.0),
            (3, 78.0, 24.0),
            (4, 88.0, 42.0),
        ];
        let base = state_input((46.0, 34.0), 0, &teammates, &opponents);
        let context = possession_value_context(&base);
        let bellman_geometry = possession_bellman_geometry(&base, &context);
        let moved_input = StateValueInput {
            teammate_positions: &moved_teammates,
            ..base
        };
        let uncached = possession_state_value(&moved_input);
        let cached = possession_state_value_with_context(&moved_input, &context);
        let cached_geometry = possession_state_value_with_context_and_bellman_geometry(
            &moved_input,
            &context,
            &bellman_geometry,
        );

        macro_rules! assert_equivalent {
            ($field:ident) => {
                assert_eq!(
                    cached.$field.to_bits(),
                    uncached.$field.to_bits(),
                    concat!("context.", stringify!($field))
                );
                assert_eq!(
                    cached_geometry.$field.to_bits(),
                    uncached.$field.to_bits(),
                    concat!("geometry.", stringify!($field))
                );
            };
        }

        assert_equivalent!(value);
        assert_equivalent!(territory);
        assert_equivalent!(pressure_relief);
        assert_equivalent!(outlet_access);
        assert_equivalent!(support_width);
        assert_equivalent!(structure);
        assert_equivalent!(creation_access);
        assert_equivalent!(direct_xg);
        assert_equivalent!(one_link_xg);
        assert_equivalent!(continuation_xg);
        assert_equivalent!(control_residual);
        assert_equivalent!(continuation_value);
        assert_equivalent!(control_survival);
        assert_equivalent!(control_readiness);
    }

    #[test]
    fn compiled_possession_context_preserves_bellman_value_for_control_states() {
        let opponents = [(78.0, 16.0), (80.0, 34.0), (78.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 0,
                finishing: 0.82,
                long_shot: 0.74,
            },
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let base = StateValueInput {
            pos: (46.0, 34.0),
            player_index: 0,
            shot_profiles: &profiles,
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            finishing: 0.82,
            long_shot: 0.74,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            team_home: true,
            shot_quality_cache: None,
            control_state: None,
        };
        let context = possession_value_context(&base);
        let bellman_geometry = possession_bellman_geometry(&base, &context);

        for control_state in [
            PossessionControlState::default(),
            PossessionControlState {
                facing_direction: 180.0,
                pressure_load: 0.54,
                containment_load: 0.42,
                forward_control: 0.16,
                turn_readiness: 0.28,
                release_window: 0.34,
                shape_readiness: 0.48,
                release_preparation: 0.20,
                stagnation_load: 0.38,
            },
        ] {
            let input = StateValueInput {
                control_state: Some(control_state),
                ..base
            };
            let uncached = possession_state_value(&input);
            let cached = possession_state_value_with_context_and_bellman_geometry(
                &input,
                &context,
                &bellman_geometry,
            );

            macro_rules! assert_field {
                ($field:ident) => {
                    assert_eq!(
                        cached.$field.to_bits(),
                        uncached.$field.to_bits(),
                        stringify!($field)
                    );
                };
            }

            assert_field!(value);
            assert_field!(territory);
            assert_field!(pressure_relief);
            assert_field!(outlet_access);
            assert_field!(support_width);
            assert_field!(structure);
            assert_field!(creation_access);
            assert_field!(direct_xg);
            assert_field!(one_link_xg);
            assert_field!(continuation_xg);
            assert_field!(control_residual);
            assert_field!(continuation_value);
            assert_field!(control_survival);
            assert_field!(control_readiness);
        }
    }

    #[test]
    fn pass_receive_context_preserves_value_for_multiple_targets() {
        let opponents = [(78.0, 16.0), (80.0, 34.0), (78.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let base = PassReceiveValueInput {
            pos: (58.0, 24.0),
            receiver_index: 1,
            shot_profiles: &profiles,
            receiver_anchor: (60.0, 22.0),
            receiver_base: (54.0, 25.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            receiver_finishing: 0.78,
            receiver_long_shot: 0.71,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            receiver_team_home: true,
            shot_quality_cache: None,
            receiver_goal_type: None,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
        };
        let context = pass_receive_value_context(&base);

        for pos in [(58.0, 24.0), (63.0, 30.0), (67.0, 19.0)] {
            let input = PassReceiveValueInput { pos, ..base };
            let uncached = pass_receive_value_breakdown(&input);
            let cached = pass_receive_value_breakdown_with_context(&input, Some(&context));

            assert_eq!(cached.value, uncached.value);
            assert_eq!(cached.direct_xg, uncached.direct_xg);
            assert_eq!(cached.one_link_xg, uncached.one_link_xg);
            assert_eq!(cached.continuation_xg, uncached.continuation_xg);
            assert_eq!(cached.control_residual, uncached.control_residual);
            assert_eq!(cached.continuation_value, uncached.continuation_value);
        }
    }

    #[test]
    fn pass_receive_context_recomputes_when_teammate_snapshot_changes() {
        let opponents = [(70.0, 18.0), (78.0, 34.0), (76.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let moved_teammates = [
            (0, 46.0, 34.0),
            (1, 62.0, 19.0),
            (2, 72.0, 12.0),
            (3, 77.0, 48.0),
            (4, 87.0, 38.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let base = PassReceiveValueInput {
            pos: (63.0, 26.0),
            receiver_index: 1,
            shot_profiles: &profiles,
            receiver_anchor: (60.0, 22.0),
            receiver_base: (54.0, 25.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            receiver_finishing: 0.78,
            receiver_long_shot: 0.71,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            receiver_team_home: true,
            shot_quality_cache: None,
            receiver_goal_type: Some("arc_arrival_for_cutback"),
            receiver_goal_target: Some((76.0, 24.0)),
            receiver_goal_value: 0.56,
        };
        let context = pass_receive_value_context(&base);
        let moved_input = PassReceiveValueInput {
            teammate_positions: &moved_teammates,
            ..base
        };
        let uncached = pass_receive_value_breakdown(&moved_input);
        let cached = pass_receive_value_breakdown_with_context(&moved_input, Some(&context));

        for (cached_value, uncached_value) in [
            (cached.value, uncached.value),
            (cached.territory, uncached.territory),
            (cached.pressure_relief, uncached.pressure_relief),
            (cached.outlet_access, uncached.outlet_access),
            (cached.support_width, uncached.support_width),
            (cached.structure, uncached.structure),
            (cached.creation_access, uncached.creation_access),
            (cached.role_balance, uncached.role_balance),
            (cached.recycle_access, uncached.recycle_access),
            (cached.wide_creation, uncached.wide_creation),
            (cached.inside_arrival, uncached.inside_arrival),
            (cached.second_line_arrival, uncached.second_line_arrival),
            (cached.receiver_goal_arrival, uncached.receiver_goal_arrival),
            (cached.pressure, uncached.pressure),
            (cached.direct_xg, uncached.direct_xg),
            (cached.one_link_xg, uncached.one_link_xg),
            (cached.continuation_xg, uncached.continuation_xg),
            (cached.control_residual, uncached.control_residual),
            (cached.continuation_value, uncached.continuation_value),
            (cached.control_survival, uncached.control_survival),
            (cached.control_readiness, uncached.control_readiness),
        ] {
            assert_eq!(cached_value.to_bits(), uncached_value.to_bits());
        }
    }

    #[test]
    fn team_pass_receive_context_preserves_static_nodes_with_missing_profiles() {
        let opponents = [(78.0, 16.0), (80.0, 34.0), (78.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let seed = PassReceiveValueInput {
            pos: (46.0, 34.0),
            receiver_index: 0,
            shot_profiles: &profiles,
            receiver_anchor: (46.0, 34.0),
            receiver_base: (46.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            receiver_finishing: 0.68,
            receiver_long_shot: 0.61,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            receiver_team_home: true,
            shot_quality_cache: None,
            receiver_goal_type: None,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
        };
        let team_context = pass_receive_team_value_context(&seed);

        for (receiver_index, pos, finishing, long_shot) in
            [(1, (58.0, 24.0), 0.78, 0.71), (2, (68.0, 18.0), 0.64, 0.59)]
        {
            let input = PassReceiveValueInput {
                pos,
                receiver_index,
                receiver_anchor: pos,
                receiver_base: pos,
                receiver_finishing: finishing,
                receiver_long_shot: long_shot,
                ..seed
            };
            let uncached_context = pass_receive_value_context(&input);
            let shared_context =
                pass_receive_value_context_with_team_context(&input, &team_context);
            let uncached =
                pass_receive_value_breakdown_with_context(&input, Some(&uncached_context));
            let shared = pass_receive_value_breakdown_with_context(&input, Some(&shared_context));

            assert_eq!(shared.value.to_bits(), uncached.value.to_bits());
            assert_eq!(shared.direct_xg.to_bits(), uncached.direct_xg.to_bits());
            assert_eq!(shared.one_link_xg.to_bits(), uncached.one_link_xg.to_bits());
            assert_eq!(
                shared.continuation_xg.to_bits(),
                uncached.continuation_xg.to_bits()
            );
            assert_eq!(
                shared.control_residual.to_bits(),
                uncached.control_residual.to_bits()
            );
            assert_eq!(
                shared.continuation_value.to_bits(),
                uncached.continuation_value.to_bits()
            );
        }
    }

    #[test]
    fn team_pass_receive_context_recomputes_when_opponent_snapshot_changes() {
        let opponents = [(78.0, 16.0), (80.0, 34.0), (78.0, 52.0)];
        let moved_opponents = [(79.5, 16.0), (80.0, 31.0), (78.0, 52.0)];
        let teammates = [
            (0, 46.0, 34.0),
            (1, 58.0, 24.0),
            (2, 68.0, 18.0),
            (3, 72.0, 43.0),
            (4, 82.0, 34.0),
        ];
        let profiles = [
            PlayerShotProfile {
                player_index: 1,
                finishing: 0.78,
                long_shot: 0.71,
            },
            PlayerShotProfile {
                player_index: 4,
                finishing: 0.91,
                long_shot: 0.78,
            },
        ];
        let seed = PassReceiveValueInput {
            pos: (46.0, 34.0),
            receiver_index: 0,
            shot_profiles: &profiles,
            receiver_anchor: (46.0, 34.0),
            receiver_base: (46.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
            receiver_finishing: 0.68,
            receiver_long_shot: 0.61,
            shot_ideal_distance: 20.0,
            shot_on_target_base: 0.50,
            gk_save_base: 0.78,
            gk_attributes: None,
            gk_pos: None,
            contest_defenders: None,
            tick: 8,
            receiver_team_home: true,
            shot_quality_cache: None,
            receiver_goal_type: None,
            receiver_goal_target: None,
            receiver_goal_value: 0.0,
        };
        let team_context = pass_receive_team_value_context(&seed);
        let input = PassReceiveValueInput {
            pos: (58.0, 24.0),
            receiver_index: 1,
            receiver_anchor: (58.0, 24.0),
            receiver_base: (58.0, 24.0),
            receiver_finishing: 0.78,
            receiver_long_shot: 0.71,
            opponent_positions: &moved_opponents,
            ..seed
        };

        let uncached_context = pass_receive_value_context(&input);
        let shared_context = pass_receive_value_context_with_team_context(&input, &team_context);
        let uncached = pass_receive_value_breakdown_with_context(&input, Some(&uncached_context));
        let shared = pass_receive_value_breakdown_with_context(&input, Some(&shared_context));

        assert_eq!(shared.value.to_bits(), uncached.value.to_bits());
        assert_eq!(shared.direct_xg.to_bits(), uncached.direct_xg.to_bits());
        assert_eq!(shared.one_link_xg.to_bits(), uncached.one_link_xg.to_bits());
        assert_eq!(
            shared.continuation_xg.to_bits(),
            uncached.continuation_xg.to_bits()
        );
        assert_eq!(
            shared.continuation_value.to_bits(),
            uncached.continuation_value.to_bits()
        );
    }
}
