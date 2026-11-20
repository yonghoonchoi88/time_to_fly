import pytest
from rest_framework.test import APIRequestFactory

from apps.accounts.permissions import IsInspector, IsQaAdmin, IsShiftLead

PERMISSIONS = (IsInspector, IsShiftLead, IsQaAdmin)


def allowed(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return tuple(p().has_permission(request, None) for p in PERMISSIONS)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        ((), (False, False, False)),
        (("inspector",), (True, False, False)),
        (("shift_lead",), (True, True, False)),
        (("qa_admin",), (True, True, True)),
        (("inspector", "qa_admin"), (True, True, True)),  # highest role wins
    ],
)
def test_role_hierarchy(make_user, roles, expected):
    assert allowed(make_user(roles=roles)) == expected


@pytest.mark.django_db
def test_superuser_passes_without_groups(make_user):
    assert allowed(make_user(is_superuser=True)) == (True, True, True)


def test_anonymous_is_denied():
    from django.contrib.auth.models import AnonymousUser

    assert allowed(AnonymousUser()) == (False, False, False)
