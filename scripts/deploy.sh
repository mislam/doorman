#!/usr/bin/env sh
set -e

# Ship worker/ to homelab and rebuild Docker.
# Secrets on server only: ~/doorface/.env (see worker/.env.example)
#
# Usage: bun deploy
# DEPLOY_HOST=homelab DEPLOY_DIR=doorface bun deploy
# DEPLOY_SKIP_BUILD=1 bun deploy

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."
rsync -az --delete \
	--exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
	--exclude .env --exclude .DS_Store \
	worker/ "$HOST:~/$REMOTE_DIR/"

if [ "${DEPLOY_SKIP_BUILD:-}" = "1" ]; then
	echo "Synced (DEPLOY_SKIP_BUILD=1)"
	exit 0
fi

echo "Rebuilding on $HOST..."
REMOTE="cd ~/$REMOTE_DIR"
if [ "${DEPLOY_NO_CACHE:-}" = "1" ]; then
	ssh "$HOST" "$REMOTE && docker compose build --no-cache --quiet worker && docker compose up -d --force-recreate worker"
else
	ssh "$HOST" "$REMOTE && docker compose build --quiet worker && docker compose up -d --force-recreate worker"
fi

if ssh "$HOST" "curl -sf http://127.0.0.1:8768/health >/dev/null 2>&1"; then
	echo "Deployed (healthy)"
else
	echo "Deployed (no /health yet — expected until Phase 3)"
fi
