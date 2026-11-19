# API 계약 v0.1

세 명이 동시에 개발할 수 있도록 먼저 정해둔 API 모양입니다. 바꾸려면 먼저 이야기하고 이 파일을 고치는 PR을 올립니다.

## POST /inspections — 이미지 1장 검사

`multipart/form-data`

| 필드 | 필수 | 설명 |
|---|---|---|
| `file` | 필수 | 이미지 (jpg / png) |
| `lot_code` | 필수 | Lot 코드. 처음 보는 코드면 서버가 자동 생성 (재생 모드: 하위 폴더 이름) |
| `source` | 필수 | `replay` 또는 `live` |
| `captured_at` | 선택 | ISO 8601, UTC (예: `2026-11-20T09:00:00Z`). 없으면 서버 수신 시각 |

```json
// 201 Created
{
  "inspection_id": 12,
  "lot_code": "S01",
  "verdict": "REVIEW",
  "latency_ms": 3.1,
  "review_task_id": 5,
  "defects": [
    {"id": 30, "defect_type": "foreign_object", "confidence": 0.52,
     "bbox": [120.0, 88.0, 40.0, 32.0], "status": "candidate"}
  ]
}
```

- `verdict`: `OK` | `NG` | `REVIEW`
- `review_task_id`: 검수 대상이 아니면 `null`

## GET /inspections/{id}/image — 검사 이미지

이미지 바이트를 그대로 돌려줍니다.

## GET /review-tasks?status=pending&limit=50 — 검수 대기열

- `status`: `pending`(기본) | `done` · `limit`: 1~200 (기본 50) · 오래된 순서

```json
[
  {
    "id": 5,
    "reason": "low_confidence",
    "status": "pending",
    "decision": null,
    "reviewer": null,
    "created_at": "2026-11-20T09:00:01Z",
    "decided_at": null,
    "inspection": {
      "id": 12, "lot_code": "S01", "verdict": "REVIEW",
      "captured_at": "2026-11-20T09:00:00Z",
      "image_url": "/inspections/12/image", "width": 640, "height": 480
    },
    "defects": [
      {"id": 30, "defect_type": "foreign_object", "confidence": 0.52,
       "bbox": [120.0, 88.0, 40.0, 32.0], "status": "candidate"}
    ]
  }
]
```

- `reason`: `low_confidence` | `audit_sample`
- `bbox`: 원본 이미지 픽셀 기준 `[x, y, w, h]`

## POST /review-tasks/{id}/decision — 검수 결정

```json
{ "decision": "confirm", "reviewer": "kim" }
{ "decision": "reject",  "reviewer": "kim" }
{ "decision": "add_missed", "reviewer": "kim",
  "defect_type": "foreign_object", "bbox": [300, 210, 25, 25] }
```

| 응답 | 의미 |
|---|---|
| `200 OK` | 갱신된 검수 작업 반환 |
| `409 Conflict` | 이미 결정된 작업 |
| `422 Unprocessable Entity` | 필드 오류 (예: `add_missed`인데 `bbox` 없음) |

| 결정 | 후보 결함 | 추가되는 것 |
|---|---|---|
| `confirm` | 전부 `confirmed` (감사 샘플처럼 후보가 없으면 "OK 판정이 맞음"을 기록) | — |
| `reject` | 전부 `rejected` + `retrain_candidate=true` | — |
| `add_missed` | 전부 `rejected` + `retrain_candidate=true` (모델이 엉뚱한 곳을 가리킴) | 사람이 그린 결함 1개 (`confirmed`, `confidence=null`) |

- 결정 대상은 해당 검사의 후보 결함 **전체**입니다 (v0.1 단순화).
- `bbox`는 `[x, y, w, h]`, `x, y ≥ 0`, `w, h > 0`. `defect_type`·`bbox`는 `add_missed`에서만 허용됩니다.
- 모든 상태 변화는 Event로 남습니다.
