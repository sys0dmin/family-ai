#!/usr/bin/env bash
# Fix broken PostgreSQL installation after ssl-cert postinst failure on Debian 13.
# Run as root on family-ai-db.

set -euo pipefail

echo "=== Diagnosis ==="
hostname -f || true
hostname -s || true
cat /etc/hostname || true
dpkg -l ssl-cert postgresql-common postgresql-17 postgresql 2>/dev/null || true

HOSTNAME_SHORT="$(hostname -s)"
if [[ ! "$HOSTNAME_SHORT" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
  echo "Hostname contains unsafe characters for ssl-cert; setting family-ai-db"
  echo family-ai-db >/etc/hostname
  hostname family-ai-db
fi

if ! grep -qE '^\s*127\.0\.1\.1\s+' /etc/hosts; then
  echo "127.0.1.1 family-ai-db" >>/etc/hosts
fi

echo "=== Repair packages ==="
export DEBIAN_FRONTEND=noninteractive
apt --fix-broken install -y

if ! dpkg --configure ssl-cert; then
  echo "ssl-cert configure failed; attempting manual snakeoil generation"
  if command -v make-ssl-cert >/dev/null 2>&1; then
    make-ssl-cert generate-default-snakeoil --force-overwrite || true
  fi
  dpkg --configure ssl-cert
fi

dpkg --configure -a
apt install -y postgresql postgresql-client

systemctl enable postgresql
systemctl start postgresql

echo "=== Cluster status ==="
pg_lsclusters
sudo -u postgres psql -c "SELECT version();"

echo "PostgreSQL installation repair complete."
