"""Public directory reads and administrator-only changes."""

import json
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.services import AuthError

from . import services


def api(handler):
    @wraps(handler)
    def wrapped(request, *args, **kwargs):
        try:
            response = handler(request, *args, **kwargs)
        except (services.DirectoryError, AuthError) as exc:
            response = JsonResponse({'error': str(exc)}, status=exc.status)
        response['Cache-Control'] = 'no-store'
        return response
    return csrf_exempt(wrapped)


def json_body(request):
    if len(request.body) > 16384:
        raise services.DirectoryError('Request body is too large.', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise services.DirectoryError('A JSON object is required.') from exc
    if not isinstance(data, dict):
        raise services.DirectoryError('A JSON object is required.')
    return data


def include_inactive(request):
    value = request.GET.get('include_inactive', 'false').lower()
    if value not in {'true', 'false'}:
        raise services.DirectoryError('include_inactive must be true or false.')
    if value == 'true':
        services.administrator(request)
        return True
    return False


def page_number(value, field, default, maximum=None):
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise services.DirectoryError(f'{field} must be an integer.') from exc
    if number < (1 if field == 'limit' else 0) or (maximum is not None and number > maximum):
        raise services.DirectoryError(f'{field} is outside the allowed range.')
    return number


@require_http_methods(['GET', 'POST'])
@api
def collection(request, resource):
    services.resource_model(resource)
    if request.method == 'POST':
        services.administrator(request)
        item = services.save_item(resource, json_body(request))
        return JsonResponse(services.serialize(resource, item), status=201)
    query = services.filter_queryset(resource, request.GET, include_inactive(request))
    limit = page_number(request.GET.get('limit'), 'limit', 50, 100)
    offset = page_number(request.GET.get('offset'), 'offset', 0)
    total = query.count()
    return JsonResponse({
        'count': total,
        'limit': limit,
        'offset': offset,
        'results': [services.serialize(resource, item) for item in query[offset:offset + limit]],
    })


@require_http_methods(['GET', 'PATCH'])
@api
def detail(request, resource, item_id):
    services.resource_model(resource)
    if request.method == 'PATCH':
        services.administrator(request)
        item = services.get_item(resource, item_id, include_inactive=True)
        item = services.save_item(resource, json_body(request), item)
    else:
        item = services.get_item(resource, item_id, include_inactive(request))
    return JsonResponse(services.serialize(resource, item))
