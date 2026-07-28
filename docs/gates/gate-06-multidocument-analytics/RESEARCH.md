# Gate 6 Research Dossier — Multi-Document Analytics

Document status: `RESEARCH READY`
Evidence cut-off: `2026-07-28`
Canonical baseline: repository commit `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
Implementation status: `TARGET`, not CURRENT
Scope: read-only research and architecture evidence. No real owner/client document was read, uploaded, or sent to a model; no runtime, dependency, credential, remote, or deployment change was performed.

## 1. Executive conclusion

Nobus SHOULD implement Gate 6 as a typed analytical pipeline, not as document chat and not as RAG-first retrieval:

`AnalysisRequest → bounded native/structured reads → NormalizedFacts + lineage → explicit reconciliation → deterministic calculations → one AnalysisResult + digest`

The recommended baseline is:

- existing Nobus trust, tenant, selection, DLP, digest, idempotency, job and artifact primitives;
- official Google Sheets and Docs structured APIs for Google-native sources;
- `openpyxl`, `python-docx` and `pdfplumber` for local structured reads;
- bounded OCR only after a deterministic reader reports that text/table extraction is insufficient;
- Pydantic contracts, Python `decimal`/`datetime`/`zoneinfo`, SQLite for durable state and DuckDB for bounded ephemeral analytical execution;
- a separate pure-Python `Decimal` reference implementation for independent reproduction;
- Hypothesis as a development-only property-test dependency;
- Codex as primary planning/narrative/semantic verifier and Gemini as an optional bounded document specialist;
- no model as calculator, conflict authority, revision authority, access-control authority, or source of unobserved facts.

The same contracts MUST serve `LOCAL`, `GOOGLE`, and `MIXED` source modes. Source transport can differ; normalized facts, calculations, provenance, verification, and Gate 7 rendering cannot.

The decisive semantic rules are:

1. `MISSING`, `PRESENT_NULL`, `PRESENT_BLANK`, `INVALID`, `CONFLICT`, `OCR_UNCERTAIN`, and observed numeric zero are different states.
2. Conflicts MUST remain visible until a versioned deterministic rule or an explicit owner decision resolves them.
3. A calculation MUST be reproducible from bound source revisions, normalized input fact digests, a versioned rule, parameters, engine identity, and rounding/currency/time policies.
4. Gate 7 formats MUST render one `AnalysisResult`; renderers MUST NOT recalculate.
5. Raw documents and unbounded excerpts MUST NOT be placed in model context merely because a provider supports long context or file upload.

## 2. Research question and evidence method

The research tested whether Nobus can answer owner questions such as:

> For client `client-017`, article `SKU-042`, and Moscow business period `[2026-06-01, 2026-07-01)`, reconcile sales, spend, clicks, and orders across one local workbook and two Google files; show conflicts and source cells; calculate approved funnel metrics; generate a reusable result for Telegram, JPEG, HTML, and XLSX.

The answer is `yes`, but only if identity, period, source snapshots, fact state, reconciliation, formula semantics, and lineage are first-class contracts.

### 2.1 Evidence levels

| Level | Meaning | Use |
|---|---|---|
| E1 | Official documentation, official repository, standard, security or pricing page | Capability, lifecycle, limit, license and provider-policy claims |
| E2 | Canonical Nobus code, tests and documentation at the baseline commit | CURRENT/reusable assessment |
| E3 | Maintained third-party repository or peer-reviewed/archival paper | Candidate comparison and test-corpus design |
| I | Nobus-specific architectural inference | Recommendation; never presented as provider fact |

Versions are observations at the evidence cut-off, not floating dependency instructions. Implementation MUST pin exact versions and hashes after Gate 8 supply-chain review.

### 2.2 Repository scope reviewed

The canonical review covered `AGENTS.md`, document 12, ADR 0002, 0014 and 0017, documents 05 and 09, `CURRENT-STATUS`, `MVP-1-ISSUES`, and relevant owner-file, Google Drive, workspace/artifact, document-analysis code and tests. Historical Nobus Memory was not used as authority.

## 3. CURRENT baseline and reusable blocks

### 3.1 What is safe and reusable

| CURRENT block | Verified value for Gate 6 | Reuse boundary |
|---|---|---|
| Owner file selection | Containment, bounded candidate selection, ambiguity handling, size limits, DLP/digest checks | Reuse discovery and trust controls, not flat extraction as facts |
| Google Drive integration | Search, folder and link resolution, ambiguity handling, bounded download/export | Reuse authorization and discovery; add native Sheets/Docs readers |
| Owner workspace/artifacts | Snapshot/CAS and atomic apply patterns | Reuse immutable result and digest semantics |
| Job/idempotency patterns | Durable state, bounded execution, explicit outcomes | Reuse for analysis jobs and cancellation |
| Tests | Malformed inputs, containment, DLP, bounds, replay and ambiguity patterns | Extend to analytical semantics and lineage |

### 3.2 The analytical gap

The existing owner-file path can produce bounded flat text from selected files. Its raw ZIP/XML handling of XLSX/DOCX is appropriate as a defensive preview fallback, but it does not preserve the analytical identity needed by Gate 6:

- workbook/sheet/table/row/column/cell coordinates;
- formula versus cached/effective/displayed value;
- typed decimals, currency, locale, timezone and units;
- exact client, SKU/article and half-open business period;
- source revision binding;
- cross-document duplicate and conflict sets;
- versioned formulas and reproducible calculation manifests.

The current Google Drive export path similarly treats Sheets and Docs as downloadable files. It does not yet provide native tab/range/cell or Docs tab/structure lineage. Therefore CURRENT is **bounded flat extraction**, not **analytical facts**.

This gap does not justify a second orchestrator or a generic agent framework. It requires one narrow analytics domain behind existing Nobus boundaries.

## 4. Query planning and normalized facts

### 4.1 Why an exact request precedes extraction

Business documents usually contain many clients, articles, months, summary rows, display formulas, hidden tabs and duplicated exports. “Summarize these files” is not an analytical contract. A bounded `AnalysisRequest` must state:

- tenant/project/owner scope;
- canonical client identifier and permitted aliases;
- SKU/article selectors;
- half-open period and business timezone;
- an allowlist of sources and source mode;
- metric identifiers and groupings;
- rule versions or a governed rule-set reference;
- local/cloud/model/OCR policy;
- byte, cell, row, page, token, time and cost ceilings.

A planner may use a model to propose source slices or mappings, but Core MUST validate the proposal against closed DTOs, source allowlists, tenant scope and monotonic budgets. Hidden reasoning is not authority; the accepted plan contains explicit reason codes and a digest.

### 4.2 Deterministic stages

| Stage | Deterministic responsibility | Permitted model contribution |
|---|---|---|
| Request validation | Entity IDs, period, policy and budget validation | Clarify an ambiguous owner phrase before execution |
| Source selection | Allowlist, metadata filters, revision binding, range/page budget | Propose candidate tabs/headers from bounded metadata |
| Extraction | Native/API/library reads into typed observations | Bounded visual/OCR specialist only when approved |
| Normalization | Locale-aware parse, units, canonical keys, fact state | Suggest a column-to-metric mapping with evidence |
| Reconciliation | Duplicate/conflict classification and governed resolution | Explain unresolved differences, never choose silently |
| Calculation | Approved rules using decimals and explicit policies | None |
| Narrative | Render facts, conflicts, limitations and provenance | Primary permitted model role |
| Verification | Digest, schema, invariants, reference calculations | Independent semantic check, not numeric authority |

### 4.3 RAG is not the baseline

Vector similarity is useful when the primary question is semantic discovery over large prose corpora. Gate 6 asks exact questions over bounded clients, SKUs, periods and metrics. Metadata filters, native ranges, table structure, typed keys and deterministic joins provide stronger precision and lineage.

RAG/vector storage MAY be reconsidered only if a benchmark demonstrates all of the following:

1. a real corpus contains unindexed semantic concepts that metadata/query planning cannot locate;
2. recall improves materially on a preregistered golden set;
3. exact source locators and revision binding survive retrieval;
4. false joins and cross-tenant retrieval remain zero;
5. privacy, retention, cost and operations are acceptable;
6. the added system reduces total code or measured latency enough to justify it.

No reviewed evidence meets that threshold for the MVP business-document workloads.

## 5. Tabular computation landscape

### 5.1 Compared engines and libraries

| Candidate | Maturity/version evidence at cut-off | License | Strength | Cost/fit | Verdict |
|---|---|---|---|---|---|
| Python stdlib + SQLite | Python-supported `decimal`, `datetime`, `zoneinfo`, `csv`, `sqlite3` | PSF / public-domain SQLite | Minimal, portable, exact reference path | More code for complex joins/pivots | **Adopt** for contracts, durable state and independent reference |
| DuckDB | `1.5.5`, released 2026-07-22; Python API and security controls documented | MIT | Strong SQL joins, windows, grouping, Parquet/CSV integration | Native wheel; extension loading must be locked down | **Adopt** as bounded ephemeral calculation engine |
| Polars | Maintained lazy and streaming APIs | MIT | Fast typed DataFrames, optimizer and streaming | Duplicates DuckDB in MVP | Fallback after measured bottleneck |
| pandas | `3.0.5` observed; broad ecosystem | BSD-3-Clause | Familiar manipulation and file interoperability | Mutable/nullable dtype complexity; another baseline | Do not add initially |
| Ibis | Multi-backend relational API | Apache-2.0 | Portable expressions across engines | No demonstrated multi-backend need | Reject for MVP |

Primary sources: [DuckDB release calendar](https://duckdb.org/release_calendar), [DuckDB Python API](https://duckdb.org/docs/current/clients/python/overview), [DuckDB securing guide](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview), [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency), [DuckDB license](https://github.com/duckdb/duckdb/blob/main/LICENSE), [Polars lazy API](https://docs.pola.rs/user-guide/lazy/using/), [pandas release notes](https://pandas.pydata.org/docs/whatsnew/), [Ibis rationale](https://ibis-project.org/why).

DuckDB MUST run without user-provided SQL. Production configuration MUST disable automatic extension installation/loading and community extensions unless a later security review explicitly approves a pinned extension. DuckDB `2.0` is announced for a later release train; Gate 8 MUST run the full golden regression before any major upgrade.

### 5.2 Schema and property validation

| Candidate | Version/license evidence | Fit | Verdict |
|---|---|---|---|
| Existing Pydantic | Already part of Nobus contract discipline | Closed DTOs, strict validation, JSON schema | **Adopt** |
| Pandera | `0.31.1`, MIT | Strong dataframe validation | Do not add without a dataframe baseline |
| Hypothesis | Maintained, MPL-2.0 | Generates edge cases for decimals, periods, joins and missing states | **Adopt for tests only** |

Sources: [Pandera repository](https://github.com/unionai-oss/pandera), [Hypothesis introduction](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html), [Hypothesis repository/license](https://github.com/HypothesisWorks/hypothesis).

The independent numeric path SHOULD be a small pure-Python implementation using `Decimal`, sorted input facts and the same published rule semantics. It MUST NOT call DuckDB or share the production SQL expression.

## 6. Structured document readers

### 6.1 Google-native reads

Google Sheets exposes bounded structured reads through `spreadsheets.get` with `ranges` and field masks. `CellData` distinguishes `userEnteredValue`, `effectiveValue` and `formattedValue`, while spreadsheet properties expose locale and timezone. These are the correct primitives for cell lineage and formula/value distinction. Sources: [spreadsheets.get](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get), [CellData](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells), [field masks](https://developers.google.com/workspace/sheets/api/guides/field-masks).

Google Docs has a structured document model with tabs, structural elements and UTF-16 indexes. `documents.get` with tab content is preferable to DOCX export when native lineage matters. Sources: [Docs structure](https://developers.google.com/workspace/docs/api/concepts/structure), [Docs tabs](https://developers.google.com/workspace/docs/api/how-tos/tabs).

Drive metadata is the discovery and snapshot boundary. Google editor files do not expose the same blob `headRevisionId` semantics as binary Drive files; the monotonically increasing Drive `version` and returned document/spreadsheet metadata must be bracketed before and after a read. A change causes retry or `SOURCE_CHANGED`, never silent mixing. Source: [Drive files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files).

### 6.2 Local reads

| Format | Primary reader | Preserved identity | Limitation/fallback |
|---|---|---|---|
| XLSX | `openpyxl 3.1.3` | Workbook, sheet, cell coordinate, formula/cached/display context, dates | Does not calculate formulas; cached values must be distinguished |
| DOCX | `python-docx 1.2.0` | Document part, paragraphs, tables, row/column positions | Complex floating layout/text boxes need explicit unsupported/alternate path |
| PDF | `pdfplumber 0.11.9` | Page, text words, bounding boxes, table cells | Works best on machine-generated PDFs; OCR required for scans |
| CSV/TSV | stdlib `csv` with explicit encoding/dialect | Line/row/column | Locale and encoding ambiguity must be surfaced |

Sources: [openpyxl tutorial](https://openpyxl.readthedocs.io/en/stable/tutorial.html), [python-docx quickstart](https://python-docx.readthedocs.io/en/latest/user/quickstart.html), [pdfplumber repository](https://github.com/jsvine/pdfplumber).

### 6.3 OCR and general extraction candidates

| Candidate | Evidence | Russian/tables/privacy/ops | Verdict |
|---|---|---|---|
| Docling | MIT; unified PDF/DOCX/XLSX/image support; published pipeline and model catalog | Local, table/layout capable, but model-heavy and redundant for native office formats | Optional bounded PDF/image OCR adapter |
| Apache Tika `3.3.2` | Apache-2.0, broad format parser | Java process and generic text metadata; weak cell-level lineage | Reject baseline |
| Unstructured | Open-source partitioning plus separate managed product | Broad OCR/partitioning, heavy dependency/product boundary | Reject baseline; benchmark only for a proven hard format |
| PyMuPDF | Fast PDF API | AGPL/commercial licensing boundary | Reject unless legal/commercial approval changes the decision |
| LlamaIndex/LangChain loaders | MIT framework ecosystems | Convenient loader catalog, but not reconciliation/calculation authority | Reject baseline |

Sources: [Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/), [Docling model catalog](https://docling-project.github.io/docling/usage/model_catalog/), [Docling paper](https://arxiv.org/abs/2408.09869), [Docling license](https://github.com/docling-project/docling/blob/main/LICENSE), [Apache Tika](https://tika.apache.org/), [Unstructured partitioning](https://docs.unstructured.io/open-source/core-functionality/partitioning), [PyMuPDF licensing](https://pymupdf.io/).

OCR MUST be a bounded fallback, not a silent second parser. The primary reader must first return a reason such as `NO_TEXT_LAYER` or `TABLE_CONFIDENCE_BELOW_THRESHOLD`; policy must permit OCR; page/byte/time/cost ceilings must remain; OCR-derived facts remain `OCR_UNCERTAIN` until deterministic checks or review promote them.

## 7. Multi-document reconciliation and provenance

### 7.1 Required lineage

Every atomic fact needs enough lineage to reproduce the observation:

- tenant and source snapshot identity;
- backend (`LOCAL` or `GOOGLE`);
- file/document/spreadsheet stable ID;
- Drive version/revision metadata or local content digest;
- sheet ID/name and A1 range/cell;
- Docs tab ID and structural index path;
- PDF page, bounding box, table/row/column;
- DOCX part/table/row/column;
- CSV encoding, line/row/column;
- extractor name/version/config digest and capture timestamp.

The audit store SHOULD persist locators, digests, typed facts and bounded sanitized evidence, not duplicate raw documents. Raw source access remains governed by the source system and job policy.

W3C PROV provides a general Entity/Activity/Agent model and can be an export format later; OpenLineage is primarily job/dataset oriented and too coarse for cell-level business facts. A compact internal domain model is the MVP choice. Sources: [W3C PROV-DM](https://www.w3.org/TR/prov-dm/), [OpenLineage object model](https://openlineage.io/docs/next/spec/object-model/).

### 7.2 Conflict and duplicate policy

Facts share a semantic key only when tenant, canonical client, canonical SKU/article, metric, period, dimensions, unit and currency agree. Equal typed values with distinct provenance are duplicates and MAY be coalesced while retaining every lineage reference. Unequal values form a `ConflictSet`.

No “latest wins”, “Google wins”, “spreadsheet wins”, average, sum or model choice may occur implicitly. Any automatic resolution must name a versioned rule, for example:

- exact duplicate coalescing;
- designated-authoritative-source by metric and period;
- superseded revision elimination within one stable source;
- additive partitions only when a partition key proves non-overlap.

Unresolved conflicts block affected authoritative calculations or produce an explicitly `PARTIAL` result. They are never converted to missing or zero.

## 8. Model role and data controls

### 8.1 OpenAI/Codex

OpenAI file-input documentation states that spreadsheet augmentation parses up to the first 1,000 rows per sheet for model input and advises computational tools for joins/aggregation. This is incompatible with treating full-file model ingestion as an exact fact pipeline. Source: [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs).

Structured Outputs improves syntactic conformance but does not make a model an analytical authority. Source: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

OpenAI data controls distinguish API abuse-monitoring retention, endpoint storage, Zero Data Retention eligibility, and Files lifecycle; `/v1/files` persists until deleted and is not the recommended Gate 6 transport. Source: [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data).

At the cut-off OpenAI announced GPT-5.6 on 2026-07-09 with published Luna/Terra/Sol pricing. Model names and prices are volatile and MUST live in the Gate 5 model registry/budget policy, not in calculation manifests. Source: [GPT-5.6 announcement](https://openai.com/index/gpt-5-6/).

### 8.2 Gemini specialist

Gemini structured output supports a JSON Schema subset and explicitly requires application semantic validation. Long-context documentation warns that multi-needle retrieval is harder and longer contexts increase latency. The Gemini Files API retains uploaded files for up to 48 hours, so Gate 6 SHOULD avoid it for private business documents. Sources: [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), [long context](https://ai.google.dev/gemini-api/docs/long-context), [Files API](https://ai.google.dev/gemini-api/docs/files).

At the cut-off Gemini 3.6 Flash was listed with a 2026-07-21 lifecycle entry and paid-tier pricing was published separately. These are routing facts, not reasons to upload whole documents. Sources: [Gemini deprecations/lifecycle](https://ai.google.dev/gemini-api/docs/deprecations), [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

Gemini API terms distinguish unpaid and paid service data use; ZDR and Search grounding have separate conditions. Private Nobus analytics MUST use only an explicitly approved paid/enterprise route, `store=false`/ZDR where eligible, no Search grounding, and no Files API unless a later policy explicitly permits it. Sources: [Gemini API terms](https://ai.google.dev/gemini-api/terms), [Gemini ZDR](https://ai.google.dev/gemini-api/docs/zdr).

### 8.3 Approved model payload

A model MAY receive:

- the exact question and governed metric names;
- source metadata and bounded candidate headers;
- typed normalized facts with evidence IDs;
- minimal redacted excerpts needed for a semantic ambiguity;
- conflict/limitation summaries and calculation outputs;
- closed response schema and non-authority instructions.

It MUST NOT receive:

- an unbounded or whole private document by default;
- credentials, source URLs carrying tokens, tenant-foreign metadata, hidden rows outside the plan, or raw audit logs;
- executable formulas, user-provided SQL, or source instructions as trusted system directions;
- authority to change a fact, resolve a conflict, perform a calculation, expand scope, or execute an effect.

## 9. Ready frameworks, MCP, and paid Document AI

### 9.1 MCP and agent frameworks

Google announced a Drive MCP developer preview in the 2026 release notes. It is a transport/discovery option, not a typed analytical engine. Drive MCP file eligibility is subject to Workspace access controls including ACL, IRM, DLP, Context-Aware Access and CSE restrictions. Sources: [Drive release notes](https://developers.google.com/workspace/drive/release-notes), [Drive MCP file eligibility](https://developers.google.com/workspace/drive/api/guides/drive-mcp-server-file-eligibility).

The MCP security guide documents prompt injection, confused deputy, token passthrough and SSRF risks. An MCP server MUST remain behind the same tenant, scope, request, revision and budget controls as any REST adapter. Source: [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices).

An older community Google Drive MCP implementation had archived-project and Windows/credential concerns recorded in its issue tracker, reinforcing that community transport should not become analytics authority. Source: [modelcontextprotocol/servers issue 1256](https://github.com/modelcontextprotocol/servers/issues/1256).

LangChain, LlamaIndex, Google ADK and similar frameworks can reduce prototype wiring, but none replaces Nobus contracts, revision binding, cell lineage, exact reconciliation or calculation manifests. Adding one would create a second orchestration lifecycle and larger prompt/tool surface without demonstrated code reduction. **Reject for MVP.**

### 9.2 Paid document AI comparison

| Service | Capability and Russian support | Indicative published cost at cut-off | Privacy/retention/lock-in | Verdict |
|---|---|---|---|---|
| Google Document AI | OCR supports 200+ languages including Russian; Layout/Form/Custom processors | OCR `$1.50/1,000 pages`, Layout `$10/1,000`, Form/Custom `$30/1,000` | Google Cloud processor boundary; batch failsafe output TTL; no customer-data training claim; generative custom extractor primarily English | Preferred cloud OCR fallback after explicit approval |
| Azure AI Document Intelligence | Russian OCR/layout support; v4 GA docs | Tier/region dependent | Service stores analysis data temporarily; container option is resource-heavy (about 8 CPU/24 GB guidance) | Secondary comparison/fallback for procurement or benchmark win |
| AWS Textract | Forms/tables/queries | Published per-page pricing | Managed-service lock-in; official best-practice language list does not include Russian | Reject for Russian-first Gate 6 |

Sources: [Google Document AI processor list](https://docs.cloud.google.com/document-ai/docs/processors-list), [Google Document AI pricing](https://cloud.google.com/document-ai/pricing), [Google Document AI security](https://docs.cloud.google.com/document-ai/docs/security), [Azure OCR language support](https://learn.microsoft.com/ru-ru/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0), [Azure service limits](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0), [Azure containers](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/containers/install-run?view=doc-intel-3.0.0), [AWS Textract best practices](https://docs.aws.amazon.com/textract/latest/dg/textract-best-practices.html), [AWS tables](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html), [AWS Textract pricing](https://aws.amazon.com/textract/pricing/).

Paid OCR is not a reconciliation or calculation service. Its output remains an uncertain source observation with provider/model/version and page/bounding-box lineage.

## 10. End-to-end variants

Scores: 1 = poor, 5 = strong. “Exactness” includes typed values, revision binding and deterministic formulas, not OCR recognition alone.

| Variant | Exactness | Provenance | Privacy | Ops | Cost | Windows/VPS | Code reduction | Fallback | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| A. Native readers + Pydantic + SQLite + pure `Decimal` | 4 | 5 | 5 | 4 | 5 | 5 | 3 | Manual/paid OCR | Strong minimal fallback |
| B. Native readers + Pydantic + SQLite + DuckDB + selective Docling | 5 | 5 | 5 | 3 | 4 | 4 | 4 | Pure `Decimal`, paid OCR | **Recommended** |
| C. Google-native APIs + Document AI + Gemini specialist | 4 | 4 | 3 | 3 | 3 | 5 | 4 | Local readers | Approved cloud-heavy profile only |
| D. Unstructured/LangChain + RAG/vector DB + model calculations | 2 | 2 | 3 | 2 | 2 | 3 | 2 after governance code | Native readers | Reject |

Variant B wins because it adds one analytical engine where it materially reduces join/window/grouping code, while retaining a stdlib reference and bounded format-specific readers. Variant A remains the degraded/local fallback. Variant C is an adapter profile for difficult OCR or Google-only deployments, not the governing architecture. Variant D optimizes document chat rather than exact business analytics.

## 11. Recommended stack and explicit rejects

### 11.1 Adopt

- existing Pydantic and canonical JSON/digest conventions;
- stdlib `Decimal`, `datetime`, `zoneinfo`, `csv`, hashing and SQLite;
- DuckDB `1.5.5` as a proposed implementation pin subject to Gate 8 review;
- `openpyxl 3.1.3`, `python-docx 1.2.0`, `pdfplumber 0.11.9`;
- Hypothesis test-only;
- official Google Drive/Sheets/Docs APIs;
- optional Docling local OCR adapter after benchmark;
- optional Google Document AI OCR after owner/policy approval;
- internal compact provenance with optional future W3C PROV export.

### 11.2 Defer until evidence

- Polars for a measured streaming/CPU bottleneck;
- Pandera after a dataframe baseline exists;
- pandas for an interoperability feature not covered by current readers/engine;
- Ibis after a real second analytical backend;
- vector retrieval after the six-part benchmark threshold in section 4.3;
- OpenLineage after job/dataset observability needs exceed existing telemetry;
- full W3C PROV serialization after an external interoperability consumer exists.

### 11.3 Reject for MVP

- whole-document or whole-workbook upload to a large model;
- model-generated or user-provided executable SQL;
- model calculations or silent model conflict resolution;
- LangChain/LlamaIndex/ADK as a second orchestrator;
- generic Tika/Unstructured as the primary structured reader;
- PyMuPDF under the current license posture;
- AWS Textract for Russian-first OCR;
- vector DB and RAG-first retrieval;
- renderers that independently recompute metrics;
- caches without tenant and source-revision keys.

## 12. Calculation and provenance model options

| Option | Description | Benefit | Risk | Decision |
|---|---|---|---|---|
| Compact Nobus fact + manifest | Atomic facts, source locators, rule/engine/input/output digests | Exact fit, small code, easy Gate 7 handoff | Own schema governance | **Adopt** |
| W3C PROV-native store | Entity/Activity/Agent graph as primary model | Standards interoperability | Verbose and indirect for cells/calculations | Optional export later |
| OpenLineage-native store | Jobs/runs/datasets | Existing observability ecosystem | Too coarse for cells and semantic conflicts | Optional job-level emission later |
| Event-sourced raw extraction | Persist every raw slice/event | Full replay | Privacy/storage/retention burden | Reject by default |

The adopted model stores enough evidence to re-read the governed source revision. It does not duplicate source contents merely to make audit convenient.

## 13. Accuracy, cost, latency and operational risks

| Risk | Failure mode | Required control | Release evidence |
|---|---|---|---|
| Identifier ambiguity | Wrong client/SKU join | Canonical IDs, alias registry, fail-closed ambiguity | Golden alias/collision tests |
| Missing-to-zero | Inflated/deflated funnel metrics | Disjoint fact-state enum; rule-specific missing policy | Property and adversarial tests |
| Revision race | Mixed versions in one result | Pre/post version bracket and immutable snapshot digest | Mutation-during-read fault test |
| Locale/currency | `1,234` or RUB/USD misparse | Source locale, ISO currency, explicit FX reference | Locale matrix |
| Formula cache | Stale spreadsheet result | Preserve formula/effective/display distinction; do not recalc arbitrary workbook formulas | Formula/cached-value fixtures |
| OCR | Plausible wrong digit or column | `OCR_UNCERTAIN`, confidence/review gate, deterministic cross-check | Russian scan corpus |
| Model injection | Source text changes plan or leaks data | Treat source as data, closed DTO, no tools/effects, minimal excerpts | Injection corpus |
| Engine drift | Upgrade changes rounding/typing | Rule and engine version in manifest; reference reproduction | Cross-engine golden regression |
| Cost explosion | Oversized corpus/OCR/model context | Monotonic budgets and early stop | Per-profile cost ceiling tests |
| Lock-in/outage | Provider unavailable | Local readers and deterministic engine remain authoritative | Model/cloud-offline test |

Latency and cost criteria MUST be empirical. Gate 8 should publish p50/p95 by corpus profile, separate read/normalize/calculate/model/OCR time and provider charges, and enforce configured ceilings. No universal millisecond or ruble target is invented before representative synthetic workloads and target hardware are measured.

## 14. Evaluation corpus and benchmark design

Only synthetic or approved anonymized fixtures are allowed.

### 14.1 Golden business corpus

- CSV/TSV in UTF-8 and CP1251 with comma/semicolon/tab delimiters;
- XLSX with formulas and cached values, merged and hidden cells, 1900/1904 date systems, locale-like numeric strings, duplicated exports and conflicting totals;
- Google Sheets with multiple tabs, named/unnamed ranges, changing Drive versions and narrow field masks;
- Google Docs with tabs, paragraphs and tables;
- machine-generated PDFs and Russian scans at 150/300 DPI, rotated pages, split tables and multi-column text;
- DOCX tables, repeated headers, nested structures and unsupported floating content;
- exact zero, blank, null, absent column, invalid text and not-applicable states;
- RUB/USD and explicit FX-date examples; Moscow and UTC boundary periods;
- malformed/encrypted/oversized archives, decompression bombs and unsupported formats;
- prompt injection, CSV/formula injection and misleading footnotes;
- duplicate, additive partition, contradiction and source-authority scenarios;
- cancellation, model outage, OCR outage and revision race.

Public table-layout datasets such as PubTables-1M may inform structural stress cases, but they do not replace Nobus golden business calculations. Source: [PubTables-1M paper](https://arxiv.org/abs/2110.00061).

### 14.2 Expected calculations

Every case must publish:

- exact normalized input facts and states;
- canonical semantic keys;
- expected conflicts and duplicate groups;
- approved rule version, rounding and missing policy;
- exact `Decimal` outputs;
- expected lineage coordinates;
- result and manifest digest fixtures;
- an independently authored reference calculation.

## 15. Acceptance matrix

| Dimension | Required Gate 6 result |
|---|---|
| Source modes | Same contracts and normalized-fact semantics for local-only, Google-only and mixed |
| Entity/period precision | Exact canonical client, SKU/article and half-open period; ambiguity fails closed |
| Bounded extraction | Every slice has byte/row/cell/page/character/time ceilings |
| Numeric accuracy | 100% exact agreement on critical golden numeric results |
| Independent reproduction | 100% of golden calculations reproduced by separately authored `Decimal` method |
| Provenance | 100% of authoritative facts and derived outputs trace to source snapshot and locator |
| Missing semantics | Zero missing/null/blank/conflict-to-zero conversions |
| Conflicts | 100% expected conflict detection; no silent winner |
| Revisions | Zero silent mixed-revision results |
| Tenant isolation | Zero cross-tenant source, join, cache or model-context leakage |
| Formula safety | Zero execution of source formulas, CSV formulas or user SQL |
| OCR | Uncertain output may fail/partial; never becomes silently authoritative |
| Model outage | Facts/calculations remain reproducible; narrative degrades explicitly |
| Gate 7 consistency | Every format cites the same `AnalysisResult.result_digest` |
| Cost/latency | Configured profile ceiling enforced; p50/p95 and component costs reported |

## 16. Dependencies on other Gates

- **Gate 2:** canonical contract registry, owner/tenant/project scope, entity aliases, error envelope, idempotency.
- **Gate 3:** Google OAuth/scopes, native Drive/Sheets/Docs adapters, quotas, source version metadata, Gemini routing and data policy.
- **Gate 5:** unified document/source gateway, local Bridge containment, parser sandbox and source-snapshot reads.
- **Gate 7:** Telegram/JPEG/HTML/XLSX renderers consume the one result contract and never calculate.
- **Gate 8:** dependency/security pinning, golden regression, observability, cost/latency SLOs and release evidence.

## 17. Verification record

### L1 — completeness and source traceability

PASS criteria for this dossier:

- every required research family is covered;
- time-sensitive claims carry a cut-off and direct primary links;
- CURRENT and TARGET are explicitly separated;
- no secret, credential, client identifier, real document content or unverifiable business value is present;
- local/Google/mixed, missing/zero, conflicts, revisions, formula safety and model boundaries are explicit.

### L2 — independent calculation and repository reconciliation

The architecture requires every calculation to be reproduced by a separately authored pure-`Decimal` method that does not call the production SQL. The documentation verification uses a synthetic funnel example and compares exact rational/decimal results. The code impact map is reconciled against the canonical owner-file, Google Drive, workspace/artifact and test boundaries; it does not claim non-existent analytical functionality as CURRENT.

### L3 — adversarial review

Release must exercise at least:

- hallucinated values;
- missing-to-zero conversion;
- silent source conflict resolution;
- revision change during read;
- cross-tenant join/cache reuse;
- source and CSV/formula injection;
- prompt injection in cells, footnotes and metadata;
- OCR digit/column errors;
- oversized or malformed corpus;
- model/OCR/cloud outage;
- format drift and formula-cache drift.

Any authoritative result produced after one of these failures without an explicit status, limitation and evidence trail is a Gate failure.

## 18. Research decision

`RESEARCH READY`

The evidence supports Variant B: native structured readers, typed fact/provenance contracts, SQLite durable state, DuckDB bounded calculations, a pure-Decimal reference, selective OCR, and tightly subordinate models. No evidence supports RAG-first retrieval, whole-document model upload, generic agent frameworks, or model-owned calculations for Gate 6.
