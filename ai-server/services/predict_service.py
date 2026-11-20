"""Decode an uploaded image, run the engine, and time the inference step."""

import time

import cv2
import numpy as np

from config import Settings
from models.base import Engine
from schemas.predict_schema import CandidateOut, PredictResponse


class ImageDecodeError(ValueError):
    """Raised when the uploaded bytes are not a decodable image."""


def decode_image(data: bytes) -> np.ndarray:
    if not data:
        raise ImageDecodeError("empty upload")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ImageDecodeError("cannot decode image")
    return image


def predict(engine: Engine, settings: Settings, data: bytes) -> PredictResponse:
    image = decode_image(data)
    height, width = image.shape[:2]

    started = time.perf_counter()
    candidates = engine.detect(image)
    latency_ms = (time.perf_counter() - started) * 1000

    return PredictResponse(
        model=settings.model_name,
        version=settings.model_version,
        engine=engine.name,
        latency_ms=round(latency_ms, 2),
        width=width,
        height=height,
        candidates=[
            CandidateOut(defect_type=c.defect_type, confidence=c.confidence, bbox=list(c.bbox))
            for c in candidates
            if c.confidence >= settings.min_conf
        ],
    )
