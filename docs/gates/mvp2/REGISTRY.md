# Реестр Gate MVP2

21 сентября 2026. Функциональная цель задана владельцем: Telegram ↔ Codex Desktop.
Gate запущен. Прежний blocker локализован на отдельном App Server: owner IPC
работающего Desktop принял initialize и нашёл владельца существующей задачи.
Минимальный adapter и 13 offline-тестов готовы; UIA semantic selectors доступны
read-only. Изменяющий Desktop smoke ещё не разрешён и не выполнен. Один Gate =
одна задача.

| Gate | Статус | Задача | Base SHA/tree | Result SHA/tree | Документы |
|---|---|---|---|---|---|
| M2-DESKTOP | WIP / DESKTOP IPC ADAPTER CHECKPOINT; live mutation awaiting permission | `01a0c425-3a83-7e82-b4c5-9a71e8251ecc` — «Реализовать Gate M2-DESKTOP» | `f3fdb2d22a41b6a5b84fec06544447014c7bb35c` / `b604fcb6591ae11c4280d3a7d41a7261c2383305` | NOT COMMITTED | [Архитектура](M2-DESKTOP-ARCHITECTURE.md), [исследование транспорта](M2-DESKTOP-TRANSPORT-RESEARCH.md), [промпт](M2-DESKTOP-PROMPT.md), [handoff](m2-desktop/HANDOFF.md), [evidence](m2-desktop/EVIDENCE.json) |

Реальные task id и title внесены после запуска. В Gate создан ровно один
`m2-desktop/HANDOFF.md` и один `m2-desktop/EVIDENCE.json`. Внутренние checkpoints,
проверки и разрешённая активация остаются в этой задаче.

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
