
import dotenv
import os

dotenv.load_dotenv(override=False)

POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
POSTGRES_USER = os.environ.get('POSTGRES_USER')
POSTGRES_HOST = os.environ.get('POSTGRES_HOST')

POSTGRES_POOLSIZE = int(os.environ.get('POSTGRES_POOLSIZE', 10))
POSTGRES_POOLSIZE_OVERFLOW = int(os.environ.get('POSTGRES_POOLSIZE_OVERFLOW', 30))

S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BASEURL    = os.environ.get('S3_BASEURL')

REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

WEB_HOST = os.environ.get('WEB_HOST')
WEB_PORT = int(os.environ.get('WEB_PORT', 80))

APPROVED_MAP_REWARDS = eval(os.environ.get('APPROVED_MAP_REWARDS', 'False').capitalize())
FREE_SUPPORTER = eval(os.environ.get('FREE_SUPPORTER', 'True').capitalize())
ALLOW_RELAX = eval(os.environ.get('ALLOW_RELAX', 'True').capitalize())
S3_ENABLED = eval(os.environ.get('ENABLE_S3', 'True').capitalize())
DEBUG = eval(os.environ.get('ENABLE_S3', 'False').capitalize())

SCORE_RESPONSE_LIMIT = int(os.environ.get('SCORE_RESPONSE_LIMIT', 50))
SCORE_SUBMISSION_KEY = os.environ.get('SCORE_SUBMISSION_KEY')

MENUICON_IMAGE = os.environ.get('MENUICON_IMAGE')
MENUICON_URL = os.environ.get('MENUICON_URL')

BANCHO_IP = os.environ.get('PUBLIC_BANCHO_IP', None)
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')
DATA_PATH = os.path.abspath('.data')

VERSION = 'dev'
