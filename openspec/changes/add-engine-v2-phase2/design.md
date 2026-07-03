# Design: Engine V2 Phase 2 — Intelligent Individual AI

## Decision Framework

All player decisions in the engine follow a unified pattern:

```
score = base_score(situation, abilities) 
      × tactic_weight[team_phase][action_type]   # default 1.0, Phase 3 fills
      × role_modifier[action_type]                # default 1.0, Phase 3 fills

selection = iq_weighted_softmax(candidates, temperature=(100-IQ)/100)
```

## State Model

```
BallOwnership: HOME_POSSESSED | AWAY_POSSESSED | CONTESTED

TeamPhase (per team):
  ATTACKING        — stable possession in build-up or final third
  TRANSITION_ATK   — just won ball (< 3 ticks since turnover)
  DEFENDING        — opponent has stable possession
  TRANSITION_DEF   — just lost ball (< 3 ticks since turnover)
  CONTESTING       — ball is CONTESTED
```

## Player Decision Tree by State

```
if ball_ownership == CONTESTED:
    → race_to_ball (Speed) or pre_position (IQ prediction)
elif my_team has ball:
    if I am ball_holder:
        → choose_on_ball(SHORT_PASS, LONG_PASS, CARRY, DRIBBLE, SHOOT, CROSS, HOLD)
    else:
        → choose_attacking_off_ball(HOLD_POS, FIND_SPACE, MAKE_RUN, DROP_DEEP, GO_WIDE)
else:  # opponent has ball
    if I am GK:
        → choose_gk_action(ADJUST_POSITION, RUSH_OUT, HOLD)
    else:
        → choose_defending_off_ball(PRESS, BLOCK_LANE, MAN_MARK, COVER, HOLD_SHAPE)
```

## CARRY vs DRIBBLE

| | CARRY | DRIBBLE |
|---|---|---|
| Trigger | No defender in front within press_radius | Defender pressing within press_radius |
| Primary ability | Speed | Dribbling |
| Opposing ability | — | Tackling |
| Success rate | 85-95% | 40-70% |
| Displacement | 8-15m (Speed-driven) | 3-5m (past beaten defender) |
| Risk | Low (can lose if fast defender catches) | High (lose ball to tackler) |

## Formation Dynamics

```python
def compute_dynamic_position(base_pos, ball_pos, config):
    # X-axis shift: team follows ball depth
    x_shift = (ball_pos.x - PITCH_LENGTH/2) * config.formation_advance_factor
    
    # Y-axis shift: team shifts toward ball side
    y_shift = (ball_pos.y - PITCH_WIDTH/2) * config.formation_side_shift_factor
    
    # Compactness: distance between lines
    # Width: horizontal spread
    
    return (
        base_pos.x + x_shift * compactness_factor,
        base_pos.y + y_shift * width_factor,
    )
```

Parameters exposed for Phase 3 tactical control:
- `formation_advance_factor` — how aggressively team pushes up with ball
- `formation_side_shift_factor` — how much team shifts toward ball side
- `compactness` — vertical tightness (0.5=spread, 1.5=compact)
- `width` — horizontal spread (0.5=narrow, 1.5=wide)

## Vision System

```python
def get_visible_targets(passer, all_teammates):
    facing_angle = passer.facing_direction  # angle toward last action/ball
    fov = 90 + passer.abilities["IQ"] * 0.5  # degrees
    half_fov = fov / 2
    
    visible = []
    for tm in all_teammates:
        angle_to_tm = angle_between(passer.pos, tm.pos)
        if abs(angle_diff(facing_angle, angle_to_tm)) <= half_fov:
            visible.append(tm)
    return visible
```

## Goalkeeper Model

```
Shot fired at goal
  │
  ├─ GK_Positioning → determines GK's position at shot moment
  │   (high = covers more angle, low = leaves gaps)
  │
  ├─ GK_Reaction → delay before GK starts moving
  │   delay_factor = (100 - Reaction) / 200  (ticks of delay)
  │   (high = immediate response, low = frozen briefly)
  │
  └─ GK_Saving → actual save probability given reach attempt
      save_prob = f(Saving, distance_to_ball, ball_speed)
      (high = reaches further, less likely to parry/fumble)
```

Rush-out decision:
- Triggered when attacker is 1v1 approaching
- Decision quality linked to GK_Positioning (high = better judgment)
- Speed of rush linked to player Speed attribute

Distribution after save:
- Short throw: uses Short_Passing ability
- Long kick: uses Long_Passing ability  
- Decision (short vs long): linked to IQ and tactic_weight

## Aerial Contest

Any ball classified as aerial (from CROSS, LONG_PASS, GK long kick):
1. Calculate landing point
2. Find all players within `heading_contest_radius` of landing point at arrival tick
3. Each player rolls: `Heading × random(0.8, 1.2) / (distance_to_landing + 1)`
4. Highest roll wins the ball
5. Winner options: header shot (if near goal), headed pass, ball drops loose

## Ability-to-Action Mapping (Complete)

| Ability | On-Ball | Attacking Off-Ball | Defending Off-Ball | Physical | GK |
|---|---|---|---|---|---|
| Finishing | SHOOT score+exec | — | — | — | — |
| Long_Shot | SHOOT(far) score+exec | — | — | — | — |
| Short_Passing | SHORT_PASS score+exec | — | — | — | distribute(short) |
| Long_Passing | LONG_PASS+CROSS score+exec | — | — | — | distribute(long) |
| Dribbling | DRIBBLE score+exec | — | — | — | — |
| Tackling | — | — | PRESS+BLOCK score+exec | — | — |
| Defence | — | — | all actions base_score quality | coverage(soft) | — |
| Speed | CARRY distance | MAKE_RUN reward | PRESS close speed | move/tick, 50/50 | rush speed |
| IQ | temperature + vision FOV | all action temperature + timing | all action temperature | — | rush decision |
| Heading | — | MAKE_RUN(aerial) | aerial contest | — | — |
| GK_Saving | — | — | — | — | save prob |
| GK_Positioning | — | — | — | — | angle coverage |
| GK_Reaction | — | — | — | — | action delay |
