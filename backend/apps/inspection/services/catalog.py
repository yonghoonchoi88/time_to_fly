"""Reference objects: production lines, lots and the active model version."""
from __future__ import annotations

from django.conf import settings
from django.db import transaction

from ..models import Lot, ModelVersion, ProductionLine
from . import events
from .errors import Conflict, NotFound


def active_model_version() -> ModelVersion:
    try:
        return ModelVersion.objects.get(is_active=True)
    except ModelVersion.DoesNotExist as exc:
        raise Conflict("no active model version; activate one in the admin site") from exc


def lot_by_code(code: str, product_type: str = "unknown") -> Lot:
    """Return the lot with this code, creating it on the default line on first sight.

    get_or_create retries the lookup when a concurrent insert wins the unique constraint,
    so two frames of a new lot arriving at once still map to one lot.
    """
    code = code.strip()
    if not code:
        raise NotFound("empty lot code")
    line, _ = ProductionLine.objects.get_or_create(name=settings.DEFAULT_LINE)
    lot, _ = Lot.objects.get_or_create(code=code, defaults={"line": line, "product_type": product_type})
    return lot


def get_lot(code: str) -> Lot:
    try:
        return Lot.objects.get(code=code)
    except Lot.DoesNotExist as exc:
        raise NotFound(f"lot {code!r}") from exc


@transaction.atomic
def activate_model_version(model_version_id: int, *, actor: str) -> ModelVersion:
    """Make one version the one new inspections are recorded against.

    Deactivate-then-activate inside one transaction keeps the single-active constraint
    satisfied at every statement. Inspections already queued keep the version they were
    received with.
    """
    target = ModelVersion.objects.select_for_update().filter(pk=model_version_id).first()
    if target is None:
        raise NotFound(f"model version {model_version_id}")
    previous = ModelVersion.objects.select_for_update().filter(is_active=True).exclude(pk=target.pk).first()
    if previous is not None:
        previous.is_active = False
        previous.save(update_fields=["is_active"])
    if not target.is_active:
        target.is_active = True
        target.save(update_fields=["is_active"])
    events.record(
        lot=None,
        object_type="model_version",
        object_id=target.pk,
        event="activated",
        actor=actor,
        payload={"name": target.name, "previous": previous.name if previous else None},
    )
    return target
