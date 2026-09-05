# Worker (Python)

Doorbell trigger → RTSP frame grab → face recognize → Home Assistant webhook.

Spec: [`../docs/spec.md`](../docs/spec.md) · Commands: [`../README.md`](../README.md)

## Layout

```
worker/
  main.py           entrypoint (HTTP server — Phase 1)
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

|                         | Mac (dev)              | Homelab (3060)   |
| ----------------------- | --------------------- | ---------------- |
| Edit code, pytest, ruff | ✓                     | via SSH optional |
| RTSP smoke test         | ✓ (`bun play-stream`) | ✓                |
| InsightFace + doorbell  | —                     | ✓                |
| Docker prod             | —                     | ✓                |

`bun setup` installs dev deps including OpenCV (needed for `stream.py` and pytest).

## Setup

```bash
bun setup
cd worker && cp .env.example .env
```

## Env (`worker/.env`)

| Var                     | Default              | Role                                   |
| ----------------------- | -------------------- | -------------------------------------- |
| `RTSP_URL`              | —                    | Reolink stream                         |
| `HA_WEBHOOK_URL`        | —                    | HA notify webhook (secret in URL path) |
| `FACES_DIR`             | `config/faces`       | Enrollment photos per person subfolder |
| `GALLERY_PATH`          | `config/gallery.pkl` | Cached embeddings (gitignored)         |
| `RECOGNITION_THRESHOLD` | `0.4`                | Match score cutoff (tune on homelab)   |
| `FRAMES_PER_EVENT`      | `5`                  | RTSP frames to grab per doorbell ring  |
| `WORKER_HOST`           | `127.0.0.1`          | HTTP bind (`0.0.0.0` in Docker)        |
| `WORKER_PORT`           | `8768`               | HTTP port (`/recognize`, `/health`)    |

## Homelab

```bash
bun deploy
cd ~/doorface && docker compose up -d
```

## Tests

```bash
bun run test
```
