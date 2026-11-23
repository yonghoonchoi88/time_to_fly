"""Status and type vocabularies of the ontology.

Values are the strings stored in the database and returned by the API, so they must stay
stable. Note that a model field read back from the database holds a plain ``str``, not the
enum member: compare with ``==``, never ``is``.
"""
from django.db import models


class LotStatus(models.TextChoices):
    OPEN = "open", "진행 중"
    ON_HOLD = "on_hold", "보류"
    RELEASED = "released", "해제"
    SCRAPPED = "scrapped", "폐기"


class InspectionSource(models.TextChoices):
    LIVE = "live", "실시간"
    REPLAY = "replay", "재생"


class InspectionStatus(models.TextChoices):
    """Processing state. Inference is asynchronous, so a row exists before its verdict does."""

    QUEUED = "queued", "대기"
    DONE = "done", "완료"
    FAILED = "failed", "실패"


class Verdict(models.TextChoices):
    OK = "OK", "OK"
    NG = "NG", "NG"
    REVIEW = "REVIEW", "검수 필요"


class DefectOrigin(models.TextChoices):
    MODEL = "model", "모델"
    HUMAN = "human", "사람"


class DefectStatus(models.TextChoices):
    CANDIDATE = "candidate", "후보"
    CONFIRMED = "confirmed", "확정"
    REJECTED = "rejected", "반려"


class ReviewReason(models.TextChoices):
    LOW_CONFIDENCE = "low_confidence", "낮은 신뢰도"
    AUDIT_SAMPLE = "audit_sample", "감사 샘플"


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "대기"
    DONE = "done", "완료"


class ReviewDecision(models.TextChoices):
    CONFIRM = "confirm", "확정"
    REJECT = "reject", "반려"
    ADD_MISSED = "add_missed", "놓친 결함 추가"


class ActionType(models.TextChoices):
    HOLD_LOT = "hold_lot", "Lot 보류"
    RECHECK = "recheck", "재검"
    STOP_LINE = "stop_line", "라인 정지"
    RELEASE_LOT = "release_lot", "Lot 해제"


class ActionStatus(models.TextChoices):
    OPEN = "open", "열림"
    IN_PROGRESS = "in_progress", "진행 중"
    DONE = "done", "완료"
    CANCELLED = "cancelled", "취소"
