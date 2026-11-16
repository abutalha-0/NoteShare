"""Fast account API tests without requiring a local MySQL server."""

import os

os.environ.setdefault('DJANGO_SECRET_KEY', 'test-only-fieldnotes-secret-key-long-enough-for-hs256')

from .settings import *  # noqa: F403,E402

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
JWT_SIGNING_KEY = 'test-only-fieldnotes-jwt-signing-key-long-enough-for-hs256'
