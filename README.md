# Doorman

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

| Command                     | What                                                   |
| --------------------------- | ------------------------------------------------------ |
| `bun setup`                 | Create `worker/.venv` and install dev deps             |
| `bun lint` / `bun lint:fix` | Prettier + Ruff                                        |
| `bun run test`              | pytest (`bun test` is Bun's runner — use `run`)        |
| `bun run convert:fixtures`  | PNG → JPEG for doorbell test images (Mac)              |
| `bun run test:integration`  | Doorbell fixture tests on homelab Docker (InsightFace) |
| `bun play-stream`           | RTSP smoke test (`-- -v` for verbose)                  |
| `bun run build:web`         | Build SvelteKit UI → `worker/static/enroll/`           |
| `bun run deploy`            | Rsync code → homelab + Docker rebuild                  |
| `bun status`                | Homelab Docker compose + GPU snapshot (in container)   |

Deploy overrides: `DEPLOY_HOST`, `DEPLOY_DIR` (default `homelab` / `doorman`). First Docker build
can take 10–15 min (CUDA base + InsightFace). After `compose up`, deploy waits for the container
healthcheck (`docker compose up --wait`) — model warmup can take a few minutes. Use
`DEPLOY_SKIP_BUILD=1` for code-only rsync; `DEPLOY_SKIP_HEALTH=1` to skip the wait; `DEPLOY_QUIET=1`
to hide build log.

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
# faces: https://192.168.x.x:8768/enroll
curl -k -X POST https://192.168.x.x:8768/recognize   # test recognition
```

| What                      | Mac | Homelab                |
| ------------------------- | --- | ---------------------- |
| pytest, lint, RTSP smoke  | ✓   | —                      |
| Doorbell fixture tests    | —   | ✓ (`test:integration`) |
| Enroll faces (web UI)     | ✓   | ✓ (photos on server)   |
| InsightFace / recognition | —   | ✓ Docker               |

You don't run recognition locally on Mac — pytest mocks InsightFace. Deploy when **code** changes;
use the **enroll UI** when **faces** change.

## Layout

```
docs/
worker/          flat Python modules + Docker (deployed to ~/doorman)
  stream.py      RTSP frame grab (on demand)
  main.py
  settings.py
  db/            homelab runtime only (manifest, photos, gallery.pkl — gitignored)
scripts/
web/             SvelteKit UI → worker/static/enroll/ (served at /enroll)
```

## Status

RTSP ingest and recognition pipeline work. HA notify in Phase 2. See [WORKLOG.md](WORKLOG.md).
