
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
S3_BASEURL = os.environ.get('S3_BASEURL')

REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER')
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_DOMAIN = EMAIL_SENDER.split('@')[-1]

SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = int(os.environ.get('SMTP_PORT') or '587')
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')

SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY')
MAILGUN_URL = os.environ.get('MAILGUN_URL', 'api.eu.mailgun.net')

EMAILS_ENABLED = bool(EMAIL_PROVIDER and EMAIL_SENDER)

WEB_HOST = os.environ.get('WEB_HOST')
WEB_PORT = int(os.environ.get('WEB_PORT', 80))

DISABLE_CLIENT_VERIFICATION = eval(os.environ.get('DISABLE_CLIENT_VERIFICATION', 'True').capitalize())
APPROVED_MAP_REWARDS = eval(os.environ.get('APPROVED_MAP_REWARDS', 'False').capitalize())
FROZEN_RANK_UPDATES = eval(os.environ.get('FROZEN_RANK_UPDATES', 'False').capitalize())
ALLOW_RELAX = eval(os.environ.get('ALLOW_RELAX', 'True').capitalize())
S3_ENABLED = eval(os.environ.get('ENABLE_S3', 'True').capitalize())
DEBUG = eval(os.environ.get('DEBUG', 'False').capitalize())

SCORE_SUBMISSION_KEY = os.environ.get('SCORE_SUBMISSION_KEY', 'h89f2-890h2h89b34g-h80g134n90133')
SCORE_RESPONSE_LIMIT = int(os.environ.get('SCORE_RESPONSE_LIMIT', 50))

SEASONAL_BACKGROUNDS = os.environ.get('SEASONAL_BACKGROUNDS', '').split(',')
MENUICON_IMAGE = os.environ.get('MENUICON_IMAGE')
MENUICON_URL = os.environ.get('MENUICON_URL')

OFFICER_WEBHOOK_URL = os.environ.get('OFFICER_WEBHOOK_URL')
EVENT_WEBHOOK_URL = os.environ.get('EVENT_WEBHOOK_URL')
OSZ2_SERVICE_URL = os.environ.get('OSZ2_SERVICE_URL')

BANCHO_IP = os.environ.get('PUBLIC_BANCHO_IP', None)
DOMAIN_NAME = os.environ.get('DOMAIN_NAME')
DATA_PATH = os.path.abspath('.data')

VERSION = '1.7.9'
