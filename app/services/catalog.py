"""Get-or-create helpers for reference objects (line, lot, active model version)."""

import os

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.models import Lot, ModelVersion, ProductionLine

DEFAULT_LINE = os.getenv("DEFAULT_LINE", "line-1")
ACTIVE_MODEL_VERSION = os.getenv("MODEL_VERSION", "mock-v1")

# Thresholds used when the default mock version is created for the first time.
MOCK_DEFAULTS = {"engine": "mock", "auto_ng_conf": 0.7, "review_conf": 0.25, "audit_rate": 0.05}


def _get_or_create(session: Session, model, lookup: dict, defaults: dict | None = None):
    obj = session.scalar(select(model).filter_by(**lookup))
    if obj is not None:
        return obj
    obj = model(**lookup, **(defaults or {}))
    session.add(obj)
    try:
        # Savepoint so a concurrent insert of the same key does not abort the caller's transaction.
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        return session.scalar(select(model).filter_by(**lookup))
    return obj


def active_model_version(session: Session) -> ModelVersion:
    defaults = MOCK_DEFAULTS if ACTIVE_MODEL_VERSION == "mock-v1" else None
    mv = session.scalar(select(ModelVersion).filter_by(name=ACTIVE_MODEL_VERSION))
    if mv is None and defaults is None:
        raise LookupError(f"model version {ACTIVE_MODEL_VERSION!r} is not registered")
    return mv or _get_or_create(session, ModelVersion, {"name": ACTIVE_MODEL_VERSION}, defaults)


def lot_by_code(session: Session, code: str, product_type: str = "unknown") -> Lot:
    """Return the lot with this code, creating it on the default line on first sight."""
    lot = session.scalar(select(Lot).filter_by(code=code))
    if lot is not None:
        return lot
    line = _get_or_create(session, ProductionLine, {"name": DEFAULT_LINE})
    return _get_or_create(session, Lot, {"code": code}, {"line": line, "product_type": product_type})
