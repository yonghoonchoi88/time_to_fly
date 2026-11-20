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
