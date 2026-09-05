#!/usr/bin/env sh
# Ruff wrapper — no-op when worker/.venv is missing.

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/worker/.venv/bin/python"
MODE="${1:-check}"

if [ ! -x "$VENV" ]; then
	echo "skip ruff (no worker/.venv)"
	exit 0
fi

cd "$ROOT/worker"

case "$MODE" in
	check)
		"$VENV" -m ruff check .
		"$VENV" -m ruff format --check .
		;;
	fix)
		"$VENV" -m ruff check --fix .
		"$VENV" -m ruff format .
		;;
	test)
		"$VENV" -m pytest -q
		;;
	*)
		echo "usage: ruff.sh check|fix|test" >&2
		exit 1
		;;
esac
