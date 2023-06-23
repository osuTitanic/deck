
import config
import app
import os

def download(path: str, url: str):
    if not os.path.isfile(path):
        response = app.session.requests.get(url)
        
        if not response.ok:
            app.session.logger.error(f'Failed to download file: {url}')
            return

        with open(path, 'wb') as f:
            f.write(response.content)

def setup():
    os.makedirs(config.DATA_PATH, exist_ok=True)
    os.makedirs(f'{config.DATA_PATH}/logs', exist_ok=True)

    if not config.S3_ENABLED:
        os.makedirs(f'{config.DATA_PATH}/screenshots')
        os.makedirs(f'{config.DATA_PATH}/replays')
        os.makedirs(f'{config.DATA_PATH}/avatars')
        os.makedirs(f'{config.DATA_PATH}/images')

        if not os.listdir(f'{config.DATA_PATH}/avatars'):
            app.session.logger.info('Downloading avatars...')

            download(f'{config.DATA_PATH}/avatars/unknown', 'https://github.com/lekuru-static/download/blob/main/unknown?raw=true')
            download(f'{config.DATA_PATH}/avatars/1', 'https://github.com/lekuru-static/download/blob/main/1?raw=true')
