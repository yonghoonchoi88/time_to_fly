"""Runtime settings for the inference server, read from environment variables only.

Verdict thresholds (review / auto-NG) deliberately do not live here: they belong to the
Django ``ModelVersion`` row (ADR 0001). ``MIN_CONF`` is a noise floor, not a verdict rule.
"""

import os
from dataclasses import dataclass

SUPPORTED_ENGINES = ("mock", "yolo")


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw in (None, "") else int(raw)


@dataclass(frozen=True)
class Settings:
    engine: str = "mock"
    model_weights: str | None = None
    model_name: str = "kimchi-yolo"
    model_version: str = "mock-0"
    imgsz: int = 1280
    min_conf: float = 0.10
    max_upload_mb: float = 10.0
    mock_defect_rate: float = 0.3

    def __post_init__(self) -> None:
        if self.engine not in SUPPORTED_ENGINES:
            raise ValueError(f"ENGINE must be one of {SUPPORTED_ENGINES}, got {self.engine!r}")
        if self.engine == "yolo" and not self.model_weights:
            raise ValueError("MODEL_WEIGHTS is required when ENGINE=yolo")
        if not 0.0 <= self.min_conf < 1.0:
            raise ValueError("MIN_CONF must be within [0, 1)")
        if not 0.0 <= self.mock_defect_rate <= 1.0:
            raise ValueError("MOCK_DEFECT_RATE must be within [0, 1]")
        if self.imgsz <= 0 or self.max_upload_mb <= 0:
            raise ValueError("IMGSZ and MAX_UPLOAD_MB must be positive")

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            engine=os.getenv("ENGINE", "mock").strip().lower(),
            model_weights=os.getenv("MODEL_WEIGHTS") or None,
            model_name=os.getenv("MODEL_NAME", "kimchi-yolo"),
            model_version=os.getenv("MODEL_VERSION", "mock-0"),
            imgsz=_get_int("IMGSZ", 1280),
            min_conf=_get_float("MIN_CONF", 0.10),
            max_upload_mb=_get_float("MAX_UPLOAD_MB", 10.0),
            mock_defect_rate=_get_float("MOCK_DEFECT_RATE", 0.3),
        )
