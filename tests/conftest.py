import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.domain import models  # noqa: F401
from app.domain.models import Lot, ModelVersion, ProductionLine


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def lot(session):
    line = ProductionLine(name="line-1", site="test")
    lot = Lot(line=line, code="LOT-0001", product_type="test")
    session.add(lot)
    session.commit()
    return lot


@pytest.fixture
def mock_version(session):
    mv = ModelVersion(name="mock-v1", engine="mock", auto_ng_conf=0.7, review_conf=0.25, audit_rate=0.05)
    session.add(mv)
    session.commit()
    return mv
