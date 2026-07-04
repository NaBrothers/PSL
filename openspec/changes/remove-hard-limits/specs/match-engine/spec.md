## MODIFIED Requirements

### Requirement: Formation Emergence Without Hard Lines
The system SHALL produce natural formation shape (defenders back, midfield middle, forwards ahead) purely from position_value scoring without any hardcoded line positions.

#### Scenario: Team advances when possessing ball
- **WHEN** a team has sustained possession and builds up from their half
- **THEN** the average x-position of all players naturally shifts toward the opponent goal
- **AND** this happens because forward positions have higher receive_reachability from ball

#### Scenario: Team retreats when defending
- **WHEN** the opponent has the ball and advances
- **THEN** the defending team's players naturally drop back
- **AND** this happens because positions between ball and own goal have higher protection_value

### Requirement: No Swarming Without Presser Designation
The system SHALL prevent defensive swarming through reward-based approach scoring (not presser flags).

#### Scenario: Only nearby unoccupied defender approaches
- **WHEN** opponent has ball and multiple defenders are nearby
- **THEN** only the defender with lowest "responsibility cost" (no attacker to mark) approaches
- **AND** others stay marking their assigned attackers because mark score > approach score

### Requirement: No Release Threshold Gate
The system SHALL allow all actions to compete equally every tick without a minimum score threshold for releasing the ball.

#### Scenario: Player holds ball because carry is best option
- **WHEN** carry_forward has the highest score among all candidates
- **THEN** player continues carrying (not because threshold blocks release, but because carry wins)
