## Project configuration

- **Language:** Python 3.11 in `worker/`
- **Tooling:** bun (scripts), husky, prettier, ruff
- **Rules:** `.cursor/rules/conventions.mdc`, `.cursor/rules/python-worker.mdc`

## Cold start (new chat / fresh context)

Read in this order:

1. [`WORKLOG.md`](WORKLOG.md) — active phase and what's next
2. [`docs/spec.md`](docs/spec.md) — product goal, stack (InsightFace), architecture, Mac vs homelab
3. [`docs/homelab.md`](docs/homelab.md) — RTX 3060, VRAM budget, deploy path `~/doorface`
4. [`worker/README.md`](worker/README.md) — env vars, flat module layout, homelab-only vision deps
5. [`README.md`](README.md) — commands (`bun setup`, `bun run test`, `bun deploy`)

**Resume phrase:** _"continue doorface"_ → start from `WORKLOG.md`, then implement the active phase
only.

**What exists:** RTSP grab (`stream.py`), `play_stream` smoke test, deploy scaffold.

**What does not exist yet:** Face enrollment, recognition, `/recognize` HTTP, HA notify webhook,
`/health`.

**Dev split:** Mac = edit + pytest + RTSP smoke test. Homelab = InsightFace + doorbell E2E. See spec
Development environments.

### Context files

| File                                   | When                      |
| -------------------------------------- | ------------------------- |
| [`WORKLOG.md`](WORKLOG.md)             | Active phase — start here |
| [`docs/spec.md`](docs/spec.md)         | Product + technical spec  |
| [`docs/homelab.md`](docs/homelab.md)   | GPU box, VRAM, network    |
| [`worker/README.md`](worker/README.md) | Env vars, Docker          |
| [`README.md`](README.md)               | Commands                  |

## Agent policy

- Git read-only unless user explicitly asks to mutate
- Never read `.env` unless asked; use `.env.example`
- One WORKLOG phase at a time
- "Review staged" → `.cursor/rules/pre-commit-review.mdc`

## Deploy

`bun deploy` rsyncs `worker/` to `~/doorface` on `homelab`, then rebuilds the Docker image. Secrets
live only in `~/doorface/.env` on the server.
