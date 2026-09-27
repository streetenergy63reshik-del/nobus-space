# M2-DESKTOP — журнал для независимого аудита

### 27.09, 09:21 — временные файлы классифицированы; recovery WIP проверен локально

Владелец разрешил только этапы 1–2: узкое исключение для временных файлов
новых изолированных test roots и локальное устранение backup/readiness
дефектов. Новый watcher: 4 passed, 58 Deleted (44 WAL/SHM, 6 journal,
4 pytest housekeeping, 4 source-name events при move), 3 Renamed;
сырые пути событий не сохранены. Предыдущие 59 неклассифицированных
событий остаются историческим отрицательным результатом. Никаких
production-файлов и чужого WIP не удаляли.

Двухшаговая Windows promotion заменена одним `ReplaceFileW` с архивом
прежнего control-файла. Проверены успех, длинный путь, отказ после
перемещения старого файла с rollback и неизвестный исход с остановкой
без повторной записи journal. Защитный предикат сначала сломал retry
первого backup (`1 failed, 24 passed`); после уточнения 36 зависимых
backup-тестов прошли, плюс один новый тест потери первого опубликованного
pointer. 6 узких readiness-тестов прошли. Это WIP, а не L1/L2/L3 и не
живое доказательство точной причины исторического timeout. Production
остаётся остановленным на `fd4d66c`; выпуск и D02–D17 отложены
владельцем на следующий запуск.

### 27.09, 08:22 — новый production incident и точечный WIP

Ночной включённый Backup Task автоматически стартовал в 03:30 на старом
чистом `fd4d66c`: новая generation `daily-20260927T033029-777f247f8b534c47a07e804bf35d74e9`
имеет journal `backup_status=VERIFIED`, но terminal phase
`failed_operator_required`, `failed_phase=starting`,
`failure_class=restart_not_ready`, `runtime_status=NOT_READY`,
`admission_hold=true`. Main/Health `Disabled`, Main result `78`,
Backup result `1`. Код этого production backup выполняет
`cleanup_staging()`; точные пути ночных удалений не записаны.
Чтобы не повторять такой цикл при no-delete, только idle Backup Task
выключен штатным helper, readback `Disabled/enabled=false`.
Supervisor journal не менялся после 26.09 21:37:48 МСК;
SHA-256 файла `b626744b7a2cea3f626a78c07abe93f8c3835a330e7d9b3b70dce5cf398fd2bc`.
Повторная **read-only** проверка `latest_manifest` и `verify_backup`
подтвердила четыре ciphertext-файла новой generation, manifest digest
`sha256:e47d610b8b758effa31805550cb7ad2593468b77c3ab65c997b3257636be3056`.
Штатный read-only `--inspect-recovery` вернул `STOP/blocked`,
`stop_non_retryable`, прежний подписанный head
`sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Reset не выполнялся.

В незакоммиченном WIP общий helper переносит прежний control-файл в
уникальный archive до promotion нового; `latest.dpapi` и signed backup
journal больше не используют `os.replace`. Три прямых тестовых вызова
без pytest/SQLite прошли в новых сохранённых каталогах; тест файловой
идентичности подтвердил сохранение прежнего inode, коллизия архива
сохранила все три исходных файла. Ещё два чистых вызова подтвердили
fail-closed при отсутствующем `latest.dpapi` с прежней generation и
при отсутствующем backup journal с историей. Все пять каталогов
сохранены. Это адресная правка overwrite, не доказательство полного
no-delete: SQLite sidecars и восстановление после crash-gap остаются.
Выпуск, reset, новые live tests не проводились.

### 26.09, 22:47 — отрицательная файловая проверка

FileSystemWatcher на уникальном синтетическом корне
`m2-file-watch-97e3b2e4d957` наблюдал четыре no-delete backup теста:
`4 passed`, `DeleteEvents=59`, общий exit 1. Полные пути событий не
сохранены; сохранившийся инвентарь — 9 `.sqlite3`, 26 прочих файлов,
ноль `-wal`/`-shm`. Источник каждого события не доказан; вероятная
часть — SQLite sidecars. Это воспроизводимое отрицательное свидетельство
самого заявленного no-delete свойства, поэтому повторять тест без
новой гипотезы нельзя. Production и чужие файлы не затрагивались;
релиз, recovery и Telegram smoke не выполнялись. Локальный checkpoint
`91a0499` оставить WIP, не использовать как выпуск.

### 26.09, после 22:40 — no-delete backup checkpoint, без внешнего эффекта

Checkpoint `91a0499c06567c9d5a9829190e2629aa26663661` / tree
`30767a04c449455269c67979942ccc39d0c1a89e`. Две локальные
итерации исправили отдельно обнаруженную несовместимость Python
backup staging/hold/retention с запретом удаления; SQLite snapshot
теперь строится в памяти и шифруется до файловой записи. После новой
проверки reviewer разрешил синтетический cycle. Чистый экспорт: 15
адресных тестов PASS; signed reconcile, fail-closed backup и disk-full
на WIP Git-контексте: 3 PASS. Синтетика не доказывает отсутствие
внутреннего удаления WAL/SHM на настоящем runtime. Read-only снимок
production показал sidecar у task-runtime/checkpoint; Health result 1
в 22:40. Ни checkout, ни Tasks, ни backup/rebind/reset, ни Telegram
после этого checkpoint не изменялись. D03 completed turn без delivery.

### 26.09, 22:27 — checkpoint readiness, выпуск остановлен до эффекта

`133929f5ea153fc8d05a093200f9733045ac2293` (tree
`e2fd0887de00b85ce672eeb976dfddc7a63019f7`): 11 адресных тестов
из нового чистого экспорта прошли. Read-only backup probe старого
production кода: 204/171/157 мс; не воспроизведён сам аварийный spike.
Ревью реального выпускного пути обнаружило `cleanup_staging()` с `unlink`
plaintext SQLite и `permit_admission()` с `unlink_durable()` hold-файла.
Это несовместимо с текущим абсолютным no-delete; backup/rebind, checkout
switch, recovery reset и Telegram-ход **не выполнялись**. Живой D03 остаётся
в завершённом Desktop turn и нуле delivery rows. Требуется отдельная
реализация и проверка no-delete backup без plaintext-следов, затем
точный signed preflight и однократное восстановление.

### 26.09, 21:36–21:51 — тот же Desktop thread, новый safety stop

Одна подтверждённая команда `continue` из исходной темы дала request
`5b965633-8670-4db5-a67f-2a530ca48f78`, source message `2312`,
и turn `01a0df02-48f2-7453-955e-350fbee2e0ea` в прежнем thread
`01a0de96-455b-73f3-a211-dda674803351`. Desktop `read_thread` и
новое **read-only** IPC-соединение показали completed и точный финал
`M2-CONTINUE-20260926-1`. Одновременное ожидание доставки было ошибочно
похоже на IPC-зависание, но signed журнал доказал ранний safety stop:
readiness deadline трижды в 18:37:09–18:37:43 UTC, `control_closed`
head `sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Bridge оставил request `running`, delivery rows `0`; никакого повтора.

Пятиминутный py-spy профиль предыдущего здорового периода показал
синхронные backup/source/Git операции в `/readyz` на Core event loop,
но не захватил конкретную блокировку 18:37. Утренний Health DB spike
39,1 с — только корреляция. WIP-диагностика event-loop stall и
append-only ротация прошли два адресных теста; production всё ещё
`fd4d66c` и stopped. Старые readiness/health архивы переименованы в
уникальные `.preserved.*` с проверкой SHA; файлы не удалялись.

### 26.09, 20:17–20:20 — один recovery и D01 доставка

После exact owner approval signed head `sha256:2665c870…` повторно
сверен, Main `Ready`, listener отсутствовал, production clean `fd4d66c`.
Один штатный `--acknowledge-recovery-stop` вернул event
`sha256:7d4bf41df20797f28f210e854d33f8102e629c6b97aa4cdeb81f5ff905e78c0a`;
один Start существующего Main. Тот же request/turn из строки ниже
перешёл в `delivered`; ledger содержит одну `text/0/sent` с Telegram
message ID `2306`. В исходной теме визуально ровно один exact final
`M2-LIVE-20260926-3` как reply к исходному поручению. Main `Running`,
Health last result `0`, local/public readiness `PASS`. Исторический
stop сохранён, его причина не объявлена устранённой; это D01 text path,
а не весь D01–D17 или Gate.

### 26.09, 19:39–19:48 — реальный Desktop turn, delivery не завершена

Одна команда в «Заметки бизнеса» / «Codex work» с меткой
`M2-LIVE-20260926-3` дала request
`ae0183d9-669a-4cde-b81e-74d749cc6643`. Установленный Desktop создал
thread `01a0de96-455b-73f3-a211-dda674803351` и выполнил turn
`01a0de97-8678-74f3-9736-0296f7009580` с точным финалом. IPC snapshot
revision 18 подтвердил `completed`, один `final_answer`, ноль ожидающих
запросов. Telegram получил только подтверждение приёма. Bridge сохранил
точную привязку, статус `running`, delivery rows `0`.

Readiness-доказательства: три local/public deadline в 19:40:32–19:41:06;
подписанный terminal `local_public_readiness_failed`,
`stop_non_retryable`, cleanup proven, а не падение Desktop или
самопроизвольный выход дочернего процесса. Signed head после закрытия
контроля — `sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`.
Main теперь `Ready`/LastTaskResult `1`. Причину задержки Core не
приписывать IPC без нового доказательства. Узкий локальный тест
восстановления `RUNNING`→доставка завершённого turn без `start_turn`:
`1 passed`. Живой reset/start ожидает отдельного точного разрешения;
не выполнять повтор сообщения, turn или recovery без readback.

### 26.09, 19:00–19:18 — выпуск fd4d66c, живой Gate не принят

На точный `fd4d66cfccb66c29702c29f6df59d137d3c26e3b` сделан
один контролируемый production switch: rollback сохранён, Main/Health/
Backup остановлены и выключены, новый O_EXCL config
`sha256:cb9af8931da6d9f0e896c208f6697845e6e7a23ecb12fa6501f9edb345c9d407`,
только Backup Task заменён в Disabled staging. Signed rebind от
`sha256:64dbfd5e5203f257e8f28e79d1cf519740e9b95575b08816627c95dac56140cc`
дал inspect `PASS/new`; один reconcile от прежнего `complete` journal
дал `PASS`, новую VERIFIED generation и signed `complete` journal
`sha256:3ceca795c3273a3802fa92fbc3b08c5d2fbdaa03a06dc78b3d0144e5f819b71a`.
Production clean на новом commit, Main `Running`, Health/Backup
`Ready`, local/public readiness `PASS` в 19:18. Первое `-WhatIf`
Backup Task остановилось на ожидаемом изменении Enabled XML; read-only
diff установил единственное поле, повтор с точным disabled SHA прошёл.
Никаких credentials/Codex/notifier/push изменений.

Сквозной Telegram-тест ещё не начат: пользователь остановил Computer Use
Escape до выбора окна и ввода. Исторические `unknown_dispatch` не
переисполнялись. Эти release-квитанции не закрывают D01–D17.

### 26.09, 18:23–18:37 — version pin и локальная UIA переквалификация

После отдельного подтверждения отправлена одна команда `/codex new` с
меткой `M2-LIVE-20260926-2`; бот создал request
`9202eece-cc7a-4e62-9d7c-e3b3f6d1e98d`, затем сообщил
неопределённый UIA исход. SQLite: `unknown_dispatch`, thread/turn NULL.
Повтора не было. Read-only процесс показал Desktop `26.924.2738.0`;
production UIA pin — `26.917.9434.0`. Старый Snapshot отказал до
действия. Snapshot с новой версией, отдельное чтение точного UIA
элемента проекта, IPC initialize и owner discovery прошли.

Локальная проба `…7A4D` вызвала новый чат, но не дошла до ввода:
`check-active-context` опередил загрузку UI. Read-only Snapshot и
accessibility подтвердили впоследствии нужный проект, пустой composer
и отсутствие метки в истории. В WIP добавлено ограниченное ожидание
контекста, без снятия проверки перед Send. Новая проба `…B19E` получила
receipt `invoked-create-task, submitted-prompt`; в Desktop видны задача
и точный финальный ответ. IPC readback exact thread
`01a0de5a-db5c-7433-8587-93bec1f39917`: один completed turn,
маркер, точный ответ, cwd проекта и owner. Текущий UIA/bridge набор
`74 passed`, PS parser 0. Это не live Telegram D01 и не full IPC parity;
кандидат пока WIP, production на `cdc59a2`.

### 26.09, вечер — production stop и первый Telegram запрос

В 10:34 Main зафиксировал signed `local_public_readiness_failed` после
трёх timeout. Только после read-only сверки exact head, процессов,
журнала и состояния заданий владелец отдельно разрешил один signed
recovery reset от `sha256:df335663097ae8c28dbaecb3c8819bf9dcfc58cc8b3c97c3169632e167017653`
и один запуск Main. Reset event
`sha256:84d20173bc1200d029659bd86bc36bcb86b36fef7e43cdae41db9e8df4ae7680`,
inspect `PASS/new`; в 18:05 Main запущен ровно раз, local/public `PASS`.
Backup cycle, config, credentials и Tasks не менялись. Первоначальная
причина задержек readiness не доказана.

Сообщение `M2-LIVE-20260926-1` отправлено один раз в 17:51 в нужную тему;
после восстановления бот ответил в 18:06 отказом продолжить несуществующую
задачу. Нового bridge request/turn нет. Регрессионный тест с точной формой
адресованного сообщения и `reply_to` корня темы до исправления дал
`topic != route`. Общий парсер теперь сохраняет `route` для явного
`/codex`, `@Nobusspacebot` и имени бота даже при `reply_to`; обычный
ответ на связанную задачу остаётся `topic`. Затронутая регрессия:
`292 passed`. Это локальный WIP, не новая проверенная release revision.

### 26.09 — однократное успешное восстановление production

Точный допуск владельца относился к `cdc59a2`, rollback, новому config,
одному signed rebind и одному backup/recovery cycle. Перед записью
production был clean на `26b95e5`, три Tasks Disabled, XML SHA-256
совпали с прежними квитанциями; failed journal имел точный digest
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
Сохранены точные XML/config/launcher/inventory rollback-копии и локальный
ref старого HEAD. Переключён только чистый checkout на `cdc59a2`, создан
O_EXCL config `sha256:bd885e5ef5953aae9ac6a38011c5a0f4b49d9f36816d361fb2664aacd929b685`,
заменён только Disabled Backup Task; его XML SHA-256 после readback
`429f4bdc62d2d6d021889d544760ebada276d2dd096e3b9fd6fc59e2ae790b71`.
Signed recovery rebind от точного head вернул event
`sha256:fdb116d5bc52fc322a77759c0a5d63387a13b70588e47f2221a2eaad8c79f9bf`;
inspect после — `PASS/new`.

Backup Task включён и прочитан как `Ready` с ближайшим расписанием
27.09 03:30 МСК, затем один `--rebind-failed-digest` завершился `PASS`,
создал VERIFIED generation
`daily-20260926T094651-e5271dad8ba84cb9aa8bb4924b94c3e1`.
Новый signed journal — `complete`, digest
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`.
Main `Running`, Health/Backup `Ready`, Main `--check-ready` вернул
`local_ready=true`, `public_ready=true`, Health LastTaskResult `0`.
Telegram-запрос на новом активном коде пока не отправлялся: runtime
доказан, D01–D17 и принятие Gate — нет. Этот checkpoint не меняет исходные
bytes замороженного code commit и не запускает L1/L2/L3 повторно.

### 25.09 — точная кандидатная проверка исправления интерпретаторов

Frozen local commit `cdc59a2ebd5d228e062937625da209be6d652c4a`, tree
`0ac7807464c3ffbdd25a18b415bcce1f4fa47711`; рабочая копия была чистой
перед проверкой. L1 (все текущие тесты, кроме прежнего `tests/gate0` и пяти
точных старых assertions): `2915 passed, 3 skipped, 5 deselected,
25 subtests passed` за 409,74 с. Новый source diff — только канонизация
двух base interpreter paths и добавление `base_pythonw` в SHA-bound manifest;
один целевой тест подтвердил одинаковый digest console/GUI.

L2: чистый `git archive` ZIP SHA-256
`16d77414ccb4620c1fa5511f39346b829a1d7601d4b77b3afcff9d4562cddf21`;
runner blob `47f3a6efcf1a38ac69760331f7d2dc94e0129d27` и test blob
`55c5f4d4ded9d6439e919cf867dbae653e6cda01` совпали с Git. Из
отдельной распаковки 13 связанных supervisor/backup/Desktop bridge файлов:
`491 passed` за 136,24 с. Оба набора дали одно старое
Starlette/httpx deprecation warning, не требующее установки зависимости.

L3: нормализация сохраняет одновременно SHA-256 evidence `python.exe` и
`pythonw.exe` как отдельные обязательные поля; отсутствующий файл
отклоняется `resolve(strict=True)`. Изменение любого evidence меняет
канонический digest, а выбор console/GUI больше не меняет его. Rebind
истории всё ещё связан с exact Git HEAD, Task signatures, config и
подписанным head; docs-only commit до выпуска тоже сменил бы binding.
Поэтому послепроверочные документы оставлены как WIP, production target
не меняется с `cdc59a2`. Проверка не утверждает живую совместимость
Desktop/Telegram или приёмку D01–D17. Точный production допуск запрошен.

### 25.09, вечер — новый подтверждённый defect интерпретаторной привязки

Точный разрешённый шаг: Backup Task Enabled/readback `Ready`, один
same-config recovery из signed journal `sha256:d32cbd…`, без Telegram.
Новый VERIFIED backup создан, Main вышел кодом 78, цикл оставил подписанный
`failed_operator_required` digest
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
Head истории не изменился, состояние `new`, latch нет; это не повреждённая
история. Все три Tasks после обратимого выключения Backup вновь Disabled,
порт/дочерние процессы отсутствуют. Неподтверждённых Telegram-эффектов нет.

Гипотеза и проверка: rebind выполняется `python.exe`, а Task —
`pythonw.exe`; у них разный `sys._base_executable`. Exit-only probe
реального venv `pythonw.exe` вернул 12 (= base `pythonw.exe`). Read-only
вычисление прежнего manifest на тех же Task аргументах: console digest
`sha256:060b26b17559eeed88a2d21a4d051bb227521a7ac5f86fb8c0db24c763b21078`
совпадает с signed head, а под GUI-base получается
`sha256:2ef8e1a14d1c924a56d6ad8cd34df10d8c74406857a7f7dd8ced0eb94b602cdc`.
Следовательно Main блокирует чужую для него привязку (exit 78) до
runtime event. Минимальная локальная поправка в `run_nobus_space_live.py`
всегда связывает base `python.exe` **и** `pythonw.exe`, независимо от
исполняемого режима. Регрессия меняет оба `sys`-пути и требует один digest.
Целевой тест прошёл; пять связанных модулей — `274 passed, 1 warning`.
Первый sandbox-прогон fixture получил WinError 5 на системном Temp,
запуск от файлового владельца прошёл; продуктовый отказ этим не маскируется.
Полная новая candidate-bound L1/L2/L3 и production разрешение открыты.

### 25.09 — второй signed recovery: отдельный release-sequencing defect

После точного разрешения установлен clean `26b95e5`; rollback snapshot
`26b95e5-preflight` сохранён. Новый O_EXCL backup config digest
`sha256:fcdb25b206e12885456b11001696397890411fd7dc93621d9411d5c23e3c4c74`,
Backup XML после stage SHA-256
`5e1757d06956b64b143730b629661036602eff26e8cd91196419a3cf6301df0b`.
Signed recovery rebind прошёл (`PASS/new`, head
`sha256:f82b14b781526f4a6a8eb75d4e1eb432e5e8ac7bd16da6131796c76a2d6474b4`).
Один `--rebind-failed-digest` создал VERIFIED generation, но restart
завершился Main exit 75; новый signed failed journal digest
`sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`.
Штатный `--inspect-failure` подтвердил same-config и exact digest.
Все три Tasks Disabled; admission hold/cleanup доказаны, бот не готов,
Telegram-эффектов нет.

Новая проверенная гипотеза: `run_telegram_backup_cycle.py` включает только
Main/Health, а staged Backup Task остаётся Disabled. В
`_scheduler_activation` signed restart разрешает Disabled Health, но не
Backup. Read-only валидатор на фактическом Backup snapshot вернул
`scheduler task profile is invalid`; тот же snapshot с локальным
`allow_disabled_staging=True` прошёл. Task action указывает на точный
новый config/digest; его следующий запуск до включения назначен на
26.09.2026 03:30 +03:00. Это не повтор старой причины с
`reconciled_from_digest`. Ни Task Enable, ни второй цикл не выполнялись;
запрошено отдельное разрешение на эти два действия и stop-on-drift.

### 25.09 — candidate-bound L1/L2 и read-only production preflight

Adversarial L3 по `fe333c6` выполнен по изменённым границам, без внешнего
действия. Проверены: запрет исполнять неоднозначный create/continue до
подтверждения автора и истечение инертного запроса; allowlist проекта и
проверка exact IPC owner/thread/cwd после UIA selector; отказ от повторной
отправки при неизвестном ACK; signed digest/VERIFIED generation/hold/cleanup/
disabled tasks при backup rebind, архивная readback-проверка до нового
snapshot; отказ от лишних полей restart journal. Адресные негативные тесты
включены в L1/L2. Изменённые исполняемые файлы не содержат совпадений с
ограниченным набором шаблонов секретов; зависимости не менялись.
Вывод L3 ограничен локальным кодом: реальная гонка Scheduled Tasks,
Telegram-доставка, skills/MCP/host-tools и весь D01–D17 ещё не проверены.
R01 подтверждает безопасный диалог, но не универсальный смысловой парсер;
R02 имеет согласованную ручную Desktop-границу для неоднозначного текста.
Это не независимый внешний аудитор и не финальный Gate verdict.

Точный локальный code checkpoint `fe333c614e30340057acd917b592c2e36b62c574`,
tree `c016023e2b4b32a2403e2c50d312ddc905891730`. Чистый Git ZIP
SHA-256 `063e6f0c7bc665fe83a0cc65b380aeb32d5fe6b956c21da87db81d95a31dcfb8`:
`225 passed, 1 warning` за 126,17 с. Первый широкий прогон без
`tests/gate0`: `2914 passed, 3 skipped, 6 failed` за 438,17 с.
Пять точных старых assertions:
`test_gate_c0_governance.py::{test_active_status_and_roadmap_are_consistent,
test_publication_projection_excludes_held_editorial_docs,
test_candidate_changes_no_production_code}` и
`test_pre_gate1_architecture_integration.py::{test_active_projections_and_authority_point_to_adr0022,
test_gate0_catalog_required_sources_remain_byte_identical}`.
Шестой `test_voice_retention.py::test_running_deadline_cancels_pending_await_and_has_no_late_result`
прошёл отдельно и в составе всего файла (`43 passed`); неизменённый код
прошёл повторный широкий прогон с исключением только пяти старых test IDs:
`2915 passed, 3 skipped, 5 deselected, 25 subtests passed` за 441,18 с.
Причина разового голосового отказа не доказана; он не повторился, но
наблюдение сохранено.

После тестов read-only checkout production clean на `fa6f1f0`, Main/Health/Backup
Disabled. Штатный `--inspect-failure` вернул `failed_operator_required` и
confirmation digest `sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`.
Ни recovery, ни Telegram не запускались. Точный следующий production шаг
нуждается в отдельном разрешении на `fe333c6` и подписанный rebind.

### 25.09 — восстановление после подписанного failed backup и R01/R02

После согласованного staging `fa6f1f0` единственный backup reconciliation
создал VERIFIED generation, но Main завершился кодом 75: reader не принимал
подписанное `reconciled_from_digest`. Failed journal
`sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`
остался в `failed_operator_required/starting`, все три Tasks Disabled,
дополнительных production-попыток не было. WIP добавил узкую проверку поля
и отдельный `--rebind-failed-digest`, не развёрнутый в production.

Для R01 неизвестная адресованная просьба теперь требует сохранённого выбора
автора «создать/продолжить» до Desktop-эффекта; это безопасный маршрут, не
полное смысловое понимание Core. Для выгруженной ранее не связанной задачи
один живой open-only UIA→IPC опыт подтвердил точные ID/title/cwd без turn.
Владелец согласовал ограничение R02: неоднозначный текстовый
`requestUserInput` — ручной ответ в Desktop, структурированные approvals —
только numeric Telegram user_id владельца. Живой Telegram-цикл не проводился.

Затронутая регрессия на неподвижной рабочей копии: `225 passed, 1 warning`
за 120,51 с (bridge/IPC/UIA/C6 backup/M1/ops/docs), включая все 13
`ops_queue1`-проверок действующих WhatIf и Health. Более ранний частичный
прогон backup-тестов дал один отказ `application changed during backup`,
поскольку исходник редактировался одновременно с тестом, который специально
проверяет неизменность application binding; этот прогон не использован как
доказательство, а на неподвижных файлах соответствующий тест прошёл.
Нужны замороженный снимок, независимая проверка, новое точное разрешение на
изменённые production bytes и подписанное восстановление, затем D01–D17.

### 25.09 — широкий набор и точная классификация отказов

На `e5921b8` полный `tests` без `tests/gate0`: `2894 passed, 3 skipped,
13 failed` (411,52 с). Три C6 migration отказа — `IMPLEMENTATION_DEFECT`
в сравнении exact DDL alternatives; исправление `935d930` прошло весь
`tests/test_c6_migration.py`: `6 passed`. C5 crash и два M1 OS-теста —
`ENVIRONMENT_FAILURE` sandbox identity, адресно от пользователя-владельца
все три прошли. Семь Gate C0/pre-Gate1/ops_queue1 отказов —
`STALE_CONTEXT`/`VERIFIER_DEFECT`: проверки требуют прежние публикационные
формулировки, sealed hashes и интерфейс установщика, не соответствующие
текущему принятому контракту. Их не правили и не объявляли M2-регрессией.
Новый кандидат после исправления требует одного полного привязанного
L1/L2/L3 и живой D01–D17, не наследует старую успешную квитанцию.

**Gate:** M2-DESKTOP

**Исторический исходный снимок:** 22 сентября 2026 года, 12:29 МСК; текущий WIP описан в конце

**Исторический статус:** разработка и live-контур были безопасно остановлены владельцем; локальная разработка возобновлена

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

## Checkpoint 24.09 после аудита готовности R01–R05

Источник проверки — канонический `docs/audits/M2-DESKTOP-AUDIT.md`
от 24 сентября (этот файл отсутствует в отдельном worktree) и его offline
reproducer. В том же worktree, без нового
импорта Grok, исправлены пять воспроизводимых локальных границ:

| ID | Локальный результат | Что ещё не доказано |
|---|---|---|
| R01 / A08 | Естественный create текста и голоса не попадает в topic continuation; выбор проекта хранится с author/topic, voice требует preview-confirmation; wrong-bot command отклоняется. | Полное смысловое разрешение через Nobus Core и живая D01/D04/D05. |
| R02 / D06–D08 | Безопасный вопрос о цвете отчёта адресован автору; явная просьба о согласии и неизвестная форма останавливаются у владельца/Desktop. | Все App/MCP семейства и полный цикл pending в реальном Desktop. |
| R03 / D08,D12 | Exact pending reconnect generation CAS проходит без новой карточки; изменённые параметры и истечение срока отвергаются. | Live reconnect/одновременный ответ Desktop–Telegram. |
| R04 / D10–D12 | Ordered reference plan и стабильные ordinal обеспечивают досылку A после B без повторного B; изменившиеся bytes → unknown. | Живой сетевой lost ACK и восстановление квитанции. |
| R05 / A07 | Точный зарегистрированный Git worktree того же проекта проходит, чужой/nested cwd — нет. | Managed-worktree задача Desktop в реальном UI/IPC. |

Дополнительно точная прежняя DDL checkout `3ea2438` воспроизвела pinned
digest и мигрировала на изолированной SQLite; повтор миграции не нужен.
Попытка чтения фактической production SQLite из текущего sandbox получила
`Access denied`, без обхода. Следовательно, A01 на фактическом контуре
не закрыт. Read-only UIA один раз увидела видимое окно и активный header;
последующее окно отсутствовало, действие InspectNewTask не выполнилось,
временный action удалён. Для OpenAndSubmit добавлена проверка header перед
вводом и отправкой, но create-context A06 остаётся непроверенным.

Связанный набор на текущем WIP: `225 passed, 1 skipped` в 14 M2 файлах,
Windows PowerShell 5.1 parser UIA-скрипта — 0 ошибок, `pip check` — без
конфликта требований. Разбор security-эвристик вынесен в
[SECURITY-TRIAGE-20260924.md](SECURITY-TRIAGE-20260924.md). Это не новый
замороженный кандидат и не независимый L1/L2/L3; live D01–D17 открыты.

### A09 — точная установка skill guard, 24.09 около 16:55 МСК

Владелец подтвердил ровно два целевых файла и SHA-256: новый sender
`d38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e`,
guard `e20cd35d1d09fc5c90ee91fe37bf80b4057de86ab4bb9e117d2ae0f0e6e6fe20`.
Первая staging-попытка завершилась до записи в skill: `git apply` отказал
из-за dubious ownership канонического репозитория. Git trust не меняли и
отказ не обходили. Установщик переведён на точное применение двух вставок
с обязательной проверкой итогового SHA. После readback прежнего sender и
отсутствия guard установка прошла; точные два installed SHA совпали.
Резервная копия `send_result.before.py` имеет исходный SHA-256
`595f4db569519d1bb545b16320dbf8aabee3277d46263fe3f0d3efa04476a4df`
и лежит по пути из release plan. Попытка `py_compile` получила отказ в
записи кэша вне workspace; read-only AST parse обоих файлов прошёл.
Проверки на текущих WIP-байтах: `226 passed, 1 skipped` в 14 связанных
файлах, включая 8 тестов guard и fake-home installer. Тесты допускают
состояния до и после установки и отвергают неизвестный installed digest.
Ни одного Telegram-сообщения, Desktop turn, изменения settings/credentials
или production task это обновление не выполняло. Положительный live
single-sender/opt-out smoke и D01–D17 всё ещё открыты.

### A06 — уточнение среды read-only UIA

Повторные нулевые результаты из sandbox-пользователя не означали закрытое
окно Desktop: пользователь видел его, процессы были в той же SessionId 3,
но read-only семантическая UIA из этого контекста не находила документ.
Разрешённый read-only запуск в интерактивном контексте увидел Desktop
`26.917.9434.0`, process 8312 и точный раскрытый проект. Ограниченный
диагностический снимок вернул два элемента с именем проекта, оба в дереве
бокового списка; следовательно, это не доказательство выбранного контекста
пустой новой задачи. Никаких кликов, ввода, task или Telegram-отправки не было.
До pre-send guard нужно наблюдение пустого нового вида проекта, затем
локальный тест смены активного контекста и отдельный live check.

### A06 — открытая владельцем пустая новая задача, около 17:30 МСК

Видимое окно Desktop `26.917.9434.0` сохранялось, но UIA находила 3–5
`RootWebArea` вместо одного; прежний fail-closed selector возвращал 0
документов. Ограниченная read-only диагностика показала, что только один
web-корень содержит `AutomationId=root` и элементы нужного проекта.
Адаптер теперь требует единственного app-root при любом количестве
web-корней. После этого в пустом виде обнаружены два разных элемента
проекта: боковой пункт и активная кнопка в main view; отдельно видна
кнопка «Новый чат». Предохранитель требует ровно один видимый активный
проект вне sidebar и ровно одну кнопку «Новый чат» перед вводом и снова
после проверки draft непосредственно перед send. Read-only применение
этого же предиката к настоящему открытому виду вернуло `true` без мутаций.
Windows PowerShell 5.1 parser: 0 ошибок; шесть UIA-тестов и связанный набор
`226 passed, 1 skipped` прошли после основного изменения. Негативное
переключение на существующую задачу того же проекта и реальная отправка
не проведены; A06 не объявлять полностью закрытым.

### A06 — отрицательный UIA-снимок, около 17:45 МСК

Владелец вручную переключил установленный Desktop на существующую задачу
того же проекта. Read-only Snapshot сохранил точный проект в sidebar, но
в основном виде отдельной активной кнопки проекта не было; тот же
`Assert-NewTaskProjectContext` вернул `false`. Кнопка «Новый чат» сама по
себе остаётся видимой и потому не использована как единственный признак.
Снимок выявил, что временная диагностика названий main-view элементов
может захватить текст задачи; этот вывод удалён из кода, структурный
предохранитель не изменён. UIA не вводила текст и не вызывала send.
Положительный и отрицательный read-only результаты подтверждают guard
контекста, но не реальное создание/correlation и не полное закрытие A06.

### A06 — одна live-попытка с неизвестным исходом, около 18:02 МСК

По точному разрешению владельца один раз вызван `CreateAndSubmit` в
`nobus-orchestrator-dev` с уникальной меткой
`M2A06-20260924-ONE-SHOT-8E5317A0` и запретом инструментов, сети и
файловых изменений. IPC был подключён до вызова. UIA receipt не получен:
PowerShell завершился с ошибкой, локализованный stderr вызвал
`UnicodeDecodeError` в Python, внешний код вернул
`desktop-uia-action-failed`. За 30 секунд IPC не сообщил новую задачу;
read-only Snapshot сохранил прежний вид, а read-only список недавних задач
не выявил тестовую. **Классификация: unknown outcome**, не `PASS` и не
доказанное `ABSENT`. Повторного UIA send, IPC turn или Telegram product
send не было. Исправлена лишь диагностическая потеря stderr для будущих
попыток (`errors="replace"`), шесть адресных тестов прошли. Причина
неуспешного UIA действия остаётся невыясненной; A06 и D01–D17 открыты.

### A06 — причины отказов после расширенного разрешения, около 18:30 МСК

Новые уникальные метки использовались по одному разу. `…SECOND-5FD883B1`
остановился до создания на `find-create-control`: отсутствие UTF-8 BOM
приводило к ANSI-разбору русского селектора Windows PowerShell 5.1.
После восстановления BOM read-only UIA нашла exact project create control.
`…BOM-3B7B2E91` открыл пустой проектный вид, но не ввёл prompt;
`…REFRESH-7A88C26D`, `…COUNT-2F9B809C`, `…SPLIT-BAE84D03` тоже
остановились до send. Для них owner IPC не получил новой задачи. Точный
read-only поиск composer успешен; булева проверка показала непустой draft
без тестовой метки. Никакого чтения/изменения текста draft нет. Владелец
попросил сохранить/очистить его вручную. Версия про устаревший UIA root
не выдержала проверки, её локальное изменение удалено. Адаптер теперь
различает отказ на `check-draft-empty`; `58 passed` в двух адресных файлах,
native PS5 parser 0. Полного Desktop turn/answer и приёмки Gate нет.

Уточнение после ответа владельца: он сообщил, что draft сохранён/очищен,
но read-only UIA в текущем пустом виде проекта по-прежнему видит 20
непробельных символов. `ValuePattern` и `TextPattern` совпадают; значение
не равно accessible name и не содержит известную тестовую метку. Исходное
содержимое не раскрывалось. Второе точное уточнение отправлено владельцу,
дальнейшего send пока не было. Продуктовый bridge теперь выдаёт специальное
уведомление только для exact `existing-draft`, сохраняя статус unknown и
запрет автоматического повтора; `60 passed` в связанных тестах.

### A06 — установленный Desktop: create, IPC и UI продолжение, около 19:18 МСК

Владелец подтвердил визуально пустой chat. Точечное read-only обследование
установило причинную ошибку прежней классификации: `ValuePattern` и
`TextPattern` пустого Chromium composer равны LF + accessible placeholder
`Поручите что угодно`, длина 20. Это не чужой черновик. Точный guard стал
распознавать только эту форму, не подменяя произвольный текст. В новом виде
обнаружены две видимые кнопки «Новый чат» (глобальная и основная); проектный
контекст проверен по единственной активной кнопке проекта. Попытка с новой
меткой `…PLACEHOLDER-C6F91304` остановилась до ввода на старом счётчике,
`…CONTEXT-5CFBE207` записала точный текст, но мгновенная UIA-проверка
`ValuePattern` увидела прежнее значение и остановилась до send. Read-only
повтор уже увидел ровно наш запрос в поле. Создание/ввод не повторялись.

В локальном адаптере добавлено bounded ожидание точного значения после
`SetValue` и отдельное однократное действие `SubmitExactDraft`: оно не
открывает задачу и не вводит текст, а дважды сверяет полный prompt и
проектный контекст перед семантическим `Invoke` кнопки «Отправить».
Адресные тесты UIA/bridge: `60 passed`; parser PowerShell 5.1: 0 ошибок.
После read-only подтверждения точного текста это действие один раз
отправило уже набранную метку `…CONTEXT-5CFBE207`.

Новый thread `01a0d432-e0c9-7280-bcd5-4350a8c7843f` обнаружен owner IPC
и списком задач установленного Desktop с `cwd` сохранённого проекта.
Первый turn `01a0d432-e6b6-7aa0-8e55-fc2a6445aa11` завершён с точным
полным финалом `M2A06-20260924-CONTEXT-5CFBE207 OK`. Отдельный внешний
IPC client затем отправил уникальный второй ход в этот же owner:
ACK `01a0d434-ab36-7c40-aada-f815b814d0dc`, история завершила его
`M2A06-20260924-IPC-159C7A42 OK`. Наконец, семантический UI
`OpenAndSubmit` открыл ту же задачу; IPC обнаружил один третий turn
`01a0d435-e430-7d03-bd48-114f93d7aacb` с финалом
`M2A06-20260924-UI-927EA64C OK`. Уникальные one-shot sentinels не дают
запустить изменяющий probe второй раз. Отдельный App Server/CLI не был
исполнителем этих ходов.

Это закрывает узкую транспортную гипотезу A06: реальное создание в Desktop,
видимость, тот же owner и двустороннее продолжение с readback. Не закрывает
проверку смены проекта в момент send, concurrency/lost ACK в живом продукте,
полный набор возможностей Desktop, pending request/approval, Telegram и
длинный ответ/файлы. `projectId=null` в native list не объявлен дефектом:
подтверждён проектный `cwd`, контракт равенства ID отсутствует. Глобальный
notifier: read-only one-shot SQLite ledger содержит `sent` для всех трёх
test turn. Это три автоматических summary, а не продуктовая доставка полного
ответа; фактические сообщения Telegram отдельно не сверены. Продуктовый
Telegram bridge не запускался. Production Tasks по последнему снимку Disabled.

### A06 / D09–D10 — настоящий Bridge с локальным приёмником, около 19:40 МСК

Проверен следующий, более широкий слой без production и без вызова Telegram
API: реальный `DesktopBridgeService`, настоящие UIA и owner IPC, но SQLite
в ignored `.runtime/m2-desktop-live-probe/bridge-isolated-20260924/` и
фальшивые `send_message`/document delivery. Однократный create request
`0d9b968f-4ffc-469a-870e-28a975647353` создал Desktop thread
`01a0d43f-edb8-70e2-85ae-5434cc992228`. Bootstrap и пользовательский
ход различны; последний turn `01a0d440-6796-7cf1-b932-bd15d0164c82`
завершился, состояние `delivered`, один полный финал поступил в локальный
приёмник по `chat=-1001/topic=7/reply=12`.

В той же задаче второй уникальный request
`fbec884c-52bf-45c7-ac00-9889338e20ce` продолжил её через owner IPC,
без UIA-новой задачи. Desktop реально создал тестовый файл только под
`.runtime/m2-desktop-live-probe/` и вернул длинный финал в turn
`01a0d442-da65-76b3-842f-ce49f2d939b9`. Read-only история содержит
отдельные `commentary` и `final_answer`. Вторая локальная доставка:
`delivered`, 2 текстовые части, `answer.md` и исходный файл, все 4 слота
`sent`; `answer.md` имеет точный digest видимого финала 6 243 символа,
файл — совпадающие bytes/SHA-256
`b326ff2bfa5d4f34549dccf23ba7b494a92384576fafade12451c0254ee7bd07`.
В выводе первого harness стояло `answer_md_exact=false`, потому что он
сравнил `answer.md` со всеми `complete_text_output`, включая неитоговый
комментарий. Read-only повтор сравнил именно `final_answer` и delivery
ledger: digest совпал; исходный финал маркер notifier не содержал. Это
исправление диагностического вывода, не потеря содержимого продуктом.

Для обоих turn и bootstrap второй задачи read-only глобальный notifier
ledger имеет `sent`; изолированная SQLite намеренно не подключена к его
production binding, поэтому этот опыт не доказывает opt-out. Никакой
продуктовой Telegram-отправки, изменения credentials/config/Tasks, push
или deploy не выполнялось. `230 passed, 1 skipped` в 14 связанных M2
файлах. D09/D10 теперь имеют реальное Desktop+локальное delivery evidence,
но остаются OPEN до подтверждённой доставки в настоящую тему Telegram;
A09/A13, A01, прочие D01–D17 и полный L1/L2/L3 открыты.

### A08 / D06–D07 — асинхронное уточнение и owner approvals, около 20:35 МСК

Версия Desktop `26.917.9434.0` отдаёт `request_user_input_async` как
`agentMessage(delivery=async, questions=...)`. Первый ответ автора через
изолированный Bridge не дошёл до Desktop: `thread-follower-steer-turn`
требовал `restoreMessage`, которого адаптер не передавал. Состояние после
неопределённого ACK сверено по exact thread/turn/call: вопрос оставался
pending, `steeringUserMessage` отсутствовал. Исправление и локальные тесты
предшествовали единственному восстановлению с прежним message ID; owner ACK,
один steering message и точный финал подтверждены. Новый request
`27273ac4-33da-41c6-8a81-a5c8b33c46af` затем прошёл полноценный
Bridge→Desktop→Bridge цикл: карточка автору `41`, отказ `55`, ответ `41`,
одна финальная доставка в fake topic `13`. В итог не попал текст карточки.
После post-claim IPC error request теперь переходит в `unknown_dispatch`;
автоматического повтора нет.

Первый approval-проход остановился потому, что renderer не знал шесть
добавленных полей установленной версии. Это безопасный manual fallback,
не отсутствие pending. Поля адресно добавлены с полным показом владельцу;
неизвестные поля сохраняют fail-closed. Старый safe approval отменён
решением `cancel`, turn interrupted; test request помечен failed после
readback. Следующий allow-сценарий остановила ошибка самого harness:
он использовал ID вводного mention, а не последней карточки. Pending-карточка
`7002` была найдена в изолированной SQLite и продолжена без нового turn:
чужой `41` отклонён, owner `99` разрешил `Write-Output`, точный финал
доставлен один раз в fake topic `15`. Отдельный deny request
`fe3376c7-e2cd-4f2d-bfd2-197be59785f8` получил отказ owner `99` на
`Start-Process calc.exe`; Desktop turn interrupted, в нём нет
`commandExecution`, fake topic `16` получил сообщение о неуспехе.
Для 26.917 отказ передаётся как предложенный `cancel`, не произвольный
`decline`; команда не запускалась.

Связанный M2-набор: `236 passed, 1 skipped` и один независимый сбой теста
установщика. Тестовый `git apply --reverse` из temp внутри родительского
Git root завершался без изменения временного файла. Установленный sender
имеет утверждённый новый SHA, резервная копия старого имеет утверждённый
старый SHA; тест заменён точным механическим обращением двух вставок со
сверкой SHA и прошёл `8 passed`. Последняя правка затронула только тест;
полный связанный набор после неё будет повторён на замороженном кандидате.
Production, реальный Telegram, positive notifier opt-out, полный D01–D17
и L1/L2/L3 не проверялись этим checkpoint.

Следующая read-only проверка **установленного**, а не только исходного
notifier использовала реальный Desktop session marker завершённого bridge
turn и изолированную SQLite-привязку. `desktop_bridge_turn` вернул true
только для точного thread/turn/request; чужой turn и отсутствие state дали
false. Это позитивное offline доказательство selector opt-out A09. Telegram
API не вызывался, рабочая notifier-конфигурация не менялась; live отсутствие
дубля по-прежнему OPEN.

Единый связанный повтор после исправления тестового helper: `237 passed,
1 skipped` в 14 файлах. Общий `pytest tests` внутри repo-root temp дал
множество Git-fixture сбоев; после переноса temp наружу `pytest -x` прошёл
44 теста и остановился на историческом Gate 0 dirty-manifest assertion,
который ожидает другой предсуществующий WIP. Это ограничение общего
набора не маскируется и не объявляется дефектом M2-моста; старые Gate 0
fixtures не правились.

### Локальный code checkpoint 55297db и release preflight

Документальный commit `16f9029d4426577ebaa61826b8baa76f6c627c6c`
имеет tree `d6840c926ec933d89e9cad5ae86381d12f7e0c35` и чистый
Git-экспорт ZIP SHA-256
`0b1bea51ea59137f4e64c15ff24bfeb0f37cef9d18254067c4a55b1f4a0ec62c`.
Этот экспорт прошёл те же 14 связанных тестовых файлов: `237 passed,
1 skipped`; skip только для проверки sender до уже установленного v2.
Старый независимый audit harness дал R01–R04 PASS. Его R05 synthetic
unregistered cwd дал fail-closed, что не свидетельствует о регрессии:
адресный read-only вызов на настоящем зарегистрированном worktree от
пользователя-владельца вернул true, на вложенном незарегистрированном —
false. Для живого managed-worktree continuation доказательства ещё нет.

После test-fixture исправления чистый ZIP-экспорт точного commit
`55297db440b502292159f2612c579f588e37c323` (tree `e0cde457…`, ZIP
SHA-256 `13f2cf38805de7b9d457bcb8f9a5db96c707c1e3d1466300a20748a3e7e2c18c`)
прошёл `237 passed, 1 skipped` в 14 M2-файлах. Guard и patch в архиве
сохранили exact SHA благодаря `eol=lf`. Негативные сценарии owner ID,
stale/expired approval, lost ACK, replay, reconnect, partial/changed file
и неизвестный исход входят в этот набор; отдельная живая Telegram-приёмка
ими не заменяется. Адресный поиск типовых ключей в восьми изменённых
исполняемых файлах — 0 совпавших файлов; новых зависимостей нет.

Три конкретных Scheduled Tasks read-only подтверждены Disabled с точными
старыми XML SHA из release plan. Backup journal read-only инспектором
текущего live checkout дал `phase=complete` и прежний confirmation digest
`sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`.
Инспектор новой ветки закономерно отказал до чтения журнала из-за другого
application binding; отказ не обходился изменением config. Staging,
backup cycle, production и Telegram не запускались.

### 25.09 — выгруженная Desktop-задача и recovery через UIA

После restart задача, остающаяся в списке Desktop, дала IPC `no-client-found`.
Штатное открытие в Desktop восстановило owner. Минимальное исправление
`b8834ae` добавило UIA `OpenExisting` без prompt/send и сохранение последнего
IPC-подтверждённого title в bridge SQLite. Перед любым продолжением после
UIA требуется read-only owner для **исходного** thread ID и обычная проверка
проекта по `cwd`. Нет title или owner — WAITING_PC, не CLI fallback.

Live-проба на установленном `26.917.9434.0`: первый open-only receipt не
сопроводился owner и не принят; затем штатное открытие этой задачи owner
вернуло. Вторая open-only проба на другой выгруженной задаче вернула exact
owner сразу. Ходов, approvals и Telegram не было. 69 адресных тестов, PS5
parser 0; широкий L1 на `b8834ae`: 2904/3 skip/7 исторических deselect;
чистый Git ZIP L2: 247/1 skip. Это не D12 live Telegram recovery.

Неустранённые границы: произвольный ранее не связанный thread без owner/title
нельзя надёжно открыть внешним UIA только по ID; нужна ручная загрузка в
Desktop. Имя может устареть, и тогда система останавливается, не угадывая.
Production и D01–D17 не активированы; точная release-привязка прежнего
`16f9029` устарела. Исторический набор Gate C0/MVP1 не переделывался.

### 25.09 — production restart failure и адресная функциональная работа

Exact approval `fa6f1f0` позволил staged-disabled замену трёх заданий,
локальную копию каталога проектов, новый backup config, signed rebind и один
backup cycle. Rollback-копии и старый checkout сохранены. Rebind прошёл с
`REBOUND` и inspect `PASS/new`. Один backup reconciliation от точного
старого complete digest создал verified generation, затем Main завершился
кодом 75; signed failed journal (digest `sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`)
показывает `failed_phase=starting`, `admission_hold=true`,
`cleanup_proven=true`. Все три Tasks Disabled, новая runtime запись отсутствует.
Повторов и Telegram-вызовов не было.

Причинный read-only разбор: `record()` во время reconciliation подписывает
`reconciled_from_digest` на каждой фазе, включая `restart_permitted`;
`_backup_restart_authorized()` на deployed commit считал это поле неизвестным
и отклонял activation manifest (`exit 75`). WIP-патч принимает поле только
при `backup_status=VERIFIED`, проверяет SHA-формат и продолжает отвергать
любое иное поле. Отрицательные тесты добавлены. Recovery требует нового
точного release-решения; failed journal не перезаписывать вслепую. Новый
`--rebind-failed-digest` отделён от same-config failed recovery и принимает
только exact signed receipt после verified backup и доказанного STOP; он
архивирует прежний журнал перед новой generation и отвергает replay.

Для R01 без распознанного явного синтаксиса добавлено durable author-choice
создать/продолжить. Это блокирует неправильное автоматическое продолжение
при адресованном «в проекте … создай …», но не является универсальным
смысловым resolver Core. Голос сначала подтверждает ASR, затем маршрут;
фоновое голосовое сообщение по-прежнему не перехватывается. R02 имеет
позитивный вопросный и отрицательный consent пример, однако IPC не даёт
доверенной классификации всех `requestUserInput`; неоднозначный тип
остаётся owner/manual Desktop и вынесен на согласование.

Для не связанной с bridge выгруженной задачи `01a0c547…` read-only IPC
подтвердил `no-client-found`, UIA нашёл один точный sidebar item и открыл
его, следующий IPC snapshot подтвердил исходный ID, title и project cwd.
Это open-only proof, не продолжение turn. Новый явный Telegram selector
хранится как подсказка UIA, не как доверенная identity.

Исторический `ops_queue1` повторно запущен как проверка поведения: 11
положительных и 2 несовместимых статических ожидания. Два теста приведены
к текущему имени health probe и readiness pair/details; WhatIf по-прежнему
проверяет отсутствие записи. Итог `13 passed`; связанный затронутый набор
после правок `187 passed, 1 warning`. Старая заморозка `fa6f1f0` не
распространяется на новые bytes. Новый независимый кандидат и реальная
Telegram-приёмка ещё впереди.
