"""Profile visibility, editing, and avatar storage rules."""

import io
import logging
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import AccountStatus
from academics.models import AcademicDepartment, University

from .models import Profile, ProfileInterest


logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 3000
ALLOWED_AVATAR_FORMATS = {'JPEG', 'PNG', 'WEBP'}
EDITABLE_FIELDS = {
    'display_name', 'bio', 'university_id', 'department_id', 'interests',
    'show_avatar', 'show_bio', 'show_university', 'show_department', 'show_interests',
}
PRIVACY_FIELDS = ('show_avatar', 'show_bio', 'show_university', 'show_department', 'show_interests')


class ProfileError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def parse_uuid(value, field):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProfileError(f'{field} must be a valid UUID or null.') from exc


def own_profile(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return Profile.objects.select_related('user', 'university', 'department').prefetch_related('interests').get(pk=profile.pk)


def public_profile(user_id):
    profile = Profile.objects.select_related('user', 'university', 'department').prefetch_related('interests').filter(
        user_id=parse_uuid(user_id, 'user_id'),
        user__status=AccountStatus.ACTIVE,
        user__email_verified_at__isnull=False,
        moderation_hidden_at__isnull=True,
    ).first()
    if profile is None:
        raise ProfileError('Profile not found.', 404)
    return profile


def academic_reference(item):
    if item is None:
        return None
    return {'id': str(item.id), 'code': item.code, 'name': item.name}


def serialize(profile, owner=False):
    data = {
        'user_id': str(profile.user_id),
        'display_name': profile.display_name or 'Fieldnotes member',
        'joined_at': profile.user.created_at.isoformat(),
        'avatar_url': None,
        'bio': None,
        'university': None,
        'department': None,
        'interests': [],
    }
    if profile.avatar_key and (owner or profile.show_avatar):
        data['avatar_url'] = reverse('own_profile_avatar' if owner else 'public_profile_avatar', kwargs={} if owner else {'user_id': profile.user_id})
    if owner or profile.show_bio:
        data['bio'] = profile.bio
    if owner or profile.show_university:
        data['university'] = academic_reference(profile.university)
    if owner or (profile.show_department and profile.show_university):
        data['department'] = academic_reference(profile.department)
    if owner or profile.show_interests:
        data['interests'] = [interest.label for interest in profile.interests.all()]
    if owner:
        data.update({
            'email': profile.user.email,
            'display_name': profile.display_name,
            'privacy': {field: getattr(profile, field) for field in PRIVACY_FIELDS},
            'moderation_hidden': profile.moderation_hidden_at is not None,
            'updated_at': profile.updated_at.isoformat(),
        })
    return data


def optional_text(value, field, max_length):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileError(f'{field} must be text or null.')
    result = value.strip()
    if len(result) > max_length or any(ord(char) < 32 and char not in '\n\t' for char in result):
        raise ProfileError(f'{field} must be at most {max_length} characters.')
    if field == 'display_name' and ('\n' in result or '\t' in result):
        raise ProfileError('display_name must be on one line.')
    return result or None


def validate_interests(value):
    if not isinstance(value, list) or len(value) > 10:
        raise ProfileError('interests must be a list of at most 10 labels.')
    result = []
    seen = set()
    for label in value:
        text = optional_text(label, 'interest', 80)
        if not text or '\n' in text or '\t' in text:
            raise ProfileError('Interest labels must be nonempty and on one line.')
        normalized = ' '.join(text.split()).casefold()
        if len(normalized) > 80 or normalized in seen:
            raise ProfileError('Interest labels must be unique, ignoring case and spacing.')
        seen.add(normalized)
        result.append((text, normalized))
    return result


def update_profile(user, data):
    if not isinstance(data, dict):
        raise ProfileError('A JSON object is required.')
    unknown = set(data) - EDITABLE_FIELDS
    if unknown:
        raise ProfileError('Unknown or read-only field: ' + sorted(unknown)[0])
    if not data:
        raise ProfileError('At least one field is required.')
    prepared = {}
    for field, value in data.items():
        if field in PRIVACY_FIELDS:
            if not isinstance(value, bool):
                raise ProfileError(f'{field} must be a boolean.')
            prepared[field] = value
        elif field == 'display_name':
            prepared[field] = optional_text(value, field, 80)
        elif field == 'bio':
            prepared[field] = optional_text(value, field, 500)
        elif field in {'university_id', 'department_id'}:
            prepared[field] = parse_uuid(value, field) if value is not None else None
        elif field == 'interests':
            prepared[field] = validate_interests(value)
    try:
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(user=user)
            for field, value in prepared.items():
                if field != 'interests':
                    setattr(profile, field, value)
            if profile.university_id and not University.objects.filter(pk=profile.university_id, is_active=True).exists():
                raise ProfileError('Select an active university.')
            if profile.department_id:
                if not profile.university_id or not AcademicDepartment.objects.filter(
                    pk=profile.department_id, university_id=profile.university_id, is_active=True,
                    university__is_active=True, discipline__is_active=True,
                ).exists():
                    raise ProfileError('Department must be active and belong to the selected university.')
            profile.save()
            if 'interests' in prepared:
                profile.interests.all().delete()
                ProfileInterest.objects.bulk_create([
                    ProfileInterest(profile=profile, label=label, label_normalized=normalized, position=position)
                    for position, (label, normalized) in enumerate(prepared['interests'], 1)
                ])
    except Profile.DoesNotExist as exc:
        raise ProfileError('Profile not found.', 404) from exc
    except IntegrityError as exc:
        raise ProfileError('Profile update conflicts with existing data.', 409) from exc
    return own_profile(user)


def prepare_avatar(upload):
    if upload is None:
        raise ProfileError('An avatar file is required.')
    if upload.size > MAX_AVATAR_BYTES:
        raise ProfileError('Avatar must be 2 MB or smaller.', 413)
    try:
        upload.seek(0)
        image = Image.open(upload)
        if image.format not in ALLOWED_AVATAR_FORMATS or getattr(image, 'n_frames', 1) != 1:
            raise ProfileError('Avatar must be a still JPEG, PNG, or WebP image.')
        if max(image.size) > MAX_AVATAR_DIMENSION or image.width * image.height > 9_000_000:
            raise ProfileError('Avatar dimensions must be at most 3000 × 3000 pixels.')
        image.load()
        image = ImageOps.exif_transpose(image)
        image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='WEBP', quality=84, method=4)
        return ContentFile(output.getvalue())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProfileError('Avatar is not a valid supported image.') from exc


def delete_file_safely(key):
    if key:
        try:
            default_storage.delete(key)
        except OSError:
            logger.exception('Could not remove an old profile avatar')


def set_avatar(user, upload):
    image = prepare_avatar(upload)
    key = f'profile_avatars/{user.id}/{uuid.uuid4().hex}.webp'
    key = default_storage.save(key, image)
    try:
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(user=user)
            previous_key = profile.avatar_key
            profile.avatar_key = key
            profile.save(update_fields=['avatar_key', 'updated_at'])
            if previous_key:
                transaction.on_commit(lambda: delete_file_safely(previous_key))
    except Exception:
        delete_file_safely(key)
        raise
    return own_profile(user)


def remove_avatar(user):
    with transaction.atomic():
        profile = Profile.objects.select_for_update().get(user=user)
        previous_key = profile.avatar_key
        if previous_key:
            profile.avatar_key = None
            profile.save(update_fields=['avatar_key', 'updated_at'])
            transaction.on_commit(lambda: delete_file_safely(previous_key))
    return own_profile(user)


def avatar_file(profile):
    if not profile.avatar_key:
        raise ProfileError('Avatar not found.', 404)
    try:
        return default_storage.open(profile.avatar_key, 'rb')
    except (OSError, ValueError) as exc:
        raise ProfileError('Avatar not found.', 404) from exc
