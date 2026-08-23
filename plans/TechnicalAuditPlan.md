# Технический аудит и план рефакторинга

Дата baseline: 23 августа 2026 года. Проверенный commit до начала изменений:
`f601bba`.

## Цель

Снизить стоимость дальнейшего развития Family AI без переписывания работающей
системы. Сохраняются публичные REST-контракты, миграционная история, локальный
домашний контур, детские privacy/safety-границы и независимость Gateway, Speech,
Admin UI и Android-клиента.

## Что проверено

- структура 456 tracked-файлов и чистота репозитория;
- зависимости Gateway, Speech и Flutter;
- Ruff, Python compileall и поиск цикломатически сложных функций;
- 225 тестов Gateway, 23 теста Speech и 38 Flutter-тестов;
- `flutter analyze`, 12 visual baseline Admin UI и 92 Markdown-файла;
- единственность Alembic head и сборка Gateway/Speech release archive;
- ссылки между provider-контрактами, DI, сервисами, моделями и роутерами;
- конфигурация, release/deploy/DR-скрипты и эксплуатационная документация;
- поиск забытых compatibility-слоёв, TODO/FIXME и подозрительных tracked-файлов.

Baseline полностью зелёный. Найденные проблемы относятся к воспроизводимости,
архитектурному долгу и отсутствующим защитным проверкам, а не к текущей аварии
production.

## Подтверждённые находки

### P0 — немедленная остановка эксплуатации

Не найдено. Секретов, дампов, APK, локальных БД и крупных случайных артефактов
среди tracked-файлов нет.

### P1 — исправить до следующего функционального этапа

- [x] Корневой `uv.lock` расходился с `pyproject.toml`: `httpx` был перенесён в
  runtime dependencies, но lock сохранял старую группу.
- [x] Release gate не проверял оба `uv.lock`, поэтому рассинхронизация проходила
  все тесты и попадала в release archive.
- [x] Release gate заявлял требование чистого дерева, но не проверял его: тесты
  могли выполняться над working tree, а archive строился из другого состояния
  `HEAD`. Добавлен отдельный fail-closed этап `working_tree_clean`.
- [x] Gateway без `FAMILY_AI_DATABASE_URL` молча создавал `family_ai.db`, хотя
  Alembic-миграции используют PostgreSQL UUID, casts и server defaults и не
  поддерживают чистый SQLite upgrade.
- [x] Удалён неиспользуемый composite `AIProvider`/`OpenAIProvider`, оставленный
  в ADR 025 на переходный период. Production и тесты уже используют узкие
  `ChatProvider`, `SpeechRecognitionProvider` и `SpeechSynthesisProvider`.
- [x] README сообщал лимит Vision 3 MiB вместо фактических 10 MiB, а
  `.env.example` оставлял старый STT timeout 35 секунд вместо 60.
- [x] Тесты Gateway строят схему через `Base.metadata.create_all()`, поэтому
  добавлен отдельный disposable PostgreSQL migration-test без доступа к
  production. Он принимает только URL системной БД `postgres`/`template1`,
  создаёт случайную БД, проверяет `upgrade → downgrade → upgrade` и удаляет её.
- [x] `ConversationService.generate_ai_response()` объединял загрузку контекста,
  input/output safety, prompt assembly, provider call, persistence, activity и
  media. Ход разделён на типизированные проверяемые этапы с сохранением одного
  application orchestrator и прежнего порядка побочных эффектов.
- [x] Voice и multimodal voice содержали параллельные реализации STT/TTS,
  таймаутов, telemetry и streaming events. Вынести общий голосовой pipeline;
  общий `VoicePipeline` теперь владеет речевыми стадиями, а Vision остался
  отдельной capability мультимодального orchestrator.

### P2 — следующий цикл поддерживаемости

- [x] Разделить `speech.create_app()` на application factory и отдельные роутеры
  health, speech, runtime settings и calibration. Сейчас функция имеет
  цикломатическую сложность 42 и 106 statements. Factory теперь отвечает только
  за lifecycle и wiring; audio/metrics и management API вынесены в отдельные
  модули с типизированным HTTP context.
- [x] Разнести оставшиеся auth/history/settings endpoints из
  `gateway/admin/main.py` по роутерам. `main.py` должен только собирать Admin app.
- [x] Разделить `gateway/admin/static/js/app.js` и `gateway/static/app.js` по
  feature-модулям. Visual suite ловит layout-регрессии, но отдельной статической
  JS-проверки сейчас нет, а Node.js в локальном toolchain не установлен.
- [x] Разбить мобильные `gateway_client.dart`, `chat_screen.dart` и
  `voice_chat_controller.dart` на transport, serialization и use-case слои без
  изменения экранных контрактов.
- [x] Убрать риск дрейфа дублированных character assets между Gateway и Flutter:
  определить канонический каталог и добавить проверяемую синхронизацию при
  сборке. Само дублирование в двух release archive допустимо.
- [x] Удалить один из идентичных внутренних prompt-файлов
  `.agents/family-ai-promt.prompt.md` и `.github/prompts/family-ai-promt.prompt.md`
  после выбора поддерживаемого редактором расположения.
- [x] Устранить `StarletteDeprecationWarning`: Speech TestClient переведён на
  рекомендуемую Starlette dev-зависимость `httpx2`; runtime-зависимости сервиса
  не изменились.
- [x] Добавить воспроизводимый dependency audit с поддержкой PyTorch CPU wheel.
  Точный lock экспортируется без повторного разрешения, локальный суффикс
  `+cpu` нормализуется только для advisory lookup. Проверены 37 Gateway и 48
  Speech packages: известных уязвимостей на 23 августа 2026 года не найдено.

### P3 — осознанно оставить в backlog

- внешний CI: локальный release gate соответствует домашнему приватному контуру;
- DR-репетиция на трёх новых VM и недельный детский тест: ждут ресурсов кластера
  и исправного телефона;
- переход на новые LLM/STT/TTS или новое железо: только после метрик и реальной
  нагрузки, не как часть рефакторинга.

## Порядок выполнения

1. **Baseline hygiene** — lock-файлы, явная БД, документация, dead provider.
2. **Conversation orchestration** — выделение preparation, prompt, safety и
   completion этапов с characterization tests.
3. **Voice pipeline** — единая реализация timeout/admission/metrics/streaming.
4. **Service composition** — тонкие `main.py` для Speech и Admin.
5. **Client modularity** — Admin JavaScript и Flutter transport/use cases.
6. **Schema and supply-chain guards** — disposable PostgreSQL migration-test и
   корректный dependency audit.
7. **Полный release gate** — тесты, visual baselines, Markdown, archives; только
   после зелёного gate допускаются commit, push и deploy.

## Результат рефакторинга

- Admin `main.py` стал composition root пяти feature routers;
- Admin bootstrap уменьшен до wiring, крупные settings/agents/studio/calibration
  сценарии изолированы и проходят прежние visual baselines;
- child web UI использует нативные ES modules без добавления Node.js toolchain;
- Flutter публичные контракты сохранены, transport/widgets/voice execution
  разделены библиотечными частями;
- release gate получил asset drift guard, locked dependency audit и безопасный
  disposable PostgreSQL harness;
- единственный редакторский prompt хранится в `.github/prompts`, а архитектурное
  решение зафиксировано в ADR 044.

## Definition of Done

- публичные API и UX не изменены без отдельного решения;
- child safety policy и privacy boundaries покрыты прежними и новыми тестами;
- нет дублирующей business logic между voice и multimodal voice;
- application factories только собирают зависимости и роутеры;
- чистая PostgreSQL-схема проверяется реальной цепочкой Alembic;
- оба lock-файла проверяются до тестов;
- документация и этот план отражают фактический статус;
- единый локальный release gate полностью зелёный.
