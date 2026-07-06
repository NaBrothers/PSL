## Context

Recent samples show engine v2 still has structural play issues: full matches produce too many shots with low shot accuracy, short trace samples are dominated by carry/hold, and line progress values show compressed team shape. The evaluator migration makes these problems observable, but the value scale still needs calibration before a Goal layer can be meaningful.

## Goals / Non-Goals

**Goals:**
- Improve action competition through continuous reward shaping.
- Make low-quality shots less attractive without hard forbidding shots.
- Make no-gain carry and passive hold less attractive without forced pass rules.
- Use macro stats plus position/action trace to evaluate results.

**Non-Goals:**
- Do not introduce `PlayerGoal`.
- Do not add scenario-specific hard gates.
- Do not directly tune to a final league-average target in this pass.
- Do not change web/API/bot behavior.

## Decisions

### Decision: Continuous shaping only

Value adjustments should use continuous functions such as smoothstep-style multipliers, value deltas, risk costs, or pressure terms. This avoids overfitting a replay symptom with brittle if/else rules.

### Decision: Fix value competition before Goal continuity

Persistent goals should not be introduced until pass/carry/shot/hold compete on a reasonable value scale. Otherwise the Goal layer would make incorrect action preferences more persistent.

### Decision: Validate with both macro and micro evidence

Macro stats alone are insufficient. Each calibration run should inspect action counts by position, shot xG/score, pass delta, carry gain, hold score, and rough line progression.

### Decision: Treat second-line finishing as a chain, not a one-tick action

Recent 4141 samples show the wide-to-forward-to-second-line chain can exist while the final second-line receiver still recycles possession. The current diagnostic example is:

- `chain W-FW-2L-S/nextC/P/H=4/10/0/1/9/0`

This means the wide player can find the forward, the forward can lay off to midfield, but the receiver almost always passes again instead of taking the first-time shot. Future changes should target this chain explicitly:

- observe wide final-third pass into FW;
- observe FW layoff into CM/WM/AM;
- inspect the second-line receiver's next candidate scores;
- only then adjust first-time shot readiness or recycle cost.

This avoids forcing WM/CM shots from poor locations and keeps the fix in the value model rather than hard-coding a tactical script.

### Decision: Do not force second-line shots over higher-value deliveries

Controlled value checks show a second-line receiver at roughly 21-23m can still have a low shot score when a higher-value wide or half-space delivery is available. This is not necessarily a bug. A second-line shot should only win when the receiver has a credible first-time window:

- acceptable xG/open-medium-window;
- manageable pressure and lane obstruction;
- no clearly superior forward or wide delivery;
- recycle/pass value that does not pay for the current shot window.

Future calibration should therefore target the creation of `arc ready` windows and the post-layoff candidate competition, not a blanket boost to CM/WM shooting.

### Decision: Carry-to-shot continuity belongs to the Goal layer

Recent 4141 and 433 traces show a repeated pattern:

- WM/CM can have carry candidates with positive `future_shot_gain`;
- after the carry, the next decision is usually another carry or pass;
- the shot candidate still has poor xG/shot-readiness because the player has not yet completed a coherent "cut inside to shoot" plan.

This should not be solved by stacking one-tick reward boosts until the immediate carry wins every comparison. That would overfit a replay symptom and make the player oscillate between local rewards. Instead:

- current value calibration may expose `future_shot_gain`, `carry_to_shoot_window`, and `wide_second_line_carry_window` as trace components;
- current diagnostics may report the next decision after a final-third carry;
- persistent intent such as "cut inside to create a shot", "hold and wait for overlap", or "arrive at the arc for a cutback" should be implemented in the next Goal continuity layer.

The value layer should stay responsible for action comparability; the Goal layer should carry multi-tick intent.

### Decision: Rest defense must be measured separately from attacking shape

Visual replay inspection can make the attacking team look over-compressed when the ball reaches the final third. Rest defense should be measured explicitly:

- actual progress of deeper defensive/support roles while attacking;
- target progress and anchor progress for those same players;
- max progress of the rest-defense layer;
- opponent front-line progress left behind the attack.

This diagnostic separates a true tactical problem from a replay perspective or temporary movement artifact. Early DB and 433 samples show rest-defense actual/target progress staying around midfield rather than the whole line joining the attack, but this should remain in scorecards while Goal continuity is tuned.

Follow-up replay inspection of `data/replays/20260706_130213_测试玩家A_测试玩家C_2-0.jsonl` showed genuine suspicious frames: while the attacking ball was in the final third, the rest-defense layer could target progress around `0.60-0.72`, leaving the opponent forward behind them. The fix should not be a hard position rule. The current mitigation changes off-ball attacking support sampling so low-depth roles remain closer to their tactical anchor before being pulled toward the carrier. This improves `rest act/tgt/anc/max/front` diagnostics, but can reduce some wide attacking involvement in short samples, so it remains a calibration trade-off to monitor.

### Health Scorecard Findings

The structural health scorecard condenses role distribution, rest defense, arc readiness, and Goal conversion into a short A/B table. Current samples show:

- Rest defense is mostly acceptable after the support-sampling mitigation.
- Wide final-third touches are often acceptable, especially in DB samples.
- Non-FW shot share remains too low across 433, 4141, and DB samples.
- `arcReady` is usually weak but not always catastrophic.
- `cut_inside_to_shoot` first actions can become carries or occasional shots, but `cutNextS` remains consistently bad.

Current priority: improve Goal completion and shot distribution after wide/cut actions. Do not spend the next iteration on rest-defense unless new replay evidence shows regression.

### Audit: Existing short-horizon goal substitutes

The current engine still contains several short-horizon substitutes for tactical intent. They are acceptable as transitional candidate generation or trace signals, but should not be expanded further in this calibration change:

- `pass_to_point` candidate generation includes stale release, layoff, cutback, box delivery, and second-line arc candidates derived from geometry.
- off-ball attacking candidate generation includes carrier-near support points, central-arrival points, half-space outlets, and far-post arrivals.
- value evaluation includes continuity terms such as pressure release, stale release, layoff retention, second-line cutback, carry-to-shot, and wide second-line carry windows.

These pieces are not hard action gates, but they are still trying to express multi-tick intentions through one-tick rewards or candidate lists. The Goal layer should absorb them into explicit, persistent intents:

- `cut_inside_to_shoot`;
- `arc_arrival_for_cutback`;
- `wide_hold_for_overlap`;
- `release_pressure_with_layoff`;
- `attack_far_post`.

After Goal continuity exists, the value layer should keep only generic action evaluation and expose the above as diagnostic components or goal-local priors, not global reward patches.

## Risks / Trade-offs

- **Over-suppressing shots** -> monitor strong-vs-weak scoring and shot xG instead of only shot count.
- **Pass spam** -> monitor pass success and backwards/recycle behavior once pass value is raised.
- **Carry collapse** -> ensure positive carry gains still win naturally when space is available.
- **Short samples are noisy** -> treat them as directional and confirm with at least small full-match samples.
- **Second-line overcorrection** -> if second-line first-time shots are over-rewarded, the engine can regress into low-quality edge shots. Monitor xG, distance, and the new chain metrics together.

## Migration Plan

1. Replace discrete value-shaping thresholds with smooth reward curves where needed.
2. Run focused tests and short trace samples.
3. Run small full-match samples for equal and strong-vs-weak teams.
4. Summarize remaining macro and micro problems.
