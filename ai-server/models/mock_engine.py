"""Deterministic mock engine.

Adapted from ``app/engines/mock.py``. The original seeds one RNG per process, so results
depend on call order. Here the RNG is seeded per image from a SHA-256 of its pixels, so the
same image always yields the same candidates and Celery retries stay idempotent.
"""

import hashlib
import random

import numpy as np

from models.base import Candidate


class MockEngine:
    name = "mock"
    class_names = ["foreign_object"]
    weights_sha256: str | None = None

    def __init__(self, defect_rate: float = 0.3, min_conf: float = 0.10) -> None:
        if not 0.0 <= defect_rate <= 1.0:
            raise ValueError("defect_rate must be within [0, 1]")
        self._defect_rate = defect_rate
        self._min_conf = min_conf

    @staticmethod
    def seed_for(image: np.ndarray) -> int:
        """Stable seed derived from the image shape and pixel bytes."""
        digest = hashlib.sha256()
        digest.update(str(image.shape).encode())
        digest.update(np.ascontiguousarray(image).tobytes())
        return int.from_bytes(digest.digest()[:8], "big")

    def detect(self, image: np.ndarray) -> list[Candidate]:
        rng = random.Random(self.seed_for(image))
        if rng.random() >= self._defect_rate:
            return []
        h, w = image.shape[:2]
        bw, bh = max(1, w // 8), max(1, h // 8)
        x = rng.uniform(0, w - bw)
        y = rng.uniform(0, h - bh)
        confidence = round(rng.uniform(max(self._min_conf, 0.10), 0.99), 3)
        return [
            Candidate(
                defect_type="foreign_object",
                confidence=confidence,
                bbox=(round(x, 1), round(y, 1), float(bw), float(bh)),
            )
        ]
