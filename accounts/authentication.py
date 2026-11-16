"""Bearer authentication helper for future API apps."""

from .services import AuthError, authenticate_access_token


def authenticated_user(request):
    authorization = request.headers.get('Authorization', '')
    scheme, separator, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not separator or not token.strip():
        raise AuthError('A Bearer access token is required.', 401)
    return authenticate_access_token(token.strip())
