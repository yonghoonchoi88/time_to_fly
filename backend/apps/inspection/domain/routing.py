"""Verdict routing: turns engine candidates into OK / NG / REVIEW.

Routing is deliberately outside the engines so that swapping an engine never changes the
rules (ADR 0001). Thresholds come from the ModelVersion row, not from code.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..enums import ReviewReason, Verdict


@dataclass(frozen=True)
class Candidate:
    defect_type: str
    confidence: float
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h in source-image pixels


@dataclass(frozen=True)
class Thresholds:
    auto_ng_conf: float
    review_conf: float
    audit_rate: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_conf <= self.auto_ng_conf <= 1.0:
            raise ValueError("expected 0 <= review_conf <= auto_ng_conf <= 1")
        if not 0.0 <= self.audit_rate <= 1.0:
            raise ValueError("audit_rate must be within [0, 1]")


@dataclass(frozen=True)
class RoutingDecision:
    verdict: Verdict
    review_reason: ReviewReason | None
    # Candidates at or above auto_ng_conf; they are stored as confirmed defects.
    auto_confirmed: tuple[Candidate, ...]


def route(candidates: list[Candidate], thresholds: Thresholds, rng: random.Random) -> RoutingDecision:
    auto = tuple(c for c in candidates if c.confidence >= thresholds.auto_ng_conf)
    if auto:
        return RoutingDecision(Verdict.NG, None, auto)

    if any(c.confidence >= thresholds.review_conf for c in candidates):
        return RoutingDecision(Verdict.REVIEW, ReviewReason.LOW_CONFIDENCE, ())

    # OK verdicts are sampled for a human audit: missed defects never show up as candidates,
    # so sampling is the only way to measure false negatives in production.
    if rng.random() < thresholds.audit_rate:
        return RoutingDecision(Verdict.OK, ReviewReason.AUDIT_SAMPLE, ())
    return RoutingDecision(Verdict.OK, None, ())
