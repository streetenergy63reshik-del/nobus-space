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

| Gate | Статус | Задача | Base SHA/tree | Result SHA/tree | Документы |
|---|---|---|---|---|---|
| M2-DESKTOP | WIP / 24.09; checkpoint `9cefc58` plus local D08 card hardening; latest related check 206 passed, 1 skipped; production bot disabled; live A09/A13 and D01–D17 open | `01a0c425-3a83-7e82-b4c5-9a71e8251ecc` — «Реализовать Gate M2-DESKTOP» | `31df0d00a0a74de920a7a7367d3b662566a653ff` → local checkpoint `9cefc58de4ba1bd5cd43f611a072ede9cca9b8e4` + uncommitted WIP; no frozen tree | `3ea243893a2647dc631662c2a2030de7679ae0e1` / LOCAL ONLY | [Архитектура](M2-DESKTOP-ARCHITECTURE.md), [исследование транспорта](M2-DESKTOP-TRANSPORT-RESEARCH.md), [промпт](M2-DESKTOP-PROMPT.md), [handoff](m2-desktop/HANDOFF.md), [журнал аудита](m2-desktop/AUDIT-JOURNAL.md), [evidence](m2-desktop/EVIDENCE.json) |

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
