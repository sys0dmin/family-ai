# Полное восстановление Family AI после аварии

Эта инструкция поднимает Family AI на трёх чистых Debian 13 VM:

| Роль | Минимум | Рекомендуется |
|---|---:|---:|
| Gateway/Admin | 2 vCPU, 2 GB RAM, 12 GB disk | 2 vCPU, 3 GB RAM |
| PostgreSQL | 2 vCPU, 2 GB RAM, 20 GB disk | диск больше исходной БД минимум в 2 раза |
| Speech | 4 vCPU, 8 GB RAM, 25 GB disk | максимально быстрый доступный CPU |

Скрипты не создают VM в Proxmox. Администратор создаёт три VM, назначает
статические IP, проверяет DNS/маршрутизацию и добавляет SSH-ключ. Всё после этого
выполняет один orchestrator с Windows-компьютера.

## Границы восстановления

Восстанавливаются:

- код Gateway/Admin/Speech из точного Git commit;
- Python-зависимости из `uv.lock`;
- API-ключи, пароли, Speech-настройки и VAD/beam из зашифрованного DR-kit;
- systemd units, node_exporter, PostgreSQL и сетевые ограничения;
- в salvage-сценарии — вся логическая БД: история, агенты, safety baseline,
  родительская память и Alembic version.

Не восстанавливаются:

- исходные голосовые записи — они намеренно не хранятся;
- история и память при полной потере PostgreSQL;
- Speech model cache — модели загрузятся заново;
- данные, появившиеся после salvage snapshot;
- гипервизор, Ceph, DNS и сами VM.

## Обязательная подготовка до аварии

### 1. Синхронизировать Git

```powershell
cd D:\Documents\Develop\family-ai
git status --short
git pull --ff-only origin main
```

Рабочая директория должна быть чистой. В аварии можно использовать любой
проверенный commit, но обычно выбирается `origin/main`.

Проверить локальную логику разбора конфигурации:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Test-FamilyAiDr.ps1
```

### 2. Создать зашифрованный DR-kit

Выполнять сейчас и повторять после изменения API-ключей, пароля админки,
Database URL или Speech-конфигурации:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Export-FamilyAiDrKit.ps1 `
  -GatewayHost 192.168.31.173 `
  -SpeechHost 192.168.31.84 `
  -OutputPath .dr\family-ai-dr-kit.dpapi
```

Файл `.dr/family-ai-dr-kit.dpapi`:

- исключён из Git;
- не содержит открытого текста;
- расшифровывается только текущей Windows-учётной записью на этом компьютере;
- достаточен при потере VM, но не при одновременной потере этого компьютера.

После создания выполнить `DryRun` только на специально подготовленных пустых
тестовых VM. Production-хосты ожидаемо не пройдут target guard.

Для защиты от потери Windows-компьютера нужна отдельная внешняя копия секретов,
зашифрованная выбранным владельцем способом. DPAPI-файл сам по себе для этого не
подходит.

## Общие требования к новым VM

1. Debian 13 с работающими `apt` и systemd.
2. Три разных статических IP в домашней сети.
3. Не менее 5 GB свободно на `/`; для DB — вдвое больше dump.
4. SSH-доступ по ключу пользователем `root` либо пользователем с
   passwordless `sudo`.
5. На VM не должно быть активного `/srv/family-ai/.../current`.
6. На новой DB VM не должно существовать базы `family_ai`.
7. VM должны иметь доступ к PyPI и PyTorch CPU index на время первой установки.
8. Gateway должен видеть DB:5432 и Speech:8010.

До запуска orchestrator один раз подключиться к каждой новой VM вручную,
сверить показанный SSH fingerprint с консолью Proxmox и добавить его в
`known_hosts`:

```powershell
ssh -i "$env:USERPROFILE\.ssh\family-ai-deploy" root@192.168.31.180 hostname
ssh -i "$env:USERPROFILE\.ssh\family-ai-deploy" root@192.168.31.181 hostname
ssh -i "$env:USERPROFILE\.ssh\family-ai-deploy" root@192.168.31.182 hostname
```

Orchestrator намеренно не отключает `StrictHostKeyChecking`.

Пример адресов в инструкции:

```text
NEW_GATEWAY=192.168.31.180
NEW_DATABASE=192.168.31.181
NEW_SPEECH=192.168.31.182
```

Заменить их своими фактическими адресами.

## Перед запуском любого сценария

1. Зафиксировать время начала инцидента.
2. Не удалять старые диски и VM до окончания проверки.
3. Не назначать старый IP новой VM, пока старый хост доступен в сети.
4. Если старая БД жива, остановить все writer-процессы. Обычно старые
   Gateway/Admin уже мертвы. Если нет:

```bash
sudo systemctl stop family-ai-gateway.service family-ai-admin.service
```

5. Проверить commit:

```powershell
git fetch origin
git rev-parse origin/main
```

## Сценарий A — потеряно всё, включая PostgreSQL

### Предварительная проверка

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Invoke-FamilyAiRecovery.ps1 TotalLoss `
  -GatewayHost 192.168.31.180 `
  -DatabaseHost 192.168.31.181 `
  -SpeechHost 192.168.31.182 `
  -SshUser root `
  -IdentityFile "$env:USERPROFILE\.ssh\family-ai-deploy" `
  -BundlePath .dr\family-ai-dr-kit.dpapi `
  -Commit origin/main `
  -DryRun
```

`DryRun` проверяет DR-kit, commit, SSH, sudo/systemd/apt, свободное место и
пустоту целевых хостов. Ничего не устанавливает и не меняет.

### Восстановление

Повторить команду без `-DryRun`, явно подтвердив одноразовые пустые targets:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Invoke-FamilyAiRecovery.ps1 TotalLoss `
  -GatewayHost 192.168.31.180 `
  -DatabaseHost 192.168.31.181 `
  -SpeechHost 192.168.31.182 `
  -SshUser root `
  -IdentityFile "$env:USERPROFILE\.ssh\family-ai-deploy" `
  -BundlePath .dr\family-ai-dr-kit.dpapi `
  -Commit origin/main `
  -ConfirmTargetsAreDisposable
```

Orchestrator:

1. устанавливает системные зависимости;
2. создаёт `familyai-deploy`;
3. разворачивает новую PostgreSQL и восстанавливает имя роли/БД и пароль из
   Database URL DR-kit;
4. переписывает Database/Speech/monitoring адреса в восстановленной конфигурации;
5. подготавливает Gateway и Speech из указанного commit;
6. выполняет `alembic upgrade head` на пустой БД;
7. сначала запускает Speech, потом Gateway/Admin;
8. устанавливает Speech admin-control и root-owned Gateway restart path unit;
9. проверяет три сервиса и Alembic;
10. включает nftables для DB/Speech;
11. повторно проверяет связность от Gateway;
12. удаляет открытые временные секреты и пишет безопасный отчёт в `.dr/reports`.

Ожидаемый результат: агенты и стартовая конфигурация есть, старая история и
родительская память отсутствуют.

## Сценарий B — сервисы потеряны, старая PostgreSQL доступна

Источник должен:

- отвечать по SSH;
- иметь активный PostgreSQL;
- позволять `sudo -u postgres`;
- содержать БД `family_ai`;
- не принимать новые записи во время snapshot.

### Предварительная проверка

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Invoke-FamilyAiRecovery.ps1 DatabaseSalvage `
  -GatewayHost 192.168.31.180 `
  -DatabaseHost 192.168.31.181 `
  -SpeechHost 192.168.31.182 `
  -SourceDatabaseHost 192.168.31.163 `
  -SshUser root `
  -SourceSshUser familyai-deploy `
  -IdentityFile "$env:USERPROFILE\.ssh\family-ai-deploy" `
  -BundlePath .dr\family-ai-dr-kit.dpapi `
  -Commit origin/main `
  -DryRun
```

Если `SourceDatabaseHost` не указан, адрес берётся из Database URL DR-kit.

### Восстановление

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\dr\Invoke-FamilyAiRecovery.ps1 DatabaseSalvage `
  -GatewayHost 192.168.31.180 `
  -DatabaseHost 192.168.31.181 `
  -SpeechHost 192.168.31.182 `
  -SourceDatabaseHost 192.168.31.163 `
  -SshUser root `
  -SourceSshUser familyai-deploy `
  -IdentityFile "$env:USERPROFILE\.ssh\family-ai-deploy" `
  -BundlePath .dr\family-ai-dr-kit.dpapi `
  -Commit origin/main `
  -ConfirmTargetsAreDisposable
```

До изменения новых VM orchestrator:

1. строит manifest исходной БД: Alembic version и точные количества строк каждой
   public-таблицы;
2. создаёт `pg_dump --format=custom --serializable-deferrable`;
3. повторно строит manifest;
4. прекращает работу, если manifests различаются;
5. передаёт dump по SSH/SCP и проверяет SHA-256.

На новой DB VM он:

1. создаёт только пустую роль и БД;
2. отказывается работать, если public schema уже содержит таблицы;
3. проверяет структуру dump через `pg_restore --list`;
4. восстанавливает dump одной транзакцией с `--exit-on-error`;
5. сравнивает source и target manifests;
6. только после точного совпадения применяет новые Alembic migrations.

Исходная БД не изменяется и не удаляется.

## Проверка после восстановления

### Автоматическая

Успешная команда уже проверила:

- `family-ai-gateway.service`;
- `family-ai-admin.service`;
- `family-ai-speech.service`;
- Gateway `/healthz`;
- Admin `/api/healthz`;
- Speech `/healthz`;
- наличие Alembic version;
- доступ Gateway к DB:5432 и Speech:8010;
- итоговый commit.

Статус можно повторить:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 status gateway `
  -HostName 192.168.31.180 -SshUser root

powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\deploy\release.ps1 status speech `
  -HostName 192.168.31.182 -SshUser root
```

### Ручная функциональная

1. Открыть `http://NEW_GATEWAY:8000` и выбрать каждого агента.
2. Отправить один текстовый вопрос.
3. Проверить голосовой вопрос и повторное воспроизведение ответа.
4. Открыть `http://NEW_GATEWAY:8001`.
5. Проверить вкладки «Инфраструктура», «История», «Память», «Агенты».
6. В salvage-сценарии найти старый диалог и одну запись долгосрочной памяти.
7. В Android-клиенте вручную указать новый адрес Gateway.
8. Если используется локальный DNS `family-ai.home.arpa`, изменить A-запись и
   только после проверки уменьшить/вернуть TTL.

### Проверка Git/production

```powershell
$expected = git rev-parse origin/main
$actual = (
  powershell -NoProfile -ExecutionPolicy Bypass -File `
    .\scripts\deploy\release.ps1 status gateway `
    -HostName 192.168.31.180 -SshUser root |
  Select-Object -First 1
).Split()[1]

"expected=$expected"
"actual=$actual"
```

Значения должны совпасть.

## Если восстановление оборвалось

- Не пытаться вручную «дочинить» частично восстановленную DB.
- Сохранить `.dr/reports`, вывод консоли и состояние старой БД.
- Удалить и заново создать три target VM либо хотя бы все изменённые target VM.
- Повторить `DryRun`.
- Запустить сценарий сначала.

Target guard специально не позволяет повторно запустить полный DR поверх
частично активированной системы. Это защита от случайного уничтожения данных.

При ошибке snapshot старая БД остаётся рабочей. При ошибке restore
`--single-transaction` не оставляет частично восстановленную схему, однако target
всё равно рекомендуется пересоздать для чистого повторения.

## Работа с временными и чувствительными файлами

- dump на source/target имеет режим `0600`;
- транспорт — SSH/SCP;
- пароль DB передаётся отдельным временным файлом и удаляется trap;
- локальные открытые env/dump находятся только в `.dr/work/<recovery-id>`;
- блок `finally` удаляет локальные и remote временные файлы;
- `.dr/`, `*.dump` и `*.backup` исключены из Git;
- отчёт содержит только адреса, commit, сценарий и времена.

Если процесс Windows был аварийно завершён так, что `finally` не исполнился:

```powershell
Get-ChildItem .dr\work
```

После проверки пути удалить только соответствующий каталог recovery вручную.

## Регулярная готовность

- обновлять DR-kit после каждого изменения секретов;
- хранить дату последнего экспорта;
- проводить clean-room fire drill не реже одного раза в год;
- обязательно повторять fire drill после изменения PostgreSQL major version,
  bootstrap Speech или release-controller;
- измерять фактический RTO отдельно для Gateway/DB и Speech;
- не считать этот runbook заменой backup: без доступной старой БД сценарий
  `TotalLoss` не возвращает пользовательские данные.

Связанные документы:

- [ADR 026](adr/026-clean-room-disaster-recovery.md);
- [план DR](../plans/DisasterRecoveryPlan.md);
- [обычное развёртывание](deployment.md).
