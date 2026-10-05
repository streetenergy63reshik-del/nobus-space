# M2-DESKTOP: план контролируемого выпуска

## 05.10, 14:38 — плиточное меню выпущено для ручной приёмки

План применён к точному source/live `9aeff52c3d11e895e048bb496cdaa6c17845b057`:
стадийное выключение трёх Scheduled Tasks, чистое завершение Main,
backup config и signed rebind, один exact reconcile, запуск Main/Health,
readiness и Telegram profile PASS. Новый complete/VERIFIED backup и
точные receipt приведены в [доказательстве выпуска](RELEASE-EVIDENCE-20261005.md).
Документы ниже сохраняют историю прежних выпусков, а не текущие команды
для повторного применения. Ручные D02–D17 и меню ещё не проведены;
Gate/MVP2 не приняты.

## 29.09, 08:55 — повторный запуск после подписанного STOP

Source/live и config binding остались `bd991760312732dd15cdad909e81a6023cc703f2` /
`sha256:815329379042de1ecd59d0ea0ddb74f659143f74a79ea99f014fcd709a7ba27b`.
28.09 внешний readiness отказ и неуспешный startup оставили signed STOP;
плановый backup создал VERIFIED copy, но restart был NOT_READY. 29.09
после read-only preflight выполнены один exact STOP reset и один recovery
по failed journal digest. Новый complete journal
`sha256:16daf29fc6534bcdc4e3c772ca05866b3fd9c2c2c7b15adb557e47f21c0ba911`,
generation `daily-20260929T085111-deeac3d9f6824ee89466d04829bc677b`
проверена. Main Running, Main/Health/Backup Enabled, local/public readiness
и два Health PASS. Следующий плановый Backup 30.09 ещё не проверен.
Ручные D02–D17 открыты; кодовые L1–L3 не повторялись, поскольку source
bytes не менялись. Нижние разделы сохраняют предыдущие состояния.

## 27.09, 18:20 — восстановление и запуск выполнены

Live checkout и source `bd991760312732dd15cdad909e81a6023cc703f2`,
tree `69dae321773812fd3d2a96004ae86f6ee3e3812b`. Новый config digest
`sha256:815329379042de1ecd59d0ea0ddb74f659143f74a79ea99f014fcd709a7ba27b`;
Main/Health/Backup Enabled, Main Running, local/public readiness PASS.
Backup cycle на этом binding complete/VERIFIED с journal digest
`sha256:6869c2093588b176a8b9181444d82323afaa64465ae299434fe95d9bfb9e2a16`.
Предыдущий failed restart на том же config сохранён; recovery выполнен
по его точному digest, без удаления файлов и без повторения Desktop turn.
Кодовые L1/L2/L3 привязаны к bd991. Следующий шаг — только владелец
проходит D02–D17, после результатов устраняются подтверждённые дефекты,
затем оформляются принятие и публикация. Текст ниже — история подготовки;
его старые digest не являются командами текущего восстановления.

## 27.09, 11:38 — передача Gate и read-only preflight

Предыдущий ответственный чат `01a0c425-3a83-7e82-b4c5-9a71e8251ecc`
остаётся idle; запись ведётся только в текущем Gate. Рабочие изменения
сохранены. Проверенный source `c6f6858` ещё не развёрнут. Live checkout
чистый на `fd4d66c`, Main/Health/Backup Disabled, порт 8765 закрыт.

Текущий signed failed backup journal `sha256:2248227dbd32ab08d2608e491c35ca16f98648e38d62d20d7b34c6f7938790ac`
имеет `failed_operator_required/starting/restart_not_ready`,
`admission_hold=true`, `cleanup_proven=true`. VERIFIED generation
`daily-20260927T033029-777f247f8b534c47a07e804bf35d74e9` проверена
по manifest `sha256:e47d610b8b758effa31805550cb7ad2593468b77c3ab65c997b3257636be3056`.
Recovery inspector показывает `STOP/stop_non_retryable`, head
`sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Последняя signed terminal-запись до ночного цикла —
`local_public_readiness_failed` 26.09; журнал 254453 байта при лимите
1 MiB, признаков незавершённой ротации в каталоге нет. Эти наблюдения
не доказывают, что новый код решит runtime-сбой до реального запуска.

Старый D03 request `5b965633-8670-4db5-a67f-2a530ca48f78` хранит
`running` без delivery rows; Desktop turn `01a0df02-48f2-7453-955e-350fbee2e0ea`
уже completed. Его не выполнять заново. Перед recovery нужен точный
config/Task/source preflight, новый application binding и один разрешённый
штатный цикл с readback. Текущий запрет удаления файлов охватывает
автоматические SQLite sidecars; узкое исключение запрошено у владельца,
ответ ещё не получен. До ответа backup/rebind/restart/deploy удержаны.

OSV-срез 80 установленных PyPI-дистрибутивов и шести уникальных CVE
в `pip 25.0.1` зафиксирован в `SECURITY-TRIAGE-20260924.md`.
Новый `UAT-20260927-01` и текущие незакрытые пункты подготовки указаны
в канонической `M2-DESKTOP-MANUAL-ACCEPTANCE.md`.

## 27.09, 10:34 — локальный кодовый кандидат проверен, выпуск не начат

`c6f6858ea1693ea046130a97061fe8fd5f589e47` / tree
`630ef35e7648cf828d2da5cb6aad15f408644d21` прошёл L1/L2/L3
по [handoff](HANDOFF.md). Это только проверка исходников. Production
последней подтверждённой сверки остаётся остановленным на `fd4d66c`;
старые digest, Task signatures и recovery-действия ниже исторические,
их нельзя механически повторять. До выпуска заново проверить реальные
Task/config/journal/head, сохранность D03 completed turn и отсутствие
неизвестных исходов; D02–D17 и CVE-аудит не закрыты этим checkpoint.

## 27.09, 10:05 — первая локальная заморозка не прошла L1

Коммит `2355ae5` дал `2933 passed, 2 failed`; одна причина в
readiness-dispatch исправлена только в WIP, семь адресных тестов
прошли. Этот SHA не выпускать и не считать L1/L2/L3-верифицированным.
Нужен новый commit и полная кандидатная цепочка; исторические
production-действия ниже не повторять. Production `fd4d66c` остаётся
выключенным.

## 27.09, 09:43 — локальный DRAFT для freeze/L1–L3; это не выпуск

Текущая команда владельца разрешает заморозить один локальный кандидат
и проверить L1–L3. Она не поручает повторять исторические reset,
backup/rebind, Telegram turn или deploy на этапе проверки. Точный SHA/tree
кандидата появится после commit и будет вынесен в post-commit evidence;
этот план не должен сам ссылаться на собственный будущий SHA.
Предзаморозочная проверка bridge/docs: 68 passed и один отказ Git
`$GIT_DIR too big` в длинном кириллическом pytest path; тот же тест
прошёл в коротком уникальном temp. Production остаётся остановленным
на `fd4d66c` с signed STOP/admission hold, все три Scheduled Tasks
Disabled. Исторические циклы ниже не переисполнять.

## 27.09, 08:22 — STOP: ночной backup оставил admission hold

Этот план ниже содержит исторические действия, не команду на повтор.
Включённый ранее Backup Task автоматически выполнил VERIFIED generation
в 03:30, затем остановился `failed_operator_required/restart_not_ready`
с `admission_hold=true`; Main/Health выключены. Backup теперь тоже
штатно выключен, чтобы не повторить удаляющий staging старый цикл.
Текущий read-only `--inspect-recovery` подтверждает `STOP/blocked` и
head `sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Локальный WIP без overwrite control-файлов
отказывает при crash-gap, но не доказывает восстановление и отсутствие
SQLite sidecar-удалений; backup/rebind/reset/deploy
не выполнять до доказанного соблюдения no-delete.

## 26.09, 22:47 — STOP: no-delete не подтверждён

Этот документ содержит исторические уже выполненные циклы. Новый
локальный checkpoint `91a0499` **не выпускать**: FileSystemWatcher
увидел 59 `Deleted` событий в синтетическом backup-тесте, хотя `pytest`
дал `4 passed`. Источник каждого события не записан, повторять тест
без новой проверяемой гипотезы нельзя. Действующий запрет владельца
на удаление файлов важнее готовности к выпуску. Production остаётся
на `fd4d66c` и остановлен; новый backup/rebind/reset не запускать.

## 26.09, 19:18 — fd4d66c выпущен, этот цикл не повторять

По точному подтверждению выполнен только один выпуск
`fd4d66cfccb66c29702c29f6df59d137d3c26e3b`. Rollback:
`.runtime/m2-desktop-release-20260926/fd4d66c-preflight/` и ветка
`codex/m2-desktop-cdc59a2-before-fd4d66c`. После остановки runtime
signed recovery head был
`sha256:64dbfd5e5203f257e8f28e79d1cf519740e9b95575b08816627c95dac56140cc`;
один rebind создал
`sha256:bbf59776cbbc783b2e860109724d609e38916b64ddabe5fa5cd3ecb19ef9843d`.
Новый config digest:
`sha256:cb9af8931da6d9f0e896c208f6697845e6e7a23ecb12fa6501f9edb345c9d407`.
Один reconcile от прежнего complete journal
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`
дал `PASS`, VERIFIED generation
`daily-20260926T191008-36e07f063a674ffcab3fa810defcfa98`.
Новый signed complete journal:
`sha256:3ceca795c3273a3802fa92fbc3b08c5d2fbdaa03a06dc78b3d0144e5f819b71a`.
Main работает, Health/Backup готовы, readiness `PASS`.
Следующий шаг — новые Telegram D01–D17, не повтор release/reset/cycle.

## 26.09, вечер — новый WIP не входит в выполненный выпуск

На `cdc59a2` после одного отдельно разрешённого operator reset Main снова
работает. Первый реальный Telegram-запрос выявил ошибку маршрута при
`reply_to` корня темы. Исправление находится только в локальном WIP;
`292 passed` затронутой регрессии не являются freeze, независимой
проверкой или разрешением на следующий production выпуск. Этот план ниже
фиксирует уже выполненный выпуск `cdc59a2`; его backup/rebind не повторять.

Вторая реальная команда дошла до bridge, но его UIA version pin отказал
до Desktop-действия: установленный Desktop `26.924.2738.0`, production pin
`26.917.9434.0`. Новая версия и задержка загрузки проектного экрана
адресно исправлены и проверены на отдельной видимой Desktop-задаче только
в WIP. Любой следующий выпуск — новый exact commit/config/signed-head
preflight и отдельное разрешение; старый release plan не переисполнять.

## 26.09 — этот выпуск выполнен; новый цикл без основания не запускать

По точному разрешению выпуск `cdc59a2` завершён: rollback сохранён в
`.runtime/m2-desktop-release-20260926/cdc59a2-preflight/`, новая конфигурация
имеет digest `sha256:bd885e5ef5953aae9ac6a38011c5a0f4b49d9f36816d361fb2664aacd929b685`,
signed recovery head после однократного rebind —
`sha256:fdb116d5bc52fc322a77759c0a5d63387a13b70588e47f2221a2eaad8c79f9bf`.
Backup включён до запуска Main. Один `--rebind-failed-digest` от
`sha256:7221cf56…92df` завершился `PASS` и подписал `complete` journal
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`.
Main `Running`, Health/Backup `Ready`, local/public readiness `PASS`.
Следующий этап — живой Telegram-продуктовый сценарий, не повтор этого плана.

## Исторический снимок до выпуска: проверенный local target `cdc59a2`

Точный commit `cdc59a2ebd5d228e062937625da209be6d652c4a`, tree
`0ac7807464c3ffbdd25a18b415bcce1f4fa47711`, code digest
`sha256:0ad4d015b031d7d7fd2348eb41d4937fff2dd68fd73cf803f6d473c84ef1147e`.
Широкий L1 — `2915 passed, 3 skipped, 5 exact historical deselected`;
чистый Git ZIP SHA-256
`16d77414ccb4620c1fa5511f39346b829a1d7601d4b77b3afcff9d4562cddf21`,
связанный L2 — `491 passed`; L3 проверил обе interpreter evidence и
signed recovery границу. На момент этого снимка production был выключен
на `26b95e5`, а точный выпускной допуск ещё ожидался. Не переносить в production
послепроверочные docs addenda: `application_binding()` включает Git HEAD,
поэтому docs-only commit изменит binding даже без изменения Python-кода.
После разрешения применять только `cdc59a2` и повторно сверить точные
preflight значения ниже до каждого эффекта.

## 25.09, вечер: signed recovery остановлен на interpreter binding

После точного подтверждения Backup Task был включён только после проверки
чистого `26b95e5`, XML-хэшей трёх заданий, same-config signed journal
`sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`,
отсутствия процесса и будущего `NextRunTime` 26.09 03:30 +03:00. Readback:
Backup `Ready`, Main/Health `Disabled`. Ровно один
`--recover-failure-digest` создал VERIFIED generation
`daily-20260925T194753-54c9cc845cdd4ee2828fc77c491302a2`, но Main
завершился кодом 78 (`recovery_history_blocked`), а цикл —
`failed_operator_required`. Новый signed journal digest
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`,
`starting/restart_not_ready`, `admission_hold=true`, `cleanup_proven=true`.
Штатный readback подтвердил отсутствие процесса и неизменный recovery head
`sha256:f82b14b781526f4a6a8eb75d4e1eb432e5e8ac7bd16da6131796c76a2d6474b4`:
история под прежним binding остаётся `new`, latch отсутствует. После отказа
Backup Task был единственным Enabled и обратимо выключен; readback всех трёх
заданий — `Disabled`. Telegram не тестировался.

Причина кода 78 воспроизведена read-only: `sys._base_executable` для
`python.exe` указывает на базовый `python.exe`, а у Scheduled Task
`pythonw.exe` — на базовый `pythonw.exe` (exit-only probe 12). Старая
`_activation_manifest` хэшировала один из них под общим ключом
`base_python`, поэтому подписанный rebind через console и реальный GUI-run
получали разные digests: `sha256:060b26…` против синтетически вычисленного
`sha256:2ef8e1…`. Это не повреждение recovery history. В WIP код
канонически связывает **оба** базовых файла независимо от способа запуска;
целевая регрессия и пять связанных модулей дали `274 passed, 1 warning`.
Это локальная проверка, не новый frozen commit/полный L1/L2/L3.

Новый production выпуск нельзя проводить по старому разрешению/commit:
сначала цельный кандидат и независимая проверка, затем новый точный commit,
rollback, O_EXCL config под новый application binding, staged Backup Task,
signed recovery rebind от `sha256:f82b14…`, *включённый Backup перед стартом
Main* и только один `--rebind-failed-digest` **нового** journal
`sha256:7221cf56…` после точного readback. При неизвестном исходе не
повторять. Для этого нужен отдельный точный выпускной допуск владельца.

## 25.09: остановка второго восстановления на проверке Backup Task

По точному разрешению production checkout чисто переключён на
`26b95e556ac0374e43925ba55e92b119cf212e51`. Сохранены rollback XML,
launcher, config и inventory в
`.runtime/m2-desktop-release-20260925/26b95e5-preflight/`; создана локальная
ветка возврата `codex/m2-desktop-fa6f1f0-before-recovery`. Новый O_EXCL
backup config имеет канонический digest
`sha256:fcdb25b206e12885456b11001696397890411fd7dc93621d9411d5c23e3c4c74`.
Заменено только определение Backup Task с readback; Main/Health остались
Disabled. Подписанный recovery head перепривязан один раз: новый event
`sha256:f82b14b781526f4a6a8eb75d4e1eb432e5e8ac7bd16da6131796c76a2d6474b4`,
binding `sha256:060b26b17559eeed88a2d21a4d051bb227521a7ac5f86fb8c0db24c763b21078`;
`--inspect-recovery` после операции дал `PASS/new`.

Один разрешённый `--rebind-failed-digest` прежнего signed journal создал
VERIFIED generation `daily-20260925T160530-6da220b0e0cf4375a768b41b1e1270bf`,
но снова остановился в `starting` с Main exit 75. Новый signed failed journal:
`sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`,
`admission_hold=true`, `cleanup_proven=true`, все три Tasks Disabled.
Живые Telegram-тесты не запускались. Предыдущая причина с полем
`reconciled_from_digest` устранена в установленном commit; у этого отказа
другая проверенная причина: при запуске Main задание Backup осталось Disabled.
`_scheduler_activation` допускает Disabled Health по signed restart journal,
но требует Enabled Backup. Read-only вызов валидатора с фактическим Backup
snapshot воспроизвёл `scheduler task profile is invalid`; тот же snapshot
с разрешённым *только в памяти* staging прошёл. Текущий цикл включает Main
и Health, но не Backup. Это ошибка последовательности выпуска; код обычного
ежедневного цикла рассчитан на уже включённый Backup.

Перед возможным восстановлением нужно точное readback трёх Tasks, config,
signed journal и recovery head; затем отдельно подтвердить включение только
Backup Task и один `--recover-failure-digest` **нового** digest. Его
`NextRunTime` до включения — 26.09.2026 03:30 +03:00; после включения
проверить состояние до запуска цикла. При ином состоянии или неизвестном
исходе не повторять действие. После успешного readiness проверить Backup
Enabled, Main/Health Enabled и только затем приступать к live Telegram.
Старый `--rebind-failed-digest` не повторять.

## Обновление 25.09: stopped failure после точного staging `fa6f1f0`

Локальный проверенный code checkpoint для следующего выпуска:
`fe333c614e30340057acd917b592c2e36b62c574`, tree
`c016023e2b4b32a2403e2c50d312ddc905891730`. Чистый ZIP SHA-256
`063e6f0c7bc665fe83a0cc65b380aeb32d5fe6b956c21da87db81d95a31dcfb8`
прошёл 225 связанных тестов; широкий L1 прошёл 2915 тестов с пятью
точно перечисленными историческими исключениями. Это не продлевает прежнее
разрешение на `fa6f1f0` и не запускает production автоматически.

Исторический план ниже выполнен до единственного backup cycle. Подписанный
rebind прошёл, verified backup generation создана, но запуск Main завершился
кодом 75; failed journal digest
`sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`,
фаза `starting`, `admission_hold=true`, `cleanup_proven=true`, три Tasks
Disabled. Причина — old restart reader не принимал подписанное
`reconciled_from_digest`. Backup и cleanup прочитаны через штатный
inspector/DPAPI, но старый цикл/команду не повторять.

Новый WIP-кандидат добавляет строгое чтение этого поля и отдельный
`--rebind-failed-digest` для смены application/config binding после
подписанного failed journal. Требуются exact digest, verified generation,
`failed_phase=starting`, `failure_class=restart_not_ready`, доказанные hold и
cleanup, остановленные задачи и валидные новые config/Task signatures;
старый signed journal архивируется, создаётся новая generation. Неполный
backup, неизвестная фаза, чужой digest или отсутствие остановки дают отказ.

После независимой проверки нового точного commit и отдельного разрешения:
сверить rollback и disabled-состояние; переключить clean production checkout
на этот commit; создать новый O_EXCL backup config под новый application
binding; заменить только Backup Task в disabled staging с точными старыми
XML/config digest; подписанно перепривязать clean runtime head
`sha256:7a77a2b7bd37ea498cc2e97cac16661f9ee44adab02cab2e8b5bf6b112b65062`
к новой конфигурации; сверить inspect; один раз запустить
`run_telegram_backup_cycle.py --rebind-failed-digest
sha256:16ef2ad933ac69fe0f791529bfb2338264be1d1bb60698da866f0cb699a854da`
с новым config/digest. При mismatch остановиться до внешнего действия; после
lost ACK сначала readback. Telegram smoke только после readiness с
согласованной владельцем границей R02: неоднозначный текстовый
`requestUserInput` отвечает в Desktop, структурированные approvals —
только владелец по numeric user_id. Прежнее точное разрешение касается
только `fa6f1f0`.

Одноразовый локальный подготовитель config в игнорируемом каталоге
`.runtime/m2-desktop-release-20260924/prepare_backup_config.py` расширен
строгим флагом `--failed-journal` для этого signed состояния. Его SHA-256
`12edf775627fdee7587a9f56ca88528120afc03c96b0ae169894c6cef963b6ac`;
AST parse прошёл. Флаг требует точный старый config/journal digest,
`failed_operator_required/starting`, `restart_not_ready`, VERIFIED,
hold/cleanup и проверенную generation до O_EXCL создания нового config.
Production helper ещё не запускался.

Историческая запись до staging: production release PREPARED, не исполнен;
отдельно подтверждённое
обновление skill `nobus-send-results` исполнено. Этот документ не является разрешением
запускать старый Telegram request `e18a5ca3-95d3-4be8-8453-630d88e97a50`
или считать Gate принятым. Точные значения ниже сняты 24.09.2026;
перед любым изменением повторно сверить drift только у затрагиваемых целей.

25.09 локальный code checkpoint теперь `b8834aeedc7a7501bdc2049f8458ef025ab8c5ff`
(tree `8622aeb6c6d57ca80a6cbca693a65af6c43a0103`). L1 на нём:
`2904 passed, 3 skipped, 7 deselected`; чистый ZIP L2: `247 passed,
1 skipped`. Новый `OpenExisting` безопасно загружает только уже связанную
задачу с IPC-подтверждённым title; один live опыт подтвердил exact owner,
другой не дал owner и остаётся отрицательным свидетельством. Эта ревизия
ещё **не** staged и не активирована. Прежнее точное разрешение на `16f9029`
не относится к новой ревизии. Перед production нужны финальная docs/release
привязка, adversarial L3, свежее точное разрешение, затем шаги ниже.

25.09 после широкого тестирования код дополнен локальным исправлением
`935d93037a94f63e9e63395d626ebdec11cff515` в legacy migration
validator. Предыдущий точный план на commit `16f9029` более не покрывает
новые кодовые bytes. До production требуется новая candidate-bound проверка
и повторная сверка 24.09 Task/XML/journal квитанций; ни один внешний шаг
этим дополнением не выполнен.

Локальный code checkpoint `55297db440b502292159f2612c579f588e37c323`
(tree `e0cde457c7993791311a6e9249ddb6fb382626e3`) прошёл в чистом
Git-экспорте связанный набор `237 passed, 1 skipped`; он ещё не является
утверждённым release commit или замороженным Gate. Read-only preflight после
этого подтвердил все три Scheduled Tasks Disabled, совпадение XML-хэшей ниже
и `phase=complete` у подписанного журнала. Новый backup config, staging Task,
backup cycle и activation не выполнялись.

## Исходная граница

- `Code\worktrees\telegram-live`: clean detached HEAD
  `3ea243893a2647dc631662c2a2030de7679ae0e1`. Не терять его локальный
  ref/commit и существующие ignored settings/state. Новый revision ещё не
  выбран и не переключён.
- `NobusSpaceBot`, Health, Backup: все `Disabled`, не `Running`.
  SHA-256 экспортированных UTF-8 Task XML: main
  `0c911d18a7b4c159564be8117c94cf57ed19ba76059c1666e279d7bb99b30403`,
  Health `e03aeb76f446f24cb2e50ade9de1250ec3516f03970dab3facaa3d9c9cbf1913`,
  Backup `79d26acc5c3f414e2d65f2a98a96745fca8118f31c684d1f458a2fd32970a87e`.
  Health launcher SHA-256
  `ecda0dc163d90b6ea7f2bd9d5a0d0463ef1a52a7fcd975323597e2f52d2dff80`.
- Старый backup config digest задачи планировщика
  `sha256:7c3876a3f7e011c2e62ab77c67516bd033db889a2c8f235d1b81cf8de0337d79`.
  Штатный read-only `--inspect-failure` вернул `phase=complete`, точный
  journal confirmation digest
  `sha256:924656486923cc0c4c72acb65ce8e893de72ba6af193a05792a741eb7a4c738c`.
  Этот digest годится только пока подписанный журнал не изменился.
- Sender operation-key extension установлен, notifier v4 release
  `e6e08ba29097b3a35e58f43cf2a7619778b95bf72561d23499c31e91a6479eda`
  установлен. `bridge_state_path` указывает read-only на прежнюю production
  SQLite. Изменять notifier JSON повторно не требуется.
- Guard прямого вызова `nobus-send-results` из активного bridge-turn установлен
  24.09 по точному подтверждению владельца: `ops/windows/nobus_send_results_guard.py`
  SHA-256 `e20cd35d1d09fc5c90ee91fe37bf80b4057de86ab4bb9e117d2ae0f0e6e6fe20`,
  patch `send-results-bridge-owner.patch` SHA-256
  `0ad0f13203176261c298f8b1f83619349778f8a5e3f1d5f0a48928181bc614d7`.
  Патч `git apply --check` подходил к прежнему `send_result.py`
  SHA-256 `595f4db569519d1bb545b16320dbf8aabee3277d46263fe3f0d3efa04476a4df`;
  установленный после точной проверки байт файл имеет SHA-256
  `d38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e`;
  установленный guard совпал с указанным выше SHA. Восемь адресных тестов
  прошли, включая fake-home install и повторный вызов без изменения файлов;
  два установленных Python-файла прошли read-only AST parse. Резервная копия
  прежнего sender с исходным SHA сохранена в ignored
  `.runtime/m2-send-results-guard-install/0cda3129365743cfb369473dcc7cb596/send_result.before.py`.
  Первая реальная попытка остановилась до замены: `git apply` в staging
  упёрся в Git dubious ownership; отказ не обходили. Установщик изменён на
  точное применение двух вставок с проверкой итогового SHA; перед повтором
  подтверждено, что installed sender остался прежним, а guard отсутствовал.
  После установки readback трёх хэшей прошёл. `py_compile` не смог записать
  `__pycache__` вне workspace; вместо него синтаксис проверен без записи.
  Положительный live bridge/notifier smoke и rollback всё ещё не доказаны.
  Для будущего Windows checkout `.gitattributes` теперь фиксирует `eol=lf`
  ровно для SHA-bound guard и patch. Перед staging проверить оба source SHA
  и Git index `i/lf`; изменение атрибутов не переустанавливает skill.

## Исторический план до первого staging — не повторять буквально

Ниже зафиксирован план до failed journal на `fa6f1f0`. В текущем состоянии
его `--reconcile-complete-digest` неприменим; действует только верхнее
обновление с новым точным разрешением и `--rebind-failed-digest`.

1. Завершить исходный код и документацию, зафиксировать один кандидат в этом
   worktree. Выполнить полный candidate-bound L1, независимый по методу L2 и
   adversarial L3. Проверить exact candidate tree, документацию и rollback.
2. Сохранить экспорт трёх Task XML, health launcher и текущего чистого
   checkout в ограниченном приватном контуре; не копировать credentials и
   незашифрованные SQLite. Сверить исходные хэши выше. Смену `telegram-live`
   производить только на проверенный local commit, без push/merge.
3. Установить игнорируемый `desktop-projects.local.json` в production
   checkout из проверенного локального каталога (10 фактически сохранённых
   проектов, текущий SHA-256
   `43e64029ec9a0e009555dcfab1faa0825ee4c003b90994a42f547be05d2eea2a`).
   Desktop UIA всё равно обязан подтверждать выбранный проект при создании;
   каталог не создаёт проекты. Не включать дополнительные artifact roots без
   отдельного явного перечня.
4. Штатным `Install-NobusSpaceBot.ps1` с `-ReplaceExisting -StageDisabled`
   и точными исходными digest staged заменить только main/Health definitions.
   Параметры: прежний StateRoot, VoiceModelDirectory, BackupRoot/Ownership,
   `-SemanticAdmission`, `-DesktopBridge`, точный
   `-DesktopProjectsFile`. Проверить, что оба задания остались Disabled и
   main action передаёт эти флаги supervisor.
   Предварительный `-WhatIf` из M2 worktree 24.09 вернул только ожидаемый
   ShouldProcess и exit 0 при точных старых main/Health XML и launcher SHA,
   текущем каталоге 10 проектов и исходных runtime/backup параметрах.
   Он ничего не установил; после переключения production checkout нужен
   повторный exact drift check для действительной операции.
5. Подготовить НОВЫЙ backup config `c6-backup-cycle-1` под новым именем в
   ТОЙ ЖЕ папке, где прежние config и `backup-cycle-state.dpapi`: journal
   привязан к `config.parent`, иначе точная сверка старого завершённого
   цикла не сработает. Не перезаписывать прежний config/journal. Связать
   новый application binding, точные staged main/Health signatures, прежние
   runtime/backup ownership и все обновлённые input evidence, включая
   `desktop-projects.local.json`.
   Штатно stage заменить Backup Task с exact старым digest и новым config
   digest; проверить все три Disabled и сам config через `load_config`.
   Одноразовый генератор в игнорируемой
   `.runtime/m2-desktop-release-20260924/prepare_backup_config.py`
   принимает только старый config/digest и signed journal digest,
   проверяет Disabled task signatures, создаёт новый файл через `O_EXCL`
   и вызывает штатный `load_config`. Его syntax check прошёл; на production
   он не запускался. Исходный config и journal не перезаписывать.
6. Проверить signed recovery history и выполнить только exact activation
   rebind с предыдущего latest event digest на новый binding. После readback
   выполнить один `run_telegram_backup_cycle.py --reconcile-complete-digest`
   с указанным выше journal digest и НОВЫМ config digest. Код под admission
   hold мигрирует только известную прежнюю DDL, создаёт новую VERIFIED
   backup generation и поднимает main/Health. Не запускать цикл без
   journal/config/Task readback и не повторять после неизвестного исхода.

## Stop / rollback

- Любой mismatch, неизвестный исход Task/Telegram, отсутствие владельца
  Desktop, неверный config/DDL, неготовый backup или readiness оставляет
  main/Health/Backup Disabled и admission hold. Сначала read-only выяснить
  фактическое состояние, не запускать «на всякий случай».
- Возврат только к точному старому Task XML + старому checkout и совместимой
  проверенной БД/backup; не восстанавливать старую копию поверх новых принятых
  Telegram effects. После первой новой задачи автоматический откат БД
  недопустим. Старый подписанный журнал и generations не удалять.
- Отдельные этапы: локальная реализация, code candidate, staged release,
  активный бот, D01–D17 live evidence, публикация и принятие владельцем.
  Успешный backup/readiness не доказывает Desktop-паритет и Telegram-доставку.
