"""Authentication models aligned with the accounts section of the DBML."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models, transaction
from django.utils import timezone


class AccountStatus(models.TextChoices):
    PENDING_VERIFICATION = 'pending_verification', 'Pending verification'
    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'


class AccountRole(models.TextChoices):
    STUDENT = 'student', 'Student'
    MODERATOR = 'moderator', 'Moderator'
    ADMIN = 'admin', 'Admin'


class TokenPurpose(models.TextChoices):
    VERIFY_EMAIL = 'verify_email', 'Verify email'
    RESET_PASSWORD = 'reset_password', 'Reset password'


class UserManager(BaseUserManager):
    def normalize_email(self, email):
        return (email or '').strip().lower()

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        if not email:
            raise ValueError('An email address is required.')
        with transaction.atomic(using=self._db):
            user = self.model(email=email, **extra_fields)
            if password is not None:
                user.set_password(password)
            user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        if not password:
            raise ValueError('A password is required.')
        extra_fields.setdefault('status', AccountStatus.ACTIVE)
        extra_fields.setdefault('email_verified_at', timezone.now())
        if extra_fields['status'] != AccountStatus.ACTIVE:
            raise ValueError('A superuser must be active.')
        with transaction.atomic(using=self._db):
            user = self.create_user(email, password, **extra_fields)
            UserRole.objects.using(self._db).create(user=user, role=AccountRole.ADMIN)
        return user


class User(AbstractBaseUser):
    # Credentials live in password_credentials. AbstractBaseUser supplies
    # Django's user interface and password/session helpers.
    last_login = None

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=320, unique=True)
    status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.PENDING_VERIFICATION)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    EMAIL_FIELD = 'email'
    objects = UserManager()

    class Meta:
        db_table = 'users'
        constraints = [models.CheckConstraint(condition=models.Q(status__in=AccountStatus.values), name='users_status_valid')]

    def __str__(self):
        return self.email

    @property
    def password(self):
        try:
            return self.credential.password_hash
        except PasswordCredential.DoesNotExist:
            return '!'

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self._pending_password_hash = make_password(raw_password)

    def save(self, *args, **kwargs):
        self.email = User.objects.normalize_email(self.email)
        with transaction.atomic(using=kwargs.get('using')):
            super().save(*args, **kwargs)
            pending_hash = getattr(self, '_pending_password_hash', None)
            if pending_hash is not None:
                PasswordCredential.objects.update_or_create(
                    user=self,
                    defaults={'password_hash': pending_hash, 'password_changed_at': timezone.now()},
                )
                del self._pending_password_hash

    @property
    def is_active(self):
        return self.status == AccountStatus.ACTIVE and self.email_verified_at is not None

    @property
    def is_staff(self):
        return self.pk is not None and self.roles.filter(role__in=[AccountRole.MODERATOR, AccountRole.ADMIN]).exists()

    @property
    def is_superuser(self):
        return self.pk is not None and self.roles.filter(role=AccountRole.ADMIN).exists()

    def has_perm(self, perm, obj=None):
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label):
        return self.has_perm(f'{app_label}.access')


class PasswordCredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, db_column='user_id', related_name='credential')
    password_hash = models.TextField()
    password_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'password_credentials'


class UserRole(models.Model):
    pk = models.CompositePrimaryKey('user', 'role')
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id', related_name='roles')
    role = models.CharField(max_length=9, choices=AccountRole.choices)
    granted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'user_roles'
        indexes = [models.Index(fields=['role'], name='user_roles_role_idx')]
        constraints = [models.CheckConstraint(condition=models.Q(role__in=AccountRole.values), name='user_roles_role_valid')]


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id', related_name='auth_sessions')
    refresh_token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'auth_sessions'
        indexes = [models.Index(fields=['user', 'expires_at'], name='auth_sessions_user_exp_idx')]
        constraints = [models.CheckConstraint(condition=models.Q(expires_at__gt=models.F('created_at')), name='auth_sessions_exp_after_create')]


class AuthActionToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id', related_name='action_tokens')
    purpose = models.CharField(max_length=14, choices=TokenPurpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'auth_action_tokens'
        indexes = [models.Index(fields=['user', 'purpose', 'expires_at'], name='auth_tokens_user_purp_exp_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(purpose__in=TokenPurpose.values), name='auth_tokens_purpose_valid'),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F('created_at')), name='auth_tokens_exp_after_create'),
        ]
