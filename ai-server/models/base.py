"""Engine interface for the inference server.

Adapted from ``app/engines/base.py`` (ADR 0001). The inference server runs in its own
container, so it keeps a copy instead of importing the root ``app`` package.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Candidate:
    defect_type: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x, y, w, h in source-image pixels, top-left origin


class Engine(Protocol):
    name: str
    class_names: list[str]
    weights_sha256: str | None

    def detect(self, image: np.ndarray) -> list[Candidate]:
        """Return defect candidates for one BGR image. Must not raise on an empty result."""
        ...
