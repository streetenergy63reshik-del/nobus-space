# 08. Эксплуатация Nobus Space

**14 сентября 2026, 14:02 МСК:** MVP1 `82003c03` принят, v1.0.2 опубликован. Read-only срез 13:57–13:59 МСК подтверждает READY прежнего runtime, но M1-S1 и 72-часовое наблюдение не завершены. Revisions `73ed1c9` и `19c9bf3` отклонены; новый protocol v3 остаётся локальным WIP до freeze/fixture/reviews. [Текущий статус](handoffs/CURRENT-STATUS.md) и [пакет M1-S1](gates/mvp1-maintenance/HANDOFF.md) содержат привязанные факты.

Этот документ содержит действующие процедуры. Прежние команды остановленных кандидатов и повторяющиеся июльские инструкции удалены из текущего текста; их история сохранена в Git и соответствующих Gate-пакетах. Подробный механизм защищённого резервирования и восстановления — [C6 OPERATIONS](gates/gate-c6-release/OPERATIONS.md).

## Действующий экземпляр

Telegram Bot и Mini App используют один Core, одну очередь, четыре SQLite БД и подтверждения доставки. Планировщик запускает supervisor с явными параметрами semantic admission, состояния, модели и backup ownership. Supervisor объединяет Core и reverse SSH в один Windows Job; действует один polling lease. HTTP 200 не доказывает выполнение задачи: отдельно проверяются приём, результат и файл.

Настроен профиль принятой ревизии: logon trigger владельца и legacy `RestartCount=10/PT1M` включены; `NobusSpaceBot-Health` и `NobusSpaceBot-Backup` включены. На срезе 14 сентября main Running с 03:31:05 МСК, один logical supervisor/Core/relay/listener и polling lease, local/public readiness PASS; Health LastTaskResult 0. Четыре БД healthy, 86 задач и 84 ACK receipts сохранены, queue пустая, delivery_unknown 0, reconciliation false; offset `375633467`, revision `43983`. Generation `daily-20260914T033039-58e82052c3f54d6da759caad4aaed41c` прошла binding, authentication, freshness и ciphertext checks; следующая плановая копия — 15 сентября, 03:30 МСК. Restore не запускался.

Реальный изолированный fixture показал: после normal action exit 23 Планировщик не выполнил ни одного из настроенных повторов. Поэтому `RestartCount/PT1M` считается существующей конфигурацией, но не работающим recovery-контрактом и не доказательством исчерпанного бюджета. Исторический первичный trigger остановок 10–13 сентября остаётся `UNKNOWN`.

Рабочая копия `Code/worktrees/telegram-live` содержит активный код; состояние и резервирование находятся в приватной `Code/nobus-orchestrator-dev/.runtime/production-c6`. Python берётся из канонического `.venv`. Модель ASR пока находится в сохранённой копии C2; удалять этот каталог нельзя. Полные роли каталогов: [WORKSPACE-INVENTORY](handoffs/WORKSPACE-INVENTORY.md).

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

В принятом v1.0.2 Health не создаёт второй runtime, а legacy Scheduler retries не считаются recovery. Текущий maintenance WIP переносит ограниченные повторы внутрь одного Scheduler action: максимум 10 retries через 60 секунд, только для exact allowlisted transient outcome и после proven cleanup; permanent, `UNKNOWN`, invalid/missing Core outcome, повреждённая evidence history или exhaustion дают typed STOP. Две frozen revisions отклонены. До PASS real three-case Scheduler fixture, L1/L2/L3, publication и activation это TARGET, а не действующее поведение.

Перед первой активацией protocol v3 оператор при остановленном runtime передаёт полный тот же набор параметров, что установлен в main action:

```text
--initialize-recovery --semantic-admission
--runtime-root <exact StateRoot>
--voice-model-directory <exact model directory>
--backup-root <exact BackupRoot> --backup-ownership <exact digest>
--health-launcher <exact generated LIVE launcher>
--scheduler-task-name NobusSpaceBot
```

Эта команда выполняется под production mutex только после установки точных main/health/backup task signatures. Для read-only `--inspect-recovery` и digest-bound `--acknowledge-recovery-stop` нужен тот же полный activation input. Отсутствующая, неполная, invalid или другая binding блокирует запуск. Незавершённый `starting/control/wait` остаётся STOP/UNKNOWN; reset допустим только после сверки данных и внешних effects и сам runtime не запускает.

V3 history находится в `<StateRoot>/supervisor-control`. Каждая запись аутентифицирована DPAPI текущего Windows owner, связана digest-chain и проходит строгую transition/terminal matrix; checkpoint допустим только вторым record физического `.previous`. Current+previous ограничены 1 MiB, fixed operator logs — 5 MiB. Отдельный CLI fallback current+previous ограничен 128 KiB и не содержит argv/env/payload/path. Потеря сегмента, reparse, hardlink, oversize/extra/invalid file, parser/write/fsync/control failure не открывают новую серию. Exit 70–78 различают control, evidence, composition, binding, busy/reset/history STOP. In-place restore четырёх БД сохраняет control directory; реконструированный StateRoot без него остаётся STOP до сверки и нового bootstrap. Удалять историю для сброса бюджета нельзя.

Activation binding включает document 11 и local configs, Mini App assets, semantic flag, voice inventory, BackupRoot/ownership, installed Python/distributions/requirements, health launcher и фактические signatures main/health/backup. Изменение любого элемента требует нового candidate binding. Windows owner является control authority: DPAPI защищает от другого пользователя и offline-подделки; произвольный код того же owner уже эквивалентен компрометации StateRoot/БД. Core/relay не имеют reset-команды, а недоверенные workers остаются в существующей sandbox/Job-изоляции.

## Резервирование и восстановление

Четыре БД: `business-notes.sqlite3`, `task-runtime.sqlite3`, `telegram-checkpoint.sqlite3`, `telegram-state.sqlite3`. TXT в папке результатов — восстанавливаемая проекция; исходные bytes сохраняются в Core/outbox. DPAPI защищает копию текущим пользователем Windows, а manifest связывает source, code/schema, root и все члены комплекта.

9 сентября на действующем e3fbaf9 проверены полный изолированный цикл восстановления за 274,891 секунды и настоящий цикл Планировщика за 126,86 секунды. Проверены расшифрование и целостность четырёх БД, `LastTaskResult=0`, новый единственный runtime и неизменные задачи/доставки. Эти результаты относятся к своей версии и не переименовываются после обновления.

Принятые цели: RPO ≤24 ч, RTO ≤30 мин; копия ежедневно 03:30 МСК и перед изменениями; хранение 7 daily / 4 weekly. Обязательный post-accept backup на 82003c03 завершён: четыре БД проверены, задачи/доставки/offset сохранены, вернулся единственный runtime. Историческое полное восстановление не переименовывается в запуск новой версии; новые связанные копии и изменённый native-путь проверены отдельно.

Managed backup удерживает admission, останавливает точные main/health, создаёт и проверяет поколение, затем разрешает один запуск. Retention перемещает только доказанно принадлежащие циклу устаревшие поколения в карантин; произвольного удаления нет. Предел управляемого корня — 64 поколения и 2 ГиБ. Неизвестные, изменённые или linked файлы требуют оператора.

Restore всегда требует точных manifest, target binding и согласования записей/эффектов после снимка. Восстановление сначала проверяется в отдельном каталоге. Существующие новые accepted tasks и receipts нельзя заменить старой копией. После restore прежние сессии и подтверждения не возрождаются; admission остаётся закрыт до аутентифицированной сверки. Автоматического live restore или отката данных нет.

## Наблюдение M1-S1

После успешной активации T0 фиксируется по exact deployed commit и authenticated control history. Heartbeat этой же задачи каждые 30 минут выполняет только read-only проверки Scheduler, history/fallback, local/public readiness, exact supervisor/Core/relay/listener/lease, DB counters и backup manifests. Он не запускает, не перезапускает, не сбрасывает и не восстанавливает runtime автоматически.

PASS требует непрерывных 72 часов включённого ПК и owner session, минимум двух daily backup с LastTaskResult 0 и повторной authentication/binding/ciphertext проверкой, одного runtime, сохранности tasks/receipts/offset и отсутствия необъяснённых terminal events. Промежуток без проверяемого наблюдения более 60 минут начинает окно заново. Старый 15-минутный smoke не засчитывается.

## Очистка и ограничения

Очистка проекта не затрагивает активные состояние, модель, окружение, credentials, полученные владельцем файлы и резервные копии. Устаревшие checkout удаляются только после сохранения Git refs, уникального WIP и непубликуемых данных с проверкой восстановления. Reparse points и вложенные worktrees проверяются отдельно. Прежние FAIL и зафиксированные доказательства остаются в истории.

Копии на том же ПК не защищают от потери диска или учётной записи DPAPI. При выключенном ПК продукт недоступен; независимого оповещения о потере всего ПК нет. Пятнадцать минут наблюдения не доказывают многосуточную устойчивость.
