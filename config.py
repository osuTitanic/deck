
import dotenv
import os

dotenv.load_dotenv(override=False)

POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
POSTGRES_USER = os.environ.get('POSTGRES_USER')
POSTGRES_HOST = os.environ.get('POSTGRES_HOST')

S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BASEURL    = os.environ.get('S3_BASEURL')

REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

WEB_HOST = os.environ.get('WEB_HOST')
WEB_PORT = int(os.environ.get('WEB_PORT', 80))

USING_AKATSUKI_PP_SYSTEM = eval(os.environ.get('USE_AKATSUKI_PP_SYSTEM', 'True').capitalize())
APPROVED_MAP_REWARDS = eval(os.environ.get('APPROVED_MAP_REWARDS', 'False').capitalize())
FREE_SUPPORTER = eval(os.environ.get('FREE_SUPPORTER', 'True').capitalize())
ALLOW_RELAX = eval(os.environ.get('ALLOW_RELAX', 'True').capitalize())
S3_ENABLED = eval(os.environ.get('ENABLE_S3', 'True').capitalize())

SCORE_RESPONSE_LIMIT = int(os.environ.get('SCORE_RESPONSE_LIMIT', 50))
SCORE_SUBMISSION_KEY = os.environ.get('SCORE_SUBMISSION_KEY')

MENUICON_IMAGE = os.environ.get('MENUICON_IMAGE')
MENUICON_URL = os.environ.get('MENUICON_URL')

BANCHO_IP = os.environ.get('PUBLIC_BANCHO_IP', None)
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')
DATA_PATH = os.path.abspath('.data')

CIRCLEGUARD_ENABLED = eval(os.environ.get('ENABLE_CIRCLEGUARD_ANTICHEAT', 'True').capitalize())

MIN_SNAP_DISTANCE = int(os.environ.get('MIN_SNAP_DISTANCE', 8))
MAX_SNAP_ANGLE = int(os.environ.get('MAX_SNAP_ANGLE', 10))
MAX_FRAMETIME = int(os.environ.get('MAX_FRAMETIME', 13))
MAX_UR = int(os.environ.get('MAX_UR', 50))

VERSION = 'dev'
