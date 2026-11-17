"""Visibility and compact response shapes for notes."""

from django.db.models import Count, Q
from django.urls import reverse

from accounts.models import AccountStatus

from .models import Note, NoteLike, NoteStatus, SavedNote
from .validation import NoteError, parse_uuid


def visible_notes():
    return Note.objects.filter(
        status=NoteStatus.PUBLISHED,
        published_at__isnull=False,
        moderation_hidden_at__isnull=True,
        deleted_at__isnull=True,
        publisher__status=AccountStatus.ACTIVE,
        publisher__email_verified_at__isnull=False,
        pdf_asset__isnull=False,
    )


def enriched(query):
    return query.select_related(
        'publisher', 'publisher__profile', 'department', 'department__university', 'subject', 'course', 'pdf_asset',
    ).prefetch_related('resources').annotate(like_count=Count('likes__user_id', distinct=True))


def note_for_read(note_id, user=None):
    identifier = parse_uuid(note_id)
    note = enriched(visible_notes()).filter(pk=identifier).first()
    if note is None and user is not None:
        note = enriched(Note.objects.filter(pk=identifier, publisher=user, deleted_at__isnull=True)).first()
    if note is None:
        raise NoteError('Note not found.', 404)
    return note


def public_note(note_id):
    note = enriched(visible_notes()).filter(pk=parse_uuid(note_id)).first()
    if note is None:
        raise NoteError('Note not found.', 404)
    return note


def viewer_states(user, notes):
    if user is None or not notes:
        return set(), set()
    ids = [note.id for note in notes]
    liked = set(NoteLike.objects.filter(user=user, note_id__in=ids).values_list('note_id', flat=True))
    saved = set(SavedNote.objects.filter(user=user, note_id__in=ids).values_list('note_id', flat=True))
    return liked, saved


def card(note, liked=False, saved=False):
    profile = getattr(note.publisher, 'profile', None)
    return {
        'id': str(note.id),
        'title': note.title,
        'short_description': note.short_description,
        'kind': note.kind,
        'published_at': note.published_at.isoformat() if note.published_at else None,
        'subject': {'id': str(note.subject_id), 'name': note.subject.name, 'slug': note.subject.slug},
        'department': {'id': str(note.department_id), 'code': note.department.code, 'name': note.department.name},
        'university': {'id': str(note.department.university_id), 'code': note.department.university.code, 'name': note.department.university.name},
        'publisher': {'id': str(note.publisher_id), 'display_name': profile.display_name if profile and profile.display_name else 'Fieldnotes member'},
        'like_count': note.like_count if hasattr(note, 'like_count') else note.likes.count(),
        'liked': liked,
        'saved': saved,
    }


def detail(note, user=None):
    liked, saved = viewer_states(user, [note])
    data = card(note, note.id in liked, note.id in saved)
    data.update({
        'detail_description': note.detail_description,
        'course': {'id': str(note.course_id), 'code': note.course.code, 'name': note.course.name} if note.course_id else None,
        'resources': [{'id': str(resource.id), 'position': resource.position, 'label': resource.label, 'url': resource.url} for resource in note.resources.all()],
        'pdf': {'url': reverse('note_pdf', kwargs={'note_id': note.id}), 'filename': note.pdf_asset.original_filename, 'page_count': note.pdf_asset.page_count} if hasattr(note, 'pdf_asset') else None,
        'created_at': note.created_at.isoformat(),
        'updated_at': note.updated_at.isoformat(),
    })
    if user is not None and note.publisher_id == user.id:
        data['owner'] = {'status': note.status, 'moderation_hidden': note.moderation_hidden_at is not None}
    return data


def explore(params):
    allowed = {'q', 'university', 'department', 'subject', 'course', 'publisher', 'kind', 'order', 'limit', 'offset'}
    unknown = set(params) - allowed
    if unknown:
        raise NoteError('Unknown query parameter: ' + sorted(unknown)[0])
    query = visible_notes()
    for key, field in (
        ('university', 'department__university_id'), ('department', 'department_id'),
        ('subject', 'subject_id'), ('course', 'course_id'), ('publisher', 'publisher_id'),
    ):
        if key in params:
            query = query.filter(**{field: parse_uuid(params[key], key)})
    if 'kind' in params:
        from .models import NoteKind
        if params['kind'] not in NoteKind.values:
            raise NoteError('kind is invalid.')
        query = query.filter(kind=params['kind'])
    search = params.get('q', '').strip()
    if len(search) > 100:
        raise NoteError('Search query is too long.')
    if search:
        query = query.filter(Q(title__icontains=search) | Q(short_description__icontains=search) | Q(detail_description__icontains=search))
    order = params.get('order', 'recent')
    if order == 'recent':
        query = enriched(query).order_by('-published_at', '-created_at', 'id')
    elif order == 'liked':
        query = enriched(query).order_by('-like_count', '-published_at', 'id')
    else:
        raise NoteError('order must be recent or liked.')
    return query
