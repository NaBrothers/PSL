#!/bin/bash

#数据库配置
HOSTNAME=localhost
PORT=3306
USERNAME=navi
PASSWORD=woshinaiwei
DBNAME=bot


echo "====== Required OS: Ubuntu 16.04+"

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
pip3 install nonebot-adapter-cqhttp

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
echo "======安装golang"
sudo apt install golang

echo "======安装cqhttp"
git submodule update --init --recursive
cd cqhttp
git checkout 99a68b144b4802d10926bdebf998f3aac8a6f1c9
go env -w GOPROXY=https://goproxy.cn,direct
go build -ldflags "-s -w -extldflags '-static'"
cp ../config.yml .
mkdir data
mkdir data/images

cd ..
cp -r assets/avatars/ cqhttp/data/images/

echo "====== 安装nonebot"
cd nonebot2
git checkout 95415659cee9c8db31f457c42dedf6786ef05923 
pip3 install .
cd ..

echo "====== 完成！请手动配置cqhttp/config.yml后运行go-cqhttp"
