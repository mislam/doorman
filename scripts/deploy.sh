#!/usr/bin/env sh
set -e

# Ship worker/ to homelab and rebuild Docker.
# Secrets on server only: ~/doorman/.env (see worker/.env.example)
#
# Usage: bun run deploy
# DEPLOY_HOST=homelab DEPLOY_DIR=doorman bun run deploy
# DEPLOY_SKIP_BUILD=1 bun run deploy
# DEPLOY_NO_CACHE=1 bun run deploy
# DEPLOY_SKIP_HEALTH=1 bun run deploy   # exit after compose up (no /health wait)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorman}"
HEALTH_WAIT_SECS=900

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."

if [ -d "$ROOT_DIR/web" ]; then
	ENROLL_OUT="$ROOT_DIR/worker/static/enroll/index.html"
	ENROLL_STAMP="$ROOT_DIR/worker/static/enroll/.build-stamp"
	need_build=0
	if [ ! -f "$ENROLL_OUT" ] || [ ! -f "$ENROLL_STAMP" ]; then
		need_build=1
	else
		for path in \
			"$ROOT_DIR/web/package.json" \
			"$ROOT_DIR/web/bun.lock" \
			"$ROOT_DIR/web/svelte.config.js" \
			"$ROOT_DIR/web/vite.config.ts" \
			"$ROOT_DIR/web/tsconfig.json"; do
			if [ -f "$path" ] && [ "$path" -nt "$ENROLL_STAMP" ]; then
				need_build=1
				break
			fi
		done
		if [ "$need_build" = "0" ] && find "$ROOT_DIR/web/src" -type f -newer "$ENROLL_STAMP" -print -quit 2>/dev/null | grep -q .; then
			need_build=1
		fi
	fi
	if [ "$need_build" = "1" ]; then
		echo "Building web UI..."
		(cd "$ROOT_DIR" && bun run build:web)
		mkdir -p "$(dirname "$ENROLL_STAMP")"
		touch "$ENROLL_STAMP"
	else
		echo "Web UI unchanged — skipping build"
	fi
fi

rsync -az --delete \
	--exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
	--exclude .env --exclude .DS_Store \
	--exclude db/ --exclude certs/ \
	worker/ "$HOST:~/$REMOTE_DIR/"

if [ "${DEPLOY_SKIP_BUILD:-}" = "1" ]; then
	echo "Synced (DEPLOY_SKIP_BUILD=1)"
	exit 0
fi

ssh "$HOST" "
	set -e
	cd ~/$REMOTE_DIR
	mkdir -p db/photos
	if [ ! -f .env ]; then
		if [ ! -f .env.example ]; then
			echo 'Missing .env and .env.example on homelab' >&2
			exit 1
		fi
		cp .env.example .env
		echo 'Created ~/$REMOTE_DIR/.env from .env.example'
		echo '  → edit STREAM_URL, STREAM_USER/PASSWORD, HA_WEBHOOK_URL, ENROLL_LAN_IP on homelab before prod use'
	fi
	if ! [ -f certs/enroll.crt ]; then
		echo 'Generating enroll TLS certs (first deploy)...'
		chmod +x scripts/generate-enroll-tls.sh
		./scripts/generate-enroll-tls.sh
	fi
"

echo "Rebuilding on $HOST..."
echo "  (first build or Dockerfile change: often 10–15 min — pulling CUDA base + pip vision stack)"
if [ "${DEPLOY_QUIET:-}" = "1" ]; then
	COMPOSE_FLAGS="--quiet"
else
	COMPOSE_FLAGS="--progress plain"
fi

REMOTE="cd ~/$REMOTE_DIR"
if [ "${DEPLOY_SKIP_HEALTH:-}" = "1" ]; then
	WAIT_FLAGS=""
else
	WAIT_FLAGS="--wait --wait-timeout $HEALTH_WAIT_SECS"
	echo "Waiting for worker health (model load — usually 1–3 min, first start can take longer)..."
fi

if [ "${DEPLOY_NO_CACHE:-}" = "1" ]; then
	BUILD_CMD="docker compose $COMPOSE_FLAGS build --no-cache worker"
else
	BUILD_CMD="docker compose $COMPOSE_FLAGS build worker"
fi
UP_CMD="docker compose up -d --force-recreate $WAIT_FLAGS"

if ! ssh -t "$HOST" "$REMOTE && $BUILD_CMD && $UP_CMD"; then
	echo "Deploy failed on $HOST. Recent logs:"
	ssh "$HOST" "cd ~/$REMOTE_DIR && docker compose logs worker --tail 40" || true
	exit 1
fi

# Drop untagged images left by rebuilds (safe — does not remove other projects' images).
ssh "$HOST" "docker image prune -f >/dev/null 2>&1 || true"

if [ "${DEPLOY_SKIP_HEALTH:-}" = "1" ]; then
	echo "Synced to $HOST (~/$REMOTE_DIR). Skipped health wait (DEPLOY_SKIP_HEALTH=1)."
else
	echo "Done — Doorman is healthy on $HOST (~/$REMOTE_DIR)."
fi
