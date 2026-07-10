# Family AI Mentor

Домашний голосовой наставник для ребёнка. Первый сервис — AI Gateway.

## Локальный запуск

Требуется Python 3.13 и `uv`.

```powershell
uv sync --all-groups
uv run uvicorn gateway.app.main:app --reload
```

Проверка доступна по адресу `http://127.0.0.1:8000/healthz`.

### Локальная база данных

```powershell
docker compose up -d postgres
copy .env.example .env
uv run alembic upgrade head
```

## Проверки

```powershell
uv run ruff check .
uv run pytest
```

## Production

- PostgreSQL разворачивается на `family-ai-db` (Debian 13).
- Скрипты: `scripts/postgres/fix-install.sh`, `scripts/postgres/harden.sh`.
- Секреты БД хранятся на Gateway в `/etc/family-ai/db.env` (`chmod 600`).
- Ежедневная очистка транскриптов: `uv run python scripts/run_retention.py`.

Конфигурация передаётся через переменные окружения. Секреты и `.env` не добавляются в репозиторий.

