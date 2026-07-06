## 1. Evaluator Interfaces

- [x] 1.1 Add `evaluate_pass_target()` as the canonical pass evaluator while preserving `expected_pass_value()` compatibility.
- [x] 1.2 Add `evaluate_carry_target()` for carry scoring.
- [x] 1.3 Add `evaluate_shot()` for shot scoring.
- [x] 1.4 Add `evaluate_hold()` for hold/shield/observe scoring.
- [x] 1.5 Add `evaluate_clear()` for clearance scoring.

## 2. Player Integration

- [x] 2.1 Update on-ball pass candidate generation to use the pass evaluator.
- [x] 2.2 Update carry candidate generation to use the carry evaluator.
- [x] 2.3 Update shot, hold, and clear candidate creation to use evaluator results.
- [x] 2.4 Keep returned action details compatible with current execution code.

## 3. Verification

- [x] 3.1 Add or update focused tests for evaluator JSON-safe components.
- [x] 3.2 Run engine v2 trace and shape tests.
- [x] 3.3 Run `openspec validate add-engine-v2-value-model-evaluators --strict --no-interactive`.

## 4. Multi-Match Analysis

- [x] 4.1 Run a small equal-strength sample and collect macro stats.
- [x] 4.2 Run a small strong-vs-weak sample and collect macro stats.
- [x] 4.3 Summarize observed field-behavior problems without tuning them.
