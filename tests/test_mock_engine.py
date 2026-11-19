import numpy as np
import pytest

from app.engines.mock import MockEngine

IMG = np.zeros((480, 640, 3), dtype=np.uint8)


def test_same_seed_is_reproducible():
    a, b = MockEngine(0.5, seed=7), MockEngine(0.5, seed=7)
    assert [a.detect(IMG) for _ in range(50)] == [b.detect(IMG) for _ in range(50)]


def test_rate_zero_never_detects():
    e = MockEngine(0.0)
    assert all(e.detect(IMG) == [] for _ in range(100))


def test_bbox_stays_inside_image():
    e = MockEngine(1.0, seed=1)
    for _ in range(200):
        (c,) = e.detect(IMG)
        x, y, w, h = c.bbox
        assert 0 <= x and 0 <= y and x + w <= 640 and y + h <= 480
        assert 0.0 <= c.confidence <= 1.0


def test_invalid_rate_is_rejected():
    with pytest.raises(ValueError):
        MockEngine(1.5)
