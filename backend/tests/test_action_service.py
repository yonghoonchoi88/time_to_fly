"""Field actions and lot containment."""
import pytest

from apps.inspection.enums import ActionStatus, ActionType, DefectStatus, LotStatus
from apps.inspection.models import Lot
from apps.inspection.services import actions
from apps.inspection.services.errors import Conflict, Invalid, NotFound

pytestmark = pytest.mark.django_db


def lot_status(code="S01"):
    return Lot.objects.get(code=code).status


def open_(action_type, lot_code="S01", **kw):
    return actions.open_action(lot_code=lot_code, action_type=action_type, owner="park", actor="lead", **kw)


def advance(action, *targets):
    for target in targets:
        action = actions.change_status(action.pk, target=target, actor="park")
    return action


def test_hold_takes_effect_when_opened(inspected):
    inspected(0.9)
    action = open_(ActionType.HOLD_LOT)
    assert action.status == ActionStatus.OPEN
    assert lot_status() == LotStatus.ON_HOLD


def test_release_takes_effect_only_when_done(inspected):
    inspected(0.9)
    open_(ActionType.HOLD_LOT)
    release = open_(ActionType.RELEASE_LOT)
    assert lot_status() == LotStatus.ON_HOLD

    release = advance(release, ActionStatus.IN_PROGRESS, ActionStatus.DONE)
    assert release.closed_at is not None
    assert lot_status() == LotStatus.RELEASED


def test_release_of_an_open_lot_is_a_conflict(inspected):
    inspected(0.9)
    with pytest.raises(Conflict):
        open_(ActionType.RELEASE_LOT)


def test_second_hold_is_a_conflict(inspected):
    inspected(0.9)
    open_(ActionType.HOLD_LOT)
    with pytest.raises(Conflict):
        open_(ActionType.HOLD_LOT)


def test_cancel_does_not_revert_the_hold(inspected):
    inspected(0.9)
    hold = open_(ActionType.HOLD_LOT)
    advance(hold, ActionStatus.CANCELLED)
    assert lot_status() == LotStatus.ON_HOLD


def test_skipping_in_progress_is_a_conflict(inspected):
    inspected(0.9)
    recheck = open_(ActionType.RECHECK)
    with pytest.raises(Conflict):
        advance(recheck, ActionStatus.DONE)


def test_action_can_reference_a_confirmed_defect_of_the_same_lot(inspected):
    defect = inspected(0.9).defects.get(status=DefectStatus.CONFIRMED)
    action = open_(ActionType.HOLD_LOT, defect_id=defect.pk)
    assert action.defect == defect


def test_defect_from_another_lot_is_invalid(inspected):
    other = inspected(0.9, lot_code="S02").defects.get()
    inspected(0.9, lot_code="S01")
    with pytest.raises(Invalid):
        open_(ActionType.HOLD_LOT, lot_code="S01", defect_id=other.pk)


def test_unconfirmed_defect_cannot_drive_an_action(inspected):
    candidate = inspected(0.5).defects.get()
    with pytest.raises(Invalid):
        open_(ActionType.RECHECK, defect_id=candidate.pk)


def test_unknown_lot_and_type(inspected):
    inspected(0.9)
    with pytest.raises(NotFound):
        open_(ActionType.HOLD_LOT, lot_code="nope")
    with pytest.raises(Invalid):
        open_("quarantine")
