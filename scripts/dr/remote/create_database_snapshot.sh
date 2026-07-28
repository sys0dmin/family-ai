#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${1:?usage: create_database_snapshot.sh OUTPUT TRANSFER_USER DATABASE_NAME}"
TRANSFER_USER="${2:?transfer user is required}"
DATABASE_NAME="${3:?database name is required}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BEFORE="${OUTPUT}.before"
MANIFEST="${OUTPUT}.manifest"
SHA_FILE="${OUTPUT}.sha256"

cleanup() {
  local status=$?
  rm -f -- "$BEFORE"
  if [[ "$status" -ne 0 ]]; then
    rm -f -- "$OUTPUT" "$MANIFEST" "$SHA_FILE"
  fi
  exit "$status"
}
trap cleanup EXIT

[[ "$(id -u)" -eq 0 ]] || {
  echo "create_database_snapshot.sh must run as root" >&2
  exit 1
}
systemctl is-active --quiet postgresql
sudo -u postgres psql -At -d postgres \
  -c "SELECT 1 FROM pg_database WHERE datname='${DATABASE_NAME}'" | grep -qx 1

"$SCRIPT_DIR/database_manifest.sh" "$DATABASE_NAME" >"$BEFORE"
sudo -u postgres pg_dump \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-acl \
  --serializable-deferrable \
  --file="$OUTPUT" \
  "$DATABASE_NAME"
"$SCRIPT_DIR/database_manifest.sh" "$DATABASE_NAME" >"$MANIFEST"

if ! cmp -s "$BEFORE" "$MANIFEST"; then
  echo "source database changed during snapshot; stop all writers and retry" >&2
  exit 1
fi
rm -f -- "$BEFORE"
sha256sum "$OUTPUT" | awk '{print $1}' >"$SHA_FILE"
chown "$TRANSFER_USER:$TRANSFER_USER" "$OUTPUT" "$MANIFEST" "$SHA_FILE"
chmod 0600 "$OUTPUT" "$MANIFEST" "$SHA_FILE"
trap - EXIT
echo "created consistent database snapshot"
