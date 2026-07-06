## Why

Engine v2 now has decision tracing, but several action scoring formulas still live in `player.py` and only partially expose consistent `ValueResult` data. Moving pass, carry, shot, hold, and clear scoring behind explicit value-model evaluators makes decision traces comparable and prepares the engine for later `PlayerGoal` work without tuning behavior yet.

## What Changes

- Add evaluator functions in `psl_core/engine_v2/value_model.py` for on-ball pass, carry, shot, hold, and clear decisions.
- Preserve the current numeric scoring formulas and selection behavior while moving calculation ownership out of `player.py`.
- Ensure each evaluator returns `ValueResult` with stable common components and action-specific fields.
- Keep web/API/bot output unchanged.
- Run multi-match analysis after migration to identify current match-flow problems, without fixing or tuning those problems in this phase.

## Capabilities

### New Capabilities
- `engine-v2-value-model-evaluators`: Unified evaluator interfaces for engine v2 action scoring that return `ValueResult` and support trace-based analysis.

### Modified Capabilities

## Impact

- Affected code: `psl_core/engine_v2/value_model.py`, `psl_core/engine_v2/player.py`.
- Affected tests/scripts: focused engine v2 tests plus a local multi-match analysis run.
- No score tuning, web/API schema changes, or bot behavior changes are intended.
