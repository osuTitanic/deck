
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

SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
SENDGRID_EMAIL = os.environ.get('SENDGRID_EMAIL')

MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY')
MAILGUN_EMAIL = os.environ.get('MAILGUN_EMAIL', '')
MAILGUN_URL = os.environ.get('MAILGUN_URL', 'api.eu.mailgun.net')
MAILGUN_DOMAIN = MAILGUN_EMAIL.split('@')[-1]

EMAILS_ENABLED = MAILGUN_API_KEY is not None or SENDGRID_API_KEY is not None
EMAIL = MAILGUN_EMAIL or SENDGRID_EMAIL

WEB_HOST = os.environ.get('WEB_HOST')
WEB_PORT = int(os.environ.get('WEB_PORT', 80))

DISABLE_CLIENT_VERIFICATION = eval(os.environ.get('DISABLE_CLIENT_VERIFICATION', 'True').capitalize())
APPROVED_MAP_REWARDS = eval(os.environ.get('APPROVED_MAP_REWARDS', 'False').capitalize())
ALLOW_RELAX = eval(os.environ.get('ALLOW_RELAX', 'True').capitalize())
S3_ENABLED = eval(os.environ.get('ENABLE_S3', 'True').capitalize())
DEBUG = eval(os.environ.get('DEBUG', 'False').capitalize())

SCORE_RESPONSE_LIMIT = int(os.environ.get('SCORE_RESPONSE_LIMIT', 50))
SCORE_SUBMISSION_KEY = os.environ.get('SCORE_SUBMISSION_KEY')

MENUICON_IMAGE = os.environ.get('MENUICON_IMAGE')
MENUICON_URL = os.environ.get('MENUICON_URL')

OFFICER_WEBHOOK_URL = os.environ.get('OFFICER_WEBHOOK_URL')

BANCHO_IP = os.environ.get('PUBLIC_BANCHO_IP', None)
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')
DATA_PATH = os.path.abspath('.data')

VERSION = 'dev'
