import random

import pytest

from app.domain.enums import ReviewReason, Verdict
from app.domain.routing import Thresholds, route
from app.engines.base import DefectCandidate

T = Thresholds(auto_ng_conf=0.7, review_conf=0.25, audit_rate=0.0)


def c(conf: float) -> DefectCandidate:
    return DefectCandidate("foreign_object", conf)


def test_high_confidence_is_auto_ng():
    d = route([c(0.9), c(0.3)], T, random.Random(0))
    assert d.verdict is Verdict.NG
    assert d.auto_confirmed == (c(0.9),)
    assert d.review_reason is None


def test_threshold_boundaries_are_inclusive():
    assert route([c(0.7)], T, random.Random(0)).verdict is Verdict.NG
    assert route([c(0.25)], T, random.Random(0)).verdict is Verdict.REVIEW


def test_mid_confidence_goes_to_review():
    d = route([c(0.5)], T, random.Random(0))
    assert d.verdict is Verdict.REVIEW
    assert d.review_reason is ReviewReason.LOW_CONFIDENCE


def test_low_confidence_and_empty_are_ok():
    assert route([c(0.1)], T, random.Random(0)).verdict is Verdict.OK
    assert route([], T, random.Random(0)).verdict is Verdict.OK


def test_audit_sampling_rate_is_respected():
    t = Thresholds(0.7, 0.25, audit_rate=0.1)
    rng = random.Random(42)
    sampled = sum(route([], t, rng).review_reason is ReviewReason.AUDIT_SAMPLE for _ in range(10_000))
    assert 900 < sampled < 1100


def test_audit_rate_one_samples_every_ok():
    t = Thresholds(0.7, 0.25, audit_rate=1.0)
    assert route([], t, random.Random(0)).review_reason is ReviewReason.AUDIT_SAMPLE


@pytest.mark.parametrize("args", [(0.2, 0.5, 0.0), (0.7, 0.25, 1.5), (1.2, 0.25, 0.0)])
def test_invalid_thresholds_are_rejected(args):
    with pytest.raises(ValueError):
        Thresholds(*args)
