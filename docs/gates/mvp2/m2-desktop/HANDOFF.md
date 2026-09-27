# M2-DESKTOP — рабочая передача

**Gate:** M2-DESKTOP
**Текущая стадия:** первый замороженный кандидат `2355ae5` получил два отказа L1 из одного brittle readiness-dispatch; в WIP внесено адресное исправление и подготовлена новая DRAFT-заморозка. Production на `fd4d66c` остановлен, три Scheduled Tasks выключены; D01 доставлен, D03 завершён в Desktop, но ещё не доставлен; D02–D17 открыты

**Дата текущего наблюдения:** 27 сентября 2026 года, 10:05 МСК
**Ветка:** `codex/m2-desktop`
**Активный production checkpoint:** `fd4d66cfccb66c29702c29f6df59d137d3c26e3b`, tree `efe10b99be591bb194d0e20f09ddd614f0ac2f27`; локальная документация не меняет его binding.

## 27.09, 10:05 МСК — первый frozen DRAFT отклонён L1; адресная правка

Локальный commit `2355ae5e47f542ea7485ad509e8128f3d1b5b7db`
заморозил 12 M2-DESKTOP файлов, рабочая копия была чистой. Широкий L1
с уникальным коротким basetemp завершился `2933 passed, 2 failed,
3 skipped, 5` заранее зафиксированных исторических deselections,
`25 subtests passed` за 601,55 с. Оба отказа — две параметризации
`test_c5_real_runner_wires_isolated_semantic_profile_once`: fixture
подменяет `DurableProductTelegramControlPlane` фабрикой, а новый runner
делал `isinstance(control, DurableProductTelegramControlPlane)`;
получался `TypeError` до проверки здоровья. Это дефект совместимости
readiness-dispatch с внедряемой реализацией, не наблюдавшийся в живом
runtime, но блокирующий кандидат. L2/L3 этого SHA не запускались.

В WIP проверка выбирает доступный `assert_healthy_nonblocking`, иначе
оставляет прежний синхронный путь. Семь адресных случаев прошли, включая
все четыре параметризации fixture, worker/loop и Mini App readiness.
Кодовые bytes изменились: `2355ae5` не наследует PASS и не может стать
новым кандидатом без отдельного freeze и повторного L1/L2/L3. Первый
снимок сохранён в Git; его результаты не стерты.

## 27.09, 09:43 МСК — предзаморозочная проверка

Владелец поручил заморозить один цельный кандидат и провести L1–L3 в этой
задаче. В замораживаемый снимок входят текущие M2-DESKTOP код, тесты,
архитектура, HANDOFF/EVIDENCE, REGISTRY, CURRENT и release plan; `tmp`,
`.runtime`, credentials и production checkout не входят. Перед freeze
затронутые backup/readiness тесты из предыдущего шага остаются
положительными. Дополнительный `test_desktop_bridge.py` вместе с
`test_documentation.py` дал `68 passed, 1 failed`: единственный отказ
создал Git worktree внутри длинного кириллического pytest basetemp,
`fatal: '$GIT_DIR' too big`. Исходный каталог сохранён. Тот же точный
тест в новом коротком системном temp прошёл (`1 passed`); это
классифицировано как ограничение проверяющей среды, не подтверждённый
дефект bridge. Для L1 использовать уникальный короткий basetemp;
не чистить предыдущие каталоги.

Снимок пока DRAFT: L1/L2/L3, выпуск, reset и новые live-сообщения не
выполнялись. Точный Git SHA/tree будет привязан после локального commit,
а не вписан в саму версию документа до его появления.

## 27.09, 09:21 МСК — локальное восстановление backup и граница готовности

Владелец разрешил выполнить только ранее обозначенные пункты 1–2 в этой
сессии; заморозку кандидата, независимую проверку, выпуск и живую приёмку
оставил на следующий запуск. Разрешение на удаление применено только к
автоматически создаваемым временным SQLite sidecar/pytest файлам внутри
новых изолированных тестовых каталогов; файлы production и чужой WIP не
удалялись. Повтор четырёх тестов под Windows FileSystemWatcher в новом
`m2-file-watch-20260927-a1` дал `4 passed` и 58 `Deleted` событий: 44
`-wal/-shm`, 6 `-journal`, 4 служебных pytest `current` и 4 события
исходных имён при перемещении control-файлов; отдельно были 3 `Renamed`.
Все наблюдавшиеся пути были внутри нового тестового корня. Полный сырой
список событий в файл не сохранён, поэтому это классифицированное
наблюдение, а не доказательство отсутствия иных файловых эффектов в
production. Исторический отрицательный результат `59` сохранён ниже.

Для `latest.dpapi` и `backup-cycle-state.dpapi` локальный WIP теперь
использует штатный Windows `ReplaceFileW` с уникальным архивом прежнего
файла при уже существующем target. Так устранён двухшаговый rename-gap
при успешном вызове. Если API сообщает частичный отказ до установки
нового файла, прежний архив возвращается с проверкой bytes; при
неопределённом исходе цикл останавливается и **не пишет повторный journal
вслепую**. `ReplaceFileW` не обещает здесь write-through при внезапном
отключении питания; после такого сбоя требуется readback control-файлов
и signed state до дальнейших действий. Проверены успешная замена с
сохранением identity, путь длиной 316 символов, коллизия архива,
смоделированные частичный и неопределённый отказы.

Слишком широкий первый fail-closed (`latest` отсутствует при любой
generation) ломал штатное восстановление первого прерванного цикла;
затронутая регрессия дала `1 failed, 24 passed`. Guard исправлен: retry
допускается только для одной аутентичной generation с pending pointer
того же failed attempt и без архива ранее опубликованного latest.
Потеря первого уже опубликованного pointer при новой попытке и потеря
pointer после последующих циклов по-прежнему закрываются отказом. После
правки 36 затронутых backup-тестов прошли вместе; добавленный отдельный
отрицательный тест первого опубликованного pointer также прошёл.
6 адресных readiness-регрессий подтвердили, что медленные backup/
Mini App/Desktop проверки не держат Core event loop и запись стека
при искусственной задержке работает. Это подтверждает локальное
устранение известного механизма блокировки, но **не устанавливает
точный зависший вызов 26.09 в 18:37 UTC**: live stack тогда не был
снят, а новый код на работающем Desktop/Telegram ещё не выпускался.

Production не менялся: все три задачи остаются Disabled, admission hold
и подписанный STOP сохранены. Уже доставленный D01 и завершённый Desktop
turn D03 не повторять. Следующий запуск: из текущего WIP сформировать
один цельный кандидат, выполнить обязательную независимую проверку;
только затем контролируемый выпуск/recovery и живые D02–D17. Без этих
шагов M2-DESKTOP не готов и не принят.

## 27.09, 08:22 МСК — автоматический backup не смог восстановить Main

Новая read-only сверка обнаружила, что запланированный на 03:30
`NobusSpaceBot-Backup` всё же был включён и **автоматически выполнился**
после вчерашнего стопа. Он создал `VERIFIED` generation
`daily-20260927T033029-777f247f8b534c47a07e804bf35d74e9`, затем
подписанный cycle journal зафиксировал `failed_operator_required`:
`failed_phase=starting`, `failure_class=restart_not_ready`,
`runtime_status=NOT_READY`, `admission_hold=true`, `cleanup_proven=true`
в 03:31:11 МСК. Main и Health теперь `Disabled`; Main last result `78`,
Backup last result `1`. Production checkout по-прежнему чистый на
`fd4d66c`. Файл supervisor journal не менялся после `control_closed`
26.09, 21:37:48 МСК (SHA-256 файла
`b626744b7a2cea3f626a78c07abe93f8c3835a330e7d9b3b70dce5cf398fd2bc`).
По одному только времени файла signed head не переиспользовать.
Отдельная **read-only** проверка `latest_manifest` + `verify_backup`
подтвердила новую generation с четырьмя зашифрованными файлами и digest
`sha256:e47d610b8b758effa31805550cb7ad2593468b77c3ab65c997b3257636be3056`;
это не проверка возможности безопасно возобновить runtime и не новый backup.
Затем штатный `--inspect-recovery` с фактическими аргументами Main Task
вернул `status=STOP`, `state=blocked`, `reason=stop_non_retryable`,
`last_digest=sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Это совпадает с прежним подписанным head; reset не выполнялся.

Рабочий production `fd4d66c` содержит `cleanup_staging()` в `finally`
backup и `unlink_durable()` для admission hold. После `VERIFIED`
generation staging cleanup был пройден, однако список фактически удалённых
путей ночного цикла не сохранился. Утверждать, что соблюдён прямой запрет
удаления, нельзя. Чтобы не допустить следующего автоматического цикла,
штатным `Invoke-NobusSpaceTask.ps1 -Operation Disable` выключен **только**
idle `NobusSpaceBot-Backup`; readback: `Disabled`, `enabled=false`.
Main/Health уже были выключены до этого действия. Ни backup, ни reset,
Desktop turn, Telegram-сообщение или удаление файлов вручную не запускались.

В локальном WIP заменены ещё два точных overwrite-пути: обновление
`latest.dpapi` и `backup-cycle-state.dpapi` теперь переносит прежний
control-файл в уникальный архив, а pending-файл — на его место, без
`os.replace`. Чистый файловый self-check сохранил inode старого и нового
файла; проверка коллизии архива не изменила три исходных файла;
отдельный вызов journal-test прошёл без SQLite/pytest. Все три
уникальных каталога сохранены. Дополнительные две чистые проверки
подтвердили fail-closed при потере `latest.dpapi` или backup journal
между двумя rename; их каталоги также сохранены. Это **не** решает
автоматически удаляемые SQLite `-wal`/`-shm` и не доказывает процедуру
восстановления после crash-gap; WIP не является кандидатом для выпуска.
Повтор файлового watcher-теста,
backup/rebind/reset и live Telegram пока запрещён действующим no-delete.

## 26.09, 22:47 МСК — no-delete не выполнен; выпуск запрещён

Новая файловая проверка наблюдала **59 событий Windows `Deleted`** за
четыре ранее зелёных синтетических no-delete backup теста в новом
изолированном каталоге
`.runtime/worktrees/m2-desktop/.runtime/m2-file-watch-97e3b2e4d957/`.
`pytest` завершился `4 passed`, но файловый монитор — отрицательно.
Список точных путей событий не был сохранён этой попыткой; после теста
остались 9 `.sqlite3` и 26 прочих файлов, ни одного `-wal`/`-shm`.
Это согласуется с удалением временных SQLite sidecar, но **не позволяет
приписать все 59 событий одному механизму**. Каталог и существующие
артефакты сохранены, production и пользовательские файлы не менялись.

Checkpoint `91a0499` устранил известные вызовы `cleanup_staging()` и
`unlink_durable()` из выпускного маршрута, но утверждение о полном
no-delete **отозвано**. Нельзя выпускать его, выполнять backup/rebind,
recovery reset, запускать новых Telegram/Desktop тестов или повторять
этот файловый эксперимент при действующем запрете удаления. До снятия
блокера требуется либо согласованное исключение для точно ограниченных
временных файлов SQLite/pytest, либо отдельный проверенный способ без
этих файловых событий. Никакого нового разрешения не предполагать.
Readiness исправлен только локально; причина исторического timeout
остаётся причинной гипотезой без live-трассы.

## 26.09, после 22:40 МСК — no-delete backup остаётся только локальным

Следующий локальный checkpoint `91a0499c06567c9d5a9829190e2629aa26663661`, tree
`30767a04c449455269c67979942ccc39d0c1a89e`, сохраняет предыдущий
readiness fix и меняет выпускной backup: SQLite backup строится в памяти,
шифруется до записи, без `cleanup_staging()`; `temp_store=MEMORY` запрещает
SQLite spill для проверок; прежние latest pointer и signed journal
архивируются, нулевой admission-hold переименовывается и сохраняется;
retention в цикле пока только read-only (`apply=False`). Новые тесты
проверяют восстановимость синтетического шифрованного snapshot через
read-only immutable SQLite, старый pointer, journal и hold. Чистый Git
экспорт точного commit дал `15 passed` адресных тестов; ещё `3 passed`
на точной Git-привязке worktree (signed reconcile, backup отказ и disk-full).
Все временные каталоги уникальны и сохранены.

**Это не доказательство полного no-delete на Windows**: сам SQLite может
создавать/удалять `-wal`/`-shm` при закрытии соединения. Read-only снимок
остановленного runtime показал, что у task-runtime и checkpoint такие
sidecar-файлы существуют, а Health продолжает обращаться к БД и получает
LastTaskResult `1`. Локальные тесты не являются проверкой всех файловых
эффектов настоящего backup. Без этой проверки и без полного независимого
L1/L2/L3 выпуск `91a0499`, signed rebind/backup/reset и новый Telegram
тест **не выполнялись**. Нельзя объявлять readiness root cause окончательно
доказанной: loop stall во время инцидента не захвачен. Уже завершённый
D03 Desktop turn не повторять.

При проверке синтетического цикла автоматический reviewer сначала отказал
из-за прежнего cleanup-пути. После read-only трассировки нового кода и
четырёх no-delete тестов один синтетический цикл и signed reconcile были
разрешены и прошли; это не заменяет разрешения на удаление и не доказывает
отсутствие внутренних SQLite sidecar-эффектов в production.

## 26.09, 22:27 МСК — локальный checkpoint и ограничение no-delete

Локальный кодовый checkpoint `133929f5ea153fc8d05a093200f9733045ac2293`, tree
`e2fd0887de00b85ce672eeb976dfddc7a63019f7`, переносит глубокие
backup-проверки ingress, polling и `/readyz` с Core event loop в worker
threads. Проверки состояния asyncio-задач оставлены на Core loop.
Синхронная Git-проверка Desktop project cwd и осмотр файлов результата
тоже вынесены с loop. Добавлена ограниченная запись stack file/function/line
при задержке loop >1,5 с и ротация диагностик без перезаписи старого архива.
Это устранение доказанного механизма блокировки, **не доказательство**, что
именно он вызвал остановку в 18:37 UTC. Три read-only измерения текущей
backup-проверки дали 204/171/157 мс: отдельный >2-секундный всплеск не
воспроизведён. 11 адресных тестов прошли в новом чистом Git-экспорте;
уникальный basetemp сохранён. Полный L1/L2/L3 по финальному Gate и live
readiness на этом commit ещё не выполнялись.

Выпуск **не выполнялся**. Штатный `backup()` вызывает `cleanup_staging()`,
который `unlink()` временные plaintext SQLite и удаляет staging-папку;
`permit_admission()` делает `unlink_durable()` для нулевого hold-файла.
`retention(apply=True)` перемещает прежние generations в quarantine
(не удаляет bytes, но является prune). Прямой запрет владельца на удаление
файлов, включая скрытую очистку, не позволяет безопасно запускать этот
цикл как есть. При текущем наборе backup `retention(apply=False)` вернул
`selected_count=0`, но после новой generation выбор изменится.
Не подменять backup/rebind простым переключением checkout. Следующий
независимый шаг — доказать и реализовать no-delete-совместимый путь
полноценного backup/recovery без сохранения plaintext staging; только
после новой проверки/выпуска доставить уже завершённый D03 без повтора turn.

## 26.09, 21:36–21:51 МСК — продолжение той же задачи и повторный readiness stop

После отдельного подтверждения владельца ровно один раз отправлена в
«Заметки бизнеса» / «Codex work» команда `continue` для существующего
thread `01a0de96-455b-73f3-a211-dda674803351`, метка
`M2-CONTINUE-20260926-1`. Telegram показал одно исходящее сообщение
`2312` и один ответ о приёме. Bridge создал только новый request
`5b965633-8670-4db5-a67f-2a530ca48f78` и привязал turn
`01a0df02-48f2-7453-955e-350fbee2e0ea` к **тому же** thread.
Штатное чтение Desktop и отдельный read-only IPC snapshot revision 36
подтвердили `completed` и полный финал ровно
`M2-CONTINUE-20260926-1`. Это положительное доказательство Telegram →
Desktop continuation, но не доставки результата обратно и не всего D03.

Main остановлен safety guard: local/public readiness трижды достигли
deadline в 18:37:09, 18:37:26 и 18:37:43 UTC; signed terminal
`local_public_readiness_failed`, затем `control_closed`, cleanup proven,
head `sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Main `Ready`/LastTaskResult `1`; для нового request статус `running`,
delivery rows `0`. Desktop завершил turn уже в период остановки. **Не
повторять** Telegram-сообщение или Desktop-turn. До нового выпуска и
readback причинного исправления не делать слепой recovery reset.

Сопоставление кода и пятиминутного py-spy профиля работающего Core
показало, что `/readyz` синхронно выполняет глубокую backup-проверку,
повторное хэширование исходников и Git subprocess на event loop; обычно
local probe занимал 188–313 мс. Профиль закончился **до** инцидента и
не указывает, какая операция задержалась именно в 18:37. Отдельный
Health-валидатор утром имел 39,1-секундную проверку task-runtime DB,
вечером — обычные 5–7 секунд; это корреляция, не доказанная причина.
WIP добавляет безопасную запись только file/function/line при stall >1,5 с
и append-only ротацию диагностик; 2 адресных теста прошли, production
ещё не обновлён. Старые архивы readiness/health заранее **переименованы**
в уникальные `.preserved.*.jsonl` в тех же каталогах с совпавшими SHA,
чтобы текущая ротация их не перезаписала. Ничего не удалено.

## Рабочая матрица незакрытых D02–D17 — 26.09, до нового live-цикла

Это перечень действий, а не зачёт. D01 уже имеет отдельную живую квитанцию ниже. Для каждого PASS нужен указанный результат, привязанный к конкретному запросу и ревизии.

| ID | Действие | Сейчас / условие закрытия |
|---|---|---|
| D02 | Принять сообщение настоящего Артура младшего и его reply на вопрос | Нет живого ingress; нужны подтверждённые numeric автор, задача и ответ без подмены личности |
| D03 | Продолжить ручную local/worktree-задачу из Telegram и bridge-задачу вручную в Desktop | Живое Telegram → тот же Desktop thread/turn прошло; ответ не доставлен из-за stop. Нужны доставка, обратное ручное продолжение и независимая ранее не связанная задача |
| D04 | Уточнить неоднозначные цель и проект в двух темах | Детерминированный Core-маршрут есть, семантический выбор не доказан; неверная цель не должна исполняться |
| D05 | Провести голос → preview → confirm → повтор confirm | Есть локальный код; нужен реальный голос и ровно один Desktop-turn |
| D06 | Получить обычный вопрос в теме и ответ автора | IPC question-cycle исторически успешен; нужен bridge request/turn/reply автора и итог |
| D07 | Провести approve и deny владельцем, отказ чужому user_id | IPC approve/deny исторически успешны; нужен Telegram owner-only цикл и Desktop readback |
| D08 | Проверить неоднозначный requestUserInput, unknown, expiry, reconnect и гонку ответов | Локальные guards есть; нужны адресные fault-квитанции, а согласованную Desktop-границу не расширять |
| D09 | Доставить полный длинный итог с Unicode, кодом и таблицей | Formatter локален; нужны все Telegram-части и сверка исходного текста |
| D10 | Доставить созданный и найденный файлы, новый запрос тех же bytes и replay | Есть локальные слоты; нужны реальные Telegram file IDs и совпадение хэшей без дубля replay |
| D11 | Проверить большой, изменившийся/отсутствующий файл, визуализацию и partial | Есть локальная обработка; каждый отрицательный исход должен быть явным, без ложного delivered |
| D12 | Проверить повтор update, lost ACK, restart, сеть, конкуренцию | D01 recovery подтверждён; остальные fault-сценарии должны не повторить исполнение/отправку вслепую |
| D13 | Сверить проекты, режим, модель и семейства инструментов настоящего Desktop | Узкий owner IPC доказан; нужна матрица фактического контекста и возможностей, без вывода о полном паритете из одного turn |
| D14 | Проверить реальный bot-to-bot и запрет другого/анонимного чата | Локальные guards есть; нужны живой Артур и безопасные отрицательные квитанции |
| D15 | Проверить backup/rollback, MVP1, единого отправителя и быстрый turn | Production работает после recovery; нужен новый проверенный цикл и отсутствие bridge/notifier/skill дублей |
| D16 | Заморозить цельный кандидат и провести L1/L2/L3 | Старые тесты привязаны к другим bytes; нужны проверки одной точной SHA/tree/config/версии Desktop |
| D17 | Выпустить через защищённый Git-путь и технически принять живой сценарий | Владелец делегировал приёмку 26.09; нужны реальные release/live/readback, не ещё одно сообщение «принимаю» |

## 26.09, 20:17–20:20 МСК — однократное восстановление и доставка D01

После точного подтверждения владельца read-only preflight повторно сверил
неизменный signed `control_closed` head
`sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`,
чистый production `fd4d66c`, Main `Ready`, listener 8765 отсутствовал.
Штатный `--acknowledge-recovery-stop` выполнен **один раз**, вернул
`RESET` с event
`sha256:7d4bf41df20797f28f210e854d33f8102e629c6b97aa4cdeb81f5ff905e78c0a`.
Штатно запущено только существующее задание `NobusSpaceBot`. Код, config,
credentials, Desktop, notifier, Backup Task и Telegram-команда не менялись
и не повторялись.

Уже привязанный request `ae0183d9-669a-4cde-b81e-74d749cc6643` перешёл
из `running` в `delivered` с тем же turn
`01a0de97-8678-74f3-9736-0296f7009580`. В delivery ledger одна запись
`text/0/sent`, Telegram message ID `2306`. В исходной теме «Codex work»
read-only UI показал ровно один итоговый message value
`M2-LIVE-20260926-3` в 20:17, ответом на исходное сообщение владельца;
никакой второй Desktop turn не запускался. Это живое доказательство
простого текстового D01, включая создание в существующем проекте, cwd
и полную доставку короткого финала, но не D02–D17 и не полный Gate.

Read-only проверка после запуска: Main `Running`, Health `Ready` с
LastTaskResult `0` в 20:20, local/public readiness `PASS`. Причина
предшествующей задержки Core не доказана и не исправлялась. Новый
readiness stop не наблюдался; при повторении не выполнять recovery
автоматически. Следующий отдельный live-сценарий продолжения той же
Desktop-задачи запрошен у владельца с точным текстом, но ещё не отправлен.

## 26.09, 19:39–19:48 МСК — первый реальный Desktop turn из Telegram, затем safety stop

По новому сообщению владельца один раз отправлена в «Заметки бизнеса» →
«Codex work» команда `/codex@Nobusspacebot new nobus-orchestrator-dev` с
точным безопасным заданием `Ответь ровно M2-LIVE-20260926-3, без инструментов
и файлов`. Telegram показал одну исходящую команду и одно подтверждение
бота. Bridge создал request `ae0183d9-669a-4cde-b81e-74d749cc6643`,
source message `2299`; установленный Desktop создал thread
`01a0de96-455b-73f3-a211-dda674803351` в cwd существующего проекта и
turn `01a0de97-8678-74f3-9736-0296f7009580`. Штатное чтение задачи
Desktop вернуло полный финал ровно `M2-LIVE-20260926-3`. Отдельный
read-only IPC snapshot revision 18 подтвердил `runtime=idle`, этот же
turn `completed`, один блок `final_answer`, ноль pending requests. Это
положительное доказательство внешнего управления настоящим Desktop, но
**не** Telegram-доставки и не полного D01–D17.

С 19:40:32 три последовательные local/public readiness-пробы дали
deadline; последняя — в 19:41:06. Подписанный recovery journal завершил
Main как `local_public_readiness_failed`, `stop_non_retryable`,
`cleanup_outcome=proven`, без самопроизвольного core/relay exit.
Точный подписанный head после `control_closed`:
`sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`.
Read-only Task Scheduler: Main `Ready`, LastTaskResult `1`; Health `Ready`,
последняя проверка также `1`; Backup `Ready`. Причина задержки самого
Core во время создания Desktop-задачи пока не установлена, safety guard
не ослаблен.

Bridge SQLite по точному request остаётся `running`, привязка
`client_message_id=nobus:ae0183d9-669a-4cde-b81e-74d749cc6643`
и turn сохранена; `desktop_bridge_deliveries` содержит **0** строк для
него. Telegram показывает только приём, итог не пришёл. Не повторять
сообщение, создание задачи или turn. После точного разрешения и сверки
неизменности signed head допустим один штатный recovery reset и один
запуск существующего Main; стартовый recovery путь обязан читать уже
привязанный turn, а не запускать новый. Адресный локальный тест этого
пути `test_recovered_running_request_delivers_completed_turn_without_resend`
прошёл (`1 passed`); первый запуск теста упёрся лишь в sandbox temp ACL,
после точного доступа к test temp завершился. Живой recovery пока
**не выполнен**; отдельный запрос владельцу отправлен.

## 26.09, 19:00–19:18 МСК — точный выпуск fd4d66c

Владелец отдельно подтвердил именно `fd4d66cfccb66c29702c29f6df59d137d3c26e3b`
и один `--reconcile-complete-digest` от прежнего signed journal. До
действия production был clean на `cdc59a2`, Main `Running`,
Health/Backup `Ready`, старый config и `complete` journal совпали с
их зафиксированными digest. Rollback-снимок создан в
`.runtime/m2-desktop-release-20260926/fd4d66c-preflight/`: три Task XML,
старый backup config, каталог проектов и оба обнаруженных health launcher.
Реальный production launcher имеет SHA-256 `ecda0dc163d90b6ea7f2bd9d5a0d0463ef1a52a7fcd975323597e2f52d2dff80`;
общий одноимённый файл отличался, поэтому точная production-копия
сохранена отдельно. БД и credentials не копировались. Локальная ветка
возврата — `codex/m2-desktop-cdc59a2-before-fd4d66c`.

Health, Backup, Main выключены штатно; один graceful `--stop` остановил
Main. `_stopped(config)=True` подтвердил отсутствие порта, дочерних
процессов и занятых mutex. После остановки signed recovery head был
`sha256:64dbfd5e5203f257e8f28e79d1cf519740e9b95575b08816627c95dac56140cc`
(`control_closed`). Чистый checkout переключён на точный `fd4d66c`.
Новый O_EXCL config создан под отдельным именем, digest
`sha256:cb9af8931da6d9f0e896c208f6697845e6e7a23ecb12fa6501f9edb345c9d407`;
его `application_binding` соответствует новому commit/code digest.

Первый `-WhatIf` Backup installer отказал, потому что прежний XML
digest был снят до `Disable`. Read-only сравнение показало единственное
изменение `<Enabled>false</Enabled>`; актуальный disabled XML digest
`429f4bdc62d2d6d021889d544760ebada276d2dd096e3b9fd6fc59e2ae790b71`.
Повторный `-WhatIf` прошёл. Штатно заменено **только** определение
остановленного Backup Task; новый disabled XML digest
`34309218a015d82eb7daafb0ba9ab2895906d6f1a70d4dc076b7c45027c6753c`.
Main/Health definitions не заменялись.

Один signed rebind от точного head вернул `REBOUND`, event
`sha256:bbf59776cbbc783b2e860109724d609e38916b64ddabe5fa5cd3ecb19ef9843d`,
activation binding
`sha256:3eed230e4abc7283da2cc4f767c99c8ce20e9f238b5a8328f5c4c9addbb005ac`;
штатный inspect с полным производственным окружением дал `PASS/new`.
Backup включён до запуска Main (следующее расписание 27.09 03:30).
Один `--reconcile-complete-digest` от
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`
вернул `PASS`, новую VERIFIED generation
`daily-20260926T191008-36e07f063a674ffcab3fa810defcfa98`,
`runtime_ready=true`; цикл не повторялся. Подписанный новый journal:
`complete`,
`sha256:3ceca795c3273a3802fa92fbc3b08c5d2fbdaa03a06dc78b3d0144e5f819b71a`.

Readback в 19:18: production clean на `fd4d66c`; Main `Running`,
Health/Backup `Ready`; local/public readiness `PASS`. Backup
`LastTaskResult=1` относится к планировщику, не к только что выполненному
ручному циклу; последний подтверждён signed journal и собственной
квитанцией `PASS`. Новый тест `M2-LIVE-20260926-3` не отправлен:
перед UI-действием пользователь остановил Computer Use физической Escape.
Это не продуктовый отказ. После нового запроса пользователя проверка
возобновлена, без повтора релиза или старых Telegram-сообщений.

## 26.09, вечер — замороженный локальный кандидат и граница выпуска

Исправления пяти файлов зафиксированы в `fd4d66c`. Чистый Git ZIP этого
commit имеет SHA-256 `8482dba7ddb03d171800be5e573abfe0802843c76f44659fcc4afe40f5cf0015`.
Связанный независимый прогон из экспорта: `433 passed, 1 skipped`.
Широкий L1 из рабочей копии: `2899 passed, 16 failed, 3 skipped,
5 deselected, 25 subtests passed`; все 16 отказов — захват настоящего
`Global\NobusSpaceBot` работающим production. Не останавливая бота, три
затронутых файла повторены из чистого экспорта в отдельном процессе с
тестовым именем mutex `Global\NobusSpaceBot_L1_fd4d66c`: `34 passed`.
Это объясняет конфликт среды, но не превращает исходный широкий прогон в
«зелёный» и не служит живой приёмкой.

Адверсариальная проверка diff: version guard по-прежнему отвергает
неизвестный Desktop; UIA выбирает точный проект семантически, ждёт его
контекст не более 5 секунд и повторно сверяет перед Send; нет координат,
clipboard или CLI-подмены. Явно адресованные `/codex`, `@bot` и имя бота
не становятся продолжением лишь из-за `reply_to` корня темы; обычный
неадресованный ответ сохраняет привязку к теме. Эти выводы ограничены
проверенными случаями, не доказывают все функции Desktop.

Read-only preflight: production checkout чистый на `cdc59a2`; Main
`Running`, Health/Backup `Ready`. Действующий config повторно прошёл
`load_config` с digest
`sha256:bd885e5ef5953aae9ac6a38011c5a0f4b49d9f36816d361fb2664aacd929b685`;
подписанный journal — `complete`, digest
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`.
Новый `application_binding()` кандидата:
`source_commit=fd4d66cfccb66c29702c29f6df59d137d3c26e3b`, code digest
`sha256:3a12dcfd6ead59073b4ed21ed764042670596cc8788bc9f806424c6c4347fff6`.
Подписанный recovery head продолжает двигаться при работе бота; в одном
read-only снимке он был `sha256:25362cc205ed1a90ebaf9998ceb964bd8e33ccb1e49ce8d6c15a0015d2b0e0c5`
с событием `starting`. Перед rebind нужен свежий head после остановки,
а не этот снимок. `--inspect-recovery` из интерактивного shell без
производственного окружения вернул `runtime_composition_invalid`; прямое
read-only чтение подписанного event прошло. Ни reset, ни rebind не запускались.

Новая production-привязка потребует отдельного точного выпуска:
rollback, остановка/Disable Main/Health, новый O_EXCL config в той же
папке, замена только Backup Task под новый config digest, signed recovery
rebind от свежего head и **один** `--reconcile-complete-digest` от указанного
complete journal. При любом mismatch или неизвестном исходе — read-only
установление состояния, не автоматический повтор. Старые два Telegram
сообщения и пробу `…7A4D` не повторять.

## 26.09, 18:23–18:37 — Desktop обновился, новый UIA подтверждён локально

После отдельного action-time подтверждения в ту же тему отправлена **одна**
явная команда `/codex@Nobusspacebot new nobus-orchestrator-dev` с меткой
`M2-LIVE-20260926-2`. Бот подтвердил приём: request
`9202eece-cc7a-4e62-9d7c-e3b3f6d1e98d`, source message `2286`.
Через минуту он сообщил о неопределённом исходе UI Automation; SQLite
показывает `unknown_dispatch`, `desktop_thread_id`/`desktop_turn_id` пусты.
Повтор Telegram-запроса или исполнения не делался.

Точная причина отказа этого запуска — установленный Codex Desktop уже
`26.924.2738.0`, тогда как production UIA принимает только ранее проверенную
`26.917.9434.0`. Старый `Snapshot` отказал до действия. Read-only
`Snapshot` с новой версией нашёл точный проект; независимый UI показал
точную кнопку «Начать новый чат в папке nobus-orchestrator-dev», а IPC
`initialize` и owner discovery существующей задачи прошли. Это не
доказательство полного паритета всех IPC методов.

В локальном WIP version pin обновлён только на фактически установленную
версию. Первая отдельная UIA-проба `M2-UIA-26924-20260926-7A4D` вызвала
кнопку нового чата, но остановилась на `check-active-context` **до ввода**:
новый экран ещё загружался. Последующий read-only UIA подтвердил активный
проект, пустой composer; в истории метки нет. Добавлено ограниченное
ожидание точного проектного контекста после Invoke; финальная проверка
непосредственно перед Send сохранена.

Вторая проба с новой меткой `M2-UIA-26924-20260926-B19E` вернула UIA receipt
`invoked-create-task, submitted-prompt` на PID 35608. В настоящем Desktop
видны задача `M2-UIA-READY-B19E` и точный итог. Read-only IPC нашёл owner
thread `01a0de5a-db5c-7433-8587-93bec1f39917`, одну завершённую историю
с меткой, точный финальный ответ и cwd существующего проекта. Это
подтверждает UIA create + IPC read на версии `26.924.2738.0`, но не новый
Telegram turn, approvals, skills/MCP или полный D01–D17. Текущий локальный
UIA/bridge набор: `74 passed`, PowerShell parser: 0 ошибок. Production
по-прежнему на старом `cdc59a2`; запрос `9202...` автоматически не оживлять.

## 26.09, вечер — остановка readiness, один reset, реальный Telegram-дефект

После утренней активации Main остановился в 10:34 МСК с подписанным
`local_public_readiness_failed`: три последовательные проверки public
превысили лимит времени, две из них также не дождались local. Дочерние
процессы при решении supervisor ещё существовали; после остановки cleanup
подтверждён. События подписаны и проверены штатной аутентификацией.
Причина тайм-аутов не установлена; Windows System/Application не дали
соответствующего события. Новый backup cycle не запускался.

В 17:51 МСК в «Заметки бизнеса» → «Codex work» отправлено ровно одно
сообщение с меткой `M2-LIVE-20260926-1`. На этот момент Main уже был
остановлен. Сначала проверено фактическое состояние: bridge не имел новой
записи, сообщение в Telegram сохранилось; его не отправляли повторно.
Владелец отдельно разрешил один recovery reset от signed head
`sha256:df335663097ae8c28dbaecb3c8819bf9dcfc58cc8b3c97c3169632e167017653`
и один запуск Main. Reset вернул `RESET`, новый event
`sha256:84d20173bc1200d029659bd86bc36bcb86b36fef7e43cdae41db9e8df4ae7680`;
последующий inspect — `PASS/new`. Main запущен один раз в 18:05;
local/public readiness после запуска — `PASS`, Main `Running`,
Health/Backup `Ready`. Ни config, ни credentials, ни SQLite, ни задания
не менялись.

В 18:06 бот ответил на исходное сообщение: «Задача для продолжения не
определена…». Это не Desktop turn и не успешная приёмка. Read-only SQLite
после ответа: последний bridge request всё ещё от 22.09, `source_message_id=2150`,
`unknown_dispatch`; нового запроса по метке нет. Причина воспроизведена в
исходном коде: Telegram-тема прикрепила `reply_to_message_id` корневого
служебного сообщения; `_parse_command()` при неоднозначной формулировке
трактовал даже явное обращение `@Nobusspacebot` как `topic`-продолжение.
Новый регрессионный тест сначала дал `topic != route`. Локальная правка
считает явное адресование боту новым запросом на выбор маршрута, сохраняя
продолжение по обычному ответу на связанный результат. Затронутый набор
bridge/product/gateway — `292 passed`. Правка пока только WIP: production
по-прежнему выполняет `cdc59a2`, она не установлена и не проверена живым
сообщением. Новое явное `/codex new`-сообщение ожидает отдельного
подтверждения перед UI-отправкой; старую метку не повторять.

## 26.09 — production восстановлен на `cdc59a2`; Telegram-приёмка ещё открыта

По точному подтверждению владельца сверены чистый production `26b95e5`, три
выключенных задания и их прежние XML SHA-256, signed failed journal
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
Точные rollback-копии трёх Task XML, прежнего backup config, health launcher
и каталога проектов сохранены в
`.runtime/m2-desktop-release-20260926/cdc59a2-preflight/`; локальная ветка
возврата — `codex/m2-desktop-26b95e5-before-release`. Credentials и SQLite
не копировались. Чистый `telegram-live` переключён только на утверждённый
`cdc59a2` (tree `0ac7807`).

Новый config создан через O_EXCL под отдельным именем
`backup-cycle-m2-desktop-cdc59a2.json`, канонический digest
`sha256:bd885e5ef5953aae9ac6a38011c5a0f4b49d9f36816d361fb2664aacd929b685`.
Штатно заменено только определение Backup Task в Disabled staging; новый XML
SHA-256 `429f4bdc62d2d6d021889d544760ebada276d2dd096e3b9fd6fc59e2ae790b71`.
Read-only inspect подтвердил старый failed journal и новый config. Signed
recovery rebind выполнен ровно один раз от head `sha256:f82b14b7…47b4`:
новый event `sha256:fdb116d5bc52fc322a77759c0a5d63387a13b70588e47f2221a2eaad8c79f9bf`,
binding `sha256:28c750cb1a0ac8d8b49cb0a2048194efce8dadb0c88fb6d53dddd5a8e39ac852`;
последующий inspect — `PASS/new`.

После проверки будущего расписания включён только Backup Task. Один разрешённый
`--rebind-failed-digest` от точного старого journal завершился `PASS`, создал
VERIFIED generation `daily-20260926T094651-e5271dad8ba84cb9aa8bb4924b94c3e1`
и поднял runtime. Новый signed journal имеет `phase=complete`, digest
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`.
Readback: Main `Running`, Health и Backup `Ready`, production checkout clean
на `cdc59a2`; штатный `--check-ready` — `PASS` (`local_ready=true`,
`public_ready=true`), Health last result `0`. Цикл не повторялся.

Это активация, но не приёмка Gate: новый продуктовый Telegram-запрос,
двустороннее продолжение, реальные вопросы/approve/deny, голос, Артур младший,
две темы, полный ответ и файлы на этом commit ещё не проверены. Действует
согласованная ручная Desktop-граница для неоднозначного текстового R02.

## 25.09 — кандидат `cdc59a2`, ещё не production

Исходники исправления interpreter binding зафиксированы на точном чистом
commit `cdc59a2` (tree `0ac7807`). Широкий L1: `2915 passed, 3 skipped,
5` прежних точно названных исторических deselections, `25 subtests` за
409,74 с. Чистый Git ZIP SHA-256
`16d77414ccb4620c1fa5511f39346b829a1d7601d4b77b3afcff9d4562cddf21`;
исходный и тестовый blobs совпали с Git, связанный L2 в отдельном экспорте:
`491 passed` за 136,24 с. Предупреждение Starlette/httpx историческое и
не относится к изменению. L3 проверил неизменность manifest при выборе
`python.exe`/`pythonw.exe`, привязку SHA обоих базовых файлов и отказ
при отсутствии одного из них; подписанное восстановление по-прежнему
требует нового exact head/journal. Это проверенный **локальный** кандидат,
не readiness, не Telegram D01–D17 и не приёмка Gate.

Важная деталь: `application_binding()` включает Git HEAD. Поэтому эти
послепроверочные записи остаются незакоммиченным docs addendum, а точный
production target — `cdc59a2`; docs-only commit перед выпуском изменил бы
runtime binding и потребовал новой привязки. Для нового production выпуска
запрошено отдельное точное разрешение владельца. Пока оно не получено,
production checkout остаётся на `26b95e5`, все три Tasks Disabled.

## 25.09, вечер — третья остановка, исправление в WIP

После подтверждения владельца Backup Task включён из `Disabled` в `Ready`,
прочитаны точные Task signatures, same-config signed journal, отсутствие
процессов и будущий scheduled run. Один штатный `--recover-failure-digest`
создал VERIFIED generation, но Main вышел с кодом 78
(`recovery_history_blocked`). Новая подписанная failed-квитанция:
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`,
фаза `starting`, admission hold и cleanup доказаны. Backup Task после
отказа оставался `Ready`; его выключили обратимо, readback всех трёх Tasks
теперь `Disabled`. Порт/дочерние процессы отсутствуют. Recovery head
`sha256:f82b14b781526f4a6a8eb75d4e1eb432e5e8ac7bd16da6131796c76a2d6474b4`
сохранился, его состояние по записанному binding — `new`, latch нет.
Telegram live-тесты не начинались, Gate не принят.

Корень второго отказа отличен от предыдущих: rebind через `python.exe`
и Main через `pythonw.exe` читали разные `sys._base_executable`.
Активационный манифест прежнего code commit связывал только один
базовый файл, из-за чего у двух штатных режимов получались разные digests
и Main честно отклонял историю. Exit-only probe реального `pythonw.exe`
подтвердил базовый `pythonw.exe`; read-only вычисление прежнего манифеста
дало digest `sha256:060b26b17559eeed88a2d21a4d051bb227521a7ac5f86fb8c0db24c763b21078`
для console и `sha256:2ef8e1a14d1c924a56d6ad8cd34df10d8c74406857a7f7dd8ced0eb94b602cdc`
для GUI base. WIP-поправка всегда связывает оба базовых исполняемых файла,
не меняя права/sandbox. Регрессия добавляет смену обоих режимов; целевой
тест прошёл, пять связанных supervisor/backup-модулей — `274 passed,
1 warning`. Первый sandbox-прогон fixture был прерван WinError 5 на
системном Temp; тот же тест от файлового владельца прошёл. Код пока не
заморожен; текущий production commit `26b95e5` остаётся выключенным.

## 25.09 — второй production restart остановлен, новая причина локализована

После независимой проверки установлен точный docs-only commit
`26b95e556ac0374e43925ba55e92b119cf212e51` с теми же проверенными
code bytes `fe333c6`. Чистый production checkout теперь на `26b95e5`.
Rollback-снимок: `.runtime/m2-desktop-release-20260925/26b95e5-preflight`;
локальная ветка возврата: `codex/m2-desktop-fa6f1f0-before-recovery`.
Новый backup config создан через O_EXCL, Backup Task заменён в Disabled
staging, точный signed recovery rebind прошёл с inspect `PASS/new`.
Один разрешённый цикл от прежнего failed journal создал VERIFIED generation,
но Main снова завершился кодом 75, readiness нет. Новый signed failed
journal: `sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`;
`failed_phase=starting`, `failure_class=restart_not_ready`, admission hold
и cleanup доказаны, все три Scheduled Tasks Disabled. Telegram-тестов не было.

Это **другая** причина: в момент старта Main Backup Task оставался Disabled.
Активационный валидатор принимает Disabled Health по подписанному backup
restart, но Backup требует Enabled. Read-only проверка на фактическом
snapshot воспроизвела отказ; разрешение Disabled только в копии snapshot
показало, что остальная форма задания проходит. Штатный цикл включает
Main и Health, но не включает Backup: обычный ежедневный режим предполагает
заранее включённый Backup Task. Его ближайший старт до включения —
26.09.2026 03:30 +03:00. Новый `--recover-failure-digest` либо включение
Backup ещё не выполнялись; требуется точное согласование нового шага и
readback перед ним. Исторические доказательства сохранены в
`EVIDENCE.json`, последовательность — в `RELEASE-PLAN-20260924.md`.

## 25.09 — кандидат `fe333c6` и граница выпуска

После узкой поправки проверки архивной signed-квитанции `25` backup-тестов
прошли. Код зафиксирован в одном локальном checkpoint без push/merge.
Независимый по методу чистый Git ZIP-экспорт: SHA-256
`063e6f0c7bc665fe83a0cc65b380aeb32d5fe6b956c21da87db81d95a31dcfb8`,
связанный набор `225 passed, 1 warning` за 126,17 с. Широкий L1 на точном
checkpoint без исторического `tests/gate0` сначала дал `2914 passed,
3 skipped, 6 failed`: пять отказов — старые Gate C0/pre-Gate1 assertions
о прежней публикации/хэшах; шестой — voice-retention timing assertion.
Последний отдельно и в полном своём файле прошёл (`1` и `43 passed`), а
подтверждающий широкий L1 с исключением только пяти точных исторических
test IDs дал `2915 passed, 3 skipped, 5 deselected, 25 subtests passed`
за 441,18 с. Голосовой тест оставался включён. Его одиночный широкий отказ
классифицирован как невоспроизведённая нестабильность тестового прогона, не
как доказанный дефект M2; повторная широкая проверка пройдена без изменения
исходников.

Read-only production preflight: checkout clean на `fa6f1f0`, все три Tasks
Disabled; штатный `--inspect-failure` подтвердил
`failed_operator_required` и прежний точный journal digest
`sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`.
Бот не запускался, Telegram/backup не повторялись. Для перехода на
`fe333c6` и подписанного восстановления требуется новое точное разрешение;
живые D01–D17 и реальный продуктовый паритет не подтверждены.

## 25.09 — точная production staging, неудачный restart и текущая разработка

Владелец подтвердил выпуск именно `fa6f1f08c67968b63bf1d33bab8a2bbfae8217f8`
с точным rollback и ограниченным Telegram smoke. До эффекта `telegram-live`
был clean на `3ea2438`, все три Scheduled Tasks Disabled; их XML и
Health launcher совпали с release plan. Созданы точные rollback-копии в
`.runtime/m2-desktop-release-20260925/fa6f1f0-preflight/` и локальная ветка
`codex/m2-desktop-pre-release-20260925`. Production checkout переведён на
`fa6f1f0`; установлены только проверенный 10-проектный локальный каталог,
staged-disabled Main/Health/Backup и отдельный новый backup config с digest
`sha256:d3837510c95cb1ef1fce7d1a44f8cbc7524c829f04bb85a1349baae1d98be9ad`.
Credentials и Codex не менялись, push/merge не выполнялись.

Старый signed recovery head `recovery_reset` имел digest
`sha256:e911277e820fa2244266d9914e9562403be2cfc37383479ec4a1ce9adbc51885`.
Первый `--inspect-recovery` с **новым** binding закономерно ответил
`runtime_history_invalid`: это сравнение с прежней привязкой, не порча
журнала. Прямое read-only чтение подтвердило прежний event и отсутствие
latch. Однократный разрешённый rebind вернул `REBOUND`, event digest
`sha256:7a77a2b7bd37ea498cc2e97cac16661f9ee44adab02cab2e8b5bf6b112b65062`,
новый binding `sha256:220a5980a0ee1e95ec3dd153d11757645939136813941cfc1d0ee6b4bba905f3`;
повторный inspect — `PASS/new`.

Один разрешённый backup reconciliation от старой завершённой квитанции
`sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`
создал VERIFIED generation
`daily-20260925T110018-12b0d56094fb4793bf3cfa694eb5c87b`, но
завершился `FAIL/backup_cycle_operator_required` на фазе `starting`.
Подписанный failed journal: digest
`sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`,
`failure_class=restart_not_ready`, `admission_hold=true`,
`cleanup_proven=true`. Main вернул код 75 до записи runtime event;
Main/Health/Backup снова Disabled. Цикл и start не повторялись. Причина:
в согласованном backup config journal на `restart_permitted/starting` содержит
подписанное `reconciled_from_digest`, а `_backup_restart_authorized` прежнего
commit допускал только базовые поля и `backup_status`; следовательно
`activation_binding_invalid` (75). Это доказанный production defect.
Новая WIP-поправка принимает только дополнительное поле точного digest при
`backup_status=VERIFIED`, неизвестные поля и неверный digest по-прежнему
отвергаются. Поскольку новый commit изменит application binding, добавлен
отдельный `--rebind-failed-digest`: старый signed failed journal принимается
только при точном digest, verified generation, конкретной фазе/причине,
доказанных admission hold и cleanup, остановленных задачах и валидной новой
конфигурации; прежний журнал архивируется до нового snapshot. Обычный
`--recover-failure-digest` для неизменного config и completed reconciliation
остаются отдельными ветвями. До нового точного разрешения production checkout
не менять, backup recovery не запускать и Telegram-тесты не начинать.

По функционалу R01 неизвестная адресованная текстовая или голосовая просьба
теперь проходит через сохранённое уточнение «создать / продолжить», не
переходит молча к задаче темы. До ответа автора Desktop не получает turn;
истечение времени атомарно закрывает и карточку, и инертный request в SQLite;
это безопасное согласование маршрута через durable Core, **не** полноценный
смысловой выбор проекта/задачи моделью. В R02 безопасный вопрос «Какой цвет
записать в отчёт?» уже классифицируется как QUESTION, явная просьба о
разрешении — UNKNOWN владельцу; для неоднозначного `requestUserInput` нет
доверенного IPC-поля происхождения. Владелец 25.09 согласовал точную
границу: неоднозначный текстовый `requestUserInput` останавливается для
ручного ответа в Desktop; структурированные approvals остаются адресованными
только владельцу по numeric Telegram user_id. Это не доказательство полного
удалённого паритета: живой Telegram-цикл вопросов и approve/deny ещё нужен.

Для ранее не связанной с bridge выгруженной задачи добавлен явный формат
`/codex continue <thread-id> | <проект> | <точный заголовок>`: заголовок
служит только selector UIA, а точные thread ID и `cwd` проверяются через
Desktop IPC до turn. На реальной не связанной задаче
`01a0c547-986f-71c2-9847-ba3a4f5925be` сначала получено
`no-client-found`, затем UIA snapshot нашёл ровно один sidebar item,
`OpenExisting` дал только `invoked-open-task`, после чего IPC подтвердил
исходный ID, заголовок и каталог `nobus-orchestrator-dev`. Нового turn,
Telegram и approvals в этой проверке не было. Отрицательный опыт прежней
задачи `01a0d432…` сохранён, универсальная успешность не утверждается.

Исторический `tests/test_ops_queue1.py` проверен целиком: два отказа были
устаревшими именем health probe и статическим ожиданием `--check-ready` в
installer. Тест теперь проверяет действующий `check_nobus_space_health.py`,
его readiness pair/details и отсутствие записи в `-WhatIf`; **13 passed**.
Затронутый неподвижный набор bridge/IPC/UIA/C6 backup/M1/ops/docs после
последних правок дал `225 passed, 1 warning` за 120,51 с; это ещё не новый
замороженный кандидат и не D01–D17.

## Checkpoint 25.09 — расширенная регрессия и исправление C6-совместимости

На чистой рабочей копии `e5921b8` расширенный запуск `tests` без исторического
`tests/gate0` дал `2894 passed, 3 skipped, 13 failed` за 411,52 с. Отказы
разобраны по владению: три M2-индуцированных C6 migration теста выявили
реальный дефект `inspect_legacy`: два заранее разрешённых точных DDL-хэша
`desktop_bridge_requests` представлены кортежем, а мигратор сравнивал его
с одной строкой. Адресное исправление принимает только перечисленные хэши,
как действующий runtime validator; все шесть `tests/test_c6_migration.py`
прошли. Code commit `935d93037a94f63e9e63395d626ebdec11cff515`, tree
`5588c5552374565db046edcfd2257535e8ced5bb`.

Три других отказа (C5 actual-process crash и два M1 OS/scheduler теста)
прошли адресно от имени владельца файлов (`1 passed` и `2 passed`): общий
запуск sandbox имеет иной Windows/Git identity. Семь оставшихся отказов —
исторические Gate C0/pre-Gate1/ops_queue1 assertions о прежних текстах,
зафиксированных hashes и форме установщика; они не являются проверкой
текущего M2-контракта. Старые Gate и fixtures не изменялись. Полный новый
candidate-bound запуск и L2/L3 после `935d930` ещё не завершены; production
по-прежнему не переключён. Предыдущие exact Task XML и backup journal
квитанции от 24.09 нужно сверить на дрейф перед первым внешним эффектом.

## Локальный code checkpoint и read-only release preflight, около 21:00 МСК

После документального commit `16f9029d4426577ebaa61826b8baa76f6c627c6c`
(tree `d6840c926ec933d89e9cad5ae86381d12f7e0c35`) рабочая копия была
чистой, а заявленный digest EVIDENCE совпал с пересчётом. Чистый Git-экспорт
этого commit, ZIP SHA-256
`0b1bea51ea59137f4e64c15ff24bfeb0f37cef9d18254067c4a55b1f4a0ec62c`,
снова прошёл связанный набор `237 passed, 1 skipped`; единственный skip —
тест, применимый лишь к sender до уже установленного v2 extension.
Независимый старый audit harness на точном commit подтвердил R01–R04.
Его R05 моделирует незарегистрированную папку и закономерно получил отказ;
адресный read-only вызов от пользователя-владельца файлов подтвердил
`registered_worktree=True`, `nested_unregistered=False`. В sandbox тот же
вызов упёрся в Git dubious ownership; Git config не менялся и отказ не
обходился. Это не живое продолжение managed-worktree task и не полная L3.

В той же ветке созданы только локальные commits `7022186` и `55297db`;
точный второй commit `55297db440b502292159f2612c579f588e37c323`, Git tree
`e0cde457c7993791311a6e9249ddb6fb382626e3`. Второй commit исправил
исключительно тестовую среду установщика: он требует Git checkout, поэтому
тест создаёт минимальный временный Git-источник вне репозитория. В рабочей
копии `8 passed`; чистый `git archive` этого commit, ZIP SHA-256
`13f2cf38805de7b9d457bcb8f9a5db96c707c1e3d1466300a20748a3e7e2c18c`,
прошёл все 14 связанных M2-файлов: `237 passed, 1 skipped`. Перед ним
экспорт `7022186` дал 236 успехов и только этот test-fixture отказ; файл
installed sender и production не менялись. В чистом ZIP guard и patch
сохранили exact утверждённые SHA `e20cd35…` / `0ad0f132…` благодаря
адресным `eol=lf` атрибутам. Это положительное L1/L2-кодовое доказательство,
не полный независимый L1/L2/L3 Gate и не Telegram-приёмка.

Read-only preflight трёх Scheduled Tasks подтвердил `Disabled` и точное
совпадение XML SHA с release plan: main `0c911d18…`, Health `e03aeb76…`,
Backup `79d26acc…`. Действующий backup config существует, его заявленный
canonical digest остаётся `sha256:7c3876a3…`. Попытка read-only
`--inspect-failure` из новой ветки получила общий отказ из-за несовпадения
application binding, без эффекта. Тот же read-only инспектор из текущего
`telegram-live` вернул `phase=complete` и прежний signed journal digest
`sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`.
Новый config, staging Task, backup cycle и activation не выполнялись.
Для восьми изменённых исполняемых файлов адресный поиск типовых
OpenAI/GitHub/AWS/PEM ключей дал 0 файлов; новых зависимостей нет.
Исторический all-repo Gate 0 dirty-manifest тест остаётся отдельным
несоответствием окружения и не подменяет M2-критерии.

## Текущий checkpoint — вопросы и разрешения на Desktop 26.917

В том же настоящем Desktop thread
`01a0d43f-edb8-70e2-85ae-5434cc992228` проверен новый формат
`request_user_input_async`: ожидающий вопрос находится в истории как
`agentMessage` с `delivery=async`, а не в прежнем массиве синхронных
`requests`. Ответ должен идти владельцу через `thread-follower-steer-turn`
с точным `questionItemId` и `restoreMessage` (cwd, context, id, время).
Первый изолированный ответ от numeric автора `41` остановился до эффекта:
`restoreMessage` отсутствовал, interaction получил `unknown`; это не
считается успешной доставкой. Read-only IPC после паузы подтвердил тот же
pending и отсутствие `steeringUserMessage`. После исправления и 68 целевых
тестов выполнено **одно** контролируемое восстановление с прежним
`clientUserMessageId`: ACK получен, `steeringUserMessage=1`, pending исчез,
Desktop завершил turn `01a0d45d-6c0e-7351-a712-eea280f16cca` точным
`M2A08-20260924-STEER-4B78A2D0 синий`. Изолированный request
`e828568b-1386-42e3-8488-c61487e1af38` затем завершён штатным monitor:
один итог в fake `topic=12/reply=16`, без текста карточки вопроса.

Новый независимый one-shot request
`27273ac4-33da-41c6-8a81-a5c8b33c46af` прошёл уже весь исправленный
продуктовый путь без ручного IPC: ровно одна карточка обычного уточнения
адресована `41` в fake topic `13`, другой участник `55` получил отказ, ответ
автора продолжил Desktop, финал `M2A08-20260924-FULL-ASYNC-7C4F1B90 синий`
доставлен один раз. Это настоящая задача Desktop, но Telegram-приёмник и
SQLite изолированные; живой Telegram D06 пока не доказан.

Для `item/commandExecution/requestApproval` установленный Desktop добавляет
`availableDecisions`, `commandActions`, `environmentId`, `kind`,
`proposedExecpolicyAmendment`, `startedAtMs`. Старый renderer честно
помечал такую карточку manual/unknown. Теперь все шесть полей показываются
владельцу, неизвестные будущие поля по-прежнему останавливают автоответ.
Bridge сохраняет режим/модель/sandbox задачи, но направляет запрос решения
в `approvalsReviewer=user`; отказ передаёт только реально предложенный
вариант `cancel` (или `decline`, если предложен). Ошибка IPC после atomic
claim переводит request в `unknown_dispatch`, без слепого повтора.

Первый последовательный approval-probe был остановлен ручным renderer;
его безопасный `Write-Output` отменён через точный owner IPC, Desktop turn
`01a0d46d-12ea-7033-834b-342279fd54e2` interrupted, изолированный
request помечен failed. Следующая проверка безопасного разрешения была
временно остановлена **ошибкой тестового сценария**: он ответил на вводную
строку с упоминанием, не на последнюю карточку. Сохранённая карточка
`7002` оставалась pending; сценарий продолжен без нового Desktop turn.
Владелец numeric `99` разрешил ровно `Write-Output`, чужой `41` отклонён;
request `4caa42b0-69ae-49e4-8a3c-32e75c7dc392` стал delivered с одним
итогом в fake topic `15`. В отдельном request
`fe3376c7-e2cd-4f2d-bfd2-197be59785f8` владелец отказал в
`Start-Process calc.exe`; Desktop turn `01a0d475-795c-7651-aeaf-f21e5a5e3f09`
interrupted, в его истории нет `commandExecution`, изолированный request
завершился failed и сообщил об отказе в fake topic `16`. Это подтверждает
узкую owner-границу команды, но не все App/MCP/permissions семейства D08.

Первый связанный запуск из 14 M2-файлов дал `236 passed, 1 skipped`
и один сбой тестового установщика. Причина: `git apply --reverse` из
`--basetemp` внутри родительского Git root не изменял тестовую копию,
хотя вернул 0. Тест теперь восстанавливает старые байты по двум точным
якорям и сверяет утверждённый SHA без `git apply`; адресный файл прошёл
`8 passed`. Установленный sender не менялся. Единый связанный повтор
на текущих bytes завершился `237 passed, 1 skipped`.
Общий прогон с temp внутри Git-root массово падал из-за вложенных Git
fixtures. С temp вне репозитория `pytest -x tests` дал `44 passed`, затем
остановился на историческом Gate 0 dirty-manifest assertion: тест ожидает
другой набор preexisting dirty paths, чем текущий M2 worktree. Legacy
fixture ради M2 не менялась; полный all-repo suite не объявлен зелёным.
Перед checkpoint добавлено точечное `.gitattributes eol=lf` для двух
SHA-bound файлов установщика sender: guard `e20cd35…` и patch `0ad0f132…`.
Read-only `git check-attr` подтвердил правило, source SHA не изменились;
ещё нужно проверить index/checkout bytes после фиксации.
Все one-shot сценарии и sentinel сохранены в ignored
`.runtime/m2-desktop-live-probe/`; их не запускать повторно.
Production бот/Telegram не включались, frozen candidate и D01–D17 отсутствуют.

Установленный notifier проверен отдельно read-only на настоящем session
marker Desktop turn `01a0d46a-dd30-7a11-a963-5ead2fcb8ee3` и точной
изолированной request↔thread↔turn SQLite-привязке: suppression=true.
Непривязанный turn и тот же turn без bridge state дали suppression=false.
Одноразовый скрипт SHA-256
`74b2ec03204afa5a0f4f33ac7fb9f2281d8a94dbfac69d461e712851c46631cf`;
никакой Telegram API не вызывался. Это положительный тест установленного
правила A09, но не доказательство фактического отсутствия второго сообщения
после production activation.

## Текущий checkpoint — реальный UIA ↔ owner IPC, 24 сентября

На установленном Desktop `26.917.9434.0` впервые подтверждён полный
минимальный цикл выбранного транспорта в одном существующем проекте. До
отправки UIA проверила ровно тот уже набранный тестовый текст, выбранный
`nobus-orchestrator-dev` и видимую кнопку «Отправить». Однократный
`SubmitExactDraft` создал задачу
`01a0d432-e0c9-7280-bcd5-4350a8c7843f`; owner IPC обнаружил её, прочитал
завершённый turn `01a0d432-e6b6-7aa0-8e55-fc2a6445aa11` и точный полный
ответ `M2A06-20260924-CONTEXT-5CFBE207 OK`. В списке Desktop задача видна
с правильным `cwd` проекта. `projectId=null` в списке задач не опровергает
выбор проекта: контракт идентификатора между UI и IPC не установлен.

Затем внешний IPC с точным owner и сохранёнными Desktop-настройками выполнил
в той же задаче второй turn `01a0d434-ab36-7c40-aada-f815b814d0dc`;
история дала `M2A06-20260924-IPC-159C7A42 OK`. Обратное направление
проверено семантическим `OpenAndSubmit` в интерфейсе Desktop: третий turn
`01a0d435-e430-7d03-bd48-114f93d7aacb` обнаружен IPC один раз и вернул
`M2A06-20260924-UI-927EA64C OK`. Никаких файлов, сети или команд эти три
тестовых запроса не просили. Это доказывает create/visibility, продолжение
через IPC и UI в одной настоящей задаче, полный короткий финал и правильный
рабочий каталог, но не полный набор D01–D17, не продуктовый Telegram-bridge,
не tools/skills/MCP parity, не вопросы/разрешения и не большой ответ.

Новая read-only диагностика раскрыла прежнюю ошибочную трактовку «черновика»:
в визуально пустом Chromium editor `ValuePattern` и `TextPattern` возвращают
ровно LF + accessible placeholder `Поручите что угодно` (20 символов). Это
не пользовательский текст. После исправления точного placeholder guard
обнаружился второй ложный стоп: в новой задаче Desktop реально две видимые
кнопки «Новый чат», поэтому guard допускает 1–2 при единственной активной
кнопке выбранного проекта. Следующий `SetValue` записал точный запрос, но
мгновенное чтение прежнего значения вызвало ложный отказ до send. Добавлены
короткое ожидание точного readback и отдельный recovery-метод без повторного
ввода/создания; он отправил только уже набранный и дважды сверенный запрос.
Все прежние уникальные метки с неизвестным/предотправочным исходом сохранены
и не повторялись. Windows PowerShell 5.1 parser: 0 ошибок, адресные
UIA/bridge tests: `60 passed` на текущих WIP-байтах.

Дополнительно проверен уже сам `DesktopBridgeService` с настоящим
Desktop UIA/IPC, изолированной SQLite и локальным тестовым приёмником вместо
Telegram. Он создал задачу `01a0d43f-edb8-70e2-85ae-5434cc992228`,
выполнил user turn `01a0d440-6796-7cf1-b932-bd15d0164c82`, сохранил
`delivered` и передал один точный итог в `chat=-1001/topic=7/reply=12`
только в fake API. Следующий новый request продолжил ту же реальную задачу
в `topic=9`: итоговый turn `01a0d442-da65-76b3-842f-ce49f2d939b9`
содержит 6 243 символа финального ответа. Мост сохранил его в двух
Telegram-частях и `answer.md`; digest `answer.md` в локальном ledger равен
SHA-256 полного видимого финала. Созданный Desktop тестовый файл находится
только в `.runtime/m2-desktop-live-probe/`; его bytes совпали с локально
«доставленным» файлом и SHA-256
`b326ff2bfa5d4f34549dccf23ba7b494a92384576fafade12451c0254ee7bd07`.
Все четыре слота второй доставки — `sent`. В первой диагностике `answer.md`
ошибочно сравнили с финалом *вместе* с отдельным commentary модели;
read-only сверка исправила сравнение, продуктового дефекта здесь нет.
Это не настоящий Telegram send и не проверка установленного sender/runtime.
Read-only notifier ledger показывает `sent` для bootstrap и обоих ходов
этой изолированной задачи: её SQLite не является production bridge binding,
поэтому эти обычные summary не доказывают bridge opt-out.

Связанный набор после UIA-исправлений и checkpoint-документов:
`230 passed, 1 skipped` в 14 файлах. Независимый полный L1/L2/L3 по
замороженному кандидату всё ещё не проводился.

Результаты одноразовых probe лежат только в ignored
`.runtime/m2-desktop-live-probe/` и привязаны в `EVIDENCE.json` к точным
маркерам, thread/turn ID и SHA скриптов. Production bot по последнему
подтверждённому снимку остаётся Disabled; продуктовый Telegram request не
отправлялся. Read-only one-shot ledger глобального notifier содержит `sent`
ровно для каждого из трёх test turn; это три автоматических summary, не
полная продуктовая доставка и не доказательство отсутствия повторов в
Telegram без отдельной сверки сообщений. Gate остаётся WIP и не принят.
Следующие разрешённые проверки:
реальный pending question/approval с owner-only адресацией, полный большой
ответ/файл и продуктовый bridge через Telegram после безопасной подготовки
кандидата и backup/activation. Никакой один short turn не доказывает
полный паритет Desktop.

## Предыдущий checkpoint — аудит готовности 24 сентября

В этом же worktree исправлены воспроизводимые R01–R05 без нового импорта
Grok. R01: естественная текстовая/голосовая просьба о создании не превращается
в продолжение; неизвестный проект выбирает автор в долговременной карточке,
голос сначала подтверждает расшифровку. Reply на связанный запрос/итог
продолжает его, адресация другому боту отклоняется. R02: обычный вопрос
«Какой цвет записать в отчёт?» идёт автору; явное согласие/разрешение и
неизвестные формы остаются у владельца/в Desktop. Это не доказательство
универсального классификатора всех App/MCP вопросов. R03: точный pending
interaction переживает смену поколения соединения без повторной карточки;
изменение payload, owner, turn или expiry по-прежнему останавливает ответ.
R04: до внешней отправки фиксируются ordered references, digest и стабильные
слоты; после частичной доставки новый файл досылается, ранее отправленный
не повторяется, изменившиеся bytes переводят результат в unknown. R05:
продолжение допускает точный корень проекта или реально зарегистрированный
Git worktree с тем же common-dir, но не произвольный cwd. Проверка нового
Desktop task в managed worktree остаётся live-пунктом.

UIA read-only после открытия окна владельцем увидела установленный Desktop
`26.917.9434.0`, точный проект и один заголовок активной задачи. Позже
запуск из sandbox-пользователя видел 0 окон, несмотря на видимое владельцу
окно; разрешённый read-only запуск в интерактивном контексте увидел процесс
8312. Когда владелец открыл пустую новую задачу, UIA обнаружила несколько
`RootWebArea`; только один содержит app-root `AutomationId=root` и проект.
Адаптер теперь выбирает его однозначно или останавливается. В новом виде
видны отдельный от боковой панели активный проект и кнопка «Новый чат»;
точный read-only предохранитель `new_task_project_context_verified=true`
прошёл на реальном Desktop. Он запускается до ввода и непосредственно перед
`send`; проверка заголовка продолжения остаётся отдельной. После ручного
переключения на существующую задачу того же проекта тот же read-only
предохранитель вернул `false`: активного project control вне sidebar больше
нет, хотя проект там по-прежнему виден. Из диагностического снимка удалён
вывод названий элементов задачи; проверяются только структурные признаки.
Ничего не вводилось и не отправлялось. Реальный create/send с IPC-correlation
остаётся отдельной live-проверкой A06.

Изолированная SQLite с точной DDL checkout `3ea2438` имеет ожидаемый digest
`c9b10b0f…` и успешно проходит аддитивную миграцию один раз. Чтение реальной
production SQLite из sandbox получило `Access denied`; обхода доступа и
изменения live не было. Это не закрывает A01 с реальными данными/журналом.
Три Scheduled Task остаются по последнему подтверждённому снимку Disabled;
в этом ходе они не переключались. Не переисполнять старый Telegram request
`e18a5ca3-95d3-4be8-8453-630d88e97a50`.

Для A09 отдельно установлен по подтверждённым точным SHA guard существующего
`nobus-send-results`: при активном bridge-owned Desktop thread или ещё
непривязанном create bootstrap прямой send через skill отвергается по
read-only SQLite; обычный thread после завершения bridge и прежний режим
без bridge-конфигурации остаются доступными по локальным тестам. Восемь
адресных тестов прошли, включая атомарную замену в fake-home и идемпотентный
повтор. Установленные sender/guard имеют соответственно SHA-256
`d38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e`
и `e20cd35d1d09fc5c90ee91fe37bf80b4057de86ab4bb9e117d2ae0f0e6e6fe20`;
старый sender сохранён с исходным SHA. Первую реальную staging-попытку
остановил Git dubious ownership до изменения skill; причина исправлена без
изменения утверждённых целевых байт. Положительный live тест единственного
отправителя и rollback ещё впереди; детали — в
[RELEASE-PLAN-20260924.md](RELEASE-PLAN-20260924.md).

Точный связанный набор на текущих WIP-байтах: **226 passed, 1 skipped** в
14 файлах M2 (без повторной приёмки C6/MVP1). Windows PowerShell parser
для изменённого UIA-скрипта: 0 ошибок; `pip check`: зависимости согласованы.
Разбор 42 эвристических security findings — в
[SECURITY-TRIAGE-20260924.md](SECURITY-TRIAGE-20260924.md); CVE-аудит не
проводился. Установка skill — единственное внешнее изменение этого
checkpoint; Desktop turn, Telegram send, Task/config/credentials, bot activation,
push и merge не выполнялись. Полный независимый L1/L2/L3 по одному
замороженному кандидату не проводился; D01–D17 по-прежнему не приняты.

Следующий безопасный шаг: завершить A06/A09 live и readback/rollback A01 на
доступном изолированном реальном снимке, затем закрепить точный кандидат и
его проверки. Положительный bridge-turn, Telegram-доставка, реальный Артур
младший и controlled activation требуют самостоятельных квитанций; успешные
fixtures не заменяют их. Публикации/push/merge в этом ходе не было.

## Исторический снимок остановки для независимого аудита — 22 сентября

Разработка и live-проверки остановлены по прямому запросу владельца из-за
лимита. Не отправлять новые Telegram-сообщения, не запускать Desktop turn и не
возобновлять production до завершения независимого аудита и нового явного
продолжения владельца. Подробная хронология, баги, блокеры, тесты и решения
вынесены в [AUDIT-JOURNAL.md](AUDIT-JOURNAL.md). Нижележащие разделы этого
документа сохраняют checkpoint 21 сентября; их утверждения «не выполнялось» и
«ожидает разрешения» являются историческими и не переопределяют этот снимок.

Точный Git-снимок разработки:

- HEAD `3ea243893a2647dc631662c2a2030de7679ae0e1`, ветка
  `codex/m2-desktop`, рабочая копия была чистой перед документированием;
- локальные commits: `3d6514d` (единый Telegram↔Desktop bridge), `3ac1cac`
  (миграция bridge schema до backup admission), `3ea2438` (UIA scroll перед
  созданием задачи);
- код не опубликован и не слит в `main`; полный независимый L1/L2/L3 по
  замороженному кандидату не выполнялся, Gate не принят.

Фактическое состояние live-контура при остановке:

- production checkout `Code\worktrees\telegram-live` находится detached на
  `3ea243893a2647dc631662c2a2030de7679ae0e1`; связанная backup-конфигурация и
  действие Scheduled Task были переведены на этот revision;
- подписанный activation rebind на новый код прошёл; binding
  `sha256:fddb39bbdfb5d2cd6403a9a19f89ff8805154eb0d41967890e084d391913f3fb`;
- непосредственный запуск Core остановился fail-closed до Telegram-сессии:
  новая application binding не имела свежей совместимой backup generation;
- штатный recovery reset для точного terminal event прошёл, а проверка тем же
  `pythonw.exe` вернула `PASS`, state `new`, last digest
  `sha256:e911277e820fa2244266d9914e9562403be2cfc37383479ec4a1ce9adbc51885`;
- последующий backup cycle завершился Scheduler result `1`. Его post-failure
  inspection показал только прежний/непривязанный `phase=complete`, digest
  `sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`,
  тогда как отдельная read-only `load_config` тем же production `pythonw.exe`
  прошла. Точная граница этого отказа пока не установлена; цикл не повторять;
- на 12:29 МСК все три задания `NobusSpaceBot`, `NobusSpaceBot-Health` и
  `NobusSpaceBot-Backup` остановлены и Disabled. Это намеренная безопасная
  пауза, а не рабочий production-статус.

Live Telegram-факт текущей итерации:

- в «Заметки бизнеса» → «Codex work» после подтверждения владельца отправлен
  ровно один тестовый запрос, Telegram message id `2150`; бот ответил
  «Задача принята и передаётся в Codex Desktop.»;
- bridge request `e18a5ca3-95d3-4be8-8453-630d88e97a50` завершён как
  `unknown_dispatch`, без `desktop_thread_id` и `turn_id`;
- read-only список задач Desktop подтвердил, что новая задача не появилась.
  Запрос не исполнился и не должен повторяться автоматически;
- причина локализована в UIA: точная кнопка создания была `offscreen=true`,
  хотя поддерживала `ScrollItemPattern`. Исправление вызывает
  `ScrollIntoView()` перед `Invoke`, fail-closed при отсутствии pattern; 29
  целевых тестов прошли за 2,04 с, read-only wrapper snapshot прошёл;
- после исправления новый Telegram-запрос не отправлялся. Следующая попытка —
  только как новый request после аудита, восстановления production и нового
  подтверждения действия.

Не завершено: реальный Desktop create/start через исправленный путь, IPC ACK и
turn id, двустороннее продолжение, полный финал, question/approval approve и
deny, файл, reconnect, голос, две темы, реальный Артур младший и полный D01–D17.
DOCX-памятка пользователя не изменялась. Исторический отдельный App Server
writer-блокер и положительные read/visibility-доказательства сохраняются без
повторения.

## Контракт результата

Цель — один сквозной Gate управления настоящими задачами Codex Desktop из
доверенной группы Telegram: создание и продолжение задачи в выбранном
сохранённом проекте, полный ответ, вопросы и штатные разрешения, артефакты,
восстановление и ровно один владелец каждой доставки.

Границы текущей стадии: локальная реализация, offline-проверки и read-only
обследование работающего Desktop. Историческое разрешение прежнего live-probe
не действует для новых изменяющих операций. Новые Desktop turn/approvals,
намеренные Telegram-действия, изменение notifier/BotFather, установка,
публикация и deploy не выполнялись. Два автоматических Telegram-уведомления
прежнего App Server probe сохранены как исторический внешний эффект.

## Что подтверждено

- В установленном Codex Desktop найден сохранённый проект этого репозитория и
  текущая реальная задача проекта. Встроенная поверхность Desktop поддерживает
  операции создания, продолжения, чтения полного ответа и ожидания вопросов,
  однако сама по себе она не является внешним API для Nobus Space.
- На Desktop `26.915.4065.0` реально прошли `initialize` версии 0 и
  `thread-owner-discovery` версии 1 через `\\.\pipe\codex-ipc`; для существующей
  задачи разработки найден owner, `supportsUntrustedAppInput=true`. Probe не
  отправлял turn и не отвечал на вопросы/approvals. Это положительное
  доказательство отдельного owner-follower маршрута внутри работающего Desktop,
  а не повтор прежнего отдельного App Server.
- Статическое чтение того же установленного bundle подтвердило версии follower-
  методов: start turn 2, полная история 1, ответы command/file/permissions,
  user input и MCP elicitation 1, stream-state broadcast 11; interrupt/update
  settings требуют точной привязки payload перед использованием. Наличие метода
  не засчитано как полный цикл события или паритет.
- Read-only Windows UI Automation в интерактивном пользовательском сеансе
  обнаружил окно `Chrome_WidgetWin_1`, 600 доступных элементов и 22 элемента с
  AutomationId. Точные кнопки проекта `nobus-orchestrator-dev`, создания новой
  задачи и открытия обеих существующих задач доступны через семантические
  `ExpandCollapse`/`Invoke`; composer предоставляет `Value`/`Text`. Фокус,
  Invoke, ввод и координатные действия не выполнялись.
- Добавлен минимальный async IPC adapter
  `src/integrations/codex_desktop_ipc.py`: bounded little-endian frames,
  version profile, owner targeting, timeouts, reconnect safe-read, ответы на
  вопросы/approvals и fail-closed `UNKNOWN` после lost ACK без слепого повтора.
  `src/integrations/codex_desktop_uia.py` фиксирует только точные selectors и
  запрещает неоднозначный/неподдерживаемый выбор; выполняющего UI backend до
  нового live-разрешения нет.
- 13 offline-тестов IPC/UIA прошли. Они подтверждают framing, routing, version
  mismatch, отсутствие fallback, reconnect, owner-targeted responses и
  readback-first recovery; fixtures не считаются реальным Desktop turn.
- Производный roadmap совпадает с источником, JSON evidence разбирается, все
  относительные ссылки внутри checkpoint scope M2-DESKTOP разрешаются. Общий
  `tests/test_documentation.py` дал 3/4 PASS: link-test видит сохранённые ранее
  ссылки на отсутствующий именно в этом worktree `ARCHITECT-HANDOFF.md` и на
  ignored исторические `.runtime/m1-s1-*` receipts. Эти чужие WIP/evidence не
  копировались и тест не ослаблялся; ограничение не связано с IPC adapter.
- Установлены Desktop `26.915.4065.0` и поставляемый с ним Codex App Server
  `0.155.0-alpha.9.2`. Статический разбор установленного Desktop bundle показал:
  наблюдаемый локальный Windows host запускает собственный дочерний App Server
  через `stdio`;
  ветка общего daemon/control socket разрешена только не на Windows и при
  отдельном feature-флаге. Это привязанное к версии наблюдение, а не публичный
  контракт OpenAI.
- Отдельный read-only stdio-пробник тем же бинарным файлом получил каталог
  проектов, нашёл существующую задачу Desktop по `cwd` и прочитал её по точному
  идентификатору. Совпали рабочая папка, originator и версия протокола. Ответ
  `thread/read` не содержал `projectId`, а фильтр по идентификатору из
  `project/list` эту задачу не вернул. Контракт не требует наличия либо равенства
  таких идентификаторов, поэтому несовместимость проекта из этого не следует.
  Положительно подтверждён путь чтения общей реальной задачи; создание и
  двустороннее продолжение проверены отдельным живым экспериментом ниже.
- Поставляемый App Server создал одну persistent-задачу `M2-DESKTOP live probe`
  с `cwd` существующего проекта. Desktop показал её в списке, прочитал по тому
  же thread ID и отобразил полный финальный ответ. Затем Desktop успешно
  выполнил второй turn в том же thread; raw `thread/read` отдельного App Server
  увидел оба завершённых turn и оба полных финальных сообщения.
- Эфемерный `remoteControl/enable` в том же foreground App Server без daemon-
  установки перешёл `disabled → connected`, получил environment ID и был явно
  возвращён в `disabled`. Это подтверждает доступность Remote Control у
  поставляемого бинарного файла, но не наличие документированного стороннего
  Remote-клиента для Telegram bridge и не подключение к приватному процессу
  Desktop.
- Схема установленной версии содержит проекты, start/resume/read задач,
  пагинацию turns/items, attachments, вопросы и семейства approvals. Наличие
  методов в схеме не засчитано как пользовательский паритет.
- Все восемь установленных файлов notifier и `nobus-send-results` совпали с
  SHA256 канонического manifest от 2 сентября 2026 года. Их установленная
  конфигурация не менялась.
- One-shot ledger существующего notifier содержит `sent` для обоих turn
  тестовой задачи. Следовательно, в «Заметки бизнеса» → «Codex work» ушло два
  автоматических уведомления — по одному на turn, без дубля. Bridge и
  `nobus-send-results` их не вызывали, но условие эксперимента «без Telegram»
  фактически не выполнено. Сообщения не удалялись, notifier/ledger/config не
  менялись.
- В текущем notifier нет per-task исключения. Настройки содержат только
  глобальный `enabled`; wrapper отправляет непустой финал каждой зарегистрированной
  основной задачи, включая fallback без marker, а reconciler сканирует весь
  реестр. Без изменения установленного notifier или точного разрешения на
  ожидаемое уведомление новый live-turn недопустим.
- Подтверждены существующие ограничения повторного использования: старый ключ
  отправки связывает только назначение и digest файла, а notifier хранит лишь
  краткий финальный summary. Для M2-DESKTOP нужен совместимый operation key v2
  и чтение полного результата по точному turn; второй Telegram sender запрещён.

## Что не подтверждено

Новый owner IPC ещё не выполнил изменяющий turn. Не подтверждены ACK и реальный
turn id, получение всех событий вопросов/approvals, approve/deny, полный
readback результата и артефактов, reconnect после настоящего разрыва, Desktop-
host tools и паритет settings/model/skills/MCP/plugins. Наличие обработчиков и
offline fixtures не заменяет эти проверки.

UIA доказал доступность точных semantic selectors, но не создание/открытие:
неизвестно, появляется ли conversation id/owner сразу после `Invoke` новой
задачи или первый prompt тоже потребуется передать через проверенный UIA
pattern. Нет доказательства безопасного поведения при закрытом/заблокированном
сеансе. CDP не запускался.

Штатные Remote Connections, managed daemon, отдельный App Server и Desktop
owner IPC остаются разными механизмами. Исторический writer-блокер относится
к отдельному App Server и сохраняется; он не блокирует автоматически follower-
делегирование существующему Desktop owner. Общая история с изолированным CLI
по-прежнему недостаточна. Gate не принят; D01/D03/D07/D09/D13/D17 требуют live.

## Критерий совместимости с Desktop

Совместимость подтверждается поведением реальных задач в выбранных существующих
проектах: задача видна в Desktop; один thread последовательно продолжается со
стороны Desktop и внешнего адаптера; `cwd`, проектный контекст и требуемые
функции Desktop корректны; вопросы и разрешения проходят через штатные
механизмы. Совпадение PID, транспортного процесса или идентификаторов разных
API не требуется без документированного контракта. Отдельный процесс адаптера
разрешён.

Официальные источники, проверенные 21 сентября 2026 года:

- [Remote connections](https://learn.chatgpt.com/docs/remote-connections) —
  setup начинается в Desktop; подключённый хост предоставляет те же проекты,
  чаты, credentials, plugins, skills, tools и approvals.
- [Codex App Server](https://learn.chatgpt.com/docs/app-server) — app-server
  предоставляет history, streaming и approvals, но отдельные app-server/WebSocket
  transport не являются доказательством связи с Desktop; WebSocket пока
  экспериментален и не поддерживается для production.
- [ChatGPT desktop app for Windows](https://learn.chatgpt.com/docs/windows/windows-app) —
  Desktop и native Windows Codex используют общий Codex home, поэтому одна
  история на диске сама по себе не доказывает общий исполняющий процесс.

## Ограничения источников

Nobus Memory 21 сентября снова подтвердил `READY`, официальный CLI-маршрут,
читаемость vault и единственный разрешённый scope `project:nobus-space`;
`write_mode=limited_auto`. Scoped search текущего M2-DESKTOP завершился
`MEMORY_OPERATION_FAILED`; неизменный запрос, bridge и fallback не повторялись.
Vibecoding требует `project:prostranstvo`, которого нет среди разрешённых scope,
поэтому новый контекст этой базы не выдумывался. Git, новое исследование,
локальное IPC/UIA-наблюдение и тесты остаются доказательствами текущего шага.

## Проверенный предел managed daemon

Владелец разрешил ограниченный интеграционный эксперимент без установки.
`remote-control start` был проверен сначала с Desktop plugin binary, затем с
перенесённым Desktop CLI. Оба завершились до запуска с
`no complete local package`. Попытка выполнить in-package `resources/codex.exe`
напрямую отклонена Windows AppX ACL. Проверка после отказов подтвердила:
standalone package отсутствует, control socket отсутствует, daemon не запущен;
созданы только два пустых lock-файла daemon lifecycle. Эти попытки задачу не
создали.

Ошибка `no complete local package` относится только к проверенному способу
запуска managed daemon. Она не доказывает, что daemon нужно устанавливать для
MVP2. Дополнительная проверка поставляемого Desktop bundle закрыла отдельный
вопрос: в наблюдаемой конфигурации Windows Desktop выбирает private stdio, а
встроенная daemon-ветка на Windows недоступна. Поэтому его установка в текущей
версии не создаст общий writer и не
является следующим шагом.

## Исторический App Server эксперимент и локализованный блокер

Разрешённый эксперимент создал ровно одну тестовую задачу через отдельный
штатный stdio App Server. После Desktop-turn попытка нового внешнего
`thread/resume` завершилась `thread ... already has an active writer`, хотя
turn был завершён. Проверка альтернативной семантики без `resume` дала
`thread not found`. Официальный `thread/unsubscribe` относится только к
текущему соединению; после последнего подписчика App Server сохраняет thread
загруженным до 30 минут. Внешнего метода освободить writer приватного процесса
Desktop в доступном контракте нет.

Это конкретный блокер отдельного короткоживущего stdio-адаптера: он создаёт
видимую задачу и читает Desktop-turn, но не может своевременно вернуть себе тот
же исполняемый thread после продолжения из Desktop. Общая история здесь
положительно доказана, однако она недостаточна для требуемого туннеля.

Дополнительно выявлена версия контракта: pinned SDK `0.144.4` не разбирает новый
item `functionCallOutput`, который Desktop `0.155.0-alpha.9.2` записал во второй
turn. Raw-схема установленной версии прочитала результат полностью. Это не
причина writer-конфликта, но обязательная совместимость будущего адаптера.

Штатные Remote Connections дают официальным клиентам ChatGPT проекты, задачи,
инструменты и approvals хоста. Foreground App Server подтвердил соединение с
Remote relay без установки daemon, однако публичный контракт для стороннего
Telegram-клиента не найден. Официальная документация App Server описывает
подключение клиента к выбранному процессу и отписку своего соединения, но не
handoff writer между private stdio-процессами. Локальный bundle дополнительно
показывает, что Desktop умеет распознавать конфликт active writer и имеет
внутренние роли owner/follower. Прежний вывод «внешнего метода получить эту роль
нет» заменён новым фактом: owner IPC обнаруживает владельца и маршрутизирует
follower-запросы. История отдельного App Server не удаляется и не переносится
на новый транспорт.

## Текущий IPC/UIA checkpoint

Основной технический вопрос сузился: принимает ли найденный Desktop owner через
IPC реальный start turn, выдаёт ли подтверждаемый turn id и все нужные события,
а UIA — создаёт/открывает ли задачу без неоднозначного ввода. Локальный adapter
и 13 тестов готовы к этому smoke. Установка daemon, патч Desktop, CLI fallback,
запись в БД, CDP и изменение ACL/PATH/config не нужны.

### Подготовленный ограниченный live-сценарий

- **Проект:** существующий `nobus-orchestrator-dev`; одна новая тестовая задача
  `M2-DESKTOP owner IPC smoke`. Существующая Gate-задача и прежний
  `M2-DESKTOP live probe` не заменяются и не удаляются.
- **UI:** только точные accessible names и `ExpandCollapse`/`ScrollItem`/`Invoke`/
  `Value` patterns найденного окна Codex. Сначала выбрать проект и вызвать
  создание задачи. Если owner ещё не появился, разрешён ровно один первый prompt
  через проверенный composer новой задачи; при неоднозначности немедленно STOP.
- **IPC:** initialize не повторять как отдельный research probe; adapter выполняет
  его как часть соединения, затем owner discovery, один start turn с уникальным
  `clientUserMessageId`, ACK, stream/history readback и контролируемый reconnect.
  После lost ACK — только history/readback, без автоматического второго turn.
- **Двусторонность:** один follow-up отправить со стороны видимого Desktop через
  точный semantic UIA control, затем один через owner IPC; подтвердить один
  thread, порядок turns, рабочую папку и полный текст. Пользовательский ручной
  ввод остаётся отдельным финальным доказательством D03, а не подменяется UIA.
- **Вопрос:** тестовый turn вызывает структурированный `requestUserInput` без
  внешнего эффекта; harness получает pending event и отвечает по точному
  request/thread/turn. Это проверяет транспорт, но ещё не Telegram-author policy.
- **Разрешения:** запросить один безвредный read-only network `HEAD` к
  `https://example.com/` и одобрить; отдельно запросить запуск Calculator и
  отклонить до запуска. Если Desktop/auto-review не создаёт pending event,
  зафиксировать конкретную границу и не имитировать PASS.
- **Файлы:** читать/создавать только
  `.runtime/m2-desktop-live-probe/source-v1.txt`,
  `desktop-owner-ipc-created.txt` и `owner-ipc-smoke.json`. Никаких файлов за
  пределами этого каталога, кроме обычной истории самой тестовой задачи.
  Подготовленный `source-v1.txt`: 159 bytes, SHA256
  `e8f15053821c09313dbcb61b6cae404cd64c931b28a87b2b2ed2d7b9ab332b88`.
- **Telegram:** product ingress, ASR, bot-to-bot и sender в этом smoke не
  запускаются. Установленный глобальный notifier может автоматически отправить
  до пяти completion-summary в доказанную тему «Заметки бизнеса» → «Codex work»
  — по одному на фактически завершённый turn. Сообщения не удалять, notifier и
  ledger не отключать/очищать. Не выдавать summary за полный результат.
- **STOP/восстановление:** несовпадение версии, несколько UIA matches, отсутствие
  owner, неизвестный event, потерянный ACK без однозначного readback, неожиданный
  путь/сеть или лишнее уведомление останавливают сценарий. Сначала читать history
  и notifier receipt; неизвестный эффект не повторять.

Для выполнения этого сценария требуется новое точное разрешение на: одну задачу,
до пяти turn, перечисленные semantic UIA/IPC mutations, один `HEAD`, один
заведомо отклоняемый Calculator request и ожидаемые notifier-summary. Оно не
разрешает явные Telegram-тесты продукта, изменение notifier, установку, CDP,
публикацию или deploy.

После успешного smoke продолжить локальную реализацию Core↔Desktop и единого
delivery operation; затем отдельно подготовить и разрешить реальные Telegram/
Артур/голос/две темы/D01–D17. Gate остаётся `WIP_ITERATION`, не BLOCKED и не
ACCEPTED. Публикация и активация не выполнялись.

## Локальное возобновление 24.09.2026 — незамороженный WIP

Предыдущие разделы выше — исторические checkpoint. После них независимый аудит
в каноническом репозитории восстановил успешные live-квитанции owner IPC:
создание/видимость/продолжение задачи, вопрос в Plan и ручные approve/deny у
user reviewer. Эти квитанции не означают прохождение продуктового Telegram-цикла.
Перед возобновлением HEAD назначенного worktree был
`31df0d00a0a74de920a7a7367d3b662566a653ff`, дерево чистое. Все
изменения ниже остаются незакоммиченным локальным WIP в этом worktree.

Три ZIP Grok приняты по неизменным SHA256 из канонической проверки поставок.
Модули G-A/G-B/G-C импортированы адресно; GA-01, GB-01…04, GC-01…05 и
IN-01 исправлены в них. `format_final_blocks` подключён к доставке видимых
финальных блоков как Telegram HTML с plain fallback; исходный полный текст
сохраняется для артефакта `answer.md` при многочастном ответе. Карточки
вопросов/разрешений подключены через literal/plain text: `echo **literal**`
остаётся командой, а не Markdown. Парсер ссылок подключён к snapshot файлов;
дополнительные локальные корни задаются оператором явно, вне них файл не
отправляется. Указание пути не заменяет фактическую проверку regular file,
reparse component, размера, bytes и чувствительного содержимого.

Сделано по аудиту:

- A01: отдельный `--reconcile-complete-digest` для завершённого журнала с
  прежним config digest. Нужны точный digest прежней квитанции, остановленные
  задачи и проверка runtime; прежний сертификат архивируется до новой
  попытки. На синтетическом изолированном цикле проверены отказ без
  подтверждения, отказ при работающих задачах, новый attempt ID и сохранение
  старого журнала. Рабочий backup не запускался.
- A02: перед отправкой сравниваются request ID, method, payload digest, thread,
  turn и kind; право ответа CAS-захватывается до эффекта и учитывает expiry.
  При lost ACK читается история без автоматического повтора. Локальный тест
  воспроизводит смену payload и истечение срока во время history read — вызова
  ответа Desktop нет. Между последним read и самим IPC ответом остаётся
  нетранзакционная гонка Desktop; live-квитанция продукта ещё нужна.
- A04/A05: карточка показывает существенные параметры, exact question IDs и
  неизвестные вложенные поля; неотображаемое безопасно переводится в ручной
  ответ в Desktop. Вопросы и approvals идут в исходную тему с numeric
  `tg://user?id=...`; ответ принимается только от назначенного user ID и из
  исходной темы. Установленный Telegram Bot API дополнен HTML parse mode.
- A06: один bootstrap удерживает внутрипроцессный и межпроцессный lock до
  correlation с созданной задачей. UIA не меняет непустой черновик и проверяет
  точное значение перед отправкой. Проверка активного контекста после ручного
  переключения владельцем ещё требует контролируемого Desktop live-сценария.
- A07: `reply` на исходное поручение или доставленный результат связывает
  нужный thread; неоднозначная тема без reply останавливается. Принимаются
  bare UUID и `codex://threads/...`, проект с пробелами. Runner получил
  явный JSON-каталог существующих проектов; UIA обязан найти проект по имени
  при использовании. Автоматическая полнота каталога Desktop и managed
  worktree не доказана.
- A09: известный `delivery_partial` можно попросить доставить заново по ID
  исходного запроса без нового turn; `delivery_unknown` не повторяется.
  Подготовлен минимальный патч существующего sender runtime:
  [telegram-delivery-runtime-v2.patch](telegram-delivery-runtime-v2.patch)
  добавляет optional operation_key и read-only receipt, сохраняя v1 CLI.
  Патч применён и проверен только на игнорируемой копии: v1 ключ не меняется,
  два запроса одного файла имеют разные ключи, receipt возвращает message_id.
  Продуктовый adapter теперь сохраняет proof-bound смысл destination_ref
  (бот, binding, topic), а request/part отделяет в operation key. Локальные
  тесты адаптера проходят; с установленным v1 bridge fail-closed при opt-in.
  Патч к установленному файлу НЕ применён. Текст запускаемого Desktop turn
  теперь прямо запрещает самостоятельный вызов `nobus-send-results`: Bridge
  обозначен единственным владельцем доставки. Это не техническая блокировка
  skill; её устойчивость и матрица callback/reconciler/notifier всё ещё
  требуют проверки (`33 passed` в адресном bridge-наборе после изменения).
- A10: полный ответ проходит HTML/plain Telegram formatter, код/таблицы
  разбиваются с учётом лимитов; артефакты отправляются отдельно. Реальный
  длинный ответ/файл ещё не доставлялись новым продуктом.
- A11: три битые навигационные ссылки на отсутствующий в этой ветке
  `ARCHITECT-HANDOFF.md` заменены точными указателями на актуальные документы;
  docs16 пересоздан из docs15; четыре documentation-теста проходят.
- A12: Desktop bridge в общем runner теперь opt-in через `--desktop-bridge`,
  поэтому обычный старт MVP1 не создаёт активный bridge. Это только локальная
  защитная граница: recovery, backup, миграция и rollback production требуют
  отдельного разрешения и проверок на изолированных копиях.
- A13: подготовлена read-only проверка request↔thread↔turn по durable SQLite,
  которая отвергает скопированный маркер. Подготовлен
  [notifier-auth-v2.patch](notifier-auth-v2.patch) к существующему notifier:
  один только синтаксис маркера не подавляет summary, требуется exact durable
  binding. `git apply --check` на свежей локальной копии прошёл; на ранее
  подготовленной патченной копии функциональный тест проверил настоящий
  binding, чужой request, другой turn и отсутствие bridge DB (`2 passed`
  вместе с verifier). Попытка записать patch в повторную временную копию
  получила отказ песочницы; установленный notifier НЕ изменён. При
  отсутствующем `bridge_state_path` уведомление не подавляется. До
  разрешённого подключения, проверки реального notifier и сбоев delivery
  A13 не закрыт.

Целевые локальные результаты: исходные и дополнительные Grok-контракты —
`100 passed`; связанные bridge/UIA/Telegram API — `232 passed` на одном WIP
срезе; runner/bridge/notifier/doc — `63 passed` на следующем; последние
bridge-тесты после redelivery — `32 passed`. Один адресный A01-тест прошёл.
Это разные изменявшиеся WIP-срезы, их нельзя суммировать или объявлять
независимым L1/L2/L3. Попытка запустить полный файл C6 backup-тестов была
отклонена auto-review как повторное открытие C6; тесты C6 после этого не
обходились. Полный gate suite и L1/L2/L3 на замороженных bytes не выполнялись.

После поздних правок A09/A13 связанный non-C6 regression-набор из 12 файлов
(`desktop_*`, IPC/UIA, Telegram runner, доставка и docs) завершился
`187 passed` за 20,08 с на текущем WIP после уточнения единственного
владельца доставки. Более широкий предыдущий срез
давал `287 passed`, но относится к прежним bytes и не переиспользуется для
этого кандидата. `git diff --check` не выявил ошибок
пробелов; CRLF-предупреждения Git относятся к правилам checkout. Это всё ещё
локальный WIP, не независимая приёмка.

Открыто до цельного кандидата: установка и проверка подготовленных расширений
общего sender/notifier по отдельному точному разрешению; исключение второго
skill-вызова внутри bridge-turn; надёжная проверка контекста UIA и managed
worktree; режим Plan/
Default и все семейства pending; обновление machine evidence и документов на
один SHA; изолированная проверка rollback/backup; независимый L1/L2/L3.
После этого только по новому точному разрешению — live-матрица D01–D17,
активация и приёмка. Production/Desktop/Telegram/notifier/skill в этом
возобновлении не менялись **на момент предыдущего снимка**; следующий
checkpoint ниже заменяет эту часть состояния.

## Checkpoint 24.09.2026 — Desktop 26.917 и установленные расширения

Это продолжение того же Gate и незакоммиченного worktree, не новый Gate.
Установленный Desktop теперь версии `26.917.9434.0`. После открытия окна
владельцем UI Automation read-only нашла точный selector существующего
проекта `nobus-orchestrator-dev`; IPC initialize/owner/history текущей
задачи успешны. Целевой статический просмотр новой версии сохранил номера
нужных методов. Новый turn, создание задачи и ответ на pending не
отправлялись: это preflight обновившейся версии, а не повтор исторического
live-сценария.

В `desktop_bridge.py` настройки нового follower-turn теперь берутся из
`latestThreadSettings` найденного владельца: collaboration mode,
approval policy, reviewer и sandbox. Реальная read-only история текущей
задачи дала `default/on-request/auto_review`; попытка сравнивать mode
с `latestCollaborationMode` отвергнута после воспроизводимого различия
только в developer instructions. Локальный Plan/default тест добавлен.
Это не доказательство полного паритета tools/skills/MCP или всех pending.

Расширение существующего sender
[telegram-delivery-runtime-v2.patch](telegram-delivery-runtime-v2.patch)
применено к установленному `nobus-send-results` runtime, сохранив v1 API.
Исходный hash сверялся с manifest; hash установленного файла
`72b7cff9c49a925d6bb6030b8c976b434e43e96f1d9dd98f7d5b05463c9d5207`
совпал с проверенной копией. Self-test прошёл, живой send не выполнялся.

Глобальный notifier обновлён штатным установщиком. Первый промежуточный
выпуск `26c05661251e2f598425228d0bbd0e487a243e0d615d52327cf9400f45129fa8`
устанавливался после точного подтверждения и сохраняется как история.
Окончательный для этого checkpoint
[notifier-auth-v3.patch](notifier-auth-v3.patch) даёт самодостаточную
read-only SQLite-проверку exact request/thread/turn без загрузки кода из
`bot_repo`. Подтверждённый SHA выпуска:
`3befa848059448783b2f5f2b270078a4240226485390d9b76c9eb93e7bfef08a`.
Исходные два файла и установленный runtime совпали по hash; патч проверен
на чистых исходных копиях и даёт те же bytes. В notifier JSON добавлен
только согласованный `bridge_state_path` к production SQLite;
`bot_repo`, credentials и Telegram destination остались прежними.
Установленный verifier загрузил настройки, увидел БД и отверг
несуществующую связку. Полного положительного live-подавления ещё нет.

Два отказа установки имеют точную причину и не скрываются: сначала в
запросе подтверждения был опечатан один символ SHA, и установщик не
применил выпуск; затем вызов другим Python не совпал с `Execute`
существующей задачи планировщика. После сверки через её проектный
`.venv` установка с правильным подтверждённым SHA завершилась
`task_created=false`, без изменения settings/credentials и без
Telegram-вызова. До завершения полной проверки не менялись
`NobusSpaceBot`, Health, Backup: все три оставались Disabled.

На текущих bytes целевой набор bridge/notifier/delivery/runner:
`65 passed, 1 skipped`. Первые два запуска этого набора не дошли до
тестов из-за deny на временные папки; запуск с временной папкой в
назначенном worktree прошёл. Полный Gate suite и независимый L1/L2/L3
на замороженном кандидате не выполнены. Ни одного нового продуктового
Telegram-запроса или Desktop turn в этом checkpoint не было; исторический
`unknown_dispatch` request 2150 не повторять.

Следующий шаг: проверить цельный локальный набор и изолированное
восстановление/backup; затем выполнить контролируемый Desktop/Telegram
live-сценарий на новой версии с точными квитанциями и остановкой при
неизвестном исходе. A09/A13 имеют установленный код, но отсутствие дублей
и полный цикл ещё не доказаны. D01–D17 и Gate остаются открыты.

После checkpoint read-only диагностика точно локализовала прежний
`NobusSpaceBot-Backup` result `1`: production `--inspect-failure`
подтвердил подписанный журнал `phase=complete` с `config_digest`
`sha256:2051b0e91632e48312ff5b5f9e2506faa4a75d69ebfd50fccddf73b9e222b143`,
тогда как существующая Scheduled Task вызывает конфигурацию с digest
`sha256:7c3876a3f7e011c2e62ab77c67516bd033db889a2c8f235d1b81cf8de0337d79`.
Production-скрипт отвергает это несовпадение до эффекта; цикл не
перезапускался. Локальный A01 reconcile для завершённого журнала — ровно
путь исправления, но ещё не развернут и не проверен на рабочем runtime.

После отдельного подтверждения на один тестовый итог проведён notifier smoke
в уже существующей задаче `M2-DESKTOP live probe`: turn
`01a0d2d7-7499-7e73-83fe-591580c11061` завершился, в её локальном
rollout найден ровно один `task_complete` с контрольной фразой, exact
thread/turn key в one-shot ledger имеет `sent`. Это обычный unmarked turn,
не Telegram product request и не доказательство позитивного A13 opt-out.
Новых задач, файлов и продуктовых сообщений боту не создавали.

В WIP остаётся `src/integrations/desktop_notifier_auth.py` только как
локальный тестовый дубль; установленный notifier его не импортирует.
Попытка удалить дубль и его отдельный тест через разрешённую файловую
операцию получила отказ, файлы не изменены. Не выдавать его за часть
runtime; перед заморозкой кандидата решить этот технический долг в
разрешённой зоне работы.

## Продолжение 24.09 — первая доставка и выпускная цепочка

В том же worktree выявлена и адресно закрыта локальная гонка A13/D15:
UIA bootstrap создавал отдельный первый Desktop turn, но его ID не входил в
durable request. Быстрый `task_complete` мог пройти в общий notifier до
привязки и дать summary параллельно полному bridge-ответу. Новый столбец
`bootstrap_turn_id` мигрируется аддитивно; bridge записывает его после
точной owner/history-корреляции. Установленный notifier v4 ждёт ограниченное
время точную read-only request/thread/turn-связь и не доверяет одному marker.
Канонический исходник и патч на установленную v3-копию совпали по SHA
`41a96251bd33ea3f2aa1a3f53fcc266c8b061383686f7e092fb60045297c9361`.
Пакет notifier дал `91 passed, 54 subtests`; владелец подтвердил релиз
`e6e08ba29097b3a35e58f43cf2a7619778b95bf72561d23499c31e91a6479eda`.
Штатный installer сообщил `installed`, `task_created=false`, `settings_changed=false`,
`credentials_changed=false`, `telegram_called=false`; hashes всех четырёх
файлов совпали с dry-run. Живого bridge turn после v4 ещё не было.

Выпускной анализ показал, что прежний Scheduled Task не передавал
`--desktop-bridge` через supervisor: backup мог успешно поднять только MVP1.
Теперь opt-in, локальный каталог проектов и явные корни артефактов проходят
installer → supervisor → Core; каталог привязан к activation/backup inputs,
корни — к activation binding. Без точной пары запуск отклоняется. В
`runtime_maintenance` сохранены два точных DDL-хэша: новая БД и известная
аддитивная миграция. A01 backup rebind теперь под admission hold мигрирует
только прежнюю известную DDL, проверяет целый runtime и лишь затем создаёт
новое поколение. Это устраняет цикл «старую схему новый backup отвергает,
а Core без нового backup не запускается». Неизвестная схема не меняется.

Адресные проверки: 3 теста привязки/старой БД прошли; после цепочки запуска
`290 passed, 1 skipped` в 12 связанных файлах; затем новые 5 тестов
supervisor/schema и 1 A01 reconcile прошли; четыре адресных совместимости
старого supervisor/installer прошли. Последний связанный срез до правки
A01 helper — `295 passed, 1 skipped`. После правки helper проверены только
его 6 тестов и A01: `7 passed`; общий срез на последних bytes ещё не повторён.
PowerShell Parser изменённого installer сообщил ноль ошибок. Это локальные
tests, не D01–D17 и не независимый L1/L2/L3.

Production checkout `telegram-live` остаётся на `3ea2438`; все три bot
Scheduled Tasks остаются Disabled. Новый branch-код, installer, backup
helper и каталог проектов туда не развернуты. Не повторять старый request
2150. Перед activation нужны единый кандидат и независимые L1/L2/L3,
точные отключённые task signatures/rollback, новая связанная backup config,
recovery rebind и новый VERIFIED backup. Только затем новые контролируемые
Telegram/Desktop сообщения с проверкой полного цикла, особенно позитивного
notifier opt-out, разрешений и D01–D17. `CURRENT_MANIFEST.json` в канонической
папке notifier исторический (22.09); фактический installed release сверять
с installer dry-run и hashes, не считать этот файл текущим receipt.

После этого два неиспользуемых локальных дубля verifier
`src/integrations/desktop_notifier_auth.py` и
`tests/test_desktop_notifier_auth.py` удалены по точным проверенным путям;
рабочий notifier и его настройки не затронуты. Связанный набор на
последних кодовых bytes дал `301 passed, 1 skipped` (13 M2-файлов и четыре
адресных backward-compatibility случая); одно предупреждение Starlette о
`httpx2` не относится к этим изменениям. Это не D01–D17 и не независимый
L1/L2/L3.

Read-only список Codex Desktop показал десять сохранённых локальных проектов.
Для opt-in подготовлен игнорируемый `desktop-projects.local.json` в текущем
worktree; `_load_desktop_projects` принял все 10 записей, SHA-256 файла
`43e64029ec9a0e009555dcfab1faa0825ee4c003b90994a42f547be05d2eea2a`.
Содержимое проектов не читалось. Это ещё не production-конфигурация и не
доказательство, что UIA создаёт задачи в каждом из десяти проектов.
Точные исходные Task definition digests, подписанный journal receipt и
безопасный порядок stage/backup/stop собраны в
[плане выпуска](RELEASE-PLAN-20260924.md); план не исполнялся.
Дополнительная read-only сверка DDL настоящей остановленной
`telegram-state.sqlite3`: 15 фактических schema keys и 15 ожидаемых;
единственное расхождение — `table:desktop_bridge_requests` с точно
предусмотренным старым hash `c9b10b0ff3ed2e0474e68b6e951177e39f70e2e46c6281f913c4056b8bac4fe6`.
Строки БД не читались, миграция на production не запускалась. Это
подтверждает вход helper, но не исход реального backup cycle.

## 24.09: L3-проверка маршрутизации и неизвестного исхода карточки

Локальный checkpoint `9cefc58de4ba1bd5cd43f611a072ede9cca9b8e4`
(tree `86f736dbb268dd264a78273f138de48550c1fe21`) создан в том же
worktree; это не замороженная приёмка. Его чистый Git-экспорт прошёл
`compileall` и отдельный запуск 13 M2-файлов: `296 passed, 1 skipped`.
Production checkout и три Disabled Scheduled Tasks не менялись.

При ручной adversarial-проверке найдено два новых дефекта. Первый:
`item/tool/requestUserInput` классифицировался как уточнение по имени метода,
даже если текст просил разрешить побочное действие. Адресный red-тест
на «Разрешаете удалить файл?» показал упоминание автора вместо владельца.
Теперь явные просьбы о согласии/доступе/побочном действии и неизвестные
поля верхнего уровня/params направляются numeric владельцу как требующие
ручного ответа в Desktop;
обычное «Уточнить?» остаётся автору. Это ограниченная локальная защита:
без достоверного поля происхождения все смысловые перефразировки доказать
невозможно; D08 требует реального полного цикла и проверки App/MCP.

Второй: после потерянного Telegram ACK карточка могла быть отправлена
повторно при восстановлении процесса. Адресный red-тест воспроизвёл
неподтверждённую отправку. Перед первым Telegram I/O теперь атомарно
резервируется exact interaction; только после ACK всей карточки она становится
доступной для reply. Потеря ACK, частичная отправка или crash оставляют
`unknown` и останавливают автоматический повтор; фактический исход нужно
сверять отдельно. Схема SQLite не менялась. Регрессии bridge — `39 passed`,
связанный набор 13 файлов после обеих правок — `206 passed, 1 skipped`.
Это новые WIP bytes; прежний чистый экспорт не подтверждает их.

Checkpoint после этих правок — `007c6540408fb446634e10d26eb01bffed1ca050`,
tree `b1331e4a22d754128e76191a47211d106011f9ee`, worktree clean.
Отдельный Git ZIP-export этого exact commit имеет SHA-256
`611cd804108a3ac0dc951f78bf0f4b2fdcffd932a5a7ac62df2e510745ec5d49`;
`compileall` и тот же связанный набор в нём прошли (`206 passed,
1 skipped`). На Windows `git archive --format=zip` применил CRLF к ряду
текстовых файлов, тогда как source worktree и Git index хранят LF. Поэтому
`content_digest` в EVIDENCE относится к точным байтам source worktree;
отдельный `clean_export_content_digest` — к распакованному ZIP. Равенство
этих двух digest не ожидается; точный Git tree связывает кодовый снимок.
Production пока остаётся на прежней ревизии и выключен.

Перед возможным выпуском повторно сверены exact XML SHA трёх Disabled
Scheduled Tasks и health launcher — значения не изменились относительно
[плана](RELEASE-PLAN-20260924.md). `Install-NobusSpaceBot.ps1 -WhatIf`
из M2 worktree на точных старых main/Health signatures и текущем каталоге
проектов завершился exit 0, вывел только ShouldProcess; задания не заменены.
Подготовлен игнорируемый одноразовый генератор нового backup config в
`.runtime/m2-desktop-release-20260924/prepare_backup_config.py` (SHA-256
`2b690c2a967b1570ed0324809b3530a04ef9a5c940231432900704f736e7e61e`),
его `py_compile` прошёл. На production он не запускался; новый config не
создан. Штатный signed journal и runtime SQLite не менялись.

## 24.09: одна разрешённая попытка A06 через Desktop UIA

Владелец разрешил ровно одну безопасную текстовую задачу в существующем
проекте `nobus-orchestrator-dev`: без инструментов, сети и изменений файлов
в самой задаче, затем только read-only IPC-проверку. Одноразовый сценарий
`.runtime/m2-desktop-live-probe/A06-ONE-SHOT-20260924.py` имеет метку
`M2A06-20260924-ONE-SHOT-8E5317A0`, SHA-256
`7a3dbb2a609aee992fc41ca9206d773d897418ab5d14fe9146f5c36032cbc44b`.
IPC слушал до вызова UIA. `CreateAndSubmit` вызван **один раз**; успешного
receipt нет: PowerShell завершился неуспешно, а поток stderr дал
`UnicodeDecodeError` при декодировании UTF-8. Адаптер вернул
`desktop-uia-action-failed`. В течение 30 секунд новых
`thread-stream-following-status-requested` не наблюдалось, кандидатов
для owner/history не найдено. Следующий read-only Snapshot Desktop
`26.917.9434.0`, PID 8312 сохранил прежний контекст существующей задачи:
проект раскрыт в sidebar, `new_task_project_context_verified=false`.
Read-only список последних задач приложения не показал новой тестовой задачи.
Эти данные указывают на сбой до подтверждённой отправки, но не доказывают
отсутствие turn: результат классифицирован как **unknown outcome**. Метку
не отправлять повторно, пока фактический исход не будет надёжно установлен.
Telegram продуктовым маршрутом не вызывался; возможное автоматическое
уведомление глобального notifier не выдавать за доказательство bridge.

Отдельный локальный диагностический дефект установлен: Windows PowerShell
5.1 может печатать локализованный stderr не в UTF-8; строгий декодер Python
падал во вспомогательном потоке и скрывал статус. Для будущих попыток
`subprocess.run(..., errors="replace")` сохраняет fail-closed поведение и
не раскрывает сырой Desktop payload. Адресный UIA-набор после правки:
`6 passed`; первый запуск упёрся в запрещённый sandbox temp-каталог,
повтор с точным новым `--basetemp` внутри `.runtime` прошёл. Это не
устраняет пока исходный отказ действия и не закрывает A06 или D01–D17.
Новой живой отправки без отдельного точного разрешения не делать.

## 24.09: расширенное разрешение на тесты, точные причины UIA-отказов

Владелец разрешил необходимое число тестов и управление установленным Desktop
для завершения Gate. Старую метку с unknown outcome не повторяли. Каждая
следующая попытка получила новую метку и одноразовый sentinel в игнорируемой
`.runtime/m2-desktop-live-probe/`. Тест с меткой `…SECOND-5FD883B1`
остановился на `find-create-control`, до ввода и send. Причина установлена
на уровне исходных байтов: UIA-скрипт после локальных правок не имел UTF-8
BOM, а Windows PowerShell 5.1 при `-File` трактовал его как ANSI и искажал
русские названия элементов. Скрипт переведён на UTF-8 с BOM; тест фиксирует
первые байты `EF BB BF`. Native PowerShell 5.1 parser вернул 0 ошибок,
read-only UIA увидела точную кнопку «Начать новый чат в папке
nobus-orchestrator-dev» с `InvokePattern`.

Следующий тест `…BOM-3B7B2E91` прошёл создание пустого вида проекта, но
остановился до ввода на `find-composer`. Независимые метки
`…REFRESH-7A88C26D`, `…COUNT-2F9B809C` и `…SPLIT-BAE84D03` также не
достигли отправки; для каждого IPC дал 0 новых thread-кандидатов.
Read-only UIA в пустом виде подтвердила проект и единственное видимое поле
«Поручите что угодно» с `ValuePattern`; прямые `Find-Exact` и `Wait-Exact`
успешны. Проверка **только булева признака** установила, что поле содержит
непустой черновик, не совпадающий ни с одной тестовой меткой. Содержимое
черновика не выводилось, не сохранялось, не изменялось и не отправлялось.
Именно существующий draft вызывает fail-closed остановку после нахождения
поля; прежняя метка `find-composer` была слишком широкой. Стадия разделена
на `find-composer` и `check-draft-empty`. Гипотеза о старом UIA-документе
не подтверждена и её код удалён; экспериментальный двухшаговый submit
тоже удалён из рабочего адаптера. Владелец получил просьбу сохранить или
очистить draft вручную; до ответа новая живая отправка не выполняется.

Последние локальные проверки текущего WIP: `58 passed` в
`test_desktop_bridge.py` и `test_codex_desktop_uia.py`, parser PowerShell
5.1 — 0 ошибок. Это не полный L1/L2/L3 и не приёмка D01–D17. Исход
самой первой метки `…ONE-SHOT-8E5317A0` остаётся unknown, хотя позднейшие
причины хорошо объясняют отсутствие подтверждённого turn; историческую
классификацию не переписывать без прямого readback.

После ответа владельца «Черновик сохранён/очищен» read-only preflight снова
подтвердил пустой вид нужного проекта, однако `ValuePattern` и независимый
`TextPattern` одного видимого editor оба показывают 20 непробельных символов
с одинаковым значением. Оно не совпадает с доступным именем редактора и
не содержит меток наших проб. Содержимое не выводилось. Владелец получил
второе узкое уточнение: проверить именно нижнее поле текущего окна или
сообщить, что оно визуально пустое. До разрешения расхождения send не
выполнялся. Для продукта добавлено строгое allowlisted `existing-draft`
только при точном guard exception; bridge сохраняет unknown/no-auto-retry и
сообщает автору о сохранённом черновике. Если ошибка на этой стадии иная,
специальный вывод не применяется. Последние адресные проверки — `60 passed`
в bridge/UIA, native PS5 parser 0. Это всё ещё WIP, не Desktop-turn evidence.

## 25.09: восстановление выгруженной Desktop-задачи и широкий regression

На локальном checkpoint `fd275fd` широкий запуск без исторического Gate 0
выявил три подлинных сбоя legacy migration: сравнение одного DDL-хэша с
кортежем двух точно разрешённых. Исправление `935d930` приняло оба известных
значения и по-прежнему отвергает неизвестную схему. Три Windows-теста,
упавшие только из-за sandbox identity, прошли от фактического владельца
файлов. Семь старых нормативных fixtures отдельно воспроизведены и
исключены точечно; они ожидают прежние тексты, sealed hashes и форму
установщика, а не поведение M2. Старые Gate не объявлялись принятыми.

Новый read-only Desktop preflight обнаружил существенный recovery-gap:
сохранённая задача `01a0d43f-edb8-70e2-85ae-5434cc992228` после выгрузки
возвращала `no-client-found` через owner IPC; штатное открытие задачи в
Desktop восстанавливало точного владельца. Отдельный CLI/App Server не
использовался. UIA получил действие `OpenExisting`: оно выбирает один
семантический sidebar-элемент по точному названию и подтверждает активный
заголовок, не читает prompt, не пишет composer и не вызывает send. Название
сохраняется в шифрованном bridge payload только после IPC readback точного
thread ID; после UIA bridge несколько раз проверяет owner **того же ID** и
только потом допускает обычную проверку `cwd` перед turn. Неизвестное или
устаревшее название, неоднозначный элемент или пропавший владелец оставляют
запрос ожидающим ручного открытия, без другого исполнителя и без повтора
хода.

В установленном Desktop `26.917.9434.0` первый open-only опыт для
`01a0d432-e0c9-7280-bcd5-4350a8c7843f` дал UIA receipt, но немедленный
IPC readback всё ещё вернул `no-client-found`; поздний UIA snapshot не
показывал активного заголовка. Этот исход **не** принят как успешное
восстановление. После штатного открытия той же задачи в приложении IPC
нашёл exact owner с первой read-only попытки. Второй open-only опыт для
ранее выгруженной `01a0d43f-edb8-70e2-85ae-5434cc992228` дал
`invoked-open-task` и exact owner с первого readback. Ни один опыт не
отправлял turn, approval или Telegram. Отрицательные локальные тесты
подтвердили, что при неизвестном title UIA не вызывается, а при
отсутствующем owner после открытия другой исполнитель не подставляется.

Кодовый checkpoint `b8834aeedc7a7501bdc2049f8458ef025ab8c5ff`
(tree `8622aeb6c6d57ca80a6cbca693a65af6c43a0103`) прошёл PowerShell
5.1 parser (0 ошибок), 69 адресных UIA/bridge тестов и широкий L1:
`2904 passed, 3 skipped, 7 deselected, 25 subtests passed` за 527.03 с.
Из чистого Git ZIP-export этого checkpoint (архив SHA-256
`d8f351a6da17c20b9702aa95c0f21fb100ceb454185e1db11bdcd773043dd119`)
отдельный L2 набор из 15 связанных файлов дал `247 passed, 1 skipped`.
Это локальная регрессия исходников, не полный D01–D17 и не завершающий
независимый Gate verdict. `ruff` в текущей venv не установлен; установка
не производилась. `pip check` ранее показал отсутствие нарушенных
зависимостей; сетевой `pip-audit` auto-review отклонил, обхода не было.

Read-only выпускная сверка 25.09: `telegram-live` по-прежнему clean на
`3ea2438`; все три Scheduled Tasks Disabled и сохранили точные XML SHA из
release plan. Установленный backup journal через старый bound inspector
даёт `phase=complete` и прежний confirmation digest. Новый код в production
не переносился, backup/rebind и Telegram live не запускались. D01–D17,
полный capability parity, реальный Артур/голос/две темы и позитивное
отсутствие дубля notifier остаются незакрытыми. Старое разрешение на
commit `16f9029` не распространяется на `b8834ae` или будущий docs commit;
для точной активации требуется отдельная release-привязка и разрешение.
