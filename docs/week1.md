# 1주차 작업 목록 (11/20 – 11/26)

목표: **가짜 엔진으로 "검사 → 기록 → 검수 → 조치 → 이력"이 API로 한 바퀴 돈다.**
아래 항목을 GitHub 이슈로 하나씩 만들고 담당자를 지정합니다.

| # | 이슈 | 담당 | 완료 조건 |
|---|---|---|---|
| 1 | 저장소 세팅 · `docker compose up`으로 `/health` 확인 | 최용훈 | 세 명 모두 각자 PC에서 `/health` 200 |
| 2 | `POST /inspections` — 이미지 업로드 → `record_inspection` 호출 | 최용훈 | 판정·Defect·ReviewTask 응답 + 테스트 |
| 3 | `GET /review-tasks?status=pending` · `POST /review-tasks/{id}/decision` | 최용훈 | confirm / reject / add_missed 각각 테스트, 반려 시 `retrain_candidate=True` |
| 4 | `POST /actions` · `POST /actions/{id}/status` (Lot 격리 연동) | 최용훈 | `hold_lot` 생성 시 Lot이 `on_hold`, 잘못된 전이는 409 |
| 5 | 라인 재생기: 폴더의 이미지를 초당 N장 `POST /inspections`로 전송 | 팀원 A | finger_counter `ipwebcam_simulator.py` 구조 재사용, 세션 폴더 = Lot |
| 6 | 검수 대기열 화면 (이미지 + bbox + 승인/반려 버튼) | 팀원 B | 이슈 3 API로 동작, 단축키 지원 |
| 7 | 이력 조회 API: Lot 하나의 Inspection → Defect → Review → Action 타임라인 | 최용훈 | Event 테이블 기준, 시간순 |
| 8 | 교수님께 김치 데이터 영상·데모 사용 허락 문의 | 최용훈 | 답변 기록 (허락 범위: 블러/원본, 영상 공개 범위) |

## 이번 주에 하지 않는 것

진짜 엔진, Prometheus/Grafana, Discord 알림, LLM 보고서. 다음 주 이후입니다.

## 확인 질문 (최용훈 본인용 — 면접 대비)

1. 판정 규칙을 엔진 안에 두지 않은 이유는? 다른 방법을 택했다면 무엇이 깨지나?
2. 기준값을 `ModelVersion`에 저장하는 이유는?
3. 샘플링 감사 없이는 왜 놓친 결함을 측정할 수 없나?
4. Action을 Defect가 아니라 Lot에 연결한 이유는?
5. `confirmed → rejected` 전이를 막은 이유는? 검수자가 실수했다면 어떻게 바로잡나?
