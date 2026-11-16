"""Authentication operations. Raw action and refresh tokens never enter the database."""

import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.core.validators import validate_email

from .models import AccountRole, AccountStatus, AuthActionToken, AuthSession, PasswordCredential, TokenPurpose, User, UserRole

ACCESS_LIFETIME = timedelta(minutes=15)
REFRESH_LIFETIME = timedelta(days=30)
ACTION_LIFETIMES = {
    TokenPurpose.VERIFY_EMAIL: timedelta(hours=24),
    TokenPurpose.RESET_PASSWORD: timedelta(hours=1),
}


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def normalize_email(email):
    if not isinstance(email, str):
        raise AuthError('A valid email address is required.')
    email = email.strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise AuthError('A valid email address is required.') from exc
    if len(email) > 320:
        raise AuthError('Email address is too long.')
    return email


def validate_new_password(password, email):
    if not isinstance(password, str) or len(password) > 1024:
        raise AuthError('A valid password is required.')
    try:
        validate_password(password, user=User(email=email))
    except ValidationError as exc:
        raise AuthError(' '.join(exc.messages)) from exc


def token_hash(raw_token):
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def new_raw_token():
    return secrets.token_urlsafe(48)


def send_action_email(user, purpose, raw_token):
    if purpose == TokenPurpose.VERIFY_EMAIL:
        subject, path, api_path = 'Verify your email address', '/verify-email', '/api/v1/auth/verify-email/'
    else:
        subject, path, api_path = 'Reset your password', '/reset-password', '/api/v1/auth/password-reset/confirm/'
    if settings.AUTH_FRONTEND_URL:
        message = 'Use this link to continue: ' + settings.AUTH_FRONTEND_URL.rstrip('/') + path + '?' + urlencode({'token': raw_token})
    else:
        message = f'Submit this token to {api_path}: {raw_token}'
    send_mail(subject, message + '\n', settings.DEFAULT_FROM_EMAIL, [user.email])


def issue_action_token(user, purpose):
    """Caller must hold a row lock on user in the surrounding transaction."""
    now = timezone.now()
    AuthActionToken.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(consumed_at=now)
    raw_token = new_raw_token()
    AuthActionToken.objects.create(
        user=user, purpose=purpose, token_hash=token_hash(raw_token),
        created_at=now, expires_at=now + ACTION_LIFETIMES[purpose],
    )
    transaction.on_commit(lambda: send_action_email(user, purpose, raw_token))


def register(email, password):
    email = normalize_email(email)
    validate_new_password(password, email)
    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, password=password)
            UserRole.objects.create(user=user, role=AccountRole.STUDENT)
            issue_action_token(user, TokenPurpose.VERIFY_EMAIL)
    except IntegrityError as exc:
        raise AuthError('An account with this email already exists.', 409) from exc
    return user


def resend_verification(email):
    email = normalize_email(email)
    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=email, status=AccountStatus.PENDING_VERIFICATION).first()
        if user:
            issue_action_token(user, TokenPurpose.VERIFY_EMAIL)


def consume_action_token(raw_token, purpose):
    if not isinstance(raw_token, str) or not raw_token:
        raise AuthError('Invalid or expired token.')
    candidate = AuthActionToken.objects.filter(token_hash=token_hash(raw_token), purpose=purpose).only('id', 'user_id').first()
    if not candidate:
        raise AuthError('Invalid or expired token.')
    user = User.objects.select_for_update().filter(id=candidate.user_id).first()
    token = AuthActionToken.objects.select_for_update().filter(id=candidate.id).first()
    if not user or not token or token.consumed_at or token.expires_at <= timezone.now():
        raise AuthError('Invalid or expired token.')
    token.consumed_at = timezone.now()
    token.save(update_fields=['consumed_at'])
    return user


def verify_email(raw_token):
    with transaction.atomic():
        user = consume_action_token(raw_token, TokenPurpose.VERIFY_EMAIL)
        if not user.email_verified_at:
            user.email_verified_at = timezone.now()
            if user.status == AccountStatus.PENDING_VERIFICATION:
                user.status = AccountStatus.ACTIVE
            user.save(update_fields=['email_verified_at', 'status', 'updated_at'])
    return user


def request_password_reset(email):
    email = normalize_email(email)
    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=email).first()
        if user and user.status != AccountStatus.SUSPENDED:
            issue_action_token(user, TokenPurpose.RESET_PASSWORD)


def confirm_password_reset(raw_token, new_password):
    with transaction.atomic():
        user = consume_action_token(raw_token, TokenPurpose.RESET_PASSWORD)
        validate_new_password(new_password, user.email)
        credential = PasswordCredential.objects.select_for_update().get(user=user)
        credential.password_hash = make_password(new_password)
        credential.password_changed_at = timezone.now()
        credential.save(update_fields=['password_hash', 'password_changed_at'])
        AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    return user


def create_access_token(user):
    now = timezone.now()
    return jwt.encode(
        {'sub': str(user.id), 'iat': now, 'exp': now + ACCESS_LIFETIME, 'iss': 'fieldnotes', 'aud': 'fieldnotes-api', 'jti': str(uuid.uuid4())},
        settings.JWT_SIGNING_KEY, algorithm='HS256',
    )


def create_session(user):
    raw_token = new_raw_token()
    now = timezone.now()
    AuthSession.objects.create(user=user, refresh_token_hash=token_hash(raw_token), created_at=now, expires_at=now + REFRESH_LIFETIME)
    return {'access_token': create_access_token(user), 'refresh_token': raw_token, 'token_type': 'Bearer', 'expires_in': int(ACCESS_LIFETIME.total_seconds())}


def login(email, password):
    email = normalize_email(email)
    user = User.objects.filter(email=email).first()
    credential = PasswordCredential.objects.filter(user=user).first() if user else None
    if not credential or not isinstance(password, str) or not check_password(password, credential.password_hash):
        raise AuthError('Invalid email or password.', 401)
    if user.status != AccountStatus.ACTIVE or not user.email_verified_at:
        raise AuthError('Account is not active or email is unverified.', 403)
    return create_session(user)


def rotate_refresh_token(raw_token):
    if not isinstance(raw_token, str) or not raw_token:
        raise AuthError('Invalid refresh token.', 401)
    with transaction.atomic():
        digest = token_hash(raw_token)
        candidate = AuthSession.objects.filter(refresh_token_hash=digest).only('id', 'user_id').first()
        if not candidate:
            raise AuthError('Invalid refresh token.', 401)
        user = User.objects.select_for_update().filter(id=candidate.user_id).first()
        session = AuthSession.objects.select_for_update().filter(id=candidate.id).first()
        if not user or not session or session.refresh_token_hash != digest or session.revoked_at or session.expires_at <= timezone.now() or user.status != AccountStatus.ACTIVE:
            raise AuthError('Invalid refresh token.', 401)
        replacement = new_raw_token()
        session.refresh_token_hash = token_hash(replacement)
        session.last_used_at = timezone.now()
        session.save(update_fields=['refresh_token_hash', 'last_used_at'])
        access = create_access_token(user)
    return {'access_token': access, 'refresh_token': replacement, 'token_type': 'Bearer', 'expires_in': int(ACCESS_LIFETIME.total_seconds())}


def revoke_refresh_token(raw_token):
    if isinstance(raw_token, str) and raw_token:
        AuthSession.objects.filter(refresh_token_hash=token_hash(raw_token), revoked_at__isnull=True).update(revoked_at=timezone.now())


def authenticate_access_token(raw_token):
    try:
        payload = jwt.decode(raw_token, settings.JWT_SIGNING_KEY, algorithms=['HS256'], audience='fieldnotes-api', issuer='fieldnotes', options={'require': ['sub', 'iat', 'exp', 'jti']})
        user_id = uuid.UUID(payload['sub'])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise AuthError('Invalid access token.', 401) from exc
    user = User.objects.filter(id=user_id, status=AccountStatus.ACTIVE, email_verified_at__isnull=False).first()
    if not user:
        raise AuthError('Invalid access token.', 401)
    return user
