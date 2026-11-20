import pytest
from django.contrib.auth.models import Group

from apps.accounts.permissions import ROLE_ORDER


@pytest.mark.django_db
def test_migrate_creates_role_groups():
    assert set(Group.objects.values_list("name", flat=True)) >= set(ROLE_ORDER)
