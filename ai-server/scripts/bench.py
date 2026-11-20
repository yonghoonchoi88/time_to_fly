"""Latency benchmark for a running ai-server.

Sends images to POST /predict one at a time and reports p50 / p95 / max for the engine
latency (``latency_ms`` from the response) and the HTTP round trip. The first
``--warmup`` requests are excluded. Numbers depend on the model, images and CPU, so all
three are printed with the result.

    python scripts/bench.py --images path/to/folder
    python scripts/bench.py --synthetic 30 --size 640x480
"""

import argparse
import platform
import sys
import time
from pathlib import Path

import cv2
import httpx
import numpy as np

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q))


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(percentile(values, 50), 2),
        "p95": round(percentile(values, 95), 2),
        "max": round(max(values), 2),
    }


def cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def folder_images(folder: Path) -> list[tuple[str, bytes]]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    return [(p.name, p.read_bytes()) for p in files]


def synthetic_images(count: int, width: int, height: int) -> list[tuple[str, bytes]]:
    rng = np.random.default_rng(0)
    images = []
    for i in range(count):
        pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".png", pixels)
        if not ok:
            raise RuntimeError("failed to encode synthetic image")
        images.append((f"synthetic_{i:03d}.png", buf.tobytes()))
    return images


def run(url: str, images: list[tuple[str, bytes]], warmup: int) -> int:
    if len(images) <= warmup:
        print(f"need more than {warmup} images, got {len(images)}", file=sys.stderr)
        return 2

    engine_ms: list[float] = []
    round_trip_ms: list[float] = []
    with httpx.Client(base_url=url, timeout=120.0) as client:
        info = client.get("/model").raise_for_status().json()
        for index, (name, data) in enumerate(images):
            started = time.perf_counter()
            response = client.post("/predict", files={"file": (name, data)})
            elapsed = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            if index < warmup:
                continue
            engine_ms.append(float(response.json()["latency_ms"]))
            round_trip_ms.append(elapsed)

    print(f"model:      {info['name']} {info['version']} (engine={info['engine']}, imgsz={info['imgsz']})")
    print(f"weights:    {info['weights_sha256']}")
    print(f"cpu:        {cpu_name()}")
    print(f"images:     {len(engine_ms)} measured (+{warmup} warm-up excluded)")
    print(f"engine ms:  {summarize(engine_ms)}")
    print(f"round ms:   {summarize(round_trip_ms)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--images", type=Path, help="folder of images to send in name order")
    source.add_argument("--synthetic", type=int, help="number of random-noise images to generate")
    parser.add_argument("--size", default="640x480", help="synthetic image size WxH")
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args(argv)

    if args.images is not None:
        if not args.images.is_dir():
            parser.error(f"not a directory: {args.images}")
        images = folder_images(args.images)
    else:
        width, height = (int(v) for v in args.size.lower().split("x"))
        images = synthetic_images(args.synthetic, width, height)
    return run(args.url, images, args.warmup)


if __name__ == "__main__":
    sys.exit(main())
