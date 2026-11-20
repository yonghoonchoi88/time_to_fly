"""Ultralytics YOLO engine.

``ultralytics`` (and therefore torch) is imported inside ``YoloEngine.__init__`` only, so
the mock path, the helpers below and CI never need the heavy dependencies.
"""

import hashlib
from pathlib import Path
from typing import Sequence

import numpy as np

from models.base import Candidate


def xyxy_to_xywh(
    box: Sequence[float], width: int, height: int
) -> tuple[float, float, float, float]:
    """Convert corner coordinates to [x, y, w, h], clipped to the image bounds."""
    x1, y1, x2, y2 = (float(v) for v in box)
    x1 = min(max(x1, 0.0), float(width))
    x2 = min(max(x2, 0.0), float(width))
    y1 = min(max(y1, 0.0), float(height))
    y2 = min(max(y2, 0.0), float(height))
    left, top = min(x1, x2), min(y1, y2)
    return (
        round(left, 1),
        round(top, 1),
        round(abs(x2 - x1), 1),
        round(abs(y2 - y1), 1),
    )


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class YoloEngine:
    name = "yolo"

    def __init__(self, weights: Path, imgsz: int, min_conf: float) -> None:
        from ultralytics import YOLO

        self.weights_sha256: str | None = sha256_file(weights)
        self._model = YOLO(str(weights))
        self._imgsz = imgsz
        self._min_conf = min_conf
        names = self._model.names
        self.class_names = [names[i] for i in sorted(names)]

    def detect(self, image: np.ndarray) -> list[Candidate]:
        result = self._model.predict(
            image, imgsz=self._imgsz, conf=self._min_conf, verbose=False
        )[0]
        height, width = image.shape[:2]
        boxes = result.boxes
        return [
            Candidate(
                defect_type=self._model.names[int(cls)],
                confidence=round(float(conf), 3),
                bbox=xyxy_to_xywh(xyxy, width, height),
            )
            for xyxy, conf, cls in zip(
                boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()
            )
        ]
