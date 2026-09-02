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
- published base, от которой собран локальный product candidate:
  protected `main` @ `d7e2b8275f20a1a261bbf541573f76db82240901`,
  подтверждённый fetch/readback 31 августа 2026 года; актуальный tip `main`
  определяется live readback и не дублируется в этом файле;
- архитектура опубликована через PR
  [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1),
  Mini App auth/list/detail/create и Gate 0 integrity repair — через PR
  [#2](https://github.com/streetenergy63reshik-del/nobus-space/pull/2),
  publication readback — через PR
  [#3](https://github.com/streetenergy63reshik-del/nobus-space/pull/3),
  полная продуктовая граница MVP-1 — через PR
  [#4](https://github.com/streetenergy63reshik-del/nobus-space/pull/4),
  финальный owner-product и изоляция внутренних уведомлений — через PR
  [#6](https://github.com/streetenergy63reshik-del/nobus-space/pull/6);
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

## Продуктовый статус — 2 сентября 2026 года

**MVP-1 READY.**

Один опубликованный и активированный release:

1. содержит согласованные backend и frontend;
2. проходит полный local/integration journey;
3. опубликован в protected GitHub `main` и прочитан обратно;
4. активирован за HTTPS и открывается из Telegram exact owner;
5. возвращает одну task identity, status, verified result и реальный artifact;
6. проходит negative/restart/recovery, bounded owner smoke и release rollback.

Release развёрнут за `https://app.nobusspace.com`, а exact-owner Telegram menu
ссылается на этот Mini App. Core, SQLite и Codex остаются на owner Windows PC;
VPS держит только Cloudflare Tunnel и restricted reverse relay. Public
health/readiness, fail-closed `502` при остановке Core, owner-bound
create/status/result/artifact, Telegram byte parity, restart/recovery и
rollback прошли. Владелец открыл Mini App из Telegram, создал и просмотрел
задачу и подтвердил итоговый интерфейс после исправлений списка, карточки,
названия и формы «Новая».

Внутренний Codex worker продукта отделён от глобального notifier основной
Codex Desktop задачи: он не отправляет служебные уведомления в `Codex work`, а
marker-like блоки удаляются или отклоняются до durable state, verifier,
артефакта, Mini App и Telegram delivery. Глобальное правило уведомлений
primary/root задач Codex Desktop не изменено. Exact code checkpoint
`14c80131b2a702d75f92abb4fe22d49ea6aa975c` опубликован через PR #6 и
прочитан обратно из protected `main`; release-relevant suite и независимые
L2/L3 зелёные. Финальная публикация фиксируется тегом `v1.0.0`.
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
  exact bot/owner/tenant authentication context и content digest;
- admission переиспользует `prepare_instruction` существующего runtime и
  `telegram_jobs` существующего `SQLiteTelegramState`; encrypted job
  фиксируется до Core task, а restart допускает тот же exact prepared contract
  из job, поэтому enqueue failure не создаёт task/outbox и crash не оставляет
  невосстановимую PENDING task;
- server-derived task id детерминирован по tenant и request id, а exact
  verified-owner/request envelope стабилен между короткими сессиями;
  поэтому повтор после restart использует одну job и возвращает ту же
  task, а rebinding другого текста или authority fail closed; exhausted dead-letter тоже блокирует
  Core admission и не оставляет orphan PENDING task;
- static HTML/CSS/ES module UI хранит bearer и pending request id только в
  памяти, открывает create/detail в отдельных нижних панелях, показывает
  bounded owner-visible название, короткий task id, status и время, не делает
  blind retry и показывает
  `Nobus Space временно недоступен` при отказе Core;
- owner-visible короткое название и bounded instruction хранятся в той же task
  snapshot только как единый DPAPI-protected payload, повторно связанный с
  tenant/task/contract и digest; список получает только название, а instruction
  возвращается exact owner только в task detail; открытый текст не появляется в
  SQLite, а legacy rows получают безопасный
  fallback `Задача #<short-id>`;
- `src/main.py` не используется новым boundary и остаётся старым
  демонстрационным API.

Исходный Git slice развёрнут в составе опубликованного MVP-1 вместе с
status/result/artifact, product composition и public HTTPS. Актуальная
release-привязка и результаты readback ведутся в `CURRENT-STATUS`.

## Локальный product composition

Одна команда запускает существующий Telegram/Core/Codex runtime и Mini App в
одном процессе, с одной authoritative task DB/queue:

```powershell
& '..\..\nobus-orchestrator-dev\.venv\Scripts\python.exe' `
  scripts\run_telegram_mvp1.py --serve --timeout 30
```

После успешного fail-closed startup локальный frontend доступен по
`http://127.0.0.1:8765/`, liveness — `/healthz`, readiness — `/readyz`.
Loopback HTTP разрешён только для локальной проверки; любой нелокальный origin
остаётся HTTPS-only. Остановка процесса сначала закрывает web admission, затем
durable control workers, Core/runtime и Telegram API client.

Активная Telegram-поверхность MVP-1 ограничена обычными текстовыми и голосовыми
задачами и командами `/start`, `/status`, `/limit`, `/help`. Маршруты `/task`,
`/calendar`, `/research`, `/document`, `/download`, `/network`, `/file`, `/notes`
и команды подтверждения future-effects не подключаются production runner и
fail closed с явным сообщением. Наличие отдельных адаптеров или тестовых
заготовок в исходниках не считается готовой функцией продукта.

Публичная owner-composition запускается одной отслеживаемой командой:

```powershell
& '..\..\nobus-orchestrator-dev\.venv\Scripts\python.exe' `
  scripts\run_nobus_space_live.py
```

Она помещает reverse SSH и Core в один Windows Job Object, а его
закрытие убивает оба process tree. Публичный frontend:
`https://app.nobusspace.com/`.

Verified answer даёт один детерминированный UTF-8 artifact. Его identity,
revision, digest, MIME, размер и безопасное имя выводятся из существующего
tamper-evident outbox result; отдельная artifact DB/queue не создаётся.
Telegram `sendDocument` и Mini App download получают одинаковые bytes/digest,
а path, foreign-tenant existence и stale/tampered refs не раскрываются.
При Telegram delivery тот же immutable `.txt` сохраняется как восстанавливаемая
локальная проекция в
`C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\NOBUS SPACE BOT\Проекты Telegram`.
SQLite/outbox остаётся единственным authoritative state; совпадающий retry не
создаёт копию, а конфликтующее содержимое под тем же именем fail closed.

Для принятого owner journey отдельный ApprovalRequest не требуется: create,
status, result и download являются Core admission/read-only delivery. Уже
существующие заготовки approval/effect для будущих срезов не входят в активную
MVP-1 composition.

## Локальная проверка документационного кандидата

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests/test_documentation.py
git diff --check
```

Полный frozen G6 evidence и независимый focused code recheck находятся в
[CURRENT-STATUS](docs/handoffs/CURRENT-STATUS.md). Исторические Gate 0 verifier
не используются как release gate текущего ADR 0022 candidate.

Наличие локального commit само по себе не разрешает push, merge, deploy,
recovery, удаление или запись в Nobus Memory: каждое внешнее действие требует
отдельной точной авторизации владельца.

Локальные правила разработки: [AGENTS.md](AGENTS.md).
