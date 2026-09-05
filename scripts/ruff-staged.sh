#!/usr/bin/env sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/worker/.venv/bin/python"

if [ ! -x "$VENV" ]; then
	exit 0
fi

cd "$ROOT"
"$VENV" -m ruff check --fix "$@"
"$VENV" -m ruff format "$@"
