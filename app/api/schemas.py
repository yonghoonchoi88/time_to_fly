"""Response and request bodies shared by the API routers. Contract: docs/api.md."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    ActionStatus,
    ActionType,
    DefectStatus,
    LotStatus,
    ReviewDecision,
    ReviewReason,
    ReviewStatus,
    Verdict,
)
from app.domain.models import Action, Defect, ReviewTask


class DefectOut(BaseModel):
    id: int
    defect_type: str
    confidence: float | None
    bbox: list[float] | None
    status: DefectStatus

    @classmethod
    def of(cls, d: Defect) -> "DefectOut":
        return cls(id=d.id, defect_type=d.defect_type, confidence=d.confidence, bbox=d.bbox, status=d.status)


class InspectionOut(BaseModel):
    inspection_id: int
    lot_code: str
    verdict: Verdict
    latency_ms: float
    review_task_id: int | None
    defects: list[DefectOut]


class ReviewInspectionOut(BaseModel):
    id: int
    lot_code: str
    verdict: Verdict
    captured_at: datetime
    image_url: str
    width: int
    height: int


class ReviewTaskOut(BaseModel):
    id: int
    reason: ReviewReason
    status: ReviewStatus
    decision: ReviewDecision | None
    reviewer: str | None
    created_at: datetime
    decided_at: datetime | None
    inspection: ReviewInspectionOut
    defects: list[DefectOut]

    @classmethod
    def of(cls, t: ReviewTask) -> "ReviewTaskOut":
        insp = t.inspection
        return cls(
            id=t.id,
            reason=t.reason,
            status=t.status,
            decision=t.decision,
            reviewer=t.reviewer,
            created_at=t.created_at,
            decided_at=t.decided_at,
            inspection=ReviewInspectionOut(
                id=insp.id,
                lot_code=insp.lot.code,
                verdict=insp.verdict,
                captured_at=insp.captured_at,
                image_url=f"/inspections/{insp.id}/image",
                width=insp.image_width,
                height=insp.image_height,
            ),
            defects=[DefectOut.of(d) for d in insp.defects],
        )


class DecisionIn(BaseModel):
    decision: ReviewDecision
    reviewer: str = Field(min_length=1, max_length=64)
    defect_type: str | None = Field(default=None, min_length=1, max_length=64)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def _missed_fields(self) -> "DecisionIn":
        has_missed = self.defect_type is not None or self.bbox is not None
        if self.decision is ReviewDecision.ADD_MISSED:
            if self.defect_type is None or self.bbox is None:
                raise ValueError("add_missed requires defect_type and bbox")
            x, y, w, h = self.bbox
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                raise ValueError("bbox must be [x, y, w, h] with x, y >= 0 and w, h > 0")
        elif has_missed:
            raise ValueError("defect_type and bbox are only allowed with add_missed")
        return self


class ActionIn(BaseModel):
    lot_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    action_type: ActionType
    owner: str = Field(min_length=1, max_length=64)
    defect_id: int | None = None
    note: str = Field(default="", max_length=2000)


class ActionStatusIn(BaseModel):
    status: ActionStatus
    actor: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=2000)


class ActionOut(BaseModel):
    id: int
    lot_code: str
    lot_status: LotStatus
    action_type: ActionType
    status: ActionStatus
    owner: str
    defect_id: int | None
    note: str
    opened_at: datetime
    closed_at: datetime | None
    # Seconds from the defect's capture to this action being opened / completed.
    # Null when the action is not tied to a defect, or not completed yet.
    detection_to_open_s: float | None
    detection_to_done_s: float | None

    @classmethod
    def of(cls, a: Action) -> "ActionOut":
        captured = a.defect.inspection.captured_at if a.defect is not None else None
        to_open = (a.opened_at - captured).total_seconds() if captured else None
        to_done = (
            (a.closed_at - captured).total_seconds()
            if captured and a.closed_at and a.status is ActionStatus.DONE
            else None
        )
        return cls(
            id=a.id,
            lot_code=a.lot.code,
            lot_status=a.lot.status,
            action_type=a.action_type,
            status=a.status,
            owner=a.owner,
            defect_id=a.defect_id,
            note=a.note,
            opened_at=a.opened_at,
            closed_at=a.closed_at,
            detection_to_open_s=round(to_open, 3) if to_open is not None else None,
            detection_to_done_s=round(to_done, 3) if to_done is not None else None,
        )
