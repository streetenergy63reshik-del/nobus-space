# Nobus Space Telegram Orchestrator — CURRENT STATUS

**Дата:** 2026-07-28
**Runtime feature commit:** `b69e846`
**Live runtime commit:** `b69e846`
**Статус:** PERSISTENT MOBILE CODEX — PUBLISHED LOCALLY
**Remote/push:** запрещены

## Принятый TARGET MVP-1 — 28 июля 2026

- Владелец принял эталон Natural Language First и гибридный document plane:
  Server Nobus Core + Google Workspace + Windows Local Library Bridge.
- Google Drive/Docs/Sheets и `C:\Хранилище\АГЕНТ` должны иметь единый lifecycle:
  search, select, read, analyze, create, revision/digest-bound update и deliver.
- Нормативный объём, Gate 0–8, acceptance matrix и L4-шаблоны находятся в
  [`../12-Эталон-MVP-1-и-дорожная-карта.md`](../12-Эталон-MVP-1-и-дорожная-карта.md);
  архитектурное решение — [ADR 0017](../adr/0017-hybrid-natural-google-local-document-plane.md).
- Это документационный TARGET. Server hybrid runtime, Local Library Bridge,
  Google document writeback и новый Gate release ещё не считаются CURRENT без
  кода, L1/L2/L3 и точного release L4.

## Three-hour web stream deadline — 26 июля 2026

- Последний product research завершился примерно через 15 минут с
  `worker_failed`, а не `worker_timeout`: внешний task deadline уже был равен
  10 800 секундам, но provider stream использовал более короткий idle-timeout и
  внутренние повторы.
- Только web-thread persistent Codex SDK/app-server получает provider idle
  9 000 000 мс (2,5 часа). Последние 1 800 секунд общего бюджета
  зарезервированы для единственного pinned CLI fallback; CLI допускает idle до
  10 800 000 мс, но фактически ограничен оставшимся task deadline.
- Обычные non-web turn не получают расширенный provider idle.
- Общая граница не стала бесконечной: Gate 5A.4 по-прежнему завершает весь
  execution через 10 800 секунд, а schema/adapter ceiling остаётся 14 400
  секунд. Telegram polling и очередь не ждут worker синхронно. Трёхчасовая
  длительность проверяется детерминированными deadline-регрессиями; буквальный
  трёхчасовой live-run для релиза не требуется.

## Web research dual-transport recovery — 26 июля 2026

- Повторные продуктовые отказы длительного research происходили через 182–488
  секунд при рабочем deadline 10 800 секунд. Причина — временный разрыв
  WebSocket/stream официального Codex app-server, а не тайм-аут Telegram или Nobus.
- Основной транспорт остаётся persistent official Codex SDK/app-server. Только для
  `web.search` при transient transport failure или отсутствии подтверждённых
  источников выполняется один изолированный `codex exec --json --ephemeral`.
- Резервный CLI берётся из того же зафиксированного пакета `codex_cli_bin`
  (`0.144.4`), запускается read-only, с live web и без shell, MCP, apps,
  workspace-write и произвольного локального доступа.
- Production-профиль `model.inference + owner.library.read + web.search`
  сохраняет server-side owner projection. Локальные файлы не передаются CLI.
- Fallback URL становится evidence только вместе с короткой точной цитатой из открытой страницы. `SafeSourceVerifier` один раз разрешает DNS, подключается TLS непосредственно к этому public IP с исходным SNI/Host, повторяет проверку на каждом redirect и принимает только совпавшую цитату из identity-encoded body не более 128 KiB. Private, CGNAT, multicast, mapped-special, DNS rebinding, non-2xx и blocked sources fail closed.
- Общая граница inference — один SDK turn плюс один fallback turn. Только доставленный результат после `L3 -> ANSWERED` и `pipeline.finalize` становится явно недоверенным контекстом следующего turn.
- L1: `1303 passed, 2 skipped, 1 warning`; compileall, pip check и diff-check: PASS. Live read-only owner-class business research: PASS, 3 независимо проверенных публичных источника.

## Google Tasks natural creation reliability — 26 июля 2026

- Текстовая owner-команда, direct-owner voice и команда вида «из резюме Заметок
  бизнеса создай задачу…» используют один специализированный Google Tasks route,
  а не общий Codex turn.
- Имя tasklist разрешается только exact-normalized match. Для брендового списка
  действует закрытый алиас `пространства` → `PROстранство`; fuzzy-write удалён,
  поэтому соседний `PROстранство2` не может получить задачу по ошибке.
- Google API service/HTTP transport создаётся отдельно на worker thread и
  сбрасывается после SSL/read failure. Mutation transport retry остаётся
  отключён; неизвестный исход записи сверяется по idempotency marker.
- Одинаковый idempotency key сериализуется в одном процессе. Production сохраняет
  invariant единственного runner через Task Scheduler и polling mutex.
- Без отдельной кнопки разрешена только прямая утвердительная owner-команда.
  Инфинитив, отрицание, отмена, пример/цитата/инструкция и управляющий текст
  fail-closed. Явный заголовок в сбалансированных кавычках остаётся данными.
- Direct owner voice выполняется без второй кнопки согласно актуальной продуктовой
  политике; удаление Google Task по-прежнему требует action-bound L4.
- Read-only live reproduction: 21 tasklist; `пространства` однозначно разрешён в
  `PROстранство`. Реальная тестовая задача не создавалась без новой точной
  owner-команды в Telegram.
## Runtime и Google Drive recovery hotfix — 26 июля 2026

- Устранён повторный отказ длительных SDK-задач после первой временной ошибки:
  Codex app-server теперь управляется поколениями с lease/refcount, а повреждённое
  поколение исключается без остановки параллельных задач. Закрытие клиента общее,
  ограниченное по времени и устойчивое к повторной отмене.
- Google Drive теперь сначала разрешает явный путь по сегментам и сохраняет папку
  жёсткой границей поиска. Добавлены безопасные точные алиасы бренда, bounded
  token fallback, защита от literal-path impostor и общий лимит не более четырёх
  list-запросов.
- Прямой длительный web-smoke: PASS за 496,11 с; итог 5829 символов,
  подтверждённый публичный источник присутствует.
- Точная продуктовая Drive-команда: PASS за 9,36 с; возвращена HTTPS-ссылка без
  раскрытия содержимого файла.
- L1: `1186 passed, 2 skipped, 1 warning`; `compileall`, `pip check`,
  `git diff --check`: PASS.
- Независимые L2 и L3: ACCEPT, открытых P0/P1/P2 нет.
- Task Scheduler: Running; Codex app-server активен; polling checkpoint
  обновляется; health четырёх runtime-БД: PASS.
- Проверенный backup:
  `ОРКЕСТРАТОР/Backups/2026-07-26-pre-runtime-drive-hotfix-2`.

## Telegram admission hotfix 26 июля 2026

- Устранён массовый отказ обычных owner-задач до durable queue. Корень:
  `TaskContract.source` ошибочно использовался одновременно как доверенный
  transport source и как SDK session key; Core policy закономерно отклонял
  `telegram:<hash>` вместо подписанного `telegram`.
- Transport source снова равен доверенному ingress source. Отдельный
  `conversation_ref` серверно выводится только из проверенного
  tenant/chat/topic и используется для persistent Codex thread.
- `conversation_ref` связан на Core boundary, условно сохраняется в Task/SQLite
  и сохраняет legacy digest для старых записей. Forged/API/malformed binding
  отклоняется fail-closed; opaque Telegram callback ID не интерпретируется.
- Естественные owner-фразы web research и запросы Google Sheets/«гугл-таблица»
  маршрутизируются в соответствующие product adapters.
- L1: `1167 passed, 2 skipped, 1 warning`; exact
  `TelegramGateway → prepare_instruction`: PASS; product phrase smoke:
  `14 passed`; `compileall`, `pip check`, `git diff --check`: PASS.
- Независимые L2 и L3: ACCEPT, открытых P0/P1/P2 нет. Четыре runtime-БД:
  health PASS; Task Scheduler и polling checkpoint: active.

## Reliability hotfix 26 июля 2026

- Длительный web research больше не наследует устаревший thread: каждый
  research-turn получает свежий ephemeral SDK thread, а обычные личные и
  topic-диалоги остаются persistent.
- Ссылки в research-ответе принимаются только из фактически наблюдавшихся
  `web_search`/`open_page` events текущего turn. Непубличные, вложенные,
  локальные и неподтверждённые URI удаляются; ответ без evidence отклоняется.
- Естественный запрос Google Drive теперь разрешает точную ссылку и поиск
  документа в указанной папке/бренде. Проверка ancestry использует bounded
  batch BFS с fail-closed binding `request_id == response.id`, deadline,
  cancellation и защитой от совпадений по подстроке.
- Полный L1: `1158 passed, 2 skipped, 1 warning`. Независимые L2 и L3:
  ACCEPT, открытых P0/P1/P2 нет.
- Live web smoke: PASS, 2164 символа и 3 подтверждённых evidence events.
  Live Google Drive link smoke: PASS. Четыре runtime-БД: health PASS.
- Проверенный pre-release backup:
  `ОРКЕСТРАТОР/Backups/2026-07-26-pre-research-drive-cc1a3ae`.

## Reliability hotfix 25 июля 2026

- Runtime-права Google и web были исправны; массовые отказы owner-запросов
  вызвала несовместимость product protocol с реальными read-only ответами
  persistent Codex SDK. Read-only turn теперь принимает plain text, минимальный
  `{"answer": ...}` и закрытый planner JSON; write-capability и patch envelope
  остаются строгими, а answer с `patch/paths` отклоняется.
- Частые read-only запросы Google Tasks (`сегодня`, `завтра`, `эта неделя`,
  все списки) разбираются детерминированно без LLM round-trip. Естественные
  follow-up работают только 10 минут внутри exact tenant/chat/topic после
  явного Google Tasks turn; project/client/file/Nobus и Calendar формулировки
  переключаются обратно в соответствующий домен.
- `#NOBUS-BIND-NOTES` в личном чате больше не становится задачей: бот объясняет,
  что marker надо отправить отдельным сообщением непосредственно в группе
  «Заметки бизнеса». Только group marker может создать binding.
- Финальный L1: `1116 passed, 2 skipped, 1 warning`. Независимые L2 и L3:
  ACCEPT, открытых P0/P1/P2 нет.
- Hotfix `e39c857` опубликован локально: main и `agent/telegram-live`
  синхронизированы, Task Scheduler работает. Runtime health четырёх БД — PASS;
  Google Tasks read-only smoke — PASS (7 разделов); persistent SDK web smoke —
  PASS (2 URL). Remote/push не выполнялись.

## Релиз 25 июля 2026

- Production worker переведён с одноразового `codex exec --json/ephemeral` на
  официальный persistent `openai-codex` SDK/app-server `0.144.4`.
- Модель: `gpt-5.6-sol`, reasoning high, Fast. Личный чат и каждая Telegram-тема
  получают отдельный resumable thread.
- SDK-turn read-only; запись остаётся в application effects со
  snapshot/diff/atomic/CAS. Общая owner-команда не разрешает удаление файла.
- Deadline задачи — 10 800 секунд, ceiling — 14 400; polling и durable queue
  не блокируются длительным turn. Interrupt/close bounded до 15 секунд.
- Voice draft теперь полностью durable и восстанавливается после crash/restart.
- Google Tasks читает все tasklists и страницы, включая assigned tasks.
  Retry разрешён только safe reads; mutation transport-retry отключён.
- Business Notes binding v2 готов к точному owner marker; исторический импорт
  Telegram не выполняется.
- Portability исправлена: runtime layout больше не зависит от `parents[n]`.
- L1 в основном worktree: `1089 passed, 2 skipped, 1 warning`.
- L2 clean detached worktree: архитектурная база — `1088 passed, 2 skipped, 1 warning`;
  hot-binding delta — `53 passed`; `pip check`
  и `compileall` — PASS.
- L3 fault injection: `208 passed, 2 skipped, 880 deselected, 1 warning`.
- Внешнее AI-review полного дерева не выполнялось: protective egress boundary
  заблокировал передачу незакоммиченного кода без отдельного разрешения.
- Live publication и Google `NOBUS-SMOKE` завершены после документационного
  commit и свежего проверенного backup. Активный polling принимает точный owner
  marker `#NOBUS-BIND-NOTES`, атомарно создаёт binding v2 и горячо обновляет gateway.

## Что входит в релиз

| Контур | Текущее состояние |
|---|---|
| Telegram owner binding, polling, queue, outbox | Durable SQLite, CAS lease, restart recovery |
| Codex SDK/app-server | persistent `gpt-5.6-sol`, high reasoning, Fast; thread per chat/topic/profile |
| Длительные задачи | deadline 10 800 секунд; polling не блокируется worker |
| Параллельность | 2 worker; bounded durable queue и восстановление после restart |
| Голос | local faster-whisper, Russian profile, startup warmup, preview/cancel |
| Product UX | обычный текст = задача; технические ID скрыты; одна progress-card |
| Web research | отдельный read-only web-search профиль с проверяемыми ссылками |
| Local files | поиск/Telegram delivery; bounded analysis text/HTML/JSON/CSV/Word/Excel |
| Documents | Word/Excel/PDF/HTML в owner workspace; overwrite только со snapshot |
| Google | Calendar/Tasks/Drive natural commands; delete всегда action-bound L4 |
| Business Notes | encrypted tenant/chat/topic index; private local summaries/tasks |
| Context | Nobus Memory progressive retrieval: scoped 3–7 notes, client isolation, explicit Inbox writes |
| Autostart/ops | Windows Task Scheduler, health, backup, restore и rollback scripts |

## Авторизация

- Точный owner text выполняет обратимое действие без второй кнопки.
- Подтверждённая voice-транскрипция имеет ту же силу.
- Удаление, публикация, деньги, права доступа, push/deploy и применение code patch
  всегда требуют отдельного action-bound L4.
- `C:\Хранилище\WORK` вне scope. Remote и push отключены.

## Проверки текущей итерации

- Полный L1 regression: `1089 passed, 2 skipped, 1 warning`.
- Calendar/Tasks/Drive read-only API health: PASS; OAuth ready, содержимое
  объектов и секреты не выводились.
- Google Tasks all-lists L3: 21 список прочитан с полной пагинацией; на неделю
  20–26 июля независимо подтверждены 36 незавершённых задач в 12 списках;
  production-контур вернул те же 36.
- Live bounded web-research L3: PASS; `gpt-5.6-sol/high/Fast` завершил четыре
  web-search и вернул структурированный результат на 7964 символа. Durable outbox
  и Telegram chunk-delivery проверены для длинного ответа.
- Natural owner-file L3: PASS; запрос без расширения выбрал точный документ
  среди двух похожих имён, не читая и не выводя его содержимое.
- Nobus Memory product/boundary L2: `117 passed`; real-vault L3: PASS (5 scoped notes, only the explicitly named client card, no network/process imports).
- Product/security targeted: `100 passed`; overwrite/restore targeted:
  `38 passed`; Codex CLI: `71 passed`.
- `compileall`: PASS; `pip check`: PASS; `git diff --check`: PASS
  (только уведомления LF→CRLF).
- Независимый L2: ACCEPT, P0/P1 отсутствуют.
- Independent final L3: ACCEPT; P0/P1/P2 absent in the accepted reliability scope.
- Owner-file reliability/security focused: 48 passed; final full suite: 1049 passed, 2 skipped, 1 warning.

## Live publication evidence

- Windows Task Scheduler: `NobusSpaceBot` — `Running`; supervised Python process
  tree is active.
- Main и локальная live-ветка синхронизированы; runtime feature — `e39c857`; remote/push не
  выполнялись.
- Startup Codex probe and cached Whisper warmup завершились до Telegram polling:
  активный polling lease подтверждён после запуска.
- Runtime health: `PASS`; all four canonical SQLite databases are valid.
- Business Notes hot-binding L3: `62 passed`; wrong owner/title/chat, tampered config
  и invalid replacement отклоняются.
- Calendar/Tasks `NOBUS-SMOKE` create/update/delete: PASS; созданные этой
  проверкой объекты удалены. Google Drive read/search: PASS.
- Verified pre-release four-database backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-pre-mobile-codex-runtime-release-bec5f47`.
- Telegram polling checkpoint advanced after restart.
- Nobus Memory live retrieval: PASS; Inbox excluded until curation; vault docs commit `4a8d268`.
- Pre-memory runtime backup: `ОРКЕСТРАТОР/Backups/2026-07-25-pre-nobus-memory`.
- Verified pre-release backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-pre-product-mvp1`.
- Verified final four-database backup:
  `ОРКЕСТРАТОР/Backups/2026-07-25-product-mvp1-final`.
- Disposable restore drill: `PASS`; every restored database passed SQLite
  `quick_check`.
- Forced-process-stop recovery: `PASS`; the durable polling lease prevented a
  duplicate consumer and the runner started normally after its 240-second TTL.
- No remote, push or external repository publication was performed.

## Остаточные границы MVP-1

- PDF можно получить вложением, но его текст не разбирается без отдельного
  проверенного parser dependency.
- Business Notes обрабатывают новые сообщения после привязки чата; историческая
  выгрузка Telegram API не обещается.
- Это owner-bound локальный продукт, а не внешний multi-user SaaS.
- Удаление пользовательских файлов не разрешено этим релизом.
- Внешний restore отдельного owner artifact не опубликован: внутренний
  snapshot/CAS primitive проверен, но внешний вызов требует будущей durable
  one-shot capability, связанной с owner, путём и digest.
- Для естественной отправки файла MVP-1 поддерживает точные owner-команды
  `пришли/отправь/направь/дай мне файл|документ ...`; составная команда
  «пришли и затем проанализируй» намеренно уходит в обычный task pipeline.
- Delivery Telegram остаётся at-least-once на узком crash-окне внешнего
  `sendDocument`.
- Длинный verified answer доставляется несколькими Telegram-сообщениями. В узком
  crash-окне между частичной внешней доставкой и локальным receipt возможен
  повтор уже отправленной части; потеря полного durable результата не допускается.
- Google MCP transport может деградировать независимо от API; штатный локальный
  read-only health check является разрешённым fallback.
