# Change: Add tick-based match engine v2 (Phase 1)

## Why

The current match engine is a holder-centric state machine where only the ball carrier makes decisions. This architecture cannot support individual player AI, tactical systems, or realistic football scenarios (crossing headers, counter-attacks, pressing). A ground-up rewrite with per-player-per-tick decision-making is needed.

## What Changes

- **NEW** `psl_core/engine_v2/` module: tick-based match simulation with individual player AI
- **NEW** Admin panel tab for engine configuration (tick duration, ability scales, etc.)
- **NEW** Engine version switch in config (`engine_version: v1|v2`)
- **NEW** Trace output system for debugging (per-match trace files with trace_id)
- **NEW** Validation benchmark script in `scripts/`
- **MODIFIED** Server match endpoints: route to v1 or v2 based on config switch
- **MODIFIED** Bot match commands: route to v1 or v2 based on config switch

## Impact

- Affected specs: match-engine (new)
- Affected code: `psl_core/engine_v2/` (new), `server/services/match.py`, `bot/src/plugins/psl/engine/game.py` (switch logic), `web/src/pages/AdminPage.tsx` (config tab)

## Design Decisions (from discussion)

1. **New code, not refactor** — engine_v2/ is independent; old engine stays functional
2. **105×68m coordinate system** — real pitch dimensions, same as v1
3. **2.0s fixed tick** — configurable via admin panel; ~2700 ticks per match
4. **13 abilities unchanged** — reuse existing card ability model, only change how consumed
5. **Replay format 100% compatible** — frontend animations work unchanged (including interpolation)
6. **Output fully aligned with v1** — score, goals, team stats, player ratings, replay JSON
7. **Phase 1 scope: minimal viable simulation** — players can pass/shoot/move, produces reasonable scorelines
8. **Deferred: fouls, free kicks, offsides, penalties** — not in Phase 1
9. **Ball flight time model** — not full physics; ball has travel duration, players move during flight
10. **IQ = decision quality optimizer** — softmax temperature on action selection
11. **Trace system** — each match gets a trace_id, detailed tick-by-tick log for post-analysis
12. **Formation data** — reuse existing FORMATION_COORDS converted to meters
