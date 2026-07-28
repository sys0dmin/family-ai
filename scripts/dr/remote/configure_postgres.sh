#!/usr/bin/env bash
set -euo pipefail

DATABASE_IP="${1:?usage: configure_postgres.sh DATABASE_IP GATEWAY_IP PASSWORD_FILE ROLE_NAME DATABASE_NAME}"
GATEWAY_IP="${2:?gateway IP is required}"
PASSWORD_FILE="${3:?password file is required}"
ROLE_NAME="${4:?database role is required}"
DATABASE_NAME="${5:?database name is required}"

[[ "$(id -u)" -eq 0 ]] || {
  echo "configure_postgres.sh must run as root" >&2
  exit 1
}
[[ -s "$PASSWORD_FILE" ]] || {
  echo "database password file is missing or empty" >&2
  exit 1
}
[[ "$ROLE_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || {
  echo "invalid database role" >&2
  exit 1
}
[[ "$DATABASE_NAME" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || {
  echo "invalid database name" >&2
  exit 1
}
trap 'rm -f -- "$PASSWORD_FILE"' EXIT

PG_VERSION="$(pg_config --version | awk '{print $2}' | cut -d. -f1)"
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"
[[ -f "$PG_CONF" && -f "$PG_HBA" ]] || {
  echo "PostgreSQL configuration was not found" >&2
  exit 1
}

APP_PASSWORD="$(cat "$PASSWORD_FILE")"
export APP_PASSWORD
PASSWORD_SQL="$(python3 - <<'PY'
import os
print(os.environ["APP_PASSWORD"].replace("'", "''"))
PY
)"
unset APP_PASSWORD

sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${ROLE_NAME}') THEN
    CREATE ROLE ${ROLE_NAME} LOGIN PASSWORD '${PASSWORD_SQL}';
  ELSE
    ALTER ROLE ${ROLE_NAME} LOGIN PASSWORD '${PASSWORD_SQL}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -At -d postgres \
  -c "SELECT 1 FROM pg_database WHERE datname='${DATABASE_NAME}'" | grep -qx 1; then
  sudo -u postgres createdb -O "$ROLE_NAME" -E UTF8 "$DATABASE_NAME"
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres <<SQL
REVOKE ALL ON DATABASE ${DATABASE_NAME} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${DATABASE_NAME} TO ${ROLE_NAME};
SQL

sed -i "/^# Family AI DR managed$/,/^# End Family AI DR managed$/d" "$PG_CONF"
cat >>"$PG_CONF" <<EOF

# Family AI DR managed
listen_addresses = '${DATABASE_IP}'
# End Family AI DR managed
EOF

sed -i "/^# Family AI DR managed$/,/^# End Family AI DR managed$/d" "$PG_HBA"
cat >>"$PG_HBA" <<EOF

# Family AI DR managed
host    ${DATABASE_NAME}    ${ROLE_NAME}    ${GATEWAY_IP}/32    scram-sha-256
# End Family AI DR managed
EOF

systemctl restart postgresql
sudo -u postgres psql -At -d postgres -c "SELECT version()" >/dev/null
echo "configured PostgreSQL database=$DATABASE_NAME role=$ROLE_NAME"
