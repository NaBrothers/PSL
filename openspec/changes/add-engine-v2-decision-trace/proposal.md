## Why

Engine v2 currently chooses actions by comparing scores each tick, but those scores are not observable in a stable, script-friendly format. This makes balancing problems such as low shot accuracy, excessive shooting, odd passing choices, and target jitter hard to diagnose without guessing from replay output.

## What Changes

- Add a decision-trace capability for engine v2 that can be enabled by test and tuning scripts.
- Introduce stable value/candidate result shapes for action scoring without changing default match behavior.
- Record selected actions and optional top alternatives in `MatchTrace` under a separate decision stream.
- Add trace filters for detail level, top-k candidates, player focus, tick windows, and phase inclusion.
- Keep web/API output unchanged in this phase.

## Capabilities

### New Capabilities
- `engine-v2-decision-trace`: Script-controlled observability for engine v2 action decisions, including chosen candidates, top alternatives, score components, and JSON-serializable trace output.

### Modified Capabilities

## Impact

- Affected code: `psl_core/engine_v2/config.py`, `psl_core/engine_v2/value_model.py`, `psl_core/engine_v2/player.py`, `psl_core/engine_v2/match.py`, `psl_core/engine_v2/trace.py`.
- Affected tests: new targeted tests for trace defaults, trace detail levels, top-k behavior, serialization, and behavior preservation.
- No web/API contract changes.
- No score formula, softmax, or candidate generation behavior changes are intended.
