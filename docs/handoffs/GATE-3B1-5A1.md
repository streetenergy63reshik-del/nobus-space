# Gate 3B.1 / 5A.1 — PRE-LIVE process и Telegram boundaries

**Статус:** ACCEPTED — L1/L2/L3 PASS в PRE-LIVE scope
**Дата:** 2026-07-22
**Implementation commit:** `cde0bd5 feat: add pre-live process and Telegram boundaries`
**L4:** не требовался: сеть, credentials, реальный Codex process и внешняя отправка не запускались

## Принятый scope

- asyncio process adapter проверяет exact executable, workspace-contained cwd, два фиксированных argv-профиля и закрытый environment;
- stdin/stdout/stderr используют pipes без shell; stdout/stderr дочитываются до EOF, а в памяти остаётся не более `limit + 1` байт;
- отменённый или запоздало созданный child остаётся под retained cleanup-task до `kill + wait`;
- POSIX использует отдельную process group; Windows по умолчанию fail-closed и требует injected launcher с независимо доказанным Job Object guard;
- Telegram Bot API client владеет injected `httpx` transport, отключает ambient proxy/auth/cookies/redirects и явно запрашивает `Accept-Encoding: identity`;
- методы `getUpdates`, `getFile`, download, `sendMessage` и `answerCallbackQuery` имеют строгие схемы, timeout/size limits и безопасные public errors без token/raw exception chain;
- polling требует synchronous local durable checkpoint contract с exact `PollingLease`: owner UUID, generation UUID и aware TTL не более 300 секунд;
- один consumer lease и local single-flight исключают параллельный batch; offset сохраняется после каждого ACK до следующего update;
- `update_id` фиксируется до handler, lease проверяется непосредственно перед handler и до CAS advance, handler ограничен оставшимся TTL;
- status sender принимает только повторно валидированный `LEASED` outbox record с точной tenant/destination binding;
- tenant normalization collisions, unsafe Telegram file paths и неоднозначные numeric значения отклоняются.

## Проверки

```text
Target PRE-LIVE tests:         34 passed
Full repository:             509 passed, 1 warning
compileall:                  PASS
pip check:                   No broken requirements found.
git diff --cached --check:   PASS
token-shaped literal scan:   NONE
Independent L2/L3:           ACCEPT; P0=0, P1=0
```

Независимое adversarial-review потребовало три rework-итерации. Воспроизведены и закрыты: orphan после cancellation, pipe deadlock после overflow, неполное Windows tree cleanup, exception-chain leakage, mutable update ID, недолговечный/ABA lease, пропуск durable checkpoint, cancellation при release, compression mismatch, tenant collision и unsafe file path.

## Что намеренно не объявлено готовым

- injected Windows callables не являются доказательством Job Object isolation;
- `PollingCheckpointStore` пока Protocol; concrete SQLite lease/checkpoint store и restart/reclaim reproduction отсутствуют;
- реальный bot token, сеть Telegram, bot identity check и live send/polling не использовались;
- production handler обязан быть cancellation-cooperative и идемпотентным; подавляющий cancellation handler не допускается;
- injected clock остаётся trusted infrastructure dependency;
- deployment, monitoring, restore drill, remote и push отсутствуют.

## Следующая граница и L4

До Gate 3B.2 / 5A.2 требуется отдельное явное L4 на конкретный live-сценарий. После него нужно реализовать и независимо воспроизвести:

1. Windows Job Object-aware launcher и реальный allowlisted Codex process;
2. concrete SQLite polling lease/checkpoint с expiry reclamation и exact-generation CAS после restart;
3. secret-store injection bot token, `getMe` identity verification и allowlisted tenant/user/chat mapping;
4. один ограниченный live polling consumer, безопасную outbox delivery и kill switch;
5. отсутствие token/audio/raw payload в Git, SQLite, logs и exception chain.

До выполнения этих пунктов Gate 3B.2/5A.2 остаются **BLOCKED UNTIL L4**, а рабочий Telegram E2E не считается запущенным.
