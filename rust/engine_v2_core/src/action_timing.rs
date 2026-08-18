#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TemporalActionKind {
    Carry,
    Hold,
    Reorient,
    Shoot,
}

#[derive(Clone, Copy, Debug)]
pub struct ActionTimingInput {
    pub kind: TemporalActionKind,
    pub target_distance: f64,
    pub nominal_step_distance: f64,
    pub pressure: f64,
    pub tempo: f64,
    pub risk_budget: f64,
    pub opportunity: f64,
    pub tick_duration: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ActionTimingPlan {
    pub initial_ticks: i32,
    pub completion_distance: f64,
    pub requires_target_completion: bool,
}

#[derive(Clone, Copy)]
struct ActionTimingProfile {
    kind: TemporalActionKind,
    base_ticks: f64,
    distance_ticks: f64,
    low_tempo_ticks: f64,
    low_risk_ticks: f64,
    opportunity_ticks: f64,
    pressure_ticks: f64,
    min_ticks: f64,
    max_ticks: f64,
    completion_step_fraction: f64,
    requires_target_completion: bool,
}

const ACTION_TIMING_PROFILES: [ActionTimingProfile; 4] = [
    ActionTimingProfile {
        kind: TemporalActionKind::Carry,
        base_ticks: 0.72,
        distance_ticks: 0.66,
        low_tempo_ticks: 0.34,
        low_risk_ticks: 0.12,
        opportunity_ticks: 0.0,
        pressure_ticks: 0.32,
        min_ticks: 1.0,
        max_ticks: 4.0,
        completion_step_fraction: 0.42,
        requires_target_completion: true,
    },
    ActionTimingProfile {
        kind: TemporalActionKind::Hold,
        base_ticks: 0.82,
        distance_ticks: 0.0,
        low_tempo_ticks: 0.72,
        low_risk_ticks: 0.28,
        opportunity_ticks: 0.96,
        pressure_ticks: 0.88,
        min_ticks: 1.0,
        max_ticks: 4.0,
        completion_step_fraction: 0.0,
        requires_target_completion: false,
    },
    ActionTimingProfile {
        kind: TemporalActionKind::Reorient,
        base_ticks: 1.0,
        distance_ticks: 0.0,
        low_tempo_ticks: 0.0,
        low_risk_ticks: 0.0,
        opportunity_ticks: 0.0,
        pressure_ticks: 0.0,
        min_ticks: 1.0,
        max_ticks: 1.0,
        completion_step_fraction: 0.0,
        requires_target_completion: false,
    },
    ActionTimingProfile {
        kind: TemporalActionKind::Shoot,
        // A selected shot is a short rolling-horizon action: the first contact
        // may only set the body and improve release readiness before the ball
        // is struck. The match runner already models that preparation contact
        // (including a defender duel), so a one-tick cap made its continuation
        // branch unreachable and discarded most selected shots.
        base_ticks: 2.0,
        distance_ticks: 0.0,
        low_tempo_ticks: 0.0,
        low_risk_ticks: 0.0,
        opportunity_ticks: 0.0,
        pressure_ticks: 0.0,
        min_ticks: 2.0,
        max_ticks: 2.0,
        completion_step_fraction: 0.0,
        requires_target_completion: false,
    },
];

fn timing_profile(kind: TemporalActionKind) -> ActionTimingProfile {
    ACTION_TIMING_PROFILES
        .iter()
        .find(|profile| profile.kind == kind)
        .copied()
        .unwrap_or(ACTION_TIMING_PROFILES[0])
}

pub fn action_timing_plan(input: &ActionTimingInput) -> ActionTimingPlan {
    let profile = timing_profile(input.kind);
    let step_distance = input.nominal_step_distance.max(0.1);
    let travel_steps = (input.target_distance.max(0.0) / step_distance).min(5.0);
    let commitment = profile.base_ticks
        + profile.distance_ticks * travel_steps
        + profile.low_tempo_ticks * (1.0 - input.tempo.clamp(0.0, 1.0))
        + profile.low_risk_ticks * (1.0 - input.risk_budget.clamp(0.0, 1.0))
        + profile.opportunity_ticks * input.opportunity.clamp(0.0, 1.0)
        - profile.pressure_ticks * input.pressure.clamp(0.0, 1.0);
    let commitment_seconds = commitment
        .clamp(profile.min_ticks, profile.max_ticks)
        .max(input.tick_duration.max(f64::EPSILON));
    let initial_ticks = (commitment_seconds / input.tick_duration.max(f64::EPSILON)).ceil() as i32;
    ActionTimingPlan {
        initial_ticks,
        completion_distance: step_distance * profile.completion_step_fraction,
        requires_target_completion: profile.requires_target_completion,
    }
}

pub fn should_continue_action(
    plan: ActionTimingPlan,
    remaining_ticks: i32,
    distance_to_target: f64,
) -> bool {
    if remaining_ticks <= 0 {
        return false;
    }
    !plan.requires_target_completion || distance_to_target > plan.completion_distance
}

#[cfg(test)]
mod tests {
    use super::{
        action_timing_plan, should_continue_action, ActionTimingInput, TemporalActionKind,
    };

    #[test]
    fn carry_duration_scales_with_geometry_and_team_tempo() {
        let short_fast = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Carry,
            target_distance: 2.0,
            nominal_step_distance: 3.0,
            pressure: 0.2,
            tempo: 0.85,
            risk_budget: 0.75,
            opportunity: 0.0,
            tick_duration: 1.0,
        });
        let long_controlled = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Carry,
            target_distance: 9.0,
            nominal_step_distance: 3.0,
            pressure: 0.2,
            tempo: 0.25,
            risk_budget: 0.30,
            opportunity: 0.0,
            tick_duration: 1.0,
        });

        assert!(long_controlled.initial_ticks > short_fast.initial_ticks);
        assert!(long_controlled.completion_distance > 0.0);
    }

    #[test]
    fn hold_duration_reacts_to_control_opportunity_and_pressure() {
        let protected_window = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Hold,
            target_distance: 0.0,
            nominal_step_distance: 3.0,
            pressure: 0.1,
            tempo: 0.25,
            risk_budget: 0.25,
            opportunity: 1.0,
            tick_duration: 1.0,
        });
        let urgent_pressure = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Hold,
            target_distance: 0.0,
            nominal_step_distance: 3.0,
            pressure: 0.95,
            tempo: 0.85,
            risk_budget: 0.75,
            opportunity: 0.0,
            tick_duration: 1.0,
        });

        assert!(protected_window.initial_ticks > urgent_pressure.initial_ticks);
    }

    #[test]
    fn reorientation_is_one_control_contact() {
        let reorientation = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Reorient,
            target_distance: 0.0,
            nominal_step_distance: 3.0,
            pressure: 0.1,
            tempo: 0.25,
            risk_budget: 0.25,
            opportunity: 1.0,
            tick_duration: 1.0,
        });

        assert_eq!(reorientation.initial_ticks, 1);
        assert!(!reorientation.requires_target_completion);
    }

    #[test]
    fn action_commitment_preserves_physical_seconds_across_tick_sizes() {
        let one_second = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Shoot,
            target_distance: 18.0,
            nominal_step_distance: 3.0,
            pressure: 0.5,
            tempo: 0.5,
            risk_budget: 0.5,
            opportunity: 0.0,
            tick_duration: 1.0,
        });
        let half_second = action_timing_plan(&ActionTimingInput {
            tick_duration: 0.5,
            ..ActionTimingInput {
                kind: TemporalActionKind::Shoot,
                target_distance: 18.0,
                nominal_step_distance: 3.0,
                pressure: 0.5,
                tempo: 0.5,
                risk_budget: 0.5,
                opportunity: 0.0,
                tick_duration: 1.0,
            }
        });

        assert_eq!(one_second.initial_ticks, 2);
        assert_eq!(half_second.initial_ticks, 4);
        assert_eq!(
            one_second.initial_ticks as f64,
            half_second.initial_ticks as f64 * 0.5,
        );
    }

    #[test]
    fn shot_keeps_a_short_preparation_horizon() {
        let shot = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Shoot,
            target_distance: 18.0,
            nominal_step_distance: 3.0,
            pressure: 0.8,
            tempo: 0.2,
            risk_budget: 0.2,
            opportunity: 0.0,
            tick_duration: 1.0,
        });

        assert_eq!(shot.initial_ticks, 2);
        assert!(!shot.requires_target_completion);
        assert!(should_continue_action(shot, 2, 18.0));
        assert!(should_continue_action(shot, 1, 18.0));
        assert!(!should_continue_action(shot, 0, 18.0));
    }

    #[test]
    fn continuation_stops_at_time_budget_or_spatial_completion() {
        let carry = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Carry,
            target_distance: 8.0,
            nominal_step_distance: 3.0,
            pressure: 0.2,
            tempo: 0.5,
            risk_budget: 0.5,
            opportunity: 0.0,
            tick_duration: 1.0,
        });
        assert!(should_continue_action(carry, 1, 4.0));
        assert!(!should_continue_action(carry, 0, 4.0));
        assert!(!should_continue_action(carry, 1, carry.completion_distance));

        let hold = action_timing_plan(&ActionTimingInput {
            kind: TemporalActionKind::Hold,
            target_distance: 0.0,
            nominal_step_distance: 3.0,
            pressure: 0.2,
            tempo: 0.5,
            risk_budget: 0.5,
            opportunity: 1.0,
            tick_duration: 1.0,
        });
        assert!(should_continue_action(hold, 1, 0.0));
    }
}
