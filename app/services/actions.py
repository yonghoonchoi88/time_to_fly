"""Field actions and their effect on lot status.

Lot effects (v0.1, see docs/ontology.md):
- hold_lot:    the lot goes on_hold as soon as the action is opened. Containment must not
               wait for paperwork.
- release_lot: allowed only for a held lot; the lot is released when the action is done,
               i.e. after the recheck it stands for has actually happened.
- recheck, stop_line: tracked work with no lot status change.
Cancelling an action never reverts lot status; a held lot leaves hold only via release_lot.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import transitions
from app.domain.enums import ActionStatus, ActionType, DefectStatus, LotStatus
from app.domain.models import Action, Defect, Event, Lot


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    """The request is valid but the current state does not allow it (HTTP 409)."""


class Invalid(ValueError):
    """The request refers to objects that do not fit together (HTTP 422)."""


def open_action(
    session: Session,
    *,
    lot_code: str,
    action_type: ActionType,
    owner: str,
    defect_id: int | None = None,
    note: str = "",
) -> Action:
    # Lock the lot row: two supervisors holding or releasing the same lot must serialise.
    lot = session.scalar(select(Lot).where(Lot.code == lot_code).with_for_update())
    if lot is None:
        raise NotFound(f"lot {lot_code!r}")

    defect = None
    if defect_id is not None:
        defect = session.get(Defect, defect_id)
        if defect is None or defect.inspection.lot_id != lot.id:
            raise Invalid(f"defect {defect_id} does not belong to lot {lot_code!r}")
        if defect.status is not DefectStatus.CONFIRMED:
            raise Invalid(f"defect {defect_id} is {defect.status.value}; only confirmed defects drive actions")

    now = datetime.now(timezone.utc)
    if action_type is ActionType.HOLD_LOT:
        _move_lot(session, lot, LotStatus.ON_HOLD, owner, now)
    elif action_type is ActionType.RELEASE_LOT and lot.status is not LotStatus.ON_HOLD:
        raise Conflict(f"lot {lot_code!r} is {lot.status.value}; only a held lot can be released")

    action = Action(lot=lot, defect=defect, action_type=action_type, owner=owner, note=note, opened_at=now)
    session.add(action)
    session.flush()
    session.add(
        Event(
            object_type="action",
            object_id=action.id,
            event=f"opened:{action_type.value}",
            actor=owner,
            at=now,
            payload={"lot_code": lot.code, "defect_id": defect_id},
        )
    )
    session.commit()
    return action


def change_status(session: Session, action_id: int, *, target: ActionStatus, actor: str, note: str = "") -> Action:
    action = session.scalar(select(Action).where(Action.id == action_id).with_for_update())
    if action is None:
        raise NotFound(f"action {action_id}")
    try:
        transitions.check(action.status, target)
    except transitions.InvalidTransition as exc:
        raise Conflict(str(exc)) from exc

    now = datetime.now(timezone.utc)
    previous = action.status
    action.status = target
    if note:
        action.note = f"{action.note}\n{note}".strip()
    if target in (ActionStatus.DONE, ActionStatus.CANCELLED):
        action.closed_at = now

    if target is ActionStatus.DONE and action.action_type is ActionType.RELEASE_LOT:
        lot = session.scalar(select(Lot).where(Lot.id == action.lot_id).with_for_update())
        _move_lot(session, lot, LotStatus.RELEASED, actor, now)

    session.add(
        Event(
            object_type="action",
            object_id=action.id,
            event=target.value,
            actor=actor,
            at=now,
            payload={"from": previous.value, "note": note} if note else {"from": previous.value},
        )
    )
    session.commit()
    return action


def list_actions(
    session: Session, *, status: ActionStatus | None, lot_code: str | None, limit: int
) -> list[Action]:
    stmt = select(Action).order_by(Action.opened_at, Action.id).limit(limit)
    if status is not None:
        stmt = stmt.where(Action.status == status)
    if lot_code is not None:
        stmt = stmt.join(Lot).where(Lot.code == lot_code)
    return list(session.scalars(stmt))


def _move_lot(session: Session, lot: Lot, target: LotStatus, actor: str, at: datetime) -> None:
    try:
        transitions.check(lot.status, target)
    except transitions.InvalidTransition as exc:
        raise Conflict(f"lot {lot.code!r} is {lot.status.value}; cannot move to {target.value}") from exc
    previous = lot.status
    lot.status = target
    session.add(Event(object_type="lot", object_id=lot.id, event=target.value, actor=actor, at=at,
                      payload={"from": previous.value}))
