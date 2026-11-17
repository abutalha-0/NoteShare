"""User profile and ordered public interests."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from academics.models import AcademicDepartment, University


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, db_column='user_id', related_name='profile')
    display_name = models.CharField(max_length=80, null=True, blank=True)
    bio = models.CharField(max_length=500, null=True, blank=True)
    avatar_key = models.CharField(max_length=512, null=True, blank=True)
    university = models.ForeignKey(University, on_delete=models.PROTECT, null=True, blank=True, related_name='profiles', db_column='university_id')
    department = models.ForeignKey(AcademicDepartment, on_delete=models.PROTECT, null=True, blank=True, related_name='profiles', db_column='department_id')
    show_avatar = models.BooleanField(default=True)
    show_bio = models.BooleanField(default=True)
    show_university = models.BooleanField(default=True)
    show_department = models.BooleanField(default=True)
    show_interests = models.BooleanField(default=True)
    moderation_hidden_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'profiles'

    def __str__(self):
        return self.display_name or str(self.user_id)


class ProfileInterest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='interests', db_column='user_id')
    label = models.CharField(max_length=80)
    label_normalized = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'profile_interests'
        ordering = ['position']
        constraints = [
            models.CheckConstraint(condition=models.Q(position__gte=1, position__lte=10), name='profile_interest_position_1_to_10'),
            models.UniqueConstraint(fields=['profile', 'label_normalized'], name='profile_interests_user_label_uniq'),
            models.UniqueConstraint(fields=['profile', 'position'], name='profile_interests_user_position_uniq'),
        ]

    def __str__(self):
        return self.label
