# Gate 4 Research Dossier — Business Notes, Calendar and Tasks

Status: `RESEARCH READY`
Evidence cut-off: 2026-07-28
Canonical baseline: repository commit `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
Scope: architecture evidence for Business Notes, Google Calendar, Google Tasks and their common durable effect lifecycle. No database, runtime, Google, Telegram, migration, commit, remote, push or deployment action was performed.

## 1. Executive verdict

The sustainable Gate 4 path is:

- **ADAPT the current SQLite/Python Core.**
- Keep Nobus Core as the only authority for owner identity, tenant scope, planning, idempotency, effect state, reconciliation, delivery and audit.
- Create capability/effect intent, durable execution job and result-delivery outbox admission atomically in one SQLite transaction.
- Use one owner- and tenant-bound effect state machine for Business Notes-derived effects, Calendar mutations and Tasks mutations.
- Treat an unproven mutation lifecycle as `PROVIDER_UNKNOWN` with provider outcome `NONE`. Never convert it to a proven outcome merely because retries were exhausted, and never tell the owner to repeat an unresolved mutation.
- Commit final provider outcome, immutable provider evidence/binding and the final owner-bound outbox atomically in one SQLite transaction; delivery recovery never re-enters provider execution.
- Retain direct official Google Calendar and Tasks APIs behind narrow Nobus adapters.
- Do not adopt Temporal, Celery, n8n, Zapier, Make, Composio or MCP as the effects authority.
- Use external connectors only as isolated read-only diagnostics or canaries if they provide a demonstrated operational benefit.

The repository already contains valuable primitives: deterministic Calendar create IDs, provider readback, Tasks action markers, fail-closed target ambiguity, SQLite leases, durable recovery and atomic delivery acknowledgement. The primary architectural defect is not absence of a queue framework; it is that these primitives do not yet form one atomic, provider-aware effect protocol.

This dossier is evidence for a target design. It does not assert runtime readiness or live Google correctness.

## 2. Research question and PASS definition

Gate 4 must make ordinary owner text or confirmed voice produce predictable, reversible behavior:

1. summarize exact-scope Business Notes and expose durable task candidates;
2. list/create/update Calendar events;
3. list/create/update/complete Google Tasks;
4. preserve exact owner, tenant, chat and topic authority;
5. avoid duplicate remote effects after duplicate ingress, process crash or lost response;
6. avoid capability/job/outbox orphans;
7. reconcile uncertain remote mutations without blind replay;
8. isolate a provider outage from Telegram ingress and unrelated domains;
9. expose explicit progress, ambiguity, conflict and unresolved status instead of generic failure.

An ideal PASS requires all of the above under deterministic tests, injected faults and an explicitly authorized live smoke. Research or architecture acceptance alone is not runtime PASS.

## 3. Evidence method

### 3.1 Evidence levels

| Level | Evidence used | Purpose |
|---|---|---|
| L1 | Official Google, Telegram and SQLite documentation; official repositories and release pages | Normative provider behavior, API limits and transport constraints |
| L2 | Canonical Nobus documentation, CURRENT code and tests at the baseline commit | Current behavior, reusable code and local failure boundaries |
| L3 | Mature third-party repositories plus explicit architectural inference | Alternative comparison and adversarial design review |

Time-sensitive facts below use the evidence cut-off above. A source version is reported where its release history exposes one. Provider quotas and commercial pricing remain subject to change and must be rechecked before implementation or procurement.

### 3.2 Canonical Nobus sources

The repository review covered:

- `AGENTS.md`;
- `docs/12-Эталон-MVP-1-и-дорожная-карта.md`;
- ADR 0009, 0011, 0012, 0013 and 0017;
- `docs/05-Спецификации-контрактов.md`;
- `docs/07-*`, `docs/08-*`;
- `docs/handoffs/CURRENT-STATUS.md`;
- `docs/handoffs/MVP-1-ISSUES.md`;
- all relevant `business_notes`, `google_calendar`, `google_tasks`, `product_effects`, Telegram queue, SQLite outbox, recovery and test code.

Nobus Memory was used only as a bounded historical source. Repository code, tests and canonical documentation remained authoritative.

## 4. CURRENT implementation findings

### 4.1 Reusable strengths

| Area | Verified CURRENT behavior | Reuse value |
|---|---|---|
| Business Notes storage | Primary identity includes tenant/chat/message; update identity is tenant/chat/update; append uses `BEGIN IMMEDIATE`; encrypted content and protected digest are stored | Strong starting point for exact-source preservation and tenant isolation |
| Business Notes binding | Group binding validates owner, chat and topic; private markers are rejected; tests cover cross-tenant and cross-topic isolation | Reuse binding and negative checks |
| Calendar create | A client event ID is derived deterministically from the idempotency key; `409` triggers GET and exact payload comparison | Retain as the Calendar create reconciliation primitive |
| Calendar target resolution | Ambiguous title/window matches fail closed | Retain, then replace follow-up title matching with durable event binding |
| Tasks | Thread-local service creation, full tasklist/task pagination, action marker, same-key conflict detection and fail-closed task ambiguity exist | Retain marker recovery and exact target resolution |
| Product effects | Tenant/actor-bound capability, durable states, execution recovery, delivery pending and atomic final delivery acknowledgement exist | Reuse the protocol vocabulary and ACK boundary |
| SQLite outbox | Fingerprints, leases, lease generations, CAS, rollback and tenant-scoped claims are tested | Reuse as the storage/concurrency foundation |

### 4.2 Root-cause map

| Symptom | Direct cause | Architectural root cause |
|---|---|---|
| Orphan `PENDING` capability | Capability issue and queue enqueue use separate transactions | Admission is a dual write rather than one invariant-preserving transaction |
| Duplicate after provider timeout | Unknown mutation may eventually become terminal text inviting a repeat | Remote outcome certainty is not represented independently from delivery state |
| Calendar concurrent overwrite | Update uses marker/read resolution without ETag precondition | Provider revision is not part of the effect target snapshot |
| Calendar worker race | One global discovery service may be reused from `asyncio.to_thread` workers | Provider transport ownership is not aligned with concurrency ownership |
| Wrong Tasks destination | A mutation without explicit list can resolve to the first tasklist | Scope registry and exact write-target authority are incomplete |
| Lost follow-up target after restart | Tasks follow-up context is process memory; Calendar has no equivalent durable binding | Conversational context is not a durable, revisioned domain record |
| False task time | A date is serialized as midnight while Tasks stores only a date | Product semantics are wider than provider semantics |
| Cross-topic note leakage | Some summary paths can aggregate a tenant beyond the exact active topic | Query scope is not always identical to ingress authority scope |
| Voice policy inconsistency | CURRENT direct reversible voice behavior and confirmed-voice Gate wording differ | Gate 1 authority policy is unresolved |
| Generic failure | Provider exceptions converge at a generic upper error path | There is no shared typed error/result contract |

### 4.3 Test coverage present and missing

Existing tests cover:

- Business Notes encryption, duplicate ingress, tamper detection and tenant/topic isolation;
- Calendar deterministic create, same-key/different-payload conflict, unique update and ambiguity;
- Tasks create replay after delivery failure, update/complete, pagination and ambiguity;
- product-effect tenant/actor binding, durable recovery and delivery acknowledgement;
- SQLite outbox rollback, leases, fencing/CAS and tenant-scoped claims.

Material gaps:

- atomic capability + job + delivery-outbox admission;
- queue-full rollback of the complete admission;
- orphan capability/job/outbox detection;
- Calendar ETag/`If-Match`, pagination, sync token and `410` reset;
- recurring master/occurrence ambiguity;
- persisted IANA timezone and frozen reference instant;
- durable provider object binding and restart-safe follow-up;
- Tasks marker collision/copy and concurrent user edit;
- tri-state Tasks patch fields;
- structured note candidate provenance and numeric selection;
- persistent provider outage remaining lifecycle `PROVIDER_UNKNOWN` with outcome `NONE`;
- action-specific owner messages for every error class.

## 5. Natural language and voice evidence

Natural language parsing is not authority. A parser or model may produce candidates, but Core must bind an effect only after validating:

- owner and tenant;
- domain/action;
- exact target ID or closed selection;
- complete payload;
- reference instant and IANA timezone;
- ambiguity set;
- source message/transcript digest;
- preview or direct-execution rule.

`dateparser` 1.4.x is a viable candidate extractor for Russian text. It supports explicit language selection, relative base and timezone settings, but its documentation warns about false positives. It should be constrained to `languages=["ru"]`, a frozen `RELATIVE_BASE`, a tenant timezone and strict rejection of incomplete/ambiguous results.

Sources:

- [dateparser documentation](https://dateparser.readthedocs.io/en/stable/index.html)
- [dateparser settings](https://dateparser.readthedocs.io/en/latest/settings.html)
- [Python `zoneinfo`](https://docs.python.org/3/library/zoneinfo.html)

Duckling would introduce a Haskell/service runtime with no demonstrated benefit for this Windows/Python MVP. New Russian-focused parsers without a mature corpus and release history are not suitable authority dependencies.

## 6. Google Calendar evidence

### 6.1 Deterministic create

Google Calendar permits a client-supplied event ID at insert. Google explicitly describes it as a way to keep the database synchronized when an insert succeeds but the client does not receive the response. Event IDs use base32hex-compatible lowercase characters and must be set at creation time.

Nobus conclusion:

- retain deterministic `event_id = f(effect identity)`;
- include calendar ID and canonical payload digest in the local binding;
- on conflict or timeout, GET the deterministic ID and compare the canonical remote projection;
- same ID and same projection means applied;
- same ID and different projection means idempotency conflict;
- absence is not automatically proof of non-application until bounded reconciliation rules complete.

Sources:

- [Events resource](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Create events](https://developers.google.com/workspace/calendar/api/guides/create-events)

### 6.2 Update concurrency

Calendar resources expose ETags. `If-Match` on update/delete prevents lost updates; a changed revision produces `412 Precondition Failed`.

Nobus conclusion:

- a mutation intent must contain an exact event ID and expected ETag;
- the adapter must not patch a target resolved only by title after planning;
- `412` is an owner-visible concurrent-change conflict and requires refresh/replan;
- it is not a safe automatic retry with the old payload.

Source: [Calendar resource versioning](https://developers.google.com/calendar/api/guides/version-resources)

### 6.3 Pagination and incremental synchronization

Calendar list returns `nextPageToken` and, after the final page, `nextSyncToken`. Incremental synchronization must preserve compatible query parameters. An invalid/expired token returns `410 Gone` and requires clearing the local synchronized projection followed by a new full sync.

Nobus conclusion:

- store sync cursor per tenant, credential subject, calendar and normalized query scope;
- commit a new token only after all pages/projections commit atomically;
- `410` starts a controlled full-resync generation and does not delete owner data;
- sync is reconciliation evidence, not authority to mutate.

Sources:

- [Synchronize resources](https://developers.google.com/workspace/calendar/api/guides/sync)
- [Events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)

### 6.4 Recurrence and timezones

A recurring series master and an occurrence have different identities. An occurrence is identified by the recurring event ID plus original start time. Recurrence rules require timezone-aware interpretation, especially across daylight-saving transitions.

Nobus conclusion:

- distinguish `single`, `series_master` and `occurrence`;
- never infer “this event” as “entire series”;
- require an explicit series/occurrence choice when the command is not closed;
- persist IANA timezone names, not only offsets;
- preserve local wall time, zone and normalized instant as separate fields.

Sources:

- [Recurring events](https://developers.google.com/workspace/calendar/api/guides/recurringevents)
- [Events resource](https://developers.google.com/workspace/calendar/api/v3/reference/events)

### 6.5 Errors, retries and quotas

Google classifies validation, authentication, permission, quota, conflict and server failures separately. Read retries can use truncated exponential backoff for quota/server errors. A mutation transport timeout is not equivalent to a rejected mutation.

At the evidence cut-off, Calendar documents default per-minute quotas of 10,000 per project and 600 per user per project. These are operational inputs, not hard-coded product constants.

Sources:

- [Calendar API errors](https://developers.google.com/workspace/calendar/api/guides/errors)
- [Calendar quota management](https://developers.google.com/workspace/calendar/api/guides/quota)

### 6.6 Python transport safety

The official Python client uses `httplib2`, whose `Http` object is not thread-safe. Each thread must own its transport/client instance.

Source: [google-api-python-client thread safety](https://googleapis.github.io/google-api-python-client/docs/thread_safety.html)

## 7. Google Tasks evidence

### 7.1 Provider identity and idempotency

Tasks insert does not expose a client-supplied task ID or a provider idempotency key. The server assigns the task ID. Therefore a Nobus create requires:

- a local effect identity;
- an exact tasklist ID;
- a bounded marker containing an unguessable/hashed Nobus effect identity and payload digest;
- post-create durable binding to server task ID;
- marker-based scan only for unresolved create reconciliation.

Sources:

- [Tasks resource](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks)
- [tasks.insert](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/insert)

### 7.2 Due-date limitation

Tasks accepts an RFC 3339 due value but stores only its date; the time component is discarded and cannot be read or written.

Nobus conclusion:

- `TasksAction.due_date` is a date, never a datetime;
- owner text containing a time must not silently become a task at false midnight;
- offer Calendar or request consent to discard the time;
- user-visible receipts say “due date”, not “at HH:MM”.

Source: [Tasks resource](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks)

### 7.3 Pagination, limits and update

Tasks list is paginated with up to 100 results per page. Current documented storage limits include 20,000 non-hidden tasks per list and 100,000 total tasks. Courtesy quota is documented separately.

Sources:

- [tasks.list](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list)
- [Tasks API limits](https://developers.google.com/workspace/tasks/limits)
- [tasks.patch](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/patch)

Tasks resources expose ETags, but the method reference does not provide a sufficiently explicit mutation-precondition guarantee for Nobus to assume production `If-Match` behavior without a contract test. The architecture must carry an expected ETag/revision slot, perform readback and keep a blocker until an authorized test proves the exact behavior.

## 8. Business Notes evidence

The current implementation already protects encrypted source notes and exact topic identities. The target must add a durable semantic layer without weakening source preservation:

- exact topic binding;
- tenant-scoped aliases;
- numbered selections bound to a snapshot revision;
- extractive summary provenance;
- stable task candidate IDs and source digests;
- explicit candidate state;
- schema and encrypted-content versioning;
- dedicated Smoke isolation.

Summary text and candidates are derived data. They must not replace or mutate the encrypted source note. A model-produced candidate is not authority to create a Google Task until Core validates the owner command and the candidate snapshot.

## 9. Durable effects patterns

### 9.1 Transactional outbox

The transactional outbox pattern atomically stores the business change and message to be relayed. Relays can still deliver more than once, so consumers must be idempotent.

Nobus conclusion:

- the transaction boundary must cover capability/effect intent, job and delivery-outbox placeholder;
- provider execution remains outside the database transaction;
- post-provider certainty is represented through durable state and evidence;
- the Google adapter remains idempotent/reconcilable;
- delivery is separately retriable and cannot re-run the provider effect.

Sources:

- [AWS transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Microservices.io transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Debezium outbox event router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)

Debezium/Kafka is not justified for a single-owner, single-host SQLite MVP. It solves a different operational scale and increases deployment and reconciliation surfaces.

### 9.2 Inbox deduplication

Telegram `update_id` provides an ingress sequencing/dedup primitive. Message identity and `message_thread_id` provide chat/topic evidence. Dedup must be tenant-bound and include a canonical source digest so an identifier collision with different content fails closed.

Telegram does not document a client idempotency key for `sendMessage`. The result-delivery edge therefore remains at-least-once unless Nobus adds a stronger application-visible protocol.

Sources:

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)
- [Bot API changelog](https://core.telegram.org/bots/api-changelog)

## 10. Whole-solution comparison

Versions are the latest stable versions observed during the evidence cut-off, not permanent pins.

| Candidate | Observed maturity/version | License | Windows/VPS/Python fit | Code reduction | Effect certainty and audit | Privacy/cost/lock-in | Verdict |
|---|---|---|---|---|---|---|---|
| Current Nobus SQLite/Python Core | Project-native; existing test and operational history | Project license | Native fit; single-host VPS/Windows | Moderate after consolidation | Best control; must close admission and reconciliation gaps | Local data, low cost, low lock-in | **ADAPT** |
| DBOS Transact Python | Active; `2.22.0` observed | MIT | Python; SQLite local/prototype, PostgreSQL recommended for production/distribution | Potentially high for generic workflow/queue code | Durable workflow IDs and steps, but external Google effects still require idempotency/reconciliation | New framework and state store coupling | **EVALUATE after Gate 8 evidence** |
| Temporal Python SDK + Server | SDK `1.27.2`; Server `1.28.x` observed | MIT | Python SDK works; server/database or paid Cloud required | High for timers/recovery | Strong workflow history; external activity remains at-least-once without provider protocol | High operations or SaaS cost; material lock-in | **REJECT for MVP** |
| Celery | `5.6.x` observed | BSD | Windows unsupported since Celery 4; broker/backend required | Moderate | Late ACK can duplicate execution; no Google-specific reconciliation | Extra infrastructure, little certainty gain | **REJECT** |
| n8n | `2.30.x` observed | Sustainable Use/fair-code plus enterprise terms | Separate Node service | High connector/UI reduction | Connector abstraction hides exact request/precondition/evidence behavior | Additional credential/data plane; licensing lock-in | **REJECT as authority** |
| Zapier / Make | Managed mature SaaS | Commercial terms | Platform-independent | Very high | Search-before-create and workflow retries are not proof of exact remote outcome | Third-party processor, task pricing, lock-in | **REJECT as authority; optional disposable canary** |
| Composio | Managed connector/MCP platform; Tasks toolkit `20260721_00` observed | Commercial terms | Easy Python/MCP integration | Very high | Managed auth/tool schema does not replace Nobus effect ledger | Additional processor and credential custody | **REJECT as authority; evaluate only for bounded auxiliary use** |

References:

- [DBOS Transact Python](https://github.com/dbos-inc/dbos-transact-py)
- [DBOS workflows](https://docs.dbos.dev/python/tutorials/workflow-tutorial)
- [DBOS steps](https://docs.dbos.dev/python/tutorials/step-tutorial)
- [DBOS database configuration](https://docs.dbos.dev/python/tutorials/database-connection)
- [Temporal Python SDK](https://github.com/temporalio/sdk-python)
- [Temporal documentation](https://docs.temporal.io/)
- [Celery documentation](https://docs.celeryq.dev/en/stable/)
- [Celery Windows support FAQ](https://docs.celeryq.dev/en/v4.3.0/faq.html)
- [n8n](https://github.com/n8n-io/n8n)
- [n8n Google Tasks](https://n8n.io/integrations/google-tasks/)
- [Composio Google Tasks](https://docs.composio.dev/toolkits/googletasks)

## 11. Connector, MCP and automation landscape

| Candidate | Capability | Limitation | Gate 4 use |
|---|---|---|---|
| Official Google Workspace MCP | Calendar list/create/update/delete in Developer Preview | Tasks absent; model-oriented tool boundary; preview status | Read-only evaluation/canary only |
| Google Workspace CLI | Discovery-generated Calendar and Tasks operations; Windows binary; structured output | Separate executable/auth surface; not an effect protocol | Read-only test oracle and operator diagnostics |
| `taylorwilsdon/google_workspace_mcp` | Broad Calendar and Tasks MCP implementation | Community credential/effect plane; release/audit dependency | Reference implementation only |
| `aaronsb/google-workspace-mcp` | Calendar/Tasks through Node/Discovery | Smaller maturity and extra runtime | Reject for Core; optional disposable evaluation |
| n8n/Zapier/Make/Composio | Ready-made auth and actions | Raw request, ETag, retry and reconciliation evidence may be hidden | Never authority; only behind Nobus ledger if later justified |

Sources:

- [Official Workspace MCP guide](https://developers.google.com/workspace/guides/configure-mcp-servers)
- [Calendar MCP release note](https://developers.google.com/workspace/calendar/release-notes)
- [Google Workspace CLI](https://github.com/googleworkspace/cli)
- [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp)
- [aaronsb/google-workspace-mcp](https://github.com/aaronsb/google-workspace-mcp)

The official MCP server was still Developer Preview at the cut-off and did not expose Tasks. No connector demonstrated a stronger idempotency or reconciliation contract than the direct APIs. Connector code reduction therefore does not outweigh the loss of deterministic evidence.

## 12. Reusable code verdict

### Reuse

- `SQLiteBusinessNotes` exact identity, encryption and source retention;
- Calendar deterministic create ID and conflict readback;
- Tasks thread-local service, pagination, exact-list normalization and action marker;
- `DurableProductEffectVault` owner/tenant binding vocabulary;
- outbox fingerprint, lease generation, CAS and atomic acknowledgement;
- existing fail-closed ambiguity and negative tenant/topic tests.

### Modify

- make complete effect admission one transaction;
- keep lifecycle state and proven provider outcome as orthogonal persisted axes;
- add durable object bindings and reconciliation evidence;
- make Calendar service thread-local;
- add Calendar ETag, pagination, sync and recurrence semantics;
- replace first-tasklist mutation fallback with explicit scope;
- add durable follow-up context and candidate snapshots;
- replace generic errors with typed owner receipts.

### Add

- effect/inbox/provider-binding/reconciliation schema;
- reconciliation worker and orphan audit;
- Calendar sync projection/cursors;
- Notes topic aliases, summary snapshots and task candidates;
- provider rate/deadline/error policy;
- deterministic fault and concurrency suite.

### Deprecate

- separate capability issue followed by non-atomic enqueue;
- converting unknown mutation to terminal failure because attempt budget ended;
- in-memory-only provider follow-up context;
- title-only target selection after a target has been resolved once;
- fixed-offset business time;
- Tasks write fallback to an arbitrary list;
- direct provider-specific generic exception text at the owner boundary.

## 13. Research conflicts and unresolved evidence

1. **Voice policy conflict:** older confirmed-voice contract and CURRENT direct reversible voice flow disagree. Gate 1 must select one normative policy; this architecture assumes confirmed voice as requested for Gate 4.
2. **CURRENT vs residual smoke:** status tables describe Business Notes as operational while ADR/status text retains group-binding/owner-message smoke as residual. Target documentation must not interpret those tables as live proof.
3. **Tasks preconditions:** ETag exists, but exact `If-Match` mutation behavior requires an authorized contract test before implementation relies on it.
4. **Telegram delivery exactly-once:** Bot API has no documented send idempotency key. Gate 8 must accept or mitigate the residual at-least-once delivery edge.
5. **SQLite deployment topology:** this design is single-host. Multi-writer network-filesystem or active/active deployment would invalidate its locking assumptions.
6. **Encryption on VPS:** Windows DPAPI cannot be treated as the target cross-platform key-management strategy.
7. **Quota/pricing drift:** Google limits and commercial connector prices must be refreshed before release/procurement.

## 14. Research acceptance

| Requirement | Result |
|---|---|
| Official Calendar create/update/sync/recurrence/timezone/error evidence | PASS |
| Official Tasks identity/due/pagination/limit evidence | PASS |
| SQLite/outbox/inbox durability evidence | PASS |
| CURRENT code/test reuse and root-cause map | PASS |
| At least three whole-solution alternatives | PASS |
| Mature connector/MCP/paid landscape and rejects | PASS |
| License, platform, privacy, cost, operational burden and lock-in comparison | PASS |
| No secrets or customer data | PASS |
| No runtime/live-write claims | PASS |

Research conclusion: `RESEARCH READY`. Architecture and implementation remain separately gated.
