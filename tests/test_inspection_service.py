import random
from datetime import datetime, timezone

import numpy as np
import pytest
from sqlalchemy import select

from app.domain.enums import DefectStatus, InspectionSource, ReviewReason, Verdict
from app.domain.models import Defect, Event, ReviewTask
from app.engines.base import DefectCandidate
from app.services.inspection import record_inspection

IMG = np.zeros((480, 640, 3), dtype=np.uint8)
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


class FixedEngine:
    name = "mock"

    def __init__(self, candidates):
        self._candidates = candidates

    def detect(self, image):
        return list(self._candidates)


def run(session, lot, mv, candidates, audit_rate=None):
    if audit_rate is not None:
        mv.audit_rate = audit_rate
    return record_inspection(
        session,
        lot=lot,
        model_version=mv,
        engine=FixedEngine(candidates),
        image=IMG,
        image_uri="replay://session-01/0001.jpg",
        captured_at=NOW,
        source=InspectionSource.REPLAY,
        rng=random.Random(0),
    )


def test_auto_ng_stores_confirmed_and_candidate_defects(session, lot, mock_version):
    insp = run(session, lot, mock_version, [DefectCandidate("foreign_object", 0.9), DefectCandidate("foreign_object", 0.1)])
    assert insp.verdict is Verdict.NG
    statuses = sorted(d.status for d in session.scalars(select(Defect)))
    assert statuses == [DefectStatus.CANDIDATE, DefectStatus.CONFIRMED]
    assert session.scalars(select(ReviewTask)).all() == []


def test_mid_confidence_creates_review_task(session, lot, mock_version):
    insp = run(session, lot, mock_version, [DefectCandidate("foreign_object", 0.5)])
    assert insp.verdict is Verdict.REVIEW
    task = session.scalars(select(ReviewTask)).one()
    assert task.reason is ReviewReason.LOW_CONFIDENCE


def test_audit_sample_is_flagged(session, lot, mock_version):
    insp = run(session, lot, mock_version, [], audit_rate=1.0)
    assert insp.verdict is Verdict.OK
    assert insp.is_audit_sample
    assert session.scalars(select(ReviewTask)).one().reason is ReviewReason.AUDIT_SAMPLE


def test_every_inspection_writes_an_event(session, lot, mock_version):
    insp = run(session, lot, mock_version, [], audit_rate=0.0)
    ev = session.scalars(select(Event)).one()
    assert (ev.object_type, ev.object_id, ev.event) == ("inspection", insp.id, "inspected:OK")
    assert insp.latency_ms >= 0


def test_engine_must_match_model_version(session, lot, mock_version):
    class Other(FixedEngine):
        name = "yolo"

    with pytest.raises(ValueError):
        record_inspection(
            session, lot=lot, model_version=mock_version, engine=Other([]), image=IMG,
            image_uri="x", captured_at=NOW, source=InspectionSource.LIVE, rng=random.Random(0),
        )
