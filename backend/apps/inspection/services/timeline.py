"""Lot history (#8): every event of one lot, oldest first.

Because each Event carries its lot, this is a single indexed query on (lot, at) rather than
a union over inspections, defects, review tasks and actions.
"""
from __future__ import annotations

from ..models import Event
from . import catalog


def lot_timeline(lot_code: str, limit: int = 500) -> list[Event]:
    lot = catalog.get_lot(lot_code)
    return list(Event.objects.filter(lot=lot).order_by("at", "id")[:limit])
