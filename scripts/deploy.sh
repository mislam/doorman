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
HEALTH_POLL_SECS=10

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."

"$SCRIPT_DIR/fix-homelab-config-perms.sh" || true

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
	--exclude db/ \
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
		echo '  → edit STREAM_URL, STREAM_USER/PASSWORD, HA_WEBHOOK_URL on homelab before prod use'
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
if [ "${DEPLOY_NO_CACHE:-}" = "1" ]; then
	ssh -t "$HOST" "$REMOTE && docker compose $COMPOSE_FLAGS build --no-cache worker && docker compose up -d --force-recreate worker"
else
	ssh -t "$HOST" "$REMOTE && docker compose $COMPOSE_FLAGS build worker && docker compose up -d --force-recreate worker"
fi

# Drop untagged images left by rebuilds (safe — does not remove other projects' images).
ssh "$HOST" "docker image prune -f >/dev/null 2>&1 || true"

if [ "${DEPLOY_SKIP_HEALTH:-}" = "1" ]; then
	echo "Synced to $HOST (~/$REMOTE_DIR). Skipped health check (DEPLOY_SKIP_HEALTH=1)."
	exit 0
fi

echo "Starting worker on $HOST — loading face models (usually 1–3 min, first start can take longer)..."

ssh "$HOST" "
	set -e
	cd ~/$REMOTE_DIR
	start=\$SECONDS
	deadline=\$((SECONDS + $HEALTH_WAIT_SECS))
	while [ \$SECONDS -lt \$deadline ]; do
		if curl -sf http://127.0.0.1:8768/health >/dev/null 2>&1; then
			elapsed=\$((SECONDS - start))
			echo \"  Worker is up (took \${elapsed}s)\"
			exit 0
		fi
		if docker compose ps worker 2>/dev/null | grep -q Restarting; then
			echo '  Worker keeps crashing. Recent logs:'
			docker compose logs worker --tail 40
			exit 1
		fi
		elapsed=\$((SECONDS - start))
		echo \"  Still loading… (\${elapsed}s)\"
		sleep $HEALTH_POLL_SECS
	done
	echo 'Timed out — worker never became healthy. Recent logs:'
	docker compose logs worker --tail 40
	exit 1
"

echo "Done! Doorman is running on $HOST (~/$REMOTE_DIR)."
