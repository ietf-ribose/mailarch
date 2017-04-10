# settings/test.py
from .base import *

DATA_ROOT = '/tmp/mailarch/data'

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend',)

# Don't try and create test IETF database
del DATABASES['ietf']

# HAYSTACK SETTINGS
HAYSTACK_SIGNAL_PROCESSOR = 'haystack.signals.RealtimeSignalProcessor'
HAYSTACK_XAPIAN_PATH = os.path.join(DATA_ROOT,'xapian.stub')
HAYSTACK_CONNECTIONS['default']['PATH'] = HAYSTACK_XAPIAN_PATH

# ARCHIVE SETTINGS
ARCHIVE_DIR = os.path.join(DATA_ROOT,'archive')
LOG_FILE = os.path.join(BASE_DIR,'tests/tmp','mlarchive.log')
IMPORT_LOG_FILE = os.path.join(BASE_DIR,'tests/tmp','archive-mail.log')

SERVER_MODE = 'development'

LOGGING['handlers']['watched_file']['filename'] = LOG_FILE
LOGGING['handlers']['archive-mail_file_handler']['filename'] = IMPORT_LOG_FILE

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache'
    }
}

# IMAP Interface
EXPORT_DIR = os.path.join(DATA_ROOT,'export')

# Inspectors
#INSPECTORS = {
#    'ListIdSpamInspector': {'includes':['mpls']}
#}
