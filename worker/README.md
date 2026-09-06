# Worker (Python)

Doorbell trigger → RTSP frame grab → face recognize → Home Assistant webhook.

Spec: [`../docs/spec.md`](../docs/spec.md) · Commands: [`../README.md`](../README.md)

## Layout

```
worker/
  main.py           entrypoint (HTTP /recognize, --once CLI)
  recognize.py      detect + match against gallery
  notify.py         POST results to HA webhook
  gallery.py        gallery pickle format + photo scan
  face_store.py     manifest.json + UUID photos under db/
  enroll.py         build db/gallery.pkl from manifest + photos
  enroll_web.py     web enroll API + doorbell MJPEG (/enroll)
  stream.py         RTSP frame grab (on demand)
  settings.py       pydantic-settings ← .env
  play_stream.py    RTSP smoke test (bun play-stream)
  tests/
  db/               homelab runtime only (manifest, photos, gallery.pkl)
  pyproject.toml
  requirements.txt
  requirements-vision.txt   InsightFace stack (homelab / Docker)
  requirements-dev.txt
```

## Mac vs homelab

|                         | Mac (dev)              | Homelab (3060)            |
| ----------------------- | --------------------- | ------------------------- |
| Edit code, pytest, ruff | ✓                     | — (Docker only)           |
| RTSP smoke test         | ✓ (`bun play-stream`) | — (use web UI / HA)       |
| Enroll faces (web UI)   | ✓ (browser)           | ✓ (browser → container)   |
| InsightFace + doorbell  | —                     | ✓ (`docker compose`)      |
| Docker prod             | —                     | ✓ (`cudnn-runtime` + GPU) |

`bun setup` installs dev deps including OpenCV (needed for `stream.py` and pytest).

## Dependencies

Three pip files — base + two overlays (each includes base via `-r requirements.txt`):

| File                      | Install via          | Why separate                          |
| ------------------------- | -------------------- | ------------------------------------- |
| `requirements.txt`        | (included by others) | Shared runtime: FastAPI, OpenCV, etc. |
| `requirements-dev.txt`    | `bun setup`          | Mac lint/test only                    |
| `requirements-vision.txt` | Docker build         | InsightFace + CUDA — homelab only     |

Do not merge vision into dev: `onnxruntime-gpu` does not belong on Mac.

## Setup

```bash
bun setup
cd worker && cp .env.example .env
```

## Env (`worker/.env`)

| Var                     | Default     | Role                                                                 |
| ----------------------- | ----------- | -------------------------------------------------------------------- |
| `STREAM_URL`            | —           | Video host/path (no credentials for RTSP)                            |
| `STREAM_USER`           | —           | RTSP username (plain text; encoded at runtime)                       |
| `STREAM_PASSWORD`       | —           | RTSP password (plain text; encoded at runtime)                       |
| `HA_WEBHOOK_URL`        | —           | HA notify webhook (secret in URL path)                               |
| `DB_DIR`                | `db`        | Enrollment data (`manifest.json`, `photos/`, `gallery.pkl`)          |
| `RECOGNITION_THRESHOLD` | `0.4`       | Match score cutoff (tune on homelab)                                 |
| `FRAMES_PER_EVENT`      | `5`         | RTSP frames to grab per doorbell ring                                |
| `WORKER_HOST`           | `127.0.0.1` | HTTP bind (`0.0.0.0` in Docker)                                      |
| `WORKER_PORT`           | `8768`      | HTTP port (`/recognize`, `/health`, `/enroll`)                       |
| `ENROLL_SECRET`         | — (open)    | Optional — set in homelab `.env` to require `?token=` on `/enroll/*` |

## Homelab (Docker only)

Doorman on homelab runs **only inside the worker container**. Do not install Python or run `main.py`
/ `enroll.py` on the host OS.

One-time: first `bun run deploy` creates `~/doorman/.env` from `.env.example` (the only app config
on the host — compose passes it into the container). Edit that file on homelab, then redeploy:

```bash
# on homelab — config file only; app stays in Docker
nano ~/doorman/.env
```

Set `STREAM_URL` at minimum (plus `STREAM_USER` / `STREAM_PASSWORD` for Reolink RTSP). Deploy from
Mac:

```bash
bun run deploy
```

One-off tasks (gallery rebuild, logs, shell) use compose — never host Python:

```bash
ssh homelab 'cd ~/doorman && docker compose logs worker --tail 30'
ssh homelab 'cd ~/doorman && docker compose exec worker python enroll.py -v'
```

## Tests

```bash
bun run test
```

## Enrollment

Web UI: `http://192.168.x.x:8768/enroll` (replace `x.x` with your homelab LAN IP; build with
`bun run build:web`). See [`../docs/enrollment.md`](../docs/enrollment.md).
