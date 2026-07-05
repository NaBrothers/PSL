## 1. Trace Configuration

- [x] 1.1 Add `TraceConfig` to `psl_core/engine_v2/config.py` with detail levels, top-k, phase flags, focus filters, and `should_trace()`.
- [x] 1.2 Add `TraceConfig` to `EngineConfig` with default detail `off`.
- [x] 1.3 Keep config-service loading behavior unchanged except for optional future trace key support.

## 2. Value and Candidate Models

- [x] 2.1 Add `ValueResult` with JSON-safe `to_dict()` and common component normalization.
- [x] 2.2 Add `ActionCandidate` with JSON-safe `to_dict()`, score access, and tuple compatibility helpers.
- [x] 2.3 Wrap existing on-ball pass, carry, shoot, hold, and clear scores into `ActionCandidate` without changing numeric scores.

## 3. Decision Trace

- [x] 3.1 Extend `MatchTrace` with a separate `decisions` list and `log_decision()`.
- [x] 3.2 Record on-ball chosen decisions when trace detail is `chosen`, `top_candidates`, or `full`.
- [x] 3.3 Record top alternatives according to `trace.top_k` and detail level.
- [x] 3.4 Apply focus player, focus tick, phase, and sample-rate filters before recording.

## 4. Behavior Preservation

- [x] 4.1 Preserve existing softmax score selection and returned `(action_type, details)` behavior.
- [x] 4.2 Ensure trace-off runs do not produce decision entries.
- [x] 4.3 Ensure trace-on and trace-off fixed-seed runs produce identical score and aggregate statistics.

## 5. Tests and Validation

- [x] 5.1 Add tests for `TraceConfig.should_trace()` filtering.
- [x] 5.2 Add tests for `ValueResult` and `ActionCandidate` JSON serialization.
- [x] 5.3 Add tests for `off`, `chosen`, `top_candidates`, and `full` decision trace behavior.
- [x] 5.4 Add behavior-preservation tests for trace on/off with a fixed seed.
- [x] 5.5 Run focused pytest tests for engine v2 trace.
- [x] 5.6 Run `openspec validate add-engine-v2-decision-trace --strict --no-interactive`.
