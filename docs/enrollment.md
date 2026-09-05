# Face enrollment

Recognition compares doorbell frames to photos on disk. **Add folders on Mac → `bun enroll` →
done.**

Paths: `worker/config/faces/{name}/` on Mac · same tree on homelab after sync.

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

## Enroll

From your Mac (after adding or changing photos):

```bash
bun enroll              # sync faces → homelab, build gallery.pkl there
bun enroll -- -v        # verbose per-photo log
```

`bun enroll` rsyncs `worker/config/faces/` to homelab and runs `enroll.py` in the Docker worker
(GPU). Run `bun run deploy` once first so the image exists.

`bun run deploy` also copies `config/faces/` (with the rest of `worker/`), but does **not** touch
`gallery.pkl` on homelab — always run `bun enroll` after photo changes.

You should see: `Wrote N embedding(s) for M person(s) → config/gallery.pkl`

## Adding a guest

Same flow as family — no separate system.

1. **While they're visiting** — iPhone photo (or doorbell snapshot if they're at the door).
2. **On Mac** — `mkdir worker/config/faces/jane` and drop in 1–3 photos. First name or nickname is
   fine (`jane`, not `guest_jane`).
3. **`bun enroll`** — sync + rebuild gallery.
4. **Next ring** — they should show up by name.

When they stop visiting, delete `worker/config/faces/jane/` on Mac, run `bun enroll` again.

## If someone isn't recognized

Add 2–3 more **doorbell** photos of that person at the door, then `bun enroll` again.

## Troubleshooting

| Problem                | Fix                                                        |
| ---------------------- | ---------------------------------------------------------- |
| No faces enrolled      | Face not visible in photo — try clearer iPhone shot        |
| `insightface` import   | Run `bun run deploy` to rebuild the Docker image           |
| `python3.11` / Docker  | Run `bun run deploy` first; enroll uses Docker on homelab  |
| `unknown flag: --gpus` | Pull latest scripts — enroll uses `docker run --gpus` now  |
| SSH / rsync fails      | Check `DEPLOY_HOST` (default `homelab`) in `~/.ssh/config` |

Env vars (`FACES_DIR`, `GALLERY_PATH`): [`worker/README.md`](../worker/README.md).
