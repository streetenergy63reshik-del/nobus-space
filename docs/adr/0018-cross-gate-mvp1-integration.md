# ADR 0018 — Интеграция Gate 0–8 MVP-1

**Статус ADR:** ACCEPTED

**Статус реализации:** TARGET

**Дата:** 28 июля 2026 года

## Контекст

После принятия ADR 0017 каждый Gate MVP-1 прошёл отдельное исследование
существующего кода, готовых решений, официальных API, GitHub-проектов и
эксплуатационных рисков. Исследования подтвердили общий hybrid design, но
выявили несколько противоречий, которые нельзя оставлять на усмотрение
отдельного implementation-чата.

Критические расхождения:

- local `DocumentRef` как относительный путь против opaque device handle;
- обещание revision-bound updates для всех Google backends против фактических
  precondition API;
- effect state как смесь protocol phase и provider outcome;
- раздельное создание durable effect и queue job;
- локальный supervisor против глобального poller fencing;
- «production только PostgreSQL» против single-writer MVP и готовых SQLite
  примитивов;
- единый алгоритм подписей против разных build/device trust boundary.

## Решение

### 1. Существующий Core адаптируется

Не создаётся новый бот, общий agent framework или второй effect engine.
Существующие ingress, queue/outbox, effects и adapters расширяются по одному
контракту на responsibility.

### 2. Atomic admission

Effect-bearing request, durable effect binding и queue job создаются одной
SQLite transaction. Outcome/evidence и финальный owner-bound outbox также
фиксируются атомарно.

### 3. Lifecycle отдельно от outcome

Protocol lifecycle использует фазы admission/execution/reconciliation/delivery.
Provider outcome хранится отдельно:

`NONE | APPLIED | REJECTED | CONFLICTED | CANCELLED`.

`PROVIDER_UNKNOWN` блокирует mutation retry. `DELIVERY_UNKNOWN` разрешает
только delivery recovery и не повторяет provider effect.

### 4. Local identity является opaque

За пределами Windows Bridge локальный source/destination представлен только
Bridge-minted opaque handle. Relative/absolute path остаётся внутри Bridge.

### 5. Google preconditions не симулируются

- Google Docs update использует `requiredRevisionId`;
- Calendar update использует provider ID/ETag precondition;
- Sheets existing in-place update и Drive blob overwrite не заявляются как
  strict CAS без отдельного доказанного provider contract;
- когда strict precondition отсутствует, MVP создаёт новую version/copy либо
  fail closed.

### 6. Google production path

Production authority принадлежит Core и официальным Workspace REST adapters.
Workspace MCP/CLI допускается только как read-only canary/reference. Gemini
работает через bounded `google-genai`/Vertex gateway и не получает OAuth/effect
authority.

### 7. SQLite является MVP-default

Для одного Core writer сохраняется SQLite. Все фактические runtime DB входят в
coordinated snapshot/restore manifest. PostgreSQL вводится только по
измеримому trigger; SQLite на network filesystem запрещён.

### 8. Один poller обеспечивается fencing

Supervisor дополняется единственной custody Telegram token и durable generation
lease. Во время acceptance automatic restart выключен.

### 9. Раздельные key profiles

Registry/release signatures и Windows device identity не обязаны использовать
один ключ/алгоритм. Device identity применяет non-exportable CNG P-256 и mTLS;
build artifacts используют отдельный offline signature profile. DPAPI/private
keys не копируются между identities.

### 10. Один аналитический и presentation source

Факты и расчёты завершаются в Gate 6. Gate 7 получает один `AnalysisResult`,
создаёт один `ArtifactDocument`/`ValueToken` set и не пересчитывает значения.
Telegram/HTML/JPEG/PDF используют одну semantic presentation.

## Последствия

Положительные:

- закрываются orphan и duplicate windows;
- исчезает ложный rollback внешних эффектов;
- local filesystem authority не покидает Windows boundary;
- Google limitations становятся явным продуктовым поведением;
- уменьшается число framework и параллельных моделей;
- implementation можно вести последовательно по Gate.

Ограничения:

- update существующей Google Sheet/Drive blob в MVP может создать новую версию
  вместо in-place overwrite;
- local функции недоступны при offline Bridge;
- PostgreSQL/HA откладываются до измеримого спроса;
- TARGET design не доказывает CURRENT runtime.

## Проверка

ADR считается реализованным только после:

- atomicity/crash tests effect+job и outcome+outbox;
- provider-vs-delivery unknown transition tests;
- opaque handle/path escape/reparse/hard-link tests;
- Docs/Calendar precondition и Sheets/Drive fail-closed contract tests;
- global poller fencing tests;
- coordinated SQLite restore drill;
- cross-format semantic equality;
- принятого Gate 0–8 handoff и 72-hour pilot.

Полная связанная архитектура:
[`docs/13`](../13-Интегрированная-архитектура-MVP-1.md).
