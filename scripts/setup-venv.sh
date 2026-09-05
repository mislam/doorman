#!/usr/bin/env sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/worker"

PYTHON="${PYTHON:-python3.11}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
	PYTHON=python3
fi

"$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt

echo "Ready: source worker/.venv/bin/activate"
