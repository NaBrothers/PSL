# Change: Engine V2 Phase 2 — Intelligent Individual AI

## Why

Phase 1 produces valid match results but player movement is mechanical (small oscillation around formation positions). Players don't make intelligent off-ball runs, don't dynamically adjust to the ball, and the visual result doesn't look like real football. The engine needs proper individual AI to make matches believable and to provide the algorithmic foundation for Phase 3's tactical system.

## What Changes

- **MODIFIED** `psl_core/engine_v2/player.py` — Complete rewrite of decision logic with 5 attacking + 5 defending off-ball actions
- **MODIFIED** `psl_core/engine_v2/match.py` — Ball ownership three-state model, team phase detection, CONTESTED state handling
- **MODIFIED** `psl_core/engine_v2/actions.py` — Add CARRY, CROSS actions; restructure scoring with tactic/role weight slots
- **MODIFIED** `psl_core/engine_v2/ball.py` — CONTESTED state, aerial ball handling
- **MODIFIED** `psl_core/engine_v2/team.py` — Dynamic formation shifting (follow ball), compactness/width parameters
- **NEW** `psl_core/engine_v2/vision.py` — Player vision system (IQ-linked field of view)
- **NEW** `psl_core/engine_v2/goalkeeper.py` — Dedicated GK model (positioning → reaction → saving chain)
- **MODIFIED** `psl_core/engine_v2/config.py` — New tunable parameters for Phase 2 features

## Design Decisions (from discussion)

1. **Ball ownership = 3 states**: HOME_POSSESSED / AWAY_POSSESSED / CONTESTED
2. **Team phase = 5 states**: ATTACKING / TRANSITION_ATK / DEFENDING / TRANSITION_DEF / CONTESTING
3. **CARRY vs DRIBBLE split**: Carry = open space forward movement (Speed-driven); Dribble = beat defender 1v1 (Dribbling vs Tackling)
4. **Unified action framework**: `score = base_score × tactic_weight[phase][action] × role_modifier[action]` — weights default to 1.0, Phase 3 fills them
5. **Vision system**: Passing candidates limited by IQ-linked field of view (90° + IQ × 0.5°)
6. **All aerial balls use Heading**: Long passes, crosses, clearances — any ball in air triggers Heading contest at landing
7. **GK model**: Positioning (shot-moment angle coverage) → Reaction (delay before action) → Saving (actual save probability)
8. **Formation dynamics**: Team formation shifts with ball position; compactness/width are adjustable parameters (Phase 3 tactical levers)
9. **Phase detection**: Transition states triggered by possession change within last 3 ticks
10. **CONTESTED state**: All players near ball compete based on Speed; distant players pre-position based on IQ prediction

## Impact

- Affected specs: match-engine
- Affected code: `psl_core/engine_v2/` (major refactor of player, match, actions, team, ball; new vision and goalkeeper modules)
- No frontend changes required (replay format unchanged)
- No API changes (MatchV2 interface stays the same)
