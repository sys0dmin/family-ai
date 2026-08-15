# Паспорт запущенных версий

## Назначение

Паспорт отвечает не на вопрос «что лежит в Git», а на вопрос «что прямо сейчас
работает в домашнем контуре». Он находится в верхней части вкладки
«Инфраструктура» и обновляется вместе с локальным снимком.

Паспорт показывает:

- фактический и ожидаемый commit Gateway;
- фактический и ожидаемый commit Speech Service;
- application version и process uptime обоих сервисов;
- текущую Alembic revision PostgreSQL и head активного Gateway release;
- последнюю замеченную версию и source commit release-APK;
- SHA-256 fingerprint эффективной конфигурации без её значений.

## Статусы

- `Совпадает` — фактическая identity совпала с локальным источником истины;
- `Drift` — процесс отвечает, но commit, схема или fingerprint отличается;
- `Нет данных` — компонент недоступен или identity нельзя подтвердить;
- `Замечен` — release Android сообщил build-wide версию и commit.

Отсутствие данных никогда не считается совпадением. Android не влияет на
работоспособность Gateway, но до первого запроса после рестарта общий паспорт
отмечается неполным.

## Источники истины

### Gateway и Speech

Release builder добавляет в каждый неизменяемый архив `release.json`. После
успешной активации release-controller записывает выбранный commit в:

```text
/srv/family-ai/gateway/deployed-version
/srv/family-ai/speech/deployed-version
```

Сервис сравнивает manifest активного процесса с соответствующим маркером. Поэтому
ручное переключение `current`, повреждённый manifest или незавершённая активация
видны как drift или отсутствие данных.

Gateway публикует identity только на loopback endpoint
`/internal/runtime-identity`. Speech включает identity в уже защищённый
`/internal/metrics`. Admin остаётся единственным браузерным API:

```text
GET /api/infrastructure/release-passport
```

### PostgreSQL

Admin читает `alembic_version` через существующее подключение PostgreSQL и
сравнивает единственную текущую revision с единственным head активного Gateway
release. Проверка ничего не мигрирует и не меняет.

### Android

Release builder передаёт в Dart compile-time значения
`FAMILY_AI_APP_VERSION` и `FAMILY_AI_SOURCE_COMMIT`. Gateway принимает их в
заголовках `X-Family-AI-App-Version` и `X-Family-AI-App-Commit`.

Хранится только последняя валидная пара и время в оперативной памяти процесса.
Не сохраняются device ID, IP, пользователь, conversation ID или история версий.
После рестарта запись исчезает до следующего запроса приложения. Debug-сборка
отправляет `development`; Gateway её игнорирует.

### Fingerprint конфигурации

Gateway и Admin независимо строят canonical JSON эффективных настроек и считают
SHA-256. До хеширования исключаются все секреты, `database_url`, Admin username
и runtime-пути конфигурации. В API и интерфейсе нет исходных значений.

## Проверка после release

1. Открыть «Инфраструктура» и нажать «Обновить».
2. Gateway, Speech, PostgreSQL schema и конфигурация должны быть зелёными.
3. Сравнить полные commits во всплывающих подсказках с release-командой.
4. Открыть release Android и выполнить любой безопасный запрос.
5. Обновить паспорт: Android должен показать version и первые восемь символов
   source commit.
6. При drift не исправлять symlink вручную: выполнить `release.ps1 status`,
   затем штатный deploy или rollback.

Архитектурное решение описано в
[`ADR 042`](adr/042-runtime-release-passport.md), воспроизводимое развёртывание —
в [`deployment.md`](deployment.md), Android release — в
[`android-release.md`](android-release.md).
