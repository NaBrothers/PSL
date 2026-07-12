use crate::goal::iq_temperature_factor;

#[derive(Clone, Copy, Debug)]
pub struct SoftmaxSelectionOutput {
    pub index: usize,
    pub temperature: f64,
    pub total_weight: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct IqNoiseScoreInput {
    pub score: f64,
    pub iq: f64,
    pub iq_noise_scale: f64,
    pub gaussian: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct IqNoiseScoreOutput {
    pub score: f64,
    pub noise_scale: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct OnBallSelectionCandidateInput {
    pub score: f64,
    pub action_code: u8,
    pub target_kind_space: bool,
    pub success_prob: f64,
    pub receiver_pressure: f64,
    pub high_threat_space: f64,
}

pub fn apply_iq_noise_score(input: &IqNoiseScoreInput) -> IqNoiseScoreOutput {
    let noise_scale = crate::goal::iq_decision_noise(input.iq) * input.iq_noise_scale;
    IqNoiseScoreOutput {
        score: input.score * (1.0 + input.gaussian * noise_scale),
        noise_scale,
    }
}

#[derive(Clone, Debug)]
pub struct OnBallSelectionInput<'a> {
    pub candidates: &'a [OnBallSelectionCandidateInput],
    pub current_goal_hold_for_opportunity: bool,
    pub iq: f64,
    pub score_noises: &'a [f64],
    pub roll: f64,
    pub fallback_index: usize,
}

#[derive(Clone, Debug)]
pub struct OnBallSelectionOutput {
    pub index: usize,
    pub adjusted_scores: Vec<f64>,
    pub noisy_scores: Vec<f64>,
    pub used_roll: bool,
    pub used_random_choice: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct SupportOpportunityPassInput {
    pub score: f64,
    pub receiver_goal_fit: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct SupportOpportunityCarryInput {
    pub score: f64,
    pub future_shot_gain: f64,
    pub carry_to_shoot_window: f64,
    pub effective_gain: f64,
}

#[derive(Clone, Debug)]
pub struct SupportOpportunityInput<'a> {
    pub passes: &'a [SupportOpportunityPassInput],
    pub carries: &'a [SupportOpportunityCarryInput],
}

#[derive(Clone, Debug)]
pub struct SupportOpportunityOutput {
    pub support_pressure: f64,
    pub adjusted_scores: Vec<f64>,
    pub costs: Vec<f64>,
}

#[derive(Clone, Copy, Debug)]
pub struct OverlapPassInput {
    pub score: f64,
    pub target: (f64, f64),
    pub receiver_pressure: f64,
}

#[derive(Clone, Debug)]
pub struct OverlapSelectionInput<'a> {
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub passes: &'a [OverlapPassInput],
}

#[derive(Clone, Copy, Debug)]
pub struct OverlapSelectionOutput {
    pub index: Option<usize>,
    pub value: f64,
    pub target: (f64, f64),
}

#[derive(Clone, Copy, Debug)]
pub struct LayoffPassInput {
    pub score: f64,
    pub target: (f64, f64),
    pub receiver_pressure: f64,
}

#[derive(Clone, Debug)]
pub struct LayoffSelectionInput<'a> {
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub passes: &'a [LayoffPassInput],
    pub opponents: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct LayoffSelectionOutput {
    pub index: Option<usize>,
    pub value: f64,
    pub target: (f64, f64),
    pub attracted_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ArrivingSupportPassInput {
    pub score: f64,
    pub target: (f64, f64),
    pub receiver_goal_fit: f64,
    pub second_line_arrival_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_support_value: f64,
}

#[derive(Clone, Debug)]
pub struct ArrivingSupportSelectionInput<'a> {
    pub player_pos: (f64, f64),
    pub passes: &'a [ArrivingSupportPassInput],
    pub opponents: &'a [(f64, f64)],
}

#[derive(Clone, Copy, Debug)]
pub struct ArrivingSupportSelectionOutput {
    pub index: Option<usize>,
    pub fit: f64,
    pub target: (f64, f64),
    pub support_value: f64,
    pub receiver_goal_fit: f64,
    pub attracted_pressure: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldSupportPassInput {
    pub score: f64,
    pub target: (f64, f64),
    pub layoff_support_value: f64,
    pub short_combination_value: f64,
    pub second_line_cutback_value: f64,
    pub layoff_retention_value: f64,
    pub receiver_goal_fit: f64,
    pub second_line_arrival_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldSupportCarryInput {
    pub carry_to_shoot_window: f64,
    pub wide_second_line_carry_window: f64,
    pub future_shot_gain: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldSupportHoldInput {
    pub opportunity_wait: f64,
    pub opportunity_wait_value: f64,
    pub no_clear_release: f64,
}

#[derive(Clone, Debug)]
pub struct HoldSupportSelectionInput<'a> {
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub passes: &'a [HoldSupportPassInput],
    pub carries: &'a [HoldSupportCarryInput],
    pub holds: &'a [HoldSupportHoldInput],
    pub current_opportunity_goal: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct HoldSupportSelectionOutput {
    pub has_support: bool,
    pub target: (f64, f64),
    pub fit: f64,
    pub support_value: f64,
    pub hold_support: f64,
    pub no_clear_release: f64,
    pub clear_carry_plan: f64,
    pub support_plan_quality: f64,
    pub carry_interrupt: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct BylineSupportTeammateInput {
    pub index: usize,
    pub pos: (f64, f64),
    pub target: (f64, f64),
    pub anchor: (f64, f64),
    pub is_goalkeeper: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct BylineCarryInput {
    pub score: f64,
    pub target: (f64, f64),
    pub byline_carry_window: f64,
}

#[derive(Clone, Debug)]
pub struct BylineCarrySelectionInput<'a> {
    pub player_index: usize,
    pub player_pos: (f64, f64),
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub teammates: &'a [BylineSupportTeammateInput],
    pub carries: &'a [BylineCarryInput],
}

#[derive(Clone, Copy, Debug)]
pub struct BylineCarrySelectionOutput {
    pub delivery_support: f64,
    pub index: Option<usize>,
    pub value: f64,
    pub score: f64,
    pub target: (f64, f64),
}

fn smoothstep(edge0: f64, edge1: f64, value: f64) -> f64 {
    let t = ((value - edge0) / (edge1 - edge0).max(1e-6)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn on_ball_release_confidence_score(
    candidate: OnBallSelectionCandidateInput,
    hold_score: Option<f64>,
    current_goal_hold_for_opportunity: bool,
) -> f64 {
    let Some(hold_score) = hold_score else {
        return candidate.score;
    };
    if hold_score <= 0.0 || candidate.action_code == 3 || candidate.action_code == 4 {
        return candidate.score;
    }
    let advantage = candidate.score - hold_score;
    let confidence = smoothstep(0.006, 0.060, advantage);
    let action_floor = if candidate.action_code == 2 {
        0.76
    } else {
        0.82
    };
    let mut multiplier = action_floor + (1.0 - action_floor) * confidence;
    if current_goal_hold_for_opportunity
        && candidate.action_code == 1
        && candidate.target_kind_space
    {
        let release_safety = candidate.success_prob * (1.0 - candidate.receiver_pressure.min(1.0));
        let unsafe_high_threat = smoothstep(0.55, 0.90, candidate.high_threat_space)
            * (1.0 - smoothstep(0.28, 0.48, release_safety));
        multiplier *= 1.0 - 0.22 * unsafe_high_threat;
    }
    candidate.score * multiplier
}

pub fn select_on_ball_candidate(input: &OnBallSelectionInput<'_>) -> Option<OnBallSelectionOutput> {
    if input.candidates.is_empty() {
        return None;
    }

    let hold_score = input
        .candidates
        .iter()
        .filter(|candidate| candidate.action_code == 3)
        .map(|candidate| candidate.score)
        .reduce(f64::max);
    let adjusted_scores: Vec<f64> = input
        .candidates
        .iter()
        .map(|candidate| {
            on_ball_release_confidence_score(
                *candidate,
                hold_score,
                input.current_goal_hold_for_opportunity,
            )
        })
        .collect();
    let noisy_scores: Vec<f64> = adjusted_scores
        .iter()
        .enumerate()
        .map(|(idx, score)| score * (1.0 + input.score_noises.get(idx).copied().unwrap_or(0.0)))
        .collect();

    if noisy_scores.len() == 1 {
        return Some(OnBallSelectionOutput {
            index: 0,
            adjusted_scores,
            noisy_scores,
            used_roll: false,
            used_random_choice: false,
        });
    }

    let max_score = noisy_scores
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    if max_score < 0.001 {
        return Some(OnBallSelectionOutput {
            index: input.fallback_index % noisy_scores.len(),
            adjusted_scores,
            noisy_scores,
            used_roll: false,
            used_random_choice: true,
        });
    }

    let selection = softmax_select_index(&noisy_scores, input.iq, input.roll, 0)?;
    Some(OnBallSelectionOutput {
        index: selection.index.min(noisy_scores.len() - 1),
        adjusted_scores,
        noisy_scores,
        used_roll: selection.total_weight >= 1e-10,
        used_random_choice: false,
    })
}

pub fn apply_support_opportunity_cost(
    input: &SupportOpportunityInput<'_>,
) -> SupportOpportunityOutput {
    let mut support_pressure: f64 = 0.0;
    for pass in input.passes {
        let second_line_value = pass.second_line_arrival_value
            + pass.second_line_cutback_value
            + pass.layoff_support_value * 0.45;
        if pass.receiver_goal_fit < 0.30 && second_line_value < 0.012 {
            continue;
        }
        let pass_quality = smoothstep(0.055, 0.240, pass.score.max(0.0));
        let support_quality = smoothstep(0.24, 0.70, pass.receiver_goal_fit).max(smoothstep(
            0.010,
            0.080,
            second_line_value,
        ));
        support_pressure = support_pressure.max(pass_quality * support_quality);
    }

    let mut adjusted_scores = Vec::with_capacity(input.carries.len());
    let mut costs = Vec::with_capacity(input.carries.len());
    for carry in input.carries {
        if support_pressure <= 0.0 {
            adjusted_scores.push(carry.score);
            costs.push(0.0);
            continue;
        }
        let carry_payoff = smoothstep(0.10, 0.26, carry.future_shot_gain)
            .max(smoothstep(0.14, 0.34, carry.carry_to_shoot_window))
            .max(smoothstep(0.12, 0.28, carry.effective_gain));
        let cost = support_pressure * (1.0 - 0.68 * carry_payoff) * 0.075;
        adjusted_scores.push((carry.score - cost).max(0.0));
        costs.push(cost);
    }
    SupportOpportunityOutput {
        support_pressure,
        adjusted_scores,
        costs,
    }
}

pub fn select_best_overlap(input: &OverlapSelectionInput<'_>) -> OverlapSelectionOutput {
    let forward_dir = if input.attacking_right { 1.0 } else { -1.0 };
    let carrier_width =
        (input.player_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
    let mut best_index = None;
    let mut best_value = f64::NEG_INFINITY;
    let mut best_target = input.player_pos;
    for (idx, pass) in input.passes.iter().enumerate() {
        let target_progress = if input.attacking_right {
            pass.target.0 / input.pitch_length
        } else {
            (input.pitch_length - pass.target.0) / input.pitch_length
        };
        let target_width =
            (pass.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0);
        let forward_gap = (pass.target.0 - input.player_pos.0) * forward_dir;
        let overlap_value = pass.score.max(0.0)
            * (forward_gap / 14.0).clamp(0.0, 1.0)
            * ((target_width - carrier_width + 0.25) / 0.45).clamp(0.0, 1.0)
            * (1.0 - pass.receiver_pressure.min(1.0))
            * ((target_progress - 0.62) / 0.22).clamp(0.0, 1.0);
        if best_index.is_none() || overlap_value > best_value {
            best_index = Some(idx);
            best_value = overlap_value;
            best_target = pass.target;
        }
    }
    OverlapSelectionOutput {
        index: best_index,
        value: if best_index.is_some() {
            best_value
        } else {
            0.0
        },
        target: best_target,
    }
}

pub fn select_best_layoff(input: &LayoffSelectionInput<'_>) -> LayoffSelectionOutput {
    let mut attracted_pressure: f64 = 0.0;
    for opp in input.opponents {
        let d = crate::physics::distance(input.player_pos, *opp);
        if d < 11.0 {
            attracted_pressure += 1.0 - d / 11.0;
        }
    }
    attracted_pressure = (attracted_pressure * 0.42).min(1.0);

    let mut best_index = None;
    let mut best_value = f64::NEG_INFINITY;
    let mut best_target = input.player_pos;
    for (idx, pass) in input.passes.iter().enumerate() {
        let pass_distance = crate::physics::distance(input.player_pos, pass.target);
        let target_progress = if input.attacking_right {
            pass.target.0 / input.pitch_length
        } else {
            (input.pitch_length - pass.target.0) / input.pitch_length
        };
        let target_centrality = 1.0
            - ((pass.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                .min(1.0);
        let backward_depth =
            (input.player_pos.0 - pass.target.0) * if input.attacking_right { 1.0 } else { -1.0 };
        let player_progress = if input.attacking_right {
            input.player_pos.0 / input.pitch_length
        } else {
            (input.pitch_length - input.player_pos.0) / input.pitch_length
        };
        let layoff_value = pass.score.max(0.0)
            * ((18.0 - (pass_distance - 12.0).abs()) / 18.0).clamp(0.0, 1.0)
            * ((target_centrality - 0.20) / 0.65).clamp(0.0, 1.0)
            * ((0.28 - (target_progress - player_progress).abs()) / 0.28).clamp(0.0, 1.0)
            * (1.0 - pass.receiver_pressure.min(1.0))
            * ((backward_depth + 4.0) / 16.0).clamp(0.0, 1.0);
        if best_index.is_none() || layoff_value > best_value {
            best_index = Some(idx);
            best_value = layoff_value;
            best_target = pass.target;
        }
    }
    LayoffSelectionOutput {
        index: best_index,
        value: if best_index.is_some() {
            best_value
        } else {
            0.0
        },
        target: best_target,
        attracted_pressure,
    }
}

pub fn select_best_arriving_support(
    input: &ArrivingSupportSelectionInput<'_>,
) -> ArrivingSupportSelectionOutput {
    let mut best_index = None;
    let mut best_fit = f64::NEG_INFINITY;
    let mut best_target = input.player_pos;
    let mut best_support_value = 0.0;
    let mut best_receiver_goal_fit = 0.0;
    for (idx, pass) in input.passes.iter().enumerate() {
        let support_value = pass
            .second_line_arrival_value
            .max(pass.second_line_cutback_value)
            .max(pass.layoff_support_value)
            .max(pass.score.max(0.0) * 0.55);
        let fit = pass.receiver_goal_fit * (support_value + pass.score.max(0.0) * 0.35);
        if best_index.is_none() || fit > best_fit {
            best_index = Some(idx);
            best_fit = fit;
            best_target = pass.target;
            best_support_value = support_value;
            best_receiver_goal_fit = pass.receiver_goal_fit;
        }
    }
    let mut attracted_pressure: f64 = 0.0;
    for opp in input.opponents {
        let d = crate::physics::distance(input.player_pos, *opp);
        if d < 11.0 {
            attracted_pressure += 1.0 - d / 11.0;
        }
    }
    attracted_pressure = (attracted_pressure * 0.42).min(1.0);
    ArrivingSupportSelectionOutput {
        index: best_index,
        fit: if best_index.is_some() { best_fit } else { 0.0 },
        target: best_target,
        support_value: best_support_value,
        receiver_goal_fit: best_receiver_goal_fit,
        attracted_pressure,
    }
}

pub fn select_hold_support(input: &HoldSupportSelectionInput<'_>) -> HoldSupportSelectionOutput {
    let mut best_fit = f64::NEG_INFINITY;
    let mut best_target = input.player_pos;
    let mut best_support_value = 0.0;
    for pass in input.passes {
        let support_value = pass
            .layoff_support_value
            .max(pass.short_combination_value)
            .max(pass.second_line_cutback_value)
            .max(pass.layoff_retention_value)
            .max(pass.score.max(0.0) * 0.45);
        let pass_distance = crate::physics::distance(input.player_pos, pass.target);
        let target_progress = if input.attacking_right {
            pass.target.0 / input.pitch_length
        } else {
            (input.pitch_length - pass.target.0) / input.pitch_length
        };
        let target_centrality = 1.0
            - ((pass.target.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                .min(1.0);
        let fit = support_value
            * ((18.0 - (pass_distance - 12.0).abs()) / 18.0).clamp(0.0, 1.0)
            * ((target_centrality - 0.18) / 0.70).clamp(0.0, 1.0)
            * ((0.90 - target_progress) / 0.26).clamp(0.0, 1.0);
        if fit > best_fit {
            best_fit = fit;
            best_target = pass.target;
            best_support_value = support_value;
        }
    }

    let mut hold_support: f64 = 0.0;
    let mut no_clear_release: f64 = 0.0;
    for hold in input.holds {
        hold_support = hold_support
            .max(hold.opportunity_wait)
            .max(hold.opportunity_wait_value);
        no_clear_release = no_clear_release.max(hold.no_clear_release);
    }
    if best_fit == f64::NEG_INFINITY && (hold_support > 0.0 || no_clear_release > 0.0) {
        let value = hold_support.max(no_clear_release);
        best_fit = value * 0.065;
        best_target = input.player_pos;
        best_support_value = value * 0.10;
    }

    let mut clear_carry_plan: f64 = 0.0;
    for carry in input.carries {
        clear_carry_plan = clear_carry_plan
            .max(carry.carry_to_shoot_window)
            .max(carry.wide_second_line_carry_window)
            .max(carry.future_shot_gain);
    }
    let mut support_plan_quality: f64 = 0.0;
    for pass in input.passes {
        support_plan_quality = support_plan_quality
            .max(smoothstep(0.28, 0.70, pass.receiver_goal_fit))
            .max(smoothstep(
                0.012,
                0.080,
                pass.second_line_arrival_value + pass.second_line_cutback_value,
            ));
    }
    let carry_interrupt =
        smoothstep(0.070, 0.185, clear_carry_plan) * (1.0 - 0.55 * support_plan_quality);

    HoldSupportSelectionOutput {
        has_support: best_fit != f64::NEG_INFINITY
            && (carry_interrupt < 0.72 || input.current_opportunity_goal),
        target: best_target,
        fit: if best_fit == f64::NEG_INFINITY {
            0.0
        } else {
            best_fit
        },
        support_value: best_support_value,
        hold_support,
        no_clear_release,
        clear_carry_plan,
        support_plan_quality,
        carry_interrupt,
    }
}

pub fn select_best_byline_carry(
    input: &BylineCarrySelectionInput<'_>,
) -> BylineCarrySelectionOutput {
    let carrier_progress = if input.attacking_right {
        input.player_pos.0 / input.pitch_length.max(1.0)
    } else {
        (input.pitch_length - input.player_pos.0) / input.pitch_length.max(1.0)
    };
    let carrier_width =
        (input.player_pos.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0).max(1.0);
    let mut delivery_support: f64 = 0.0;
    if carrier_progress >= 0.58 && carrier_width >= 0.38 {
        for teammate in input.teammates {
            if teammate.index == input.player_index || teammate.is_goalkeeper {
                continue;
            }
            for point in [teammate.pos, teammate.target, teammate.anchor] {
                let progress = if input.attacking_right {
                    point.0 / input.pitch_length.max(1.0)
                } else {
                    (input.pitch_length - point.0) / input.pitch_length.max(1.0)
                };
                let centrality = 1.0
                    - ((point.1 - input.pitch_width / 2.0).abs() / (input.pitch_width / 2.0))
                        .min(1.0);
                let depth_gap =
                    (point.0 - input.player_pos.0) * if input.attacking_right { 1.0 } else { -1.0 };
                let weak_side = if (point.1 - input.pitch_width / 2.0)
                    * (input.player_pos.1 - input.pitch_width / 2.0)
                    < 0.0
                {
                    1.0
                } else {
                    0.0
                };
                let box_target = smoothstep(0.78, 0.94, progress)
                    * smoothstep(0.45, 0.92, centrality)
                    * (0.60 + 0.25 * weak_side);
                let cutback_target = smoothstep(0.62, 0.84, progress)
                    * smoothstep(0.52, 0.92, centrality)
                    * smoothstep(-12.0, 6.0, depth_gap)
                    * (1.0 - smoothstep(18.0, 34.0, depth_gap.abs()));
                delivery_support = delivery_support.max(box_target).max(cutback_target);
            }
        }
        delivery_support = delivery_support.clamp(0.0, 1.0);
    }

    let mut best_index = None;
    let mut best_value = f64::NEG_INFINITY;
    let mut best_score = 0.0;
    let mut best_target = input.player_pos;
    for (idx, carry) in input.carries.iter().enumerate() {
        if carry.byline_carry_window <= 0.025 {
            continue;
        }
        let value =
            carry.score * 0.35 + carry.byline_carry_window * (0.45 + 0.70 * delivery_support);
        if best_index.is_none() || value > best_value {
            best_index = Some(idx);
            best_value = value;
            best_score = carry.score;
            best_target = carry.target;
        }
    }
    BylineCarrySelectionOutput {
        delivery_support,
        index: best_index,
        value: if best_index.is_some() {
            best_value
        } else {
            0.0
        },
        score: best_score,
        target: best_target,
    }
}

pub fn softmax_select_index(
    scores: &[f64],
    iq: f64,
    roll: f64,
    fallback_index: usize,
) -> Option<SoftmaxSelectionOutput> {
    if scores.is_empty() {
        return None;
    }
    if scores.len() == 1 {
        return Some(SoftmaxSelectionOutput {
            index: 0,
            temperature: 0.0,
            total_weight: 1.0,
        });
    }

    let max_score = scores.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let min_score = scores.iter().copied().fold(f64::INFINITY, f64::min);

    if max_score < 0.001 {
        return Some(SoftmaxSelectionOutput {
            index: fallback_index % scores.len(),
            temperature: 0.0,
            total_weight: 1.0,
        });
    }

    let score_spread = (max_score - min_score).max(0.0);
    let temperature = ((0.0012 + score_spread * 0.10)
        * iq_temperature_factor(iq, 0.18, 0.62, 0.30))
    .clamp(0.0008, 0.018);
    let weights: Vec<f64> = scores
        .iter()
        .map(|score| ((score - max_score) / temperature).exp())
        .collect();
    let total_weight: f64 = weights.iter().sum();
    if total_weight < 1e-10 {
        return Some(SoftmaxSelectionOutput {
            index: 0,
            temperature,
            total_weight,
        });
    }

    let threshold = roll.clamp(0.0, 1.0) * total_weight;
    let mut cumulative = 0.0;
    for (idx, weight) in weights.iter().enumerate() {
        cumulative += weight;
        if threshold <= cumulative {
            return Some(SoftmaxSelectionOutput {
                index: idx,
                temperature,
                total_weight,
            });
        }
    }

    Some(SoftmaxSelectionOutput {
        index: scores.len() - 1,
        temperature,
        total_weight,
    })
}

pub fn softmax_select_index_with_temperature(
    scores: &[f64],
    temperature: f64,
    roll: f64,
    fallback_index: usize,
) -> Option<SoftmaxSelectionOutput> {
    if scores.is_empty() {
        return None;
    }
    if scores.len() == 1 {
        return Some(SoftmaxSelectionOutput {
            index: 0,
            temperature,
            total_weight: 1.0,
        });
    }
    let max_score = scores.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if max_score < 0.001 {
        return Some(SoftmaxSelectionOutput {
            index: fallback_index % scores.len(),
            temperature,
            total_weight: 1.0,
        });
    }
    let weights: Vec<f64> = scores
        .iter()
        .map(|score| ((score - max_score) / temperature.max(1e-9)).exp())
        .collect();
    let total_weight: f64 = weights.iter().sum();
    if total_weight < 1e-10 {
        return Some(SoftmaxSelectionOutput {
            index: 0,
            temperature,
            total_weight,
        });
    }
    let threshold = roll.clamp(0.0, 1.0) * total_weight;
    let mut cumulative = 0.0;
    for (idx, weight) in weights.iter().enumerate() {
        cumulative += weight;
        if threshold <= cumulative {
            return Some(SoftmaxSelectionOutput {
                index: idx,
                temperature,
                total_weight,
            });
        }
    }
    Some(SoftmaxSelectionOutput {
        index: scores.len() - 1,
        temperature,
        total_weight,
    })
}
