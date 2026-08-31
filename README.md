# Nobus Space MVP-1

Nobus Space развивается как owner-bound Telegram-оркестратор с обязательным
тонким Telegram Mini App поверх существующего локального Windows Core/Codex
runtime.

Активное архитектурное решение:
[ADR 0022](docs/adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).

## Publication binding — 31 августа 2026 года

- репозиторий `streetenergy63reshik-del/nobus-space` публичный;
- принятый опубликованный канон — exact revision, достижимая из защищённой
  GitHub `main` после live readback; этот файл не дублирует подвижный SHA;
- содержащая этот файл revision вне защищённой `main` является
  `GATE_CANDIDATE`; после разрешённого merge и проверки достижимости та же
  revision становится частью `ACCEPTED_PUBLISHED_BASELINE`;
- принятый published baseline до этой docs-only актуализации: protected
  `main` @ `a363db032d4451b73c93b530a59ac1850364e710`, подтверждённый live
  fetch/readback 31 августа 2026 года;
- архитектура опубликована через PR
  [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1),
  Mini App auth/list/detail/create и Gate 0 integrity repair — через PR
  [#2](https://github.com/streetenergy63reshik-del/nobus-space/pull/2),
  publication readback — через PR
  [#3](https://github.com/streetenergy63reshik-del/nobus-space/pull/3);
- снимок защиты `main`, повторно прочитанный 31 августа 2026 года: требуется
  pull request и
  закрытие всех обсуждений, запрещены bypass, force-push и удаление ветки;
  обязательные status checks не настроены;
- локальный owner-bound Telegram/Core/Codex runtime существует; точное live
  состояние процессов в этой docs-задаче не проверялось;
- Gate 0 принят как исторический sealed snapshot @
  `f5086b2a71a9ae22be3c858ff69453287f6925da`; его 20 digest-bound sources
  не изменяются;
- отдельный historical Gate 1 implementation остаётся `HOLD / NOT_ACCEPTED`;
  его нельзя вливать целиком или считать текущей архитектурой;
- Telegram Mini App и Telegram-оркестратор обязательны в MVP-1 и используют
  один Core, одну queue/state model и одну effect authority;
- полный распределённый Gate 2A — **FROZEN / NOT CURRENT**.

Git-репозиторий — источник истины для code/tests/ADR/CURRENT/docs. Nobus Memory
хранит только pointer, короткий status, decisions и freshness и не
переопределяет exact Git revision.

Точный фактический статус:
[CURRENT-STATUS](docs/handoffs/CURRENT-STATUS.md). Иерархия источников и
навигация: [docs/README.md](docs/README.md).

## Продуктовый статус — 31 августа 2026 года

**MVP-1: IN PROGRESS / NOT PRODUCT READY.**

Опубликованные backend и static frontend source ещё не образуют готовый
бизнес-продукт. `MVP-1 READY` допустим только когда один exact release:

1. содержит согласованные backend и frontend;
2. проходит полный local/integration journey;
3. опубликован в protected GitHub `main` и прочитан обратно;
4. активирован за HTTPS и открывается из Telegram exact owner;
5. возвращает одну task identity, status, verified result и реальный artifact;
6. проходит negative/restart/recovery, bounded owner smoke и release rollback.

Локальный `VERIFIED LOCAL CANDIDATE`
`f18a664f2fab2fbd193e894bc93d5624683badf2` добавляет status, events и
verified-result projection и прошёл локальные L1/L2/L3, но не опубликован и не
закрывает artifact, production composition, HTTPS/BotFather activation или
owner acceptance.
Редакционная продуктовая roadmap и её HTML-представление остаются на owner
publication hold и не входят в этот docs-only release.

## Обязательный MVP-путь

```text
Telegram Mini App -> owner authentication / Telegram initData
  -> existing Nobus Core -> local Codex/runtime
  -> authoritative state -> Telegram/Mini App status/result/artifact
```

Первый новый deployment unit — один `Mini App Web Boundary`: static UI,
bounded pass-through Telegram `initData` и тонкий API adapter к Core за
публичным HTTPS ingress. У него нет собственной БД, queue, policy/effect
authority, bot secret или Agent Registry.

## Опубликованный thin Mini App Git slice — 28 августа 2026 года

В protected `main` опубликованы owner-authenticated read-only projection и
самостоятельный task-create slice:

- `MiniAppCore` проверяет Telegram signature для exact bot, exact owner,
  `auth_date`, TTL/future skew и durable replay digest;
- opaque session живёт кратко и хранится в Core только по SHA-256 bearer;
- `SQLiteStore.list_tasks` читает bounded stable tenant-scoped projection из
  существующего `task-runtime.sqlite3`;
- `POST /api/session`, `GET /api/tasks` и `GET /api/tasks/{task_id}` не
  принимают client-selected authority и возвращают только allowlisted поля;
- `POST /api/tasks` принимает только bounded JSON instruction и один
  `Idempotency-Key`; Core сам выводит owner/tenant/actor и связывает request с
  текущей session и content digest;
- admission переиспользует `prepare_instruction` существующего runtime и
  `telegram_jobs` существующего `SQLiteTelegramState`; encrypted job
  фиксируется до Core task, а restart допускает тот же exact prepared contract
  из job, поэтому enqueue failure не создаёт task/outbox и crash не оставляет
  невосстановимую PENDING task;
- server-derived task id детерминирован по tenant и request id, а exact
  session/request envelope стабилен; поэтому повтор в crash-window
  использует одну job и возвращает ту же task, а rebinding другого
  текста или session fail closed; exhausted dead-letter тоже блокирует
  Core admission и не оставляет orphan PENDING task;
- static HTML/CSS/ES module UI хранит bearer и pending request id только в
  памяти, не делает blind retry и показывает
  `Nobus Space временно недоступен` при отказе Core;
- `src/main.py` не используется новым boundary и остаётся старым
  демонстрационным API.

Это опубликованный Git slice, но не live Mini App: production composition,
HTTPS ingress/hostname, BotFather menu button, deploy и live owner smoke не
подтверждены. Следующий незакрытый продуктовый результат — безопасный реальный
artifact, затем production wiring, activation, owner acceptance и release.

## Локальная проверка документационного кандидата

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests/test_miniapp.py `
  tests/test_durable_telegram_state.py `
  tests/test_sqlite_store.py `
  tests/test_main.py `
  tests/test_pre_gate1_architecture_integration.py `
  tests/test_documentation.py
git diff --check
```

Наличие локального commit само по себе не разрешает push, merge, deploy,
recovery, удаление или запись в Nobus Memory: каждое внешнее действие требует
отдельной точной авторизации владельца.

Локальные правила разработки: [AGENTS.md](AGENTS.md).
