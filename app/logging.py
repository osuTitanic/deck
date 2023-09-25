
from discord_webhook_logging import DiscordWebhookHandler
from logging import FileHandler, Formatter, StreamHandler
from datetime import datetime

import logging
import config
import os

os.makedirs('./logs', exist_ok=True)

Console = StreamHandler()

Discord = DiscordWebhookHandler(config.WEBHOOK_URL, auto_flush=True)
Discord.setLevel(logging.ERROR)

File = FileHandler(f'./logs/{datetime.now().strftime("%Y-%m-%d")}.log', mode='a')
File.setFormatter(
    Formatter(
        '[%(asctime)s] - <%(name)s> %(levelname)s: %(message)s'
    )
)
