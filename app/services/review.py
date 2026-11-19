"""Human review decisions on queued inspections.

Decision semantics (v0.1, see docs/api.md):
- confirm:    the model was right. Candidate defects become confirmed. On an audit sample
              with no candidates this records that the OK verdict was correct.
- reject:     false alarm. Candidates become rejected and are flagged for retraining.
- add_missed: the reviewer marks a defect the model did not find. A human defect is added
              as confirmed; remaining candidates are rejected and flagged, because the model
              pointed at the wrong place.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import transitions
from app.domain.enums import DefectOrigin, DefectStatus, ReviewDecision, ReviewStatus
from app.domain.models import Defect, Event, ReviewTask


class TaskNotFound(LookupError):
    pass


class TaskAlreadyDecided(RuntimeError):
    pass


@dataclass(frozen=True)
class MissedDefect:
    defect_type: str
    bbox: tuple[float, float, float, float]


def decide(
    session: Session,
    task_id: int,
    *,
    decision: ReviewDecision,
    reviewer: str,
    missed: MissedDefect | None = None,
) -> ReviewTask:
    if (decision is ReviewDecision.ADD_MISSED) != (missed is not None):
        raise ValueError("missed defect is required for add_missed and only allowed there")

    # Row lock so two reviewers cannot decide the same task concurrently (PostgreSQL;
    # SQLite ignores FOR UPDATE, which is fine for single-process tests).
    task = session.scalar(select(ReviewTask).where(ReviewTask.id == task_id).with_for_update())
    if task is None:
        raise TaskNotFound(task_id)
    if task.status is not ReviewStatus.PENDING:
        raise TaskAlreadyDecided(task_id)

    now = datetime.now(timezone.utc)
    candidates = [d for d in task.inspection.defects if d.status is DefectStatus.CANDIDATE]

    if decision is ReviewDecision.CONFIRM:
        for d in candidates:
            _move_defect(session, d, DefectStatus.CONFIRMED, reviewer, now)
    else:
        for d in candidates:
            _move_defect(session, d, DefectStatus.REJECTED, reviewer, now)
            d.retrain_candidate = True

    if missed is not None:
        human = Defect(
            inspection=task.inspection,
            defect_type=missed.defect_type,
            confidence=None,
            bbox=list(missed.bbox),
            origin=DefectOrigin.HUMAN,
            status=DefectStatus.CONFIRMED,
        )
        session.add(human)
        session.flush()
        session.add(_event("defect", human.id, "added_by_reviewer", reviewer, now, {"bbox": list(missed.bbox)}))

    transitions.check(task.status, ReviewStatus.DONE)
    task.status = ReviewStatus.DONE
    task.decision = decision
    task.reviewer = reviewer
    task.decided_at = now
    session.add(
        _event(
            "review_task",
            task.id,
            f"decided:{decision.value}",
            reviewer,
            now,
            {"inspection_id": task.inspection_id, "reason": task.reason.value, "candidates": len(candidates)},
        )
    )
    session.commit()
    return task


def list_tasks(session: Session, status: ReviewStatus, limit: int) -> list[ReviewTask]:
    """Oldest first, so the queue is worked in arrival order."""
    stmt = (
        select(ReviewTask)
        .where(ReviewTask.status == status)
        .order_by(ReviewTask.created_at, ReviewTask.id)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _move_defect(session: Session, defect: Defect, target: DefectStatus, actor: str, at: datetime) -> None:
    transitions.check(defect.status, target)
    defect.status = target
    session.add(_event("defect", defect.id, target.value, actor, at, {}))


def _event(object_type: str, object_id: int, event: str, actor: str, at: datetime, payload: dict) -> Event:
    return Event(object_type=object_type, object_id=object_id, event=event, actor=actor, at=at, payload=payload)
