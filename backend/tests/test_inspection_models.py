"""Database-level guarantees: seed data, constraints, frozen thresholds, append-only events."""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inspection.models import Event, ModelVersion, ProductionLine
from apps.inspection.services import catalog
from apps.inspection.services.errors import Conflict

pytestmark = pytest.mark.django_db


def new_version(name="yolo-1", **overrides):
    values = {"engine": "yolo", "auto_ng_conf": 0.8, "review_conf": 0.3, "audit_rate": 0.05}
    values.update(overrides)
    return ModelVersion.objects.create(name=name, **values)


def test_migration_seeds_default_line_and_active_mock_version():
    assert ProductionLine.objects.filter(name="line-1").exists()
    active = catalog.active_model_version()
    assert (active.name, active.engine) == ("mock-0", "mock")


def test_only_one_version_can_be_active():
    with pytest.raises(IntegrityError), transaction.atomic():
        new_version(is_active=True)


@pytest.mark.parametrize("overrides", [{"review_conf": 0.9}, {"auto_ng_conf": 1.2}, {"audit_rate": -0.1}])
def test_threshold_ranges_are_enforced_by_the_database(overrides):
    with pytest.raises(IntegrityError), transaction.atomic():
        new_version(**overrides)


def test_activation_switches_the_active_version_and_logs_it():
    yolo = new_version()
    catalog.activate_model_version(yolo.pk, actor="admin")

    assert catalog.active_model_version() == yolo
    assert not ModelVersion.objects.get(name="mock-0").is_active
    event = Event.objects.get(object_type="model_version", event="activated")
    assert event.payload == {"name": "yolo-1", "previous": "mock-0"}


def test_no_active_version_is_a_conflict():
    ModelVersion.objects.update(is_active=False)
    with pytest.raises(Conflict):
        catalog.active_model_version()


def test_thresholds_are_editable_until_first_use(receive):
    version = catalog.active_model_version()
    version.review_conf = 0.3
    version.save()  # unused so far

    receive()
    version.review_conf = 0.35
    with pytest.raises(ValidationError):
        version.save()
    version.refresh_from_db()
    assert version.review_conf == 0.3


def test_note_stays_editable_after_use(receive):
    receive()
    version = catalog.active_model_version()
    version.note = "used for the first demo"
    version.save()


def test_events_are_append_only(receive):
    event = Event.objects.get(object_type="inspection", object_id=receive().pk)
    event.actor = "someone-else"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
