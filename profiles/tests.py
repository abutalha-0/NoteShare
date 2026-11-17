import io
import json
import tempfile
from importlib import import_module
from types import SimpleNamespace

from PIL import Image
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import AccountStatus, User
from accounts.services import create_access_token
from academics.models import AcademicDepartment, Discipline, University

from .models import Profile, ProfileInterest


class ProfileApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(
            'member@example.com', 'ExamplePassword123!',
            status=AccountStatus.ACTIVE, email_verified_at=timezone.now(),
        )
        self.token = create_access_token(self.user)
        self.other = User.objects.create_user(
            'other@example.com', 'ExamplePassword123!',
            status=AccountStatus.ACTIVE, email_verified_at=timezone.now(),
        )
        self.university = University.objects.create(code='BUET', name='Bangladesh University of Engineering and Technology')
        self.other_university = University.objects.create(code='DU', name='University of Dhaka')
        self.discipline = Discipline.objects.create(code='CSE', name='Computer Science and Engineering')
        self.department = AcademicDepartment.objects.create(university=self.university, discipline=self.discipline, code='CSE', name='Computer Science and Engineering')

    def auth(self):
        return {'HTTP_AUTHORIZATION': 'Bearer ' + self.token}

    def patch(self, data, headers=None):
        return self.client.patch('/api/v1/profiles/me/', data=json.dumps(data), content_type='application/json', **(self.auth() if headers is None else headers))

    def image_upload(self, format='PNG'):
        image = Image.new('RGB', (100, 80), color=(200, 100, 40))
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return SimpleUploadedFile('avatar.png', buffer.getvalue(), content_type='image/png')

    def test_new_account_gets_profile_and_public_view_hides_email(self):
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
        own = self.client.get('/api/v1/profiles/me/', **self.auth())
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()['email'], 'member@example.com')
        self.assertIsNone(own.json()['display_name'])
        public = self.client.get(f'/api/v1/profiles/{self.user.id}/')
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()['display_name'], 'Fieldnotes member')
        self.assertNotIn('email', public.json())
        self.assertNotIn('privacy', public.json())
        self.assertEqual(self.client.get('/api/v1/profiles/me/').status_code, 401)

    def test_backfill_restores_profile_for_existing_account(self):
        Profile.objects.filter(user=self.user).delete()
        migration = import_module('profiles.migrations.0002_backfill_profiles')
        migration.backfill_profiles(apps, SimpleNamespace(connection=connection))
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_edit_profile_and_privacy_fields(self):
        response = self.patch({
            'display_name': '  Samir Das  ', 'bio': '  Data structures and notes.  ',
            'university_id': str(self.university.id), 'department_id': str(self.department.id),
            'interests': [' Algorithms ', 'Operating Systems'],
            'show_bio': False, 'show_university': False, 'show_interests': False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['display_name'], 'Samir Das')
        self.assertEqual(response.json()['interests'], ['Algorithms', 'Operating Systems'])
        self.assertEqual(response.json()['department']['code'], 'CSE')
        self.assertEqual(list(ProfileInterest.objects.filter(profile__user=self.user).values_list('position', flat=True)), [1, 2])
        public = self.client.get(f'/api/v1/profiles/{self.user.id}/').json()
        self.assertEqual(public['display_name'], 'Samir Das')
        self.assertIsNone(public['bio'])
        self.assertIsNone(public['university'])
        self.assertIsNone(public['department'])
        self.assertEqual(public['interests'], [])
        self.assertNotIn('email', public)

    def test_affiliation_must_match_and_failed_edit_is_atomic(self):
        initial = self.patch({'university_id': str(self.university.id), 'department_id': str(self.department.id), 'interests': ['Networks']})
        self.assertEqual(initial.status_code, 200)
        mismatch = self.patch({'university_id': str(self.other_university.id), 'interests': ['Changed']})
        self.assertEqual(mismatch.status_code, 400)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.university_id, self.university.id)
        self.assertEqual(list(profile.interests.values_list('label', flat=True)), ['Networks'])
        self.assertEqual(self.patch({'university_id': None}).status_code, 400)
        self.assertEqual(self.patch({'department_id': None, 'university_id': None}).status_code, 200)
        self.university.is_active = False
        self.university.save()
        self.assertEqual(self.patch({'university_id': str(self.university.id)}).status_code, 400)

    def test_interest_and_read_only_validation(self):
        self.assertEqual(self.patch({'interests': ['AI', ' ai ']}).status_code, 400)
        self.assertEqual(self.patch({'interests': [str(i) for i in range(11)]}).status_code, 400)
        self.assertEqual(self.patch({'interests': ['']}).status_code, 400)
        self.assertEqual(self.patch({'show_bio': 'false'}).status_code, 400)
        self.assertEqual(self.patch({'avatar_key': 'secret/path'}).status_code, 400)
        self.assertEqual(self.patch({'moderation_hidden_at': None}).status_code, 400)
        self.assertEqual(self.patch({'email': 'changed@example.com'}).status_code, 400)
        self.assertEqual(self.patch({'interests': ['AI', 'Data Science']}).status_code, 200)
        self.assertEqual(self.patch({'interests': []}).json()['interests'], [])

    def test_public_visibility_and_other_user_cannot_edit(self):
        pending = User.objects.create_user('pending@example.com', 'ExamplePassword123!')
        self.assertEqual(self.client.get(f'/api/v1/profiles/{pending.id}/').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/v1/profiles/{self.other.id}/', data='{}', content_type='application/json', **self.auth()).status_code, 405)
        profile = Profile.objects.get(user=self.user)
        profile.moderation_hidden_at = timezone.now()
        profile.save()
        self.assertEqual(self.client.get(f'/api/v1/profiles/{self.user.id}/').status_code, 404)
        self.assertTrue(self.client.get('/api/v1/profiles/me/', **self.auth()).json()['moderation_hidden'])
        self.user.status = AccountStatus.SUSPENDED
        self.user.save()
        self.assertEqual(self.client.get('/api/v1/profiles/me/', **self.auth()).status_code, 401)

    def test_avatar_upload_privacy_download_and_removal(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            response = self.client.post('/api/v1/profiles/me/avatar/', {'avatar': self.image_upload()}, **self.auth())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['avatar_url'], '/api/v1/profiles/me/avatar/')
            key = Profile.objects.get(user=self.user).avatar_key
            self.assertTrue(key.startswith(f'profile_avatars/{self.user.id}/'))
            self.assertNotIn('avatar_key', self.client.get(f'/api/v1/profiles/{self.user.id}/').json())
            public_avatar = self.client.get(f'/api/v1/profiles/{self.user.id}/avatar/')
            self.assertEqual(public_avatar.status_code, 200)
            self.assertEqual(public_avatar['Content-Type'], 'image/webp')
            public_avatar.close()
            own_avatar = self.client.get('/api/v1/profiles/me/avatar/', **self.auth())
            self.assertEqual(own_avatar.status_code, 200)
            own_avatar.close()
            self.assertEqual(self.patch({'show_avatar': False}).status_code, 200)
            self.assertIsNone(self.client.get(f'/api/v1/profiles/{self.user.id}/').json()['avatar_url'])
            self.assertEqual(self.client.get(f'/api/v1/profiles/{self.user.id}/avatar/').status_code, 404)
            self.assertEqual(self.client.get('/api/v1/profiles/me/avatar/', **self.auth()).status_code, 200)
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post('/api/v1/profiles/me/avatar/', {'avatar': self.image_upload()}, **self.auth()).status_code, 200)
            self.assertFalse(default_storage.exists(key))
            replacement_key = Profile.objects.get(user=self.user).avatar_key
            self.assertTrue(default_storage.exists(replacement_key))
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.delete('/api/v1/profiles/me/avatar/', **self.auth()).status_code, 200)
            self.assertIsNone(Profile.objects.get(user=self.user).avatar_key)
            self.assertFalse(default_storage.exists(replacement_key))
            self.assertEqual(self.client.get('/api/v1/profiles/me/avatar/', **self.auth()).status_code, 404)

    def test_avatar_rejects_invalid_image_and_missing_auth(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            self.assertEqual(self.client.post('/api/v1/profiles/me/avatar/', {'avatar': self.image_upload()}).status_code, 401)
            self.assertEqual(self.client.post('/api/v1/profiles/me/avatar/', {'avatar': SimpleUploadedFile('bad.png', b'not an image')}, **self.auth()).status_code, 400)
            self.assertEqual(self.client.post('/api/v1/profiles/me/avatar/', {'avatar': SimpleUploadedFile('huge.png', b'x' * (2 * 1024 * 1024 + 1))}, **self.auth()).status_code, 413)
            self.assertIsNone(Profile.objects.get(user=self.user).avatar_key)

    def test_no_profile_data_leak_on_malformed_requests(self):
        self.assertEqual(self.patch({'display_name': 'A\nB'}).status_code, 400)
        self.assertEqual(self.client.patch('/api/v1/profiles/me/', data='bad', content_type='application/json', **self.auth()).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/profiles/me/avatar/', **self.auth()).status_code, 404)
