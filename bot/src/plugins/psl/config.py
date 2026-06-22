from pydantic_settings import BaseSettings
import os

# 项目文件夹
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# 图片模式（更好的显示效果，但响应更慢）
# 文字模式被风控时可以尝试
PICTURE_MODE = True

# 联赛默认球队数（可通过联赛 重置 [数量] [循环]修改）
LEAGUE_COUNT = 7

# 联赛默认循环数（可通过联赛 重置 [数量] [循环]修改）
LEAGUE_REPEAT = 2

class Config(BaseSettings):
    class Config:
        extra = "ignore"
