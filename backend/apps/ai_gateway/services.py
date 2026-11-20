"""HTTP client for the AI inference server (ai-server/).

The server only answers "which defect candidates are in this image?". Turning candidates
into an OK/NG/REVIEW verdict and storing them is the caller's job (ADR 0001), so nothing
here knows about thresholds or the database.

Contract: ai-server/README.md and ai-server/schemas/predict_schema.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Fixed and short: a server that does not accept connections is down, not busy.
CONNECT_TIMEOUT_S = 2.0


class AiServerError(Exception):
    """Base class for every failure talking to the AI server."""


class AiServerUnavailable(AiServerError):
    """Connection refused, timeout or 5xx. Transient, so worth retrying."""


class AiServerRejected(AiServerError):
    """4xx such as 413 (too large) or 422 (not an image). Resending gives the same answer."""

    def __init__(self, status_code: int, detail: str):
        # Keep the constructor arguments as ``args``: Celery rebuilds exceptions from
        # ``type(exc)(*exc.args)`` when results cross the backend, and a mismatch would
        # silently downgrade this to AiServerError.
        super().__init__(status_code, detail)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return f"AI server rejected the request ({self.status_code}): {self.detail}"


class AiServerContractError(AiServerError):
    """2xx with a body that does not match the contract, usually a version mismatch."""


@dataclass(frozen=True)
class Candidate:
    defect_type: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x, y, w, h in source-image pixels


@dataclass(frozen=True)
class Prediction:
    model: str
    version: str
    engine: str
    latency_ms: float  # engine time only, as measured by the server
    width: int
    height: int
    candidates: list[Candidate]


def predict(image_bytes: bytes, filename: str = "frame.jpg") -> Prediction:
    """POST /predict and return the defect candidates for one image."""
    files = {"file": (filename, image_bytes, "application/octet-stream")}
    payload = _request("POST", "/predict", files=files)
    try:
        return _parse_prediction(payload)
    except AiServerContractError as exc:
        logger.error("ai-server /predict contract mismatch: %s", exc)
        raise


def model_info() -> dict[str, Any]:
    """GET /model: name, engine, version and weights hash of the model being served."""
    return _request("GET", "/model")


def health() -> dict[str, Any]:
    """GET /health: whether the server is up and its engine is loaded."""
    return _request("GET", "/health")


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = settings.FASTAPI_BASE_URL.rstrip("/") + path
    timeout = (CONNECT_TIMEOUT_S, settings.AI_SERVER_TIMEOUT_S)
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise AiServerUnavailable(f"{method} {url} failed: {exc}") from exc

    if response.status_code >= 500:
        raise AiServerUnavailable(f"{method} {url} returned {response.status_code}")
    if response.status_code >= 400:
        raise AiServerRejected(response.status_code, _error_detail(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiServerContractError(f"{method} {url} returned a non-JSON body") from exc
    if not isinstance(payload, dict):
        raise AiServerContractError(f"{method} {url} returned {type(payload).__name__}, expected an object")
    return payload


def _error_detail(response: requests.Response) -> str:
    # FastAPI errors look like {"detail": "..."}; fall back to the raw text.
    try:
        return str(response.json().get("detail", response.text))
    except (ValueError, AttributeError):
        return response.text[:200]


def _parse_prediction(payload: dict[str, Any]) -> Prediction:
    raw_candidates = _field(payload, "candidates", list)
    return Prediction(
        model=_field(payload, "model", str),
        version=_field(payload, "version", str),
        engine=_field(payload, "engine", str),
        latency_ms=_field(payload, "latency_ms", float),
        width=_field(payload, "width", int),
        height=_field(payload, "height", int),
        candidates=[_parse_candidate(item) for item in raw_candidates],
    )


def _parse_candidate(item: Any) -> Candidate:
    if not isinstance(item, dict):
        raise AiServerContractError(f"candidate is {type(item).__name__}, expected an object")
    bbox = _field(item, "bbox", list)
    if len(bbox) != 4 or not all(_is_number(v) for v in bbox):
        raise AiServerContractError(f"bbox must be 4 numbers [x, y, w, h], got {bbox!r}")
    return Candidate(
        defect_type=_field(item, "defect_type", str),
        confidence=_field(item, "confidence", float),
        bbox=tuple(float(v) for v in bbox),
    )


def _field(obj: dict[str, Any], key: str, kind: type) -> Any:
    """Return obj[key] if it has the expected JSON type, else raise AiServerContractError."""
    if key not in obj:
        raise AiServerContractError(f"missing field {key!r}")
    value = obj[key]
    if kind is float:
        ok = _is_number(value)
        value = float(value) if ok else value
    elif kind is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, kind)
    if not ok:
        raise AiServerContractError(f"field {key!r} is {type(value).__name__}, expected {kind.__name__}")
    return value


def _is_number(value: Any) -> bool:
    # JSON has one number type; bool is an int subclass in Python and must not pass.
    return isinstance(value, (int, float)) and not isinstance(value, bool)
