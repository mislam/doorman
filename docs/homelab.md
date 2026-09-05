# Homelab AI server

GPU VRAM budget and deploy notes for the home inference box that runs Doorman (`~/doorman` on host
`homelab`).

## Status

| Step                  | Status              |
| --------------------- | ------------------- |
| Hardware built        | **Done**            |
| Doorman vision worker | **In progress**     |

## Hardware (summary)

| Component | Notes                             |
| --------- | --------------------------------- |
| GPU       | NVIDIA RTX 3060 12 GB — inference |
| CPU / RAM | Ryzen 5-class · 32 GB RAM         |

Wired Ethernet to the server; reserved DHCP lease for a stable LAN IP.

## GPU capacity (RTX 3060 12 GB)

Rough **inference** VRAM (`nvidia-smi` often ~0.5–1 GB above weight-only estimates).

### Running alongside other GPU work

The homelab already runs another GPU service (~2–3 GB VRAM). Doorman InsightFace adds **&lt;1 GB**
typical. **Combined peak ~3–4 GB** — comfortable on 12 GB.

| Workload                  | VRAM (typical) | Notes                       |
| ------------------------- | -------------- | --------------------------- |
| Doorman (InsightFace)     | ~0.5–1 GB      | This project · port **8768** |
| Other homelab GPU service | ~2–3 GB        | Already resident on the box |
| **Doorman + other**       | ~3–4 GB peak   | ✓ fits on 3060              |
| 13B+ LLM (Q4)             | ~8–11 GB+      | Not compatible with both above |

## Network

- Wired LAN path to the inference server
- Reserved DHCP lease for stable SSH/deploy target
- Reolink doorbell RTSP stays on LAN; Doorman pulls frames on demand when the bell rings

## Deploy

| Item       | Value                                                         |
| ---------- | ------------------------------------------------------------- |
| SSH host   | `homelab` (Mac `~/.ssh/config`)                               |
| Remote dir | `~/doorman`                                                   |
| Health     | `docker compose ps worker` (compose healthcheck in container) |

Deploy from Mac: `bun run deploy` (rsync `worker/` + Docker rebuild on the box).

## Docker-only rule

Doorman on this box is **container-only**. Do not install Python, create a host venv, or run
`enroll.py` / `main.py` on the OS. All GPU work goes through `docker compose` or
`docker run --gpus all` with the worker image in `~/doorman`.

Allowed on host: rsync’d tree, `~/doorman/.env`, bind-mounted `db/`, and the Docker CLI only. Do not
run `curl` against localhost for ops — use `docker compose ps` / `docker compose logs` /
`docker compose exec`.

Agents: see [`.cursor/rules/homelab-docker.mdc`](../.cursor/rules/homelab-docker.mdc).

## Resume in Cursor

| Phrase                 | Doc                  |
| ---------------------- | -------------------- |
| **"homelab GPU"**      | This file            |
| **"continue doorman"** | [`spec.md`](spec.md) |
