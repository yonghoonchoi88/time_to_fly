"""Status and type vocabularies shared across the ontology."""

from enum import Enum


class StrEnum(str, Enum):
    """str-valued enum that also works on Python 3.10 (enum.StrEnum is 3.11+)."""

    def __str__(self) -> str:
        return self.value


class LotStatus(StrEnum):
    OPEN = "open"
    ON_HOLD = "on_hold"
    RELEASED = "released"
    SCRAPPED = "scrapped"


class InspectionSource(StrEnum):
    LIVE = "live"
    REPLAY = "replay"


class Verdict(StrEnum):
    OK = "OK"
    NG = "NG"
    REVIEW = "REVIEW"


class DefectOrigin(StrEnum):
    MODEL = "model"
    HUMAN = "human"


class DefectStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ReviewReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    AUDIT_SAMPLE = "audit_sample"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"


class ReviewDecision(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"
    ADD_MISSED = "add_missed"


class ActionType(StrEnum):
    HOLD_LOT = "hold_lot"
    RECHECK = "recheck"
    STOP_LINE = "stop_line"
    RELEASE_LOT = "release_lot"


class ActionStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"
