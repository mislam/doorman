#!/usr/bin/env sh
set -e

# Homelab status (Docker only — no host curl or app Python).
# Usage: bun status

HOST="${DEPLOY_HOST:-homelab}"
REMOTE_DIR="${DEPLOY_DIR:-doorman}"

echo "=== $HOST:~/$REMOTE_DIR ==="

ssh "$HOST" "
	set -e
	if [ ! -d ~/$REMOTE_DIR ]; then
		echo 'Not deployed yet'
		exit 0
	fi
	cd ~/$REMOTE_DIR
	if ! command -v docker >/dev/null 2>&1 || [ ! -f compose.yaml ]; then
		echo 'Docker compose not found'
		exit 0
	fi
	docker compose ps 2>/dev/null || true
	echo ''
	docker system df 2>/dev/null || true
	if docker compose ps --status running worker 2>/dev/null | grep -q worker; then
		if docker compose exec -T worker nvidia-smi \
			--query-gpu=name,memory.used,memory.total,utilization.gpu \
			--format=csv,noheader 2>/dev/null; then
			:
		else
			echo 'GPU: nvidia-smi unavailable in worker container'
		fi
	fi
"
