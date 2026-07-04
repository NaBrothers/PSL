## 1. Position Value Upgrade
- [ ] 1.1 Add receive_reachability factor: time_me_arrive vs time_defender_arrive → sigmoid advantage
- [ ] 1.2 Add space_creation_bonus: count defenders drawn away if I move here
- [ ] 1.3 IQ noise: perceived_value = real_value * (1 + gauss(0, (100-IQ)/100 * noise_scale))
- [ ] 1.4 Validate: high-value positions are in space between defense lines, not just near goal

## 2. Off-Ball Attack Runs
- [ ] 2.1 Candidate positions: sample 6-8 positions (ahead/wide/behind/diagonal) within roam range
- [ ] 2.2 Each scored by: PV(pos) × reachability(pos) × pass_feasibility(ball→pos)
- [ ] 2.3 Verify emergence: front-runs happen when space behind defense + fast player
- [ ] 2.4 Verify emergence: wide-runs happen when strong-side crowded + weak-side open
- [ ] 2.5 Verify emergence: drop-deep when forward passing blocked

## 3. Pass To Space
- [ ] 3.1 New on-ball candidate: pass_to_space(target_pos)
- [ ] 3.2 Score = PV(target) × teammate_arrival_prob × pass_accuracy
- [ ] 3.3 teammate_arrival_prob = probability any teammate reaches target before any defender
- [ ] 3.4 Execution: ball flies to target_pos, on arrival first-to-arrive (Speed race) gets it
- [ ] 3.5 If defender arrives first → interception

## 4. Zone-Based Marking
- [ ] 4.1 Each defender has a "zone" (15-20m radius from formation_pos)
- [ ] 4.2 mark_runner target = most threatening attacker IN MY ZONE (not nearest to ball)
- [ ] 4.3 block_lane target = between ball and attacker in my zone
- [ ] 4.4 If no attacker in zone → hold_position (don't chase ball)
- [ ] 4.5 Only designated presser approaches ball

## 5. IQ Integration
- [ ] 5.1 All position evaluations get noise: scale = (100-IQ)/100 * config.iq_noise_scale
- [ ] 5.2 Softmax temperature for final selection = (100-IQ)/100
- [ ] 5.3 High IQ: precise runs (tighter to offside line), better pass choices
- [ ] 5.4 Low IQ: mistimed runs, poor decisions, more turnovers

## 6. Validation
- [ ] 6.1 Trace: verify front-runs occur (attacker x increases rapidly toward goal)
- [ ] 6.2 Trace: verify wide-runs (player moves to sideline when strong-side crowded)
- [ ] 6.3 Trace: verify pass-to-space occurs (ball travels to empty space, player arrives)
- [ ] 6.4 Trace: defenders stay in zones (not all chase ball)
- [ ] 6.5 Benchmark: 1v1=2.5-3.5g, 5v5=2.5-3.0g, 10v10=2.0-2.8g
- [ ] 6.6 Benchmark: shots 20-28, pass% 82-90%, tackles 30-40
