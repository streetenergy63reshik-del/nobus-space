# Архитектурный пакет Gate 0–8, включая Gate 2A

**Статус:** TARGET DESIGN

**CURRENT implementation:** Gate 0 `REWORK`; Gate 1 integration/commit
заблокирован до нового immutable Gate 0 acceptance binding

**База исследования:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`

**Дата:** 28 июля 2026 года

Эта папка содержит исследовательское основание и детальную архитектуру каждого
Gate MVP-1. Исследование и архитектура сами по себе не доказывают реализацию,
работающий runtime или PASS соответствующего Gate. Прежний Gate 0 READY отозван
независимым аудитом; текущий handoff до повторного seal обязан быть BLOCKED.

## Текущий implementation status

| Gate | Статус | Evidence | Следующий шаг |
|---:|---|---|---|
| 0 | `REWORK`, прежний READY отозван | [HANDOFF](gate-00-product-contract-baseline/HANDOFF.md), [remediation](gate-00-product-contract-baseline/INDEPENDENT-AUDIT-REMEDIATION.md) | Завершить v2 regeneration, independent L1/L2/L3, result commit и acceptance binding |
| 1 | `BLOCKED`, isolated WIP не является integration candidate | [ARCHITECTURE](gate-01-natural-language-voice/ARCHITECTURE.md) | Не связывать Gate 0 digests до accepted binding |
| 2–8, включая 2A | `TARGET` | Research/Architecture ниже | Выполнять только после accepted handoff предыдущего Gate |

| Gate | Результат | Исследование | Архитектура |
|---:|---|---|---|
| 0 | Product Contract и воспроизводимый baseline | [RESEARCH](gate-00-product-contract-baseline/RESEARCH.md) | [ARCHITECTURE](gate-00-product-contract-baseline/ARCHITECTURE.md) |
| 1 | Natural Language и Voice Kernel | [RESEARCH](gate-01-natural-language-voice/RESEARCH.md) | [ARCHITECTURE](gate-01-natural-language-voice/ARCHITECTURE.md) |
| 2 | Scope Registry и единые document contracts | [RESEARCH](gate-02-scope-document-contracts/RESEARCH.md) | [ARCHITECTURE](gate-02-scope-document-contracts/ARCHITECTURE.md) |
| 2A | Telegram Mini App, ранний Server Control Plane и Development Worker | [RESEARCH](gate-02a-miniapp-development-control/RESEARCH.md) | [ARCHITECTURE](gate-02a-miniapp-development-control/ARCHITECTURE.md) |
| 3 | Google Foundation и Google Workspace specialist | [RESEARCH](gate-03-google-foundation/RESEARCH.md) | [ARCHITECTURE](gate-03-google-foundation/ARCHITECTURE.md) |
| 4 | Business Notes, Calendar, Tasks и effect plane | [RESEARCH](gate-04-notes-calendar-tasks/RESEARCH.md) | [ARCHITECTURE](gate-04-notes-calendar-tasks/ARCHITECTURE.md) |
| 5 | Unified Document Gateway и Windows Bridge | [RESEARCH](gate-05-document-gateway-windows-bridge/RESEARCH.md) | [ARCHITECTURE](gate-05-document-gateway-windows-bridge/ARCHITECTURE.md) |
| 6 | Multi-document Analytics | [RESEARCH](gate-06-multidocument-analytics/RESEARCH.md) | [ARCHITECTURE](gate-06-multidocument-analytics/ARCHITECTURE.md) |
| 7 | Artifact Factory и controlled writeback | [RESEARCH](gate-07-artifact-factory-writeback/RESEARCH.md) | [ARCHITECTURE](gate-07-artifact-factory-writeback/ARCHITECTURE.md) |
| 8 | Hybrid Release и 72-hour pilot | [RESEARCH](gate-08-hybrid-release-pilot/RESEARCH.md) | [ARCHITECTURE](gate-08-hybrid-release-pilot/ARCHITECTURE.md) |

## Правило использования

1. Канонический продуктовый контракт и последовательность остаются в
   [`docs/12`](../12-Эталон-MVP-1-и-дорожная-карта.md).
2. Общие связи, ownership контрактов и разрешённые межблочные зависимости
   закреплены в
   [`docs/13`](../13-Интегрированная-архитектура-MVP-1.md).
3. `RESEARCH.md` объясняет выбор и содержит первичные источники, но не является
   runtime authority.
4. `ARCHITECTURE.md` определяет TARGET своего Gate. При противоречии между
   Gate-документами действует разрешение конфликта из `docs/13` и принятого ADR.
5. Фактический CURRENT каждого Gate берётся только из accepted per-Gate handoff
   и связанного свежего evidence. Для завершённого Gate 0 точным источником
   является запечатанный
   [`HANDOFF`](gate-00-product-contract-baseline/HANDOFF.md). Файл
   [`CURRENT-STATUS`](../handoffs/CURRENT-STATUS.md) сохраняет хронологию
   прежнего локального runtime и не является authority текущей реализации Gate 0–8.
6. Реализация Gate получает отдельный exact L4, локальный change manifest,
   L1/L2/L3 и accepted handoff. Документная готовность не переносится на код.
7. Gate 2A выполняется после accepted Gate 2 и до Gate 3. Он является первым
   bounded server/Mini App release, но не заменяет финальный Gate 8 pilot.
