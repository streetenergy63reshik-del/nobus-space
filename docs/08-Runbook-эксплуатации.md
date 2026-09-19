# 08. Эксплуатация Nobus Space

**16 сентября 2026:** релиз v1.0.2 сохранён. Maintenance source/deployed `0bd63db`, merge/main `26860ad`: 210 PASS, реальный three-case Scheduler fixture и L1/L2/L3 PASS; квалификация text/TXT PASS. Закрепление Python и текущее состояние runtime/72-часового наблюдения отражаются в [CURRENT](handoffs/CURRENT-STATUS.md) и [M1-S1](gates/mvp1-maintenance/HANDOFF.md). Исторические pending не являются текущими блокерами.

Этот документ содержит действующие процедуры. Прежние команды остановленных кандидатов и повторяющиеся июльские инструкции удалены из текущего текста; их история сохранена в Git и соответствующих Gate-пакетах. Подробный механизм защищённого резервирования и восстановления — [C6 OPERATIONS](gates/gate-c6-release/OPERATIONS.md).

## Действующий экземпляр

Telegram Bot и Mini App используют один Core, одну очередь, четыре SQLite БД и подтверждения доставки. Планировщик запускает supervisor с явными параметрами semantic admission, состояния, модели и backup ownership. Supervisor объединяет Core и reverse SSH в один Windows Job; действует один polling lease. HTTP 200 не доказывает выполнение задачи: отдельно проверяются приём, результат и файл.

Профиль принятого maintenance: logon trigger владельца, один supervisor action с внутренним ограниченным recovery; Scheduler restart у main/health равен 0. Health выполняет только наблюдение; backup назначен ежедневно на03:30 МСК. Enabled/Running и последняя квитанция каждого задания читаются при проверке, а не выводятся из расписания. В срезе16.09 до закрепления Python сохранены87 tasks/85 receipts/16 confirmed parts; это не предел новых задач. Актуальные offset, lease, generation и причины завершений находятся в EVIDENCE M1-S1.

Реальный изолированный fixture показал: после normal action exit 23 Планировщик не выполнил ни одного из настроенных повторов. Поэтому `RestartCount/PT1M` считается существующей конфигурацией, но не работающим recovery-контрактом и не доказательством исчерпанного бюджета. Исторический первичный trigger остановок 10–14 сентября остаётся `UNKNOWN`.

Рабочая копия `Code/worktrees/telegram-live` содержит активный код; состояние и резервирование находятся в приватной `Code/nobus-orchestrator-dev/.runtime/production-c6`. Задания используют канонический `.venv/Scripts/python[w].exe`. Базовый Python для этой `.venv` закреплён отдельно: canonical `.runtime/production-python/cpython-3.12.14-ed91bed4/base`. Это точная офлайн-копия нынешней3.12.14, не обновление пакетов; `include-system-site-packages=false`. Кэш Codex не является production runtime. Модель ASR пока находится в сохранённой копии C2; удалять этот каталог нельзя. [Роли каталогов](handoffs/WORKSPACE-INVENTORY.md).

## Проверка без изменения состояния

Из существующей Windows-сессии владельца можно прочитать задания Планировщика и выполнить `scripts/run_nobus_space_live.py --check-ready` из LIVE с Python принятого окружения. Ключ проверяет точную локальную и публичную readiness; он не запускает ещё один Core. `scripts/check_telegram_health.py --runtime <точный StateRoot> --details` проверяет хранилище и безопасные операционные счётчики. Версию кода следует брать из `git -C <LIVE> rev-parse HEAD`, а не из старого тега или корневой рабочей копии.

| Наблюдение | Действие |
|---|---|
| Mini App не знает исход отправки | «Проверить приём»; дождаться сохранённого исхода. При подтверждённом непринятии можно завершить отправку и создать новую. |
| Истекла Telegram-сессия | Закрыть Mini App и открыть заново из Telegram; прежнюю задачу найти в списке. |
| Semantic недоступен | Показать типизированную причину и не выдавать техническую readiness за готовность приёма. |
| Результат есть, доставка неизвестна | Сверить подтверждения частей и внешний факт; не отправлять ответ или TXT повторно вслепую. |
| Копия старше 24 ч, недостоверна или диск <256 МиБ | Приём закрывается. Проверить binding и выполнить согласованную копию; не удалять историю ради PASS. |
| БД достигла 36 МиБ | Принять решение о ёмкости до предела 48 МиБ на БД. |
| Два poller, чужой процесс или неясная остановка | Остановить затронутую операцию, сохранить доказательства и выяснить владельца процесса. Не завершать все python/ssh по имени. |

`/status` различает Core, смысловой приём, исполнителя/ASR, неразрешённые заявки и историю. 31 историческая failed-задача не означает 31 новый сбой. В поддержку передаются время, версия, безопасный код/этап и отпечаток запроса; raw payload, токены, cookies, аудио и credentials не выводятся.

## Остановка, обновление и запуск

Обновление выполняется по одному точному плану с проверенным опубликованным SHA, runtime inputs, schema, конфигурацией, заданиями и бюджетом. Сначала проверяются текущие данные и создаётся свежая аутентифицированная копия. Новая заявка после подготовки плана обновляет базу сверки; её не удаляют.

Штатный `scripts/run_nobus_space_live.py --stop` только запрашивает остановку собственного supervisor. Core завершает приём и cleanup/checkpoints в пределах 90 секунд, затем supervisor закрывает Job и проверяет дерево. До checkout должны быть доказаны завершение собственных процессов, свободный порт и mutex. Принятые задачи, receipts и offset сверяются до и после. Неизвестный исход не превращается в разрешение на повтор.

При подтверждённом STOP переключается чистый LIVE; новая версия проверяет прежние БД и создаёт новую связанную копию. Затем запускается ровно один экземпляр и проверяются Job, lease, local/public/stock readiness и относящийся к изменению сценарий. Ошибка оставляет безопасную остановку и доказательства; прежние одноразовые operators и использованные intent нельзя проигрывать заново.

В принятом maintenance `0bd63db` Health не создаёт второй runtime. Ограниченные повторы выполняются внутри одного Scheduler action: максимум10 retries через60 секунд, только для exact allowlisted transient outcome и после proven cleanup; permanent, `UNKNOWN`, invalid/missing или противоречащий exit code Core outcome, повреждённая evidence history или exhaustion дают typed STOP. Этот механизм проверен реальным three-case Scheduler fixture `613682de7d1243ffb3ee3ed9c08f11fd` и независимыми L1/L2/L3 именно принятой ревизии. Отклонённые предыдущие кандидаты остаются историей.

Перед первой активацией protocol v3 оператор при остановленном runtime передаёт полный тот же набор параметров, что установлен в main action:

```text
--initialize-recovery --semantic-admission
--runtime-root <exact StateRoot>
--voice-model-directory <exact model directory>
--backup-root <exact BackupRoot> --backup-ownership <exact digest>
--health-launcher <exact generated LIVE launcher>
--scheduler-task-name NobusSpaceBot
```

Эта команда выполняется под production mutex только после установки и readback точных main/health/backup task signatures. Binding включает канонический SID principal, identity/time триггеров, действия и влияющие settings: demand/hard-terminate, compatibility, priority, idle/network, delay/random delay, unified engine, volatile и maintenance. Main/health имеют Scheduler restart `0`; backup — daily 03:30 по локальному часовому поясу. Для read-only `--inspect-recovery` и digest-bound `--acknowledge-recovery-stop` нужен тот же полный activation input. Отсутствующая, неполная, invalid или другая binding блокирует запуск. Незавершённый `starting/control/wait` остаётся STOP/UNKNOWN; reset допустим только после сверки данных и внешних effects и сам runtime не запускает.

V3 history находится в `<StateRoot>/supervisor-control`. Каждая запись аутентифицирована DPAPI текущего Windows owner, связана digest-chain и проходит строгую transition/terminal matrix; checkpoint допустим только вторым record физического `.previous`. Current+previous ограничены 1 MiB, fixed operator logs — 5 MiB. Отдельный CLI fallback current+previous ограничен 128 KiB и не содержит argv/env/payload/path. Bounded recovery latch ≤2048 bytes отдельно аутентифицирован DPAPI и сохраняет pre-control отказ записи: новая серия блокируется, пока оператор не сверит состояние, не материализует latch в точный `control_failure` и не выполнит digest-bound acknowledgement. Потеря сегмента, latch, reparse, hardlink, oversize/extra/invalid file, parser/write/fsync/control failure не открывают новую серию. Только exact authenticated latch с прежним anchor позволяет owner acknowledge прерванного zero/partial current или фиксированного bounded .compact staging; complete .compact дополнительно проверяется по bootstrap/checkpoint semantics. Inspect ничего не удаляет. Полный invalid artifact, mismatch или отсутствие latch сохраняют STOP. Exit 70–80 отдельно обозначают create/signal/close/evidence/composition/binding/busy/reset/history/startup/rebind STOP. Новый activation binding v3 включает exact main/health/backup task profiles и candidate-bound backup config; смена проверенной конфигурации требует exact authenticated rebind, а не удаления истории. In-place restore четырёх БД сохраняет control directory; реконструированный StateRoot без него остаётся STOP до сверки и нового bootstrap.

До первой production mutation Gate operator сохраняет exact XML main/health/backup, старые config и launcher bytes в приватный rollback-каталог через CreateNew, flush/fsync, SHA-256 и readback. Backup installer лишь сверяет old XML digest; backup XML сохраняет Gate operator. Bot installer дополнительно сохраняет main/health XML и launcher. После admission hold, штатного STOP и доказанного отсутствия exact процессов/Job/lease/listener отключаются только эти три задачи. Installers с `-ReplaceExisting -StageDisabled` проверяют old digests и читают обратно disabled profile; промежуточный отказ оставляет задания отключёнными. Staged backup получает ближайшие будущие 03:30. Initialize/rebind/inspect/acknowledge принимают все три disabled задания с теми же signatures под production mutex; обычный run отклоняет disabled profile. После exact readback и initialize/rebind задания включаются и контролируемо запускается candidate-bound backup cycle: hold до generation, повторной binding/STOP-проверки и authenticated `restart_permitted`, затем `permit_admission → Enable/Start main → local/public readiness → Enable health`. При startup приём уже разрешён; сверка сохранности учитывает все новые accepted tasks/receipts/offset. Ошибка start/readiness возвращает hold и scoped cleanup; внешняя ошибка baseline-сверки требует той же безопасной остановки. Fresh LIVE inputs обязательны. Возврат code/config/task bytes — по решению владельца; БД поверх новых accepted tasks не откатываются.

Activation binding включает document 11 и local configs, Mini App assets, semantic flag, voice inventory, BackupRoot/ownership, installed Python/distributions/requirements, health launcher и фактические signatures main/health/backup. Изменение любого элемента требует нового candidate binding. Windows owner является control authority: DPAPI защищает от другого пользователя и offline-подделки; произвольный код того же owner уже эквивалентен компрометации StateRoot/БД. Core/relay не имеют reset-команды, а недоверенные workers остаются в существующей sandbox/Job-изоляции.

## Резервирование и восстановление

### Закреплённый Python

Замена базового `pythonw.exe` в кэше Codex изменила activation binding и заблокировала restart после backup16.09. При подготовке изолированной копии проверены12182 файла/443809639байт, Authenticode и запуск stdlib/native модулей. Копия не использует symlink/hardlink на кэш. `pyvenv.cfg` указывает на production-каталог; прежний файл сохранён рядом с inventory в `rollback/pyvenv.cfg`. Точные квитанции и результаты перехода — `EVIDENCE.python_pinning_20260916`.

Не выполнять `venv --upgrade`, переустановку или обновление production-пакетов из bundled Codex runtime. Следующее обновление Python — отдельный точный переход: offline staging/version/hash/signature/inventory → проверки зависимостей → свежая проверенная копия → admission hold → штатный STOP/cleanup → сохранение исходного cfg → переключение → проверка фактического `sys.base_prefix`, search path и activation binding под **pythonw владельца** → штатный backup/start → сохранность/readiness. Пауза ограничена20 минутами. Console и windowed executable имеют разные bytes: проверку production binding не подменять console identity.

При побайтово одинаковой копии текущая activation binding остаётся прежней; rebind/reset не выполнять только из-за нового пути base. При реальном изменении связанного содержимого нужен точный разрешённый rebind от authenticated history head после сверки effects. Историю не удалять. Rollback cfg возможен только после проверки совместимости, штатного STOP и точного разрешения; БД не откатывать. Само наличие старого cfg не гарантирует, что изменяемый кэш всё ещё содержит прежние bytes.

Четыре БД: `business-notes.sqlite3`, `task-runtime.sqlite3`, `telegram-checkpoint.sqlite3`, `telegram-state.sqlite3`. TXT в папке результатов — восстанавливаемая проекция; исходные bytes сохраняются в Core/outbox. DPAPI защищает копию текущим пользователем Windows, а manifest связывает source, code/schema, root и все члены комплекта.

9 сентября на действующем e3fbaf9 проверены полный изолированный цикл восстановления за 274,891 секунды и настоящий цикл Планировщика за 126,86 секунды. Проверены расшифрование и целостность четырёх БД, `LastTaskResult=0`, новый единственный runtime и неизменные задачи/доставки. Эти результаты относятся к своей версии и не переименовываются после обновления.

Принятые цели: RPO ≤24 ч, RTO ≤30 мин; копия ежедневно 03:30 МСК и перед изменениями; хранение 7 daily / 4 weekly. Обязательный post-accept backup на 82003c03 завершён: четыре БД проверены, задачи/доставки/offset сохранены, вернулся единственный runtime. Историческое полное восстановление не переименовывается в запуск новой версии; новые связанные копии и изменённый native-путь проверены отдельно.

Managed backup удерживает admission, останавливает точные main/health, создаёт и проверяет поколение, затем разрешает один запуск. Во время этой узкой транзакции health может оставаться disabled только при свежей аутентифицированной candidate-bound journal-фазе `restart_permitted` или `starting`; это исключение не разрешает обычный запуск с disabled health. Retention перемещает только доказанно принадлежащие циклу устаревшие поколения в карантин; произвольного удаления нет. Предел управляемого корня — 64 поколения и 2 ГиБ. Неизвестные, изменённые или linked файлы требуют оператора.

Restore всегда требует точных manifest, target binding и согласования записей/эффектов после снимка. Восстановление сначала проверяется в отдельном каталоге. Существующие новые accepted tasks и receipts нельзя заменить старой копией. После restore прежние сессии и подтверждения не возрождаются; admission остаётся закрыт до аутентифицированной сверки. Автоматического live restore или отката данных нет.

## Наблюдение M1-S1

После успешной активации T0 фиксируется по exact deployed commit и authenticated control history. Heartbeat этой же задачи каждые 30 минут выполняет только read-only проверки Scheduler, history/fallback, local/public readiness, exact supervisor/Core/relay/listener/lease, DB counters и backup manifests. Он не запускает, не перезапускает, не сбрасывает и не восстанавливает runtime автоматически.

PASS требует непрерывных 72 часов включённого ПК и owner session, минимум двух daily backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой, одного runtime, сохранности tasks/receipts/offset и отсутствия необъяснённых terminal events. Промежуток без проверяемого наблюдения более 60 минут начинает окно заново. Старый 15-минутный smoke не засчитывается.

## Очистка и ограничения

Очистка проекта не затрагивает активные состояние, модель, окружение, credentials, полученные владельцем файлы и резервные копии. Устаревшие checkout удаляются только после сохранения Git refs, уникального WIP и непубликуемых данных с проверкой восстановления. Reparse points и вложенные worktrees проверяются отдельно. Прежние FAIL и зафиксированные доказательства остаются в истории.

Копии на том же ПК не защищают от потери диска или учётной записи DPAPI. При выключенном ПК продукт недоступен; независимого оповещения о потере всего ПК нет. Пятнадцать минут наблюдения не доказывают многосуточную устойчивость.
