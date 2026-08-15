# Безопасное управление runtime-конфигурацией

## Назначение

Вкладка «Настройки» управляет только разрешённой частью Gateway-конфигурации:

- LLM и web search;
- общими и раздельными STT/TTS endpoints, моделями, голосом и ключами;
- Vision и поиском иллюстраций;
- ACRCloud;
- сроком хранения сообщений.

Строка PostgreSQL, пароль Admin, адреса node exporter, operational thresholds и
остальные инфраструктурные значения не входят в этот lifecycle. Они не меняются
при apply или rollback старой ревизии.

## Как применяется изменение

1. Admin отправляет candidate в `POST /api/settings/preview`.
2. Gateway проверяет allow-list и валидирует полную candidate-конфигурацию через
   ту же Pydantic-модель `Settings`, которая используется приложением. CR, LF и
   NUL в строковых значениях отклоняются до записи, чтобы значение не могло
   создать дополнительную environment-переменную.
3. В браузер возвращается redacted diff. Значение секрета никогда не возвращается:
   видно только `настроен` или `не настроен`.
4. После подтверждения `POST /api/settings` создаёт исходную baseline-ревизию,
   атомарно заменяет `/etc/family-ai/gateway.env` и перезапускает только
   `family-ai-gateway.service`.
5. Ревизия принимается, только когда `http://127.0.0.1:8000/healthz` отвечает
   успешно.
6. При ошибке старый environment-файл возвращается байт-в-байт, Gateway снова
   запускается и проверяется. Неуспешная candidate остаётся только в безопасном
   metadata со статусом `rolled_back`; её секретный snapshot не сохраняется.

Health-check подтверждает загрузку процесса и его локальный HTTP-контракт. Он не
выполняет платные запросы к LLM, STT, TTS или Vision. После существенной смены
провайдера следует использовать «Тест-студию». Полный provider-контур также
проверяет release smoke-test.

## Ревизии

Production-каталог:

```text
/var/lib/family-ai-config/gateway/
  <revision-id>.json  # redacted metadata, chmod 0600
  <revision-id>.env   # только managed allow-list, chmod 0600
```

Каталог принадлежит `familyai-deploy`, имеет режим `0700` и доступен на запись
только Admin unit. Хранятся последние 20 событий. Snapshot может содержать
реальные provider credentials, поэтому его нельзя копировать в Git, прикладывать
к диагностике или показывать через API.

Статусы:

- `active` — текущая подтверждённая конфигурация;
- `superseded` — рабочая предыдущая ревизия, доступная для возврата;
- `rolled_back` — отклонённая попытка без восстанавливаемого snapshot.

Rollback выполняется через
`POST /api/settings/revisions/{revision_id}/rollback`. Он создаёт новую активную
ревизию с ссылкой `source_revision_id`, а не переписывает историю.

## Speech runtime

Speech Service остаётся владельцем `/var/lib/family-ai-speech/runtime.env` и
принимает только `beam size` и `VAD` через свой закрытый API. Gateway не получает
доступ к файловой системе Speech-хоста.

При изменении Admin запоминает прежние значения, ждёт новый `instance_id` и
проверяет фактические beam/VAD. Если новый процесс не подтверждается, adapter
отправляет прежние значения повторно и ждёт отдельный восстановленный процесс.
Если недоступен сам закрытый API, Admin явно сообщает, что автоматический rollback
не смог подтвердить восстановление.

## API

Все endpoints требуют Admin session:

- `GET /api/settings` — текущая эффективная конфигурация без секретов;
- `POST /api/settings/preview` — проверка и redacted diff без записи;
- `POST /api/settings` — атомарное применение, restart и health-check;
- `GET /api/settings/revisions` — локальная безопасная история;
- `POST /api/settings/revisions/{id}/rollback` — контролируемый возврат;
- `GET/PUT /api/speech/runtime-settings` — чтение и применение beam/VAD.

OpenAPI содержит точные request/response-схемы.

## Развёртывание и права

Обычный Gateway release обновляет systemd unit и идемпотентно создаёт каталог:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 deploy gateway `
  -HostName 192.168.31.173 `
  -Commit <commit>
```

`family-ai-admin.service` получает:

```text
FAMILY_AI_ADMIN_ENV_FILE=/etc/family-ai/gateway.env
FAMILY_AI_ADMIN_CONFIG_HISTORY_DIR=/var/lib/family-ai-config/gateway
ReadWritePaths=/etc/family-ai /var/lib/family-ai-config/gateway
```

Произвольная команда от веб-процесса не выполняется. Admin с
`NoNewPrivileges=true` атомарно пишет одноразовый nonce в закрытый
`restart.request`. Root-owned path unit перезапускает только известную
Gateway-службу и подтверждает выполнение тем же nonce в `restart.ack`.

Для атомарного `rename(2)` Gateway-каталог `/etc/family-ai` принадлежит
`root:familyai-deploy` и имеет режим `0770`. Systemd делает его writable только
в sandbox Admin unit. На Gateway-хосте каталог предназначен для управляемого
`gateway.env`; Speech-конфигурация находится на отдельном Speech-хосте.

## Проверка

```powershell
.\.venv\Scripts\python.exe -m ruff check gateway alembic
.\.venv\Scripts\python.exe -m pytest gateway/tests/test_admin_configuration.py
.\.venv\Scripts\python.exe -m pytest gateway/tests/test_speech_runtime_service.py
```

После deploy:

1. открыть вкладку «Настройки» и убедиться, что история доступна;
2. изменить безвредное значение, например timeout;
3. проверить redacted diff;
4. применить и дождаться сообщения об успешном health-check;
5. вернуть baseline и убедиться, что Gateway снова готов;
6. проверить «Тест-студию» для LLM/TTS/STT/Vision.

Архитектурные решения: [ADR 038](adr/038-safe-runtime-configuration-lifecycle.md)
и [ADR 039](adr/039-root-mediated-gateway-restart.md).
