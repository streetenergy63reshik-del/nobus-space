# M1-S1 — HANDOFF

**Статус 14.09.2026, 09:27 МСК:** дефект F03 воспроизведён, а исправленный механизм подтверждён на реальном Планировщике. Локальный repair прошёл целевые проверки, D01 завершён как `REVIEW_TOOLING`. Кандидат готов к единственному freeze, но ещё не опубликован и не развёрнут. Принятый MVP1 v1.0.2 работает на прежнем коде; это не PASS 72-часового наблюдения.

## Результат текущего этапа

Исторический первичный триггер остановок 10–13 сентября восстановить нельзя: он остаётся `UNKNOWN`. Отдельно воспроизведена причина отсутствия recovery: на этом хосте `RestartCount/PT1M` не перезапустил нормально стартовавший `pythonw` после exit 23. Обе fixture-задачи выполнились ровно один раз и были удалены; исчерпание production-бюджета по-прежнему не заявляется.

Локальный repair сохраняет строгий безопасный JSON Core и отдельные типизированные причины, а ограниченную серию retry выполняет внутри одного Scheduler action после доказанного cleanup. Реальный fixture подтвердил recovery transient-сбоя на второй попытке и постоянный STOP после исчерпания трёх попыток без четвёртого запуска. Затронутые наборы — 49, 134 и 88 PASS. Сетевой D01 выполнен один раз; matches относятся только к установленному `pip 25.0.1`, пакеты не менялись.

## Контракт Gate

- Восстановить один принятый MVP1 без повторения C6 и без работ MVP2.
- Сохранить Core authority, четыре канонические БД, receipts, polling offset, idempotency и `UNKNOWN/reconciliation`.
- Не создавать второй Core, очередь или blind retry; не восстанавливать БД поверх новых принятых данных.
- До production предъявить один revision-bound пакет с точными Actions/config/input digests, backup, baseline, бюджетами, паузой и rollback.
- Разделять published release, repaired candidate, deployed runtime и завершённое 72-часовое наблюдение.

## Точные исходные refs

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

## F01–F04 и D01

| ID | Класс | Состояние | Факт и остаток |
|---|---|---|---|
| F01 | FACT + UNKNOWN | DIAGNOSED / historical trigger UNKNOWN | Детерминированно различаются Core/relay exit, startup deadline, local/public/both readiness failure, planned stop и cleanup. Точный trigger старых остановок не выводится по аналогии |
| F02 | FACT | LOCAL REPAIR GREEN / NOT DEPLOYED | Строгий parser безопасного Core JSON, bounded capture, schema `nobus-runtime-event-2`, ротация и fail-closed write/history. Raw stdout/stderr, argv/env, payload и credentials не сохраняются |
| F03 | FACT | OLD MECHANISM FAIL / REPAIRED MECHANISM REAL PASS | `RestartOnFailure` для normal action exit 23 не сработал. Один Scheduler-hosted candidate controller реально восстановил transient на attempt 2 и остановил permanent на attempt 3 по бюджету; cleanup proven |
| F04 | FACT | LOCAL FIX INCLUDED / NOT PUBLISHED | Подготовленные docs01/CURRENT/runbook сохранены и актуализированы по новым фактам. Документ 11 и исторические C6 sources не менялись; публикации нет |
| D01 | FACT | REVIEW_TOOLING | Python 3.12.14, 80 пакетов, 15/15 direct pins, `pip check` PASS. Один OSV query выполнен; matches относятся только к `pip 25.0.1`. Обновления и установки не выполнялись |

## Read-only production evidence

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

## Локальный repaired WIP

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

## Проверки текущего WIP

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

## Реальный F03 FAIL, сохранённый без повторения

Разрешённый run `1a45b43f98e84558b3695b7371ad9b7e` создал только `NobusSpace-M1S1-Fixture-Transient-1a45b43f` и `NobusSpace-M1S1-Fixture-Permanent-1a45b43f`. Обе задачи стартовали 14.09 в 07:30:49 МСК, записали только attempt 1 / `retryable_failure` / exit 23 и остались Ready с LastTaskResult 23. Ни через две минуты, ни в дополнительном 75-секундном окне повторов не было.

Cleanup — `proven`; в 07:47:05 МСК оба имени повторно подтверждены отсутствующими. `result.json`: 1296 bytes, SHA-256 `33bcfbe35fa8b0c6a7a26412f4941879ec2fa79eed7e0e44c49b2e4f4a17b6fa`; оба JSONL: 203 bytes, SHA-256 `763c4efe054f8fb3f6e21989272293635851276add203c887ded7b95c9e19f78`.

[Схема Microsoft RestartOnFailure](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element) описывает Count/Interval. [Протокольное описание Microsoft](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/2ff4aa5a-7bc4-449f-bbb1-27475645867f) связывает повтор с невыполненными условиями запуска или невозможностью запустить action; оно не обещает повтор любого уже стартовавшего процесса после обычного ненулевого exit. Локальный fixture подтверждает фактическое поведение этого хоста.

## D01 advisory metadata

Один разрешённый POST к `https://api.osv.dev/v1/querybatch` передал только 80 public name/version пар. Inventory digest: `sha256:c4b1be2c5795df1c19722441f157264ce7041558c616e26df98e67037c905be7`. OSV вернул шесть advisory families для `pip 25.0.1`: [GHSA-4xh5-x5gv-qwph](https://github.com/advisories/GHSA-4xh5-x5gv-qwph), [GHSA-6vgw-5pg2-w6jp](https://github.com/advisories/GHSA-6vgw-5pg2-w6jp), [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v), [GHSA-jp4c-xjxw-mgf9](https://github.com/advisories/GHSA-jp4c-xjxw-mgf9), [GHSA-wf93-45jw-7689](https://github.com/advisories/GHSA-wf93-45jw-7689) и [GHSA-qwm4-qh6w-59xr](https://github.com/advisories/GHSA-qwm4-qh6w-59xr). Последний исправлен в 26.2.0. Structured result — `REVIEW`; внешний wrapper сообщил exit 1 вместо предусмотренного скриптом exit 2 для matches. Причина этого расхождения остаётся `UNKNOWN`; запрос не повторялся.

Production action не импортирует и не запускает `pip`; в `requirements.txt` его нет. Verifier lock всё ещё содержит `pip==26.1.2`, поэтому до любого нового install/rebuild нужны exact version/hash review и отдельное разрешение. В этом Gate пакеты не менялись.

## Реальный F03 PASS исправленного механизма

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

## 72-часовое наблюдение — критерий согласован, окно не начато

Владелец согласовал критерий 14.09. После разрешённой активации heartbeat этой же задачи каждые 30 минут только читает Scheduler, structured events, local/public readiness, singleton/process/lease counts, safe DB health и backup manifests. Автоматика пока не создана.

Критерий PASS:

- нет необъяснённых terminal events; каждый planned stop, transient recovery или bounded STOP имеет run id, причину, attempt/budget и cleanup;
- вне планового backup local/public готовы; плановая пауза backup не более 10 минут и явно связана с его run;
- всегда не более одного supervisor/Core/relay/listener/polling lease, нет второй очереди и `delivery_unknown/reconciliation`;
- минимум два плановых backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой;
- начальный и конечный baseline подтверждают сохранность старых tasks/receipts и монотонный offset, а одна разрешённая новая задача имеет ровно один intake/result/TXT;
- любой разрыв наблюдения более 60 минут, выключение ПК или потеря owner session не считается PASS: окно начинается заново после сверки состояния.

Автоматика создаётся только после отдельного разрешения и точного T0/T72. Старый 15-минутный smoke не используется как доказательство устойчивости.

## Раздельный verdict

| Уровень | Verdict |
|---|---|
| Published release | `v1.0.2` / `82003c03` — ACCEPTED / PUBLISHED |
| Repaired candidate | READY FOR FREEZE; LOCAL GREEN / REAL SCHEDULER-HOSTED FIXTURE PASS |
| Deployed runtime | Candidate NOT DEPLOYED; прежний v1.0.2 сейчас READY |
| Stability observation | AGREED / NOT STARTED; automation NOT CREATED |
| M2-G0 | BLOCKED до полного PASS M1-S1 и отдельного решения владельца |
