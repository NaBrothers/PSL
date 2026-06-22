# QQ群足球小游戏

## 1. 部署
修改 `./config.sh` 中的数据库配置后运行脚本
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

## 3. 配置机器人

修改 `bot/src/plugins/psl/config.py` 中的数据库配置

## 4. 运行

启动 NapCatQQ：
```
napcat start
```

启动机器人脚本：
```
python3 bot/bot.py
```
