# Gate index

**Статус:** ACTIVE C1 GATE CANDIDATE + HISTORICAL SEALED BASELINE
**CURRENT:** `C1 CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING`; `DEPLOYMENT REVISION UNVERIFIED`; `MVP-2 HOLD`
**Active roadmap:** [C1 acceptance](gate-c1-semantic-task-compiler/ACCEPTANCE.md)
и [C2 handoff](gate-c1-semantic-task-compiler/HANDOFF.md).
Редакционная product roadmap остаётся `LOCAL EDITORIAL WIP / PUBLICATION HOLD`
и не входит в published tree.

Gate 0–8 package сохраняется как исследовательский и digest-bound historical
baseline. Он не является active Definition of Done MVP-1. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.
Тонкий MVP-1 Telegram Mini App и один существующий Core по-прежнему задаёт
[ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md).

**Один Gate = одна Codex-задача = один пользовательский чат.** Active
closure-roadmap содержит ровно C0–C6; Txx/Cxx и R01–R47 — внутренние
checkpoints, не отдельные пользовательские чаты.

## Active closure package

| Gate | Статус | Package / boundary |
|---|---|---|
| C0 — единая истина и контракт | `PUBLISHED / ACCEPTED` @ `70085f8...`, tree `3a31914a...` | [handoff](gate-c0-mvp1-truth-contract/HANDOFF.md), [schema](gate-c0-mvp1-truth-contract/semantic-contract.schema.json), [registry](gate-c0-mvp1-truth-contract/capability-registry.v1.json), [corpus](gate-c0-mvp1-truth-contract/semantic-gold-corpus.v1.json) |
| C1 — универсальное семантическое понимание | `CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING` | [acceptance](gate-c1-semantic-task-compiler/ACCEPTANCE.md), [evidence](gate-c1-semantic-task-compiler/EVIDENCE.json), [handoff](gate-c1-semantic-task-compiler/HANDOFF.md) |
| C2 — voice parity и ASR qualification | HOLD до принятого опубликованного C1 | Faster-Whisper остаётся CURRENT до bake-off |
| C3 — стабильность Core/backend/worker | HOLD до C2 | queue/state/retry/status/recovery |
| C4 — завершённый frontend/user journey | HOLD до C3 | Telegram/Mini App E2E |
| C5 — operations/recovery/security | HOLD до C4 | health/ingress/backup/cleanup/rollback |
| C6 — frozen release и owner acceptance | HOLD до C5 | exact publication/activation/readback/acceptance |

## Historical status map

| Scope | Фактический статус | Authority / правило |
|---|---|---|
| Gate 0 | `ACCEPTED`, sealed `22/22` | historical acceptance @ `f5086b2a71a9ae22be3c858ff69453287f6925da`; bytes/evidence immutable |
| PRE-G1 / ADR 0021 | historical accepted overlay | сохранён byte-identical; active role/Gate sequence superseded ADR 0022 |
| Gate 1 design | sealed historical TARGET | architecture file не доказывает implementation |
| Gate 1 implementation WIP | `HOLD / NOT_ACCEPTED` | dirty 86-path worktree @ `db0a24e...`; preserve/reuse only by future exact diff |
| Gate 2 | historical/deferred | не prerequisite ближайшего Telegram Mini App slice |
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

Active implementation truth находится в
[CURRENT-STATUS](../handoffs/CURRENT-STATUS.md), а не в исторических Gate-файлах.
Published source/history остаются evidence только в своих revision/digest
границах. Current acceptance переоткрыта; следующий Gate после публикации C1 —
C2, а не historical G7/G8 sequence.
