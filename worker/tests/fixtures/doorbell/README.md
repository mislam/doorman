# Doorbell recognition fixtures

Integration tests read `manifest.json` (committed, public fixtures only). Optional
`manifest.private.json` (gitignored) adds real-household enroll + scenarios — copy from
`manifest.private.json.example`.

Images stay **out of git** (see `.gitignore`).

## Layout

```text
public/enroll/          enroll photos for shareable fixtures
public/frames/          doorbell test frames (e.g. YouTube screenshots)
private/enroll/         real enroll photos (gitignored)
private/frames/         real doorbell frames (gitignored)
manifest.json           public scenarios only
manifest.private.json   your private enroll/scenarios (never commit)
```

`public/` and `private/` use the same shape: `enroll/` + `frames/`. Paths in the manifest include
the prefix (`public/frames/…` or `private/enroll/…`).

## Private fixtures

```bash
cp manifest.private.json.example manifest.private.json
# edit names/paths; add JPEGs under private/enroll and private/frames
```

`manifest.private.json` and `private/**` rsync to homelab with `bun run test:integration` but are
never committed.

## Enroll photos

Use images InsightFace can detect — **frontal or three-quarter face**, not tight crops under a cap
brim. Indoor close-ups may fail detection entirely.

Prefer **doorbell-domain** enroll shots (same person, similar distance/lighting as the ring frames).
The manifest may list frame paths under `enroll` when they embed reliably.

Tune `min_match_score` per scenario after `bun run test:integration` (night-vision IR scores are
much lower than daylight).

After adding PNG screenshots:

```bash
bun run convert:fixtures
```

JPEG quality **92**; long edge capped at **1280** (enroll) / **1920** (frames). Source PNGs are
removed after conversion.

## Run tests

```bash
bun run test:integration        # homelab Docker + InsightFace
```

Tune thresholds in `manifest.json` (public) or `manifest.private.json` (private) after the first
homelab run. If a frame shows `det=0.00`, InsightFace cannot see a face — replace the image or drop
that scenario until you have a usable shot.

## Preprocessing checks

`preprocessing` in the manifest compares **raw vs CLAHE** through the full `recognize_frames`
pipeline at each case's `match_threshold`:

- CLAHE must identify `expected_names`
- Match score must not regress beyond `match_tolerance` (default **0.03**)
- If raw misses identification, CLAHE must recover
- Optional `min_det_gain` / `min_match_gain` when a frame shows a real CLAHE lift

Regression-only run: `INTEGRATION_MARKER=integration bun run test:integration`. Preprocessing-only:
`INTEGRATION_MARKER=preprocessing bun run test:integration`.
