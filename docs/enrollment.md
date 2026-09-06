# Face enrollment

Recognition uses enrollment data on homelab at `~/doorman/db/` (`manifest.json`, `photos/`,
`gallery.pkl`). Add and update faces through the **web UI** — deploy does not sync `db/` from Mac.

## Web UI

On your phone or laptop (home Wi‑Fi), open:

```
http://homelab:8768/enroll
```

If `ENROLL_SECRET` is set in homelab `.env`, add `?token=YOUR_SECRET` to the URL once (saved in the
browser session).

### Enroll (live or footage)

1. Open **Enroll** → enter **Name**
2. **Live** — person at the door; tap **Capture** for each step (Front → Left → Right)
3. **Footage** — tap **Capture** per step; pick a doorbell photo or clip (tap a face if several
   appear)
4. Tap **Enroll** when done

Optional: stand at the door and `curl -X POST http://homelab:8768/recognize` to test recognition.

### Family vs guests

- **Live** — family at the door (uses doorbell stream, not the phone camera)
- **Footage** — guests or neighbors from Reolink exports (consent-based)

### Build the UI (Mac)

From the repo root before deploy:

```bash
bun run build:web
```

`bun run deploy` runs this automatically. Output: `worker/static/enroll/`.

---

## CLI fallback (Docker only)

If the UI is unavailable but photos already exist on homelab:

```bash
ssh homelab 'cd ~/doorman && docker compose exec worker python3.11 enroll.py -v'
```

This rebuilds `gallery.pkl` from `db/manifest.json` and `db/photos/` — it does not copy data from
Mac.

---

## Workflows

| Change                      | What to run                                                            |
| --------------------------- | ---------------------------------------------------------------------- |
| Code, Dockerfile, enroll UI | `bun run deploy`                                                       |
| Add / update faces          | Web UI → **Enroll now**                                                |
| Test recognition            | Web **Test recognize** or `curl -X POST http://homelab:8768/recognize` |

Deploy rsyncs code only (`db/` stays on homelab).

## If someone isn't recognized

Add 2–3 more **doorbell** captures in the web UI, then **Enroll now** again.

## Troubleshooting

| Problem               | Fix                                                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Enroll page 401       | Add `?token=` matching `ENROLL_SECRET` in homelab `.env`                                                                         |
| Enroll page missing   | Run `bun run build:web` then `bun run deploy`                                                                                    |
| No faces enrolled     | Face not visible in photo — try clearer shot                                                                                     |
| Doorbell stream blank | Check `STREAM_URL` / `STREAM_USER` / `STREAM_PASSWORD` in homelab `.env`                                                         |
| Permission errors     | If `id -u` ≠ 1000, set `DOCKER_UID`/`DOCKER_GID` in homelab `.env`; run `./scripts/fix-homelab-config-perms.sh`, recreate worker |
| Worker unhealthy      | `ssh homelab 'cd ~/doorman && docker compose logs worker --tail 30'`                                                             |

Env vars: [`worker/README.md`](../worker/README.md).
