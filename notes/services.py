"""Transactional note authoring, publication, resources, and engagement."""

import hashlib
import io
import logging
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import Note, NoteLike, NotePdfAsset, NoteResource, NoteStatus, SavedNote
from .queries import public_note
from .validation import NoteError, parse_uuid, validate_metadata, validate_resources


logger = logging.getLogger(__name__)
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500


def owned_note(user, note_id, lock=False):
    query = Note.objects.select_for_update() if lock else Note.objects
    note = query.filter(pk=parse_uuid(note_id), publisher=user, deleted_at__isnull=True).first()
    if note is None:
        raise NoteError('Note not found.', 404)
    return note


def editable(note):
    if note.status not in {NoteStatus.DRAFT, NoteStatus.PUBLISHED} or note.moderation_hidden_at:
        raise NoteError('This note cannot be edited in its current state.', 409)


def create_note(user, data):
    values = validate_metadata(data)
    return Note.objects.create(publisher=user, **values)


def update_note(user, note_id, data):
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        editable(note)
        values = validate_metadata(data, note)
        for field, value in values.items():
            setattr(note, field, value)
        note.save()
    return note


def publish_note(user, note_id):
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        if note.status != NoteStatus.DRAFT or note.moderation_hidden_at:
            raise NoteError('Only an unrestricted draft can be published.', 409)
        validate_metadata({}, note, allow_empty=True)
        asset = NotePdfAsset.objects.filter(note=note).first()
        if asset is None or not default_storage.exists(asset.storage_key):
            raise NoteError('Upload a PDF before publishing.', 409)
        note.status = NoteStatus.PUBLISHED
        note.published_at = timezone.now()
        note.save(update_fields=['status', 'published_at', 'updated_at'])
    return note


def archive_note(user, note_id):
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        if note.status != NoteStatus.PUBLISHED:
            raise NoteError('Only a published note can be archived.', 409)
        note.status = NoteStatus.ARCHIVED
        note.save(update_fields=['status', 'updated_at'])
    return note


def delete_note(user, note_id):
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        note.deleted_at = timezone.now()
        note.save(update_fields=['deleted_at', 'updated_at'])


def replace_resources(user, note_id, data):
    resources = validate_resources(data)
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        editable(note)
        note.resources.all().delete()
        NoteResource.objects.bulk_create([
            NoteResource(note=note, position=position, label=label, url=url)
            for position, (label, url) in enumerate(resources, 1)
        ])
        note.save(update_fields=['updated_at'])
    return note


def prepare_pdf(upload):
    if upload is None:
        raise NoteError('A PDF file is required.')
    if upload.size > MAX_PDF_BYTES:
        raise NoteError('PDF must be 20 MB or smaller.', 413)
    upload.seek(0)
    data = upload.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise NoteError('PDF must be 20 MB or smaller.', 413)
    if not data.startswith(b'%PDF-'):
        raise NoteError('File is not a PDF.')
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise NoteError('Encrypted PDFs are not supported.')
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, OSError, TypeError) as exc:
        raise NoteError('PDF is invalid or unreadable.') from exc
    if page_count < 1 or page_count > MAX_PDF_PAGES:
        raise NoteError('PDF must contain 1 to 500 pages.')
    filename = upload.name.replace('\\', '/').split('/')[-1].strip()
    if not filename.lower().endswith('.pdf') or len(filename) > 255 or any(ord(char) < 32 for char in filename):
        raise NoteError('PDF filename is invalid.')
    return data, page_count, filename


def delete_file_safely(key):
    if key:
        try:
            default_storage.delete(key)
        except OSError:
            logger.exception('Could not remove an old note PDF')


def upload_pdf(user, note_id, upload):
    data, pages, filename = prepare_pdf(upload)
    note = owned_note(user, note_id)
    if note.status != NoteStatus.DRAFT or note.moderation_hidden_at:
        raise NoteError('PDFs can only be changed on unrestricted drafts.', 409)
    key = default_storage.save(f'note_pdfs/{user.id}/{note.id}/{uuid.uuid4().hex}.pdf', ContentFile(data))
    try:
        with transaction.atomic():
            note = owned_note(user, note_id, lock=True)
            if note.status != NoteStatus.DRAFT or note.moderation_hidden_at:
                raise NoteError('PDFs can only be changed on unrestricted drafts.', 409)
            previous = NotePdfAsset.objects.filter(note=note).first()
            previous_key = previous.storage_key if previous else None
            NotePdfAsset.objects.update_or_create(
                note=note,
                defaults={
                    'storage_key': key, 'original_filename': filename, 'byte_size': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(), 'page_count': pages, 'uploaded_at': timezone.now(),
                },
            )
            note.save(update_fields=['updated_at'])
            if previous_key:
                transaction.on_commit(lambda: delete_file_safely(previous_key))
    except Exception:
        delete_file_safely(key)
        raise
    return NotePdfAsset.objects.get(note=note)


def remove_pdf(user, note_id):
    with transaction.atomic():
        note = owned_note(user, note_id, lock=True)
        if note.status != NoteStatus.DRAFT:
            raise NoteError('Published PDFs cannot be removed.', 409)
        asset = NotePdfAsset.objects.filter(note=note).first()
        if asset:
            key = asset.storage_key
            asset.delete()
            note.save(update_fields=['updated_at'])
            transaction.on_commit(lambda: delete_file_safely(key))


def set_like(user, note_id, liked):
    note = public_note(note_id)
    if liked:
        try:
            NoteLike.objects.get_or_create(user=user, note=note)
        except IntegrityError:
            pass
    else:
        NoteLike.objects.filter(user=user, note=note).delete()
    return {'liked': liked, 'like_count': NoteLike.objects.filter(note=note).count()}


def set_saved(user, note_id, saved):
    if saved:
        note = public_note(note_id)
        try:
            SavedNote.objects.get_or_create(user=user, note=note)
        except IntegrityError:
            pass
    else:
        SavedNote.objects.filter(user=user, note_id=parse_uuid(note_id)).delete()
    return {'saved': saved}
