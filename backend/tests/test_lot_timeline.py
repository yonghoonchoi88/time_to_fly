"""The whole loop on one lot, read back as its timeline (#8)."""
import pytest

from apps.inspection.enums import ActionStatus, ActionType, ReviewDecision
from apps.inspection.services import actions, review
from apps.inspection.services.errors import NotFound
from apps.inspection.services.inspections import complete_inspection
from apps.inspection.services.timeline import lot_timeline

pytestmark = pytest.mark.django_db


def test_detection_to_action_reads_back_in_order(receive, prediction, reviewer):
    inspection = receive(lot_code="S01")
    complete_inspection(inspection.pk, prediction(0.5))
    task = inspection.review_tasks.get()
    review.decide(task.pk, decision=ReviewDecision.CONFIRM, reviewer=reviewer)
    defect = inspection.defects.get()
    hold = actions.open_action(lot_code="S01", action_type=ActionType.HOLD_LOT, owner="park", actor="lead",
                               defect_id=defect.pk)
    actions.change_status(hold.pk, target=ActionStatus.IN_PROGRESS, actor="park")
    actions.change_status(hold.pk, target=ActionStatus.DONE, actor="park")

    # Another lot's history must not leak in.
    complete_inspection(receive(lot_code="S02").pk, prediction(0.9))

    timeline = [(e.object_type, e.event, e.actor) for e in lot_timeline("S01")]
    assert timeline == [
        ("inspection", "received", "line-replay"),
        ("inspection", "inspected:REVIEW", "system"),
        ("defect", "confirmed", "kim"),
        ("review_task", "decided:confirm", "kim"),
        ("lot", "on_hold", "lead"),
        ("action", "opened:hold_lot", "lead"),
        ("action", "in_progress", "park"),
        ("action", "done", "park"),
    ]


def test_unknown_lot_has_no_timeline():
    with pytest.raises(NotFound):
        lot_timeline("nope")
