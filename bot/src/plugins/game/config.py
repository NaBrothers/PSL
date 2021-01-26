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

# 联赛默认球队数（可通过联赛 重置 [数量] [循环]修改）
LEAGUE_COUNT = 10

# 联赛默认循环数（可通过联赛 重置 [数量] [循环]修改）
LEAGUE_REPEAT = 2

class Config(BaseSettings):
    # Your Config Here

    class Config:
        extra = "ignore"

  