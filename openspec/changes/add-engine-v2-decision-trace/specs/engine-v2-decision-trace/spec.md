## ADDED Requirements

### Requirement: Trace Configuration
Engine v2 SHALL expose script-controllable decision trace configuration through `EngineConfig.trace`.

#### Scenario: Trace is off by default
- **WHEN** a match is created with the default engine v2 configuration
- **THEN** decision trace recording is disabled
- **AND** `match.get_trace()["decisions"]` is empty after the match runs

#### Scenario: Focus filters are respected
- **WHEN** `EngineConfig.trace` specifies focus players, focus tick windows, phase inclusion, or sample rate
- **THEN** engine v2 records only decision entries allowed by those filters

### Requirement: Stable Decision Value Shape
Engine v2 SHALL represent scored decision candidates with JSON-serializable value components.

#### Scenario: Candidate value is serializable
- **WHEN** a decision candidate is recorded
- **THEN** its value data includes `score`, `success_prob`, `risk_cost`, `current_value`, `after_value`, and `components`
- **AND** the recorded value data can be serialized by `json.dumps`

#### Scenario: Common component names are stable
- **WHEN** a candidate has component data
- **THEN** common fields such as `current_value`, `after_value`, `delta`, `success_prob`, `risk_cost`, `opportunity_cost`, `continuity`, and `final_score` use those exact names when present

### Requirement: Decision Trace Stream
Engine v2 SHALL record decision trace entries separately from match events and action logs.

#### Scenario: Chosen decision is recorded
- **WHEN** `EngineConfig.trace.detail` is `chosen`
- **THEN** each traced decision entry contains the chosen candidate
- **AND** alternatives are omitted or empty

#### Scenario: Top candidates are recorded
- **WHEN** `EngineConfig.trace.detail` is `top_candidates`
- **THEN** each traced decision entry contains the chosen candidate and at most `trace.top_k` alternatives
- **AND** alternatives are ordered by score descending

#### Scenario: Full candidates are recorded
- **WHEN** `EngineConfig.trace.detail` is `full`
- **THEN** each traced decision entry contains the chosen candidate and all available alternatives for that traced decision

### Requirement: Behavior Preservation
Decision tracing SHALL NOT change match simulation behavior.

#### Scenario: Trace does not affect deterministic result
- **WHEN** two matches run with the same teams, same random seed, and same engine configuration except trace detail
- **THEN** the score and key aggregate statistics are identical
- **AND** the selected actions remain unchanged

### Requirement: Internal-Only Exposure
Decision trace data SHALL be available through the Python engine trace API in this phase and SHALL NOT change web or bot API responses.

#### Scenario: Trace is available from match object
- **WHEN** a script enables decision trace and runs `MatchV2`
- **THEN** the script can read decision entries from `match.get_trace()["decisions"]`

#### Scenario: Server match response remains unchanged
- **WHEN** a web match request uses engine v2
- **THEN** the response schema does not include decision trace data
