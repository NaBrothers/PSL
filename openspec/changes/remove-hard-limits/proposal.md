# Change: Remove all hard limits — pure PV-driven positioning and decisions

## Why

Current engine still has "god's hand" hard limits that override natural behavior:
- Three-line forced positioning (def/mid/atk lines at fixed offsets from ball)
- Release threshold gate (must exceed threshold to pass)
- Presser designation (system picks who presses)
- Forced decision radius (must act when enemy within X meters)
- Max roam clamp (forced back if too far from formation)
- Cross zone gate (can't cross unless past 82% of pitch)

These prevent natural football behavior from emerging and create artificial constraints that make the game look unrealistic.

## What Changes

- **REWRITE** `team.py` — Remove dynamic three-line computation; formation_pos becomes static base + soft PV-based pull
- **MODIFY** `player.py` — Remove release_threshold, forced_decision_radius, _is_closest_presser check, max_roam clamp, cross_zone check. Replace with PV-driven equivalents.
- **MODIFY** `position_value.py` — Add role_distance_decay (soft pull toward formation area) + protection_value for defenders
- **MODIFY** `config.py` — Remove obsolete gate parameters

## Design: How Formation Emerges Without Hard Lines

### Attacking players (team has ball):
```
run_target_score = base_PV(pos)
    × receive_reachability(pos, ball)  # near ball = can get pass
    × role_distance_decay(pos, formation_base)  # far from role area = slight penalty
```
- Players near ball: reachability high → cluster around ball
- Crowding penalty: prevents too much clustering → spreads out
- Role decay: gentle pull back toward default role area → maintains rough layers

### Defending players (opponent has ball):
```
defend_target_score = protection_value(pos, ball, own_goal)  # between ball and goal = good
    × zone_responsibility(pos, nearby_attackers)  # attacker nearby = stay and mark
    × role_distance_decay(pos, formation_base)  # stay in general area
```
- Protection value: high when between ball and goal → defenders naturally retreat
- Zone responsibility: attacker in my zone → I stay to mark → no swarming
- Ball moves → protection value shifts → defenders shift WITH ball naturally

### Formation advance/retreat emerges from:
- Ball forward → forward area PV high (receive_reachability) → everyone creeps forward
- Ball backward → backfield protection_value high → defenders drop back
- No explicit "push line to ball+20m" needed

## Impact
- Affected: team.py, player.py, position_value.py, config.py, match.py
- No frontend/API changes
