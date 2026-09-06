#!/usr/bin/env sh
# Convert fixture PNGs to JPEG (quality 92, doorbell-ish max dimensions).
#
# Usage: bun run convert:fixtures

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/worker/.venv/bin/python"

if [ ! -x "$VENV" ]; then
	echo "Run bun setup first (needs worker/.venv + OpenCV)." >&2
	exit 1
fi

"$VENV" "$ROOT/scripts/convert-fixture-images.py"
