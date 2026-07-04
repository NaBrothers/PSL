## MODIFIED Requirements

### Requirement: Dynamic Position Value with Space Creation
The system SHALL compute position value considering not just static factors (goal proximity, space) but dynamic factors: how the player's presence at that position creates space for teammates, and whether the player can actually receive the ball there before defenders.

#### Scenario: Forward run into space behind defense emerges
- **WHEN** there is open space behind the defensive line and a fast forward
- **THEN** position_value for that space is high (goal proximity + low defender density + high reachability for fast player)
- **AND** the forward naturally runs there without hard-coded "make run" logic

#### Scenario: Weak-side pull emerges
- **WHEN** play is congested on the right side with multiple players
- **THEN** left-side positions have high space_factor (no opponents) and low crowding
- **AND** a left-side player naturally moves there

### Requirement: Pass to Space
The system SHALL support passing to empty space where a teammate is expected to arrive, not only passing to a player's current position.

#### Scenario: Through-ball on counter-attack
- **WHEN** a forward is sprinting into space behind defense and the midfielder has the ball
- **THEN** pass_to_space scores higher than pass_to_feet because: target space has high PV + teammate arrival probability is high (fast + running toward it)
- **AND** ball is played ahead of the forward for them to run onto

#### Scenario: Ball arrives and no one reaches it
- **WHEN** a pass_to_space is played but no teammate arrives before a defender
- **THEN** the defender intercepts (first-to-arrive logic)

### Requirement: Zone-Based Defensive Marking
The system SHALL have defenders mark attackers within their assigned zone rather than all converging on the ball carrier.

#### Scenario: Defender tracks runner in their zone
- **WHEN** an attacker enters a defender's zone (15-20m from formation_pos)
- **THEN** the defender marks that attacker (positions between attacker and goal)
- **AND** does NOT leave their zone to chase the ball

### Requirement: IQ as Perception Quality
The system SHALL use IQ to control the accuracy of spatial evaluations — high IQ players perceive position values and timing more accurately, low IQ players have noisy perceptions leading to suboptimal decisions.

#### Scenario: High IQ forward times run perfectly
- **WHEN** a forward with IQ=95 evaluates run timing
- **THEN** their perceived offside line is very close to actual → they run right at the last moment

#### Scenario: Low IQ player makes poor choice
- **WHEN** a player with IQ=55 evaluates options
- **THEN** noise distorts their perception → they may choose a suboptimal pass or mistimed run
