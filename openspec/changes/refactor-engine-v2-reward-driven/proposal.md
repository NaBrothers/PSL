# Change: Refactor engine v2 to pure reward-driven decision model

## Why

The current engine v2 has multiple "god's hand" hard rules (forced decision radius, minimum hold ticks, tick-based release thresholds) that produce unrealistic behavior (200+ tackles/match, instant one-touch passing, back-pass loops). These hard rules mask the underlying problem: the scoring model doesn't naturally produce correct football behavior.

A ground-up refactor of the decision model is needed where ALL player behavior emerges purely from reward/score comparisons, with no hard-coded gates or forced actions.

## What Changes

- **REWRITE** `psl_core/engine_v2/match.py` — New 3-phase tick loop (choose → detect interactions → resolve)
- **REWRITE** `psl_core/engine_v2/player.py` — Pure reward-driven decisions, no hard rules
- **NEW** `psl_core/engine_v2/position_value.py` — Unified position value function (all decisions' foundation)
- **NEW** `psl_core/engine_v2/interactions.py` — Interaction detection and resolution (1v1, interception, block)
- **MODIFIED** `psl_core/engine_v2/actions.py` — Scoring uses position_value, adds unforced error
- **MODIFIED** `psl_core/engine_v2/config.py` — Time params in seconds, new error rates

## Design Decisions (from discussion)

1. **No hard rules** — No min hold ticks, no forced decision radius, no release threshold gates. All behavior from score comparison.
2. **Unified position_value function** — Single function outputs "how valuable is this position for our attack". Used by all decisions.
3. **3-phase tick** — Phase 1: all choose actions simultaneously. Phase 2: detect interactions (1v1, interception). Phase 3: resolve with probability.
4. **Tackle = high risk/reward** — Defender "出脚" has failure penalty (stun 1.5s). Only chosen when score is positive (close + high Tackling).
5. **Unforced errors** — Even without pressure, actions have small failure chance based on ability.
6. **Duel system** — Same-tick conflicts between attacker and defender resolved as contests (Dribbling vs Tackling).
7. **Interception = spatial** — Ball path intercepted only if defender moved to that path this tick.
8. **Time in seconds** — All time params defined in seconds, converted to ticks at runtime.
9. **Layer 1 only** — This refactor implements the universal AI. Position/role/tactic modifiers (Layers 2-4) stay as 1.0 multiplier slots.

## Impact

- Affected specs: match-engine
- Affected code: Complete rewrite of player.py, match.py; new position_value.py, interactions.py
- No frontend changes (replay format unchanged)
- No API changes (MatchV2 interface unchanged)
