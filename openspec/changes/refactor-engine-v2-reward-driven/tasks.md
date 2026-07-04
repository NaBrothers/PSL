## 1. Position Value Function
- [ ] 1.1 Create `position_value.py` with unified value function
- [ ] 1.2 Factors: goal proximity, opponent density, teammate density, shooting zone, sideline
- [ ] 1.3 Expose tactic_weight slot for Phase 3 modification
- [ ] 1.4 Validate: plot value heatmap, verify high near goal + low in crowded areas

## 2. 3-Phase Tick Loop
- [ ] 2.1 Rewrite `match.py` tick loop: Phase 1 (all choose), Phase 2 (detect), Phase 3 (resolve)
- [ ] 2.2 Phase 1: Collect all player actions into an action map
- [ ] 2.3 Phase 2: Scan for interactions (attacker carry + defender tackle = duel; pass path + defender position = interception)
- [ ] 2.4 Phase 3: Resolve each interaction with probability, execute non-conflicting actions directly
- [ ] 2.5 Ball position update follows holder or flight interpolation

## 3. On-Ball Decision (Pure Reward)
- [ ] 3.1 Remove ALL hard gates (min ticks, forced decision, release threshold as gate)
- [ ] 3.2 Candidates: carry_to(pos_A), carry_to(pos_B), pass_to(X), pass_to(Y), shoot, clear
- [ ] 3.3 Carry score = position_value(target) × path_feasibility (no opponent blocking)
- [ ] 3.4 Pass score = pass_success_rate × position_value(teammate_pos)
- [ ] 3.5 Shoot score = on_target_prob × (1-save_prob) × goal_reward
- [ ] 3.6 Clear score = danger_reduction (high when under heavy pressure in own half)
- [ ] 3.7 IQ controls softmax temperature for selection noise
- [ ] 3.8 "Continue carrying" naturally wins when space ahead > available passes

## 4. Off-Ball Decision
- [ ] 4.1 Attacking: score = position_value(target) × reachability × receive_probability
- [ ] 4.2 Defending:逼近 / 出脚 / 卡位 / 盯人 / 回位 scored by defensive contribution
- [ ] 4.3 "出脚" score = success_rate × reward - (1-success_rate) × penalty
- [ ] 4.4 Defender stun on failed tackle (1.5 seconds, defined in seconds not ticks)

## 5. Interaction Detection & Resolution
- [ ] 5.1 Create `interactions.py` with detect + resolve functions
- [ ] 5.2 Duel: if attacker carries AND defender tackles within range → contest(Dribbling vs Tackling)
- [ ] 5.3 Interception: if pass executed AND defender moved onto pass path → intercept check(Defence)
- [ ] 5.4 Block: if shot executed AND defender in shot path → block check
- [ ] 5.5 Missed tackle: if defender tackles but attacker passed → defender stunned (wasted)
- [ ] 5.6 Contest outcomes: win/lose/loose_ball

## 6. Unforced Errors
- [ ] 6.1 Pass error: (100-Passing)/500 chance of ball going astray
- [ ] 6.2 First touch error: (100-IQ)/400 chance on receiving
- [ ] 6.3 Carry error: (100-Dribbling)/600 chance of losing control
- [ ] 6.4 All errors produce CONTESTED (loose ball)

## 7. Time Unit Normalization
- [ ] 7.1 All time parameters in config defined in seconds
- [ ] 7.2 Runtime conversion: ticks = ceil(seconds / tick_duration)
- [ ] 7.3 Verify: changing tick_duration doesn't change gameplay feel

## 8. Validation
- [ ] 8.1 Trace single player (CM): verify carries 4-8s, passes forward when opportunity exists
- [ ] 8.2 Trace defender: verify tackles only when close, mostly just follows
- [ ] 8.3 Macro stats: 2-4 goals, 15-25 shots, 30-50 tackles, 5-10 unforced errors per match
- [ ] 8.4 Ball progression: average possession moves ball toward goal over time
- [ ] 8.5 No back-pass loops: defenders don't pass among themselves indefinitely
- [ ] 8.6 Benchmark assertions pass
