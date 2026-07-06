# Tasks: Add Engine V2 Goal Continuity

## 1. Goal Model

- [x] 1.1 Add a `PlayerGoal` data model with trace-safe serialization.
- [x] 1.2 Add pure goal switching helper using value advantage over switch cost.
- [x] 1.3 Add switch-cost components: base, context stability, role discipline, pressure interrupt, IQ adjustment.
- [x] 1.4 Add goal trace fields without changing match behavior.

## 2. Goal Acceptance Cases

- [x] 2.1 Test that goals persist without hard TTL when current value is close to best alternative.
- [x] 2.2 Test that goals switch immediately when best alternative clears switch cost.
- [x] 2.3 Test `cut_inside_to_shoot` proposes a carry bias first and shot bias after a credible window appears.
- [x] 2.4 Test `arc_arrival_for_cutback` proposes an off-ball arc target without forcing a pass.
- [x] 2.5 Test `wide_hold_for_overlap` proposes hold/pass bias only while overlap value is improving.
- [x] 2.6 Test `release_pressure_with_layoff` proposes a layoff target under attracted pressure.
- [x] 2.7 Test `attack_far_post` proposes far-post arrival during wide delivery windows.

## 3. Integration

- [x] 3.1 Wire one attacking goal into on-ball decision trace behind a minimal integration point.
- [x] 3.2 Wire one off-ball attacking goal into target selection behind a minimal integration point.
- [x] 3.3 Run focused tests.
- [x] 3.4 Run 4141/433 short structural diagnostics and compare role behavior.
- [x] 3.5 Decide whether to enable the Goal layer by default or keep it behind config.
- [x] 3.6 Enable Goal continuity by default while keeping diagnostic/config rollback.

## 4. Calibration Follow-up

- [ ] 4.1 Reduce over-frequent `arc_arrival_for_cutback` triggering before enabling by default.
- [ ] 4.2 Make `wide_hold_for_overlap` and `release_pressure_with_layoff` observable in real short samples.
- [x] 4.3 Add goal type counts to the long-form decision report.
- [x] 4.4 Re-run 4141/433/DB samples with goal continuity enabled after calibration.
- [ ] 4.5 Calibrate raw goal counts versus switch counts before enabling by default.
