"""Celery tasks that call the AI inference server.

Tasks receive a path, not image bytes: bytes would bloat the Redis message and are not
JSON-serialisable, while a path lets every retry re-read the same file.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings

from . import services
from .services import AiServerUnavailable


def resolve_image_path(image_path: str) -> Path:
    """Map a MEDIA_ROOT-relative path to an absolute one, refusing anything outside it.

    resolve() collapses ``..`` and symlinks first, so "../../etc/passwd" or an absolute
    path cannot escape the image directory.
    """
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / image_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"image path is outside MEDIA_ROOT: {image_path!r}")
    return path


# Only AiServerUnavailable is retried: a server that is restarting may answer in a few
# seconds, but a rejected or malformed image fails the same way every time and would
# only clog the queue. Bad paths and missing files are not retried either.
@shared_task(
    bind=True,
    autoretry_for=(AiServerUnavailable,),
    retry_backoff=2,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def predict_image(self, image_path: str) -> dict[str, Any]:
    """Run inference on one stored frame and return the candidates as a JSON-safe dict.

    ``image_path`` is relative to MEDIA_ROOT. The result is ``Prediction`` fields plus
    ``attempts`` (1 on first success). No verdict is made here: thresholds live on the
    ModelVersion row, applied by the caller.
    """
    path = resolve_image_path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {image_path!r}")

    prediction = services.predict(path.read_bytes(), filename=path.name)
    result = asdict(prediction)
    # Lists, not tuples: the same shape whether the task runs eagerly or through Redis JSON.
    for candidate in result["candidates"]:
        candidate["bbox"] = list(candidate["bbox"])
    result["attempts"] = self.request.retries + 1
    return result


@shared_task
def ping() -> str:
    """Round trip through Redis and a worker; used to check that both are alive."""
    return "pong"
