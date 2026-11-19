"""Allowed state transitions (the ontology's action types).

Any transition not listed here is rejected. Keeping the table in one place makes the rules
reviewable and testable without a database.
"""

from app.domain.enums import ActionStatus, DefectStatus, LotStatus, ReviewStatus, StrEnum

ALLOWED: dict[type[StrEnum], dict[StrEnum, set[StrEnum]]] = {
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


def check(current: StrEnum, target: StrEnum) -> None:
    """Raise InvalidTransition unless current -> target is an allowed move."""
    table = ALLOWED.get(type(current), {})
    if target not in table.get(current, set()):
        raise InvalidTransition(f"{type(current).__name__}: {current} -> {target} is not allowed")
