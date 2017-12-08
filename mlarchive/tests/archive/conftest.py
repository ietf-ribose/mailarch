from django.core.management import call_command
from factories import *
from mlarchive.archive.management.commands._classes import get_base_subject
from StringIO import StringIO

import datetime
import os
import pytest


def load_db():
    pubone = EmailListFactory.create(name='pubone')
    pubtwo = EmailListFactory.create(name='pubtwo')
    pubthree = EmailListFactory.create(name='pubthree')
    private = EmailListFactory.create(name='private', private=True)
    athread = ThreadFactory.create(date=datetime.datetime(2013, 1, 1))
    bthread = ThreadFactory.create(date=datetime.datetime(2013, 2, 1))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          base_subject=get_base_subject('Another message'),
                          date=datetime.datetime(2013, 1, 1))
    MessageFactory.create(email_list=pubone,
                          thread=bthread,
                          subject='BBQ Invitation',
                          base_subject=get_base_subject('BBQ Invitation'),
                          date=datetime.datetime(2013, 2, 1),
                          to='to@amsl.com')
    MessageFactory.create(email_list=pubone,
                          thread=bthread,
                          base_subject=get_base_subject('Zero conf stuff'),
                          date=datetime.datetime(2013, 3, 1))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          frm='larry@amsl.com',
                          base_subject=get_base_subject('[RE] BBQ Invitation things'),
                          date=datetime.datetime(2014, 1, 1),
                          spam_score=1)
    MessageFactory.create(email_list=pubtwo)
    MessageFactory.create(email_list=pubtwo)
    date = datetime.datetime.now().replace(second=0, microsecond=0)
    for n in range(21):
        MessageFactory.create(email_list=pubthree, date=date - datetime.timedelta(days=n))

    # add thread view messages
    # NOTE: thread_order 1 has later date
    apple = EmailListFactory.create(name='apple')
    cthread = ThreadFactory.create(date=datetime.datetime(2017, 1, 1))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='New Topic',
                          thread_order=0,
                          date=datetime.datetime(2017, 1, 1))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=5,
                          date=datetime.datetime(2017, 1, 2))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=2,
                          date=datetime.datetime(2017, 1, 3))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=3,
                          date=datetime.datetime(2017, 1, 4))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=4,
                          date=datetime.datetime(2017, 1, 5))
    MessageFactory.create(email_list=apple,
                          thread=cthread,
                          subject='Re: New Topic',
                          thread_order=1,
                          date=datetime.datetime(2017, 1, 6))
    MessageFactory.create(email_list=private)
    
    # listnames with hyphen
    devops = EmailListFactory.create(name='dev-ops')
    MessageFactory.create(email_list=devops)

    privateops = EmailListFactory.create(name='private-ops', private=True)
    MessageFactory.create(email_list=privateops)

@pytest.fixture(scope="session")
def index_resource():
    if not Message.objects.first():
        load_db()
    # build index
    content = StringIO()
    call_command('update_index', stdout=content)

    def fin():
        call_command('clear_index', noinput=True, stdout=content)
        print content.read()


@pytest.fixture()
def messages(index_resource):
    """Load some messages into db and index for testing"""
    if not Message.objects.first():
        load_db()


@pytest.fixture(scope="session")
def index():
    """Load a Xapian index"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'ancp-2010-03.mail')
    call_command('load', path, listname='ancp', summary=True, stdout=content)
    # def fin():
    #   remove index


@pytest.fixture()
def thread_messages():
    """Load some threads"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'thread.mail')
    call_command('load', path, listname='acme', summary=True, stdout=content)


