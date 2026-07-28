#!/usr/bin/env bash
set -euo pipefail

DATABASE_NAME="${1:-family_ai}"

sudo -u postgres psql -At -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
  -c "SELECT 'alembic|' || version_num FROM alembic_version ORDER BY version_num" \
  2>/dev/null || true

while IFS= read -r table; do
  count="$(sudo -u postgres psql -At -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -c "SELECT count(*) FROM public.\"${table}\"")"
  printf 'table:%s|%s\n' "$table" "$count"
done < <(
  sudo -u postgres psql -At -v ON_ERROR_STOP=1 -d "$DATABASE_NAME" \
    -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
)
