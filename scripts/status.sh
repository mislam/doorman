#!/usr/bin/env sh
set -e

# Homelab status. Usage: bun status

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorface}"

echo "=== $HOST:~/$REMOTE_DIR ==="

ssh "$HOST" "
	set -e
	if [ ! -d ~/$REMOTE_DIR ]; then
		echo 'Not deployed yet'
		exit 0
	fi
	cd ~/$REMOTE_DIR
	if command -v docker >/dev/null 2>&1 && [ -f compose.yaml ]; then
		docker compose ps 2>/dev/null || true
	fi
	if command -v nvidia-smi >/dev/null 2>&1; then
		echo ''
		nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
	fi
	if curl -sf http://127.0.0.1:8768/health >/dev/null 2>&1; then
		echo 'worker: healthy'
	else
		echo 'worker: no /health (not implemented or down)'
	fi
"
