#!/bin/bash

#数据库配置
HOSTNAME=localhost
PORT=3306
USERNAME=navi
PASSWORD=woshinaiwei
DBNAME=bot

# QQ号配置
QQ_ACCOUNT=1427259739

echo "====== Required OS: Ubuntu 20.04+"

echo "====== 安装python"
sudo apt update
sudo apt install python3.8
sudo apt install python3.8-dev
sudo apt install python3-pip

echo "====== 安装python依赖库"
pip3 install nonebot2
pip3 install pymysql
pip3 install cryptography
pip3 install requests
pip3 install pillow
pip3 install nonebot-adapter-onebot

echo "======安装MySQL"
sudo apt install mysql-server
sudo service mysql start

echo "======导入数据库"
echo "CREATE DATABASE if not exists ${DBNAME} character set utf8" | mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD}
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/players.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/users.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/cards.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/transfer.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/challenge_times.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/offline.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/global.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/items.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/league.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/team.sql
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/schedule.sql

echo "====== 安装 NapCatQQ"
curl -o napcat.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.sh && bash napcat.sh

echo "====== 完成！"
echo "请通过 NapCat WebUI 配置反向 WebSocket 地址为 ws://127.0.0.1:8080/onebot/v11/ws/"
echo "然后运行 python3 bot/bot.py 启动机器人"
