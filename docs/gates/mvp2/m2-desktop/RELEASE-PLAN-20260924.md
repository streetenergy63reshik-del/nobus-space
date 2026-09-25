# M2-DESKTOP: план контролируемого выпуска

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
