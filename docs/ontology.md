# Ontology 설계 v0.1

검사 결과를 "표 한 장"이 아니라 **현장의 사물·판단·조치를 연결한 객체 그래프**로 저장한다.
목표는 하나의 결함에서 출발해 "어느 Lot에서, 어떤 모델이, 누가 확인했고, 무슨 조치를 했으며, 얼마나 걸렸는가"를
한 번에 따라갈 수 있게 하는 것이다.

## 1. 객체 (Object types)

| 객체 | 의미 | 핵심 속성 |
|---|---|---|
| `ProductionLine` | 생산 라인 | name, site |
| `Lot` | 생산 묶음 (김치: 촬영 세션 1개 = Lot 1개) | code, product_type, status |
| `ModelVersion` | 검사 엔진 + 판정 기준값 | name, engine, weights_sha256, auto_ng_conf, review_conf |
| `Inspection` | 이미지 1장에 대한 검사 1회 | image_path, status(queued/done/failed), captured_at, received_at, completed_at, source(live/replay), verdict, image_width/height, engine_latency_ms, is_audit_sample, failure_reason |
| `Defect` | 결함 후보 1개 | defect_type, confidence, bbox, origin(model/human), status |
| `ReviewTask` | 사람이 확인해야 할 일 | reason(low_confidence/audit_sample), status, reviewer, decided_at |
| `Action` | 현장 조치 | action_type, status, owner, opened_at, closed_at, note |
| `Event` | 모든 상태 변화 기록 (감사 로그, 수정·삭제 불가) | lot, object_type, object_id, event, actor, at, payload |

## 2. 관계 (Link types)

```
ProductionLine 1 ──< Lot 1 ──< Inspection 1 ──< Defect
                      │            │  └── ModelVersion (어떤 모델이 판정했나)
                      │            └──< ReviewTask
                      └──< Action >── (선택) Defect
```

- Action은 **Lot에 걸린다** (격리·재검은 Lot 단위로 한다). 어떤 결함 때문에 열렸는지는 `defect_id`로 남긴다.
- Event는 어떤 객체든 가리킬 수 있다. 지표(감지→조치 시간 등)는 Event에서 계산한다.

## 3. 판정 규칙 (Routing)

엔진은 Defect 후보 목록만 돌려준다. **판정은 엔진 밖에서 한다.** 그래서 엔진을 바꿔도 규칙은 같다.

| 조건 | 판정 | 다음 단계 |
|---|---|---|
| 후보 중 하나라도 `confidence ≥ auto_ng_conf` | `NG` | 해당 Defect는 confirmed, Lot에 Action 생성 가능 |
| 최고 신뢰도가 `review_conf ≤ c < auto_ng_conf` | `REVIEW` | ReviewTask(reason=low_confidence) 생성 |
| 그 외 | `OK` | 확률 `audit_rate`로 무작위 추출 → ReviewTask(reason=audit_sample) |

- `review_conf` 미만 후보는 버리지 않고 저장만 한다 (나중에 기준값을 바꿔 다시 평가할 수 있게).
- **샘플링 감사가 필요한 이유:** 모델이 놓친 결함(FN)은 후보로 뜨지 않으므로 검수 대기열에 들어오지 않는다.
  김치 모델은 Val 기준 놓침이 60건 남아 있었다. OK 판정 일부를 사람이 다시 봐야 이 놓침을 잡을 수 있다.
- 기준값은 `ModelVersion`에 고정한다. 김치 프로젝트에서 배운 대로, 자동 최적 임계값이 아니라 **고정 임계값**으로 비교해야
  버전 간 수치가 왜곡되지 않는다.

## 4. 허용 동작 (Action types = 상태 전이)

정해진 동작으로만 상태가 바뀐다. 모든 동작은 Event를 남긴다.

**Defect.status**
- `candidate → confirmed` : 결함 승인 (검수자)
- `candidate → rejected` : 오탐 반려 (검수자) → 해당 이미지가 재학습 후보로 표시됨
- 자동 NG는 `confirmed`로 생성 (actor = `system`)

**ReviewTask.status**
- `pending → done` (decision: `confirm` / `reject` / `add_missed`)
- 결정의 의미는 대기열에 들어온 이유에 따라 다르다.

| decision | low_confidence (모델이 애매했던 경우) | audit_sample (OK 판정 무작위 재확인) |
|---|---|---|
| `confirm` | 후보 → confirmed | **OK 판정이 맞음**: 기준 미만 후보 → rejected, 재학습 표시 안 함 |
| `reject` | 후보 → rejected, 재학습 표시 | 허용 안 함 (반려할 경보가 없음) |
| `add_missed` | 사람 결함 추가(confirmed), 후보 → rejected + 재학습 표시 | 같음. 이 건수가 "감사로 되찾은 놓침" 지표 |

**Action.status**
- `open → in_progress → done`, `open/in_progress → cancelled`

**Lot.status**
- `open → on_hold` : 격리 조치(`hold_lot`)가 **열리는 즉시** (격리는 서류를 기다리지 않는다)
- `on_hold → released` : 해제 조치(`release_lot`)가 **완료(done)될 때** (실제 재검이 끝난 뒤)
- `on_hold → scrapped` : 폐기 (v0.1에서는 API 미제공)
- 조치를 취소해도 Lot 상태는 되돌리지 않는다. 보류 해제는 `release_lot`으로만.

`backend/apps/inspection/domain/transitions.py`가 이 표의 코드 버전이다. 표에 없는 전이는 `InvalidTransition`으로 거부한다.

## 5. 지표 (Event에서 계산)

| 지표 | 정의 |
|---|---|
| 처리 지연 | `Inspection.latency_ms` (엔진 추론 + 판정) |
| 처리량 | 분당 Inspection 수 (재생 모드에서는 카메라 FPS가 아니라 처리량으로 표기) |
| 검수 대기 시간 | ReviewTask 생성 → 결정 |
| **감지 → 조치 완료 시간** | Inspection.captured_at → 연결된 Action.closed_at (API: `detection_to_done_s`) |
| 오탐 비율 | rejected / (confirmed + rejected) |
| 감사로 되찾은 놓침 | audit ReviewTask 중 `add_missed` 건수 |

> 수치는 측정한 것만 쓴다. 측정 전 값은 "예상"으로 표시한다.

## 6. 의도적으로 뺀 것 (v0.1)

- 사용자/권한 테이블: 지금은 `actor` 문자열로 충분. 필요해지면 추가.
- 재학습 파이프라인: 반려 이미지를 표시하는 데까지만. 실제 재학습은 범위 밖.
- Kubernetes.
