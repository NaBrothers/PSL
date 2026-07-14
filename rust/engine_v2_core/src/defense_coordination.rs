use crate::physics::distance;

pub const MAX_FIXED_TEAM_DEFENSE_PLAYERS: usize = 11;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DefenseTaskKind {
    Press,
    Mark,
    BlockLane,
    RecoverShape,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseCandidate {
    pub target: (f64, f64),
    pub projected_pos: (f64, f64),
    pub local_value: f64,
    pub residual_threat: f64,
    pub pressure_coverage: f64,
    pub task_kind: DefenseTaskKind,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefensePlayerInput<'a> {
    pub index: usize,
    pub anchor: (f64, f64),
    pub candidates: &'a [TeamDefenseCandidate],
}

#[derive(Clone, Debug)]
pub struct TeamDefenseAssignmentInput<'a> {
    pub players: &'a [TeamDefensePlayerInput<'a>],
    pub compactness: f64,
    pub immediate_threat: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseAssignment {
    pub index: usize,
    pub candidate_index: usize,
    pub local_value: f64,
    pub residual_threat: f64,
}

#[derive(Clone, Debug)]
pub struct TeamDefenseAssignmentOutput {
    pub assignments: Vec<TeamDefenseAssignment>,
    pub objective: f64,
    pub formation_scale: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct TeamDefenseCoordinationSummary {
    pub objective: f64,
    pub formation_scale: f64,
}

fn formation_scale(players: &[TeamDefensePlayerInput<'_>]) -> f64 {
    let mut nearest_distances = Vec::with_capacity(players.len());
    for (index, player) in players.iter().enumerate() {
        let nearest = players
            .iter()
            .enumerate()
            .filter(|(other_index, _)| *other_index != index)
            .map(|(_, other)| distance(player.anchor, other.anchor))
            .filter(|distance| *distance > 1e-6)
            .fold(f64::INFINITY, f64::min);
        if nearest.is_finite() {
            nearest_distances.push(nearest);
        }
    }
    if nearest_distances.is_empty() {
        return 1.0;
    }
    nearest_distances
        .sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    nearest_distances[nearest_distances.len() / 2].max(1.0)
}

fn formation_scale_fixed(players: &[TeamDefensePlayerInput<'_>]) -> f64 {
    assert!(
        players.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense coordination supports eleven players"
    );
    let mut nearest_distances = [0.0; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    let mut nearest_count = 0;
    for (index, player) in players.iter().enumerate() {
        let nearest = players
            .iter()
            .enumerate()
            .filter(|(other_index, _)| *other_index != index)
            .map(|(_, other)| distance(player.anchor, other.anchor))
            .filter(|distance| *distance > 1e-6)
            .fold(f64::INFINITY, f64::min);
        if nearest.is_finite() {
            nearest_distances[nearest_count] = nearest;
            nearest_count += 1;
        }
    }
    if nearest_count == 0 {
        return 1.0;
    }
    nearest_distances[..nearest_count]
        .sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    nearest_distances[nearest_count / 2].max(1.0)
}

fn task_concentration(kind: DefenseTaskKind) -> f64 {
    match kind {
        DefenseTaskKind::Press => 1.0,
        DefenseTaskKind::Mark => 0.86,
        DefenseTaskKind::BlockLane => 0.72,
        DefenseTaskKind::RecoverShape => 0.28,
    }
}

fn local_candidate_value(
    candidate: TeamDefenseCandidate,
    player: TeamDefensePlayerInput<'_>,
    scale: f64,
    compactness: f64,
) -> f64 {
    let anchor_stiffness = 0.05 + 0.10 * compactness;
    let role_departure = distance(candidate.projected_pos, player.anchor) / scale;
    candidate.local_value.max(0.0)
        - anchor_stiffness * role_departure * role_departure
        - 0.04 * candidate.residual_threat.clamp(0.0, 1.0)
}

fn pair_candidate_penalty(
    left_player: TeamDefensePlayerInput<'_>,
    left_candidate: TeamDefenseCandidate,
    right_player: TeamDefensePlayerInput<'_>,
    right_candidate: TeamDefenseCandidate,
    scale: f64,
    compactness: f64,
) -> f64 {
    let linkage_stiffness = 0.08 + 0.18 * compactness;
    let anchor_distance = distance(left_player.anchor, right_player.anchor);
    let neighborhood_weight = (-anchor_distance / scale).exp();
    let relative_anchor = (
        left_player.anchor.0 - right_player.anchor.0,
        left_player.anchor.1 - right_player.anchor.1,
    );
    let relative_position = (
        left_candidate.projected_pos.0 - right_candidate.projected_pos.0,
        left_candidate.projected_pos.1 - right_candidate.projected_pos.1,
    );
    let relative_deformation = distance(relative_position, relative_anchor) / scale;
    let linkage_penalty =
        linkage_stiffness * neighborhood_weight * relative_deformation * relative_deformation;

    let occupancy =
        (-(distance(left_candidate.projected_pos, right_candidate.projected_pos) / scale).powi(2))
            .exp();
    let occupancy_penalty = (0.14 + 0.20 * compactness) * occupancy;

    let target_overlap =
        (-(distance(left_candidate.target, right_candidate.target) / scale).powi(2)).exp();
    let task_overlap = task_concentration(left_candidate.task_kind)
        * task_concentration(right_candidate.task_kind);
    let overlap_penalty = (0.10 + 0.24 * compactness) * target_overlap * task_overlap;

    linkage_penalty + occupancy_penalty + overlap_penalty
}

fn candidate_pressure_coverage(
    player: TeamDefensePlayerInput<'_>,
    candidate_index: usize,
) -> Option<f64> {
    player
        .candidates
        .get(candidate_index)
        .map(|candidate| candidate.pressure_coverage.clamp(0.0, 1.0))
}

fn selection_objective(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    scale: f64,
) -> f64 {
    let compactness = input.compactness.clamp(0.0, 1.0);
    let mut value = 0.0;

    for (player_index, player) in input.players.iter().enumerate() {
        let Some(candidate) = player.candidates.get(selections[player_index]) else {
            continue;
        };
        value += local_candidate_value(*candidate, *player, scale, compactness);
    }

    let uncovered_immediate_threat = input
        .players
        .iter()
        .enumerate()
        .filter_map(|(player_index, player)| {
            candidate_pressure_coverage(*player, selections[player_index])
        })
        .fold(1.0, |uncovered, coverage| uncovered * (1.0 - coverage));
    value += input.immediate_threat.clamp(0.0, 1.0) * (1.0 - uncovered_immediate_threat);

    for left_index in 0..input.players.len() {
        let left_player = &input.players[left_index];
        let Some(left_candidate) = left_player.candidates.get(selections[left_index]) else {
            continue;
        };
        for right_index in left_index + 1..input.players.len() {
            let right_player = &input.players[right_index];
            let Some(right_candidate) = right_player.candidates.get(selections[right_index]) else {
                continue;
            };
            value -= pair_candidate_penalty(
                *left_player,
                *left_candidate,
                *right_player,
                *right_candidate,
                scale,
                compactness,
            );
        }
    }
    value
}

fn selection_objective_after_change(
    input: &TeamDefenseAssignmentInput<'_>,
    selections: &[usize],
    scale: f64,
    current_objective: f64,
    player_index: usize,
    candidate_index: usize,
) -> f64 {
    let compactness = input.compactness.clamp(0.0, 1.0);
    let Some(player) = input.players.get(player_index).copied() else {
        return current_objective;
    };
    let Some(current_candidate) = player.candidates.get(selections[player_index]).copied() else {
        return current_objective;
    };
    let Some(candidate) = player.candidates.get(candidate_index).copied() else {
        return current_objective;
    };

    let local_delta = local_candidate_value(candidate, player, scale, compactness)
        - local_candidate_value(current_candidate, player, scale, compactness);
    let uncovered_without_player = input
        .players
        .iter()
        .enumerate()
        .filter(|(other_index, _)| *other_index != player_index)
        .filter_map(|(other_index, other)| {
            candidate_pressure_coverage(*other, selections[other_index])
        })
        .fold(1.0, |uncovered, coverage| uncovered * (1.0 - coverage));
    let coverage_delta = input.immediate_threat.clamp(0.0, 1.0)
        * uncovered_without_player
        * (candidate.pressure_coverage.clamp(0.0, 1.0)
            - current_candidate.pressure_coverage.clamp(0.0, 1.0));
    let pair_delta = input
        .players
        .iter()
        .enumerate()
        .filter(|(other_index, _)| *other_index != player_index)
        .filter_map(|(other_index, other)| {
            other
                .candidates
                .get(selections[other_index])
                .copied()
                .map(|other_candidate| {
                    pair_candidate_penalty(
                        player,
                        candidate,
                        *other,
                        other_candidate,
                        scale,
                        compactness,
                    ) - pair_candidate_penalty(
                        player,
                        current_candidate,
                        *other,
                        other_candidate,
                        scale,
                        compactness,
                    )
                })
        })
        .sum::<f64>();

    current_objective + local_delta + coverage_delta - pair_delta
}

pub fn coordinate_team_defense_into(
    input: &TeamDefenseAssignmentInput<'_>,
    assignments: &mut [TeamDefenseAssignment],
) -> TeamDefenseCoordinationSummary {
    assert!(
        input.players.len() <= MAX_FIXED_TEAM_DEFENSE_PLAYERS,
        "fixed defense coordination supports eleven players"
    );
    assert!(
        assignments.len() >= input.players.len(),
        "fixed defense assignment output is too small"
    );
    let player_count = input.players.len();
    let scale = formation_scale_fixed(input.players);
    let mut selections = [0usize; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
    for (index, player) in input.players.iter().enumerate() {
        selections[index] = player
            .candidates
            .iter()
            .enumerate()
            .max_by(|(_, left), (_, right)| {
                left.local_value
                    .partial_cmp(&right.local_value)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .map(|(candidate_index, _)| candidate_index)
            .unwrap_or(0);
    }

    let maximum_sweeps = player_count.saturating_mul(2).max(1);
    for _ in 0..maximum_sweeps {
        let mut changed = false;
        let mut current_objective = selection_objective(input, &selections[..player_count], scale);
        for player_index in 0..player_count {
            let candidate_count = input.players[player_index].candidates.len();
            if candidate_count == 0 {
                continue;
            }
            let current_index = selections[player_index];
            let mut best_index = current_index;
            let mut best_value = current_objective;
            for candidate_index in 0..candidate_count {
                if candidate_index == current_index {
                    continue;
                }
                let candidate_value = selection_objective_after_change(
                    input,
                    &selections[..player_count],
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                );
                if candidate_value > best_value + 1e-9 {
                    best_index = candidate_index;
                    best_value = candidate_value;
                }
            }
            selections[player_index] = best_index;
            changed |= best_index != current_index;
            current_objective = best_value;
        }
        if !changed {
            break;
        }
    }

    let objective = selection_objective(input, &selections[..player_count], scale);
    for (player_index, player) in input.players.iter().enumerate() {
        let candidate_index = selections[player_index];
        let candidate =
            player
                .candidates
                .get(candidate_index)
                .copied()
                .unwrap_or(TeamDefenseCandidate {
                    target: player.anchor,
                    projected_pos: player.anchor,
                    local_value: 0.0,
                    residual_threat: 1.0,
                    pressure_coverage: 0.0,
                    task_kind: DefenseTaskKind::RecoverShape,
                });
        assignments[player_index] = TeamDefenseAssignment {
            index: player.index,
            candidate_index,
            local_value: candidate.local_value,
            residual_threat: candidate.residual_threat,
        };
    }
    TeamDefenseCoordinationSummary {
        objective,
        formation_scale: scale,
    }
}

pub fn coordinate_team_defense(
    input: &TeamDefenseAssignmentInput<'_>,
) -> TeamDefenseAssignmentOutput {
    let scale = formation_scale(input.players);
    let mut selections = input
        .players
        .iter()
        .map(|player| {
            player
                .candidates
                .iter()
                .enumerate()
                .max_by(|(_, left), (_, right)| {
                    left.local_value
                        .partial_cmp(&right.local_value)
                        .unwrap_or(std::cmp::Ordering::Equal)
                })
                .map(|(index, _)| index)
                .unwrap_or(0)
        })
        .collect::<Vec<_>>();

    let maximum_sweeps = input.players.len().saturating_mul(2).max(1);
    for _ in 0..maximum_sweeps {
        let mut changed = false;
        let mut current_objective = selection_objective(input, &selections, scale);
        for player_index in 0..input.players.len() {
            let candidate_count = input.players[player_index].candidates.len();
            if candidate_count == 0 {
                continue;
            }
            let current_index = selections[player_index];
            let mut best_index = current_index;
            let mut best_value = current_objective;
            for candidate_index in 0..candidate_count {
                if candidate_index == current_index {
                    continue;
                }
                let candidate_value = selection_objective_after_change(
                    input,
                    &selections,
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                );
                if candidate_value > best_value + 1e-9 {
                    best_index = candidate_index;
                    best_value = candidate_value;
                }
            }
            selections[player_index] = best_index;
            changed |= best_index != current_index;
            current_objective = best_value;
        }
        if !changed {
            break;
        }
    }

    let objective = selection_objective(input, &selections, scale);
    let assignments =
        input
            .players
            .iter()
            .zip(selections)
            .map(|(player, candidate_index)| {
                let candidate = player.candidates.get(candidate_index).copied().unwrap_or(
                    TeamDefenseCandidate {
                        target: player.anchor,
                        projected_pos: player.anchor,
                        local_value: 0.0,
                        residual_threat: 1.0,
                        pressure_coverage: 0.0,
                        task_kind: DefenseTaskKind::RecoverShape,
                    },
                );
                TeamDefenseAssignment {
                    index: player.index,
                    candidate_index,
                    local_value: candidate.local_value,
                    residual_threat: candidate.residual_threat,
                }
            })
            .collect();
    TeamDefenseAssignmentOutput {
        assignments,
        objective,
        formation_scale: scale,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        coordinate_team_defense, coordinate_team_defense_into, formation_scale,
        selection_objective, selection_objective_after_change, DefenseTaskKind,
        TeamDefenseAssignment, TeamDefenseAssignmentInput, TeamDefenseCandidate,
        TeamDefensePlayerInput, MAX_FIXED_TEAM_DEFENSE_PLAYERS,
    };

    fn candidate(
        target: (f64, f64),
        projected_pos: (f64, f64),
        local_value: f64,
        task_kind: DefenseTaskKind,
    ) -> TeamDefenseCandidate {
        TeamDefenseCandidate {
            target,
            projected_pos,
            local_value,
            residual_threat: 0.2,
            pressure_coverage: 0.0,
            task_kind,
        }
    }

    #[test]
    fn coordinates_a_single_press_without_collapsing_the_line() {
        let left = [
            candidate((58.0, 34.0), (46.0, 31.0), 1.10, DefenseTaskKind::Press),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let center = [
            candidate((58.0, 34.0), (47.0, 34.0), 1.04, DefenseTaskKind::Press),
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            candidate((58.0, 34.0), (46.0, 37.0), 0.98, DefenseTaskKind::Press),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.7,
            immediate_threat: 0.0,
        });
        let press_count = output
            .assignments
            .iter()
            .filter(|assignment| assignment.candidate_index == 0)
            .count();

        assert_eq!(press_count, 1);
        assert!(output.formation_scale > 1.0);
    }

    #[test]
    fn fixed_buffer_coordination_matches_vec_api() {
        let left = [
            candidate((58.0, 34.0), (46.0, 31.0), 1.10, DefenseTaskKind::Press),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 26.0), (46.0, 26.0), 0.82, DefenseTaskKind::BlockLane),
        ];
        let center = [
            candidate((58.0, 34.0), (47.0, 34.0), 1.04, DefenseTaskKind::Press),
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 34.0), (46.0, 34.0), 0.76, DefenseTaskKind::BlockLane),
        ];
        let right = [
            candidate((58.0, 34.0), (46.0, 37.0), 0.98, DefenseTaskKind::Press),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.48,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((54.0, 42.0), (46.0, 42.0), 0.80, DefenseTaskKind::Mark),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];
        let input = TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.7,
            immediate_threat: 0.62,
        };
        let vec_output = coordinate_team_defense(&input);
        let mut fixed_assignments = [TeamDefenseAssignment {
            index: 0,
            candidate_index: 0,
            local_value: 0.0,
            residual_threat: 0.0,
        }; MAX_FIXED_TEAM_DEFENSE_PLAYERS];
        let fixed_summary =
            coordinate_team_defense_into(&input, &mut fixed_assignments[..players.len()]);

        assert_eq!(
            fixed_assignments[..players.len()]
                .iter()
                .map(|assignment| assignment.index)
                .collect::<Vec<_>>(),
            vec_output
                .assignments
                .iter()
                .map(|assignment| assignment.index)
                .collect::<Vec<_>>()
        );
        assert_eq!(
            fixed_assignments[..players.len()]
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec_output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>()
        );
        for (fixed, allocated) in fixed_assignments[..players.len()]
            .iter()
            .zip(&vec_output.assignments)
        {
            assert_eq!(fixed.local_value, allocated.local_value);
            assert_eq!(fixed.residual_threat, allocated.residual_threat);
        }
        assert_eq!(fixed_summary.objective, vec_output.objective);
        assert_eq!(fixed_summary.formation_scale, vec_output.formation_scale);
    }

    #[test]
    fn preserves_separate_marks_when_their_threat_targets_are_distinct() {
        let left = [
            candidate((55.0, 18.0), (47.0, 19.0), 1.00, DefenseTaskKind::Mark),
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.30,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            candidate((55.0, 50.0), (47.0, 49.0), 0.98, DefenseTaskKind::Mark),
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.30,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.55,
            immediate_threat: 0.0,
        });

        assert_eq!(
            output
                .assignments
                .iter()
                .map(|assignment| assignment.candidate_index)
                .collect::<Vec<_>>(),
            vec![0, 0]
        );
    }

    #[test]
    fn assigns_one_reachable_press_when_immediate_threat_requires_coverage() {
        let left = [
            TeamDefenseCandidate {
                target: (56.0, 32.0),
                projected_pos: (48.0, 31.0),
                local_value: 0.48,
                residual_threat: 0.5,
                pressure_coverage: 0.68,
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            TeamDefenseCandidate {
                target: (56.0, 36.0),
                projected_pos: (48.0, 37.0),
                local_value: 0.47,
                residual_threat: 0.5,
                pressure_coverage: 0.66,
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];

        let output = coordinate_team_defense(&TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.65,
            immediate_threat: 0.90,
        });
        let press_count = output
            .assignments
            .iter()
            .filter(|assignment| assignment.candidate_index == 0)
            .count();

        assert_eq!(press_count, 1);
    }

    #[test]
    fn incremental_objective_matches_full_objective_for_each_candidate_swap() {
        let left = [
            TeamDefenseCandidate {
                target: (56.0, 32.0),
                projected_pos: (48.0, 31.0),
                local_value: 0.48,
                residual_threat: 0.5,
                pressure_coverage: 0.68,
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 22.0),
                (40.0, 22.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((50.0, 26.0), (45.0, 25.0), 0.52, DefenseTaskKind::Mark),
        ];
        let center = [
            TeamDefenseCandidate {
                target: (56.0, 34.0),
                projected_pos: (49.0, 34.0),
                local_value: 0.46,
                residual_threat: 0.48,
                pressure_coverage: 0.71,
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 34.0),
                (40.0, 34.0),
                0.55,
                DefenseTaskKind::RecoverShape,
            ),
        ];
        let right = [
            TeamDefenseCandidate {
                target: (56.0, 36.0),
                projected_pos: (48.0, 37.0),
                local_value: 0.47,
                residual_threat: 0.5,
                pressure_coverage: 0.66,
                task_kind: DefenseTaskKind::Press,
            },
            candidate(
                (40.0, 46.0),
                (40.0, 46.0),
                0.56,
                DefenseTaskKind::RecoverShape,
            ),
            candidate((50.0, 42.0), (45.0, 43.0), 0.51, DefenseTaskKind::BlockLane),
        ];
        let players = [
            TeamDefensePlayerInput {
                index: 0,
                anchor: (40.0, 22.0),
                candidates: &left,
            },
            TeamDefensePlayerInput {
                index: 1,
                anchor: (40.0, 34.0),
                candidates: &center,
            },
            TeamDefensePlayerInput {
                index: 2,
                anchor: (40.0, 46.0),
                candidates: &right,
            },
        ];
        let input = TeamDefenseAssignmentInput {
            players: &players,
            compactness: 0.65,
            immediate_threat: 0.90,
        };
        let selections = [1, 0, 2];
        let scale = formation_scale(&players);
        let current_objective = selection_objective(&input, &selections, scale);

        for (player_index, player) in players.iter().enumerate() {
            for candidate_index in 0..player.candidates.len() {
                let incremental = selection_objective_after_change(
                    &input,
                    &selections,
                    scale,
                    current_objective,
                    player_index,
                    candidate_index,
                );
                let mut changed = selections;
                changed[player_index] = candidate_index;
                let full = selection_objective(&input, &changed, scale);
                assert!(
                    (incremental - full).abs() <= 1e-10,
                    "player={player_index}, candidate={candidate_index}, incremental={incremental}, full={full}"
                );
            }
        }
    }
}
