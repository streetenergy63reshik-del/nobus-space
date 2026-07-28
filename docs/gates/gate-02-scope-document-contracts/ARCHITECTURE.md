# Gate 2 — Scope Registry and Unified Document Contracts Architecture

**Document status:** NORMATIVE TARGET
**Canonical base:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Implementation status:** not implemented
**Research basis:** [`RESEARCH.md`](RESEARCH.md)

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative in this document.

## 1. Purpose

Gate 2 defines one safe document authority model for local and Google
documents. It establishes contracts, registries, policy decisions,
classification, containment, and handoff invariants. It does not execute real
document reads or writes.

The architecture MUST allow useful document discovery, selection, analysis,
artifact planning, and later writeback while preventing:

- tenant, project, or client data crossing;
- local path escape or backend-folder escape;
- access to secrets or always-denied locations;
- OAuth or filesystem authority reaching a model;
- prompt content becoming instructions or tool authority;
- unbounded parsing, decompression, indexing, or provider calls;
- stale, duplicate, or unrequested effects.

## 2. Product behavior

### 2.1. Owner-visible behavior

The product MUST:

1. Accept natural text/voice intent from a trusted ingress.
2. Clarify missing project, client, source, period, document, range, format, or
   destination before authority is created.
3. Search document metadata within explicitly bound source scopes.
4. Return safe candidates without reading document contents.
5. Require an exact `DocumentRef` selection before content access.
6. Read only bounded ranges/pages/sheets supported by the selected backend.
7. Explain ambiguity, denied scope, unsupported format, secret rejection,
   stale revision, and provider outage with safe stable messages.
8. Treat document text as untrusted data.
9. Produce an `ArtifactPlan` or `DocumentWritePlan`; the model MUST NOT execute
   a write.
10. Apply the same semantic contracts to local and Google documents.

### 2.2. Non-goals

Gate 2 MUST NOT:

- scan owner roots or read owner document content;
- start the Windows Bridge or any live Nobus runtime;
- make Google API calls or change OAuth scopes;
- implement PDF/Office/Google parsers;
- create or update real local/Google documents;
- expose arbitrary filesystem, Google, shell, browser, or MCP tools to a model;
- implement generic ABAC/RBAC infrastructure;
- replace Gate 1 intent admission, Gate 3 Google foundation, Gate 5 document
  gateway, Gate 6 analytics, or Gate 7 writeback;
- define delete, share, permission-change, publish, deploy, money, or
  third-party delivery authority.

## 3. CURRENT, reuse, and TARGET

| Area | CURRENT | Reuse | TARGET |
|---|---|---|---|
| Contract base | Pydantic frozen models with unknown-field rejection | Canonical digest, UUID, datetime and negative-test patterns | Strict seven-contract family and generated schemas |
| Generic task source/permissions | Free strings remain in the current draft | Ingress/task binding and idempotency | Closed enums; no document authority from `allowed_paths` |
| Policy | Application-owned checks | Existing pure policy direction | Exact binding, registry-backed deny-overrides decisions |
| Local search/read | Metadata-first, bounded extraction, DLP, final-handle verification | Selection, limits, scanner, final-handle evidence | All-component handle identity and race-safe containment |
| Local write | Snapshot, digest CAS, pinned directory, atomic replace, journal/readback | Entire algorithmic lineage | Output-registry binding and strict handle/identity preconditions |
| Google | Read-only metadata/download adapter | Pagination, ancestry, ambiguity, size/time bounds | Opaque references and unified revision/read contracts |
| Model | Tool-less owner-file analysis exists | Prompt/data separation and exfil checks | Mandatory for all document analysis |

Relevant code is mapped in [Section 24](#24-code-impact-map).

## 4. Trust and authority model

### 4.1. Trust zones

| Zone | Trusted for | MUST NOT be trusted for |
|---|---|---|
| Trusted ingress | Authenticated actor, tenant/conversation binding, owner text provenance | Backend scope or file authority supplied inside text |
| Nobus Core | Contract validation, policy, registry activation, queue/effect state | Raw local path traversal or model-proposed authority |
| Registry store | Versioned source/output/deny policy data | Runtime content or model instructions |
| Local Bridge | Local private root/ref resolution and handle-based I/O | Widening a signed job or accepting model paths |
| Google adapter | OAuth, Google IDs, API calls, folder/revision verification | Model-provided OAuth or raw provider query fragments |
| Extractor/DLP | Bounded parsing and local classification | Tool execution, external fetches, macros, embedded instructions |
| Model provider | Reasoning over bounded untrusted excerpts | Tenant binding, scope selection, policy, credentials, tools, writes |
| Effect executor | Exact approved/idempotent plan execution | Replanning scope, target, payload, or approval |
| Durable state | Digests, metadata, refs, decisions, audit | Plaintext owner document content |

### 4.2. Authority rule

Authority can only narrow while moving downstream:

```text
trusted ingress binding
  → intent
  → registry scope
  → exact document reference
  → bounded read plan
  → analysis/artifact plan
  → exact write plan
  → effect executor
```

No downstream component MAY introduce a tenant, project, client, source,
output, operation, format, locator, or limit absent from its verified upstream
bindings.

### 4.3. Model authority

The model receives:

- a bounded owner instruction;
- model-safe contract projections;
- bounded document excerpts explicitly labelled as untrusted data;
- safe provenance and limitations.

The model MUST NOT receive:

- absolute or private local roots;
- local relative path handles that can be executed directly;
- Google file/folder IDs used by adapters;
- OAuth client secrets, access tokens, refresh tokens, scopes, or credential
  paths;
- registry private locators or signing material;
- general filesystem, Google, MCP, shell, process, network, or browser tools;
- raw DLP findings.

## 5. Threat model

| Threat | Required control |
|---|---|
| Tenant/project/client field substitution | Values originate from trusted ingress/registry; exact equality at every boundary |
| Guessing another document UUID | Composite binding lookup; indistinguishable deny response |
| Registry modification | Schema validation, JCS digest, Ed25519 signature |
| Registry replay/rollback | Monotonic version and accepted-digest state |
| Partial registry refresh | Atomic three-registry activation only |
| Path traversal | Relative component grammar before any I/O |
| UNC/device/volume path | Absolute namespace forms rejected before resolution |
| ADS | Colon forbidden in all relative components |
| Reserved/case alias | Windows reserved-name and ordinal case policy plus handle identity |
| Symlink/junction/reparse | Root, every ancestor, and final object rejected on any reparse tag |
| Hard-link alias | Multiple-link local documents/targets denied by default |
| Ancestor/final replacement | Parent-relative handle opens and file/volume identity checks |
| Concurrent content mutation | Share-mode control, before/after identity/size/timestamp, digest/revision |
| Google folder escape | Private ID mapping, verified ancestry, shortcuts denied |
| MIME lie/polyglot | Extension + declared MIME + magic/parser agreement |
| Decompression bomb | Compressed/uncompressed, entry, depth, ratio, time and memory limits |
| Secret exposure | Metadata/path deny, local scanner, optional Gitleaks, no model call |
| Prompt injection | Document labelled data; no tools; closed output validation |
| Model exfiltration | Post-model DLP/verbatim overlap checks |
| Duplicate/stale write | Idempotency, expected revision/digest, approval binding and readback |
| Generic MCP authority | Explicit policy denial; no general MCP server in Core boundary |

## 6. Common wire rules

### 6.1. Serialization and model configuration

Every contract MUST use:

```python
ConfigDict(
    strict=True,
    extra="forbid",
    frozen=True,
    validate_default=True,
)
```

JSON is UTF-8. Generated JSON Schema MUST target Draft 2020-12 and set
`additionalProperties: false` on every object.

`TypeAdapter` MAY validate an explicitly declared discriminated union. Smart
unions and fallback-to-first-variant behavior are forbidden.

### 6.2. Common scalar types

| Alias | Wire type | Rule |
|---|---|---|
| `Uuid` | string | RFC 4122 UUID; server-generated where specified |
| `BoundRef` | string | 1–128 ASCII chars, regex `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` |
| `Digest` | string | `^sha256:[0-9a-f]{64}$` |
| `AwareDateTime` | string | RFC 3339 with timezone; server-authoritative |
| `SafeLabel` | string | trimmed 1–255, no control chars, separators or bidi controls |
| `MediaType` | string | lowercase type/subtype, 3–127 chars, no parameters |
| `IdempotencyKey` | string | trimmed 1–128; unique within exact binding and operation family |
| `SafeReason` | string | 1–512; no path, token, raw provider response or document excerpt |

Boolean MUST NOT be accepted as integer. Empty strings, non-finite numbers,
duplicate object keys, naive datetimes, and unknown enums are invalid.

### 6.3. Common binding

Every authority-bearing contract MUST contain:

| Field | Type | Rule |
|---|---|---|
| `tenant_id` | `BoundRef` | trusted ingress value |
| `project_ref` | `BoundRef` | exact registry binding |
| `client_ref` | `BoundRef \| null` | exact client or explicit clientless scope; never wildcard |
| `policy_version` | `BoundRef` | active policy version |
| `registry_bundle_digest` | `Digest` | active source/output/deny set |

`client_ref=null` means only an explicitly clientless registry entry. It MUST
NOT match an arbitrary client.

### 6.4. Contract identity and digest

Every contract MUST contain:

| Field | Type | Rule |
|---|---|---|
| `schema` | literal | exact `nobus.<contract>.v1`; discriminator |
| `schema_version` | literal `"1"` | must agree with `schema` |
| `schema_digest` | `Digest` | generated JSON Schema JCS digest |
| `contract_digest` | `Digest` | instance JCS digest excluding this field |
| `created_at` | `AwareDateTime` | Core server time |

The digest algorithm is:

```text
contract_digest = SHA-256(JCS(contract without contract_digest))
schema_digest   = SHA-256(JCS(generated JSON Schema))
```

Arrays retain order. Strings are not silently Unicode-normalized during
canonicalization. Input normalization MUST occur before the accepted contract
is created.

## 7. Closed enums

### 7.1. Common enums

```text
Backend =
  local | google

Classification =
  public | internal | confidential | restricted

DocumentKind =
  text | markdown | json | csv | html | docx | xlsx | pdf |
  google_doc | google_sheet

OutputFormat =
  telegram_text | jpeg | html | xlsx | docx | pdf |
  google_doc | google_sheet

CollisionPolicy =
  new_version | ask

WriteOperation =
  create | update
```

`secret` is a scanner verdict, not a valid document classification.

### 7.2. Imported Gate 1 contract and Gate 2 local types

`IntentEnvelope` and every intent enum are owned exclusively by Gate 1 and are
imported without adding Section 6 common fields or redefining field names, limits,
confidence encoding, action vocabulary, effects, context or digest. The normative
shape is `nobus.intent.v1` in Gate 1 and canonical document 12.

Gate 2 consumes only a validated envelope. For document work it resolves each
`IntentEnvelope.source_scope[].scope_ref` through the active signed source
registry and emits a `DocumentQuery.source_scope_ids` projection. The proposal,
selector or owner text is never document authority; the exact `DocumentRef` issued
after selection is authority-bearing.

Gate 2 defines one document-local period union for `DocumentQuery` and
`AnalysisRequest`:

`DocumentPeriod` is discriminated by `kind`:

- `date_range`: `start_date`, `end_date` as ISO dates;
- `datetime_range`: `start_at`, `end_at` as aware RFC 3339 datetimes.

Every `DocumentPeriod` is canonical half-open `[start, end)` and end MUST be
greater than start. Conversion from Gate 1 `TimeRange` is one deterministic Core
mapper, not a second intent parser:

| Gate 1 boundary | Gate 2 result |
|---|---|
| date phrase with `inclusive_end=true` | `date_range.end_date = local end date + 1 calendar day` |
| date phrase with `inclusive_end=false` | `date_range.end_date = supplied exclusive local date` |
| datetime with `inclusive_end=false` | preserve the exact aware RFC 3339 end instant |
| datetime with `inclusive_end=true` | exclusive end = exact instant + 1 microsecond; overflow rejects |

The IANA timezone is retained in the scope/request binding. A nonexistent DST
local time rejects; a fold without an explicit UTC offset requires clarification.
Provider conversion happens only after this half-open interval is frozen. The
maximum admitted span is policy-bound. Golden tests cover month/year end, leap
day, DST gap/fold, Moscow/non-Moscow zones and Russian inclusive phrases.
## 9. DocumentRef v1

`DocumentRef` is issued only by the trusted document gateway after exact
selection. It is not accepted as a user-authored locator.

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `document_ref_id` | `Uuid` | opaque, server-generated |
| `source_scope_id` | `BoundRef` | exact source registry entry |
| `backend` | `Backend` | closed |
| `source_id` | `Uuid` | opaque ref-store key, not path/Google ID |
| `display_name` | `SafeLabel` | sanitized, 1–255 |
| `document_kind` | `DocumentKind` | closed |
| `media_type` | `MediaType` | validated against kind and metadata |
| `classification` | `Classification` | registry/scanner result |
| `size_bytes` | strict integer | 0–52,428,800 |
| `revision` | `DocumentRevision` | discriminated union |
| `content_digest` | `Digest \| null` | required when stable source bytes exist |
| `provenance` | `DocumentProvenance` | closed bounded object |
| `expires_at` | `AwareDateTime` | later than creation; max policy TTL |

`DocumentRevision`, discriminated by `kind`:

| Variant | Fields |
|---|---|
| `local_sha256` | `sha256`, `volume_id_digest`, `file_id_digest`, `observed_at` |
| `google_drive_version` | `version` as decimal string 1–32 chars, `observed_at` |
| `google_docs_revision` | opaque `revision_ref` 1–256, `observed_at` |
| `google_sheets_observation` | Drive `version`, `observed_at`, `strict_cas=false` literal |

Raw volume serials, file IDs, local paths, Google IDs, and revision IDs MUST
remain in the private ref record. Their model-safe fields are opaque
digests/refs.

`DocumentProvenance`:

| Field | Type | Rule |
|---|---|---|
| `adapter` | enum | `windows_bridge`, `google_drive`, `google_docs`, `google_sheets` |
| `observed_at` | `AwareDateTime` | server observation |
| `parent_scope_id` | `BoundRef` | registry parent |
| `metadata_digest` | `Digest` | canonical safe metadata |
| `selection_method` | enum | `exact_id`, `unique_metadata_match`, `owner_confirmed_candidate` |

## 10. DocumentQuery v1

`DocumentQuery` searches metadata only.

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `query_id` | `Uuid` | server-generated |
| `source_scope_ids` | array[`BoundRef`] | 1..8, unique |
| `query_text` | string \| null | 1–512; treated as metadata hint |
| `name_hints` | array[`SafeLabel`] | 0..16 |
| `folder_hints` | array[`SafeLabel`] | 0..8; never a path |
| `period` | `DocumentPeriod \| null` | optional |
| `document_kinds` | array[`DocumentKind`] | 0..10, unique |
| `media_types` | array[`MediaType`] | 0..16, unique |
| `classifications` | array[`Classification`] | 0..4, unique |
| `max_candidates` | strict integer | 1–50; default 20 |
| `max_pages` | strict integer | 1–5 |
| `metadata_timeout_ms` | strict integer | 100–10,000 |

The adapter MUST build its provider query itself. `query_text`, names, or folder
hints MUST NOT be passed as a raw Google query expression, SQL fragment,
filesystem glob, regex, or shell expression.

Query results are zero or more model-safe candidates. Content MUST NOT be read
until one or more exact `DocumentRef` values are issued.

## 11. DocumentReadPlan v1

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `read_plan_id` | `Uuid` | server-generated |
| `documents` | array[`DocumentSelection`] | 1..32, unique `document_ref_id` |
| `purpose` | enum | `summarize`, `answer`, `extract_facts`, `analyze`, `preview` |
| `max_source_bytes_per_document` | strict integer | 1–52,428,800 |
| `max_source_bytes_total` | strict integer | 1–104,857,600 |
| `max_extracted_chars_per_document` | strict integer | 1–24,000 |
| `max_extracted_chars_total` | strict integer | 1–96,000 |
| `max_parser_seconds_per_document` | strict integer | 1–30 |
| `max_parser_seconds_total` | strict integer | 1–120 |
| `dlp_profile` | `BoundRef` | active local profile |
| `prompt_profile` | `BoundRef` | tool-less prompt profile |

`DocumentSelection` is discriminated by `selection_kind`:

| Variant | Fields and limits |
|---|---|
| `whole_document` | exact embedded `DocumentRef` |
| `pages` | exact `DocumentRef`; 1–100 unique page numbers in range 1–200 |
| `sheet_ranges` | exact `DocumentRef`; 1–64 ranges, each 1–128 chars; max 20,000 cells/document |
| `text_sections` | exact `DocumentRef`; 1–32 opaque section refs, each 1–128 |

The embedded `DocumentRef` revision MUST be revalidated immediately before
opening/downloading. A stale or expired ref results in `revision_conflict`; the
adapter MUST NOT silently refresh and continue.

### 11.1 DocumentSlice v1

Gate 2 exclusively owns `nobus.document_slice.v1`. Every slice contains the
Section 6 common identity/binding and digest fields plus:

| Field | Type | Limit / rule |
|---|---|---|
| `slice_id` | `Uuid` | server/adapter-generated under the accepted plan |
| `read_plan_id` / `read_plan_digest` | ID + digest | exact accepted Gate 2 plan |
| `document_ref` / `document_ref_digest` | exact `DocumentRef` + digest | same tenant/project/client/policy/registry binding |
| `revision_seen` | exact revision union | must equal the revalidated ref revision |
| `selection` | exact normalized `DocumentSelection` | no selector expansion |
| `transport_binding` | closed union | exact local or Google execution fence below |
| `blocks` | array[`DocumentBlock`] | 0..512; closed typed blocks and bounded content |
| `output_bytes` / `output_characters` | strict integers | within plan budgets |
| `truncated` | boolean | never interpreted as complete evidence |
| `next_cursor` | `BoundCursor \| null` | scope/plan/ref/revision/policy/expiry bound |
| `source_untrusted` | literal `true` | required |
| `classification` | `Classification` | no lower than source/policy result |
| `extraction_warnings` | array[`DocumentWarning`] | 0..32 closed codes |
| `provenance_ids` | array[`BoundRef`] | opaque private-vault ingest refs only |

`transport_binding` is discriminated:

- `local_bridge`: opaque device ID, enrollment/device epoch, session ID/epoch,
  job ID/digest, lease ID/epoch, and exact `read_v1_capability_digest`;
- `google_adapter`: opaque adapter/grant binding refs, attempt generation and
  adapter evidence digest.

`DocumentBlock` is a closed union of bounded `text`, `table`, `key_value` and
`metadata` blocks. It contains no local path, Google/provider ID, sheet/tab/client
name, package part or arbitrary metadata map. Exact locators live only in the
client-bound private provenance vault keyed by `provenance_id`.

`BoundCursor` contains an opaque value plus cursor digest, plan/ref/revision and
scope-binding digests, policy/registry versions and expiry. It cannot be replayed
for another tenant/project/client, revision, plan, device/enrollment/capability
or adapter attempt.

### 11.2 DocumentReadResult v1

Gate 2 exclusively owns `nobus.document_read_result.v1`. It contains the Section
6 common fields plus:

| Field | Type | Limit / rule |
|---|---|---|
| `result_id` | `Uuid` | required |
| `read_plan_id` / `read_plan_digest` | ID + digest | exact accepted plan |
| `status` | enum | `complete`, `partial`, `failed`, `cancelled` |
| `slices` | array[`DocumentSlice`] | set/order constrained by plan; 0..512 |
| `failed_documents` | array[`SafeDocumentFailure`] | opaque ref + closed safe reason; 0..32 |
| `usage` | closed totals | bytes/chars/pages/cells/time, within plan ceilings |
| `transport_evidence_digests` | array[`Digest`] | every contributing attempt/fence |

`complete` requires every selected document/revision and requested selector to be
represented without truncation or failure. The result carries no raw provider
object or free provenance. Gate 5 and Gate 6 literally import these two schemas;
golden vectors MUST produce the same `schema_digest`. Any stale tenant/client,
policy/registry/revision, lease/device/enrollment/capability or adapter binding
fails closed before a slice is admitted.

## 12. AnalysisRequest v1

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `analysis_id` | `Uuid` | server-generated |
| `idempotency_key` | `BoundedString` | required; same key with another digest is a conflict |
| `read_plan_digest` | `Digest` | exact accepted read plan |
| `sources` | array[`DocumentRef`] | 1..32; same set/binding as read plan |
| `question` | string | 1–20,000 chars |
| `sku_or_articles` | array[`BoundRef`] | 0..128; canonical registry refs only |
| `period` | `DocumentPeriod \| null` | optional |
| `metrics` | array[`MetricRequest`] | 0..32, unique |
| `grouping` | array[`Grouping`] | 0..8, unique |
| `calculation_rules` | array[`BoundRef`] | 0..16; versioned rules only |
| `requested_outputs` | array[`AnalysisOutput`] | 1..8, unique |
| `limitations` | array[`SafeReason`] | 0..16 |
| `processing_policy_ref` | `BoundRef` | exact versioned local/cloud/model/OCR policy |
| `limits` | `AnalysisLimits` | closed monotonic hard ceilings |
| `maximum_classification` | `Classification` | cannot exceed policy result |

Closed values:

```text
MetricRequest =
  revenue | units | average_price | margin | growth_rate |
  share | count | custom_declared

Grouping =
  client | sku | source | day | week | month | quarter | year

AnalysisOutput =
  telegram_text | normalized_facts | table | chart | artifact_plan

AnalysisLimits = {
  max_documents: integer 1..32,
  max_source_bytes: integer 1..536870912,
  max_extracted_characters: integer 1..2000000,
  max_cells: integer 1..200000,
  max_pages: integer 1..1000,
  max_model_input_bytes: integer 0..2000000,
  max_provider_calls: integer 0..256
}
```

`custom_declared` MUST reference a versioned calculation rule; the model cannot
invent an executable formula. Missing values remain missing. Conflicts retain
source provenance.

Document excerpts are runtime inputs associated with `read_plan_digest`; they
are not embedded in or durably stored with `AnalysisRequest`.

Gate 2 is the exclusive owner of the `AnalysisRequest` wire schema. Gate 6
imports this contract unchanged and may derive an internal
`AnalysisExecutionPlan`; it MUST NOT register another `AnalysisRequest`.

## 13. ArtifactPlan v1

`ArtifactPlan` defines a proposed render, not a file write.

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `artifact_plan_id` | `Uuid` | server-generated |
| `analysis_digest` | `Digest \| null` | required for analysis-derived artifact |
| `title` | `SafeLabel` | 1–255 |
| `format` | `OutputFormat` | closed |
| `sections` | array[`ArtifactSection`] | 1–64 |
| `content_digest` | `Digest` | normalized render input |
| `render_profile` | `BoundRef` | versioned renderer/profile |
| `target_backend` | enum | `telegram`, `local`, `google` |
| `output_scope_id` | `BoundRef \| null` | required for local/Google |
| `destination_hint` | `SafeLabel \| null` | filename stem/document title only |
| `collision_policy` | `CollisionPolicy` | closed |
| `provenance_refs` | array[`Uuid`] | 0..64, binding checked |

`ArtifactSection`, discriminated by `section_kind`:

| Variant | Fields |
|---|---|
| `text` | `heading` optional `SafeLabel`, opaque `content_ref`, `content_digest` |
| `table` | `heading` optional, opaque `table_ref`, `table_digest`, rows ≤10,000, columns ≤256 |
| `chart` | `heading` optional, opaque `chart_spec_ref`, `chart_spec_digest` |
| `reference` | `label`, `document_ref_id`, `revision_digest` |

No section contains raw source-document content in durable task state.

## 14. DocumentWritePlan v1

`DocumentWritePlan` is accepted only from a verified artifact and is executed
later by Gate 7.

| Field | Type | Limit / rule |
|---|---|---|
| common identity/binding fields | Section 6 | required |
| `write_plan_id` | `Uuid` | server-generated |
| `artifact_plan_digest` | `Digest` | exact artifact plan |
| `artifact_ref` | `Uuid` | immutable rendered artifact |
| `artifact_digest` | `Digest` | exact artifact bytes/content |
| `backend` | `Backend` | closed |
| `operation` | `WriteOperation` | `create` or `update` only |
| `output_scope_id` | `BoundRef` | exact output registry entry |
| `target` | `WriteTarget` | discriminated union |
| `expected_revision` | `DocumentRevision \| null` | required for update; null for create |
| `collision_policy` | `CollisionPolicy` | `new_version` or `ask` |
| `snapshot_required` | strict boolean | true for every local update |
| `strict_cas_required` | strict boolean | policy-derived |
| `idempotency_key` | `IdempotencyKey` | exact binding + operation + target + payload |
| `approval_binding` | `ApprovalBinding` | discriminated union |
| `expires_at` | `AwareDateTime` | later than created; policy TTL |

`WriteTarget`, discriminated by `target_kind`:

| Variant | Fields |
|---|---|
| `new_document` | `destination_name: SafeLabel`; no separators/path |
| `existing_document` | exact `DocumentRef`; binding/backend/output-scope checked |

`ApprovalBinding`, discriminated by `approval_kind`:

| Variant | Fields |
|---|---|
| `exact_owner_request` | `ingress_digest`, `intent_digest`, `unchanged_payload_digest`, `unchanged_destination_digest` |
| `preview_confirmation` | `approval_request_id`, `action_digest`, `preview_digest`, `decision_digest`, `expires_at` |

Delete, trash, sharing, permissions, publication, deployment, money, and
third-party delivery are impossible values in v1.

An update requires an exact expected revision. If the backend cannot implement
`strict_cas_required=true`, policy MUST deny with
`backend_capability_missing`.

## 15. Registry architecture

### 15.1. Registry set

There are exactly three application-owned registries:

- `source` — where metadata/read authority may be resolved;
- `output` — where create/update authority may be resolved;
- `deny` — global and scoped prohibitions.

The three active revisions form one `RegistryBundle`. A contract binds to the
bundle digest, never to a filename or mutable "latest" label.

### 15.2. Signed envelope

Every registry file has:

| Field | Type | Rule |
|---|---|---|
| `envelope_schema` | literal `nobus.registry_envelope.v1` | required |
| `registry_type` | enum `source`, `output`, `deny` | must agree with payload |
| `payload` | typed object | strict, no unknown fields |
| `payload_sha256` | `Digest` | SHA-256 of JCS payload |
| `key_id` | `BoundRef` | accepted verification key |
| `signature_algorithm` | literal `ed25519` | required |
| `signature` | string | base64url without padding, exactly 64 signature bytes |

`signature = Ed25519.sign(JCS(payload))`.

### 15.3. Common payload header

| Field | Type | Rule |
|---|---|---|
| `schema` | literal | `nobus.source_registry.v1`, `nobus.output_registry.v1`, or `nobus.deny_registry.v1` |
| `schema_version` | literal `"1"` | required |
| `registry_id` | `BoundRef` | stable logical registry |
| `registry_version` | strict integer | ≥1, strictly monotonic |
| `issued_at` | `AwareDateTime` | signer time |
| `not_before` | `AwareDateTime` | activation lower bound |
| `expires_at` | `AwareDateTime \| null` | null allowed only by policy |
| `previous_payload_sha256` | `Digest \| null` | chain; null only at genesis |
| `entries` | typed array | unique IDs |

### 15.4. Source registry entry

Common fields:

| Field | Type | Rule |
|---|---|---|
| `scope_id` | `BoundRef` | unique |
| `tenant_id`, `project_ref`, `client_ref` | common binding | exact, no wildcard |
| `enabled` | strict boolean | false denies all |
| `backend` | `Backend` | discriminator |
| `display_label` | `SafeLabel` | model-safe projection |
| `maximum_classification` | `Classification` | ceiling |
| `allowed_document_kinds` | array[`DocumentKind`] | 1..10 |
| `allowed_media_types` | array[`MediaType`] | 1..32 |
| `allowed_operations` | array[enum] | subset `metadata`, `read` |
| `limits_profile` | `BoundRef` | versioned limits |
| `private_locator` | `SourceLocator` | never model-visible |

`SourceLocator`, discriminated by `backend`:

- `local`: private absolute `root_path`, expected local fixed-volume policy,
  provisioned root identity digest, and Bridge device ID;
- `google`: private folder ID, OAuth binding ref, allowed Drive scope family,
  shared-drive ID or null, and shortcut policy fixed to `deny`.

The model-safe projection excludes `private_locator`.

### 15.5. Output registry entry

Common fields:

| Field | Type | Rule |
|---|---|---|
| `scope_id` | `BoundRef` | unique |
| exact tenant/project/client binding | common binding | no wildcard |
| `enabled` | strict boolean | false denies |
| `backend` | `Backend` | discriminator |
| `display_label` | `SafeLabel` | model-safe |
| `allowed_operations` | array[`WriteOperation`] | `create`, optionally `update` |
| `allowed_formats` | array[`OutputFormat`] | 1..8 |
| `maximum_classification` | `Classification` | ceiling |
| `collision_policy` | `CollisionPolicy` | fixed default |
| `snapshot_required_for_update` | strict boolean | true for local |
| `strict_cas_supported` | strict boolean | adapter capability |
| `limits_profile` | `BoundRef` | versioned |
| `private_locator` | `OutputLocator` | never model-visible |

Local private locator contains the private output root and Bridge device.
Google private locator contains the output folder ID and OAuth binding.

### 15.6. Deny registry entry

| Field | Type | Rule |
|---|---|---|
| `rule_id` | `BoundRef` | unique |
| `enabled` | strict boolean | required |
| `tenant_id`, `project_ref`, `client_ref` | exact value or literal `all` only where schema permits global rule | no pattern |
| `backend` | `Backend \| all` | closed |
| `match_kind` | `DenyMatchKind` | closed |
| `values` | array[string] | normalized values for that kind |
| `reason_code` | closed deny reason | safe |
| `priority` | strict integer | 1–10,000; does not override deny semantics |

`DenyMatchKind`:

```text
exact_component
relative_prefix
extension
media_type
classification
document_kind
secret_name_prefix
secret_name_suffix
reparse_any
multiple_hard_links
non_local_volume
google_shortcut
```

Regex, shell glob, arbitrary code, user-supplied provider query, and negative
lookaround rules are forbidden.

Required always-deny coverage includes:

- VPN data;
- arbitrary `Системные`;
- Nobus Memory backups;
- VCS, runtime, virtual environment, cache, log and temp locations;
- secret/token/credential-like names;
- every reparse point;
- non-local/UNC/device volumes;
- Google shortcuts that could cross folder scope.

Nobus Memory is available only through its curated adapter.

### 15.7. Registry bundle

```text
registry_bundle_digest =
  SHA-256(JCS({
    "source": source_payload_sha256,
    "output": output_payload_sha256,
    "deny": deny_payload_sha256
  }))
```

The bundle stores no private signing key.

### 15.8. Load and refresh

Startup/refresh MUST:

1. Read all three candidate envelopes into bounded memory.
2. Reject duplicate JSON keys and enforce input byte limits.
3. Validate envelope and payload schemas.
4. Recompute payload digests.
5. Verify Ed25519 signatures against pinned accepted public keys.
6. Verify time validity and previous-digest chain.
7. Verify strictly increasing versions against durable accepted state.
8. Validate unique IDs, exact bindings, backend/locator compatibility, and
   required always-deny rules.
9. Build immutable indexes off to the side.
10. Compute the bundle digest.
11. Atomically replace the active bundle pointer.
12. Persist accepted versions/digests and a sanitized activation event.

Readers pin one immutable bundle for the whole decision/operation. They MUST
NOT observe a partial refresh.

If refresh fails, the last valid unexpired bundle remains active and a safe
error is emitted. If no valid active bundle exists, all document operations
fail closed.

### 15.9. Rollback

Automatic rollback is forbidden.

An emergency rollback requires:

- explicit owner L4;
- a signed rollback authorization naming current and target bundle digests;
- target signatures and schema revalidation;
- a reason code and expiry;
- durable audit and post-rollback health check.

The monotonic accepted-version store is not silently reduced. The rollback is
recorded as an exceptional activation event.

## 16. Policy decision contract

### 16.1. Decision inputs

The pure policy evaluator receives:

- authenticated principal and trusted ingress digest;
- action and proposed effect;
- exact tenant/project/client binding;
- contract/schema/policy/bundle digests;
- source/output scope entry;
- deny rules;
- `DocumentRef` and revision where applicable;
- requested operation, backend, kind, MIME, classification and sizes;
- adapter capability profile;
- DLP verdict;
- approval/idempotency/revision evidence.

It does not read file content, call a model, resolve paths, call Google, or
mutate state.

### 16.2. Decision outputs

| Field | Type | Rule |
|---|---|---|
| `decision_id` | `Uuid` | server-generated |
| exact tenant/project/client binding | common binding | copied and verified |
| `outcome` | enum | `allow`, `deny`, `require_confirmation`, `require_l4` |
| `reason_code` | `PolicyReasonCode` | closed |
| `matched_rule_ids` | array[`BoundRef`] | deny/allow evidence, no private locator |
| `effective_limits` | closed limits object | never wider than contract/registry |
| `policy_version` | `BoundRef` | active |
| `registry_bundle_digest` | `Digest` | pinned |
| `input_digest` | `Digest` | canonical decision inputs |
| `decision_digest` | `Digest` | canonical decision record |
| `decided_at` | `AwareDateTime` | server time |

### 16.3. Stable reason codes

```text
allow_metadata
allow_read
allow_create_exact
allow_update_exact

validation_failed
unauthenticated
binding_mismatch
registry_invalid
registry_expired
registry_rollback
scope_unknown
scope_disabled
operation_not_allowed
deny_rule_match
classification_exceeded
document_kind_not_allowed
media_type_not_allowed
size_limit_exceeded
path_invalid
containment_failed
reparse_point
multiple_hard_links
identity_changed
secret_detected
dlp_failed
revision_conflict
approval_required
approval_mismatch
idempotency_conflict
backend_capability_missing
provider_unavailable
prompt_authority_attempt
mcp_authority_forbidden
```

Messages exposed outside Core map from reason codes and MUST NOT disclose a
private path, Google ID, another binding, secret match, provider payload, or
whether a guessed cross-tenant document exists.

### 16.4. Precedence

Evaluation order is:

1. schema/digest/authentication;
2. exact tenant/project/client equality;
3. active registry validity and exact scope lookup;
4. global and scoped deny;
5. classification/kind/MIME/size limits;
6. operation and adapter capability;
7. revision/idempotency/approval.

Any deny terminates evaluation. An allow entry never overrides a deny.
Unknown state is deny.

## 17. End-to-end binding invariants

1. `tenant_id` originates only from trusted ingress.
2. `project_ref/client_ref` originate from clarified intent confirmed against a
   model-safe registry projection.
3. Every query scope has exact equality with the intent binding.
4. Every `DocumentRef` repeats and matches the query/scope binding.
5. Every read selection repeats the exact immutable `DocumentRef`.
6. `AnalysisRequest.sources` is set-equal to the accepted read plan.
7. `ArtifactPlan` cannot raise classification or change project/client.
8. `DocumentWritePlan` uses an output scope with the same exact binding.
9. Queue rows, idempotency records, cache keys, ref records, approvals and audit
   use composite binding keys; a UUID alone is never authority.
10. Bridge jobs are signed and bind device, exact binding, operation, scope,
    ref/target, limits, registry/contract/payload digests, expiry and nonce.
11. Google adapter methods receive private locators only after Core policy
    allows the opaque ref.
12. Result/error lookup repeats the original binding; no existence oracle is
    exposed across bindings.

## 18. Windows containment algorithm

### 18.1. Inputs

The Bridge receives a signed job containing an opaque source/output scope and
opaque document ref. It resolves those through its private, digest-matched
registry/ref store.

The model, Core request payload, and user do not provide an absolute root or
executable path.

### 18.2. Lexical component validation

The private relative locator is parsed into components before filesystem I/O.
The Bridge MUST reject:

- empty input or component;
- `.` or `..`;
- NUL, control, bidi-control, wildcard, quote, pipe, redirection, or shell
  metacharacters;
- `/` or `\` inside an already parsed component;
- any colon, preventing drive syntax and ADS;
- leading/trailing whitespace;
- trailing dot or space;
- absolute, drive-relative, UNC, device, volume GUID, `\\?\`, `\\.\`, `\??\`,
  `GLOBALROOT`, or NT object namespace forms;
- DOS reserved device names, including reserved base names before extensions;
- a component over 255 UTF-16 code units;
- a path over the configured component/length limit;
- invalid Unicode or normalization ambiguity.

No `Path.resolve()`, `commonpath()`, string prefix, case-folded prefix, or final
path string is sufficient authority.

### 18.3. Root provisioning

For every local scope, provisioning records:

- Bridge device identity;
- local fixed NTFS volume identity;
- root directory file identity;
- private canonical display path for operator diagnostics only;
- registry entry and digest.

The root MUST be opened as a directory handle. The Bridge MUST reject a root
that is reparse, remote, removable, different from the provisioned volume, or
inside a per-directory case-sensitive tree.

### 18.4. Race-safe component open

For each job:

1. Reopen and verify the provisioned root handle identity.
2. Starting from the pinned parent handle, open each child component relative
   to that handle using an audited `NtCreateFile`/equivalent wrapper with
   `RootDirectory`; no absolute concatenated child path is used.
3. Use `FILE_OPEN_REPARSE_POINT`; ancestors require directory semantics.
4. Query `FileAttributeTagInfo`, `FileIdInfo`, standard information, volume
   identity, link count, and case-sensitivity information.
5. Reject every reparse tag, not only symlink/junction.
6. Reject a volume change, unexpected object type, per-directory case-sensitive
   component, multiple hard links, or identity mismatch.
7. Pin each verified child handle before opening the next component.
8. Open the final object relative to its pinned parent using read/write-specific
   access and share modes.

`GetFinalPathNameByHandleW` MAY be recorded as corroborating evidence after
sanitization; it is not the containment proof.

### 18.5. Read

For a read:

1. Open final object without write sharing where compatible with policy.
2. Verify final non-reparse, single-link, volume/file identity and expected
   revision.
3. Check source byte limit before parsing.
4. Read only through the verified handle.
5. Track bytes and deadline while reading.
6. Recheck identity, size and timestamps after read.
7. Compute SHA-256 over the exact bytes read.
8. Reject mutation, truncation, growth, identity/revision mismatch, or timeout.

If the required share mode cannot be obtained, the operation fails closed
rather than reading a concurrently writable object.

### 18.6. Create/update

Create/update is implemented in Gate 7 using the output scope:

1. Pin and verify the target directory as above.
2. Validate the new single filename component; it is not a path.
3. Create a unique temp file with `CREATE_NEW` inside the pinned directory.
4. Write bounded artifact bytes, flush, reopen/read back, and verify digest.
5. For update, open and verify the exact target, expected digest/revision,
   single-link state, and verified snapshot.
6. Perform handle-relative atomic rename/replace using
   `SetFileInformationByHandle`/`NtSetInformationFile`.
7. Reopen target through the pinned parent, verify file identity/content
   digest, and commit journal state.
8. Unknown outcome enters reconciliation; it is not blindly retried.

### 18.7. Case handling

Windows comparisons use invariant ordinal case-insensitive comparison for
lexical duplicate detection, followed by handle identity. Python `.lower()` or
locale-dependent casing is not sufficient.

Case-sensitive directories are denied in MVP-1. Two locators that normalize to
the same ordinal-insensitive component sequence cannot coexist in one active
scope index.

## 19. Google/local parity and opaque references

| Contract guarantee | Local implementation | Google implementation |
|---|---|---|
| Scope | Private provisioned root | Private provisioned folder/shared drive |
| Model locator | Opaque `source_id` | Opaque `source_id` |
| Metadata search | Bridge bounded index/walk | Drive bounded `files.list` built by adapter |
| Exact selection | Private relative locator + identities | Private file ID + verified ancestry |
| Revision | SHA-256 + volume/file identity | Drive version or Docs revision |
| Read | Verified handle | Bounded API/export response |
| Strict update | Snapshot + digest CAS + atomic replace | Docs `requiredRevisionId` where supported |
| Unsupported strict update | Deny | Sheets strict-CAS plan denied |
| Authority | Signed Bridge job | Server-held OAuth |

Google rules:

1. OAuth credentials and requested scopes exist only in the adapter.
2. A private ref record maps opaque `source_id` to exact Google file/folder
   IDs.
3. File metadata and ancestry are revalidated before every read/write.
4. Shortcuts are denied in MVP-1.
5. Search is metadata-first and bounded by pages, requests and deadline.
6. Google Docs reads use structured API or a verified bounded export.
7. Google Sheets reads use exact ranges and cell limits.
8. Drive/API failure is `provider_unavailable`, not empty results.
9. A Drive version observation does not automatically provide strict CAS.
10. Docs `requiredRevisionId` may implement strict update; `targetRevisionId`
    may not.
11. Sheets `batchUpdate` atomicity does not equal revision CAS. A
    `strict_cas_required=true` Sheets update is denied.

## 20. Classification, DLP, MIME and resource limits

### 20.1. Classification

```text
public       — approved for ordinary provider processing
internal     — owner/project internal; provider policy required
confidential — exact client scope and approved provider/retention profile
restricted   — trusted-local processing by default; model call denied unless a
               future explicit provider policy permits it
```

Classification can only stay equal or become more restrictive downstream.

`secret` is a terminal scanner verdict. Secret content MUST NOT reach model
input, output, durable plaintext state, error messages, telemetry, or external
scanners.

### 20.2. Metadata-first order

1. Validate contract and binding.
2. Apply registry/deny policy.
3. Inspect safe metadata only.
4. Exact owner/system selection.
5. Revalidate revision and containment.
6. Enforce compressed/source byte limits.
7. Validate extension, declared MIME, magic and parser kind.
8. Perform bounded extraction.
9. Run mandatory current scanner.
10. Optionally run pinned Gitleaks via stdin with full redaction.
11. Apply classification/provider policy.
12. Build ephemeral tool-less model context.
13. Validate output and run exfiltration checks.

### 20.3. Required limits profile

MVP-1 hard ceilings:

| Resource | Ceiling |
|---|---:|
| Registry file | 4 MiB each |
| Registry entries | 10,000 each |
| Metadata candidates | 50/query |
| Metadata pages | 5/query |
| Provider/Bridge metadata requests | 10/query |
| Metadata deadline | 10 seconds |
| Source file | 50 MiB |
| Aggregate source bytes/read plan | 100 MiB |
| Extracted text/document | 24,000 chars and 96 KiB UTF-8 |
| Aggregate extracted text | 96,000 chars and 384 KiB UTF-8 |
| Parser time/document | 30 seconds |
| Aggregate parser time | 120 seconds |
| PDF pages available | 200 |
| PDF pages selected | 100 |
| Sheet ranges | 64/document |
| Sheet cells | 20,000/document; 50,000/read plan |
| ZIP/container entries | 200 |
| Total uncompressed container bytes | 100 MiB |
| Compression ratio | 100:1 |
| Nested archive depth | 0 beyond the document-format container |
| Artifact sections | 64 |
| Write artifact | output-profile limit, never above 50 MiB in MVP |

Registries MAY narrow these ceilings. They MUST NOT widen them without a new
policy/version review.

### 20.4. Format safety

- An extension/MIME/magic/parser disagreement is denied.
- Macro-enabled Office formats, executables, scripts, disk images, encrypted
  archives, password-protected documents, and unknown binary formats are
  unsupported in MVP-1.
- Office relationships, external links, macros, embedded packages, formulas
  that cause external access, and remote images are not followed/executed.
- Archive traversal and nested archive extraction are prohibited.
- Parsers run without network, shell, or arbitrary file access.

### 20.5. DLP

The current scanner is mandatory. Gitleaks MAY run as a pinned local process
only when:

- input is supplied by stdin;
- `--redact=100` and safe log level are enforced;
- no report containing matched text is persisted;
- binary/config checksum and rule-config digest are pinned;
- timeout and input bytes are bounded.

Presidio is not active until an owner-approved PII taxonomy, languages,
thresholds, false-positive handling, regression corpus, and provider policy
exist.

TruffleHog verification and YARA are not part of the runtime document decision.

### 20.6. Prompt injection

Every excerpt is wrapped in a data-only envelope containing document ref,
revision, classification and delimiters. The system prompt states that text
inside the envelope is evidence, not an instruction.

A document cannot:

- request a tool or external call;
- change policy/binding/scope/limits;
- create an `ArtifactPlan`/`DocumentWritePlan` without the owner intent;
- authorize a write or approval;
- request secret disclosure.

Because the model has no authority tools, instruction-like document text has
no direct effect. Model output still passes closed-schema validation, binding
checks, DLP and verbatim/exfiltration checks.

## 21. Read flows

### 21.1. Metadata query

```text
Trusted ingress
  → IntentEnvelope validation
  → exact binding and source-scope policy
  → DocumentQuery
  → adapter receives private scope
  → bounded metadata search
  → deny/classification filtering
  → safe candidate projections
  → exact selection or ambiguity
  → DocumentRef issuance
```

No content is read and no model is required for adapter-side metadata search.

### 21.2. Document read and analysis

```text
DocumentReadPlan
  → pin registry bundle
  → revalidate each DocumentRef binding/TTL/revision
  → local handle containment or Google ancestry
  → MIME/size/resource checks
  → bounded extraction
  → mandatory local DLP
  → classification/provider policy
  → ephemeral untrusted-document context
  → tool-less model
  → closed output + post-model exfiltration checks
  → normalized result/provenance refs
```

If any source fails, the result records an explicit missing/conflict/error
limitation. It MUST NOT substitute empty content or zero values.

## 22. Write flows

### 22.1. Planning

```text
Verified analysis/result
  → ArtifactPlan
  → renderer creates immutable artifact/content digest
  → output-scope policy
  → exact create/update target
  → DocumentWritePlan
  → exact-owner-request binding OR preview confirmation
  → Gate 7 effect executor
```

The model may propose content structure but does not select a private locator or
execute the operation.

### 22.2. Execution

The executor MUST:

1. Reload the immutable write plan by digest.
2. Revalidate tenant/project/client, policy and registry bundle.
3. Verify output scope, operation, format, classification and backend
   capability.
4. Verify artifact, target, revision, approval and idempotency digests.
5. Execute once through the backend adapter.
6. Perform readback/revision verification.
7. Record a sanitized receipt.
8. Reconcile unknown outcome before any retry.

`collision_policy=new_version` creates a deterministic new name through the
adapter. It never overwrites the original. `ask` returns a clarification.

## 23. Index, cache and durable-state boundaries

Durable metadata MAY contain:

- exact tenant/project/client binding;
- scope/ref UUIDs;
- safe display label;
- kind, MIME, size, classification;
- revision/content/metadata/registry/contract digests;
- provider/Bridge adapter identity;
- timestamps, TTLs, decisions, reason codes, idempotency and receipts;
- private locator in an access-controlled adapter/ref store, never in general
  task/model state.

Durable state MUST NOT contain:

- plaintext local or Google document content/excerpts;
- raw DLP matches;
- prompts containing document excerpts;
- OAuth tokens/secrets;
- signing private keys;
- raw local paths in events, errors or model records;
- data of another binding.

Metadata indexes and caches are keyed at minimum by:

```text
tenant_id
project_ref
client_ref
scope_id
registry_bundle_digest
document_ref_id or query digest
revision
```

No global cache key may omit the exact binding. Cache entries inherit source
classification and TTL. A registry refresh, revision change, or binding change
invalidates the entry.

Extraction is in bounded memory. A parser requiring durable plaintext temp
files is not admitted until Gate 5 defines an encrypted, access-controlled,
crash-cleaned contract; the default is fail-closed.

The intended final output artifact is not a cache. Its location is controlled
by the output registry and Gate 7 write contract.

## 24. Code impact map

This section is a future implementation map, not authorization to edit code.

| Path | TARGET impact |
|---|---|
| [`src/contracts/models.py`](../../../src/contracts/models.py) | Add strict common primitives or split document models into a dedicated imported module; close current free source/permissions |
| `src/contracts/document_models.py` (new) | Seven v1 contracts, discriminated revisions/selections/targets, schema/digest validation |
| `src/application/scope_registry.py` (new) | Strict registry envelopes/payloads, JCS digest/signature, immutable indexes, atomic activation, anti-rollback |
| [`src/core/policy.py`](../../../src/core/policy.py) | Pure Gate 2 policy input/output and stable reason codes; deny-overrides |
| `src/application/document_gateway.py` (new) | Query/ref/read-plan orchestration and model-safe projections |
| [`src/application/owner_files.py`](../../../src/application/owner_files.py) | Reuse metadata/extraction/DLP; accept opaque ref and verified handle interface rather than model path |
| [`src/application/owner_workspace.py`](../../../src/application/owner_workspace.py) | Reuse snapshot/CAS/atomic/readback/journal under output-scope/write-plan binding |
| `src/integrations/windows_safe_io.py` (new or extracted) | Narrow root-relative handle/identity API; no generic filesystem API |
| [`src/integrations/google_drive.py`](../../../src/integrations/google_drive.py) | Opaque ref mapping, exact scope/binding, version metadata, private query building |
| `src/integrations/google_documents.py` (future Gate 3/5/7) | Docs/Sheets structured read/write capabilities and revision reporting |
| [`tests/test_contracts.py`](../../../tests/test_contracts.py) | Seven schemas, strictness, digests, versions, bindings |
| `tests/test_scope_registry.py` (new) | Signature, canonicalization, atomic refresh, rollback/tamper/precedence |
| `tests/test_document_policy.py` (new) | Exhaustive binding/action/classification/capability decisions |
| [`tests/test_owner_files.py`](../../../tests/test_owner_files.py) | Ancestor/final identity, all reparse tags, hard links, races, MIME/decompression/DLP |
| [`tests/test_owner_workspace.py`](../../../tests/test_owner_workspace.py) | Output scope, CAS, relative-handle replace, unknown outcome |
| [`tests/test_google_drive_adversarial.py`](../../../tests/test_google_drive_adversarial.py) | Cross-folder, shortcut, opaque ref, revision and scope mismatch |
| `tests/test_document_contract_properties.py` (new) | Property-based path, contract and binding corpus if dependency review permits |

No parallel second contract model or compatibility framework is allowed.

## 25. Cross-Gate handoffs

### Gate 1 — Natural Language and Voice Kernel

Gate 1 provides:

- authenticated ingress digest and conversation binding;
- `IntentEnvelope` producer;
- action/entity/ambiguity normalization;
- clarification without inventing scopes.

Gate 1 MUST NOT emit private paths, Google IDs, permissions, or OAuth.

### Gate 3 — Google Foundation

Gate 3 provides:

- OAuth binding and secure credential storage;
- exact approved scopes and API health;
- provider budget/retention/circuit breaker;
- closed Google response normalization.

It consumes private Google registry locators but does not expose them to the
model. The `google-auth` upgrade decision belongs to Gate 3.

### Gate 5 — Unified Document Gateway and Windows Bridge

Gate 5 implements:

- the opaque ref store;
- registry-bound local/Google metadata search;
- Windows handle/identity algorithm and Bridge signed jobs;
- bounded Docs/Sheets/PDF/local extraction;
- offline/reconnect/replay behavior;
- prompt-injection isolation.

Gate 5 must prove real Windows NTFS race/reparse tests in test-only scopes.

### Gate 6 — Multi-document Analytics

Gate 6 consumes only accepted `DocumentReadPlan` and `AnalysisRequest`.
Normalized facts retain document/ref/revision provenance. Missing values and
conflicts are explicit.

### Gate 7 — Artifact Factory and writeback

Gate 7 implements `ArtifactPlan` rendering and `DocumentWritePlan` execution,
including snapshot/CAS/revision/readback/idempotency/reconciliation.

Sheets strict-CAS mismatch remains denied unless a later approved contract
defines weaker semantics explicitly.

### Gate 8 — Hybrid Release

Gate 8 pins:

- release commit;
- source/output/deny and aggregate bundle digests;
- Google folder registry digest;
- Bridge device identity and signing keys;
- policy/schema versions.

Readiness fails if registry, Bridge, Google, DB or runtime health is stale or if
an orphan/unknown effect is unreconciled.

## 26. Implementation slices

Each slice is independently reviewed and remains TARGET until verified.

1. **Contract primitives:** strict base, scalar aliases, enums, JCS, schema and
   instance digest goldens.
2. **Seven contracts:** models, generated schemas, round-trip and negative
   tests.
3. **Registry envelopes:** source/output/deny payloads, signature, chaining,
   aggregate bundle and atomic loader.
4. **Pure policy:** decision models, exact binding, deny precedence, reason
   codes and exhaustive tables.
5. **Local boundary contract:** private ref record and audited Windows I/O
   interface with synthetic/TestTemp tests only.
6. **Google boundary contract:** private ref record, adapter capabilities and
   synthetic response tests only; no live Google calls in Gate 2.
7. **DLP/resource profiles:** current scanner integration contract,
   decompression/MIME limits and optional Gitleaks interface.
8. **Migration:** current draft source/permissions inventory and in-place
   pre-wire migration.
9. **Cross-Gate handoff:** schema/registry/policy digests, evidence manifest,
   unresolved owner decisions, Gate 5/7 capability gaps.

## 27. Migration and deprecation

The current wire protocol is not externally frozen. Migration MUST be in place,
not a permanent dual model.

### 27.1. `TaskContract.source`

- Replace free `str` with the existing closed ingress source enum for generic
  tasks.
- `IntentEnvelope.source_scope[].scope_ref` remains a Gate 1 opaque selector;
  trusted Gate 2 resolution emits exact `DocumentQuery.source_scope_ids`.
- A legacy source string MUST NOT be interpreted as a path, Google provider
  query, scope, or permission.
- Unknown stored values are quarantined for owner review, not guessed.

### 27.2. `TaskContract.permissions`

- Replace free strings with the canonical closed permission registry.
- Document permissions are derived from policy + registry operation; the model
  cannot add permissions.
- `external.write_l4` means permission to request approval, not execute a
  write.
- Unknown permissions fail migration.

### 27.3. `allowed_paths`

- Generic repository tasks may retain their separate allowlisted path contract
  until its own migration.
- Document tasks MUST NOT use `allowed_paths`.
- Local document authority uses only `source_scope_id/output_scope_id` and an
  opaque ref.
- No automatic conversion from an arbitrary historical path to a document
  scope is permitted.

### 27.4. Durable migration

Before migration:

1. inventory affected rows by schema/source/permission without reading document
   content;
2. stop new admissions and drain/expire leases;
3. create verified DB backups;
4. map only known closed values;
5. recompute contract/schema digests;
6. preserve old record/digest as audit evidence;
7. quarantine non-mappable rows;
8. run migration and rollback tests for all affected SQLite stores;
9. remove transitional readers after one verified release.

Long-lived dual-write or "try old schema on validation failure" is forbidden.

## 28. Test matrix

### 28.1. Contract and version tests

| Case | Expected |
|---|---|
| Unknown field at every nesting level | reject |
| Unknown schema/version/enum/discriminator | reject |
| Missing schema/contract digest | reject |
| Wrong generated schema digest | reject |
| Contract digest mismatch | reject |
| Duplicate JSON key | reject before Pydantic |
| String→integer/boolean coercion | reject |
| Boolean as integer | reject |
| Naive datetime/non-finite number | reject |
| Mutable accepted instance | impossible |
| v1 reader receives v2 | reject |
| Pydantic upgrade changes schema digest | golden failure |

### 28.2. Binding tests

Property matrix covers every pairwise and triple swap:

- tenant only;
- project only;
- client only, including `null` versus non-null;
- tenant+project;
- tenant+client;
- project+client;
- all three.

The matrix runs at:

- intent→query;
- query→scope;
- candidate→DocumentRef;
- ref→read plan;
- read plan→analysis;
- analysis→artifact;
- artifact→write plan;
- write plan→output scope;
- queue/job→Bridge/Google adapter;
- result/approval/idempotency/cache lookup.

Every mismatch is a safe deny with no existence disclosure.

### 28.3. Registry tests

| Case | Expected |
|---|---|
| Byte tamper | digest/signature reject |
| Valid signature from unknown key | reject |
| Wrong registry type/schema | reject |
| Duplicate scope/rule ID | reject |
| Missing mandatory deny | reject |
| Version equal/lower than accepted | rollback reject |
| Broken previous-digest chain | reject |
| Expired/not-yet-valid registry | reject |
| Source new, output/deny old | no activation |
| Invalid candidate refresh | retain last valid unexpired bundle |
| Contract pins old bundle after refresh | reject/replan |
| Deny and allow both match | deny |
| Explicit signed L4 rollback absent/expired | reject |

### 28.4. Windows lexical/path tests

Include generated and fixed cases for:

- empty, dot, dot-dot and mixed separators;
- absolute and drive-relative paths;
- UNC, device, volume GUID, `\\?\`, `\\.\`, `\??\`, `GLOBALROOT`;
- ADS and colon variants;
- trailing dot/space and Unicode whitespace;
- reserved DOS names, extensions and case variants;
- invalid Unicode, normalization and bidi controls;
- wildcard/shell metacharacters;
- long component/path;
- drive-letter and component case collisions;
- 8.3 aliases where enabled.

All fail before content access.

### 28.5. Windows identity/race tests

On real NTFS test scopes:

- root symlink/junction/mount/cloud reparse;
- every ancestor reparse type;
- final reparse;
- reparse created between validation/open;
- ancestor swapped concurrently;
- final file replaced concurrently;
- file mutated/truncated/grown during read;
- file moved during read;
- cross-volume target;
- hard link inside/outside scope;
- multiple-link target before update;
- directory case-sensitivity enabled;
- root identity changed after registry activation;
- CAS target changed after snapshot;
- crash before/after temp flush/rename/readback/journal commit;
- concurrent same idempotency key and conflicting payload.

Expected result is fail-closed or deterministic recovery; no outside bytes are
returned.

### 28.6. Google tests

- file ID from another binding;
- file outside registered folder/shared drive;
- folder ancestry changes after query;
- shortcut inside scope targeting outside;
- duplicate/ambiguous metadata candidates;
- page/request/deadline exhaustion;
- Drive API failure versus empty results;
- stale Drive version;
- stale Docs `requiredRevisionId`;
- Docs `targetRevisionId` incorrectly used for strict CAS;
- Sheets strict-CAS request;
- oversize/export truncation;
- OAuth binding/scope mismatch;
- raw Google query/file ID/token appears in model payload/log.

### 28.7. MIME/parser/resource tests

- extension/MIME/magic mismatch;
- polyglot;
- unsupported/encrypted/password-protected file;
- macro-enabled Office file;
- external relationship/remote image;
- XML entity expansion;
- ZIP slip;
- nested archive;
- excessive entry count;
- compressed bytes, uncompressed bytes, ratio and parser timeout boundary
  values;
- PDF page and Sheet range/cell overflow;
- aggregate read-plan overflow;
- parser cancellation and cleanup.

### 28.8. DLP/exfiltration tests

- secret-like names denied metadata-first;
- token/key/password/cookie/private-key patterns;
- high entropy, chunked base64/hex and encoded variants;
- raw scanner match absent from logs/errors;
- optional Gitleaks receives stdin and redacts output;
- DLP unavailable/timeout returns fail-closed;
- model answer repeats forbidden excerpt;
- transformed/verbatim overlap exfiltration;
- cross-document reconstruction of a secret.

### 28.9. Prompt/MCP authority tests

Document text attempts to:

- override system/policy;
- request filesystem/Google/shell/network/browser/MCP tools;
- reveal roots/OAuth/registry;
- change tenant/project/client/scope;
- authorize a write/delete/share;
- increase limits/classification/provider retention;
- embed a fake `DocumentWritePlan`.

Expected:

- text remains untrusted data;
- no tool is available;
- closed output rejects authority fields;
- policy decision remains unchanged.

Attempting to register or call a generic filesystem/Google MCP server returns
`mcp_authority_forbidden`.

### 28.10. Google/local parity properties

For the same semantic fixture, both adapters MUST produce equal:

- model-safe `DocumentRef` fields;
- classification and limits;
- ambiguity/not-found/provider-failed distinctions;
- stale revision behavior where strict CAS exists;
- prompt/data envelope and provenance requirements;
- safe reason-code family.

Backend-only fields MUST remain private. If a backend lacks the required
guarantee, it denies rather than returning a weaker success.

## 29. Gate 2 acceptance / Definition of Done

Gate 2 implementation is PASS only when:

1. All seven Pydantic models and their nested models are strict, frozen,
   unknown-field rejecting and generated as closed JSON Schemas.
2. Schema and instance canonicalization have cross-process golden digests.
3. Source/output/deny registries have strict schemas, signatures, digest chain,
   anti-rollback and atomic three-file activation.
4. Pure policy has closed inputs/outputs/reason codes and exhaustive
   deny-overrides tests.
5. Tenant/project/client swaps fail at every end-to-end boundary.
6. No model contract contains an absolute root, executable path, Google
   backend ID, OAuth authority or free capability.
7. Windows lexical and identity interfaces reject device/UNC/ADS/reserved
   names, reparse, hard links and identity races in the authorized test scope.
8. Google/local contract parity and capability-deny behavior are proven with
   synthetic tests.
9. Metadata-first, MIME/resource/decompression, mandatory DLP,
   prompt-injection-as-data and post-model exfiltration contracts pass.
10. Generic filesystem/Google MCP authority is impossible by policy and
    dependency/config manifest.
11. No plaintext owner document content is durable.
12. Current free source/permissions migration has inventory, rollback and
    regression evidence.
13. Required L1/L2/L3 evidence and clean manifest exist.
14. Only explicitly authorized Gate 2 files/test fixtures are changed.
15. Gate 1/3/5/6/7/8 handoffs identify exact schema, policy and registry
    digests.

Documentation alone does not make any TARGET behavior CURRENT.

## 30. Unresolved owner decisions

Defaults are fail-closed. These decisions do not block the architecture but
must be resolved before their implementation slice:

1. Whether clientless owner work remains `client_ref=null` as in the canon or
   moves to an explicit reserved owner client in the first frozen wire version.
2. Exact local source/output scopes, fixed NTFS volume, Bridge OS account and
   filesystem ACLs.
3. Registry signing-key owner, offline storage, rotation, revocation and
   emergency rollback approver.
4. Whether every local hard link remains denied or an owner-approved
   provisioned exception is ever needed.
5. Exact Google OAuth mode per source: owner Picker/`drive.file`, shared test
   folder, service account, or restricted `drive.readonly`.
6. Whether `restricted` documents are always local-only in MVP-1.
7. Final allowed MIME/format list and whether password-protected documents are
   permanently unsupported.
8. Whether Gitleaks is deployed in Bridge/Core or remains a release/test
   reinforcement.
9. Google Sheets write policy: create-only, explicit weaker confirmed update in
   a future version, or no update.
10. Registry expiry duration and emergency operation when the signer is
    unavailable.
11. Exact metadata/ref-store encryption and retention profile.
12. Property-test dependency choice versus a repository-native generated test
    corpus.

## 31. Architecture verification

### L1 — required structure and deterministic invariants

This document defines:

- product behavior, non-goals and CURRENT/reuse/TARGET;
- trust, authority and threat model;
- exact seven contract schemas, enums, limits, validation, digests and
  evolution;
- all three registries, signing, activation and rollback;
- policy inputs/outputs/reason codes;
- end-to-end binding;
- Windows and Google/local algorithms;
- classification, DLP, MIME/decompression and prompt boundaries;
- read/write/cache flows;
- code impact, Gate handoffs, slices, migration, tests, DoD and owner
  decisions.

No credential, token, cookie, raw owner document, private key, or real backend
locator is included.

### L2 — canonical/research reconciliation

The architecture was reconciled against:

- the canonical commit and roadmap/contract/ADR/status sources listed in
  [`RESEARCH.md`](RESEARCH.md);
- current contract, owner-file, owner-workspace, policy and Google adapter
  behavior;
- official Pydantic, JSON Schema, RFC, Microsoft, Google and MCP sources;
- upstream policy, DLP and MCP repositories and releases.

### L3 — adversarial architecture audit

The normative controls and test matrix explicitly cover:

- tenant/project/client swaps;
- registry rollback and tamper;
- lexical path escape, reparse, hard-link and TOCTOU races;
- MIME lies and decompression bombs;
- secret input/output exfiltration;
- prompt injection;
- arbitrary MCP authority;
- Google/local concurrency mismatch.

Any missing guarantee results in deny, replan, clarification, reconciliation,
or human decision; it is not relabelled as success.
