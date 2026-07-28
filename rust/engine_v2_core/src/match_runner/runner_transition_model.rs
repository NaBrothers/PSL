use super::*;

pub(super) fn projected_shot_possession_transition(
    action: &RunnerEvaluatedAction,
    holder_home: bool,
    unreleased_preparation_transition: PossessionTransition,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
    blocked_opposing_control_value: f64,
    saved_opposing_control_value: f64,
    off_target_opposing_control_value: f64,
) -> PossessionTransition {
    let RunnerHeldAction::Shoot {
        xg,
        on_target_prob,
        body_release_probability,
        release_probability,
        block_probability,
        block_point,
        ..
    } = action.action
    else {
        unreachable!();
    };
    let second_ball_inputs = RunnerSecondBallInputs::from_players(teammates, opponents, config);
    let model = action.shot_model.unwrap_or_else(|| {
        crate::execution_transition::ShotActionModel::new(
            origin,
            target,
            config.contest_radius,
            config.pitch_length,
            config.pitch_width,
        )
    });
    let transition = model.condition(
        body_release_probability,
        release_probability,
        block_probability,
    );
    let blocked_second_ball = second_ball_inputs.estimate(block_point, config);
    let unreleased_retained_control_value = unreleased_preparation_transition
        .retained_control_value
        .min(action.debug_current_pv)
        .clamp(0.0, 1.0);
    let blocked_retained_control_value = projected_blocked_second_ball_value(
        &second_ball_inputs,
        block_point,
        origin,
        holder_home,
        teammates,
        opponents,
        attacking_right,
        tick,
        shot_quality_cache,
        config,
    );
    let shot_transition = crate::action_value::shot_possession_transition_from_execution(
        &ShotPossessionTransitionInput {
            execution_probability: transition.body_release.success_probability,
            release_probability: transition.released_probability_given_body_release,
            block_probability: transition.blocked_probability_given_body_release,
            conditional_on_target_probability: on_target_prob,
            goal_probability: xg,
            blocked_second_ball,
            unreleased_retained_control_value,
            blocked_retained_control_value,
            blocked_opposing_control_value,
            saved_opposing_control_value,
            off_target_opposing_control_value,
        },
        transition,
    );
    replace_unreleased_shot_branch(
        shot_transition,
        transition.mass().unreleased,
        unreleased_retained_control_value,
        unreleased_preparation_transition,
    )
}

fn replace_unreleased_shot_branch(
    shot_transition: PossessionTransition,
    unreleased_probability: f64,
    old_unreleased_retained_value: f64,
    preparation_transition: PossessionTransition,
) -> PossessionTransition {
    let unreleased_probability = unreleased_probability.clamp(0.0, 1.0);
    let preparation_goal = preparation_transition.goal_probability.clamp(0.0, 1.0);
    let preparation_retained = preparation_transition
        .retained_control_probability
        .clamp(0.0, 1.0 - preparation_goal);
    let preparation_opposing = preparation_transition
        .opposing_control_probability
        .clamp(0.0, 1.0 - preparation_goal - preparation_retained);

    let retained_weight = (shot_transition.retained_control_probability
        * shot_transition.retained_control_value
        - unreleased_probability * old_unreleased_retained_value)
        .max(0.0)
        + unreleased_probability
            * preparation_retained
            * preparation_transition
                .retained_control_value
                .clamp(0.0, 1.0);
    let opposing_weight = shot_transition.opposing_control_probability
        * shot_transition.opposing_control_value
        + unreleased_probability
            * preparation_opposing
            * preparation_transition
                .opposing_control_value
                .clamp(0.0, 1.0);
    let retained_control_probability = (shot_transition.retained_control_probability
        - unreleased_probability
        + unreleased_probability * preparation_retained)
        .max(0.0);
    let opposing_control_probability = shot_transition.opposing_control_probability
        + unreleased_probability * preparation_opposing;

    PossessionTransition {
        goal_probability: shot_transition.goal_probability
            + unreleased_probability * preparation_goal,
        retained_control_probability,
        retained_control_value: if retained_control_probability > 1e-12 {
            retained_weight / retained_control_probability
        } else {
            0.0
        },
        opposing_control_probability,
        opposing_control_value: if opposing_control_probability > 1e-12 {
            opposing_weight / opposing_control_probability
        } else {
            0.0
        },
    }
}

#[cfg(test)]
#[allow(clippy::too_many_arguments)]
pub(super) fn projected_unreleased_shot_value(
    holder_idx: usize,
    holder_home: bool,
    current_control: PossessionControlState,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan: TeamPlanState,
    opponent_plan: TeamPlanState,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    shape_inputs: &RunnerProjectedExecutionShapeInputs,
    value_context: &mut RunnerProjectedControlValueContext,
    config: &RunnerRuntimeConfig,
) -> Option<f64> {
    let holder = teammates.get(holder_idx)?;
    Some(runner_projected_control_value_with_shape_inputs(
        holder_idx,
        origin,
        teammates,
        opponents,
        shape_inputs,
        true,
        holder_home,
        attacking_right,
        team_phase,
        opponent_phase,
        team_plan,
        opponent_plan,
        team_plan_signals,
        opponent_plan_signals,
        current_control,
        holder.facing_direction,
        1.0,
        0.0,
        1,
        0.0,
        Some(angle_between_points(origin, target)),
        tick,
        shot_quality_cache,
        value_context,
        config,
    ))
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_blocked_second_ball_value(
    second_ball_inputs: &RunnerSecondBallInputs,
    block_point: (f64, f64),
    shot_origin: (f64, f64),
    holder_home: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    config: &RunnerRuntimeConfig,
) -> f64 {
    let Some((controller_idx, _)) =
        second_ball_inputs.controller_index_and_access(true, block_point, config)
    else {
        return 0.0;
    };
    let Some(controller) = teammates.get(controller_idx) else {
        return 0.0;
    };
    let mut projected_controller = controller.clone();
    projected_controller.pos = block_point;
    projected_controller.target_pos = block_point;
    let arrival_heading = angle_between_points(shot_origin, block_point);
    projected_controller.facing_direction = arrival_heading;
    let control = runner_live_control_transition(
        PossessionControlState::default(),
        controller_idx,
        block_point,
        teammates,
        opponents,
        attacking_right,
        arrival_heading,
        0.0,
        1.0,
        1,
        distance(controller.pos, block_point),
        None,
        config.pitch_length,
        config.pitch_width,
    );
    runner_state_value(
        controller_idx,
        &projected_controller,
        holder_home,
        control,
        teammates,
        opponents,
        &[],
        attacking_right,
        tick + 1,
        shot_quality_cache,
        config,
    )
    .clamp(0.0, 1.0)
}

pub(super) fn apply_control_arrival_heading(
    outcomes: &mut ExecutionTransitionDistribution,
    action: RunnerHeldAction,
    target: (f64, f64),
    current_control: PossessionControlState,
) {
    let arrival_heading = match action {
        RunnerHeldAction::Reorient { .. } => outcomes
            .retained
            .first()
            .map(|branch| angle_between_points(branch.pos, target))
            .unwrap_or(current_control.facing_direction),
        RunnerHeldAction::Hold { .. } => current_control.facing_direction,
        _ => unreachable!(),
    };
    if let Some(branch) = outcomes.retained.first_mut() {
        branch.arrival_heading = arrival_heading;
    }
}

fn projected_carry_arrival_heading(origin: (f64, f64), destination: (f64, f64)) -> f64 {
    angle_between_points(origin, destination)
}

fn projected_carry_stays_in_play(
    origin: (f64, f64),
    destination: (f64, f64),
    config: &RunnerRuntimeConfig,
) -> bool {
    crate::physics::segment_pitch_boundary_crossing(
        origin,
        destination,
        config.pitch_length,
        config.pitch_width,
    )
    .is_none()
}

fn projected_carry_first_boundary_outcome(
    transitions: &[Option<crate::execution_transition::CarrySegmentTransition>],
    constrained: bool,
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> Option<RunnerControlledCarryBoundaryOutcome> {
    transitions.iter().flatten().find_map(|transition| {
        let branch = if constrained {
            transition.constrained
        } else {
            transition.unconstrained
        };
        crate::physics::segment_pitch_boundary_crossing(
            transition.origin,
            branch.end_pos,
            config.pitch_length,
            config.pitch_width,
        )
        .map(|crossing| {
            controlled_carry_boundary_outcome(
                crossing,
                attacking_right,
                config.pitch_length,
                config.pitch_width,
                config.goal_width,
            )
        })
    })
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_control_execution_outcomes_into(
    action: &RunnerEvaluatedAction,
    holder_idx: usize,
    origin: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    execution_opponents: &[ExecutionOpponent],
    defender_responses: &[DefenderActionInput],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    duration_ticks: i32,
    config: &RunnerRuntimeConfig,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    second_ball_inputs: &mut RunnerSecondBallInputs,
    outcomes: &mut ExecutionTransitionDistribution,
) -> Option<crate::execution_transition::ControlActionTransition> {
    outcomes.clear();
    let Some(holder) = teammates.get(holder_idx) else {
        outcomes.unresolved_probability = 1.0;
        return None;
    };
    let (holder_action, control_target, control_step_distance) = match action.action {
        RunnerHeldAction::Hold { opportunity_target } => (
            "hold",
            opportunity_target.unwrap_or(origin),
            config.carrier_speed * 0.34,
        ),
        RunnerHeldAction::Reorient { target } => ("reorient", target, config.carrier_speed * 0.24),
        RunnerHeldAction::Shoot { .. } => unreachable!(),
        _ => unreachable!(),
    };
    let contact = crate::control_contact_transition(
        origin,
        holder_action,
        control_target,
        control_step_distance,
        holder.dribbling,
        defender_responses,
        config.tackle_range,
    );
    let contact_second_ball_inputs =
        RunnerSecondBallInputs::from_players(teammates, opponents, config);
    let contact_loose_transition = crate::execution_transition::RectangularLooseBallTransition {
        center: origin,
        radius_x: 3.0,
        radius_y: 2.0,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
    };
    let opportunity_target = match action.action {
        RunnerHeldAction::Hold { opportunity_target } => opportunity_target,
        RunnerHeldAction::Reorient { .. } => None,
        _ => unreachable!(),
    };
    let control = hold_phase_plan(&HoldPhasePlanInput {
        transition: None,
        holder_pos: origin,
        velocity: holder.velocity,
        speed_ability: holder.speed.round() as i32,
        dribbling: holder.dribbling,
        attacking_right,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
        player_max_speed: config.player_max_speed,
        player_min_speed: config.player_min_speed,
        carry_error_divisor: config.carry_error_divisor,
        opponents: execution_opponents,
        opportunity_target,
        error_roll: 1.0,
        loose_x_roll: 0.5,
        loose_y_roll: 0.5,
    });
    let projected_teammates = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            teammates,
            opponents,
            control.new_pos,
            attacking_right,
            team_phase,
            team_plan_signals,
            Some((holder_idx, control.new_pos)),
            duration_ticks,
            config,
            shape_inputs,
            true,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            teammates,
            opponents,
            control.new_pos,
            attacking_right,
            team_phase,
            team_plan_signals,
            Some((holder_idx, control.new_pos)),
            duration_ticks,
            config,
            scratch,
        )
    };
    let projected_opponents = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            opponents,
            teammates,
            control.new_pos,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            shape_inputs,
            false,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            opponents,
            teammates,
            control.new_pos,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            scratch,
        )
    };
    second_ball_inputs.refresh_projected_positions(
        teammates,
        opponents,
        projected_teammates.slice(),
        projected_opponents.slice(),
    );
    let transition_mass = crate::execution_transition::control_execution_transition_mass(
        contact.retained_probability,
        contact.opposing_control_probability,
        contact.unresolved_probability,
        crate::execution_transition::BinaryExecutionTransition::from_success_probability(
            control.error_chance,
        ),
    );
    outcomes.retained.push(ExecutionTransitionBranch {
        probability: transition_mass.retained,
        controller_idx: Some(holder_idx),
        pos: control.new_pos,
        arrival_heading: 0.0,
        ownership_continuity: 1.0,
        contact_load: control.pressure.clamp(0.0, 1.0),
    });
    if let Some(controller_idx) = contact.contact.defender_index {
        let pos = opponents
            .get(controller_idx)
            .map(|defender| defender.pos)
            .unwrap_or(origin);
        outcomes.opposing.push(ExecutionTransitionBranch {
            probability: transition_mass.opposing_control,
            controller_idx: Some(controller_idx),
            pos,
            arrival_heading: angle_between_points(pos, origin),
            ownership_continuity: 0.0,
            contact_load: contact.contact.contact_quality,
        });
    } else {
        outcomes.unresolved_probability += transition_mass.opposing_control;
    }
    for loose_pos in contact_loose_transition.quadrature() {
        runner_append_projected_second_ball_outcomes(
            outcomes,
            transition_mass.contact_loose * 0.25,
            loose_pos,
            origin,
            &contact_second_ball_inputs,
            config,
        );
    }
    let loose_transition = crate::execution_transition::RectangularLooseBallTransition {
        center: control.new_pos,
        radius_x: 2.0,
        radius_y: 2.0,
        pitch_length: config.pitch_length,
        pitch_width: config.pitch_width,
    };
    for loose_pos in loose_transition.quadrature() {
        runner_append_projected_second_ball_outcomes(
            outcomes,
            transition_mass.technical_loose * 0.25,
            loose_pos,
            origin,
            second_ball_inputs,
            config,
        );
    }
    Some(crate::execution_transition::ControlActionTransition {
        contact,
        ..control.transition
    })
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_clearance_execution_outcomes_into(
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    duration_ticks: i32,
    config: &RunnerRuntimeConfig,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    outcomes: &mut ExecutionTransitionDistribution,
) -> Option<RunnerClearanceTransition> {
    outcomes.clear();
    let projected_teammates = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            teammates,
            opponents,
            target,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            duration_ticks,
            config,
            shape_inputs,
            true,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            teammates,
            opponents,
            target,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            duration_ticks,
            config,
            scratch,
        )
    };
    let projected_opponents = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            opponents,
            teammates,
            target,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            shape_inputs,
            false,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            opponents,
            teammates,
            target,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            scratch,
        )
    };
    let mut projected_home = [ClearancePlayerInput {
        index: 0,
        pos: (0.0, 0.0),
    }; RUNNER_TEAM_SIZE];
    let mut projected_away = projected_home;
    for (index, player) in teammates.iter().enumerate() {
        projected_home[index] = ClearancePlayerInput {
            index,
            pos: projected_position(projected_teammates.slice(), index, player.pos),
        };
    }
    for (index, player) in opponents.iter().enumerate() {
        projected_away[index] = ClearancePlayerInput {
            index,
            pos: projected_position(projected_opponents.slice(), index, player.pos),
        };
    }
    let arrival = clearance_arrival_plan(&ClearanceArrivalPlanInput {
        target_pos: target,
        passer_team_home: true,
        home_players: &projected_home[..teammates.len()],
        away_players: &projected_away[..opponents.len()],
    });
    let Some(controller_idx) = arrival.player_index else {
        outcomes.unresolved_probability = 1.0;
        return None;
    };
    let winner_distance = if arrival.winner_code == 0 {
        arrival.home_distance
    } else {
        arrival.away_distance
    };
    if winner_distance > config.contest_radius {
        outcomes.unresolved_probability = 1.0;
        return None;
    }
    let winner_pos = if arrival.passer_completed {
        projected_home[controller_idx].pos
    } else {
        projected_away[controller_idx].pos
    };
    if arrival.passer_completed {
        outcomes.retained.push(ExecutionTransitionBranch {
            probability: 1.0,
            controller_idx: Some(controller_idx),
            pos: winner_pos,
            arrival_heading: 0.0,
            ownership_continuity: 0.0,
            contact_load: 0.0,
        });
    } else {
        outcomes.opposing.push(ExecutionTransitionBranch {
            probability: 1.0,
            controller_idx: Some(controller_idx),
            pos: winner_pos,
            arrival_heading: 0.0,
            ownership_continuity: 0.0,
            contact_load: 0.0,
        });
    }
    Some(RunnerClearanceTransition {
        arrival,
        contact_pos: winner_pos,
    })
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_pass_execution_outcomes_into(
    action: &RunnerEvaluatedAction,
    holder_idx: usize,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    defender_responses: &[DefenderActionInput],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    _duration_ticks: i32,
    config: &RunnerRuntimeConfig,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    second_ball_inputs: &mut RunnerSecondBallInputs,
    outcomes: &mut ExecutionTransitionDistribution,
) -> Option<crate::execution_transition::PassActionTransition> {
    outcomes.clear();
    let RunnerHeldAction::Pass {
        technical_probability,
        is_long,
        ..
    } = action.action
    else {
        unreachable!();
    };
    let Some(holder) = teammates.get(holder_idx) else {
        outcomes.unresolved_probability = 1.0;
        return None;
    };
    let release = crate::pass_release_contact_transition(
        origin,
        target,
        config.carrier_speed * 0.18,
        holder.dribbling,
        defender_responses,
        config.tackle_range,
    );
    if release.opposing_control_probability > 1e-12 {
        if let Some(defender_idx) = release.contact.defender_index {
            let defender_pos = opponents
                .get(defender_idx)
                .map(|defender| defender.pos)
                .unwrap_or(origin);
            outcomes.opposing.push(ExecutionTransitionBranch {
                probability: release.opposing_control_probability,
                controller_idx: Some(defender_idx),
                pos: defender_pos,
                arrival_heading: angle_between_points(defender_pos, origin),
                ownership_continuity: 0.0,
                contact_load: release.contact.contact_quality,
            });
        } else {
            outcomes.unresolved_probability += release.opposing_control_probability;
        }
    }
    if release.unresolved_probability > 1e-12 {
        let projected_teammates = runner_projected_team_positions_into(
            teammates,
            opponents,
            origin,
            attacking_right,
            team_phase,
            team_plan_signals,
            Some((holder_idx, origin)),
            0,
            config,
            scratch,
        );
        let projected_opponents = runner_projected_team_positions_into(
            opponents,
            teammates,
            origin,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            0,
            config,
            scratch,
        );
        second_ball_inputs.refresh_projected_positions(
            teammates,
            opponents,
            projected_teammates.slice(),
            projected_opponents.slice(),
        );
        let loose_transition = crate::execution_transition::RectangularLooseBallTransition {
            center: origin,
            radius_x: 3.0,
            radius_y: 2.0,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
        };
        for loose_pos in loose_transition.quadrature() {
            runner_append_projected_second_ball_outcomes(
                outcomes,
                release.unresolved_probability * 0.25,
                loose_pos,
                origin,
                second_ball_inputs,
                config,
            );
        }
    }
    let passing = if is_long {
        holder.long_passing
    } else {
        holder.short_passing
    };
    let transition = crate::execution_transition::PassActionTransition {
        release,
        execution: crate::execution_transition::PassExecutionTransition::new(
            technical_probability,
            0.0,
        ),
        spatial: crate::execution_transition::PassSpatialTransition::new(
            origin,
            target,
            passing,
            config.pitch_length,
            config.pitch_width,
        ),
    };
    for (delivery_succeeded, delivery_probability) in [
        (true, transition.execution.delivery.success_probability),
        (false, transition.execution.delivery.failure_probability),
    ] {
        if delivery_probability <= 1e-12 {
            continue;
        }
        for sample in transition.spatial.quadrature(delivery_succeeded) {
            append_projected_pass_spatial_outcome(
                action,
                holder_idx,
                origin,
                sample.target,
                delivery_succeeded,
                release.released_probability * delivery_probability * 0.25,
                teammates,
                opponents,
                attacking_right,
                team_phase,
                opponent_phase,
                team_plan_signals,
                opponent_plan_signals,
                config,
                scratch,
                shape_inputs,
                second_ball_inputs,
                outcomes,
            );
        }
    }
    Some(transition)
}

#[allow(clippy::too_many_arguments)]
fn append_projected_pass_spatial_outcome(
    action: &RunnerEvaluatedAction,
    holder_idx: usize,
    origin: (f64, f64),
    target: (f64, f64),
    delivery_succeeded: bool,
    branch_probability: f64,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    config: &RunnerRuntimeConfig,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    second_ball_inputs: &mut RunnerSecondBallInputs,
    outcomes: &mut ExecutionTransitionDistribution,
) {
    let RunnerHeldAction::Pass {
        receiver_idx: action_receiver_idx,
        is_long,
        target: intended_target,
        ..
    } = action.action
    else {
        unreachable!();
    };
    let configured_speed = if is_long {
        config.ball_long_pass_speed
    } else {
        config.ball_pass_speed
    };
    let pass_distance = distance(origin, target);
    let speed = crate::pass_average_speed(pass_distance, configured_speed, config.tick_duration);
    let sampled_duration_ticks = (pass_distance / speed.max(0.1)).ceil().max(1.0) as i32;
    let exact_duration_ticks = pass_distance / speed.max(0.1);
    let arrival = runner_pass_arrival_plan(
        holder_idx,
        Some(action_receiver_idx),
        target,
        origin,
        speed,
        exact_duration_ticks,
        teammates,
        opponents,
        config,
    );
    let early_interception =
        arrival.outcome_code == 1 && arrival.contact_tick < sampled_duration_ticks;
    let projected_ticks = if early_interception {
        arrival.contact_tick.max(1)
    } else {
        sampled_duration_ticks
    };
    let mut projected_teammates = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            teammates,
            opponents,
            target,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            projected_ticks,
            config,
            shape_inputs,
            true,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            teammates,
            opponents,
            target,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            projected_ticks,
            config,
            scratch,
        )
    };
    if let Some(receiver) = teammates.get(action_receiver_idx) {
        let pos = runner_projected_contact_position(
            receiver,
            target,
            projected_ticks,
            "attack_run",
            config,
        );
        if let Some(entry) = projected_teammates.positions[..projected_teammates.len]
            .iter_mut()
            .find(|(player_idx, _, _)| *player_idx == action_receiver_idx)
        {
            *entry = (action_receiver_idx, pos.0, pos.1);
        }
    }
    let mut projected_opponents = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            opponents,
            teammates,
            target,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            projected_ticks,
            config,
            shape_inputs,
            false,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            opponents,
            teammates,
            target,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            projected_ticks,
            config,
            scratch,
        )
    };
    if early_interception {
        if let Some(opponent_idx) = arrival.opponent_index {
            if let Some(opponent) = opponents.get(opponent_idx) {
                let pos = runner_projected_contact_position(
                    opponent,
                    arrival.contact_pos,
                    projected_ticks,
                    "contest",
                    config,
                );
                if let Some(entry) = projected_opponents.positions[..projected_opponents.len]
                    .iter_mut()
                    .find(|(player_idx, _, _)| *player_idx == opponent_idx)
                {
                    *entry = (opponent_idx, pos.0, pos.1);
                }
            }
        }
    }
    second_ball_inputs.refresh_projected_positions(
        teammates,
        opponents,
        projected_teammates.slice(),
        projected_opponents.slice(),
    );
    if early_interception {
        if let Some(opponent_idx) = arrival.opponent_index {
            let controller = &opponents[opponent_idx];
            let controller_pos =
                projected_position(projected_opponents.slice(), opponent_idx, controller.pos);
            outcomes.opposing.push(ExecutionTransitionBranch {
                probability: branch_probability,
                controller_idx: Some(opponent_idx),
                pos: controller_pos,
                arrival_heading: angle_between_points(controller_pos, origin),
                ownership_continuity: 0.0,
                contact_load: 0.0,
            });
        } else {
            outcomes.unresolved_probability += branch_probability;
        }
        return;
    }
    let receiver_idx = runner_receiver_arrival_index(&arrival);
    let opponent_idx = arrival.opponent_index.and_then(|opponent_idx| {
        opponents.get(opponent_idx).and_then(|opponent| {
            let opponent_pos =
                projected_position(projected_opponents.slice(), opponent_idx, opponent.pos);
            runner_arrival_opponent_can_control(&arrival, opponent, opponent_pos, config)
                .then_some(opponent_idx)
        })
    });
    if delivery_succeeded {
        let Some(_) = receiver_idx else {
            if let Some(controller_idx) = opponent_idx {
                let controller_pos =
                    projected_position(projected_opponents.slice(), controller_idx, target);
                outcomes.opposing.push(ExecutionTransitionBranch {
                    probability: branch_probability,
                    controller_idx: Some(controller_idx),
                    pos: controller_pos,
                    arrival_heading: angle_between_points(controller_pos, origin),
                    ownership_continuity: 0.0,
                    contact_load: 0.0,
                });
            } else {
                append_projected_uncontrolled_pass_outcome(
                    outcomes,
                    branch_probability,
                    is_long,
                    intended_target,
                    target,
                    origin,
                    action_receiver_idx,
                    delivery_succeeded,
                    teammates,
                    opponents,
                    attacking_right,
                    team_phase,
                    opponent_phase,
                    team_plan_signals,
                    opponent_plan_signals,
                    projected_ticks,
                    scratch,
                    shape_inputs,
                    second_ball_inputs,
                    config,
                    None,
                );
            }
            return;
        };
        let target_is_space = teammates
            .get(action_receiver_idx)
            .is_some_and(|intended| distance(intended_target, intended.pos) > 4.0);
        let arrival_control = projected_pass_arrival_control(
            holder_idx,
            origin,
            target,
            speed,
            pass_terminal_speed_ratio_for(is_long, target_is_space, false),
            projected_ticks,
            teammates,
            opponents,
            projected_teammates.slice(),
            projected_opponents.slice(),
            attacking_right,
            config,
        );
        match arrival_control {
            ProjectedPassArrivalControl::Stable {
                controller_idx,
                team_retained: true,
                position,
            } => outcomes.retained.push(ExecutionTransitionBranch {
                probability: branch_probability,
                controller_idx: Some(controller_idx),
                pos: position,
                arrival_heading: angle_between_points(position, origin),
                ownership_continuity: 0.0,
                contact_load: 0.0,
            }),
            ProjectedPassArrivalControl::Stable {
                controller_idx,
                team_retained: false,
                position,
            } => outcomes.opposing.push(ExecutionTransitionBranch {
                probability: branch_probability,
                controller_idx: Some(controller_idx),
                pos: position,
                arrival_heading: angle_between_points(position, origin),
                ownership_continuity: 0.0,
                contact_load: 0.0,
            }),
            ProjectedPassArrivalControl::Residual { motion, control } => {
                match projected_residual_pass_outcome(
                    motion,
                    control,
                    projected_ticks,
                    teammates,
                    opponents,
                    projected_teammates.slice(),
                    projected_opponents.slice(),
                    attacking_right,
                    config,
                ) {
                    ProjectedResidualPassOutcome::Stable {
                        controller_idx,
                        team_retained: true,
                        position,
                        ..
                    } => outcomes.retained.push(ExecutionTransitionBranch {
                        probability: branch_probability,
                        controller_idx: Some(controller_idx),
                        pos: position,
                        arrival_heading: angle_between_points(position, origin),
                        ownership_continuity: 0.0,
                        contact_load: 0.0,
                    }),
                    ProjectedResidualPassOutcome::Stable {
                        controller_idx,
                        team_retained: false,
                        position,
                        ..
                    } => outcomes.opposing.push(ExecutionTransitionBranch {
                        probability: branch_probability,
                        controller_idx: Some(controller_idx),
                        pos: position,
                        arrival_heading: angle_between_points(position, origin),
                        ownership_continuity: 0.0,
                        contact_load: 0.0,
                    }),
                    ProjectedResidualPassOutcome::InPlay {
                        position,
                        extra_ticks,
                    } => append_projected_uncontrolled_pass_outcome(
                        outcomes,
                        branch_probability,
                        is_long,
                        intended_target,
                        target,
                        origin,
                        action_receiver_idx,
                        delivery_succeeded,
                        teammates,
                        opponents,
                        attacking_right,
                        team_phase,
                        opponent_phase,
                        team_plan_signals,
                        opponent_plan_signals,
                        projected_ticks + extra_ticks,
                        scratch,
                        shape_inputs,
                        second_ball_inputs,
                        config,
                        Some(BallMotionState::stationary(position)),
                    ),
                    ProjectedResidualPassOutcome::OutOfPlay => {
                        outcomes.unresolved_probability += branch_probability;
                    }
                }
            }
        }
    } else if let Some(controller_idx) = opponent_idx {
        let controller_pos =
            projected_position(projected_opponents.slice(), controller_idx, target);
        outcomes.opposing.push(ExecutionTransitionBranch {
            probability: branch_probability,
            controller_idx: Some(controller_idx),
            pos: controller_pos,
            arrival_heading: angle_between_points(controller_pos, origin),
            ownership_continuity: 0.0,
            contact_load: 0.0,
        });
    } else {
        append_projected_uncontrolled_pass_outcome(
            outcomes,
            branch_probability,
            is_long,
            intended_target,
            target,
            origin,
            action_receiver_idx,
            delivery_succeeded,
            teammates,
            opponents,
            attacking_right,
            team_phase,
            opponent_phase,
            team_plan_signals,
            opponent_plan_signals,
            projected_ticks,
            scratch,
            shape_inputs,
            second_ball_inputs,
            config,
            None,
        );
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum ProjectedPassArrivalControl {
    Stable {
        controller_idx: usize,
        team_retained: bool,
        position: (f64, f64),
    },
    Residual {
        motion: BallMotionState,
        control: BallControlContest,
    },
}

fn projected_ball_contact_inputs(
    ball_pos: (f64, f64),
    projected_ticks: f64,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    projected_teammates: &[(usize, f64, f64)],
    projected_opponents: &[(usize, f64, f64)],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> Vec<PlayerBallContactInput> {
    let projection_ticks = projected_ticks.max(f64::EPSILON);
    let mut players = Vec::with_capacity(teammates.len() + opponents.len());
    for (team_retained, team, projected, team_attacking_right) in [
        (true, teammates, projected_teammates, attacking_right),
        (false, opponents, projected_opponents, !attacking_right),
    ] {
        for (index, player) in team.iter().enumerate() {
            if matches!(player.state.as_str(), "stunned" | "recovering") {
                continue;
            }
            let position = projected_position(projected, index, player.pos);
            let velocity = (
                (position.0 - player.pos.0) / projection_ticks,
                (position.1 - player.pos.1) / projection_ticks,
            );
            let is_goalkeeper = player.position == "GK";
            let own_goal_x = if team_attacking_right {
                0.0
            } else {
                config.pitch_length
            };
            let can_use_hands = is_goalkeeper
                && (ball_pos.0 - own_goal_x).abs() <= 16.5
                && (ball_pos.1 - config.pitch_width * 0.5).abs() <= 20.2;
            players.push(PlayerBallContactInput {
                index,
                team_home: team_retained,
                position,
                velocity,
                facing_direction: player.facing_direction,
                dribbling: player.dribbling,
                iq: player.iq,
                speed: player.speed,
                tackling: player.tackling,
                defence: player.defence,
                gk_saving: player.gk_saving,
                gk_positioning: player.gk_positioning,
                gk_reaction: player.gk_reaction,
                can_use_hands,
            });
        }
    }
    players
}

#[allow(clippy::too_many_arguments)]
fn projected_pass_arrival_control(
    passer_idx: usize,
    origin: (f64, f64),
    target: (f64, f64),
    speed: f64,
    terminal_speed_ratio: f64,
    _projected_ticks: i32,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    projected_teammates: &[(usize, f64, f64)],
    projected_opponents: &[(usize, f64, f64)],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> ProjectedPassArrivalControl {
    let exact_flight_ticks = distance(origin, target) / speed.max(f64::EPSILON);
    let curve_input = FlightTickInput {
        origin,
        target,
        ticks_elapsed: 0,
        ticks_total: exact_flight_ticks.ceil().max(1.0) as i32,
        speed,
        terminal_speed_ratio,
    };
    let substep_ticks = crate::ball_contact_substep_ticks(config.tick_duration);
    let mut elapsed_ticks = 0.0;
    let start_sample = sample_ball_flight_curve(&curve_input, 0.0);
    let mut motion = BallMotionState {
        position: start_sample.position,
        velocity: start_sample.velocity,
    };
    let mut control = BallControlContest::default();
    let mut contacted = false;
    while elapsed_ticks + 1e-9 < exact_flight_ticks {
        let step_ticks = substep_ticks.min(exact_flight_ticks - elapsed_ticks);
        let next_elapsed = elapsed_ticks + step_ticks;
        let next_sample = sample_ball_flight_curve(&curve_input, next_elapsed);
        let next_motion = if contacted {
            crate::advance_free_ball(&crate::FreeBallMotionInput {
                state: motion,
                elapsed_ticks: step_ticks,
                rolling_deceleration: crate::free_ball_rolling_deceleration(config.tick_duration),
                drag: crate::free_ball_drag(config.tick_duration),
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            })
        } else {
            BallMotionState {
                position: next_sample.position,
                velocity: next_sample.velocity,
            }
        };
        let progress = (next_elapsed / exact_flight_ticks.max(f64::EPSILON)).clamp(0.0, 1.0);
        let mut players = projected_ball_contact_inputs(
            next_motion.position,
            exact_flight_ticks,
            teammates,
            opponents,
            projected_teammates,
            projected_opponents,
            attacking_right,
            config,
        );
        for player in &mut players {
            let team = if player.team_home {
                teammates
            } else {
                opponents
            };
            if let Some(source) = team.get(player.index) {
                player.position = (
                    source.pos.0 + (player.position.0 - source.pos.0) * progress,
                    source.pos.1 + (player.position.1 - source.pos.1) * progress,
                );
            }
        }
        if next_elapsed <= 1.0 {
            players.retain(|player| !player.team_home || player.index != passer_idx);
        }
        let contact = resolve_ball_contacts(&BallContactTickInput {
            motion: next_motion,
            previous_motion: motion,
            previous_control: control,
            players: &players,
            elapsed_ticks: step_ticks,
            control_elapsed_seconds: step_ticks * config.tick_duration,
            control_radius: config.contest_radius.min(1.35),
            impulse_scale: 20.0,
        });
        motion = contact.motion;
        control = contact.control;
        if let Some(controller) = contact.stable_controller {
            return ProjectedPassArrivalControl::Stable {
                controller_idx: controller.player_index,
                team_retained: controller.team_home,
                position: motion.position,
            };
        }
        let velocity_scale = 2.0 / config.tick_duration.max(f64::EPSILON);
        let incoming_speed = next_motion.speed() * velocity_scale;
        let velocity_change =
            distance(contact.motion.velocity, next_motion.velocity) * velocity_scale;
        let materially_deflected = contact
            .strongest_contact
            .is_some_and(|strongest| strongest.confidence >= 0.15)
            && velocity_change >= 0.45_f64.max(incoming_speed * 0.10);
        if materially_deflected {
            contacted = true;
        }
        elapsed_ticks = next_elapsed;
    }
    ProjectedPassArrivalControl::Residual { motion, control }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum ProjectedUncontrolledPassMotion {
    InPlay {
        position: (f64, f64),
        extra_ticks: i32,
    },
    OutOfPlay,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum ProjectedResidualPassOutcome {
    Stable {
        controller_idx: usize,
        team_retained: bool,
        position: (f64, f64),
        extra_ticks: i32,
    },
    InPlay {
        position: (f64, f64),
        extra_ticks: i32,
    },
    OutOfPlay,
}

#[allow(clippy::too_many_arguments)]
fn projected_residual_pass_outcome(
    mut motion: BallMotionState,
    mut control: BallControlContest,
    projected_ticks: i32,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    projected_teammates: &[(usize, f64, f64)],
    projected_opponents: &[(usize, f64, f64)],
    attacking_right: bool,
    config: &RunnerRuntimeConfig,
) -> ProjectedResidualPassOutcome {
    let substep_ticks = crate::ball_contact_substep_ticks(config.tick_duration);
    let mut players = projected_ball_contact_inputs(
        motion.position,
        projected_ticks.max(1) as f64,
        teammates,
        opponents,
        projected_teammates,
        projected_opponents,
        attacking_right,
        config,
    );
    let mut substeps_elapsed = 0;
    while motion.speed() > 1e-6 {
        let input = crate::FreeBallMotionInput {
            state: motion,
            elapsed_ticks: substep_ticks,
            rolling_deceleration: crate::free_ball_rolling_deceleration(config.tick_duration),
            drag: crate::free_ball_drag(config.tick_duration),
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
        };
        let unclamped_position = crate::free_ball_unclamped_position(&input);
        if crate::segment_pitch_boundary_crossing(
            motion.position,
            unclamped_position,
            config.pitch_length,
            config.pitch_width,
        )
        .is_some()
        {
            return ProjectedResidualPassOutcome::OutOfPlay;
        }
        let next_motion = crate::advance_free_ball(&input);
        for player in &mut players {
            player.position.0 = (player.position.0 + player.velocity.0 * substep_ticks)
                .clamp(0.0, config.pitch_length);
            player.position.1 = (player.position.1 + player.velocity.1 * substep_ticks)
                .clamp(0.0, config.pitch_width);
        }
        let contact = resolve_ball_contacts(&BallContactTickInput {
            motion: next_motion,
            previous_motion: motion,
            previous_control: control,
            players: &players,
            elapsed_ticks: substep_ticks,
            control_elapsed_seconds: substep_ticks * config.tick_duration,
            control_radius: config.contest_radius.min(1.35),
            impulse_scale: 4.0,
        });
        motion = contact.motion;
        control = contact.control;
        substeps_elapsed += 1;
        if let Some(controller) = contact.stable_controller {
            return ProjectedResidualPassOutcome::Stable {
                controller_idx: controller.player_index,
                team_retained: controller.team_home,
                position: motion.position,
                extra_ticks: (substeps_elapsed as f64 * substep_ticks).ceil() as i32,
            };
        }
    }
    ProjectedResidualPassOutcome::InPlay {
        position: motion.position,
        extra_ticks: (substeps_elapsed as f64 * substep_ticks).ceil() as i32,
    }
}

fn projected_residual_pass_motion(
    mut motion: BallMotionState,
    config: &RunnerRuntimeConfig,
) -> ProjectedUncontrolledPassMotion {
    let substep_ticks = crate::ball_contact_substep_ticks(config.tick_duration);
    let mut substeps_elapsed = 0;
    while motion.speed() > 1e-6 {
        let input = crate::FreeBallMotionInput {
            state: motion,
            elapsed_ticks: substep_ticks,
            rolling_deceleration: crate::free_ball_rolling_deceleration(config.tick_duration),
            drag: crate::free_ball_drag(config.tick_duration),
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
        };
        let unclamped_position = crate::free_ball_unclamped_position(&input);
        if crate::segment_pitch_boundary_crossing(
            motion.position,
            unclamped_position,
            config.pitch_length,
            config.pitch_width,
        )
        .is_some()
        {
            return ProjectedUncontrolledPassMotion::OutOfPlay;
        }
        motion = crate::advance_free_ball(&input);
        substeps_elapsed += 1;
    }
    ProjectedUncontrolledPassMotion::InPlay {
        position: motion.position,
        extra_ticks: (substeps_elapsed as f64 * substep_ticks).ceil() as i32,
    }
}

fn projected_uncontrolled_pass_motion(
    origin: (f64, f64),
    target: (f64, f64),
    speed: f64,
    terminal_speed_ratio: f64,
    config: &RunnerRuntimeConfig,
) -> ProjectedUncontrolledPassMotion {
    projected_residual_pass_motion(
        BallMotionState {
            position: target,
            velocity: crate::flight_terminal_velocity(origin, target, speed, terminal_speed_ratio),
        },
        config,
    )
}

#[allow(clippy::too_many_arguments)]
fn append_projected_uncontrolled_pass_outcome(
    outcomes: &mut ExecutionTransitionDistribution,
    probability: f64,
    is_long: bool,
    intended_target: (f64, f64),
    sampled_target: (f64, f64),
    origin: (f64, f64),
    receiver_idx: usize,
    delivery_succeeded: bool,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    arrival_ticks: i32,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    second_ball_inputs: &mut RunnerSecondBallInputs,
    config: &RunnerRuntimeConfig,
    residual_motion: Option<BallMotionState>,
) {
    let target_is_space = teammates
        .get(receiver_idx)
        .is_some_and(|receiver| distance(intended_target, receiver.pos) > 4.0);
    let terminal_speed_ratio =
        pass_terminal_speed_ratio_for(is_long, target_is_space, !delivery_succeeded);
    let configured_speed = if is_long {
        config.ball_long_pass_speed
    } else {
        config.ball_pass_speed
    };
    let speed = crate::pass_average_speed(
        distance(origin, sampled_target),
        configured_speed,
        config.tick_duration,
    );
    let motion = residual_motion.map_or_else(
        || {
            projected_uncontrolled_pass_motion(
                origin,
                sampled_target,
                speed,
                terminal_speed_ratio,
                config,
            )
        },
        |motion| projected_residual_pass_motion(motion, config),
    );
    let ProjectedUncontrolledPassMotion::InPlay {
        position,
        extra_ticks,
    } = motion
    else {
        outcomes.unresolved_probability += probability;
        return;
    };
    let total_ticks = arrival_ticks + extra_ticks;
    let projected_teammates = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            teammates,
            opponents,
            position,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            total_ticks,
            config,
            shape_inputs,
            true,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            teammates,
            opponents,
            position,
            attacking_right,
            team_phase,
            team_plan_signals,
            None,
            total_ticks,
            config,
            scratch,
        )
    };
    let projected_opponents = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            opponents,
            teammates,
            position,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            total_ticks,
            config,
            shape_inputs,
            false,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            opponents,
            teammates,
            position,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            total_ticks,
            config,
            scratch,
        )
    };
    second_ball_inputs.refresh_projected_positions(
        teammates,
        opponents,
        projected_teammates.slice(),
        projected_opponents.slice(),
    );
    runner_append_projected_second_ball_outcomes(
        outcomes,
        probability,
        position,
        origin,
        second_ball_inputs,
        config,
    );
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_carry_execution_outcomes_into(
    action: &RunnerEvaluatedAction,
    response_arena: Option<&RunnerCarryDefenderResponseArena>,
    immediate_defender_responses: &[DefenderActionInput],
    current_control: PossessionControlState,
    holder_idx: usize,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    execution_opponents: &[ExecutionOpponent],
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    duration_ticks: i32,
    config: &RunnerRuntimeConfig,
    scratch: &mut RunnerProjectedTeamProjectionScratch,
    shape_inputs: Option<&RunnerProjectedExecutionShapeInputs>,
    second_ball_inputs: &mut RunnerSecondBallInputs,
    outcomes: &mut ExecutionTransitionDistribution,
) -> (
    [Option<crate::execution_transition::CarrySegmentTransition>;
        RUNNER_MAX_CARRY_RESPONSE_SEGMENTS],
    Option<PossessionControlState>,
)
{
    outcomes.clear();
    let baseline_survival = action.carry_survival.unwrap_or(CarrySurvivalTransition {
        retained_control_probability: action.success_prob.clamp(0.0, 1.0),
        unconstrained_control_probability: action.success_prob.clamp(0.0, 1.0),
        constrained_control_probability: 0.0,
        opposing_control_probability: 1.0 - action.success_prob.clamp(0.0, 1.0),
        unresolved_probability: 0.0,
        unconstrained_control_position: target,
        constrained_control_position: target,
        opposing_control_position: target,
        peak_contact_probability: 0.0,
        peak_containment_probability: 0.0,
        segment_count: duration_ticks.max(1),
    });
    let Some(holder) = teammates.get(holder_idx) else {
        outcomes.unresolved_probability = 1.0;
        return ([None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS], None);
    };
    let stored_defender_responses = action
        .carry_defender_response_index
        .and_then(|index| response_arena.and_then(|arena| arena.get(index)));
    let computed_defender_responses = if stored_defender_responses.is_none() {
        Some(runner_carry_defender_responses(
            holder_idx,
            holder,
            teammates,
            opponents,
            current_control,
            target,
            attacking_right,
            opponent_plan_signals,
            baseline_survival.segment_count,
            config,
        ))
    } else {
        None
    };
    let defender_responses = stored_defender_responses
        .or(computed_defender_responses.as_ref())
        .expect("carry projection requires defender responses");
    let mut response_slices = [&[][..]; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS];
    for segment in 0..baseline_survival.segment_count.max(1) as usize {
        response_slices[segment] = defender_responses.segment(segment);
    }
    let mut merged_immediate_responses = [RUNNER_EMPTY_DEFENDER_ACTION; RUNNER_TEAM_SIZE];
    let mut merged_immediate_count = response_slices[0].len();
    if !immediate_defender_responses.is_empty() {
        merged_immediate_responses[..merged_immediate_count].copy_from_slice(response_slices[0]);
        for immediate in immediate_defender_responses {
            if immediate.action == "hold_position" {
                continue;
            }
            if let Some(existing) = merged_immediate_responses[..merged_immediate_count]
                .iter_mut()
                .find(|response| response.index == immediate.index)
            {
                *existing = *immediate;
            } else if merged_immediate_count < RUNNER_TEAM_SIZE {
                merged_immediate_responses[merged_immediate_count] = *immediate;
                merged_immediate_count += 1;
            }
        }
        response_slices[0] = &merged_immediate_responses[..merged_immediate_count];
    }
    let survival = carry_survival_transition_with_defender_response_slices(
        &CarrySurvivalInput {
            holder_pos: origin,
            carry_target: target,
            carrier_step_distance: config.carrier_speed,
            attacker_dribbling: holder.dribbling,
            defenders: &[],
            tackle_range: config.tackle_range,
            segment_count: baseline_survival.segment_count,
        },
        &response_slices[..baseline_survival.segment_count.max(1) as usize],
    );
    let mut carry_pos = holder.pos;
    let mut carry_velocity = holder.velocity;
    let initial_control_readiness = crate::directional_control_readiness(
        current_control,
        projected_carry_arrival_heading(origin, target),
    );
    let mut technical_transition =
        crate::execution_transition::SequentialExecutionTransition::new();
    let mut technical_error_positions = [(0.0, 0.0); 4];
    let mut carry_transitions = [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS];
    for segment in 0..survival.segment_count.max(1) {
        let response = response_slices[segment as usize];
        let control_readiness = if (segment as usize) < defender_responses.control_readiness_count {
            defender_responses.control_readiness[segment as usize]
        } else {
            initial_control_readiness
        };
        let carry = carry_phase_plan(&CarryPhasePlanInput {
            transition: None,
            holder_pos: carry_pos,
            terminal_touch_origin: Some(defender_responses.action_origin),
            target,
            velocity: carry_velocity,
            speed_ability: holder.speed.round() as i32,
            dribbling: holder.dribbling,
            consecutive_carries: holder.consecutive_carries + segment,
            control_readiness,
            attacking_right,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            goal_width: config.goal_width,
            player_max_speed: config.player_max_speed,
            player_min_speed: config.player_min_speed,
            carrier_speed: config.carrier_speed,
            carry_error_divisor: config.carry_error_divisor,
            opponents: execution_opponents,
            defender_responses: response,
            error_roll: 1.0,
            containment_roll: 1.0,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        });
        carry_transitions[segment as usize] = Some(carry.transition);
        let entering_mass = technical_transition.success_probability;
        let (unconstrained_error_mass, constrained_error_mass) =
            carry.transition.technical_failure_masses();
        let error_mass = technical_transition.append(carry.transition.technical_survival());
        debug_assert!(
            (error_mass - entering_mass * (unconstrained_error_mass + constrained_error_mass))
                .abs()
                <= 1e-12
        );
        for (branch, branch_error_mass) in [
            (carry.transition.unconstrained, unconstrained_error_mass),
            (carry.transition.constrained, constrained_error_mass),
        ] {
            let loose_transition = crate::execution_transition::RectangularLooseBallTransition {
                center: branch.control_pos,
                radius_x: 3.0,
                radius_y: 2.0,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
            };
            for (index, loose_pos) in loose_transition.quadrature().into_iter().enumerate() {
                let weighted_error_mass = entering_mass * branch_error_mass;
                technical_error_positions[index].0 += weighted_error_mass * loose_pos.0;
                technical_error_positions[index].1 += weighted_error_mass * loose_pos.1;
            }
        }
        carry_pos = carry.transition.projected_surviving_control_pos();
        carry_velocity = carry.transition.projected_surviving_velocity();
    }
    let technical_survival = technical_transition.success_probability;
    let transition_mass = crate::execution_transition::carry_execution_transition_mass(
        technical_transition,
        survival.unconstrained_control_probability,
        survival.constrained_control_probability,
        survival.opposing_control_probability,
        survival.unresolved_probability,
    );
    let projected_teammates = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            teammates,
            opponents,
            carry_pos,
            attacking_right,
            team_phase,
            team_plan_signals,
            Some((holder_idx, carry_pos)),
            duration_ticks,
            config,
            shape_inputs,
            true,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            teammates,
            opponents,
            carry_pos,
            attacking_right,
            team_phase,
            team_plan_signals,
            Some((holder_idx, carry_pos)),
            duration_ticks,
            config,
            scratch,
        )
    };
    let projected_opponents = if let Some(shape_inputs) = shape_inputs {
        runner_projected_execution_team_positions_into(
            opponents,
            teammates,
            carry_pos,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            shape_inputs,
            false,
            scratch,
        )
    } else {
        runner_projected_team_positions_into(
            opponents,
            teammates,
            carry_pos,
            !attacking_right,
            opponent_phase,
            opponent_plan_signals,
            None,
            duration_ticks,
            config,
            scratch,
        )
    };
    second_ball_inputs.refresh_projected_positions(
        teammates,
        opponents,
        projected_teammates.slice(),
        projected_opponents.slice(),
    );
    let final_segment = carry_transitions[survival.segment_count.max(1).saturating_sub(1) as usize]
        .expect("projected carry must retain its final execution segment");
    match projected_carry_first_boundary_outcome(
        &carry_transitions,
        false,
        attacking_right,
        config,
    ) {
        Some(RunnerControlledCarryBoundaryOutcome::Goal) => {
            outcomes.goal_probability += transition_mass.retained_unconstrained;
        }
        Some(RunnerControlledCarryBoundaryOutcome::OutOfPlay) => {
            outcomes.unresolved_probability += transition_mass.retained_unconstrained;
        }
        None => outcomes.retained.push(ExecutionTransitionBranch {
            probability: transition_mass.retained_unconstrained,
            controller_idx: Some(holder_idx),
            pos: final_segment.unconstrained.control_pos,
            arrival_heading: projected_carry_arrival_heading(
                origin,
                final_segment.unconstrained.control_pos,
            ),
            ownership_continuity: 1.0,
            contact_load: 0.0,
        }),
    }
    match projected_carry_first_boundary_outcome(
        &carry_transitions,
        true,
        attacking_right,
        config,
    ) {
        Some(RunnerControlledCarryBoundaryOutcome::Goal) => {
            outcomes.goal_probability += transition_mass.retained_constrained;
        }
        Some(RunnerControlledCarryBoundaryOutcome::OutOfPlay) => {
            outcomes.unresolved_probability += transition_mass.retained_constrained;
        }
        None => outcomes.retained.push(ExecutionTransitionBranch {
            probability: transition_mass.retained_constrained,
            controller_idx: Some(holder_idx),
            pos: final_segment.constrained.control_pos,
            arrival_heading: projected_carry_arrival_heading(
                origin,
                final_segment.constrained.control_pos,
            ),
            ownership_continuity: 1.0,
            contact_load: survival.peak_containment_probability,
        }),
    }
    if let Some(controller_idx) = runner_projected_controller_index(
        opponents,
        projected_opponents.slice(),
        survival.opposing_control_position,
    ) {
        outcomes.opposing.push(ExecutionTransitionBranch {
            probability: transition_mass.opposing_control,
            controller_idx: Some(controller_idx),
            pos: survival.opposing_control_position,
            arrival_heading: angle_between_points(survival.opposing_control_position, origin),
            ownership_continuity: 0.0,
            contact_load: 0.0,
        });
    } else {
        outcomes.unresolved_probability += transition_mass.opposing_control;
    }
    let physical_loose_probability = technical_survival * survival.unresolved_probability;
    let loose_probability = transition_mass.loose;
    if loose_probability > 1e-9 {
        let physical_loose_pos = survival.unconstrained_control_position;
        for technical_error_position in technical_error_positions {
            let loose_pos = (
                (technical_error_position.0 + physical_loose_probability * physical_loose_pos.0)
                    / loose_probability,
                (technical_error_position.1 + physical_loose_probability * physical_loose_pos.1)
                    / loose_probability,
            );
            runner_append_projected_second_ball_outcomes(
                outcomes,
                loose_probability * 0.25,
                loose_pos,
                origin,
                second_ball_inputs,
                config,
            );
        }
    }
    (carry_transitions, Some(defender_responses.successor_control))
}

pub(super) fn projected_execution_transition_values(
    outcomes: &ExecutionTransitionDistribution,
    origin: (f64, f64),
    turn_target: Option<f64>,
    retained_control_override: Option<PossessionControlState>,
    holder_home: bool,
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    team_plan: TeamPlanState,
    opponent_plan: TeamPlanState,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    current_control: PossessionControlState,
    duration_ticks: i32,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    shape_inputs: &RunnerProjectedExecutionShapeInputs,
    retained: &mut Option<RunnerProjectedControlValueContext>,
    opposing: &mut Option<RunnerProjectedControlValueContext>,
    config: &RunnerRuntimeConfig,
) -> RunnerProjectedTransitionValues {
    let mut value_for_retained = |branch: ExecutionTransitionBranch| {
        branch.controller_idx.map_or(0.0, |controller_idx| {
            let value_context = retained.get_or_insert_with(|| {
                runner_projected_control_value_context(teammates, opponents, config)
            });
            runner_projected_control_value_with_shape_inputs(
                controller_idx,
                branch.pos,
                teammates,
                opponents,
                shape_inputs,
                true,
                holder_home,
                attacking_right,
                team_phase,
                opponent_phase,
                team_plan,
                opponent_plan,
                team_plan_signals,
                opponent_plan_signals,
                retained_control_override.unwrap_or(current_control),
                branch.arrival_heading,
                branch.ownership_continuity,
                branch.contact_load,
                duration_ticks,
                distance(origin, branch.pos),
                turn_target,
                tick,
                shot_quality_cache,
                value_context,
                config,
            )
        })
    };
    let mut value_for_opposing = |branch: ExecutionTransitionBranch| {
        branch.controller_idx.map_or(0.0, |controller_idx| {
            let value_context = opposing.get_or_insert_with(|| {
                runner_projected_control_value_context(opponents, teammates, config)
            });
            runner_projected_control_value_with_shape_inputs(
                controller_idx,
                branch.pos,
                opponents,
                teammates,
                shape_inputs,
                false,
                !holder_home,
                !attacking_right,
                opponent_phase,
                team_phase,
                opponent_plan,
                team_plan,
                opponent_plan_signals,
                team_plan_signals,
                PossessionControlState::default(),
                branch.arrival_heading,
                branch.ownership_continuity,
                branch.contact_load,
                duration_ticks,
                distance(origin, branch.pos),
                None,
                tick,
                shot_quality_cache,
                value_context,
                config,
            )
        })
    };
    let expected = outcomes.expected_values(&mut value_for_retained, &mut value_for_opposing);
    RunnerProjectedTransitionValues {
        goal_probability: outcomes.goal_probability.clamp(0.0, 1.0),
        retained_control_probability: expected.retained_control_probability,
        retained_control_value: expected.retained_control_value.clamp(0.0, 1.0),
        opposing_control_probability: expected.opposing_control_probability,
        opposing_control_value: expected.opposing_control_value.clamp(0.0, 1.0),
        carry_transition: None,
        carry_transitions: [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS],
        pass_transition: None,
        control_transition: None,
        clearance_transition: None,
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn projected_transition_values(
    action: &RunnerEvaluatedAction,
    response_arena: Option<&RunnerCarryDefenderResponseArena>,
    defender_responses: &[DefenderActionInput],
    holder_idx: usize,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    holder_home: bool,
    attacking_right: bool,
    team_phase: &str,
    opponent_phase: &str,
    team_plan: TeamPlanState,
    opponent_plan: TeamPlanState,
    team_plan_signals: TeamPlanSignals,
    opponent_plan_signals: TeamPlanSignals,
    current_control: PossessionControlState,
    duration_ticks: i32,
    tick: i32,
    shot_quality_cache: &ShotQualityCache,
    value_contexts: &mut RunnerProjectedTransitionValueContexts,
    config: &RunnerRuntimeConfig,
) -> Option<RunnerProjectedTransitionValues> {
    if !value_contexts.execution_shape_inputs_ready {
        value_contexts
            .execution_shape_inputs
            .refresh(teammates, opponents);
        value_contexts.execution_shape_inputs_ready = true;
    }
    if !value_contexts.execution_opponents_ready {
        value_contexts.execution_opponent_count =
            execution_opponents_into(opponents, &mut value_contexts.execution_opponents);
        value_contexts.execution_opponents_ready = true;
    }
    let RunnerProjectedTransitionValueContexts {
        retained,
        opposing,
        execution_opponents,
        execution_opponent_count,
        execution_shape_inputs,
        execution_team_scratch,
        execution_second_ball_inputs,
        execution_outcomes,
        control_execution_outcome_cache,
        ..
    } = value_contexts;
    execution_second_ball_inputs.prepare_projected_players(teammates, opponents, config);
    let (
        carry_transitions,
        pass_transition,
        control_transition,
        clearance_transition,
        retained_control_override,
    ) =
        match action.action {
            RunnerHeldAction::Pass { .. } => {
                let transition = projected_pass_execution_outcomes_into(
                    action,
                    holder_idx,
                    origin,
                    target,
                    teammates,
                    opponents,
                    defender_responses,
                    attacking_right,
                    team_phase,
                    opponent_phase,
                    team_plan_signals,
                    opponent_plan_signals,
                    duration_ticks,
                    config,
                    execution_team_scratch,
                    Some(execution_shape_inputs),
                    execution_second_ball_inputs,
                    execution_outcomes,
                );
                (
                    [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS],
                    transition,
                    None,
                    None,
                    None,
                )
            }
            RunnerHeldAction::Carry { .. } => {
                let (transitions, successor_control) = projected_carry_execution_outcomes_into(
                    action,
                    response_arena,
                    defender_responses,
                    current_control,
                    holder_idx,
                    origin,
                    target,
                    teammates,
                    opponents,
                    &execution_opponents[..*execution_opponent_count],
                    attacking_right,
                    team_phase,
                    opponent_phase,
                    team_plan_signals,
                    opponent_plan_signals,
                    duration_ticks,
                    config,
                    execution_team_scratch,
                    Some(execution_shape_inputs),
                    execution_second_ball_inputs,
                    execution_outcomes,
                );
                (transitions, None, None, None, successor_control)
            }
            RunnerHeldAction::Hold { .. } | RunnerHeldAction::Reorient { .. } => {
                let (action_code, control_target) = match action.action {
                    RunnerHeldAction::Hold { opportunity_target } => (0, opportunity_target),
                    RunnerHeldAction::Reorient { target } => (1, Some(target)),
                    _ => unreachable!(),
                };
                let cached = control_execution_outcome_cache.as_ref().and_then(|cache| {
                    cache
                        .matches(
                            holder_idx,
                            origin,
                            action_code,
                            control_target,
                            duration_ticks,
                        )
                        .then_some((cache.outcomes, cache.transition))
                });
                let transition = if let Some((cached_outcomes, transition)) = cached {
                    *execution_outcomes = cached_outcomes;
                    transition
                } else {
                    let transition = projected_control_execution_outcomes_into(
                        action,
                        holder_idx,
                        origin,
                        teammates,
                        opponents,
                        &execution_opponents[..*execution_opponent_count],
                        defender_responses,
                        attacking_right,
                        team_phase,
                        opponent_phase,
                        team_plan_signals,
                        opponent_plan_signals,
                        duration_ticks,
                        config,
                        execution_team_scratch,
                        Some(execution_shape_inputs),
                        execution_second_ball_inputs,
                        execution_outcomes,
                    )
                    .expect("control projection requires the current holder");
                    *control_execution_outcome_cache =
                        Some(RunnerProjectedControlExecutionOutcomeCache {
                            holder_idx,
                            origin_x_bits: origin.0.to_bits(),
                            origin_y_bits: origin.1.to_bits(),
                            action_code,
                            control_target_bits: control_target
                                .map(|target| (target.0.to_bits(), target.1.to_bits())),
                            duration_ticks,
                            outcomes: *execution_outcomes,
                            transition,
                        });
                    transition
                };
                apply_control_arrival_heading(
                    execution_outcomes,
                    action.action,
                    target,
                    current_control,
                );
                (
                    [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS],
                    None,
                    Some(transition),
                    None,
                    None,
                )
            }
            RunnerHeldAction::Clear { .. } => {
                let transition = projected_clearance_execution_outcomes_into(
                    target,
                    teammates,
                    opponents,
                    attacking_right,
                    team_phase,
                    opponent_phase,
                    team_plan_signals,
                    opponent_plan_signals,
                    duration_ticks,
                    config,
                    execution_team_scratch,
                    Some(execution_shape_inputs),
                    execution_outcomes,
                );
                (
                    [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS],
                    None,
                    None,
                    transition,
                    None,
                )
            }
            RunnerHeldAction::Shoot { .. } => return None,
        };
    let mut values = projected_execution_transition_values(
        execution_outcomes,
        origin,
        match action.action {
            RunnerHeldAction::Reorient { target } => Some(angle_between_points(origin, target)),
            _ => None,
        },
        retained_control_override,
        holder_home,
        attacking_right,
        team_phase,
        opponent_phase,
        teammates,
        opponents,
        team_plan,
        opponent_plan,
        team_plan_signals,
        opponent_plan_signals,
        current_control,
        duration_ticks,
        tick,
        shot_quality_cache,
        execution_shape_inputs,
        retained,
        opposing,
        config,
    );
    values.carry_transition = carry_transitions[0];
    values.carry_transitions = carry_transitions;
    values.pass_transition = pass_transition;
    values.control_transition = control_transition;
    values.clearance_transition = clearance_transition;
    Some(values)
}

#[cfg(test)]
mod tests {
    use super::{
        projected_carry_arrival_heading, projected_carry_first_boundary_outcome,
        projected_carry_stays_in_play, projected_clearance_execution_outcomes_into,
        projected_pass_arrival_control,
        projected_uncontrolled_pass_motion, ProjectedPassArrivalControl,
        ProjectedUncontrolledPassMotion,
    };
    use crate::match_runner::{
        build_players, formation_data, runner_pass_arrival_plan, runner_receiver_arrival_index,
        runtime_config, ExecutionTransitionDistribution, RunnerControlledCarryBoundaryOutcome,
        RunnerProjectedTeamProjectionScratch, RUNNER_TEAM_SIZE,
    };
    use serde_json::json;

    fn test_card(name: &str) -> serde_json::Value {
        json!({
            "name": name,
            "player_id": name,
            "color": "b",
            "abilities": {
                "Finishing": 75.0,
                "Long_Shot": 75.0,
                "Short_Passing": 75.0,
                "Long_Passing": 75.0,
                "Dribbling": 80.0,
                "Tackling": 75.0,
                "Defence": 75.0,
                "Speed": 80.0,
                "IQ": 80.0,
                "GK_Saving": 75.0,
                "GK_Positioning": 75.0,
                "GK_Reaction": 75.0
            }
        })
    }

    #[test]
    fn projected_carry_arrival_heading_follows_the_direction_of_travel() {
        let origin = (42.0, 30.0);

        assert_eq!(
            projected_carry_arrival_heading(origin, (48.0, 30.0)).to_bits(),
            0.0_f64.to_bits()
        );
        assert_eq!(
            projected_carry_arrival_heading(origin, (42.0, 36.0)).to_bits(),
            90.0_f64.to_bits()
        );
        assert_ne!(
            projected_carry_arrival_heading(origin, (48.0, 30.0)).to_bits(),
            180.0_f64.to_bits()
        );
    }

    #[test]
    fn projected_carry_control_ends_when_either_pitch_boundary_is_crossed() {
        let config = runtime_config(&json!({}));

        assert!(projected_carry_stays_in_play(
            (95.0, 8.0),
            (103.0, 12.0),
            &config
        ));
        assert!(!projected_carry_stays_in_play(
            (95.0, 8.0),
            (106.0, 20.0),
            &config
        ));
        assert!(!projected_carry_stays_in_play(
            (40.0, 1.0),
            (48.0, -1.0),
            &config
        ));
    }

    #[test]
    fn projected_carry_cannot_reenter_after_an_earlier_out_of_play_crossing() {
        let config = runtime_config(&json!({}));
        let transition = |origin, end_pos| {
            Some(crate::execution_transition::CarrySegmentTransition::new(
                origin,
                crate::execution_transition::BinaryExecutionTransition::from_success_probability(
                    0.0,
                ),
                end_pos,
                (
                    end_pos.0.clamp(0.5, config.pitch_length - 0.5),
                    end_pos.1.clamp(0.5, config.pitch_width - 0.5),
                ),
                (4.0, 0.0),
                end_pos,
                (
                    end_pos.0.clamp(0.5, config.pitch_length - 0.5),
                    end_pos.1.clamp(0.5, config.pitch_width - 0.5),
                ),
                (4.0, 0.0),
                0.0,
                0.0,
            ))
        };
        let transitions = [
            transition((102.0, 20.0), (106.0, 28.0)),
            transition((104.5, 28.0), (106.0, 34.0)),
            None,
            None,
        ];

        assert_eq!(
            projected_carry_first_boundary_outcome(&transitions, false, true, &config),
            Some(RunnerControlledCarryBoundaryOutcome::OutOfPlay),
            "the first goal-line crossing ends play before a later projected segment can bend back through the goal mouth"
        );
    }

    #[test]
    fn projected_clearance_does_not_grant_control_to_an_unreachable_nearest_player() {
        let cards = (0..RUNNER_TEAM_SIZE)
            .map(|index| test_card(format!("Player {index}").as_str()))
            .collect::<Vec<_>>();
        let mut teammates = build_players(&cards, formation_data("442"), true, 105.0, 68.0);
        let mut opponents = build_players(&cards, formation_data("442"), false, 105.0, 68.0);
        let config = runtime_config(&json!({}));
        let target = (52.5, 34.0);
        for player in teammates.iter_mut().chain(opponents.iter_mut()) {
            player.pos = (5.0, 5.0);
            player.target_pos = player.pos;
        }
        let mut scratch = RunnerProjectedTeamProjectionScratch::new();
        let mut outcomes = ExecutionTransitionDistribution::default();

        let transition = projected_clearance_execution_outcomes_into(
            target,
            &teammates,
            &opponents,
            true,
            "defend",
            "attack",
            crate::team_plan_signals(crate::TeamPlanKind::DefendBlock),
            crate::team_plan_signals(crate::TeamPlanKind::Advance),
            1,
            &config,
            &mut scratch,
            None,
            &mut outcomes,
        );

        assert!(transition.is_none());
        assert_eq!(outcomes.retained_probability(), 0.0);
        assert_eq!(outcomes.opposing_probability(), 0.0);
        assert_eq!(outcomes.unresolved_probability, 1.0);
    }

    #[test]
    fn projected_uncontrolled_pass_rolls_out_instead_of_stopping_at_the_target() {
        let config = runtime_config(&json!({}));

        let motion = projected_uncontrolled_pass_motion(
            (40.0, 8.0),
            (46.0, 1.2),
            config.ball_pass_speed,
            0.24,
            &config,
        );

        assert_eq!(motion, ProjectedUncontrolledPassMotion::OutOfPlay);
    }

    #[test]
    fn projected_uncontrolled_pass_preserves_an_in_play_second_ball() {
        let config = runtime_config(&json!({}));
        let target = (46.0, 12.0);

        let motion = projected_uncontrolled_pass_motion(
            (40.0, 8.0),
            target,
            config.ball_pass_speed,
            0.24,
            &config,
        );

        let ProjectedUncontrolledPassMotion::InPlay {
            position,
            extra_ticks,
        } = motion
        else {
            panic!("an inward pass should remain available as an in-play second ball");
        };
        assert!(position.0 > target.0);
        assert!(position.1 > target.1);
        assert!(extra_ticks > 0);
    }

    #[test]
    fn projected_arrival_does_not_equate_geometric_arrival_with_stable_control() {
        let cards = (0..RUNNER_TEAM_SIZE)
            .map(|index| test_card(format!("Player {index}").as_str()))
            .collect::<Vec<_>>();
        let mut teammates = build_players(&cards, formation_data("442"), true, 105.0, 68.0);
        let mut opponents = build_players(&cards, formation_data("442"), false, 105.0, 68.0);
        let config = runtime_config(&json!({}));
        let passer_idx = 7;
        let receiver_idx = 9;
        let origin = (40.0, 8.0);
        let target = (46.0, 1.2);
        teammates[passer_idx].pos = origin;
        teammates[receiver_idx].pos = target;
        teammates[receiver_idx].target_pos = target;
        teammates[receiver_idx].velocity = (0.0, 0.0);
        for opponent in &mut opponents {
            opponent.pos = (80.0, 50.0);
            opponent.target_pos = opponent.pos;
        }
        let exact_ticks = crate::distance(origin, target) / config.ball_pass_speed;
        let arrival = runner_pass_arrival_plan(
            passer_idx,
            Some(receiver_idx),
            target,
            origin,
            config.ball_pass_speed,
            exact_ticks,
            &teammates,
            &opponents,
            &config,
        );
        assert_eq!(runner_receiver_arrival_index(&arrival), Some(receiver_idx));

        let projected_teammates = teammates
            .iter()
            .enumerate()
            .map(|(index, player)| (index, player.pos.0, player.pos.1))
            .collect::<Vec<_>>();
        let projected_opponents = opponents
            .iter()
            .enumerate()
            .map(|(index, player)| (index, player.pos.0, player.pos.1))
            .collect::<Vec<_>>();
        let control = projected_pass_arrival_control(
            passer_idx,
            origin,
            target,
            config.ball_pass_speed,
            0.24,
            exact_ticks.ceil() as i32,
            &teammates,
            &opponents,
            &projected_teammates,
            &projected_opponents,
            true,
            &config,
        );

        let ProjectedPassArrivalControl::Residual { motion, .. } = control else {
            panic!("arrival geometry must not grant stable control at the same instant");
        };
        assert!(motion.speed() > 0.5);
    }

    #[test]
    fn projected_pass_control_is_invariant_to_equivalent_tick_durations() {
        let cards = (0..RUNNER_TEAM_SIZE)
            .map(|index| test_card(format!("Player {index}").as_str()))
            .collect::<Vec<_>>();
        let mut teammates = build_players(&cards, formation_data("442"), true, 105.0, 68.0);
        let mut opponents = build_players(&cards, formation_data("442"), false, 105.0, 68.0);
        let passer_idx = 7;
        let receiver_idx = 9;
        let origin = (40.0, 34.0);
        let target = (52.0, 34.0);
        teammates[passer_idx].pos = origin;
        teammates[receiver_idx].pos = (51.2, 34.35);
        teammates[receiver_idx].target_pos = target;
        teammates[receiver_idx].velocity = (0.0, 0.0);
        opponents[4].pos = (51.4, 33.55);
        opponents[4].target_pos = target;
        opponents[4].velocity = (0.0, 0.0);
        for (index, opponent) in opponents.iter_mut().enumerate() {
            if index != 4 {
                opponent.pos = (80.0, 50.0);
                opponent.target_pos = opponent.pos;
                opponent.velocity = (0.0, 0.0);
            }
        }

        let projected_teammates = teammates
            .iter()
            .enumerate()
            .map(|(index, player)| (index, player.target_pos.0, player.target_pos.1))
            .collect::<Vec<_>>();
        let projected_opponents = opponents
            .iter()
            .enumerate()
            .map(|(index, player)| (index, player.target_pos.0, player.target_pos.1))
            .collect::<Vec<_>>();

        let config_two_seconds = runtime_config(&json!({}));
        let mut config_one_second = config_two_seconds.clone();
        config_one_second.tick_duration = 1.0;
        config_one_second.player_max_speed *= 0.5;
        config_one_second.player_min_speed *= 0.5;
        config_one_second.ball_pass_speed *= 0.5;
        config_one_second.ball_long_pass_speed *= 0.5;
        config_one_second.ball_shot_speed *= 0.5;
        config_one_second.carrier_speed *= 0.5;

        let speed_two_seconds = crate::pass_average_speed(
            crate::distance(origin, target),
            config_two_seconds.ball_pass_speed,
            config_two_seconds.tick_duration,
        );
        let speed_one_second = crate::pass_average_speed(
            crate::distance(origin, target),
            config_one_second.ball_pass_speed,
            config_one_second.tick_duration,
        );
        let flight_ticks_two_seconds = crate::distance(origin, target) / speed_two_seconds;
        let flight_ticks_one_second = crate::distance(origin, target) / speed_one_second;
        assert!(
            (flight_ticks_two_seconds * config_two_seconds.tick_duration
                - flight_ticks_one_second * config_one_second.tick_duration)
                .abs()
                < 1e-9
        );

        let control_two_seconds = projected_pass_arrival_control(
            passer_idx,
            origin,
            target,
            speed_two_seconds,
            0.24,
            flight_ticks_two_seconds.ceil() as i32,
            &teammates,
            &opponents,
            &projected_teammates,
            &projected_opponents,
            true,
            &config_two_seconds,
        );
        let control_one_second = projected_pass_arrival_control(
            passer_idx,
            origin,
            target,
            speed_one_second,
            0.24,
            flight_ticks_one_second.ceil() as i32,
            &teammates,
            &opponents,
            &projected_teammates,
            &projected_opponents,
            true,
            &config_one_second,
        );

        match (control_two_seconds, control_one_second) {
            (
                ProjectedPassArrivalControl::Stable {
                    controller_idx: controller_two_seconds,
                    team_retained: retained_two_seconds,
                    position: position_two_seconds,
                },
                ProjectedPassArrivalControl::Stable {
                    controller_idx: controller_one_second,
                    team_retained: retained_one_second,
                    position: position_one_second,
                },
            ) => {
                assert_eq!(controller_two_seconds, controller_one_second);
                assert_eq!(retained_two_seconds, retained_one_second);
                assert!(crate::distance(position_two_seconds, position_one_second) < 1e-6);
            }
            (
                ProjectedPassArrivalControl::Residual {
                    motion: motion_two_seconds,
                    control: contest_two_seconds,
                },
                ProjectedPassArrivalControl::Residual {
                    motion: motion_one_second,
                    control: contest_one_second,
                },
            ) => {
                assert_eq!(
                    contest_two_seconds.home.player_index,
                    contest_one_second.home.player_index
                );
                assert_eq!(
                    contest_two_seconds.away.player_index,
                    contest_one_second.away.player_index
                );
                assert!(
                    (contest_two_seconds.home.confidence
                        - contest_one_second.home.confidence)
                        .abs()
                        < 1e-6,
                    "home control diverged: two_seconds={contest_two_seconds:?}, one_second={contest_one_second:?}, motion_two_seconds={motion_two_seconds:?}, motion_one_second={motion_one_second:?}"
                );
                assert!(
                    (contest_two_seconds.away.confidence
                        - contest_one_second.away.confidence)
                        .abs()
                        < 1e-6,
                    "away control diverged: two_seconds={contest_two_seconds:?}, one_second={contest_one_second:?}, motion_two_seconds={motion_two_seconds:?}, motion_one_second={motion_one_second:?}"
                );
                assert!(
                    crate::distance(motion_two_seconds.position, motion_one_second.position) < 1e-6
                );
                assert!(
                    crate::distance(
                        (
                            motion_two_seconds.velocity.0 / config_two_seconds.tick_duration,
                            motion_two_seconds.velocity.1 / config_two_seconds.tick_duration,
                        ),
                        (
                            motion_one_second.velocity.0 / config_one_second.tick_duration,
                            motion_one_second.velocity.1 / config_one_second.tick_duration,
                        ),
                    ) < 1e-6
                );
            }
            (two_seconds, one_second) => {
                panic!(
                    "equivalent physical passes diverged by tick duration: two_seconds={two_seconds:?}, one_second={one_second:?}"
                );
            }
        }
    }
}
