# Design: Engine V2 Goal Continuity

## Context

The calibration work has exposed a boundary in the current reward-driven engine:

- one-tick scoring can compare pass/carry/shot/hold;
- one-tick scoring is a poor place to encode multi-tick intentions.

The Goal layer should carry short-term intent while still using the value model to choose concrete actions.

## Data Model

```python
@dataclass
class PlayerGoal:
    goal_type: str
    target_pos: tuple[float, float]
    value: float
    confidence: float
    created_tick: int
    last_updated_tick: int
    context: dict
```

Initial goal types:

- `cut_inside_to_shoot`
- `arc_arrival_for_cutback`
- `wide_hold_for_overlap`
- `release_pressure_with_layoff`
- `attack_far_post`
- `support_carrier`
- `recover_shape`

## Goal Selection

Goal selection must not be a hard TTL:

```python
if best_new_goal.value > current_goal.value + switch_cost:
    switch_goal()
else:
    keep_goal()
```

`switch_cost` should be continuous:

```text
switch_cost = base
            * context_stability
            * role_discipline
            * (1 - pressure_interrupt)
            * iq_adjustment
```

High-value immediate chances still interrupt goals. For example, a good shot should interrupt `cut_inside_to_shoot`.

## Goal Execution

Goals should not directly force actions. A goal proposes a bias or target for the existing candidate system:

- `cut_inside_to_shoot`: bias carry candidates toward half-space/central shooting lanes and prefer shooting once a credible shot window appears.
- `arc_arrival_for_cutback`: bias off-ball target toward the arc, using current dynamic anchor and pressure.
- `wide_hold_for_overlap`: bias hold/pass choices while an overlap support run is improving.
- `release_pressure_with_layoff`: bias short layoff targets when pressure is attracted.
- `attack_far_post`: bias off-ball target toward far-post arrival during wide delivery windows.

The value model remains responsible for action comparability and risk.

## Trace

Goal trace should include:

- current goal;
- candidate goals and values;
- switch cost;
- keep/switch reason;
- action bias emitted by the goal;
- action ultimately selected by the value model.

## Acceptance Focus

The first acceptance tests should prove continuity, not final football balance:

- A goal persists when its value remains close to the best alternative.
- A goal switches immediately when a significantly better opportunity appears.
- A goal biases target/action generation without hard-forcing the action.
- Carry-to-shot and arc-arrival flows become observable as goal state transitions.

## Initial A/B Findings

Short 4141, 433, and DB samples show the Goal layer has useful directional effects but is not ready to be enabled by default.

Observed improvements with `goal_continuity_enabled=True`:

- 433 produced more wide-player shots and a less FW-only shot distribution.
- 4141 produced a small amount of WM shooting that did not exist in the default run.
- DB samples showed wider role distribution in shots, especially W/WM involvement.

Observed remaining issues:

- CM second-line shots remain rare or absent.
- `arc_arrival_for_cutback` and `attack_far_post` can be held across many off-ball ticks, so raw goal counts are high and must be interpreted with switch counts.
- `wide_hold_for_overlap` and `release_pressure_with_layoff` are still rare in real short samples.
- Some gains are formation-dependent; the Goal layer should remain behind config until the per-goal windows are calibrated.

Role-fit calibration note:

- A strong attempt to make `arc_arrival_for_cutback` less attractive for front-line anchors reduced wide-player contribution and hurt the useful 433 signal.
- Position hard-limits are rejected. Role fit should stay continuous and evidence-driven.
- For now, keep the broader geometry-based arc/far-post formulas and rely on diagnostics (`goal` counts, switch counts, role breakdowns, `2L/2Lt/2La`) before further narrowing.

Cut-inside follow-up note:

- A/B diagnostics show `cut_inside_to_shoot` mostly converts into carry on the first action.
- The next decision after a cut-inside carry is still usually another carry or pass, not a shot.
- A small second-touch shot bias did not materially change short scorecards, which suggests the missing behavior is not just a one-line shot reward issue.
- Making the cut target more aggressive and adding distance-to-goal-target carry bias reduced wide-player shot contribution in short samples. This should not be used as a shortcut.
- Adding explicit `drive` / `finish` phase context to `cut_inside_to_shoot` improved traceability and produced some direct shot conversion from finish-phase cut goals. It still did not make the next decision after a drive carry consistently become a shot, which means the carry path itself often has not reached a credible finishing state.
- Adding a `release` phase for stalled wide drives makes the failure mode visible: a carrier can keep the cut goal after repeated wide carries without creating enough shot value. Early short samples show the release phase appears only rarely, so the next step is to improve the goal's phase transition and release target selection rather than increasing global pass or shot reward.
- Same-type goal updates should not blindly bypass switch cost every tick. Only meaningful lifecycle progression, such as `drive -> finish` or `drive -> release`, should update immediately. Repeated `drive -> drive` refreshes made cut goals persist too often and degraded short-sample role distribution.
- `release` can now also consider goal age, not only action-level consecutive carries, because ordinary actions can reset carry counters while the same cut intent remains conceptually active. Short 433 samples still show release rarely, which means stalled cut-ins often end through normal pass/default behavior before the release condition fires.
- Drive target diagnostics show many cut carries still choose wide or shallow targets. A mild target-fit bias toward existing good targets did not move short-sample outcomes, so the issue is likely candidate generation / path feasibility trade-off rather than small score weighting.
- Bucketed drive diagnostics show the better inside targets have higher future-shot gain but lower path feasibility. In a 433 trace, good cut targets averaged higher `future_shot_gain` than wide targets, but path feasibility was lower. This means the model is often seeing the right inside route as a real but risky dribble, not simply missing the target. Do not blindly boost these carries without also validating duel/path risk.
- Path-risk diagnostics show the cut-carry feasibility loss is mostly from route-intercept threat, not the final-third control term. In the sampled 433 trace, average `path_peak_threat` was high while `path_peak_final_third_control` stayed low. This argues against simply relaxing final-third path control.
- Target-density diagnostics show cut carry targets are not necessarily crowded: sampled targets averaged fewer than one defender inside 10m and the nearest defender was around 9m away. The larger issue is that the nearest attacking support around the cut target can be about 20m away, while a defender still threatens the route. This points toward coordinated support/decoy goals around the cut-in lane rather than lowering path-risk penalties.
- Focused support tests show the existing off-ball value model can naturally create nearby support around a cut lane in controlled DB-team contexts. The remaining issue is not a total absence of support behavior, but consistency across match states and especially second-line/central support quality.
- A direct inside-lane support reward in off-ball scoring was tested and rolled back. It improved some support indicators but produced unstable health-score outcomes: 433 shot volume could rise while non-FW finishing worsened, and 4141 wide/shot health regressed. This reinforces that support should be calibrated through broader space value and goal lifecycle diagnostics, not a one-off support multiplier.
- Off-ball deep support coverage diagnostics show that deeper support candidates can exist and even score higher than the chosen support point. In a 433 cut trace, CM deep-support candidates appeared in a minority of samples but had higher average score and stronger support/second-line components than the average chosen point. This suggests the next bottleneck is often ball delivery or post-receive action, not merely off-ball candidate generation.
- Future work should let the active `cut_inside_to_shoot` goal propose a multi-tick plan target and completion condition, rather than stacking global shot/carry reward terms.

Decision: enable `goal_continuity_enabled=True` by default so live and local matches generate observable Goal behavior. Keep explicit A/B controls in diagnostics (`--no-goal-continuity`) and config for rollback while calibration continues.

## Migration

1. Add `PlayerGoal` and pure goal-selection helpers.
2. Add focused unit tests for switching semantics and goal proposals.
3. Wire goal trace without changing match behavior.
4. Connect one attacking goal at a time behind a small integration surface.
5. Re-run structural diagnostics before enabling more goals.
