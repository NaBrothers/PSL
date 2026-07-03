## MODIFIED Requirements

### Requirement: Individual Player Decision-Making
The system SHALL have each player independently select actions each tick using a unified scoring framework where every action score is computed as `base_score × tactic_weight[phase][action] × role_modifier[action]`, with tactic and role weights defaulting to 1.0 for Phase 2.

#### Scenario: Attacking off-ball player makes forward run
- **WHEN** a forward player is in ATTACKING phase, the ball carrier is facing them, and there is >15m space behind the defensive line
- **THEN** the player selects "make_run" action and sprints forward at Speed-determined pace

#### Scenario: Defending player blocks passing lane
- **WHEN** the opponent has the ball and there is a dangerous attacker in the defending player's zone
- **THEN** the defender positions between the ball carrier and the dangerous attacker

#### Scenario: CONTESTED ball resolved by speed
- **WHEN** the ball is in CONTESTED state and two players from different teams are racing to it
- **THEN** the player who arrives first (based on distance / Speed) gains possession

### Requirement: Ball Ownership Three-State Model
The system SHALL track ball ownership as one of three states: HOME_POSSESSED, AWAY_POSSESSED, or CONTESTED, where CONTESTED represents situations with no clear possessor.

#### Scenario: Ball becomes contested after tackle
- **WHEN** a dribble is interrupted by a tackle and neither player cleanly wins the ball
- **THEN** ball_ownership becomes CONTESTED until a player reaches the ball

### Requirement: Team Phase Detection
The system SHALL detect five team phases (ATTACKING, TRANSITION_ATK, DEFENDING, TRANSITION_DEF, CONTESTING) based on ball ownership state and recency of possession change.

#### Scenario: Transition attack detected
- **WHEN** a team gains possession after the opponent held the ball for >3 ticks
- **THEN** that team enters TRANSITION_ATK phase for 3 ticks before becoming ATTACKING

### Requirement: CARRY vs DRIBBLE Distinction
The system SHALL distinguish between carrying the ball forward (open space, Speed-driven, high success) and dribbling past a defender (contested, Dribbling vs Tackling, lower success).

#### Scenario: Player carries ball in open space
- **WHEN** a player has the ball with no defender within press_radius ahead
- **THEN** the CARRY action is available with success rate >85% and displacement of Speed × factor meters

#### Scenario: Player dribbles past defender
- **WHEN** a player has the ball with a defender pressing within press_radius
- **THEN** the DRIBBLE action resolves as Dribbling vs opponent Tackling contest

### Requirement: Dynamic Formation Positioning
The system SHALL dynamically shift the entire team's formation anchor points based on ball position, with configurable compactness (vertical) and width (horizontal) parameters.

#### Scenario: Team advances with ball
- **WHEN** the ball is in the opponent's half during ATTACKING phase
- **THEN** all formation anchor points shift forward proportionally

### Requirement: Vision-Limited Passing
The system SHALL limit pass target selection to players within the passer's field of view, where FOV angle is determined by IQ (90° + IQ × 0.5°).

#### Scenario: High IQ player sees more options
- **WHEN** a player with IQ=90 has the ball (FOV=135°)
- **THEN** they can consider pass targets in a wider arc than a player with IQ=60 (FOV=120°)

### Requirement: Aerial Ball Contest
The system SHALL resolve all aerial balls (long passes, crosses, clearances) via Heading attribute contests among all players near the landing point.

#### Scenario: Cross contested in box
- **WHEN** a cross is delivered into the penalty area
- **THEN** all players within contest radius at landing point compete using Heading attribute
- **AND** the winner can attempt a header shot, headed pass, or the ball becomes CONTESTED

### Requirement: Goalkeeper Sequential Model
The system SHALL model goalkeeper saves as a three-stage process: Positioning (angle coverage at shot moment) → Reaction (delay before action begins) → Saving (save success probability).

#### Scenario: Well-positioned keeper saves more
- **WHEN** a goalkeeper with high GK_Positioning faces a shot
- **THEN** their starting position covers more of the goal angle, requiring less distance to reach the ball

#### Scenario: Slow reaction lets close shot through
- **WHEN** a goalkeeper with low GK_Reaction faces a close-range shot
- **THEN** the reaction delay causes them to start the save too late, reducing save probability
