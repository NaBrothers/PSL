use crate::physics::{angle_between_points, angle_diff, distance, smoothstep};

#[derive(Clone, Copy, Debug)]
pub struct PossessionControlState {
    pub facing_direction: f64,
    pub pressure_load: f64,
    pub containment_load: f64,
    pub forward_control: f64,
    pub turn_readiness: f64,
    pub release_window: f64,
    pub shape_readiness: f64,
    pub release_preparation: f64,
    pub stagnation_load: f64,
}

impl Default for PossessionControlState {
    fn default() -> Self {
        Self {
            facing_direction: 0.0,
            pressure_load: 0.0,
            containment_load: 0.0,
            forward_control: 1.0,
            turn_readiness: 1.0,
            release_window: 1.0,
            shape_readiness: 1.0,
            release_preparation: 1.0,
            stagnation_load: 0.0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct PossessionControlObservation<'a> {
    pub controller_index: usize,
    pub controller_pos: (f64, f64),
    pub teammate_positions: &'a [(usize, f64, f64)],
    pub teammate_goalkeeper_indices: &'a [usize],
    pub opponent_positions: &'a [(f64, f64)],
    pub pitch_length: f64,
    pub pitch_width: f64,
    pub attacking_right: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct PossessionControlTransitionInput<'a> {
    pub previous: PossessionControlState,
    pub observation: PossessionControlObservation<'a>,
    pub arrival_heading: f64,
    pub ownership_continuity: f64,
    pub contact_load: f64,
    pub settling_ticks: i32,
    pub movement_distance: f64,
    pub turn_target: Option<f64>,
}

#[derive(Clone, Copy)]
struct PossessionControlFeatures {
    pressure: f64,
    forward_space: f64,
    release_window: f64,
    shape_readiness: f64,
}

fn local_pressure(pos: (f64, f64), opponents: &[(f64, f64)]) -> f64 {
    let unavailable_probability = opponents.iter().fold(1.0, |remaining, opponent| {
        let separation = distance(pos, *opponent);
        let immediate_control_access = (1.0 - separation / 8.0).max(0.0);
        remaining * (1.0 - immediate_control_access)
    });
    (1.0 - unavailable_probability).clamp(0.0, 1.0)
}

fn team_shape_readiness(observation: PossessionControlObservation<'_>) -> f64 {
    let mut min_x = observation.controller_pos.0;
    let mut max_x = observation.controller_pos.0;
    let mut min_y = observation.controller_pos.1;
    let mut max_y = observation.controller_pos.1;
    let mut local_crowding = 0.0;
    let mut field_player_count = 0;
    for (index, x, y) in observation.teammate_positions {
        if *index == observation.controller_index
            || observation.teammate_goalkeeper_indices.contains(index)
        {
            continue;
        }
        field_player_count += 1;
        let teammate = (*x, *y);
        min_x = min_x.min(teammate.0);
        max_x = max_x.max(teammate.0);
        min_y = min_y.min(teammate.1);
        max_y = max_y.max(teammate.1);
        let separation = distance(observation.controller_pos, teammate);
        local_crowding += (1.0 - separation / 12.0).max(0.0);
    }
    if field_player_count == 0 {
        return 0.0;
    }

    let longitudinal_span = (max_x - min_x) / observation.pitch_length.max(1.0);
    let lateral_span = (max_y - min_y) / observation.pitch_width.max(1.0);
    let width = smoothstep(0.16, 0.42, lateral_span);
    let depth = smoothstep(0.18, 0.52, longitudinal_span);
    let crowding_relief = 1.0 / (1.0 + local_crowding * 0.42);
    (0.38 * width + 0.42 * depth + 0.20 * crowding_relief).clamp(0.0, 1.0)
}

fn forward_space(observation: PossessionControlObservation<'_>) -> f64 {
    let forward_direction = if observation.attacking_right {
        1.0
    } else {
        -1.0
    };
    let corridor_density = observation
        .opponent_positions
        .iter()
        .map(|opponent| {
            let longitudinal = (opponent.0 - observation.controller_pos.0) * forward_direction;
            let lateral = (opponent.1 - observation.controller_pos.1).abs();
            let ahead =
                smoothstep(-2.0, 4.0, longitudinal) * (1.0 - smoothstep(10.0, 28.0, longitudinal));
            let corridor = (-lateral / 8.0).exp();
            ahead * corridor
        })
        .sum::<f64>();
    (-corridor_density).exp().clamp(0.0, 1.0)
}

fn release_window(
    observation: PossessionControlObservation<'_>,
    facing_direction: f64,
    source_pressure: f64,
) -> f64 {
    let mut unavailable_probability = 1.0;
    for (index, x, y) in observation.teammate_positions {
        if *index == observation.controller_index {
            continue;
        }
        let target = (*x, *y);
        let separation = distance(observation.controller_pos, target);
        let range = smoothstep(2.0, 5.0, separation) * (1.0 - smoothstep(42.0, 58.0, separation));
        let target_pressure = local_pressure(target, observation.opponent_positions);
        let target_angle = angle_between_points(observation.controller_pos, target);
        let angle_access =
            0.38 + 0.62 * (1.0 - angle_diff(facing_direction, target_angle).abs() / 180.0);
        let route_control = (0.42 + 0.58 * (1.0 - source_pressure)) * (1.0 - target_pressure);
        let outlet = (range * angle_access * route_control).clamp(0.0, 1.0);
        unavailable_probability *= 1.0 - outlet;
    }
    (1.0 - unavailable_probability).clamp(0.0, 1.0)
}

fn control_features(
    observation: PossessionControlObservation<'_>,
    facing_direction: f64,
) -> PossessionControlFeatures {
    let pressure = local_pressure(observation.controller_pos, observation.opponent_positions);
    PossessionControlFeatures {
        pressure,
        forward_space: forward_space(observation),
        release_window: release_window(observation, facing_direction, pressure),
        shape_readiness: team_shape_readiness(observation),
    }
}

fn blend_heading(previous_heading: f64, previous_weight: f64, arrival_heading: f64) -> f64 {
    let previous_radians = previous_heading.to_radians();
    let arrival_radians = arrival_heading.to_radians();
    let x = previous_weight * previous_radians.cos() + arrival_radians.cos();
    let y = previous_weight * previous_radians.sin() + arrival_radians.sin();
    y.atan2(x).to_degrees()
}

pub fn reorient_control_heading(
    state: PossessionControlState,
    target_heading: f64,
    mobility: f64,
    elapsed_ticks: i32,
) -> f64 {
    let remaining_turn = angle_diff(state.facing_direction, target_heading);
    let turn_capacity = (34.0 + 66.0 * mobility.clamp(0.0, 1.0))
        * elapsed_ticks.max(1) as f64
        * (0.42 + 0.58 * (1.0 - state.pressure_load))
        * (0.58 + 0.42 * state.turn_readiness);
    (state.facing_direction + remaining_turn.clamp(-turn_capacity, turn_capacity)).rem_euclid(360.0)
}

pub fn observe_possession_control(
    observation: PossessionControlObservation<'_>,
    facing_direction: f64,
) -> PossessionControlState {
    let features = control_features(observation, facing_direction);
    let attacking_heading = if observation.attacking_right {
        0.0
    } else {
        180.0
    };
    let forward_alignment = 1.0 - angle_diff(facing_direction, attacking_heading).abs() / 180.0;
    let pressure_relief = 1.0 - features.pressure;
    PossessionControlState {
        facing_direction,
        pressure_load: features.pressure,
        containment_load: 0.0,
        forward_control: (features.forward_space
            * (0.30 + 0.70 * forward_alignment)
            * (0.40 + 0.60 * pressure_relief))
            .clamp(0.0, 1.0),
        turn_readiness: (pressure_relief
            * (0.36 + 0.34 * features.release_window + 0.30 * features.shape_readiness))
            .clamp(0.0, 1.0),
        release_window: features.release_window,
        shape_readiness: features.shape_readiness,
        release_preparation: (forward_alignment * (0.42 + 0.58 * pressure_relief)).clamp(0.0, 1.0),
        stagnation_load: 0.0,
    }
}

pub fn transition_possession_control(
    input: &PossessionControlTransitionInput<'_>,
) -> PossessionControlState {
    let continuity = input.ownership_continuity.clamp(0.0, 1.0);
    let elapsed_ticks = input.settling_ticks.max(1);
    let settling = 1.0 - (-0.45 * elapsed_ticks as f64).exp();
    let retained_memory = continuity * (1.0 - settling);
    let facing_direction = input.turn_target.map_or_else(
        || {
            blend_heading(
                input.previous.facing_direction,
                0.45 * continuity,
                input.arrival_heading,
            )
        },
        |target_heading| {
            reorient_control_heading(
                input.previous,
                target_heading,
                (0.36 + 0.64 * input.previous.turn_readiness).clamp(0.0, 1.0),
                elapsed_ticks,
            )
        },
    );
    let features = control_features(input.observation, facing_direction);
    let containment_load = (input.previous.containment_load * retained_memory
        + input.contact_load.clamp(0.0, 1.0) * (0.52 + 0.48 * continuity))
        .clamp(0.0, 1.0);
    let pressure_load = (features.pressure
        + input.previous.pressure_load * retained_memory * 0.34
        + containment_load * 0.58)
        .clamp(0.0, 1.0);
    let attacking_heading = if input.observation.attacking_right {
        0.0
    } else {
        180.0
    };
    let forward_alignment = 1.0 - angle_diff(facing_direction, attacking_heading).abs() / 180.0;
    let pressure_relief = 1.0 - pressure_load;
    let turn_readiness = (pressure_relief
        * (0.34 + 0.36 * features.release_window + 0.30 * features.shape_readiness)
        * (1.0 - 0.72 * containment_load))
        .clamp(0.0, 1.0);
    let forward_control = (features.forward_space
        * (0.28 + 0.72 * forward_alignment)
        * (0.34 + 0.66 * turn_readiness)
        * (1.0 - 0.58 * containment_load))
        .clamp(0.0, 1.0);
    let release_window = (features.release_window
        * (0.42 + 0.58 * pressure_relief)
        * (1.0 - 0.38 * containment_load))
        .clamp(0.0, 1.0);
    let movement_refresh = 1.0 - (-input.movement_distance.max(0.0) / 1.8).exp();
    let structure_refresh = ((features.release_window - input.previous.release_window).max(0.0)
        * 0.58
        + (features.shape_readiness - input.previous.shape_readiness).max(0.0) * 0.42)
        .clamp(0.0, 1.0);
    let preparation_alignment = input.turn_target.map_or(forward_alignment, |target| {
        1.0 - angle_diff(facing_direction, target).abs() / 180.0
    });
    let previous_preparation_alignment = input.turn_target.map_or(forward_alignment, |target| {
        1.0 - angle_diff(input.previous.facing_direction, target).abs() / 180.0
    });
    let reorientation_progress = (preparation_alignment - previous_preparation_alignment).max(0.0);
    let purposeful_reorientation = input
        .turn_target
        .map(|_| preparation_alignment)
        .unwrap_or(0.0);
    let exposure_duration = 1.0 - (-0.32 * elapsed_ticks as f64).exp();
    let stagnant_control = continuity
        * exposure_duration
        * (1.0 - movement_refresh)
        * (1.0 - structure_refresh)
        * (1.0 - 0.62 * purposeful_reorientation);
    let stagnation_relief = (0.72 * movement_refresh + 0.46 * structure_refresh).clamp(0.0, 1.0);
    let stagnation_load = (input.previous.stagnation_load * (1.0 - stagnation_relief)
        + (1.0 - input.previous.stagnation_load) * stagnant_control)
        .clamp(0.0, 1.0);
    let baseline_preparation =
        (preparation_alignment * (0.34 + 0.66 * pressure_relief) * (1.0 - 0.32 * containment_load))
            .clamp(0.0, 1.0);
    let preparation_decay =
        (0.10 * exposure_duration + 0.24 * containment_load + 0.20 * stagnation_load)
            .clamp(0.0, 0.72);
    let retained_preparation =
        input.previous.release_preparation * retained_memory * (1.0 - preparation_decay);
    let reorientation_gain =
        reorientation_progress * (0.34 + 0.66 * pressure_relief) * (1.0 - 0.28 * containment_load);
    let release_preparation = (retained_preparation
        + (1.0 - retained_memory) * baseline_preparation
        + (1.0 - input.previous.release_preparation) * reorientation_gain)
        .clamp(0.0, 1.0);

    PossessionControlState {
        facing_direction,
        pressure_load,
        containment_load,
        forward_control,
        turn_readiness,
        release_window,
        shape_readiness: features.shape_readiness,
        release_preparation,
        stagnation_load,
    }
}

pub fn shot_release_readiness(state: PossessionControlState) -> f64 {
    let stagnation_impact = state.stagnation_load.powf(4.0);
    (state.turn_readiness * (1.0 - 0.45 * state.containment_load))
        * (0.45 + 0.55 * state.release_preparation)
        * (1.0 - 0.28 * stagnation_impact).clamp(0.0, 1.0)
}

pub fn continuation_control_readiness(state: PossessionControlState) -> f64 {
    let stagnation_impact = state.stagnation_load.powf(4.0);
    ((0.22
        + 0.34 * state.release_window
        + 0.24 * state.turn_readiness
        + 0.20 * state.shape_readiness)
        * (1.0 - 0.48 * state.containment_load)
        * (1.0 - 0.62 * stagnation_impact)
        * (0.35 + 0.65 * state.release_preparation)
        * (0.42 + 0.58 * (1.0 - state.pressure_load)))
        .clamp(0.0, 1.0)
}

pub fn directional_control_readiness(state: PossessionControlState, target_heading: f64) -> f64 {
    let continuation = continuation_control_readiness(state);
    let turn_demand =
        (angle_diff(state.facing_direction, target_heading).abs() / 180.0).clamp(0.0, 1.0);
    let turn_access = 1.0
        - turn_demand
            * (1.0
                - 0.75
                    * state.turn_readiness.clamp(0.0, 1.0)
                    * (1.0 - 0.45 * state.containment_load));
    (continuation * turn_access).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::{
        angle_diff, directional_control_readiness, observe_possession_control,
        shot_release_readiness, team_shape_readiness, transition_possession_control,
        PossessionControlObservation, PossessionControlState, PossessionControlTransitionInput,
    };
    use crate::physics::{distance, smoothstep};

    fn allocated_team_shape_readiness_reference(
        observation: PossessionControlObservation<'_>,
    ) -> f64 {
        let field_players = observation
            .teammate_positions
            .iter()
            .filter(|(index, _, _)| {
                *index != observation.controller_index
                    && !observation.teammate_goalkeeper_indices.contains(index)
            })
            .map(|(_, x, y)| (*x, *y))
            .collect::<Vec<_>>();
        if field_players.is_empty() {
            return 0.0;
        }

        let mut min_x = observation.controller_pos.0;
        let mut max_x = observation.controller_pos.0;
        let mut min_y = observation.controller_pos.1;
        let mut max_y = observation.controller_pos.1;
        let mut local_crowding = 0.0;
        for teammate in field_players {
            min_x = min_x.min(teammate.0);
            max_x = max_x.max(teammate.0);
            min_y = min_y.min(teammate.1);
            max_y = max_y.max(teammate.1);
            let separation = distance(observation.controller_pos, teammate);
            local_crowding += (1.0 - separation / 12.0).max(0.0);
        }

        let longitudinal_span = (max_x - min_x) / observation.pitch_length.max(1.0);
        let lateral_span = (max_y - min_y) / observation.pitch_width.max(1.0);
        let width = smoothstep(0.16, 0.42, lateral_span);
        let depth = smoothstep(0.18, 0.52, longitudinal_span);
        let crowding_relief = 1.0 / (1.0 + local_crowding * 0.42);
        (0.38 * width + 0.42 * depth + 0.20 * crowding_relief).clamp(0.0, 1.0)
    }

    #[test]
    fn stack_shape_readiness_matches_allocated_reference_bit_for_bit() {
        let teammates = [
            (0, 50.0, 34.0),
            (1, 24.0, 12.0),
            (2, 36.0, 54.0),
            (3, 58.0, 22.0),
            (4, 72.0, 48.0),
            (5, 8.0, 34.0),
        ];
        let goalkeepers = [5];
        let observation = PossessionControlObservation {
            controller_index: 0,
            controller_pos: (50.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &goalkeepers,
            opponent_positions: &[],
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        };

        assert_eq!(
            team_shape_readiness(observation).to_bits(),
            allocated_team_shape_readiness_reference(observation).to_bits()
        );
    }

    #[test]
    fn containment_reduces_forward_and_shoot_control_in_the_same_shape() {
        let teammates = [
            (1, 34.0, 17.0),
            (2, 38.0, 52.0),
            (3, 60.0, 24.0),
            (4, 68.0, 43.0),
        ];
        let opponents = [(57.0, 34.0), (66.0, 24.0), (66.0, 44.0)];
        let observation = PossessionControlObservation {
            controller_index: 0,
            controller_pos: (50.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        };
        let initial = observe_possession_control(observation, 0.0);
        let unconstrained = transition_possession_control(&PossessionControlTransitionInput {
            previous: initial,
            observation,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 0.0,
            settling_ticks: 0,
            movement_distance: 0.0,
            turn_target: None,
        });
        let contained = transition_possession_control(&PossessionControlTransitionInput {
            previous: initial,
            observation,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 1.0,
            settling_ticks: 0,
            movement_distance: 0.0,
            turn_target: None,
        });

        assert!(contained.containment_load > unconstrained.containment_load);
        assert!(contained.forward_control < unconstrained.forward_control);
        assert!(contained.turn_readiness < unconstrained.turn_readiness);
        assert!(shot_release_readiness(contained) < shot_release_readiness(unconstrained));
    }

    #[test]
    fn shot_release_is_not_penalized_again_for_the_shot_lane() {
        let body_ready = PossessionControlState {
            facing_direction: 0.0,
            pressure_load: 0.18,
            containment_load: 0.12,
            forward_control: 1.0,
            turn_readiness: 0.78,
            release_window: 0.66,
            shape_readiness: 0.72,
            release_preparation: 0.74,
            stagnation_load: 0.08,
        };
        let blocked_forward_lane = PossessionControlState {
            forward_control: 0.0,
            ..body_ready
        };

        assert!(
            (shot_release_readiness(body_ready) - shot_release_readiness(blocked_forward_lane))
                .abs()
                < 1e-12,
            "body preparation must remain separate from shot-line contest quality"
        );
    }

    #[test]
    fn directional_control_requires_more_turning_capacity_for_a_reverse_carry() {
        let control = PossessionControlState {
            facing_direction: 0.0,
            pressure_load: 0.25,
            containment_load: 0.15,
            forward_control: 0.45,
            turn_readiness: 0.55,
            release_window: 0.60,
            shape_readiness: 0.65,
            release_preparation: 0.58,
            stagnation_load: 0.10,
        };

        let aligned = directional_control_readiness(control, 0.0);
        let lateral = directional_control_readiness(control, 90.0);
        let reverse = directional_control_readiness(control, 180.0);

        assert!(aligned > lateral);
        assert!(lateral > reverse);
    }

    #[test]
    fn unpressured_control_recovers_without_action_specific_overrides() {
        let teammates = [
            (1, 30.0, 16.0),
            (2, 34.0, 52.0),
            (3, 58.0, 22.0),
            (4, 64.0, 46.0),
        ];
        let pressured_opponents = [(52.0, 34.0), (55.0, 31.0), (58.0, 39.0)];
        let relieved_opponents = [(72.0, 16.0), (74.0, 52.0), (80.0, 34.0)];
        let pressured = PossessionControlObservation {
            controller_index: 0,
            controller_pos: (50.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &pressured_opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        };
        let relieved = PossessionControlObservation {
            opponent_positions: &relieved_opponents,
            ..pressured
        };
        let constrained = transition_possession_control(&PossessionControlTransitionInput {
            previous: observe_possession_control(pressured, 0.0),
            observation: pressured,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 1.0,
            settling_ticks: 0,
            movement_distance: 0.0,
            turn_target: None,
        });
        let recovered = transition_possession_control(&PossessionControlTransitionInput {
            previous: constrained,
            observation: relieved,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 0.0,
            settling_ticks: 3,
            movement_distance: 2.4,
            turn_target: None,
        });

        assert!(recovered.containment_load < constrained.containment_load);
        assert!(recovered.forward_control > constrained.forward_control);
        assert!(recovered.release_window > constrained.release_window);
    }

    #[test]
    fn repeated_static_control_accumulates_exposure_until_shape_or_movement_relieve_it() {
        let teammates = [
            (1, 35.0, 18.0),
            (2, 35.0, 50.0),
            (3, 62.0, 25.0),
            (4, 66.0, 43.0),
        ];
        let opponents = [(58.0, 30.0), (61.0, 37.0), (68.0, 24.0)];
        let observation = PossessionControlObservation {
            controller_index: 0,
            controller_pos: (54.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        };
        let initial = observe_possession_control(observation, 180.0);
        let static_once = transition_possession_control(&PossessionControlTransitionInput {
            previous: initial,
            observation,
            arrival_heading: 180.0,
            ownership_continuity: 1.0,
            contact_load: 0.0,
            settling_ticks: 1,
            movement_distance: 0.0,
            turn_target: None,
        });
        let static_twice = transition_possession_control(&PossessionControlTransitionInput {
            previous: static_once,
            observation,
            arrival_heading: 180.0,
            ownership_continuity: 1.0,
            contact_load: 0.0,
            settling_ticks: 1,
            movement_distance: 0.0,
            turn_target: None,
        });
        let relieved = transition_possession_control(&PossessionControlTransitionInput {
            previous: static_twice,
            observation,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 0.0,
            settling_ticks: 1,
            movement_distance: 2.5,
            turn_target: Some(0.0),
        });

        assert!(static_twice.stagnation_load > static_once.stagnation_load);
        assert!(relieved.stagnation_load < static_twice.stagnation_load);
        assert!(
            shot_release_readiness(relieved) > shot_release_readiness(static_twice),
            "a physically executed preparation must improve release availability"
        );
    }

    #[test]
    fn reorientation_progresses_under_pressure_without_instant_heading_change() {
        let teammates = [
            (1, 34.0, 18.0),
            (2, 38.0, 50.0),
            (3, 68.0, 25.0),
            (4, 72.0, 43.0),
        ];
        let opponents = [(52.0, 34.0), (56.0, 30.0), (56.0, 38.0)];
        let observation = PossessionControlObservation {
            controller_index: 0,
            controller_pos: (50.0, 34.0),
            teammate_positions: &teammates,
            teammate_goalkeeper_indices: &[],
            opponent_positions: &opponents,
            pitch_length: 105.0,
            pitch_width: 68.0,
            attacking_right: true,
        };
        let previous = PossessionControlState {
            facing_direction: 180.0,
            pressure_load: 0.72,
            containment_load: 0.30,
            forward_control: 0.15,
            turn_readiness: 0.26,
            release_window: 0.35,
            shape_readiness: 0.42,
            release_preparation: 0.10,
            stagnation_load: 0.15,
        };
        let turned = transition_possession_control(&PossessionControlTransitionInput {
            previous,
            observation,
            arrival_heading: 0.0,
            ownership_continuity: 1.0,
            contact_load: 0.2,
            settling_ticks: 1,
            movement_distance: 0.0,
            turn_target: Some(0.0),
        });

        assert!(angle_diff(previous.facing_direction, turned.facing_direction).abs() > 0.0);
        assert!(angle_diff(turned.facing_direction, 0.0).abs() > 0.0);
        assert!(turned.release_preparation > previous.release_preparation);
    }
}
