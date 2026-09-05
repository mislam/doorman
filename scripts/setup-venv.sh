#!/usr/bin/env sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/worker"

PYTHON="${PYTHON:-python3.11}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
	PYTHON=python3
fi

venv_broken() {
	[ ! -x .venv/bin/python ] && return 0
	.venv/bin/python -c "import sys" >/dev/null 2>&1 || return 0
	.venv/bin/python -m pip --version >/dev/null 2>&1 || return 0
	if [ -f .venv/bin/pip ]; then
		.venv/bin/pip --version >/dev/null 2>&1 || return 0
	fi
	return 1
}

if [ -d .venv ] && venv_broken; then
	echo "Repairing broken .venv (stale interpreter — common after moving/renaming the repo)..."
	"$PYTHON" -m venv --clear .venv
else
	"$PYTHON" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

echo "Ready: source worker/.venv/bin/activate"
