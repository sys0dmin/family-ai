#!/usr/bin/env bash
set -euo pipefail

DUMP="${1:?usage: restore_database_snapshot.sh DUMP EXPECTED_SHA DATABASE_NAME ROLE_NAME}"
EXPECTED_SHA="${2:?expected SHA-256 is required}"
DATABASE_NAME="${3:?database name is required}"
ROLE_NAME="${4:?database role is required}"

[[ "$(id -u)" -eq 0 ]] || {
  echo "restore_database_snapshot.sh must run as root" >&2
  exit 1
}
[[ -s "$DUMP" ]] || {
  echo "database dump is missing or empty" >&2
  exit 1
}
[[ "$(sha256sum "$DUMP" | awk '{print $1}')" == "$EXPECTED_SHA" ]] || {
  echo "database dump checksum mismatch" >&2
  exit 1
}
pg_restore --list "$DUMP" >/dev/null
RESTORE_INPUT="$(mktemp /var/lib/postgresql/.family-ai-restore.XXXXXX)"
trap 'rm -f -- "$RESTORE_INPUT"' EXIT
install -o postgres -g postgres -m 0600 "$DUMP" "$RESTORE_INPUT"

TABLE_COUNT="$(sudo -u postgres psql -At -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
  -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
[[ "$TABLE_COUNT" == "0" ]] || {
  echo "target database is not empty; refusing destructive restore" >&2
  exit 1
}

sudo -u postgres pg_restore \
  --exit-on-error \
  --single-transaction \
  --no-owner \
  --no-acl \
  --role="$ROLE_NAME" \
  --dbname="$DATABASE_NAME" \
  "$RESTORE_INPUT"
rm -f -- "$RESTORE_INPUT"
trap - EXIT
echo "restored database snapshot"
