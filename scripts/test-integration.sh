#!/usr/bin/env sh
# Run doorbell fixture integration tests on homelab (InsightFace GPU, isolated container).
#
# Usage: bun run test:integration
# DEPLOY_HOST=homelab DEPLOY_DIR=doorman bun run test:integration
#
# Rebuilds the worker image only when Dockerfile/requirements change or pytest
# is missing. Rsync'd *.py and tests/ are bind-mounted so code/fixture edits
# do not require a rebuild.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorman}"

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."
rsync -az --delete \
	--exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
	--exclude .env --exclude .DS_Store \
	--exclude db/ \
	--exclude .integration-image-stamp \
	"$ROOT/worker/" "$HOST:~/$REMOTE_DIR/"

echo "Homelab: $HOST (~/$REMOTE_DIR)"
ssh "$HOST" "REMOTE_DIR=$REMOTE_DIR" bash -s <<'REMOTE'
set -e
set -o pipefail
cd ~/"$REMOTE_DIR"

compute_image_stamp() {
	sha256sum Dockerfile requirements.txt requirements-vision.txt pyproject.toml 2>/dev/null \
		| sha256sum | awk '{print $1}'
}

worker_image_id() {
	docker compose images -q worker 2>/dev/null | head -1
}

build_reason() {
	image_id="$(worker_image_id)"
	if [ -z "$image_id" ]; then
		echo "no worker image yet"
		return 0
	fi

	stamp="$(compute_image_stamp)"
	stored="$(cat .integration-image-stamp 2>/dev/null || true)"
	if [ "$stamp" != "$stored" ]; then
		echo "Dockerfile or requirements changed"
		return 0
	fi

	if ! docker run --rm --entrypoint python "$image_id" -c "import pytest" >/dev/null 2>&1; then
		echo "worker image missing pytest"
		return 0
	fi

	return 1
}

reason="$(build_reason || true)"
if [ -n "$reason" ]; then
	echo ""
	echo "Building worker image ($reason)..."
	echo "  Layers: CUDA base, pip vision stack, pytest. Usually 1–3 min; first build often 10+ min."
	echo ""
	docker compose build --progress plain worker
	compute_image_stamp > .integration-image-stamp
	echo ""
	echo "Worker image ready."
else
	echo "Worker image up to date — skipping build."
fi

py_mounts=""
for py in *.py; do
	[ -f "$py" ] || continue
	py_mounts="$py_mounts -v $(pwd)/$py:/app/$py:ro"
done

# Optional: INTEGRATION_MARKER=integration|preprocessing to run one suite only.
case "${INTEGRATION_MARKER:-all}" in
integration)
	TEST_FILES="tests/test_recognition_fixtures.py"
	TEST_LABEL="integration regression"
	;;
preprocessing)
	TEST_FILES="tests/test_preprocessing_fixtures.py"
	TEST_LABEL="preprocessing A/B"
	;;
*)
	TEST_FILES="tests/test_preprocessing_fixtures.py tests/test_recognition_fixtures.py"
	TEST_LABEL="integration + preprocessing"
	;;
esac

echo ""
echo "Running fixture tests ($TEST_LABEL)..."
echo ""

export COMPOSE_ANSI=never

# Only doorbell fixture modules — avoids collecting Mac-only tests (httpx2, etc.).
# shellcheck disable=SC2086
docker compose run --rm --no-deps \
	-v "$(pwd)/tests:/app/tests:ro" \
	$py_mounts \
	worker python -m pytest $TEST_FILES -s -q -o addopts= --tb=line --no-header 2>&1 \
	| grep -v '^ Container '
REMOTE

echo ""
echo "Integration tests finished."
