# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-07-25 09:22
# from __future__ import unicode_literals

import email
import os
import re
from django.db import migrations
from django.conf import settings
from mlarchive.utils.encoding import decode_safely, decode_rfc2047_header


subj_blob_pattern = r'(\[[\040-\132\134\136-\176]{1,}\]\s*)'
subj_refwd_pattern = r'([Rr][eE]|F[Ww][d]?)\s*' + subj_blob_pattern + r'?:\s'
subj_leader_pattern = subj_blob_pattern + r'*' + subj_refwd_pattern
subj_blob_regex = re.compile(r'^' + subj_blob_pattern)
subj_leader_regex = re.compile(r'^' + subj_leader_pattern)


def fix_encoded_words(apps, schema_editor):
    """For all messages with MIME encoded-words in headers, get decoded, normalized value
    and update database if necessary.

    The file 0017_auto_20180725_0922.data provides PKs of all messages with encoded-words
    in headers From or Subject.
    """
    Message = apps.get_model('archive', 'Message')
    count = 0
    pks = []
    path = os.path.join(settings.BASE_DIR, 'archive', 'migrations', '0017_auto_20180725_0922.data')
    with open(path) as f:
        line = f.readline()
        while line:
            chop = line[:-1]    # remove newline
            pks.extend(chop.split(','))
            line = f.readline()

    for pk in pks:
        print "Processing: %s" % pk
        message = Message.objects.get(pk=pk)
        for db_header, header in (('frm', 'from'), ('subject', 'subject')):
            msg = email.message_from_string(get_body_raw(message))
            if msg[header] and '=?' in msg[header]:
                text = normalize(msg[header])
                if text != getattr(message, db_header):
                    count = count + 1
                    setattr(message, db_header, text)
                    if header == 'subject':
                        message.base_subject = get_base_subject(text)
                    message.save()

    print "%s Messages fixed" % count


def get_body_raw(message):
    """Returns the raw contents of the message file.
    NOTE: this will include encoded attachments
    """
    with open(get_file_path(message)) as f:
        return f.read()


def get_file_path(message):
    return os.path.join(
        settings.ARCHIVE_DIR,
        message.email_list.name,
        message.hashcode)


# from _classes.py
def normalize(header_text):
    """This function takes some header_text as a string.
    It returns the string decoded and normalized.
    Checks if the header needs decoding:
    - if text contains encoded_words, "=?", use decode_rfc2047_header()
    - or call decode_safely
    - finally, compress whitespace characters to one space
    """
    if not header_text:                  # just return if we are passed an empty string
        return header_text

    # TODO: need this?
    # if type(header_text) is unicode:    # return if already unicode
    #    return header_text              # ie. get_filename() for example sometimes returns unicode

    if '=?' in header_text:              # handle RFC2047 encoded-words
        normal = decode_rfc2047_header(header_text)
    else:
        normal = decode_safely(header_text)

    # encode as UTF8 and compress whitespace
    # normal = normal.encode('utf8')        # this is unnecessary
    normal = clean_spaces(normal)
    return normal.rstrip()


def clean_spaces(s):
    """Reduce all whitespaces to one space"""
    s = re.sub(r'\s+', ' ', s)
    return s


def get_base_subject(text):
    """Returns 'base subject' of a message.  This is the subject which has specific
    subject artifacts removed.  This function implements the algorithm defined in
    section 2.1 of RFC5256
    """
    # step 1 - now all handled by normalize
    # uni = decode_rfc2047_header(text)
    # utf8 = uni.encode('utf8')
    # text = clean_spaces(utf8)
    # text = text.rstrip()

    while True:
        # step 2
        while text.endswith('(fwd)'):
            text = text[:-5].rstrip()

        while True:
            # step 3
            textin = text
            text = subj_leader_regex.sub('', text)

            # step 4
            m = subj_blob_regex.match(text)
            if m:
                temp = subj_blob_regex.sub('', text)
                if temp:
                    text = temp
            if text == textin:    # step 5 (else repeat 3 & 4)
                break

        # step 6
        if text.startswith('[Fwd:') and text.endswith(']'):
            text = text[5:-1]
            text = text.strip()
        else:
            break

    return text


class Migration(migrations.Migration):

    dependencies = [
        ('archive', '0016_auto_20180724_2250'),
    ]

    operations = [
        migrations.RunPython(fix_encoded_words),
    ]
