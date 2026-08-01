# Архитектурный пакет Gate 0–8, включая Gate 2A

**Статус:** TARGET DESIGN

**CURRENT implementation на 1 августа 2026 года:** Gate 0 READY и immutable
accepted; Gate 1 `READY TO START`; Gate 2 и Gate 2A ещё заблокированы
непройденными predecessors

result_commit: f5086b2a71a9ae22be3c858ff69453287f6925da
result_tree: 2e3248eb295b1627d36f196c26dfc21c6ebd90fd

**База исследования:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`

**Дата исследования:** 28 июля 2026 года

Эта папка содержит исследовательское основание и детальную архитектуру каждого
Gate MVP-1. Исследование и архитектура сами по себе не доказывают реализацию,
работающий runtime или PASS соответствующего Gate. Gate 0 READY повторно
доказан после независимого аудита: sealed `22/22`, trusted runtime capture,
independent L1/L2/L3 и отдельный immutable acceptance binding.

## Текущий implementation status

| Gate | Статус | Evidence | Следующий шаг |
|---:|---|---|---|
| 0 | `READY`, immutable accepted | [ACCEPTANCE](gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json), [HANDOFF](gate-00-product-contract-baseline/HANDOFF.md), [remediation](gate-00-product-contract-baseline/INDEPENDENT-AUDIT-REMEDIATION.md) | Сохранять result commit/tree неизменными |
| 1 | `READY TO START`, implementation ещё не начат | [ARCHITECTURE](gate-01-natural-language-voice/ARCHITECTURE.md) | Выдать отдельный Gate 1 L4; VPS/SSH не требуются |
| 2 | `BLOCKED` до accepted Gate 1 | [ARCHITECTURE](gate-02-scope-document-contracts/ARCHITECTURE.md) | После Gate 1 подтвердить metadata-only owner root и TestTemp Gate 2 |
| 2A | `BLOCKED` до accepted Gate 2 | [ARCHITECTURE](gate-02a-miniapp-development-control/ARCHITECTURE.md) | Сначала offline candidate; VPS/SSH/DNS/TLS — только отдельное live L4 после PASS |
| 3–8 | `TARGET` | Research/Architecture ниже | Выполнять последовательно после accepted handoff predecessor |

Практический порядок действий владельца, включая независимые Git SSH и VPS SSH,
описан в [owner-runbook](../14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md).

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
