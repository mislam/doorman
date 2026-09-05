# Face enrollment

Recognition compares doorbell frames to photos on disk at `~/doorface/config/faces/{name}/` on
homelab. Add and update faces through the **web UI** — deploy does not sync photos from Mac. The
repo keeps `worker/config/faces/.gitkeep` only; real data lives on the server.

## Web UI

On your phone or laptop (home Wi‑Fi), open:

```
http://homelab:8768/enroll
```

If `ENROLL_SECRET` is set in homelab `.env`, add `?token=YOUR_SECRET` to the URL once (saved in the
browser session).

### Family (live capture)

1. **Live capture** tab → enter name (`alice`)
2. Person stands at the door — watch the live stream on your phone
3. Follow the steps (front, left, right) and tap **Capture from stream** for each
4. Tap **Enroll now** to rebuild `gallery.pkl`
5. Optional: **Test recognize** — stand at the door and confirm your name appears

Uses your doorbell camera (`STREAM_URL`) — not the phone camera.

### Guests / neighbors (from footage)

Consent-based live capture is for family only. For others, use doorbell recordings:

1. **Reolink app** → find the clip → export/share video or stills
2. **From footage** tab → upload the file
3. Tap faces to select 2–3 clear crops → enter name → **Save selected**
4. **Enroll now**

When they stop visiting, delete them in the **Enrolled people** list.

### Build the UI (Mac)

From the repo root before deploy:

```bash
bun run build:enroll
```

`bun run deploy` runs this automatically. Output: `worker/static/enroll/`.

---

## CLI fallback (Docker only)

If the UI is unavailable but photos already exist on homelab:

```bash
ssh homelab 'cd ~/doorface && docker compose exec worker python3.11 enroll.py -v'
```

This rebuilds `gallery.pkl` from `config/faces/` — it does not copy photos from Mac.

---

## Workflows

| Change                      | What to run                                                            |
| --------------------------- | ---------------------------------------------------------------------- |
| Code, Dockerfile, enroll UI | `bun run deploy`                                                       |
| Add / update faces          | Web UI → **Enroll now**                                                |
| Test recognition            | Web **Test recognize** or `curl -X POST http://homelab:8768/recognize` |

Deploy rsyncs code only (`config/faces/` and `gallery.pkl` stay on homelab).

## If someone isn't recognized

Add 2–3 more **doorbell** captures in the web UI, then **Enroll now** again.

## Troubleshooting

| Problem               | Fix                                                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| Enroll page 401       | Add `?token=` matching `ENROLL_SECRET` in homelab `.env`                                                      |
| Enroll page missing   | Run `bun run build:enroll` then `bun run deploy`                                                              |
| No faces enrolled     | Face not visible in photo — try clearer shot                                                                  |
| Doorbell stream blank | Check `STREAM_URL` / `STREAM_USER` / `STREAM_PASSWORD` in homelab `.env`                                      |
| Permission errors     | Set `DOCKER_UID`/`DOCKER_GID` in homelab `.env`, run `./scripts/fix-homelab-config-perms.sh`, recreate worker |
| Worker unhealthy      | `ssh homelab 'cd ~/doorface && docker compose logs worker --tail 30'`                                         |

Env vars: [`worker/README.md`](../worker/README.md).
