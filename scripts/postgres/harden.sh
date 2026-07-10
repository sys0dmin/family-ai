#!/usr/bin/env bash
# Secure PostgreSQL for Family AI Gateway.
# Run as root on family-ai-db after fix-install.sh.
#
# Usage:
#   GATEWAY_IP=192.168.31.173 DB_LISTEN_IP=192.168.31.XXX ./harden.sh
#
# The app password is read from stdin (not echoed) and printed once as a
# DATABASE_URL line for copying to the Gateway host.

set -euo pipefail

GATEWAY_IP="${GATEWAY_IP:-192.168.31.173}"
DB_LISTEN_IP="${DB_LISTEN_IP:?Set DB_LISTEN_IP to this host LAN address}"
PG_VERSION="${PG_VERSION:-17}"
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"
ROLE_NAME="family_ai_app"
DB_NAME="family_ai"

if [[ ! -f "$PG_CONF" ]]; then
  echo "PostgreSQL config not found at $PG_CONF" >&2
  exit 1
fi

read -r -s -p "Enter password for role ${ROLE_NAME}: " APP_PASSWORD
echo
if [[ -z "$APP_PASSWORD" ]]; then
  echo "Password must not be empty." >&2
  exit 1
fi

ESCAPED_PASSWORD="${APP_PASSWORD//\'/\'\'}"
ENCODED_PASSWORD="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read().strip(), safe=''))" <<<"$APP_PASSWORD")"

echo "=== Create role and database ==="
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${ROLE_NAME}') THEN
    CREATE ROLE ${ROLE_NAME} WITH LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  ELSE
    ALTER ROLE ${ROLE_NAME} WITH LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "${ROLE_NAME}" -E UTF8 "${DB_NAME}"
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres <<SQL
REVOKE ALL ON DATABASE ${DB_NAME} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${ROLE_NAME};
SQL

echo "=== Configure listen address ==="
if grep -q "^listen_addresses" "$PG_CONF"; then
  sed -i "s/^#*listen_addresses.*/listen_addresses = '${DB_LISTEN_IP}'/" "$PG_CONF"
else
  echo "listen_addresses = '${DB_LISTEN_IP}'" >>"$PG_CONF"
fi

echo "=== Configure pg_hba.conf ==="
if ! grep -q "${GATEWAY_IP}/32" "$PG_HBA"; then
  cat >>"$PG_HBA" <<EOF

# Family AI Gateway
host    ${DB_NAME}    ${ROLE_NAME}    ${GATEWAY_IP}/32    scram-sha-256
EOF
fi

systemctl restart postgresql

echo
echo "Copy this line to /etc/family-ai/db.env on the Gateway host (chmod 600):"
echo "FAMILY_AI_DATABASE_URL=postgresql+psycopg://${ROLE_NAME}:${ENCODED_PASSWORD}@${DB_LISTEN_IP}:5432/${DB_NAME}"
