import io
import json
import tempfile

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from accounts.models import AccountStatus, User
from accounts.services import create_access_token
from academics.models import AcademicDepartment, Course, Discipline, Subject, University

from .models import Note, NoteComment, NotePdfAsset, NoteResource, NoteStatus


class NoteApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.author = User.objects.create_user('author@example.com', 'ExamplePassword123!', status=AccountStatus.ACTIVE, email_verified_at=timezone.now())
        self.reader = User.objects.create_user('reader@example.com', 'ExamplePassword123!', status=AccountStatus.ACTIVE, email_verified_at=timezone.now())
        self.university = University.objects.create(code='BUET', name='Bangladesh University of Engineering and Technology')
        self.discipline = Discipline.objects.create(code='CSE', name='Computer Science and Engineering')
        self.department = AcademicDepartment.objects.create(university=self.university, discipline=self.discipline, code='CSE', name='Computer Science and Engineering')
        self.subject = Subject.objects.create(slug='algorithms', name='Algorithms')
        self.course = Course.objects.create(department=self.department, subject=self.subject, code='CSE220', name='Data Structures')

    def auth(self, user):
        return {'HTTP_AUTHORIZATION': 'Bearer ' + create_access_token(user)}

    def request_json(self, method, path, data, user=None):
        return getattr(self.client, method)(
            path, data=json.dumps(data), content_type='application/json',
            **(self.auth(user) if user else {}),
        )

    def metadata(self, **extra):
        return {
            'department_id': str(self.department.id), 'subject_id': str(self.subject.id),
            'course_id': str(self.course.id), 'kind': 'lecture_notes',
            'title': 'Trees, Graphs & Heaps', 'short_description': 'A quick route through the structures behind fast algorithms.',
            **extra,
        }

    def draft(self, **extra):
        response = self.request_json('post', '/api/v1/notes/me/', self.metadata(**extra), self.author)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']

    def pdf_upload(self, filename='guide.pdf'):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buffer = io.BytesIO()
        writer.write(buffer)
        return SimpleUploadedFile(filename, buffer.getvalue(), content_type='application/pdf')

    def publish(self, note_id):
        response = self.client.post(f'/api/v1/notes/me/{note_id}/publish/', **self.auth(self.author))
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_draft_pdf_publish_reader_archive_and_owner_visibility(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            note_id = self.draft()
            self.assertEqual(self.client.get(f'/api/v1/notes/{note_id}/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/notes/{note_id}/pdf/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/notes/me/{note_id}/', **self.auth(self.reader)).status_code, 404)
            self.assertEqual(self.client.post(f'/api/v1/notes/me/{note_id}/publish/', **self.auth(self.author)).status_code, 409)
            uploaded = self.client.post(f'/api/v1/notes/me/{note_id}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author))
            self.assertEqual(uploaded.status_code, 200, uploaded.content)
            self.assertEqual(uploaded.json()['pdf']['page_count'], 1)
            self.publish(note_id)
            public = self.client.get(f'/api/v1/notes/{note_id}/')
            self.assertEqual(public.status_code, 200)
            self.assertEqual(public.json()['title'], 'Trees, Graphs & Heaps')
            self.assertEqual(public.json()['pdf']['page_count'], 1)
            self.assertNotIn('storage_key', str(public.content))
            inline = self.client.get(f'/api/v1/notes/{note_id}/pdf/')
            self.assertEqual(inline.status_code, 200)
            self.assertEqual(inline['Content-Type'], 'application/pdf')
            self.assertIn('inline', inline['Content-Disposition'])
            inline.close()
            download = self.client.get(f'/api/v1/notes/{note_id}/pdf/?download=true')
            self.assertIn('attachment', download['Content-Disposition'])
            download.close()
            self.assertEqual(self.client.post(f'/api/v1/notes/me/{note_id}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author)).status_code, 409)
            archived = self.client.post(f'/api/v1/notes/me/{note_id}/archive/', **self.auth(self.author))
            self.assertEqual(archived.json()['owner']['status'], NoteStatus.ARCHIVED)
            self.assertEqual(self.client.get(f'/api/v1/notes/{note_id}/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/notes/me/{note_id}/', **self.auth(self.author)).status_code, 200)

    def test_metadata_validation_academic_consistency_and_owner_edits(self):
        self.assertEqual(self.request_json('post', '/api/v1/notes/me/', self.metadata(), None).status_code, 401)
        note_id = self.draft()
        other_subject = Subject.objects.create(slug='physics', name='Physics')
        self.assertEqual(self.request_json('patch', f'/api/v1/notes/me/{note_id}/', {'subject_id': str(other_subject.id)}, self.author).status_code, 400)
        self.assertEqual(self.request_json('patch', f'/api/v1/notes/me/{note_id}/', {'title': ' Updated title '}, self.reader).status_code, 404)
        self.assertEqual(self.request_json('patch', f'/api/v1/notes/me/{note_id}/', {'status': 'published'}, self.author).status_code, 400)
        self.assertEqual(self.request_json('patch', f'/api/v1/notes/me/{note_id}/', {'title': ' Updated title '}, self.author).json()['title'], 'Updated title')
        self.assertEqual(self.request_json('post', '/api/v1/notes/me/', self.metadata(title=''), self.author).status_code, 400)
        self.assertEqual(self.request_json('post', '/api/v1/notes/me/', self.metadata(kind='wrong'), self.author).status_code, 400)
        self.assertEqual(self.request_json('post', '/api/v1/notes/me/', self.metadata(course_id='invalid'), self.author).status_code, 400)
        self.department.is_active = False
        self.department.save()
        self.assertEqual(self.client.post(f'/api/v1/notes/me/{note_id}/publish/', **self.auth(self.author)).status_code, 400)

    def test_resources_limit_safe_urls_and_atomic_replacement(self):
        note_id = self.draft()
        path = f'/api/v1/notes/me/{note_id}/resources/'
        good = {'resources': [{'label': 'MIT OpenCourseWare', 'url': 'https://ocw.mit.edu/algorithms'}]}
        self.assertEqual(self.request_json('put', path, good, self.author).status_code, 200)
        self.assertEqual(NoteResource.objects.filter(note_id=note_id).count(), 1)
        self.assertEqual(self.request_json('put', path, {'resources': [{'label': 'Bad', 'url': 'javascript:alert(1)'}]}, self.author).status_code, 400)
        self.assertEqual(self.request_json('put', path, {'resources': [{'label': 'Bad', 'url': 'https://user:pass@example.com'}]}, self.author).status_code, 400)
        self.assertEqual(self.request_json('put', path, {'resources': [{'label': 'One', 'url': 'https://example.com'}] * 6}, self.author).status_code, 400)
        self.assertEqual(NoteResource.objects.filter(note_id=note_id).count(), 1)
        five = {'resources': [{'label': str(i), 'url': f'https://example.com/{i}'} for i in range(5)]}
        self.assertEqual(self.request_json('put', path, five, self.author).status_code, 200)
        self.assertEqual(list(NoteResource.objects.filter(note_id=note_id).values_list('position', flat=True)), [1, 2, 3, 4, 5])
        self.assertEqual(self.request_json('put', path, {'resources': []}, self.reader).status_code, 404)

    def test_explore_filters_search_order_likes_and_saved_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            first = self.draft(title='Graph Search')
            second = self.draft(title='Tree Traversal')
            for note_id in (first, second):
                self.client.post(f'/api/v1/notes/me/{note_id}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author))
                self.publish(note_id)
            self.assertEqual(self.client.get('/api/v1/notes/').json()['count'], 2)
            self.assertEqual(self.client.get('/api/v1/notes/', {'q': 'graph'}).json()['count'], 1)
            self.assertEqual(self.client.get('/api/v1/notes/', {'university': str(self.university.id), 'subject': str(self.subject.id)}).json()['count'], 2)
            self.assertEqual(self.client.get('/api/v1/notes/', {'department': str(self.department.id), 'course': str(self.course.id)}).json()['count'], 2)
            self.assertEqual(self.client.get('/api/v1/notes/', {'publisher': str(self.author.id)}).json()['count'], 2)
            self.assertEqual(self.client.get('/api/v1/notes/', {'publisher': str(self.reader.id)}).json()['count'], 0)
            self.assertEqual(self.client.get('/api/v1/notes/', {'limit': 1}).json()['count'], 2)
            self.assertEqual(self.client.get('/api/v1/notes/', {'limit': 0}).status_code, 400)
            self.assertEqual(self.client.get('/api/v1/notes/', {'university': 'bad'}).status_code, 400)
            like_path = f'/api/v1/notes/{first}/like/'
            self.assertEqual(self.client.post(like_path, **self.auth(self.reader)).json()['like_count'], 1)
            self.assertEqual(self.client.post(like_path, **self.auth(self.reader)).json()['like_count'], 1)
            self.assertEqual(self.client.get('/api/v1/notes/', {'order': 'liked'}).json()['results'][0]['id'], first)
            self.assertEqual(self.client.delete(like_path, **self.auth(self.reader)).json()['like_count'], 0)
            save_path = f'/api/v1/notes/{first}/save/'
            self.assertEqual(self.client.post(save_path, **self.auth(self.reader)).json()['saved'], True)
            self.assertEqual(self.client.post(save_path, **self.auth(self.reader)).status_code, 200)
            saved = self.client.get('/api/v1/notes/me/saved/', **self.auth(self.reader)).json()['results'][0]
            self.assertTrue(saved['available'])
            self.assertEqual(saved['note']['title'], 'Graph Search')
            self.client.post(f'/api/v1/notes/me/{first}/archive/', **self.auth(self.author))
            saved = self.client.get('/api/v1/notes/me/saved/', **self.auth(self.reader)).json()['results'][0]
            self.assertFalse(saved['available'])
            self.assertIsNone(saved['note'])
            self.assertEqual(self.client.post(like_path, **self.auth(self.reader)).status_code, 404)
            self.assertEqual(self.client.delete(save_path, **self.auth(self.reader)).status_code, 200)
            self.assertEqual(self.client.get('/api/v1/notes/me/saved/', **self.auth(self.reader)).json()['count'], 0)

    def test_comments_parent_links_edit_and_soft_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            note_id = self.draft()
            self.client.post(f'/api/v1/notes/me/{note_id}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author))
            self.publish(note_id)
            path = f'/api/v1/notes/{note_id}/comments/'
            root = self.request_json('post', path, {'body': 'What about heaps?'}, self.reader)
            self.assertEqual(root.status_code, 201)
            root_id = root.json()['id']
            reply = self.request_json('post', path, {'body': 'See section two.', 'parent_comment_id': root_id}, self.author)
            self.assertEqual(reply.status_code, 201)
            self.assertEqual(reply.json()['parent_comment_id'], root_id)
            other_note = self.draft(title='Another note')
            self.client.post(f'/api/v1/notes/me/{other_note}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author))
            self.publish(other_note)
            self.assertEqual(self.request_json('post', f'/api/v1/notes/{other_note}/comments/', {'body': 'Wrong parent', 'parent_comment_id': root_id}, self.reader).status_code, 400)
            self.assertEqual(self.request_json('patch', f'{path}{root_id}/', {'body': 'Changed'}, self.author).status_code, 404)
            changed = self.request_json('patch', f'{path}{root_id}/', {'body': 'Updated question'}, self.reader)
            self.assertEqual(changed.json()['body'], 'Updated question')
            self.assertEqual(self.client.delete(f'{path}{root_id}/', **self.auth(self.reader)).json()['state'], 'deleted')
            listed = self.client.get(path).json()['results']
            self.assertEqual(listed[0]['state'], 'deleted')
            self.assertIsNone(listed[0]['author'])
            self.assertEqual(listed[1]['parent_comment_id'], root_id)
            self.assertEqual(self.request_json('patch', f'{path}{root_id}/', {'body': 'Again'}, self.reader).status_code, 409)

    def test_pdf_validation_and_replacement_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            note_id = self.draft()
            path = f'/api/v1/notes/me/{note_id}/pdf/'
            self.assertEqual(self.client.post(path, {'pdf': SimpleUploadedFile('bad.pdf', b'%PDF-not-valid')}, **self.auth(self.author)).status_code, 400)
            self.assertEqual(self.client.post(path, {'pdf': self.pdf_upload()}, **self.auth(self.reader)).status_code, 404)
            self.assertEqual(self.client.post(path, {'pdf': self.pdf_upload()}, **self.auth(self.author)).status_code, 200)
            old_key = NotePdfAsset.objects.get(note_id=note_id).storage_key
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(path, {'pdf': self.pdf_upload('revision.pdf')}, **self.auth(self.author)).status_code, 200)
            self.assertFalse(default_storage.exists(old_key))
            new_key = NotePdfAsset.objects.get(note_id=note_id).storage_key
            self.assertTrue(default_storage.exists(new_key))
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.delete(path, **self.auth(self.author)).status_code, 200)
            self.assertFalse(default_storage.exists(new_key))
            self.assertFalse(NotePdfAsset.objects.filter(note_id=note_id).exists())

    def test_soft_deletion_and_suspended_publisher_hide_note(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            note_id = self.draft()
            self.client.post(f'/api/v1/notes/me/{note_id}/pdf/', {'pdf': self.pdf_upload()}, **self.auth(self.author))
            self.publish(note_id)
            self.author.status = AccountStatus.SUSPENDED
            self.author.save()
            self.assertEqual(self.client.get(f'/api/v1/notes/{note_id}/').status_code, 404)
            self.author.status = AccountStatus.ACTIVE
            self.author.save()
            self.assertEqual(self.client.delete(f'/api/v1/notes/me/{note_id}/', **self.auth(self.author)).status_code, 200)
            self.assertEqual(self.client.get(f'/api/v1/notes/{note_id}/').status_code, 404)
            self.assertEqual(self.client.get('/api/v1/notes/me/', **self.auth(self.author)).json()['count'], 0)

    def test_database_rejects_sixth_resource_position_and_undated_publication(self):
        note_id = self.draft()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NoteResource.objects.create(note_id=note_id, position=6, label='Extra', url='https://example.com')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Note.objects.filter(pk=note_id).update(status=NoteStatus.PUBLISHED, published_at=None)
