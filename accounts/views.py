import json
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from . import services
from .authentication import authenticated_user


def body(request):
    if len(request.body) > 16384:
        raise services.AuthError('Request body is too large.', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise services.AuthError('A JSON object is required.') from exc
    if not isinstance(data, dict):
        raise services.AuthError('A JSON object is required.')
    return data


def api(handler):
    @wraps(handler)
    def wrapped(request, *args, **kwargs):
        try:
            response = handler(request, *args, **kwargs)
        except services.AuthError as exc:
            response = JsonResponse({'error': str(exc)}, status=exc.status)
        response['Cache-Control'] = 'no-store'
        return response
    return csrf_exempt(wrapped)


@require_POST
@api
def register(request):
    data = body(request)
    user = services.register(data.get('email'), data.get('password'))
    return JsonResponse({'id': str(user.id), 'email': user.email, 'status': user.status}, status=201)


@require_POST
@api
def verify_email(request):
    user = services.verify_email(body(request).get('token'))
    return JsonResponse({'id': str(user.id), 'status': user.status})


@require_POST
@api
def resend_verification(request):
    services.resend_verification(body(request).get('email'))
    return JsonResponse({'message': 'If the account is pending verification, an email has been sent.'})


@require_POST
@api
def login(request):
    data = body(request)
    return JsonResponse(services.login(data.get('email'), data.get('password')))


@require_POST
@api
def refresh(request):
    return JsonResponse(services.rotate_refresh_token(body(request).get('refresh_token')))


@require_POST
@api
def logout(request):
    services.revoke_refresh_token(body(request).get('refresh_token'))
    return JsonResponse({'message': 'Session revoked.'})


@require_POST
@api
def request_password_reset(request):
    services.request_password_reset(body(request).get('email'))
    return JsonResponse({'message': 'If the account exists, a reset email has been sent.'})


@require_POST
@api
def confirm_password_reset(request):
    data = body(request)
    services.confirm_password_reset(data.get('token'), data.get('password'))
    return JsonResponse({'message': 'Password updated.'})


@require_GET
@api
def me(request):
    user = authenticated_user(request)
    return JsonResponse({'id': str(user.id), 'email': user.email, 'status': user.status, 'roles': list(user.roles.values_list('role', flat=True))})
