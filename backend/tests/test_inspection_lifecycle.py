"""received -> completed / failed, as driven by the intake endpoint and the Celery worker."""
import pytest

from apps.inspection.enums import DefectStatus, InspectionStatus, ReviewReason, Verdict
from apps.inspection.models import Defect, Event, Lot, ModelVersion, ReviewTask
from apps.inspection.services.errors import Invalid
from apps.inspection.services.inspections import complete_inspection, fail_inspection, receive_inspection

pytestmark = pytest.mark.django_db


def test_receive_creates_queued_row_lot_and_event(receive):
    inspection = receive(lot_code="S07")

    assert inspection.status == InspectionStatus.QUEUED
    assert inspection.verdict is None
    assert inspection.model_version.name == "mock-0"
    assert Lot.objects.get(code="S07").line.name == "line-1"
    event = Event.objects.get(object_type="inspection", object_id=inspection.pk)
    assert (event.event, event.actor, event.lot.code) == ("received", "line-replay", "S07")


def test_receive_rejects_unknown_source():
    with pytest.raises(Invalid):
        receive_inspection(lot_code="S01", image_path="x.jpg", source="webcam", actor="t")


def test_high_confidence_is_recorded_as_ng_with_confirmed_defect(inspected):
    inspection = inspected(0.9, 0.1)

    assert inspection.status == InspectionStatus.DONE
    assert inspection.verdict == Verdict.NG
    assert (inspection.image_width, inspection.image_height, inspection.engine_latency_ms) == (640, 480, 12.5)
    statuses = sorted(inspection.defects.values_list("confidence", "status"))
    # The sub-threshold candidate is kept so thresholds can be re-evaluated later.
    assert statuses == [(0.1, DefectStatus.CANDIDATE), (0.9, DefectStatus.CONFIRMED)]
    assert not inspection.review_tasks.exists()


def test_mid_confidence_queues_a_review_task(inspected):
    inspection = inspected(0.5)

    assert inspection.verdict == Verdict.REVIEW
    task = inspection.review_tasks.get()
    assert task.reason == ReviewReason.LOW_CONFIDENCE
    event = Event.objects.get(object_type="inspection", object_id=inspection.pk, event="inspected:REVIEW")
    assert event.payload["review_task_id"] == task.pk


def test_ok_verdict_is_audit_sampled_at_the_configured_rate(inspected):
    ModelVersion.objects.filter(name="mock-0").update(audit_rate=1.0)
    inspection = inspected()

    assert inspection.verdict == Verdict.OK
    assert inspection.is_audit_sample
    assert inspection.review_tasks.get().reason == ReviewReason.AUDIT_SAMPLE


def test_ok_verdict_without_audit_needs_no_review(inspected):
    ModelVersion.objects.filter(name="mock-0").update(audit_rate=0.0)
    inspection = inspected(0.1)

    assert inspection.verdict == Verdict.OK
    assert not inspection.is_audit_sample
    assert not inspection.review_tasks.exists()


def test_redelivered_task_does_not_duplicate_rows(receive, prediction):
    inspection = receive()
    complete_inspection(inspection.pk, prediction(0.5))
    complete_inspection(inspection.pk, prediction(0.9))  # acks_late redelivery

    inspection.refresh_from_db()
    assert inspection.verdict == Verdict.REVIEW
    assert Defect.objects.filter(inspection=inspection).count() == 1
    assert ReviewTask.objects.filter(inspection=inspection).count() == 1


def test_wrong_served_model_fails_the_inspection_instead_of_recording_it(receive, prediction):
    inspection = complete_inspection(receive().pk, prediction(0.9, engine="yolo", version="yolo-2"))

    assert inspection.status == InspectionStatus.FAILED
    assert "yolo/yolo-2" in inspection.failure_reason
    assert not inspection.defects.exists()
    assert Event.objects.filter(object_id=inspection.pk, event="failed").exists()


def test_fail_marks_the_frame_and_is_final(receive, prediction):
    inspection = fail_inspection(receive().pk, "AI server rejected the request (422): not an image")
    assert inspection.status == InspectionStatus.FAILED

    # A late success must not overwrite the recorded failure.
    after = complete_inspection(inspection.pk, prediction(0.9))
    assert after.status == InspectionStatus.FAILED
    assert not after.defects.exists()
