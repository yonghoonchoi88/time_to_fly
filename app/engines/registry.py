"""Maps a ModelVersion.engine name to an engine instance."""

from functools import lru_cache

from app.engines.base import InspectionEngine
from app.engines.mock import MockEngine


@lru_cache(maxsize=None)
def get_engine(name: str) -> InspectionEngine:
    # Engines are cached because real ones (e.g. YOLO) are expensive to load.
    if name == "mock":
        return MockEngine(defect_rate=0.3, seed=0)
    raise KeyError(f"unknown engine: {name}")
