"""AI server client, Celery tasks and the ai_check command.

HTTP is faked with ``responses``; tasks run eagerly. No Redis or ai-server is needed.
"""
import json
import os
import struct
import subprocess
import sys
import zlib

import pytest
import requests
import responses
from django.conf import settings as django_settings
from django.core.management import CommandError, call_command

from apps.ai_gateway import services
from apps.ai_gateway.services import (
    AiServerContractError,
    AiServerError,
    AiServerRejected,
    AiServerUnavailable,
)
from apps.ai_gateway.tasks import ping, predict_image
from mysite.celery import app as celery_app

BASE_URL = "http://ai.test"
PREDICT_URL = f"{BASE_URL}/predict"

PREDICTION = {
    "model": "kimchi-yolo",
    "version": "mock-0",
    "engine": "mock",
    "latency_ms": 3.21,
    "width": 64,
    "height": 48,
    "candidates": [
        {"defect_type": "foreign_object", "confidence": 0.82, "bbox": [10, 12, 8, 6]},
        {"defect_type": "foreign_object", "confidence": 0.31, "bbox": [40.5, 20.0, 5.0, 5.0]},
    ],
}


def synthetic_png(width=64, height=48) -> bytes:
    """A valid grey PNG built in code, so tests never touch real (NDA) images."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))  # filter byte + grey pixels
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def ai_settings(settings, tmp_path):
    settings.FASTAPI_BASE_URL = BASE_URL
    settings.MEDIA_ROOT = tmp_path / "images"
    settings.MEDIA_ROOT.mkdir()
    return settings


@pytest.fixture
def eager_celery():
    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = previous


@pytest.fixture
def stored_image(ai_settings):
    (ai_settings.MEDIA_ROOT / "line1").mkdir()
    path = ai_settings.MEDIA_ROOT / "line1" / "frame.png"
    path.write_bytes(synthetic_png())
    return "line1/frame.png"


# --- services.predict -----------------------------------------------------------------


@responses.activate
def test_predict_parses_candidates():
    responses.post(PREDICT_URL, json=PREDICTION)

    result = services.predict(synthetic_png(), filename="frame.png")

    assert result.model == "kimchi-yolo" and result.engine == "mock"
    assert (result.width, result.height) == (64, 48)
    assert len(result.candidates) == 2
    first = result.candidates[0]
    assert first.defect_type == "foreign_object"
    assert first.confidence == pytest.approx(0.82)
    assert first.bbox == (10.0, 12.0, 8.0, 6.0)
    # Sent as multipart field "file", as ai-server expects.
    body = responses.calls[0].request.body
    assert b'name="file"; filename="frame.png"' in body


@responses.activate
def test_predict_with_no_candidates_is_valid():
    responses.post(PREDICT_URL, json={**PREDICTION, "candidates": []})

    assert services.predict(synthetic_png()).candidates == []


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError("connection refused"),
        requests.ConnectTimeout("connect timed out"),
        requests.ReadTimeout("read timed out"),
    ],
    ids=["connection-refused", "connect-timeout", "read-timeout"],
)
@responses.activate
def test_network_failures_are_unavailable(failure):
    responses.post(PREDICT_URL, body=failure)

    with pytest.raises(AiServerUnavailable) as excinfo:
        services.predict(synthetic_png())
    assert excinfo.value.__cause__ is failure  # original error preserved


@pytest.mark.parametrize("status", [500, 502, 503])
@responses.activate
def test_server_errors_are_unavailable(status):
    responses.post(PREDICT_URL, status=status, body="busy")

    with pytest.raises(AiServerUnavailable):
        services.predict(synthetic_png())


@pytest.mark.parametrize("status", [413, 422])
@responses.activate
def test_client_errors_are_rejected(status):
    responses.post(PREDICT_URL, status=status, json={"detail": "cannot decode image"})

    with pytest.raises(AiServerRejected) as excinfo:
        services.predict(synthetic_png())
    assert excinfo.value.status_code == status
    assert excinfo.value.detail == "cannot decode image"


def _without(key):
    return {k: v for k, v in PREDICTION.items() if k != key}


def _with_candidate(**changes):
    return {**PREDICTION, "candidates": [{**PREDICTION["candidates"][0], **changes}]}


@pytest.mark.parametrize(
    "payload",
    [
        _without("candidates"),
        _without("model"),
        {**PREDICTION, "width": "64"},
        {**PREDICTION, "latency_ms": True},
        {**PREDICTION, "candidates": ["not-an-object"]},
        _with_candidate(confidence="0.9"),
        _with_candidate(bbox=[1, 2, 3]),
        _with_candidate(bbox=[1, 2, 3, "4"]),
        {**PREDICTION, "candidates": [{"confidence": 0.5, "bbox": [0, 0, 1, 1]}]},
        ["not", "an", "object"],
    ],
    ids=[
        "missing-candidates",
        "missing-model",
        "width-string",
        "latency-bool",
        "candidate-not-object",
        "confidence-string",
        "bbox-3-values",
        "bbox-string-value",
        "missing-defect-type",
        "top-level-list",
    ],
)
@responses.activate
def test_contract_violations(payload):
    responses.post(PREDICT_URL, json=payload)

    with pytest.raises(AiServerContractError):
        services.predict(synthetic_png())


@responses.activate
def test_non_json_body_is_contract_error():
    responses.post(PREDICT_URL, body="<html>proxy error page</html>", status=200)

    with pytest.raises(AiServerContractError):
        services.predict(synthetic_png())


def test_error_hierarchy():
    for error in (AiServerUnavailable, AiServerRejected, AiServerContractError):
        assert issubclass(error, AiServerError)


@responses.activate
def test_timeouts_are_passed_to_requests(ai_settings):
    ai_settings.AI_SERVER_TIMEOUT_S = 7.5
    responses.post(PREDICT_URL, json=PREDICTION)

    services.predict(synthetic_png())

    assert responses.calls[0].request.req_kwargs["timeout"] == (services.CONNECT_TIMEOUT_S, 7.5)


# --- predict_image task ---------------------------------------------------------------


@pytest.mark.parametrize("bad_path", ["../outside.png", "line1/../../outside.png", "/etc/passwd"])
def test_predict_image_refuses_paths_outside_media_root(eager_celery, ai_settings, bad_path):
    (ai_settings.MEDIA_ROOT.parent / "outside.png").write_bytes(synthetic_png())

    with pytest.raises(ValueError, match="outside MEDIA_ROOT"):
        predict_image.delay(bad_path).get()


@responses.activate
def test_predict_image_missing_file_is_not_retried(eager_celery):
    with pytest.raises(FileNotFoundError):
        predict_image.delay("line1/nope.png").get()
    assert len(responses.calls) == 0


@responses.activate
def test_predict_image_returns_json_safe_dict(eager_celery, stored_image):
    responses.post(PREDICT_URL, json=PREDICTION)

    result = predict_image.delay(stored_image).get()

    assert result["attempts"] == 1
    assert result["model"] == "kimchi-yolo"
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["defect_type"] == "foreign_object"
    assert result["candidates"][0]["bbox"] == [10.0, 12.0, 8.0, 6.0]
    assert json.loads(json.dumps(result)) == result  # same shape after the Redis JSON round trip  # must not raise: this is what crosses the Redis result backend
    assert responses.calls[0].request.body.count(synthetic_png()) == 1


@responses.activate
def test_predict_image_retries_when_server_is_unavailable(eager_celery, stored_image):
    responses.post(PREDICT_URL, status=503)
    responses.post(PREDICT_URL, json=PREDICTION)

    result = predict_image.delay(stored_image).get()

    assert result["attempts"] == 2
    assert len(responses.calls) == 2


@responses.activate
def test_predict_image_does_not_retry_rejected_image(eager_celery, stored_image):
    responses.post(PREDICT_URL, status=422, json={"detail": "cannot decode image"})

    with pytest.raises(AiServerRejected):
        predict_image.delay(stored_image).get()
    assert len(responses.calls) == 1


def test_retry_policy_only_covers_unavailable():
    assert predict_image.autoretry_for == (AiServerUnavailable,)
    assert AiServerRejected not in predict_image.autoretry_for
    assert AiServerContractError not in predict_image.autoretry_for
    assert predict_image.max_retries == 3


def test_ping(eager_celery):
    assert ping.delay().get() == "pong"


def test_celery_reads_django_settings():
    conf = celery_app.conf
    assert conf.broker_url == django_settings.REDIS_URL
    assert conf.task_acks_late is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_time_limit == 120


# --- ai_check command -----------------------------------------------------------------

HEALTH = {"status": "ok", "engine": "mock", "model_loaded": True}
MODEL = {"name": "kimchi-yolo", "engine": "mock", "version": "mock-0", "weights_sha256": None,
         "imgsz": 1280, "min_conf": 0.1, "class_names": ["foreign_object"]}


@responses.activate
def test_ai_check_prints_health_and_model(capsys):
    responses.get(f"{BASE_URL}/health", json=HEALTH)
    responses.get(f"{BASE_URL}/model", json=MODEL)

    call_command("ai_check")

    out = capsys.readouterr().out
    assert '"model_loaded": true' in out
    assert '"version": "mock-0"' in out


@responses.activate
def test_ai_check_fails_when_model_not_loaded():
    responses.get(f"{BASE_URL}/health", json={**HEALTH, "model_loaded": False})
    responses.get(f"{BASE_URL}/model", json=MODEL)

    with pytest.raises(CommandError):
        call_command("ai_check")


def test_ai_check_exits_nonzero_when_server_is_down():
    # A real process against a closed port: checks the exit code scripts will see.
    env = {**os.environ, "FASTAPI_BASE_URL": "http://127.0.0.1:9", "DB_HOST": ""}
    proc = subprocess.run(
        [sys.executable, "manage.py", "ai_check"],
        cwd=django_settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "AI server check failed" in proc.stderr
