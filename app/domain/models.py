"""Ontology object types persisted with SQLAlchemy.

See docs/ontology.md for the design rationale behind each object and link.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.enums import (
    ActionStatus,
    ActionType,
    DefectOrigin,
    DefectStatus,
    InspectionSource,
    LotStatus,
    ReviewDecision,
    ReviewReason,
    ReviewStatus,
    Verdict,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(enum_cls: type) -> Enum:
    # Stored as VARCHAR so the schema stays portable between SQLite (tests) and PostgreSQL.
    return Enum(enum_cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class ProductionLine(Base):
    __tablename__ = "production_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    site: Mapped[str] = mapped_column(String(64), default="")

    lots: Mapped[list[Lot]] = relationship(back_populates="line")


class Lot(Base):
    __tablename__ = "lot"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("production_line.id"))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    product_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[LotStatus] = mapped_column(_enum(LotStatus), default=LotStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    line: Mapped[ProductionLine] = relationship(back_populates="lots")
    inspections: Mapped[list[Inspection]] = relationship(back_populates="lot")
    actions: Mapped[list[Action]] = relationship(back_populates="lot")


class ModelVersion(Base):
    """An inspection engine plus the thresholds used to route its output.

    Thresholds live here, not in code, so verdicts stay comparable across versions.
    """

    __tablename__ = "model_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    engine: Mapped[str] = mapped_column(String(32))
    weights_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auto_ng_conf: Mapped[float] = mapped_column(Float)
    review_conf: Mapped[float] = mapped_column(Float)
    audit_rate: Mapped[float] = mapped_column(Float, default=0.05)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Inspection(Base):
    __tablename__ = "inspection"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lot.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_version.id"))
    image_uri: Mapped[str] = mapped_column(String(512))
    image_width: Mapped[int] = mapped_column(Integer)
    image_height: Mapped[int] = mapped_column(Integer)
    source: Mapped[InspectionSource] = mapped_column(_enum(InspectionSource))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict))
    latency_ms: Mapped[float] = mapped_column(Float)
    is_audit_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    lot: Mapped[Lot] = relationship(back_populates="inspections")
    model_version: Mapped[ModelVersion] = relationship()
    defects: Mapped[list[Defect]] = relationship(back_populates="inspection")
    review_tasks: Mapped[list[ReviewTask]] = relationship(back_populates="inspection")


class Defect(Base):
    __tablename__ = "defect"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspection.id"), index=True)
    defect_type: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # None for human-added
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)  # [x, y, w, h], pixels
    origin: Mapped[DefectOrigin] = mapped_column(_enum(DefectOrigin))
    status: Mapped[DefectStatus] = mapped_column(_enum(DefectStatus))
    retrain_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    inspection: Mapped[Inspection] = relationship(back_populates="defects")


class ReviewTask(Base):
    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspection.id"), index=True)
    reason: Mapped[ReviewReason] = mapped_column(_enum(ReviewReason))
    status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus), default=ReviewStatus.PENDING)
    decision: Mapped[ReviewDecision | None] = mapped_column(_enum(ReviewDecision), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inspection: Mapped[Inspection] = relationship(back_populates="review_tasks")


class Action(Base):
    """A field action. Attached to a Lot because holds and rechecks happen per lot."""

    __tablename__ = "action"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lot.id"), index=True)
    defect_id: Mapped[int | None] = mapped_column(ForeignKey("defect.id"), nullable=True)
    action_type: Mapped[ActionType] = mapped_column(_enum(ActionType))
    status: Mapped[ActionStatus] = mapped_column(_enum(ActionStatus), default=ActionStatus.OPEN)
    owner: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lot: Mapped[Lot] = relationship(back_populates="actions")
    defect: Mapped[Defect | None] = relationship()


class Event(Base):
    """Append-only audit log. Every state change writes one row; metrics are derived from it."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(32), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    event: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
