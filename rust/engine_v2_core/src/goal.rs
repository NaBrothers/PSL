#[derive(Debug, Clone)]
pub struct GoalSwitchCostInput {
    pub base: f64,
    pub context_stability: f64,
    pub role_discipline: f64,
    pub pressure_interrupt: f64,
    pub iq: f64,
}

#[derive(Debug, Clone)]
pub struct GoalInput<'a> {
    pub goal_type: &'a str,
    pub value: f64,
    pub phase: Option<&'a str>,
}

#[derive(Debug, Clone, Copy)]
pub struct GoalSelectionOutput {
    pub selected: &'static str,
    pub switched: bool,
    pub switch_cost: f64,
    pub value_advantage: f64,
    pub noisy_value_advantage: f64,
    pub reason: &'static str,
}

#[derive(Debug, Clone)]
pub struct GoalCandidateChoiceOutput {
    pub index: usize,
    pub candidate_noise: f64,
    pub noisy_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OnBallGenericCandidateInput {
    pub score: f64,
    pub action_code: u8,
    pub target: Option<(f64, f64)>,
    pub progress_gain: f64,
    pub xg: f64,
    pub pressure: f64,
    pub receiver_pressure: f64,
    pub target_kind_space: bool,
    pub lateral_change: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OnBallGenericGoalInput<'a> {
    pub goal_type: Option<&'a str>,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub action_code: u8,
}

#[derive(Clone, Debug)]
pub struct OnBallGenericContinuityInput<'a> {
    pub candidates: &'a [OnBallGenericCandidateInput],
    pub current_goal: Option<OnBallGenericGoalInput<'a>>,
    pub iq: f64,
    pub goal_cut_inside_bias: f64,
}

#[derive(Clone, Debug)]
pub struct OnBallGenericContinuityOutput {
    pub selected_goal_type: String,
    pub selected_action_code: u8,
    pub selected_target: (f64, f64),
    pub selected_value: f64,
    pub candidate_goal_type: String,
    pub candidate_action_code: u8,
    pub candidate_target: (f64, f64),
    pub candidate_value: f64,
    pub switched: bool,
    pub switch_cost: f64,
    pub value_advantage: f64,
    pub reason: String,
    pub biased_scores: Vec<f64>,
    pub alignments: Vec<f64>,
}

#[derive(Clone, Copy, Debug)]
pub struct OnBallSpecializedBiasCandidateInput {
    pub score: f64,
    pub action_code: u8,
    pub target: Option<(f64, f64)>,
    pub carry_to_shoot_window: f64,
    pub wide_second_line_carry_window: f64,
    pub future_shot_gain: f64,
    pub byline_carry_window: f64,
    pub xg: f64,
    pub shot_readiness: f64,
    pub open_medium_window: f64,
    pub clean_second_line_shot: f64,
    pub space_manipulation: f64,
    pub pressure_draw: f64,
}

#[derive(Clone, Debug)]
pub struct OnBallSpecializedBiasInput<'a> {
    pub candidates: &'a [OnBallSpecializedBiasCandidateInput],
    pub goal_type: &'a str,
    pub goal_phase: &'a str,
    pub goal_target: (f64, f64),
    pub goal_value: f64,
    pub bias: f64,
    pub consecutive_carries: i32,
}

#[derive(Clone, Debug)]
pub struct OnBallSpecializedBiasOutput {
    pub biased_scores: Vec<f64>,
    pub alignments: Vec<f64>,
    pub opportunity_target_indices: Vec<usize>,
}

#[derive(Clone, Copy, Debug)]
pub struct CutInsideGoalInput {
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub best_carry_target: Option<(f64, f64)>,
    pub future_shot_gain: f64,
    pub carry_to_shoot_window: f64,
    pub wide_second_line_carry_window: f64,
    pub current_shot: f64,
    pub current_readiness: f64,
    pub consecutive_carries: i32,
    pub goal_age_ticks: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct CutInsideGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub phase_code: u8,
    pub progress: f64,
    pub width: f64,
    pub finish_window: f64,
    pub drive_staleness: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DriveBylineGoalInput {
    pub player_pos: (f64, f64),
    pub carry_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub carry_score: f64,
    pub progress_gain: f64,
    pub byline_carry_window: f64,
    pub path_feasibility: f64,
    pub space_manipulation: f64,
    pub delivery_support: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct BylineDeliveryGoalInput {
    pub player_pos: (f64, f64),
    pub delivery_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub pass_score: f64,
    pub target_progress: f64,
    pub centrality: f64,
    pub high_threat_space: f64,
    pub final_third_combination: f64,
    pub success_prob: f64,
    pub receiver_pressure: f64,
    pub lane_risk: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct BylineGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub phase_code: u8,
    pub origin_progress: f64,
    pub origin_width: f64,
    pub target_progress: f64,
    pub target_width_or_centrality: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ThroughBallGoalInput {
    pub player_pos: (f64, f64),
    pub pass_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub pass_score: f64,
    pub target_kind_space: bool,
    pub target_progress: f64,
    pub centrality: f64,
    pub progress_gain: f64,
    pub high_threat_space: f64,
    pub success_prob: f64,
    pub receiver_pressure: f64,
    pub lane_risk: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ThroughBallGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub origin_progress: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct WideHoldOverlapGoalInput {
    pub player_pos: (f64, f64),
    pub overlap_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub overlap_value: f64,
    pub immediate_best_score: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct WideHoldOverlapGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub progress: f64,
    pub width: f64,
    pub target_progress: f64,
    pub target_width: f64,
    pub forward_gap: f64,
    pub same_lane: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ArcArrivalGoalInput {
    pub player_pos: (f64, f64),
    pub anchor_pos: (f64, f64),
    pub ball_pos: (f64, f64),
    pub base_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ArcArrivalGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub ball_progress: f64,
    pub ball_width: f64,
    pub anchor_progress: f64,
    pub base_progress: f64,
    pub anchor_width: f64,
    pub target_dist: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct AttackFarPostGoalInput {
    pub player_pos: (f64, f64),
    pub anchor_pos: (f64, f64),
    pub ball_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub goal_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct AttackFarPostGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub ball_progress: f64,
    pub ball_width: f64,
    pub weak_side: f64,
    pub player_progress: f64,
    pub anchor_progress: f64,
    pub target_dist: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackGoalBuildInput {
    pub target_pos: (f64, f64),
    pub value: f64,
    pub second_line_support: f64,
    pub inside_support: f64,
    pub support_angle_value: f64,
    pub layoff_window: f64,
    pub candidate_progress: f64,
    pub candidate_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OffBallAttackGoalBuildOutput {
    pub goal_type: &'static str,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub box_arrival: f64,
    pub second_line_support: f64,
    pub inside_support: f64,
    pub support_angle_value: f64,
    pub layoff_window: f64,
    pub candidate_progress: f64,
    pub candidate_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DefensiveGoalBuildInput<'a> {
    pub action_type: &'a str,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub pressure: f64,
    pub threat: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct DefensiveGoalBuildOutput<'a> {
    pub goal_type: &'static str,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub action_type: &'a str,
    pub pressure: f64,
    pub threat: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct LayoffGoalInput {
    pub player_pos: (f64, f64),
    pub layoff_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attracted_pressure: f64,
    pub layoff_value: f64,
    pub immediate_best_score: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct LayoffGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub progress: f64,
    pub target_progress: f64,
    pub target_centrality: f64,
    pub pass_distance: f64,
    pub backward_depth: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReleaseSupportGoalInput {
    pub player_pos: (f64, f64),
    pub support_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub support_value: f64,
    pub receiver_goal_fit: f64,
    pub current_shot: f64,
    pub shot_readiness: f64,
    pub consecutive_carries: i32,
    pub attracted_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ReleaseSupportGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub progress: f64,
    pub target_progress: f64,
    pub target_centrality: f64,
    pub pass_distance: f64,
    pub layer_gap: f64,
    pub release_maturity: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldOpportunityGoalInput {
    pub player_pos: (f64, f64),
    pub support_target: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub support_value: f64,
    pub hold_value: f64,
    pub current_shot: f64,
    pub shot_readiness: f64,
    pub immediate_best_score: f64,
    pub goal_age_ticks: i32,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldOpportunityGoalOutput {
    pub has_goal: bool,
    pub target_pos: (f64, f64),
    pub value: f64,
    pub confidence: f64,
    pub progress: f64,
    pub target_progress: f64,
    pub target_centrality: f64,
    pub pass_distance: f64,
    pub lateral_gap: f64,
    pub opportunity_window: f64,
    pub stale: f64,
}

pub fn iq_decision_noise(iq: f64) -> f64 {
    let value = iq.max(1.0);
    if value <= 100.0 {
        return ((100.0 - value) / 100.0).max(0.01);
    }
    (0.01 * (-(value - 100.0) / 35.0).exp()).max(0.003)
}

pub fn iq_temperature_factor(iq: f64, floor: f64, low_iq_range: f64, elite_discount: f64) -> f64 {
    let value = iq.max(1.0);
    let low_iq_noise = ((100.0 - value.min(100.0)) / 100.0).max(0.0);
    let mut factor = floor + low_iq_noise * low_iq_range;
    if value > 100.0 {
        let elite = 1.0 - (-(value - 100.0) / 35.0).exp();
        factor *= 1.0 - elite_discount.clamp(0.0, 0.75) * elite;
    }
    factor.max(floor * (1.0 - elite_discount.clamp(0.0, 0.75)))
}

pub fn goal_switch_cost(input: &GoalSwitchCostInput) -> f64 {
    let iq_adjustment = 0.78 + iq_decision_noise(input.iq) * 0.38;
    let pressure_factor = (1.0 - input.pressure_interrupt.clamp(0.0, 1.0)).max(0.15);
    (input.base
        * input.context_stability.max(0.0)
        * input.role_discipline.max(0.0)
        * pressure_factor
        * iq_adjustment)
        .max(0.0)
}

pub fn goal_selection_noise_from_gauss(
    input: &GoalSwitchCostInput,
    goal_noise_scale: f64,
    gaussian_output: f64,
) -> f64 {
    let base = goal_noise_scale.max(0.0);
    if base <= 0.0 {
        return 0.0;
    }
    let iq_instability = iq_decision_noise(input.iq);
    let pressure = input.pressure_interrupt.clamp(0.0, 1.0);
    let cap = base * (0.70 + 1.60 * iq_instability) * (1.0 + 0.50 * pressure);
    gaussian_output.clamp(-cap, cap)
}

pub fn select_goal_candidate_with_gaussians(
    values: &[f64],
    gaussians: &[f64],
    input: &GoalSwitchCostInput,
    goal_noise_scale: f64,
) -> Option<GoalCandidateChoiceOutput> {
    let mut best: Option<GoalCandidateChoiceOutput> = None;
    for (index, value) in values.iter().enumerate() {
        let gaussian = gaussians.get(index).copied().unwrap_or(0.0);
        let noise = goal_selection_noise_from_gauss(input, goal_noise_scale, gaussian);
        let noisy_value = *value + noise;
        let choice = GoalCandidateChoiceOutput {
            index,
            candidate_noise: noise,
            noisy_value,
        };
        if best
            .as_ref()
            .map(|current| choice.noisy_value > current.noisy_value)
            .unwrap_or(true)
        {
            best = Some(choice);
        }
    }
    best
}

pub fn select_goal_deterministic(
    current_goal: Option<&GoalInput<'_>>,
    candidate_goal: &GoalInput<'_>,
    context: &GoalSwitchCostInput,
) -> GoalSelectionOutput {
    if current_goal.is_none() {
        return GoalSelectionOutput {
            selected: "candidate",
            switched: true,
            switch_cost: 0.0,
            value_advantage: candidate_goal.value,
            noisy_value_advantage: candidate_goal.value,
            reason: "no_current_goal",
        };
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
    let advantage = candidate_goal.value - current.value;

    if current.goal_type == candidate_goal.goal_type
        && matches!(candidate_phase, Some("finish") | Some("release"))
        && candidate_phase != current_phase
    {
        return GoalSelectionOutput {
            selected: "candidate",
            switched: false,
            switch_cost: 0.0,
            value_advantage: advantage,
            noisy_value_advantage: advantage,
            reason: "current_goal_phase_updated",
        };
    }
    if current.goal_type == "cut_inside_to_shoot"
        && candidate_goal.goal_type == "cut_inside_to_shoot"
        && current_phase == Some("drive")
        && candidate_phase == Some("drive")
    {
        return GoalSelectionOutput {
            selected: "candidate",
            switched: false,
            switch_cost: 0.0,
            value_advantage: advantage,
            noisy_value_advantage: advantage,
            reason: "current_goal_drive_updated",
        };
    }
    if current.goal_type == "hold_for_opportunity"
        && candidate_goal.goal_type == "hold_for_opportunity"
        && current_phase == Some("scan")
        && candidate_phase == Some("scan")
    {
        return GoalSelectionOutput {
            selected: "candidate",
            switched: false,
            switch_cost: 0.0,
            value_advantage: advantage,
            noisy_value_advantage: advantage,
            reason: "current_goal_scan_updated",
        };
    }
    let switch_cost = goal_switch_cost(context);
    let noisy_advantage = advantage;
    if noisy_advantage > switch_cost {
        GoalSelectionOutput {
            selected: "candidate",
            switched: true,
            switch_cost,
            value_advantage: advantage,
            noisy_value_advantage: noisy_advantage,
            reason: "candidate_clears_switch_cost",
        }
    } else {
        GoalSelectionOutput {
            selected: "current",
            switched: false,
            switch_cost,
            value_advantage: advantage,
            noisy_value_advantage: noisy_advantage,
            reason: "current_goal_within_switch_cost",
        }
    }
}

fn action_name(action_code: u8) -> &'static str {
    match action_code {
        0 => "carry",
        1 => "pass",
        2 => "shoot",
        3 => "hold",
        4 => "clear",
        5 => "reorient",
        _ => "",
    }
}

fn build_on_ball_action_goal_type(candidate: &OnBallGenericCandidateInput) -> &'static str {
    match action_name(candidate.action_code) {
        "shoot" => "create_shot",
        "carry" => {
            if candidate.progress_gain > 0.015 {
                "progress_carry"
            } else {
                "protect_ball"
            }
        }
        "pass" => {
            if candidate.progress_gain < -0.015 {
                "recycle"
            } else if candidate.target_kind_space {
                "through_ball"
            } else if candidate.lateral_change.abs() > 0.28 {
                "switch_play"
            } else {
                "recycle"
            }
        }
        "hold" => "protect_ball",
        "clear" => "clear_danger",
        _ => "protect_ball",
    }
}

pub fn apply_generic_on_ball_goal_continuity(
    input: &OnBallGenericContinuityInput<'_>,
) -> Option<OnBallGenericContinuityOutput> {
    if input.candidates.is_empty() {
        return None;
    }
    let mut best_index = 0usize;
    let mut best_score = input.candidates[0].score;
    for (idx, candidate) in input.candidates.iter().enumerate().skip(1) {
        if candidate.score > best_score {
            best_index = idx;
            best_score = candidate.score;
        }
    }
    let best_candidate = input.candidates[best_index];
    let candidate_goal_type = build_on_ball_action_goal_type(&best_candidate);
    let candidate_target = best_candidate.target.unwrap_or((0.0, 0.0));
    let candidate_value = best_candidate.score.max(0.0);

    let current_storage;
    let current_goal_ref = if let Some(current) = input.current_goal {
        current_storage = GoalInput {
            goal_type: current.goal_type.unwrap_or(""),
            value: current.value,
            phase: Some("execute"),
        };
        Some(&current_storage)
    } else {
        None
    };
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
        iq: input.iq,
    };
    let selection = select_goal_deterministic(current_goal_ref, &candidate_goal, &context);
    let selected_is_candidate = selection.selected == "candidate";
    let selected_goal_type = if selected_is_candidate {
        candidate_goal_type.to_string()
    } else {
        input
            .current_goal
            .and_then(|goal| goal.goal_type)
            .unwrap_or(candidate_goal_type)
            .to_string()
    };
    let selected_action_code = if selected_is_candidate {
        best_candidate.action_code
    } else {
        input
            .current_goal
            .map(|goal| goal.action_code)
            .unwrap_or(best_candidate.action_code)
    };
    let selected_target = if selected_is_candidate {
        candidate_target
    } else {
        input
            .current_goal
            .map(|goal| goal.target_pos)
            .unwrap_or(candidate_target)
    };
    let selected_value = if selected_is_candidate {
        candidate_value
    } else {
        input
            .current_goal
            .map(|goal| goal.value)
            .unwrap_or(candidate_value)
    };

    let continuity_strength = input.goal_cut_inside_bias.max(0.0).clamp(0.0, 1.0);
    let target_action = action_name(selected_action_code);
    let mut biased_scores = Vec::with_capacity(input.candidates.len());
    let mut alignments = Vec::with_capacity(input.candidates.len());
    for candidate in input.candidates {
        let alignment =
            if continuity_strength > 0.0 && action_name(candidate.action_code) == target_action {
                let target_fit = candidate
                    .target
                    .map(|target| {
                        (1.0 - crate::physics::distance(target, selected_target) / 18.0).max(0.0)
                    })
                    .unwrap_or(1.0);
                continuity_strength * (0.35 + 0.65 * target_fit)
            } else {
                0.0
            };
        alignments.push(alignment.clamp(0.0, 1.0));
        biased_scores.push(candidate.score);
    }

    Some(OnBallGenericContinuityOutput {
        selected_goal_type,
        selected_action_code,
        selected_target,
        selected_value,
        candidate_goal_type: candidate_goal_type.to_string(),
        candidate_action_code: best_candidate.action_code,
        candidate_target,
        candidate_value,
        switched: selection.switched,
        switch_cost: selection.switch_cost,
        value_advantage: selection.value_advantage,
        reason: selection.reason.to_string(),
        biased_scores,
        alignments,
    })
}

pub fn apply_specialized_on_ball_bias(
    input: &OnBallSpecializedBiasInput<'_>,
) -> OnBallSpecializedBiasOutput {
    let mut biased_scores = Vec::with_capacity(input.candidates.len());
    let mut alignments = Vec::with_capacity(input.candidates.len());
    let mut opportunity_target_indices = Vec::new();
    for (idx, candidate) in input.candidates.iter().enumerate() {
        let mut affinity = 0.0;
        let action = action_name(candidate.action_code);
        match input.goal_type {
            "cut_inside_to_shoot" if action == "carry" => {
                let target_fit = candidate
                    .target
                    .map(|target| {
                        (1.0 - crate::physics::distance(target, input.goal_target) / 16.0).max(0.0)
                    })
                    .unwrap_or(0.0);
                if input.goal_phase == "drive" && target_fit > 0.0 {
                    affinity += input.goal_value * target_fit;
                }
            }
            "cut_inside_to_shoot" if action == "shoot" => {
                let xg_window = crate::physics::smoothstep(0.08, 0.18, candidate.xg);
                let second_touch_window =
                    crate::physics::smoothstep(1.0, 3.0, input.consecutive_carries.max(0) as f64);
                let finish_window = xg_window * second_touch_window;
                let readiness = candidate
                    .shot_readiness
                    .max(candidate.open_medium_window)
                    .max(candidate.clean_second_line_shot)
                    .max(finish_window);
                if readiness > 0.0 {
                    affinity += readiness
                        * if input.goal_phase == "finish" {
                            1.0
                        } else {
                            0.65
                        };
                }
            }
            "cut_inside_to_shoot" if input.goal_phase == "finish" && action == "reorient" => {
                let target_fit = candidate
                    .target
                    .map(|target| {
                        (1.0 - crate::physics::distance(target, input.goal_target) / 16.0).max(0.0)
                    })
                    .unwrap_or(0.0);
                let preparation_need = 1.0 - candidate.shot_readiness.clamp(0.0, 1.0);
                affinity += input.goal_value * target_fit * preparation_need;
            }
            "wide_byline_attack" if input.goal_phase == "drive" && action == "carry" => {
                let target_fit = candidate
                    .target
                    .map(|target| {
                        (1.0 - crate::physics::distance(target, input.goal_target) / 16.0).max(0.0)
                    })
                    .unwrap_or(0.0);
                if target_fit > 0.0 {
                    affinity += input.goal_value * target_fit;
                }
            }
            "wide_hold_for_overlap" => {
                if action == "hold" {
                    affinity += input.goal_value;
                } else if action == "pass" {
                    if let Some(target) = candidate.target {
                        let overlap_fit = (1.0
                            - crate::physics::distance(target, input.goal_target) / 16.0)
                            .max(0.0);
                        if overlap_fit > 0.0 {
                            affinity += overlap_fit * input.goal_value;
                        }
                    }
                }
            }
            "wide_byline_attack" if input.goal_phase == "release" && action == "pass" => {
                if let Some(target) = candidate.target {
                    let release_fit =
                        (1.0 - crate::physics::distance(target, input.goal_target) / 18.0).max(0.0);
                    if release_fit > 0.0 {
                        affinity += release_fit * input.goal_value;
                    }
                }
            }
            "through_ball_behind" if action == "pass" => {
                if let Some(target) = candidate.target {
                    let release_fit =
                        (1.0 - crate::physics::distance(target, input.goal_target) / 14.0).max(0.0);
                    if release_fit > 0.0 {
                        affinity += release_fit * input.goal_value;
                    }
                }
            }
            "release_pressure_with_layoff" => {
                if action == "hold" {
                    affinity += input.goal_value * 0.35;
                } else if action == "pass" {
                    if let Some(target) = candidate.target {
                        let layoff_fit = (1.0
                            - crate::physics::distance(target, input.goal_target) / 12.0)
                            .max(0.0);
                        if layoff_fit > 0.0 {
                            affinity += layoff_fit * input.goal_value;
                        }
                    }
                }
            }
            "release_to_arriving_support" => {
                if action == "hold" {
                    affinity += input.goal_value * 0.22;
                } else if action == "pass" {
                    if let Some(target) = candidate.target {
                        let support_fit = (1.0
                            - crate::physics::distance(target, input.goal_target) / 12.0)
                            .max(0.0);
                        if support_fit > 0.0 {
                            affinity += support_fit * input.goal_value;
                        }
                    }
                }
            }
            "hold_for_opportunity" => {
                if action == "hold" {
                    affinity += input.goal_value * 0.34;
                    opportunity_target_indices.push(idx);
                } else if action == "carry" {
                    if let Some(target) = candidate.target {
                        let stretch_fit = (1.0
                            - crate::physics::distance(target, input.goal_target) / 14.0)
                            .max(0.0);
                        if stretch_fit > 0.0 {
                            affinity += input.goal_value * 0.80 * stretch_fit;
                        }
                    }
                } else if action == "pass" {
                    if let Some(target) = candidate.target {
                        let support_fit = (1.0
                            - crate::physics::distance(target, input.goal_target) / 13.0)
                            .max(0.0);
                        if support_fit > 0.0 {
                            affinity += support_fit * input.goal_value;
                        }
                    }
                }
            }
            _ => {}
        }
        let alignment = affinity.clamp(0.0, 1.0);
        alignments.push(alignment);
        biased_scores.push(candidate.score + input.bias.max(0.0) * alignment);
    }
    OnBallSpecializedBiasOutput {
        biased_scores,
        alignments,
        opportunity_target_indices,
    }
}

pub fn evaluate_cut_inside_goal(input: &CutInsideGoalInput) -> CutInsideGoalOutput {
    let x = input.player_pos.0;
    let y = input.player_pos.1;
    let progress = if input.attacking_right {
        x / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - x) / input.pitch_length.max(1.0)
    };
    let width = (y - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let carry_plan = crate::physics::smoothstep(0.62, 0.82, progress)
        * crate::physics::smoothstep(0.36, 0.82, width)
        * crate::physics::smoothstep(0.035, 0.12, input.future_shot_gain)
        * (0.35 + 0.65 * crate::physics::smoothstep(0.02, 0.14, input.carry_to_shoot_window));
    let drive_staleness =
        crate::physics::smoothstep(2.0, 5.0, input.consecutive_carries.max(0) as f64).max(
            crate::physics::smoothstep(4.0, 9.0, input.goal_age_ticks.max(0) as f64),
        );
    let already_shootable = crate::physics::smoothstep(0.08, 0.16, input.current_shot)
        * crate::physics::smoothstep(0.20, 0.70, input.current_readiness);
    let finish_window = crate::physics::smoothstep(0.09, 0.18, input.current_shot)
        * (0.45 + 0.55 * crate::physics::smoothstep(0.12, 0.70, input.current_readiness));
    let stalled_drive = (input.consecutive_carries >= 3 || input.goal_age_ticks >= 6)
        && width > 0.58
        && input.current_shot < 0.045
        && finish_window < 0.12;
    let release_window =
        crate::physics::smoothstep(2.0, 4.0, input.consecutive_carries.max(0) as f64).max(
            crate::physics::smoothstep(4.0, 8.0, input.goal_age_ticks.max(0) as f64),
        ) * crate::physics::smoothstep(0.58, 0.82, width)
            * (1.0 - crate::physics::smoothstep(0.035, 0.070, input.current_shot));
    let value = 0.0_f64
        .max(carry_plan * (1.0 - 0.72 * already_shootable) * (1.0 - 0.58 * drive_staleness))
        .max(finish_window * 0.55)
        .max(release_window * 0.20);
    if value <= 0.0 {
        return CutInsideGoalOutput {
            has_goal: false,
            target_pos: input.player_pos,
            value: 0.0,
            confidence: 0.0,
            phase_code: 0,
            progress,
            width,
            finish_window,
            drive_staleness,
        };
    }
    let phase_code = if finish_window > 0.35 {
        2
    } else if stalled_drive {
        1
    } else {
        0
    };
    let target_pos = if let Some(target) = input.best_carry_target {
        target
    } else {
        let goal_x = if input.attacking_right {
            input.pitch_length
        } else {
            0.0
        };
        let mut target_x = x + if input.attacking_right { 6.0 } else { -6.0 };
        let target_y = y + (input.pitch_width / 2.0 - y) * 0.55;
        if input.attacking_right {
            target_x = (goal_x - 14.0).min((x + 1.0).max(target_x));
        } else {
            target_x = (goal_x + 14.0).max((x - 1.0).min(target_x));
        }
        (target_x, target_y)
    };
    CutInsideGoalOutput {
        has_goal: true,
        target_pos,
        value,
        confidence: input
            .carry_to_shoot_window
            .max(input.wide_second_line_carry_window)
            .max(input.future_shot_gain),
        phase_code,
        progress,
        width,
        finish_window,
        drive_staleness,
    }
}

pub fn evaluate_drive_byline_goal(input: &DriveBylineGoalInput) -> BylineGoalOutput {
    let origin_progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let origin_width =
        (input.player_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let target_progress = if input.attacking_right {
        input.carry_target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.carry_target.0) / input.pitch_length.max(1.0)
    };
    let target_width =
        (input.carry_target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let delivery_support = input.delivery_support.clamp(0.0, 1.0);
    let window = crate::physics::smoothstep(0.58, 0.82, origin_progress)
        * crate::physics::smoothstep(0.44, 0.84, origin_width)
        * crate::physics::smoothstep(0.72, 0.92, target_progress)
        * crate::physics::smoothstep(0.50, 0.90, target_width)
        * crate::physics::smoothstep(0.012, 0.090, input.progress_gain)
        * crate::physics::smoothstep(0.020, 0.260, input.byline_carry_window)
        * crate::physics::smoothstep(0.34, 0.82, input.path_feasibility)
        * (0.72 + 0.52 * delivery_support);
    let value = (window
        * (0.120
            + input.carry_score.max(0.0) * 1.40
            + input.space_manipulation * 0.050
            + input.byline_carry_window * 0.300
            + delivery_support * 1.450))
        .max(0.0);
    if value <= 0.0 {
        return BylineGoalOutput {
            has_goal: false,
            target_pos: input.carry_target,
            value: 0.0,
            confidence: 0.0,
            phase_code: 0,
            origin_progress,
            origin_width,
            target_progress,
            target_width_or_centrality: target_width,
        };
    }
    BylineGoalOutput {
        has_goal: true,
        target_pos: input.carry_target,
        value,
        confidence: value
            .max(input.byline_carry_window)
            .max(input.path_feasibility),
        phase_code: 0,
        origin_progress,
        origin_width,
        target_progress,
        target_width_or_centrality: target_width,
    }
}

pub fn evaluate_byline_delivery_goal(input: &BylineDeliveryGoalInput) -> BylineGoalOutput {
    let origin_progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let origin_width =
        (input.player_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let window = crate::physics::smoothstep(0.78, 0.94, origin_progress)
        * crate::physics::smoothstep(0.44, 0.82, origin_width)
        * crate::physics::smoothstep(0.78, 0.96, input.target_progress)
        * crate::physics::smoothstep(0.30, 0.88, input.centrality)
        * crate::physics::smoothstep(0.22, 0.72, input.high_threat_space).max(
            crate::physics::smoothstep(0.22, 0.72, input.final_third_combination),
        )
        * crate::physics::smoothstep(0.10, 0.46, input.success_prob)
        * (1.0 - crate::physics::smoothstep(0.52, 0.92, input.receiver_pressure))
        * (1.0 - crate::physics::smoothstep(0.46, 0.90, input.lane_risk));
    let threat = input.high_threat_space.max(input.final_third_combination);
    let value = (window * (0.090 + input.pass_score.max(0.0) * 1.45 + threat * 0.070)).max(0.0);
    if value <= 0.0 {
        return BylineGoalOutput {
            has_goal: false,
            target_pos: input.delivery_target,
            value: 0.0,
            confidence: 0.0,
            phase_code: 1,
            origin_progress,
            origin_width,
            target_progress: input.target_progress,
            target_width_or_centrality: input.centrality,
        };
    }
    BylineGoalOutput {
        has_goal: true,
        target_pos: input.delivery_target,
        value,
        confidence: value
            .max(input.high_threat_space)
            .max(input.final_third_combination)
            .max(input.success_prob),
        phase_code: 1,
        origin_progress,
        origin_width,
        target_progress: input.target_progress,
        target_width_or_centrality: input.centrality,
    }
}

pub fn evaluate_through_ball_goal(input: &ThroughBallGoalInput) -> ThroughBallGoalOutput {
    if !input.target_kind_space {
        return ThroughBallGoalOutput {
            has_goal: false,
            target_pos: input.pass_target,
            value: 0.0,
            confidence: 0.0,
            origin_progress: 0.0,
        };
    }
    let origin_progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let window = crate::physics::smoothstep(0.42, 0.76, origin_progress)
        * crate::physics::smoothstep(0.66, 0.92, input.target_progress)
        * crate::physics::smoothstep(0.34, 0.88, input.centrality)
        * crate::physics::smoothstep(0.040, 0.155, input.progress_gain)
        * crate::physics::smoothstep(0.08, 0.58, input.high_threat_space)
        * crate::physics::smoothstep(0.16, 0.58, input.success_prob)
        * (1.0 - crate::physics::smoothstep(0.46, 0.88, input.receiver_pressure))
        * (1.0 - crate::physics::smoothstep(0.34, 0.78, input.lane_risk));
    let value = (window
        * (0.080 + input.pass_score.max(0.0) * 1.45 + input.high_threat_space * 0.060))
        .max(0.0);
    if value <= 0.0 {
        return ThroughBallGoalOutput {
            has_goal: false,
            target_pos: input.pass_target,
            value: 0.0,
            confidence: 0.0,
            origin_progress,
        };
    }
    ThroughBallGoalOutput {
        has_goal: true,
        target_pos: input.pass_target,
        value,
        confidence: value.max(input.high_threat_space).max(input.success_prob),
        origin_progress,
    }
}

pub fn evaluate_wide_hold_overlap_goal(
    input: &WideHoldOverlapGoalInput,
) -> WideHoldOverlapGoalOutput {
    let progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let width =
        (input.player_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let target_progress = if input.attacking_right {
        input.overlap_target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.overlap_target.0) / input.pitch_length.max(1.0)
    };
    let target_width = (input.overlap_target.1 - input.pitch_width / 2.0).abs()
        / (input.pitch_width / 2.0).max(1.0);
    let forward_gap = (input.overlap_target.0 - input.player_pos.0)
        * if input.attacking_right { 1.0 } else { -1.0 };
    let lateral_gap = (input.overlap_target.1 - input.player_pos.1).abs();
    let same_lane = 1.0 - (lateral_gap / (input.pitch_width * 0.28).max(1.0)).min(1.0);
    let window = crate::physics::smoothstep(0.62, 0.84, progress)
        * crate::physics::smoothstep(0.42, 0.82, width)
        * crate::physics::smoothstep(0.00, 0.12, target_progress - progress)
        * (1.0 - crate::physics::smoothstep(0.24, 0.52, forward_gap / input.pitch_length.max(1.0)))
        * crate::physics::smoothstep(0.42, 0.86, target_width)
        * (0.35 + 0.65 * same_lane)
        * crate::physics::smoothstep(0.04, 0.20, input.overlap_value);
    let interrupt = crate::physics::smoothstep(0.12, 0.30, input.immediate_best_score);
    let value = (window * (1.0 - interrupt)).max(0.0);
    if value <= 0.0 {
        return WideHoldOverlapGoalOutput {
            has_goal: false,
            target_pos: input.player_pos,
            value: 0.0,
            confidence: 0.0,
            progress,
            width,
            target_progress,
            target_width,
            forward_gap,
            same_lane,
        };
    }
    WideHoldOverlapGoalOutput {
        has_goal: true,
        target_pos: input.player_pos,
        value,
        confidence: value.max(input.overlap_value),
        progress,
        width,
        target_progress,
        target_width,
        forward_gap,
        same_lane,
    }
}

pub fn evaluate_arc_arrival_goal(input: &ArcArrivalGoalInput) -> ArcArrivalGoalOutput {
    let ball_progress = if input.attacking_right {
        input.ball_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.ball_pos.0) / input.pitch_length.max(1.0)
    };
    let ball_width =
        (input.ball_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let anchor_progress = if input.attacking_right {
        input.anchor_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.anchor_pos.0) / input.pitch_length.max(1.0)
    };
    let base_progress = if input.attacking_right {
        input.base_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.base_pos.0) / input.pitch_length.max(1.0)
    };
    let anchor_width =
        (input.anchor_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let player_to_anchor = crate::physics::distance(input.player_pos, input.anchor_pos);
    let arc_x = input.pitch_length * if input.attacking_right { 0.80 } else { 0.20 };
    let arc_y = input.pitch_width / 2.0;
    let target_pos = (
        input.anchor_pos.0 * 0.45 + arc_x * 0.55,
        input.anchor_pos.1 * 0.45 + arc_y * 0.55,
    );
    let target_dist = crate::physics::distance(input.player_pos, target_pos);
    let value = crate::physics::smoothstep(0.70, 0.86, ball_progress)
        * crate::physics::smoothstep(0.28, 0.64, ball_width)
        * crate::physics::smoothstep(0.56, 0.78, anchor_progress)
        * (1.0 - 0.92 * crate::physics::smoothstep(0.70, 0.84, anchor_progress))
        * crate::physics::smoothstep(0.34, 0.56, base_progress)
        * (1.0 - crate::physics::smoothstep(0.62, 0.76, base_progress))
        * (1.0 - crate::physics::smoothstep(0.34, 0.68, anchor_width))
        * (1.0 - crate::physics::smoothstep(28.0, 46.0, target_dist))
        * (0.65 + 0.35 * (1.0 - crate::physics::smoothstep(0.0, 28.0, player_to_anchor)));
    ArcArrivalGoalOutput {
        has_goal: value > 0.0,
        target_pos,
        value: value.max(0.0),
        confidence: value.max(0.0),
        ball_progress,
        ball_width,
        anchor_progress,
        base_progress,
        anchor_width,
        target_dist,
    }
}

pub fn evaluate_attack_far_post_goal(input: &AttackFarPostGoalInput) -> AttackFarPostGoalOutput {
    let ball_progress = if input.attacking_right {
        input.ball_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.ball_pos.0) / input.pitch_length.max(1.0)
    };
    let ball_side =
        (input.ball_pos.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0).max(1.0);
    let ball_width = ball_side.abs();
    let player_progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let anchor_progress = if input.attacking_right {
        input.anchor_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.anchor_pos.0) / input.pitch_length.max(1.0)
    };
    let player_side =
        (input.player_pos.1 - input.pitch_width / 2.0) / (input.pitch_width / 2.0).max(1.0);
    let weak_side = (-player_side * ball_side).clamp(0.0, 1.0);
    let goal_x = if input.attacking_right {
        input.pitch_length
    } else {
        0.0
    };
    let far_post_x = goal_x - if input.attacking_right { 8.5 } else { -8.5 };
    let weak_post_y = if ball_side >= 0.0 {
        (input.pitch_width - input.goal_width) / 2.0
    } else {
        (input.pitch_width + input.goal_width) / 2.0
    };
    let far_post_y = weak_post_y + (input.pitch_width / 2.0 - weak_post_y) * 0.12;
    let target_pos = (far_post_x, far_post_y);
    let target_dist = crate::physics::distance(input.player_pos, target_pos);
    let value = crate::physics::smoothstep(0.72, 0.90, ball_progress)
        * crate::physics::smoothstep(0.34, 0.72, ball_width)
        * crate::physics::smoothstep(0.52, 0.82, player_progress.max(anchor_progress))
        * crate::physics::smoothstep(0.08, 0.30, weak_side)
        * (1.0 - crate::physics::smoothstep(18.0, 46.0, target_dist));
    AttackFarPostGoalOutput {
        has_goal: value > 0.0,
        target_pos,
        value: value.max(0.0),
        confidence: value.max(0.0),
        ball_progress,
        ball_width,
        weak_side,
        player_progress,
        anchor_progress,
        target_dist,
    }
}

pub fn build_off_ball_attack_goal(
    input: &OffBallAttackGoalBuildInput,
) -> OffBallAttackGoalBuildOutput {
    let second_line = input.second_line_support;
    let inside = input.inside_support;
    let support_angle = input.support_angle_value;
    let layoff = input.layoff_window;
    let candidate_progress = input.candidate_progress;
    let candidate_width = input.candidate_width;
    let box_arrival = crate::physics::smoothstep(0.76, 0.92, candidate_progress)
        * crate::physics::smoothstep(0.18, 0.70, 1.0 - candidate_width)
        * (0.55 + 0.45 * second_line.max(inside).max(support_angle));
    let goal_type = if box_arrival > 0.18 {
        "attack_box"
    } else if second_line > 0.12 {
        "support_second_line"
    } else if inside > 0.16 {
        "drop_between_lines"
    } else if support_angle > 0.18 || layoff > 0.10 {
        "support_carrier"
    } else if candidate_progress > 0.76 {
        "run_behind"
    } else if candidate_width > 0.62 && candidate_progress > 0.58 {
        "hold_width"
    } else {
        "recycle_support"
    };
    OffBallAttackGoalBuildOutput {
        goal_type,
        target_pos: input.target_pos,
        value: input.value.max(0.0),
        confidence: input.value.clamp(0.0, 1.0),
        box_arrival,
        second_line_support: second_line,
        inside_support: inside,
        support_angle_value: support_angle,
        layoff_window: layoff,
        candidate_progress,
        candidate_width,
    }
}

pub fn build_defensive_goal<'a>(
    input: &DefensiveGoalBuildInput<'a>,
) -> DefensiveGoalBuildOutput<'a> {
    let mut goal_type = match input.action_type {
        "close_down" => "defend_close_down",
        "approach" | "tackle" => "defend_press",
        "pursuit" => "defend_pursuit",
        "mark_runner" => "defend_mark_runner",
        "block_lane" => "defend_cover_lane",
        "hold_position" => "defend_recover_shape",
        _ => "defend_recover_shape",
    };
    if matches!(input.action_type, "block_lane" | "hold_position") && input.threat > 0.58 {
        goal_type = "defend_protect_box";
    }
    DefensiveGoalBuildOutput {
        goal_type,
        target_pos: input.target_pos,
        value: input.value.max(0.0),
        confidence: input.value.clamp(0.0, 1.0),
        action_type: input.action_type,
        pressure: input.pressure,
        threat: input.threat,
    }
}

pub fn evaluate_layoff_goal(input: &LayoffGoalInput) -> LayoffGoalOutput {
    let progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let target_progress = if input.attacking_right {
        input.layoff_target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.layoff_target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality = 1.0
        - ((input.layoff_target.1 - input.pitch_width / 2.0).abs()
            / (input.pitch_width / 2.0).max(1.0))
        .min(1.0);
    let pass_distance = crate::physics::distance(input.player_pos, input.layoff_target);
    let backward_depth = (input.player_pos.0 - input.layoff_target.0)
        * if input.attacking_right { 1.0 } else { -1.0 };
    let window = crate::physics::smoothstep(0.66, 0.88, progress)
        * crate::physics::smoothstep(0.18, 0.70, input.attracted_pressure)
        * crate::physics::smoothstep(4.0, 14.0, pass_distance)
        * (1.0 - crate::physics::smoothstep(24.0, 36.0, pass_distance))
        * crate::physics::smoothstep(-3.0, 9.0, backward_depth)
        * (1.0 - crate::physics::smoothstep(0.24, 0.48, (progress - target_progress).abs()))
        * crate::physics::smoothstep(0.32, 0.82, target_centrality)
        * crate::physics::smoothstep(0.035, 0.16, input.layoff_value);
    let interrupt = crate::physics::smoothstep(0.16, 0.34, input.immediate_best_score);
    let value = (window * (1.0 - interrupt)).max(0.0);
    if value <= 0.0 {
        return LayoffGoalOutput {
            has_goal: false,
            target_pos: input.layoff_target,
            value: 0.0,
            confidence: 0.0,
            progress,
            target_progress,
            target_centrality,
            pass_distance,
            backward_depth,
        };
    }
    LayoffGoalOutput {
        has_goal: true,
        target_pos: input.layoff_target,
        value,
        confidence: value.max(input.layoff_value).max(input.attracted_pressure),
        progress,
        target_progress,
        target_centrality,
        pass_distance,
        backward_depth,
    }
}

pub fn evaluate_release_support_goal(input: &ReleaseSupportGoalInput) -> ReleaseSupportGoalOutput {
    let progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let target_progress = if input.attacking_right {
        input.support_target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.support_target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality = 1.0
        - ((input.support_target.1 - input.pitch_width / 2.0).abs()
            / (input.pitch_width / 2.0).max(1.0))
        .min(1.0);
    let pass_distance = crate::physics::distance(input.player_pos, input.support_target);
    let layer_gap = (progress - target_progress).abs();
    let no_clear_shot = (1.0 - crate::physics::smoothstep(0.080, 0.155, input.current_shot))
        * (1.0 - crate::physics::smoothstep(0.18, 0.56, input.shot_readiness));
    let release_maturity =
        crate::physics::smoothstep(1.0, 3.0, input.consecutive_carries.max(0) as f64).max(
            crate::physics::smoothstep(0.18, 0.62, input.attracted_pressure.clamp(0.0, 1.0)) * 0.72,
        );
    let window = crate::physics::smoothstep(0.62, 0.88, progress)
        * crate::physics::smoothstep(0.58, 0.84, target_progress)
        * (1.0 - crate::physics::smoothstep(0.86, 0.96, target_progress))
        * crate::physics::smoothstep(0.44, 0.86, target_centrality)
        * crate::physics::smoothstep(5.0, 14.0, pass_distance)
        * (1.0 - crate::physics::smoothstep(30.0, 44.0, pass_distance))
        * (1.0 - crate::physics::smoothstep(0.28, 0.44, layer_gap))
        * crate::physics::smoothstep(0.12, 0.58, input.receiver_goal_fit)
        * crate::physics::smoothstep(0.050, 0.220, input.support_value)
        * no_clear_shot
        * (0.74 + 0.48 * release_maturity);
    let value = (window
        * (0.11 + 1.18 * input.support_value.max(0.0))
        * (0.88 + 0.64 * input.receiver_goal_fit.clamp(0.0, 1.0)))
    .max(0.0);
    if value <= 0.0 {
        return ReleaseSupportGoalOutput {
            has_goal: false,
            target_pos: input.support_target,
            value: 0.0,
            confidence: 0.0,
            progress,
            target_progress,
            target_centrality,
            pass_distance,
            layer_gap,
            release_maturity,
        };
    }
    ReleaseSupportGoalOutput {
        has_goal: true,
        target_pos: input.support_target,
        value,
        confidence: value.max(input.receiver_goal_fit).max(input.support_value),
        progress,
        target_progress,
        target_centrality,
        pass_distance,
        layer_gap,
        release_maturity,
    }
}

pub fn evaluate_hold_opportunity_goal(
    input: &HoldOpportunityGoalInput,
) -> HoldOpportunityGoalOutput {
    let progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let target_progress = if input.attacking_right {
        input.support_target.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.support_target.0) / input.pitch_length.max(1.0)
    };
    let target_centrality = 1.0
        - ((input.support_target.1 - input.pitch_width / 2.0).abs()
            / (input.pitch_width / 2.0).max(1.0))
        .min(1.0);
    let pass_distance = crate::physics::distance(input.player_pos, input.support_target);
    let lateral_gap =
        (input.player_pos.1 - input.support_target.1).abs() / (input.pitch_width / 2.0).max(1.0);
    let opportunity_window = input.support_value.max(input.hold_value).max(0.0);
    let no_clear_shot = (1.0 - crate::physics::smoothstep(0.075, 0.145, input.current_shot))
        * (1.0 - crate::physics::smoothstep(0.14, 0.52, input.shot_readiness));
    let support_window = crate::physics::smoothstep(0.42, 0.88, progress)
        * crate::physics::smoothstep(5.0, 14.0, pass_distance)
        * (1.0 - crate::physics::smoothstep(26.0, 38.0, pass_distance))
        * crate::physics::smoothstep(0.42, 0.84, target_progress)
        * (1.0 - crate::physics::smoothstep(0.86, 0.96, target_progress))
        * crate::physics::smoothstep(0.28, 0.86, target_centrality)
        * crate::physics::smoothstep(0.06, 0.44, lateral_gap)
        * crate::physics::smoothstep(0.030, 0.120, opportunity_window)
        * no_clear_shot;
    let interrupt = crate::physics::smoothstep(0.14, 0.32, input.immediate_best_score);
    let stale = crate::physics::smoothstep(5.0, 9.0, input.goal_age_ticks.max(0) as f64);
    let value = (support_window * (1.0 - interrupt) * (1.0 - 0.55 * stale)).max(0.0);
    if value <= 0.0 {
        return HoldOpportunityGoalOutput {
            has_goal: false,
            target_pos: input.support_target,
            value: 0.0,
            confidence: 0.0,
            progress,
            target_progress,
            target_centrality,
            pass_distance,
            lateral_gap,
            opportunity_window,
            stale,
        };
    }
    HoldOpportunityGoalOutput {
        has_goal: true,
        target_pos: input.support_target,
        value,
        confidence: value.max(opportunity_window),
        progress,
        target_progress,
        target_centrality,
        pass_distance,
        lateral_gap,
        opportunity_window,
        stale,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pressure_lowers_switch_cost() {
        let stable = goal_switch_cost(&GoalSwitchCostInput {
            base: 0.04,
            context_stability: 1.0,
            role_discipline: 1.0,
            pressure_interrupt: 0.0,
            iq: 80.0,
        });
        let pressured = goal_switch_cost(&GoalSwitchCostInput {
            pressure_interrupt: 0.8,
            ..GoalSwitchCostInput {
                base: 0.04,
                context_stability: 1.0,
                role_discipline: 1.0,
                pressure_interrupt: 0.0,
                iq: 80.0,
            }
        });
        assert!(pressured < stable);
    }

    #[test]
    fn defensive_plan_requires_a_clear_value_advantage_to_switch() {
        let current = GoalInput {
            goal_type: "defend_mark_runner",
            value: 0.42,
            phase: Some("defend"),
        };
        let context = GoalSwitchCostInput {
            base: 0.04,
            context_stability: 1.0,
            role_discipline: 1.0,
            pressure_interrupt: 0.0,
            iq: 85.0,
        };
        let close_alternative = GoalInput {
            goal_type: "defend_press",
            value: 0.43,
            phase: Some("defend"),
        };
        let better_alternative = GoalInput {
            value: 0.52,
            ..close_alternative
        };

        let retained = select_goal_deterministic(Some(&current), &close_alternative, &context);
        assert_eq!(retained.selected, "current");
        assert!(!retained.switched);

        let released = select_goal_deterministic(Some(&current), &better_alternative, &context);
        assert_eq!(released.selected, "candidate");
        assert!(released.switched);
    }

    #[test]
    fn hold_opportunity_requires_a_distinct_support_target() {
        let output = evaluate_hold_opportunity_goal(&HoldOpportunityGoalInput {
            player_pos: (72.0, 34.0),
            support_target: (72.0, 34.0),
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
            support_value: 0.92,
            hold_value: 0.95,
            current_shot: 0.0,
            shot_readiness: 0.0,
            immediate_best_score: 0.0,
            goal_age_ticks: 0,
        });

        assert!(
            !output.has_goal,
            "an opportunity task must wait for a reachable support line, not its own location"
        );
        assert_eq!(output.target_pos, (72.0, 34.0));
    }

    #[test]
    fn specialized_goal_produces_normalized_alignment_not_unbounded_action_value() {
        let candidates = [
            OnBallSpecializedBiasCandidateInput {
                score: 0.42,
                action_code: 0,
                target: Some((92.0, 10.0)),
                carry_to_shoot_window: 0.0,
                wide_second_line_carry_window: 0.0,
                future_shot_gain: 0.0,
                byline_carry_window: 1.0,
                xg: 0.0,
                shot_readiness: 0.0,
                open_medium_window: 0.0,
                clean_second_line_shot: 0.0,
                space_manipulation: 0.0,
                pressure_draw: 0.0,
            },
            OnBallSpecializedBiasCandidateInput {
                score: 0.46,
                action_code: 3,
                target: Some((82.0, 34.0)),
                carry_to_shoot_window: 0.0,
                wide_second_line_carry_window: 0.0,
                future_shot_gain: 0.0,
                byline_carry_window: 0.0,
                xg: 0.0,
                shot_readiness: 0.0,
                open_medium_window: 0.0,
                clean_second_line_shot: 0.0,
                space_manipulation: 0.0,
                pressure_draw: 0.0,
            },
        ];
        let output = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
            candidates: &candidates,
            goal_type: "wide_byline_attack",
            goal_phase: "drive",
            goal_target: (92.0, 10.0),
            goal_value: 1.0,
            bias: 0.0,
            consecutive_carries: 0,
        });

        assert_eq!(output.alignments, vec![1.0, 0.0]);
        assert_eq!(output.biased_scores, vec![0.42, 0.46]);
    }

    #[test]
    fn specialized_goal_alignment_does_not_reprice_successor_value_metadata() {
        let candidate = OnBallSpecializedBiasCandidateInput {
            score: 0.42,
            action_code: 0,
            target: Some((92.0, 10.0)),
            carry_to_shoot_window: 0.0,
            wide_second_line_carry_window: 0.0,
            future_shot_gain: 0.0,
            byline_carry_window: 0.0,
            xg: 0.0,
            shot_readiness: 0.0,
            open_medium_window: 0.0,
            clean_second_line_shot: 0.0,
            space_manipulation: 0.0,
            pressure_draw: 0.0,
        };
        let metadata_rich = OnBallSpecializedBiasCandidateInput {
            carry_to_shoot_window: 1.0,
            wide_second_line_carry_window: 1.0,
            future_shot_gain: 1.0,
            byline_carry_window: 1.0,
            space_manipulation: 1.0,
            pressure_draw: 1.0,
            ..candidate
        };

        for (goal_type, goal_phase) in [
            ("cut_inside_to_shoot", "drive"),
            ("wide_byline_attack", "drive"),
            ("hold_for_opportunity", "scan"),
        ] {
            let candidates = [candidate, metadata_rich];
            let output = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
                candidates: &candidates,
                goal_type,
                goal_phase,
                goal_target: (92.0, 10.0),
                goal_value: 1.0,
                bias: 0.0,
                consecutive_carries: 0,
            });

            assert_eq!(
                output.alignments[0], output.alignments[1],
                "{goal_type} must use successor metadata to form the goal, not repay it as policy"
            );
        }
    }

    #[test]
    fn cut_inside_finish_uses_reorientation_only_while_the_body_is_unprepared() {
        let reorient = OnBallSpecializedBiasCandidateInput {
            score: 0.04,
            action_code: 5,
            target: Some((105.0, 34.0)),
            carry_to_shoot_window: 0.0,
            wide_second_line_carry_window: 0.0,
            future_shot_gain: 0.0,
            byline_carry_window: 0.0,
            xg: 0.0,
            shot_readiness: 0.20,
            open_medium_window: 0.0,
            clean_second_line_shot: 0.0,
            space_manipulation: 0.0,
            pressure_draw: 0.0,
        };
        let prepared = OnBallSpecializedBiasCandidateInput {
            shot_readiness: 0.90,
            ..reorient
        };

        let unprepared = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
            candidates: &[reorient],
            goal_type: "cut_inside_to_shoot",
            goal_phase: "finish",
            goal_target: (105.0, 34.0),
            goal_value: 0.60,
            bias: 0.0,
            consecutive_carries: 0,
        });
        let prepared = apply_specialized_on_ball_bias(&OnBallSpecializedBiasInput {
            candidates: &[prepared],
            goal_type: "cut_inside_to_shoot",
            goal_phase: "finish",
            goal_target: (105.0, 34.0),
            goal_value: 0.60,
            bias: 0.0,
            consecutive_carries: 0,
        });

        assert!(unprepared.alignments[0] > prepared.alignments[0]);
        assert!(unprepared.alignments[0] > 0.40);
        assert!(prepared.alignments[0] < 0.10);
    }
}
