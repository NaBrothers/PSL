## 1. Core State Model
- [ ] 1.1 Implement BallOwnership three-state model (HOME_POSSESSED / AWAY_POSSESSED / CONTESTED)
- [ ] 1.2 Implement TeamPhase five-state detection (ATTACKING / TRANSITION_ATK / DEFENDING / TRANSITION_DEF / CONTESTING)
- [ ] 1.3 Add CONTESTED ball handling (Speed-based race to ball, IQ-based pre-positioning for distant players)
- [ ] 1.4 Add transition detection logic (possession change within last 3 ticks)

## 2. Attacking Off-Ball AI (5 actions)
- [ ] 2.1 Hold position (stay near formation anchor with small noise)
- [ ] 2.2 Find space (move toward highest space-value point within zone)
- [ ] 2.3 Make run (timed forward run into space behind defense, trigger conditions: ball carrier facing + space ahead + Speed)
- [ ] 2.4 Drop deep (move toward ball carrier to offer short option, triggered when carrier under pressure)
- [ ] 2.5 Go wide (move toward sideline to stretch defense)
- [ ] 2.6 All actions use unified framework: `base_score × tactic_weight["in_possession"][phase][action] × role_modifier`

## 3. Defending Off-Ball AI (5 actions)
- [ ] 3.1 Press ball carrier (close down, weighted by proximity and Tackling)
- [ ] 3.2 Block passing lane (position between carrier and dangerous teammate)
- [ ] 3.3 Man-mark (track specific attacker in zone)
- [ ] 3.4 Cover (position behind pressing teammate as safety net)
- [ ] 3.5 Hold shape (maintain formation position, don't commit)
- [ ] 3.6 All actions use unified framework: `base_score × tactic_weight["out_of_possession"][phase][action] × role_modifier`

## 4. On-Ball Actions Extension
- [ ] 4.1 CARRY action (open space forward movement, Speed determines distance, high success rate)
- [ ] 4.2 DRIBBLE action refactor (1v1 take-on under pressure, Dribbling vs Tackling contest)
- [ ] 4.3 CROSS action (wide position → aerial delivery into box, Long_Passing for accuracy)
- [ ] 4.4 On-ball scoring split by team_phase: `base × tactic_weight["on_ball"][phase][action] × role_modifier`

## 5. Formation Dynamics
- [ ] 5.1 Formation shifts with ball position (x-axis: team advances/retreats with ball; y-axis: shifts toward ball side)
- [ ] 5.2 Compactness parameter (vertical distance between lines, adjustable)
- [ ] 5.3 Width parameter (horizontal spread, adjustable)
- [ ] 5.4 Parameters exposed in config for Phase 3 tactical control

## 6. Vision System
- [ ] 6.1 Implement player field-of-view (based on facing direction)
- [ ] 6.2 IQ determines vision cone angle: 90° + IQ × 0.5°
- [ ] 6.3 Pass target selection filtered by vision (can't pass to players outside FOV)

## 7. Aerial / Heading System
- [ ] 7.1 Classify ball as aerial when in flight above certain height/from long pass/cross
- [ ] 7.2 Landing point contest: all players within radius compete using Heading attribute
- [ ] 7.3 Post-heading actions: header shot (near goal), headed pass/flick, ball drops loose (CONTESTED)

## 8. Goalkeeper Model
- [ ] 8.1 GK_Positioning: determines shot-moment angle coverage (position error = f(100-Positioning))
- [ ] 8.2 GK_Reaction: delay ticks before GK begins save action (delay = f(100-Reaction))
- [ ] 8.3 GK_Saving: actual save success probability given reach attempt
- [ ] 8.4 Rush out decision (1v1 situations, linked to Positioning/IQ)
- [ ] 8.5 Distribution logic after save/goal kick (short throw vs long kick, linked to passing abilities)

## 9. Validation
- [ ] 9.1 Update benchmark script with Phase 2 metrics (carry distance, cross count, header goals, contested events)
- [ ] 9.2 Trace analysis: verify front-runs appear, verify formation shifts visible
- [ ] 9.3 Spot-check patterns: fast forward beats slow CB, high Heading wins aerials, high IQ selects better passes
- [ ] 9.4 Macro stats still in valid range after changes
- [ ] 9.5 Visual replay check (deploy and review)
