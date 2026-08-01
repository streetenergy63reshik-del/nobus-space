# ADR 0021 — Post-Gate-0 роли агентов и downstream integration

**Статус ADR:** ACCEPTED

**Статус реализации:** TARGET; открывает отдельный Gate 1 cycle

**Дата:** 1 августа 2026 года

## Контекст и точная binding

Это решение является forward-only `post-seal overlay` после immutable
acceptance Gate 0. Оно связано с:

- [`GATE-0-ACCEPTANCE.json`](../gates/gate-00-product-contract-baseline/GATE-0-ACCEPTANCE.json),
  `result_commit = f5086b2a71a9ae22be3c858ff69453287f6925da` и
  `result_tree = 2e3248eb295b1627d36f196c26dfc21c6ebd90fd`;
- [`normative-catalog.json`](../gates/gate-00-product-contract-baseline/product/normative-catalog.json),
  который фиксирует closed `agent_roles` и SHA-256 всех `required_sources`.

После seal обнаружены два ограничения чтения принятого TARGET:

1. ADR 0020 перечисляет пять specialist profiles, но catalog и Gate 2A
   содержат шесть, включая `verification_specialist`.
2. Gate 5–8 architectures не повторяют все cross-Gate boundaries из уже
   принятых docs 12/13 и Gate 2A.

Gate 0 не переоткрывается. Этот overlay уточняет только role vocabulary,
specialist authority и перечисленные ниже Gate 5–8 integration clauses.
Acceptance, catalog, evidence, ADR 0020, docs 12/13 и Gate 5–8 architectures
остаются byte-identical. Все остальные clauses sealed источников сохраняют
принятый смысл.

## Решение и приоритет

Для новой разработки этот ACCEPTED ADR имеет приоритет post-seal overlay над
ограниченными формулировками ADR 0020 и individual Gate 5–8 architectures.
Он не заменяет их целиком и не меняет Gate 0 acceptance binding.

### 1. Closed AgentRole

MVP-1 имеет ровно шесть execution roles:

<!-- closed-agent-roles:start -->
- `general_orchestrator_worker`
- `google_workspace_specialist`
- `research_analytics_specialist`
- `content_studio_specialist`
- `development_specialist`
- `verification_specialist`
<!-- closed-agent-roles:end -->

Роль может быть зарегистрирована как `disabled/not_implemented` до своего
Gate, но это не создаёт другой vocabulary и не выдаёт capability раньше PASS.

### 2. Один Core и закрытая specialist authority

В системе один Nobus Core. Он остаётся единственным orchestrator и владельцем
policy, tenant/scope binding, routing, capabilities, approvals, durable state,
verification orchestration, effects, reconciliation и delivery.

Только Core создаёт typed `AgentDispatch`, принимает closed `WorkerResult`,
проверяет schema/digest/tenant/capability binding и выбирает следующий шаг.
peer-to-peer authority запрещена: specialist workers не вызывают друг друга и
не назначают себе роли, tools, scope, budget или capabilities.

provider credentials не передаются specialist. Любой specialist не выполняет external effects.
OAuth, Telegram token, filesystem/Git authority и provider
mutation принадлежат только application-owned adapters за Core boundary.

### 3. Независимая verification role

`verification_specialist` получает только exact candidate/result digest,
закрытый verification profile и минимальные evidence refs. Он независим от
проверяемого исполнителя и не может проверять или одобрять собственную работу.
Core отклоняет self-review, совпадение maker/verifier identity и receipt,
который не связан с текущим candidate.

### 4. Один generic effect plane

Gate 2A создаёт один generic effect plane под authority Core. Gate 4 расширяет
его typed Notes/Calendar/Tasks payloads, а Gate 7 переиспользует его для
artifact writeback; второй effect engine запрещён. Specialist result сам по
себе не является разрешением или внешним эффектом.

### 5. Development Worker и Document Bridge

Gate 2A Development Worker и Gate 5 Document Bridge имеют разные Windows service identities,
разные queue namespaces и разные capability sets:

| Boundary | Development Worker | Document Bridge |
|---|---|---|
| Service identity | отдельная development identity | отдельная document identity |
| Queue namespace | `development_jobs.v1` | `document_jobs.v1` |
| Capabilities | registered repository, isolated worktree, Codex, tests, local candidate | closed document search/read и отдельно pinned Gate 7 write v2 |
| Запрет | нет owner-document authority | нет Git/Codex/development authority |

Document Bridge не исполняет development jobs. Development Worker не получает document authority.
Они могут переиспользовать только transport/fencing
library; device credentials, ACL, queue lease, registry и capability digest не
переиспользуются между identities. Unknown namespace/operation/version
отклоняются fail closed.

### 6. Gate 6 analytical result

Gate 6 возвращает один closed `AnalysisResult`: строгий versioned contract,
unknown fields отклоняются. Он связывает request/plan/source revisions,
observed/calculated facts, conflicts, calculation manifests, limitations,
verification refs и один `result_digest`.

Deterministic extraction, reconciliation и calculations принадлежат Core-owned
analytical components. Модель может предложить plan/narrative/check, но не
является fact, formula, conflict, revision или verification authority.

### 7. Gate 7 verified source

Gate 7 принимает только verified analytical source, связанный с closed
`AnalysisResult` и требуемыми independent verification refs. Gate 7 не перечитывает источники и не пересчитывает факты;
он компилирует один `ArtifactDocument`, проверяет format parity и передаёт
approved effect в тот же
generic effect plane.

### 8. Gate 8 final integration

Gate 8 — финальная интеграция уже существующих Core/Mini App, Development Worker и Document Bridge,
их immutable artifacts, identities, fencing, composite health, backup/restore,
full smoke и 72-hour pilot. Gate 8 не является первым server deployment:
bounded Core/Mini App server release уже принадлежит
Gate 2A.

Gate 8 не объединяет Windows identities и не создаёт второй Core, poller,
queue/effect authority или deployment path.

### 9. Gate sequence

Gate 2A выполняется после accepted Gate 2 и до Gate 3. PRE-G1 открывает только
Gate 1. Gate 2 остаётся `BLOCKED` до accepted Gate 1; Gate 2A остаётся
`BLOCKED` до accepted Gate 2. Ни один статус READY не является L4 на
implementation, server activation или внешний effect.

## Последствия

Положительные:

- Gate 1 получает один exact role vocabulary;
- verification становится отдельной проверяемой ролью без self-approval;
- Windows code/document authority нельзя случайно объединить;
- Gate 6–8 handoffs не создают второй calculation/effect/deployment plane;
- immutable Gate 0 остаётся воспроизводимым evidence snapshot.

Цена: новые разработчики обязаны читать ADR 0021 вместе с sealed source, если
затронута одна из перечисленных clauses. Это намеренный audit trail, а не
совместимость двух активных архитектур.

## Проверка

Решение защищает
[`tests/test_pre_gate1_architecture_integration.py`](../../tests/test_pre_gate1_architecture_integration.py).
Тест проверяет exact roles, overlay priority, authority/identity/effect
boundaries, Gate order, Gate 6–8 handoffs, exact acceptance commit/tree и
SHA-256 каждого `required_sources` catalog entry.

Этот ADR не разрешает Gate 1 implementation, runtime/Scheduler операции,
credentials, SSH/VPS/DNS/TLS/BotFather, remote, push, deploy или публикацию.
