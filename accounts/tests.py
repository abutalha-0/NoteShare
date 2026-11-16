import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import AccountRole, AccountStatus, AuthActionToken, AuthSession, User, UserRole


class AuthenticationFlowTests(TestCase):
    def post_json(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type='application/json')

    def email_token(self):
        return mail.outbox[-1].body.rsplit(': ', 1)[1].strip()

    def register(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_json('/api/v1/auth/register/', {'email': '  Student@Example.com ', 'password': 'SecurePassphrase123!'})
        self.assertEqual(response.status_code, 201)
        return self.email_token()

    def verify(self, token):
        response = self.post_json('/api/v1/auth/verify-email/', {'token': token})
        self.assertEqual(response.status_code, 200)

    def test_registration_verification_login_refresh_and_logout(self):
        token = self.register()
        user = User.objects.get()
        self.assertEqual(user.email, 'student@example.com')
        self.assertEqual(user.status, AccountStatus.PENDING_VERIFICATION)
        self.assertEqual(list(UserRole.objects.values_list('role', flat=True)), [AccountRole.STUDENT])
        self.assertEqual(AuthActionToken.objects.count(), 1)
        self.assertNotIn('SecurePassphrase123!', user.credential.password_hash)
        self.assertEqual(self.post_json('/api/v1/auth/login/', {'email': user.email, 'password': 'SecurePassphrase123!'}).status_code, 403)
        self.verify(token)
        self.assertEqual(self.post_json('/api/v1/auth/verify-email/', {'token': token}).status_code, 400)
        login = self.post_json('/api/v1/auth/login/', {'email': user.email, 'password': 'SecurePassphrase123!'})
        self.assertEqual(login.status_code, 200)
        credentials = login.json()
        me = self.client.get('/api/v1/auth/me/', HTTP_AUTHORIZATION='Bearer ' + credentials['access_token'])
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['roles'], ['student'])
        self.assertEqual(AuthSession.objects.count(), 1)
        self.assertNotEqual(AuthSession.objects.get().refresh_token_hash, credentials['refresh_token'])
        rotated = self.post_json('/api/v1/auth/refresh/', {'refresh_token': credentials['refresh_token']})
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(self.post_json('/api/v1/auth/refresh/', {'refresh_token': credentials['refresh_token']}).status_code, 401)
        replacement = rotated.json()['refresh_token']
        self.assertEqual(self.post_json('/api/v1/auth/logout/', {'refresh_token': replacement}).status_code, 200)
        self.assertEqual(self.post_json('/api/v1/auth/refresh/', {'refresh_token': replacement}).status_code, 401)

    def test_reset_replaces_token_and_revokes_sessions(self):
        self.verify(self.register())
        login = self.post_json('/api/v1/auth/login/', {'email': 'student@example.com', 'password': 'SecurePassphrase123!'}).json()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post_json('/api/v1/auth/password-reset/request/', {'email': 'student@example.com'}).status_code, 200)
        old_token = self.email_token()
        with self.captureOnCommitCallbacks(execute=True):
            self.post_json('/api/v1/auth/password-reset/request/', {'email': 'student@example.com'})
        new_token = self.email_token()
        self.assertEqual(self.post_json('/api/v1/auth/password-reset/confirm/', {'token': old_token, 'password': 'AnotherStrongPass456!'}).status_code, 400)
        self.assertEqual(self.post_json('/api/v1/auth/password-reset/confirm/', {'token': new_token, 'password': 'AnotherStrongPass456!'}).status_code, 200)
        self.assertEqual(self.post_json('/api/v1/auth/password-reset/confirm/', {'token': new_token, 'password': 'AnotherStrongPass456!'}).status_code, 400)
        self.assertEqual(self.post_json('/api/v1/auth/refresh/', {'refresh_token': login['refresh_token']}).status_code, 401)
        self.assertEqual(self.post_json('/api/v1/auth/login/', {'email': 'student@example.com', 'password': 'SecurePassphrase123!'}).status_code, 401)
        self.assertEqual(self.post_json('/api/v1/auth/login/', {'email': 'student@example.com', 'password': 'AnotherStrongPass456!'}).status_code, 200)

    def test_email_uniqueness_and_generic_reset_response(self):
        self.register()
        response = self.post_json('/api/v1/auth/register/', {'email': 'STUDENT@example.com', 'password': 'SecurePassphrase123!'})
        self.assertEqual(response.status_code, 409)
        response = self.post_json('/api/v1/auth/password-reset/request/', {'email': 'nobody@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_suspended_account_cannot_login(self):
        self.verify(self.register())
        User.objects.update(status=AccountStatus.SUSPENDED)
        self.assertEqual(self.post_json('/api/v1/auth/login/', {'email': 'student@example.com', 'password': 'SecurePassphrase123!'}).status_code, 403)

    def test_expired_action_token_and_invalid_access_token(self):
        token = self.register()
        future = timezone.now() + timedelta(days=2)
        with mock.patch('accounts.services.timezone.now', return_value=future):
            self.assertEqual(self.post_json('/api/v1/auth/verify-email/', {'token': token}).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/auth/me/', HTTP_AUTHORIZATION='Bearer invalid').status_code, 401)

    def test_user_model_normalizes_email_and_uses_external_credential(self):
        self.assertIs(get_user_model(), User)
        user = User.objects.create_user(' Upper@Example.com ', 'SecurePassphrase123!')
        self.assertEqual(user.email, 'upper@example.com')
        self.assertNotIn('password', [field.name for field in User._meta.local_fields])
        self.assertTrue(user.check_password('SecurePassphrase123!'))
        self.assertIsNone(authenticate(email=user.email, password='SecurePassphrase123!'))
        user.status = AccountStatus.ACTIVE
        user.email_verified_at = timezone.now()
        user.save()
        self.assertEqual(authenticate(email=user.email, password='SecurePassphrase123!'), user)

    def test_validation_and_request_errors(self):
        self.assertEqual(self.post_json('/api/v1/auth/register/', {'email': 'bad', 'password': 'short'}).status_code, 400)
        self.assertEqual(self.post_json('/api/v1/auth/register/', {'email': 'ok@example.com', 'password': 'short'}).status_code, 400)
        self.assertEqual(self.client.post('/api/v1/auth/register/', 'bad json', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/auth/register/').status_code, 405)
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)

    def test_resend_verification_invalidates_previous_token(self):
        first = self.register()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post_json('/api/v1/auth/resend-verification/', {'email': 'student@example.com'}).status_code, 200)
        second = self.email_token()
        self.assertNotEqual(first, second)
        self.assertEqual(self.post_json('/api/v1/auth/verify-email/', {'token': first}).status_code, 400)
        self.verify(second)

    def test_superuser_role_and_csrf_exempt_bearer_api(self):
        user = User.objects.create_superuser('admin@example.com', 'SecurePassphrase123!')
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.has_perm('accounts.view_user'))
        client = self.client_class(enforce_csrf_checks=True)
        response = client.post('/api/v1/auth/login/', data=json.dumps({'email': user.email, 'password': 'SecurePassphrase123!'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
