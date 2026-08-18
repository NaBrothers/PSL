#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TackleCommitment {
    pub holder_idx: usize,
    pub holder_team_home: bool,
    pub possession_id: i32,
    pub target: (f64, f64),
    pub contact_sampled: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct TackleCommitmentStepInput {
    pub commitment: TackleCommitment,
    pub holder_idx: usize,
    pub holder_team_home: bool,
    pub possession_id: i32,
    pub defender_start: (f64, f64),
    pub defender_end: (f64, f64),
    pub holder_start: (f64, f64),
    pub holder_end: (f64, f64),
    pub contact_radius: f64,
    pub target_tolerance: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TackleCommitmentStep {
    Continue,
    ContactWindow { progress: f64 },
    Missed,
    Cancelled,
}

fn squared_length(vector: (f64, f64)) -> f64 {
    vector.0 * vector.0 + vector.1 * vector.1
}

fn distance(left: (f64, f64), right: (f64, f64)) -> f64 {
    ((left.0 - right.0).powi(2) + (left.1 - right.1).powi(2)).sqrt()
}

fn closest_contact_progress(
    left_start: (f64, f64),
    left_end: (f64, f64),
    right_start: (f64, f64),
    right_end: (f64, f64),
    contact_radius: f64,
) -> Option<f64> {
    let relative_start = (left_start.0 - right_start.0, left_start.1 - right_start.1);
    let relative_velocity = (
        (left_end.0 - left_start.0) - (right_end.0 - right_start.0),
        (left_end.1 - left_start.1) - (right_end.1 - right_start.1),
    );
    let velocity_norm = squared_length(relative_velocity);
    let approach = relative_start.0 * relative_velocity.0 + relative_start.1 * relative_velocity.1;
    if velocity_norm <= 1e-12 {
        return None;
    }
    let progress = (-approach / velocity_norm).clamp(0.0, 1.0);
    if progress <= 1e-12 && approach >= 0.0 {
        return None;
    }
    let separation = (
        relative_start.0 + relative_velocity.0 * progress,
        relative_start.1 + relative_velocity.1 * progress,
    );
    (squared_length(separation) <= contact_radius.max(0.0).powi(2) + 1e-12).then_some(progress)
}

pub fn step_tackle_commitment(input: TackleCommitmentStepInput) -> TackleCommitmentStep {
    if input.commitment.holder_idx != input.holder_idx
        || input.commitment.holder_team_home != input.holder_team_home
        || input.commitment.possession_id != input.possession_id
    {
        return TackleCommitmentStep::Cancelled;
    }
    if !input.commitment.contact_sampled {
        if let Some(progress) = closest_contact_progress(
            input.defender_start,
            input.defender_end,
            input.holder_start,
            input.holder_end,
            input.contact_radius,
        ) {
            return TackleCommitmentStep::ContactWindow { progress };
        }
    }
    if distance(input.defender_end, input.commitment.target) <= input.target_tolerance.max(0.0) {
        TackleCommitmentStep::Missed
    } else {
        TackleCommitmentStep::Continue
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn commitment() -> TackleCommitment {
        TackleCommitment {
            holder_idx: 6,
            holder_team_home: true,
            possession_id: 4,
            target: (4.0, 0.0),
            contact_sampled: false,
        }
    }

    fn input() -> TackleCommitmentStepInput {
        TackleCommitmentStepInput {
            commitment: commitment(),
            holder_idx: 6,
            holder_team_home: true,
            possession_id: 4,
            defender_start: (0.0, 0.0),
            defender_end: (2.0, 0.0),
            holder_start: (4.0, 0.0),
            holder_end: (2.5, 0.0),
            contact_radius: 0.9,
            target_tolerance: 0.05,
        }
    }

    #[test]
    fn commitment_resolves_the_first_swept_contact() {
        let step = step_tackle_commitment(input());
        let TackleCommitmentStep::ContactWindow { progress } = step else {
            panic!("converging paths must make contact");
        };
        assert_eq!(progress, 1.0);
    }

    #[test]
    fn commitment_cancels_when_control_identity_changes() {
        assert_eq!(
            step_tackle_commitment(TackleCommitmentStepInput {
                possession_id: 5,
                ..input()
            }),
            TackleCommitmentStep::Cancelled,
        );
        assert_eq!(
            step_tackle_commitment(TackleCommitmentStepInput {
                holder_idx: 7,
                ..input()
            }),
            TackleCommitmentStep::Cancelled,
        );
    }

    #[test]
    fn reaching_the_frozen_target_without_contact_is_a_miss() {
        let step = step_tackle_commitment(TackleCommitmentStepInput {
            defender_start: (3.0, 0.0),
            defender_end: (4.0, 0.0),
            holder_start: (8.0, 3.0),
            holder_end: (9.0, 3.0),
            ..input()
        });
        assert_eq!(step, TackleCommitmentStep::Missed);
    }

    #[test]
    fn equivalent_physical_paths_contact_at_the_same_position_across_tick_sizes() {
        let coarse = step_tackle_commitment(input());
        let first_half = step_tackle_commitment(TackleCommitmentStepInput {
            defender_end: (1.0, 0.0),
            holder_end: (3.25, 0.0),
            ..input()
        });
        assert_eq!(first_half, TackleCommitmentStep::Continue);
        let second_half = step_tackle_commitment(TackleCommitmentStepInput {
            defender_start: (1.0, 0.0),
            defender_end: (2.0, 0.0),
            holder_start: (3.25, 0.0),
            holder_end: (2.5, 0.0),
            ..input()
        });
        let (
            TackleCommitmentStep::ContactWindow {
                progress: coarse_progress,
            },
            TackleCommitmentStep::ContactWindow {
                progress: half_progress,
            },
        ) = (coarse, second_half)
        else {
            panic!("both resolutions must contact");
        };
        let coarse_position = 2.0 * coarse_progress;
        let half_position = 1.0 + half_progress;
        assert!((coarse_position - half_position).abs() < 1e-12);
    }

    #[test]
    fn sampled_contact_window_is_not_offered_twice() {
        assert_eq!(
            step_tackle_commitment(TackleCommitmentStepInput {
                commitment: TackleCommitment {
                    contact_sampled: true,
                    ..commitment()
                },
                ..input()
            }),
            TackleCommitmentStep::Continue,
        );
    }
}
