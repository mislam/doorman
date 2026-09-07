#!/usr/bin/env sh
# Generate homelab-only TLS for the enroll Caddy proxy (LAN IP in SAN).
# Run on homelab: ~/doorman/scripts/generate-enroll-tls.sh
# Uses a one-off Alpine container — no host openssl required.

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LAN_IP="${ENROLL_LAN_IP:-}"
if [ -z "$LAN_IP" ] && [ -f .env ]; then
	LAN_IP="$(grep -E '^ENROLL_LAN_IP=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
if [ -z "$LAN_IP" ]; then
	echo "Set ENROLL_LAN_IP in ~/doorman/.env to your homelab LAN IP (e.g. 192.168.1.100)" >&2
	exit 1
fi

CERT_DIR="${ROOT_DIR}/certs"
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

if [ -f "$CERT_DIR/enroll.crt" ] && [ -f "$CERT_DIR/enroll.key" ] && [ -f "$CERT_DIR/root.crt" ]; then
	echo "TLS certs already exist in certs/ — delete them to regenerate"
	exit 0
fi

docker run --rm -e "LAN_IP=$LAN_IP" -v "$CERT_DIR:/out" alpine:3.20 sh -eu -c '
	apk add --no-cache openssl >/dev/null
	openssl ecparam -genkey -name prime256v1 -out root.key
	openssl req -x509 -new -key root.key -out root.crt -days 3650 -subj "/CN=Doorman"
	openssl ecparam -genkey -name prime256v1 -out enroll.key
	openssl req -new -key enroll.key -out enroll.csr -subj "/CN=Doorman"
	printf "subjectAltName=IP:%s\n" "$LAN_IP" > san.ext
	openssl x509 -req -in enroll.csr -CA root.crt -CAkey root.key -CAcreateserial \
		-out enroll.crt -days 825 -sha256 -extfile san.ext
	chmod 600 enroll.key root.key
	cp enroll.crt enroll.key root.crt /out/
'

echo "Wrote certs/ (install root.crt on phones — see docs/enrollment.md)"
