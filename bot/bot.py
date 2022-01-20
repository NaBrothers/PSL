#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotAdapter

# Custom your logger
# 
# from nonebot.log import logger, default_format
# logger.add("error.log",
#            rotation="00:00",
#            d:qiagnose=False,
#            level="ERROR",
#            format=default_format)

# You can pass some keyword args config to init function
nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotAdapter)

nonebot.load_plugin("src.plugins.psl")

# Modify some config / config depends on loaded configs
# 
# config = driver.config
# do something...
SHORT_MESSAGE_MAX_LENGTH = 2000

if __name__ == "__main__":
    nonebot.run()
