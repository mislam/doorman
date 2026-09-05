# Doorface

When the **Reolink doorbell rings**, recognize **enrolled family faces** from the camera stream and
send a **Home Assistant** notification (who's at the door, or unknown visitor).

Self-hosted on the homelab GPU (RTX 3060). Learning project — small scope, daily usefulness.

## Docs

| Doc                                        | Purpose                               |
| ------------------------------------------ | ------------------------------------- |
| [`docs/spec.md`](docs/spec.md)             | Product + technical spec              |
| [`docs/enrollment.md`](docs/enrollment.md) | Add family photos + build gallery     |
| [`docs/homelab.md`](docs/homelab.md)       | Shared AI rig hardware and GPU budget |
| [`worker/README.md`](worker/README.md)     | Python modules, env, Docker           |
| [`WORKLOG.md`](WORKLOG.md)                 | Active implementation phase           |

## Commands

| Command                     | What                                             |
| --------------------------- | ------------------------------------------------ |
| `bun setup`                 | Create `worker/.venv` and install dev deps       |
| `bun lint` / `bun lint:fix` | Prettier + Ruff                                  |
| `bun run test`              | pytest (`bun test` is Bun's runner — use `run`)  |
| `bun play-stream`           | RTSP smoke test (`-- -v` for verbose)            |
| `bun enroll`                | Build gallery.pkl from `config/faces/` (homelab) |
| `bun start`                 | Run `worker/main.py` (scaffold until Phase 1)    |
| `bun run deploy`            | Rsync `worker/` to homelab + Docker rebuild      |
| `bun status`                | Homelab GPU + compose snapshot                   |

Deploy overrides: `DEPLOY_HOST`, `DEPLOY_DIR` (default `homelab` / `doorface`).

## Local development (Mac)

```bash
bun install
bun setup
cd worker && cp .env.example .env   # STREAM_URL for play-stream
bun play-stream -- -v             # verify doorbell stream
bun run test
```

| What                          | Mac | Homelab          |
| ----------------------------- | --- | ---------------- |
| pytest, lint, RTSP smoke test | ✓   | optional via SSH |
| Face recognition + HA E2E     | —   | ✓                |

GPU inference and doorbell integration run on homelab. See [docs/spec.md](docs/spec.md) and
[worker/README.md](worker/README.md).

## Layout

```
docs/
worker/          flat Python modules + Docker (deployed to ~/doorface)
  stream.py      RTSP frame grab (on demand)
  main.py
  settings.py
  config/faces/  enrollment photos (gitignored jpgs)
scripts/
```

## Status

RTSP ingest works. Face recognition + HA notify in Phase 1. See [WORKLOG.md](WORKLOG.md).
