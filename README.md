# Family AI Mentor

Домашний голосовой наставник для ребёнка. Первый сервис — AI Gateway.

## Архитектура (Production/Stage)

Проект развернут на двух узлах в домашней сети:
- **Gateway (Шлюз):** `192.168.31.173` (Debian 13, Python 3.13, `uv`)
- **Database (БД):** `192.168.31.163` (PostgreSQL 17)

### Переменные окружения

Все настройки передаются через префикс `FAMILY_AI_` (см. `.env.example`):
- `FAMILY_AI_DATABASE_URL`: `postgresql+psycopg://user:pass@192.168.31.163:5432/family_ai`
- `FAMILY_AI_OPENAI_API_KEY`: Ключ для STT/LLM/TTS
- `FAMILY_AI_MESSAGE_RETENTION_DAYS`: Срок хранения истории (10 дней)

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

## Проверки и тесты

```powershell
# Локально или на шлюзе
uv run ruff check .
uv run pytest
```

Тесты автоматически используют мок-провайдер для AI, поэтому не требуют реального ключа OpenAI.

```

## Production

- PostgreSQL разворачивается на `family-ai-db` (Debian 13).
- Скрипты: `scripts/postgres/fix-install.sh`, `scripts/postgres/harden.sh`.
- Секреты БД хранятся на Gateway в `/etc/family-ai/db.env` (`chmod 600`).
- Ежедневная очистка транскриптов: `uv run python scripts/run_retention.py`.

Конфигурация передаётся через переменные окружения. Секреты и `.env` не добавляются в репозиторий.

