# Face enrollment

Recognition compares doorbell frames to photos on disk. **Add folders → run enroll on homelab.**

Paths: `worker/config/faces/{name}/` on Mac · `~/doorface/config/faces/{name}/` on homelab after
deploy.

## Photos

**Use both doorbell and iPhone** — the doorbell shows real distance and lighting; the phone is easy
for extra angles.

| Source   | When to use it                                      |
| -------- | --------------------------------------------------- |
| Doorbell | 2–3 shots with the person at the door (day is fine) |
| iPhone   | 2–3 clear face shots (front, slight left/right)     |

**~5 photos per person** is enough. Face visible, no sunglasses if you can avoid them. One person
per photo.

Folder name = the name in notifications (`alice`, `bob`, `jane`).

```
config/faces/
  alice/
    door-1.jpg
    phone-1.jpg
  jane/          # guest — same idea
    phone-1.jpg
```

## Enroll (homelab)

Do this on the **homelab** (InsightFace needs the GPU). From your Mac:

```bash
# 1. Put photos in worker/config/faces/{name}/ on Mac

# 2. Copy to homelab
rsync -av worker/config/faces/ homelab:~/doorface/config/faces/

# 3. Build gallery (first time: create venv + vision deps on homelab)
ssh homelab 'cd ~/doorface && \
  test -d .venv || (python3.11 -m venv .venv && .venv/bin/pip install -r requirements-vision.txt) && \
  .venv/bin/python enroll.py -v'
```

You should see: `Wrote N embedding(s) for M person(s) → config/gallery.pkl`

**Whenever you add or change photos, run steps 2–3 again.** The worker reads `gallery.pkl`; it does
not watch the folders.

## Adding a guest

Same flow as family — no separate system.

1. **While they're visiting** — iPhone photo (or doorbell snapshot if they're at the door).
2. **On Mac** — `mkdir worker/config/faces/jane` and drop in 1–3 photos. First name or nickname is
   fine (`jane`, not `guest_jane`).
3. **Rsync + enroll** — same commands as above.
4. **Next ring** — they should show up by name.

When they stop visiting, delete `config/faces/jane/` on homelab, re-run enroll, and they're gone.

## If someone isn't recognized

Add 2–3 more **doorbell** photos of that person at the door, rsync, enroll again.

## Troubleshooting

| Problem              | Fix                                                 |
| -------------------- | --------------------------------------------------- |
| No faces enrolled    | Face not visible in photo — try clearer iPhone shot |
| `insightface` import | Run `pip install -r requirements-vision.txt` once   |

Env vars (`FACES_DIR`, `GALLERY_PATH`): [`worker/README.md`](../worker/README.md).
