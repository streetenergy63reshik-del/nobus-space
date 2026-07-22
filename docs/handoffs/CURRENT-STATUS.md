# Nobus Space MVP — текущий статус разработки

**Снимок:** 2026-07-22, Europe/Moscow

**Канонический репозиторий:** `nobus-orchestrator-dev`

**Назначение:** единственная обновляемая точка передачи фактического состояния между итерациями

## Короткий итог

Каноническая документация, Core contracts/policy, Telegram ingress, voice preview/confirmation, fake-only Codex CLI boundary, trusted ingress, SQLite checkpoints/events/outbox и локальный durable text/voice E2E приняты независимыми L1/L2/L3 и зафиксированы в `main`.

Gate 4F принят в `a56bdf3`: Task transitions атомарно связаны с WorkerEvents/outbox, restart не повторяет worker вслепую, а delivery выполняется только через injected fake boundary.

PRE-LIVE Gate 3B.1/5A.1 принят в `cde0bd5`: добавлены cancellation-safe process adapter и ограниченный Telegram Bot API/polling/status boundary с generation-bound checkpoint contract.

PRE-LIVE substrate Gate 3B.2a/5A.2a принят в `1d4029f`: добавлены concrete SQLite polling lease/checkpoint с restart CAS и gated Windows Job Object launcher.

Ограниченный Windows Job live probe Gate 3B.2b принят в `6b0f923`: два успешных запуска, включая независимое воспроизведение, подтвердили stdio, Job inheritance, normal kill-on-close, explicit tree kill и cancellation cleanup без orphan-процессов. Реальный Codex при этом не запускался.

Live Telegram owner control plane принят в `b17f650`, `96fa634` и `17ac081`: bot identity проверена через Telegram API, один owner binding хранится только в Git-игнорируемой локальной конфигурации, а `/start`, `/status` и `/help` принимаются и получают ограниченные ответы в том же связанном чате. Serve-runner использует cancellation-safe backoff `1/2/4/8/16/30` секунд.

Gate 5A.3 принят в `70941d8`: `/task` атомарно создаёт content-free durable `PENDING`, выдаёт owner-bound one-shot preview и только после `/confirm` запускает локальный fake-worker с L1/L2/L3 и terminal status outbox; `/cancel`, expiry, retry, restart и malformed token fail-closed. Raw instruction/token не попадают в SQLite. Live Codex, voice network path и filesystem/network effects fake-worker не использует. Обновлённый serve-runner активирован в текущей desktop-сессии 2026-07-22 18:37 Europe/Moscow. В 18:49 owner live `/task` → `/confirm` → terminal `completed` воспроизведён; SQLite projection имеет revision 7, outbox `acked`, attempt count 1.

Компоненты образуют рабочий live Telegram status-control и confirmed fake-task E2E: owner network `/task` → `/confirm` → terminal `completed` воспроизведён. Live Codex worker, voice download/transcription, OS service/autostart, deployment, monitoring и restore drill не подключены.

## Gate status

| Gate | Реализация | Воспроизводимая проверка | Статус |
|---|---|---|---|
| Gate 0 — baseline | `ea5bd51` | исторический baseline: 28 tests | **ACCEPTED** |
| Documentation baseline | `364e6ab`, docs 01–10, ADR 0001–0008 | link/structure + независимые L2/L3 | **ACCEPTED** |
| Gate 1 — Core contracts/policy | `7b92978` | 91 target; 119 full на момент Gate; adversarial bindings/replay/state | **ACCEPTED** |
| Gate 2 — Telegram/voice | `5df4ccd` | 100 target; 252 full main; independent cancellation/replay/leakage review | **ACCEPTED** |
| Gate 3A — fake-only Codex CLI boundary | `294047c` | 33 target; 152 full на момент Gate; timeout/cancellation/protocol review | **ACCEPTED** |
| Gate 3B.1 — PRE-LIVE process adapter | `cde0bd5` | 10 target process tests; cancellation/overflow/tree-guard review | **ACCEPTED PRE-LIVE** |
| Gate 3B.2a — Windows Job substrate | `1d4029f` | 7 fake WinAPI tests; startup/ABA/cancellation/handle review | **ACCEPTED PRE-LIVE** |
| Gate 3B.2b — Windows Job live probe | `6b0f923` | 17 target; 534 full; 2 live runs; 1 independent reproduction; orphan/temp audit | **ACCEPTED; REAL CODEX EXCLUDED** |
| Gate 4A — local fake vertical E2E | `dfc2e66` | 10 target; 262 full; independent result/evidence/replay/leakage review | **ACCEPTED** |
| Gate 4B — trusted ingress envelope | `2afd880` | 176 target; 354 full; 20 independent regression | **ACCEPTED** |
| Gate 4C — durable SQLite checkpoints | `d775699` | 61 target; 365 full; restart/tamper/policy recovery review | **ACCEPTED; WIRED IN 4F** |
| Gate 4D — actor-bound voice confirmation | `438233c` | 46 target; 192 relevant; 460 full; independent replay/race/tenant review | **ACCEPTED; IN-MEMORY; WIRED IN 4F** |
| Gate 4E — durable status outbox | `afb6859` | 110 target; 414 full; independent replay/time/receipt review | **ACCEPTED; WIRED IN 4F** |
| Gate 4F — durable local runtime E2E | `a56bdf3` | 14 target; 135 relevant; 475 full; independent crash/replay/tenant/delivery review | **ACCEPTED; LOCAL FAKE** |
| Gate 5A.1 — PRE-LIVE Telegram API/polling boundary | `cde0bd5` | 24 target Telegram tests; lease/offset/leakage/limit review | **ACCEPTED PRE-LIVE** |
| Gate 5A.2a — durable polling checkpoint | `1d4029f` | 18 SQLite tests; restart/CAS/expiry/clock/tamper review | **ACCEPTED PRE-LIVE; LIVE ACTIVATED IN 5A.2b** |
| Gate 5A.2b — live owner control plane | `b17f650`, `96fa634`, `17ac081` | verified identity/binding; live poll/send; 11 retry tests; 609 full; independent retry review | **ACCEPTED LIVE TEXT CONTROL** |
| Gate 5A.3 — confirmed Telegram fake tasks | `70941d8` | 36 target; 630 full; independent review; owner live terminal `completed`; SQLite/outbox ACK evidence | **ACCEPTED LIVE FAKE E2E; LIVE CODEX EXCLUDED** |
| Gate 5B — production readiness | только TARGET runbook | нет deploy/monitoring/restore evidence | **BLOCKED BY DESIGN** |

## Реализованные границы

### Core

- tenant/task/contract/result-bound модели;
- строгая state machine, atomic update и terminal audit lock;
- scoped idempotency, WorkerEvent replay и sequence checks;
- последовательные L1/L2/L3 с разными identities;
- L4 record для HIGH/CRITICAL и отдельный `EXECUTING` для внешнего эффекта;
- безопасные public error codes вместо текста внутренних исключений.

StateManager и PolicyStore остаются process-memory, но recovery-safe Task projection, ingress claims, WorkerEvents и status outbox сохраняются в SQLite. Worker/verifier identities и completion evidence пока являются утверждениями локальной server configuration, а не результатом отдельной authenticated execution/verification boundary; Telegram actor identity проверяется live owner boundary.

### Telegram и voice

- Telegram update нормализуется без сети и SDK;
- PRE-LIVE Bot API client владеет injected transport, запрещает ambient HTTP authority/redirect/compression и ограничивает response/download;
- polling использует concrete SQLite generation-bound lease/checkpoint: store-owned clock, expiry reclaim, exact-generation CAS, restart resume и parallel-consumer exclusion;
- accepted update получает self-validating `TrustedIngressEnvelope` с server-owned actor/time и точной payload binding;
- exact actor/chat binding, atomic update replay claim и opaque callback token claim;
- voice preview подтверждается единожды тем же tenant/actor/role/auth context/user/chat; callback capability имеет TTL, хранится только в виде digest и после success заменяется минимальным replay tombstone;
- callback/replay/confirmation stores пока in-memory и после restart безопасно теряют незавершённые challenge;
- text `/task` подтверждение связано с exact tenant/actor/role/auth context/user/chat, делит bounded capacity между active challenge и tombstone и не сохраняет raw instruction/token в SQLite;
- voice preview принимает только ограниченные bytes, очищает temp file после success/error, а при cancellation ждёт bounded drain и откладывает cleanup до фактической остановки provider;
- stream API удалён после независимого L3 resource-exhaustion finding;
- optional `faster-whisper` не установлен и не является текущей обязательной зависимостью.

### Worker

- Codex CLI adapter остаётся fake-first, но PRE-LIVE asyncio spawner проверяет executable/cwd/argv/env/pipes, bounded drain и retained cancellation cleanup;
- POSIX process-group cleanup реализован; Windows launcher создаёт kill-on-close Job Object, назначает gated helper до target start и удерживает gate до завершения ownership;
- Windows Job inheritance, stdio, normal kill-on-close, explicit tree kill и adapter cancellation независимо воспроизведены на локальном probe-child; реальный `codex` и его OS sandbox не запускались;
- fake worker связан с Core attempt и атомарными `STARTED`/`RESULT_READY`/`FAILED` WorkerEvents; live process lease отсутствует.

## Git-снимок

### Main worktree

- Ветка: `main`.
- Последний принятый implementation commit: `70941d8 feat: add confirmed Telegram fake tasks`.
- Предыдущие live Telegram commits: `17ac081`, `96fa634`, `b17f650`.
- Предыдущие принятые commits: `6b0f923`, `1d4029f`, `cde0bd5`, `a56bdf3`, `438233c`, `afb6859`, `d775699`, `2afd880`, `dfc2e66`, `5df4ccd`, `294047c`, `7b92978`, `364e6ab`, `ea5bd51`.
- Remote отсутствует; push не выполнялся.
- Канонические docs синхронизированы отдельным локальным docs commit после независимой проверки этого снимка.
- `.nobus-quality/cases.ndjson` содержит append-only обезличенные case records принятых и отклонённых итераций.

### Kimi worktree

- Ветка: `agent/kimi-telegram`.
- HEAD: `d0f0765 fix: harden Telegram and voice preview boundaries`.
- Рабочее дерево чистое.
- Исходные commits: `8478a77`, `227076d`; rework: `d0f0765`.
- Merge/rebase/push/remote не выполнялись; итог перенесён в `main` одним проверенным commit `5df4ccd`.

## Документация и уборка

- Единственный нормативный комплект находится в `nobus-orchestrator-dev/docs`.
- Временная директория черновой LLM-платформы удалена после создания локальной резервной копии.
- Устаревшие материалы корня `ОРКЕСТРАТОР/Code` и старый `space-nobus` удалены после архивирования.
- Архивы находятся в `ОРКЕСТРАТОР/Backups/2026-07-20 Миграция документации`.
- Архив старого прототипа потенциально содержит `.env`; его нельзя публиковать или добавлять в Git.
- Все четыре найденные одноразовые `test-temp-review-*` директории удалены после проверки точных путей; канонических файлов в них не было, совпадающих директорий в `ОРКЕСТРАТОР/Code` не осталось.

Проверенные SHA-256 резервных архивов:

| Архив | SHA-256 |
|---|---|
| архив черновой LLM-платформы до канонической миграции | `66BC6D282BDAB14777A97845030B052029D6562FAD03BD01DC0F4CCB8B03C457` |
| `Устаревшие материалы корня Code.zip` | `6AE9AEB25D5B5DB53375A56E0DAB64F8E06236A8CE3777D4E28B591DCDB9DA1B` |
| `space-nobus legacy source.zip` | `4351C6433CDE933176F0999D9E9D467A41402B4A312D827E2185BA73A09374D0` |

## Оценка готовности Telegram MVP

Расчёт ведётся по фиксированным весам обязательных блоков, а не по числу файлов или тестов.

| Блок | Вес | Фактический статус | Зачтено |
|---|---:|---|---:|
| Baseline и каноническая документация | 5% | ACCEPTED | 5% |
| Core contracts, state/policy и L1–L4 | 15% | ACCEPTED | 15% |
| Локальный Telegram ingress и trusted binding | 12% | ACCEPTED, без сети | 12% |
| Bytes-only voice preview | 8% | ACCEPTED, без live provider | 8% |
| SQLite checkpoints, events и status outbox | 15% | ACCEPTED и wired локально | 15% |
| Worker boundary и локальный fake vertical | 10% | Job Object live probe принят; real Codex отсутствует | 9.5% |
| Actor-bound voice confirmation | 8% | ACCEPTED, wired локально; store in-memory | 8% |
| Runtime wiring и restart/recovery E2E | 12% | ACCEPTED; local fake | 12% |
| Authenticated Telegram receive/send | 10% | owner-bound polling и confirmed fake-task E2E live; terminal outbox ACKed; live Codex отсутствует | 10% |
| Deployment, monitoring и restore drill | 5% | NOT STARTED; REQUIRES L4 | 0% |
| **Итого** | **100%** | **инженерная готовность MVP** | **94.5%** |

`94.5%` включает live owner-воспроизведение text flow: durable Task, one-shot confirmation, local fake-worker и ACKed status outbox. Live Codex и voice network path не активированы, runner не установлен как OS service.

Материалы Kimi D1–D4 сохранены только как `REWORK`-черновик в `ОРКЕСТРАТОР/Backups/2026-07-21 Kimi Web drafts`; исходная `Kimi handoffs/2026-07-21 Web tasks` удалена после проверки ZIP `ADBFAA13F435567E4221A806452331FDDF66714B56753A965A628EA6BFE2D218`. E1–E4 не архивировались, поскольку полностью заменены принятым Gate 4E.

## Следующая очередь

Следующая очередь: отдельным L4 подключить строго ограниченный Codex worker вместо fake-worker. После этого активировать voice download/transcription/confirmation. Отдельно требуется Gate 5B: supervised startup, health/monitoring и restore drill.

## Обязательная остановка и L4

Автономная работа останавливается перед:

- заменой Telegram credential, owner binding или добавлением нового адресата/чата;
- внешними сообщениями вне уже разрешённой owner-bound control-plane сессии;
- live Codex/subprocess boundary и расширением разрешений;
- установкой новой зависимости без отдельного обоснования и проверки;
- push, remote, deployment, публикацией, деньгами, доступами и внешним удалением;
- утверждением production RPO/RTO, retention или approval channel.

## Среда и известные ограничения

- Проверки Gate 4F воспроизведены локальной `.venv` на Python 3.12; перед release среду всё равно требуется пересоздать из manifest.
- В ограниченной среде `tmp_path` требует разрешённый локальный TEMP; это не runtime-дефект voice service.
- Gate 4F остаётся local fake: update/callback claims, confirmation challenges, StateManager и PolicyStore process-memory.
- Gate 3B.2b доказывает Windows Job inheritance/stdio/tree cleanup/cancellation только на локальном probe-child; поведение реального Codex и OS sandbox ещё не проверено.
- SQLite polling store реализован; его `state_digest` является checksum, а не MAC против субъекта с правом переписать БД и пересчитать digest.
- Live polling активирован только для одного owner binding; временная недоступность Telegram повторяется с bounded backoff, но runner зависит от текущей desktop-сессии и не имеет OS supervisor/health alert.
- Gate 5A.3 consume-before-execute fail-closed: crash/cancellation после consume может оставить stranded `PENDING/PARSING`; capability не восстанавливается и повторный worker start запрещён до будущего durable confirmation/recovery.
- Pre-durable transient failure требует restart либо нового voice preview/confirm; незавершённый durable Task возвращает `RECOVERY_REQUIRED`, без автоматического resume.
- Injected delivery имеет at-least-once semantics; stale destination получает NACK и требует reconciliation, live adapter обязан поддерживать idempotency.
- Ожидаемое предупреждение FastAPI tests: `StarletteDeprecationWarning` о будущем переходе TestClient на `httpx2`.
- Перед release окружение нужно создать заново из `requirements.txt`, выполнить полный suite, dependency audit и restore drill.
