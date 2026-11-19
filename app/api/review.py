"""Review queue endpoints. Contract: docs/api.md."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import DecisionIn, ReviewTaskOut
from app.db import get_session
from app.domain.enums import ReviewDecision, ReviewStatus
from app.services.review import MissedDefect, TaskAlreadyDecided, TaskNotFound, decide, list_tasks

router = APIRouter(tags=["review"])


@router.get("/review-tasks", response_model=list[ReviewTaskOut])
def get_review_tasks(
    status: ReviewStatus = ReviewStatus.PENDING,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ReviewTaskOut]:
    return [ReviewTaskOut.of(t) for t in list_tasks(session, status, limit)]


@router.post("/review-tasks/{task_id}/decision", response_model=ReviewTaskOut)
def post_decision(
    task_id: int,
    body: DecisionIn,
    session: Session = Depends(get_session),
) -> ReviewTaskOut:
    missed = None
    if body.decision is ReviewDecision.ADD_MISSED:
        missed = MissedDefect(body.defect_type, tuple(body.bbox))
    try:
        task = decide(session, task_id, decision=body.decision, reviewer=body.reviewer, missed=missed)
    except TaskNotFound:
        raise HTTPException(404, "review task not found")
    except TaskAlreadyDecided:
        raise HTTPException(409, "review task is already decided")
    return ReviewTaskOut.of(task)
