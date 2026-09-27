# Реестр Gate MVP2

27 сентября, 09:43: по новому поручению владельца локальный источник
M2-DESKTOP подготовлен как DRAFT к одной заморозке и L1–L3. Bridge/docs
предпроверка: 68 passed; один Git `$GIT_DIR too big` в длинном
кириллическом test root классифицирован как ограничение проверяющей
среды, ровно тот тест прошёл в коротком новом temp. До commit точный
candidate SHA не существует; вердикт L1–L3 не выдан. Production
`fd4d66c` остановлен, D03 Desktop turn не повторять, Gate открыт.
[Передача](m2-desktop/HANDOFF.md).

27 сентября, 09:21: по разрешению владельца только для этапов 1–2
классифицированы временные файловые эффекты в новом test root; локально
исправлен control-file crash-gap и первый recovery retry. После найденной
и исправленной регрессии 36 зависимых backup-тестов, новый негативный
тест и 6 readiness-тестов прошли. Точный вызов, вызвавший исторический
тайм-аут, не доказан; выпуск и живые D02–D17 оставлены на следующий
запуск. Production всё ещё `fd4d66c`/Disabled с admission hold и signed
STOP; уже завершённый D03 Desktop turn не повторять. Gate открыт.
[Передача](m2-desktop/HANDOFF.md).

27 сентября, 08:22: старый scheduled Backup на production `fd4d66c`
автоматически выполнил VERIFIED backup, затем оставил `admission_hold`
и `failed_operator_required/restart_not_ready`. Main/Health уже выключены;
idle Backup Task выключен штатным helper, чтобы не повторять цикл с
`cleanup_staging()` при запрете удаления. Новый локальный WIP сохраняет
прежние control-файлы без `os.replace` и отказывает при crash-gap, но
SQLite sidecars и восстановление после разрыва не проверены. Production
не восстановлен; D03 ещё не доставлен,
D02–D17/Gate открыты. [Подробности](m2-desktop/HANDOFF.md).

26 сентября, 22:47: файловый монитор показал 59 `Deleted` событий за
четыре синтетических backup-теста checkpoint `91a0499`. Зелёные
unit-тесты не доказывают no-delete; локальный кандидат не выпускать.
Production не менялся и остаётся остановленным на `fd4d66c`; D03
Desktop-turn завершён, Telegram delivery нет. Внешние операции
остановлены до устранения точного файлового ограничения; D02–D17 и
Gate открыты. [Детали](m2-desktop/HANDOFF.md).

26 сентября, после 22:40: локальный checkpoint `91a0499` добавил
no-delete вариант backup поверх readiness fix. Чистый экспорт: `15 passed`
адресных тестов, worktree signed rebind/negative: `3 passed`. Настоящий
backup может иметь недоказанные внутренние SQLite WAL/SHM эффекты;
полный L1/L2/L3 и live на этом commit не проводились. Production
по-прежнему остановлен на `fd4d66c`, D03 Desktop final не доставлен;
D02–D17 и Gate открыты. [Детали](m2-desktop/HANDOFF.md).

26 сентября, 22:27: локальный checkpoint `133929f` прошёл 11 адресных
тестов в чистом экспорте. Он устраняет синхронные блокировки Core loop,
но не доказан live и **не выпущен**. Production всё ещё остановлен на
`fd4d66c`; D03 completed turn без Telegram delivery. Выпускной backup
требует удаления временных SQLite и hold-файла, запрещённого владельцем;
до безопасного no-delete решения новый backup/rebind/reset не запускать.
Остальные D02–D17 и Gate открыты. [Детали](m2-desktop/HANDOFF.md).

26 сентября, 21:36–21:51: новый запрос `continue` один раз прошёл из
«Заметок бизнеса» в **тот же** thread установленного Desktop и дал
завершённый точный ответ `M2-CONTINUE-20260926-1`. Bridge request
`5b965633-8670-4db5-a67f-2a530ca48f78` ещё `running`, delivery rows
`0`: Main снова штатно остановился после трёх local/public readiness
deadline. Новый signed `control_closed` head
`sha256:1d1bf928da0d8eea509ae329bc15ed271414afca3e50de77f8c8d9c099e42d83`.
Production остаётся на `fd4d66c`; диагностическое исправление только
в WIP, без выпуска. D01 подтверждён прежним запросом, D03 частичен,
D02–D17 и Gate открыты; исходный запрос и Desktop-turn не повторять.
[Доказательства](m2-desktop/EVIDENCE.json).

26 сентября, 20:17–20:20: один разрешённый signed reset и один запуск
существующего Main восстановили уже завершённый Desktop turn запроса
`ae0183d9-669a-4cde-b81e-74d749cc6643` без нового исполнения.
Delivery ledger: одна `text/0/sent` с message ID `2306`; исходная тема
Telegram показывает ровно один полный итог `M2-LIVE-20260926-3`,
ответом на запрос владельца. Main/Health и local/public readiness теперь
здоровы. D01 подтверждён простым реальным текстовым сценарием, D02–D17
и Gate остаются открытыми; причина прежнего safety stop неизвестна.
[Доказательства](m2-desktop/EVIDENCE.json).

26 сентября, 19:39–19:48: одна реальная команда в Telegram дошла до
установленного Desktop; thread/turn и точный полный финал подтверждены
IPC. Bridge request `ae0183d9-669a-4cde-b81e-74d749cc6643` остаётся
`running` без delivery: Main штатно остановлен после трёх local/public
readiness deadline. Подписанный head
`sha256:2665c870e53768eb24d0467c8e1b10a9a6d97bb8d11399f156556409686c9365`.
Повторять сообщение и Desktop-ход нельзя. Один reset/start только после
точного разрешения и readback; D01–D17 и Gate не приняты.
[Доказательства](m2-desktop/EVIDENCE.json).

В 18:23 второй живой Telegram-запрос был принят, но production UIA
отказал до создания задачи: Desktop обновился до `26.924.2738.0`,
а `cdc59a2` допускает только `26.917.9434.0`. Request `9202eece…`
остаётся `unknown_dispatch`, повтор запрещён. Локальная новая версия и
ожидание проектного контекста дали отдельную видимую Desktop-задачу;
IPC подтвердил owner, cwd и точный полный итог. `74 passed` UIA/bridge,
но исправления ещё WIP, Telegram D01–D17 не приняты.

26 сентября в 10:34 Main остановился после трёх local/public readiness
timeout. Один отдельно разрешённый signed recovery reset и один запуск
Main в 18:05 вернули local/public `PASS`; Main `Running`. Реальный запрос
`M2-LIVE-20260926-1` дал ответ бота, но не Desktop turn: reply к корню темы
ошибочно трактовался как продолжение. Локальная правка и `292 passed`
затронутой регрессии — WIP, в production остаётся `cdc59a2`. D01–D17
не приняты; старое сообщение не повторять. [Доказательства](m2-desktop/EVIDENCE.json).

26 сентября production активирован на проверенном `cdc59a2` (tree `0ac7807`)
после точного rollback, нового O_EXCL config, единственного signed rebind
и одного успешного backup/recovery cycle. Signed journal `complete`:
`sha256:5c11f47370b09290f9683a78d70061593a3bfd99ba05cafd4cc3fe529363b596`;
Main `Running`, Health/Backup `Ready`, local/public readiness `PASS`.
Это рабочий runtime, не принятый M2-DESKTOP: живые Telegram D01–D17 открыты.
Точные квитанции — в [handoff](m2-desktop/HANDOFF.md) и
[evidence](m2-desktop/EVIDENCE.json).

25 сентября code checkpoint `cdc59a2` (tree `0ac7807`) прошёл L1
`2915 passed` и чистый ZIP L2 `491 passed`; L3 проверил новый
interpreter binding и signed recovery. Production по-прежнему выключен
на прежнем `26b95e5` с failed journal `sha256:7221cf56…`;
новый выпускной допуск запрошен. Локальный кандидат не равен активному
или принятому M2-DESKTOP; D01–D17 через Telegram ещё не выполнены.

25 сентября вечером один точно разрешённый same-config recovery после
включения Backup снова завершился `failed_operator_required`: Main exit 78,
signed journal `sha256:7221cf56d01c950bb3f82efa65eeebfa8fcf176081fca2595c7f20a8e2bb92df`.
История восстановления исправна, все три Tasks после безопасного отката
Disabled. Подтверждённый новый дефект — различный base interpreter в
activation binding `python.exe`/`pythonw.exe`; локальная поправка и
регрессия `274 passed` ещё WIP. Нового frozen commit, Telegram D01–D17 и
приёмки нет; предыдущая точная авторизация израсходована.

25 сентября следующий разрешённый выпуск установил clean `26b95e5` в
production, сохранил rollback, поставил новый backup config и подписанно
перепривязал recovery head. Один цикл создал VERIFIED generation, но снова
остановился на `starting` (Main exit 75). Новый signed failed journal
`sha256:d32cbd85ae804f4cb3a92cdf6e0482a1ba0bc1d506990a5a7d8a9f9996ff60d4`;
admission hold и cleanup доказаны, три Tasks Disabled. Новая конкретная
причина — Backup Task остался Disabled при запуске Main, а активация требует
его Enabled. Telegram live-тестов не было. Включение Backup и один
same-config recovery запрошены отдельно; старый цикл не повторять.

25 сентября локальный кандидат кода `fe333c6` (tree `c016023e2b4b32a2403e2c50d312ddc905891730`):
чистый Git ZIP `225 passed`; широкий L1 `2915 passed, 3 skipped,
5 exact historical deselected`. Production read-only: clean `fa6f1f0`,
три Tasks Disabled, signed failed journal без дрейфа. R02 manual-Desktop
граница согласована; R01 не объявлен полным модельным пониманием.
Gate остаётся неактивным и непринятым до точного recovery и живых D01–D17.

25 сентября текущий checkpoint: `telegram-live` staged на локальном
`fa6f1f0` по точному разрешению, но один backup reconciliation завершился
`failed_operator_required` на `starting`: verified generation создана,
admission hold и cleanup подтверждены, все три Scheduled Tasks Disabled.
Причина exit 75 — непринятое signed поле `reconciled_from_digest`; поправка
только в WIP. Новый live UIA open-only для ранее не связанной выгруженной
задачи восстановил owner точного ID без turn. Затронутая регрессия после
последних правок — 225 passed, в том числе `ops_queue1` — 13 passed.
Владелец согласовал ручной Desktop-ответ для неоднозначного текстового R02;
структурированные Telegram approvals ещё требуют live-цикла. Gate остаётся WIP, публикации, живой
Telegram-приёмки D01–D17 и принятия нет. Для изменённого commit и recovery
нужна новая точная авторизация.

25 сентября checkpoint `b8834ae` добавил безопасное open-only восстановление
известной выгруженной задачи Desktop. Один live опыт через UIA+IPC дал
точного owner, другой не дал и сохранён как ограничение; turn и Telegram
не отправлялись. Широкий локальный L1: 2904 успеха, 3 skip, 7 точных
исторических deselect; чистый Git ZIP L2: 247 успехов, 1 skip.
Production по-прежнему выключен; D01–D17, release L3 и точное разрешение
на новую привязку остаются открытыми.

25 сентября локальный code checkpoint дополнен точным исправлением
мигратора `935d93037a94f63e9e63395d626ebdec11cff515`: оба разрешённых
DDL-хэша принимаются, неизвестный по-прежнему запрещён. Шесть C6 migration
тестов прошли. Широкий прогон прежнего `e5921b8` дал 2894 успеха, три
skip и 13 отказов: три исправлены, три связаны с sandbox identity и прошли
от пользователя-владельца, семь — устаревшие нормативные fixtures старых
Gate. Полная новая кандидатная проверка, activation и D01–D17 ещё открыты.

24 сентября 2026. Функциональная цель: Telegram ↔ Codex Desktop.
Gate остаётся одной задачей; локальная разработка возобновлена после
исторической паузы 22 сентября. Тогда один Telegram request дошёл до
bridge и завершился `unknown_dispatch` до создания Desktop task; UIA root cause
исправлен локально. Активация revision выполнена не полностью: recovery rebind
прошёл, cold-start backup cycle завершился result `1`, readiness не достигнута.
Read-only диагностика 24.09 локализовала отказ: completed backup journal
связан с прежним config digest, текущая задача планировщика — с новым.
Все три production Scheduled Tasks остановлены и Disabled. Gate не принят.

Позднее 24 сентября на Desktop `26.917.9434.0` подтверждён узкий
owner-транспорт: новая задача в `nobus-orchestrator-dev` создана через UIA,
видна в Desktop, её финал прочитан owner IPC; затем IPC и UI сделали по
одному продолжению в той же задаче с точным readback. Прежняя гипотеза о
чужом draft опровергнута: пустой Chromium editor отдавал LF + placeholder.
Это не продуктовая Telegram-приёмка. Ранее неизвестные метки не повторялись;
полный D01–D17 и L1/L2/L3 ещё впереди.
Локальный `DesktopBridgeService` также прошёл реальный create/continue
через Desktop с изолированной SQLite и fake Telegram: полный короткий
итог, затем 6 243-символьный финал/`answer.md` и файл с проверенным SHA.
Позднее в той же задаче проверены async-уточнение автору и два решения
владельца (безопасное approve, отказ на запуск Calculator) с отказом
чужому numeric ID; всё ещё с fake Telegram, не live приёмка D06/D07.
Локальный code checkpoint `55297db440b502292159f2612c579f588e37c323`
(tree `e0cde457c7993791311a6e9249ddb6fb382626e3`) проверен в чистом
Git-экспорте: `237 passed, 1 skipped` в 14 связанных M2-файлах;
общий исторический набор отдельно остановился на Gate 0 dirty-manifest
fixture, не относящемся к M2.
Установленный notifier read-only подавил точный реальный Desktop bridge-turn
при изолированной SQLite, но не чужой turn; живое отсутствие дубля в Telegram
ещё открыто.

| Gate | Статус | Задача | Base SHA/tree | Result SHA/tree | Документы |
|---|---|---|---|---|---|
| M2-DESKTOP | `fd4d66c` в production, Main остановлен safety guard после повторного readiness timeout. Реальный D01 доставлен ровно один раз; новый Telegram continuation завершён в том же Desktop thread, но не доставлен из-за остановки. D03 частичен, D02–D17 и Gate открыты. | `01a0c425-3a83-7e82-b4c5-9a71e8251ecc` — «Реализовать Gate M2-DESKTOP» | Исторический code checkpoint `cdc59a2ebd5d228e062937625da209be6d652c4a`, tree `0ac7807464c3ffbdd25a18b415bcce1f4fa47711`; Gate ещё не принят | `fd4d66cfccb66c29702c29f6df59d137d3c26e3b`, tree `efe10b99be591bb194d0e20f09ddd614f0ac2f27` / PRODUCTION STOPPED, ACCEPTANCE OPEN | [Архитектура](M2-DESKTOP-ARCHITECTURE.md), [исследование транспорта](M2-DESKTOP-TRANSPORT-RESEARCH.md), [промпт](M2-DESKTOP-PROMPT.md), [handoff](m2-desktop/HANDOFF.md), [журнал аудита](m2-desktop/AUDIT-JOURNAL.md), [evidence](m2-desktop/EVIDENCE.json) |

Реальные task id и title внесены после запуска. В Gate сохраняются один
`m2-desktop/HANDOFF.md`, один `m2-desktop/EVIDENCE.json` и один журнал
независимого аудита. Внутренние checkpoints, проверки и незавершённая
активация остаются в этой задаче. Локальный result SHA не опубликован и не
означает FROZEN, VERIFIED, ACTIVE или ACCEPTED.

Статусы: NOT STARTED → WIP → CHECKPOINT → FROZEN → CANDIDATE VERIFIED →
ACCEPTED; при доказанных препятствиях BLOCKED/REWORK. Публикация и активация —
отдельные поля. CANDIDATE VERIFIED не означает ACTIVE или приёмку MVP2.
ACCEPTED требует D01–D17, включая реальную проверку и приёмку владельцем.

Scope ведётся в [roadmap](../../15-Продуктовая-дорожная-карта.md), критерии —
в архитектуре, фактические evidence — в пакете Gate после начала разработки.

## Заменённое предложение

M2-G0, M2-G1, M2-G2, M2-G3, M2-G4: **SUPERSEDED / NOT STARTED**.
Это прежний план редизайна от 13–19 сентября, заменённый вводными 21 сентября.
Сохранённые промпты не запускать; predecessor-зависимости старой последовательности
к M2-DESKTOP не относятся. Исторические документы не являются разрешением действий.
