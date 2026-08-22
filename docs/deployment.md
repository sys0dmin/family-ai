# Воспроизводимое развёртывание Family AI

## Что развёртывается

Есть два независимо версионируемых компонента:

| Компонент | Службы | Production-хост |
|---|---|---|
| `gateway` | `family-ai-gateway`, `family-ai-admin`, retention timer | `192.168.31.173` |
| `speech` | `family-ai-speech` | `192.168.31.84` |

Gateway и Admin переключаются вместе. Это исключает ситуацию, когда админка
работает с несовместимой версией Gateway-моделей или конфигурации.

Все команды выполняются из корня репозитория в PowerShell. По умолчанию
используются пользователь `familyai-deploy` и ключ
`~/.ssh/family-ai-deploy`.

Если локальная execution policy запрещает `.ps1`, запускайте скрипт через
`powershell -NoProfile -ExecutionPolicy Bypass -File`, как в примерах ниже.

## Как код попадает на сервер

Production-хосты не выполняют `git clone` или `git pull`. Развёртывание не
зависит от доступности GitHub и не требует предварительного `git push`:

```text
рабочая копия на Windows
  -> локальный Git commit
  -> git archive только из этого commit
  -> детерминированный tar.gz + release.json + SHA-256
  -> SCP готового архива на production-хост
  -> проверка манифеста и SHA-256
  -> /srv/family-ai/<component>/releases/<commit>
  -> атомарное переключение current
  -> restart systemd + health-check
  -> автоматический rollback при ошибке
```

SCP используется только как транспорт собранного release-артефакта и
release-controller. Отдельные файлы приложения вручную не копируются.

`git push` — независимая операция сохранения локальных коммитов в удалённом
Git-репозитории. Она нужна для синхронизации истории разработки, но сама по себе
ничего не развёртывает. И наоборот, локальный commit можно развернуть до push,
хотя при финализации работы следует выполнить обе операции и убедиться, что
production и ветка `main` указывают на один commit.

Фактический manifest активного процесса, controller marker, Alembic revision и
последнюю замеченную Android-сборку объединяет Admin-паспорт. Диагностика
расхождений описана в [`release-passport.md`](release-passport.md).

Перед любым production-релизом выполнить единый локальный gate из точного
чистого commit. Команда и состав проверок описаны в
[`release-gate.md`](release-gate.md).

## Обычное обновление без миграции

Команда строит архив из конкретного commit, проверяет SHA-256, устанавливает
зависимости из `uv.lock`, атомарно переключает `current`, перезапускает службы и
ждёт health-check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 deploy gateway `
  -HostName 192.168.31.173 `
  -Commit <полный-commit-или-тег>

powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 deploy speech `
  -HostName 192.168.31.84 `
  -Commit <полный-commit-или-тег>
```

Повтор той же команды идемпотентен. Пакет всегда собирается через `git archive`;
незакоммиченные локальные файлы в него не попадают.

Даже для этой короткой команды release-controller перед активацией Gateway
сравнивает Alembic revision БД с code head релиза. Если в commit появилась новая
миграция, `deploy` безопасно остановится до переключения `current`; нужно
выполнить трёхфазную процедуру ниже.

## Функциональный smoke-test релиза

После health-check нового Gateway-релиза release-controller автоматически
запускает сквозную функциональную проверку из активированного release-каталога.
Она использует только loopback HTTP и последовательно проверяет:

1. HTML, CSS и JavaScript Admin UI;
2. Gateway и чтение активных агентов из PostgreSQL;
3. LLM через stateless-контур тест-студии;
4. TTS на синтетической фразе `Проверка связи`;
5. STT на только что синтезированном аудио;
6. Vision на сгенерированном одноцветном PNG, если Vision включён.

Проверка не создаёт детский диалог, сообщения, медиа, activity session или
долгосрочную память. Синтетические аудио и изображение существуют только в
памяти процесса до завершения команды. Если Vision отключён конфигурацией, его
этап получает статус `skipped`; настроенный, но неработающий Vision завершает
релиз ошибкой.

При ошибке вывод содержит стабильное имя этапа (`admin_ui`,
`gateway_database`, `llm`, `tts`, `stt` или `vision`) без ключей, паролей и
содержимого ответов провайдеров. Новый Gateway-релиз не записывается как
успешный, а controller атомарно возвращает предыдущий код и проверяет его
health-check.

Smoke-test текущего активного Gateway можно повторить отдельно:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 smoke gateway `
  -HostName 192.168.31.173
```

Команда обращается к реальным настроенным провайдерам и может занимать несколько
десятков секунд на J3710. Она предназначена для релиза и диагностики, а не для
частого опроса. Развёртывание Speech остаётся независимым; после изменения его
моделей или runtime-конфигурации полный контур проверяется этой же командой с
Gateway-хоста.

## Обновление с миграцией БД

Миграция никогда не запускается автоматически:

```powershell
# 1. Установить код и точные зависимости, но не переключать службы.
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 prepare gateway `
  -HostName 192.168.31.173 `
  -Commit <commit>

# 2. Явно применить forward-миграции этим подготовленным релизом.
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 migrate gateway `
  -HostName 192.168.31.173 `
  -TargetVersion <полный-commit>

# 3. Переключить Gateway и Admin на уже проверенный релиз.
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 activate gateway `
  -HostName 192.168.31.173 `
  -TargetVersion <полный-commit>
```

Миграции должны сохранять обратную совместимость с предыдущим кодом хотя бы на
время релиза. Автоматический rollback кода не выполняет downgrade БД.
Активация Gateway с неподготовленной схемой блокируется до перезапуска служб.
Явный rollback старого совместимого кода остаётся доступен после forward-миграции.

## Статус и откат

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy\release.ps1 `
  status gateway -HostName 192.168.31.173
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy\release.ps1 `
  status speech -HostName 192.168.31.84

# Вернуть previous:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy\release.ps1 `
  rollback gateway -HostName 192.168.31.173

# Или переключиться на заранее подготовленный commit:
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 rollback speech `
  -HostName 192.168.31.84 `
  -TargetVersion <полный-commit>
```

Если health-check нового релиза не проходит, controller сам возвращает
предыдущую ссылку `current`, перезапускает прежний код и завершает команду с
ошибкой.

То же происходит, если процессы готовы, но функциональный smoke-test Gateway не
прошёл. Откат к явно выбранной старой версии выполняет health-check, но не
требует наличия smoke-runner в историческом release-артефакте.

## Каталоги на сервере

```text
/srv/family-ai/
  tools/uv-<version>/
  gateway/
    current -> releases/<commit>/
    previous -> releases/<commit>/
    deployed-version
    incoming/
    releases/
    venvs/<uv.lock sha256>/
  speech/
    ...
```

Изменяемые и чувствительные данные не находятся внутри релиза:

- `/etc/family-ai/gateway.env` — Gateway/Admin, владелец `familyai-deploy`,
  режим `0600`, потому что защищённая админка редактирует настройки;
- `/etc/family-ai/speech.env` — основной Speech-конфиг;
- `/var/lib/family-ai-speech/runtime.env` — управляемые из админки VAD/beam/token limit;
- `/var/lib/family-ai-speech/models` — кеш моделей;
- `/var/lib/family-ai-config/gateway` — последние 20 локальных ревизий только
  управляемой части Gateway-конфигурации; каталог `0700`, файлы `0600`;
- `/var/lib/family-ai-diagnostics` — не более 200 обезличенных технических трасс
  Gateway/Admin за последние 24 часа; сообщения и медиа туда не попадают;
- PostgreSQL — история и конфигурация агентов.

Admin применяет runtime-настройки через безопасный lifecycle с redacted preview,
readiness-check и автоматическим возвратом. Это не заменяет release rollback и не
является резервной копией. Подробности — в
[`runtime-configuration.md`](runtime-configuration.md).

На Gateway-хосте `/etc/family-ai` имеет владельца `root:familyai-deploy` и режим
`0770`: это требуется для атомарного создания и `rename` временного env-файла.
Запись каталога доступна только Admin unit через явный `ReadWritePaths`.
В этом же закрытом каталоге находятся одноразовые `restart.request` и
`restart.ack`. Root-owned `family-ai-gateway-admin.path` запускает фиксированный
helper только для `family-ai-gateway.service`; Admin не вызывает `sudo`, а его
`NoNewPrivileges=true` не отключается.

Скрипты не печатают содержимое env-файлов. В архив допускаются только явно
перечисленные runtime-пути из Git commit; `.env`, `.git` и локальные файлы туда
не входят.

## Первый запуск и требования

`release.ps1` сам идемпотентно устанавливает systemd unit-файлы и создаёт
каталоги. Для bootstrap у SSH-пользователя должен быть `sudo`. На хосте нужны:

- Linux с systemd;
- Python 3.13, `python3-venv`, `curl`, `tar`, `sha256sum`;
- сетевой доступ к индексам пакетов при первой установке нового `uv.lock`;
- существующие `/etc/family-ai/speech.env` и legacy `.env` Gateway при первом
  переносе.

Первый переход создаёт `current`, указывающий на прежний рабочий каталог. Это
позволяет безопасно вернуть legacy-код, если первый новый релиз не пройдёт
health-check.

Перед публикацией нового release-controller:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -n `
  scripts/deploy/remote_release.sh `
  scripts/deploy/install_host.sh

.\.venv\Scripts\python.exe -m pytest gateway/tests/test_release_builder.py
```

Для восстановления на трёх полностью чистых VM используется отдельный
clean-room orchestrator: [`disaster-recovery.md`](disaster-recovery.md).
