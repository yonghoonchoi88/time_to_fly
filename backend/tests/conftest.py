import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(django_user_model):
    """Creates a user holding the given role groups (seeded by migration 0002)."""

    def _make(username="user", roles=(), **extra):
        user = django_user_model.objects.create_user(username=username, password="pw-for-tests", **extra)
        user.groups.set(Group.objects.filter(name__in=roles))
        return user

    return _make
