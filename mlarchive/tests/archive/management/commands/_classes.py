from mlarchive.archive.management.commands._classes import *
from factories import *
from pprint import pprint

import datetime
import email
import glob
import mailbox
import pytest
import pytz

@pytest.mark.django_db(transaction=True)
def test_archive_message(client):
    data = '''From: Ryan Cross <rcross@amsl.com>
To: Ryan Cross <rcross@amsl.com>
Date: Thu, 7 Nov 2013 17:54:55 +0000
Message-ID: <0000000002@amsl.com>
Content-Type: text/plain; charset="us-ascii"
Subject: This is a test

Hello,

This is a test email.  database
'''
    status = archive_message(data,'test',private=False)
    assert status == 0
    # ensure message in db
    assert Message.objects.all().count() == 1
    # ensure message in index
    url = '%s/?q=database' % reverse('archive_search')
    response = client.get(url)
    results = response.context['results']
    assert len(results) == 1

@pytest.mark.django_db(transaction=True)
def test_archive_message_fail(client):
    data = '''Hello,

This is a test email.  With no headers
'''
    # remove any existing failed messages
    publist = EmailListFactory.create(name='public')
    failed_dir = publist.get_failed_dir()
    if os.path.exists(failed_dir):              # ensure failed directory empty
        assert not os.listdir(failed_dir)
    status = archive_message(data,'public',private=False)
    assert status == 1
    assert Message.objects.all().count() == 0
    filename = os.path.join(failed_dir,
            datetime.datetime.today().strftime('%Y-%m-%d') + '.0000')
    assert os.path.exists(filename)
    os.remove(filename)                         # cleanup

def test_clean_spaces():
    s = 'this     is   a    string   with extra    spaces'
    assert clean_spaces(s) == 'this is a string with extra spaces'

def test_convert_date():
    data = ['Fri Feb 21 11:09:00 2014',
            'Fri, 21 Feb 2014 11:09:00 PST',
            'Fri Feb 21 11:09:00 2014 PST']
    date = datetime.datetime(2014,02,21,19,9)  # utc date
    for item in data:
        result = convert_date(item)
        assert result == date
        assert not is_aware(result)

    assert convert_date('bogus date string') == None

def decode_rfc2047_header():
    data = [('=?utf-8?b?562U5aSNOiAgQU5DUCBGcmFtZXdvcmsgdXBkYXRl?=',
            u'\u7b54\u590d:  ANCP Framework update'),
            ('To: =?iso-8859-1?Q?Ivan_Skytte_J=F8rgensen?= <isj@i1.dk>',
            u'To: Ivan Skytte J\xf8rgensen <isj@i1.dk>'),
            ('nothing to convert',u'nothing_to_convert')]
    for item in data:
        assert decode_rfc2047_header(item[0]) == item[1]

def test_get_base_subject():
    data = [('[ANCP] =?iso-8859-1?q?R=FCckruf=3A_Welcome_to_the_=22ANCP=22_mail?=\n\t=?iso-8859-1?q?ing_list?=',
             'R\xc3\xbcckruf: Welcome to the "ANCP" mailing list'),
            ('Re: [IAB] Presentation at IAB Tech Chat (fwd)','Presentation at IAB Tech Chat'),
            ('Re: [82companions] [Bulk]  Afternoon North Coast tour','Afternoon North Coast tour'),
            ('''[cdni-footprint] Fwd: Re: [CDNi] Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"''','''Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"'''),
            ('[dccp] [Fwd: Re: [Tsvwg] Fwd: WGLC for draft-ietf-dccp-quickstart-03.txt]','WGLC for draft-ietf-dccp-quickstart-03.txt'),
            ('[ANCP] Fw: note the boilerplate change','note the boilerplate change'),
            ('Re: [ANCP] RE: draft-ieft-ancp-framework-00.txt','draft-ieft-ancp-framework-00.txt')]

    message = email.message_from_string('From: rcross@amsl.com')
    mw = MessageWrapper(message, 'test')
    for item in data:
        normal = mw.normalize(item[0])
        base = get_base_subject(normal)
        assert base == item[1]

def test_get_date_part():
    data = [('iesg-bounces@ietf.org Fri Dec 01 02:58:22 2006',
            'Fri Dec 01 02:58:22 2006'),                                # normal
            ('denis.pinkas at bull.net  Fri Feb  1 03:12:37 2008',
            'Fri Feb  1 03:12:37 2008'),                                # obfiscated
            ('fluffy@cisco.com Thu, 15 Jul 2004 17:15:16 -0700 (PDT)',
            'Thu, 15 Jul 2004 17:15:16 -0700'),                         # double tzinfo
            ('Kim.Fullbrook@O2.COM Tue, 01 Feb 2005 06:01:13 -0500',
            'Tue, 01 Feb 2005 06:01:13 -0500'),                         # numeric tzinfo
            ('eburger@brooktrout.com Thu, 3 Feb 2005 19:55:03 GMT',
            'Thu, 3 Feb 2005 19:55:03 GMT'),                            # char tzinfo
            ('scott.mcglashan@hp.com Wed, 6 Jul 2005 12:24:15 +0100 (BST)',
            'Wed, 6 Jul 2005 12:24:15 +0100'),                          # odd tzinfo
            ('scoya  Fri Sep  1 02:28:55 2000',
            'Fri Sep  1 02:28:55 2000')]                                # simple from
    for item in data:
        assert get_date_part(item[0]) == item[1]

def test_get_envelope_date():
    data = '''From rcross@amsl.com Fri Feb 21 11:09:00 2014
From: rcross@amsl.com
To: rcross@amsl.com
Subject: Test

Hello.
'''
    message = email.message_from_string(data)
    assert get_envelope_date(message) == datetime.datetime(2014,2,21,19,9)

def test_get_from():
    data = '''From rcross@amsl.com Fri Feb 21 11:09:00 2014
From: rcross@amsl.com
To: rcross@amsl.com
Subject: Test

Hello.
'''
    # test email.message.Message
    message = email.message_from_string(data)
    assert get_from(message) == 'From rcross@amsl.com Fri Feb 21 11:09:00 2014'

    # test mailbox.mboxMessage
    path = os.path.join(settings.BASE_DIR,'tests','data','ancp-2013-08.mail')
    mb = mailbox.mbox(path)
    assert get_from(mb[0]) == 'internet-drafts@ietf.org  Wed Aug 21 16:20:36 2013'

def test_get_header_date():
    data = [('Date: Wed, 08 Apr 92 13:31:28 -0400',
            datetime.datetime(1992,4,8,17,31,28)),      # 2-digit year, numeric tz
            ('Date: Thu, 28 May 92 9:18:58 PDT',
            datetime.datetime(1992,5,28,16,18,58)),     # 2-digit year, char tz
            ('Date: Thursday, 28 May 1992 12:06:31 EDT',
            datetime.datetime(1992,5,28,16,06,31)),     # full day name, char tz
            ('Date: Fri, 29 May 1992 18:02:45 -0400 (EDT)',
            datetime.datetime(1992,5,29,22,02,45)),     # numeric & char tz
            ('Date: 27 Jan 2002 21:46:45 +0000',
            datetime.datetime(2002,1,27,21,46,45)),     # no day of week
            ('Sent: Thu, 28 May 92 9:18:58 PDT',
            datetime.datetime(1992,5,28,16,18,58))]     # Sent header
    for item in data:
        message = email.message_from_string(item[0])
        date = get_header_date(message)
        # convert to naive if we get a timezone aware object
        date = date.astimezone(pytz.utc).replace(tzinfo=None)
        assert date == item[1]

def test_get_mb():
    files = glob.glob(os.path.join(settings.BASE_DIR,'tests','data','mailbox_*'))
    for file in files:
        mb = get_mb(file)
        assert len(mb) > 0

def test_get_mime_extension():
    data = [('image/jpeg','jpg'),('text/html','html'),('hologram/3d','bin')]
    for item in data:
        ext, desc = get_mime_extension(item[0])
        assert ext == item[1]

def test_get_received_date():
    data = '''Received: from mail.ietf.org ([64.170.98.30]) by localhost \
(ietfa.amsl.com [127.0.0.1]) (amavisd-new, port 10024) with ESMTP id oE4MnXBb8IJ9 \
for <ancp@ietfa.amsl.com>; Tue, 29 Jan 2013 00:08:57 -0800 (PST)'''
    message = email.message_from_string(data)
    date = get_received_date(message)
    # convert to naive if we get a timezone aware object
    date = date.astimezone(pytz.utc).replace(tzinfo=None)
    assert date == datetime.datetime(2013,1,29,8,8,57)

def test_is_aware():
    assert is_aware(datetime.datetime(2013,1,1)) == False
    assert is_aware(datetime.datetime(2013,1,1,12,0,0,0,pytz.UTC)) == True

def test_parsedate_to_datetime():
    data = [('Tue Jan  1 2014 12:30:00 PST',
            datetime.datetime(2014,1,1,12,30,0,0,pytz.timezone('US/Pacific')))]
    for item in data:
        assert parsedate_to_datetime(item[0]) == item[1]

#def test_save_failed_msg

#def test_BetterMbox

#def test_Loader()

#def test_MessageWrapper
    # various exceptions raised
