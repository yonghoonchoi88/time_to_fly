[한국어](README.md) | English

# Defect-to-Action

> An inspection operations system that doesn't stop at **finding** a defect: it carries the result through
> **record → human review → field action → recurrence analysis**.

🚧 **v0.1 — in development.** Metrics and screenshots will be added once measured.

## Why

A highly accurate inspection model changes nothing on the floor unless its output reaches a person who decides
and acts. This project covers the operational loop after detection.

## Flow

```
Camera / line replay ─▶ Engine ─▶ Verdict (OK·NG·REVIEW) ─▶ Persist
                                    │
                    REVIEW / audit sample ─▶ Review queue ─▶ Confirm · Reject · Add missed
                                    │
                           Confirmed NG ─▶ Action (hold lot · recheck · stop line) ─▶ Done
                                                                    │
                                              History · recurrence · operational metrics
```

- **Swappable engines**: an engine only returns defect candidates; verdict rules live outside it.
- **Audit sampling**: missed defects never appear as candidates, so a share of OK verdicts is re-checked by a person.
- Data model: [docs/ontology.md](docs/ontology.md)

## Run

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health
```

Tests:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Status

| Stage | Status |
|---|---|
| Ontology · routing rules · mock engine | ✅ v0.1 |
| Inspection API · review queue · actions | ⬜ |
| Line replay / live stream | ⬜ |
| Dashboard · history | ⬜ |
| Operational metrics (Prometheus · Grafana) | ⬜ |

## Data policy

`data/` is git-ignored. NDA images, labels and model weights are never committed.
