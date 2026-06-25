# PSL Web 端实现计划

## 架构决策总结

| 决策项 | 结论 |
|--------|------|
| 范围 | 对齐现有全部玩法，不新增 |
| 身份 | QQ 号选择 + 4位 PIN，存 users 表 |
| API 风格 | 资源式业务 API |
| 前端栈 | Vite + React + TypeScript + Tailwind + Shadcn/ui |
| UI 风格 | 深色足球经理手游风格，手机优先 |
| 后端框架 | FastAPI 独立进程，8888 端口 |
| 比赛体验 | 快速模式（同步JSON）+ 观看模式（SSE推送） |
| 并发 | 完全不限制，多场并发 |
| 回放 | 嵌入 Web 端作为比赛动画页面 |
| 与 bot 关系 | 独立进程，共享 SQLite（WAL） |

## 重构策略：业务逻辑复用

### 现状问题

当前 `kernel/` 层把业务逻辑和 nonebot IO 耦合在一起：

```python
# kernel/lottery.py — 逻辑和消息发送混合
async def try_single(user, pool):
    if user.money < g_pool[pool]["cost"]:        # 业务校验
        await try_lottery.finish(...)             # bot 输出（耦合）
    card = g_pool[pool]["pool"].choice(user)      # 业务逻辑
    id = Bag.addToBag(user, card)                 # 业务逻辑
    user.spend(g_pool[pool]["cost"])              # 业务逻辑
    await try_lottery.finish(toImage(ret))        # bot 输出（耦合）
```

这导致 Web 端无法复用这些逻辑，必须重写一遍。

### 目标架构

```
service/          # 纯业务逻辑，无 IO，返回结果数据或抛业务异常
  lottery.py      # draw_single(user, pool) -> DrawResult | raises InsufficientFunds
  squad.py        # swap_players(user, id1, id2) -> SwapResult | raises NotFound
  match.py        # run_match(user1, user2, mode) -> MatchOutput
  transfer.py     # buy_card(user, card_id) -> BuyResult | raises ...
  league.py       # register(user) -> ..., play_round(user, mode) -> MatchOutput
  challenge.py    # play_challenge(user, difficulty, mode) -> ChallengeResult
  player_ops.py   # upgrade(user, main_id, sub_id) -> UpgradeResult

kernel/           # bot adapter：解析命令 → 调 service → 格式化文本/图片输出
server/routes/    # web adapter：解析请求 → 调 service → 返回 JSON
```

### 重构原则

1. **随 Phase 逐步抽取，不做 big-bang 重构**
   - 每实现一个 Web 模块时，顺手把对应 `kernel/` 的业务逻辑抽到 `service/`
   - 然后 `kernel/` 改为调用 service，bot 行为不变
   - Web route 也调用同一个 service

2. **Service 层约束**
   - 纯 Python 函数/类，不依赖 nonebot、不依赖 FastAPI
   - 不做消息格式化、不调 `toImage`、不 `await matcher.send`
   - 返回结构化数据（dataclass / TypedDict），由 adapter 层决定怎么展示
   - 业务错误用自定义异常（`InsufficientFunds`, `CardNotFound`, `InvalidFormation` 等）

3. **Model 层保持现状**
   - `model/` 的数据库操作可以直接被 service 调用
   - 后续如果需要，再把 model 迁移到 repository 模式（已有雏形）

4. **渐进式验证**
   - 每抽完一个 service，跑现有 bot 测试确认功能不变
   - Web route 和 bot kernel 调用同一个 service 入口

### 抽取顺序（对应 Phase）

| Phase | 抽取的 Service | 对应 kernel 文件 |
|-------|---------------|-----------------|
| Phase 1 | `service/auth.py` | 新增（无现有 kernel） |
| Phase 2 | `service/squad.py` | `kernel/formation.py` |
| Phase 4 | `service/match.py` | `kernel/game.py` + `engine/game.py` |
| Phase 3 | `service/bag.py` | `kernel/bag.py` |
| Phase 5 | `service/lottery.py` | `kernel/lottery.py` + `kernel/pool.py` |
| Phase 6 | `service/transfer.py` | `kernel/transfer.py` |
| Phase 7 | `service/player_ops.py` | `kernel/player.py` |
| Phase 8 | `service/league.py` | `kernel/league.py` |
| Phase 9 | `service/challenge.py` | `kernel/challenge.py` |

### Service 返回值示例

```python
@dataclass
class DrawResult:
    cards: List[CardData]        # 抽到的卡
    cost: int                    # 花费
    remaining_money: int         # 剩余余额

@dataclass
class MatchOutput:
    result: MatchResult          # 复用现有 engine 类型
    report_text: str             # 战报文本
    stats_text: str              # 统计文本
    replay_path: Optional[str]   # 回放文件路径
    broadcasts: List[str]        # 播报文本列表（观看模式用）

@dataclass  
class SwapResult:
    success: bool
    squad: List[CardData]        # 更新后的阵容
```

---

## 目录结构

```
PSL/
  web/
    package.json
    vite.config.ts
    src/
      main.tsx
      api/
      pages/
      components/
      replay/         # 迁移现有 canvas 逻辑
    dist/             # 构建产物，FastAPI 静态服务
  server/
    __init__.py
    main.py           # uvicorn 启动入口
    app.py            # FastAPI 实例，mount 静态资源和路由
    config.py         # 端口、DB路径、密钥等
    database.py       # 独立 SQLite 连接（WAL）
    auth.py           # PIN hash、JWT 签发校验
    dependencies.py   # FastAPI Depends 注入当前用户
    schemas.py        # Pydantic DTOs
    routes/
      auth.py
      bag.py
      squad.py
      match.py
      lottery.py
      transfer.py
      league.py
      challenge.py
      player.py
      replay.py
    services/
      squad.py
      bag.py
      match.py
      lottery.py
      transfer.py
      player_ops.py
      league.py
      challenge.py
  bot/                # 现有 nonebot，不动
  database/           # 共享
  data/replays/       # 共享
  assets/avatars/     # 球员头像
```

---

## Phase 0：基础设施搭建

### 0.1 数据库 Schema 升级

- `users` 表新增 `WebPinHash TEXT DEFAULT NULL`
- 修改 `database/init_db.py` 的 SCHEMAS
- 提供 migration 语句给已有数据库：

```sql
ALTER TABLE users ADD COLUMN WebPinHash TEXT DEFAULT NULL;
```

### 0.2 FastAPI 后端骨架

- `server/app.py`：FastAPI 实例，mount 静态资源 (`web/dist`)、replay 文件 (`data/replays`)、球员头像 (`assets/avatars`)
- `server/database.py`：独立的 SQLite 连接（WAL 模式，复用 `psl.db`）
- `server/config.py`：端口、DB 路径、JWT 密钥等
- `server/auth.py`：PIN hash 工具（pbkdf2）、JWT token 签发校验
- `server/dependencies.py`：FastAPI Depends 注入当前用户
- 启动入口：`python -m server` 或 `python server/main.py`

### 0.3 前端项目初始化

- `web/` 下 Vite + React + TypeScript 模板
- 安装 Tailwind CSS、Shadcn/ui、axios
- `vite.config.ts`：开发时 proxy `/api` 和 `/replays` 到 localhost:8888
- 基础布局：App shell + 底部 Tab 导航 + React Router

---

## Phase 1：认证模块

### 1.1 后端

`server/routes/auth.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/players` | 返回所有玩家列表 `[{id, qq, name, has_pin}]` |
| POST | `/api/auth/setup-pin` | `{qq, pin}` 首次设置，hash 存入 users |
| POST | `/api/auth/login` | `{qq, pin}` 校验，返回 JWT token |
| GET | `/api/me` | 当前用户信息（余额、等级、阵型） |

### 1.2 前端

- `LoginPage.tsx`：玩家列表选择 → 输入/设置 PIN → 登录
- token 存 localStorage，axios interceptor 自动带 Authorization header

---

## Phase 2：球队/阵容模块

### 2.1 后端

`server/services/squad.py`：封装阵容查询、替换、自动排阵、换阵型

`server/routes/squad.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/squad` | 当前阵容（球员卡详细信息 + 位置 + 能力值） |
| POST | `/api/squad/formation` | 切换阵型 `{formation: "433"}` |
| POST | `/api/squad/swap` | 替换两个球员 `{card_id_1, card_id_2}` |
| POST | `/api/squad/auto` | 自动排阵 |
| GET | `/api/squad/{user_id}` | 查看他人阵容 |

### 2.2 前端

- `SquadPage.tsx`：2D 球场 + 球员槽位（SVG 绝对定位）
- 球员卡组件：球衣图标 + 位置标签 + 评分 + 星级 + 风格 + 突破
- 底部替补横滑栏
- 点击槽位弹出替换选择 Sheet
- 阵型切换下拉

---

## Phase 3：背包模块

### 3.1 后端

`server/services/bag.py`：封装背包查询、搜索、回收

`server/routes/bag.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bag?page=&query=` | 分页、搜索 |
| GET | `/api/cards/{id}` | 球员卡详情（能力雷达、位置适配、生涯统计） |
| POST | `/api/cards/{id}/lock` | 锁定/解锁 |
| POST | `/api/cards/recycle` | 批量回收 `{ids: [...]}` |

### 3.2 前端

- `BagPage.tsx`：卡片网格/列表切换，搜索栏，分页
- `CardDetailSheet.tsx`：能力值面板、位置适配图、赛季/生涯数据
- 批量选择 + 回收确认

---

## Phase 4：比赛模块

### 4.1 后端

`server/services/match.py`：封装比赛引擎调用

- 友谊赛：同步跑 `Game.run_simulation()`，返回 JSON
- 观看模式：SSE endpoint，引擎每个 broadcast interval 推事件
- 十连/赔率：循环跑 N 场，返回聚合结果

`server/routes/match.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/matches/opponents` | 可挑战对手列表 |
| POST | `/api/matches` | `{opponent_id, mode: "quick"\|"watch"\|"ten"\|"odds"}` |
| GET | `/api/matches/{id}/stream` | SSE 实时事件流（观看模式） |
| GET | `/api/matches/{id}/result` | 完整比赛结果 JSON |

### 4.2 前端

- `MatchPage.tsx`：对手选择 → 模式选择 → 开始
- `MatchLivePage.tsx`：实时文字播报滚动 + 比分面板
- `MatchResultPage.tsx`：战报 + 统计面板 + 回放入口
- 回放路由到 `ReplayPage.tsx`

---

## Phase 5：抽卡模块

### 5.1 后端

`server/services/lottery.py`：封装卡池查询、单抽、十连、奖励抽

`server/routes/lottery.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/lottery/pools` | 可用卡池列表（价格、描述、持有奖励包数量） |
| POST | `/api/lottery/draw` | `{pool, count: 1\|10, type: "normal"\|"reward"}` |

### 5.2 前端

- `LotteryPage.tsx`：卡池列表 → 点击抽卡 → 结果动画/展示
- 单抽翻卡动画 + 十连展示

---

## Phase 6：转会模块

### 6.1 后端

`server/services/transfer.py`：封装上架、购买、下架

`server/routes/transfer.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/transfer?page=` | 转会市场列表 |
| POST | `/api/transfer/list` | 上架 `{card_id, price}` |
| POST | `/api/transfer/buy` | 购买 `{card_id}` |
| POST | `/api/transfer/cancel` | 下架 `{card_id}` |

### 6.2 前端

- `TransferPage.tsx`：市场列表 + 购买确认 + 我的上架

---

## Phase 7：球员强化/突破模块

### 7.1 后端

`server/services/player_ops.py`：封装强化、突破逻辑

`server/routes/player.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cards/upgrade` | 强化 `{main_id, sub_id}` |
| POST | `/api/cards/breach` | 突破 `{main_id, sub_id}` |
| POST | `/api/cards/{id}/compare` | 对比两张卡 `{other_id}` |

### 7.2 前端

- 集成在 `CardDetailSheet` 或独立 `UpgradePage.tsx`
- 主卡 + 副卡选择 → 预览结果 → 确认

---

## Phase 8：联赛模块

### 8.1 后端

`server/services/league.py`：封装报名、开赛、赛程、积分、榜单、奖励

`server/routes/league.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/league` | 当前联赛状态（赛季、轮次、积分榜） |
| POST | `/api/league/register` | 报名 |
| POST | `/api/league/play` | 踢本轮比赛 `{mode: "quick"\|"watch"}` |
| GET | `/api/league/schedule` | 赛程表 |
| GET | `/api/league/standings` | 积分榜 |
| GET | `/api/league/stats` | 数据榜（射手、助攻等） |

### 8.2 前端

- `LeaguePage.tsx`：积分榜 + 赛程 + 当前对阵 + 开赛按钮
- 赛季奖励展示

---

## Phase 9：挑战赛模块

### 9.1 后端

`server/services/challenge.py`：封装 NPC 巡回赛逻辑

`server/routes/challenge.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/challenge` | 今日 NPC + 难度列表 + 剩余次数 |
| GET | `/api/challenge/squad/{difficulty}` | NPC 阵容 |
| POST | `/api/challenge/play` | `{difficulty, mode}` |

### 9.2 前端

- `ChallengePage.tsx`：今日对手 + 难度选择 + 开赛

---

## Phase 10：回放集成

- 将现有 `web/replay.html` 的 canvas 逻辑迁移为 `web/src/replay/ReplayViewer.tsx`
- `ReplayPage.tsx`：加载指定 `.jsonl` 文件，渲染 canvas 播放器
- 路由：`/replay/:filename`
- FastAPI mount `/replays` 提供静态 jsonl 文件

---

## Phase 11：部署与联调

- `server/main.py`：`uvicorn server.app:app --host 0.0.0.0 --port 8888`
- 构建前端：`cd web && npm run build`，产物在 `web/dist/`
- FastAPI `StaticFiles` mount `web/dist` 作为 SPA fallback
- 移除旧的 `replay_server.py` 的 `http.server`（由 FastAPI 替代）
- bot 端的 `start_replay_server(8888)` 改为不启动（由独立 web server 提供）
- Docker/systemd 配置两个进程：`bot.py`（8080）+ `server`（8888）

---

## 实现顺序

```
Phase 0 → Phase 1 → Phase 2 → Phase 4 → Phase 10 → Phase 3 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 11
```

优先级：基础设施 → 认证 → 阵容（核心页面）→ 比赛（核心玩法）→ 回放 → 其余模块 → 部署。

---

## 关键技术点

| 点 | 方案 |
|----|------|
| Session/Auth | JWT（PyJWT），token 有效期 7 天 |
| SSE 比赛直播 | FastAPI `StreamingResponse` + `asyncio.Queue` |
| 引擎复用 | Web server 直接 import `engine.game.Game`（`sys.path` 加 bot 目录） |
| 静态资源 | Vite build → `web/dist/`，FastAPI `StaticFiles` + SPA fallback |
| 球员头像 | `assets/avatars/` mount 为 `/assets/avatars` |
| 数据库并发 | SQLite WAL，`check_same_thread=False`，多进程安全 |
| 前后端类型对齐 | 后端 Pydantic schema → 手动维护前端 TypeScript interface（后续可用 openapi-typescript 自动生成） |
| 并发控制 | 无全局锁，多场比赛完全并发，DB 原子性由 SQLite 事务保证 |

---

## API 完整列表

### 认证
- `GET /api/players`
- `POST /api/auth/setup-pin`
- `POST /api/auth/login`
- `GET /api/me`

### 阵容
- `GET /api/squad`
- `POST /api/squad/formation`
- `POST /api/squad/swap`
- `POST /api/squad/auto`
- `GET /api/squad/{user_id}`

### 背包
- `GET /api/bag?page=&query=`
- `GET /api/cards/{id}`
- `POST /api/cards/{id}/lock`
- `POST /api/cards/recycle`

### 比赛
- `GET /api/matches/opponents`
- `POST /api/matches`
- `GET /api/matches/{id}/stream`
- `GET /api/matches/{id}/result`

### 抽卡
- `GET /api/lottery/pools`
- `POST /api/lottery/draw`

### 转会
- `GET /api/transfer?page=`
- `POST /api/transfer/list`
- `POST /api/transfer/buy`
- `POST /api/transfer/cancel`

### 球员操作
- `POST /api/cards/upgrade`
- `POST /api/cards/breach`
- `POST /api/cards/{id}/compare`

### 联赛
- `GET /api/league`
- `POST /api/league/register`
- `POST /api/league/play`
- `GET /api/league/schedule`
- `GET /api/league/standings`
- `GET /api/league/stats`

### 挑战赛
- `GET /api/challenge`
- `GET /api/challenge/squad/{difficulty}`
- `POST /api/challenge/play`

### 回放
- `GET /replays` — 回放文件列表
- `GET /replays/{filename}` — 回放 jsonl 文件

### 静态资源
- `GET /assets/avatars/{player_id}.png`
- `GET /*` — SPA fallback（web/dist）
