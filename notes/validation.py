"""Input rules for note metadata, links, and comments."""

import uuid
from urllib.parse import urlsplit

from academics.models import AcademicDepartment, Course, Subject

from .models import NoteKind


class NoteError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def parse_uuid(value, field='id'):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise NoteError(f'{field} must be a valid UUID.') from exc


def text(value, field, max_length, required=True, multiline=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise NoteError(f'{field} must be text.')
    result = value.strip()
    if (required and not result) or len(result) > max_length or any(ord(char) < 32 and (not multiline or char not in '\n\t') for char in result):
        raise NoteError(f'{field} must contain at most {max_length} valid characters' + (' and cannot be empty.' if required else '.'))
    return result or None


def validate_metadata(data, note=None, allow_empty=False):
    allowed = {'department_id', 'subject_id', 'course_id', 'kind', 'title', 'short_description', 'detail_description'}
    if not isinstance(data, dict):
        raise NoteError('A JSON object is required.')
    unknown = set(data) - allowed
    if unknown:
        raise NoteError('Unknown or read-only field: ' + sorted(unknown)[0])
    if note is None:
        required = {'department_id', 'subject_id', 'title', 'short_description'}
        missing = required - set(data)
        if missing:
            raise NoteError('Missing field: ' + sorted(missing)[0])
    elif not data and not allow_empty:
        raise NoteError('At least one field is required.')
    values = {}
    for field, value in data.items():
        if field in {'department_id', 'subject_id'}:
            values[field] = parse_uuid(value, field)
        elif field == 'course_id':
            values[field] = parse_uuid(value, field) if value is not None else None
        elif field == 'kind':
            if value is not None and value not in NoteKind.values:
                raise NoteError('kind is invalid.')
            values[field] = value
        elif field == 'title':
            values[field] = text(value, field, 180)
        elif field == 'short_description':
            values[field] = text(value, field, 280)
        elif field == 'detail_description':
            values[field] = text(value, field, 10_000, required=False, multiline=True)
    department_id = values.get('department_id', note.department_id if note else None)
    subject_id = values.get('subject_id', note.subject_id if note else None)
    course_id = values.get('course_id', note.course_id if note else None)
    department = AcademicDepartment.objects.filter(
        pk=department_id, is_active=True, university__is_active=True, discipline__is_active=True,
    ).first()
    if department is None:
        raise NoteError('Select an active department.')
    if not Subject.objects.filter(pk=subject_id, is_active=True).exists():
        raise NoteError('Select an active subject.')
    if course_id and not Course.objects.filter(
        pk=course_id, department_id=department_id, subject_id=subject_id, is_active=True,
    ).exists():
        raise NoteError('Course must be active and match the department and subject.')
    return values


def validate_resources(data):
    if not isinstance(data, list) or len(data) > 5:
        raise NoteError('resources must be a list of at most five links.')
    result = []
    for resource in data:
        if not isinstance(resource, dict) or set(resource) != {'label', 'url'}:
            raise NoteError('Each resource requires only label and url.')
        label = text(resource['label'], 'label', 160)
        url = text(resource['url'], 'url', 2048)
        if '\\' in url or any(char.isspace() for char in url):
            raise NoteError('Resource URL contains invalid characters.')
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            parsed.port
        except ValueError as exc:
            raise NoteError('Resource URL is invalid.') from exc
        if parsed.scheme.lower() not in {'http', 'https'} or not hostname or '@' in parsed.netloc or parsed.netloc.endswith(':'):
            raise NoteError('Resource URL must be an HTTP or HTTPS link without credentials.')
        result.append((label, url))
    return result


def validate_comment_body(value):
    return text(value, 'body', 5000, multiline=True)
