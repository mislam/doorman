# Face enrollment

Recognition uses enrollment data on homelab at `~/doorman/db/` (`manifest.json`, `photos/`,
`gallery.pkl`). Add and update faces through the **web UI** — deploy does not sync `db/` from Mac.

## Web UI

On your phone or laptop (home Wi‑Fi), open:

```
https://192.168.x.x:8768/enroll
```

Replace `192.168.x.x` with your homelab LAN IP (phones and browsers usually cannot resolve the SSH
hostname). **HTTPS on port 8768** is served by a **Caddy container** in `compose.yaml` — it proxies
to the worker on the Docker network. One port for enroll, `/recognize`, and `/health`.

Use **`https://`** (not `http://`). Plain HTTP on 8768 is not exposed on the host.

If `ENROLL_SECRET` is set in homelab `.env`, add `?token=YOUR_SECRET` to the URL once (saved in the
browser session).

### Trust the HTTPS certificate (one-time per phone)

Enroll uses a **homelab-only** root CA (not Let's Encrypt). On your phone it shows as **Doorman**.
Installing the profile alone is **not** enough — you must also enable full trust (step 3).

1. **Export** the root cert on your Mac:

   ```bash
   ssh homelab 'cat ~/doorman/certs/root.crt' > doorman-ca.crt
   ```

2. **Install** the profile on your iPhone — AirDrop or email `doorman-ca.crt`, open it, and follow
   the install prompts (Settings may show a “Profile Downloaded” notice).

3. **Enable full trust** — **Settings → General → About → Certificate Trust Settings** → turn
   **Doorman** **ON** and confirm. Without this step, Safari shows “This Connection Is Not Private”.

After all three steps, `https://…:8768/enroll` opens without warnings and **Phone** guided capture
works.

Certs are generated on first deploy (`scripts/generate-enroll-tls.sh`) using `ENROLL_LAN_IP` from
homelab `.env`. Regenerate after an IP change: delete `~/doorman/certs/` and redeploy.

### Enroll

1. Open `https://192.168.x.x:8768/enroll` on your phone or laptop
2. Tap the **camera icon** (top right) and choose **Doorbell**, **Phone**, or **Upload**
3. Follow the pose prompts for live capture, or pick photos/clips from your library
4. Enter **Name**, tap **Done** — if that name is already enrolled, confirm to **replace** their
   photos

Use **doorbell-domain** photos when possible (same camera and lighting as real rings). **Upload**
works on HTTPS too. **Phone** live camera needs the trusted CA (see above).

**Guided capture** runs in two phases:

1. **Get ready** — face the camera straight on. The worker checks **one face**, **distance** (move
   closer on phone), **lighting**, **sharpness**, and a **plain background**. Pose arrows do not
   appear until this passes for a moment. Nothing is saved in this phase.
2. **Pose steps** — left, right, up, down, then straight on. The same environment checks still run
   on every poll; pose hints appear only when setup is OK.

Move to better light or a simpler backdrop if prompted.

The page remembers your last camera choice in the browser.

Optional: `curl -k -X POST https://192.168.x.x:8768/recognize` to test recognition (`-k` skips CA
verify from your laptop; use `--cacert doorman-ca.crt` if you exported the root).

### Family vs guests

- **Guided capture** — doorbell or phone camera with pose checks
- **Upload** — photos or clips from Reolink exports (no pose checks)

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
ssh homelab 'cd ~/doorman && docker compose exec worker python enroll.py -v'
```

This rebuilds `gallery.pkl` from `db/manifest.json` and `db/photos/` — it does not copy data from
Mac.

---

## Workflows

| Change                      | What to run                                          |
| --------------------------- | ---------------------------------------------------- |
| Code, Dockerfile, enroll UI | `bun run deploy`                                     |
| Add / update faces          | Web UI → **Enroll now**                              |
| Test recognition            | `curl -k -X POST https://192.168.x.x:8768/recognize` |

Deploy rsyncs code only (`db/` stays on homelab).

## If someone isn't recognized

Add 2–3 more **doorbell** captures in the web UI, then **Enroll now** again.

## Troubleshooting

| Problem               | Fix                                                                                      |
| --------------------- | ---------------------------------------------------------------------------------------- |
| Enroll page 401       | Add `?token=` matching `ENROLL_SECRET` in homelab `.env`                                 |
| Enroll page missing   | Run `bun run build:web` then `bun run deploy`                                            |
| No faces enrolled     | Face not visible in photo — try clearer shot                                             |
| Doorbell stream blank | Check `STREAM_URL` / `STREAM_USER` / `STREAM_PASSWORD` in homelab `.env`                 |
| Permission errors     | Rebuild and recreate: `bun run deploy`                                                   |
| Page won't load       | Use `https://` on **8768**; run `docker compose ps` — both `worker` and `enroll` healthy |
| Phone camera disabled | Trust the **Doorman** CA (see above); must use `https://`                                |
| HTTPS cert warning    | Complete all 3 trust steps — especially **Certificate Trust Settings → Doorman ON**      |
| Worker unhealthy      | `ssh homelab 'cd ~/doorman && docker compose logs worker --tail 30'`                     |
| Enroll proxy down     | `ssh homelab 'cd ~/doorman && docker compose logs enroll --tail 20'`                     |

Env vars: [`worker/README.md`](../worker/README.md).
