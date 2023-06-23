
from logging import FileHandler, Formatter, StreamHandler
from datetime import datetime

import config
import os

os.makedirs(f'{config.DATA_PATH}/logs', exist_ok=True)

Console = StreamHandler()

File = FileHandler(f'{config.DATA_PATH}/logs/{datetime.now().strftime("%Y-%m-%d")}.log', mode='a')
File.setFormatter(
    Formatter(
        '[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s'
    )
)
