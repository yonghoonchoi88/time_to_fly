import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import synthetic_png
from main import create_app
from models.mock_engine import MockEngine


def post_image(client, data: bytes):
    return client.post("/predict", files={"file": ("a.png", data, "image/png")})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "engine": "mock", "model_loaded": True}


def test_model_info(client):
    r = client.get("/model")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "name", "engine", "version", "weights_sha256", "imgsz", "min_conf", "class_names"
    }
    assert body["engine"] == "mock"
    assert body["version"] == "mock-0"
    assert body["weights_sha256"] is None
    assert body["imgsz"] == 1280
    assert body["min_conf"] == pytest.approx(0.10)
    assert body["class_names"] == ["foreign_object"]


def test_predict_returns_contract_fields(always_defect_client):
    r = post_image(always_defect_client, synthetic_png(width=320, height=240))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "model", "version", "engine", "latency_ms", "width", "height", "candidates"
    }
    assert (body["width"], body["height"]) == (320, 240)
    assert body["engine"] == "mock"
    assert isinstance(body["latency_ms"], float)
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    assert cand["defect_type"] == "foreign_object"
    assert isinstance(cand["confidence"], float)
    assert len(cand["bbox"]) == 4


def test_no_defect_rate_returns_empty_list(monkeypatch):
    monkeypatch.setenv("MOCK_DEFECT_RATE", "0")
    with TestClient(create_app()) as c:
        assert post_image(c, synthetic_png()).json()["candidates"] == []


def test_same_image_gives_same_candidates(always_defect_client):
    data = synthetic_png(seed=7)
    first = post_image(always_defect_client, data).json()["candidates"]
    second = post_image(always_defect_client, data).json()["candidates"]
    assert first == second


def test_different_images_get_different_seeds():
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = a.copy()
    b[0, 0, 0] = 1
    assert MockEngine.seed_for(a) != MockEngine.seed_for(b)


def test_candidates_respect_min_conf_and_image_bounds(always_defect_client):
    for seed in range(20):
        body = post_image(always_defect_client, synthetic_png(seed=seed)).json()
        for c in body["candidates"]:
            x, y, w, h = c["bbox"]
            assert c["confidence"] >= 0.10
            assert x >= 0 and y >= 0
            assert x + w <= body["width"] and y + h <= body["height"]


def test_garbage_bytes_return_422(client):
    assert post_image(client, b"not an image").status_code == 422


def test_upload_over_limit_returns_413(client):
    assert post_image(client, b"\x00" * (11 * 1024 * 1024)).status_code == 413


def test_yolo_with_missing_weights_fails_at_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE", "yolo")
    monkeypatch.setenv("MODEL_WEIGHTS", str(tmp_path / "missing.pt"))
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app()):
            pass


def test_yolo_without_weights_setting_fails_at_startup(monkeypatch):
    monkeypatch.setenv("ENGINE", "yolo")
    with pytest.raises(ValueError):
        with TestClient(create_app()):
            pass
