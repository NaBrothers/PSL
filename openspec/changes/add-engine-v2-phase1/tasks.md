## 1. Foundation
- [ ] 1.1 Create `psl_core/engine_v2/` package structure (config, pitch, ball, player, match, replay_adapter, trace)
- [ ] 1.2 Implement pitch model (105×68m coordinate system, zones, goal areas)
- [ ] 1.3 Implement ball model (position, state: held/in_flight/dead, flight duration calculation)
- [ ] 1.4 Implement player model (position, state machine: off_ball/on_ball/contest/pressing, abilities, movement)
- [ ] 1.5 Implement match tick loop (2s/tick, 2700 ticks per 90min, half-time swap)

## 2. Player AI (Minimal)
- [ ] 2.1 On-ball actions: short pass, long pass, shoot, dribble (with scoring function)
- [ ] 2.2 Off-ball offensive: run to space, hold position (formation attraction)
- [ ] 2.3 Off-ball defensive: press ball carrier, track back, hold shape
- [ ] 2.4 IQ-based decision selection (softmax with temperature = (100-IQ)/100)
- [ ] 2.5 Contest resolution (tackle vs dribble, aerial duel)

## 3. Match Flow
- [ ] 3.1 Kick-off (start of half, after goal)
- [ ] 3.2 Goal detection (ball crosses goal line within posts)
- [ ] 3.3 Out of play detection (goal kick, corner kick, throw-in as simple possession swap)
- [ ] 3.4 GK behavior (save attempts, distribution after save/goal kick)

## 4. Output & Compatibility
- [ ] 4.1 Examine existing replay format and frontend interpolation logic
- [ ] 4.2 Implement replay adapter (tick trace → v1-compatible replay JSON)
- [ ] 4.3 Match result output (score, goals list with scorer/assister/minute)
- [ ] 4.4 Team statistics (possession, shots, shots on target, passes, pass accuracy, tackles, etc.)
- [ ] 4.5 Player ratings and individual stats

## 5. Configuration & Integration
- [ ] 5.1 Engine config model (tick_duration, ability scales, etc.) with defaults
- [ ] 5.2 Admin panel tab for engine v2 config
- [ ] 5.3 Engine version switch in server match route
- [ ] 5.4 Engine version switch in bot match command

## 6. Validation
- [ ] 6.1 Trace output system (trace_id per match, JSON log file)
- [ ] 6.2 Benchmark script: run N matches, compute macro stats
- [ ] 6.3 Macro stat assertions (goals/match, shots, pass accuracy, upset rate, etc.)
- [ ] 6.4 Spot-check patterns (header goals exist, fast forwards beat slow CBs, etc.)
