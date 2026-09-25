# M2-DESKTOP: план контролируемого выпуска

Статус: production release PREPARED, не исполнен; отдельно подтверждённое
обновление skill `nobus-send-results` исполнено. Этот документ не является разрешением
запускать старый Telegram request `e18a5ca3-95d3-4be8-8453-630d88e97a50`
или считать Gate принятым. Точные значения ниже сняты 24.09.2026;
перед любым изменением повторно сверить drift только у затрагиваемых целей.

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

## До production activation

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
