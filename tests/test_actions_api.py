from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.domain.models import Event, Lot
from app.engines.base import DefectCandidate
from tests.api_helpers import ctx, post  # noqa: F401  (ctx is a fixture)

NG = [DefectCandidate("foreign_object", 0.95)]
REVIEW = [DefectCandidate("foreign_object", 0.5)]


def ng_defect(client, fixed, lot="S01", **kw) -> int:
    fixed.candidates = list(NG)
    body = post(client, lot=lot, **kw).json()
    assert body["verdict"] == "NG", body
    return body["defects"][0]["id"]


def open_action(client, **body):
    return client.post("/actions", json={"lot_code": "S01", "owner": "lead", **body})


def move(client, action_id, status, actor="lead", **extra):
    return client.post(f"/actions/{action_id}/status", json={"status": status, "actor": actor, **extra})


def test_hold_lot_puts_lot_on_hold_immediately(ctx):
    client, fixed, Session, _ = ctx
    did = ng_defect(client, fixed)
    r = open_action(client, action_type="hold_lot", defect_id=did)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["lot_status"] == "on_hold" and body["status"] == "open" and body["defect_id"] == did
    with Session() as s:
        assert s.scalar(select(Lot)).status == "on_hold"


def test_second_hold_is_conflict(ctx):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed)
    assert open_action(client, action_type="hold_lot").status_code == 201
    assert open_action(client, action_type="hold_lot").status_code == 409


def test_release_requires_held_lot(ctx):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed)
    assert open_action(client, action_type="release_lot").status_code == 409


def test_release_completes_only_when_done(ctx):
    client, fixed, Session, _ = ctx
    ng_defect(client, fixed)
    open_action(client, action_type="hold_lot")
    rid = open_action(client, action_type="release_lot").json()["id"]
    assert move(client, rid, "in_progress").json()["lot_status"] == "on_hold"
    done = move(client, rid, "done").json()
    assert done["lot_status"] == "released" and done["closed_at"].endswith("Z")


def test_lifecycle_must_pass_through_in_progress(ctx):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed)
    aid = open_action(client, action_type="recheck").json()["id"]
    assert move(client, aid, "done").status_code == 409
    assert move(client, aid, "in_progress").status_code == 200
    assert move(client, aid, "done").status_code == 200
    assert move(client, aid, "cancelled").status_code == 409


def test_cancel_does_not_release_held_lot(ctx):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed)
    aid = open_action(client, action_type="hold_lot").json()["id"]
    body = move(client, aid, "cancelled").json()
    assert body["status"] == "cancelled" and body["lot_status"] == "on_hold"


def test_detection_to_action_times(ctx):
    client, fixed, _, _ = ctx
    captured = datetime.now(timezone.utc) - timedelta(minutes=10)
    did = ng_defect(client, fixed, captured_at=captured.isoformat())
    aid = open_action(client, action_type="recheck", defect_id=did).json()["id"]
    move(client, aid, "in_progress")
    body = move(client, aid, "done").json()
    assert 590 < body["detection_to_open_s"] < 660
    assert body["detection_to_done_s"] >= body["detection_to_open_s"]


def test_times_are_null_without_defect_or_until_done(ctx):
    client, fixed, _, _ = ctx
    did = ng_defect(client, fixed)
    no_defect = open_action(client, action_type="stop_line").json()
    assert no_defect["detection_to_open_s"] is None and no_defect["detection_to_done_s"] is None
    with_defect = open_action(client, action_type="recheck", defect_id=did).json()
    assert with_defect["detection_to_open_s"] is not None and with_defect["detection_to_done_s"] is None


def test_defect_must_be_confirmed_and_in_lot(ctx):
    client, fixed, _, _ = ctx
    fixed.candidates = list(REVIEW)
    candidate_id = post(client).json()["defects"][0]["id"]
    assert open_action(client, action_type="recheck", defect_id=candidate_id).status_code == 422
    other = ng_defect(client, fixed, lot="S02")
    assert open_action(client, action_type="recheck", defect_id=other).status_code == 422
    assert open_action(client, action_type="recheck", defect_id=9999).status_code == 422


def test_unknown_lot_and_action_are_404(ctx):
    client, _, _, _ = ctx
    assert open_action(client, lot_code="NOPE", action_type="recheck").status_code == 404
    assert move(client, 999, "in_progress").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"action_type": "scrap"},
        {"action_type": "recheck", "owner": ""},
        {"action_type": "recheck", "lot_code": "../x"},
    ],
)
def test_invalid_body_is_422(ctx, body):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed)
    assert open_action(client, **body).status_code == 422


def test_list_filters_by_status_and_lot(ctx):
    client, fixed, _, _ = ctx
    ng_defect(client, fixed, lot="S01")
    ng_defect(client, fixed, lot="S02")
    a1 = open_action(client, action_type="recheck").json()["id"]
    open_action(client, lot_code="S02", action_type="recheck")
    move(client, a1, "in_progress")
    assert [a["id"] for a in client.get("/actions?status=in_progress").json()] == [a1]
    assert {a["lot_code"] for a in client.get("/actions?lot_code=S02").json()} == {"S02"}


def test_events_trace_lot_and_action(ctx):
    client, fixed, Session, _ = ctx
    ng_defect(client, fixed)
    aid = open_action(client, action_type="hold_lot").json()["id"]
    move(client, aid, "in_progress")
    with Session() as s:
        names = [(e.object_type, e.event) for e in s.scalars(select(Event).order_by(Event.id))]
    assert ("lot", "on_hold") in names
    assert names[-2:] == [("action", "opened:hold_lot"), ("action", "in_progress")]
