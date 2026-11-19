# Daily log

하루에 파일 1개: `YYYY-MM-DD.csv` (UTF-8 BOM, 엑셀에서 바로 열림). 한 줄 = 한 사람의 작업 1건.

| 열 | 내용 |
|---|---|
| `date` | 작업 날짜 |
| `member` · `github` · `role` | 누가 |
| `category` | setup · planning · feature · fix · test · docs · review · data · verify |
| `issue` · `pr` | 연결된 이슈 · PR 번호 (없으면 빈칸) |
| `work` | 무엇을 했나 |
| `result` | merged · approved · closed 등 상태 |
| `evidence` | 확인 근거 (테스트 수, 실행 결과 등 **측정한 값만**) |
| `next_step` | 이어서 할 일 |

회사 데이터(NDA)의 파일 이름 · 내용은 적지 않습니다. 개수와 용도만 적습니다.
