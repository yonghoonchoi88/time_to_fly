"""Shared API test helpers: in-memory DB, fixed engine, temp image store."""

import random

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import inspections as api
from app.db import Base, get_session
from app.engines.base import DefectCandidate
from app.main import app
from app.storage import ImageStore


class FixedEngine:
    name = "mock"

    def __init__(self):
        self.candidates: list[DefectCandidate] = []

    def detect(self, image):
        return list(self.candidates)


def png_bytes(w: int = 64, h: int = 48) -> bytes:
    ok, buf = cv2.imencode(".png", np.full((h, w, 3), 128, dtype=np.uint8))
    assert ok
    return buf.tobytes()


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    fixed = FixedEngine()
    store = ImageStore(tmp_path / "images")

    def session_override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[api.get_image_store] = lambda: store
    app.dependency_overrides[api.get_rng] = lambda: random.Random(0)
    app.dependency_overrides[api.get_engine_resolver] = lambda: (lambda name: fixed)
    with TestClient(app) as client:
        yield client, fixed, Session, store
    app.dependency_overrides.clear()


def post(client, *, lot="S01", source="replay", data=None, name="0001.png", **extra):
    return client.post(
        "/inspections",
        files={"file": (name, data if data is not None else png_bytes(), "image/png")},
        data={"lot_code": lot, "source": source, **extra},
    )
