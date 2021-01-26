# QQ群足球小游戏

## 1. 部署
修改 `./config.sh` 中的数据库配置后运行脚本
```
bash ./config.sh
```

## 2. 配置
修改 `cqhttp/config.hjson` 中机器人的QQ号与密码

修改 `bot/src/plugins/game/config.py` 中的数据库配置

## 3. 运行
运行go-cqhttp，第一次登陆需要验证设备
```
./cqhttp/go-cqhttp
```
运行机器人脚本
```
python3 bot/bot.py
```
