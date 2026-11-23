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


# --- inspection domain -----------------------------------------------------------------

MOCK_VERSION = "mock-0"  # seeded active by inspection migration 0002


def make_prediction(*confidences, engine="mock", version=MOCK_VERSION, width=640, height=480):
    """An inference-server /predict body with one candidate per confidence."""
    return {
        "model": "kimchi-yolo",
        "version": version,
        "engine": engine,
        "latency_ms": 12.5,
        "width": width,
        "height": height,
        "candidates": [
            {"defect_type": "foreign_object", "confidence": c, "bbox": [10.0 * i, 20.0, 30.0, 40.0]}
            for i, c in enumerate(confidences)
        ],
    }


@pytest.fixture
def prediction():
    return make_prediction


@pytest.fixture
def receive():
    """Records a received frame for a lot, as the intake endpoint will."""
    from apps.inspection.services.inspections import receive_inspection

    def _receive(lot_code="S01", source="replay", actor="line-replay"):
        return receive_inspection(lot_code=lot_code, image_path=f"{lot_code}/frame.jpg", source=source, actor=actor)

    return _receive


@pytest.fixture
def inspected(receive):
    """A completed inspection with the given candidate confidences."""
    from apps.inspection.services.inspections import complete_inspection

    def _inspected(*confidences, lot_code="S01"):
        inspection = receive(lot_code=lot_code)
        return complete_inspection(inspection.pk, make_prediction(*confidences))

    return _inspected


@pytest.fixture
def reviewer(make_user):
    return make_user(username="kim", roles=["inspector"])
