## ADDED Requirements

### Requirement: On-Ball Value Evaluators
Engine v2 SHALL expose on-ball action scoring through value-model evaluator functions that return `ValueResult`.

#### Scenario: Evaluators return traceable value results
- **WHEN** pass, carry, shot, hold, or clear scoring is evaluated
- **THEN** the scoring path returns a `ValueResult`
- **AND** the result includes `score`, `success_prob`, `risk_cost`, `current_value`, `after_value`, and `components`

#### Scenario: Components use common names
- **WHEN** an evaluator returns component data
- **THEN** common component names such as `current_value`, `after_value`, `delta`, `success_prob`, `risk_cost`, `opportunity_cost`, `continuity`, and `final_score` are used when present

### Requirement: Behavior-Preserving Migration
Moving scoring logic into value-model evaluators SHALL NOT tune match behavior in this phase.

#### Scenario: Existing scores are preserved
- **WHEN** a migrated evaluator is called with the same inputs as the previous player-level scoring logic
- **THEN** the numeric score and returned action details remain equivalent

#### Scenario: Fixed-seed short match remains deterministic
- **WHEN** a fixed-seed short match is run after the migration
- **THEN** it completes successfully with stable aggregate output

### Requirement: Match-Flow Analysis
The system SHALL support running multi-match samples after the evaluator migration to identify current field-behavior problems without applying fixes.

#### Scenario: Analysis reports observed problems only
- **WHEN** multi-match samples are run after migration
- **THEN** the output summarizes observed statistical and tactical issues
- **AND** no tuning changes are made as part of the analysis
