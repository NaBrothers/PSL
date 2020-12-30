from pydantic import BaseSettings

# 数据库
HOSTNAME="127.0.0.1"
USERNAME="navi"
PASSWORD="woshinaiwei"
DBNAME="bot"

PROJECT_DIR="/home/admin/PSL"

class Config(BaseSettings):
    # Your Config Here

    class Config:
        extra = "ignore"

  