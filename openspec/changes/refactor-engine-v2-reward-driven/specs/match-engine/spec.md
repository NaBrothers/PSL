## MODIFIED Requirements

### Requirement: Pure Reward-Driven Player Decisions
The system SHALL have all player decisions driven purely by action score comparisons, with no hard-coded gates, minimum timers, or forced actions. The highest-scoring action is always selected (with IQ-weighted noise).

#### Scenario: Player naturally holds ball when no good option
- **WHEN** a player has the ball with open space ahead and no teammate in a better position
- **THEN** "carry forward" scores highest and player advances with ball
- **AND** no minimum tick timer forces this behavior — it emerges from scoring

#### Scenario: Player passes when teammate is in better position  
- **WHEN** a teammate is in a higher position_value location with a clear passing lane
- **THEN** "pass to teammate" scores higher than "carry" and player passes
- **AND** this happens regardless of how many ticks the player has held the ball

### Requirement: Three-Phase Tick Resolution
The system SHALL process each tick in three phases: all players choose actions simultaneously, then interactions are detected, then interactions are resolved with probability.

#### Scenario: Simultaneous duel detection
- **WHEN** an attacker chooses "carry forward" and a defender chooses "tackle" in the same tick
- **THEN** the system detects this as an interaction and resolves it as a 1v1 duel (Dribbling vs Tackling)

#### Scenario: Defender tackles but attacker already passed
- **WHEN** a defender chooses "tackle" but the attacker chose "pass" in the same tick  
- **THEN** the pass executes and the defender is stunned (wasted tackle)

### Requirement: Unified Position Value Function
The system SHALL use a single position_value function as the foundation for all spatial decisions (carrying direction, pass target selection, off-ball movement).

#### Scenario: Position near goal with space is high value
- **WHEN** a position is within 20m of the opponent goal with few defenders nearby
- **THEN** position_value returns a high score (>0.7)

#### Scenario: Crowded area has reduced value
- **WHEN** a position has 3+ teammates already nearby
- **THEN** position_value returns a reduced score due to crowding penalty

### Requirement: Tackle as High-Risk Decision
The system SHALL model "tackle attempt" as a deliberate high-risk decision with explicit failure penalty (stun duration), not as an automatic system check.

#### Scenario: Defender chooses to tackle and succeeds
- **WHEN** a defender within 1.5m with high Tackling chooses "tackle" and wins the duel
- **THEN** possession transfers to the defender (recorded as tackle)

#### Scenario: Defender tackles and fails
- **WHEN** a defender chooses "tackle" and loses the duel
- **THEN** the defender is stunned for 1.5 seconds (unable to act) and the attacker advances

### Requirement: Unforced Errors
The system SHALL model small-probability execution failures independent of opponent pressure, based on player ability.

#### Scenario: Low-ability player misplaces pass
- **WHEN** a player with Passing=60 executes a pass with no defenders nearby
- **THEN** there is an 8% chance the ball goes astray (unforced error)

#### Scenario: High-ability player rarely makes errors
- **WHEN** a player with Passing=90 executes a pass
- **THEN** the unforced error chance is only 2%

### Requirement: Interception from Positioning
The system SHALL only allow interceptions when the defending player has actively moved into the ball's path during the same tick, not as an automatic probability check on nearby defenders.

#### Scenario: Defender reads pass and intercepts
- **WHEN** a defender's chosen movement this tick places them on the pass trajectory
- **THEN** an interception check occurs based on their Defence attribute

#### Scenario: Nearby defender who didn't move to path cannot intercept
- **WHEN** a defender is near the pass path but chose "track runner" (moved away from path)
- **THEN** no interception check occurs — the pass completes
