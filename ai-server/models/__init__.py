"""Engine factory. Heavy dependencies (torch, ultralytics) are imported lazily."""

from pathlib import Path

from config import Settings
from models.base import Engine


def load_engine(settings: Settings) -> Engine:
    if settings.engine == "mock":
        from models.mock_engine import MockEngine

        return MockEngine(defect_rate=settings.mock_defect_rate, min_conf=settings.min_conf)

    # Check the weights file before importing ultralytics so a bad path fails fast at
    # startup, and so CI can test this path without torch installed.
    weights = Path(settings.model_weights or "")
    if not weights.is_file():
        raise FileNotFoundError(f"MODEL_WEIGHTS not found: {weights}")

    from models.yolo_engine import YoloEngine

    return YoloEngine(weights=weights, imgsz=settings.imgsz, min_conf=settings.min_conf)
