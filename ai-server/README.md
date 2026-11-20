# ai-server — AI 추론 서버 (FastAPI)

[English](README.en.md)

"이 사진에 어떤 결함 후보가 있나"만 답하는 서버입니다. OK/NG/REVIEW 판정, DB 저장, Lot 처리는 Django와 Celery 워커가 맡습니다 (ADR 0001).

```
Django(접수, 202) → Redis → Celery 워커 ──POST /predict──▶ ai-server
                                       ◀── 후보 목록 JSON ──
```

## 실행
```bash
cd ai-server
pip install -r requirements-dev.txt
pytest -q
uvicorn main:app --port 8001   # http://localhost:8001/docs
```

## API
- `POST /predict` (multipart, 필드 `file`) → `{model, version, engine, latency_ms, width, height, candidates:[{defect_type, confidence, bbox:[x,y,w,h]}]}` · 422 디코드 불가 · 413 용량 초과
- `GET /health` → `{status, engine, model_loaded}`
- `GET /model` → `{name, engine, version, weights_sha256, imgsz, min_conf, class_names}`

## 환경변수
| 변수 | 기본값 | 설명 |
|---|---|---|
| `ENGINE` | `mock` | `mock` \| `yolo` |
| `MODEL_WEIGHTS` | (없음) | yolo일 때 필수, 파일이 없으면 시작 실패 |
| `MODEL_NAME` / `MODEL_VERSION` | `kimchi-yolo` / `mock-0` | Django `ModelVersion`과 맞춰 볼 이름 |
| `IMGSZ` / `MIN_CONF` | `1280` / `0.10` | 추론 크기 / 노이즈 하한 (판정 기준 아님) |
| `MAX_UPLOAD_MB` | `10` | 초과 시 413 |
| `MOCK_DEFECT_RATE` | `0.3` | mock에서 후보가 나올 확률 |

mock 엔진은 이미지 픽셀의 sha256으로 시드를 만들어 같은 사진에 항상 같은 결과를 돌려줍니다.

## YOLO 엔진
```bash
pip install -r requirements-yolo.txt            # CPU torch + ultralytics
mkdir -p ../data/models && (cd ../data/models && python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')")
ENGINE=yolo MODEL_WEIGHTS=../data/models/yolo11n.pt MODEL_NAME=yolo11n MODEL_VERSION=yolo11n IMGSZ=640 uvicorn main:app --port 8001
```
가중치 파일이 없으면 서버가 시작되지 않습니다 (ultralytics 자동 다운로드를 쓰지 않음). `/model`의 `weights_sha256`으로 실제 서빙 중인 가중치를 확인합니다.

## Docker
```bash
docker build -t ai-server ai-server                              # mock 전용
docker build --build-arg WITH_YOLO=1 -t ai-server ai-server      # YOLO 포함
docker run --rm -p 8001:8001 -e ENGINE=yolo -e MODEL_WEIGHTS=/models/yolo11n.pt \
  -e MODEL_NAME=yolo11n -e MODEL_VERSION=yolo11n -e IMGSZ=640 -v $PWD/data/models:/models:ro ai-server
```
가중치는 이미지에 넣지 않고 마운트합니다.

## 지연시간 측정
```bash
python scripts/bench.py --synthetic 30 --size 640x480    # 합성 이미지
python scripts/bench.py --images <폴더>                   # 폴더의 이미지를 이름순으로
```
엔진 시간(`latency_ms`)과 왕복 시간의 p50 / p95 / 최대, 장수, CPU, 모델을 출력합니다. 첫 1장은 워밍업으로 제외합니다. 숫자는 모델 · 이미지 · CPU와 함께 적습니다.
