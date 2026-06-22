# QQ群足球小游戏

## 1. 部署
运行脚本安装 Python 依赖、初始化 SQLite 数据库并安装 NapCatQQ：
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

## 4. 运行

启动 NapCatQQ：
```
napcat start
```

启动机器人脚本：
```
python3 bot/bot.py
```

## 5. 测试

测试绕过 QQ Bot，直接覆盖模型层和核心游戏功能流：

```
python3 -m pytest tests -q
```
