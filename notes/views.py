"""JSON and file endpoints for notes."""

import json
from functools import wraps

from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.authentication import authenticated_user
from accounts.services import AuthError

from . import comments, queries, services
from .models import Note, NotePdfAsset, SavedNote
from .validation import NoteError


def api(handler):
    @wraps(handler)
    def wrapped(request, *args, **kwargs):
        try:
            response = handler(request, *args, **kwargs)
        except (NoteError, AuthError) as exc:
            response = JsonResponse({'error': str(exc)}, status=exc.status)
        response['Cache-Control'] = 'no-store'
        return response
    return csrf_exempt(wrapped)


def body(request):
    if len(request.body) > 65536:
        raise NoteError('Request body is too large.', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise NoteError('Valid JSON is required.') from exc
    return data


def optional_user(request):
    return authenticated_user(request) if request.headers.get('Authorization') else None


def page(request):
    try:
        limit = int(request.GET.get('limit', '30'))
        offset = int(request.GET.get('offset', '0'))
    except ValueError as exc:
        raise NoteError('limit and offset must be integers.') from exc
    if not 1 <= limit <= 100 or offset < 0 or offset > 1_000_000:
        raise NoteError('limit or offset is outside the allowed range.')
    return limit, offset


@require_http_methods(['GET'])
@api
def explore(request):
    user = optional_user(request)
    query = queries.explore(request.GET)
    limit, offset = page(request)
    total = query.count()
    notes = list(query[offset:offset + limit])
    liked, saved = queries.viewer_states(user, notes)
    return JsonResponse({
        'count': total, 'limit': limit, 'offset': offset,
        'results': [queries.card(note, note.id in liked, note.id in saved) for note in notes],
    })


@require_http_methods(['GET', 'POST'])
@api
def mine(request):
    user = authenticated_user(request)
    if request.method == 'POST':
        note = services.create_note(user, body(request))
        return JsonResponse(queries.detail(queries.note_for_read(note.id, user), user), status=201)
    limit, offset = page(request)
    query = queries.enriched(Note.objects.filter(publisher=user, deleted_at__isnull=True)).order_by('-updated_at', 'id')
    total = query.count()
    notes = list(query[offset:offset + limit])
    liked, saved = queries.viewer_states(user, notes)
    return JsonResponse({
        'count': total, 'limit': limit, 'offset': offset,
        'results': [dict(queries.card(note, note.id in liked, note.id in saved), status=note.status) for note in notes],
    })


@require_http_methods(['GET'])
@api
def saved_notes(request):
    user = authenticated_user(request)
    limit, offset = page(request)
    query = SavedNote.objects.filter(user=user).order_by('-created_at', 'note_id')
    total = query.count()
    rows = list(query[offset:offset + limit])
    notes = list(queries.enriched(queries.visible_notes().filter(pk__in=[row.note_id for row in rows])))
    by_id = {note.id: note for note in notes}
    liked, _ = queries.viewer_states(user, notes)
    results = [
        {'note_id': str(row.note_id), 'saved_at': row.created_at.isoformat(), 'available': row.note_id in by_id,
         'note': queries.card(by_id[row.note_id], by_id[row.note_id].id in liked, True) if row.note_id in by_id else None}
        for row in rows
    ]
    return JsonResponse({'count': total, 'limit': limit, 'offset': offset, 'results': results})


@require_http_methods(['GET', 'PATCH', 'DELETE'])
@api
def my_note(request, note_id):
    user = authenticated_user(request)
    if request.method == 'PATCH':
        services.update_note(user, note_id, body(request))
    elif request.method == 'DELETE':
        services.delete_note(user, note_id)
        return JsonResponse({'deleted': True})
    return JsonResponse(queries.detail(queries.note_for_read(note_id, user), user))


@require_http_methods(['PUT'])
@api
def resources(request, note_id):
    user = authenticated_user(request)
    data = body(request)
    if not isinstance(data, dict) or set(data) != {'resources'}:
        raise NoteError('A resources array is required.')
    services.replace_resources(user, note_id, data['resources'])
    return JsonResponse(queries.detail(queries.note_for_read(note_id, user), user))


@require_http_methods(['POST', 'DELETE'])
@api
def my_pdf(request, note_id):
    user = authenticated_user(request)
    if request.method == 'DELETE':
        services.remove_pdf(user, note_id)
        return JsonResponse({'pdf': None})
    asset = services.upload_pdf(user, note_id, request.FILES.get('pdf'))
    return JsonResponse({'pdf': {'url': f'/api/v1/notes/{note_id}/pdf/', 'filename': asset.original_filename, 'page_count': asset.page_count}})


@require_http_methods(['POST'])
@api
def publish(request, note_id):
    user = authenticated_user(request)
    services.publish_note(user, note_id)
    return JsonResponse(queries.detail(queries.note_for_read(note_id, user), user))


@require_http_methods(['POST'])
@api
def archive(request, note_id):
    user = authenticated_user(request)
    services.archive_note(user, note_id)
    return JsonResponse(queries.detail(queries.note_for_read(note_id, user), user))


@require_http_methods(['GET'])
@api
def note_detail(request, note_id):
    user = optional_user(request)
    return JsonResponse(queries.detail(queries.note_for_read(note_id, user), user))


@require_http_methods(['GET'])
@api
def pdf(request, note_id):
    user = optional_user(request)
    note = queries.note_for_read(note_id, user)
    asset = NotePdfAsset.objects.filter(note=note).first()
    if asset is None:
        raise NoteError('PDF not found.', 404)
    download = request.GET.get('download', 'false').lower()
    if download not in {'true', 'false'}:
        raise NoteError('download must be true or false.')
    try:
        file = services.default_storage.open(asset.storage_key, 'rb')
    except OSError as exc:
        raise NoteError('PDF not found.', 404) from exc
    return FileResponse(file, content_type='application/pdf', as_attachment=download == 'true', filename=asset.original_filename)


@require_http_methods(['POST', 'DELETE'])
@api
def like(request, note_id):
    user = authenticated_user(request)
    return JsonResponse(services.set_like(user, note_id, request.method == 'POST'))


@require_http_methods(['POST', 'DELETE'])
@api
def save(request, note_id):
    user = authenticated_user(request)
    return JsonResponse(services.set_saved(user, note_id, request.method == 'POST'))


@require_http_methods(['GET', 'POST'])
@api
def comment_collection(request, note_id):
    if request.method == 'POST':
        user = authenticated_user(request)
        return JsonResponse(comments.serialize(comments.create_comment(user, note_id, body(request))), status=201)
    query = comments.list_comments(note_id)
    limit, offset = page(request)
    total = query.count()
    return JsonResponse({
        'count': total, 'limit': limit, 'offset': offset,
        'results': [comments.serialize(comment) for comment in query[offset:offset + limit]],
    })


@require_http_methods(['PATCH', 'DELETE'])
@api
def comment_detail(request, note_id, comment_id):
    user = authenticated_user(request)
    if request.method == 'PATCH':
        return JsonResponse(comments.serialize(comments.update_comment(user, note_id, comment_id, body(request))))
    return JsonResponse(comments.delete_comment(user, note_id, comment_id))
