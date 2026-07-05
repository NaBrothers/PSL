# PSL 比赛引擎 V2：空间价值、决策奖励、Goal 连续性与战术系统技术方案

## 1. 当前问题

### 1.1 每 tick 直接重算动作，缺少决策连续性

当前引擎的核心循环接近：

```text
每个 tick -> 读取当前局势 -> 直接给动作打分 -> softmax 选动作 -> 执行动作
```

这导致球员像每 2 秒刷新一次大脑：

- 无球球员目标点频繁跳变。
- 防守球员会在 `approach / block_lane / mark_runner` 之间反复切换。
- 持球球员有时会刚接球就立刻传、带、射，缺少“连续执行一个短期计划”的感觉。
- 即使加了 target smoothing 和 velocity inertia，仍然只是修补物理层，不能解决“意图每 tick 重 roll”的根因。

真实比赛里，球员通常会持续执行一个短期意图：前插、回撤接应、拉边、护球观察、封内线、盯人、保护禁区。这个意图会随局势变化调整，但不会每 2 秒完全重置。

### 1.2 动作评分不是同一种“货币”

当前曾经出现过这些问题：

- `pass` 看接球点绝对价值。
- `carry` 看目标点价值或局部增量。
- `shoot` 看 xG。
- `hold` 看等待收益。
- `clear` 用危险区域和压力的规则。

这些分数不完全可比，所以会出现局部合理但整体奇怪的行为：

- 前锋在门前大幅回传。
- 后场横向大范围转移。
- 前锋斜长传回自家半场边后卫。
- 持球人连续粘球，等防守人追上。
- 传球少、带球多，或反过来一脚出球过多。

本质问题是：动作没有统一成“当前局面价值 -> 动作后局面价值”的增量收益。

### 1.3 传球模型拆分过早

当前实现里仍保留 `pass` 与 `pass_to_space` 的分支概念。实际上它们应该是同一个动作：

```text
pass_to_point(target_point)
```

区别只是目标点来源不同：

- 队友脚下
- 队友未来位置
- 肋部空间
- 弱侧空间
- 禁区落点
- 回做点

执行层也应该统一：球员选择理想目标点，传球能力、距离、压力、线路风险共同决定实际落点偏差，球飞到实际落点后再决定谁能接到。

### 1.4 无球跑位仍有模板化与目标跳变问题

虽然已经将部分无球进攻改为空间采样，但仍存在两个风险：

- 采样点过自由会打散阵型。
- 每 tick 重新采样会导致目标点抖动。

防守同理，空间点位选择如果没有意图连续性，会出现来回跑和频繁切换目标。

### 1.5 防守、抢断、盘带对抗需要更自然的空间交互

当前 `duel` 仍然容易变成一个被动作标签触发的事件。真实比赛里，对抗更像空间交互：

- 持球路线进入防守控制范围。
- 防守球员身体角度、速度、距离和抢断倾向影响对抗概率。
- 不一定要显式选择 `tackle` 才有对抗。

但是如果空间触发范围过大，又会导致 duels 爆炸。因此需要更精细地建模防守控制区，而不是简单扩大/缩小阈值。

### 1.6 速度模型与目标模型需要分离

已经明确：

- 最大速度应该由球员能力决定。
- 实际速度应该由意图、压力、目标距离和场上局势决定。
- 持球速度应该在无球最大速度基础上按盘带能力和压力衰减。

但仅有速度惯性不够。如果目标点每 tick 大跳，球员还是会表现出不自然的折返。因此需要目标连续性和意图连续性。

---

## 2. 整体分层架构

建议把比赛引擎拆成四层：

```text
战术系统层
    ↓ 调整 goal 权重 / 空间偏好 / 风险偏好
Goal 决策连续性层
    ↓ 选择并维持短期意图
动作奖励层
    ↓ 评估 pass/carry/shoot/hold/clear 等动作增量
空间价值层
    ↓ 计算空间、线路、压力、角度、风险等底层价值
物理执行层
    ↓ 速度、加速度、球飞行、传球偏差、对抗、接球
```

用户提出的四层可以对应为：

1. 底层：空间模型
2. 上层：决策奖励机制
3. 再上层：Goal 连续意图
4. 最上层：球队战术 + 个人角色/指令

### 2.1 底层：空间模型

空间模型回答：哪里有价值、哪里危险。

核心输入：

- 球位置
- 球员位置
- 对手位置
- 队友位置
- 球门位置
- 传球线路
- 角色/阵型锚点
- 越位线
- 压力范围

核心输出：

- `space_value(pos)`：这个点对进攻是否有价值
- `defensive_space_value(pos)`：这个点对防守是否有价值
- `shot_quality(pos)`：这个点射门质量如何
- `pass_lane_risk(origin, target)`：这条传球线风险多大
- `receiver_pressure(target)`：接球点压力多大
- `turnover_consequence(pos)`：这里丢球后果多严重
- `offside_risk(pos)`：目标点越位风险
- `shape_fit(pos, role_anchor)`：是否符合阵型/角色空间

空间层应该尽量不写“如果后场横传就扣分”这种模式规则，而是让后场横传因线路长、经过中路、被断后果高而自然低分。

### 2.2 上层：决策奖励机制

动作奖励层回答：这个动作是否让局面变好。

统一公式：

```text
action_score = success_prob * (after_state_value - current_state_value + continuity_value)
               - risk_cost
               - opportunity_cost
```

动作包括：

- `pass_to_point(target_point)`
- `carry_to(target_point)`
- `shoot(target)`
- `hold/shield/observe`
- `clear_to(target_point)`
- `defensive_move_to(target_point)`
- `tackle/duel` 作为空间交互的结果，而不是孤立硬动作

#### 2.2.1 传球模型

统一为：

```text
pass_to_point(target_point, intended_receiver=None)
```

候选点来源：

- 队友脚下
- 队友未来半步位置
- 队友前方空间
- 弱侧空间
- 禁区落点
- 回做点

评分：

```text
pass_score = expected_pass_value(...)
```

其中：

```text
success_prob = passer_skill
             * distance_factor
             * lane_safety
             * receiver_availability
             * first_touch_factor

risk_cost = (1 - success_prob) * turnover_consequence

after_value = pass_receive_value(target_point, receiver)
```

执行：

1. AI 选择理想目标点 `ideal_target`。
2. 根据短传/长传能力、距离、压力、线路风险计算落点偏差。
3. 得到 `actual_target`。
4. 球飞向 `actual_target`。
5. 到点后比较接球队友与防守球员谁先到。
6. 再进行接球/停球/拦截/争抢。

#### 2.2.2 带球模型

统一为：

```text
carry_to(target_point)
```

不是固定方向。目标点来自周围可达空间采样或空间梯度。

评分：

```text
carry_score = success_prob * (after_state_value - current_state_value + retain_value)
              - carry_risk
              - opportunity_cost
```

考虑：

- 目标点空间价值
- 路径上防守压力
- 持球人 Speed / Dribbling
- 是否改善射门角度
- 是否带向底线/死角
- 是否粘球过久

#### 2.2.3 射门模型

射门价值主要是 xG：

```text
shoot_score = shot_quality(pos) * goal_reward - possession_loss_cost
```

`shot_quality` 包含：

- 距离
- 角度
- 中路/边路
- 防守压力
- 射门线路是否被封
- 射手能力
- 门将扑救估计

#### 2.2.4 Hold / Shield / Observe

hold 不是站着不动，而是护球和观察：

- 低压时可以放慢节奏观察。
- 有压力时小范围调整身体和球的位置。
- 队友跑位正在变好时，等待有收益。
- 如果被逼抢太近，hold 风险上升。
- 连续持球过久，机会成本上升。

### 2.3 Goal 连续意图层

Goal 层回答：球员接下来几秒想完成什么短期意图。

它解决的问题：不要每 tick 直接重选 action。

#### 2.3.1 Goal 示例

无球进攻：

- `run_into_channel`
- `support_carrier`
- `hold_width`
- `drop_between_lines`
- `attack_box`
- `recycle_support`

持球：

- `progress_carry`
- `create_shot`
- `protect_ball`
- `switch_play`
- `through_ball`
- `recycle`

无球防守：

- `contain`
- `press`
- `cover_lane`
- `mark_runner`
- `protect_box`
- `recover_shape`

#### 2.3.2 Goal 不是硬 TTL

不要写：

```python
if goal.age < 3:
    keep_goal()
```

这是硬限制。

应该写：

```python
if best_new_goal_value > current_goal_value + switch_cost:
    switch_goal()
else:
    keep_goal()
```

Goal 有连续性，但可以随时被更高价值机会打断。

#### 2.3.3 Goal 数据结构建议

```python
@dataclass
class PlayerGoal:
    goal_type: str
    target_zone: tuple
    target_pos: tuple
    value: float
    confidence: float
    created_tick: int
    last_updated_tick: int
    context: dict
```

每 tick：

1. 评估当前 goal 是否还有效。
2. 评估候选新 goal。
3. 计算切换收益与切换成本。
4. 决定 keep / switch。
5. 当前 goal 产出本 tick action。

### 2.4 最上层：战术系统

战术系统不直接控制 action，而是调整 goal 和空间价值的权重。

#### 2.4.1 球队整体战术

例如：控球战术

- 提高 `support_carrier`, `recycle`, `switch_play`
- 降低无意义 long direct pass
- 提高 hold/observe 在低压下价值
- 提高传球安全性权重

快速反击

- 提高 `run_into_channel`, `progress_carry`, `through_ball`
- 降低 recycle 权重
- 允许更高风险传球

高位逼抢

- 提高 `press`, `counter_press`
- 提高前场防守目标线
- 降低回撤 shape 的切换成本

低位防守

- 提高 `protect_box`, `cover_lane`, `compact_shape`
- 降低 press
- 防守空间锚点更靠近禁区

#### 2.4.2 球员角色

角色决定 goal 权重。

中锋：

- `pin_center_back`
- `attack_box`
- `run_behind`
- `layoff`

伪九：

- `drop_between_lines`
- `link_play`
- `create_space`

边锋：

- `hold_width`
- `cut_inside`
- `attack_half_space`
- `run_behind_fullback`

边后卫：

- `overlap`
- `underlap`
- `support_backline`
- `switch_outlet`

后腰：

- `screen_defense`
- `recycle_possession`
- `progressive_pass_angle`
- `cover_fullback`

#### 2.4.3 个人指令

个人指令是角色上的微调：

- 更多前插
- 保持位置
- 多盘带
- 少冒险传球
- 更多传中
- 内切
- 拉边
- 多回撤接应

实现上都是 modifier：

```text
goal_value *= team_tactic_weight * role_weight * personal_instruction_weight
```

---

## 3. 详细技术方案

### 3.1 阶段一：稳定当前测试版，避免继续靠局部补丁

当前已经有部分改动：

- `value_model.py` 初版
- 自适应持球速度
- velocity inertia
- hold/shield
- pass target deviation
- team stats 补全
- shot/heatmap 修正

但是仍有问题：

- pass/carry/shot/hold 的 value scale 还不稳定。
- defense spatial movement 初版会造成 target 抖动。
- duel 空间触发还需要精细建模。
- 宏观比分和 duels 不稳定。

建议先不要再堆 action 级 if，而是按下面阶段推进。

### 3.2 阶段二：完善 Value Model

扩展 `value_model.py`，形成统一接口：

```python
def evaluate_space(pos, context) -> float

def evaluate_state(player, pos, context) -> float

def evaluate_pass_target(passer, target_point, receiver, context) -> PassValue

def evaluate_carry_target(carrier, target_point, context) -> CarryValue

def evaluate_shot(player, context) -> ShotValue

def evaluate_hold(player, context) -> HoldValue

def evaluate_defensive_position(player, pos, context) -> DefensiveValue
```

返回结构建议：

```python
@dataclass
class ValueResult:
    score: float
    success_prob: float
    risk_cost: float
    after_value: float
    current_value: float
    components: dict
```

这样 trace 能看到为什么某个动作被选中。

### 3.3 阶段三：统一传球模型

目标：只保留 `pass_to_point`。

实现步骤：

1. 合并 `_score_pass_options` 与 `_score_pass_to_space_options`。
2. 生成目标点集合：脚下、未来点、空间点、弱侧点、禁区点。
3. 所有点调用 `evaluate_pass_target()`。
4. 执行阶段引入 `ideal_target -> actual_target`。
5. 到点后统一 resolve：接球、拦截、争抢。
6. replay 兼容层仍可输出 `short_pass / long_pass / pass_to_space`，但内部统一。

### 3.4 阶段四：统一 Carry 模型

目标：`carry_to(point)` 由空间模型选目标，不枚举固定方向。

实现步骤：

1. 采样当前可达区域。
2. 候选点受角色空间、压力、路径风险、球员能力影响。
3. 评分使用 `evaluate_carry_target()`。
4. 执行阶段用自适应 carry speed。
5. 高速 carry 增加失误风险。
6. 粘球增加机会成本。

### 3.5 阶段五：引入 PlayerGoal

先做轻量版：

```python
class Player:
    current_goal: Optional[PlayerGoal]
```

每 tick：

```python
current_goal_value = evaluate_goal(current_goal)
best_new_goal = find_best_goal()

if best_new_goal.value > current_goal_value + switch_cost:
    current_goal = best_new_goal

action = current_goal.propose_action()
```

Goal 切换成本：

```text
switch_cost = base
            * context_stability
            * role_discipline
            * (1 - pressure_interrupt)
            * iq_adjustment
```

不是硬 TTL。

### 3.6 阶段六：无球进攻 Goal

无球进攻 goal：

- `support_carrier`
- `run_behind`
- `hold_width`
- `drop_between_lines`
- `attack_box`
- `recycle_support`

每个 goal 的 target 由空间模型连续更新，但 goal 本身有切换成本。

这样解决：

- 无球跑位每 tick 随机换点
- 边锋跨边
- 前锋忽然回撤又前插
- 阵型散掉

### 3.7 阶段七：无球防守 Goal

无球防守 goal：

- `contain`
- `press`
- `cover_lane`
- `mark_runner`
- `protect_box`
- `recover_shape`

目标：

- 防守球员不在 `approach / block / mark` 之间每 tick 跳。
- 防守目标点连续变化。
- 逼抢、封线、盯人都变成 goal 的执行方式。

防守 goal 的目标点应该来自连续防守价值场，而不是每 tick 重新随机采点。

### 3.8 阶段八：Duel 触发改成空间交互

当前问题：

- 只看 `tackle` 太少。
- 空间触发过宽又 duels 爆炸。

新方案：

```text
duel_probability = control_overlap
                 * defender_body_position
                 * defender_tackle_intent
                 * carrier_touch_size
                 * carrier_speed
                 * pressure_context
```

不是硬触发。

例如：

- 防守人只是 contain，duel 概率低。
- 防守人选择 press/tackle，duel 概率高。
- 持球人大步趟球，duel 概率高。
- 持球人护球，duel 概率低但推进慢。

### 3.9 阶段九：战术系统接入

战术系统不直接控制 action，而是调整 goal 和 value 权重。

接口示例：

```python
@dataclass
class TeamTacticProfile:
    mentality: float
    tempo: float
    width: float
    defensive_line: float
    pressing_intensity: float
    pass_directness: float
    risk_appetite: float
    buildup_patience: float
```

角色接口：

```python
@dataclass
class RoleProfile:
    goal_weights: dict[str, float]
    space_preferences: dict[str, float]
    risk_modifiers: dict[str, float]
```

最终 goal value：

```text
goal_value = base_value
           * team_tactic_weight
           * role_weight
           * personal_instruction_weight
           * ability_fit
           - risk_cost
           - switch_cost
```

---

## 4. 验证方案

### 4.1 宏观指标

每次修改跑至少：

- 1v1
- 5v5
- 10v10
- 强弱对抗

指标：

- 进球
- 射门
- 射正
- xG
- 传球成功率
- 抢断成功
- 过人成功
- 拦截
- 越位
- duels
- 持球时长
- 一脚出球比例

### 4.2 微观 trace

需要保留并分析：

- 每个 goal 的选择与切换
- goal value components
- action value components
- pass lane risk
- turnover consequence
- target smoothing
- velocity vector
- defensive control overlap

### 4.3 场面验证

重点看：

- 防守是否还来回跳点
- 无球进攻是否保持阵型层次
- 前锋持球是否合理射门/传球/护球
- 边路是否自然拉开或内切
- 后场是否减少危险横传
- 是否出现合理回传再组织

---

## 5. Hand-off 建议

给下一个 Agent 的建议顺序：

1. 不要继续堆 if-else 修局部行为。
2. 先完善 `value_model.py` 的 ValueResult 和 components。
3. 统一 pass/carry/hold/shoot 的 value scale。
4. 引入 PlayerGoal，但不要硬 TTL。
5. 先接无球进攻 goal，再接无球防守 goal。
6. 最后接战术系统权重。
7. 每一步都跑宏观 + trace，不要只看比分。

当前最关键的工程目标：

```text
从 “每 tick 直接选 action”
迁移到 “持续 goal -> goal 产生 action -> 物理执行”
```

这才是后续战术系统能成立的底层架构。
