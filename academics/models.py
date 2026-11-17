"""Academic directory models shared by profiles and notes."""

import uuid

from django.db import models
from django.utils import timezone


class University(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'universities'
        ordering = ['name', 'code']

    def __str__(self):
        return self.name


class Discipline(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'disciplines'
        ordering = ['name', 'code']

    def __str__(self):
        return self.name


class AcademicDepartment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    university = models.ForeignKey(University, on_delete=models.PROTECT, related_name='departments', db_column='university_id')
    discipline = models.ForeignKey(Discipline, on_delete=models.PROTECT, related_name='departments', db_column='discipline_id')
    code = models.CharField(max_length=24)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'academic_departments'
        ordering = ['university__name', 'name', 'code']
        constraints = [
            models.UniqueConstraint(fields=['university', 'code'], name='academic_dept_university_code_uniq'),
            models.UniqueConstraint(fields=['university', 'name'], name='academic_dept_university_name_uniq'),
        ]

    def __str__(self):
        return f'{self.name} · {self.university.code}'


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subjects'
        ordering = ['name', 'slug']

    def __str__(self):
        return self.name


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    department = models.ForeignKey(AcademicDepartment, on_delete=models.PROTECT, related_name='courses', db_column='department_id')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='courses', db_column='subject_id')
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'courses'
        ordering = ['department__university__name', 'department__name', 'code']
        constraints = [models.UniqueConstraint(fields=['department', 'code'], name='courses_department_code_uniq')]

    def __str__(self):
        return f'{self.code} · {self.name}'
