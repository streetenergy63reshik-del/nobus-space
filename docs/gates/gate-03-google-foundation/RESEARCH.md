# Gate 3 Research Dossier — Google Foundation

Status: `RESEARCH READY`
Evidence cut-off: 2026-07-28
Canonical baseline: repository commit `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
Scope: design evidence for Google Workspace, Google AI, identity, resilience, cost, retention and observability. No runtime, OAuth, billing or Google-side changes were performed.

## 1. Executive verdict

The sustainable Google foundation for Nobus is:

- **ADOPT** official Google Workspace REST APIs and the official `google-genai` Python SDK.
- Use **Vertex AI as the primary, isolated Google-specialist gateway**. It is a subordinate inference provider, not the Nobus control plane.
- Restrict official Workspace MCP and Google Workspace CLI to **read-only canary and diagnostics**. Neither is production authority or an effects path.
- Keep policy, owner identity, closed DTO validation, idempotency, reconciliation, budget and telemetry in **Nobus Core**.
- Never give a model OAuth or refresh tokens, and never let it execute an effect.
- Migrate from Desktop OAuth to a separate Web OAuth/token broker through fresh consent; do not copy a desktop token file. Use Workload Identity Federation (WIF) or another keyless service identity for Google Cloud.
- Isolate Google failures so Telegram ingress and the Nobus Core loop remain available.

This verdict is an **architecture target**, not a statement that the current repository already implements it.

## 2. Evidence method and confidence

### 2.1 Source levels

| Level | Meaning | Use in this dossier |
|---|---|---|
| L1 | Official product/API/security/pricing documentation or official Google-maintained repository | Normative capability, limit, security and lifecycle claims |
| L2 | Repository code, tests and canonical Nobus documentation at the baseline commit | CURRENT state and integration fit |
| L3 | Maintained third-party repository or reasoned synthesis | Candidate evaluation and architecture inference only |

All time-sensitive external claims below were rechecked against their linked sources with an evidence cut-off of 2026-07-28. “Fact” means directly supported by a cited source or the canonical repository. “Conclusion” means the Nobus-specific interpretation of those facts.

### 2.2 Canonical Nobus evidence

The repository assessment covered `AGENTS.md`, `docs/12`, ADR 0002, 0011, 0012 and 0017, `docs/05`, `docs/07`, `CURRENT-STATUS`, `MVP-1-ISSUES`, `WORKSPACE-INVENTORY`, and all `src/integrations/google_*` code and corresponding tests at the canonical baseline. Historical Nobus Memory was not used as authority.

The canonical dependency labels are:

1. Gate 4 — Business Notes, Calendar и Tasks.
2. Gate 5 — Unified Document Gateway и Windows Bridge.
3. Gate 6 — Multi-document Analytics.
4. Gate 7 — Artifact Factory и writeback.
5. Gate 8 — Hybrid Release и 72-часовой pilot.

## 3. CURRENT baseline: verified repository capabilities

### 3.1 Reusable strengths

| Area | Verified CURRENT fact | Architectural value |
|---|---|---|
| Contracts | `ContractModel` is strict, frozen and rejects extra fields; contract digests use canonical JSON and SHA-256; sensitive key markers are rejected | Reuse this contract discipline for every Google boundary |
| Transport | Authorized-user credentials are loaded, expired credentials are refreshed, discovery cache is disabled, connect/request timeouts exist, and retries default to zero | Reuse bounded transport principles; replace direct token-file ownership |
| Calendar | Deterministic event IDs, conflict readback and payload comparison exist; ambiguous or unauthorized operations fail closed | Reuse deterministic create and reconciliation behavior |
| Tasks | Mutation attempts are not blindly retried; action markers and same-key locking support unknown-outcome recovery; pagination is bounded | Reuse marker-based reconciliation and serialized ownership |
| Drive | Read-only search/link/download has size, host, request-budget, pagination and ambiguity controls | Reuse containment and planning; add native Docs/Sheets APIs |
| Tests | Adversarial, durable, pagination, thread-safety, scope, reconciliation and containment cases exist | Extend the same style into a Gate 3 contract/fault/security suite |

### 3.2 Gaps that Gate 3 must close

Facts from the code and tests:

- Workspace user credentials are still loaded from an authorized-user file inside the provider adapter.
- Calendar and Tasks have product-specific resilience logic, but there is no shared provider health, circuit, budget or telemetry contract.
- Drive is a bounded read gateway, not a unified Docs/Sheets semantic API.
- There is no official Gemini/Vertex gateway, model budget governor, retention routing or model-output DTO.
- There is no server-side Web OAuth/token broker topology or WIF-backed Cloud identity.
- Workspace MCP/CLI is not part of CURRENT production behavior.

Conclusion: the code has useful safety primitives, but it does not yet satisfy the Gate 3 target. The correct path is incremental adaptation of the existing Core and adapters, not a second orchestration framework.

## 4. Official Google AI solution landscape

### 4.1 SDK and hosting surfaces

| Candidate | Verified facts | Nobus conclusion |
|---|---|---|
| `google-genai` | Official unified Python SDK for Gemini Developer API and Vertex AI. Latest observed release: `v2.14.0`, 2026-07-22. [SDK releases](https://github.com/googleapis/python-genai/releases), [Vertex SDK overview](https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview) | **Adopt.** One adapter can keep provider switching explicit while Vertex remains primary |
| Vertex AI | Google Cloud identity, project isolation, Cloud billing, regional/global endpoints, enterprise data-governance controls and optional request/response logging. [Vertex generative AI](https://cloud.google.com/vertex-ai/generative-ai/docs/overview), [Zero data retention](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention) | **Primary Google-specialist gateway.** Use keyless Cloud identity and Core-side routing |
| Gemini Developer API | API-key/OAuth developer surface with paid and free tiers, Files API and rapid capability access. [Gemini API](https://ai.google.dev/gemini-api/docs), [Pricing](https://ai.google.dev/gemini-api/docs/pricing) | Optional paid fallback for explicitly permitted lower data classes; never a transparent fallback for confidential data |
| Google ADK | Official agent framework, Apache-2.0. Latest observed 2.x release: `v2.5.0`, 2026-07-16. [ADK](https://adk.dev/), [releases](https://github.com/google/adk-python/releases) | **Do not adopt as a second runtime.** Borrow patterns only if a concrete adapter need appears |
| Gemini CLI | Official, Apache-2.0 CLI with tools, shell/filesystem and MCP integrations. [Repository](https://github.com/google-gemini/gemini-cli) | Developer investigation only; reject in production due to ambient tool authority |

### 4.2 Model control features

| Capability | Official fact | Safe Nobus use | Boundary |
|---|---|---|---|
| Structured output | Gemini accepts a supported subset of JSON Schema and SDK schema types; valid syntax does not guarantee semantic correctness. [Structured output](https://ai.google.dev/gemini-api/docs/structured-output) | Generate a closed result candidate, then validate in Core | Never treat schema conformance as authorization |
| Function calling | Models can propose function calls; the application decides whether and how to run them. [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) | At most, map a proposal into a closed, non-effect DTO | Do not expose effectful tools to the model |
| Context caching | Gemini supports implicit caching and explicit TTL-based caches; explicit cache default TTL is one hour. [Context caching](https://ai.google.dev/gemini-api/docs/generate-content/caching) | Only for allowed, stable, repeatedly used context after retention classification | No confidential material by default; Core owns cache creation/deletion |
| Files API | Up to 2 GB per file and 20 GB per project; uploaded files are automatically deleted after 48 hours and are not a document store. [Files API](https://ai.google.dev/gemini-api/docs/files) | Optional transient ingestion for permitted data classes | Not a Workspace sync plane or evidence store |
| Batch API | Asynchronous service with a target completion window of 24 hours and discounted pricing. [Batch API](https://ai.google.dev/gemini-api/docs/batch-api) | Gate 6 non-interactive analytics with durable job state | Never for owner-interactive effects |
| Grounding with Search | Billed by search queries and subject to provider retention rules. [Grounding](https://ai.google.dev/gemini-api/docs/grounding), [pricing](https://ai.google.dev/gemini-api/docs/pricing) | Explicit external-research mode with provenance | Off for private document summarization and effect planning |

Conclusion: Google AI can specialize in document understanding, structured extraction and bounded analytics. Codex/Nobus Core remains the governing brain because authorization, identity, reconciliation, costs and effect execution cannot be delegated to probabilistic output.

## 5. Workspace APIs and client landscape

### 5.1 Production interfaces

| Interface | Status / maintenance | License / support | Verdict |
|---|---|---|---|
| Workspace REST APIs | Google-supported product APIs with per-product discovery/reference docs | Google service terms | **Adopt as production authority** |
| `google-api-python-client` | Official supported Python client; repository describes it as maintenance mode. Latest observed release `v2.197.0`, 2026-05-28. [Repository](https://github.com/googleapis/google-api-python-client) | Apache-2.0 | **Adapt behind Nobus adapters.** Avoid leaking discovery resources outside integration code |
| Direct REST | Stable HTTP surface with explicit request/response control | Google service terms | Use where it reduces discovery-client ambiguity or improves observability; keep same adapter contract |

### 5.2 MCP, CLI and connector candidates

| Candidate | Maturity and maintenance | Rights / security | Windows/VPS/Python fit | Verdict |
|---|---|---|---|---|
| Official Workspace remote MCP servers | Developer Preview; guide observed updated 2026-07-23. Drive, Docs, Sheets and Calendar endpoints are documented; Tasks is absent. [Official guide](https://developers.google.com/workspace/guides/configure-mcp-servers) | OAuth account access; Google explicitly warns that indirect prompt injection can cause data disclosure or modification | Useful for isolated diagnostics, not an embedded Python authority | **Adopt only as read-only canary** |
| Google Workspace CLI (`gws`) | Google Workspace-maintained, latest observed `v0.22.5`, 2026-03-31; repository states it is not an officially supported Google product. Dynamic discovery, structured JSON and dry run remain; the former `mcp` command was removed in `v0.8.0`. [Repository](https://github.com/googleworkspace/cli), [releases](https://github.com/googleworkspace/cli/releases), [changelog](https://github.com/googleworkspace/cli/blob/main/CHANGELOG.md) | Local OAuth; recent releases support OS keychain storage | Strong Windows/operator diagnostic fit; extra runtime and credential surface | **Adopt only for read-only diagnostics/canary** |
| `taylorwilsdon/google_workspace_mcp` | Active community project, latest observed `v1.22.2`, 2026-07-26; broad Workspace coverage including Tasks. [Repository](https://github.com/taylorwilsdon/google_workspace_mcp), [releases](https://github.com/taylorwilsdon/google_workspace_mcp/releases) | MIT; broad OAuth/tool surface; a recent release fixed an OAuth refresh loop | Easy evaluation path, but adds a third-party credential/effect plane | Evaluate in a disposable read-only environment; **reject as production authority** |
| SaaS automation/connectors | Varying maturity, pricing and retention; often require broad account delegation | Additional processor, credential and audit boundary | Can reduce prototype code | No candidate has demonstrated enough benefit to justify another effects authority; reconsider only with measurable SLO and audit gains |

No paid third-party connector advances to the shortlist: none has demonstrated a measurable SLO, audit or code-reduction advantage sufficient to justify an additional credential and effects authority.

Fact: the official MCP guide warns that MCP clients may expose account data and that prompt injection can induce unintended tool use.
Conclusion: even an official MCP server is unsuitable as Nobus production authority while it is a preview tool surface controlled through model-oriented protocols.

## 6. OAuth and identity topology

### 6.1 Options

| Identity option | Official behavior | Fit | Verdict |
|---|---|---|---|
| Installed/Desktop OAuth | Public-client flow using system browser and loopback redirect; PKCE S256; OOB is deprecated. [Native apps](https://developers.google.com/identity/protocols/oauth2/native-app) | Current owner-only Windows bridge/bootstrap | Retain temporarily, harden storage; do not move its token file to the server |
| Web server OAuth | Confidential web client, state validation, offline access and incremental authorization. [Web server apps](https://developers.google.com/identity/protocols/oauth2/web-server) | Target central token broker | **Adopt through new consent and independent credential lineage** |
| Service account | Non-human identity; domain-wide delegation requires a Workspace super-admin and impersonation configuration. [Service accounts](https://developers.google.com/identity/protocols/oauth2/service-account) | Cloud resources, not a private owner account | Do not use for owner Workspace data |
| Domain-wide delegation | Admin-authorized impersonation across a Workspace domain | Inapplicable or excessive for owner-only usage | **Reject** |
| WIF / keyless service identity | Exchanges trusted external/workload identity for short-lived Google credentials without a service-account key file. Guide observed updated 2026-07-21. [WIF](https://cloud.google.com/iam/docs/workload-identity-federation) | VPS/server access to Vertex and Google Cloud | **Adopt** |

Google’s OAuth best-practices guide, observed updated 2026-05-20, recommends secure platform storage, refresh-token protection, revocation handling and least privilege. [OAuth best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)

### 6.2 Target identity separation

1. Workspace user identity: owner consent, Web OAuth client, token broker, per-scope grant inventory.
2. Desktop bootstrap identity: separate Desktop OAuth client and local secure store during migration only.
3. Cloud workload identity: WIF/service identity for Vertex and Cloud APIs; no Workspace impersonation.
4. Model identity: none. The model receives sanitized content and closed parameters only.
5. Operator diagnostics identity: isolated read-only grant, not the production token broker.

Migration conclusion: copying `token.json` or another installed-app token artifact to a VPS would collapse client identity, storage and revocation boundaries. The safe migration is a new Web OAuth grant, verification of read-only parity, explicit cutover, then revocation and removal of the old local grant after a rollback window.

## 7. Recommended least-privilege scopes

Scopes are granted incrementally by capability. A requested scope is not an authorization decision: Core policy must also allow the action.

| Product capability | Read scope | Write scope | Avoid / notes |
|---|---|---|---|
| Calendar list | `calendar.calendarlist.readonly` | None required | Avoid Calendar ACL/settings scopes |
| Owner event read | `calendar.events.owned.readonly` | None | If shared-calendar product requirements emerge, re-review |
| Owner event write | Read scope above | `calendar.events.owned` | Prefer owned events over broad `calendar` |
| Tasks read | `tasks.readonly` | None | Tasks API has only broad read/write families |
| Tasks write | `tasks.readonly` during staged rollout | `tasks` | Separate consent milestone |
| Drive metadata | `drive.metadata.readonly` where sufficient | None | Metadata scope does not read content |
| User-selected Drive files | `drive.file` | `drive.file` | Preferred through Picker/app-created or explicitly opened files |
| Global Drive content discovery | `drive.readonly` | None | Restricted scope; owner product decision and verification burden |
| Docs read | `documents.readonly` plus file access | None | Drive access still controls file discoverability |
| Docs write | `documents.readonly` | `documents` or preferably `drive.file` for selected files | Use revision preconditions |
| Sheets read | `spreadsheets.readonly` plus file access | None | Scope applies to the whole spreadsheet, not one tab |
| Sheets write | `spreadsheets.readonly` | `spreadsheets` or preferably `drive.file` | Use bounded ranges and readback |

Official scope references: [Calendar](https://developers.google.com/workspace/calendar/api/auth), [Tasks](https://developers.google.com/workspace/tasks/auth), [Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [Docs](https://developers.google.com/workspace/docs/api/auth), [Sheets](https://developers.google.com/workspace/sheets/api/scopes).

A write scope that already includes read access does not require a redundant read-only scope. “Read then write” means staged incremental consent and a separately enabled Core capability, not duplicate grants.

## 8. API constraints that shape Gates 4, 5 and 7

### 8.1 Docs

Facts:

- `documents.batchUpdate` validates all requests and applies them atomically.
- `requiredRevisionId` rejects a stale write; `targetRevisionId` may merge concurrent changes.
- Multi-tab documents require explicit tab handling.

Source: [Docs batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate), [Docs API best practices](https://developers.google.com/workspace/docs/api/how-tos/best-practices).

Conclusion: Gate 7 must use a closed `DocumentWritePlan`, `requiredRevisionId` for compare-and-swap behavior, and post-write readback. Model-generated raw Docs requests are forbidden.

### 8.2 Sheets

Facts:

- Quotas are 300 read and 300 write requests per minute per project, plus 60 per minute per user per project.
- Google recommends payloads around 2 MB or less; requests can time out after 180 seconds.
- Batch updates are atomic.

Source: [Sheets usage limits](https://developers.google.com/workspace/sheets/api/limits).

Conclusion: Gate 5/7 must chunk reads/writes, bound ranges and cells, batch semantically related updates, use a local quota gate and reconcile timed-out mutations.

### 8.3 Drive

Facts:

- Drive applies API quotas and a quota-unit model; batch HTTP requests are limited to 100 subrequests.
- Search and file download/export semantics differ; Google-native formats require export.

Sources: [Drive limits](https://developers.google.com/workspace/drive/api/guides/limits), [performance](https://developers.google.com/workspace/drive/api/guides/performance), [download/export](https://developers.google.com/workspace/drive/api/guides/manage-downloads).

Conclusion: current bounded Drive planning is reusable. Gate 5 should add native Docs/Sheets reads rather than treating exported Office files as the semantic source of truth.

### 8.4 Tasks

Facts:

- Task `due` is a date; time information is discarded.
- Title and notes limits are 1,024 and 8,192 characters.
- Deleting an assigned task may affect the originating Docs or Chat surface.
- Default courtesy limit is documented as 50,000 queries per day.

Sources: [Task resource](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks), [Tasks limits](https://developers.google.com/workspace/tasks/limits).

Conclusion: Gate 4 must keep date-only semantics explicit, validate lengths and distinguish owner-created tasks from assigned tasks before destructive actions.

### 8.5 Calendar

Facts: Google documents refresh/reauth handling for 401, quota/rate backoff for 403/429, refetch/reapply for 412 and exponential backoff for server errors. [Calendar errors](https://developers.google.com/workspace/calendar/api/guides/errors)

Conclusion: Calendar errors must enter a Core-owned failure taxonomy. A 412 or ambiguous transport result is reconciliation work, not a blind retry.

## 9. Cost, quota and retention evidence

Prices are list prices observed on 2026-07-28 and must be rechecked before implementation or release.

| Surface | Verified current evidence | Nobus guard |
|---|---|---|
| Gemini 3.6 Flash standard | Paid tier: $1.50 / 1M input tokens and $7.50 / 1M output tokens; cached input $0.15 / 1M plus $1.00 / 1M token-hours; batch/flex $0.75 input and $3.75 output. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) | Per-task reservation, hard Core ledger, daily/monthly ceilings, max output tokens |
| Gemini grounding | Shared free allowance then billed per search query; observed price $14 / 1,000 Search queries after allowance. [Pricing](https://ai.google.dev/gemini-api/docs/pricing) | Disabled by default; separate research budget |
| Vertex Gemini | Global Gemini 3.6 Flash list price aligns with $1.50 input / $7.50 output; batch/flex $0.75 / $3.75. [Vertex pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) | Model alias allowlist and Cloud billing alerts/cap plus Core ledger |
| Gemini API quotas | Limits are enforced per project using RPM, TPM, RPD and batch concurrency dimensions. [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) | Local token/request buckets below provider ceilings |
| Cloud budgets | Budgets primarily alert; they do not generally hard-cap spend. Google also documents spend caps for supported services, with delayed enforcement/possible overage. [Budgets](https://cloud.google.com/billing/docs/how-to/budgets), [spend caps](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps) | Never rely on billing alone; Core hard-denies new reservations at its ceiling |

### 9.1 Retention findings

| Feature | Official behavior | Gate 3 policy |
|---|---|---|
| Vertex prompts/outputs | Not used to train Google models without permission; request/response logging is off by default. Separate abuse-monitoring retention can apply unless the project has an approved exception. Implicit cache is a project-level control and can retain data in memory for up to 24 hours unless disabled. [Vertex ZDR](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention) | Primary route; logging off; strict ZDR fails closed unless the exception/status and project-level cache setting are verified |
| Gemini Developer API logs | Optional logs have configurable retention of 7/14/28/55 days, with 55 days the documented default when enabled; datasets have separate lifecycle. [Logs policy](https://ai.google.dev/gemini-api/docs/logs-policy) | Logs and datasets disabled for Nobus production |
| Gemini Developer API ZDR | Interactions may store by default unless configured otherwise; explicit caches and Files have independent retention; implicit caching may retain content in RAM. [ZDR](https://ai.google.dev/gemini-api/docs/zdr) | If used as fallback, set non-storage modes and deny sensitive classes |
| Files API | Automatic deletion after 48 hours; manual deletion supported | Core registry and eager delete; never evidence storage |
| Grounding | Search/Maps services have unavoidable provider-specific retention windows | Explicit policy/owner consent; forbidden for confidential/private document paths |
| Cloud location | Google Cloud publishes data-residency terms and location controls per service | Owner selects deployment location before production |

Conclusion: “zero retention” is a route-specific configuration and feature restriction, not a provider-wide label. Files, caches, interactions, logging and grounding must each be independently governed.

## 10. Three end-to-end foundation options

| Dimension | A — Official APIs + Vertex/Core authority | B — Official APIs + Gemini Developer API primary | C — MCP/CLI-led Workspace agent |
|---|---|---|---|
| Maturity | High for REST/Cloud identity; model features managed behind SDK | High API velocity; lighter Cloud setup | MCP is Developer Preview; CLI is not officially supported product |
| Maintenance | Google APIs/SDK plus Nobus adapters | Google API/SDK plus Nobus adapters | Extra protocol/server/client and credential lifecycle |
| Windows/VPS/Python | Strong; Desktop bootstrap and server WIF/Web OAuth | Strong; simpler API-key path but weaker identity separation | Strong for operator use, less deterministic for service authority |
| License | SDK/client Apache-2.0; Google service terms | SDK Apache-2.0; Google service terms | Official CLI Apache-2.0; services and community components vary |
| Pricing | Vertex list pricing and Cloud governance | Comparable model list price; paid/free data terms differ | Product/API costs plus operational connector cost |
| Privacy | Best isolation and Cloud controls | Acceptable only with paid/ZDR-compatible configuration and route limits | Prompt/tool plane expands data and injection surface |
| Operational burden | Medium, explicit but auditable | Medium-low initially; later governance migration likely | High due to duplicate authority and debugging surface |
| Code reduction | Moderate through official SDKs | Moderate | High prototype reduction, low control |
| Lock-in | Adapter-contained Google APIs | Adapter-contained, but Developer-specific storage features tempt coupling | High coupling to tool schemas and server behavior |
| Fallback | Developer API for allowed classes; provider-neutral Core survives | Vertex or other provider after extra identity work | Difficult to prove effects and replay safely |
| Verdict | **ADOPT** | **ADAPT as constrained fallback** | **REJECT as production authority** |

## 11. Adopt / adapt / build shortlist

### Adopt

- Workspace REST APIs for Calendar, Tasks, Drive, Docs and Sheets.
- `google-genai` as the only Google model SDK boundary.
- Vertex AI as primary Google-specialist route.
- Web OAuth/token broker target and WIF/keyless Cloud identity.
- Official MCP or `gws` only for isolated read-only canaries and diagnostics.

### Adapt

- Existing Calendar deterministic IDs/conflict readback.
- Existing Tasks markers, locking, bounded pagination and unknown-outcome recovery.
- Existing Drive containment, request budgets and ambiguity controls.
- Existing strict/frozen Core contracts and canonical digests.
- `google-api-python-client` or direct REST only behind operation-specific adapters.

### Build inside Nobus Core

- Closed Google request/result/effect/reconciliation DTOs.
- Policy and scope intersection.
- Extend the existing `DurableProductEffectVault` with Google outcome/reconciliation metadata; do not build a second journal or event store.
- Per-route deadlines, retry classifiers and circuit breakers.
- Budget reservation/settlement ledger.
- Content-safe telemetry and audit.
- Token-broker interface and grant inventory.

## 12. Explicit reject list

- Model access to OAuth access tokens, refresh tokens, API keys, service credentials or the token broker.
- Model-executed Workspace effects or unrestricted function/tool calls.
- Workspace MCP, Gemini CLI or the historical/removed `gws mcp` path as production write authority.
- Community MCP server in the production credential/effect plane.
- Google ADK as a parallel orchestrator beside Nobus Core.
- Copying a Desktop OAuth token file to a VPS.
- Service-account domain-wide delegation for an owner-only personal Workspace.
- Long-lived service-account key files when WIF/keyless identity is available.
- Broad `drive` or `calendar` scopes when capability-specific scopes suffice.
- Blind retry of a Workspace mutation after timeout, reset or unknown response.
- Gemini Files API, cache, logs or grounding as a hidden document/evidence store.
- Billing alerts as the only cost ceiling.
- Provider outage propagation that blocks Telegram/Core.

## 13. Gate handoff evidence

| Gate | Receives from Gate 3 | Must not assume |
|---|---|---|
| Gate 4 — Business Notes, Calendar и Tasks | Closed read/effect contracts, owner identity, least-privilege Calendar/Tasks grants, idempotency and reconciliation | Model authority or time-of-day support in Tasks due dates |
| Gate 5 — Unified Document Gateway и Windows Bridge | Drive/Docs/Sheets read contracts, provider-neutral document references, tokenless Bridge target | Exports are the semantic source of truth or Bridge owns OAuth |
| Gate 6 — Multi-document Analytics | Isolated Vertex gateway, structured result validation, batch job and cost/retention policy | Model output is evidence or authorization |
| Gate 7 — Artifact Factory и writeback | Closed write plans, Docs revision CAS, bounded Sheets ranges, Drive markers/readback, durable unknown-outcome state | A retry is safe merely because the SDK raised an exception |
| Gate 8 — Hybrid Release и 72-часовой pilot | Health canary, token-broker/WIF topology, outage isolation, observability, budget/retention acceptance suite | A successful happy-path OAuth call proves production readiness |

## 14. Research acceptance

- [x] Official APIs/SDKs and primary repositories are the basis of the verdict.
- [x] Time-sensitive versions, dates, prices, limits and retention behaviors have direct links.
- [x] CURRENT facts are separated from TARGET conclusions.
- [x] At least three complete foundation options are compared.
- [x] OAuth, scopes, quotas, idempotency, retention, cost and outage isolation are covered.
- [x] MCP/CLI/paid connector candidates are evaluated without granting them production authority.
- [x] Gate 4–8 dependency labels match `docs/12`.
- [x] No credentials, account identifiers, secrets or local credential files were read or recorded.

Research status: **RESEARCH READY**. The implementation and release gates remain unpassed.
