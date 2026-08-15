#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/var/lib/family-ai-config/gateway"
REQUEST_PATH="$RUNTIME_DIR/restart.request"
ACK_PATH="$RUNTIME_DIR/restart.ack"

[[ "$EUID" -eq 0 ]] || { echo "must run as root" >&2; exit 1; }
[[ -f "$REQUEST_PATH" ]] || { echo "restart request is missing" >&2; exit 1; }

nonce="$(tr -d '\r\n' <"$REQUEST_PATH")"
[[ "$nonce" =~ ^[a-f0-9]{32}$ ]] || { echo "invalid restart request" >&2; exit 1; }

/usr/bin/systemctl restart family-ai-gateway.service

temporary="$RUNTIME_DIR/.restart.ack.tmp"
printf '%s\n' "$nonce" >"$temporary"
runtime_group="$(stat -c '%G' "$RUNTIME_DIR")"
chown root:"$runtime_group" "$temporary"
chmod 0640 "$temporary"
mv -f "$temporary" "$ACK_PATH"
