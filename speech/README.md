# Family AI Speech Service

Локальный OpenAI-совместимый сервис распознавания и синтеза русской речи для
Family AI Mentor.

- STT: `faster-whisper` с VAD, beam search и словарём доменных терминов;
- TTS: Silero `v5_2_ru` с пятью русскими голосами;
- последовательная очередь inference для маломощных CPU;
- runtime-метрики без текста и аудио;
- временная калибровка STT с автоматическим удалением записей;
- bearer-аутентификация всех рабочих и технических endpoints.

Исходное и синтезированное аудио сервис не сохраняет. Исключение — явно
запущенная родителем калибровка: её временные файлы удаляются после анализа,
ошибки, отмены или истечения срока.

## Запуск

Требуются Python 3.13, `uv` и CPU с поддержкой зависимостей PyTorch.

```bash
cd speech
cp .env.example .env
uv sync --frozen
uv run uvicorn family_ai_speech.main:app --host 127.0.0.1 --port 8010
```

При первом запуске модели будут загружены в каталог, заданный
`FAMILY_AI_SPEECH_MODEL_CACHE_DIR`. Для сетевого развёртывания замените
`FAMILY_AI_SPEECH_API_KEY`, ограничьте доступ firewall и запускайте сервис от
непривилегированного пользователя.

Проверка готовности не требует токена:

```bash
curl http://127.0.0.1:8010/healthz
```

## API

Сервис реализует используемую проектом часть OpenAI Audio API:

- `POST /v1/audio/transcriptions` — STT;
- `POST /v1/audio/speech` — TTS;
- `GET /internal/metrics` — очередь и обезличенные runtime-метрики;
- management endpoints — калибровка и управляемые runtime-настройки.

Кроме `/healthz`, endpoints требуют заголовок:

```text
Authorization: Bearer <FAMILY_AI_SPEECH_API_KEY>
```

## Подключение Gateway

В корневом `.env` укажите:

```dotenv
FAMILY_AI_SPEECH_BASE_URL=http://127.0.0.1:8010/v1
FAMILY_AI_SPEECH_API_KEY=<тот же случайный токен>
FAMILY_AI_STT_MODEL=base
FAMILY_AI_TTS_MODEL=silero-v5_2-ru
FAMILY_AI_TTS_VOICE=xenia
FAMILY_AI_TTS_RESPONSE_FORMAT=wav
```

Gateway может использовать отдельные STT/TTS URLs и ключи, поэтому локальный
сервис можно заменить независимо от LLM и остальных компонентов.

## Проверки

```bash
cd speech
uv run ruff check .
uv run pytest
```

Калибровка детской речи и применение VAD/beam описаны в
[`docs/stt-calibration-guide.md`](../docs/stt-calibration-guide.md), production
развёртывание — в [`docs/deployment.md`](../docs/deployment.md).
