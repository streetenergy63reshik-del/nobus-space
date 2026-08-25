# Журнал архитектурных решений

**Статус документа:** CANONICAL

Журнал содержит короткие ссылки на решения. Полный контекст и последствия находятся в соответствующем ADR.

| ADR | Решение | Статус решения | Реализация |
|---|---|---|---|
| [0001](adr/0001-platforma-zamenyaet-menedzhera-marketpleisa.md) | Платформа автоматизирует координацию, но человек сохраняет контроль высокорисковых действий | ACCEPTED | TARGET |
| [0002](adr/0002-determinirovannoe-yadro-smennye-llm.md) | Детерминированное Core и сменные workers | ACCEPTED | PARTIAL |
| [0003](adr/0003-kanal-prodazh-abstraktsiya.md) | Канал продаж — изолированный адаптер | ACCEPTED | TARGET |
| [0004](adr/0004-uchet-rashodov-prezhde-limitov.md) | Сначала учёт расходов, затем лимиты и блокировки | ACCEPTED | TARGET |
| [0005](adr/0005-agent-prompt-inzhener.md) | Доверенный intake формирует контракт до необязательного LLM-обогащения | ACCEPTED | TARGET |
| [0006](adr/0006-rezidentskie-proksi.md) | Доступ без официального API: residential proxies и обход защит запрещены; browser adapter — только после правовой/security проверки | PROPOSED | DEFERRED |
| [0007](adr/0007-reglament-rezervnogo-kopirovaniya.md) | Проверяемое резервное копирование и восстановление | ACCEPTED | TARGET |
| [0008](adr/0008-pravila-vneshney-zapisi.md) | Любое внешнее изменение требует связанного L4-подтверждения | SUPERSEDED by 0012 | SUPERSEDED |
| [0009](adr/0009-telegram-queue-sol-fast-timeouts.md) | Telegram intake отделён от длительного Codex execution; два read-only workers, Sol/High/Fast и отдельный двухчасовой deadline | ACCEPTED | PARTIAL |
| [0010](adr/0010-owner-library-read-scope.md) | Server-mediated path index/file-transfer библиотеки владельца без расширения worker filesystem boundary | ACCEPTED | IMPLEMENTED |
| [0011](adr/0011-durable-owner-effects-and-web-profiles.md) | Durable Telegram admission, explicit owner effects и закрытые web/network profiles | ACCEPTED | IMPLEMENTED |
| [0012](adr/0012-owner-command-authority-and-calendar.md) | Точная owner-команда разрешает обратимые действия; удаление и иные необратимые эффекты сохраняют exact L4 | ACCEPTED | IMPLEMENTED |
| [0013](adr/0013-business-notes-memory.md) | Telegram «Заметки бизнеса» хранятся локально зашифрованно, изолируются по tenant/chat/topic и не передаются внешней LLM | ACCEPTED | IMPLEMENTED |
| [0014](adr/0014-natural-product-router-and-bounded-context.md) | Естественные owner-команды маршрутизируются в закрытые профили; project/file context передаётся минимально и без прямого доступа LLM к диску | ACCEPTED | IMPLEMENTED |
| [0015](adr/0015-nobus-memory-progressive-retrieval.md) | Nobus Memory подключается через server-side progressive retrieval; exact owner save создаёт только pending-review Inbox note | ACCEPTED | IMPLEMENTED |
| [0016](adr/0016-persistent-mobile-codex-runtime.md) | Production worker использует persistent официальный Codex SDK/app-server; threads разделены по owner chat/topic, а effects остаются application-owned | ACCEPTED | RELEASE CANDIDATE |
| [0017](adr/0017-hybrid-natural-google-local-document-plane.md) | Natural Language First; hybrid Server Core + Windows Local Library Bridge; единый Google/local document lifecycle и application-owned writeback | ACCEPTED; scoped by 0022 | PARTIAL / DEFERRED |
| [0018](adr/0018-cross-gate-mvp1-integration.md) | Единая интеграция Gate 0–8: atomic effects, opaque document identity, честные Google preconditions, single-node SQLite и global poller fencing | ACCEPTED; scoped by 0022 | PARTIAL / DEFERRED |
| [0019](adr/0019-owner-service-filesystem-and-runtime-decisions.md) | Owner decisions: CLI-first Codex, Drive-wide read, controlled full owner-root workspace, Healthchecks.io → Gmail и benchmark-gated paid services | ACCEPTED; scoped by 0022 | PARTIAL / DEFERRED |
| [0020](adr/0020-early-miniapp-and-specialist-workers.md) | Telegram Mini App is required; historical Server/Development Control Gate 2A topology is scoped by ADR 0022 | ACCEPTED; scoped by 0022 | THIN MVP ACTIVE / FULL 2A FROZEN |
| [0021](adr/0021-post-gate0-agent-roles-and-downstream-integration.md) | Historical post-seal role/verification overlay; active process and roadmap are scoped by ADR 0022 | ACCEPTED; scoped by 0022 | HISTORICAL / PARTIAL |
| [0022](adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md) | Forward-only rebaseline: thin Telegram Mini App + existing local Core; full Gate 2A frozen; one candidate-bound delivery workflow | ACCEPTED | CURRENT PROCESS / TARGET PRODUCT |

## Правила статусов ADR

- `PROPOSED` — решение обсуждается и не является разрешением на реализацию или действие.
- `ACCEPTED` — решение обязательно для новой разработки.
- `SUPERSEDED` — заменено более новым ADR; старый файл сохраняется для истории.
- `REJECTED` — рассмотрено и не принято.

Статус реализации ведётся отдельно, потому что принятое решение может ещё не
быть реализовано. `ACCEPTED; scoped by 0022` означает, что
обязателен только незаменённый scope старого решения; исторический ADR не
переписывается.

## Scoped supersession by ADR 0022

| Source | Retained | Superseded / deferred |
|---|---|---|
| docs 06/07 | product/runtime approval semantics | nothing |
| docs 12/13 | sealed historical baseline; security, tenant, effect, evidence and recovery invariants | Gate 0–8 topology, full rollout and delivery sequence |
| ADR 0017 | Natural Language First, deterministic Core, application-owned effects | early Server Core/document-platform sequence |
| ADR 0018 | Core reuse, atomic admission/outbox, idempotency and poller fencing | Gate 0–8 integration sequence as active MVP roadmap |
| ADR 0019 | owner/secret/filesystem boundaries and recovery discipline | mandatory server/Bridge steps outside the vertical slice |
| ADR 0020 | Mini App required, one Core/state/effect authority, client not authority | full Server Control Plane, universal Agent Registry and Gate 2A sequence |
| ADR 0021 | Gate 0 binding, worker distrust and independent frozen-candidate review | six-role runtime registry, Gate 1→2→2A→3–8 order and platform handoffs |
| full Gate 2A | narrow security requirements reused by ADR 0022 | **FROZEN / NOT CURRENT** topology, deployment and acceptance matrix |

Security, tenant isolation, effect authority, idempotency, evidence binding,
audit trail and recovery invariants remain active.

Нормативное изменение получает owner decision и candidate-bound review по
своему риску. Обычные локальные docs/code/tests/commit не требуют formal
quality-L4. Product/runtime `ApprovalRequest/ApprovalDecision` и внешние
авторизации остаются отдельными правилами.
