# 실행 가이드 (Docker Compose)

저장소 루트에서 실행합니다. 서비스 구성:

| 서비스 | 역할 | 포트 |
|---|---|---|
| `db` | PostgreSQL 16 (`d2a` = 옛 FastAPI, `d2a_django` = Django) | - |
| `db-init` | `d2a_django`가 없으면 만들고 끝나는 1회용 컨테이너 | - |
| `redis` | Celery 작업 대기열 | - |
| `fastapi` | ai-server, 추론만 (기본 mock 엔진) | 8001 |
| `web` | Django + DRF (시작할 때 migrate 후 gunicorn) | 8000 |
| `celery` | Celery 워커 (`--concurrency=1`) | - |
| `api` | 옛 FastAPI (`--profile legacy`일 때만) | 8080 |

## 1. 실행

```bash
cp -n .env.example .env          # .env가 이미 있으면 그대로 둠
mkdir -p data/images data/models # 없으면 Docker가 root 소유로 만들어 내 계정으로 못 씀
docker compose up --build -d
docker compose ps
```

정상이면 `db` `redis` `fastapi` `web`은 `Up (healthy)`, `celery`는 `Up`입니다. 새 볼륨으로 처음 띄울 때는 DB 초기화 때문에 시간이 걸립니다 (느린 PC에서 db가 healthy까지 약 40초). `db-init`은 할 일을 끝내고 `exited (0)`로 보입니다 (`docker compose ps -a`).

## 2. 확인

```bash
curl localhost:8000/api/health/              # {"status":"ok","db":"ok"}
curl localhost:8001/health                   # {"status":"ok","engine":"mock","model_loaded":true}
docker compose exec web python manage.py ai_check
```

Celery 왕복 (Redis → 워커 → ai-server). 예시 이미지는 검수 화면용 합성 이미지입니다.

```bash
mkdir -p data/images && cp backend/static/review/mock/sample.png data/images/
docker compose exec web python manage.py shell -c "
from apps.ai_gateway.tasks import ping, predict_image
print(ping.delay().get(timeout=15))
print(predict_image.delay('sample.png').get(timeout=60))"
docker compose logs celery --tail 20
```

브라우저: http://localhost:8000/review/ · http://localhost:8000/admin/

관리자 계정 (DB마다 따로):

```bash
docker compose exec web python manage.py createsuperuser
```

## 3. YOLO 엔진으로 바꾸기

가중치 파일을 `data/models/`에 두고 (Git 제외, NDA) `.env`에 추가합니다.

```
WITH_YOLO=1
ENGINE=yolo
MODEL_WEIGHTS=/models/final_best.pt
MODEL_VERSION=<버전 이름>
```

```bash
docker compose up --build -d fastapi
curl localhost:8001/model                    # weights_sha256으로 실제 가중치 확인
```

## 4. 종료

```bash
docker compose down        # 컨테이너만 내림, DB 데이터는 유지
docker compose down -v     # DB 볼륨까지 삭제 (처음 상태로)
```

## 5. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| `port is already allocated` (8000/8001) | `runserver`·`uvicorn`이 이미 켜져 있음 → 끄고 다시 `up` |
| `db-init` 실패, `password authentication failed` | DB 볼륨을 만들 때와 `.env`의 `POSTGRES_PASSWORD`가 다름 → 원래 값으로 되돌리거나 `docker compose down -v` |
| `web`이 `unhealthy` | `docker compose logs web` → migrate 오류나 DB 연결 확인 |
| `celery`가 시작 안 함 | `fastapi`가 healthy가 될 때까지 기다림 → `docker compose logs fastapi` |
| `data/images`에 파일 복사 시 `허가 거부` | Docker가 폴더를 root로 만듦 → `sudo chown -R "$USER":"$USER" data` |
| celery 로그의 superuser 경고 | 컨테이너가 root로 실행되어 나오는 경고. 동작에는 영향 없음 |
