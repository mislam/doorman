#!/usr/bin/env sh
# Fix root-owned files in ~/doorface/config via Docker (not host sudo chown).
# Also fixes model cache volume perms when using DOCKER_UID (volumes under /app, not /root).
#
# Usage: ./scripts/fix-homelab-config-perms.sh

set -e

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"

ssh "$HOST" "cd ~/$REMOTE_DIR && \
	IMAGE=\$(docker compose images -q worker 2>/dev/null | head -1) && \
	[ -n \"\$IMAGE\" ] || exit 0 && \
	docker compose run --rm --no-deps --entrypoint '' --user root worker \
		chown -R \$(id -u):\$(id -g) /app/config /app/.insightface /app/.cache 2>/dev/null || \
	docker compose run --rm --no-deps --entrypoint '' --user root worker \
		chown -R \$(id -u):\$(id -g) /app/config"
