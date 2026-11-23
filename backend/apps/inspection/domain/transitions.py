"""Allowed state transitions (the ontology's action types).

Any transition not listed here is rejected. Keeping the table in one place makes the rules
reviewable and testable without a database.
"""
from __future__ import annotations

from django.db.models import TextChoices

from ..enums import ActionStatus, DefectStatus, LotStatus, ReviewStatus

ALLOWED: dict[type[TextChoices], dict[str, set[str]]] = {
    DefectStatus: {
        DefectStatus.CANDIDATE: {DefectStatus.CONFIRMED, DefectStatus.REJECTED},
    },
    ReviewStatus: {
        ReviewStatus.PENDING: {ReviewStatus.DONE},
    },
    ActionStatus: {
        ActionStatus.OPEN: {ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED},
        ActionStatus.IN_PROGRESS: {ActionStatus.DONE, ActionStatus.CANCELLED},
    },
    LotStatus: {
        LotStatus.OPEN: {LotStatus.ON_HOLD},
        LotStatus.ON_HOLD: {LotStatus.RELEASED, LotStatus.SCRAPPED},
    },
}


class InvalidTransition(ValueError):
    pass


def check(current: str, target: TextChoices) -> None:
    """Raise InvalidTransition unless current -> target is an allowed move.

    ``target`` must be an enum member; it selects the table. ``current`` may be a plain
    string, which is what a model field holds after it is loaded from the database.
    """
    enum_cls = type(target)
    try:
        current = enum_cls(current)
    except ValueError as exc:
        raise InvalidTransition(f"{current!r} is not a {enum_cls.__name__}") from exc
    if target not in ALLOWED.get(enum_cls, {}).get(current, set()):
        raise InvalidTransition(f"{enum_cls.__name__}: {current} -> {target} is not allowed")
