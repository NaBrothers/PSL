# Proposal: Add Engine V2 Goal Continuity

## Problem

Engine v2 now has a value model and structural diagnostics, but several realistic football behaviors remain hard to express with one-tick action scoring:

- a wide player cutting inside over multiple touches to create a shot;
- a midfielder arriving at the arc for a cutback;
- a wide carrier holding briefly for an overlap;
- a pressured carrier releasing with a layoff;
- a far-side attacker attacking the far post.

Recent diagnostics show that trying to solve these with stronger immediate reward terms risks overfitting: the same reward boost can reduce total shots, increase recycle/carry loops, or force poor long-range attempts.

## Scope

Introduce a lightweight Goal continuity layer for engine v2 as a first-class concept:

- `PlayerGoal` data model;
- goal value and switch-cost semantics;
- traceable goal evaluation;
- first acceptance cases for attacking continuity.

This change should not replace the existing value model. Goals should sit above it and bias candidate/action generation for a few ticks while remaining interruptible by higher-value opportunities.

## Non-Goals

- Do not implement full tactics or personal instructions.
- Do not add hard TTLs or forced action scripts.
- Do not remove existing pass/carry/shot evaluators.
- Do not require web/API changes.

## Success Criteria

- Goal switching uses value advantage over switch cost, not a fixed minimum duration.
- Goal state can persist across ticks when the current goal remains competitive.
- Higher-value opportunities can interrupt a goal immediately.
- First attacking goals have tests:
  - `cut_inside_to_shoot`;
  - `arc_arrival_for_cutback`;
  - `wide_hold_for_overlap`;
  - `release_pressure_with_layoff`;
  - `attack_far_post`.
