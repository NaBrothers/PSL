use crate::physics::{distance, smoothstep};

#[derive(Debug, Clone)]
pub struct GkSaveInput {
    pub gk_pos: (f64, f64),
    pub shot_target: (f64, f64),
    pub shot_origin: (f64, f64),
    pub gk_saving: f64,
    pub gk_positioning: f64,
    pub gk_reaction: f64,
    pub pitch_length: f64,
    pub gk_position_error_factor: f64,
    pub gk_reaction_delay_factor: f64,
    pub gk_save_base: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct GkSaveAttributes {
    pub gk_saving: f64,
    pub gk_positioning: f64,
    pub gk_reaction: f64,
    pub gk_position_error_factor: f64,
    pub gk_reaction_delay_factor: f64,
    pub gk_save_base: f64,
}

#[derive(Debug, Clone)]
pub struct GkRushInput {
    pub gk_pos: (f64, f64),
    pub attacker_pos: (f64, f64),
    pub gk_positioning: f64,
    pub iq: f64,
    pub gk_rush_distance: f64,
}

#[derive(Debug, Clone)]
pub struct GkDistributionInput {
    pub gk_y: f64,
    pub iq: f64,
    pub short_passing: f64,
    pub long_passing: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub decision_noise: f64,
    pub target_x_sample: f64,
    pub target_y_sample: f64,
}

#[derive(Debug, Clone)]
pub struct GkDistributionOutput {
    pub distribution_type: &'static str,
    pub target: (f64, f64),
}

#[derive(Debug, Clone)]
pub struct GkFallbackTargetInput {
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Debug, Clone)]
pub struct GkFallbackTargetOutput {
    pub target: (f64, f64),
}

pub fn compute_gk_save_probability(input: &GkSaveInput) -> f64 {
    compute_gk_save_probability_for_attributes(
        GkSaveAttributes {
            gk_saving: input.gk_saving,
            gk_positioning: input.gk_positioning,
            gk_reaction: input.gk_reaction,
            gk_position_error_factor: input.gk_position_error_factor,
            gk_reaction_delay_factor: input.gk_reaction_delay_factor,
            gk_save_base: input.gk_save_base,
        },
        input.gk_pos,
        input.shot_origin,
        input.shot_target,
        input.pitch_length,
    )
}

pub fn compute_gk_save_probability_for_attributes(
    attributes: GkSaveAttributes,
    gk_pos: (f64, f64),
    shot_origin: (f64, f64),
    shot_target: (f64, f64),
    pitch_length: f64,
) -> f64 {
    let position_error = (100.0 - attributes.gk_positioning) * attributes.gk_position_error_factor;
    let goal_x = if shot_target.0 >= pitch_length / 2.0 {
        pitch_length
    } else {
        0.0
    };
    let ideal_depth = if goal_x > 0.0 { goal_x - 4.5 } else { 4.5 };
    let lateral_dist = (gk_pos.1 - shot_target.1).abs();
    let depth_error = ((gk_pos.0 - ideal_depth).abs() - 2.0).max(0.0) * 0.35;
    let effective_dist = lateral_dist + depth_error + position_error;

    let reaction_factor = (1.0
        - (100.0 - attributes.gk_reaction) * attributes.gk_reaction_delay_factor)
        .clamp(0.3, 1.0);
    let saving_ability = attributes.gk_saving / 100.0;
    let reach_factor = (1.0 - effective_dist / 9.0).max(0.25);
    let shot_dist = distance(shot_origin, shot_target);
    let reaction_window = 0.52 + 0.48 * smoothstep(9.0, 30.0, shot_dist);
    let long_shot_read = 1.0 + 0.18 * smoothstep(24.0, 42.0, shot_dist);

    ((0.08
        + attributes.gk_save_base * 0.25
        + saving_ability * 0.18
        + reach_factor * 0.18
        + reaction_factor * 0.08
        + reaction_window * 0.10)
        * long_shot_read)
        .clamp(0.10, 0.90)
}

pub fn should_rush_out(input: &GkRushInput) -> bool {
    let dist_to_attacker = distance(input.gk_pos, input.attacker_pos);
    if dist_to_attacker > input.gk_rush_distance {
        return false;
    }
    let decision_quality = (input.gk_positioning * 0.6 + input.iq * 0.4) / 100.0;
    let rush_threshold = 0.3 + decision_quality * 0.4;
    let proximity_factor = (1.0 - dist_to_attacker / input.gk_rush_distance).max(0.0);
    proximity_factor > rush_threshold
}

pub fn choose_distribution(input: &GkDistributionInput) -> GkDistributionOutput {
    let short_score = input.short_passing / 100.0 + input.iq / 200.0;
    let long_score = input.long_passing / 100.0;
    if short_score > long_score + input.decision_noise {
        GkDistributionOutput {
            distribution_type: "short",
            target: (input.target_x_sample, input.gk_y + input.target_y_sample),
        }
    } else {
        GkDistributionOutput {
            distribution_type: "long",
            target: (input.target_x_sample, input.target_y_sample),
        }
    }
}

pub fn choose_fallback_target(input: &GkFallbackTargetInput) -> GkFallbackTargetOutput {
    GkFallbackTargetOutput {
        target: (
            input.pitch_length * if input.attacking_right { 0.55 } else { 0.45 },
            input.pitch_width / 2.0,
        ),
    }
}
