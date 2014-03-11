#!/usr/bin/python
"""
Generic scan script.  Define a scan as a function.  Specifiy the function as the
first command line argument.

usage:

scan_all.py [func name] [optional arguments][

"""
# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings'
# -------------------------------------------------------------------------------------

from mlarchive.archive.models import *
from mlarchive.bin.scan_utils import *
from mlarchive.archive.management.commands import _classes
from tzparse import tzparse
from pprint import pprint
from pytz import timezone

import argparse
import datetime
import glob
import mailbox
import re
import sys

date_pattern = re.compile(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
dupetz_pattern = re.compile(r'[\-\+]\d{4} \([A-Z]+\)$')

date_formats = ["%a %b %d %H:%M:%S %Y",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%a %b %d %H:%M:%S %Y %Z"]

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def get_date_part(str):
    """Get the date portion of the envelope header.  Based on the observation
    that all date parts start with abbreviated weekday
    """
    match = date_pattern.search(str)
    if match:
        date = match.group()

        # a very few dates have redundant timezone designations on the end
        # which tzparse can't handle.  If this is the case strip it off
        # ie. Wed, 6 Jul 2005 12:24:15 +0100 (BST)
        if dupetz_pattern.search(date):
            date = re.sub(r'\s\([A-Z]+\)$','',date)
        return date
    else:
        return None

def convert_date(date):
    """Try different patterns to convert string to naive UTC datetime object"""
    for format in date_formats:
        try:
            result = tzparse(date.rstrip(),format)
            if result:
                # convert to UTC and make naive
                utc_tz = timezone('utc')
                time = utc_tz.normalize(result.astimezone(utc_tz))
                time = time.replace(tzinfo=None)                # make naive
                return time
        except ValueError:
            pass
# ---------------------------------------------------------
# Scan Functions
# ---------------------------------------------------------

def bodies():
    """Call get_body_html() and get_body() for every message in db. Use logging in
    generator_handler methods to gather stats.
    """
    query = Message.objects.filter(pk__gte=457000)
    total = Message.objects.count()
    for msg in query:
        try:
            x = msg.get_body_html()
            y = msg.get_body()
        except (UnicodeDecodeError, LookupError, TypeError) as e:
            print '{0} [{1}]'.format(e, msg.pk)
        if msg.pk % 1000 == 0:
            print 'processed {0} of {1}'.format(msg.pk,total)

def count(listname):
    """Count number of messages in legacy archive for listname"""
    total = 0
    years = {}
    for mb in get_mboxs(listname):
        parts = mb._file.name.split('/')
        num = len(mb)
        year = parts[-1][:4]
        years[year] = years.get(year,0) + num
        print "%s/%s: %d" % (parts[-2],parts[-1],num)
        total += num
    print "Total: %d" % total
    pprint(years)

def envelope_date():
    """Quickly test envelope date parsing on every standard mbox file in archive"""
    #for path in ['/a/www/ietf-mail-archive/text/lemonade/2002-09.mail']:
    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                date = get_date_part(line.rstrip())
                if date == None:
                    print path,line
                if not convert_date(date.rstrip()):
                    print path,date

def envelope_regex():
    """Quickly test envelope regex matching on every standard mbox file in archive"""
    #for path in ['/a/www/ietf-mail-archive/text/lemonade/2002-09.mail']:
    # pattern = re.compile(r'From (.*@.* |MAILER-DAEMON ).{24}')
    pattern = re.compile(r'From .* (Sun|Mon|Tue|Wed|Thu|Fri|Sat)( |,)')

    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if line.startswith('From '):
                if not pattern.match(line):
                    print path,line

def html_only():
    """Scan all mboxs and report messages that have only one MIME part that is text/html"""
    elist = ''
    for path in all_mboxs():
        name = os.path.basename(os.path.dirname(path))
        if elist != name:
            elist = name
            print "Scanning %s" % name
        if name in ('django-project','iab','ietf'):
            continue
        mb = _classes.get_mb(path)
        for msg in mb:
            if msg.is_multipart() == False:
                if msg.get_content_type() == 'text/html':
                    print msg['message-id']

def mailbox_types():
    """Scan all mailbox files and print example of each unique envelope form other
    than typical mbox or mmdf
    """
    matches = dict.fromkeys(_classes.SEPARATOR_PATTERNS)
    for path in all_mboxs():
        with open(path) as f:
            line = f.readline()
            while not line or line == '\n':
                line = f.readline()
            if not (line.startswith('From ') or line.startswith('\x01\x01\x01\x01')):
                for pattern in _classes.SEPARATOR_PATTERNS:
                    if pattern.match(line):
                        if not matches[pattern]:
                            matches[pattern] = path
                            print "%s: %s" % (pattern.pattern, path)
                        break

def missing_files():
    """Scan messages in date range and report if any are missing the archive file"""
    total = 0
    start = datetime.datetime(2014,01,20)
    end = datetime.datetime(2014,01,23)
    messages = Message.objects.filter(date__gte=start,date__lte=end)
    for message in messages:
        if not os.path.exists(message.get_file_path()):
            print 'missing: %s:%s:%s' % (message.email_list, message.pk, message.date)
            total += 1
            #message.delete()
    print '%d of %d missing.' % (total, messages.count())

def subjects(listname):
    """Return subject line of all messages for listname"""
    for msg in process([listname]):
        print "%s: %s" % (msg.get('date'),msg.get('subject'))

# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Run an archive scan.')
    parser.add_argument('function')
    parser.add_argument('extras', nargs='*')
    args = vars(parser.parse_args())
    if args['function'] in globals():
        func = globals()[args['function']]
        func(*args['extras'])
    else:
        raise argparse.ArgumentTypeError('no scan function: %s' % args['function'])

if __name__ == "__main__":
    main()
