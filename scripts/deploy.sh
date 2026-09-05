#!/usr/bin/env sh
set -e

# Ship worker/ to homelab and rebuild Docker.
# Secrets on server only: ~/doorface/.env (see worker/.env.example)
#
# Usage: bun run deploy
# DEPLOY_HOST=homelab DEPLOY_DIR=doorface bun run deploy
# DEPLOY_SKIP_BUILD=1 bun run deploy

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."
rsync -az --delete \
	--exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
	--exclude .env --exclude .DS_Store \
	--exclude config/gallery.pkl \
	worker/ "$HOST:~/$REMOTE_DIR/"

if [ "${DEPLOY_SKIP_BUILD:-}" = "1" ]; then
	echo "Synced (DEPLOY_SKIP_BUILD=1)"
	exit 0
fi

if ! ssh "$HOST" "test -f ~/$REMOTE_DIR/.env"; then
	echo "Missing ~/$REMOTE_DIR/.env on $HOST (deploy never rsyncs secrets)." >&2
	echo "One-time on homelab:" >&2
	echo "  ssh $HOST 'cd ~/$REMOTE_DIR && cp .env.example .env && nano .env'" >&2
	echo "Set STREAM_URL at minimum, then re-run: bun run deploy" >&2
	exit 1
fi

echo "Rebuilding on $HOST..."
echo "  (first build or Dockerfile change: often 10–15 min — pulling CUDA base + pip vision stack)"
if [ "${DEPLOY_QUIET:-}" = "1" ]; then
	COMPOSE_FLAGS="--quiet"
else
	COMPOSE_FLAGS="--progress plain"
fi

REMOTE="cd ~/$REMOTE_DIR"
if [ "${DEPLOY_NO_CACHE:-}" = "1" ]; then
	ssh -t "$HOST" "$REMOTE && docker compose $COMPOSE_FLAGS build --no-cache worker && docker compose up -d --force-recreate worker"
else
	ssh -t "$HOST" "$REMOTE && docker compose $COMPOSE_FLAGS build worker && docker compose up -d --force-recreate worker"
fi

# Drop untagged images left by rebuilds (safe — does not remove other projects' images).
ssh "$HOST" "docker image prune -f >/dev/null 2>&1 || true"

if ssh "$HOST" "curl -sf http://127.0.0.1:8768/health >/dev/null 2>&1"; then
	echo "Deployed (healthy)"
else
	echo "Deployed — worker still starting or unhealthy (model load can take 1–3 min)"
	echo "  ssh $HOST 'cd ~/$REMOTE_DIR && docker compose logs worker --tail 30'"
fi
