## ADDED Requirements

### Requirement: Continuous Reward Calibration
Engine v2 structural behavior calibration SHALL use continuous reward/value shaping rather than hard-coded tactical gates.

#### Scenario: Low-quality actions are discouraged smoothly
- **WHEN** shot, carry, hold, or pass value is adjusted
- **THEN** the adjustment uses smooth score multipliers or continuous value terms
- **AND** it does not force or forbid an action solely through scenario-specific if/else gates

### Requirement: Macro and Micro Behavior Validation
Engine v2 calibration SHALL inspect both aggregate statistics and positional/action behavior.

#### Scenario: Macro sample is collected
- **WHEN** calibration changes are applied
- **THEN** equal-strength and strong-vs-weak match samples are run
- **AND** shots, shots on target, goals, passes, possession, and action mix are reviewed

#### Scenario: Micro behavior is inspected
- **WHEN** calibration changes are applied
- **THEN** trace output is used to inspect chosen actions by position and average line progression
- **AND** the analysis identifies whether positions and phase behavior look football-like

### Requirement: Goal Layer Deferred
Engine v2 SHALL NOT introduce persistent `PlayerGoal` state during this calibration phase.

#### Scenario: Calibration happens below Goal layer
- **WHEN** structural behavior is improved
- **THEN** changes remain in value/evaluator/trace-level code
- **AND** no per-player persistent goal switching state is added
