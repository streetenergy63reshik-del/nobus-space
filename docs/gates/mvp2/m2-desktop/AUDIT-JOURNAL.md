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
  устанавливался, не обновлялся и не патчился; PATH, ACL и credentials не
  менялись. Позднейший независимый аудит восстановил UIA-действие по
  переключателю Bot to Bot Communication Mode в BotFather: это доказывает
  действие, но не текущую настройку и не приём сообщения Артура. Утверждение
  «BotFather не менялся» больше не является действующей квитанцией.
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

## 13. Журнал локального возобновления 24.09.2026

Этот раздел дополняет исторический журнал, не переписывая старые receipts.
Рабочий HEAD `31df0d00a0a74de920a7a7367d3b662566a653ff`, все изменения
пока незакоммичены. Не было новых внешних сообщений, Desktop turn, установки,
изменения notifier/skill, production start, push/merge/deploy.

| Граница | Факт / проверка | Решение / остаток |
|---|---|---|
| Grok GA/GB/GC/IN | SHA ZIP совпали с аудитом; импортированы шесть файлов. После адресных исправлений 100 тестов прошли. | Код используется в продуктовых границах, но ZIP и fixtures не являются D01–D17. |
| A01 backup rebind | Новая конфигурация и old phase=complete раньше отвергались до попытки. Адресный тест reconcile прошёл, старый сертификат сохранён. | Только локальная логика; живой цикл запрещён до точного разрешения. Весь файл C6-тестов повторно запускать отказал auto-review; обхода не было. |
| A02 stale approval | Тесты смены payload/turn и expiry во время history read не вызвали Desktop answer; CAS отвергает второй ответ. | Между последним read и IPC остаётся теоретическая гонка, как у любого внешнего API без условного ACK. Реконнект с новой generation при том же payload потребует отдельного подтверждения: попытка снять проверку generation в durable state была отклонена auto-review как риск устаревшего approval, изменение не применено. |
| A03 files | Markdown C:/..., backslash, explicit additional roots, reparse и sensitive filter проходят локальные тесты. | Корни должны быть явно включены оператором; live файл и два topic не проверены. |
| A04/A05 cards | Renderer показывает exact IDs и action scope, карточка остаётся literal/plain, numeric mention — HTML в исходной теме. | Получение каждого вида pending и фактический Telegram approve/deny ещё live. |
| A06 UIA | Python lock удерживается до owner correlation; PowerShell mutex и non-empty draft guard. Тест второго lock пройден. | После ручного UI-переключения нужен live stop-check; слепой retry запрещён. |
| A07/A08 | Reply, UUID/deep link, проект с пробелами и каталог проектов — локальные проверки. | Автоматическая полнота сохранённых проектов, managed worktree и mode parity не доказаны. Продукт по-прежнему передаёт Default; Plan question receipt относится к harness. |
| A09 | Новая команда redeliver вызывает только восстановление known partial без нового turn; unknown остаётся остановленным. | Shared skill runtime v1 ключует destination+digest; нужен совместимый operation-key и receipt, без второго sender и без изменения смысла destination_ref. |
| A10 | Продуктовый `_deliver` отправляет HTML `parse_mode`; test доказывает bold/code. | Длинный live ответ, часть/файл и Telegram receipt ждут разрешения. |
| A11 | Исправлены три битые ссылки, docs16 регенерирован; `tests/test_documentation.py` — 4 passed. | Machine EVIDENCE пересчитать на замороженном снимке; прежний digest не выдавать за текущий. |
| A12 | Флаг `--desktop-bridge` default false; runner + bridge тесты проходят. | Изолированный rollback/backup generation и readiness ещё не проведены, production не трогать. |
| A13 | Read-only verifier exact durable request/thread/turn отвергает поддельный/скопированный marker в unit-тесте. | Установленный notifier пока не вызывает verifier; не считать opt-out аутентичным. |

Последние целевые проверки: `tests/test_telegram_mvp1_runner.py` +
`tests/test_desktop_bridge.py` + `tests/test_desktop_notifier_auth.py` +
`tests/test_documentation.py` — 63 passed; затем inventory+bridge — 59 passed;
после redelivery bridge — 32 passed. Срезы различаются, повторный общий прогон
будет только по замороженному кандидату. `git diff --check` на момент проверки
не сообщал whitespace errors; после дальнейших правок проверить снова.

Поздний локальный связанный non-C6 regression-набор на текущем WIP: 12 файлов,
`287 passed` за 22,75 с на последнем WIP; `git diff --check` без whitespace errors. Этот
результат не заменяет independent L1/L2/L3 и не относится к live D01–D17.

### A09 — подготовленный sender-v2 patch (после 287-test среза)

Только в игнорируемой копии установленного `telegram_delivery_runtime.py`
проверен [минимальный patch](telegram-delivery-runtime-v2.patch): прежний v1
ключ остаётся неизменным; optional operation key различает новый запрос того
же файла; read-only receipt возвращает status/message_id. `git apply --check`
на свежей копии прошёл. Интеграционный adapter теперь передаёт стабильный
proof-bound destination_ref без request ID, отдельный request-scoped operation
key и принимает `sent_existing` только с числовой квитанцией. Тесты
sender/bridge/runner — 63 passed. Установленный skill не менялся: с его v1
adapter намеренно отказывает при opt-in. Автоматического решения для второго
skill-вызова из bridge-turn пока нет; A09 не закрыт полностью.

### A13 — локальный patch существующего notifier (24.09.2026)

Подготовлен [notifier-auth-v2.patch](notifier-auth-v2.patch) для двух файлов
существующего глобального notifier. Вместо подавления по пользовательскому
маркеру патч требует точную read-only связь request↔thread↔turn в durable
bridge DB. Неуказанный `bridge_state_path`, отсутствующий DB, поддельный
request и другой turn сохраняют обычное уведомление. `git apply --check` на
свежей копии источника прошёл. Функциональный тест на ранее подготовленной
локальной патченной копии и verifier — `2 passed`; вместе с sender-тестами —
`4 passed`. Применение patch через `git apply` к второй игнорируемой копии
получило отказ записи песочницы; установленный notifier и его config не
менялись. Это не доказательство production opt-out: A13 открыт до разрешённой
установки и проверки обычной/bridge-задачи, включая сбой доставки.

После изменения sender-adapter полный связанный non-C6 набор 12 файлов на
текущем WIP — `187 passed` за 18,46 с. Ранее полученные `287 passed` относятся
к другим bytes; полная независимая проверка замороженного кандидата не
проводилась. В тестах не было новых Desktop turn или Telegram-доставки.

После этого текст IPC turn получил явное правило единственного владельца
доставки: модель не должна вызывать `nobus-send-results`, поскольку Bridge
сам доставляет итог и файлы. Адресные bridge-тесты — `33 passed`, после них
повторён связанный non-C6 набор на новых bytes — `187 passed` за 20,08 с.
Это снижение риска, но не исполнимая блокировка стороннего skill-вызова; A09
остаётся открытым.

## 24.09: проверка обновлённого Desktop и установка общего runtime

Установленный Desktop обновился до `26.917.9434.0`. Read-only IPC
initialize/owner/history текущей задачи и semantic UIA selector существующего
проекта прошли. В новых `latestThreadSettings` подтверждены default,
on-request, auto_review и workspaceWrite; это не полный паритет tools.
До и после проверки не отправлялись новый Desktop turn/approval.

Sender: исходный installed runtime совпал с manifest; патч A09 применён
к тому же файлу. Hash установленного файла
`72b7cff9c49a925d6bb6030b8c976b434e43e96f1d9dd98f7d5b05463c9d5207`
совпал с тестовой копией; self-test и регрессии v1 прошли. Новой
Telegram-доставки не было.

Notifier: первоначальный выпуск A13 был подтверждён и установлен, но
конфигурация с изменением `bot_repo` отклонена auto-review как переход
trust boundary; отказ не обходился. Вместо этого создан самодостаточный
read-only verifier в существующем core. Актуальный патч
[notifier-auth-v3.patch](notifier-auth-v3.patch) применён к чистым локальным
копиям; hashes совпали с установленным выпуском. Его SHA
`3befa848059448783b2f5f2b270078a4240226485390d9b76c9eb93e7bfef08a`
подтверждён владельцем. Первая установка была отклонена из-за опечатки
в подтверждённом SHA, вторая — из-за другого Python относительно
Scheduled Task. После read-only выяснения точных причин штатная установка
через прежний проектный `.venv` прошла: задача планировщика не создана
заново, settings/credentials не изменены установщиком, Telegram не вызван.
Отдельно добавлен только явно подтверждённый `bridge_state_path` в JSON.
Installed verifier загрузил настройки, увидел production SQLite и отверг
несуществующую request/thread/turn связку. Положительного live-подавления
ещё нет.

Целевой набор текущего WIP: `65 passed, 1 skipped`. Два первых запуска
давали 50 setup errors из-за отказа записи pytest tmp, а не ошибок продукта;
запуск с временной папкой в назначенном worktree прошёл. Это не полный
Gate suite, не L1/L2/L3 и не D01–D17. Production bot tasks остаются Disabled.

Read-only разбор старого Backup result `1` дал конкретную причину.
`--inspect-failure` из production checkout успешно проверил конфигурацию
и подписанный журнал, `phase=complete`; текущая Scheduled Task передаёт
digest `7c3876…`, журнал связан с `2051b0…`. Вызов inspect из WIP
worktree сначала дал общий FAIL из-за другого application binding;
его не принимали за состояние production. Production-скрипт без A01
отказывает на mismatched completed journal. Сам цикл не повторялся;
три production tasks оставлены Disabled. Следующее изменение требует
контролируемого deploy A01, новой проверенной backup generation и readiness.

Ровно один согласованный smoke существующего notifier после выпуска:
завершённый turn `01a0d2d7-7499-7e73-83fe-591580c11061` в тестовой
задаче `01a0c45d-e9f8-7f81-a7b5-eb29818e33a5`; local rollout содержит
один `task_complete` с тестовой фразой, one-shot ledger exact event key —
`sent`. Проверка не относится к bridge-auth positive path, полному
Telegram-ответу или D01–D17.

### Продолжение: fast-turn и production wiring (24.09)

| ID | Новый воспроизводимый факт | Исправление и проверка | Остаток |
|---|---|---|---|
| M2B-012 / A13-D15 | Bootstrap turn UIA не был привязан к durable request; установленный v3 notifier мог отправить summary до bridge final. | Red-тест `AttributeError` для `bind_bootstrap_turn`; затем аддитивная миграция, точный turn binding и v4 notifier с ограниченным ожиданием записи. Патч на v3-копию совпал побайтно с исходником. Canonical package: `91 passed, 54 subtests`; release SHA `e6e08ba29097b3a35e58f43cf2a7619778b95bf72561d23499c31e91a6479eda` подтверждён и установлен; installer не менял settings/credentials и не вызывал Telegram. | Позитивный живой opt-out и один полный итог в исходной теме не проверены. |
| M2B-013 / A12 | Production Scheduled Task через supervisor не передавал Core `--desktop-bridge`; прежний backup запустил бы только MVP1. | Три red-теста, затем opt-in цепочка installer → supervisor → Core, точная привязка каталога проектов и явных корней артефактов. PS Parser 0 errors; целевые 5 tests PASS. | Остановленный production ещё не обновлён; staged action/activation/readiness нужны на точной версии. |
| M2B-014 / A01-A12 | Аддитивный столбец меняет DDL, а backup проверяет точные хэши; новый application не мог бы подтвердить старую БД до Core startup. | Red-тест свежей схемы, два точных разрешённых DDL-хэша, миграция только известной прежней DDL под admission hold в A01 reconcile. Fresh+migrated content validation и one A01 test PASS (`7 passed` вместе с новыми тестами). | Неизвестная схема отвергается; реальная новая backup generation и rollback не проверены. |

После этих правок общий связанный срез до последнего A01 helper —
`295 passed, 1 skipped`; затем на последних кодовых bytes связанный набор
и четыре адресных совместимости дали `301 passed, 1 skipped`.
Неиспользуемый локальный verifier-дубль и его тест удалены по двум точным
путям после отказа `apply_patch`; установленный runtime не затронут.
Production bot tasks остаются остановленными и
Disabled. Ни одного нового продуктового Telegram-запроса или Desktop turn
не отправлено. Gate не заморожен, не опубликован и не принят.

### L3 на checkpoint `9cefc58` — новые локальные исправления

Чистый экспорт checkpoint `9cefc58` дал `compileall` PASS и `296 passed,
1 skipped` в 13 M2-файлах; ZIP SHA-256
`f1ed957a6858dffe78ace764662eca4a633c22b52910c8aab4f3c8839bcce7d5`.
Это независимый по среде локальный прогон, но не live D01–D17 и не проверка
последующих WIP bytes.

| ID | Воспроизводимый дефект | Решение | Остаток |
|---|---|---|---|
| M2B-015 / D08 | `requestUserInput` с просьбой «Разрешаете удалить файл?» уходил автору как обычное уточнение. Red-тест показал `tg://user?id=41`, требовался owner `99`. | Консервативный фильтр явных просьб о согласии и побочных действиях; такие и неизвестные контейнерные поля уходят владельцу для ручного ответа только в Desktop. Обычное уточнение остаётся автору. | Private IPC не даёт подтверждённого provenance для всех семантических форм; реальный App/MCP-вариант и текстовое разрешение требуют live доказательства. |
| M2B-016 / D08 | Потерянный ACK Telegram на вводной карточке оставлял pending без message id; crash/restart мог отправить её повторно. Red-тест воспроизвёл исключение после принятого сообщения. | Durable CAS `pending→unknown` перед I/O и `unknown→pending` лишь после подтверждения всей карточки. При lost ACK автоматическая отправка не повторяется; перезапуск SQLite проверен. Схема не менялась. | Фактический Telegram receipt при неопределённом исходе требует ручной сверки; продуктовый live crash/recovery ещё открыт. |

После исправлений `tests/test_desktop_bridge.py` — `39 passed`, затем
13 связанных M2-файлов — `206 passed, 1 skipped`. Первый вызов red-теста
попал в старый недоступный `basetemp` и завершился setup `WinError 5`;
новый отдельный `basetemp` показал ожидаемый продуктовый FAIL. Отказ доступа
не обходился и не трактовался как дефект bridge. Production и Telegram не
менялись. Новый цельный кандидат ещё не заморожен.

Новый локальный commit `007c6540408fb446634e10d26eb01bffed1ca050`
(tree `b1331e4a22d754128e76191a47211d106011f9ee`) был проверен
чистым Git ZIP-экспортом SHA-256
`611cd804108a3ac0dc951f78bf0f4b2fdcffd932a5a7ac62df2e510745ec5d49`:
`compileall` PASS, `206 passed, 1 skipped`. Архивный digest файлов
`sha256:0639234b255fd2ce1a534bd797a66d49422ef704654388e5913ecd1921c968b4`
не равен digest source worktree, потому что `git archive` применил CRLF
к тексту (например, 2061/2061 переводов строк в `desktop_bridge.py`
против 0/2061 CRLF в рабочей копии). Это два явно разных byte-снимка,
не ошибка тестов и не разрешение переиспользовать произвольный digest.
