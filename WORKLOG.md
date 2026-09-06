# WORKLOG

Spec: [`docs/spec.md`](docs/spec.md)

## Active — Phase 2 integrate

- [ ] HA doorbell trigger → POST worker `/recognize` (automation — user config)
- [ ] HA notify webhook URL — in `worker/.env`
- [x] Worker POSTs recognition JSON to `HA_WEBHOOK_URL` after `/recognize`

## Done — Phase 1

**Goal:** Enroll family faces from photos; detect + match on RTSP grab; stdout log.

- [x] `stream.py` — RTSP grab on demand (reconnect backoff)
- [x] `enroll.py` — build gallery from `db/manifest.json` + `db/photos/`
- [x] `recognize.py` — InsightFace detect + match
- [x] `main.py` — HTTP `/recognize` or CLI for testing
- [x] Web enroll UI (`/enroll`)

## Backlog

| Phase         | Deliverable                                  |
| ------------- | -------------------------------------------- |
| 1 — Recognize | Gallery + match on doorbell frame grab       |
| 2 — Integrate | HA webhook notify with names                 |
| 3 — Ship      | `/health`, compose healthcheck, doorbell E2E |
| 4 — Tune      | Thresholds, stream choice, guest enrollment  |

## Done

| Date       | Item                                                                    |
| ---------- | ----------------------------------------------------------------------- |
| 2026-09-05 | `face_store.py` — `db/manifest.json` + UUID photos; `enroll-ui` → `web` |
| 2026-09-05 | `notify.py` — POST recognition payload to HA webhook after `/recognize` |
| 2026-09-05 | `enroll.py` + `gallery.py` — enrollment gallery from photos on disk     |
| 2026-09-05 | `stream.py` + `play_stream` RTSP smoke test                             |
| 2026-09-04 | Phase 0: docs, flat worker modules, bun tooling, deploy/status scripts  |
