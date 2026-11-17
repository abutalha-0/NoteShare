"""Note discussion with stable parent links and soft-deleted placeholders."""

from django.db import transaction
from django.utils import timezone

from .models import NoteComment
from .queries import public_note
from .validation import NoteError, parse_uuid, validate_comment_body


def serialize(comment):
    unavailable = comment.deleted_at is not None or comment.moderation_hidden_at is not None
    profile = getattr(comment.author, 'profile', None) if not unavailable else None
    return {
        'id': str(comment.id),
        'parent_comment_id': str(comment.parent_comment_id) if comment.parent_comment_id else None,
        'body': None if unavailable else comment.body,
        'author': None if unavailable else {
            'id': str(comment.author_id),
            'display_name': profile.display_name if profile and profile.display_name else 'Fieldnotes member',
        },
        'state': 'moderated' if comment.moderation_hidden_at else 'deleted' if comment.deleted_at else 'visible',
        'created_at': comment.created_at.isoformat(),
        'updated_at': comment.updated_at.isoformat(),
    }


def list_comments(note_id):
    note = public_note(note_id)
    return NoteComment.objects.filter(note=note).select_related('author', 'author__profile').order_by('created_at', 'id')


def create_comment(user, note_id, data):
    if not isinstance(data, dict) or set(data) - {'body', 'parent_comment_id'} or 'body' not in data:
        raise NoteError('A comment requires body and optional parent_comment_id.')
    body = validate_comment_body(data['body'])
    parent_id = parse_uuid(data['parent_comment_id'], 'parent_comment_id') if data.get('parent_comment_id') is not None else None
    with transaction.atomic():
        note = public_note(note_id)
        parent = None
        if parent_id:
            parent = NoteComment.objects.filter(pk=parent_id, note=note, moderation_hidden_at__isnull=True).first()
            if parent is None:
                raise NoteError('Parent comment must belong to this note and be available.')
        comment = NoteComment.objects.create(note=note, author=user, parent_comment=parent, body=body)
    return NoteComment.objects.select_related('author', 'author__profile').get(pk=comment.pk)


def own_comment(user, note_id, comment_id, lock=False):
    public_note(note_id)
    query = NoteComment.objects.select_for_update() if lock else NoteComment.objects
    comment = query.filter(pk=parse_uuid(comment_id, 'comment_id'), note_id=parse_uuid(note_id), author=user).first()
    if comment is None:
        raise NoteError('Comment not found.', 404)
    return comment


def update_comment(user, note_id, comment_id, data):
    if not isinstance(data, dict) or set(data) != {'body'}:
        raise NoteError('Only body may be changed.')
    body = validate_comment_body(data['body'])
    with transaction.atomic():
        comment = own_comment(user, note_id, comment_id, lock=True)
        if comment.deleted_at or comment.moderation_hidden_at:
            raise NoteError('This comment can no longer be edited.', 409)
        comment.body = body
        comment.save(update_fields=['body', 'updated_at'])
    return NoteComment.objects.select_related('author', 'author__profile').get(pk=comment.pk)


def delete_comment(user, note_id, comment_id):
    with transaction.atomic():
        comment = own_comment(user, note_id, comment_id, lock=True)
        if not comment.deleted_at:
            comment.deleted_at = timezone.now()
            comment.save(update_fields=['deleted_at', 'updated_at'])
    return serialize(comment)
