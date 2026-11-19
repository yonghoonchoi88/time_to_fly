from datetime import datetime, timedelta, timezone

from app.domain.models import Event
from app.engines.base import DefectCandidate
from tests.api_helpers import ctx, post  # noqa: F401  (ctx is a fixture)

KST = timezone(timedelta(hours=9))


def test_round_trip_is_utc_aware(session):
    session.add(Event(object_type="x", object_id=1, event="e", actor="a", at=datetime(2026, 11, 20, 18, 0, tzinfo=KST)))
    session.commit()
    session.expunge_all()
    ev = session.query(Event).one()
    assert ev.at.tzinfo is not None and ev.at.utcoffset() == timedelta(0)
    assert ev.at == datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def test_naive_input_is_treated_as_utc(session):
    session.add(Event(object_type="x", object_id=1, event="e", actor="a", at=datetime(2026, 11, 20, 9, 0)))
    session.commit()
    session.expunge_all()
    assert session.query(Event).one().at == datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def test_api_timestamps_end_with_z(ctx):
    client, fixed, _, _ = ctx
    fixed.candidates = [DefectCandidate("foreign_object", 0.5)]
    post(client, captured_at="2026-11-20T18:00:00+09:00")
    (task,) = client.get("/review-tasks").json()
    assert task["created_at"].endswith("Z")
    assert task["inspection"]["captured_at"] == "2026-11-20T09:00:00Z"
