import subprocess
import sys
from pathlib import Path

import pytest

from models.yolo_engine import sha256_file, xyxy_to_xywh
from scripts.bench import summarize

ROOT = Path(__file__).resolve().parents[1]


def test_xyxy_to_xywh_converts_corners():
    assert xyxy_to_xywh([10, 20, 110, 70], width=640, height=480) == (10.0, 20.0, 100.0, 50.0)


def test_xyxy_to_xywh_clips_to_image():
    assert xyxy_to_xywh([-5, -5, 700, 500], width=640, height=480) == (0.0, 0.0, 640.0, 480.0)


def test_xyxy_to_xywh_rounds_to_one_decimal():
    assert xyxy_to_xywh([1.234, 2.345, 3.456, 4.567], width=10, height=10) == (1.2, 2.3, 2.2, 2.2)


def test_importing_engine_module_does_not_load_ultralytics():
    code = "import sys, models.yolo_engine; sys.exit('ultralytics' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT)
    assert result.returncode == 0


def test_sha256_file(tmp_path):
    path = tmp_path / "w.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_bench_summary():
    stats = summarize([float(v) for v in range(1, 101)])
    assert stats["p50"] == pytest.approx(50.5)
    assert stats["p95"] == pytest.approx(95.05)
    assert stats["max"] == 100.0
