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
- `/var/lib/family-ai-speech/runtime.env` — управляемые из админки VAD/beam;
- `/var/lib/family-ai-speech/models` — кеш моделей;
- PostgreSQL — история и конфигурация агентов.

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
