# Единый локальный release gate

Release gate — последняя обязательная локальная проверка конкретного Git commit
перед push, сборкой Android или развёртыванием. Он не изменяет production, не
читает домашнюю БД и не отправляет исходники или детские данные во внешние CI.

Архитектурные решения зафиксированы в
[`ADR 043`](adr/043-local-release-gate-and-schema-guard.md) и
[`ADR 044`](adr/044-modular-clients-and-build-time-drift-guards.md).

## Запуск

Рабочее дерево должно быть чистым, а проверяемый commit — текущим `HEAD`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\release\Invoke-LocalReleaseGate.ps1 `
  -Commit HEAD
```

При необходимости путь к локальному Edge или Chrome передаётся через
`-BrowserPath`. Gate намеренно не имеет флага, разрешающего грязное рабочее
дерево: иначе тесты выполнялись бы над одними файлами, а release archive
собирался бы из другого состояния Git.

## Что проверяется

Одна команда последовательно выполняет:

1. политику tracked-файлов и чистоту рабочего дерева;
2. `git diff --check`;
3. актуальность корневого `uv.lock` и отдельного `speech/uv.lock`;
4. совпадение канонических web-ассетов персонажей с Flutter-зеркалом;
5. известные уязвимости в точных lock-графах Gateway и Speech, включая PyTorch
   CPU wheel;
6. Ruff для Gateway, Alembic, Speech и эксплуатационных Python-скриптов;
7. полный pytest Gateway и отдельный pytest Speech Service;
8. `flutter analyze --no-pub` и полный Flutter test suite;
9. визуальные baseline Admin UI в локальном headless-браузере;
10. все локальные Markdown-ссылки;
11. наличие ровно одного Alembic head и, если задан тестовый PostgreSQL,
    полный `upgrade → downgrade → upgrade`;
12. детерминированные Gateway и Speech release archives из точного commit;
13. повторную проверку repository policy после сборки.

Проверка lock-файлов их не обновляет. Dependency audit использует закреплённый
`pip-audit 2.10.1` и обращается только к публичной базе advisory; исходники,
конфигурация и детские данные туда не отправляются. Flutter запускается с
`--no-pub`, браузер — с отключённой фоновой сетью. Обычные unit-тесты не
обращаются к production и внешним LLM/STT/TTS/Vision.

## Disposable PostgreSQL

Для полного доказательства миграционной цепочки передайте административный URL
отдельной системной БД `postgres` или `template1`:

```powershell
$env:FAMILY_AI_MIGRATION_TEST_ADMIN_URL = `
  "postgresql+psycopg://migration_test:password@db-host/postgres"
```

Gate создаст БД `family_ai_migration_test_<случайный суффикс>`, выполнит
`upgrade head`, `downgrade base`, повторный `upgrade head`, проверит
`alembic_version` и удалит БД в `finally`. Скрипт откажется работать, если URL
указывает на прикладную БД. Без переменной стадия явно помечается как skipped;
остальные проверки продолжаются и не подключаются к PostgreSQL.

Канонические изображения лежат в `gateway/static/assets/characters`. После
осознанной замены персонажа Flutter-зеркало обновляется командой:

```powershell
.\.venv\Scripts\python.exe .\scripts\assets\sync_character_assets.py `
  --repo . --write
```

## Политика репозитория

`repository_policy.py` проверяет только файлы, возвращённые `git ls-files`:

- `.env*`, кроме явного `.env.example`, запрещены;
- APK/AAB, keystore, private key, dump, backup, локальные БД и логи запрещены;
- tracked-файл более 2 MiB блокируется как случайный артефакт;
- блокируются только высокодостоверные сигнатуры приватных ключей и токенов
  OpenAI/Groq/GitHub/AWS.

Это страховка, а не хранилище секретов и не замена внимательному review.
Проверка не печатает найденное значение — только путь и тип нарушения.

## Результат

При первом сбое команда завершается ненулевым кодом. Технический отчёт без
секретов сохраняется в игнорируемом каталоге:

```text
.artifacts/release-gate/<full-commit>/gate.json
```

Там находятся статус и длительность этапов. Собранные рядом `gateway.tar.gz` и
`speech.tar.gz` предназначены только для локальной верификации; production
deploy по-прежнему самостоятельно строит и проверяет свой архив из commit.

## Миграции и активация

Локальный gate доказывает, что у кода один Alembic head, но не подключается к
production-БД. Второй независимый барьер работает на Gateway-хосте:

- перед `activate` release-controller сравнивает текущую revision БД с head
  подготовленного релиза;
- при несовпадении активация запрещается до явной команды `migrate`;
- rollback к ранее совместимому коду не требует равенства старого code head и
  уже обновлённой БД.

Таким образом, релиз с миграцией выполняется только в порядке
`prepare → migrate → activate`. Подробные команды приведены в
[`deployment.md`](deployment.md).
