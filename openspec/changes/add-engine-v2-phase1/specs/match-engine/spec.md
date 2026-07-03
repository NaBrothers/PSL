# Spec: Match Engine v2

## ADDED Requirements

### Requirement: Tick-Based Match Simulation
The system SHALL simulate a football match as a series of discrete ticks (configurable duration, default 2.0s) where all 22 players independently perceive, decide, and execute actions each tick.

#### Scenario: Standard match completes
- **WHEN** a match is started between two valid squads
- **THEN** the engine runs for the configured number of ticks (match_duration / tick_duration)
- **AND** produces a final score, goal list, team stats, player ratings, and replay data

#### Scenario: Match produces reasonable scoreline
- **WHEN** 200+ matches are simulated between balanced teams
- **THEN** the average goals per match is between 2.0 and 3.5

### Requirement: Individual Player Decision-Making
The system SHALL have each player independently select actions each tick based on their abilities, game state, and tactical parameters, using a scoring function with IQ-weighted randomness.

#### Scenario: High IQ player makes better decisions
- **WHEN** comparing decision quality between IQ=90 and IQ=60 players in identical situations
- **THEN** the IQ=90 player selects the higher-reward action more frequently

#### Scenario: Player state transitions are valid
- **WHEN** a player is in OFF_BALL state
- **THEN** they can only transition to ON_BALL (receive), PRESSING (decide to press), or CONTEST (50/50 ball)

### Requirement: Ball Flight Time Model
The system SHALL model ball movement with a travel duration proportional to distance, during which other players continue to move.

#### Scenario: Pass has flight time
- **WHEN** a player makes a 30m pass
- **THEN** the ball takes approximately 1-2 ticks to arrive
- **AND** other players update their positions during the flight

### Requirement: Replay Output Compatibility
The system SHALL output replay data in the exact format consumed by the existing frontend replay animation system, including support for the frontend's interpolation logic.

#### Scenario: Frontend renders v2 replay
- **WHEN** a match is played with engine v2
- **THEN** the replay JSON can be loaded by the existing frontend without modification
- **AND** player movements animate smoothly via the existing interpolation

### Requirement: Engine Version Switch
The system SHALL support switching between v1 and v2 engines via a configuration parameter, allowing A/B comparison.

#### Scenario: Config switches engine
- **WHEN** admin sets engine_version to "v2" in the config panel
- **THEN** all subsequent matches use the v2 engine
- **AND** setting it back to "v1" restores original behavior

### Requirement: Match Trace Output
The system SHALL produce a detailed per-tick trace log for each match, identifiable by a unique trace_id, for post-match analysis and debugging.

#### Scenario: Trace file written
- **WHEN** a match completes with trace_enabled=true
- **THEN** a JSON trace file is written containing tick-by-tick player positions, actions, and events
- **AND** the trace_id is included in the match result

### Requirement: Engine Configuration via Admin Panel
The system SHALL expose all engine v2 parameters (tick duration, ability scales, feature flags) in the admin web panel for hot-reload without code changes.

#### Scenario: Parameter change takes effect
- **WHEN** admin changes tick_duration_sec from 2.0 to 1.5
- **THEN** the next match uses 1.5s ticks without server restart

### Requirement: Full Statistics Output
The system SHALL output team-level and player-level statistics matching the existing v1 engine output format.

#### Scenario: Stats match v1 schema
- **WHEN** a v2 match completes
- **THEN** the output includes possession, shots, shots_on_target, passes, pass_success_rate, tackles, interceptions, and all other fields present in v1 output
