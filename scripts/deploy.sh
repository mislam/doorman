#!/usr/bin/env sh
set -e

# Ship worker/ to homelab and rebuild Docker.
# Secrets on server only: ~/doorface/.env (see worker/.env.example)
#
# Usage: bun run deploy
# DEPLOY_HOST=homelab DEPLOY_DIR=doorface bun run deploy
# DEPLOY_SKIP_BUILD=1 bun run deploy
# DEPLOY_NO_CACHE=1 bun run deploy
# DEPLOY_SKIP_HEALTH=1 bun run deploy   # exit after compose up (no /health wait)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"
HEALTH_WAIT_SECS=900
HEALTH_POLL_SECS=10

echo "Syncing worker/ to $HOST:~/$REMOTE_DIR..."
if [ -d "$ROOT_DIR/enroll-ui" ]; then
	echo "Building enroll UI..."
	(cd "$ROOT_DIR" && bun run build:enroll)
fi

"$SCRIPT_DIR/fix-homelab-config-perms.sh" || true

rsync -az --delete \
	--exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
	--exclude .env --exclude .DS_Store \
	--exclude config/gallery.pkl \
	--exclude config/faces/ \
	--exclude config/enroll_sessions/ \
	worker/ "$HOST:~/$REMOTE_DIR/"

if [ "${DEPLOY_SKIP_BUILD:-}" = "1" ]; then
	echo "Synced (DEPLOY_SKIP_BUILD=1)"
	exit 0
fi

ssh "$HOST" "
	set -e
	cd ~/$REMOTE_DIR
	if [ ! -f .env ]; then
		if [ ! -f .env.example ]; then
			echo 'Missing .env and .env.example on homelab' >&2
			exit 1
		fi
		cp .env.example .env
		uid=\$(id -u)
		gid=\$(id -g)
		if grep -q '^DOCKER_UID=' .env; then
			sed -i \"s/^DOCKER_UID=.*/DOCKER_UID=\$uid/\" .env
		else
			printf '\nDOCKER_UID=%s\n' \"\$uid\" >> .env
		fi
		if grep -q '^DOCKER_GID=' .env; then
			sed -i \"s/^DOCKER_GID=.*/DOCKER_GID=\$gid/\" .env
		else
			printf 'DOCKER_GID=%s\n' \"\$gid\" >> .env
		fi
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
	echo "Deployed to $HOST:~/$REMOTE_DIR (DEPLOY_SKIP_HEALTH=1 — check /health yourself)"
	exit 0
fi

echo "Waiting for /health (InsightFace warmup — often 1–3 min, up to ${HEALTH_WAIT_SECS}s)..."

ssh "$HOST" "
	set -e
	cd ~/$REMOTE_DIR
	start=\$SECONDS
	deadline=\$((SECONDS + $HEALTH_WAIT_SECS))
	while [ \$SECONDS -lt \$deadline ]; do
		if curl -sf http://127.0.0.1:8768/health >/dev/null 2>&1; then
			elapsed=\$((SECONDS - start))
			echo \"  healthy after \${elapsed}s\"
			exit 0
		fi
		if docker compose ps worker 2>/dev/null | grep -q Restarting; then
			echo '  worker is crash-looping — recent logs:'
			docker compose logs worker --tail 40
			exit 1
		fi
		elapsed=\$((SECONDS - start))
		echo \"  still starting (\${elapsed}s)...\"
		sleep $HEALTH_POLL_SECS
	done
	echo 'timed out waiting for /health'
	docker compose logs worker --tail 40
	exit 1
"

echo "Deployed to $HOST:~/$REMOTE_DIR (healthy)"
