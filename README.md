# Doorface

When the **Reolink doorbell rings**, recognize **enrolled family faces** from the camera stream and
send a **Home Assistant** notification (who's at the door, or unknown visitor).

Self-hosted on the homelab GPU (RTX 3060). Learning project — small scope, daily usefulness.

## Docs

| Doc                                        | Purpose                               |
| ------------------------------------------ | ------------------------------------- |
| [`docs/spec.md`](docs/spec.md)             | Product + technical spec              |
| [`docs/enrollment.md`](docs/enrollment.md) | Enroll faces via web UI               |
| [`docs/homelab.md`](docs/homelab.md)       | Shared AI rig hardware and GPU budget |
| [`worker/README.md`](worker/README.md)     | Python modules, env, Docker           |
| [`WORKLOG.md`](WORKLOG.md)                 | Active implementation phase           |

## Commands

| Command                     | What                                                |
| --------------------------- | --------------------------------------------------- |
| `bun setup`                 | Create `worker/.venv` and install dev deps          |
| `bun lint` / `bun lint:fix` | Prettier + Ruff                                     |
| `bun run test`              | pytest (`bun test` is Bun's runner — use `run`)     |
| `bun play-stream`           | RTSP smoke test (`-- -v` for verbose)               |
| `bun run build:enroll`      | Build SvelteKit enroll UI → `worker/static/enroll/` |
| `bun run deploy`            | Rsync code → homelab + Docker rebuild               |
| `bun status`                | Homelab GPU + compose snapshot                      |

Deploy overrides: `DEPLOY_HOST`, `DEPLOY_DIR` (default `homelab` / `doorface`). First Docker build
can take 10–15 min (CUDA base + InsightFace). After `compose up`, deploy waits for `/health` (model
warmup — prints progress every 10s). Use `DEPLOY_SKIP_BUILD=1` for code-only rsync;
`DEPLOY_SKIP_HEALTH=1` to skip the wait; `DEPLOY_QUIET=1` to hide build log.

## Development workflow

**Mac (fast loop)** — edit code, pytest, lint, RTSP smoke test:

```bash
bun install && bun setup
cd worker && cp .env.example .env   # STREAM_URL for play-stream
bun run test
bun play-stream -- -v               # optional: verify stream URL
```

**Homelab (GPU truth)** — enrollment and recognition run in Docker:

```bash
bun run deploy                      # code / UI changes
# faces: http://homelab:8768/enroll → Enroll now
curl -X POST http://192.168.1.100:8768/recognize   # test recognition
```

| What                      | Mac | Homelab              |
| ------------------------- | --- | -------------------- |
| pytest, lint, RTSP smoke  | ✓   | —                    |
| Enroll faces (web UI)     | ✓   | ✓ (photos on server) |
| InsightFace / recognition | —   | ✓ Docker             |

You don't run recognition locally on Mac — pytest mocks InsightFace. Deploy when **code** changes;
use the **enroll UI** when **faces** change.

## Layout

```
docs/
worker/          flat Python modules + Docker (deployed to ~/doorface)
  stream.py      RTSP frame grab (on demand)
  main.py
  settings.py
  config/faces/  homelab runtime only — empty skeleton in repo (.gitkeep)
scripts/
enroll-ui/       SvelteKit enroll UI → worker/static/enroll/
```

## Status

RTSP ingest and recognition pipeline work. HA notify in Phase 2. See [WORKLOG.md](WORKLOG.md).
