
from logging import FileHandler, Formatter, StreamHandler
from datetime import datetime

import os

os.makedirs('./logs', exist_ok=True)

Console = StreamHandler()

File = FileHandler(f'./logs/{datetime.now().strftime("%Y-%m-%d")}.log', mode='a')
File.setFormatter(
    Formatter(
        '[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s'
    )
)
