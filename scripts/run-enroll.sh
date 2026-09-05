#!/usr/bin/env sh
# Sync faces to homelab and build gallery.pkl (InsightFace needs GPU).
# On homelab with vision deps installed locally, runs enroll.py in-process instead.
#
# Usage: bun enroll [-- -v]

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/worker/.venv/bin/python"
HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"
PROJECT="${COMPOSE_PROJECT_NAME:-doorface}"

if "$VENV" -c "import insightface" 2>/dev/null; then
	cd "$ROOT/worker"
	exec "$VENV" enroll.py "$@"
fi

if [ "$#" -gt 0 ]; then
	REMOTE_ARGS=$(printf '%q ' "$@")
else
	REMOTE_ARGS=""
fi

echo "Syncing config/faces/ → $HOST:~/$REMOTE_DIR/config/faces/ ..."
rsync -az --delete \
	"$ROOT/worker/config/faces/" "$HOST:~/$REMOTE_DIR/config/faces/"

echo "Building gallery on $HOST (Docker) ..."
# docker compose run --gpus is not available on all Compose versions; docker run --gpus is.
ssh "$HOST" "cd ~/$REMOTE_DIR && \
	IMAGE=\$(docker compose images -q worker | head -1) && \
	[ -n \"\$IMAGE\" ] || { echo 'No worker image — run: bun run deploy' >&2; exit 1; } && \
	docker run --rm --gpus all \
		-v \"\$(pwd)/config:/app/config\" \
		-v ${PROJECT}_insightface_models:/root/.insightface \
		\"\$IMAGE\" python3.11 enroll.py ${REMOTE_ARGS}"
