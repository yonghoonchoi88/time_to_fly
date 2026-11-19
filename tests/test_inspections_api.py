import pytest
from sqlalchemy import select

from app.api import inspections as api
from app.domain.models import Inspection, Lot, ModelVersion
from app.engines.base import DefectCandidate
from app.storage import ImageStore
from tests.api_helpers import ctx, png_bytes, post  # noqa: F401  (ctx is a fixture)


def test_ok_inspection_creates_lot_and_default_model_version(ctx):
    client, _, Session, _ = ctx
    r = post(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verdict"] == "OK" and body["lot_code"] == "S01"
    assert body["review_task_id"] is None and body["defects"] == []
    with Session() as s:
        assert s.scalar(select(Lot)).code == "S01"
        assert s.scalar(select(ModelVersion)).name == "mock-v1"


def test_review_verdict_returns_task_and_candidate(ctx):
    client, fixed, _, _ = ctx
    fixed.candidates = [DefectCandidate("foreign_object", 0.5, (1.0, 2.0, 3.0, 4.0))]
    body = post(client).json()
    assert body["verdict"] == "REVIEW"
    assert body["review_task_id"] is not None
    assert body["defects"][0]["status"] == "candidate"
    assert body["defects"][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_ng_verdict_confirms_defect(ctx):
    client, fixed, _, _ = ctx
    fixed.candidates = [DefectCandidate("foreign_object", 0.95)]
    body = post(client).json()
    assert body["verdict"] == "NG"
    assert body["defects"][0]["status"] == "confirmed"


def test_same_lot_code_is_reused(ctx):
    client, _, Session, _ = ctx
    post(client, lot="S02")
    post(client, lot="S02", name="0002.png")
    with Session() as s:
        assert len(s.scalars(select(Lot)).all()) == 1


def test_image_round_trip_and_size_recorded(ctx):
    client, _, Session, _ = ctx
    data = png_bytes(80, 60)
    iid = post(client, data=data).json()["inspection_id"]
    r = client.get(f"/inspections/{iid}/image")
    assert r.status_code == 200 and r.content == data
    with Session() as s:
        insp = s.get(Inspection, iid)
        assert (insp.image_width, insp.image_height) == (80, 60)


def test_captured_at_is_stored_as_utc(ctx):
    client, _, Session, _ = ctx
    iid = post(client, captured_at="2026-11-20T09:00:00").json()["inspection_id"]
    with Session() as s:
        assert s.get(Inspection, iid).captured_at.replace(tzinfo=None).isoformat() == "2026-11-20T09:00:00"


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"data": b"not an image"}, 422),
        ({"name": "frame.gif"}, 422),
        ({"lot": "../etc"}, 422),
        ({"lot": ""}, 422),
        ({"source": "camera"}, 422),
    ],
)
def test_bad_input_is_rejected(ctx, kwargs, code):
    client, _, _, store = ctx
    assert post(client, **kwargs).status_code == code
    # Rejected uploads must not leave files behind.
    assert not store.root.exists() or not any(store.root.rglob("*.*"))


def test_oversized_upload_is_rejected(ctx, monkeypatch):
    client, _, _, _ = ctx
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 100)
    assert post(client).status_code == 413


def test_missing_inspection_image_is_404(ctx):
    client, _, _, _ = ctx
    assert client.get("/inspections/999/image").status_code == 404


def test_store_refuses_keys_outside_root(tmp_path):
    store = ImageStore(tmp_path)
    with pytest.raises(ValueError):
        store.path("../outside.png")
