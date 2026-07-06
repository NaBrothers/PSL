## Why

Engine v2 still produces structurally unrealistic play after evaluator migration: full-match samples show excessive shots, low shot accuracy, overuse of carry/hold, too few useful passes, and compressed positional lines. These issues must be addressed in the reward/value model before introducing a higher-level `PlayerGoal` layer.

## What Changes

- Calibrate engine v2 value scale using continuous reward shaping rather than hard tactical gates.
- Reduce low-quality shot selection by making shot value follow smooth xG/angle/pressure quality curves.
- Reduce no-gain carry and passive hold rewards so positive-value passes can compete naturally.
- Improve trace fidelity for chosen shot/carry/pass/hold candidates so micro behavior can be inspected.
- Run macro and micro samples to identify remaining positional and phase-behavior issues.
- Do not introduce Goal state, hard TTLs, forced action rules, or web/API changes in this phase.

## Capabilities

### New Capabilities
- `engine-v2-structural-behavior-calibration`: Continuous reward-model calibration for engine v2 macro stats and micro positional/action behavior.

### Modified Capabilities

## Impact

- Affected code: `psl_core/engine_v2/value_model.py`, `psl_core/engine_v2/player.py`, engine v2 tests.
- Affected validation: engine v2 focused tests, OpenSpec validation, short/full match analysis.
- No database, web, bot, or API schema changes.
