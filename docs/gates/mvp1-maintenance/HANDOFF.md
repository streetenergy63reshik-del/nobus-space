# M1-S1 — HANDOFF

**Checkpoint 14.09.2026, 21:17 МСК:** published release остаётся v1.0.2; production в этом продолжении не изменялся. Пятый frozen candidate `5b743680eaee4b43fd4912f916c52ea1a8ed1080` восстановлен по clean HEAD и внешней квитанции и отклонён по собранному review. Проверенный пакет ремонта кода — `23e47414932e236824c0d48430addac3cb4e9f88` (предыдущий checkpoint `180ac12e1e83f1f1f4217acdba15eb9214692890`). Точная итоговая revision/tree после этого документа связывается одной внешней freeze-квитанцией; до её создания пакет DRAFT.

## Конечный результат и границы

M1-S1 завершается безопасным различением новых завершений, ограниченным восстановлением transient-отказов и понятным STOP при permanent/UNKNOWN/exhaustion; одним Core/Job/lease без повторения неизвестных effects и потери accepted tasks; совместимостью с backup; проверенным переходом, реальной задачей и TXT и началом согласованного наблюдения. Старый первичный trigger может остаться UNKNOWN. Отсутствующие исторические журналы не являются основанием для бесконечного поиска. Необязательные усиления не расширяют ремонт.

Зона владельца пакета: supervisor, два installer, Scheduler fixture, относящиеся tests, Runbook/CURRENT и этот Gate-пакет. Подготовленный docs01 сохранён; документ 11, C6 receipts, sealed sources, старые backups и recovery refs не менялись.

## Сохранённые доказательства

Внешние freeze/JUnit-квитанции находятся в указанном владельцем каталоге Codex visualizations / 2026 / 09 / 13 / 01a09c25-1d78-73e2-8691-be3db59a9fd1. Результаты Scheduler fixture сохраняются в изолированном worktree, `.runtime/m1-s1/scheduler-fixture/<run_id>/result.json`.

- Пятый кандидат: tree `cea7a00248d8c8bbd564d153436f967ab75f924c`; freeze SHA-256 `ba464970889610e1e264c3e05fd34aecbdbc3efc215425e73d620e3cf59505d4`.
- Существующие 218 PASS: `m1-s1-wip-dependent-host-20260914-1844.xml`, SHA-256 `3d9083ae2049d4e1e2123f495af6ee9dfb426f00c1bcc1a1ff6a4e8c52b4b200`; code/test/input blobs сверены с пятым freeze в `m1-s1-junit-binding-5b74368.json`, SHA-256 `6d0e39a4bdbcc00683c88c2411fdd20177966e36f2c0d3120d57b0e454066133`. Смена WIP → frozen сама по себе их не обнуляла. Для изменённого кода ниже получено новое evidence; неизменные Core/contracts не переоткрываются.
- Попытка `4f4d9f130bbc4f21a800d754e5e0fd1b`: exact tasks/process/result отсутствовали при повторной сверке; исход не объявлен успешным. Квитанция reconciliation SHA-256 `169df3171a84d724ca68394b385363062e15d919b3b4700b43fb42cd048658ce`.
- Попытка `a50f1e4a20a24721a43b43c2847395ee`: FAIL `fixture_observation_failed`, rows пустые, cleanup proven; SHA-256 `a70601cbaffdf40bf382051cc2c565dbeb4830b4767ac9656db9713ad2c2bef7`. Проверяющий запущен в Windows PowerShell 5.1 при использовании API PowerShell 7; до product attempt не дошёл.
- Текущий целевой набор: 137 PASS, `m1-s1-wip-dependent-09.xml`, SHA-256 `bb655c4994b070ad2f9263f7f77a8f6bdcb21ae8e63439a190e160e2771bd804`. Зависимые C5 runtime/ops: 56 PASS, `m1-s1-wip-dependent-c5ops-03.xml`, SHA-256 `8457a0909b4ff7a521e9d8f60cd52c51450fe3878a53198b6f1d554f2ef1a433`. Оба запуска — Windows identity владельца и отдельный pytest mutex namespace, без production/model/ASR.
- Отрицательная проверка WPS 5.1: run `2f0d0c98df5b49d1b61ed44fe0c7e372`, точный `fixture_runtime_unsupported` до регистрации; cleanup proven, tasks/processes отсутствуют; result SHA-256 `d380d8547b73352b1fa87de501c98b346a69d124f90d5a859262fca332ebda4b`.
- D01: прежние inventory/tool/requirements неизменны, 80 packages/15 pins/0 mismatch; inventory digest `c4b1be2c5795df1c19722441f157264ce7041558c616e26df98e67037c905be7`. OSV finding относится к pip 25.0.1 вне runtime Actions; пакеты не менялись.
- Security: повторный scoped scanner даёт тот же report SHA-256 `54d33ab1ef098a5d5b31a00f4ccfa793803fb81d950cee857ce8734eeb4192f8`: 42 findings, включая 6 synthetic fake-secret fixtures; новых findings в изменённых файлах нет. Классификация сохранена.

## Собранные замечания пятого кандидата и ремонт

L1: FAIL из-за проверяющего, product blockers не найдено. L2/L3: FAIL/REWORK. Все обязательные замечания собраны до исправления: совместимость fixture с PowerShell, поздние child exits в cleanup, пропавший current при первой rotation/compaction/latch-clear failure, backup trigger в далёком будущем, частичная замена Scheduler tasks.

Пакет закрывает эти случаи целевыми тестами: типизированный отказ неподдерживаемой среды до регистрации; late Core/relay exit фиксируется до принадлежащего supervisor завершения; только exact authenticated latch позволяет материализовать control failure после прерванной rotation; backup start не позже ближайших локальных 03:30; installers проверяют старые XML/launcher digests, сохраняют rollback bytes, ставят задания disabled и при промежуточном отказе оставляют их отключёнными.

Инициализация/rebind/inspect/acknowledge допускают профиль всех трёх disabled заданий с теми же signatures под production mutex. Обычный run этот профиль отклоняет. После включения binding сохраняется. Смешанный профиль запрещён, кроме уже аутентифицированного backup перехода с disabled health. Staged backup получает ближайший будущий trigger, чтобы включение не проигрывало пропущенное время. Это минимальная правка безопасного переключения.

Необязательные P2 (дополнительные principal fields, усиление alert, детальные fixture substages, независимый parser auth) сохранены отдельно; точного нарушенного обязательного контракта в текущей области для них не установлено.

## Оставшиеся блокеры и переход

1. Проверить изменённые документы, записать одну внешнюю freeze-квитанцию итогового commit/tree/assets/config/input digests.
2. Выполнить three-case fixture этой revision через точный PowerShell 7: transient recovery, budget exhaustion, permanent STOP и доказанный cleanup. Использовать новый run id после сверки предыдущих effects.
3. Передать этот же freeze существующим L1/L2/L3 с прежними findings и применимым evidence. Собрать все verdicts; до aggregate PASS production закрыт.
4. Перед activation обновить LIVE inputs (сейчас PENDING), refs/status, backup и baseline. Выполнить разрешённые publication и переключение; проверить реальный результат/TXT и сохранность.
5. Только после фактической activation создать heartbeat этой же задачи: 72 часа включённого ПК, каждые 30 минут, минимум две плановые backup; gap >60 минут начинает окно заново; уведомления только об изменении/сбое/завершении. Автоматический restore/reset/restart heartbeat не выполняет.

Production-план: свежая проверенная v1.0.2 generation; baseline tasks/receipts/offset и exact XML/config hashes; admission hold; штатный STOP и доказательство отсутствия exact процессов/Job/lease/listener; только три production task disabled; сохранить rollback bytes; опубликовать проверенный source через защищённую main без перемещения v1.0.2; clean LIVE на проверенном source; staged main/health/backup с candidate-bound config и точным readback; initialize/rebind при всех disabled; включить задания и контролируемо запустить candidate backup cycle, который сохраняет hold, останавливает runtime при необходимости и создаёт новую связанную generation до своего разрешённого старта runtime. До завершения baseline/backup/readiness hold не снимается. Затем один Core/Job/lease, local/public/stock readiness, одна квалификационная text-задача (model 1, ASR 0), правильный результат/TXT и post-baseline. Плановая пауза до 20 минут; при превышении остаётся STOP до диагностики. UNKNOWN эффект сначала сверяется. Rollback совместимых code/config/task bytes — по решению владельца; БД поверх новых accepted tasks не откатываются.

Разрешения владельца на необходимые действия и число запусков сохраняются; повторное подтверждение только из-за новой revision не требуется. Автоматический отказ среды фиксируется отдельно и не обходится.

Последний production read-only срез 14.09, 15:34–15:37 МСК: LIVE `82003c03…`, runtime DOWN; 86 tasks, 84 ACK receipts, 14/14 parts, четыре БД healthy, queue пустая, unknown=0, reconciliation=false, offset 375633467/revision 44146. Эти значения — исторический baseline, не свежие preconditions.

Раздельный verdict: published release — v1.0.2 unchanged; repaired candidate — проверенный код, финальный freeze/review pending; deployed runtime — без изменений, последний срез DOWN; stability observation — NOT STARTED; M2-G0 — BLOCKED.

## Архив предыдущих checkpoint

Ниже сохранена история прежних решений и проверок. Старые статусы и разрешения не заменяют текущий раздел и свежие внешние readbacks.

## Канонические refs и границы

| Объект | Значение |
|---|---|
| Published product/tag | `v1.0.2` → `82003c03d8a36015703472b472640ab4021fb416` |
| Remote main до M1-S1 | `88e58c8866db2384423f2b154df901a2e4af6c48` |
| LIVE | clean detached `Code/worktrees/telegram-live` на `82003c03…` |
| StateRoot / BackupRoot | canonical `.runtime/production-c6/migration-01/state` / `.runtime/production-c6/backups` |
| Ветка Gate | `codex/m1-s1-stability`, изолированный worktree |
| Текущий WIP | parent `e357629…`; exact candidate фиксируется только post-commit freeze receipt |

C6 не повторяется, MVP2 не запускался. Документ 11, исторические C6 receipts, sealed sources, старые backups и recovery refs не изменялись. Публикация и activation — разные статусы; tag v1.0.2 не перемещается.

## Свежий production-срез

Read-only проверка 14.09.2026, 13:57–13:59 МСК:

- main enabled/Running, LastTaskResult `267009`; legacy `RestartCount=10/PT1M` ещё действует;
- Health enabled/Ready/0; Backup enabled/Ready/0, daily 03:30 МСК;
- один logical supervisor (два venv host), два gated helper, один relay, одна Core chain; listener `127.0.0.1:8765` принадлежит Core;
- local readiness `true`, public readiness `true`;
- четыре БД healthy; 86 tasks/ingress, 168 audit events, 7 sealed answers, 84 ACK messages/receipts, 14/14 delivery parts;
- queue пустая, active job leases `0`, `delivery_unknown=0`, `reconciliation=false`;
- polling offset `375633467`, revision `43983`, один active polling lease; task/receipt/delivery counters не изменились;
- generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`, manifest `sha256:575a2f272f7c48810fbb4c44d88215bcba2556dc01fb0c95a396c75ad93ae84e`: authentication/binding/ciphertext PASS, возраст `37840.017` с (<24 ч);
- restore не запускался.

Первая попытка проверки backup использовала неверный путь без `snapshot` и дала безопасный `backup_unverified`. После read-only inventory проверен правильный `snapshot/manifest.json`, получен PASS. Это ошибка диагностического пути, а не состояние копии.

Срез подтверждает доступность принятого runtime только на этот момент. Он не объясняет остановки 10–13 сентября, не доказывает recovery нового кандидата и не считается 72-часовой устойчивостью.

## Отклонённые снимки

1. `73ed1c95ff81f4c087bd7bc7e5d468e09cc8b1a6`, tree `2ca97f0a4b8a2a0fb6f534e211a636efe065c99c`: L1 FAIL, L2/L3 REWORK. Freeze receipt SHA-256 `90a20f87c36e8baf83fa166fcbedd1b8560001b361d9752cf664b86b05f2aaf8`.
2. `19c9bf3b790f411790191d58c6110817ae887d3f`, tree `340c37763e5164cb5163454d698d03ac90281a54`: L1 PASS, aggregate FAIL. Freeze receipt `m1-s1-source-freeze-19c9bf3.json`, SHA-256 `b0e449d82ec1404bfd6d864ac571f20dbdc841cddc5246b550d41634df8b404a`; review receipt `m1-s1-review-evidence-19c9bf3.json`, SHA-256 `a65bf4de927628d2a545cbe2ed27631265d4b005ec3d5d237830db9517e7b682`.
3. `121a4df400a6bed01427e48f9aa66eb2822852db`, tree `e35b662538aa5b6470eca4aea8356ef12286163f`: aggregate FAIL; freeze receipt SHA-256 `505749417eccdb67fe10ea87868b9d520547754b24c29519942ed93df3bb7663`.
4. `e357629859f728bf3403174a25a7a64c90d0d830`, tree `225a7000cc470e4bb011a4e3d5f7567182d17915`: L1 PASS, L2/L3 FAIL, aggregate FAIL; freeze receipt SHA-256 `930af8bd2aa57730015e413a99be2af1817e34ee11b6e76d8c6b52ce08540fc0`.

Evidence этих ревизий архивно и не переносится на новый candidate. Fixture `9af4c7e28d6b41d0a735e2f6b8c1934e` относится только к `19c9bf3…`: он доказал transient recovery и exhaustion, но не отдельную permanent ошибку.

## F01–F04 / D01

| ID | Класс | Состояние |
|---|---|---|
| F01 | FACT + UNKNOWN | Core/relay/simultaneous exit, local/public/both readiness, startup timeout, planned stop и cleanup различаются. Child exit после blocking probe теперь имеет приоритет. Исторический trigger 10–13 сентября остаётся `UNKNOWN` |
| F02 | FACT | Core JSON ≤4096 bytes и exact allowlist. History v3 хранит run/stage/error/exit, readiness, attempt/budget и cleanup; raw streams, argv/env, payload, task text и credential paths не сохраняются. Ранние CLI/control failures получают typed exit и bounded fallback receipt |
| F03 | FACT | Старый `RestartCount/PT1M` не перезапустил normal exit 23. Recovery остаётся внутри одного action, только после proven cleanup. Fixture v3 разделяет transient→attempt2, repeated transient→budget STOP attempt3 и permanent Core FAIL→один attempt/`stop_non_retryable`. Real Scheduler run нового freeze pending |
| F04 | FACT | Подготовленные docs01/CURRENT/runbook сохранены и включены. Документ 11 не редактировался: его digest теперь обязательный activation input |
| D01 | FACT + REVIEW | Python 3.12.14, 80 installed, 15 direct pins, 0 mismatch. OSV matches только у `pip 25.0.1`; pip не входит в runtime requirements/action. Install, upgrade, rebuild и package operations запрещены |

## Исправленный recovery-контракт

- `starting` записывается до проверки runtime inputs, Job API и operator log. После него есть exact terminal либо durable `control_failure`; ошибка history сохраняет класс `runtime_event_write_failed`.
- Terminal parser проверяет точную матрицу stage/error/status/child exit/readiness/count/outcome/cleanup.
- После каждого blocking readiness probe child проверяется снова; перед readiness terminal есть bounded propagation check.
- Каждая v3 запись аутентифицирована DPAPI текущего Windows owner и связана digest-chain. Checkpoint допустим только второй записью физического `.previous`, никогда в `current`.
- Reset требует exact newest authenticated digest. Отдельный owner-authenticated latch сохраняет pre-control failure до материализации в `control_failure`; потеря/подмена latch, сегмента, reparse, hardlink, extra/oversize/invalid file, append/fsync/rotation failure дают STOP.
- Operator log имеет fixed parser и current+previous по 5 MiB. Fallback CLI log — current+previous по 128 KiB, строка ≤2048 bytes, fixed schema и DPAPI authentication.
- Exit `70/71/72/73/74/75/76/77/78/79/80` различает create/signal/close/evidence, composition, activation binding, busy control, rejected reset, blocked history, startup и rebind.
- Retry разрешён только exact allowlisted transient после proven cleanup; permanent, missing/invalid outcome, cleanup/evidence failure, UNKNOWN и exhaustion дают STOP.

Trust boundary: Windows owner — control authority. DPAPI защищает от другого пользователя и offline-подделки; произвольный код того же owner уже имеет эквивалентный доступ к StateRoot/БД и вне этой границы. Core/relay не имеют команды reset; недоверенные Codex workers остаются в существующей sandbox/Job-изоляции. Секретный key file не создаётся.

Activation binding v3 включает source/code/schema, exact StateRoot, semantic flag, hashes документа 11, двух local config и Mini App assets, voice inventory, BackupRoot/ownership, Python/pythonw/base runtime и installed distributions/requirements, health launcher и фактические main/health/backup Scheduler signatures. Он также связывает principal SID, trigger identity/time и все влияющие task settings. Изменение любого input требует нового binding и явного bootstrap/rebind после сверки.

## WIP-проверки

- новый targeted supervisor/rework/L3 набор: `118 passed`;
- affected/dependent набор под реальной Windows identity и отдельным pytest mutex namespace: `218 passed`;
- sandbox-only identity mismatch воспроизведён отдельно; те же три проверки под владельцем: `3 passed`;
- Python AST, PowerShell parser, EVIDENCE JSON и `git diff --check`: PASS.

Real fixture новой ревизии, D01, security audit и L1/L2/L3 привязываются только к следующему source freeze. C0–C6 целиком не повторяются.

## Следующий checkpoint и production-план

1. Зафиксировать один source candidate и внешнюю receipt с commit/tree/source/assets/config/input digests.
2. На нём выполнить real Scheduler fixture v3, D01 без package operations, scoped security audit и независимые L1/L2/L3.
3. После aggregate PASS: fresh pre-change backup, baseline, exact XML/config export, planned stop exact supervisor/Job, свободные port/mutex/lease.
4. Опубликовать candidate через protected main, без нового tag и без перемещения v1.0.2.
5. Отключить остановленные exact задачи; заменить backup только через `-ReplaceExisting`, затем main/health, сделать readback; переключить LIVE на exact reviewed source commit и candidate-bound config.
6. При остановленном runtime выполнить explicit initialization полного activation binding; candidate backup cycle запускает ровно один runtime.
7. Проверить один Core/Job/lease, local/public/stock readiness; одну разрешённую text-задачу, результат/TXT и post-baseline. UNKNOWN сначала сверяется, blind retry запрещён.

Бюджеты: одна activation, одна реальная text-задача, максимум один model execution, ASR `0`. Ожидаемая пауза ≤15 минут; через 20 минут без сигнала — STOP/diagnosis. Rollback только совместимого code/config; БД не откатываются поверх новых accepted tasks.

## Согласованное наблюдение

После T0 эта же задача создаёт heartbeat каждые 30 минут. Он только читает Scheduler, authenticated history/fallback, readiness, exact process/listener/lease, DB counters и backup manifests; auto restart/reset/restore отсутствует.

PASS требует непрерывных 72 часов включённого ПК и owner session, минимум двух planned daily backup с LastTaskResult 0 и authentication/binding/ciphertext PASS, отсутствия необъяснённых terminal events, одного runtime и сохранности данных. Gap >60 минут начинает окно заново. Старый 15-минутный smoke не считается устойчивостью.

## Раздельный verdict

| Слой | Статус |
|---|---|
| Published release | v1.0.2 / `82003c03…` неизменён |
| Repaired candidate | WIP GREEN; source freeze/reviews pending |
| Deployed runtime | accepted `82003c03…`, currently DOWN |
| Stability observation | AGREED, NOT STARTED |
| M2-G0 | BLOCKED |

## Архив состояния до отклонения `19c9bf3…`


**Текущий статус 14.09.2026, 12:28 МСК:** замечания по первой отклонённой ревизии собраны и исправлены одним WIP-пакетом. Implementation checkpoint `87dba94ab340f5b335f0779043c948b7ac5671b3`, tree `3a5408aa630070f247f5b3069311cd08585b4a0a` локально GREEN. Единственный новый Gate freeze, реальный Scheduler fixture v2 и независимые L1/L2/L3 ещё не выполнены. Принятый v1.0.2 остаётся в LIVE; это не PASS 72-часового наблюдения.

## Текущий checkpoint после rework

Freeze `73ed1c95ff81f4c087bd7bc7e5d468e09cc8b1a6` / tree `2ca97f0a4b8a2a0fb6f534e211a636efe065c99c` отклонён: L1 `FAIL`, L2/L3 `REWORK`. Его нельзя публиковать, развёртывать или смешивать с доказательствами нового кандидата. Внешняя квитанция этой ревизии сохраняется с SHA-256 `90a20f87c36e8baf83fa166fcbedd1b8560001b361d9752cf664b86b05f2aaf8`.

Все замечания первой ревизии были собраны до пакетных исправлений. Закрыты: privacy temp path; гонка planned stop/Core exit; общий local/public probe slot; сброс STOP удалением recovery history; неустойчивые control failures; неполный fixture; safe-shaped вместо exact Core allowlist; retry без точного `STOPPED`; отсутствие полной hash/transition chain; raw health redirects; parser/D01 и stale active docs.

Новый стабильный freeze id — `a8e7a1f0330f4f889263ed2751d3eee8`. Самоссылочный commit нельзя включить в собственные bytes, поэтому этот документ хранит exact implementation checkpoint, а commit/tree/source/assets/config/input digests следующего документационного commit будут один раз записаны во внешнюю post-commit квитанцию с этим id. Только эта ревизия получит реальный Scheduler fixture v2 и L1/L2/L3.

### Актуальный production-срез

Read-only срез 14.09.2026, 12:20–12:26 МСК:

- LIVE clean detached на `82003c03d8a36015703472b472640ab4021fb416`; `origin/main` — `88e58c8866db2384423f2b154df901a2e4af6c48`;
- main enabled/Running с 03:31:05 МСК, LastTaskResult `267009`, legacy `RestartCount=10/PT1M`; Health Ready/0 в 12:20:44 МСК; Backup Ready/0, следующий запуск 15.09 в 03:30 МСК;
- один logical supervisor (venv host+child), два gated helper, один relay, один Core chain, один listener `127.0.0.1:8765` и один active polling lease;
- read-only probe вне сетевого sandbox: `local_ready=true`, `public_ready=true`; sandbox-only public FAIL отброшен как ограничение инструментальной сети, а не production факт;
- четыре БД healthy; 86 tasks/ingress, 168 audit events, 7 sealed answers, 84 ACK messages/receipts, 14/14 delivery parts; queue пустая, active job leases `0`, delivery unknown `0`, reconciliation `false`;
- offset `375633467` не уменьшился, revision вырос до `43607`; tasks/receipts не изменились;
- generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c`, manifest `sha256:575a2f272f7c48810fbb4c44d88215bcba2556dc01fb0c95a396c75ad93ae84e`, authentication/binding/ciphertext PASS, возраст `32082.868` с. Restore не запускался.

Эти факты подтверждают доступность принятого runtime на момент среза, но не объясняют остановки и не доказывают recovery или 72 часа.

### F01–F04 / D01

| ID | Текущее состояние |
|---|---|
| F01 | Core/relay/simultaneous exit, local/public/both readiness, startup timeout, planned stop и cleanup различаются. Исторический trigger 10–13 сентября остаётся `UNKNOWN` |
| F02 | Локально repaired: exact Core failure allowlist, один ASCII JSON ≤4096 bytes, no raw persistence; `nobus-runtime-event-3` хранит binding, linked digests, run/stage/error/exit, local/public, attempt/budget и cleanup |
| F03 | Локально repaired, но real v2 pending: один Scheduler action, budget `10 retries / 60 s / 11 total`, retry только после proven cleanup; missing/invalid/binding mismatch, UNKNOWN, permanent и exhaustion дают STOP |
| F04 | docs01/CURRENT/runbook входят в пакет; документ 11, C6 receipts и sealed sources не менялись |
| D01 | Local inventory проверяет actual environment, exact pins и duplicate inputs. Frozen network metadata query ещё не выполнен; install/upgrade не выполнялись |

История recovery находится только в `<StateRoot>/supervisor-control`. Первый запуск требует отдельного `--initialize-recovery` под production mutex. Каждая v3 запись связана с предыдущей; reset требует exact newest digest. Ротация — current+previous по 1 MiB, строка ≤2048 bytes; отсутствие любого сегмента после ротации, лишний/reparse/oversize файл, parser/write/fsync/rotation error блокируют запуск. Fixed operator log также ограничен двумя файлами по 5 MiB. Exit `70/71/72/73` различает create/signal/close/evidence failure. Child exit проверяется раньше planned stop; permanent Core FAIL и invalid/missing outcome побеждают retry.

In-place backup/restore меняет только четыре БД, поэтому control history сохраняется. Если StateRoot реконструирован или control directory утрачен, обычный start даёт STOP; bootstrap новой binding разрешён только после сверки данных/effects. Удаление истории не является reset.

### Текущие проверки

- initial rework RED: `13 failed`;
- расширенная rework-матрица: `24 passed`;
- затронутый набор C5 runtime + M1-S1: `116 passed in 18.60s`;
- зависимые host-context tests: `34 passed in 32.35s` с отдельными mutex/temp roots;
- Python AST, PowerShell parser и `git diff --check`: PASS; C0–C6 целиком не повторялись.

### Следующая точная проверка

После commit документационного checkpoint внешняя квитанция фиксирует единственную Gate revision. Fixture v2 создаёт ровно два уникальных one-time tasks с canonical `pythonw`, Interactive/Limited, `IgnoreNew`, Scheduler restart count `0`. Transient обязан завершиться на attempt 2 / LastTaskResult 0; permanent — на attempt 3 / budget STOP / LastTaskResult 23 и без четвёртой попытки 75 секунд. Result включает controller/probe digests, hashes v3/operator segments, финальные attempt/budget/disposition/cleanup и proven удаление tasks. Та же frozen revision проходит D01 metadata и scoped static/manual security audit без установки пакетов; затем L1/L2/L3 проверяют этот же commit.

### Production и 72 часа

После PASS reviewers: fresh backup → baseline → штатная остановка exact Job → свободные port/mutex/lease → exact LIVE checkout → Tasks с Scheduler retry `0` → recovery bootstrap → один start → local/public/stock readiness → одна text-задача и TXT → post-baseline. Бюджеты: одна activation; одна text-задача и максимум одно model execution; ASR `0`; UNKNOWN сначала сверяется; БД не откатываются. Ожидаемая пауза до 15 минут, после 20 минут без проверяемого сигнала — STOP и диагностика.

После фактического T0 heartbeat этой же задачи каждые 30 минут только читает Scheduler, v3, readiness, singleton/process/listener/lease, DB counters и backup manifests. Никакого auto reset/restore/restart. PASS требует непрерывные 72 часа включённого ПК/owner session, минимум два planned backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой, один runtime и сохранность данных. Разрыв более 60 минут запускает окно заново. Старый 15-минутный smoke не считается устойчивостью.

Раздельный verdict: published release — `v1.0.2` неизменён; repaired candidate — implementation GREEN, freeze/reviews pending; deployed runtime — прежний `82003c03`; observation — NOT STARTED; M2-G0 — BLOCKED.

## Архив первой отклонённой ревизии

Весь текст ниже — сохранённый pre-freeze record `73ed1c9`. Он нужен для истории RED/diagnosis, но его утверждения о «исправленном реальном fixture» не являются доказательством новой revision.

### Архив: результат pre-freeze этапа

Исторический первичный триггер остановок 10–13 сентября восстановить нельзя: он остаётся `UNKNOWN`. Отдельно воспроизведена причина отсутствия recovery: на этом хосте `RestartCount/PT1M` не перезапустил нормально стартовавший `pythonw` после exit 23. Обе fixture-задачи выполнились ровно один раз и были удалены; исчерпание production-бюджета по-прежнему не заявляется.

Локальный repair сохраняет строгий безопасный JSON Core и отдельные типизированные причины, а ограниченную серию retry выполняет внутри одного Scheduler action после доказанного cleanup. Реальный fixture подтвердил recovery transient-сбоя на второй попытке и постоянный STOP после исчерпания трёх попыток без четвёртого запуска. Затронутые наборы — 49, 134 и 88 PASS. Сетевой D01 выполнен один раз; matches относятся только к установленному `pip 25.0.1`, пакеты не менялись.

### Архив: контракт Gate

- Восстановить один принятый MVP1 без повторения C6 и без работ MVP2.
- Сохранить Core authority, четыре канонические БД, receipts, polling offset, idempotency и `UNKNOWN/reconciliation`.
- Не создавать второй Core, очередь или blind retry; не восстанавливать БД поверх новых принятых данных.
- До production предъявить один revision-bound пакет с точными Actions/config/input digests, backup, baseline, бюджетами, паузой и rollback.
- Разделять published release, repaired candidate, deployed runtime и завершённое 72-часовое наблюдение.

### Архив: исходные refs

| Объект | Значение |
|---|---|
| Base/main | `88e58c8866db2384423f2b154df901a2e4af6c48` |
| Published product v1.0.2 | `82003c03d8a36015703472b472640ab4021fb416` |
| Annotated tag object | `59952c44118606c26e34e20a39ed88ef5c686620` |
| Product tree | `78d47a3be446d33a2ace24144b75d7221f73009e` |
| Main tree | `800e999dc9f24e90808a4784b90bf44d00a72cb1` |
| Рабочая ветка | `codex/m1-s1-stability`, изолированный worktree от exact main |
| Candidate commit/tree | отсутствует: freeze выполняется один раз после закрытия F03/D01 |

Канонический checkout имел пользовательский docs WIP и не изменялся. LIVE остаётся clean detached на product commit. Исторические C6 receipts, sealed sources, документ 11, backups и recovery refs не изменялись.

Контекст Nobus Memory читался только в `project:nobus-space`. Попытка создать managed pointer на этот checkpoint завершилась `ARGUMENT_REJECTED`; запись не произошла, повтор без новой гипотезы не выполнялся. Доступность хранилища из этого не выводится и работа Gate не блокируется.

### Архив: F01–F04 и D01

| ID | Класс | Состояние | Факт и остаток |
|---|---|---|---|
| F01 | FACT + UNKNOWN | DIAGNOSED / historical trigger UNKNOWN | Детерминированно различаются Core/relay exit, startup deadline, local/public/both readiness failure, planned stop и cleanup. Точный trigger старых остановок не выводится по аналогии |
| F02 | FACT | LOCAL REPAIR GREEN / NOT DEPLOYED | Строгий parser безопасного Core JSON, bounded capture, schema `nobus-runtime-event-2`, ротация и fail-closed write/history. Raw stdout/stderr, argv/env, payload и credentials не сохраняются |
| F03 | FACT | OLD MECHANISM FAIL / REPAIRED MECHANISM REAL PASS | `RestartOnFailure` для normal action exit 23 не сработал. Один Scheduler-hosted candidate controller реально восстановил transient на attempt 2 и остановил permanent на attempt 3 по бюджету; cleanup proven |
| F04 | FACT | LOCAL FIX INCLUDED / NOT PUBLISHED | Подготовленные docs01/CURRENT/runbook сохранены и актуализированы по новым фактам. Документ 11 и исторические C6 sources не менялись; публикации нет |
| D01 | FACT | REVIEW_TOOLING | Python 3.12.14, 80 пакетов, 15/15 direct pins, `pip check` PASS. Один OSV query выполнен; matches относятся только к `pip 25.0.1`. Обновления и установки не выполнялись |

### Архив: read-only production evidence

Последнее цельное наблюдение: 14.09.2026, 08:28–08:31 МСК.

- LIVE — прежний `82003c03`; candidate не развёрнут.
- `NobusSpaceBot`: enabled / Running, LastRun 03:31:05 МСК, LastTaskResult `267009` (running). Legacy settings всё ещё `RestartCount=10/PT1M`; definition digest не изменился: `sha256:f68400b92c7dbc94e6116c7f616f9d3ea4473a50ace5e94ea3b70deb1eabfa80`.
- Один логический supervisor (два `pythonw` action-host из-за venv redirector), два gated helpers, один relay, один Core-владелец listener и один listener 8765.
- `local_ready=true`, `public_ready=true`. Health завершился Ready / LastTaskResult 0 в 08:28:44 МСК.
- Backup завершился LastTaskResult 0; новое поколение `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c` прошло ownership, latest pointer, generation inventory, authenticated manifest, target binding, freshness и ciphertext hashes. Следующая копия — 15.09 в 03:30 МСК; restore не запускался.
- Запуск main через 65 секунд после начала backup соответствует штатному backup restart path; это вывод по времени и коду цикла, а не доказательство `RestartOnFailure`.
- Legacy log дополнился только `starting` в 03:31:06 МСК; последний terminal — `runtime_failed` 13.09 в 13:28:54 МСК. V2 log отсутствует, что ожидаемо до deploy.

Baseline после автозапуска:

- 86 task snapshots и ingress claims, 168 audit events, 7 sealed answers;
- 84 outbox messages `acked`, 84 `ack` receipts, 14/14 delivery parts подтверждены;
- Telegram jobs/очередь пусты, active job leases 0, delivery unknown 0, reconciliation false;
- один active polling lease; offset `375633467`, revision `42685`;
- по сравнению с baseline 13.09 задачи/receipts/delivery не изменились, offset монотонно вырос с `375633465` на 2. Дублей или второй очереди не обнаружено.

Текущая доступность принятого runtime — факт, но не закрытие M1-S1: controlled candidate launch, реальный результат/TXT и 72 часа ещё не выполнялись.

### Архив: локальный repaired WIP

`scripts/run_nobus_space_live.py`:

- читает только один завершённый ASCII JSON Core до 4096 байт; лишние поля, повторные ключи, неверный framing, unsafe code и переполнение отвергаются;
- stderr по-прежнему уходит в `DEVNULL`; stdout Core только дренируется bounded parser, сырой текст не сохраняется;
- пишет schema `nobus-runtime-event-2`: JSONL не более 2048 байт на запись, current не более 1 MiB и один `.previous`; symlink/junction/не-файл и ошибка записи дают STOP;
- различает Core, relay, одновременный child exit, startup timeout, local/public/both readiness, planned stop и cleanup outcome;
- сохраняет обе readiness-проверки без short-circuit, `series_id`, `run_id`, exact attempt/budget и cleanup outcome;
- retry разрешён только для relay exit после steady, public fail при local PASS, startup timeout при local PASS/public FAIL и safe Core `telegram_unavailable`; все остальное даёт типизированный STOP;
- `starting` без terminal блокирует новый запуск как `previous_attempt_unknown`; exact terminal retry продолжает тот же series. `--inspect-recovery` только читает, а exact-digest reset сам runtime не запускает.

Gate-only инструменты не входят в production action:

- `tests/gate_m1_s1/collect_runtime_baseline.py` — defensive SQLite `mode=ro`, только агрегаты/offset/digests;
- `tests/gate_m1_s1/audit_dependencies_osv.py` — без флага выполняет только локальный inventory; сеть возможна только с `--query-osv` на один фиксированный endpoint;
- `tests/gate_m1_s1/Invoke-SchedulerRetryFixture.ps1` и `tests/fixtures/m1_scheduler_exit_probe.py` — два уникальных synthetic tasks, без production input, stdout/stderr и event logs; candidate-owned controller запускается как один реальный Scheduler action.

### Архив: проверки pre-freeze WIP

- Исходный RED: 23 ожидаемых отказа новых F02-тестов до реализации.
- Реальный изолированный Windows Job доказал `gated helper → child exit 23` и передачу одного безопасного JSON.
- Реальный старый F03 mechanism: FAIL `scheduler_restart_contract_not_observed`, cleanup proven.
- Реальный исправленный F03 mechanism: PASS; transient attempts `1→2`, permanent attempts `1→2→3 budget_exhausted`, 75 секунд без лишней попытки, cleanup proven.
- Дополнительный RED на fail-closed recovery semantics: 4 отказа; после исправления M1-S1 файл — `49 passed`.
- Единый затронутый набор supervisor/readiness/Windows SSH/installer/maintenance — `134 passed in 56.70s` при работающем production и отдельных test mutex.
- Все зависимые runtime-maintenance и backup-recovery тесты — `88 passed in 107.33s`; одна существующая deprecation warning, установок нет.
- Прежние `76 passed` и 11 supervisor/readiness проверок сохранены; C0–C6 целиком не повторялись.
- PowerShell parser трёх затронутых scripts, Python AST, `git diff --check`, `pip check` и относительные Markdown-ссылки — PASS.

Это WIP evidence, а не L1/L2/L3. Независимые L1/L2/L3 выполняются только после одного freeze целого кандидата; evidence разных bytes смешивать нельзя.

### Архив: реальный F03 FAIL, сохранённый без повторения

Разрешённый run `1a45b43f98e84558b3695b7371ad9b7e` создал только `NobusSpace-M1S1-Fixture-Transient-1a45b43f` и `NobusSpace-M1S1-Fixture-Permanent-1a45b43f`. Обе задачи стартовали 14.09 в 07:30:49 МСК, записали только attempt 1 / `retryable_failure` / exit 23 и остались Ready с LastTaskResult 23. Ни через две минуты, ни в дополнительном 75-секундном окне повторов не было.

Cleanup — `proven`; в 07:47:05 МСК оба имени повторно подтверждены отсутствующими. `result.json`: 1296 bytes, SHA-256 `33bcfbe35fa8b0c6a7a26412f4941879ec2fa79eed7e0e44c49b2e4f4a17b6fa`; оба JSONL: 203 bytes, SHA-256 `763c4efe054f8fb3f6e21989272293635851276add203c887ded7b95c9e19f78`.

[Схема Microsoft RestartOnFailure](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element) описывает Count/Interval. [Протокольное описание Microsoft](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/2ff4aa5a-7bc4-449f-bbb1-27475645867f) связывает повтор с невыполненными условиями запуска или невозможностью запустить action; оно не обещает повтор любого уже стартовавшего процесса после обычного ненулевого exit. Локальный fixture подтверждает фактическое поведение этого хоста.

### Архив: D01 advisory metadata

Один разрешённый POST к `https://api.osv.dev/v1/querybatch` передал только 80 public name/version пар. Inventory digest: `sha256:c4b1be2c5795df1c19722441f157264ce7041558c616e26df98e67037c905be7`. OSV вернул шесть advisory families для `pip 25.0.1`: [GHSA-4xh5-x5gv-qwph](https://github.com/advisories/GHSA-4xh5-x5gv-qwph), [GHSA-6vgw-5pg2-w6jp](https://github.com/advisories/GHSA-6vgw-5pg2-w6jp), [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v), [GHSA-jp4c-xjxw-mgf9](https://github.com/advisories/GHSA-jp4c-xjxw-mgf9), [GHSA-wf93-45jw-7689](https://github.com/advisories/GHSA-wf93-45jw-7689) и [GHSA-qwm4-qh6w-59xr](https://github.com/advisories/GHSA-qwm4-qh6w-59xr). Последний исправлен в 26.2.0. Structured result — `REVIEW`; внешний wrapper сообщил exit 1 вместо предусмотренного скриптом exit 2 для matches. Причина этого расхождения остаётся `UNKNOWN`; запрос не повторялся.

Production action не импортирует и не запускает `pip`; в `requirements.txt` его нет. Verifier lock всё ещё содержит `pip==26.1.2`, поэтому до любого нового install/rebuild нужны exact version/hash review и отдельное разрешение. В этом Gate пакеты не менялись.

### Архив: непригодный как Gate evidence F03 fixture v1

Разрешённый run завершён; bounded evidence сохранено, оба временных задания удалены и отдельно подтверждены отсутствующими в 09:26:51 МСК.

| Поле | Значение |
|---|---|
| Run id | `762a5aaeb35546d1be51b0febf576bf5` |
| Transient task | `NobusSpace-M1S1-Fixture-Transient-762a5aae` |
| Permanent task | `NobusSpace-M1S1-Fixture-Permanent-762a5aae` |
| Fixture script SHA-256 | `17a5b17848c8b5e1255d74a321791ca14a1d1b386d9d6d2177350d4c2d891563` |
| Probe SHA-256 | `4160ff69fd5040716282c7ad5cca85e111cc89662c0b9f8a7e1c2d7df49b0167` |
| Product controller SHA-256 | `77ea03f5a41ea09a8a622c03d040aefbe758d806efa0909b97ce342f381612c6` |
| Result | `PASS`, 1614 bytes, `sha256:36cd9c1ad73484161bceff9a58140e4cb6998baea132e63320a1a4eb670919a6` |
| Transient receipt | attempts 1 retryable / 2 recovered; 397 bytes, `sha256:36ccdf621955112ea3dd8f47e7dec976cc61a9770b2d1683c21d19b31cb67dee` |
| Permanent receipt | attempts 1/2 retryable / 3 budget exhausted; 608 bytes, `sha256:d9af5102789f8edbaf46f9a633f5ace3184a584876270129b6ec74fadeeb5499` |

Один разрешённый вызов зарегистрировал ровно эти два one-time tasks с canonical `pythonw`, Interactive/Limited и `IgnoreNew`, без Scheduler restart settings. Scheduler запустил один candidate controller: transient восстановился на attempt 2 после 60 секунд, permanent завершился budget STOP после трёх total attempts. Дополнительные 75 секунд подтвердили отсутствие четвёртой попытки. Production task, StateRoot, модель, ASR, порты, сеть, messages и event logs не использовались.

Следующий шаг: один freeze commit/tree/source/assets/config/input digests → обязательные независимые L1/L2/L3 ровно этой ревизии → единый production plan → публикация, deploy, Task definitions, controlled start, одна реальная text-задача и TXT в пределах текущего разрешения. Блокирующие reviewer findings сначала собираются и только затем исправляются одним пакетом.

### Архив: критерий 72-часового наблюдения

Владелец согласовал критерий 14.09. После разрешённой активации heartbeat этой же задачи каждые 30 минут только читает Scheduler, structured events, local/public readiness, singleton/process/lease counts, safe DB health и backup manifests. Автоматика пока не создана.

Критерий PASS:

- нет необъяснённых terminal events; каждый planned stop, transient recovery или bounded STOP имеет run id, причину, attempt/budget и cleanup;
- вне планового backup local/public готовы; плановая пауза backup не более 10 минут и явно связана с его run;
- всегда не более одного supervisor/Core/relay/listener/polling lease, нет второй очереди и `delivery_unknown/reconciliation`;
- минимум два плановых backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой;
- начальный и конечный baseline подтверждают сохранность старых tasks/receipts и монотонный offset, а одна разрешённая новая задача имеет ровно один intake/result/TXT;
- любой разрыв наблюдения более 60 минут, выключение ПК или потеря owner session не считается PASS: окно начинается заново после сверки состояния.

Автоматика создаётся только после отдельного разрешения и точного T0/T72. Старый 15-минутный smoke не используется как доказательство устойчивости.

### Архив: прежний раздельный verdict

| Уровень | Verdict |
|---|---|
| Published release | `v1.0.2` / `82003c03` — ACCEPTED / PUBLISHED |
| Repaired candidate | READY FOR FREEZE; LOCAL GREEN / REAL SCHEDULER-HOSTED FIXTURE PASS |
| Deployed runtime | Candidate NOT DEPLOYED; прежний v1.0.2 сейчас READY |
| Stability observation | AGREED / NOT STARTED; automation NOT CREATED |
| M2-G0 | BLOCKED до полного PASS M1-S1 и отдельного решения владельца |
