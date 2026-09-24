# Реестр Gate MVP2

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
| M2-DESKTOP | WIP / 24.09; R01–R05 исправлены локально; реальный create/visibility/UI↔IPC и изолированные full-answer/file, async question, owner approve/deny прошли на установленном Desktop. Установленный notifier read-only подтвердил exact opt-out; live отсутствие дубля и Telegram D01–D17, A01, голос/агент/две темы, паритет и независимый L1/L2/L3 открыты. Чистый Git-экспорт code checkpoint `55297db` прошёл связанный набор `237 passed, 1 skipped`; all-repo диагностика упёрлась в исторический Gate 0 dirty-manifest fixture. Production bot Disabled по точному read-only preflight | `01a0c425-3a83-7e82-b4c5-9a71e8251ecc` — «Реализовать Gate M2-DESKTOP» | code checkpoint `55297db440b502292159f2612c579f588e37c323` / `e0cde457c7993791311a6e9249ddb6fb382626e3`; frozen Gate tree отсутствует | `3ea243893a2647dc631662c2a2030de7679ae0e1` / LOCAL ONLY | [Архитектура](M2-DESKTOP-ARCHITECTURE.md), [исследование транспорта](M2-DESKTOP-TRANSPORT-RESEARCH.md), [промпт](M2-DESKTOP-PROMPT.md), [handoff](m2-desktop/HANDOFF.md), [журнал аудита](m2-desktop/AUDIT-JOURNAL.md), [evidence](m2-desktop/EVIDENCE.json) |

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
