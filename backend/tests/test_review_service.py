"""Reviewer decisions: low-confidence tasks and audit samples have different meanings."""
import pytest

from apps.inspection.enums import DefectOrigin, DefectStatus, ReviewDecision, ReviewStatus
from apps.inspection.models import Event, ModelVersion
from apps.inspection.services import review
from apps.inspection.services.errors import Conflict, Invalid, NotFound
from apps.inspection.services.review import MissedDefect

pytestmark = pytest.mark.django_db

MISSED = MissedDefect("foreign_object", (100.0, 120.0, 30.0, 25.0))


@pytest.fixture
def low_conf_task(inspected):
    return inspected(0.5, 0.4).review_tasks.get()


@pytest.fixture
def audit_task(inspected):
    ModelVersion.objects.filter(name="mock-0").update(audit_rate=1.0)
    return inspected(0.1).review_tasks.get()  # OK verdict with one sub-threshold candidate


def defect_states(task):
    return sorted(task.inspection.defects.values_list("origin", "status", "retrain_candidate"))


def test_confirm_low_confidence_confirms_candidates(low_conf_task, reviewer):
    task = review.decide(low_conf_task.pk, decision=ReviewDecision.CONFIRM, reviewer=reviewer)

    assert (task.status, task.decision, task.reviewer) == (ReviewStatus.DONE, ReviewDecision.CONFIRM, reviewer)
    assert task.decided_at is not None
    assert defect_states(task) == [(DefectOrigin.MODEL, DefectStatus.CONFIRMED, False)] * 2


def test_reject_flags_candidates_for_retraining(low_conf_task, reviewer):
    task = review.decide(low_conf_task.pk, decision=ReviewDecision.REJECT, reviewer=reviewer)
    assert defect_states(task) == [(DefectOrigin.MODEL, DefectStatus.REJECTED, True)] * 2


def test_add_missed_adds_human_defect_and_flags_model_candidates(low_conf_task, reviewer):
    task = review.decide(low_conf_task.pk, decision=ReviewDecision.ADD_MISSED, reviewer=reviewer, missed=MISSED)

    assert defect_states(task) == [
        (DefectOrigin.HUMAN, DefectStatus.CONFIRMED, False),
        (DefectOrigin.MODEL, DefectStatus.REJECTED, True),
        (DefectOrigin.MODEL, DefectStatus.REJECTED, True),
    ]
    human = task.inspection.defects.get(origin=DefectOrigin.HUMAN)
    assert human.confidence is None
    assert human.bbox == [100.0, 120.0, 30.0, 25.0]


def test_confirm_on_audit_sample_means_the_ok_verdict_was_right(audit_task, reviewer):
    task = review.decide(audit_task.pk, decision=ReviewDecision.CONFIRM, reviewer=reviewer)
    # The weak candidate was correctly ignored by routing: rejected, nothing to retrain.
    assert defect_states(task) == [(DefectOrigin.MODEL, DefectStatus.REJECTED, False)]


def test_reject_is_not_allowed_on_audit_sample(audit_task, reviewer):
    with pytest.raises(Invalid):
        review.decide(audit_task.pk, decision=ReviewDecision.REJECT, reviewer=reviewer)


def test_add_missed_on_audit_sample_records_a_false_negative(audit_task, reviewer):
    task = review.decide(audit_task.pk, decision=ReviewDecision.ADD_MISSED, reviewer=reviewer, missed=MISSED)
    assert task.inspection.defects.filter(origin=DefectOrigin.HUMAN, status=DefectStatus.CONFIRMED).count() == 1


def test_decision_is_final(low_conf_task, reviewer):
    review.decide(low_conf_task.pk, decision=ReviewDecision.CONFIRM, reviewer=reviewer)
    with pytest.raises(Conflict):
        review.decide(low_conf_task.pk, decision=ReviewDecision.REJECT, reviewer=reviewer)


@pytest.mark.parametrize(
    "decision,missed",
    [(ReviewDecision.ADD_MISSED, None), (ReviewDecision.CONFIRM, MISSED), ("approve", None)],
)
def test_inconsistent_requests_are_invalid(low_conf_task, reviewer, decision, missed):
    with pytest.raises(Invalid):
        review.decide(low_conf_task.pk, decision=decision, reviewer=reviewer, missed=missed)


def test_unknown_task_is_not_found(reviewer):
    with pytest.raises(NotFound):
        review.decide(999, decision=ReviewDecision.CONFIRM, reviewer=reviewer)


@pytest.mark.parametrize("bbox", [(0, 0, 0, 10), (-1, 0, 5, 5), (1, 2, 3)])
def test_degenerate_missed_box_is_invalid(bbox):
    with pytest.raises(Invalid):
        MissedDefect("foreign_object", bbox)


def test_decision_events_name_the_reviewer(low_conf_task, reviewer):
    review.decide(low_conf_task.pk, decision=ReviewDecision.REJECT, reviewer=reviewer)
    events = Event.objects.filter(lot=low_conf_task.inspection.lot, actor="kim")
    assert sorted(events.values_list("event", flat=True)) == ["decided:reject", "rejected", "rejected"]


def test_pending_tasks_are_oldest_first(inspected, reviewer):
    first = inspected(0.5).review_tasks.get()
    second = inspected(0.6).review_tasks.get()
    assert list(review.pending_tasks()) == [first, second]

    review.decide(first.pk, decision=ReviewDecision.CONFIRM, reviewer=reviewer)
    assert list(review.pending_tasks()) == [second]
