import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import create_app

ENV_KEYS = (
    "ENGINE",
    "MODEL_WEIGHTS",
    "MODEL_NAME",
    "MODEL_VERSION",
    "IMGSZ",
    "MIN_CONF",
    "MAX_UPLOAD_MB",
    "MOCK_DEFECT_RATE",
)


def synthetic_png(seed: int = 0, width: int = 320, height: int = 240) -> bytes:
    """Random-noise PNG generated in code; no real or customer images in tests."""
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", pixels)
    assert ok
    return buf.tobytes()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def always_defect_client(monkeypatch):
    monkeypatch.setenv("MOCK_DEFECT_RATE", "1.0")
    with TestClient(create_app()) as c:
        yield c
