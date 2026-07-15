# Engine V2 行为审计基线

## 目的

这份文档将比赛引擎的结论分为三类：

- **已证实**：代码路径和可重复的窄场景测试共同证明的局部性质。
- **待验证**：机制上可能改善某项比赛表现，但尚无固定比赛基线或分布证据。
- **风险**：当前实现的明确假设、耦合点或未覆盖边界。

未完成比赛级对比前，任何“更接近真实英超”都只能是待验证结论，不能作为继续调参的依据。

## 当前机制审计

| 机制 | 代码入口 | 已证实 | 待验证与风险 |
| --- | --- | --- | --- |
| TacticalTask 与球员信念 | `tactical_task.rs`、`match_runner.rs` | Task 保存原始目标、承诺、到期时间、结构债务；运动目标由 Task 软解析，不会覆盖原始目标。决策信念只由视野内实体和衰减记忆构成，IQ 只影响可见信息的置信度与记忆。 | Task 的接受阈值、期限和结构债务仍是模型参数；其是否恢复了足够的无球接应、盘带自由度和队形弹性尚未做比赛级验证。 |
| 阵型与任务运动 | `player_effective_movement_target`、`task_motion_target` | 活跃 Task 会在真实运动和未来位置投影中使用同一任务运动目标；普通 Team Plan 回拉不再直接覆盖该路径。 | `team_plan_movement_target` 仍存在于通用 Team Plan 投影接口；任何新增调用必须证明不会绕过 Task 路径。阵型宽度、纵深和恢复速度尚无基线。 |
| 传球到达与接球 | `arrival.rs`、`runner_pass_arrival_plan` | 候选投影与飞行期结算使用相同的传球到达模型；该模型复用球员加速度、转向、速度和运动意图。传球技术保留、到达竞争和第一脚失误已分离。 | 接球意图优势和可达竞争的宏观校准尚未完成；快照只冻结出球时的到达输入，比赛级传球成功率和失误类型分布仍未知。 |
| 护球与抢断 | `interactions.rs`、`resolve_runner_duel` | `hold`、`shield`、`reorient` 可进入空间对抗窗口；控制球被断会计为抢断/失去球权，不会伪记为带球过人。 | 触发次数仍依赖防守职责分配、接触概率和属性差异；抢断总量、位置和犯规式上抢风险未做比赛级验证。 |
| 射门动作竞争 | `apply_temporal_option_values_with_contexts` | 动作总价值显式为局部价值、团队策略价值与未来价值之和；射门不会再被通用的持球未来价值完全压制。开放近距离场景中，射门可胜过继续带球。 | 射门权重是当前模型假设，不是英超统计校准结果；射门数、射正率、xG 和禁区内决策分布尚未建立基线。 |
| 接球窗口压迫 | `off_ball_defense.rs` | 防守威胁在接球窗口即可成立，不再只等待持球时间累积；有保护时可分配一名可达的第一上抢人。 | 压迫频率、首压时机、协防暴露和中前场抢断率均未做比赛级验证。 |
| 朝向与可见性 | `vision.rs` | 显式的 `0°` 朝向不再被误判为未初始化，因此球员可见性不会被错误翻转。 | 视野范围、记忆衰减与 IQ 的实际分布仍未校准。 |

## 已证实的契约

下列测试只证明局部因果链，不代表整场真实性：

- `tactical_task::tests::invisible_entities_do_not_enter_belief`
- `tactical_task::tests::higher_iq_improves_use_of_visible_clues_without_revealing_hidden_entities`
- `tactical_task::tests::task_preserves_raw_target_when_motion_target_is_resolved`
- `tactical_task::tests::high_value_support_is_not_rejected_only_for_anchor_distance`
- `arrival::tests::committed_receiver_can_control_a_ball_reached_during_flight`
- `match_runner::tests::projected_pass_to_an_unreachable_target_has_no_direct_receipt`
- `match_runner::tests::executed_pass_to_an_unreachable_target_stays_loose_without_a_receipt`
- `interactions::tests::shielding_exposes_the_holder_without_becoming_a_dribble_contact`
- `match_runner::tests::shielding_duel_awards_a_tackle_without_recording_a_take_on`
- `off_ball_defense::tests::receiving_window_with_cover_triggers_local_engagement`
- `match_runner::tests::open_close_range_finisher_selects_terminal_shot_over_another_carry`
- `match_runner::tests::normal_replay_frames_respect_the_player_motion_bound`

## 可观测性协议

启用 `EngineConfig.trace.detail = "full"` 时，`trace["decisions"]` 现包含
`phase = "tactical_task"` 的记录。每条记录必须能回答：

1. **什么意图来源**：`source.kind` 是 `goal` 或 `on_ball_action`，并带有 Goal 或动作类型。
2. **基于什么局部信息**：`belief.ball_pos` 与 `belief.ball_confidence`。
3. **为什么继续、替换或拒绝**：`resolution.outcome`、`candidate_value`、`retained_value`。
4. **最终为什么朝某处移动**：同时记录 `tactical_anchor`、`raw_target` 和 `effective_target`。
5. **任务何时应结束**：`accepted_tick`、`expires_tick`、`commitment`、`formation_debt` 与 `interruption`。

`trace_detail = "off"` 不产生这些记录，也不应改变 Task 状态、RNG 序列或动作选择。

## 后续改动准入

在修改任何比赛行为前，必须先填写并满足以下链路：

1. **现象**：固定 seed、固定阵容、固定配置下可复现，且标注发生的 tick、球员和事件。
2. **决策证据**：给出相关的 Goal/Task、候选动作或防守职责 trace，不能只描述回放画面。
3. **执行证据**：给出运动、到达、对抗或射门结算的 trace，区分“选错”与“执行结果不同”。
4. **单一根因假设**：说明哪个模块的接口或不变量被违反；没有此项不得修改参数或增加规则。
5. **窄场景契约**：先新增失败测试，再实现修复；测试必须验证该根因，不能只断言最终比分。
6. **比赛级验收**：在批准固定基线后，比较改前/改后的事件分布；不将联赛均值硬编码到运行时规则。

## 尚未建立的比赛级基线

以下指标目前均为待验证，不能据此声称当前引擎已经改善或退化：

- 每队射门、禁区内射门、射正、xG 与射门来源；
- 传球尝试、成功率、前进/横向/回传比例、失误原因；
- 抢断尝试、成功抢断、持球对抗和拦截的位置与时机；
- 单次控球时长、完成传球串长度、射门前传球数；
- 无球任务持续时间、取消率、到位前任务替换率；
- 压迫触发位置、第一上抢到接球人的时间、上抢后的协防暴露；
- 队形宽度、纵深、局部拥挤和任务结束后的结构恢复。

固定基线应只用于离线验收和趋势比较，不得作为运行时的特判阈值。
