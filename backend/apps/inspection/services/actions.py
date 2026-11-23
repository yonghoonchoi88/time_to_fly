"""Field actions and their effect on lot status.

Lot effects (see docs/ontology.md):
- hold_lot:    the lot goes on_hold as soon as the action is opened. Containment must not
               wait for paperwork.
- release_lot: allowed only for a held lot; the lot is released when the action is done,
               i.e. after the recheck it stands for has actually happened.
- recheck, stop_line: tracked work with no lot status change.
Cancelling an action never reverts lot status; a held lot leaves hold only via release_lot.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ..domain import transitions
from ..enums import ActionStatus, ActionType, DefectStatus, LotStatus
from ..models import Action, Defect, Lot
from . import events
from .errors import Conflict, Invalid, NotFound

CLOSED = {ActionStatus.DONE, ActionStatus.CANCELLED}


@transaction.atomic
def open_action(
    *,
    lot_code: str,
    action_type: str,
    owner: str,
    actor: str,
    defect_id: int | None = None,
    note: str = "",
) -> Action:
    """Open a field action. ``owner`` does the work; ``actor`` is who ordered it."""
    if action_type not in ActionType.values:
        raise Invalid(f"unknown action type {action_type!r}")
    # Lock the lot row: two supervisors holding or releasing the same lot must serialise.
    lot = Lot.objects.select_for_update().filter(code=lot_code).first()
    if lot is None:
        raise NotFound(f"lot {lot_code!r}")

    defect = None
    if defect_id is not None:
        defect = Defect.objects.select_related("inspection").filter(pk=defect_id).first()
        if defect is None or defect.inspection.lot_id != lot.pk:
            raise Invalid(f"defect {defect_id} does not belong to lot {lot_code!r}")
        if defect.status != DefectStatus.CONFIRMED:
            raise Invalid(f"defect {defect_id} is {defect.status}; only confirmed defects drive actions")

    now = timezone.now()
    if action_type == ActionType.HOLD_LOT:
        _move_lot(lot, LotStatus.ON_HOLD, actor, now)
    elif action_type == ActionType.RELEASE_LOT and lot.status != LotStatus.ON_HOLD:
        raise Conflict(f"lot {lot_code!r} is {lot.status}; only a held lot can be released")

    action = Action.objects.create(
        lot=lot, defect=defect, action_type=action_type, owner=owner, note=note, opened_at=now
    )
    events.record(
        lot=lot, object_type="action", object_id=action.pk, event=f"opened:{action_type}",
        actor=actor, at=now, payload={"owner": owner, "defect_id": defect_id},
    )
    return action


@transaction.atomic
def change_status(action_id: int, *, target: str, actor: str, note: str = "") -> Action:
    if target not in ActionStatus.values:
        raise Invalid(f"unknown action status {target!r}")
    target = ActionStatus(target)
    action = Action.objects.select_for_update().filter(pk=action_id).first()
    if action is None:
        raise NotFound(f"action {action_id}")
    try:
        transitions.check(action.status, target)
    except transitions.InvalidTransition as exc:
        raise Conflict(str(exc)) from exc

    now = timezone.now()
    previous = action.status
    lot = Lot.objects.select_for_update().get(pk=action.lot_id)
    if target == ActionStatus.DONE and action.action_type == ActionType.RELEASE_LOT:
        _move_lot(lot, LotStatus.RELEASED, actor, now)

    action.status = target
    if note:
        action.note = f"{action.note}\n{note}".strip()
    if target in CLOSED:
        action.closed_at = now
    action.save(update_fields=["status", "note", "closed_at"])
    payload = {"from": previous}
    if note:
        payload["note"] = note
    events.record(
        lot=lot, object_type="action", object_id=action.pk, event=str(target),
        actor=actor, at=now, payload=payload,
    )
    return action


def _move_lot(lot: Lot, target: LotStatus, actor: str, at) -> None:
    try:
        transitions.check(lot.status, target)
    except transitions.InvalidTransition as exc:
        raise Conflict(f"lot {lot.code!r} is {lot.status}; cannot move to {target}") from exc
    previous = lot.status
    lot.status = target
    lot.save(update_fields=["status"])
    events.record(
        lot=lot, object_type="lot", object_id=lot.pk, event=str(target),
        actor=actor, at=at, payload={"from": previous},
    )
