# Design: Match Engine v2 Phase 1

## Architecture

```
psl_core/engine_v2/
├── __init__.py
├── config.py          # Engine parameters (tick duration, scales, etc.)
├── pitch.py           # Pitch model (coordinates, zones, boundaries)
├── ball.py            # Ball state (position, flight, state enum)
├── player.py          # Player model (state machine, abilities, AI decision)
├── team.py            # Team model (formation, player list)
├── match.py           # Match loop (tick simulation, event detection)
├── actions.py         # Action definitions and scoring functions
├── physics.py         # Movement, distance, flight time calculations
├── replay_adapter.py  # Convert tick trace to v1-compatible replay JSON
├── trace.py           # Trace output (per-tick log with trace_id)
├── stats.py           # Match statistics aggregation
└── rating.py          # Post-match player ratings
```

## Tick Loop

```
for each tick (0..total_ticks):
    1. All players perceive (ball pos, teammates, opponents, game state)
    2. All players decide (generate candidate actions, score them, select via IQ-weighted softmax)
    3. All players execute (move, pass, shoot, tackle, etc.)
    4. Physics settle (ball flight progress, position updates)
    5. Event detection (goal, out of play, possession change)
    6. Trace append
```

## Player State Machine

States: OFF_BALL, ON_BALL, PRESSING, CONTEST

Transitions:
- OFF_BALL → ON_BALL: receive ball (pass arrives, win contest)
- OFF_BALL → PRESSING: decide to press carrier
- OFF_BALL → CONTEST: 50/50 ball nearby
- ON_BALL → OFF_BALL: pass, shoot, lose ball
- ON_BALL → CONTEST: defender engages
- PRESSING → CONTEST: reach ball carrier
- PRESSING → OFF_BALL: give up press
- CONTEST → ON_BALL: win
- CONTEST → OFF_BALL: lose

## Decision Model

Each tick, a player generates candidate actions based on state:

```python
candidates = generate_candidates(player, game_state)
for action in candidates:
    action.score = success_prob(action, player.abilities) * reward(action, game_state) * tactic_weight(action, team_tactics)
temperature = (100 - player.ability["IQ"]) / 100
chosen = softmax_select(candidates, temperature)
```

## Ball Flight Model

- Ball has states: HELD, IN_FLIGHT, DEAD
- When passed/shot: calculate flight_duration = distance / ball_speed
- During flight: ball position interpolates toward target
- At arrival: determine who receives (closest player within reception radius, weighted by Speed)
- If no valid receiver: ball becomes DEAD (out of play or loose)

## Ability Usage (Key Mappings)

| Ability | Decision Layer | Execution Layer | Physics Layer |
|---------|---------------|-----------------|---------------|
| Finishing | Shoot reward accuracy | Shot on target prob | Miss cone width |
| Short_Passing | Pass option scoring | Pass accuracy | Ball deviation |
| Long_Passing | Long ball scoring | Long pass accuracy | Landing scatter |
| Dribbling | Dribble preference | Beat defender prob | Carry speed |
| Tackling | Press aggressiveness | Tackle success prob | Foul chance |
| Defence | Positioning quality | Interception read | Coverage radius (soft decay) |
| Speed | Counter-attack reward | — | Movement per tick, 50/50 arrival |
| IQ | **Temperature (core)** | Run timing precision | — |
| Heading | Aerial action bias | Header success prob | — |
| Long_Shot | Long shot reward | Ranged shot accuracy | Ball trajectory |
| GK_* | GK positioning decisions | Save probability | Reaction window |

## Replay Adapter Strategy

The adapter converts tick-level trace data into v1 replay event format:
1. Sample key events from trace (goals, shots, passes, dribbles, tackles)
2. Add player positions at regular intervals (for frontend animation interpolation)
3. Output JSON matching existing `replay.py` schema

## Configuration Parameters (Admin Panel)

All values hot-reloadable via admin panel:

| Parameter | Default | Description |
|-----------|---------|-------------|
| engine_version | v1 | Which engine to use |
| tick_duration_sec | 2.0 | Seconds per tick |
| match_duration_min | 90 | Match length |
| decision_noise_base | 1.0 | IQ noise multiplier |
| defence_decay_rate | 0.15 | Defence coverage falloff |
| finishing_scale | 12 | Finishing accuracy scale |
| speed_factor | 1.0 | Speed → distance multiplier |
| trace_enabled | true | Write trace files |
| replay_enabled | true | Generate replay JSON |
