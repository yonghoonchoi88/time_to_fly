# ai-server — inference server (FastAPI)

[한국어](README.md)

Answers one question: "which defect candidates are in this image?". Verdicts (OK/NG/REVIEW), persistence and lots are handled by Django and its Celery workers (ADR 0001).

```
Django (intake, 202) → Redis → Celery worker ──POST /predict──▶ ai-server
                                            ◀── candidates JSON ──
```

## Run
```bash
cd ai-server
pip install -r requirements-dev.txt
pytest -q
uvicorn main:app --port 8001   # http://localhost:8001/docs
```

## API
- `POST /predict` (multipart, field `file`) → `{model, version, engine, latency_ms, width, height, candidates:[{defect_type, confidence, bbox:[x,y,w,h]}]}` · 422 undecodable · 413 too large
- `GET /health` → `{status, engine, model_loaded}`
- `GET /model` → `{name, engine, version, weights_sha256, imgsz, min_conf, class_names}`

## Environment
| Variable | Default | Notes |
|---|---|---|
| `ENGINE` | `mock` | `mock` \| `yolo` |
| `MODEL_WEIGHTS` | (none) | Required for yolo; startup fails if the file is missing |
| `MODEL_NAME` / `MODEL_VERSION` | `kimchi-yolo` / `mock-0` | Matched against Django `ModelVersion` |
| `IMGSZ` / `MIN_CONF` | `1280` / `0.10` | Inference size / noise floor (not a verdict threshold) |
| `MAX_UPLOAD_MB` | `10` | 413 above this |
| `MOCK_DEFECT_RATE` | `0.3` | Probability that the mock returns a candidate |

The mock engine seeds its RNG from a SHA-256 of the image pixels, so the same image always gets the same result.

## YOLO engine
```bash
pip install -r requirements-yolo.txt            # CPU torch + ultralytics
mkdir -p ../data/models && (cd ../data/models && python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')")
ENGINE=yolo MODEL_WEIGHTS=../data/models/yolo11n.pt MODEL_NAME=yolo11n MODEL_VERSION=yolo11n IMGSZ=640 uvicorn main:app --port 8001
```
The server refuses to start if the weights file is missing (no ultralytics auto-download). `/model` exposes `weights_sha256` of the weights actually being served.

## Docker
```bash
docker build -t ai-server ai-server                              # mock only
docker build --build-arg WITH_YOLO=1 -t ai-server ai-server      # with YOLO
docker run --rm -p 8001:8001 -e ENGINE=yolo -e MODEL_WEIGHTS=/models/yolo11n.pt \
  -e MODEL_NAME=yolo11n -e MODEL_VERSION=yolo11n -e IMGSZ=640 -v $PWD/data/models:/models:ro ai-server
```
Weights are mounted, never baked into the image.

## Latency benchmark
```bash
python scripts/bench.py --synthetic 30 --size 640x480    # synthetic images
python scripts/bench.py --images <folder>                 # images in a folder, name order
```
Prints p50 / p95 / max of engine time (`latency_ms`) and round trip, image count, CPU and model. The first image is a warm-up and excluded. Always report numbers with the model, images and CPU.
