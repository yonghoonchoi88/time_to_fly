"""Routing and transition rules. Pure functions: no database."""
import random

import pytest

from apps.inspection.domain.routing import Candidate, Thresholds, route
from apps.inspection.domain.transitions import InvalidTransition, check
from apps.inspection.enums import ActionStatus, DefectStatus, LotStatus, ReviewReason, ReviewStatus, Verdict

T = Thresholds(auto_ng_conf=0.7, review_conf=0.25, audit_rate=0.0)


def c(conf: float) -> Candidate:
    return Candidate("foreign_object", conf)


def test_high_confidence_is_auto_ng():
    d = route([c(0.9), c(0.3)], T, random.Random(0))
    assert d.verdict == Verdict.NG
    assert d.auto_confirmed == (c(0.9),)
    assert d.review_reason is None


def test_threshold_boundaries_are_inclusive():
    assert route([c(0.7)], T, random.Random(0)).verdict == Verdict.NG
    assert route([c(0.25)], T, random.Random(0)).verdict == Verdict.REVIEW


def test_mid_confidence_goes_to_review():
    d = route([c(0.5)], T, random.Random(0))
    assert d.verdict == Verdict.REVIEW
    assert d.review_reason == ReviewReason.LOW_CONFIDENCE


def test_low_confidence_and_empty_are_ok():
    assert route([c(0.1)], T, random.Random(0)).verdict == Verdict.OK
    assert route([], T, random.Random(0)).verdict == Verdict.OK


def test_audit_sampling_rate_is_respected():
    t = Thresholds(0.7, 0.25, audit_rate=0.1)
    rng = random.Random(42)
    sampled = sum(route([], t, rng).review_reason == ReviewReason.AUDIT_SAMPLE for _ in range(10_000))
    assert 900 < sampled < 1100


def test_audit_rate_one_samples_every_ok():
    t = Thresholds(0.7, 0.25, audit_rate=1.0)
    assert route([], t, random.Random(0)).review_reason == ReviewReason.AUDIT_SAMPLE


@pytest.mark.parametrize("args", [(0.2, 0.5, 0.0), (0.7, 0.25, 1.5), (1.2, 0.25, 0.0)])
def test_invalid_thresholds_are_rejected(args):
    with pytest.raises(ValueError):
        Thresholds(*args)


@pytest.mark.parametrize(
    "current,target",
    [
        (DefectStatus.CANDIDATE, DefectStatus.CONFIRMED),
        (DefectStatus.CANDIDATE, DefectStatus.REJECTED),
        (ReviewStatus.PENDING, ReviewStatus.DONE),
        (ActionStatus.OPEN, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.DONE),
        (ActionStatus.OPEN, ActionStatus.CANCELLED),
        (LotStatus.OPEN, LotStatus.ON_HOLD),
        (LotStatus.ON_HOLD, LotStatus.RELEASED),
        (LotStatus.ON_HOLD, LotStatus.SCRAPPED),
    ],
)
def test_allowed(current, target):
    check(current, target)


def test_plain_string_from_the_database_is_accepted():
    check("candidate", DefectStatus.CONFIRMED)


@pytest.mark.parametrize(
    "current,target",
    [
        (DefectStatus.CONFIRMED, DefectStatus.REJECTED),  # decisions are final; correct via a new event
        (DefectStatus.REJECTED, DefectStatus.CANDIDATE),
        (ReviewStatus.DONE, ReviewStatus.PENDING),
        (ActionStatus.OPEN, ActionStatus.DONE),  # must pass through in_progress
        (ActionStatus.DONE, ActionStatus.OPEN),
        (LotStatus.OPEN, LotStatus.RELEASED),  # only a held lot can be released
        (LotStatus.SCRAPPED, LotStatus.OPEN),
        ("not-a-status", LotStatus.OPEN),
    ],
)
def test_rejected(current, target):
    with pytest.raises(InvalidTransition):
        check(current, target)
