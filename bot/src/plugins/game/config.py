from pydantic import BaseSettings

HOSTNAME="127.0.0.1"
USERNAME="navi"
PASSWORD="woshinaiwei"
DBNAME="bot"

class Config(BaseSettings):
    # Your Config Here

    class Config:
        extra = "ignore"
  