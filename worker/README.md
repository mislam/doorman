# Worker (Python)

Doorbell trigger → RTSP frame grab → face recognize → Home Assistant webhook.

Spec: [`../docs/spec.md`](../docs/spec.md) · Commands: [`../README.md`](../README.md)

## Layout

```
worker/
  main.py           entrypoint (HTTP /recognize, --once CLI)
  recognize.py      detect + match against gallery
  gallery.py        gallery pickle format + photo scan
  enroll.py         build gallery.pkl from config/faces/
  stream.py         RTSP frame grab (on demand)
  settings.py       pydantic-settings ← .env
  play_stream.py    RTSP smoke test (bun play-stream)
  tests/
  config/
    faces/{name}/   enrollment photos (jpg/png gitignored)
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
| `bun enroll` (via SSH)  | ✓                     | ✓ (local if venv)         |
| InsightFace + doorbell  | —                     | ✓                         |
| Docker prod             | —                     | ✓ (`cudnn-runtime` + GPU) |

`bun setup` installs dev deps including OpenCV (needed for `stream.py` and pytest).

## Dependencies

Three pip files — base + two overlays (each includes base via `-r requirements.txt`):

| File                      | Install via                | Why separate                          |
| ------------------------- | -------------------------- | ------------------------------------- |
| `requirements.txt`        | (included by others)       | Shared runtime: FastAPI, OpenCV, etc. |
| `requirements-dev.txt`    | `bun setup`                | Mac lint/test only                    |
| `requirements-vision.txt` | Docker build, `bun enroll` | InsightFace + CUDA — homelab only     |

Do not merge vision into dev: `onnxruntime-gpu` does not belong on Mac.

## Setup

```bash
bun setup
cd worker && cp .env.example .env
```

## Env (`worker/.env`)

| Var                     | Default              | Role                                   |
| ----------------------- | -------------------- | -------------------------------------- |
| `STREAM_URL`            | —                    | Video source (RTSP, HTTP MJPEG, …)     |
| `HA_WEBHOOK_URL`        | —                    | HA notify webhook (secret in URL path) |
| `FACES_DIR`             | `config/faces`       | Enrollment photos per person subfolder |
| `GALLERY_PATH`          | `config/gallery.pkl` | Cached embeddings (gitignored)         |
| `RECOGNITION_THRESHOLD` | `0.4`                | Match score cutoff (tune on homelab)   |
| `FRAMES_PER_EVENT`      | `5`                  | RTSP frames to grab per doorbell ring  |
| `WORKER_HOST`           | `127.0.0.1`          | HTTP bind (`0.0.0.0` in Docker)        |
| `WORKER_PORT`           | `8768`               | HTTP port (`/recognize`, `/health`)    |

## Homelab

One-time: create secrets on the server (never rsync'd from Mac):

```bash
ssh homelab 'cd ~/doorface && cp .env.example .env && nano .env'
```

Set `STREAM_URL` at minimum. Then deploy:

```bash
bun run deploy
cd ~/doorface && docker compose up -d   # or rely on deploy to recreate
```

## Tests

```bash
bun run test
```

## Enrollment

See [`../docs/enrollment.md`](../docs/enrollment.md).
