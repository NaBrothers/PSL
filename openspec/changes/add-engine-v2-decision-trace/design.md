## Context

Engine v2 is moving toward a reward-driven model, but current decisions are hard to diagnose because candidate scores are transient tuples and the trace stream records actions/events rather than the value comparison that produced them. The immediate need is observability for agent-driven balancing scripts, not a user-facing feature.

The current code already has a partial `value_model.py`, `MatchTrace`, and `MatchV2.get_trace()`. This design adds structured decision trace data without changing scoring formulas, candidate generation, softmax selection, web responses, or bot behavior.

## Goals / Non-Goals

**Goals:**
- Add script-controlled decision trace configuration under `EngineConfig.trace`.
- Introduce stable `ValueResult` and `ActionCandidate` data shapes.
- Record chosen candidates and optional top alternatives in `MatchTrace.decisions`.
- Keep trace output JSON-serializable and suitable for tuning scripts.
- Preserve default behavior and performance when trace is off.

**Non-Goals:**
- Do not implement `PlayerGoal` in this phase.
- Do not unify pass/carry models in this phase.
- Do not tune score formulas or macro match statistics in this phase.
- Do not expose decision trace through web/API or bot output in this phase.
- Do not rewrite all off-ball candidate generation in this phase.

## Decisions

### Decision: Trace configuration lives in `EngineConfig.trace`

`EngineConfig` will include a `TraceConfig` dataclass:

```python
@dataclass
class TraceConfig:
    detail: str = "off"  # off | chosen | top_candidates | full
    top_k: int = 5
    include_off_ball: bool = False
    include_defense: bool = False
    focus_players: tuple[int, ...] = ()
    focus_ticks: tuple[tuple[int, int], ...] = ()
    sample_rate: int = 1
```

This keeps scripts, benchmarks, and future config-center mapping on one path. A separate `MatchV2(trace_options=...)` argument was rejected because it would create split control paths.

### Decision: Use `ValueResult` and `ActionCandidate`

`ValueResult` is the common score shape:

```python
@dataclass
class ValueResult:
    score: float
    success_prob: float = 1.0
    risk_cost: float = 0.0
    current_value: float = 0.0
    after_value: float = 0.0
    components: dict = field(default_factory=dict)
```

`ActionCandidate` wraps a decision candidate:

```python
@dataclass
class ActionCandidate:
    phase: str
    action_type: str
    target: tuple[float, float] | None
    value: ValueResult
    details: dict = field(default_factory=dict)
    source: str = ""
```

First implementation focuses on on-ball candidates. Off-ball attack/defense can record selected decisions through the same trace interface later without forcing a full rewrite now.

### Decision: Extend `MatchTrace`, keep decision trace separate

`MatchTrace` gains a `decisions` list and `log_decision(...)`. It will not mix decision trace with regular events/actions. `get_trace()` remains the only debug entrypoint:

```python
{
    "trace_id": "...",
    "events": [...],
    "actions": [...],
    "decisions": [...]
}
```

### Decision: Detail levels are explicit

- `off`: no decision trace.
- `chosen`: record only the chosen candidate.
- `top_candidates`: record chosen + top `top_k` alternatives.
- `full`: record chosen + all candidates.

Default is `off` to avoid default runtime overhead.

### Decision: Behavior must not change

Candidate wrapping must not alter score values or random selection. Trace-on and trace-off runs with identical seeds must select the same actions and produce the same aggregate results.

## Risks / Trade-offs

- **Trace volume can grow quickly** -> default to `off`, add `top_k`, focus filters, phase flags, and sample rate.
- **Wrapping candidates can accidentally change softmax behavior** -> keep numeric scores unchanged and add deterministic tests comparing trace on/off with fixed seeds.
- **Components can become inconsistent** -> define stable common field names while allowing action-specific fields.
- **Off-ball tracing is useful but expensive** -> first phase focuses on on-ball decisions and leaves off-ball flags in config for controlled later expansion.

## Migration Plan

1. Add `TraceConfig`, `ValueResult`, and `ActionCandidate`.
2. Extend `MatchTrace` with decision entries and JSON-safe serialization.
3. Adapt on-ball candidate generation to create candidates while preserving existing action choice behavior.
4. Add targeted tests for defaults, detail levels, top-k, filters, JSON serialization, and behavior preservation.
5. Validate OpenSpec and run focused pytest tests.

Rollback is simple: default trace is off, and the added structures are internal. Reverting the change removes the observability layer without data migration.
