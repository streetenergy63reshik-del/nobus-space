# Документация Nobus Space

**Актуально на:** 9 сентября 2026 года. C0–C5 приняты и опубликованы. Квалификационный экземпляр C6 сейчас остановлен; исправление зависшего приёма включено, исправление промптов проверено и опубликовано, но ожидает включения. Итоговая приёмка, постоянный режим и v1.0.2 не завершены.

Начните с [текущего статуса](handoffs/CURRENT-STATUS.md), [пакета C6](gates/gate-c6-release/HANDOFF.md) и [эксплуатационной инструкции](08-Runbook-эксплуатации.md). Точная история проверки кода — [PROMPT-RECHECK-10](gates/gate-c6-release/PROMPT-RECHECK-10.md).

Тонкие Telegram и Mini App используют один локальный Core по ADR 0022/0023. Полный распределённый Gate 2A остаётся FROZEN / NOT CURRENT; MVP2 HOLD. Редакционные документы 15/16 сохраняются как неопубликованный WIP и не подменяют принятый продукт.

## Иерархия источников

1. Системная безопасность, прямое текущее решение владельца и ближайший
   `AGENTS.md`.
2. Последний применимый `ACCEPTED` ADR; для активной MVP topology и delivery
   workflow это ADR 0022.
3. Exact Git revision с code/tests и связанными воспроизводимыми checks.
4. [CURRENT-STATUS](handoffs/CURRENT-STATUS.md) как короткая проекция
   фактического состояния.
5. Historical sealed contracts/evidence только в границах revision/digest, к
   которым они приняты.
6. Research, старые handoff, отчёты и Nobus Memory — reference data, а не
   authority новой revision.

Git-репозиторий — источник истины для code, tests, ADR, CURRENT и постоянной
документации. GitHub `main` и release tags становятся каноном принятой
опубликованной истории только после разрешённых push/PR/merge и проверки exact
remote SHA. Наличие `origin` этого не доказывает. Nobus Memory хранит только
pointer, короткий status, decisions и freshness.

## Активный короткий комплект

1. [Единый документ проекта](01-Единый-документ-проекта.md) — продуктовая
   граница тонкого MVP-1.
2. [Глоссарий](02-Глоссарий.md) — единые термины.
3. [Архитектурный обзор](03-Архитектурный-обзор.md) — текущая и целевая thin
   topology.
4. [Журнал ADR](04-Журнал-ADR.md) и
   [ADR 0022](adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)
   и [ADR 0023](adr/0023-modality-neutral-semantic-admission-and-core-decision.md),
   [ADR 0025](adr/0025-miniapp-session-and-request-recovery.md) и
   [ADR 0026](adr/0026-channel-neutral-product-projection.md) и [ADR 0027](adr/0027-miniapp-bounded-admission-reconciliation.md) — topology, semantic admission,
   восстановление сессии/запроса и общая продуктовая проекция.
5. [CURRENT-STATUS](handoffs/CURRENT-STATUS.md) — branch/revision, WIP,
   blockers, checks и следующий slice.
6. [Runbook](08-Runbook-эксплуатации.md) — действующий Telegram runtime и
   действующие процедуры C6 и граница постоянного режима.
7. [Контекст продукта](11-Контекст-продукта.md) — безопасная coarse-проекция
   без подвижных SHA.
8. [Workspace inventory](handoffs/WORKSPACE-INVENTORY.md) — роли repo,
   worktrees и recovery; точное live-состояние всегда читается из Git.
9. [Owner inputs](14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md) —
   оставшиеся пользовательские сценарии, точное переключение и итоговая приёмка.
10. [Gate index](gates/README.md) — принятые C0–C5, текущий C6 и исторические Gate.
11. [C0 handoff](gates/gate-c0-mvp1-truth-contract/HANDOFF.md) — exact
    predecessor/contract C1.
12. [C1 acceptance](gates/gate-c1-semantic-task-compiler/ACCEPTANCE.md) и
    [передача C1 → C2](gates/gate-c1-semantic-task-compiler/HANDOFF.md) — принятый
    опубликованный C1, доказательства и условия старта C2.
13. [Принятый C2 handoff](gates/gate-c2-voice-parity/HANDOFF.md) и
    [индекс доказательств](gates/gate-c2-voice-parity/EVIDENCE.json) — опубликованный
    voice parity, принятый ASR и закрытая B02; исторические FAIL сохранены.
14. [C3 handoff](gates/gate-c3-core-stability/HANDOFF.md) — принятые recovery/result/artifact contracts.
15. [C4](gates/gate-c4-frontend-journey/ACCEPTANCE.md) — frontend/user journey, проверки и граница передачи C5.

## Сохранённые контракты

- [docs 06](06-Регламент-качества-L1-L4.md) и
  [docs 07](07-Правила-внешней-записи.md) остаются авторитетными для
  product/runtime approval semantics. Они не задают частоту review локальной
  разработки Codex.
- [docs 12](12-Эталон-MVP-1-и-дорожная-карта.md),
  [docs 13](13-Интегрированная-архитектура-MVP-1.md), ADR 0017–0020 и все Gate
  `ARCHITECTURE.md` являются byte-identical sealed baseline Gate 0.
- ADR 0022 supersedes docs 12/13, ADR 0020 и full Gate 2A только в части
  topology и последовательности поставки; security, tenant isolation, effect
  authority, idempotency, evidence binding, audit и recovery сохраняются.
- [ADR 0021](adr/0021-post-gate0-agent-roles-and-downstream-integration.md)
  остаётся историческим overlay; его active role/Gate sequence и test mapping
  superseded ADR 0022 без изменения старого файла.

## CURRENT / TARGET

- `CURRENT` — факт exact revision/runtime, подтверждённый воспроизводимой
  проверкой.
- `TARGET` — принятое направление, ещё не доказанное кодом.
- `FROZEN / NOT CURRENT` — сохранённый design/WIP, который не является
  активным путём реализации.
- `HOLD / NOT_ACCEPTED` — существующий кандидат без принятого verdict.

Документный статус не превращает TARGET в CURRENT. При противоречии работа
останавливается только в затронутой части, finding классифицируется, а
forward-only решение фиксируется новым ADR.

## Процесс поставки

`TASK -> WIP_ITERATION -> CHECKPOINT -> GATE_CANDIDATE -> MERGE -> RELEASE_PRODUCTION`

Обычный WIP получает target L1. Полный независимый L1/L2/L3 выполняется один
раз по frozen coherent candidate. Формальный quality-L4 нужен только перед
удалением данных с ПК или критическим изменением кабинета маркетплейса.
Runtime `ApprovalRequest/ApprovalDecision` может быть строже для конкретного
product effect.

## Правило изменения

- Обновлять активные файлы на месте; не создавать `v2`, `final`, dated copy
  или второй handoff.
- Не менять digest-bound Gate 0 sources/evidence задним числом.
- Сохранять CURRENT/TARGET и program/runtime authority раздельно.
- Не записывать credentials, tokens, cookies, raw payload, audio, local secret
  paths или данные другого tenant.

Исправление зависшего приёма Mini App в C6 описано в [ADR 0027](adr/0027-miniapp-bounded-admission-reconciliation.md) и [рабочем пакете](gates/gate-c6-release/INTAKE-CORRECTION-07.md). Исправление приёма включено на e3fbaf9; исправление промптов опубликовано через PR №28 и ещё не включено.
