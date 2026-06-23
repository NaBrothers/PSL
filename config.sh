#!/bin/bash

echo "====== Required OS: Ubuntu 20.04+ / macOS"

echo "====== 安装 Python 依赖库"
pip3 install nonebot2[fastapi] nonebot-adapter-onebot pydantic-settings requests pillow pytest

echo "====== 初始化 SQLite 数据库"
python3 database/init_db.py

echo "====== 安装 NapCatQQ"
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh && bash napcat.sh

echo "====== 完成！"
echo "请通过 NapCat WebUI 配置反向 WebSocket 地址为 ws://127.0.0.1:8080/onebot/v11/ws/"
echo "然后运行 python3 bot/bot.py 启动机器人"
