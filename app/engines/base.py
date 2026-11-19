"""Inspection engine interface.

An engine only answers "what defect candidates are in this image?". It does not decide
verdicts, write to the database, or know about lots. That keeps engines swappable
(mock, rule-based OpenCV, YOLO) without touching the rest of the pipeline.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class DefectCandidate:
    defect_type: str
    confidence: float
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h in pixels


class InspectionEngine(Protocol):
    name: str

    def detect(self, image: np.ndarray) -> list[DefectCandidate]:
        """Return defect candidates for one BGR image. Must not raise on an empty result."""
        ...
