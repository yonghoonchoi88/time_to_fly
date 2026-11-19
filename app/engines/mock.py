"""Deterministic test double for the inspection engine.

Lets the full pipeline (persistence, review queue, actions, metrics) be built and tested
before a real engine is chosen.
"""

import random

import numpy as np

from app.engines.base import DefectCandidate


class MockEngine:
    name = "mock"

    def __init__(self, defect_rate: float = 0.2, seed: int = 0) -> None:
        if not 0.0 <= defect_rate <= 1.0:
            raise ValueError("defect_rate must be within [0, 1]")
        self._defect_rate = defect_rate
        self._rng = random.Random(seed)

    def detect(self, image: np.ndarray) -> list[DefectCandidate]:
        if self._rng.random() >= self._defect_rate:
            return []
        h, w = image.shape[:2]
        bw, bh = max(1, w // 8), max(1, h // 8)
        x = self._rng.uniform(0, w - bw)
        y = self._rng.uniform(0, h - bh)
        return [
            DefectCandidate(
                defect_type="foreign_object",
                confidence=round(self._rng.uniform(0.1, 0.99), 3),
                bbox=(x, y, float(bw), float(bh)),
            )
        ]
