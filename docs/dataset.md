# 데이터 카드 — kimchi_v1

> 이 문서는 데이터의 **설명**만 담는다. 이미지·라벨·가중치는 저장소에 넣지 않는다.

## 출처와 사용 범위

| 항목 | 내용 |
|---|---|
| 출처 | 김치 제조 라인 이물 검사 이미지 (회사 제공, NDA) |
| 허락받은 범위 | 지원 영상, 포트폴리오 (2026-11-19 확인), 팀 내부 개발 공유 (같은 과정 수강생 2명) |
| 허락받지 않은 것 | 원본 이미지·라벨·가중치·매니페스트의 저장소 커밋, 외부 공개, 제3자 재배포 |
| 팀 공유 위치 | 비공개 Google Drive 폴더 (링크는 팀 채팅에만, 저장소에 적지 않음) |
| 화면·영상 노출 | 블러 처리한 이미지만 사용 |
| 새 데이터 | 추가 수급 없음. 아래 900장이 전부 |

## 분할 (세션 단위)

같은 촬영 세션의 사진이 학습과 평가에 동시에 들어가면 성능이 부풀려진다. 그래서 **촬영 세션(capture_group) 단위**로 나눴다. 분할 검증(누락·중복·세션 누수·Test 고정)은 전부 PASS.

| 분할 | 장수 | 용도 | 규칙 |
|---|---:|---|---|
| train | 600 | 학습 | — |
| val | 74 | 학습 중 검증, **판정 기준값(0.25 / 0.7) 조정** | 기준값은 val에서만 정한다 |
| test (Frozen) | 80 | 최종 성능 1회 보고 | **다시 쓰지 않는다.** 기준값 조정·모델 선택에 사용 금지 (fingerprint `4f9291849fe6`) |
| bridge (Holdout) | 146 | 라인 재생기 시연, 운영 지표 측정 | 학습·조정에 쓰지 않는다 |
| 합계 | 900 | | |

## 모델

| 항목 | 값 |
|---|---|
| 가중치 | `final_best.pt` (실험 exp001, yolo11n 기반) — 로컬 `data/` 아래에만 보관 |
| 가중치 sha256 | `029c0e92e59467fbef0dbb412bca6c9e1b51de34cb37c73eb4e3486e62e2d67f` |
| 추론 크기 | `imgsz=1280` |
| 노이즈 하한 | ai-server `MIN_CONF=0.10` (판정 기준 아님) |
| 판정 기준값 | Django `ModelVersion`에 저장 (ADR 0001) |
| 클래스 | 0 leaf_paper · 1 plastic_stone_metal · 2 branch · 3 insect · 4 rubber_glove_unused(미사용) · 5 disease_browning · 6 green_onion_pepper |
| 라벨 형식 | YOLO txt (`class cx cy w h`, 0~1 정규화), 사진 1장당 1개 |

## 로컬 배치

```
data/                      # git-ignored (data/README.md 제외)
├── kimchi_v1/
│   ├── final/images, final/labels   # 900장 + 라벨 900개
│   └── kimchi_v1_split.csv          # file_name, capture_group, role
├── replay/                # bridge를 Lot 폴더 구조로 복사한 것
└── models/final_best.pt   # ai-server 컨테이너에 -v로 마운트
```

## 지표를 쓸 때

- test 결과는 1회 측정한 값만 인용하고, 측정 날짜·가중치 sha256을 같이 적는다.
- bridge 재생 결과(FPS, 지연, 감지→조치 시간)는 측정 환경(CPU, 재생 fps)과 함께 적는다.
- mock 엔진이나 공개 모델(yolo11n)로 잰 숫자는 "파이프라인 확인용"이며 성과 수치가 아니다.
