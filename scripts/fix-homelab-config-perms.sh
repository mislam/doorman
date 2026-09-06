#!/usr/bin/env sh
# Fix root-owned files in ~/doorface/db via Docker (not host sudo chown).
#
# Usage: ./scripts/fix-homelab-config-perms.sh

set -e

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"

ssh "$HOST" "cd ~/$REMOTE_DIR && \
	IMAGE=\$(docker compose images -q worker 2>/dev/null | head -1) && \
	[ -n \"\$IMAGE\" ] || exit 0 && \
	docker compose run --rm --no-deps --entrypoint '' --user root worker \
		chown -R \$(id -u):\$(id -g) /app/db /app/.insightface /app/.cache 2>/dev/null || \
	docker compose run --rm --no-deps --entrypoint '' --user root worker \
		chown -R \$(id -u):\$(id -g) /app/db"
