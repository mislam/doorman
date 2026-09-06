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
| Edit code, pytest, ruff | ✓                     | via SSH optional          |
| RTSP smoke test         | ✓ (`bun play-stream`) | ✓                         |
| Enroll faces (web UI)   | ✓ (browser)           | ✓                         |
| InsightFace + doorbell  | —                     | ✓                         |
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

Compose runs the worker as UID/GID `1000` by default (`compose.yaml`). If homelab `id -u` is not
`1000` and enroll hits permission errors, add `DOCKER_UID` / `DOCKER_GID` to homelab `.env` and run
`./scripts/fix-homelab-config-perms.sh`.

## Homelab

One-time: homelab `.env` is created from `.env.example` on first deploy (never overwritten). Edit on
the server for real stream URL and secrets:

```bash
ssh homelab 'cd ~/doorman && nano .env'
```

Set `STREAM_URL` at minimum (plus `STREAM_USER` / `STREAM_PASSWORD` for Reolink RTSP). Then deploy:

```bash
bun run deploy
cd ~/doorman && docker compose up -d   # or rely on deploy to recreate
```

## Tests

```bash
bun run test
```

## Enrollment

Web UI: `http://homelab:8768/enroll` (build with `bun run build:web`). See
[`../docs/enrollment.md`](../docs/enrollment.md).
