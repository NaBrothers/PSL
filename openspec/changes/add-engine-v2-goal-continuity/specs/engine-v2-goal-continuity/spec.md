# Engine V2 Goal Continuity

## ADDED Requirements

### Requirement: Goal State Model

Engine v2 SHALL provide a lightweight `PlayerGoal` model that can represent a player's short-term intent without forcing immediate actions.

#### Scenario: Goal contains traceable state

- **Given** a goal has been selected for a player
- **When** the goal is serialized for trace output
- **Then** it includes goal type, target position, value, confidence, creation tick, last updated tick, and context

### Requirement: Value-Based Goal Switching

Engine v2 SHALL decide whether to keep or switch goals by comparing goal value against switch cost, not by enforcing a hard minimum duration.

#### Scenario: Goal persists when still competitive

- **Given** a player has a current goal
- **And** a candidate goal has only a small value advantage
- **When** the advantage does not exceed switch cost
- **Then** the player keeps the current goal

#### Scenario: Goal switches on clear opportunity

- **Given** a player has a current goal
- **And** a candidate goal has a value advantage greater than switch cost
- **When** goal selection runs
- **Then** the player switches to the candidate goal immediately

### Requirement: Goal Biases Existing Action Evaluation

Engine v2 goals SHALL bias candidate generation or action scoring through the existing value model instead of hard-forcing an action.

#### Scenario: Cut-ins remain interruptible

- **Given** a wide carrier has a `cut_inside_to_shoot` goal
- **When** a high-value immediate shot or pass appears
- **Then** the value model can still select that action over the goal's preferred carry

#### Scenario: Arc arrival does not force a pass

- **Given** a midfielder has an `arc_arrival_for_cutback` goal
- **When** the player reaches an arc target
- **Then** the team may pass, carry, shoot, or recycle according to value-model scores

### Requirement: Goal Diagnostics

Engine v2 SHALL expose goal state and switching decisions in trace output.

#### Scenario: Trace explains keep or switch

- **Given** goal tracing is enabled
- **When** a player keeps or switches a goal
- **Then** the trace includes current goal, best candidate goal, switch cost, and keep/switch reason
