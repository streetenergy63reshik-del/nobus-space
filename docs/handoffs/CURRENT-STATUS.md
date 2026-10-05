# Nobus Space: текущий статус и опубликованные версии

Плиточное меню Codex и его backup-миграция находятся в
`codex/m2-desktop`; работающий экземпляр их ещё не использует.
Новый исходник проверяется на отдельном снимке. Подтверждённые
результаты ручных D02–D17 не получены; Gate и MVP2 не приняты.

## Production перед выпуском меню — 5 октября 2026

Работающий LIVE остаётся чистым на `4db5f0e9266637feca408a57aa0c8e8ac580dbc0`.
После [ночного STOP с HTTP 503](../incidents/2026-10-05-readiness-503-stop.md)
штатное восстановление к 08:13 МСК подтвердило Main Running, два завершённых
Health 0, local/public HTTP 200, полные БД/effects PASS, сохранность 89 задач
и 20 частей доставки, complete/VERIFIED backup и hold=false. Первопричина
нового отказа неизвестна; это не доказательство его устранения. Read-only
проверка перед подготовкой выпуска снова увидела Main Running и local `/readyz`
HTTP 200. [Остановка 4 октября](../incidents/2026-10-04-readiness-stop.md)
была отдельным deadline-событием. Текущий кандидат плиточного меню находится
в `codex/m2-desktop` и ещё не переключён в LIVE; D02–D17 остаются за владельцем,
Gate/MVP2 не приняты.

## Production Nobus Space Bot — 3 октября 2026, 17:35 МСК

Наблюдаемый LIVE — чистый `4db5f0e9266637feca408a57aa0c8e8ac580dbc0`. Main Running; Health и Backup Enabled/Ready, последний Health — 0 в 17:35. Local/public readiness: HTTP 200 с точным телом за 218/797 мс при действующих deadlines 5/10 с. Одна активная polling lease; цепочка supervisor/Core/relay и один listener Core отдельно подтверждены в 17:46 МСК. Четыре БД PASS; 89 задач, 20 подтверждённых частей доставки, pending/leased/unknown/failed — 0, очередь пуста. Подлинный backup `complete` от 12:44:12, поколение VERIFIED, admission hold=false. [Датированная read-only проверка](../incidents/System/2026-10-03-documentation-observation.json).

Сегодня после некорректного перезапуска Windows выполнено штатное восстановление, затем установлен проверенный эксплуатационный ремонт: строгая классификация штатных обрывов OpenSSH и перенос idle SQLite операций с потока Core с безопасным завершением транзакций и lease при отмене. [Журнал 16 аварийных завершений за 20.09–03.10 и выполненные мероприятия](../incidents/2026-10-03-production-stability-14d.md), [доказательство выпуска](../incidents/System/2026-10-03-stability-release.json). Первопричины прежних SSH exit 255, конкретной задержки 95 с и перезапуска Windows остаются UNKNOWN. Проверка работы не доказывает многосуточную устойчивость.

GitHub и LIVE пока различаются: опубликованный код `main` — ремонт от 20 сентября; исходник установленного LIVE хранится в локальной ветке `codex/nobus-production-stability-20261003`. Эта публикация содержит только документацию и обезличенные доказательства. История Desktop bridge и новый runtime-код не включаются в документный PR. LIVE нельзя переключать на docs-only HEAD без нового application binding. [Передача и границы следующего изменения](ARCHITECT-HANDOFF.md).

Монитор 08:00/22:00 МСК активен. Историческая приёмка MVP1 от 19 сентября остаётся отдельной. Установленные Desktop bridge аргументы сохранены; их наличие не означает принятия всего M2-DESKTOP Gate. Старые планы MVP2 не запускаются этим обновлением.

## M2-DESKTOP: плиточное меню Codex в WIP — 4 октября

По read-only сверке работающий live checkout чистый на `4db5f0e9266637feca408a57aa0c8e8ac580dbc0`
(исправление стабильности 03.10 после `bd991`); Main Running,
Backup/Health Ready, локальный `/readyz` с точным Host вернул HTTP 200
и `{"status":"ready"}`. Новый маршрут `/codex` с плитками проектов/задач,
пустым вводом промта, «Назад» и bot-to-bot ответом по номеру реализован в
рабочем M2 checkout и объединён с `4db5f0e`; live на новом коде ещё не
переключён. Исправлена обязательная проверка токенов плиток в общем Telegram
gateway. Последняя проверка затронутых модулей: `407 passed`; ранее один
Git-fixture отказал только из-за длинного тестового пути и прошёл
отдельно в коротком `%TEMP%`. Живой Desktop IPC и список
11 локальных проектов/11 задач Nobus Space прочитаны без отправки turn.
Новая спецификация: [M2-DESKTOP-TILE-MENU](../gates/mvp2/M2-DESKTOP-TILE-MENU.md).
D02–D17 владелец по-прежнему не проходил; Gate/MVP2 не приняты.
Следующий абзац описывает прежнюю дату, а не текущий live SHA.

## M2-DESKTOP: восстановлен после STOP — 29 сентября, 08:55 МСК

Live/source остаются на `bd991760312732dd15cdad909e81a6023cc703f2`.
28 сентября после `public_readiness_failed` повторный запуск получил
`telegram_unavailable`, и подписанная защита оставила Main/Health Disabled.
Ночной backup создал VERIFIED generation, но не восстановил ready.
29 сентября после сверки истории, сети, БД и копии выполнены один exact
STOP reset и один recovery по failed-journal digest. Новая проверенная
generation `daily-20260929T085111-deeac3d9f6824ee89466d04829bc677b`;
Main Running, Main/Health/Backup Enabled, local/public HTTP 200 с точным
ready-body, Health PASS в 08:53 и 08:54 МСК. Код и L1–L3 не менялись;
D02–D17 владелец ещё не проходил. Точный внешний первичный сбой не доказан,
следующий плановый Backup 30 сентября ещё не проверен. Подробности — в
[handoff](../gates/mvp2/m2-desktop/HANDOFF.md) и
[карте ручной приёмки](../gates/mvp2/M2-DESKTOP-MANUAL-ACCEPTANCE.md).

## M2-DESKTOP: готово к ручной приёмке — 27 сентября, 18:20 МСК

Текущий source/live `bd991760312732dd15cdad909e81a6023cc703f2`, tree
`69dae321773812fd3d2a96004ae86f6ee3e3812b`. L1: 2939 passed,
3 skipped, 5 исторических deselections; L2 на независимом чистом clone:
589 passed, 1 skipped; L3 адресная проверка изменений. Main работает,
Main/Health/Backup включены, local/public readiness и Health PASS;
подписанный backup complete/VERIFIED. Старый D03 завершённый turn доставлен
без повторного исполнения. Точные данные для владельца — в
[инструкции D02–D17](../gates/mvp2/M2-DESKTOP-MANUAL-ACCEPTANCE.md) и
[handoff](../gates/mvp2/m2-desktop/HANDOFF.md). **Это READY_FOR_MANUAL_ACCEPTANCE,
не принятый MVP2:** результаты D02–D17 ещё не получены, PR/merge/release
не завершены. Нижеследующие даты — исторические checkpoints.

## M2-DESKTOP: локальный кодовый кандидат прошёл L1/L2/L3 — 27 сентября, 10:34

Точный frozen source commit `c6f6858ea1693ea046130a97061fe8fd5f589e47`,
tree `630ef35e7648cf828d2da5cb6aad15f408644d21`. L1:
`2935 passed, 3 skipped, 5` старых исключений; L2 на независимом чистом
Git clone: `406 passed, 1 skipped`; L3 по изменённым опасным границам
без нового блокирующего дефекта. Статический отчёт классифицирован;
отдельный CVE-аудит не проводился. Это локальная проверка кода, а не
завершение D16: обязательные реальные D02–D17, восстановление production
и выпуск открыты. Production последней подтверждённой сверки остаётся
чистым `fd4d66c`, Main/Health/Backup Disabled, admission hold и signed
STOP; завершённый D03 Desktop-turn не повторять. Послезаморозочные
доказательства [в handoff](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: первый кандидат получил L1-отказ — 27 сентября, 10:05

Локальный frozen DRAFT `2355ae5e47f542ea7485ad509e8128f3d1b5b7db`
прошёл широкий L1 с результатом `2933 passed, 2 failed, 3 skipped,
5` прежних исторических deselections и `25 subtests passed`.
Оба отказа — один дефект `isinstance` в readiness-dispatch при
внедрённой тестовой фабрике. Адресное исправление в WIP дало
`7 passed`; первый SHA не объявляется проверенным, L2/L3 по нему не
начинались. Следующий локальный шаг — новая заморозка и полный
candidate-bound L1/L2/L3. Production не менялся: чистый `fd4d66c`,
Main/Health/Backup Disabled, admission hold и signed STOP. D03 Desktop
turn завершён, но Telegram delivery не было; повторять ход нельзя.
[Передача](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: источник DRAFT подготовлен к заморозке — 27 сентября, 09:43

В этой задаче владелец поручил заморозить один локальный кандидат и
провести L1–L3; production, Telegram и Desktop live-действия этим шагом
не выполняются. Предзаморозочная проверка bridge+документации дала
`68 passed` и один отказ тестового Git worktree под длинным кириллическим
pytest path (`$GIT_DIR too big`); ровно этот тест прошёл в новом коротком
temp. Исходный каталог сохранён. Источник готов к локальному commit,
точный SHA/tree будет установлен после него. D01 доставлен ранее,
D03 Desktop turn завершён, но ещё не доставлен; D02–D17 открыты.
Production по-прежнему чистый `fd4d66c` и остановлен после backup,
три Scheduled Tasks Disabled; Gate не принят.
[Передача](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: локальный backup/recovery WIP, без выпуска — 27 сентября, 09:21

Владелец разрешил в этой сессии только узкую проверку временных файлов
в новых тестовых каталогах и локальную доработку backup/readiness;
заморозка кандидата, независимая проверка, выпуск и живые D02–D17
отложены на следующий запуск. FileSystemWatcher классифицировал 58
событий внутри нового test root (50 SQLite temp, 4 pytest, 4 исходных
имени при move; 3 отдельных Renamed). Исторический отрицательный счёт
59 без путей сохранён. Локальный WIP устранил успешный двухшаговый
rename-gap control-файлов через Windows `ReplaceFileW`, при неизвестном
исходе прекращает повтор journal; восстановление первого прерванного
backup и отказ при потере опубликованного pointer проверены. После
исправления найденной регрессии 36 зависимых backup-тестов, один новый
негативный тест и 6 адресных readiness-тестов прошли. Точный зависший
вызов при инциденте 26.09 не установлен, live-устойчивость не проверена.
Production остаётся остановленным на `fd4d66c`, все три Scheduled Tasks
Disabled, admission hold и signed STOP сохранены; D03 Desktop turn
завершён, но не доставлен, повторять его нельзя. Gate не принят.
[Передача](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: все задачи выключены после ночного backup — 27 сентября, 08:22

На чистом production `fd4d66c` включённый по прежнему расписанию Backup
запустился в 03:30, создал `VERIFIED` generation, но не восстановил Main:
подписанный cycle journal содержит `failed_operator_required`,
`restart_not_ready`, `admission_hold=true`. Main/Health уже были
`Disabled`; чтобы завтра не повторить старый цикл с `cleanup_staging()`
при запрете удаления файлов, idle Backup Task штатно выключен и проверен
как `Disabled`. Продукт сейчас не работает. D03 Desktop turn завершён,
Telegram-ответ не доставлен; его не повторять. В локальном WIP устранена
перезапись двух control-файлов и добавлен fail-closed для crash-gap, но
SQLite sidecars и восстановление после разрыва не закрыты,
поэтому выпуск и восстановление не разрешены. Подробности и точные
квитанции: [HANDOFF](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: no-delete проверка провалена, выпуск не выполнялся — 26 сентября, 22:47

Windows FileSystemWatcher зафиксировал 59 событий `Deleted` внутри нового
синтетического каталога за четыре зелёных backup-теста на локальном
`91a0499`. Пути событий не сохранены; на диске осталось 9 `.sqlite3`
без `-wal`/`-shm`. Значит, полное соблюдение прямого запрета удаления
не доказано и этот checkpoint **не допущен к production**. Тесты с
возможным повтором события прекращены. Production остаётся остановлен
на `fd4d66c`; завершённый Desktop turn D03 не повторять. Нужен
отдельно согласованный узкий режим обращения с временными файлами либо
доказанный маршрут без Delete; до этого backup/rebind/reset не запускать.
[Доказательства](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: no-delete backup проверен локально, production не выпущен — 26 сентября, после 22:40

Локальный checkpoint `91a0499c06567c9d5a9829190e2629aa26663661`
включает readiness fix и шифрованный SQLite backup без plaintext staging
и явного удаления файлов. На его чистом экспорте `15 passed` адресных
тестов; синтетический signed reconcile и два отказа дали ещё `3 passed`
на точной Git-привязке worktree. Отсутствие скрытого удаления SQLite
`-wal`/`-shm` при настоящем backup пока не доказано. **Production не
обновлялся**: он штатно остановлен на `fd4d66c`, signed head
`sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Завершённый Desktop turn D03 не доставлен и не должен повторяться.
Полный L1/L2/L3, выпуск и D02–D17 остаются открытыми.
[Передача](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: локальное исправление без выпуска — 26 сентября, 22:27

Checkpoint `133929f5ea153fc8d05a093200f9733045ac2293` (tree
`e2fd0887de00b85ce672eeb976dfddc7a63019f7`) вынес тяжёлые
readiness/Git/file-проверки с Core event loop; 11 адресных тестов прошли
в чистом экспорте. Точный зависший вызов при аварии не пойман, поэтому
живую устойчивость ещё нельзя считать доказанной. Production остаётся
**остановленным на `fd4d66c`** с signed head `sha256:1d1bf928…42d83`;
завершённый Desktop turn D03 не доставлен и не должен исполняться снова.
Штатный выпускной backup-цикл удаляет временные SQLite-файлы и hold-файл,
что противоречит действующему запрету удаления. Выпуск, reset и новые
Telegram-тесты не выполнялись; нужен проверенный no-delete путь backup.
[Подробности](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: продолжение в Desktop прошло, Main снова остановлен — 26 сентября, 21:51

Одна команда `continue` из «Заметок бизнеса» / «Codex work» создала
новый turn в **том же** Desktop thread; read-only IPC подтвердил точный
завершённый ответ `M2-CONTINUE-20260926-1`. До доставки снова возникли
три local/public readiness timeout; подписанный head после штатной
остановки `sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Main `Ready`/result `1`, bridge request `running`, delivery rows `0`.
Не повторять сообщение или Desktop-turn. Профиль здорового периода
выявил синхронную глубокую проверку в `/readyz`, но конкретный долгий
вызов во время остановки ещё не зафиксирован. Диагностическая правка и
два адресных теста — только WIP; D03 частично доказан, D02–D17 и Gate
не приняты. [Подробности](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: первый сквозной текстовый запрос доставлен — 26 сентября, 20:20

По точному подтверждению владельца выполнен один signed recovery reset
от `sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`
с новым event
`sha256:7d4bf41df20797f28f210e854d33f8102e629c6b97aa4cdeb81f5ff905e78c0a`
и один запуск существующего Main. Запрос `M2-LIVE-20260926-3` не
повторялся: ранее завершённый Desktop turn восстановлен по той же
привязке и доставлен в «Заметки бизнеса» / «Codex work» одним итогом
`M2-LIVE-20260926-3`, Telegram message ID `2306`. В исходной теме
визуально подтверждены точный текст, reply к исходному сообщению и
отсутствие дубля. Main `Running`, Health `Ready`/result `0`, local/public
readiness `PASS`. Простой текстовый D01 подтверждён; D02–D17 и Gate
не приняты. Причина предшествующего safety stop остаётся неустановленной.
[Подробности](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: Desktop-ход доказан, доставка остановлена safety guard — 26 сентября, 19:48

Один новый Telegram-запрос `M2-LIVE-20260926-3` создал реальную задачу
в установленном Codex Desktop и завершённый turn с точным ответом.
Bridge сохранил request `ae0183d9-669a-4cde-b81e-74d749cc6643` и
связанные thread/turn, но итог в Telegram не успел отправить: во время
создания задачи три local/public readiness-пробы истекли, подписанный
контроллер штатно остановил Main. Recovery head
`sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`;
Main `Ready`/LastTaskResult `1`. Для запроса delivery rows `0`;
повторять Telegram-сообщение или Desktop-ход нельзя. Адресный локальный
тест восстановления привязанного завершённого turn прошёл (`1 passed`).
Запрошено точное разрешение на один reset и запуск, но они ещё не
выполнены. Причина задержки Core пока неизвестна; D01–D17 не приняты.
Подробности — в [M2 handoff](../gates/mvp2/m2-desktop/HANDOFF.md).

## M2-DESKTOP: новый production fd4d66c работает, Gate ещё не принят — 26 сентября

После отдельного точного разрешения чистый production checkout переведён
с `cdc59a2` на `fd4d66cfccb66c29702c29f6df59d137d3c26e3b`.
Сохранены rollback-копии и ветка возврата; новый O_EXCL backup config
имеет digest `sha256:cb9af8931da6d9f0e896c208f6697845e6e7a23ecb12fa6501f9edb345c9d407`.
Один signed rebind и один `--reconcile-complete-digest` завершились
`PASS`; VERIFIED generation
`daily-20260926T191008-36e07f063a674ffcab3fa810defcfa98`,
новый signed complete journal
`sha256:3ceca795c3273a3802fa92fbc3b08c5d2fbdaa03a06dc78b3d0144e5f819b71a`.
Readback в 19:18 МСК: production clean, Main `Running`,
Health/Backup `Ready`, local/public readiness `PASS`. Это выпуск
исправления маршрута и UIA, **не** приёмка D01–D17. Новый Telegram-тест
после выпуска ещё не отправлен: пользователь остановил управление ПК
клавишей Escape до выбора окна. Проверка возобновлена по новому запросу.
Детали — в [M2 handoff](../gates/mvp2/m2-desktop/HANDOFF.md).

Вторая реальная команда `/codex new` была принята ботом, но UIA остановился
до создания задачи: установленный Desktop обновился до `26.924.2738.0`,
а production на `cdc59a2` привязан к `26.917.9434.0`. Запрос
`9202eece-cc7a-4e62-9d7c-e3b3f6d1e98d` удерживается в
`unknown_dispatch`, без автоматического повтора. Локально новый version pin
и ожидание проектного UIA-контекста проверены: отдельная проба создала
видимую Desktop-задачу, IPC подтвердил владельца, полный ответ и cwd;
`74 passed` затронутых тестов. Это ещё WIP, не production и не полная
Telegram-приёмка. Подробности — в [M2 handoff](../gates/mvp2/m2-desktop/HANDOFF.md).

Утренний запуск `cdc59a2` остановился в 10:34 после трёх local/public
readiness timeout; причина задержек не установлена. Отдельно разрешённый
однократный signed recovery reset и запуск Main в 18:05 вернули
local/public `PASS`; Main сейчас `Running`, Health/Backup `Ready`.
Одно реальное сообщение `M2-LIVE-20260926-1` получило ответ бота в 18:06,
но Desktop-задача не создана: reply к корню Telegram-темы ошибочно
выбрал продолжение вместо маршрута нового запроса. Локальное исправление
и затронутая регрессия (`292 passed`) есть только в WIP; production его
не содержит. Старое сообщение не повторять. Детали — в
[M2 handoff](../gates/mvp2/m2-desktop/HANDOFF.md).

По точному разрешению владельца production checkout чисто переведён на
проверенный `cdc59a2ebd5d228e062937625da209be6d652c4a`. После
rollback-снимка, нового привязанного backup config и однократного signed
rebind один восстановительный цикл завершился `PASS` с VERIFIED backup.
Подписанный журнал — `complete`, digest
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`.
Main `Running`, Health/Backup `Ready`; штатная local/public readiness —
`PASS`, Health last result `0`. Детали и точные квитанции — в
[M2 handoff](../gates/mvp2/m2-desktop/HANDOFF.md). Это активация кода,
не приёмка M2-DESKTOP: живые Telegram-сценарии D01–D17 ещё открыты.

## Исторический снимок 25 сентября: локальный кандидат `cdc59a2` ещё не активирован

Исправление несовпадения interpreter binding зафиксировано на точном
commit `cdc59a2ebd5d228e062937625da209be6d652c4a` (tree `0ac7807`).
Широкий L1: `2915 passed, 3 skipped, 5` прежних точных исторических
исключений; независимый чистый ZIP L2: `491 passed`; L3 проверил
консольный/оконный режимы и обе SHA-bound базы Python. Production checkout
по-прежнему `26b95e5`, бот и все три Tasks выключены, signed failed journal
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
Запрошено новое точное разрешение на выпуск `cdc59a2` и один подписанный
rebind/backup cycle. Это ещё не реальная Telegram-приёмка D01–D17.

## M2-DESKTOP: 25 сентября вечером production вновь остановлен

По новому точному разрешению Backup Task был включён, затем выполнен один
same-config recovery. VERIFIED backup создан, но Main вышел с кодом 78;
signed failed journal теперь
`sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
Admission hold и cleanup доказаны; после обратимого выключения Backup все
три Tasks Disabled, процессов нет. Telegram live-тестов не было.
Read-only диагностика доказала новую причину: rebind через `python.exe`
и Scheduled Task через `pythonw.exe` формировали разные activation digests
из-за `sys._base_executable`. Подписанная история исправна, latch нет.
Локальное исправление связывает оба базовых файла независимо от режима;
затронутая регрессия — `274 passed, 1 warning`. Новый код WIP,
не развёрнут и не принят; нужен один новый frozen кандидат с независимой
проверкой и отдельное точное разрешение на новый production commit.

## M2-DESKTOP: 25 сентября второй восстановительный запуск остановлен

Production checkout чисто переведён на локальный `26b95e5`, который
содержит проверенные code bytes `fe333c6`; rollback-снимок сохранён.
Новый backup config и определение Backup Task установлены, подписанный
recovery rebind прошёл. Один разрешённый цикл создал VERIFIED backup, но
Main не достиг readiness (exit 75). Новый signed failed journal:
`sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`,
`starting/restart_not_ready`, admission hold и cleanup подтверждены.
Все три Scheduled Tasks Disabled, Telegram-тестов не было. Read-only
диагностика локализовала новую причину: Backup Task оставался Disabled
при запуске Main, тогда как активация требует Enabled Backup. Цикл не
повторялся. Для продолжения нужно отдельно согласовать включение Backup
и один same-config recovery после точной сверки состояния; прежний
`--rebind-failed-digest` не повторять. Gate и D01–D17 не приняты.

## M2-DESKTOP: 25 сентября production staged, восстановление не завершено

Локальный code checkpoint `fe333c614e30340057acd917b592c2e36b62c574`
(tree `c016023e2b4b32a2403e2c50d312ddc905891730`) прошёл независимый
чистый ZIP-набор `225 passed` и широкий L1 `2915 passed, 3 skipped,
5 точно исторических deselected`; голосовой timing-тест включён и прошёл.
Read-only сверка после проверки: production checkout по-прежнему clean на
`fa6f1f0`, три Tasks Disabled, signed failed journal имеет прежний digest.
Это проверенный локальный кандидат кода, не активация и не приёмка D01–D17.
Для изменённых production bytes и одного подписанного recovery требуется
отдельное точное разрешение.

По точному разрешению владельца production checkout `telegram-live` переведён
на локальный `fa6f1f08c67968b63bf1d33bab8a2bbfae8217f8`, каталог проектов
и три Scheduled Tasks staged. Старый подписанный recovery head успешно
перепривязан; один согласованный backup reconciliation создал verified
generation, но Main не достиг readiness (`exit 75`). Подписанный журнал:
`failed_operator_required` на `starting`, admission hold и cleanup подтверждены;
все три задачи планировщика снова Disabled. Причина — проверка запуска в
`fa6f1f0` не принимает подписанное поле `reconciled_from_digest` нового
backup journal. Ни цикл, ни запуск не повторялись; Telegram-тестов не было.
Реальный MVP2 не активирован и D01–D17 не приняты.

В текущем WIP добавлены узкая поправка restart guard, сохранённое уточнение
неоднозначного create/continue и явный selector для ранее не связанной
выгруженной Desktop-задачи. Read-only UIA→IPC проверка такой задачи на
установленном Desktop подтвердила exact owner/thread/title/cwd без turn.
Для смены application binding после failed journal добавлена отдельная
строго проверяемая ветвь `--rebind-failed-digest`; она ещё не развёрнута.
Затронутая регрессия на неподвижных файлах: 225 тестов прошли;
`ops_queue1` теперь целиком проверяет действующие WhatIf и Health
(13 passed). Код ещё не заморожен и не установлен в production.
Неоднозначный `requestUserInput` без доверенного поля происхождения остаётся
точной границей R02: владелец согласовал ручной ответ в Desktop для такого
случая; живой цикл структурированных approvals остаётся обязательным.
Следующий безопасный шаг — единый проверенный кандидат
и отдельное разрешение на его конкретный commit и восстановление failed
backup journal; до этого бот остаётся выключен.

## M2-DESKTOP: 25 сентября ограниченно проверен owner recovery; production не активирован

Кодовый checkpoint `b8834aeedc7a7501bdc2049f8458ef025ab8c5ff`
устраняет конкретный сбой после выгрузки задачи из Desktop: если title
ранее подтверждён IPC, адаптер открывает один точный элемент через UIA без
ввода и повторно ищет owner исходного thread ID. Один live open-only опыт
дал exact owner, другой — не дал и оставлен отрицательным свидетельством;
ходов и Telegram не было. При неизвестном title/owner система ждёт ручного
открытия, не подменяет Desktop отдельным исполнителем. Локальный широкий
L1: `2904 passed, 3 skipped, 7 deselected`; чистый Git ZIP L2: `247 passed,
1 skipped`. Это не сквозная приёмка D01–D17. Production checkout остаётся
на `3ea2438`, все три Scheduled Tasks Disabled; backup/activation не
выполнялись. Предыдущая точная release-привязка `16f9029` устарела.

### Предыдущий checkpoint — исправление совместимости мигратора

После расширенного прогона на прежнем checkpoint `e5921b8`
(`2894 passed, 3 skipped, 13 failed` без исторического Gate 0) подтверждён
и адресно исправлен M2-индуцированный дефект сравнения двух допустимых DDL
вариантов в старом миграторе: commit `935d93037a94f63e9e63395d626ebdec11cff515`,
`tests/test_c6_migration.py`: `6 passed`. Три отказа C5/M1 прошли от имени
владельца файлов; остальные семь относятся к историческим fixtures старых
Gate и не менялись. После исправления широкий набор на `b8834ae` прошёл с
указанными выше исключениями. Живой бот не включался; release-хэши надо освежить
перед первым внешним действием. Gate остаётся WIP.

## Предыдущий code checkpoint 55297db

Commit `55297db440b502292159f2612c579f588e37c323` (tree
`e0cde457c7993791311a6e9249ddb6fb382626e3`) проверен в чистом
Git-экспорте: 14 связанных M2-файлов, `237 passed, 1 skipped`.
Это проверка исходного кода, не заморозка полного Gate и не приёмка
Telegram. Read-only сверка подтвердила, что все три production Scheduled
Tasks по-прежнему Disabled и их XML совпадает с планом выпуска; действующий
подписанный backup journal имеет `phase=complete`. Ни новый backup cycle,
ни staging, ни Telegram-запрос не запускались. Следующий рубеж — точная
привязка release-кандидата, независимая проверка и контролируемая живая
приёмка D01–D17; до этого Gate остаётся WIP.

## Предыдущий checkpoint — уточнения и разрешения через реальный Desktop, около 20:35 МСК

После подтверждённого UIA↔IPC создания и продолжения изолированный
`DesktopBridgeService` на установленном Desktop `26.917.9434.0` прошёл
обычное асинхронное уточнение: карточка автору numeric `41`, отказ
участнику `55`, ответ автора и один точный финал в fake Telegram topic `13`.
Отдельные approval-сценарии проверили разрешение владельцем numeric `99`
безопасного `Write-Output` и отказ в `Start-Process calc.exe`; чужой ID
не принимался, в отказанном turn нет выполненной команды. Новые поля
approval этой версии полностью отображаются в карточке. Неизвестный исход
первого ответа и ошибочная адресация тестовой карточки восстановлены только
после точного readback, без повторного Desktop turn. Тестовый sender не
переустанавливался. Единый связанный M2-набор на текущих bytes:
`237 passed, 1 skipped`. Диагностический all-repo запуск с отдельным temp
остановился после 44 успехов на историческом Gate 0 тесте, ожидающем
другой dirty-manifest; он не использован как приёмка M2.
Это WIP с изолированной SQLite/fake Telegram, а не живые Telegram D06/D07.
Установленный notifier отдельно подтвердил read-only exact suppression
реального Desktop bridge-turn при изолированной SQLite; чужой turn и
отсутствие binding не подавляются. Фактические сообщения Telegram ещё не
сверялись.
Frozen candidate, полный L1/L2/L3, D01–D17 и production activation ещё
открыты; три production Scheduled Tasks по последней квитанции Disabled.

## Предыдущий checkpoint — owner-транспорт, около 19:18 МСК

На установленном Desktop `26.917.9434.0` один точный UIA send создал
задачу `01a0d432-e0c9-7280-bcd5-4350a8c7843f` в выбранном
`nobus-orchestrator-dev`. Она видна в списке Desktop с правильным `cwd`;
owner IPC прочитал полный завершённый ответ. Второй ход через внешний
owner IPC, третий через штатный интерфейс Desktop завершились в той же
задаче; оба финала IPC прочитал без сокращения. Это положительное
доказательство узкого create/visibility/bidirectional продолжения, но не
проверка Telegram-bridge, вопросов, approvals, файлов, больших ответов или
полного паритета tools/skills/MCP. До send исправлены UIA false stops:
визуально пустой Chromium editor отдаёт LF + placeholder, в новом виде
две кнопки «Новый чат», а `SetValue` даёт отложенный readback. Точный
уже набранный запрос отправлен отдельным однократным recovery-действием
без повторного создания/ввода. `60 passed` в адресных UIA/bridge тестах;
PowerShell 5.1 parser — 0 ошибок. История первых меток с неизвестным
исходом сохранена, их не повторяли. Production bot по последнему снимку
Disabled, продуктового Telegram-запроса в этом checkpoint не было.
Read-only ledger существующего notifier содержит `sent` для всех трёх
test turn; это автоматические summary, не продуктовая доставка полного
ответа.
Затем реальный `DesktopBridgeService` с изолированной SQLite и fake Telegram
создал ещё одну задачу Desktop и передал один полный короткий итог в
локальный приёмник с исходной темой/reply. Продолжение этой задачи дало
финал 6 243 символа, 2 части текста, `answer.md` с точным SHA видимого
финала и тестовый файл с совпавшими bytes; четыре слота локальной доставки
имеют `sent`. Telegram и установленный sender в этих двух сценариях не
вызывались; обычный глобальный notifier отдельно отметил их turn как `sent`.
Связанный набор на текущем WIP: `230 passed, 1 skipped` в 14 файлах.
Gate остаётся WIP; D01–D17 и полный независимый L1/L2/L3 не закрыты.
Подробности: [handoff](../gates/mvp2/m2-desktop/HANDOFF.md),
[evidence](../gates/mvp2/m2-desktop/EVIDENCE.json).

## Предыдущий локальный WIP после аудита 24 сентября, около 18:45 МСК

В одном существующем worktree `codex/m2-desktop` адресно исправлены R01–R05:
естественное создание (включая голос с подтверждением и выбором проекта),
адресация обычного вопроса, reconnect pending interaction, устойчивые слоты
частичной доставки и точная проверка Git worktree проекта. Связанный набор
на текущих WIP-байтах — `226 passed, 1 skipped` в 14 файлах; это не
сквозная приёмка. Точная DDL прежнего checkout мигрирует на изолированной
SQLite; реальная production SQLite из sandbox недоступна (`Access denied`),
без обхода. Read-only UIA увидела активную задачу; в интерактивном контексте
пустая новая задача выбранного проекта подтвердилась по отдельному активному
проекту и метке «Новый чат». Адаптер исправлен для нескольких web-корней
Chromium и проверяет контекст до ввода и перед send. После ручного
переключения на существующую задачу того же проекта read-only предохранитель
вернул `false`. После отдельного точного разрешения один раз вызван
`CreateAndSubmit` с безопасным текстом и уникальной меткой. Receipt потерян:
PowerShell завершился с ошибкой, а локализованный stderr вызвал сбой
декодирования в Python. IPC за 30 секунд не увидел нового thread-кандидата;
read-only Desktop по-прежнему показывал прежнюю задачу. Исход первой метки
классифицирован как unknown, она не повторялась. По расширенному разрешению
следующие попытки с новыми метками локализовали два фактора: отсутствие BOM
искажало русский селектор в PowerShell 5.1; после восстановления BOM
UIA открыла пустой вид проекта, но предохранитель остановился на уже
существующем непустом черновике, не относящемся к тестам. Черновик не
читался и не изменялся. После ответа владельца «сохранён/очищен» оба
read-only паттерна всё ещё видят 20 непробельных символов в этом поле;
владельца попросили проверить именно текущее окно. Специальное уведомление
автору об exact чужом draft добавлено локально без автоматического повтора.
Связанный адресный набор после правок — `60 passed` в двух файлах.

Кандидат не заморожен, полный L1/L2/L3 и D01–D17 не закрыты. Production
bot остаётся Disabled по последнему подтверждённому снимку; новый Desktop
turn не подтверждён, прямого Telegram product send и публикации не было. По отдельному
подтверждению точных SHA установлен guard двух файлов существующего
`nobus-send-results` с резервной копией старого sender; настройки и
credentials не менялись.
Оставшиеся границы: A01 на реальной изолированной копии, A06 после очистки
чужого draft и доказанный полный create/send, A09/A13
положительный live opt-out и единая доставка, реальный
Артур младший, rollback и controlled activation. Подробности:
[handoff](../gates/mvp2/m2-desktop/HANDOFF.md),
[security triage](../gates/mvp2/m2-desktop/SECURITY-TRIAGE-20260924.md).

## Предыдущий локальный checkpoint — 24 сентября

В той же задаче и worktree `codex/m2-desktop` продолжается локальная
разработка. Три поставки Grok интегрированы адресно, исправлены дефекты
форматирования/путей/карточек; bridge получил numeric-адресацию в исходной
теме, защиту stale approval, UIA bootstrap lock, opt-in-флаг в общем runner и
начальные offline-пути восстановления. Backup rebind для завершённого старого
журнала проверен только на изолированном тесте. Существующий sender runtime
расширен request-scoped ключом, notifier штатно обновлён до подтверждённого
SHA `e6e08ba29097b3a35e58f43cf2a7619778b95bf72561d23499c31e91a6479eda`;
ему добавлен только read-only путь к SQLite-привязкам. Настройки Telegram,
credentials и три Disabled production-задачи не менялись. Desktop обновился
до `26.917.9434.0`: read-only IPC/UIA preflight пройден, новых turn не было.
Причина прежнего Backup result `1` уточнена read-only: завершённый
подписанный журнал привязан к прежнему config digest, production-скрипт
отказывает на новом digest до запуска цикла. Локальный A01 reconcile
проверен только на изолированном тесте и не развернут.
Один отдельно разрешённый обычный тестовый итог в существующей Desktop-задаче
завершился; exact notifier ledger key имеет `sent`. Это не проверка
подавления bridge-уведомления и не приёмка продуктовой доставки.
Обнаружены и локально исправлены гонка bootstrap turn с notifier,
отсутствовавшая передача `--desktop-bridge` через Scheduled Task/supervisor и
несовместимость backup exact-schema после аддитивной миграции. Новый
notifier v4 установлен по точному подтверждению SHA, без Telegram-вызова;
production bot по-прежнему выключен. Связанный набор на последних кодовых
bytes вместе с четырьмя адресными совместимостями дал `301 passed, 1 skipped`.
Checkpoint `9cefc58` проверен также в чистом Git-экспорте: `compileall`
и `296 passed, 1 skipped`; последующая L3-проверка нашла два дефекта
карточек. Локально исправлены адресация явного permission-вопроса через
`requestUserInput` владельцу и повтор карточки после потерянного Telegram ACK;
адресные red→green и 13 связанных файлов дали `206 passed, 1 skipped` на
новых WIP bytes. Чистый экспорт относится к прежнему checkpoint и не
подменяет проверку этих новых bytes.
Кандидат ещё не заморожен, полный Gate suite и L1/L2/L3 не пройдены. A09/A13 установлены, но их живой цикл и
отсутствие дублей не доказаны; A06–A08 и D01–D17 открыты. Старые
live-квитанции owner IPC сохранены как история, не как приёмка нового
продукта. Подробности и точные результаты — в
[handoff](../gates/mvp2/m2-desktop/HANDOFF.md) и
[журнале](../gates/mvp2/m2-desktop/AUDIT-JOURNAL.md).

## Историческая пауза M2-DESKTOP для независимого аудита — 22 сентября, 12:29 МСК

По прямому запросу владельца разработка и live-проверки M2-DESKTOP безопасно
остановлены. Production checkout сейчас detached на локальном commit
`3ea243893a2647dc631662c2a2030de7679ae0e1`; связанная backup-конфигурация
изменена под этот revision, но запуск не достиг readiness. После успешного
activation rebind штатный cold-start backup cycle завершился Scheduler result
`1`, точная failing boundary ещё не локализована. Все три задания
`NobusSpaceBot`, `NobusSpaceBot-Health` и `NobusSpaceBot-Backup` остановлены и
Disabled. Бот намеренно недоступен до аудита и контролируемого восстановления.

Один подтверждённый Telegram request в «Заметки бизнеса» → «Codex work»
(message `2150`, request
`e18a5ca3-95d3-4be8-8453-630d88e97a50`) завершён как `unknown_dispatch` без
Desktop thread/turn; read-only проверка показала, что новая задача Desktop не
создана. Запрос не повторять. UIA root cause исправлен локально в `3ea2438`, но
post-fix live journey не выполнялся. Gate остаётся WIP, не опубликован и не
принят; полный L1/L2/L3 не запускался. Точная передача — в
[handoff](../gates/mvp2/m2-desktop/HANDOFF.md),
[журнале аудита](../gates/mvp2/m2-desktop/AUDIT-JOURNAL.md) и
[evidence](../gates/mvp2/m2-desktop/EVIDENCE.json).

Этот текущий операционный снимок не отменяет историческую приёмку MVP1 ниже,
но заменяет старое утверждение, что production продолжает работать на принятом
MVP1 revision.

**M1-S1 CLOSED / ACCEPTED; MVP1 ACCEPTED — 19 сентября 2026, 17:50 МСК.**

Устойчивость принята по сокращённым критериям владельца от 19.09.2026 после исправлений и целевой проверки работающего бота. Повторное 72-часовое наблюдение не проводилось.

## Отдельный инцидент 20 сентября

После гибридного выключения Windows production остановился на подписанном `starting` с прежним BootIdentifier. В 13:37 МСК бот восстановлен штатной операторской сверкой и новым проверенным backup; данные и recovery history не откатывались и не удалялись. Проверка реальной text-задачи в 13:44 и read-only срез в 13:47 подтвердили ответ, TXT, обе доставки, четыре БД и local/public readiness. Подробности и ограничения — в [записи инцидента](../incidents/2026-09-20-production-stop.md).

Исправление [ADR 0028](../adr/0028-post-mvp1-power-transition-recovery.md) принято через [PR №38](https://github.com/streetenergy63reshik-del/nobus-space/pull/38) и развёрнуто 20 сентября: LIVE `9065cfc6a5b6e23fc44062e8a4d7001315033fa8`. Оно различает истёкшую голосовую кнопку и исполняемый эффект, а также допускает согласование после перехода питания при прежнем BootIdentifier только по проверенному свежему доказательству. Историческая приёмка MVP1 от 19 сентября сохраняется отдельно; на дату этого инцидента MVP2 не был начат.

На 20.09, 16:27:36 МСК полный backup/start завершён, Bot Running, Health и Backup Enabled/Ready с результатом 0. Local/public HTTP 200 за 234/766 мс; одна цепочка Core/relay, один listener, активная lease. Четыре БД и межбазовая сверка PASS, прежние строки сохранены, offset не уменьшился, pending/leased/unknown/failed deliveries — 0, confirmed parts — 20. Копия VERIFIED, admission hold снят. Два свежих аутентифицированных Health PASS — 16:28:05 и 16:29:05. [Подробности проверки и ограничения](../incidents/2026-09-20-production-stop.md).

## Последующие остановки и восстановление

- [29–30 сентября: relay, backup и порядок включения задач](../incidents/2026-09-30-relay-stop.md).
- [1 октября: повторное завершение relay](../incidents/2026-10-01-relay-stop.md).
- [2 октября: local readiness STOP](../incidents/2026-10-02-local-readiness-stop.md).
- [3 октября: сводный журнал и установленный ремонт](../incidents/2026-10-03-production-stability-14d.md).

## Версии и публикация

| Объект | Подтверждённое состояние |
|---|---|
| Наблюдаемый LIVE 3 октября | `4db5f0e9266637feca408a57aa0c8e8ac580dbc0`, локально проверен и установлен; код ещё не опубликован в main |
| Опубликованная база документного PR | `f3fdb2d22a41b6a5b84fec06544447014c7bb35c`, после PR №39; runtime-код документным обновлением не меняется |
| LIVE после инцидента 20 сентября | `9065cfc6a5b6e23fc44062e8a4d7001315033fa8`, PR №38; проверенный кандидат `863ba6f097199cbe8136516ab6ac16f389f76ed3` имеет то же дерево |
| Историческая приёмка MVP1 от 19 сентября | `0c9b778ef59eb4cc01d3ab0c2ef9a14969801d83` |
| Слияние исправлений | [PR №33](https://github.com/streetenergy63reshik-del/nobus-space/pull/33), затем [PR №34](https://github.com/streetenergy63reshik-del/nobus-space/pull/34); итоговый code merge `8af1309af36eb3ab591186906975dd8cd3ac9880` |
| Документы окончательной приёмки | [PR №36](https://github.com/streetenergy63reshik-del/nobus-space/pull/36), merge `c9390cc445d4e338d01552719dc6a02203c755a7` |
| Релизный тег | `v1.0.2` остаётся на `82003c03d8a36015703472b472640ab4021fb416`; maintenance не перемещает тег |
| Историческая граница возврата 20 сентября | До записи v5 возможен возврат к `0c9b778` с точной прежней конфигурацией и rebind; после `power_reconciled` нужен совместимый reader по ADR 0028. Исторический `220b396` относится к v4 и сам по себе v5 не читает. БД не откатываются |

Последующие изменения документации не меняют LIVE и не являются новой эксплуатационной проверкой. Фактический HEAD опубликованной `main` читается в GitHub; таблица отдельно фиксирует текущий развёрнутый код и историческую приёмку, а не обещает совпадать с последним документным commit.

## Историческая эксплуатационная приёмка 19 сентября

На 19.09.2026, 17:50:10 МСК:

- local/public readiness: HTTP 200, точное ожидаемое тело, прежние deadlines 2/5 с;
- одна цепочка supervisor/Core/relay, один listener и активная lease;
- два завершённых Health PASS и полный контролируемый backup-цикл с проверенной копией, снятием hold и возвратом ready;
- реальная text-задача: правильный ответ 42, доступный TXT, ACK обеих частей первой попыткой, без дублей; один worker attempt, отдельно разрешённый semantic-разбор, ASR 0;
- четыре БД исправны, прежние строки сохранены, offset не уменьшился; неизвестных доставок и зависших задач нет.

Счётчики этого среза: 88 задач, 86 receipts, 18 подтверждённых частей доставки, offset 375633521. Это исторический baseline; новые принятые задачи закономерно меняют счётчики. Число внутренних сетевых повторов провайдера из worker audit не выводится.

Проверка состояла из двух частей — 11:41:51–11:48:40 и 17:44:26–17:50:10 МСК — с паузой согласования вызовов модели. Собственно проверки заняли суммарно менее 20 минут; непрерывное 20-минутное наблюдение не заявляется.

## Границы и следующий шаг

Историческое окно 16–19 сентября сохраняет **NOT PASS**. Неизвестные исторические причины public/SSH/Health не объявлены установленными. Исправления закрыли доказанные пробелы восстановления и диагностики; прежние FAIL сохранены.

Монитор Codex в 08:00 и 22:00 МСК активен и дополняет три штатных задания Windows. C6 и историческая приёмка не переоткрываются. Старый опубликованный план MVP2 сохранён как история предложения; текущее наличие Desktop bridge в LIVE не превращает его незавершённый Gate в принятый. Следующий шаг по коду — отдельная сверка и публикация установленной истории с её собственными доказательствами, без смешения с этим документным PR.

## Доказательства и навигация

- [Таблица I01–I07, V01/V02 и итог приёмки](../gates/mvp1-maintenance/REPAIR-ACCEPTANCE.md).
- [EVIDENCE.json](../gates/mvp1-maintenance/EVIDENCE.json): актуальный раздел `current_acceptance_20260919`; остальные разделы сохраняют свои даты и границы.
- [Исторический журнал 72 часов](../gates/mvp1-maintenance/JOURNAL-72H.md) и [передача M1-S1](../gates/mvp1-maintenance/HANDOFF.md).
- [Эксплуатация](../08-Runbook-эксплуатации.md), [роли каталогов](WORKSPACE-INVENTORY.md), [планы MVP2](../15-Продуктовая-дорожная-карта.md).
- [История передач](README.md). Полный прежний CURRENT с промежуточными checkpoints доступен [в принятой ревизии c9390cc](https://github.com/streetenergy63reshik-del/nobus-space/blob/c9390cc445d4e338d01552719dc6a02203c755a7/docs/handoffs/CURRENT-STATUS.md).
