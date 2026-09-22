# M2-DESKTOP — журнал для независимого аудита

**Gate:** M2-DESKTOP

**Снимок:** 22 сентября 2026 года, 12:29 МСК

**Статус:** разработка и live-контур безопасно остановлены владельцем

**Ветка:** `codex/m2-desktop`

**HEAD:** `3ea243893a2647dc631662c2a2030de7679ae0e1`
**Base:** `f3fdb2d22a41b6a5b84fec06544447014c7bb35c`

## 1. Краткий итог

Локально реализован единый Telegram ↔ работающий Codex Desktop bridge с
durable request state, private owner-follower IPC, семантическим Windows UIA,
маршрутизацией вопросов и разрешений, полным финалом, файлами, защитой от
дублей и unknown-outcome recovery. Реализация находится в трёх локальных
commits и не опубликована.

Один реальный Telegram-запрос дошёл до bridge, но новая задача Desktop не была
создана. Исход корректно сохранён как `unknown_dispatch`; повторного исполнения
не было. Причина — точная кнопка Create task находилась вне viewport, а UIA
backend вызывал `Invoke` без `ScrollIntoView`. Исправление добавлено и покрыто
целевыми тестами, но новый end-to-end запрос после него не отправлялся.

Попытка активировать исправленный revision выявила отдельную эксплуатационную
границу: после application rebind старые backup generation не удовлетворяли
admission новой версии. Recovery reset прошёл, но штатный backup cycle затем
завершился Scheduler result `1`; его точная failing boundary не локализована.
По запросу владельца дальнейшая диагностика остановлена. Все три production
Scheduled Tasks остановлены и Disabled. Gate не принят, production не готов.

## 2. Состав снимка и неизменяемые границы

- Единственная рабочая задача Gate: текущая задача M2-DESKTOP. Старые M2-G0…G4,
  принятый C6 и MVP1 повторно не запускались.
- Каноническая рабочая копия:
  `Code\nobus-orchestrator-dev\.runtime\worktrees\m2-desktop`.
- Production checkout:
  `Code\worktrees\telegram-live`, detached на `3ea2438`; он не является
  опубликованной `main`.
- Прямых записей в БД или историю Codex Desktop не было. Codex не
  устанавливался, не обновлялся и не патчился; PATH, ACL, credentials и
  BotFather не менялись.
- CDP не запускался. Отдельный CLI/App Server не принят как замена Desktop.
- Полный независимый L1/L2/L3 не выполнялся: кандидат ещё не заморожен и live
  journey не завершён.
- Пользовательская DOCX-памятка не изменялась и не должна считаться актуальной
  для MVP2.

## 3. Локальные commits

| Commit | Содержание | Статус |
|---|---|---|
| `3d6514d5d42cb599a16c3858f70a7288a56c3749` | Telegram↔Desktop bridge, durable state, IPC/UIA, единая доставка, документация и тесты | WIP, не опубликован |
| `3ac1cac1574956854a8d5256a40e84c5373ef12e` | Миграция bridge schema выполняется до backup admission | WIP, не опубликован |
| `3ea243893a2647dc631662c2a2030de7679ae0e1` | ScrollItem/ScrollIntoView для offscreen Create task; исправление snapshot argument | WIP, развёрнут в остановленном checkout |

Суммарный diff от base: 40 файлов, около 9,4 тыс. добавленных строк. Это крупный
security- и reliability-sensitive change; независимый аудит должен смотреть
не только последний commit, а весь диапазон `f3fdb2d..3ea2438`.

## 4. Хронология существенных фактов

### 21 сентября — выбор транспорта

1. Исторический отдельный stdio App Server сохранил положительные
   create/visibility/readback-факты, но после Desktop turn не смог возобновить
   writer: `already has an active writer`. Этот транспорт отклонён.
2. `no complete local package` локализован только на попытке managed daemon;
   вывод об обязательной установке daemon снят.
3. На установленном Desktop `26.915.4065.0` через `\\.\pipe\codex-ipc`
   прошли `initialize` и `thread-owner-discovery`; найден owner существующей
   задачи с `supportsUntrustedAppInput=true`.
4. Read-only UIA обнаружил точные semantic controls проекта, Create task,
   существующих задач и composer. Координатный ввод не использовался.
5. В bundle обнаружены follower start/history и методы ответов на вопросы и
   approvals. Наличие методов не засчитано как live parity.

### 22 сентября — реализация и локальная проверка

1. Реализованы IPC client, UIA wrapper/backend, bridge orchestration, durable
   request/turn/delivery state, Telegram команды и маршрутизация, документная
   доставка и восстановление.
2. Разрешения привязаны к проверенному numeric owner `user_id`; вопросы — к
   автору текущего request. Fallback на другого executor отсутствует.
3. Финал читается из точного Desktop turn и отправляется полностью; удаляется
   только terminal notifier marker. Summary notifier не считается результатом.
4. Для delivery введена привязка request/turn/part, single-owner claim и
   unknown-result state. Повтор нового request того же файла не смешивается с
   retry прежнего request.
5. Существующий notifier не заменён вторым sender. Реализовано подавление его
   terminal marker в пользовательском полном ответе; исторические notifier
   side effects сохранены.
6. Выявлен startup defect: новая bridge DB/schema создавалась после backup
   admission и могла сделать уже допущенный snapshot неполным. Порядок изменён:
   schema migration до admission; добавлен regression test.

### 22 сентября — реальный Telegram request

1. После точного подтверждения владельца в «Заметки бизнеса» → «Codex work»
   отправлен один сценарий, message id `2150`.
2. Ожидалось: одна новая задача в `nobus-orchestrator-dev`, вопрос о цвете,
   approval безопасного `HEAD https://example.com/`, deny Calculator, один
   файл только в `.runtime/m2-desktop-live-probe/`, финал более 5000 символов.
3. Бот подтвердил приём: «Задача принята и передаётся в Codex Desktop.»
4. Durable request id
   `e18a5ca3-95d3-4be8-8453-630d88e97a50` перешёл в `unknown_dispatch` без
   `desktop_thread_id` и `turn_id`.
5. Read-only список Desktop подтвердил отсутствие новой задачи. Следовательно,
   нет скрытого исполнения, которое можно задублировать повтором.
6. Точечный UIA probe установил: project selector найден; Create task найден,
   enabled и Invoke-capable, но `offscreen=true`; `ScrollItemPattern` доступен;
   composer найден.
7. Исправление `3ea2438`: `ScrollIntoView()` перед `Invoke`, fail-closed без
   ScrollItem, mutation receipt `scrolled-create-task`. Snapshot wrapper теперь
   передаёт строку `snapshot`, а не `-`, которое Windows PowerShell трактовал
   как границу switch.
8. Новый Telegram request после исправления не отправлялся. Старый
   `unknown_dispatch` не переоткрывать и не мутировать вручную.

### 22 сентября — попытка активации и безопасная остановка

1. Работающий bot был штатно остановлен; live checkout чисто переведён на
   `3ea2438`.
2. Backup config и действие `NobusSpaceBot-Backup` переведены на application
   binding нового revision. Config digest:
   `sha256:7c3876a3f7e011c2e62ab77c67516bd033db889a2c8f235d1b81cf8de0337d79`.
3. Activation rebind тем же production `pythonw.exe` завершился кодом `0`.
   Новый binding:
   `sha256:fddb39bbdfb5d2cd6403a9a19f89ff8805154eb0d41967890e084d391913f3fb`.
4. Первый запуск завершился fail-closed: Core result
   `telegram_mvp1_failed`, supervisor disposition `stop_non_retryable`. Причина
   по коду и состоянию: admission проверяется до первого stage marker, а
   существующие backups относятся к прежней application binding.
5. Все задачи были остановлены и Disabled; точный terminal event
   `sha256:3b9e354a613fc3cc7b4063f685630e14a78ce2bd12924b4185da7728cd263fce`
   подтверждён штатным `--acknowledge-recovery-stop`. Проверка точным
   `pythonw.exe` вернула PASS/state `new`, last digest
   `sha256:e911277e820fa2244266d9914e9562403be2cfc37383479ec4a1ce9adbc51885`.
6. Main и Backup были включены, запущен штатный Backup cycle для cold start.
   Scheduler завершил его result `1`; Main не поднялся, Health остался Disabled.
7. `--inspect-failure` после отказа вернул `phase=complete` и confirmation
   digest `sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`.
   Этот journal не доказывает фазу только что отказавшего запуска: result `1`
   мог возникнуть до новой записи journal. Read-only `load_config` тем же
   production `pythonw.exe` отдельно прошла.
8. Диагностика остановлена по запросу владельца. В 12:29 МСК все три задачи
   остановлены и Disabled. Новых внешних сообщений не отправлялось.

## 5. Реестр багов и технических рисков

| ID | Статус | Наблюдение / причина | Предпринятое решение | Что аудировать |
|---|---|---|---|---|
| M2B-001 | CLOSED FOR ROUTE | Separate App Server теряет writer после Desktop turn | Маршрут отклонён; выбран owner-follower IPC | Нет ли скрытого fallback на App Server/CLI |
| M2B-002 | MITIGATED | SDK 0.144.4 не понимает `functionCallOutput` Desktop 0.155 | Version-pinned raw JSON IPC profile, fail-closed mismatch | Bounds, schema checks, version policy |
| M2B-003 | FIXED LOCALLY | Bridge schema создавалась после backup admission | `3ac1cac`: migration до admission | Crash consistency и backup completeness |
| M2B-004 | FIXED LOCALLY, LIVE NOT REPEATED | UIA Invoke на offscreen Create task завершал dispatch неопределённо | `3ea2438`: ScrollItem/ScrollIntoView + fail-closed | Exact selector, focus safety, locale/version drift |
| M2B-005 | FIXED LOCALLY | Snapshot argument `-` ломал Windows PowerShell parsing | Передавать literal `snapshot`; regression test | Нет ли других sentinel-аргументов |
| M2B-006 | OPEN | Backup cycle Scheduler result `1` после rebind; journal не привязан к failed attempt | Никакого слепого повтора; все задачи Disabled | Самый первый runtime blocker после аудита |
| M2B-007 | OPEN | Private IPC version-bound, live start ACK ещё не подтверждён | Timeouts, bounded frames, owner check, UNKNOWN/readback-first | Framing, ACK correlation, reconnect races |
| M2B-008 | OPEN | Questions/approvals покрыты fixtures, но не live events | Target exact request/thread/turn; owner numeric id | Expiry, race с Desktop UI, все approval families |
| M2B-009 | OPEN | Full delivery journey и artifacts не проверены live | Single-owner delivery, exact request/turn/part key | Callback/reconciler/notifier duplicate matrix |
| M2B-010 | OPEN | Голос, две темы и Артур младший не прогнаны на кандидате | Код переиспользует ingress/ASR/outbox | Реальные, не fixture интеграции |
| M2B-011 | OPEN | Production checkout/config изменены, но система остановлена | Safe stop, три tasks Disabled | Recovery/rollback plan до любого запуска |

## 6. Блокеры на момент паузы

### Операционный блокер P0

Нельзя включать production, пока не локализован Scheduler result `1` последнего
backup cycle и не создана проверенная backup generation для application binding
`3ea2438`. `phase=complete` из inspection недостаточен: нет доказательства, что
он относится к отказавшему attempt.

### Функциональные блокеры Gate

- Исправленный create/dispatch не подтверждён новым Desktop thread.
- Не получены IPC ACK/turn id и полный event/history цикл реального turn.
- Не выполнены live question → author и approve/deny → verified owner.
- Не доказаны Desktop tools/settings/model/skills/MCP/plugins parity.
- Не проверены длинный полный ответ, файлы, voice, две темы, bot-to-bot Arthur,
  reconnect и restart recovery на замороженном кандидате.
- D01–D17 не закрыты; приёмка и публикация отсутствуют.

## 7. Журнал проверок

| Проверка | Результат | Граница доказательства |
|---|---|---|
| Initial IPC/UIA offline fixtures | 13 PASS | Framing, owner routing, version mismatch, reconnect/readback-first; не Desktop live |
| Документационные проверки checkpoint 21.09 | 3/4 PASS | Scoped M2 links/roadmap PASS; общий link test затронул чужой отсутствующий WIP |
| Реальный owner discovery `\\.\pipe\codex-ipc` | PASS | Read-only initialize/owner only; turn не отправлялся |
| Read-only UIA inventory | PASS | Точные controls найдены; mutation не выполнялась |
| Targeted UIA regression после `3ea2438` | 29 PASS, 2,04 с | Scroll guard + snapshot command; не end-to-end |
| Worktree UIA wrapper snapshot | PASS | Read-only exact Desktop window snapshot |
| Telegram request 2150 | PARTIAL / terminal UNKNOWN | Ingress/ACK есть; Desktop task отсутствует; no retry |
| Activation rebind | PASS | Подписанная привязка нового revision; не readiness |
| Main startup после rebind | FAIL CLOSED | Нет свежей совместимой backup generation |
| Recovery stop acknowledgement | PASS | Точный production `pythonw.exe`, state `new` |
| Backup cold-start cycle | FAIL / UNLOCALIZED | Scheduler result `1`; journal не связывает failing attempt |
| Broad local run | INFORMATIONAL ONLY | Рабочая сессия зафиксировала 461 PASS и отдельную проблему C5, но raw отчёт не привязан к этому handoff; не считать формальным green suite |
| Полный независимый L1/L2/L3 | NOT RUN | Кандидат не заморожен |

После документной правки допустима только проверка JSON/ссылки/diff hygiene;
она не меняет этот тестовый журнал и не является новым L1/L2/L3.

## 8. Принятые архитектурные решения

1. Desktop — единственный исполнитель. Отсутствие owner не разрешает fallback.
2. UIA используется только для выбора существующего проекта и create/open;
   после owner discovery операции идут через owner IPC.
3. Только semantic selectors/patterns; никаких координат и ввода в произвольное
   активное окно.
4. Private IPC строго привязан к версии и profile; неизвестная версия — STOP.
5. Lost ACK → сначала readback фактического thread state; слепого повтора нет.
6. Request identity и delivery identity включают конкретный Telegram request и
   Desktop turn; одинаковый файл нового request — новая операция.
7. Один владелец отправки; callback, reconciler, skill и notifier не могут
   независимо доставить один и тот же полный результат.
8. Полный Desktop final передаётся без смыслового сокращения с Telegram
   formatting; файлы идут документами в исходную тему.
9. Вопрос получает автор request; approval/deny — только подтверждённый numeric
   owner user id. Username не является полномочием.
10. Штатные sandbox/approval механизмы Desktop сохраняются; bridge не повышает
    права и не обходит отказ.
11. Managed daemon и отдельный App Server не считаются обязательными. Их
    исторические результаты сохраняются как route-specific evidence.

## 9. Карта файлов для аудита

Основные новые/изменённые поверхности:

- `src/integrations/codex_desktop_ipc.py` — private IPC, framing, owner routing,
  ACK/events/readback/reconnect;
- `scripts/codex_desktop_uia.ps1` и
  `src/integrations/codex_desktop_uia.py` — semantic UIA;
- `src/application/desktop_bridge.py` — orchestration, policy, final/artifacts;
- `src/application/desktop_bridge_state.py` — durable state/idempotency;
- `src/integrations/nobus_document_delivery.py` — повторное использование
  document delivery;
- `src/transport/telegram/*` — команды, topic/request binding, Bot API;
- `scripts/run_telegram_mvp1.py` — composition, schema migration и activation;
- `src/application/runtime_maintenance.py` — backup/application binding inputs;
- `tests/test_codex_desktop_ipc.py`, `tests/test_codex_desktop_uia.py`,
  `tests/test_desktop_bridge.py`, `tests/test_nobus_document_delivery.py`,
  Telegram и runner regressions;
- `docs/adr/0029-telegram-desktop-owner-tunnel.md` и M2-DESKTOP документы.

Runtime-only evidence не добавлено в Git и находится под
`.runtime/m2-desktop-live-probe/`. В частности, диагностические JSON/ERR и
`probe_uia_selectors.ps1` — рабочие артефакты, не продуктовый код.

## 10. Приоритет независимого аудита

1. Проверить весь diff `f3fdb2d..3ea2438` на безопасность trust boundary,
   owner authorization, tenant/topic isolation и утечки payload/path/secret.
2. Проверить durable state machine: unique constraints, crash boundaries,
   UNKNOWN transitions, readback-before-retry и совместимость миграций.
3. Проверить single-sender invariant и матрицу callback/reconciler/notifier/
   `nobus-send-results`, включая новый request того же файла.
4. Проверить IPC parser: frame limit, partial frame, timeout, notification vs
   response, request id, version mismatch, reconnect и event correlation.
5. Проверить UIA backend: exact window/process binding, ambiguity stop,
   offscreen/focus handling, composer binding и отсутствие arbitrary input.
6. Проверить operational upgrade: application binding, activation rebind,
   admission, schema-before-backup, cold-start backup и rollback.
7. Проверить Telegram policy: закрытая группа, topic binding, author identity,
   numeric owner approvals, voice confirmation, formatting и file delivery.
8. Отделить fixtures от реальных доказательств D01–D17; не принимать Gate по
   количеству unit tests.

## 11. Безопасный протокол продолжения после аудита

1. Начать с read-only проверки Git status обоих checkout и текущего состояния
   трёх Scheduled Tasks; ожидается Disabled/Stopped.
2. Не повторять Telegram message `2150` и request
   `e18a5ca3-95d3-4be8-8453-630d88e97a50`.
3. Локализовать backup cycle result `1` новым конкретным диагностическим
   основанием. Не запускать цикл повторно, пока failing boundary не доказана.
4. После исправления создать одну свежую VERIFIED backup generation, снять
   admission hold штатно и доказать local/public readiness, один процесс,
   Health/Backup state и отсутствие pending/unknown delivery.
5. Только после восстановления production сформировать новый ограниченный live
   request и получить новое action-time подтверждение владельца.
6. Проверить исправленный create → owner → IPC turn → question/approvals → full
   final/file → reconnect. При lost ACK — readback, без resend.
7. Затем отдельно провести оставшиеся voice/two-topic/Arthur/D01–D17 проверки.
8. Заморозить один цельный кандидат и один раз провести независимый L1/L2/L3.
9. Публикацию, merge и принятие отличать от локальной реализации и активации.

## 12. Что нельзя повторять без нового основания

- managed daemon `remote-control start` с теми же binaries;
- read-only initialize/owner discovery как самостоятельное исследование;
- historical App Server create/read/writer-conflict experiment;
- Telegram message `2150` и его unknown request;
- backup cycle до локализации последнего result `1`;
- полный L1/L2/L3 до заморозки цельного кандидата;
- C6, MVP1 acceptance и 72-часовое наблюдение.
