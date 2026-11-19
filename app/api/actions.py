"""Field action endpoints. Contract: docs/api.md."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas import ActionIn, ActionOut, ActionStatusIn
from app.db import get_session
from app.domain.enums import ActionStatus
from app.services import actions as svc

router = APIRouter(tags=["actions"])


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


@router.post("/actions", status_code=status.HTTP_201_CREATED, response_model=ActionOut)
def create_action(body: ActionIn, session: Session = Depends(get_session)) -> ActionOut:
    try:
        action = svc.open_action(
            session,
            lot_code=body.lot_code,
            action_type=body.action_type,
            owner=body.owner,
            defect_id=body.defect_id,
            note=body.note,
        )
    except (svc.NotFound, svc.Conflict, svc.Invalid) as exc:
        session.rollback()
        raise _http(exc)
    return ActionOut.of(action)


@router.post("/actions/{action_id}/status", response_model=ActionOut)
def update_action_status(action_id: int, body: ActionStatusIn, session: Session = Depends(get_session)) -> ActionOut:
    try:
        action = svc.change_status(session, action_id, target=body.status, actor=body.actor, note=body.note)
    except (svc.NotFound, svc.Conflict) as exc:
        session.rollback()
        raise _http(exc)
    return ActionOut.of(action)


@router.get("/actions", response_model=list[ActionOut])
def get_actions(
    status: ActionStatus | None = None,
    lot_code: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[ActionOut]:
    return [ActionOut.of(a) for a in svc.list_actions(session, status=status, lot_code=lot_code, limit=limit)]
