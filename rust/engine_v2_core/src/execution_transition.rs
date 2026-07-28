pub const MAX_EXECUTION_TRANSITION_BRANCHES: usize = 64;

#[derive(Clone, Copy, Debug)]
pub struct BinaryExecutionTransition {
    pub success_probability: f64,
    pub failure_probability: f64,
}

impl BinaryExecutionTransition {
    pub fn from_success_probability(success_probability: f64) -> Self {
        let success_probability = success_probability.clamp(0.0, 1.0);
        Self {
            success_probability,
            failure_probability: 1.0 - success_probability,
        }
    }

    pub fn succeeds(self, roll: f64) -> bool {
        roll.clamp(0.0, 1.0) < self.success_probability
    }

    pub fn fails(self, roll: f64) -> bool {
        !self.succeeds(roll)
    }

    pub fn sample(self, roll: f64) -> BinaryExecutionOutcome {
        if self.succeeds(roll) {
            BinaryExecutionOutcome::Success
        } else {
            BinaryExecutionOutcome::Failure
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BinaryExecutionOutcome {
    Success,
    Failure,
}

#[derive(Clone, Copy, Debug)]
pub struct SequentialExecutionTransition {
    pub success_probability: f64,
    pub failure_probability: f64,
}

impl SequentialExecutionTransition {
    pub fn new() -> Self {
        Self {
            success_probability: 1.0,
            failure_probability: 0.0,
        }
    }

    pub fn append(&mut self, transition: BinaryExecutionTransition) -> f64 {
        let failure_mass = self.success_probability * transition.failure_probability;
        self.failure_probability += failure_mass;
        self.success_probability *= transition.success_probability;
        failure_mass
    }
}

impl Default for SequentialExecutionTransition {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct CarryExecutionTransitionMass {
    pub retained_unconstrained: f64,
    pub retained_constrained: f64,
    pub opposing_control: f64,
    pub loose: f64,
}

pub fn carry_execution_transition_mass(
    technical: SequentialExecutionTransition,
    unconstrained_control_probability: f64,
    constrained_control_probability: f64,
    opposing_control_probability: f64,
    unresolved_probability: f64,
) -> CarryExecutionTransitionMass {
    let technical_survival = technical.success_probability.clamp(0.0, 1.0);
    CarryExecutionTransitionMass {
        retained_unconstrained: technical_survival
            * unconstrained_control_probability.clamp(0.0, 1.0),
        retained_constrained: technical_survival * constrained_control_probability.clamp(0.0, 1.0),
        opposing_control: technical_survival * opposing_control_probability.clamp(0.0, 1.0),
        loose: technical.failure_probability.clamp(0.0, 1.0)
            + technical_survival * unresolved_probability.clamp(0.0, 1.0),
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ControlExecutionTransitionMass {
    pub retained: f64,
    pub opposing_control: f64,
    pub contact_loose: f64,
    pub technical_loose: f64,
    pub loose: f64,
}

pub fn control_execution_transition_mass(
    contact_retained_probability: f64,
    contact_opposing_control_probability: f64,
    contact_unresolved_probability: f64,
    error_transition: BinaryExecutionTransition,
) -> ControlExecutionTransitionMass {
    let contact_retained_probability = contact_retained_probability.clamp(0.0, 1.0);
    let contact_loose = contact_unresolved_probability.clamp(0.0, 1.0);
    let technical_loose = contact_retained_probability * error_transition.success_probability;
    ControlExecutionTransitionMass {
        retained: contact_retained_probability * error_transition.failure_probability,
        opposing_control: contact_opposing_control_probability.clamp(0.0, 1.0),
        contact_loose,
        technical_loose,
        loose: contact_loose + technical_loose,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct CarrySegmentTransition {
    pub origin: (f64, f64),
    pub containment: BinaryExecutionTransition,
    pub unconstrained: CarrySegmentBranch,
    pub constrained: CarrySegmentBranch,
}

#[derive(Clone, Copy, Debug)]
pub struct PassActionTransition {
    pub release: crate::interactions::PassReleaseContactTransition,
    pub execution: PassExecutionTransition,
    pub spatial: PassSpatialTransition,
}

#[derive(Clone, Copy, Debug)]
pub struct ControlActionTransition {
    pub contact: crate::interactions::ControlContactTransition,
    pub new_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub facing_direction: Option<f64>,
    pub distance_covered: f64,
    pub pressure: f64,
    pub nearest_dist: f64,
    pub technical_error: BinaryExecutionTransition,
}

#[derive(Clone, Copy, Debug)]
pub struct CarrySegmentBranch {
    pub end_pos: (f64, f64),
    pub control_pos: (f64, f64),
    pub velocity: (f64, f64),
    pub technical_survival: BinaryExecutionTransition,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CarrySegmentSample {
    pub technical_error: bool,
    pub constrained_control: bool,
    pub end_pos: (f64, f64),
    pub control_pos: (f64, f64),
    pub velocity: (f64, f64),
}

impl CarrySegmentTransition {
    pub fn new(
        origin: (f64, f64),
        containment: BinaryExecutionTransition,
        unconstrained_end_pos: (f64, f64),
        unconstrained_control_pos: (f64, f64),
        unconstrained_velocity: (f64, f64),
        constrained_end_pos: (f64, f64),
        constrained_control_pos: (f64, f64),
        constrained_velocity: (f64, f64),
        unconstrained_error_chance: f64,
        constrained_error_chance: f64,
    ) -> Self {
        Self {
            origin,
            containment,
            unconstrained: CarrySegmentBranch {
                end_pos: unconstrained_end_pos,
                control_pos: unconstrained_control_pos,
                velocity: unconstrained_velocity,
                technical_survival: BinaryExecutionTransition::from_success_probability(
                    1.0 - unconstrained_error_chance,
                ),
            },
            constrained: CarrySegmentBranch {
                end_pos: constrained_end_pos,
                control_pos: constrained_control_pos,
                velocity: constrained_velocity,
                technical_survival: BinaryExecutionTransition::from_success_probability(
                    1.0 - constrained_error_chance,
                ),
            },
        }
    }

    pub fn technical_survival(self) -> BinaryExecutionTransition {
        BinaryExecutionTransition::from_success_probability(
            self.containment.failure_probability
                * self.unconstrained.technical_survival.success_probability
                + self.containment.success_probability
                    * self.constrained.technical_survival.success_probability,
        )
    }

    pub fn technical_failure_masses(self) -> (f64, f64) {
        (
            self.containment.failure_probability
                * self.unconstrained.technical_survival.failure_probability,
            self.containment.success_probability
                * self.constrained.technical_survival.failure_probability,
        )
    }

    pub fn projected_surviving_control_pos(self) -> (f64, f64) {
        self.projected_surviving_branch_value(
            self.unconstrained.control_pos,
            self.constrained.control_pos,
        )
    }

    pub fn projected_surviving_velocity(self) -> (f64, f64) {
        self.projected_surviving_branch_value(
            self.unconstrained.velocity,
            self.constrained.velocity,
        )
    }

    fn projected_surviving_branch_value(
        self,
        unconstrained: (f64, f64),
        constrained: (f64, f64),
    ) -> (f64, f64) {
        let unconstrained_mass = self.containment.failure_probability
            * self.unconstrained.technical_survival.success_probability;
        let constrained_mass = self.containment.success_probability
            * self.constrained.technical_survival.success_probability;
        let surviving_mass = unconstrained_mass + constrained_mass;
        if surviving_mass <= 1e-12 {
            return (
                unconstrained.0 * self.containment.failure_probability
                    + constrained.0 * self.containment.success_probability,
                unconstrained.1 * self.containment.failure_probability
                    + constrained.1 * self.containment.success_probability,
            );
        }
        (
            (unconstrained.0 * unconstrained_mass + constrained.0 * constrained_mass)
                / surviving_mass,
            (unconstrained.1 * unconstrained_mass + constrained.1 * constrained_mass)
                / surviving_mass,
        )
    }

    pub fn sample(self, error_roll: f64, containment_roll: f64) -> CarrySegmentSample {
        let constrained_control = self.containment.succeeds(containment_roll);
        let branch = if constrained_control {
            self.constrained
        } else {
            self.unconstrained
        };
        CarrySegmentSample {
            technical_error: error_roll.clamp(0.0, 1.0)
                < branch.technical_survival.failure_probability,
            constrained_control,
            end_pos: branch.end_pos,
            control_pos: branch.control_pos,
            velocity: branch.velocity,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecutionControlSide {
    Retained,
    Opposing,
    Unresolved,
}

#[derive(Clone, Copy, Debug)]
pub struct PassExecutionTransition {
    pub delivery: BinaryExecutionTransition,
    pub first_touch_error: BinaryExecutionTransition,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct PassExecutionTransitionMass {
    pub retained_clean: f64,
    pub opposing_control: f64,
    pub delivery_loose: f64,
    pub first_touch_loose: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassSpatialTransition {
    pub ideal_target: (f64, f64),
    pub successful_delivery_error_radius: f64,
    pub failed_delivery_error_radius: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct PassSpatialSample {
    pub target: (f64, f64),
    pub error_radius: f64,
    pub used_target_error: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct RectangularLooseBallTransition {
    pub center: (f64, f64),
    pub radius_x: f64,
    pub radius_y: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

impl RectangularLooseBallTransition {
    pub fn sample(self, x_roll: f64, y_roll: f64) -> (f64, f64) {
        (
            (self.center.0 + (-self.radius_x + 2.0 * self.radius_x * x_roll.clamp(0.0, 1.0)))
                .clamp(0.5, self.pitch_length - 0.5),
            (self.center.1 + (-self.radius_y + 2.0 * self.radius_y * y_roll.clamp(0.0, 1.0)))
                .clamp(0.5, self.pitch_width - 0.5),
        )
    }

    pub fn quadrature(self) -> [(f64, f64); 4] {
        [
            self.sample(0.25, 0.25),
            self.sample(0.25, 0.75),
            self.sample(0.75, 0.25),
            self.sample(0.75, 0.75),
        ]
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ShotMishitSpatialTransition {
    pub origin: (f64, f64),
    pub intended_target: (f64, f64),
    pub minimum_distance: f64,
    pub maximum_distance: f64,
    pub maximum_angle_radians: f64,
    pub pitch_length: f64,
    pub pitch_width: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotExecutionTransition {
    pub body_release: BinaryExecutionTransition,
    pub released_probability_given_body_release: f64,
    pub blocked_probability_given_body_release: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ShotActionModel {
    pub mishit: ShotMishitSpatialTransition,
}

impl ShotActionModel {
    pub fn new(
        origin: (f64, f64),
        intended_target: (f64, f64),
        contest_radius: f64,
        pitch_length: f64,
        pitch_width: f64,
    ) -> Self {
        Self {
            mishit: ShotMishitSpatialTransition::from_contest_geometry(
                origin,
                intended_target,
                contest_radius,
                pitch_length,
                pitch_width,
            ),
        }
    }

    pub fn condition(
        self,
        body_release_probability: f64,
        release_probability: f64,
        block_probability: f64,
    ) -> ShotExecutionTransition {
        ShotExecutionTransition::new(
            body_release_probability,
            release_probability,
            block_probability,
        )
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ShotExecutionTransitionMass {
    pub unreleased: f64,
    pub blocked: f64,
    pub released: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShotExecutionOutcome {
    Unreleased,
    Blocked,
    Released,
}

impl ShotExecutionTransition {
    pub fn new(
        body_release_probability: f64,
        release_probability: f64,
        block_probability: f64,
    ) -> Self {
        let declared_release_probability = release_probability.clamp(0.0, 1.0);
        let declared_block_probability = block_probability.clamp(0.0, 1.0);
        let contest_probability_mass = declared_release_probability + declared_block_probability;
        let (released_probability_given_body_release, blocked_probability_given_body_release) =
            if contest_probability_mass > 1e-9 {
                (
                    declared_release_probability / contest_probability_mass,
                    declared_block_probability / contest_probability_mass,
                )
            } else {
                (1.0, 0.0)
            };
        Self {
            body_release: BinaryExecutionTransition::from_success_probability(
                body_release_probability,
            ),
            released_probability_given_body_release,
            blocked_probability_given_body_release,
        }
    }

    pub fn mass(self) -> ShotExecutionTransitionMass {
        ShotExecutionTransitionMass {
            unreleased: self.body_release.failure_probability,
            blocked: self.body_release.success_probability
                * self.blocked_probability_given_body_release,
            released: self.body_release.success_probability
                * self.released_probability_given_body_release,
        }
    }

    pub fn sample(self, body_release_roll: f64, contest_roll: f64) -> ShotExecutionOutcome {
        if self.body_release.fails(body_release_roll) {
            ShotExecutionOutcome::Unreleased
        } else if contest_roll.clamp(0.0, 1.0) < self.blocked_probability_given_body_release {
            ShotExecutionOutcome::Blocked
        } else {
            ShotExecutionOutcome::Released
        }
    }
}

impl ShotMishitSpatialTransition {
    pub fn from_contest_geometry(
        origin: (f64, f64),
        intended_target: (f64, f64),
        contest_radius: f64,
        pitch_length: f64,
        pitch_width: f64,
    ) -> Self {
        let contest_radius = contest_radius.max(0.1);
        Self {
            origin,
            intended_target,
            minimum_distance: contest_radius + 0.25,
            maximum_distance: contest_radius + 2.0,
            maximum_angle_radians: std::f64::consts::PI,
            pitch_length,
            pitch_width,
        }
    }

    pub fn sample(self, angle_roll: f64, distance_roll: f64) -> (f64, f64) {
        let target_dx = self.intended_target.0 - self.origin.0;
        let target_dy = self.intended_target.1 - self.origin.1;
        let target_norm = (target_dx * target_dx + target_dy * target_dy).sqrt();
        let base_heading = if target_norm > 1e-9 {
            target_dy.atan2(target_dx)
        } else {
            0.0
        };
        let angle = base_heading
            + (-self.maximum_angle_radians
                + 2.0 * self.maximum_angle_radians * angle_roll.clamp(0.0, 1.0));
        let distance = self.minimum_distance.max(0.0)
            + (self.maximum_distance.max(self.minimum_distance) - self.minimum_distance.max(0.0))
                * distance_roll.clamp(0.0, 1.0);
        (
            (self.origin.0 + angle.cos() * distance).clamp(0.5, self.pitch_length - 0.5),
            (self.origin.1 + angle.sin() * distance).clamp(0.5, self.pitch_width - 0.5),
        )
    }

    pub fn quadrature(self) -> [(f64, f64); 4] {
        [
            self.sample(0.25, 0.25),
            self.sample(0.25, 0.75),
            self.sample(0.75, 0.25),
            self.sample(0.75, 0.75),
        ]
    }
}

impl PassSpatialTransition {
    pub fn new(
        passer_pos: (f64, f64),
        ideal_target: (f64, f64),
        passing: f64,
        pitch_length: f64,
        pitch_width: f64,
    ) -> Self {
        let distance = ((ideal_target.0 - passer_pos.0).powi(2)
            + (ideal_target.1 - passer_pos.1).powi(2))
        .sqrt();
        let ability_factor = (passing / 100.0).clamp(0.0, 1.0);
        let successful_delivery_error_radius = (1.0 - ability_factor) * (1.2 + distance / 12.0);
        Self {
            ideal_target,
            successful_delivery_error_radius,
            failed_delivery_error_radius: successful_delivery_error_radius
                * (1.85 + (distance / 90.0).min(0.45)),
            pitch_length,
            pitch_width,
        }
    }

    pub fn error_radius(self, delivery_succeeded: bool) -> f64 {
        if delivery_succeeded {
            self.successful_delivery_error_radius
        } else {
            self.failed_delivery_error_radius
        }
    }

    pub fn sample(
        self,
        delivery_succeeded: bool,
        angle_roll: f64,
        radius_roll: f64,
    ) -> PassSpatialSample {
        let error_radius = self.error_radius(delivery_succeeded);
        let used_target_error = error_radius > 0.05;
        let target = if used_target_error {
            let angle = angle_roll.clamp(0.0, 1.0) * std::f64::consts::TAU;
            let magnitude = radius_roll.clamp(0.0, 1.0) * error_radius;
            (
                self.ideal_target.0 + angle.cos() * magnitude,
                self.ideal_target.1 + angle.sin() * magnitude,
            )
        } else {
            self.ideal_target
        };
        PassSpatialSample {
            target: (
                target.0.clamp(0.5, self.pitch_length - 0.5),
                target.1.clamp(0.5, self.pitch_width - 0.5),
            ),
            error_radius,
            used_target_error,
        }
    }

    pub fn quadrature(self, delivery_succeeded: bool) -> [PassSpatialSample; 4] {
        [
            self.sample(delivery_succeeded, 0.125, 0.5),
            self.sample(delivery_succeeded, 0.375, 0.5),
            self.sample(delivery_succeeded, 0.625, 0.5),
            self.sample(delivery_succeeded, 0.875, 0.5),
        ]
    }
}

impl PassExecutionTransition {
    pub fn new(retention_probability: f64, first_touch_error_probability: f64) -> Self {
        Self {
            delivery: BinaryExecutionTransition::from_success_probability(retention_probability),
            first_touch_error: BinaryExecutionTransition::from_success_probability(
                first_touch_error_probability,
            ),
        }
    }

    pub fn mass(
        self,
        receiver_available: bool,
        opponent_controls_failure: bool,
    ) -> PassExecutionTransitionMass {
        if !receiver_available {
            return if opponent_controls_failure {
                PassExecutionTransitionMass {
                    opposing_control: 1.0,
                    ..PassExecutionTransitionMass::default()
                }
            } else {
                PassExecutionTransitionMass {
                    delivery_loose: 1.0,
                    ..PassExecutionTransitionMass::default()
                }
            };
        }
        let retained_clean =
            self.delivery.success_probability * self.first_touch_error.failure_probability;
        let first_touch_loose =
            self.delivery.success_probability * self.first_touch_error.success_probability;
        let failed_delivery = self.delivery.failure_probability;
        PassExecutionTransitionMass {
            retained_clean,
            opposing_control: if opponent_controls_failure {
                failed_delivery
            } else {
                0.0
            },
            delivery_loose: if opponent_controls_failure {
                0.0
            } else {
                failed_delivery
            },
            first_touch_loose,
        }
    }

    pub fn delivery_control_side(
        self,
        delivery_roll: f64,
        receiver_available: bool,
        opponent_controls_failure: bool,
    ) -> ExecutionControlSide {
        self.delivery_distribution(receiver_available, opponent_controls_failure)
            .sample(delivery_roll)
            .0
    }

    pub fn delivery_distribution(
        self,
        receiver_available: bool,
        opponent_controls_failure: bool,
    ) -> ExecutionTransitionDistribution {
        let mut distribution = ExecutionTransitionDistribution::new();
        if !receiver_available {
            if opponent_controls_failure {
                distribution
                    .opposing
                    .push(EMPTY_EXECUTION_TRANSITION_BRANCH.with_probability(1.0));
            } else {
                distribution.unresolved_probability = 1.0;
            }
            return distribution;
        }
        distribution.retained.push(
            EMPTY_EXECUTION_TRANSITION_BRANCH.with_probability(self.delivery.success_probability),
        );
        if opponent_controls_failure {
            distribution.opposing.push(
                EMPTY_EXECUTION_TRANSITION_BRANCH
                    .with_probability(self.delivery.failure_probability),
            );
        } else {
            distribution.unresolved_probability = self.delivery.failure_probability;
        }
        distribution
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ExecutionTransitionBranch {
    pub probability: f64,
    pub controller_idx: Option<usize>,
    pub pos: (f64, f64),
    pub arrival_heading: f64,
    pub ownership_continuity: f64,
    pub contact_load: f64,
}

const EMPTY_EXECUTION_TRANSITION_BRANCH: ExecutionTransitionBranch = ExecutionTransitionBranch {
    probability: 0.0,
    controller_idx: None,
    pos: (0.0, 0.0),
    arrival_heading: 0.0,
    ownership_continuity: 0.0,
    contact_load: 0.0,
};

impl ExecutionTransitionBranch {
    fn with_probability(self, probability: f64) -> Self {
        Self {
            probability,
            ..self
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ExecutionTransitionBranches {
    branches: [ExecutionTransitionBranch; MAX_EXECUTION_TRANSITION_BRANCHES],
    len: usize,
}

impl ExecutionTransitionBranches {
    fn new() -> Self {
        Self {
            branches: [EMPTY_EXECUTION_TRANSITION_BRANCH; MAX_EXECUTION_TRANSITION_BRANCHES],
            len: 0,
        }
    }

    pub fn clear(&mut self) {
        self.len = 0;
    }

    pub fn push(&mut self, branch: ExecutionTransitionBranch) {
        assert!(
            self.len < self.branches.len(),
            "execution transition exceeded its bounded branch capacity"
        );
        self.branches[self.len] = branch;
        self.len += 1;
    }

    pub fn iter(&self) -> impl Iterator<Item = &ExecutionTransitionBranch> {
        self.branches[..self.len].iter()
    }

    pub fn first(&self) -> Option<&ExecutionTransitionBranch> {
        self.branches[..self.len].first()
    }

    pub fn first_mut(&mut self) -> Option<&mut ExecutionTransitionBranch> {
        self.branches[..self.len].first_mut()
    }

    pub fn probability(&self) -> f64 {
        self.iter().map(|branch| branch.probability.max(0.0)).sum()
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ExecutionTransitionDistribution {
    pub goal_probability: f64,
    pub retained: ExecutionTransitionBranches,
    pub opposing: ExecutionTransitionBranches,
    pub unresolved_probability: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct ExecutionTransitionExpectedValues {
    pub retained_control_probability: f64,
    pub retained_control_value: f64,
    pub opposing_control_probability: f64,
    pub opposing_control_value: f64,
}

impl ExecutionTransitionDistribution {
    pub fn new() -> Self {
        Self {
            goal_probability: 0.0,
            retained: ExecutionTransitionBranches::new(),
            opposing: ExecutionTransitionBranches::new(),
            unresolved_probability: 0.0,
        }
    }

    pub fn clear(&mut self) {
        self.goal_probability = 0.0;
        self.retained.clear();
        self.opposing.clear();
        self.unresolved_probability = 0.0;
    }

    pub fn retained_probability(&self) -> f64 {
        self.retained
            .probability()
            .clamp(0.0, 1.0 - self.goal_probability.clamp(0.0, 1.0))
    }

    pub fn opposing_probability(&self) -> f64 {
        self.opposing.probability().clamp(
            0.0,
            1.0 - self.goal_probability.clamp(0.0, 1.0) - self.retained_probability(),
        )
    }

    pub fn unresolved_probability(&self) -> f64 {
        self.unresolved_probability.max(0.0).min(
            1.0 - self.goal_probability.clamp(0.0, 1.0)
                - self.retained_probability()
                - self.opposing_probability(),
        )
    }

    pub fn sample(&self, roll: f64) -> (ExecutionControlSide, Option<ExecutionTransitionBranch>) {
        let threshold = roll.clamp(0.0, 1.0);
        let mut cumulative = 0.0;
        for branch in self.retained.iter() {
            cumulative += branch.probability.max(0.0);
            if threshold < cumulative {
                return (ExecutionControlSide::Retained, Some(*branch));
            }
        }
        for branch in self.opposing.iter() {
            cumulative += branch.probability.max(0.0);
            if threshold < cumulative {
                return (ExecutionControlSide::Opposing, Some(*branch));
            }
        }
        (ExecutionControlSide::Unresolved, None)
    }

    pub fn expected_values(
        &self,
        mut retained_value: impl FnMut(ExecutionTransitionBranch) -> f64,
        mut opposing_value: impl FnMut(ExecutionTransitionBranch) -> f64,
    ) -> ExecutionTransitionExpectedValues {
        let retained_control_probability = self.retained_probability();
        let opposing_control_probability = self.opposing_probability();
        let retained_control_value = if retained_control_probability > 1e-9 {
            self.retained
                .iter()
                .map(|branch| branch.probability.max(0.0) * retained_value(*branch))
                .sum::<f64>()
                / retained_control_probability
        } else {
            0.0
        };
        let opposing_control_value = if opposing_control_probability > 1e-9 {
            self.opposing
                .iter()
                .map(|branch| branch.probability.max(0.0) * opposing_value(*branch))
                .sum::<f64>()
                / opposing_control_probability
        } else {
            0.0
        };
        ExecutionTransitionExpectedValues {
            retained_control_probability,
            retained_control_value,
            opposing_control_probability,
            opposing_control_value,
        }
    }
}

impl Default for ExecutionTransitionDistribution {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn branch(probability: f64, controller_idx: usize) -> ExecutionTransitionBranch {
        ExecutionTransitionBranch {
            probability,
            controller_idx: Some(controller_idx),
            pos: (50.0 + controller_idx as f64, 34.0),
            arrival_heading: 0.0,
            ownership_continuity: 0.0,
            contact_load: 0.0,
        }
    }

    #[test]
    fn one_distribution_drives_both_expected_mass_and_realized_sampling() {
        let mut distribution = ExecutionTransitionDistribution::new();
        distribution.retained.push(branch(0.55, 4));
        distribution.retained.push(branch(0.10, 7));
        distribution.opposing.push(branch(0.25, 2));
        distribution.unresolved_probability = 0.10;

        assert_eq!(distribution.retained_probability(), 0.65);
        assert_eq!(distribution.opposing_probability(), 0.25);
        assert!((distribution.unresolved_probability() - 0.10).abs() <= f64::EPSILON);
        assert_eq!(distribution.sample(0.60).0, ExecutionControlSide::Retained);
        assert_eq!(distribution.sample(0.80).0, ExecutionControlSide::Opposing);
        assert_eq!(
            distribution.sample(0.95).0,
            ExecutionControlSide::Unresolved
        );
    }

    #[test]
    fn binary_transition_uses_the_same_mass_for_prediction_and_execution() {
        let transition = BinaryExecutionTransition::from_success_probability(0.72);

        assert_eq!(transition.success_probability, 0.72);
        assert!((transition.failure_probability - 0.28).abs() <= f64::EPSILON);
        assert!(transition.succeeds(0.719));
        assert!(transition.fails(0.72));
    }

    #[test]
    fn carry_segment_prediction_marginalizes_the_same_conditional_tree_sampled_live() {
        let transition = CarrySegmentTransition::new(
            (20.0, 34.0),
            BinaryExecutionTransition::from_success_probability(0.25),
            (24.0, 34.0),
            (24.0, 34.0),
            (4.0, 0.0),
            (22.0, 34.0),
            (22.0, 34.0),
            (2.0, 0.0),
            0.10,
            0.30,
        );
        let grid_size = 100;
        let mut live_survival_count = 0;
        let mut live_constrained_count = 0;
        let mut live_surviving_pos_sum = (0.0, 0.0);
        let mut live_surviving_velocity_sum = (0.0, 0.0);
        for containment_index in 0..grid_size {
            for error_index in 0..grid_size {
                let sample = transition.sample(
                    (error_index as f64 + 0.5) / grid_size as f64,
                    (containment_index as f64 + 0.5) / grid_size as f64,
                );
                if !sample.technical_error {
                    live_survival_count += 1;
                    live_surviving_pos_sum.0 += sample.control_pos.0;
                    live_surviving_pos_sum.1 += sample.control_pos.1;
                    live_surviving_velocity_sum.0 += sample.velocity.0;
                    live_surviving_velocity_sum.1 += sample.velocity.1;
                }
                live_constrained_count += usize::from(sample.constrained_control);
            }
        }
        let sample_count = (grid_size * grid_size) as f64;

        assert!(
            (live_survival_count as f64 / sample_count
                - transition.technical_survival().success_probability)
                .abs()
                <= 1e-12
        );
        assert!(
            (live_constrained_count as f64 / sample_count
                - transition.containment.success_probability)
                .abs()
                <= 1e-12
        );
        assert!(
            transition
                .constrained
                .technical_survival
                .success_probability
                < transition
                    .unconstrained
                    .technical_survival
                    .success_probability
        );
        let projected_pos = transition.projected_surviving_control_pos();
        let projected_velocity = transition.projected_surviving_velocity();
        assert!(
            (live_surviving_pos_sum.0 / live_survival_count as f64 - projected_pos.0).abs()
                <= 1e-12
        );
        assert!(
            (live_surviving_pos_sum.1 / live_survival_count as f64 - projected_pos.1).abs()
                <= 1e-12
        );
        assert!(
            (live_surviving_velocity_sum.0 / live_survival_count as f64 - projected_velocity.0)
                .abs()
                <= 1e-12
        );
        assert!(
            (live_surviving_velocity_sum.1 / live_survival_count as f64 - projected_velocity.1)
                .abs()
                <= 1e-12
        );
    }

    #[test]
    fn expected_values_and_sampling_consume_the_same_branches() {
        let mut distribution = ExecutionTransitionDistribution::new();
        distribution.retained.push(branch(0.60, 1));
        distribution.retained.push(branch(0.20, 2));
        distribution.opposing.push(branch(0.15, 3));
        distribution.unresolved_probability = 0.05;

        let values = distribution.expected_values(
            |branch| branch.controller_idx.unwrap_or(0) as f64 / 10.0,
            |branch| branch.controller_idx.unwrap_or(0) as f64 / 10.0,
        );

        assert_eq!(values.retained_control_probability, 0.80);
        assert_eq!(values.opposing_control_probability, 0.15);
        assert!((values.retained_control_value - 0.125).abs() <= f64::EPSILON);
        assert!((values.opposing_control_value - 0.30).abs() <= f64::EPSILON);
        assert_eq!(distribution.sample(0.70).0, ExecutionControlSide::Retained);
        assert_eq!(distribution.sample(0.90).0, ExecutionControlSide::Opposing);
    }

    #[test]
    fn pass_transition_uses_one_tree_for_prediction_mass_and_live_delivery() {
        let transition = PassExecutionTransition::new(0.72, 0.10);
        let mass = transition.mass(true, true);

        assert!((mass.retained_clean - 0.648).abs() <= f64::EPSILON);
        assert!((mass.first_touch_loose - 0.072).abs() <= f64::EPSILON);
        assert!((mass.opposing_control - 0.28).abs() <= f64::EPSILON);
        assert_eq!(
            transition.delivery_control_side(0.71, true, true),
            ExecutionControlSide::Retained
        );
        assert_eq!(
            transition.delivery_control_side(0.72, true, true),
            ExecutionControlSide::Opposing
        );
    }

    #[test]
    fn pass_spatial_transition_shares_live_sampling_and_prediction_quadrature() {
        let transition = PassSpatialTransition::new((20.0, 30.0), (50.0, 34.0), 80.0, 105.0, 68.0);
        let successful = transition.sample(true, 0.25, 0.5);
        let failed = transition.sample(false, 0.25, 0.5);
        let quadrature = transition.quadrature(true);

        assert!(
            failed.error_radius > successful.error_radius,
            "failed delivery must use the same amplified spatial error in prediction and execution"
        );
        assert!(
            failed.error_radius < successful.error_radius * 2.5,
            "a technical miss should remain a continuous pass error rather than an extreme random redirection"
        );
        assert!((successful.target.0 - 50.0).abs() <= 1e-12);
        assert!(successful.target.1 > 34.0);
        assert!(quadrature
            .iter()
            .all(|sample| (sample.error_radius - successful.error_radius).abs() <= 1e-12));
        let mean = quadrature.iter().fold((0.0, 0.0), |sum, sample| {
            (
                sum.0 + sample.target.0 * 0.25,
                sum.1 + sample.target.1 * 0.25,
            )
        });
        assert!((mean.0 - transition.ideal_target.0).abs() <= 1e-12);
        assert!((mean.1 - transition.ideal_target.1).abs() <= 1e-12);
    }

    #[test]
    fn loose_ball_transition_shares_live_sampling_and_prediction_quadrature() {
        let transition = RectangularLooseBallTransition {
            center: (50.0, 34.0),
            radius_x: 3.0,
            radius_y: 2.0,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };
        let live = transition.sample(0.25, 0.75);
        let quadrature = transition.quadrature();
        let mean = quadrature.iter().fold((0.0, 0.0), |sum, pos| {
            (sum.0 + pos.0 * 0.25, sum.1 + pos.1 * 0.25)
        });

        assert_eq!(live, quadrature[1]);
        assert!((mean.0 - transition.center.0).abs() <= 1e-12);
        assert!((mean.1 - transition.center.1).abs() <= 1e-12);
    }

    #[test]
    fn shot_mishit_transition_shares_live_sampling_and_prediction_quadrature() {
        let transition = ShotMishitSpatialTransition {
            origin: (86.0, 34.0),
            intended_target: (105.0, 34.0),
            minimum_distance: 1.5,
            maximum_distance: 4.5,
            maximum_angle_radians: 1.15,
            pitch_length: 105.0,
            pitch_width: 68.0,
        };
        let live = transition.sample(0.25, 0.75);
        let quadrature = transition.quadrature();

        assert_eq!(live, quadrature[1]);
        assert!(quadrature.iter().all(|pos| {
            let dx = pos.0 - transition.origin.0;
            let dy = pos.1 - transition.origin.1;
            (dx * dx + dy * dy).sqrt() >= transition.minimum_distance
        }));
        assert!(quadrature
            .iter()
            .all(|pos| *pos != transition.origin && pos.0 > transition.origin.0));
    }

    #[test]
    fn shot_transition_uses_one_tree_for_prediction_and_live_sampling() {
        let transition = ShotExecutionTransition::new(0.80, 0.75, 0.25);
        let mass = transition.mass();

        assert!((mass.unreleased - 0.20).abs() <= f64::EPSILON);
        assert!((mass.blocked - 0.20).abs() <= f64::EPSILON);
        assert!((mass.released - 0.60).abs() <= f64::EPSILON);
        assert_eq!(
            transition.sample(0.80, 0.99),
            ShotExecutionOutcome::Unreleased
        );
        assert_eq!(transition.sample(0.20, 0.24), ShotExecutionOutcome::Blocked);
        assert_eq!(
            transition.sample(0.20, 0.25),
            ShotExecutionOutcome::Released
        );
    }

    #[test]
    fn sequential_transition_matches_repeated_live_binary_trials() {
        let per_segment = BinaryExecutionTransition::from_success_probability(0.90);
        let mut sequence = SequentialExecutionTransition::new();
        let first_failure = sequence.append(per_segment);
        let second_failure = sequence.append(per_segment);
        let third_failure = sequence.append(per_segment);

        assert!((first_failure - 0.10).abs() <= f64::EPSILON);
        assert!((second_failure - 0.09).abs() <= f64::EPSILON);
        assert!((third_failure - 0.081).abs() <= f64::EPSILON);
        assert!((sequence.success_probability - 0.729).abs() <= f64::EPSILON);
        assert!(
            (sequence.failure_probability + sequence.success_probability - 1.0).abs()
                <= f64::EPSILON
        );
    }

    #[test]
    fn carry_and_control_terminal_mass_preserve_probability() {
        let mut technical = SequentialExecutionTransition::new();
        technical.append(BinaryExecutionTransition::from_success_probability(0.90));
        technical.append(BinaryExecutionTransition::from_success_probability(0.80));
        let carry = carry_execution_transition_mass(technical, 0.50, 0.20, 0.20, 0.10);
        let carry_total = carry.retained_unconstrained
            + carry.retained_constrained
            + carry.opposing_control
            + carry.loose;
        assert!((carry_total - 1.0).abs() <= f64::EPSILON);

        let control = control_execution_transition_mass(
            0.82,
            0.11,
            0.07,
            BinaryExecutionTransition::from_success_probability(0.18),
        );
        assert!(
            (control.retained + control.opposing_control + control.loose - 1.0).abs()
                <= f64::EPSILON
        );
    }
}
