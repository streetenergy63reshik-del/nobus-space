# Historical Gate architecture index

**Статус:** HISTORICAL SEALED BASELINE / FROZEN WIP
**Active roadmap:** [ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)

Gate 0–8 package сохраняется как исследовательский и digest-bound historical
baseline. Он не является active Definition of Done MVP-1. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.

## Status map

| Scope | Фактический статус | Authority / правило |
|---|---|---|
| Gate 0 | `ACCEPTED`, sealed `22/22` | historical acceptance @ `f5086b2a71a9ae22be3c858ff69453287f6925da`; bytes/evidence immutable |
| PRE-G1 / ADR 0021 | historical accepted overlay | сохранён byte-identical; active role/Gate sequence superseded ADR 0022 |
| Gate 1 design | sealed historical TARGET | architecture file не доказывает implementation |
| Gate 1 implementation WIP | `HOLD / NOT_ACCEPTED` | dirty 86-path worktree @ `db0a24e...`; preserve/reuse only by future exact diff |
| Gate 2 | historical/deferred | не prerequisite ближайшего Mini App slice |
| Full Gate 2A | **FROZEN / NOT CURRENT** | security ideas reused narrowly; server Core/Agent Registry/Development Control topology не активна |
| Gate 3–8 | historical/deferred | backlog до прямой потребности коммерческого vertical slice |

## Gate 0 binding

- [Acceptance](gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json)
- [Handoff](gate-00-product-contract-baseline/HANDOFF.md)
- [Normative catalog](gate-00-product-contract-baseline/product/normative-catalog.json)

Все 20 `required_sources`, acceptance, evidence, manifests, corpus и
verification остаются привязанными к старой revision/digest. ADR 0022 не
регенерирует и не переписывает их.

## Historical research/design navigation

| Gate | Research | Architecture |
|---:|---|---|
| 0 | [Research](gate-00-product-contract-baseline/RESEARCH.md) | [Architecture](gate-00-product-contract-baseline/ARCHITECTURE.md) |
| 1 | [Research](gate-01-natural-language-voice/RESEARCH.md) | [Architecture](gate-01-natural-language-voice/ARCHITECTURE.md) |
| 2 | [Research](gate-02-scope-document-contracts/RESEARCH.md) | [Architecture](gate-02-scope-document-contracts/ARCHITECTURE.md) |
| 2A | [Research](gate-02a-miniapp-development-control/RESEARCH.md) | [Architecture](gate-02a-miniapp-development-control/ARCHITECTURE.md) |
| 3 | [Research](gate-03-google-foundation/RESEARCH.md) | [Architecture](gate-03-google-foundation/ARCHITECTURE.md) |
| 4 | [Research](gate-04-notes-calendar-tasks/RESEARCH.md) | [Architecture](gate-04-notes-calendar-tasks/ARCHITECTURE.md) |
| 5 | [Research](gate-05-document-gateway-windows-bridge/RESEARCH.md) | [Architecture](gate-05-document-gateway-windows-bridge/ARCHITECTURE.md) |
| 6 | [Research](gate-06-multidocument-analytics/RESEARCH.md) | [Architecture](gate-06-multidocument-analytics/ARCHITECTURE.md) |
| 7 | [Research](gate-07-artifact-factory-writeback/RESEARCH.md) | [Architecture](gate-07-artifact-factory-writeback/ARCHITECTURE.md) |
| 8 | [Research](gate-08-hybrid-release-pilot/RESEARCH.md) | [Architecture](gate-08-hybrid-release-pilot/ARCHITECTURE.md) |

Research и Architecture объясняют старый TARGET, но не определяют CURRENT и не
разрешают implementation/live effect.

## What ADR 0022 reuses

- Telegram `initData`: exact bot/owner/signature/freshness/replay;
- exact Host/Origin, CSP, body/time/rate bounds и in-memory opaque session;
- client is not authority;
- tenant/task-bound status/result/artifact projection;
- one Core/queue/state/effect authority;
- idempotency, provider-vs-delivery unknown и recovery invariants.

## What stays frozen

- Linux/VPS Core and Telegram custody migration;
- universal Agent Registry and peer-to-peer/specialist platform;
- generic Development Control plane and Windows Development Worker;
- agents/health/diff/evidence Control Center;
- Gate 3–8 handoffs and full Gate 2A acceptance matrix;
- Gate-specific L4 templates as instructions for local development.

Active next slice:
**thin Telegram Mini App owner authentication + read-only task list/detail over
the existing local Core/state**.
