"""Human review decisions on queued inspections.

Decision semantics differ by why the task was queued:

low_confidence (the model saw something but was unsure)
- confirm:    the model was right. Candidates become confirmed defects.
- reject:     false alarm. Candidates become rejected and are flagged for retraining.
- add_missed: the real defect is elsewhere. A human defect is added as confirmed; the
              candidates are rejected and flagged, because the model pointed at the wrong place.

audit_sample (an OK verdict picked at random for a second look)
- confirm:    the OK verdict is correct. Any sub-threshold candidates are rejected but not
              flagged for retraining: routing already ignored them, so the model was right.
- reject:     not allowed. There is no alarm to reject.
- add_missed: the model missed a defect (a false negative). Handled as above; this count
              is the "missed defects recovered by audit" metric.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ..domain import transitions
from ..enums import DefectOrigin, DefectStatus, ReviewDecision, ReviewReason, ReviewStatus
from ..models import Defect, ReviewTask
from . import events
from .errors import Conflict, Invalid, NotFound


@dataclass(frozen=True)
class MissedDefect:
    defect_type: str
    bbox: tuple[float, float, float, float]  # x, y, w, h in source-image pixels

    def __post_init__(self) -> None:
        if len(self.bbox) != 4:
            raise Invalid("bbox must be [x, y, w, h]")
        x, y, w, h = self.bbox
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise Invalid("bbox needs a non-negative origin and a positive size")


@transaction.atomic
def decide(task_id: int, *, decision: str, reviewer, missed: MissedDefect | None = None) -> ReviewTask:
    """Apply one reviewer decision. ``reviewer`` is the authenticated User."""
    if decision not in ReviewDecision.values:
        raise Invalid(f"unknown decision {decision!r}")
    if (decision == ReviewDecision.ADD_MISSED) != (missed is not None):
        raise Invalid("a missed defect is required for add_missed and only allowed there")

    # Row lock so two reviewers cannot decide the same task at once.
    task = ReviewTask.objects.select_for_update().select_related("inspection__lot").filter(pk=task_id).first()
    if task is None:
        raise NotFound(f"review task {task_id}")
    if task.status != ReviewStatus.PENDING:
        raise Conflict(f"review task {task_id} is already decided ({task.decision})")
    is_audit = task.reason == ReviewReason.AUDIT_SAMPLE
    if is_audit and decision == ReviewDecision.REJECT:
        raise Invalid("an audit sample has no alarm to reject; use confirm or add_missed")

    inspection = task.inspection
    lot = inspection.lot
    actor = reviewer.get_username()
    now = timezone.now()
    candidates = list(inspection.defects.select_for_update().filter(status=DefectStatus.CANDIDATE))

    if decision == ReviewDecision.CONFIRM and not is_audit:
        for defect in candidates:
            _move_defect(defect, DefectStatus.CONFIRMED, lot, actor, now, retrain=False)
    else:
        # The model's candidates were not the defect: audit confirm (they were noise below the
        # review threshold, nothing to learn) or reject / add_missed (the model was wrong).
        retrain = not (is_audit and decision == ReviewDecision.CONFIRM)
        for defect in candidates:
            _move_defect(defect, DefectStatus.REJECTED, lot, actor, now, retrain=retrain)

    if missed is not None:
        human = Defect.objects.create(
            inspection=inspection,
            defect_type=missed.defect_type,
            confidence=None,
            bbox=list(missed.bbox),
            origin=DefectOrigin.HUMAN,
            status=DefectStatus.CONFIRMED,
        )
        events.record(
            lot=lot, object_type="defect", object_id=human.pk, event="added_by_reviewer",
            actor=actor, at=now, payload={"bbox": list(missed.bbox), "inspection_id": inspection.pk},
        )

    transitions.check(task.status, ReviewStatus.DONE)
    task.status = ReviewStatus.DONE
    task.decision = decision
    task.reviewer = reviewer
    task.decided_at = now
    task.save(update_fields=["status", "decision", "reviewer", "decided_at"])
    events.record(
        lot=lot,
        object_type="review_task",
        object_id=task.pk,
        event=f"decided:{decision}",
        actor=actor,
        at=now,
        payload={"inspection_id": inspection.pk, "reason": task.reason, "candidates": len(candidates)},
    )
    return task


def pending_tasks(limit: int = 50):
    """Oldest first, so the queue is worked in arrival order."""
    return (
        ReviewTask.objects.filter(status=ReviewStatus.PENDING)
        .select_related("inspection__lot")
        .prefetch_related("inspection__defects")
        .order_by("created_at", "id")[:limit]
    )


def _move_defect(defect: Defect, target: DefectStatus, lot, actor: str, at, *, retrain: bool) -> None:
    transitions.check(defect.status, target)
    defect.status = target
    defect.retrain_candidate = retrain
    defect.save(update_fields=["status", "retrain_candidate"])
    events.record(
        lot=lot, object_type="defect", object_id=defect.pk, event=str(target),
        actor=actor, at=at, payload={"retrain_candidate": retrain},
    )
