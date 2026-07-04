## 1. Position Value: Add Formation-Aware Factors
- [ ] 1.1 Add role_distance_decay: soft penalty for being far from base formation_pos (not clamp, gradual)
- [ ] 1.2 Add protection_value: for defenders, score positions between ball and own goal
- [ ] 1.3 Remove crowding from same-team only (keep opponent density)

## 2. Team.py: Remove Three-Line System
- [ ] 2.1 Remove compute_dynamic_positions (or simplify to only set initial formation_pos once)
- [ ] 2.2 formation_pos = static base from initial formation (no dynamic shifting per tick)
- [ ] 2.3 Off-ball movement entirely driven by PV scoring (no formation anchor forcing)

## 3. Player.py: Remove Hard Gates
- [ ] 3.1 Remove release_threshold check — all actions compete equally
- [ ] 3.2 Remove forced_decision_radius — low feasibility at close range handles this naturally
- [ ] 3.3 Remove _is_closest_presser check — approach score includes "responsibility cost" factor
- [ ] 3.4 Remove max_roam clamp — replaced by role_distance_decay in PV
- [ ] 3.5 Remove cross_zone_x_threshold — cross score determined by target PV + receiver availability

## 4. Defender Approach: Responsibility-Based
- [ ] 4.1 approach_score = proximity_to_ball × (1.0 - responsibility_cost)
- [ ] 4.2 responsibility_cost = high if attacker is in my zone (I need to mark them)
- [ ] 4.3 Natural result: only unoccupied defenders near ball will approach

## 5. Match.py: Remove Presser Assignment
- [ ] 5.1 Remove _presser_count and presser loop before defender decisions
- [ ] 5.2 Defenders choose approach/mark/hold purely by score comparison

## 6. Validation
- [ ] 6.1 Formation naturally advances when team has ball (avg positions shift forward)
- [ ] 6.2 Formation naturally retreats when defending (avg positions shift back)
- [ ] 6.3 Only 1-2 defenders approach ball (responsibility prevents others)
- [ ] 6.4 Forwards in attacking positions when team attacks (not stuck in midfield)
- [ ] 6.5 Multi-tier benchmark passes
