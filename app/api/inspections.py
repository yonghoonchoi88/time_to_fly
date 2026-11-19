"""Inspection endpoints: submit a frame, fetch its image. Contract: docs/api.md."""

import random
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.enums import DefectStatus, InspectionSource, Verdict
from app.domain.models import Inspection
from app.engines.base import InspectionEngine
from app.engines.registry import get_engine
from app.services.catalog import active_model_version, lot_by_code
from app.services.inspection import record_inspection
from app.storage import IMAGE_DIR, ImageStore

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png"}
# lot_code becomes a directory name, so keep it to a safe character set.
LOT_CODE_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

router = APIRouter(tags=["inspections"])

_rng = random.Random()


def get_image_store() -> ImageStore:
    return ImageStore(IMAGE_DIR)


def get_rng() -> random.Random:
    return _rng


def get_engine_resolver() -> Callable[[str], InspectionEngine]:
    """Dependency returning a name -> engine lookup; overridden in tests."""
    return get_engine


class DefectOut(BaseModel):
    id: int
    defect_type: str
    confidence: float | None
    bbox: list[float] | None
    status: DefectStatus


class InspectionOut(BaseModel):
    inspection_id: int
    lot_code: str
    verdict: Verdict
    latency_ms: float
    review_task_id: int | None
    defects: list[DefectOut]


@router.post("/inspections", status_code=status.HTTP_201_CREATED, response_model=InspectionOut)
def create_inspection(
    file: Annotated[UploadFile, File()],
    lot_code: Annotated[str, Form(pattern=LOT_CODE_PATTERN)],
    source: Annotated[InspectionSource, Form()],
    captured_at: Annotated[datetime | None, Form()] = None,
    session: Session = Depends(get_session),
    store: ImageStore = Depends(get_image_store),
    rng: random.Random = Depends(get_rng),
    resolve_engine: Callable[[str], InspectionEngine] = Depends(get_engine_resolver),
) -> InspectionOut:
    # Sync handler on purpose: decoding, inference and DB writes are blocking, so FastAPI
    # runs this in its worker thread pool instead of stalling the event loop.
    ext = ALLOWED_EXT.get(Path(file.filename or "").suffix.lower())
    if ext is None:
        raise HTTPException(422, "file must be .jpg, .jpeg or .png")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "image exceeds 10 MB")

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(422, "file is not a decodable image")

    if captured_at is None:
        captured_at = datetime.now(timezone.utc)
    elif captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)  # contract: naive means UTC

    model_version = active_model_version(session)
    lot = lot_by_code(session, lot_code)
    key = store.save(lot_code, data, ext)

    inspection = record_inspection(
        session,
        lot=lot,
        model_version=model_version,
        engine=resolve_engine(model_version.engine),
        image=image,
        image_uri=key,
        captured_at=captured_at,
        source=source,
        rng=rng,
    )

    task = inspection.review_tasks[0] if inspection.review_tasks else None
    return InspectionOut(
        inspection_id=inspection.id,
        lot_code=lot.code,
        verdict=inspection.verdict,
        latency_ms=round(inspection.latency_ms, 3),
        review_task_id=task.id if task else None,
        defects=[
            DefectOut(id=d.id, defect_type=d.defect_type, confidence=d.confidence, bbox=d.bbox, status=d.status)
            for d in inspection.defects
        ],
    )


@router.get("/inspections/{inspection_id}/image")
def get_inspection_image(
    inspection_id: int,
    session: Session = Depends(get_session),
    store: ImageStore = Depends(get_image_store),
) -> FileResponse:
    inspection = session.get(Inspection, inspection_id)
    if inspection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "inspection not found")
    path = store.path(inspection.image_uri)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image file is missing from the store")
    return FileResponse(path)
