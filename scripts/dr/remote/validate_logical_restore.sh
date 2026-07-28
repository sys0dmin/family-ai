#!/usr/bin/env bash
set -euo pipefail

SOURCE_DATABASE="${1:?usage: validate_logical_restore.sh SOURCE_DB TEST_DB ROLE WORK_DIR}"
TEST_DATABASE="${2:?test database is required}"
ROLE_NAME="${3:?database role is required}"
WORK_DIR="${4:?work directory is required}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DUMP="${WORK_DIR}/source.dump"
TARGET_MANIFEST="${WORK_DIR}/target.manifest"

[[ "$(id -u)" -eq 0 ]] || {
  echo "validate_logical_restore.sh must run as root" >&2
  exit 1
}
[[ "$SOURCE_DATABASE" != "$TEST_DATABASE" ]] || {
  echo "source and test database must differ" >&2
  exit 1
}
for identifier in "$SOURCE_DATABASE" "$TEST_DATABASE" "$ROLE_NAME"; do
  [[ "$identifier" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || {
    echo "invalid PostgreSQL identifier" >&2
    exit 1
  }
done
[[ -d "$WORK_DIR" ]] || {
  echo "work directory does not exist" >&2
  exit 1
}

cleanup() {
  sudo -u postgres dropdb --if-exists "$TEST_DATABASE" >/dev/null 2>&1 || true
  rm -f -- \
    "$DUMP" \
    "${DUMP}.before" \
    "${DUMP}.manifest" \
    "${DUMP}.sha256" \
    "$TARGET_MANIFEST"
}
trap cleanup EXIT

if sudo -u postgres psql -At -d postgres \
  -c "SELECT 1 FROM pg_database WHERE datname='${TEST_DATABASE}'" | grep -qx 1; then
  echo "test database already exists" >&2
  exit 1
fi

"$SCRIPT_DIR/create_database_snapshot.sh" \
  "$DUMP" \
  root \
  "$SOURCE_DATABASE"
sudo -u postgres createdb -O "$ROLE_NAME" "$TEST_DATABASE"
EXPECTED_SHA="$(cat "${DUMP}.sha256")"
"$SCRIPT_DIR/restore_database_snapshot.sh" \
  "$DUMP" \
  "$EXPECTED_SHA" \
  "$TEST_DATABASE" \
  "$ROLE_NAME"
"$SCRIPT_DIR/database_manifest.sh" "$TEST_DATABASE" >"$TARGET_MANIFEST"
diff -u "${DUMP}.manifest" "$TARGET_MANIFEST"

echo "logical restore validation passed"
