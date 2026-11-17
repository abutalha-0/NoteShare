"""Own and public profile API."""

import json
from functools import wraps

from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.authentication import authenticated_user
from accounts.services import AuthError

from . import services


def api(handler):
    @wraps(handler)
    def wrapped(request, *args, **kwargs):
        try:
            response = handler(request, *args, **kwargs)
        except (services.ProfileError, AuthError) as exc:
            response = JsonResponse({'error': str(exc)}, status=exc.status)
        response['Cache-Control'] = 'no-store'
        return response
    return csrf_exempt(wrapped)


def json_body(request):
    if len(request.body) > 16384:
        raise services.ProfileError('Request body is too large.', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise services.ProfileError('A JSON object is required.') from exc
    if not isinstance(data, dict):
        raise services.ProfileError('A JSON object is required.')
    return data


@require_http_methods(['GET', 'PATCH'])
@api
def me(request):
    user = authenticated_user(request)
    profile = services.own_profile(user) if request.method == 'GET' else services.update_profile(user, json_body(request))
    return JsonResponse(services.serialize(profile, owner=True))


@require_http_methods(['GET'])
@api
def public(request, user_id):
    return JsonResponse(services.serialize(services.public_profile(user_id)))


@require_http_methods(['GET', 'POST', 'DELETE'])
@api
def my_avatar(request):
    user = authenticated_user(request)
    if request.method == 'POST':
        profile = services.set_avatar(user, request.FILES.get('avatar'))
        return JsonResponse({'avatar_url': services.serialize(profile, owner=True)['avatar_url']})
    if request.method == 'DELETE':
        services.remove_avatar(user)
        return JsonResponse({'avatar_url': None})
    return FileResponse(services.avatar_file(services.own_profile(user)), content_type='image/webp')


@require_http_methods(['GET'])
@api
def public_avatar(request, user_id):
    profile = services.public_profile(user_id)
    if not profile.show_avatar:
        raise services.ProfileError('Avatar not found.', 404)
    return FileResponse(services.avatar_file(profile), content_type='image/webp')
