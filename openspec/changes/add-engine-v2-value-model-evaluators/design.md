## Context

The previous decision-trace change introduced `ValueResult` and `ActionCandidate`, but several formulas still live directly in `Player` methods. This makes `value_model.py` an incomplete source of truth and keeps later `PlayerGoal` work coupled to player-level implementation details.

This change migrates formula ownership, not gameplay balance. The first goal is a clearer evaluation boundary that can be measured and analyzed.

## Goals / Non-Goals

**Goals:**
- Move on-ball pass, carry, shot, hold, and clear scoring into `value_model.py` evaluator functions.
- Keep existing numerical formulas and return details equivalent.
- Preserve trace components for tuning scripts.
- Run multi-match samples after migration and summarize observed problems.

**Non-Goals:**
- Do not tune scores or macro match stats in this phase.
- Do not introduce `PlayerGoal`.
- Do not rewrite off-ball goal selection.
- Do not change web/API/bot responses.

## Decisions

### Decision: Add evaluator functions, keep compatibility wrappers

`value_model.py` will expose:

```python
evaluate_pass_target(...) -> ValueResult
evaluate_carry_target(...) -> ValueResult
evaluate_shot(...) -> ValueResult
evaluate_hold(...) -> ValueResult
evaluate_clear(...) -> ValueResult
```

Existing player methods can remain as thin candidate-generation wrappers while formulas move into the evaluator functions. This limits blast radius and keeps call sites stable.

### Decision: Preserve formulas first

The evaluator migration must reproduce the existing formulas. If a score looks wrong, it should be reported after multi-match analysis rather than fixed during migration.

### Decision: Analyze after migration

After tests pass, run small multi-match samples with trace enabled enough to inspect action score distributions. The output should identify issues such as excessive shots, low shot accuracy, carry over-selection, pass risk imbalance, or slow performance.

## Risks / Trade-offs

- **Migration accidentally changes scores** -> Add focused tests comparing helper output and run short fixed-seed smoke tests.
- **Evaluator signatures become large** -> Accept explicit arguments now; later a context object can consolidate inputs when `PlayerGoal` is introduced.
- **Analysis samples are small due to runtime cost** -> Treat findings as directional, not final tuning proof.

## Migration Plan

1. Add value-model evaluator functions.
2. Replace player-level formula bodies with calls to evaluators where practical.
3. Keep action candidate details stable for execution.
4. Run focused pytest tests.
5. Run multi-match samples and summarize observed problems only.
