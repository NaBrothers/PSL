from pydantic import BaseSettings

# 数据库
HOSTNAME="127.0.0.1"
USERNAME="navi"
PASSWORD="woshinaiwei"
DBNAME="bot"

# 项目文件夹
PROJECT_DIR="/home/admin/PSL"

# 图片模式（更好的显示效果，但响应更慢）
# 文字模式被风控时可以尝试
PICTURE_MODE=True

# 联赛球队数
LEAGUE_COUNT = 7

# 联赛循环数
LEAGUE_REPEAT = 2

class Config(BaseSettings):
    # Your Config Here

    class Config:
        extra = "ignore"

  