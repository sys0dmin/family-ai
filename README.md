# Family AI Mentor

Домашний голосовой наставник для ребёнка. Первый сервис — AI Gateway.

## Локальный запуск

Требуется Python 3.13 и `uv`.

```powershell
uv sync --all-groups
uv run uvicorn gateway.app.main:app --reload
```

Проверка доступна по адресу `http://127.0.0.1:8000/healthz`.

## Проверки

```powershell
uv run ruff check .
uv run pytest
```

Конфигурация передаётся через переменные окружения. Секреты и `.env` не добавляются в репозиторий.

