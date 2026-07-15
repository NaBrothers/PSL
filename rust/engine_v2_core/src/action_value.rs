#[derive(Clone, Copy, Debug)]
pub struct PossessionTransition {
    pub goal_probability: f64,
    pub retained_control_probability: f64,
    pub retained_control_value: f64,
    pub opposing_control_probability: f64,
    pub opposing_control_value: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct SecondBallPlayerInput {
    pub pos: (f64, f64),
    pub projected_pos: (f64, f64),
    pub speed: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct SecondBallControlInput<'a> {
    pub ball_pos: (f64, f64),
    pub contest_radius: f64,
    pub attacking_players: &'a [SecondBallPlayerInput],
    pub defending_players: &'a [SecondBallPlayerInput],
}

#[derive(Clone, Copy, Debug)]
pub struct SecondBallControlEstimate {
    pub attacking_control_probability: f64,
    pub defending_control_probability: f64,
    pub unresolved_probability: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotPossessionTransitionInput {
    pub execution_probability: f64,
    pub release_probability: f64,
    pub block_probability: f64,
    pub conditional_on_target_probability: f64,
    pub goal_probability: f64,
    pub unreleased_second_ball: SecondBallControlEstimate,
    pub blocked_second_ball: SecondBallControlEstimate,
    pub unreleased_retained_control_value: f64,
    pub unreleased_opposing_control_value: f64,
    pub blocked_retained_control_value: f64,
    pub blocked_opposing_control_value: f64,
    pub saved_opposing_control_value: f64,
    pub off_target_opposing_control_value: f64,
}

pub fn second_ball_player_access(
    player: &SecondBallPlayerInput,
    ball_pos: (f64, f64),
    contest_radius: f64,
) -> f64 {
    let contest_radius = contest_radius.max(0.1);
    let speed = player.speed.max(0.1);
    let dx = player.projected_pos.0 - ball_pos.0;
    let dy = player.projected_pos.1 - ball_pos.1;
    let projected_distance = (dx * dx + dy * dy).sqrt();
    let arrival_ticks = projected_distance / speed;
    let immediate_access = (-projected_distance / contest_radius).exp();
    immediate_access / (0.35 + arrival_ticks)
}

pub fn estimate_second_ball_control(
    input: &SecondBallControlInput<'_>,
) -> SecondBallControlEstimate {
    let attacking_access = input
        .attacking_players
        .iter()
        .map(|player| second_ball_player_access(player, input.ball_pos, input.contest_radius))
        .sum::<f64>();
    let defending_access = input
        .defending_players
        .iter()
        .map(|player| second_ball_player_access(player, input.ball_pos, input.contest_radius))
        .sum::<f64>();
    let total_access = attacking_access + defending_access;
    if total_access <= 1e-9 {
        return SecondBallControlEstimate {
            attacking_control_probability: 0.0,
            defending_control_probability: 0.0,
            unresolved_probability: 1.0,
        };
    }

    let resolved_probability = (1.0 - (-total_access).exp()).clamp(0.0, 1.0);
    SecondBallControlEstimate {
        attacking_control_probability: resolved_probability * attacking_access / total_access,
        defending_control_probability: resolved_probability * defending_access / total_access,
        unresolved_probability: 1.0 - resolved_probability,
    }
}

pub fn shot_possession_transition(input: &ShotPossessionTransitionInput) -> PossessionTransition {
    let execution_probability = input.execution_probability.clamp(0.0, 1.0);
    let unreleased_probability = 1.0 - execution_probability;
    let declared_release_probability = input.release_probability.clamp(0.0, 1.0);
    let declared_block_probability = input.block_probability.clamp(0.0, 1.0);
    let contest_probability_mass = declared_release_probability + declared_block_probability;
    let (release_probability, block_probability) = if contest_probability_mass > 1e-9 {
        (
            declared_release_probability / contest_probability_mass,
            declared_block_probability / contest_probability_mass,
        )
    } else {
        (1.0, 0.0)
    };
    let conditional_on_target_probability = input.conditional_on_target_probability.clamp(0.0, 1.0);
    let on_target_probability =
        execution_probability * release_probability * conditional_on_target_probability;
    let goal_probability =
        (execution_probability * input.goal_probability).clamp(0.0, on_target_probability);
    let saved_probability = (on_target_probability - goal_probability).max(0.0);
    let off_target_probability =
        execution_probability * release_probability * (1.0 - conditional_on_target_probability);
    let unreleased_retained_probability = unreleased_probability
        * input
            .unreleased_second_ball
            .attacking_control_probability
            .clamp(0.0, 1.0);
    let unreleased_opposing_probability = unreleased_probability
        * input
            .unreleased_second_ball
            .defending_control_probability
            .clamp(0.0, 1.0);
    let blocked_retained_probability = execution_probability
        * block_probability
        * input
            .blocked_second_ball
            .attacking_control_probability
            .clamp(0.0, 1.0);
    let blocked_opposing_probability = execution_probability
        * block_probability
        * input
            .blocked_second_ball
            .defending_control_probability
            .clamp(0.0, 1.0);
    let retained_control_probability =
        unreleased_retained_probability + blocked_retained_probability;
    let opposing_control_probability = unreleased_opposing_probability
        + saved_probability
        + off_target_probability
        + blocked_opposing_probability;
    let retained_control_value = if retained_control_probability > 0.0 {
        (unreleased_retained_probability * input.unreleased_retained_control_value.clamp(0.0, 1.0)
            + blocked_retained_probability * input.blocked_retained_control_value.clamp(0.0, 1.0))
            / retained_control_probability
    } else {
        0.0
    };
    let opposing_control_value = if opposing_control_probability > 0.0 {
        (unreleased_opposing_probability * input.unreleased_opposing_control_value.clamp(0.0, 1.0)
            + saved_probability * input.saved_opposing_control_value.clamp(0.0, 1.0)
            + off_target_probability * input.off_target_opposing_control_value.clamp(0.0, 1.0)
            + blocked_opposing_probability * input.blocked_opposing_control_value.clamp(0.0, 1.0))
            / opposing_control_probability
    } else {
        0.0
    };

    PossessionTransition {
        goal_probability,
        retained_control_probability,
        retained_control_value,
        opposing_control_probability,
        opposing_control_value,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TemporalOptionValueInput {
    pub current_control_value: f64,
    pub transition: PossessionTransition,
    pub duration_ticks: i32,
    pub tempo: f64,
    pub risk_budget: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TemporalOptionValueOutput {
    pub score: f64,
    pub advantage: f64,
    pub continuation_return: f64,
    pub terminal_return: f64,
    pub temporal_discount: f64,
    pub turnover_cost: f64,
    pub unresolved_probability: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ActionOutcomeValueInput {
    pub temporal: TemporalOptionValueOutput,
    pub policy_alignment: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ActionOutcomeValueOutput {
    pub score: f64,
    pub outcome_value: f64,
    pub policy_value: f64,
}

pub fn temporal_option_value(input: &TemporalOptionValueInput) -> TemporalOptionValueOutput {
    let duration = input.duration_ticks.max(1) as f64;
    let tempo = input.tempo.clamp(0.0, 1.0);
    let risk_budget = input.risk_budget.clamp(0.0, 1.0);
    let temporal_discount = (-(0.0015 + 0.0060 * tempo) * duration).exp();
    let current_control_value = input.current_control_value.clamp(0.0, 1.0);
    let goal_probability = input.transition.goal_probability.clamp(0.0, 1.0);
    let retained_control_probability = input
        .transition
        .retained_control_probability
        .clamp(0.0, 1.0 - goal_probability);
    let opposing_control_probability = input
        .transition
        .opposing_control_probability
        .clamp(0.0, 1.0 - goal_probability - retained_control_probability);
    let unresolved_probability =
        (1.0 - goal_probability - retained_control_probability - opposing_control_probability)
            .max(0.0);
    let continuation_return =
        retained_control_probability * input.transition.retained_control_value.clamp(0.0, 1.0);
    let terminal_return = goal_probability;
    let turnover_severity = 0.76 + 0.12 * (1.0 - risk_budget);
    let turnover_cost = opposing_control_probability
        * input.transition.opposing_control_value.clamp(0.0, 1.0)
        * turnover_severity;
    let score = temporal_discount * (continuation_return + terminal_return - turnover_cost);
    let advantage = score - current_control_value;

    TemporalOptionValueOutput {
        score,
        advantage,
        continuation_return,
        terminal_return,
        temporal_discount,
        turnover_cost,
        unresolved_probability,
    }
}

pub fn action_outcome_value(input: &ActionOutcomeValueInput) -> ActionOutcomeValueOutput {
    let outcome_value = input.temporal.score;
    let policy_value = 0.035 * input.policy_alignment.clamp(-0.25, 1.25);
    ActionOutcomeValueOutput {
        score: outcome_value + policy_value,
        outcome_value,
        policy_value,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        action_outcome_value, estimate_second_ball_control, shot_possession_transition,
        temporal_option_value, ActionOutcomeValueInput, PossessionTransition,
        SecondBallControlEstimate, SecondBallControlInput, SecondBallPlayerInput,
        ShotPossessionTransitionInput, TemporalOptionValueInput,
    };

    #[test]
    fn second_ball_control_favors_the_side_with_earlier_arrival() {
        let attacking_players = [SecondBallPlayerInput {
            pos: (87.0, 34.0),
            projected_pos: (89.0, 34.0),
            speed: 6.4,
        }];
        let defending_players = [SecondBallPlayerInput {
            pos: (96.0, 34.0),
            projected_pos: (94.0, 34.0),
            speed: 5.8,
        }];
        let estimate = estimate_second_ball_control(&SecondBallControlInput {
            ball_pos: (90.0, 34.0),
            contest_radius: 2.5,
            attacking_players: &attacking_players,
            defending_players: &defending_players,
        });

        assert!(estimate.attacking_control_probability > estimate.defending_control_probability);
        assert!(
            (estimate.attacking_control_probability
                + estimate.defending_control_probability
                + estimate.unresolved_probability
                - 1.0)
                .abs()
                < 1e-12
        );
    }

    #[test]
    fn blocked_shot_preserves_second_ball_continuation_and_probability_mass() {
        let low_block = shot_possession_transition(&ShotPossessionTransitionInput {
            execution_probability: 1.0,
            release_probability: 0.92,
            block_probability: 0.08,
            conditional_on_target_probability: 0.58,
            goal_probability: 0.16,
            unreleased_second_ball: SecondBallControlEstimate {
                attacking_control_probability: 0.0,
                defending_control_probability: 0.0,
                unresolved_probability: 1.0,
            },
            blocked_second_ball: SecondBallControlEstimate {
                attacking_control_probability: 0.52,
                defending_control_probability: 0.34,
                unresolved_probability: 0.14,
            },
            unreleased_retained_control_value: 0.0,
            unreleased_opposing_control_value: 0.0,
            blocked_retained_control_value: 0.18,
            blocked_opposing_control_value: 0.08,
            saved_opposing_control_value: 0.06,
            off_target_opposing_control_value: 0.05,
        });
        let high_block = shot_possession_transition(&ShotPossessionTransitionInput {
            execution_probability: 1.0,
            release_probability: 0.55,
            block_probability: 0.45,
            goal_probability: 0.096,
            ..ShotPossessionTransitionInput {
                execution_probability: 1.0,
                release_probability: 0.92,
                block_probability: 0.08,
                conditional_on_target_probability: 0.58,
                goal_probability: 0.16,
                unreleased_second_ball: SecondBallControlEstimate {
                    attacking_control_probability: 0.0,
                    defending_control_probability: 0.0,
                    unresolved_probability: 1.0,
                },
                blocked_second_ball: SecondBallControlEstimate {
                    attacking_control_probability: 0.52,
                    defending_control_probability: 0.34,
                    unresolved_probability: 0.14,
                },
                unreleased_retained_control_value: 0.0,
                unreleased_opposing_control_value: 0.0,
                blocked_retained_control_value: 0.18,
                blocked_opposing_control_value: 0.08,
                saved_opposing_control_value: 0.06,
                off_target_opposing_control_value: 0.05,
            }
        });
        let total_probability = |transition: PossessionTransition| {
            transition.goal_probability
                + transition.retained_control_probability
                + transition.opposing_control_probability
        };
        let unresolved_block_probability = |block_probability: f64| block_probability * 0.14;

        assert!(high_block.goal_probability < low_block.goal_probability);
        assert!(high_block.retained_control_probability > low_block.retained_control_probability);
        assert!(
            (1.0 - total_probability(high_block) - unresolved_block_probability(0.45)).abs()
                < 1e-12
        );
        assert!(
            (1.0 - total_probability(low_block) - unresolved_block_probability(0.08)).abs() < 1e-12
        );
    }

    #[test]
    fn unreleased_shot_becomes_a_second_ball_not_a_prepare_option() {
        let transition = shot_possession_transition(&ShotPossessionTransitionInput {
            execution_probability: 0.35,
            release_probability: 1.0,
            block_probability: 0.0,
            conditional_on_target_probability: 0.60,
            goal_probability: 0.10,
            unreleased_second_ball: SecondBallControlEstimate {
                attacking_control_probability: 0.20,
                defending_control_probability: 0.55,
                unresolved_probability: 0.25,
            },
            blocked_second_ball: SecondBallControlEstimate {
                attacking_control_probability: 0.0,
                defending_control_probability: 0.0,
                unresolved_probability: 1.0,
            },
            unreleased_retained_control_value: 0.14,
            unreleased_opposing_control_value: 0.14,
            blocked_retained_control_value: 0.0,
            blocked_opposing_control_value: 0.0,
            saved_opposing_control_value: 0.06,
            off_target_opposing_control_value: 0.05,
        });

        assert!((transition.goal_probability - 0.035).abs() < 1e-12);
        assert!((transition.retained_control_probability - 0.13).abs() < 1e-12);
        assert!((transition.retained_control_value - 0.14).abs() < 1e-12);
        assert!((transition.opposing_control_probability - 0.6725).abs() < 1e-12);
        assert!((transition.opposing_control_value - 0.100_446_096_654_275_09).abs() < 1e-12);
        assert!(
            (transition.goal_probability
                + transition.retained_control_probability
                + transition.opposing_control_probability
                + 0.65 * 0.25
                - 1.0)
                .abs()
                < 1e-12
        );
    }

    #[test]
    fn safe_recycle_beats_low_quality_terminal_from_valuable_control() {
        let recycle = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.18,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.84,
                retained_control_value: 0.17,
                opposing_control_probability: 0.16,
                opposing_control_value: 0.11,
            },
            duration_ticks: 1,
            tempo: 0.38,
            risk_budget: 0.28,
        });
        let shot = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.18,
            transition: PossessionTransition {
                goal_probability: 0.12,
                retained_control_probability: 0.03,
                retained_control_value: 0.12,
                opposing_control_probability: 0.85,
                opposing_control_value: 0.06,
            },
            duration_ticks: 1,
            tempo: 0.38,
            risk_budget: 0.28,
        });

        assert!(recycle.score > shot.score);
        assert!(recycle.continuation_return > shot.continuation_return);
        assert!(shot.terminal_return > 0.0);
    }

    #[test]
    fn duration_discounts_an_identical_state_transition() {
        let short = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.12,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.72,
                retained_control_value: 0.16,
                opposing_control_probability: 0.28,
                opposing_control_value: 0.08,
            },
            duration_ticks: 1,
            tempo: 0.55,
            risk_budget: 0.50,
        });
        let long = temporal_option_value(&TemporalOptionValueInput {
            duration_ticks: 4,
            ..TemporalOptionValueInput {
                current_control_value: 0.12,
                transition: PossessionTransition {
                    goal_probability: 0.0,
                    retained_control_probability: 0.72,
                    retained_control_value: 0.16,
                    opposing_control_probability: 0.28,
                    opposing_control_value: 0.08,
                },
                duration_ticks: 1,
                tempo: 0.55,
                risk_budget: 0.50,
            }
        });

        assert!(long.temporal_discount < short.temporal_discount);
        assert!(long.score < short.score);
    }

    #[test]
    fn high_quality_terminal_can_beat_low_control_release() {
        let low_control_release = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.16,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.38,
                retained_control_value: 0.09,
                opposing_control_probability: 0.62,
                opposing_control_value: 0.12,
            },
            duration_ticks: 2,
            tempo: 0.72,
            risk_budget: 0.68,
        });
        let clear_chance = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.16,
            transition: PossessionTransition {
                goal_probability: 0.42,
                retained_control_probability: 0.05,
                retained_control_value: 0.15,
                opposing_control_probability: 0.53,
                opposing_control_value: 0.05,
            },
            duration_ticks: 1,
            tempo: 0.72,
            risk_budget: 0.68,
        });

        assert!(clear_chance.score > low_control_release.score);
    }

    #[test]
    fn high_quality_terminal_still_beats_safe_but_non_improving_control() {
        let retain = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.14,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.55,
                retained_control_value: 0.14,
                opposing_control_probability: 0.45,
                opposing_control_value: 0.10,
            },
            duration_ticks: 1,
            tempo: 0.64,
            risk_budget: 0.62,
        });
        let shot = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.14,
            transition: PossessionTransition {
                goal_probability: 0.26,
                retained_control_probability: 0.04,
                retained_control_value: 0.11,
                opposing_control_probability: 0.70,
                opposing_control_value: 0.05,
            },
            duration_ticks: 1,
            tempo: 0.64,
            risk_budget: 0.62,
        });

        assert!(shot.score > retain.score);
    }

    #[test]
    fn outcome_comparison_keeps_policy_secondary_to_executed_return() {
        let direct_terminal = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.12,
            transition: PossessionTransition {
                goal_probability: 0.18,
                retained_control_probability: 0.04,
                retained_control_value: 0.11,
                opposing_control_probability: 0.72,
                opposing_control_value: 0.05,
            },
            duration_ticks: 1,
            tempo: 0.62,
            risk_budget: 0.58,
        });
        let safe_control = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.12,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.82,
                retained_control_value: 0.15,
                opposing_control_probability: 0.18,
                opposing_control_value: 0.08,
            },
            duration_ticks: 2,
            tempo: 0.62,
            risk_budget: 0.58,
        });
        let terminal_value = action_outcome_value(&ActionOutcomeValueInput {
            temporal: direct_terminal,
            policy_alignment: 0.0,
        });
        let control_value = action_outcome_value(&ActionOutcomeValueInput {
            temporal: safe_control,
            policy_alignment: 1.25,
        });

        assert!(
            terminal_value.outcome_value > control_value.outcome_value,
            "the terminal result must be compared on its own expected return"
        );
        assert!(
            terminal_value.score > control_value.score,
            "the bounded team policy term must not overturn a materially better executed result"
        );
        assert!(
            control_value.policy_value <= 0.04375 + 1e-12,
            "team policy must stay a coordination term instead of a replacement action value"
        );
    }

    #[test]
    fn micro_carry_that_preserves_the_same_state_has_negative_advantage() {
        let micro_carry = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.20,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.98,
                retained_control_value: 0.20,
                opposing_control_probability: 0.02,
                opposing_control_value: 0.10,
            },
            duration_ticks: 2,
            tempo: 0.70,
            risk_budget: 0.62,
        });
        let state_improving_recycle = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.20,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.91,
                retained_control_value: 0.27,
                opposing_control_probability: 0.09,
                opposing_control_value: 0.06,
            },
            duration_ticks: 2,
            tempo: 0.36,
            risk_budget: 0.24,
        });

        assert!(micro_carry.advantage < 0.0);
        assert!(state_improving_recycle.advantage > 0.0);
        assert!(state_improving_recycle.score > micro_carry.score);
    }

    #[test]
    fn controlled_restart_is_less_damaging_than_an_open_play_turnover() {
        let open_turnover = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.16,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.0,
                retained_control_value: 0.0,
                opposing_control_probability: 1.0,
                opposing_control_value: 0.14,
            },
            duration_ticks: 1,
            tempo: 0.50,
            risk_budget: 0.50,
        });
        let defensive_restart = temporal_option_value(&TemporalOptionValueInput {
            current_control_value: 0.16,
            transition: PossessionTransition {
                goal_probability: 0.0,
                retained_control_probability: 0.0,
                retained_control_value: 0.0,
                opposing_control_probability: 1.0,
                opposing_control_value: 0.05,
            },
            duration_ticks: 1,
            tempo: 0.50,
            risk_budget: 0.50,
        });

        assert!(open_turnover.turnover_cost > defensive_restart.turnover_cost);
    }
}
