# Family AI Mentor

Домашний голосовой наставник для ребёнка. Основной сервис — AI Gateway.

## Архитектура (Production/Stage)

Проект развёрнут на двух узлах в домашней сети:

- **Gateway (шлюз):** `192.168.31.173` (Debian 13, Python 3.13, `uv`)
- **Database (БД):** `192.168.31.163` (PostgreSQL 17)

## Переменные окружения

Все настройки передаются через префикс `FAMILY_AI_` (см. `.env.example`):

- `FAMILY_AI_DATABASE_URL`: `postgresql+psycopg://user:pass@192.168.31.163:5432/family_ai`
- `FAMILY_AI_OPENAI_API_KEY`: ключ провайдера LLM/STT/TTS
- `FAMILY_AI_OPENAI_MODEL`: модель чата (например, `deepseek-chat`)
- `FAMILY_AI_OPENAI_BASE_URL`: базовый URL провайдера (для DeepSeek: `https://api.deepseek.com/v1`)
- `FAMILY_AI_STT_MODEL`: модель распознавания речи
- `FAMILY_AI_TTS_MODEL`: модель синтеза речи
- `FAMILY_AI_TTS_VOICE`: голос синтеза
- `FAMILY_AI_MESSAGE_RETENTION_DAYS`: срок хранения истории (дней)

### Переменные админки

- `FAMILY_AI_ADMIN_USERNAME`: логин администратора
- `FAMILY_AI_ADMIN_PASSWORD`: пароль администратора
- `FAMILY_AI_ADMIN_FORCE_PASSWORD_CHANGE`: `true/false`, требовать смену пароля при первом входе
- `FAMILY_AI_ADMIN_ENV_FILE`: путь к env-файлу, который редактирует админка

## Локальный запуск

Требуется Python 3.13 и `uv`.

### Gateway API (порт 8000)

```powershell
uv sync --all-groups
uv run uvicorn gateway.app.main:app --reload
```

Проверка: `http://127.0.0.1:8000/healthz`

### Admin Panel (порт 8001)

```powershell
uv run uvicorn gateway.admin.main:app --host 0.0.0.0 --port 8001 --reload
```

Админка доступна по адресу: `http://127.0.0.1:8001`

## Локальная база данных

```powershell
docker compose up -d postgres
copy .env.example .env
uv run alembic upgrade head
```

## Проверки и тесты

```powershell
uv run ruff check .
uv run pytest
```

Тесты используют мок-провайдер AI и не требуют реального API-ключа.

## Production

- PostgreSQL разворачивается на `family-ai-db` (Debian 13).
- Скрипты: `scripts/postgres/fix-install.sh`, `scripts/postgres/harden.sh`.
- Секреты БД хранятся на Gateway в `/etc/family-ai/db.env` (`chmod 600`).
- Ежедневная очистка сообщений: `uv run python scripts/run_retention.py`.

### Управление админкой через systemd

```bash
sudo systemctl status family-ai-admin
sudo systemctl restart family-ai-admin
sudo journalctl -u family-ai-admin -n 100 --no-pager
```

### Первый вход в админку

1. Открыть `http://<gateway-ip>:8001`
2. Войти логином/паролем из `.env`
3. Если включён `FAMILY_AI_ADMIN_FORCE_PASSWORD_CHANGE=true`, админка сразу потребует сменить пароль

Конфигурация передаётся через переменные окружения. Секреты и `.env` не добавляются в репозиторий.

## Быстрый запуск в проде (без systemd)

```bash
cd /home/familyai-deploy/family-ai
nohup ./.venv/bin/python -m uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
nohup ./.venv/bin/python -m uvicorn gateway.admin.main:app --host 0.0.0.0 --port 8001 > admin.log 2>&1 &
```

Проверка портов:

```bash
ss -ltnp | grep -E '8000|8001'
```

### Перезапуск без systemd

```bash
pkill -f "gateway.app.main:app" || true
pkill -f "gateway.admin.main:app" || true

nohup ./.venv/bin/python -m uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
nohup ./.venv/bin/python -m uvicorn gateway.admin.main:app --host 0.0.0.0 --port 8001 > admin.log 2>&1 &
```

Логи:

```bash
tail -n 100 server.log
tail -n 100 admin.log
```
