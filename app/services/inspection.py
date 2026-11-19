"""Runs one image through an engine, routes the result, and persists the ontology objects."""

import random
import time
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from app.domain.enums import DefectOrigin, DefectStatus, InspectionSource, ReviewReason
from app.domain.models import Defect, Event, Inspection, Lot, ModelVersion, ReviewTask
from app.domain.routing import Thresholds, route
from app.engines.base import InspectionEngine

SYSTEM = "system"


def record_inspection(
    session: Session,
    *,
    lot: Lot,
    model_version: ModelVersion,
    engine: InspectionEngine,
    image: np.ndarray,
    image_uri: str,
    captured_at: datetime,
    source: InspectionSource,
    rng: random.Random,
) -> Inspection:
    """Inspect one image and write Inspection, Defect, ReviewTask and Event rows in one transaction."""
    if engine.name != model_version.engine:
        raise ValueError(f"engine '{engine.name}' does not match model version '{model_version.engine}'")

    started = time.perf_counter()
    candidates = engine.detect(image)
    decision = route(
        candidates,
        Thresholds(model_version.auto_ng_conf, model_version.review_conf, model_version.audit_rate),
        rng,
    )
    latency_ms = (time.perf_counter() - started) * 1000

    inspection = Inspection(
        lot=lot,
        model_version=model_version,
        image_uri=image_uri,
        image_width=int(image.shape[1]),
        image_height=int(image.shape[0]),
        source=source,
        captured_at=captured_at,
        verdict=decision.verdict,
        latency_ms=latency_ms,
        is_audit_sample=decision.review_reason is ReviewReason.AUDIT_SAMPLE,
    )
    session.add(inspection)

    auto = set(decision.auto_confirmed)
    for c in candidates:
        # Sub-threshold candidates are kept as candidates so thresholds can be re-evaluated later.
        session.add(
            Defect(
                inspection=inspection,
                defect_type=c.defect_type,
                confidence=c.confidence,
                bbox=list(c.bbox) if c.bbox else None,
                origin=DefectOrigin.MODEL,
                status=DefectStatus.CONFIRMED if c in auto else DefectStatus.CANDIDATE,
            )
        )

    if decision.review_reason is not None:
        session.add(ReviewTask(inspection=inspection, reason=decision.review_reason))

    session.flush()  # assign ids before writing events
    session.add(
        Event(
            object_type="inspection",
            object_id=inspection.id,
            event=f"inspected:{decision.verdict.value}",
            actor=SYSTEM,
            payload={
                "candidates": len(candidates),
                "review_reason": decision.review_reason.value if decision.review_reason else None,
                "latency_ms": round(latency_ms, 3),
            },
        )
    )
    session.commit()
    return inspection
