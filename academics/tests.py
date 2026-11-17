import json

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import AccountStatus, User
from accounts.services import create_access_token

from .models import AcademicDepartment, Course, Discipline, Subject, University


class AcademicDirectoryTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.admin = User.objects.create_superuser('admin@example.com', 'ExamplePassword123!')
        self.student = User.objects.create_user(
            'student@example.com', 'ExamplePassword123!',
            status=AccountStatus.ACTIVE, email_verified_at=timezone.now(),
        )
        self.university = University.objects.create(code='BUET', name='Bangladesh University of Engineering and Technology')
        self.discipline = Discipline.objects.create(code='CSE', name='Computer Science and Engineering')
        self.department = AcademicDepartment.objects.create(
            university=self.university, discipline=self.discipline,
            code='CSE', name='Department of Computer Science and Engineering',
        )
        self.subject = Subject.objects.create(slug='algorithms', name='Algorithms')
        self.course = Course.objects.create(department=self.department, subject=self.subject, code='CSE220', name='Data Structures')

    def url(self, resource, item=None):
        return f'/api/v1/academics/{resource}/' + (f'{item.id}/' if item is not None else '')

    def write(self, method, path, data, user=None):
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + create_access_token(user)} if user else {}
        return getattr(self.client, method)(path, data=json.dumps(data), content_type='application/json', **headers)

    def test_public_directory_and_cascading_filters(self):
        response = self.client.get(self.url('universities'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['code'], 'BUET')
        response = self.client.get(self.url('departments'), {'university': str(self.university.id)})
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['discipline']['code'], 'CSE')
        response = self.client.get(self.url('courses'), {'department': str(self.department.id), 'subject': str(self.subject.id)})
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['university']['code'], 'BUET')
        self.assertEqual(self.client.get(self.url('courses'), {'university': str(self.university.id)}).json()['count'], 1)
        self.assertEqual(self.client.get(self.url('subjects'), {'q': 'algo'}).json()['count'], 1)
        self.assertEqual(self.client.get(self.url('courses'), {'q': 'CSE220'}).json()['count'], 1)
        self.assertEqual(self.client.get(self.url('courses'), {'offset': '1'}).json()['results'], [])
        self.assertEqual(self.client.get(self.url('courses', self.course)).json()['name'], 'Data Structures')

    def test_inactive_ancestors_hide_descendants_from_public_lookup(self):
        self.university.is_active = False
        self.university.save()
        self.assertEqual(self.client.get(self.url('universities')).json()['count'], 0)
        self.assertEqual(self.client.get(self.url('departments')).json()['count'], 0)
        self.assertEqual(self.client.get(self.url('courses')).json()['count'], 0)
        self.assertEqual(self.client.get(self.url('departments', self.department)).status_code, 404)
        self.assertEqual(self.client.get(self.url('courses', self.course)).status_code, 404)
        self.assertEqual(self.client.get(self.url('departments'), {'include_inactive': 'true'}).status_code, 401)
        response = self.client.get(self.url('departments') + '?include_inactive=true', HTTP_AUTHORIZATION='Bearer ' + create_access_token(self.admin))
        self.assertEqual(response.json()['count'], 1)

    def test_admin_create_update_and_unique_codes(self):
        response = self.write('post', self.url('universities'), {'code': ' du ', 'name': ' University of Dhaka '}, self.admin)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['code'], 'DU')
        du = University.objects.get(code='DU')
        response = self.write('patch', self.url('universities', du), {'name': 'University of Dhaka', 'is_active': False}, self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_active'])
        self.assertEqual(self.client.get(self.url('universities', du)).status_code, 404)
        self.assertEqual(self.write('post', self.url('universities'), {'code': 'buet', 'name': 'Duplicate'}, self.admin).status_code, 409)
        self.assertEqual(self.write('post', self.url('subjects'), {'slug': ' linear-algebra ', 'name': 'Linear Algebra'}, self.admin).json()['slug'], 'linear-algebra')

    def test_admin_can_create_department_and_course_with_active_parents(self):
        department = self.write('post', self.url('departments'), {
            'university_id': str(self.university.id), 'discipline_id': str(self.discipline.id),
            'code': 'EEE', 'name': 'Electrical Engineering',
        }, self.admin)
        self.assertEqual(department.status_code, 201)
        course = self.write('post', self.url('courses'), {
            'department_id': department.json()['id'], 'subject_id': str(self.subject.id),
            'code': 'EEE101', 'name': 'Introduction to Circuits',
        }, self.admin)
        self.assertEqual(course.status_code, 201)
        self.assertEqual(course.json()['department']['code'], 'EEE')
        self.university.is_active = False
        self.university.save()
        self.assertEqual(self.write('post', self.url('courses'), {
            'department_id': department.json()['id'], 'subject_id': str(self.subject.id),
            'code': 'EEE102', 'name': 'Another Course',
        }, self.admin).status_code, 400)

    def test_writes_require_admin_and_reject_invalid_data(self):
        payload = {'code': 'RU', 'name': 'Rajshahi University'}
        self.assertEqual(self.write('post', self.url('universities'), payload).status_code, 401)
        self.assertEqual(self.write('post', self.url('universities'), payload, self.student).status_code, 403)
        self.assertEqual(self.write('patch', self.url('universities', self.university), {'name': 'Changed'}, self.student).status_code, 403)
        self.assertEqual(self.write('post', self.url('universities'), {'code': 'BAD CODE', 'name': 'Bad'}, self.admin).status_code, 400)
        self.assertEqual(self.write('post', self.url('universities'), {'code': 'RU'}, self.admin).status_code, 400)
        self.assertEqual(self.write('post', self.url('universities'), {'code': 'RU', 'name': 'Rajshahi', 'id': 'override'}, self.admin).status_code, 400)
        self.assertEqual(self.write('patch', self.url('universities', self.university), {'is_active': 'false'}, self.admin).status_code, 400)
        self.assertEqual(self.write('post', self.url('courses'), {
            'department_id': 'not-a-uuid', 'subject_id': str(self.subject.id), 'code': 'X1', 'name': 'Bad',
        }, self.admin).status_code, 400)

    def test_query_validation_and_unknown_resources(self):
        self.assertEqual(self.client.get(self.url('universities'), {'limit': '101'}).status_code, 400)
        self.assertEqual(self.client.get(self.url('universities'), {'offset': '-1'}).status_code, 400)
        self.assertEqual(self.client.get(self.url('departments'), {'university': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(self.url('courses'), {'unknown': 'x'}).status_code, 400)
        self.assertEqual(self.client.get(self.url('nothing')).status_code, 404)
