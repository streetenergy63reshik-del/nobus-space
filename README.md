# Nobus Space MVP-1

Nobus Space развивается как owner-bound Telegram-оркестратор с обязательным
тонким Telegram Mini App поверх существующего локального Windows Core/Codex
runtime.

Активное архитектурное решение:
[ADR 0022](docs/adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).

## Publication binding — 25 августа 2026 года

- репозиторий `streetenergy63reshik-del/nobus-space` публичный;
- принятый опубликованный канон — exact revision, достижимая из защищённой
  GitHub `main` после live readback; этот файл не дублирует подвижный SHA;
- содержащая этот файл revision вне защищённой `main` является
  `GATE_CANDIDATE`; после разрешённого merge и проверки достижимости та же
  revision становится частью `ACCEPTED_PUBLISHED_BASELINE`;
- baseline `main` при заморозке архитектурного кандидата:
  `8b896fbca9b23c8751d651d14a122506338b5827`;
- исходный head PR [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1)
  до post-publication refresh:
  `d3a235e4db2257826d5a5c5661a709c442be981e`; живой статус PR и head читать
  в GitHub, а не из постоянного документа;
- снимок защиты `main` на 25 августа 2026 года: требуется pull request и
  закрытие всех обсуждений, запрещены bypass, force-push и удаление ветки;
  обязательные status checks не настроены;
- локальный owner-bound Telegram/Core/Codex runtime существует; точное live
  состояние процессов в этой docs-задаче не проверялось;
- Gate 0 принят как исторический sealed snapshot @
  `f5086b2a71a9ae22be3c858ff69453287f6925da`; его 20 digest-bound sources
  не изменяются;
- Gate 1 implementation существует только как dirty
  `HOLD / NOT_ACCEPTED` WIP в отдельном worktree; его нельзя считать каноном;
- Telegram Mini App и Telegram-оркестратор обязательны в MVP-1 и используют
  один Core, одну queue/state model и одну effect authority;
- полный распределённый Gate 2A — **FROZEN / NOT CURRENT**.

Git-репозиторий — источник истины для code/tests/ADR/CURRENT/docs. Nobus Memory
хранит только pointer, короткий status, decisions и freshness и не
переопределяет exact Git revision.

Точный фактический статус:
[CURRENT-STATUS](docs/handoffs/CURRENT-STATUS.md). Иерархия источников и
навигация: [docs/README.md](docs/README.md).

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

## Локальный thin Mini App candidate — 27 августа 2026 года

В содержащей локальной revision реализованы owner-authenticated read-only
projection и следующий самостоятельный task-create slice:

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

Это локальный кандидат, а не live Mini App: HTTPS ingress/hostname, BotFather,
Telegram menu button, запуск live runtime, push/PR/merge и deploy не
выполнялись. Следующий вертикальный slice после принятия кандидата — единый
status и безопасное получение результата/артефакта через Telegram и Mini App.

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
