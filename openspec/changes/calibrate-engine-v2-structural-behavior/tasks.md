## 1. Reward Shaping

- [x] 1.1 Replace discrete shot quality thresholds with continuous xG/angle/pressure shaping.
- [x] 1.2 Replace discrete carry low-gain penalties with continuous gain/staleness shaping.
- [x] 1.3 Replace discrete hold interruption/decay with continuous pressure/opportunity shaping.
- [x] 1.4 Preserve trace components for the new shaping terms.

## 2. Validation

- [x] 2.1 Run engine v2 focused tests.
- [x] 2.2 Run OpenSpec validation for this change.
- [x] 2.3 Run short trace samples for equal-strength and strong-vs-weak teams.
- [x] 2.4 Run small full-match samples for equal-strength and strong-vs-weak teams.

## 3. Analysis

- [x] 3.1 Summarize macro stats after calibration.
- [x] 3.2 Summarize action mix by position.
- [x] 3.3 Summarize remaining positional/phase behavior problems.
- [x] 3.4 Add arc ready-window diagnostics to distinguish second-line absence from defensive pressure.
- [x] 3.5 Add wide-forward-second-line chain diagnostics to locate where second-line finishing breaks.

## 4. Follow-up Chain Calibration

- [x] 4.1 Inspect second-line receiver candidate scores after FW layoff.
- [ ] 4.2 Add a focused test for first-time second-line shot readiness after a high-value layoff.
- [ ] 4.3 Calibrate recycle/pass cost only for good second-line windows, not generic long shots.
- [ ] 4.4 Re-run 4141, 433, and DB matrix scorecards with chain metrics.
- [ ] 4.5 Define acceptance criteria for a second-line shot window using xG/open-window/pressure/lane, so CM/WM shots are not forced over higher-value deliveries.

## 5. Goal-Layer Handoff

- [x] 5.1 Add diagnostics for final-third carry follow-up decisions by role.
- [x] 5.2 Expose carry-to-shot continuity trace components for future Goal evaluation.
- [x] 5.3 Document that multi-tick cut-ins and arc arrivals should move to Goal continuity instead of additional one-tick reward boosts.
- [x] 5.4 Audit existing short-horizon goal substitutes in pass/off-ball/value logic.
- [ ] 5.5 Define the first Goal-layer acceptance cases for `cut_inside_to_shoot`, `arc_arrival_for_cutback`, `wide_hold_for_overlap`, `release_pressure_with_layoff`, and `attack_far_post`.
