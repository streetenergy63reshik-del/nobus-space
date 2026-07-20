# Gate 2 — Telegram ingress and voice preview

**Статус:** ACCEPTED — L1/L2/L3 PASS

**Дата:** 2026-07-20

**Commit main:** `5df4ccd feat: add hardened Telegram and voice previews`

## Scope

Gate 2 добавляет локальные границы нормализации Telegram update и безопасного preview голосовой команды. Компоненты не подключаются к Telegram API, не загружают файлы по сети, не используют bot token и не создают TaskContract. Их выход остаётся недоверенным входом для будущего authenticated boundary Gate 4.

## Telegram boundary

- принимает только словарь ограниченной формы и различает text, voice и callback;
- проверяет точную пару разрешённых `user_id`/`chat_id`, не декартово произведение списков;
- атомарно поглощает повторный `update_id` через injected claim store;
- использует opaque callback token, связанный с точной парой actor/chat, и одноразовый atomic claim;
- отклоняет bool/float/coercion для Telegram integer identifiers;
- нормализует текст и ограничивает его длину;
- пропускает только allowlisted voice metadata, не сохраняя произвольный payload;
- возвращает closed `IngressStatus` и безопасные reason codes.

In-memory stores пригодны только для тестов и одного процесса. Persistence и межпроцессная атомарность остаются Gate 4/5.

## Voice boundary

- публично принимает только уже загруженные и ограниченные `bytes`;
- вычисляет SHA-256 и размер, но не возвращает сырые audio bytes;
- создаёт уникальный temp file только внутри injected private root;
- передаёт provider ранний предел длины transcript;
- повторно валидирует provider result на service boundary;
- очищает temp file после успеха и ошибки; при cancellation выполняет bounded drain, а затем откладывает cleanup до фактической остановки provider, не удаляя активный файл раньше времени;
- не раскрывает provider exception, audio, temp path или exception chain;
- сохраняет семантику `CancelledError` и ограничивает ожидание provider cleanup.

Stream API намеренно отсутствует. Независимый L3 воспроизвёл, что отмена `asyncio.to_thread(stream.read)` не останавливает синхронное чтение и позволяет исчерпать thread pool. Для MVP transport обязан сначала получить ограниченные bytes на управляемой сетевой границе. Возврат stream API потребует отдельного кооперативно отменяемого async reader.

`FasterWhisperTranscriber` загружает optional provider лениво и выполняет блокирующую работу в worker thread. Пакет `faster-whisper` не установлен и не добавлен в зависимости этим Gate.

## Проверка

- финальный target `tests/test_telegram_gateway.py tests/test_voice_service.py`: `100 passed`;
- полный объединённый suite main: `252 passed`;
- независимый replay target/full: PASS;
- adversarial callback type/binding/replay, stream-cancellation/resource exhaustion, provider mutation, temp cleanup и exception leakage: PASS после rework;
- `git diff --cached --check`, `compileall`, `pip check`: PASS;
- real Telegram, сеть, credentials, live transcription и внешние действия не использовались.

Единственное ожидаемое предупреждение — `StarletteDeprecationWarning` существующего FastAPI TestClient. Дополнительное cache warning возможно только в ограниченной среде Codex и не относится к runtime-коду.

## Ограничения следующего Gate

- actor/chat allowlist ещё не является authenticated Telegram identity boundary;
- callback token не имеет persistent TTL/nonce/request digest;
- voice bytes ещё не приходят из управляемого Telegram downloader;
- ingress не создаёт TrustedIngressEnvelope и TaskContract;
- Telegram/voice, Core и fake-only worker ещё не образуют вертикальный E2E;
- отправка ответа в Telegram отсутствует.
