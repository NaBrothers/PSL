use super::*;

pub(super) fn projected_shot_possession_transition(
    action: &RunnerEvaluatedAction,
    origin: (f64, f64),
    target: (f64, f64),
    teammates: &[RunnerPlayer],
    opponents: &[RunnerPlayer],
    config: &RunnerRuntimeConfig,
    opposing_control_value: &mut impl FnMut((f64, f64)) -> f64,
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
    let unreleased_second_ball = model.mishit.quadrature().into_iter().fold(
        crate::SecondBallControlEstimate {
            attacking_control_probability: 0.0,
            defending_control_probability: 0.0,
            unresolved_probability: 0.0,
        },
        |mut aggregate, ball_pos| {
            let estimate = second_ball_inputs.estimate(ball_pos, config);
            aggregate.attacking_control_probability +=
                estimate.attacking_control_probability * 0.25;
            aggregate.defending_control_probability +=
                estimate.defending_control_probability * 0.25;
            aggregate.unresolved_probability += estimate.unresolved_probability * 0.25;
            aggregate
        },
    );
    let blocked_second_ball = second_ball_inputs.estimate(block_point, config);
    let retained_second_ball_value =
        (action.debug_current_pv * 0.55 + action.xg * 0.45).clamp(0.015, 0.35);
    let target_opposing_control_value = opposing_control_value(target);
    crate::action_value::shot_possession_transition_from_execution(
        &ShotPossessionTransitionInput {
            execution_probability: transition.body_release.success_probability,
            release_probability: transition.released_probability_given_body_release,
            block_probability: transition.blocked_probability_given_body_release,
            conditional_on_target_probability: on_target_prob,
            goal_probability: xg,
            unreleased_second_ball,
            blocked_second_ball,
            unreleased_retained_control_value: retained_second_ball_value,
            unreleased_opposing_control_value: opposing_control_value(origin),
            blocked_retained_control_value: retained_second_ball_value,
            blocked_opposing_control_value: opposing_control_value(block_point),
            saved_opposing_control_value: target_opposing_control_value,
            off_target_opposing_control_value: target_opposing_control_value,
        },
        transition,
    )
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
        receiver_idx,
        is_long,
        ..
    } = action.action
    else {
        unreachable!();
    };
    let speed = if is_long {
        config.ball_long_pass_speed
    } else {
        config.ball_pass_speed
    };
    let sampled_duration_ticks = (distance(origin, target) / speed.max(0.1)).ceil().max(1.0) as i32;
    let arrival = runner_pass_arrival_plan(
        holder_idx,
        Some(receiver_idx),
        target,
        origin,
        speed,
        sampled_duration_ticks,
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
    if let Some(receiver) = teammates.get(receiver_idx) {
        let pos = runner_projected_contact_position(
            receiver,
            target,
            projected_ticks,
            "attack_run",
            config,
        );
        if let Some(entry) = projected_teammates.positions[..projected_teammates.len]
            .iter_mut()
            .find(|(player_idx, _, _)| *player_idx == receiver_idx)
        {
            *entry = (receiver_idx, pos.0, pos.1);
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
    let opponent_idx = (arrival.opponent_control > arrival.loose_control)
        .then_some(arrival.opponent_index)
        .flatten();
    if delivery_succeeded {
        let Some(receiver_idx) = receiver_idx else {
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
                runner_append_projected_second_ball_outcomes(
                    outcomes,
                    branch_probability,
                    target,
                    origin,
                    second_ball_inputs,
                    config,
                );
            }
            return;
        };
        let receiver = &teammates[receiver_idx];
        let receiver_pos =
            projected_position(projected_teammates.slice(), receiver_idx, receiver.pos);
        let defensive_interference = runner_control_interference_probability(
            receiver_pos,
            opponents,
            projected_opponents.slice(),
        );
        let clean_receive = pass_receive_plan(&PassReceivePlanInput {
            receiver_pos,
            target_pos: target,
            receiver_iq: receiver.iq,
            defensive_interference,
            receiver_offside_flagged: false,
            pitch_length: config.pitch_length,
            pitch_width: config.pitch_width,
            first_touch_error_divisor: config.first_touch_error_divisor,
            error_roll: 1.0,
            loose_x_roll: 0.5,
            loose_y_roll: 0.5,
        });
        let first_touch =
            crate::execution_transition::BinaryExecutionTransition::from_success_probability(
                clean_receive.first_touch_error_chance,
            );
        outcomes.retained.push(ExecutionTransitionBranch {
            probability: branch_probability * first_touch.failure_probability,
            controller_idx: Some(receiver_idx),
            pos: receiver_pos,
            arrival_heading: angle_between_points(receiver_pos, origin),
            ownership_continuity: 0.0,
            contact_load: 0.0,
        });
        for (loose_x_roll, loose_y_roll) in [(0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75)]
        {
            let error_receive = pass_receive_plan(&PassReceivePlanInput {
                receiver_pos,
                target_pos: target,
                receiver_iq: receiver.iq,
                defensive_interference,
                receiver_offside_flagged: false,
                pitch_length: config.pitch_length,
                pitch_width: config.pitch_width,
                first_touch_error_divisor: config.first_touch_error_divisor,
                error_roll: 0.0,
                loose_x_roll,
                loose_y_roll,
            });
            runner_append_projected_second_ball_outcomes(
                outcomes,
                branch_probability * first_touch.success_probability * 0.25,
                error_receive.loose_pos,
                origin,
                second_ball_inputs,
                config,
            );
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
        runner_append_projected_second_ball_outcomes(
            outcomes,
            branch_probability,
            target,
            origin,
            second_ball_inputs,
            config,
        );
    }
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
) -> [Option<crate::execution_transition::CarrySegmentTransition>; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS]
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
        return [None; RUNNER_MAX_CARRY_RESPONSE_SEGMENTS];
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
    if crate::physics::attacking_goal_line_crossing(
        origin,
        survival.unconstrained_control_position,
        attacking_right,
        config.pitch_length,
        config.pitch_width,
        config.goal_width,
    )
    .is_none()
    {
        outcomes.retained.push(ExecutionTransitionBranch {
            probability: transition_mass.retained_unconstrained,
            controller_idx: Some(holder_idx),
            pos: survival.unconstrained_control_position,
            arrival_heading: projected_carry_arrival_heading(
                origin,
                survival.unconstrained_control_position,
            ),
            ownership_continuity: 1.0,
            contact_load: 0.0,
        });
    } else {
        outcomes.unresolved_probability += transition_mass.retained_unconstrained;
    }
    outcomes.retained.push(ExecutionTransitionBranch {
        probability: transition_mass.retained_constrained,
        controller_idx: Some(holder_idx),
        pos: survival.constrained_control_position,
        arrival_heading: projected_carry_arrival_heading(
            origin,
            survival.constrained_control_position,
        ),
        ownership_continuity: 1.0,
        contact_load: survival.peak_containment_probability,
    });
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
    carry_transitions
}

pub(super) fn projected_execution_transition_values(
    outcomes: &ExecutionTransitionDistribution,
    origin: (f64, f64),
    turn_target: Option<f64>,
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
                current_control,
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
    let (carry_transitions, pass_transition, control_transition, clearance_transition) =
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
                )
            }
            RunnerHeldAction::Carry { .. } => (
                projected_carry_execution_outcomes_into(
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
                ),
                None,
                None,
                None,
            ),
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
    use super::projected_carry_arrival_heading;

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
}
