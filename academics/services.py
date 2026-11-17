"""Validation and queries for the shared academic directory."""

import re
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from accounts.authentication import authenticated_user

from .models import AcademicDepartment, Course, Discipline, Subject, University


class DirectoryError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


RESOURCES = {
    'universities': University,
    'disciplines': Discipline,
    'departments': AcademicDepartment,
    'subjects': Subject,
    'courses': Course,
}
FIELDS = {
    'universities': {'code', 'name', 'is_active'},
    'disciplines': {'code', 'name', 'is_active'},
    'departments': {'university_id', 'discipline_id', 'code', 'name', 'is_active'},
    'subjects': {'slug', 'name', 'is_active'},
    'courses': {'department_id', 'subject_id', 'code', 'name', 'is_active'},
}
RELATIONS = {
    'university_id': University,
    'discipline_id': Discipline,
    'department_id': AcademicDepartment,
    'subject_id': Subject,
}


def resource_model(resource):
    try:
        return RESOURCES[resource]
    except KeyError as exc:
        raise DirectoryError('Academic resource not found.', 404) from exc


def parse_uuid(value, field='id'):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise DirectoryError(f'{field} must be a valid UUID.') from exc


def administrator(request):
    user = authenticated_user(request)
    if not user.is_superuser:
        raise DirectoryError('Administrator access is required.', 403)
    return user


def visible_queryset(resource, include_inactive=False):
    model = resource_model(resource)
    query = model.objects.all()
    if not include_inactive:
        query = query.filter(is_active=True)
        if resource == 'departments':
            query = query.filter(university__is_active=True, discipline__is_active=True)
        elif resource == 'courses':
            query = query.filter(
                department__is_active=True,
                department__university__is_active=True,
                department__discipline__is_active=True,
                subject__is_active=True,
            )
    if resource == 'departments':
        query = query.select_related('university', 'discipline')
    elif resource == 'courses':
        query = query.select_related('department', 'department__university', 'subject')
    return query


def filter_queryset(resource, params, include_inactive=False):
    query = visible_queryset(resource, include_inactive)
    allowed = {'q', 'limit', 'offset', 'include_inactive'}
    filters = {
        'departments': {'university': 'university_id', 'discipline': 'discipline_id'},
        'courses': {'department': 'department_id', 'subject': 'subject_id', 'university': 'department__university_id'},
    }.get(resource, {})
    unknown = set(params) - allowed - set(filters)
    if unknown:
        raise DirectoryError('Unknown query parameter: ' + sorted(unknown)[0])
    for key, lookup in filters.items():
        if key in params:
            query = query.filter(**{lookup: parse_uuid(params[key], key)})
    search = params.get('q', '').strip()
    if len(search) > 100:
        raise DirectoryError('Search query is too long.')
    if search:
        match = Q(name__icontains=search)
        if resource == 'subjects':
            match |= Q(slug__icontains=search)
        else:
            match |= Q(code__icontains=search)
        query = query.filter(match)
    return query


def serialize(resource, item):
    data = {'id': str(item.id), 'name': item.name, 'is_active': item.is_active}
    if resource == 'subjects':
        data['slug'] = item.slug
    else:
        data['code'] = item.code
    if resource == 'departments':
        data['university'] = {'id': str(item.university_id), 'code': item.university.code, 'name': item.university.name}
        data['discipline'] = {'id': str(item.discipline_id), 'code': item.discipline.code, 'name': item.discipline.name}
    elif resource == 'courses':
        data['department'] = {'id': str(item.department_id), 'code': item.department.code, 'name': item.department.name}
        data['subject'] = {'id': str(item.subject_id), 'slug': item.subject.slug, 'name': item.subject.name}
        data['university'] = {'id': str(item.department.university_id), 'code': item.department.university.code, 'name': item.department.university.name}
    return data


def get_item(resource, item_id, include_inactive=False):
    item = visible_queryset(resource, include_inactive).filter(pk=parse_uuid(item_id)).first()
    if item is None:
        raise DirectoryError('Academic record not found.', 404)
    return item


def normalize_text(value, field, max_length):
    if not isinstance(value, str):
        raise DirectoryError(f'{field} must be text.')
    result = value.strip()
    if not result or len(result) > max_length or any(ord(char) < 32 for char in result):
        raise DirectoryError(f'{field} must contain 1 to {max_length} printable characters.')
    return result


def normalize_code(value, max_length):
    code = normalize_text(value, 'code', max_length).upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]*', code):
        raise DirectoryError('code may contain letters, numbers, dots, underscores and hyphens.')
    return code


def normalize_slug(value):
    slug = normalize_text(value, 'slug', 100).lower()
    if not re.fullmatch(r'[a-z0-9]+(?:[-_][a-z0-9]+)*', slug):
        raise DirectoryError('slug must use lowercase letters, numbers, hyphens or underscores.')
    return slug


def save_item(resource, data, item=None):
    model = resource_model(resource)
    if not isinstance(data, dict):
        raise DirectoryError('A JSON object is required.')
    unknown = set(data) - FIELDS[resource]
    if unknown:
        raise DirectoryError('Unknown field: ' + sorted(unknown)[0])
    if not data:
        raise DirectoryError('At least one field is required.')
    if item is None:
        missing = FIELDS[resource] - {'is_active'} - set(data)
        if missing:
            raise DirectoryError('Missing field: ' + sorted(missing)[0])
        item = model()
    for field, value in data.items():
        if field == 'is_active':
            if not isinstance(value, bool):
                raise DirectoryError('is_active must be a boolean.')
            item.is_active = value
        elif field == 'code':
            item.code = normalize_code(value, model._meta.get_field('code').max_length)
        elif field == 'slug':
            item.slug = normalize_slug(value)
        elif field == 'name':
            item.name = normalize_text(value, 'name', model._meta.get_field('name').max_length)
        elif field in RELATIONS:
            parent = RELATIONS[field].objects.filter(pk=parse_uuid(value, field)).first()
            if parent is None:
                raise DirectoryError(f'{field} does not exist.')
            setattr(item, field, parent.id)
    if item.is_active and resource == 'departments':
        if not University.objects.filter(pk=item.university_id, is_active=True).exists() or not Discipline.objects.filter(pk=item.discipline_id, is_active=True).exists():
            raise DirectoryError('An active department requires an active university and discipline.')
    if item.is_active and resource == 'courses':
        if not visible_queryset('departments').filter(pk=item.department_id).exists() or not Subject.objects.filter(pk=item.subject_id, is_active=True).exists():
            raise DirectoryError('An active course requires an active department and subject.')
    try:
        with transaction.atomic():
            item.full_clean()
            item.save()
    except (ValidationError, IntegrityError) as exc:
        raise DirectoryError('Academic record conflicts with existing data or is invalid.', 409) from exc
    return get_item(resource, item.id, include_inactive=True)
