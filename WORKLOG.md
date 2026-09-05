# WORKLOG

Spec: [`docs/spec.md`](docs/spec.md)

## Active — Phase 1 prep

User inputs before face recognition work:

- [x] Stream URL — in `worker/.env` (Reolink RTSP prod; ESP HTTP MJPEG dev)
- [ ] HA doorbell trigger → POST worker `/recognize` (automation)
- [ ] HA notify webhook URL — in `worker/.env`
- [x] Enrollment photos per family member via web UI ([guide](docs/enrollment.md))

## Next — Phase 1

**Goal:** Enroll family faces from photos; detect + match on RTSP grab; stdout log (no HA yet).

Suggested files: `enroll.py`, `recognize.py`, wire trigger stub in `main.py`.

- [x] `stream.py` — RTSP grab on demand (reconnect backoff)
- [x] `enroll.py` — build gallery from `config/faces/`
- [x] `recognize.py` — InsightFace detect + match
- [x] `main.py` — HTTP `/recognize` or CLI for testing

## Backlog

| Phase         | Deliverable                                  |
| ------------- | -------------------------------------------- |
| 1 — Recognize | Gallery + match on doorbell frame grab       |
| 2 — Integrate | HA webhook notify with names                 |
| 3 — Ship      | `/health`, compose healthcheck, doorbell E2E |
| 4 — Tune      | Thresholds, stream choice, guest enrollment  |

## Done

| Date       | Item                                                                   |
| ---------- | ---------------------------------------------------------------------- |
| 2026-09-05 | `enroll.py` + `gallery.py` — enrollment gallery from `config/faces/`   |
| 2026-09-05 | `stream.py` + `play_stream` RTSP smoke test                            |
| 2026-09-04 | Phase 0: docs, flat worker modules, bun tooling, deploy/status scripts |
