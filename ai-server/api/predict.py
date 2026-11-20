"""HTTP endpoints.

Handlers are plain ``def`` on purpose: inference is CPU-bound, so FastAPI runs them in its
thread pool instead of blocking the event loop. Scale out with replicas, not threads.
"""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from schemas.predict_schema import HealthResponse, ModelInfo, PredictResponse
from services import predict_service

router = APIRouter()


@router.post("/predict", response_model=PredictResponse)
def predict(request: Request, file: UploadFile = File(...)) -> PredictResponse:
    settings = request.app.state.settings
    limit = settings.max_upload_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"upload exceeds {settings.max_upload_mb} MB")
    try:
        return predict_service.predict(request.app.state.engine, settings, data)
    except predict_service.ImageDecodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    engine = getattr(request.app.state, "engine", None)
    return HealthResponse(
        status="ok",
        engine=request.app.state.settings.engine,
        model_loaded=engine is not None,
    )


@router.get("/model", response_model=ModelInfo)
def model_info(request: Request) -> ModelInfo:
    settings = request.app.state.settings
    engine = request.app.state.engine
    return ModelInfo(
        name=settings.model_name,
        engine=engine.name,
        version=settings.model_version,
        weights_sha256=engine.weights_sha256,
        imgsz=settings.imgsz,
        min_conf=settings.min_conf,
        class_names=list(engine.class_names),
    )
