use crate::physics::{angle_to_goal, distance, interpolate, smoothstep};

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

#[derive(Clone, Copy, Debug)]
pub struct GkShapeAnchorInput {
    pub ball_pos: (f64, f64),
    pub base_pos: (f64, f64),
    pub attacking_right: bool,
    pub team_depth_scale: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct GkPositioningInput {
    pub ball_pos: (f64, f64),
    pub ball_confidence: f64,
    pub structure_anchor: (f64, f64),
    pub gk_positioning: f64,
    pub attacking_right: bool,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct GkPositioningOutput {
    pub target: (f64, f64),
    pub structure_target: (f64, f64),
    pub geometric_target: (f64, f64),
    pub threat: f64,
    pub shot_angle: f64,
    pub geometry_weight: f64,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct GkSaveContext {
    attributes: GkSaveAttributes,
    goalkeeper_x: f64,
    goalkeeper_y: f64,
    goal_x: f64,
    position_error: f64,
    depth_error: f64,
    reaction_factor: f64,
    saving_ability: f64,
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

fn goal_geometry(attacking_right: bool, pitch_length: f64, pitch_width: f64) -> (f64, f64, f64) {
    (
        if attacking_right { 0.0 } else { pitch_length },
        pitch_width / 2.0,
        if attacking_right { 1.0 } else { -1.0 },
    )
}

fn pitch_clamp(pos: (f64, f64), pitch_length: f64, pitch_width: f64) -> (f64, f64) {
    (
        pos.0.clamp(0.5, pitch_length - 0.5),
        pos.1.clamp(0.5, pitch_width - 0.5),
    )
}

pub fn goalkeeper_shape_anchor(input: &GkShapeAnchorInput) -> (f64, f64) {
    let (goal_x, goal_y, goal_direction) =
        goal_geometry(input.attacking_right, input.pitch_length, input.pitch_width);
    let base_depth = ((input.base_pos.0 - goal_x) * goal_direction).max(0.5);
    let ball_distance = distance((goal_x, goal_y), input.ball_pos);
    let structural_advance = smoothstep(22.0, input.pitch_length * 0.90, ball_distance)
        * (4.3 + 2.1 * input.team_depth_scale.clamp(0.5, 1.5));
    let depth = (base_depth + 1.8 + structural_advance).clamp(2.3, 11.5);
    let ball_side = (input.ball_pos.1 - goal_y) / (input.pitch_width / 2.0).max(1.0);
    let lateral_shift = ball_side * (0.35 + 0.11 * depth);
    pitch_clamp(
        (goal_x + goal_direction * depth, goal_y + lateral_shift),
        input.pitch_length,
        input.pitch_width,
    )
}

pub fn goalkeeper_positioning_target(input: &GkPositioningInput) -> GkPositioningOutput {
    let (goal_x, goal_y, goal_direction) =
        goal_geometry(input.attacking_right, input.pitch_length, input.pitch_width);
    let ball_vector = (input.ball_pos.0 - goal_x, input.ball_pos.1 - goal_y);
    let ball_distance = distance((goal_x, goal_y), input.ball_pos);
    let shot_angle = angle_to_goal(input.ball_pos, (goal_x, goal_y), 7.32);
    let threat = 1.0 - smoothstep(20.0, 75.0, ball_distance);
    let angle_factor = smoothstep(0.08, 0.45, shot_angle);
    let ideal_depth =
        (2.4 + threat * (2.7 + 2.0 * angle_factor)).min((ball_distance * 0.72).max(0.5));
    let ball_direction = if ball_distance > 1e-6 {
        (ball_vector.0 / ball_distance, ball_vector.1 / ball_distance)
    } else {
        (goal_direction, 0.0)
    };
    let geometric_target = pitch_clamp(
        (
            goal_x + ball_direction.0 * ideal_depth,
            goal_y + ball_direction.1 * ideal_depth,
        ),
        input.pitch_length,
        input.pitch_width,
    );
    let positioning_quality = smoothstep(15.0, 95.0, input.gk_positioning);
    let geometry_weight =
        input.ball_confidence.clamp(0.0, 1.0) * threat * (0.24 + 0.76 * positioning_quality);
    let target = interpolate(
        input.structure_anchor,
        geometric_target,
        geometry_weight.clamp(0.0, 1.0),
    );

    GkPositioningOutput {
        target,
        structure_target: input.structure_anchor,
        geometric_target,
        threat,
        shot_angle,
        geometry_weight,
    }
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
    let goal_x = if shot_target.0 >= pitch_length / 2.0 {
        pitch_length
    } else {
        0.0
    };
    let context = gk_save_context_for_goal(attributes, gk_pos, goal_x);
    compute_gk_save_probability_with_context(context, shot_origin, shot_target)
}

pub(crate) fn gk_save_context_for_goal(
    attributes: GkSaveAttributes,
    gk_pos: (f64, f64),
    goal_x: f64,
) -> GkSaveContext {
    let position_error = (100.0 - attributes.gk_positioning) * attributes.gk_position_error_factor;
    let ideal_depth = if goal_x > 0.0 { goal_x - 4.5 } else { 4.5 };
    let depth_error = ((gk_pos.0 - ideal_depth).abs() - 2.0).max(0.0) * 0.35;
    let reaction_factor = (1.0
        - (100.0 - attributes.gk_reaction) * attributes.gk_reaction_delay_factor)
        .clamp(0.3, 1.0);
    let saving_ability = attributes.gk_saving / 100.0;
    GkSaveContext {
        attributes,
        goalkeeper_x: gk_pos.0,
        goalkeeper_y: gk_pos.1,
        goal_x,
        position_error,
        depth_error,
        reaction_factor,
        saving_ability,
    }
}

pub(crate) fn compute_gk_save_probability_with_context(
    context: GkSaveContext,
    shot_origin: (f64, f64),
    shot_target: (f64, f64),
) -> f64 {
    let shot_dx = shot_target.0 - shot_origin.0;
    let goal_direction = (context.goal_x - shot_origin.0).signum();
    let goalkeeper_goalward_depth = (context.goalkeeper_x - shot_origin.0) * goal_direction;
    let shot_goalward_depth = shot_dx.abs().max(1e-9);
    let longitudinal_access = smoothstep(
        -0.15,
        (1.2 + 0.12 * shot_goalward_depth).min(3.0),
        goalkeeper_goalward_depth,
    ) * (1.0
        - smoothstep(
            shot_goalward_depth,
            shot_goalward_depth + 0.8,
            goalkeeper_goalward_depth,
        ));
    let lateral_dist = (context.goalkeeper_y - shot_target.1).abs();
    let effective_dist = lateral_dist + context.depth_error + context.position_error;
    let reach_factor = (1.0 - effective_dist / 9.0).max(0.25);
    let shot_dist = distance(shot_origin, shot_target);
    let reaction_window = 0.52 + 0.48 * smoothstep(9.0, 30.0, shot_dist);
    let long_shot_read = 1.0 + 0.18 * smoothstep(24.0, 42.0, shot_dist);

    (((0.08
        + context.attributes.gk_save_base * 0.25
        + context.saving_ability * 0.18
        + reach_factor * 0.18
        + context.reaction_factor * 0.08
        + reaction_window * 0.10)
        * long_shot_read)
        .clamp(0.10, 0.90)
        * longitudinal_access)
        .clamp(0.0, 0.90)
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

#[cfg(test)]
mod tests {
    use super::*;

    fn positioning_input() -> GkPositioningInput {
        GkPositioningInput {
            ball_pos: (20.0, 34.0),
            ball_confidence: 1.0,
            structure_anchor: (7.5, 34.0),
            gk_positioning: 90.0,
            attacking_right: true,
            pitch_length: 105.0,
            pitch_width: 68.0,
        }
    }

    #[test]
    fn shape_anchor_advances_with_team_structure_without_leaving_goal_coverage() {
        let near_ball = goalkeeper_shape_anchor(&GkShapeAnchorInput {
            ball_pos: (12.0, 34.0),
            base_pos: (0.5, 34.0),
            attacking_right: true,
            team_depth_scale: 0.82,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });
        let high_line_ball = goalkeeper_shape_anchor(&GkShapeAnchorInput {
            ball_pos: (86.0, 54.0),
            base_pos: (0.5, 34.0),
            attacking_right: true,
            team_depth_scale: 1.16,
            pitch_length: 105.0,
            pitch_width: 68.0,
        });

        assert!(
            high_line_ball.0 > near_ball.0 + 3.0,
            "the goalkeeper's structural anchor must advance with the team when the ball is far from its own goal: near={near_ball:?}, high_line={high_line_ball:?}"
        );
        assert!(
            high_line_ball.0 < 12.0 && high_line_ball.1 > 34.0,
            "the structural anchor remains a goal-coverage position while following the team's depth and ball side: {high_line_ball:?}"
        );
    }

    #[test]
    fn positioning_follows_visible_shooting_geometry_and_positioning_ability() {
        let centered = goalkeeper_positioning_target(&positioning_input());
        let wide_input = GkPositioningInput {
            ball_pos: (20.0, 58.0),
            ..positioning_input()
        };
        let wide = goalkeeper_positioning_target(&wide_input);
        let low_positioning = goalkeeper_positioning_target(&GkPositioningInput {
            gk_positioning: 10.0,
            ..wide_input
        });

        assert!(
            wide.target.1 > centered.target.1 + 1.0,
            "a wide visible attacker must pull the goalkeeper toward the near-post coverage line: centered={centered:?}, wide={wide:?}"
        );
        assert!(
            distance(wide.target, wide.geometric_target)
                < distance(low_positioning.target, low_positioning.geometric_target),
            "higher GK_Positioning must place the goalkeeper closer to the geometry-optimal target: high={wide:?}, low={low_positioning:?}"
        );
    }

    #[test]
    fn uncertain_ball_keeps_goalkeeper_at_the_structural_anchor() {
        let input = GkPositioningInput {
            ball_confidence: 0.0,
            structure_anchor: (8.0, 31.0),
            ..positioning_input()
        };
        let output = goalkeeper_positioning_target(&input);

        assert_eq!(output.target, input.structure_anchor);
        assert_eq!(output.geometry_weight, 0.0);
    }

    fn reference_save_probability(
        attributes: GkSaveAttributes,
        gk_pos: (f64, f64),
        shot_origin: (f64, f64),
        shot_target: (f64, f64),
        pitch_length: f64,
    ) -> f64 {
        let position_error =
            (100.0 - attributes.gk_positioning) * attributes.gk_position_error_factor;
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
        let goal_direction = (goal_x - shot_origin.0).signum();
        let goalkeeper_goalward_depth = (gk_pos.0 - shot_origin.0) * goal_direction;
        let shot_goalward_depth = (shot_target.0 - shot_origin.0).abs().max(1e-9);
        let longitudinal_access = smoothstep(
            -0.15,
            (1.2 + 0.12 * shot_goalward_depth).min(3.0),
            goalkeeper_goalward_depth,
        ) * (1.0
            - smoothstep(
                shot_goalward_depth,
                shot_goalward_depth + 0.8,
                goalkeeper_goalward_depth,
            ));

        (((0.08
            + attributes.gk_save_base * 0.25
            + saving_ability * 0.18
            + reach_factor * 0.18
            + reaction_factor * 0.08
            + reaction_window * 0.10)
            * long_shot_read)
            .clamp(0.10, 0.90)
            * longitudinal_access)
            .clamp(0.0, 0.90)
    }

    #[test]
    fn prepared_save_context_preserves_reference_probability() {
        let attributes = GkSaveAttributes {
            gk_saving: 86.0,
            gk_positioning: 78.0,
            gk_reaction: 83.0,
            gk_position_error_factor: 0.05,
            gk_reaction_delay_factor: 0.005,
            gk_save_base: 0.67,
        };
        for (gk_pos, shot_origin, shot_target) in [
            ((100.5, 34.0), (84.0, 29.0), (105.0, 31.6)),
            ((4.5, 30.5), (25.0, 41.0), (0.0, 36.4)),
            ((96.2, 38.8), (53.0, 18.0), (105.0, 34.0)),
        ] {
            let expected =
                reference_save_probability(attributes, gk_pos, shot_origin, shot_target, 105.0);
            let actual = compute_gk_save_probability_for_attributes(
                attributes,
                gk_pos,
                shot_origin,
                shot_target,
                105.0,
            );
            assert_eq!(actual.to_bits(), expected.to_bits());
        }
    }

    #[test]
    fn goalkeeper_behind_the_shooter_cannot_save_through_the_shooter() {
        let attributes = GkSaveAttributes {
            gk_saving: 90.0,
            gk_positioning: 90.0,
            gk_reaction: 90.0,
            gk_position_error_factor: 0.05,
            gk_reaction_delay_factor: 0.005,
            gk_save_base: 0.66,
        };
        let shot_origin = (103.8, 34.0);
        let shot_target = (105.0, 34.0);
        let behind = compute_gk_save_probability_for_attributes(
            attributes,
            (102.5, 34.0),
            shot_origin,
            shot_target,
            105.0,
        );
        let goal_side = compute_gk_save_probability_for_attributes(
            attributes,
            (104.4, 34.0),
            shot_origin,
            shot_target,
            105.0,
        );

        assert!(behind < 0.02);
        assert!(goal_side > behind + 0.30);
    }
}
