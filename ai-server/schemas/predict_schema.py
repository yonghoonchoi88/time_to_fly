"""Response schemas. This is the contract the Celery worker relies on."""

from pydantic import BaseModel, Field


class CandidateOut(BaseModel):
    defect_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(min_length=4, max_length=4, description="[x, y, w, h] in pixels")


class PredictResponse(BaseModel):
    model: str
    version: str
    engine: str
    latency_ms: float = Field(description="Engine inference time only; excludes HTTP and decode")
    width: int
    height: int
    candidates: list[CandidateOut]


class HealthResponse(BaseModel):
    status: str
    engine: str
    model_loaded: bool


class ModelInfo(BaseModel):
    name: str
    engine: str
    version: str
    weights_sha256: str | None
    imgsz: int
    min_conf: float
    class_names: list[str]
