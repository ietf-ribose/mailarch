

import random
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache

from mlarchive.archive.utils import get_lists
from mlarchive.utils.test_utils import get_search_backend


VALID_QUERYID_RE = re.compile(r'^[a-f0-9]{32}$')
FILTER_PARAMS = ('f_list', 'f_from')
NON_FILTER_PARAMS = ('so', 'sso', 'page', 'gbt')

VALID_SORT_OPTIONS = ('frm', '-frm', 'date', '-date', 'email_list', '-email_list',
                      'subject', '-subject')

DEFAULT_SORT = getattr(settings, 'ARCHIVE_DEFAULT_SORT', '-date')
DB_THREAD_SORT_FIELDS = ('-thread__date', 'thread_id', 'thread_order')
IDX_THREAD_SORT_FIELDS = ('-tdate', 'tid', 'torder')

# --------------------------------------------------
# Functions handle URL parameters
# --------------------------------------------------


def generate_queryid():
    return '%032x' % random.getrandbits(128)


def get_base_query(querydict):
    """Expects a QueryDict object, ie. request.GET.  Returns a copy of the querydict
    with sorting or grouping parameters (those which do not alter the content of
    the results) removed.
    """
    copy = querydict.copy()
    for key in querydict:
        if key in NON_FILTER_PARAMS:
            copy.pop(key)
    return copy


def get_cached_query(request):
    if 'qid' in request.GET:
        queryid = clean_queryid(request.GET['qid'])
        if queryid:
            return (queryid, cache.get(queryid))
    return (None, None)


def clean_queryid(query_id):
    if VALID_QUERYID_RE.match(query_id):
        return query_id
    else:
        return None


def get_filter_params(query):
    """Return list of filter parameters that appear in the query"""
    return [k for k, v in list(query.items()) if k in FILTER_PARAMS and v]


def get_kwargs(data):
    """Returns a dictionary to be used as kwargs for the SearchQuerySet, data is
    a dictionary from form.cleaned_data.  This function can be used with multiple
    forms which may not include exactly the same fields, so we use the get() method.
    """
    kwargs = {}
    spam_score = data.get('spam_score')
    for key in ('msgid',):
        if data.get(key):
            kwargs[key] = data[key]
    if data.get('start_date'):
        kwargs['date__gte'] = data['start_date']
    if data.get('end_date'):
        kwargs['date__lte'] = data['end_date']
    if data.get('email_list'):
        # with Haystack/Xapian must replace dash with space in email list names
        if get_search_backend() == 'xapian':
            kwargs['email_list__in'] = [x.replace('-', ' ') for x in data['email_list']]
        else:
            kwargs['email_list__in'] = data['email_list']
    if data.get('frm'):
        kwargs['frm__contains'] = data['frm']   # use __contains for faceted(keyword) field
    if data.get('subject'):
        kwargs['subject'] = data['subject']
    if data.get('spam'):
        kwargs['spam_score__gt'] = 0
    if spam_score and spam_score.isdigit():
        bits = [x for x in range(255) if x & int(spam_score)]
        kwargs['spam_score__in'] = bits
    if data.get('to'):
        kwargs['to'] = data['to']
    kwargs.update(get_qdr_kwargs(data))

    return kwargs


def get_qdr_kwargs(data):
    qdr_kwargs = {}
    if data.get('qdr') and data['qdr'] in ('d', 'w', 'm', 'y'):
        qdr_kwargs['date__gte'] = get_qdr_time(data['qdr'])

    return qdr_kwargs


def get_qdr_time(val):
    """Expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    """
    now = datetime.now()
    if val == 'h':
        return now - timedelta(hours=1)
    elif val == 'd':
        return now - timedelta(days=1)
    elif val == 'w':
        return now - timedelta(weeks=1)
    elif val == 'm':
        return now - timedelta(days=30)
    elif val == 'y':
        return now - timedelta(days=365)


def get_order_fields(params, use_db=False):
    """Returns the list of fields to use in queryset ordering.
    use_db: use database sort fields, as opposed to index sort fields
    TODO: synchronize index and database sort fields
    """
    if params.get('gbt'):
        if use_db:
            return DB_THREAD_SORT_FIELDS
        else:
            return IDX_THREAD_SORT_FIELDS

    # default sort order is date descending
    so = map_sort_option(params.get('so', DEFAULT_SORT), use_db)
    sso = map_sort_option(params.get('sso'), use_db)
    fields = [v for v in (so, sso) if v]
    return fields if fields else [DEFAULT_SORT]


def map_sort_option(val, use_db=False):
    """This function takes a sort parameter and validates and maps it for use
    in an order_by clause.
    TODO: do in a dictionary instead
    """
    if val not in VALID_SORT_OPTIONS:
        return ''
    if val in ('frm', '-frm') and not use_db:
        val = val + '_name'
    if val == 'subject':
        val = 'base_subject'
    if val == '-subject':
        val = '-base_subject'
    return val


def parse_query(request):
    """Returns the query as a string.  Usually this is just the 'q' parameter.
    However, in the case of an advanced search with javascript disabled we need
    to build the query given the query parameters in the request"""
    if request.GET.get('q'):
        return parse_query_string(request.GET.get('q'))
    elif 'nojs' in request.META['QUERY_STRING']:
        query = []
        not_query = []
        items = list(filter(is_nojs_value, list(request.GET.items())))
        for key, value in items:
            field = request.GET[key.replace('value', 'field')]
            # qualifier = request.GET[key.replace('value','qualifier')]
            if 'query' in key:
                query.append('{}:({})'.format(field, value))
            else:
                not_query.append('-{}:({})'.format(field, value))
        return ' '.join(query + not_query)
    else:
        return ''


def parse_query_string(query):
    # Map from => frm
    if 'from:' in query:
        query = query.replace('from:', 'frm:')
    return query


def is_nojs_value(items):
    k, v = items
    if k.startswith('nojs') and k.endswith('value') and v:
        return True
    else:
        return False


def get_browse_equivalent(request):
    """Returns the listname if the query params are the equivalent of a list browse:
    /?q=[listname] or /?email_list=[listname]"""
    if list(request.GET) == ['q'] and request.GET.get('q') in get_lists():
        return request.GET.get('q')
    if list(request.GET) == ['email_list'] and len(request.GET.getlist('email_list')) == 1:
        return request.GET.get('email_list')


def is_static_on(request):
    return True if request.COOKIES.get('isStaticOn') == 'true' else False
