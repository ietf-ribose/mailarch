#!/usr/bin/python
'''
This script will report on and fix various kinds of corruptions identified in the
original mail archive
'''

# Set PYTHONPATH and load environment variables for standalone script -----------------
# for file living in project/bin/
import os
import sys
path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not path in sys.path:
    sys.path.insert(0, path)

import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.development'
django.setup()

# -------------------------------------------------------------------------------------

import argparse
import re
import shutil
from collections import deque
from pprint import pprint
from scan_utils import all_mboxs, is_mmdf
from mlarchive.archive.management.commands import _classes
from mlarchive.archive.models import Message

VALID_FROM_PATTERN = re.compile(r'^From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
EMBEDDED_FROM_PATTERN = re.compile(r'.+(From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+)')
QUOTED_FROM_PATTERN = re.compile(r'[ :>%\|\-\*\]]+From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
LEGIT_FROM_PATTERN = re.compile(r'^(Received|MBOX-Line|X-Mailbox-Line): From')
SPACES_FROM_PATTERN = re.compile(r'\s+From\s[^ ]* (Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s.+')
HTML_FROM_PATTERN = re.compile(r'^(<.+>)+[ :>%\|\-\*\]]*(&gt;)*From')
CONTINUED_HEADER_PATTERN = re.compile(r'^Return-[Pp]ath:')
HEADER_PATTERN = re.compile(r'^[\041-\071\073-\176]{1,}:')
RETURN_PATH_PATTERN = re.compile(r'^Return-[Pp]ath:')
WHITESPACE_PATTERN = re.compile(r'\s')
MMDF_SEPARATOR = '\x01\x01\x01\x01\n'
TYPE1_FILE_RE = re.compile(r'\d{4}-\d{2}\.mail')
TYPE2_ID_RE = re.compile(r'^id .*; (Mon|Tue|Wed|Thu|Fri|Sat|Sun)')
STATS = {}

TOTAL_EFCOUNT = 0

def false_positive(line):
    """Returns True if line matches a type of legitimate line"""
    if QUOTED_FROM_PATTERN.match(line):
        return True
    if LEGIT_FROM_PATTERN.match(line):
        new_line = line[14:]
        if not EMBEDDED_FROM_PATTERN.match(new_line):
            return True
    if SPACES_FROM_PATTERN.match(line):
        return True
    if QUOTED_FROM_PATTERN.match(line.replace('&gt;','>')):
        return True
    if HTML_FROM_PATTERN.match(line):
        return True
    return False

def find_top(lines,index):
    """Given a mbox file, list of lines, and a particular line number, index,
    find the beginning of the Message above index"""
    pointer = index
    while True:
        while lines[pointer] != '\n':
            pointer = pointer - 1
        #print lines[pointer+1]
        if VALID_FROM_PATTERN.match(lines[pointer+1]) or RETURN_PATH_PATTERN.match(lines[pointer+1]):
            break
        pointer = pointer - 1
    return pointer + 1

def get_from_chunk(line):
    """Given a line with an embedded From segment, extract the From segment from end of
    line"""
    match = EMBEDDED_FROM_PATTERN.match(line)
    if not match:
        print "FROM PATTERN UNMATCHED: {}".format(line)
    return match.groups()[0]

def get_listname(path):
    return path.split('/')[-2]
    
def handle_type1(path,line,args):
    '''
    Type1 is when the file starts with MMDF style envelope lines (^A^A^A^A) and
    switches to normal "From " line separators.
    
    Fix splits the file into two pieces ie. 
    1998-08 : containing the MMDF style messages
    1998-08.mail : containing the normal mbox style messages
    '''
    if args.type1:
        if args.verbose:
            print "{}:{}".format(path,line)
        if args.fix:
            basename = os.path.basename(path)
            assert TYPE1_FILE_RE.match(basename)
            dirname = os.path.dirname(path)
            filename, file_extension = os.path.splitext(basename)
            dst = os.path.join(dirname,filename + '.orig')
            shutil.move(path,dst)
            input = open(dst, 'r').read().split('\n')
            # write first piece
            output = open(os.path.join(dirname,filename),'w')
            outputData = input[:line]
            output.write('\n'.join(outputData))
            output.close()
            # write second piece
            output = open(os.path.join(dirname,filename + '.mail'),'w')
            outputData = input[line:]
            output.write('\n'.join(outputData))
            output.close()
            
def handle_type2(path,line,args,last_two):
    '''
    Type2 is when Received "id" lines aren't properly indented
    '''
    global STATS
    if args.type2:
        STATS['type2_files'].add(path)
        STATS['type2_calls'] += 1
        if TYPE2_ID_RE.match(last_two[1]):
            STATS['type2_per_file'][path] = STATS['type2_per_file'].get(path,0) + 1
        if args.verbose:
            print "{}:{}".format(path,line)
            pprint(last_two)
        if args.fix:
            pass

def handle_type3(path,index,args):
    '''
    Type3 is a embedded From line
    '''
    global STATS
    STATS['type3_files'].add(path)
    listname = get_listname(path)
    
    with open(path) as fp:
        lines = fp.readlines()
    
    try:
        start = find_top(lines,index)
    except IndexError:
        print "top not found: {}.{}".format(path,index)
        STATS['type3_errors'] += 1
    
    # readlines up to but not including top
    with open(path) as fp:
        for x in xrange(start):
            xline = fp.readline()
        begin_byte = fp.tell()
        #print "start: {}, xline: {}, begin_byte: {}".format(start,xline,begin_byte)
    
    # use TOC to find message in mailbox
    mb = _classes.get_mb(path)
    mb._generate_toc()
    for k,v in mb._toc.items():
        if v[0] == begin_byte:
            toc_index = k
            break
    else:
        print "no match to {}".format(begin_byte)
        sys.exit(1)
        
    # match to messages in archive
    print "toc index: {}".format(toc_index)
    mw = _classes.MessageWrapper(mb[toc_index],listname)
    try:
        message = Message.objects.get(email_list__name=listname,
            msgid=mw.archive_message.msgid)
    except Message.DoesNotExist:
        print "failed, {}:{}".format(listname,mw.archive_message.msgid)
        STATS['type3_missing'] += 1
        #sys.exit(1)
    
    #print "found message {}".format(message.pk)
    
    #from_line = get_from_chunk(lines[index]) + '\n'
    #if lines[start] != from_line:
    #    print "lines[start] : {}".format(lines[start])
    #    print "from_line : {}".format(from_line)
    #    sys.exit(1)
    #assert lines[start] == from_line + '\n'
    #print "START {}:{}".format(start,lines[start])

def process_mbox(path,args):
    # skip django-project, too many false positives
    listname = path.split('/')[-2]
    if listname == 'django-project':
        return
    global TOTAL_EFCOUNT
    efcount = 0
    with open(path) as fp:
        for num,line in enumerate(fp):
            if EMBEDDED_FROM_PATTERN.match(line) and not false_positive(line):
                efcount += 1
                if args.verbose:
                    print "{}:{}:{}".format(listname,num+1,line)
                handle_type3(path,num,args)
    if efcount > 0:
        print "{}:{}:{}".format(path,'MBOX',efcount)
    TOTAL_EFCOUNT = TOTAL_EFCOUNT + efcount

def process_mmdf(path,args):
    global STATS

    lines = deque(maxlen=5)
    with open(path) as fp:
        for num,line in enumerate(fp):
            lines.append(line)
            if line == MMDF_SEPARATOR:
                in_header = True
                continue
            if not in_header:
                continue
            if line == '\n':    # end of headers, skip to next message
                in_header = False
                continue
            if HEADER_PATTERN.match(line):
                continue
            if not WHITESPACE_PATTERN.match(line):
                STATS['uhcount'] += 1
                last_two = list(lines)[-2:]
                if last_two[0] == MMDF_SEPARATOR:
                    handle_type1(path,num,args)
                if last_two[0].startswith('Received:'):
                    handle_type2(path,num,args,last_two)
                else:
                    if args.verbose:
                        print "{}:{}".format(path,num)
                        pprint(last_two)
                    STATS['unhandled'] += 1

def test():
    '''Real examples from the archive to use for testing'''
    samples = [
    '<From asrg-bounces@ietf.org Tue Sep 18 09:28:25 2007',
    '|From wes@hardakers.net Thu Feb 22 10:55:31 PST 2001',
    '    &gt; From owner-disman@dorothy.bmc.com Mon Mar 18 13:08:39 PST 2002 =',
    '<BR><FONT SIZE=3D2>|From ramk@cisco.com Thu Dec 16 15:49:13 PST =',
    '<P><FONT SIZE=2>&gt;From amyk@cnri.reston.va.us Mon Jan 19 23:37:40 2004</FONT>',
    'X-Mailbox-Line: From elwynd@nomadic.n4c.eu Sat Jul 25 12:56:31 2009',
    ]
    
def main():
    global STATS
    parser = argparse.ArgumentParser(description='Fix corrupt mbox file')
    parser.add_argument('path',nargs="?")     # positional argument
    parser.add_argument('-c','--check',help="check only, dont't import",action='store_true')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    # show type1: when file starts with MMDF separator but continues with normal From lines
    parser.add_argument('-1','--type1', help='type1: multiple separators',action='store_true')
    parser.add_argument('-2','--type2', help='type2: unindented multiline header',action='store_true')
    parser.add_argument('-f','--fix',help="perform fix",action='store_true')
    args = parser.parse_args()

    # init stats
    STATS['type2_files'] = set()
    STATS['type3_files'] = set()
    STATS['type3_errors'] = 0
    STATS['type3_missing'] = 0
    STATS['type2_per_file'] = {}
    STATS['type2_calls'] = 0
    STATS['unhandled'] = 0
    STATS['uhcount'] = 0
    
    if args.path:
        listnames = [args.path]
    else:
        listnames = []

    for mbox in all_mboxs(listnames):
        if is_mmdf(mbox):
            process_mmdf(mbox, args)
        else:
            process_mbox(mbox, args)

    print "Total Embedded From Lines: {}".format(TOTAL_EFCOUNT)
    
    # print stats
    exceptions = ['type2_files','type3_files']  # don't print these stats
    items = [ '%s:%s' % (k,v) for k,v in STATS.items() if k not in exceptions]
    items.append('\n')
    print '\n'.join(items)
    print
    #print '\n'.join(STATS['type3_files'])
    print "Total: {}".format(len(STATS['type3_files']))
            
if __name__ == "__main__":
    main()


