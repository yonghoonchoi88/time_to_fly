"""User model.

A custom user model is declared from the first migration: swapping
AUTH_USER_MODEL later would mean rebuilding every migration, so it exists
now even though it adds no fields yet.
"""
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    pass
