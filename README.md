# QQ群足球小游戏

## 1. 部署
运行脚本安装 Python/Rust 依赖、构建 release 版比赛引擎、初始化 SQLite 数据库并安装 NapCatQQ：
```
bash ./config.sh
```

## 2. 配置 NapCatQQ

安装脚本会自动安装 NapCatQQ。安装完成后：

1. 启动 NapCat 并扫码登录 QQ
2. 打开 NapCat WebUI，在「网络配置」中新建反向 WebSocket，地址填写：
   ```
   ws://127.0.0.1:8080/onebot/v11/ws/
   ```
3. 也可以直接使用 `napcat/onebot11_1427259739.json` 作为参考配置

> 如需修改 token，同时修改 NapCat 配置和 NoneBot 的 `.env` 文件中的 `ONEBOT_ACCESS_TOKEN`。

## 3. 数据库

游戏使用 SQLite，数据库文件默认生成在项目根目录：

```
python3 database/init_db.py
```

测试或临时环境可以通过 `PSL_DB_PATH` 指定数据库文件：

```
PSL_DB_PATH=/tmp/psl-test.db python3 bot/bot.py
```

## 4. 运行 Bot

启动 NapCatQQ：
```
napcat start
```

启动机器人脚本：
```
python3 bot/bot.py
```

## 5. 运行 Web

Web 端是独立 FastAPI 服务，默认监听 `8088`，和 Bot 共享项目根目录的 `psl.db`。

首次运行先安装前端依赖并构建静态资源：

```
cd web
npm install --cache /tmp/npm-cache
npm run build
cd ..
```

启动 Web 服务：

```
python3 -m server
```

浏览器访问：

```
http://127.0.0.1:8088
```

生产环境建议同时启动两个进程：

```
python3 bot/bot.py
python3 -m server
```

可选环境变量：

```
PSL_DB_PATH=/path/to/psl.db
PSL_WEB_PORT=8088
PSL_JWT_SECRET=replace-with-a-long-random-secret
PSL_RUST_PROFILE=debug
```

比赛默认使用 release 版 Rust 引擎。仅本地调试 Rust 代码时需要显式设置
`PSL_RUST_PROFILE=debug`；`start.sh` 会自动构建并使用 release 版本。

需要优化单场延迟时，可以用一个或多个真实的 `match_v2_run` 请求训练 PGO 构建：

```
scripts/build_engine_v2_pgo.sh /path/to/match-request.json
```

脚本会将 PGO 引擎写入正常的 `rust/engine_v2_core/target/release/engine`。
`start.sh`、`config.sh` 和 Python bridge 会复用与当前 Rust 源码 digest 匹配的 PGO
引擎；Rust 源码或 Cargo manifest 变化后会自动回落到普通 release 构建。
如只在当前机器部署，可显式传 `--native`，默认构建保持跨同架构机器可移植。
`start.sh` 默认会在 PGO 缺失或过期时，从 `PSL_DB_PATH`（默认 `psl.db`）选择
完整真实阵容并自动重训；有效 PGO 会直接复用。单核小内存服务器默认使用 1 个
Cargo build job。临时跳过自动 PGO 可设置 `PSL_ENGINE_AUTO_PGO=0`，需要调整
编译并发可设置 `PSL_ENGINE_BUILD_JOBS`。首次启动或 Rust 源码变化后的启动会执行
两次 release 编译和一场训练比赛，耗时明显更长；构建完成后后续启动直接复用。

## 6. 测试

测试绕过 QQ Bot，直接覆盖模型层和核心游戏功能流：

```
python3 -m pytest tests -q
```

批量模拟比赛用于检查引擎数值平衡：

```
python3 scripts/simulate_matches.py --matches 100 --seed 1 --home-star 3 --away-star 3
```
