#!/bin/bash

echo "====== Required OS: Ubuntu 20.04+ / macOS"

echo "====== 安装 Python 依赖库"
pip3 install nonebot2[fastapi] nonebot-adapter-onebot pydantic-settings requests pillow pytest

echo "====== 检查 Rust 工具链"
if ! command -v cargo >/dev/null 2>&1; then
  echo "未检测到 cargo，正在安装 Rust stable 工具链"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "====== 编译 Rust 比赛引擎"
scripts/build_engine_v2_release.sh

echo "====== 初始化 SQLite 数据库"
python3 database/init_db.py

echo "====== 安装 NapCatQQ"
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh && bash napcat.sh

echo "====== 完成！"
echo "请通过 NapCat WebUI 配置反向 WebSocket 地址为 ws://127.0.0.1:8080/onebot/v11/ws/"
echo "然后运行 python3 bot/bot.py 启动机器人"
