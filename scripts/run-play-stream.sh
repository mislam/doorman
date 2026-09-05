#!/usr/bin/env sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/worker"
exec .venv/bin/python play_stream.py "$@"
