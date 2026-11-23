"""Inspection lifecycle: received -> completed (verdict) or failed.

The web process only stores the frame and creates a ``queued`` row; the Celery worker
calls the inference server and then ``complete_inspection``. Splitting it this way lets
the intake endpoint answer 202 at once, whatever the inference load.
"""
from __future__ import annotations

import random
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from ..domain.routing import Candidate, Thresholds, route
from ..enums import DefectOrigin, DefectStatus, InspectionSource, InspectionStatus, ReviewReason
from ..models import Defect, Inspection, ReviewTask
from . import catalog, events
from .errors import Invalid, NotFound

FAILURE_REASON_LEN = 255


@transaction.atomic
def receive_inspection(
    *,
    lot_code: str,
    image_path: str,
    source: str,
    actor: str,
    captured_at: datetime | None = None,
) -> Inspection:
    """Record that a frame arrived. The verdict is filled in later by the worker."""
    if source not in InspectionSource.values:
        raise Invalid(f"unknown source {source!r}")
    model_version = catalog.active_model_version()
    lot = catalog.lot_by_code(lot_code)
    now = timezone.now()
    inspection = Inspection.objects.create(
        lot=lot,
        model_version=model_version,
        image_path=image_path,
        source=source,
        captured_at=captured_at or now,
        received_at=now,
    )
    events.record(
        lot=lot,
        object_type="inspection",
        object_id=inspection.pk,
        event="received",
        actor=actor,
        at=now,
        payload={"model_version": model_version.name, "source": source},
    )
    return inspection


@transaction.atomic
def complete_inspection(inspection_id: int, prediction: Mapping[str, Any]) -> Inspection:
    """Route the inference result and write Defect, ReviewTask and Event rows.

    ``prediction`` is the inference server's /predict body (apps.ai_gateway Prediction as a
    dict). Safe to call twice: the worker acknowledges tasks late, so a redelivered task
    finds the row already completed and changes nothing.
    """
    inspection = _lock(inspection_id)
    if inspection.status != InspectionStatus.QUEUED:
        return inspection

    model_version = inspection.model_version
    served = (prediction.get("engine"), prediction.get("version"))
    expected = (model_version.engine, model_version.name)
    if served != expected:
        # Recording these candidates under the wrong version would corrupt version comparisons.
        return _fail(
            inspection,
            f"model version mismatch: server runs {served[0]}/{served[1]}, expected {expected[0]}/{expected[1]}",
        )

    candidates = [_candidate(c) for c in prediction.get("candidates", [])]
    thresholds = Thresholds(model_version.auto_ng_conf, model_version.review_conf, model_version.audit_rate)
    # Seeded per inspection, so a retried task makes the same audit-sampling choice.
    rng = random.Random(f"{model_version.pk}:{inspection.pk}")
    decision = route(candidates, thresholds, rng)

    now = timezone.now()
    inspection.status = InspectionStatus.DONE
    inspection.verdict = decision.verdict
    inspection.image_width = int(prediction["width"])
    inspection.image_height = int(prediction["height"])
    inspection.engine_latency_ms = float(prediction["latency_ms"])
    inspection.is_audit_sample = decision.review_reason == ReviewReason.AUDIT_SAMPLE
    inspection.completed_at = now
    inspection.save()

    auto = set(decision.auto_confirmed)
    for c in candidates:
        # Sub-threshold candidates are kept so thresholds can be re-evaluated later.
        Defect.objects.create(
            inspection=inspection,
            defect_type=c.defect_type,
            confidence=c.confidence,
            bbox=list(c.bbox) if c.bbox else None,
            origin=DefectOrigin.MODEL,
            status=DefectStatus.CONFIRMED if c in auto else DefectStatus.CANDIDATE,
        )

    review_task = None
    if decision.review_reason is not None:
        review_task = ReviewTask.objects.create(inspection=inspection, reason=decision.review_reason, created_at=now)

    events.record(
        lot=inspection.lot,
        object_type="inspection",
        object_id=inspection.pk,
        event=f"inspected:{decision.verdict}",
        actor=events.SYSTEM_ACTOR,
        at=now,
        payload={
            "candidates": len(candidates),
            "review_reason": decision.review_reason.value if decision.review_reason else None,
            "review_task_id": review_task.pk if review_task else None,
            "engine_latency_ms": inspection.engine_latency_ms,
        },
    )
    return inspection


@transaction.atomic
def fail_inspection(inspection_id: int, reason: str) -> Inspection:
    """Mark a frame that could not be inspected, so it is visible instead of silently lost."""
    inspection = _lock(inspection_id)
    if inspection.status != InspectionStatus.QUEUED:
        return inspection
    return _fail(inspection, reason)


def _fail(inspection: Inspection, reason: str) -> Inspection:
    now = timezone.now()
    inspection.status = InspectionStatus.FAILED
    inspection.failure_reason = reason[:FAILURE_REASON_LEN]
    inspection.completed_at = now
    inspection.save(update_fields=["status", "failure_reason", "completed_at"])
    events.record(
        lot=inspection.lot,
        object_type="inspection",
        object_id=inspection.pk,
        event="failed",
        actor=events.SYSTEM_ACTOR,
        at=now,
        payload={"reason": inspection.failure_reason},
    )
    return inspection


def _lock(inspection_id: int) -> Inspection:
    # Row lock: a redelivered task and the original must not complete the same row twice.
    inspection = (
        Inspection.objects.select_for_update().select_related("model_version", "lot").filter(pk=inspection_id).first()
    )
    if inspection is None:
        raise NotFound(f"inspection {inspection_id}")
    return inspection


def _candidate(raw: Mapping[str, Any]) -> Candidate:
    bbox = raw.get("bbox")
    return Candidate(
        defect_type=str(raw["defect_type"]),
        confidence=float(raw["confidence"]),
        bbox=tuple(float(v) for v in bbox) if bbox else None,
    )
