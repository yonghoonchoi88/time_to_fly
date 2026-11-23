"""Single place that writes Event rows, so every event has the same shape."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from ..models import Event, Lot

SYSTEM_ACTOR = "system"


def record(
    *,
    lot: Lot | None,
    object_type: str,
    object_id: int,
    event: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> Event:
    return Event.objects.create(
        lot=lot,
        object_type=object_type,
        object_id=object_id,
        event=event,
        actor=actor,
        at=at or timezone.now(),
        payload=payload or {},
    )
