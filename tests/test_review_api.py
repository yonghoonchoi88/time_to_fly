import random

import pytest
from sqlalchemy import select

from app.api import inspections as api
from app.domain.models import Defect, Event, ReviewTask
from app.engines.base import DefectCandidate
from app.main import app
from tests.api_helpers import ctx, post  # noqa: F401  (ctx is a fixture)

MID = [DefectCandidate("foreign_object", 0.5, (10.0, 10.0, 5.0, 5.0))]


def queue_review(client, fixed, candidates=MID, **kw) -> int:
    fixed.candidates = list(candidates)
    body = post(client, **kw).json()
    assert body["review_task_id"] is not None, body
    return body["review_task_id"]


class AlwaysSample(random.Random):
    """RNG stub that makes every OK verdict an audit sample."""

    def random(self) -> float:
        return 0.0


def queue_audit(client, fixed) -> int:
    fixed.candidates = []
    app.dependency_overrides[api.get_rng] = AlwaysSample
    body = post(client).json()
    assert body["verdict"] == "OK" and body["review_task_id"] is not None
    return body["review_task_id"]


def decide(client, task_id, **body):
    return client.post(f"/review-tasks/{task_id}/decision", json={"reviewer": "kim", **body})


def test_pending_queue_matches_contract(ctx):
    client, fixed, _, _ = ctx
    tid = queue_review(client, fixed, lot="S07")
    (item,) = client.get("/review-tasks").json()
    assert item["id"] == tid and item["reason"] == "low_confidence" and item["status"] == "pending"
    insp = item["inspection"]
    assert insp["lot_code"] == "S07" and insp["image_url"] == f"/inspections/{insp['id']}/image"
    assert (insp["width"], insp["height"]) == (64, 48)
    assert item["defects"][0]["bbox"] == [10.0, 10.0, 5.0, 5.0]


def test_queue_is_oldest_first_and_limited(ctx):
    client, fixed, _, _ = ctx
    ids = [queue_review(client, fixed, name=f"{i}.png") for i in range(3)]
    assert [t["id"] for t in client.get("/review-tasks?limit=2").json()] == ids[:2]


def test_confirm_confirms_candidates(ctx):
    client, fixed, Session, _ = ctx
    tid = queue_review(client, fixed)
    r = decide(client, tid, decision="confirm")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done" and body["decision"] == "confirm" and body["reviewer"] == "kim"
    assert [d["status"] for d in body["defects"]] == ["confirmed"]
    assert client.get("/review-tasks").json() == []
    assert client.get("/review-tasks?status=done").json()[0]["id"] == tid


def test_reject_flags_for_retraining(ctx):
    client, fixed, Session, _ = ctx
    tid = queue_review(client, fixed)
    assert decide(client, tid, decision="reject").json()["defects"][0]["status"] == "rejected"
    with Session() as s:
        assert s.scalar(select(Defect)).retrain_candidate is True


def test_add_missed_adds_human_defect_and_rejects_candidates(ctx):
    client, fixed, Session, _ = ctx
    tid = queue_review(client, fixed)
    body = decide(client, tid, decision="add_missed", defect_type="foreign_object", bbox=[30, 20, 8, 8]).json()
    by_status = sorted((d["status"], d["confidence"]) for d in body["defects"])
    assert by_status == [("confirmed", None), ("rejected", 0.5)]
    with Session() as s:
        human = s.scalar(select(Defect).where(Defect.confidence.is_(None)))
        assert human.origin == "human" and human.bbox == [30, 20, 8, 8]


def test_audit_confirm_upholds_ok(ctx):
    client, fixed, _, _ = ctx
    tid = queue_audit(client, fixed)
    body = decide(client, tid, decision="confirm").json()
    assert body["reason"] == "audit_sample" and body["defects"] == []


def test_audit_add_missed_records_false_negative(ctx):
    client, fixed, Session, _ = ctx
    tid = queue_audit(client, fixed)
    decide(client, tid, decision="add_missed", defect_type="foreign_object", bbox=[1, 1, 4, 4])
    with Session() as s:
        ev = s.scalar(select(Event).where(Event.event == "decided:add_missed"))
        assert ev.payload["reason"] == "audit_sample"


def test_second_decision_is_conflict(ctx):
    client, fixed, _, _ = ctx
    tid = queue_review(client, fixed)
    assert decide(client, tid, decision="confirm").status_code == 200
    assert decide(client, tid, decision="reject").status_code == 409


def test_unknown_task_is_404(ctx):
    client, _, _, _ = ctx
    assert decide(client, 999, decision="confirm").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "add_missed"},
        {"decision": "add_missed", "defect_type": "x"},
        {"decision": "add_missed", "defect_type": "x", "bbox": [1, 2, 3]},
        {"decision": "add_missed", "defect_type": "x", "bbox": [1, 2, 0, 4]},
        {"decision": "confirm", "bbox": [1, 2, 3, 4]},
        {"decision": "approve"},
        {"decision": "confirm", "reviewer": ""},
    ],
)
def test_invalid_decision_body_is_422(ctx, body):
    client, fixed, Session, _ = ctx
    tid = queue_review(client, fixed)
    r = client.post(f"/review-tasks/{tid}/decision", json={"reviewer": "kim", **body})
    assert r.status_code == 422
    with Session() as s:
        assert s.get(ReviewTask, tid).status == "pending"


def test_every_decision_writes_events(ctx):
    client, fixed, Session, _ = ctx
    tid = queue_review(client, fixed)
    decide(client, tid, decision="confirm")
    with Session() as s:
        names = [e.event for e in s.scalars(select(Event).order_by(Event.id))]
    assert names[-2:] == ["confirmed", "decided:confirm"]
