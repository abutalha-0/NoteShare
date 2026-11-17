"""Shared notes, PDF assets, resources, likes, saves, and discussion."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from academics.models import AcademicDepartment, Course, Subject


class NoteStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_REVIEW = 'pending_review', 'Pending review'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


class NoteKind(models.TextChoices):
    LECTURE_NOTES = 'lecture_notes', 'Lecture notes'
    EXAM_PREP = 'exam_prep', 'Exam preparation'
    PROBLEM_SET = 'problem_set', 'Problem set'
    STUDY_GUIDE = 'study_guide', 'Study guide'
    OTHER = 'other', 'Other'


class Note(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='notes', db_column='publisher_id')
    department = models.ForeignKey(AcademicDepartment, on_delete=models.PROTECT, related_name='notes', db_column='department_id')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='notes', db_column='subject_id')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, null=True, blank=True, related_name='notes', db_column='course_id')
    kind = models.CharField(max_length=13, choices=NoteKind.choices, null=True, blank=True)
    title = models.CharField(max_length=180)
    short_description = models.CharField(max_length=280)
    detail_description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=14, choices=NoteStatus.choices, default=NoteStatus.DRAFT)
    moderation_hidden_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notes'
        indexes = [
            models.Index(fields=['status', 'published_at'], name='notes_status_published_idx'),
            models.Index(fields=['publisher', 'status', 'published_at'], name='notes_pub_status_date_idx'),
            models.Index(fields=['department', 'subject', 'status'], name='notes_dept_subject_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=NoteStatus.values), name='notes_status_valid'),
            models.CheckConstraint(condition=models.Q(kind__in=NoteKind.values) | models.Q(kind__isnull=True), name='notes_kind_valid'),
            models.CheckConstraint(condition=~models.Q(status=NoteStatus.PUBLISHED) | models.Q(published_at__isnull=False), name='notes_published_has_date'),
        ]

    def __str__(self):
        return self.title


class NotePdfAsset(models.Model):
    note = models.OneToOneField(Note, on_delete=models.CASCADE, primary_key=True, related_name='pdf_asset', db_column='note_id')
    storage_key = models.CharField(max_length=512, unique=True)
    original_filename = models.CharField(max_length=255)
    byte_size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'note_pdf_assets'
        constraints = [models.CheckConstraint(condition=models.Q(byte_size__gt=0), name='note_pdf_positive_size')]


class NoteResource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='resources', db_column='note_id')
    position = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=160)
    url = models.URLField(max_length=2048)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'note_resources'
        ordering = ['position']
        constraints = [
            models.CheckConstraint(condition=models.Q(position__gte=1, position__lte=5), name='note_resource_position_1_to_5'),
            models.UniqueConstraint(fields=['note', 'position'], name='note_resource_note_position_uniq'),
        ]


class NoteLike(models.Model):
    pk = models.CompositePrimaryKey('user', 'note')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='note_likes', db_column='user_id')
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='likes', db_column='note_id')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = 'note_likes'


class SavedNote(models.Model):
    pk = models.CompositePrimaryKey('user', 'note')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_notes', db_column='user_id')
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='saved_by', db_column='note_id')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = 'saved_notes'
        indexes = [models.Index(fields=['user', 'created_at'], name='saved_notes_user_date_idx')]


class NoteComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='comments', db_column='note_id')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='note_comments', db_column='author_id')
    parent_comment = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='replies', db_column='parent_comment_id')
    body = models.TextField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    moderation_hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'note_comments'
        indexes = [
            models.Index(fields=['note', 'created_at'], name='note_comments_note_date_idx'),
            models.Index(fields=['author', 'created_at'], name='note_comments_author_date_idx'),
        ]
