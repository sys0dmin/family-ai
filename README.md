# Family AI Mentor

Домашний голосовой наставник для ребёнка. Основной сервис — AI Gateway.

## Архитектура (Production/Stage)

Проект развёрнут на двух узлах в домашней сети:

- **Gateway (шлюз):** `192.168.31.173` (Debian 13, Python 3.13, `uv`)
- **Database (БД):** `192.168.31.163` (PostgreSQL 17)

## Переменные окружения

Все настройки передаются через префикс `FAMILY_AI_` (см. `.env.example`):

- `FAMILY_AI_DATABASE_URL`: `postgresql+psycopg://user:pass@192.168.31.163:5432/family_ai`
- `FAMILY_AI_OPENAI_API_KEY`: ключ текстового LLM-провайдера
- `FAMILY_AI_OPENAI_MODEL`: модель чата (например, `deepseek-chat`)
- `FAMILY_AI_OPENAI_BASE_URL`: базовый URL провайдера (для DeepSeek: `https://api.deepseek.com/v1`)
- `FAMILY_AI_WEB_SEARCH_TOOL_TYPE`: `browser_search` для provider-native поиска Groq GPT-OSS или `disabled`
- `FAMILY_AI_SPEECH_API_KEY`: отдельный ключ провайдера STT/TTS
- `FAMILY_AI_SPEECH_BASE_URL`: API STT/TTS (для OpenAI: `https://api.openai.com/v1`)
- `FAMILY_AI_STT_MODEL`: модель распознавания речи
- `FAMILY_AI_STT_TEMPERATURE`: вариативность распознавания (`0` для стабильного результата)
- `FAMILY_AI_TTS_MODEL`: модель синтеза речи
- `FAMILY_AI_TTS_VOICE`: голос синтеза
- `FAMILY_AI_TTS_RESPONSE_FORMAT`: формат аудиоответа (`mp3` или `wav`)
- `FAMILY_AI_MESSAGE_RETENTION_DAYS`: срок хранения истории (дней)
- `FAMILY_AI_DEFAULT_AGENT_ID`: агент для клиентов, которые не передали выбор явно
- `FAMILY_AI_MUSIC_RECOGNITION_PROVIDER`: `disabled` или `acrcloud`
- `FAMILY_AI_ACRCLOUD_HOST`, `FAMILY_AI_ACRCLOUD_ACCESS_KEY`, `FAMILY_AI_ACRCLOUD_ACCESS_SECRET`: данные Audio & Video Recognition project ACRCloud
- `FAMILY_AI_MUSIC_RECOGNITION_TIMEOUT_SECONDS`: таймаут внешнего распознавания

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

Интерфейс адаптирован для компьютера и телефона и не загружает внешние UI-библиотеки или шрифты.

После входа доступны отдельные вкладки:

- «Настройки» — модели, ключи, голос, распознавание мелодий и срок хранения;
- «Агенты» — карточки персонажей, голоса, инструменты и версионные промпты;
- «Инфраструктура» — состояние двух LXC, CPU, память, диски, uptime и PostgreSQL;
- «История и аналитика» — недавние диалоги, поиск, активность и частые вопросы.

Промпт личности не редактируется на месте. Админ создаёт новую неизменяемую
версию и отдельно публикует её. Новая версия применяется только к новым
диалогам; уже начатые продолжают использовать закреплённую версию. Общие
правила детской безопасности хранятся в Gateway и не редактируются через UI.

История доступна только через защищённую админку. Исходное аудио не сохраняется,
а текстовые сообщения автоматически удаляются согласно сроку хранения.

### Метрики инфраструктуры

На `family-ai-gateway` и `family-ai-db` устанавливается `prometheus-node-exporter`.
Админка читает endpoints только на серверной стороне; браузер не обращается к
exporter напрямую. Для production задаются:

```dotenv
FAMILY_AI_GATEWAY_NODE_METRICS_URL=http://127.0.0.1:9100/metrics
FAMILY_AI_DATABASE_NODE_METRICS_URL=http://192.168.31.163:9100/metrics
FAMILY_AI_MONITORING_REQUEST_TIMEOUT_SECONDS=2
```

Порт `9100` на контейнере БД должен быть доступен только с Gateway
`192.168.31.173`. История мини-графиков хранится только в текущей вкладке браузера.

## Агенты

Детский API `GET /v1/agents` возвращает только безопасные данные для карточек:
имя, описание, иконку, цвет и приветствие. Промпты, версии и настройки голоса
доступны только родителю через защищённую админку.

Новый диалог создаётся запросом `POST /v1/conversations/` с телом
`{"agent_id": "scientist"}`. Выбранный агент и точная ревизия сохраняются в
таблице `conversations`. Голос TTS берётся из конфигурации выбранного агента.

Агент «Нотка» умеет сочинять с ребёнком новые песни и получает два явно разрешённых инструмента: `music_recognition` для аудио и `web_search` для фрагментов текста. Только его голосовые ходы могут отправляться в ACRCloud, а текстовые фрагменты — в provider-native веб-поиск. Исходное аудио не сохраняется; если инструмент выключен или не нашёл совпадение, агент не выдумывает ответ, а просит напеть ещё раз или добавить слова.

Агент «Мурка» имеет узкое permission `supervised_outdoor_safety`. Она даёт полезные ответы о палатке, костре, спичках, рыбалке, ноже и опасностях дикой природы, но опасную часть действия всегда отдаёт родителю. Она может объяснять, чем опасны растения, клещи, змеи, животные, вода, погода и другие походные риски. Gateway программно добавляет напоминание о родителях, если модель его пропустила. Мурка не определяет найденный вид или съедобность по тексту или фото.

### Детский интерфейс

Интерфейс рассчитан на ребёнка, который ещё не читает: агенты различаются
крупными иллюстрациями, цветами и визуальными предметами, а основные состояния
передаются движением и цветовым индикатором. Нажатие на персонажа может озвучить
его приветствие системным голосом браузера. Вся автоматическая озвучка текстового
режима отключается кнопкой `🔊 / 🔇`, а выбор сохраняется локально на устройстве.
На голосовой диалог эта настройка не влияет. Голосовая кнопка является основным действием, текстовый ввод
открывается отдельно как дополнительный режим.

Визуальные подсказки запускают обычный текстовый ход Gateway, после чего ответ
озвучивается голосом закреплённого агента через
`POST /v1/voice/{conversation_id}/synthesize`. Интерфейс адаптирован для
desktop, Android-планшета и узкого мобильного экрана.

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

### Управление Gateway через systemd

```bash
sudo systemctl status family-ai-gateway
sudo systemctl restart family-ai-gateway
sudo journalctl -u family-ai-gateway -n 100 --no-pager
```

### Автоматическая очистка истории

```bash
sudo systemctl status family-ai-retention.timer
sudo systemctl start family-ai-retention.service
sudo journalctl -u family-ai-retention.service -n 50 --no-pager
```

Timer запускает очистку ежедневно и удаляет сообщения старше
`FAMILY_AI_MESSAGE_RETENTION_DAYS`. `Persistent=true` выполняет пропущенную
очистку после включения сервера.

### Первый вход в админку

1. Открыть `http://<gateway-ip>:8001`
2. Войти логином/паролем из `.env`
3. Если включён `FAMILY_AI_ADMIN_FORCE_PASSWORD_CHANGE=true`, админка сразу потребует сменить пароль

Конфигурация передаётся через переменные окружения. Секреты и `.env` не добавляются в репозиторий.

## Аварийный запуск в проде (без systemd)

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
