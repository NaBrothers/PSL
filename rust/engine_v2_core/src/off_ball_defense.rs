use crate::decision::softmax_select_index;
use crate::match_flow::{
    player_move_speed, player_move_tick, score_block_lane_zone, score_mark_runner_zone,
    DefenseZoneAttackerInput, DefenseZoneHelperInput, PlayerMoveSpeedInput, PlayerMoveTickInput,
};
use crate::physics::{distance, smoothstep};
use crate::position_value::{defensive_position_value, DefensivePositionValueInput};
use crate::shot_quality::{
    estimate_shot_contest, shot_contest_engagement, shot_contest_intent, ShotContestDefender,
};
use crate::team_plan::TeamPlanSignals;

#[derive(Clone, Copy, Debug)]
pub struct DefenseTeammateInput {
    pub pos: (f64, f64),
    pub target_pos: (f64, f64),
    pub anchor: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseMovementInput<'a> {
    pub velocity: (f64, f64),
    pub speed_ability: i32,
    pub defence: f64,
    pub state: &'a str,
    pub plan_signals: TeamPlanSignals,
    pub player_max_speed: f64,
    pub player_min_speed: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseMotionOutput {
    pub movement_target: (f64, f64),
    pub pos: (f64, f64),
    pub velocity: (f64, f64),
    pub distance_covered: f64,
    pub facing_direction: Option<f64>,
}

#[derive(Debug)]
pub struct DefenseScoreInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub base_ref: (f64, f64),
    pub ball_pos: (f64, f64),
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub ball_carrier_consecutive_carries: i32,
    pub ball_carrier_possession_ticks: i32,
    pub carrier_control_readiness: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub press_radius: f64,
    pub tackle_range: f64,
    pub carrier_speed: f64,
    pub press_intensity: f64,
    pub compactness: f64,
    pub movement: DefenseMovementInput<'a>,
    pub candidates: &'a [(f64, f64)],
    pub attackers: &'a [(f64, f64)],
    pub local_attackers: &'a [(f64, f64)],
    pub dangerous_receivers: &'a [(f64, f64)],
    pub teammates: &'a [DefenseTeammateInput],
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseScoreOutput {
    pub score: f64,
    pub target: (f64, f64),
    pub movement_target: (f64, f64),
    pub projected_pos: (f64, f64),
    pub action_type: &'static str,
    pub residual_threat: f64,
    pub base_score: f64,
    pub press_value: f64,
    pub press_access: f64,
    pub carrier_threat: f64,
    pub shot_lane_closure: f64,
    pub best_mark_value: f64,
}

#[derive(Clone, Copy)]
struct DefenseScoreContext {
    own_goal_x: f64,
    own_goal: (f64, f64),
    dist_to_ball: f64,
    shot_danger: f64,
    carrier_control_threat: f64,
    press_access: f64,
    immediate_threat: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseRandomSample {
    pub angle_unit: f64,
    pub radius_unit: f64,
}

#[derive(Debug)]
pub struct DefenseRawInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub carrier_speed: f64,
    pub carrier_control_threat: f64,
    pub shot_danger: f64,
    pub local_attackers: &'a [(f64, f64)],
    pub dangerous_receivers: &'a [(f64, f64)],
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub carrier_velocity: (f64, f64),
    pub shot_lane_threat: f64,
    pub random_samples: &'a [DefenseRandomSample],
}

#[derive(Debug)]
pub struct DefenseChoiceInput<'a> {
    pub defender_pos: (f64, f64),
    pub anchor: (f64, f64),
    pub base_ref: (f64, f64),
    pub ball_pos: (f64, f64),
    pub ball_carrier_pos: Option<(f64, f64)>,
    pub carrier_velocity: (f64, f64),
    pub ball_carrier_consecutive_carries: i32,
    pub ball_carrier_possession_ticks: i32,
    pub carrier_control_readiness: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub press_radius: f64,
    pub tackle_range: f64,
    pub carrier_speed: f64,
    pub press_intensity: f64,
    pub compactness: f64,
    pub movement: DefenseMovementInput<'a>,
    pub iq: f64,
    pub attackers: &'a [(f64, f64)],
    pub teammates: &'a [DefenseTeammateInput],
    pub random_samples: &'a [DefenseRandomSample],
    pub score_noises: &'a [f64],
    pub roll_by_count: &'a [f64],
    pub fallback_index_by_count: &'a [usize],
}

fn predicted_carrier_interception_point(input: &DefenseRawInput<'_>) -> Option<(f64, f64)> {
    let carrier_pos = input.ball_carrier_pos?;
    let velocity = input.carrier_velocity;
    let current_speed = (velocity.0 * velocity.0 + velocity.1 * velocity.1).sqrt();
    if current_speed <= 1e-6 {
        return None;
    }
    let direction = (velocity.0 / current_speed, velocity.1 / current_speed);
    let reachable_speed = input.carrier_speed.max(current_speed);
    let acceleration = (
        direction.0 * (reachable_speed - current_speed) * 0.35,
        direction.1 * (reachable_speed - current_speed) * 0.35,
    );
    let separation = distance(input.defender_pos, carrier_pos);
    let horizon = (0.45 + separation / 18.0).clamp(0.45, 1.65);
    Some(pitch_clamp(
        (
            carrier_pos.0 + velocity.0 * horizon + 0.5 * acceleration.0 * horizon * horizon,
            carrier_pos.1 + velocity.1 * horizon + 0.5 * acceleration.1 * horizon * horizon,
        ),
        input.pitch_length,
        input.pitch_width,
    ))
}

fn carrier_breakthrough_basis(input: &DefenseRawInput<'_>) -> ((f64, f64), (f64, f64)) {
    let own_goal = (
        if input.attacking_right {
            0.0
        } else {
            input.pitch_length
        },
        input.pitch_width * 0.5,
    );
    let goal_delta = (own_goal.0 - input.ball_pos.0, own_goal.1 - input.ball_pos.1);
    let goal_length = (goal_delta.0 * goal_delta.0 + goal_delta.1 * goal_delta.1)
        .sqrt()
        .max(1e-6);
    let goal_direction = (goal_delta.0 / goal_length, goal_delta.1 / goal_length);
    let carrier_speed = (input.carrier_velocity.0 * input.carrier_velocity.0
        + input.carrier_velocity.1 * input.carrier_velocity.1)
        .sqrt();
    let carrier_direction = if carrier_speed > 1e-6 {
        (
            input.carrier_velocity.0 / carrier_speed,
            input.carrier_velocity.1 / carrier_speed,
        )
    } else {
        goal_direction
    };
    let forward_raw = (
        0.78 * carrier_direction.0 + 0.22 * goal_direction.0,
        0.78 * carrier_direction.1 + 0.22 * goal_direction.1,
    );
    let forward_length = (forward_raw.0 * forward_raw.0 + forward_raw.1 * forward_raw.1)
        .sqrt()
        .max(1e-6);
    let forward = (
        forward_raw.0 / forward_length,
        forward_raw.1 / forward_length,
    );
    (forward, (-forward.1, forward.0))
}

#[derive(Clone, Copy, Debug)]
pub struct DefenseGoalCandidate {
    pub action_type: &'static str,
    pub target: (f64, f64),
    pub value: f64,
}

#[derive(Clone, Debug)]
pub struct DefenseChoiceOutput {
    pub action_type: &'static str,
    pub target: (f64, f64),
    pub score: f64,
    pub candidate_count: usize,
    pub local_attackers_count: usize,
    pub dangerous_receivers_count: usize,
    pub raw_targets: Vec<(f64, f64)>,
    pub candidate_targets: Vec<(f64, f64)>,
    pub candidate_scores: Vec<f64>,
    pub candidate_movement_targets: Vec<(f64, f64)>,
    pub candidate_projected_positions: Vec<(f64, f64)>,
    pub candidate_action_types: Vec<&'static str>,
    pub candidate_residual_threats: Vec<f64>,
    pub goal_candidates: Vec<DefenseGoalCandidate>,
    pub used_roll: bool,
    pub used_random_choice: bool,
    pub press_access: f64,
    pub shot_danger: f64,
    pub carrier_control_threat: f64,
    pub base_score: f64,
    pub press_value: f64,
    pub carrier_threat: f64,
    pub shot_lane_closure: f64,
    pub best_mark_value: f64,
}

#[derive(Clone, Debug)]
pub struct DefensePreparedChoice {
    raw_targets: Vec<(f64, f64)>,
    scored: Vec<DefenseScoreOutput>,
    local_attackers_count: usize,
    dangerous_receivers_count: usize,
    shot_danger: f64,
    carrier_control_threat: f64,
    press_access: f64,
}

impl DefensePreparedChoice {
    pub fn candidate_count(&self) -> usize {
        self.scored.len()
    }

    pub fn best_scored_candidate(&self) -> Option<DefenseScoreOutput> {
        self.scored.iter().copied().max_by(|left, right| {
            left.score
                .partial_cmp(&right.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
    }
}

struct DefensePreparedSelection {
    chosen_index: usize,
    noisy_scores: Vec<f64>,
    used_roll: bool,
    used_random_choice: bool,
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn defense_action_movement_intent(action: &str) -> &'static str {
    match action {
        "smother" => "contest",
        "close_down" | "tackle" | "approach" | "pursuit" => "press",
        "mark_runner" => "mark",
        "block_lane" => "block_lane",
        _ => "defend_shape",
    }
}

pub fn project_defense_action_motion(
    defender_pos: (f64, f64),
    target: (f64, f64),
    _anchor: (f64, f64),
    action: &str,
    movement: DefenseMovementInput<'_>,
) -> DefenseMotionOutput {
    let movement_target = target;
    let movement_intent = defense_action_movement_intent(action);
    let tick = if action == "smother" {
        let desired_speed = player_move_speed(&PlayerMoveSpeedInput {
            pos: defender_pos,
            target_pos: movement_target,
            speed_ability: movement.speed_ability,
            movement_intent,
            state: movement.state,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
        })
        .speed;
        let motion = crate::physics::advance_player_motion(&crate::physics::PlayerMotionInput {
            pos: defender_pos,
            target: movement_target,
            velocity: movement.velocity,
            speed_ability: movement.speed_ability,
            desired_speed,
            acceleration_scale: 1.5,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
            pitch_length: movement.pitch_length,
            pitch_width: movement.pitch_width,
        });
        crate::match_flow::PlayerMoveTickOutput {
            moved: motion.distance_covered > 1e-6,
            pos: motion.pos,
            velocity: motion.velocity,
            distance_covered: motion.distance_covered,
            facing_direction: motion.facing_direction,
            desired_speed,
        }
    } else {
        player_move_tick(&PlayerMoveTickInput {
            pos: defender_pos,
            target_pos: movement_target,
            velocity: movement.velocity,
            speed_ability: movement.speed_ability,
            movement_intent,
            state: movement.state,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
            pitch_length: movement.pitch_length,
            pitch_width: movement.pitch_width,
        })
    };
    DefenseMotionOutput {
        movement_target,
        pos: tick.pos,
        velocity: tick.velocity,
        distance_covered: tick.distance_covered,
        facing_direction: tick.facing_direction,
    }
}

pub fn defensive_pursuit_reachability(
    defender_pos: (f64, f64),
    carrier_pos: (f64, f64),
    anchor: (f64, f64),
    press_radius: f64,
    movement: DefenseMovementInput<'_>,
    commitment_ticks: i32,
) -> f64 {
    let mut projected_pos = defender_pos;
    let mut projected_velocity = movement.velocity;
    let mut closest_distance = distance(defender_pos, carrier_pos);
    for _ in 0..commitment_ticks.clamp(1, 8) {
        let motion = project_defense_action_motion(
            projected_pos,
            carrier_pos,
            anchor,
            "approach",
            DefenseMovementInput {
                velocity: projected_velocity,
                ..movement
            },
        );
        closest_distance = closest_distance.min(distance(motion.pos, carrier_pos));
        projected_pos = motion.pos;
        projected_velocity = motion.velocity;
    }
    1.0 - smoothstep(
        press_radius.max(0.1) * 0.32,
        press_radius.max(0.1) * 0.92,
        closest_distance,
    )
}

pub fn defensive_approach_reachability(
    defender_pos: (f64, f64),
    carrier_pos: (f64, f64),
    anchor: (f64, f64),
    press_radius: f64,
    movement: DefenseMovementInput<'_>,
    commitment_ticks: i32,
) -> f64 {
    defensive_pursuit_reachability(
        defender_pos,
        carrier_pos,
        anchor,
        press_radius,
        movement,
        commitment_ticks,
    )
}

pub fn defensive_interception_reachability(
    defender_pos: (f64, f64),
    carrier_pos: (f64, f64),
    carrier_velocity: (f64, f64),
    anchor: (f64, f64),
    press_radius: f64,
    movement: DefenseMovementInput<'_>,
    commitment_ticks: i32,
) -> f64 {
    let mut projected_defender_pos = defender_pos;
    let mut projected_defender_velocity = movement.velocity;
    let mut projected_carrier_pos = carrier_pos;
    let mut best_reachability = 0.0_f64;
    let contact_radius = (press_radius.max(0.1) * 0.22).clamp(1.0, 2.8);

    for elapsed_tick in 1..=commitment_ticks.clamp(1, 8) {
        let next_carrier_pos = pitch_clamp(
            (
                projected_carrier_pos.0 + carrier_velocity.0,
                projected_carrier_pos.1 + carrier_velocity.1,
            ),
            movement.pitch_length,
            movement.pitch_width,
        );
        let motion = project_defense_action_motion(
            projected_defender_pos,
            next_carrier_pos,
            anchor,
            "pursuit",
            DefenseMovementInput {
                velocity: projected_defender_velocity,
                ..movement
            },
        );
        let relative_start = (
            projected_defender_pos.0 - projected_carrier_pos.0,
            projected_defender_pos.1 - projected_carrier_pos.1,
        );
        let relative_end = (
            motion.pos.0 - next_carrier_pos.0,
            motion.pos.1 - next_carrier_pos.1,
        );
        let closest_distance =
            closest_distance_to_motion_segment((0.0, 0.0), relative_start, relative_end);
        let contact_access =
            1.0 - smoothstep(contact_radius * 0.58, contact_radius, closest_distance);
        let arrival_discount = (-0.24 * (elapsed_tick - 1) as f64).exp();
        best_reachability = best_reachability.max(contact_access * arrival_discount);
        projected_defender_pos = motion.pos;
        projected_defender_velocity = motion.velocity;
        projected_carrier_pos = next_carrier_pos;
    }

    best_reachability
}

fn closest_distance_to_motion_segment(
    point: (f64, f64),
    start: (f64, f64),
    end: (f64, f64),
) -> f64 {
    let direction = (end.0 - start.0, end.1 - start.1);
    let length_squared = direction.0 * direction.0 + direction.1 * direction.1;
    if length_squared <= 1e-9 {
        return distance(point, start);
    }
    let projected =
        ((point.0 - start.0) * direction.0 + (point.1 - start.1) * direction.1) / length_squared;
    let fraction = projected.clamp(0.0, 1.0);
    distance(
        point,
        (
            start.0 + direction.0 * fraction,
            start.1 + direction.1 * fraction,
        ),
    )
}

fn close_down_contact_window(
    defender_pos: (f64, f64),
    carrier_pos: (f64, f64),
    anchor: (f64, f64),
    tackle_range: f64,
    movement: DefenseMovementInput<'_>,
) -> f64 {
    let motion =
        project_defense_action_motion(defender_pos, carrier_pos, anchor, "close_down", movement);
    let approach_reach = (0.75 + 0.36 * tackle_range.max(0.0)) * 0.94;
    let closest_distance =
        closest_distance_to_motion_segment(carrier_pos, defender_pos, motion.pos);
    1.0 - smoothstep(approach_reach * 0.72, approach_reach, closest_distance)
}

fn shot_lane_closure(
    point: (f64, f64),
    ball_pos: (f64, f64),
    own_goal_x: f64,
    pitch_width: f64,
) -> f64 {
    let goal_y = pitch_width / 2.0;
    let shot_dx = own_goal_x - ball_pos.0;
    let shot_dy = goal_y - ball_pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    if shot_len <= 1.0 {
        return 0.0;
    }
    let nx = shot_dx / shot_len;
    let ny = shot_dy / shot_len;
    let relx = point.0 - ball_pos.0;
    let rely = point.1 - ball_pos.1;
    let proj = relx * nx + rely * ny;
    if proj <= 0.5 || proj >= shot_len - 0.5 {
        return 0.0;
    }
    let perp = (relx * ny - rely * nx).abs();
    let lane = 1.0 - smoothstep(1.8, 7.5, perp);
    let depth = 1.0 - ((proj / shot_len) - 0.40).abs().min(0.52) / 0.52;
    lane.max(0.0) * (0.42 + 0.58 * depth.max(0.0))
}

fn local_press_access(
    defender_pos: (f64, f64),
    ball_carrier_pos: Option<(f64, f64)>,
    press_radius: f64,
) -> f64 {
    ball_carrier_pos.map_or(0.0, |carrier_pos| {
        1.0 - smoothstep(
            press_radius.max(0.1) * 0.45,
            press_radius.max(0.1) * 1.20,
            distance(defender_pos, carrier_pos),
        )
    })
}

fn carrier_control_threat(input: &DefenseScoreInput<'_>) -> f64 {
    let Some(carrier_pos) = input.ball_carrier_pos else {
        return 0.0;
    };
    let nearest_defender_distance = std::iter::once(input.defender_pos)
        .chain(input.teammates.iter().map(|teammate| teammate.pos))
        .map(|defender_pos| distance(defender_pos, carrier_pos))
        .fold(f64::INFINITY, f64::min);
    let settled_control = 1.0 - (-(input.ball_carrier_possession_ticks.max(0) as f64) / 4.0).exp();
    let receiving_window =
        (1.0 - settled_control) * (0.30 + 0.70 * input.carrier_control_readiness.clamp(0.0, 1.0));
    let control_duration = settled_control.max(receiving_window);
    let pressure_arrival_scale = (input.press_radius * 0.55).max(0.1);
    let pressure_absence = 1.0 - (-nearest_defender_distance / pressure_arrival_scale).exp();
    let control_availability = input.carrier_control_readiness.clamp(0.0, 1.0);

    (control_duration * (0.24 + 0.76 * control_availability) * (0.18 + 0.82 * pressure_absence))
        .clamp(0.0, 1.0)
}

const MAX_FIXED_TEAM_DEFENSE_PLAYERS: usize = 11;
const MAX_FIXED_TEAM_DEFENSE_RAW_CANDIDATES: usize = 32;
pub const MAX_FIXED_TEAM_DEFENSE_CANDIDATES: usize = MAX_FIXED_TEAM_DEFENSE_RAW_CANDIDATES;

#[derive(Clone, Copy, Debug)]
pub(crate) struct FixedDefenseTeamContext {
    defender_count: usize,
    defender_positions: [(f64, f64); MAX_FIXED_TEAM_DEFENSE_PLAYERS],
    own_goal_x: f64,
    own_goal: (f64, f64),
    shot_danger: f64,
    carrier_control_threat: f64,
}

pub(crate) fn fixed_defense_team_context(
    ball_pos: (f64, f64),
    ball_carrier_pos: Option<(f64, f64)>,
    ball_carrier_possession_ticks: i32,
    carrier_control_readiness: f64,
    attacking_right: bool,
    pitch_length: f64,
    pitch_width: f64,
    press_radius: f64,
    defenders: &[DefenseTeammateInput],
) -> FixedDefenseTeamContext {
    assert!(
        defenders.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense team context supports eleven players"
    );
    let (own_goal_x, own_goal, shot_danger) =
        defense_ball_context(ball_pos, attacking_right, pitch_length, pitch_width);
    let mut defender_positions = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    for (index, defender) in defenders.iter().enumerate() {
        defender_positions[index] = defender.pos;
    }
    let carrier_control_threat = ball_carrier_pos.map_or(0.0, |carrier_pos| {
        let nearest_defender_distance = defenders
            .iter()
            .map(|defender| distance(defender.pos, carrier_pos))
            .fold(f64::INFINITY, f64::min);
        let settled_control = 1.0 - (-(ball_carrier_possession_ticks.max(0) as f64) / 4.0).exp();
        let receiving_window =
            (1.0 - settled_control) * (0.30 + 0.70 * carrier_control_readiness.clamp(0.0, 1.0));
        let control_duration = settled_control.max(receiving_window);
        let pressure_arrival_scale = (press_radius * 0.55).max(0.1);
        let pressure_absence = 1.0 - (-nearest_defender_distance / pressure_arrival_scale).exp();
        let control_availability = carrier_control_readiness.clamp(0.0, 1.0);
        (control_duration * (0.24 + 0.76 * control_availability) * (0.18 + 0.82 * pressure_absence))
            .clamp(0.0, 1.0)
    });
    FixedDefenseTeamContext {
        defender_count: defenders.len(),
        defender_positions,
        own_goal_x,
        own_goal,
        shot_danger,
        carrier_control_threat,
    }
}

impl FixedDefenseTeamContext {
    fn defender_positions(&self) -> &[(f64, f64)] {
        &self.defender_positions[..self.defender_count]
    }

    fn score_context(
        self,
        input: &DefenseChoiceInput<'_>,
        defender_index: usize,
    ) -> DefenseScoreContext {
        assert!(
            defender_index < self.defender_count,
            "fixed defense team context defender index is out of bounds"
        );
        let dist_to_ball = distance(input.defender_pos, input.ball_pos);
        let immediate_threat = 1.0 - (1.0 - self.shot_danger) * (1.0 - self.carrier_control_threat);
        DefenseScoreContext {
            own_goal_x: self.own_goal_x,
            own_goal: self.own_goal,
            dist_to_ball,
            shot_danger: self.shot_danger,
            carrier_control_threat: self.carrier_control_threat,
            press_access: local_press_access(
                input.defender_pos,
                input.ball_carrier_pos,
                input.press_radius,
            ),
            immediate_threat,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct FixedDefensePreparedChoice {
    pub candidate_count: usize,
    pub local_attackers_count: usize,
    pub dangerous_receivers_count: usize,
    pub candidate_targets: [(f64, f64); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub candidate_scores: [f64; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub candidate_movement_targets: [(f64, f64); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub candidate_projected_positions: [(f64, f64); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub candidate_action_types: [&'static str; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub candidate_residual_threats: [f64; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
    pub press_access: f64,
    pub shot_danger: f64,
    pub carrier_control_threat: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct FixedDefenseSelection {
    pub chosen_index: usize,
    pub score: f64,
    pub used_roll: bool,
    pub used_random_choice: bool,
}

pub fn generate_defense_raw_candidates(input: &DefenseRawInput<'_>) -> Vec<(f64, f64)> {
    let capacity =
        2 + if input.local_attackers.is_empty() {
            0
        } else {
            2
        } + input.dangerous_receivers.len()
            + if input.ball_carrier_pos.is_some() {
                8
            } else {
                0
            }
            + input.random_samples.len();
    let mut candidates = vec![(0.0, 0.0); capacity];
    let count = generate_defense_raw_candidates_into(input, &mut candidates);
    candidates.truncate(count);
    candidates
}

fn generate_defense_raw_candidates_into(
    input: &DefenseRawInput<'_>,
    output: &mut [(f64, f64)],
) -> usize {
    let required_capacity =
        2 + if input.local_attackers.is_empty() {
            0
        } else {
            2
        } + input.dangerous_receivers.len()
            + if input.ball_carrier_pos.is_some() {
                8
            } else {
                0
            }
            + input.random_samples.len();
    assert!(
        output.len() >= required_capacity,
        "defense raw candidate output buffer is too small"
    );
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let goal_y = input.pitch_width / 2.0;
    let shot_dx = own_goal_x - input.ball_pos.0;
    let shot_dy = goal_y - input.ball_pos.1;
    let shot_len = (shot_dx * shot_dx + shot_dy * shot_dy).sqrt();
    let mut count = 0;
    let mut push = |point| {
        output[count] = point;
        count += 1;
    };
    push(input.anchor);
    push(pitch_clamp(
        (
            input.anchor.0 * 0.85 + input.ball_pos.0 * 0.15,
            input.anchor.1 * 0.72 + input.ball_pos.1 * 0.28,
        ),
        input.pitch_length,
        input.pitch_width,
    ));

    if !input.local_attackers.is_empty() {
        let mut attackers: [DefenseZoneAttackerInput; MAX_FIXED_TEAM_DEFENSE_PLAYERS] =
            std::array::from_fn(|_| DefenseZoneAttackerInput { pos: (0.0, 0.0) });
        for (index, position) in input.local_attackers.iter().enumerate() {
            attackers[index] = DefenseZoneAttackerInput { pos: *position };
        }
        let zone_input = DefenseZoneHelperInput {
            defender_pos: input.defender_pos,
            tactical_anchor: input.anchor,
            ball_pos: input.ball_pos,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            attackers: &attackers[..input.local_attackers.len()],
        };
        push(score_mark_runner_zone(&zone_input).target);
        push(score_block_lane_zone(&zone_input).target);
    }

    let goal_side = if input.attacking_right { -1.0 } else { 1.0 };
    for receiver in input.dangerous_receivers {
        let receiver_progress = if !input.attacking_right {
            receiver.0 / input.pitch_length.max(1.0)
        } else {
            (input.pitch_length - receiver.0) / input.pitch_length.max(1.0)
        };
        let receiver_centrality = 1.0
            - ((receiver.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
        let receiver_ball_dist = distance(*receiver, input.ball_pos);
        let receive_threat = smoothstep(0.58, 0.90, receiver_progress)
            * (0.42 + 0.58 * receiver_centrality)
            * (1.0 - smoothstep(28.0, 46.0, receiver_ball_dist));
        if receive_threat <= 0.02 {
            continue;
        }
        let mark_gap = 2.4 + 1.2 * receive_threat;
        let lateral_gap = (input.defender_pos.1 - receiver.1).clamp(-2.8, 2.8) * 0.22;
        push(pitch_clamp(
            (receiver.0 + goal_side * mark_gap, receiver.1 + lateral_gap),
            input.pitch_length,
            input.pitch_width,
        ));
    }

    if let Some(carrier_pos) = input.ball_carrier_pos {
        push(pitch_clamp(
            carrier_pos,
            input.pitch_length,
            input.pitch_width,
        ));
        let lead = input.carrier_speed * 0.45;
        push(
            predicted_carrier_interception_point(input).unwrap_or_else(|| {
                pitch_clamp(
                    (input.ball_pos.0 + goal_side * lead, input.ball_pos.1),
                    input.pitch_length,
                    input.pitch_width,
                )
            }),
        );
        let contain_depth = 2.2 + 1.6 * input.carrier_control_threat;
        let contain_width = 3.0 + 2.0 * input.carrier_control_threat;
        let (breakthrough_direction, breakthrough_perpendicular) =
            carrier_breakthrough_basis(input);
        for lateral_offset in [-contain_width, 0.0, contain_width] {
            push(pitch_clamp(
                (
                    input.ball_pos.0
                        + breakthrough_direction.0 * contain_depth
                        + breakthrough_perpendicular.0 * lateral_offset,
                    input.ball_pos.1
                        + breakthrough_direction.1 * contain_depth
                        + breakthrough_perpendicular.1 * lateral_offset,
                ),
                input.pitch_length,
                input.pitch_width,
            ));
        }
        let lateral_sign = if input.defender_pos.1 < input.ball_pos.1 {
            -1.0
        } else {
            1.0
        };
        let angle_width = 5.5 + 3.0 * input.carrier_control_threat;
        let angle_depth = 3.2 + 1.4 * input.carrier_control_threat.max(input.shot_danger);
        push(pitch_clamp(
            (
                input.ball_pos.0 + goal_side * angle_depth,
                input.ball_pos.1 + lateral_sign * angle_width,
            ),
            input.pitch_length,
            input.pitch_width,
        ));
        if shot_len > 1.0 && input.shot_lane_threat > 0.05 {
            let nx = shot_dx / shot_len;
            let ny = shot_dy / shot_len;
            for lane_fraction in [0.30, 0.46] {
                let lane_depth = (shot_len * lane_fraction).clamp(2.5, 10.5);
                let lane_x = input.ball_pos.0 + nx * lane_depth;
                let lane_y = input.ball_pos.1 + ny * lane_depth;
                let side_offset = (input.defender_pos.1 - lane_y).clamp(-3.2, 3.2) * 0.45;
                push(pitch_clamp(
                    (lane_x, lane_y + side_offset),
                    input.pitch_length,
                    input.pitch_width,
                ));
            }
        }
    }

    for sample in input.random_samples {
        let angle = sample.angle_unit * std::f64::consts::TAU;
        let radius = sample.radius_unit.powf(0.7) * (8.0 + input.shot_danger * 4.0);
        push(pitch_clamp(
            (
                input.anchor.0 + angle.cos() * radius,
                input.anchor.1 + angle.sin() * radius,
            ),
            input.pitch_length,
            input.pitch_width,
        ));
    }
    count
}

fn candidate_defense_action_type(
    raw_target: (f64, f64),
    defender_pos: (f64, f64),
    anchor: (f64, f64),
    ball_pos: (f64, f64),
    ball_carrier_pos: Option<(f64, f64)>,
    attacking_right: bool,
    pitch_length: f64,
    pitch_width: f64,
    press_radius: f64,
    tackle_range: f64,
    dist_to_ball: f64,
    shot_danger: f64,
    carrier_control_threat: f64,
    dangerous_receivers: &[(f64, f64)],
    local_attackers: &[(f64, f64)],
    movement: DefenseMovementInput<'_>,
) -> &'static str {
    let Some(carrier_pos) = ball_carrier_pos else {
        if dangerous_receivers
            .iter()
            .any(|receiver| distance(raw_target, *receiver) < 5.4)
        {
            return "mark_runner";
        }
        if local_attackers
            .iter()
            .any(|attacker| distance(raw_target, *attacker) < 5.0)
        {
            return "mark_runner";
        }
        return if local_attackers.is_empty() {
            "hold_position"
        } else {
            "block_lane"
        };
    };

    let own_goal_x = if attacking_right { 0.0 } else { pitch_length };
    let carrier_distance = distance(raw_target, carrier_pos);
    let defender_access = 1.0
        - smoothstep(
            press_radius.max(0.1) * 0.45,
            press_radius.max(0.1) * 1.20,
            distance(defender_pos, carrier_pos),
        );
    let target_access = (-carrier_distance / press_radius.max(0.1)).exp();
    let physical_contact_range = 0.75 + 0.36 * tackle_range.max(0.0);
    let contact_window =
        close_down_contact_window(defender_pos, carrier_pos, anchor, tackle_range, movement);
    let tackle_target_alignment = 1.0
        - smoothstep(
            physical_contact_range * 0.35,
            physical_contact_range,
            carrier_distance,
        );
    let tackle_immediacy = 1.0
        - smoothstep(
            physical_contact_range * 0.30,
            physical_contact_range * 1.25,
            dist_to_ball,
        );
    let carrier_urgency = 0.12 + 0.88 * shot_danger.max(carrier_control_threat);
    let tackle_value = carrier_urgency
        * contact_window
        * (0.40 + 0.60 * defender_access)
        * tackle_target_alignment
        * tackle_immediacy;
    let approach_value = carrier_urgency
        * contact_window
        * target_access
        * (1.0 - tackle_immediacy)
        * (0.20 + 0.80 * defender_access);
    let close_down_value =
        carrier_urgency * defender_access * (0.34 + 0.66 * target_access) * (1.0 - contact_window);
    let immediate_closure = defender_access.max(contact_window);
    let pursuit_reachability = defensive_pursuit_reachability(
        defender_pos,
        carrier_pos,
        anchor,
        press_radius,
        movement,
        4,
    );
    let pursuit_value =
        if target_access >= 0.72 && immediate_closure < 0.10 && pursuit_reachability > 0.10 {
            carrier_urgency
                * pursuit_reachability
                * target_access
                * (0.42 + 0.58 * (1.0 - immediate_closure))
        } else {
            0.0
        };
    let non_contact_target = 1.0 - tackle_target_alignment;
    let mark_value = dangerous_receivers
        .iter()
        .chain(local_attackers.iter())
        .map(|receiver| {
            let receiver_progress = if !attacking_right {
                receiver.0 / pitch_length.max(1.0)
            } else {
                (pitch_length - receiver.0) / pitch_length.max(1.0)
            };
            let receiver_centrality =
                1.0 - ((receiver.1 - pitch_width / 2.0).abs() / (pitch_width / 2.0)).min(1.0);
            let receiver_ball_dist = distance(*receiver, ball_pos);
            let receive_threat = smoothstep(0.58, 0.90, receiver_progress)
                * (0.42 + 0.58 * receiver_centrality)
                * (1.0 - smoothstep(28.0, 46.0, receiver_ball_dist));
            receive_threat * (-distance(raw_target, *receiver) / 7.5).exp() * non_contact_target
        })
        .fold(0.0, f64::max);
    let block_value = shot_lane_closure(raw_target, ball_pos, own_goal_x, pitch_width)
        * shot_danger
        * non_contact_target;
    [
        ("tackle", tackle_value),
        ("approach", approach_value),
        ("close_down", close_down_value),
        ("pursuit", pursuit_value),
        ("mark_runner", mark_value),
        ("block_lane", block_value),
        ("hold_position", 0.04),
    ]
    .into_iter()
    .max_by(|(_, left), (_, right)| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal))
    .map(|(action, _)| action)
    .unwrap_or("hold_position")
}

fn defense_ball_context(
    ball_pos: (f64, f64),
    attacking_right: bool,
    pitch_length: f64,
    pitch_width: f64,
) -> (f64, (f64, f64), f64) {
    let own_goal_x = if attacking_right { 0.0 } else { pitch_length };
    let own_goal = (own_goal_x, pitch_width / 2.0);
    let ball_goal_dist = distance(ball_pos, own_goal);
    let central_threat =
        1.0 - ((ball_pos.1 - pitch_width / 2.0).abs() / (pitch_width / 2.0)).min(1.0);
    let shot_danger = (1.0 - ball_goal_dist / 32.0).max(0.0) * (0.55 + 0.45 * central_threat);
    (own_goal_x, own_goal, shot_danger)
}

fn defense_score_context(input: &DefenseScoreInput<'_>) -> DefenseScoreContext {
    let (own_goal_x, own_goal, shot_danger) = defense_ball_context(
        input.ball_pos,
        input.attacking_right,
        input.pitch_length,
        input.pitch_width,
    );
    let dist_to_ball = distance(input.defender_pos, input.ball_pos);
    let carrier_control_threat = carrier_control_threat(input);

    let immediate_threat = 1.0 - (1.0 - shot_danger) * (1.0 - carrier_control_threat);
    DefenseScoreContext {
        own_goal_x,
        own_goal,
        dist_to_ball,
        shot_danger,
        carrier_control_threat,
        press_access: local_press_access(
            input.defender_pos,
            input.ball_carrier_pos,
            input.press_radius,
        ),
        immediate_threat,
    }
}

fn defense_task_target(
    action: &str,
    candidate_target: (f64, f64),
    ball_carrier_pos: Option<(f64, f64)>,
) -> (f64, f64) {
    if matches!(action, "close_down" | "tackle") {
        ball_carrier_pos.unwrap_or(candidate_target)
    } else {
        candidate_target
    }
}

fn score_defense_candidate(
    input: &DefenseScoreInput<'_>,
    context: DefenseScoreContext,
    point: (f64, f64),
    teammate_positions: &[(f64, f64)],
    skip_teammate_index: Option<usize>,
) -> DefenseScoreOutput {
    let candidate_action = candidate_defense_action_type(
        point,
        input.defender_pos,
        input.anchor,
        input.ball_pos,
        input.ball_carrier_pos,
        input.attacking_right,
        input.pitch_length,
        input.pitch_width,
        input.press_radius,
        input.tackle_range,
        context.dist_to_ball,
        context.shot_danger,
        context.carrier_control_threat,
        input.dangerous_receivers,
        input.local_attackers,
        input.movement,
    );
    let task_target = defense_task_target(candidate_action, point, input.ball_carrier_pos);
    let motion = project_defense_action_motion(
        input.defender_pos,
        task_target,
        input.anchor,
        candidate_action,
        input.movement,
    );
    let (engagement_weight, engagement_reach) =
        shot_contest_engagement(candidate_action, input.tackle_range);
    let contest = input.ball_carrier_pos.map(|carrier_pos| {
        estimate_shot_contest(
            carrier_pos,
            context.own_goal,
            &[ShotContestDefender {
                index: 0,
                pos: input.defender_pos,
                projected_pos: motion.pos,
                speed: input.movement.speed_ability as f64,
                defence: input.movement.defence,
                intent: shot_contest_intent(candidate_action),
                engagement_weight,
                engagement_reach,
                is_goalkeeper: false,
            }],
        )
    });
    let body_release_probability = contest
        .map(|estimate| estimate.body_release_probability)
        .unwrap_or(1.0);
    let release_probability = contest
        .map(|estimate| estimate.release_probability)
        .unwrap_or(1.0);
    let residual_shot_threat = context.shot_danger * body_release_probability * release_probability;
    let residual_control_threat = context.carrier_control_threat * body_release_probability;
    let residual_threat = 1.0 - (1.0 - residual_shot_threat) * (1.0 - residual_control_threat);
    let immediate_denial = (context.immediate_threat - residual_threat).max(0.0);
    let base_score = defensive_position_value(&DefensivePositionValueInput {
        pos: motion.pos,
        ball_pos: input.ball_pos,
        own_goal_x: context.own_goal_x,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        attackers: input.attackers,
        teammates: teammate_positions,
        formation_pos: input.anchor,
        skip_teammate_index,
    });
    let press_value = input.ball_carrier_pos.map_or(0.0, |carrier_pos| {
        (1.0 - distance(motion.pos, carrier_pos) / input.press_radius.max(0.1)).max(0.0)
    });
    let cover_cost = (input.local_attackers.len() as f64 * 0.08).min(0.32);
    let carrier_threat = 0.35 + 0.65 * context.shot_danger.max(context.carrier_control_threat);
    let anchor_distance = distance(motion.pos, input.anchor);
    let structure_factor =
        1.0 / (1.0 + input.compactness.clamp(0.0, 1.0) * (anchor_distance / 18.0).powi(2));
    let structural_value = base_score
        * structure_factor
        * (1.0 - cover_cost * 0.28)
        * (1.0 - context.immediate_threat.clamp(0.0, 1.0));
    let mut score = immediate_denial + structural_value;
    if matches!(candidate_action, "close_down" | "approach" | "tackle") {
        let projected_carrier_access = input.ball_carrier_pos.map_or(0.0, |carrier_pos| {
            1.0 - smoothstep(
                input.press_radius.max(0.1) * 0.30,
                input.press_radius.max(0.1),
                distance(motion.pos, carrier_pos),
            )
        });
        score += context.immediate_threat
            * context.press_access
            * projected_carrier_access
            * (0.12 + 0.10 * input.press_intensity.clamp(0.0, 1.0));
    }
    if candidate_action == "pursuit" {
        let future_closure = input.ball_carrier_pos.map_or(0.0, |carrier_pos| {
            defensive_pursuit_reachability(
                input.defender_pos,
                carrier_pos,
                input.anchor,
                input.press_radius,
                input.movement,
                4,
            )
        });
        score += context.immediate_threat
            * future_closure
            * (0.30 + 0.30 * input.press_intensity.clamp(0.0, 1.0));
    }
    let lane_closure = shot_lane_closure(
        motion.pos,
        input.ball_pos,
        context.own_goal_x,
        input.pitch_width,
    );
    let mut best_mark_value: f64 = 0.0;
    for receiver in input.dangerous_receivers {
        let receiver_progress = if !input.attacking_right {
            receiver.0 / input.pitch_length.max(1.0)
        } else {
            (input.pitch_length - receiver.0) / input.pitch_length.max(1.0)
        };
        let receiver_centrality = 1.0
            - ((receiver.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
        let receiver_ball_dist = distance(*receiver, input.ball_pos);
        let mark_dist = distance(motion.pos, *receiver);
        let useful_distance = 1.0 - smoothstep(3.2, 10.5, mark_dist);
        let goal_side_progress =
            (motion.pos.0 - receiver.0) * if !input.attacking_right { 1.0 } else { -1.0 };
        let goal_side_fit = smoothstep(0.0, 2.2, goal_side_progress)
            * (1.0 - smoothstep(6.5, 12.0, goal_side_progress));
        let receive_threat = smoothstep(0.58, 0.90, receiver_progress)
            * (0.42 + 0.58 * receiver_centrality)
            * (1.0 - smoothstep(28.0, 46.0, receiver_ball_dist));
        best_mark_value =
            best_mark_value.max(receive_threat * useful_distance * (0.48 + 0.52 * goal_side_fit));
    }
    if best_mark_value > 0.0 {
        score += best_mark_value * (1.0 - context.immediate_threat.clamp(0.0, 1.0));
    }
    DefenseScoreOutput {
        score: score.max(0.0),
        target: task_target,
        movement_target: motion.movement_target,
        projected_pos: motion.pos,
        action_type: candidate_action,
        residual_threat,
        base_score,
        press_value,
        press_access: context.press_access,
        carrier_threat,
        shot_lane_closure: lane_closure,
        best_mark_value,
    }
}

pub fn score_defense_candidates(input: &DefenseScoreInput<'_>) -> Vec<DefenseScoreOutput> {
    let context = defense_score_context(input);
    let teammate_positions: Vec<(f64, f64)> = input.teammates.iter().map(|tm| tm.pos).collect();
    input
        .candidates
        .iter()
        .map(|point| score_defense_candidate(input, context, *point, &teammate_positions, None))
        .collect()
}

pub fn best_fixed_team_defense_candidate(
    input: &DefenseChoiceInput<'_>,
) -> Option<DefenseScoreOutput> {
    best_fixed_team_defense_candidate_with_team_context(input, None)
}

pub(crate) fn best_fixed_team_defense_candidate_with_team_context(
    input: &DefenseChoiceInput<'_>,
    team_context: Option<(&FixedDefenseTeamContext, usize)>,
) -> Option<DefenseScoreOutput> {
    assert!(
        input.attackers.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS
            && input.teammates.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS
            && input.random_samples.is_empty(),
        "fixed-team defense prediction expects eleven-player teams without random samples"
    );
    let mut local_attackers = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut local_attacker_count = 0;
    let mut dangerous_receivers = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut dangerous_receiver_count = 0;
    for attacker in input.attackers.iter().copied() {
        let is_carrier = input
            .ball_carrier_pos
            .is_some_and(|carrier_pos| distance(attacker, carrier_pos) < 1e-9);
        if !is_carrier
            && (distance(attacker, input.anchor) < 24.0
                || distance(attacker, input.defender_pos) < 16.0)
        {
            local_attackers[local_attacker_count] = attacker;
            local_attacker_count += 1;
        }
        if !is_carrier
            && (distance(attacker, input.ball_pos) < 34.0
                || distance(attacker, input.anchor) < 28.0
                || distance(attacker, input.defender_pos) < 18.0)
        {
            dangerous_receivers[dangerous_receiver_count] = attacker;
            dangerous_receiver_count += 1;
        }
    }
    let local_attackers = &local_attackers[..local_attacker_count];
    let dangerous_receivers = &dangerous_receivers[..dangerous_receiver_count];
    let score_input = DefenseScoreInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        base_ref: input.base_ref,
        ball_pos: input.ball_pos,
        ball_carrier_pos: input.ball_carrier_pos,
        ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
        ball_carrier_possession_ticks: input.ball_carrier_possession_ticks,
        carrier_control_readiness: input.carrier_control_readiness,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        press_radius: input.press_radius,
        tackle_range: input.tackle_range,
        carrier_speed: input.carrier_speed,
        press_intensity: input.press_intensity,
        compactness: input.compactness,
        movement: input.movement,
        candidates: &[],
        attackers: input.attackers,
        local_attackers,
        dangerous_receivers,
        teammates: input.teammates,
    };
    let context = team_context.map_or_else(
        || defense_score_context(&score_input),
        |(context, defender_index)| context.score_context(input, defender_index),
    );
    let shot_lane_threat =
        (1.0 - smoothstep(
            24.0,
            54.0,
            distance(
                input.ball_pos,
                (context.own_goal_x, input.pitch_width / 2.0),
            ),
        )) * (0.45
            + 0.55
                * (1.0
                    - ((input.ball_pos.1 - input.pitch_width / 2.0).abs()
                        / (input.pitch_width / 2.0))
                        .min(1.0)));
    let mut raw_candidates = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_RAW_CANDIDATES];
    let raw_candidate_count = generate_defense_raw_candidates_into(
        &DefenseRawInput {
            defender_pos: input.defender_pos,
            anchor: input.anchor,
            ball_pos: input.ball_pos,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            carrier_speed: input.carrier_speed,
            carrier_control_threat: context.carrier_control_threat,
            shot_danger: context.shot_danger,
            local_attackers,
            dangerous_receivers,
            ball_carrier_pos: input.ball_carrier_pos,
            carrier_velocity: input.carrier_velocity,
            shot_lane_threat,
            random_samples: &[],
        },
        &mut raw_candidates,
    );
    let mut unique_candidates = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_RAW_CANDIDATES];
    let mut unique_candidate_count = 0;
    let mut seen = [(0, 0); MAX_FIXED_TEAM_DEFENSE_RAW_CANDIDATES];
    for point in &raw_candidates[..raw_candidate_count] {
        let key = (python_round_1_key(point.0), python_round_1_key(point.1));
        if seen[..unique_candidate_count].contains(&key) {
            continue;
        }
        seen[unique_candidate_count] = key;
        unique_candidates[unique_candidate_count] = *point;
        unique_candidate_count += 1;
    }
    if unique_candidate_count == 0 {
        return None;
    }
    let mut teammate_positions = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let (teammate_positions, skip_teammate_index) =
        if let Some((context, defender_index)) = team_context {
            (context.defender_positions(), Some(defender_index))
        } else {
            for (index, teammate) in input.teammates.iter().enumerate() {
                teammate_positions[index] = teammate.pos;
            }
            (&teammate_positions[..input.teammates.len()], None)
        };
    let mut best = None;
    for point in &unique_candidates[..unique_candidate_count] {
        let candidate = score_defense_candidate(
            &score_input,
            context,
            *point,
            teammate_positions,
            skip_teammate_index,
        );
        if best
            .as_ref()
            .map(|current: &DefenseScoreOutput| candidate.score >= current.score)
            .unwrap_or(true)
        {
            best = Some(candidate);
        }
    }
    best
}

fn python_round_1_key(value: f64) -> i64 {
    if !value.is_finite() {
        return (value * 10.0).round_ties_even() as i64;
    }

    let sign = if value.is_sign_negative() { -1 } else { 1 };
    let abs_value = value.abs();
    let lower = (abs_value * 10.0).floor() as i64;
    let midpoint = (lower as f64 + 0.5) / 10.0;
    let rounded = if abs_value < midpoint {
        lower
    } else if abs_value > midpoint {
        lower + 1
    } else if lower % 2 == 0 {
        lower
    } else {
        lower + 1
    };
    sign * rounded
}

#[cfg(test)]
fn defense_action_type(
    raw_target: (f64, f64),
    input: &DefenseChoiceInput<'_>,
    dist_to_ball: f64,
    shot_danger: f64,
    carrier_control_threat: f64,
    dangerous_receivers: &[(f64, f64)],
    local_attackers: &[(f64, f64)],
) -> &'static str {
    candidate_defense_action_type(
        raw_target,
        input.defender_pos,
        input.anchor,
        input.ball_pos,
        input.ball_carrier_pos,
        input.attacking_right,
        input.pitch_length,
        input.pitch_width,
        input.press_radius,
        input.tackle_range,
        dist_to_ball,
        shot_danger,
        carrier_control_threat,
        dangerous_receivers,
        local_attackers,
        input.movement,
    )
}

fn unique_points(points: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut seen: Vec<(i64, i64)> = Vec::new();
    let mut unique = Vec::new();
    for point in points {
        let key = (python_round_1_key(point.0), python_round_1_key(point.1));
        if seen.contains(&key) {
            continue;
        }
        seen.push(key);
        unique.push(*point);
    }
    unique
}

pub fn prepare_fixed_defense_choice(
    input: &DefenseChoiceInput<'_>,
) -> Option<FixedDefensePreparedChoice> {
    prepare_fixed_defense_choice_with_team_context(input, None)
}

pub(crate) fn prepare_fixed_defense_choice_with_team_context(
    input: &DefenseChoiceInput<'_>,
    team_context: Option<(&FixedDefenseTeamContext, usize)>,
) -> Option<FixedDefensePreparedChoice> {
    assert!(
        input.attackers.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS
            && input.teammates.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense choice supports eleven-player teams"
    );
    let (own_goal, shot_danger) = team_context.map_or_else(
        || {
            let (_, own_goal, shot_danger) = defense_ball_context(
                input.ball_pos,
                input.attacking_right,
                input.pitch_length,
                input.pitch_width,
            );
            (own_goal, shot_danger)
        },
        |(context, _)| (context.own_goal, context.shot_danger),
    );
    let ball_goal_dist = distance(input.ball_pos, own_goal);
    let central_threat = 1.0
        - ((input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let carrier_control_threat = team_context.map_or_else(
        || {
            carrier_control_threat(&DefenseScoreInput {
                defender_pos: input.defender_pos,
                anchor: input.anchor,
                base_ref: input.base_ref,
                ball_pos: input.ball_pos,
                ball_carrier_pos: input.ball_carrier_pos,
                ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
                ball_carrier_possession_ticks: input.ball_carrier_possession_ticks,
                carrier_control_readiness: input.carrier_control_readiness,
                attacking_right: input.attacking_right,
                pitch_length: input.pitch_length,
                pitch_width: input.pitch_width,
                press_radius: input.press_radius,
                tackle_range: input.tackle_range,
                carrier_speed: input.carrier_speed,
                press_intensity: input.press_intensity,
                compactness: input.compactness,
                movement: input.movement,
                candidates: &[],
                attackers: input.attackers,
                local_attackers: &[],
                dangerous_receivers: &[],
                teammates: input.teammates,
            })
        },
        |(context, _)| context.carrier_control_threat,
    );

    let mut local_attackers = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut local_attacker_count = 0;
    let mut dangerous_receivers = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut dangerous_receiver_count = 0;
    for attacker in input.attackers.iter().copied() {
        let is_carrier = input
            .ball_carrier_pos
            .is_some_and(|carrier_pos| distance(attacker, carrier_pos) < 1e-9);
        if !is_carrier
            && (distance(attacker, input.anchor) < 24.0
                || distance(attacker, input.defender_pos) < 16.0)
        {
            local_attackers[local_attacker_count] = attacker;
            local_attacker_count += 1;
        }
        if !is_carrier
            && (distance(attacker, input.ball_pos) < 34.0
                || distance(attacker, input.anchor) < 28.0
                || distance(attacker, input.defender_pos) < 18.0)
        {
            dangerous_receivers[dangerous_receiver_count] = attacker;
            dangerous_receiver_count += 1;
        }
    }
    let local_attackers = &local_attackers[..local_attacker_count];
    let dangerous_receivers = &dangerous_receivers[..dangerous_receiver_count];
    let shot_lane_threat =
        (1.0 - smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * central_threat);

    let required_capacity = 2
        + if local_attackers.is_empty() { 0 } else { 2 }
        + dangerous_receivers.len()
        + if input.ball_carrier_pos.is_some() {
            8
        } else {
            0
        }
        + input.random_samples.len();
    assert!(
        required_capacity <= MAX_FIXED_TEAM_DEFENSE_CANDIDATES,
        "fixed defense candidate buffer is too small"
    );
    let mut raw_points = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_CANDIDATES];
    let raw_count = generate_defense_raw_candidates_into(
        &DefenseRawInput {
            defender_pos: input.defender_pos,
            anchor: input.anchor,
            ball_pos: input.ball_pos,
            attacking_right: input.attacking_right,
            pitch_length: input.pitch_length,
            pitch_width: input.pitch_width,
            carrier_speed: input.carrier_speed,
            carrier_control_threat,
            shot_danger,
            local_attackers,
            dangerous_receivers,
            ball_carrier_pos: input.ball_carrier_pos,
            carrier_velocity: input.carrier_velocity,
            shot_lane_threat,
            random_samples: input.random_samples,
        },
        &mut raw_points,
    );
    let mut unique_points = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_CANDIDATES];
    let mut seen = [(0i64, 0i64); MAX_FIXED_TEAM_DEFENSE_CANDIDATES];
    let mut candidate_count = 0;
    for point in &raw_points[..raw_count] {
        let key = (python_round_1_key(point.0), python_round_1_key(point.1));
        if seen[..candidate_count].contains(&key) {
            continue;
        }
        seen[candidate_count] = key;
        unique_points[candidate_count] = *point;
        candidate_count += 1;
    }
    if candidate_count == 0 {
        return None;
    }

    let score_input = DefenseScoreInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        base_ref: input.base_ref,
        ball_pos: input.ball_pos,
        ball_carrier_pos: input.ball_carrier_pos,
        ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
        ball_carrier_possession_ticks: input.ball_carrier_possession_ticks,
        carrier_control_readiness: input.carrier_control_readiness,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        press_radius: input.press_radius,
        tackle_range: input.tackle_range,
        carrier_speed: input.carrier_speed,
        press_intensity: input.press_intensity,
        compactness: input.compactness,
        movement: input.movement,
        candidates: &unique_points[..candidate_count],
        attackers: input.attackers,
        local_attackers,
        dangerous_receivers,
        teammates: input.teammates,
    };
    let context = team_context.map_or_else(
        || defense_score_context(&score_input),
        |(context, defender_index)| context.score_context(input, defender_index),
    );
    let mut teammate_positions = [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let (teammate_positions, skip_teammate_index) =
        if let Some((context, defender_index)) = team_context {
            (context.defender_positions(), Some(defender_index))
        } else {
            for (index, teammate) in input.teammates.iter().enumerate() {
                teammate_positions[index] = teammate.pos;
            }
            (&teammate_positions[..input.teammates.len()], None)
        };
    let mut prepared = FixedDefensePreparedChoice {
        candidate_count,
        local_attackers_count: local_attackers.len(),
        dangerous_receivers_count: dangerous_receivers.len(),
        candidate_targets: [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        candidate_scores: [0.0; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        candidate_movement_targets: [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        candidate_projected_positions: [(0.0, 0.0); MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        candidate_action_types: ["hold_position"; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        candidate_residual_threats: [1.0; MAX_FIXED_TEAM_DEFENSE_CANDIDATES],
        press_access: 0.0,
        shot_danger,
        carrier_control_threat,
    };
    for (index, point) in unique_points[..candidate_count].iter().enumerate() {
        let candidate = score_defense_candidate(
            &score_input,
            context,
            *point,
            teammate_positions,
            skip_teammate_index,
        );
        if index == 0 {
            prepared.press_access = candidate.press_access;
        }
        prepared.candidate_targets[index] = candidate.target;
        prepared.candidate_scores[index] = candidate.score;
        prepared.candidate_movement_targets[index] = candidate.movement_target;
        prepared.candidate_projected_positions[index] = candidate.projected_pos;
        prepared.candidate_action_types[index] = candidate.action_type;
        prepared.candidate_residual_threats[index] = candidate.residual_threat;
    }
    Some(prepared)
}

pub fn fixed_defense_random_branch(
    prepared: &FixedDefensePreparedChoice,
    _iq: f64,
    score_noises: &[f64],
) -> Option<(bool, bool)> {
    let count = prepared.candidate_count;
    if count == 0 || count > MAX_FIXED_TEAM_DEFENSE_CANDIDATES {
        return None;
    }
    if count == 1 {
        return Some((false, false));
    }
    let max_score = (0..count)
        .map(|index| {
            prepared.candidate_scores[index]
                * (1.0 + score_noises.get(index).copied().unwrap_or(0.0))
        })
        .fold(f64::NEG_INFINITY, f64::max);
    fixed_defense_random_branch_from_noisy_max(count, max_score)
}

pub(crate) fn fixed_defense_random_branch_from_noisy_max(
    candidate_count: usize,
    max_noisy_score: f64,
) -> Option<(bool, bool)> {
    if candidate_count == 0 || candidate_count > MAX_FIXED_TEAM_DEFENSE_CANDIDATES {
        return None;
    }
    if candidate_count == 1 {
        return Some((false, false));
    }
    if max_noisy_score < 0.001 {
        Some((false, true))
    } else {
        Some((true, false))
    }
}

pub fn select_fixed_defense_action(
    prepared: &FixedDefensePreparedChoice,
    iq: f64,
    score_noises: &[f64],
    roll_by_count: &[f64],
    fallback_index_by_count: &[usize],
) -> Option<FixedDefenseSelection> {
    let count = prepared.candidate_count;
    if count == 0 || count > MAX_FIXED_TEAM_DEFENSE_CANDIDATES {
        return None;
    }
    let mut noisy_scores = [0.0; MAX_FIXED_TEAM_DEFENSE_CANDIDATES];
    let mut max_score = f64::NEG_INFINITY;
    for index in 0..count {
        let score = prepared.candidate_scores[index]
            * (1.0 + score_noises.get(index).copied().unwrap_or(0.0));
        noisy_scores[index] = score;
        max_score = max_score.max(score);
    }
    let mut used_roll = false;
    let mut used_random_choice = false;
    let chosen_index = if count == 1 {
        0
    } else if max_score < 0.001 {
        used_random_choice = true;
        fallback_index_by_count.get(count).copied().unwrap_or(0) % count
    } else {
        let roll = roll_by_count.get(count).copied().unwrap_or(0.0);
        let selection = softmax_select_index(&noisy_scores[..count], iq, roll, 0)?;
        used_roll = selection.total_weight >= 1e-10;
        selection.index.min(count - 1)
    };
    Some(FixedDefenseSelection {
        chosen_index,
        score: noisy_scores[chosen_index],
        used_roll,
        used_random_choice,
    })
}

pub fn prepare_defense_choice(input: &DefenseChoiceInput<'_>) -> Option<DefensePreparedChoice> {
    let own_goal_x = if input.attacking_right {
        0.0
    } else {
        input.pitch_length
    };
    let own_goal = (own_goal_x, input.pitch_width / 2.0);
    let ball_goal_dist = distance(input.ball_pos, own_goal);
    let central_threat = 1.0
        - ((input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0)).min(1.0);
    let shot_danger = (1.0 - ball_goal_dist / 32.0).max(0.0) * (0.55 + 0.45 * central_threat);
    let carrier_control_threat = carrier_control_threat(&DefenseScoreInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        base_ref: input.base_ref,
        ball_pos: input.ball_pos,
        ball_carrier_pos: input.ball_carrier_pos,
        ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
        ball_carrier_possession_ticks: input.ball_carrier_possession_ticks,
        carrier_control_readiness: input.carrier_control_readiness,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        press_radius: input.press_radius,
        tackle_range: input.tackle_range,
        carrier_speed: input.carrier_speed,
        press_intensity: input.press_intensity,
        compactness: input.compactness,
        movement: input.movement,
        candidates: &[],
        attackers: input.attackers,
        local_attackers: &[],
        dangerous_receivers: &[],
        teammates: input.teammates,
    });

    let local_attackers: Vec<(f64, f64)> = input
        .attackers
        .iter()
        .copied()
        .filter(|attacker| {
            let is_carrier = input
                .ball_carrier_pos
                .is_some_and(|carrier_pos| distance(*attacker, carrier_pos) < 1e-9);
            !is_carrier
                && (distance(*attacker, input.anchor) < 24.0
                    || distance(*attacker, input.defender_pos) < 16.0)
        })
        .collect();
    let dangerous_receivers: Vec<(f64, f64)> = input
        .attackers
        .iter()
        .copied()
        .filter(|attacker| {
            if let Some(carrier_pos) = input.ball_carrier_pos {
                if distance(*attacker, carrier_pos) < 1e-9 {
                    return false;
                }
            }
            distance(*attacker, input.ball_pos) < 34.0
                || distance(*attacker, input.anchor) < 28.0
                || distance(*attacker, input.defender_pos) < 18.0
        })
        .collect();
    let shot_lane_threat =
        (1.0 - smoothstep(24.0, 54.0, ball_goal_dist)) * (0.45 + 0.55 * central_threat);
    let raw_points = generate_defense_raw_candidates(&DefenseRawInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        ball_pos: input.ball_pos,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        carrier_speed: input.carrier_speed,
        carrier_control_threat,
        shot_danger,
        local_attackers: &local_attackers,
        dangerous_receivers: &dangerous_receivers,
        ball_carrier_pos: input.ball_carrier_pos,
        carrier_velocity: input.carrier_velocity,
        shot_lane_threat,
        random_samples: input.random_samples,
    });
    let candidates = unique_points(&raw_points);
    if candidates.is_empty() {
        return None;
    }

    let scored = score_defense_candidates(&DefenseScoreInput {
        defender_pos: input.defender_pos,
        anchor: input.anchor,
        base_ref: input.base_ref,
        ball_pos: input.ball_pos,
        ball_carrier_pos: input.ball_carrier_pos,
        ball_carrier_consecutive_carries: input.ball_carrier_consecutive_carries,
        ball_carrier_possession_ticks: input.ball_carrier_possession_ticks,
        carrier_control_readiness: input.carrier_control_readiness,
        attacking_right: input.attacking_right,
        pitch_length: input.pitch_length,
        pitch_width: input.pitch_width,
        press_radius: input.press_radius,
        tackle_range: input.tackle_range,
        carrier_speed: input.carrier_speed,
        press_intensity: input.press_intensity,
        compactness: input.compactness,
        movement: input.movement,
        candidates: &candidates,
        attackers: input.attackers,
        local_attackers: &local_attackers,
        dangerous_receivers: &dangerous_receivers,
        teammates: input.teammates,
    });
    if scored.is_empty() {
        return None;
    }
    Some(DefensePreparedChoice {
        raw_targets: raw_points,
        press_access: scored[0].press_access,
        scored,
        local_attackers_count: local_attackers.len(),
        dangerous_receivers_count: dangerous_receivers.len(),
        shot_danger,
        carrier_control_threat,
    })
}

fn select_prepared_defense_candidate(
    prepared: &DefensePreparedChoice,
    iq: f64,
    score_noises: &[f64],
    roll_by_count: &[f64],
    fallback_index_by_count: &[usize],
) -> Option<DefensePreparedSelection> {
    let noisy_scores: Vec<f64> = prepared
        .scored
        .iter()
        .enumerate()
        .map(|(idx, candidate)| {
            let noise = score_noises.get(idx).copied().unwrap_or(0.0);
            candidate.score * (1.0 + noise)
        })
        .collect();
    let count = noisy_scores.len();
    let max_score = noisy_scores
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let mut used_roll = false;
    let mut used_random_choice = false;
    let chosen_index = if count == 1 {
        0
    } else if max_score < 0.001 {
        used_random_choice = true;
        fallback_index_by_count.get(count).copied().unwrap_or(0) % count
    } else {
        let roll = roll_by_count.get(count).copied().unwrap_or(0.0);
        let selection = softmax_select_index(&noisy_scores, iq, roll, 0)?;
        used_roll = selection.total_weight >= 1e-10;
        selection.index.min(prepared.scored.len() - 1)
    };
    Some(DefensePreparedSelection {
        chosen_index,
        noisy_scores,
        used_roll,
        used_random_choice,
    })
}

pub fn prepared_defense_choice_random_branch(
    prepared: &DefensePreparedChoice,
    iq: f64,
    score_noises: &[f64],
) -> Option<(bool, bool)> {
    let selection = select_prepared_defense_candidate(prepared, iq, score_noises, &[], &[])?;
    Some((selection.used_roll, selection.used_random_choice))
}

pub fn select_prepared_defense_action(
    prepared: &DefensePreparedChoice,
    iq: f64,
    score_noises: &[f64],
    roll_by_count: &[f64],
    fallback_index_by_count: &[usize],
) -> Option<DefenseChoiceOutput> {
    let selection = select_prepared_defense_candidate(
        prepared,
        iq,
        score_noises,
        roll_by_count,
        fallback_index_by_count,
    )?;
    let chosen_index = selection.chosen_index;
    let chosen = prepared.scored[chosen_index];
    let chosen_score = selection.noisy_scores[chosen_index];

    let action_type = chosen.action_type;
    let goal_candidates = prepared
        .scored
        .iter()
        .map(|candidate| DefenseGoalCandidate {
            action_type: candidate.action_type,
            target: candidate.target,
            value: candidate.score,
        })
        .collect();

    Some(DefenseChoiceOutput {
        action_type,
        target: chosen.target,
        score: chosen_score,
        candidate_count: selection.noisy_scores.len(),
        local_attackers_count: prepared.local_attackers_count,
        dangerous_receivers_count: prepared.dangerous_receivers_count,
        raw_targets: prepared.raw_targets.clone(),
        candidate_targets: prepared
            .scored
            .iter()
            .map(|candidate| candidate.target)
            .collect(),
        candidate_scores: prepared
            .scored
            .iter()
            .map(|candidate| candidate.score)
            .collect(),
        candidate_movement_targets: prepared
            .scored
            .iter()
            .map(|candidate| candidate.movement_target)
            .collect(),
        candidate_projected_positions: prepared
            .scored
            .iter()
            .map(|candidate| candidate.projected_pos)
            .collect(),
        candidate_action_types: prepared
            .scored
            .iter()
            .map(|candidate| candidate.action_type)
            .collect(),
        candidate_residual_threats: prepared
            .scored
            .iter()
            .map(|candidate| candidate.residual_threat)
            .collect(),
        goal_candidates,
        used_roll: selection.used_roll,
        used_random_choice: selection.used_random_choice,
        press_access: prepared.press_access,
        shot_danger: prepared.shot_danger,
        carrier_control_threat: prepared.carrier_control_threat,
        base_score: chosen.base_score,
        press_value: chosen.press_value,
        carrier_threat: chosen.carrier_threat,
        shot_lane_closure: chosen.shot_lane_closure,
        best_mark_value: chosen.best_mark_value,
    })
}

pub fn choose_defense_action(input: &DefenseChoiceInput<'_>) -> Option<DefenseChoiceOutput> {
    let prepared = prepare_defense_choice(input)?;
    select_prepared_defense_action(
        &prepared,
        input.iq,
        input.score_noises,
        input.roll_by_count,
        input.fallback_index_by_count,
    )
}

#[cfg(test)]
mod tests {
    use super::{
        best_fixed_team_defense_candidate, best_fixed_team_defense_candidate_with_team_context,
        choose_defense_action, close_down_contact_window, defense_action_movement_intent,
        defense_action_type, defense_task_target, defensive_approach_reachability,
        defensive_interception_reachability, defensive_pursuit_reachability,
        fixed_defense_random_branch, fixed_defense_team_context, generate_defense_raw_candidates,
        predicted_carrier_interception_point, prepare_defense_choice, prepare_fixed_defense_choice,
        prepare_fixed_defense_choice_with_team_context, project_defense_action_motion,
        score_defense_candidates, select_fixed_defense_action, select_prepared_defense_action,
        select_prepared_defense_candidate, DefenseChoiceInput, DefenseMovementInput,
        DefenseRandomSample, DefenseRawInput, DefenseScoreInput, DefenseScoreOutput,
        DefenseTeammateInput, FixedDefensePreparedChoice,
    };
    use crate::match_flow::{
        player_move_speed, player_move_tick, PlayerMoveSpeedInput, PlayerMoveTickInput,
    };
    use crate::team_plan::TeamPlanSignals;

    fn movement() -> DefenseMovementInput<'static> {
        DefenseMovementInput {
            velocity: (0.0, 0.0),
            speed_ability: 80,
            defence: 80.0,
            state: "off_ball",
            plan_signals: TeamPlanSignals::default(),
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        }
    }

    fn teammates() -> [DefenseTeammateInput; 3] {
        [
            DefenseTeammateInput {
                pos: (79.0, 34.0),
                target_pos: (79.0, 34.0),
                anchor: (76.0, 34.0),
            },
            DefenseTeammateInput {
                pos: (68.0, 24.0),
                target_pos: (68.0, 24.0),
                anchor: (67.0, 22.0),
            },
            DefenseTeammateInput {
                pos: (64.0, 46.0),
                target_pos: (64.0, 46.0),
                anchor: (63.0, 46.0),
            },
        ]
    }

    fn assert_defense_scores_identical(actual: DefenseScoreOutput, expected: DefenseScoreOutput) {
        macro_rules! assert_field {
            ($field:ident) => {
                assert_eq!(
                    actual.$field.to_bits(),
                    expected.$field.to_bits(),
                    stringify!($field)
                );
            };
        }

        assert_field!(score);
        assert_eq!(actual.target, expected.target);
        assert_eq!(actual.movement_target, expected.movement_target);
        assert_eq!(actual.projected_pos, expected.projected_pos);
        assert_eq!(actual.action_type, expected.action_type);
        assert_field!(residual_threat);
        assert_field!(base_score);
        assert_field!(press_value);
        assert_field!(press_access);
        assert_field!(carrier_threat);
        assert_field!(shot_lane_closure);
        assert_field!(best_mark_value);
    }

    fn assert_fixed_prepared_choices_identical(
        actual: FixedDefensePreparedChoice,
        expected: FixedDefensePreparedChoice,
    ) {
        assert_eq!(actual.candidate_count, expected.candidate_count);
        assert_eq!(actual.local_attackers_count, expected.local_attackers_count);
        assert_eq!(
            actual.dangerous_receivers_count,
            expected.dangerous_receivers_count
        );
        assert_eq!(
            actual.press_access.to_bits(),
            expected.press_access.to_bits()
        );
        assert_eq!(actual.shot_danger.to_bits(), expected.shot_danger.to_bits());
        assert_eq!(
            actual.carrier_control_threat.to_bits(),
            expected.carrier_control_threat.to_bits()
        );
        for index in 0..actual.candidate_count {
            assert_eq!(
                actual.candidate_targets[index].0.to_bits(),
                expected.candidate_targets[index].0.to_bits()
            );
            assert_eq!(
                actual.candidate_targets[index].1.to_bits(),
                expected.candidate_targets[index].1.to_bits()
            );
            assert_eq!(
                actual.candidate_scores[index].to_bits(),
                expected.candidate_scores[index].to_bits()
            );
            assert_eq!(
                actual.candidate_movement_targets[index].0.to_bits(),
                expected.candidate_movement_targets[index].0.to_bits()
            );
            assert_eq!(
                actual.candidate_movement_targets[index].1.to_bits(),
                expected.candidate_movement_targets[index].1.to_bits()
            );
            assert_eq!(
                actual.candidate_projected_positions[index].0.to_bits(),
                expected.candidate_projected_positions[index].0.to_bits()
            );
            assert_eq!(
                actual.candidate_projected_positions[index].1.to_bits(),
                expected.candidate_projected_positions[index].1.to_bits()
            );
            assert_eq!(
                actual.candidate_action_types[index],
                expected.candidate_action_types[index]
            );
            assert_eq!(
                actual.candidate_residual_threats[index].to_bits(),
                expected.candidate_residual_threats[index].to_bits()
            );
        }
    }

    #[test]
    fn approach_reachability_respects_speed_turning_and_task_window() {
        let direct = defensive_approach_reachability(
            (42.0, 34.0),
            (57.0, 34.0),
            (42.0, 34.0),
            12.0,
            movement(),
            4,
        );
        let retreating = defensive_approach_reachability(
            (42.0, 34.0),
            (57.0, 34.0),
            (42.0, 34.0),
            12.0,
            DefenseMovementInput {
                velocity: (-5.0, 0.0),
                ..movement()
            },
            4,
        );
        let short_window = defensive_approach_reachability(
            (42.0, 34.0),
            (57.0, 34.0),
            (42.0, 34.0),
            12.0,
            movement(),
            1,
        );

        assert!(
            direct > retreating,
            "a defender already moving toward the carrier must be more reachable than one who first has to turn"
        );
        assert!(
            direct > short_window,
            "a legal multi-tick press commitment must value future arrival more than the current-tick snapshot"
        );
        assert!(
            retreating < 1.0 && short_window < 1.0,
            "reachability is a motion prediction, not an instant arrival claim"
        );
    }

    #[test]
    fn moving_carrier_cannot_be_claimed_by_a_distant_non_intercepting_pursuer() {
        let unreachable = defensive_interception_reachability(
            (52.0, 34.0),
            (88.0, 34.0),
            (5.0, 0.0),
            (52.0, 34.0),
            12.0,
            movement(),
            4,
        );
        let converging = defensive_interception_reachability(
            (86.0, 28.0),
            (88.0, 34.0),
            (2.0, 0.0),
            (86.0, 28.0),
            12.0,
            movement(),
            4,
        );

        assert!(
            unreachable < 0.05,
            "distance alone must not let a defender claim a moving carrier they cannot intercept: {unreachable}"
        );
        assert!(
            converging > unreachable + 0.20,
            "a genuinely converging trajectory must produce materially more closure: unreachable={unreachable}, converging={converging}"
        );
    }

    #[test]
    fn pursuit_requires_future_closure_without_claiming_immediate_contact() {
        let teammates = teammates();
        let carrier = (57.0, 34.0);
        let input = DefenseChoiceInput {
            defender_pos: (42.0, 34.0),
            anchor: (42.0, 34.0),
            base_ref: (42.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 0,
            ball_carrier_possession_ticks: 3,
            carrier_control_readiness: 0.88,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.72,
            compactness: 0.60,
            movement: movement(),
            iq: 90.0,
            attackers: &[carrier],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let action = defense_action_type(carrier, &input, 15.0, 0.60, 0.60, &[], &[]);
        let reachability = defensive_pursuit_reachability(
            input.defender_pos,
            carrier,
            input.anchor,
            input.press_radius,
            input.movement,
            4,
        );

        assert_eq!(
            action, "pursuit",
            "a defender outside immediate contact but able to close in the commitment window must pursue"
        );
        assert!(
            reachability > 0.10,
            "pursuit must be backed by physical future reachability"
        );
        assert!(
            close_down_contact_window(
                input.defender_pos,
                carrier,
                input.anchor,
                input.tackle_range,
                input.movement,
            ) < 0.10,
            "pursuit must not fabricate an immediate tackle window"
        );
    }

    #[test]
    fn unreachable_defender_does_not_receive_a_pursuit_label() {
        let teammates = teammates();
        let carrier = (82.0, 34.0);
        let input = DefenseChoiceInput {
            defender_pos: (42.0, 34.0),
            anchor: (42.0, 34.0),
            base_ref: (42.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 0,
            ball_carrier_possession_ticks: 3,
            carrier_control_readiness: 0.88,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.72,
            compactness: 0.60,
            movement: movement(),
            iq: 90.0,
            attackers: &[carrier],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let action = defense_action_type(carrier, &input, 40.0, 0.60, 0.60, &[], &[]);
        let reachability = defensive_pursuit_reachability(
            input.defender_pos,
            carrier,
            input.anchor,
            input.press_radius,
            input.movement,
            4,
        );

        assert!(
            reachability <= 0.10,
            "the narrow unreachable control must be outside the closure window"
        );
        assert_ne!(
            action, "pursuit",
            "the decision layer must not label an unreachable player as a future closer"
        );
    }

    #[test]
    fn fixed_team_context_preserves_every_defender_candidate_score() {
        let defenders = [
            DefenseTeammateInput {
                pos: (79.0, 34.0),
                target_pos: (80.0, 34.0),
                anchor: (76.0, 34.0),
            },
            DefenseTeammateInput {
                pos: (75.0, 22.0),
                target_pos: (76.0, 24.0),
                anchor: (73.0, 21.0),
            },
            DefenseTeammateInput {
                pos: (74.0, 46.0),
                target_pos: (75.0, 44.0),
                anchor: (72.0, 47.0),
            },
            DefenseTeammateInput {
                pos: (68.0, 34.0),
                target_pos: (69.0, 34.0),
                anchor: (66.0, 34.0),
            },
        ];
        let carrier = (84.0, 34.0);
        let context = fixed_defense_team_context(
            carrier,
            Some(carrier),
            5,
            0.83,
            false,
            105.0,
            68.0,
            12.0,
            &defenders,
        );
        let teammates_by_defender: [[DefenseTeammateInput; 3]; 4] =
            std::array::from_fn(|defender_index| {
                std::array::from_fn(|teammate_offset| {
                    defenders[if teammate_offset < defender_index {
                        teammate_offset
                    } else {
                        teammate_offset + 1
                    }]
                })
            });

        for defender_index in 0..defenders.len() {
            let defender = defenders[defender_index];
            let input = DefenseChoiceInput {
                defender_pos: defender.pos,
                anchor: defender.anchor,
                base_ref: defender.anchor,
                ball_pos: carrier,
                ball_carrier_pos: Some(carrier),
                carrier_velocity: (0.0, 0.0),
                ball_carrier_consecutive_carries: 3,
                ball_carrier_possession_ticks: 5,
                carrier_control_readiness: 0.83,
                attacking_right: false,
                pitch_length: 105.0,
                pitch_width: 68.0,
                press_radius: 12.0,
                tackle_range: 6.0,
                carrier_speed: 3.0,
                press_intensity: 0.72,
                compactness: 0.61,
                movement: movement(),
                iq: 76.0,
                attackers: &[carrier, (72.0, 24.0), (70.0, 45.0), (64.0, 34.0)],
                teammates: &teammates_by_defender[defender_index],
                random_samples: &[],
                score_noises: &[],
                roll_by_count: &[],
                fallback_index_by_count: &[],
            };
            let direct =
                best_fixed_team_defense_candidate(&input).expect("direct defense candidate");
            let shared = best_fixed_team_defense_candidate_with_team_context(
                &input,
                Some((&context, defender_index)),
            )
            .expect("shared defense candidate");
            assert_defense_scores_identical(shared, direct);
            let shared_input = DefenseChoiceInput {
                defender_pos: defender.pos,
                anchor: defender.anchor,
                base_ref: defender.anchor,
                ball_pos: carrier,
                ball_carrier_pos: Some(carrier),
                carrier_velocity: (0.0, 0.0),
                ball_carrier_consecutive_carries: 3,
                ball_carrier_possession_ticks: 5,
                carrier_control_readiness: 0.83,
                attacking_right: false,
                pitch_length: 105.0,
                pitch_width: 68.0,
                press_radius: 12.0,
                tackle_range: 6.0,
                carrier_speed: 3.0,
                press_intensity: 0.72,
                compactness: 0.61,
                movement: movement(),
                iq: 76.0,
                attackers: &[carrier, (72.0, 24.0), (70.0, 45.0), (64.0, 34.0)],
                teammates: &[],
                random_samples: &[],
                score_noises: &[],
                roll_by_count: &[],
                fallback_index_by_count: &[],
            };
            let shared_without_rebuilt_teammates =
                best_fixed_team_defense_candidate_with_team_context(
                    &shared_input,
                    Some((&context, defender_index)),
                )
                .expect("shared defense candidate without rebuilt teammates");
            assert_defense_scores_identical(shared_without_rebuilt_teammates, direct);
            let direct_prepared =
                prepare_fixed_defense_choice(&input).expect("direct prepared defense choice");
            let shared_prepared = prepare_fixed_defense_choice_with_team_context(
                &shared_input,
                Some((&context, defender_index)),
            )
            .expect("shared prepared defense choice");
            assert_fixed_prepared_choices_identical(shared_prepared, direct_prepared);
        }
    }

    #[test]
    fn nearby_teammates_do_not_dilute_local_press_candidates() {
        let nearby_teammates = teammates();
        let carrier = (84.0, 34.0);
        let with_teammates = DefenseScoreInput {
            defender_pos: (82.0, 34.0),
            anchor: (80.0, 34.0),
            base_ref: (80.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.80,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            candidates: &[],
            attackers: &[],
            local_attackers: &[],
            dangerous_receivers: &[],
            teammates: &nearby_teammates,
        };
        let isolated = DefenseScoreInput {
            teammates: &[],
            ..with_teammates
        };
        let with_teammates_choice = score_defense_candidates(&DefenseScoreInput {
            candidates: &[carrier],
            ..with_teammates
        })
        .remove(0);
        let isolated_choice = score_defense_candidates(&DefenseScoreInput {
            candidates: &[carrier],
            ..isolated
        })
        .remove(0);

        assert!(
            matches!(with_teammates_choice.action_type, "tackle" | "approach"),
            "nearby visible teammates must not suppress this player's executable press: {with_teammates_choice:?}"
        );
        assert_eq!(
            with_teammates_choice.action_type, isolated_choice.action_type,
            "candidate semantics are local; team responsibility is assigned later"
        );
        assert_eq!(
            with_teammates_choice.press_access.to_bits(),
            isolated_choice.press_access.to_bits()
        );
    }

    #[test]
    fn carrier_is_not_counted_as_a_marking_receiver() {
        let teammates = teammates();
        let carrier = (84.0, 34.0);
        let input = DefenseChoiceInput {
            defender_pos: (82.0, 34.0),
            anchor: (80.0, 34.0),
            base_ref: (80.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.80,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            iq: 1.0,
            attackers: &[carrier],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let choice = choose_defense_action(&input).expect("defense choice");
        assert_eq!(choice.local_attackers_count, 0);
        assert_eq!(choice.dangerous_receivers_count, 0);
    }

    #[test]
    fn reachable_primary_carrier_engagement_is_not_reclassified_as_marking() {
        let teammates = teammates();
        let input = DefenseChoiceInput {
            defender_pos: (82.0, 34.0),
            anchor: (80.0, 34.0),
            base_ref: (80.0, 34.0),
            ball_pos: (84.0, 34.0),
            ball_carrier_pos: Some((84.0, 34.0)),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.80,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            iq: 1.0,
            attackers: &[],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let action = defense_action_type((84.0, 34.0), &input, 2.0, 0.6, 0.6, &[], &[]);
        assert!(
            matches!(action, "tackle" | "approach"),
            "the reachable primary defender must engage the carrier, got {action}"
        );
    }

    #[test]
    fn tackle_label_requires_the_selected_target_to_engage_the_carrier() {
        let teammates = teammates();
        let input = DefenseChoiceInput {
            defender_pos: (82.0, 34.0),
            anchor: (80.0, 34.0),
            base_ref: (80.0, 34.0),
            ball_pos: (84.0, 34.0),
            ball_carrier_pos: Some((84.0, 34.0)),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.80,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            iq: 1.0,
            attackers: &[],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let action = defense_action_type((48.0, 28.0), &input, 2.0, 0.6, 0.6, &[], &[]);
        assert_ne!(
            action, "tackle",
            "a defender moving away from the carrier cannot have tackle contact semantics"
        );
    }

    #[test]
    fn sustained_unpressured_control_selects_a_reachable_primary_engagement() {
        let teammates = [
            DefenseTeammateInput {
                pos: (66.0, 18.0),
                target_pos: (66.0, 18.0),
                anchor: (66.0, 18.0),
            },
            DefenseTeammateInput {
                pos: (69.0, 50.0),
                target_pos: (69.0, 50.0),
                anchor: (69.0, 50.0),
            },
        ];
        let carrier = (54.0, 34.0);
        let input = DefenseChoiceInput {
            defender_pos: (50.0, 34.0),
            anchor: (50.0, 34.0),
            base_ref: (50.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 0,
            ball_carrier_possession_ticks: 8,
            carrier_control_readiness: 0.95,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            iq: 1.0,
            attackers: &[carrier],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let choice = choose_defense_action(&input).expect("defense choice");

        assert_eq!(choice.shot_danger, 0.0);
        assert!(choice.carrier_control_threat > 0.45);
        assert!(
            matches!(choice.action_type, "tackle" | "approach"),
            "a reachable primary defender must deny sustained unpressured control, got {}",
            choice.action_type
        );
    }

    #[test]
    fn receiving_window_with_cover_triggers_local_engagement() {
        let teammates = [
            DefenseTeammateInput {
                pos: (47.0, 34.0),
                target_pos: (47.0, 34.0),
                anchor: (47.0, 34.0),
            },
            DefenseTeammateInput {
                pos: (50.0, 26.0),
                target_pos: (50.0, 26.0),
                anchor: (50.0, 26.0),
            },
        ];
        let carrier = (54.0, 34.0);
        let input = DefenseChoiceInput {
            defender_pos: (50.0, 34.0),
            anchor: (50.0, 34.0),
            base_ref: (50.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 0,
            ball_carrier_possession_ticks: 0,
            carrier_control_readiness: 0.95,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            iq: 1.0,
            attackers: &[carrier],
            teammates: &teammates,
            random_samples: &[],
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };

        let choice = choose_defense_action(&input).expect("defense choice");

        assert!(
            choice.carrier_control_threat > 0.45,
            "the receiving window must be actionable before possession ticks accumulate"
        );
        assert!(
            matches!(choice.action_type, "tackle" | "approach"),
            "a nearby defender with cover must engage the visible receiver, got {}",
            choice.action_type
        );
    }

    #[test]
    fn fixed_choice_kernel_matches_dynamic_prepare_and_selection() {
        let teammates = teammates();
        let carrier = (84.0, 34.0);
        let samples = [
            DefenseRandomSample {
                angle_unit: 0.12,
                radius_unit: 0.66,
            },
            DefenseRandomSample {
                angle_unit: 0.51,
                radius_unit: 0.27,
            },
            DefenseRandomSample {
                angle_unit: 0.83,
                radius_unit: 0.91,
            },
        ];
        let input = DefenseChoiceInput {
            defender_pos: (79.0, 34.0),
            anchor: (78.0, 34.0),
            base_ref: (78.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (0.0, 0.0),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.83,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.75,
            compactness: 0.6,
            movement: movement(),
            iq: 76.0,
            attackers: &[carrier, (72.0, 25.0), (70.0, 45.0), (62.0, 34.0)],
            teammates: &teammates,
            random_samples: &samples,
            score_noises: &[],
            roll_by_count: &[],
            fallback_index_by_count: &[],
        };
        let dynamic = prepare_defense_choice(&input).expect("dynamic prepared choice");
        let fixed = prepare_fixed_defense_choice(&input).expect("fixed prepared choice");

        assert_eq!(fixed.candidate_count, dynamic.candidate_count());
        assert_eq!(fixed.local_attackers_count, dynamic.local_attackers_count);
        assert_eq!(
            fixed.dangerous_receivers_count,
            dynamic.dangerous_receivers_count
        );
        assert_eq!(fixed.shot_danger, dynamic.shot_danger);
        assert_eq!(fixed.carrier_control_threat, dynamic.carrier_control_threat);
        assert_eq!(fixed.press_access, dynamic.press_access);
        for (index, candidate) in dynamic.scored.iter().enumerate() {
            assert_eq!(fixed.candidate_targets[index], candidate.target);
            assert_eq!(fixed.candidate_scores[index], candidate.score);
            assert_eq!(
                fixed.candidate_movement_targets[index],
                candidate.movement_target
            );
            assert_eq!(
                fixed.candidate_projected_positions[index],
                candidate.projected_pos
            );
            assert_eq!(fixed.candidate_action_types[index], candidate.action_type);
            assert_eq!(
                fixed.candidate_residual_threats[index],
                candidate.residual_threat
            );
        }

        let noises = (0..fixed.candidate_count)
            .map(|index| (index as f64 - 3.0) * 0.013)
            .collect::<Vec<_>>();
        let mut rolls = vec![0.0; fixed.candidate_count + 1];
        let mut fallbacks = vec![0usize; fixed.candidate_count + 1];
        rolls[fixed.candidate_count] = 0.37;
        fallbacks[fixed.candidate_count] = 2;
        assert_eq!(
            fixed_defense_random_branch(&fixed, input.iq, &noises),
            super::prepared_defense_choice_random_branch(&dynamic, input.iq, &noises)
        );
        let dynamic_choice =
            select_prepared_defense_action(&dynamic, input.iq, &noises, &rolls, &fallbacks)
                .expect("dynamic choice");
        let dynamic_selection =
            select_prepared_defense_candidate(&dynamic, input.iq, &noises, &rolls, &fallbacks)
                .expect("dynamic selection");
        let fixed_choice =
            select_fixed_defense_action(&fixed, input.iq, &noises, &rolls, &fallbacks)
                .expect("fixed choice");
        assert_eq!(fixed_choice.chosen_index, dynamic_selection.chosen_index);
        assert_eq!(
            fixed_choice.score,
            dynamic_selection.noisy_scores[dynamic_selection.chosen_index]
        );
        assert_eq!(
            fixed.candidate_targets[fixed_choice.chosen_index],
            dynamic_choice.target
        );
        assert_eq!(fixed_choice.score, dynamic_choice.score);
        assert_eq!(fixed_choice.used_roll, dynamic_choice.used_roll);
        assert_eq!(
            fixed_choice.used_random_choice,
            dynamic_choice.used_random_choice
        );
    }

    #[test]
    fn carrier_closure_moves_to_the_carrier_instead_of_their_sampled_shape_point() {
        let teammates = teammates();
        let carrier = (84.0, 34.0);
        let sampled_shape_point = (78.0, 29.0);
        let scored = score_defense_candidates(&DefenseScoreInput {
            defender_pos: (79.0, 34.0),
            anchor: (78.0, 34.0),
            base_ref: (78.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            ball_carrier_consecutive_carries: 3,
            ball_carrier_possession_ticks: 4,
            carrier_control_readiness: 0.85,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.75,
            compactness: 0.6,
            movement: movement(),
            candidates: &[sampled_shape_point],
            attackers: &[carrier],
            local_attackers: &[],
            dangerous_receivers: &[],
            teammates: &teammates,
        });

        let carrier_task = scored
            .iter()
            .find(|candidate| matches!(candidate.action_type, "close_down" | "tackle" | "approach"))
            .expect("the nearby defender must receive a carrier-closing task");

        assert_eq!(carrier_task.action_type, "close_down");
        assert_eq!(carrier_task.target, carrier);
        assert_ne!(carrier_task.target, sampled_shape_point);
    }

    #[test]
    fn approach_preserves_its_predicted_interception_target() {
        let carrier = (95.0, 28.0);
        let interception = (99.0, 31.0);
        assert_eq!(
            defense_task_target("approach", interception, Some(carrier)),
            interception
        );
    }

    #[test]
    fn pursuit_preserves_its_predicted_interception_target() {
        let carrier = (95.0, 28.0);
        let interception = (99.5, 30.0);
        assert_eq!(
            defense_task_target("pursuit", interception, Some(carrier)),
            interception
        );
    }

    #[test]
    fn moving_carrier_interception_follows_velocity_vector_instead_of_goal_axis() {
        let carrier = (72.0, 27.0);
        let input = DefenseRawInput {
            defender_pos: (66.0, 34.0),
            anchor: (66.0, 34.0),
            ball_pos: carrier,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            carrier_speed: 6.0,
            carrier_control_threat: 0.8,
            shot_danger: 0.4,
            local_attackers: &[],
            dangerous_receivers: &[],
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (2.4, 2.0),
            shot_lane_threat: 0.0,
            random_samples: &[],
        };

        let interception =
            predicted_carrier_interception_point(&input).expect("moving carrier interception");

        assert!(interception.0 > carrier.0);
        assert!(
            interception.1 > carrier.1,
            "a carrier cutting laterally must create a lateral interception lead, not a fixed goal-axis point"
        );
        assert_eq!(
            defense_task_target("pursuit", interception, Some(carrier)),
            interception
        );
    }

    #[test]
    fn moving_carrier_interception_projects_acceleration_not_only_current_velocity() {
        let carrier = (72.0, 27.0);
        let mut input = DefenseRawInput {
            defender_pos: (66.0, 34.0),
            anchor: (66.0, 34.0),
            ball_pos: carrier,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            carrier_speed: 2.0,
            carrier_control_threat: 0.8,
            shot_danger: 0.4,
            local_attackers: &[],
            dangerous_receivers: &[],
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (2.0, 0.0),
            shot_lane_threat: 0.0,
            random_samples: &[],
        };
        let constant_velocity =
            predicted_carrier_interception_point(&input).expect("constant-speed interception");
        input.carrier_speed = 6.0;
        let accelerating =
            predicted_carrier_interception_point(&input).expect("accelerating interception");

        assert!(
            accelerating.0 > constant_velocity.0,
            "the interception horizon must include the carrier's reachable acceleration instead of extrapolating only current velocity"
        );
        assert_eq!(accelerating.1, constant_velocity.1);
    }

    #[test]
    fn containment_candidates_rotate_into_the_carriers_breakthrough_corridor() {
        let carrier = (84.0, 32.0);
        let input = DefenseRawInput {
            defender_pos: (89.0, 38.0),
            anchor: (90.0, 40.0),
            ball_pos: carrier,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            carrier_speed: 6.0,
            carrier_control_threat: 0.8,
            shot_danger: 0.4,
            local_attackers: &[],
            dangerous_receivers: &[],
            ball_carrier_pos: Some(carrier),
            carrier_velocity: (4.0, -2.0),
            shot_lane_threat: 0.0,
            random_samples: &[],
        };

        let candidates = generate_defense_raw_candidates(&input);
        let contain_center = candidates[5];

        assert!(
            contain_center.0 > carrier.0 && contain_center.1 < carrier.1,
            "the central containment point must rotate with a carrier cutting diagonally toward goal: {contain_center:?}"
        );
    }

    #[test]
    fn defensive_motion_uses_the_same_player_physics_kernel_without_a_speed_bonus() {
        let movement = DefenseMovementInput {
            velocity: (0.8, -0.2),
            speed_ability: 86,
            defence: 92.0,
            state: "off_ball",
            plan_signals: TeamPlanSignals::default(),
            player_max_speed: 8.0,
            player_min_speed: 2.5,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };
        let defender = project_defense_action_motion(
            (50.0, 30.0),
            (58.0, 35.0),
            (48.0, 30.0),
            "pursuit",
            movement,
        );
        let shared = player_move_tick(&PlayerMoveTickInput {
            pos: (50.0, 30.0),
            target_pos: (58.0, 35.0),
            velocity: movement.velocity,
            speed_ability: movement.speed_ability,
            movement_intent: defense_action_movement_intent("pursuit"),
            state: movement.state,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
            pitch_length: movement.pitch_length,
            pitch_width: movement.pitch_width,
        });

        assert_eq!(defender.pos, shared.pos);
        assert_eq!(defender.velocity, shared.velocity);
        assert_eq!(defender.distance_covered, shared.distance_covered);
        assert_eq!(defender.facing_direction, shared.facing_direction);
    }

    #[test]
    fn goalkeeper_smother_uses_contest_urgency_without_bypassing_shared_motion() {
        let movement = DefenseMovementInput {
            velocity: (-4.4, 1.6),
            speed_ability: 96,
            defence: 24.0,
            state: "off_ball",
            plan_signals: TeamPlanSignals::default(),
            player_max_speed: 18.0,
            player_min_speed: 4.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };
        let origin = (98.1, 35.5);
        let target = (103.7, 32.8);
        let smother =
            project_defense_action_motion(origin, target, (102.7, 34.0), "smother", movement);
        let desired_speed = player_move_speed(&PlayerMoveSpeedInput {
            pos: origin,
            target_pos: target,
            speed_ability: movement.speed_ability,
            movement_intent: "contest",
            state: movement.state,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
        })
        .speed;
        let shared = crate::physics::advance_player_motion(&crate::physics::PlayerMotionInput {
            pos: origin,
            target,
            velocity: movement.velocity,
            speed_ability: movement.speed_ability,
            desired_speed,
            acceleration_scale: 1.5,
            player_max_speed: movement.player_max_speed,
            player_min_speed: movement.player_min_speed,
            pitch_length: movement.pitch_length,
            pitch_width: movement.pitch_width,
        });
        let press = player_move_tick(&PlayerMoveTickInput {
            movement_intent: "press",
            ..PlayerMoveTickInput {
                pos: origin,
                target_pos: target,
                velocity: movement.velocity,
                speed_ability: movement.speed_ability,
                movement_intent: "contest",
                state: movement.state,
                player_max_speed: movement.player_max_speed,
                player_min_speed: movement.player_min_speed,
                pitch_length: movement.pitch_length,
                pitch_width: movement.pitch_width,
            }
        });

        assert_eq!(defense_action_movement_intent("smother"), "contest");
        assert_eq!(smother.pos, shared.pos);
        assert_eq!(smother.velocity, shared.velocity);
        assert!(
            (smother.velocity.0 * smother.velocity.0 + smother.velocity.1 * smother.velocity.1)
                .sqrt()
                <= crate::physics::player_speed(
                    movement.speed_ability,
                    movement.player_max_speed,
                    movement.player_min_speed
                ) * 0.98
                    + 1e-9
        );
        let target_delta = (target.0 - origin.0, target.1 - origin.1);
        let target_length =
            (target_delta.0 * target_delta.0 + target_delta.1 * target_delta.1).sqrt();
        let smother_target_speed = (smother.velocity.0 * target_delta.0
            + smother.velocity.1 * target_delta.1)
            / target_length;
        let press_target_speed =
            (press.velocity.0 * target_delta.0 + press.velocity.1 * target_delta.1) / target_length;
        assert!(
            smother_target_speed > press_target_speed,
            "a committed smother must redirect velocity toward the live interception faster than ordinary pressure: smother={smother_target_speed}, press={press_target_speed}"
        );
    }

    #[test]
    fn high_danger_primary_engagement_outweighs_a_retreating_lane_cover() {
        let teammates = [
            DefenseTeammateInput {
                pos: (82.0, 18.0),
                target_pos: (82.0, 18.0),
                anchor: (82.0, 18.0),
            },
            DefenseTeammateInput {
                pos: (82.0, 50.0),
                target_pos: (82.0, 50.0),
                anchor: (82.0, 50.0),
            },
        ];
        let carrier = (100.03, 34.02);
        let retreating_cover = (102.32, 37.14);
        let candidates = [retreating_cover, carrier];
        let scored = score_defense_candidates(&DefenseScoreInput {
            defender_pos: (100.54, 34.00),
            anchor: (96.0, 34.0),
            base_ref: (96.0, 34.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            ball_carrier_consecutive_carries: 4,
            ball_carrier_possession_ticks: 5,
            carrier_control_readiness: 0.86,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 3.0,
            press_intensity: 0.7,
            compactness: 0.6,
            movement: movement(),
            candidates: &candidates,
            attackers: &[carrier],
            local_attackers: &[],
            dangerous_receivers: &[],
            teammates: &teammates,
        });

        assert!(
            scored[1].score > scored[0].score,
            "the nearby primary defender must prefer carrier engagement over retreating lane cover: {:?}",
            scored
        );
    }

    #[test]
    fn reachable_box_defender_values_shrinking_the_carriers_control_window() {
        let carrier = (100.1, 30.6);
        let candidates = [(104.4, 29.0), carrier];
        let scored = score_defense_candidates(&DefenseScoreInput {
            defender_pos: (90.9, 27.8),
            anchor: (88.0, 28.0),
            base_ref: (88.0, 28.0),
            ball_pos: carrier,
            ball_carrier_pos: Some(carrier),
            ball_carrier_consecutive_carries: 2,
            ball_carrier_possession_ticks: 3,
            carrier_control_readiness: 0.84,
            attacking_right: false,
            pitch_length: 105.0,
            pitch_width: 68.0,
            press_radius: 12.0,
            tackle_range: 6.0,
            carrier_speed: 6.0,
            press_intensity: 0.68,
            compactness: 0.64,
            movement: movement(),
            candidates: &candidates,
            attackers: &[carrier],
            local_attackers: &[],
            dangerous_receivers: &[],
            teammates: &[],
        });

        assert!(matches!(
            scored[1].action_type,
            "close_down" | "approach" | "tackle"
        ));
        assert!(
            scored[1].score > scored[0].score,
            "a reachable defender must value reducing the carrier's live action window over a retreating lane point: {scored:?}"
        );
    }
}
