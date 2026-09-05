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

| Command                     | What                                                  |
| --------------------------- | ----------------------------------------------------- |
| `bun setup`                 | Create `worker/.venv` and install dev deps            |
| `bun lint` / `bun lint:fix` | Prettier + Ruff                                       |
| `bun run test`              | pytest (`bun test` is Bun's runner — use `run`)       |
| `bun play-stream`           | RTSP smoke test (`-- -v` for verbose)                 |
| `bun enroll`                | Sync `config/faces/` → homelab + build `gallery.pkl`  |
| `bun start`                 | Run worker on homelab (`-- --once` for one-shot test) |
| `bun run deploy`            | Rsync code → homelab + Docker rebuild (not gallery)   |
| `bun status`                | Homelab GPU + compose snapshot                        |

Deploy overrides: `DEPLOY_HOST`, `DEPLOY_DIR` (default `homelab` / `doorface`). First Docker build
can take 10–15 min (CUDA base + InsightFace). Use `DEPLOY_SKIP_BUILD=1` for code-only rsync;
`DEPLOY_QUIET=1` to hide build log (Tasmi-style).

## Development workflow

**Mac (fast loop)** — edit code, pytest, lint, RTSP smoke test:

```bash
bun install && bun setup
cd worker && cp .env.example .env   # STREAM_URL for play-stream
bun run test
bun play-stream -- -v               # optional: verify stream URL
```

**Homelab (GPU truth)** — after code or face changes:

```bash
bun enroll                          # photos changed → sync faces + rebuild gallery.pkl
bun run deploy                      # code changed → rsync + Docker rebuild
ssh homelab 'cd ~/doorface && .venv/bin/python main.py --once'   # test recognition
```

| What                          | Mac                       | Homelab |
| ----------------------------- | ------------------------- | ------- |
| pytest, lint, RTSP smoke test | ✓                         | —       |
| `bun enroll` (sync + gallery) | ✓ runs on homelab via SSH | ✓       |
| InsightFace / recognition     | —                         | ✓       |
| Docker prod (`/recognize`)    | —                         | ✓       |

You don't run recognition locally on Mac — pytest mocks InsightFace. Real inference needs homelab,
but you only deploy when **code** changes; `bun enroll` is the lightweight path for **photo**
changes.

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

RTSP ingest and recognition pipeline work. HA notify in Phase 2. See [WORKLOG.md](WORKLOG.md).
