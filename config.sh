#!/bin/bash

#数据库配置
HOSTNAME="127.0.0.1"
PORT="3306"
USERNAME="root"
PASSWORD="woshinaiwei"
DBNAME="bot"


echo "====== Required OS: Ubuntu 16.04+"

echo "====== 安装python"
sudo apt update
sudo apt install python3.8
sudo apt install python3.8-dev
sudo apt install python3-pip

echo "====== 安装python依赖库"
python3 -m pip install nonebot2
python3 -m pip install pymysql

echo "======安装MySQL"
sudo apt install mysql-server
sudo service mysql start

echo "======导入数据库"
echo "CREATE DATABASE if not exists ${DBNAME} character set utf8" | mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD}
mysql -h${HOSTNAME} -P${PORT} -u${USERNAME} -p${PASSWORD} ${DBNAME} <./database/players.sql

echo "======安装golang"
sudo apt install golang

echo "======安装cqhttp"
git submodule update --init --recursive
cd cqhttp
go env -w GOPROXY=https://goproxy.cn,direct
go build -ldflags "-s -w -extldflags '-static'"
cp ../config.hjson .

echo "====== 完成！请手动配置cqhttp/config.hjson后运行go-cqhttp"
