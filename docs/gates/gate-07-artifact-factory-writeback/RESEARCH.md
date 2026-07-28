# Gate 7 Research Dossier — Artifact Factory and Controlled Writeback

**Project:** Nobus Space
**Research cutoff:** 2026-07-28
**Canonical documentation commit inspected:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Research status:** `RESEARCH READY`

## 1. Question and constraints

Gate 7 must turn one immutable set of normalized facts into useful Telegram
text, JPEG, self-contained HTML, PDF, XLSX and DOCX outputs without allowing
the values to drift between formats. It must then create or update permitted
local and Google artifacts with exact destination binding, approval,
idempotency, readback, recovery and evidence.

The research compared rendering stacks, Office writers, chart engines, Google
APIs, local Windows write algorithms, MCP/connectors and paid document
platforms. Primary documentation, repositories, releases, licenses and
security notices were preferred. Nobus Memory was used only as a secondary
historical index.

Phase 1 was strictly read-only: no renderer, local write, Google/Telegram
effect, dependency installation, code change, commit, push or deployment was
performed.

## 2. Executive verdict

Adopt a small in-process Artifact Factory behind the existing Nobus
product-effect plane:

1. Gate 6 or another accepted producer emits immutable normalized facts and a
   digest. Gate 7 never recalculates business values.
2. Gate 7 compiles them once into a closed `ArtifactDocument` whose
   `ValueToken` objects carry typed raw values, display text, locale, units,
   precision and provenance.
3. Curated Jinja templates generate semantic, self-contained HTML. A pinned
   Playwright/Chromium runtime creates the stored HTML projection, JPEG card
   and PDF from the same DOM and CSS profiles.
4. Vega-Lite specifications use the same ValueTokens and render into that DOM.
5. XlsxWriter and python-docx are specialized serializers of the same
   ArtifactDocument; they do not calculate values.
6. Existing Nobus approval, effect journal, local snapshot/CAS/atomic replace
   and Google reconciliation boundaries execute the write.

Recommended disposition:

| Component | Verdict |
|---|---|
| Jinja2 + semantic HTML/CSS | **ADOPT** |
| Pinned Playwright/Chromium for HTML/JPEG/PDF | **ADOPT** |
| Vega-Lite rendered into the same DOM | **ADOPT** |
| XlsxWriter for new XLSX | **ADOPT** |
| python-docx for new DOCX | **ADOPT** |
| Existing Nobus effect vault and local workspace safety | **ADAPT** |
| Official Google APIs through Gate 3 | **ADAPT** |
| openpyxl for arbitrary workbook round-trips | **RESTRICT** |
| WeasyPrint | **PDF fallback only** |
| Typst | **Explicit PDF/UA fallback only** |
| LibreOffice headless | **Isolated QA/conversion only** |
| Gotenberg | **Hardened optional fallback only** |
| MCP/SaaS document generation | **Not a trusted critical path** |

The important blocker is not rendering. Google Docs exposes a real revision
precondition, but Google Sheets does not expose an equivalent strict
server-side CAS contract, and a suitable Drive v3 conditional overwrite
contract for binary blobs was not proven. Strict Gate 7 therefore creates a
new version/copy or fails closed for those updates; it must not simulate CAS.

## 3. Canonical and CURRENT evidence

The canonical Gate 2 contract already defines `ArtifactPlan` as a proposed
render and `DocumentWritePlan` as an exact approved create/update plan. Gate 7
must implement them rather than invent a parallel model. The canonical rules
also require:

- opaque source and destination references;
- exact tenant/project/client and output-scope binding;
- immutable artifact and plan digests;
- `collision_policy=new_version|ask`;
- snapshot for every local update;
- exact expected revision for update;
- strict CAS denial when a backend lacks the requested capability;
- exact-owner-request binding or preview confirmation;
- readback and reconciliation before any retry.

Gate 6 defines `NormalizedFact`, `AnalysisResult`, provenance and calculation
manifests. Its Gate 7 handoff is explicit: one immutable result, no
recalculation, no source re-query, no silent conflict resolution and the same
`result_digest` in every projection.

Reusable CURRENT code:

| Current path | Reusable behavior | Missing Gate 7 behavior |
|---|---|---|
| [`src/application/product_effects.py`](../../../src/application/product_effects.py) | Encrypted durable effects, stable idempotency, conflict rejection, `UNKNOWN`, recovery and receipts | Artifact manifest, render adapters, Google write reconciliation |
| [`src/application/owner_workspace.py`](../../../src/application/owner_workspace.py) | Proposal, preview, snapshot, digest CAS, same-directory replace, readback, journal and restore | Production renderers, opaque output-scope binding |
| [`src/integrations/google_drive.py`](../../../src/integrations/google_drive.py) | Bounded read/search/download/export, no hidden retries | Create/upload markers, Docs/Sheets write adapters |
| [`tests/test_product_effects.py`](../../../tests/test_product_effects.py) | Durable idempotency and recovery coverage | Artifact-specific states and receipts |
| [`tests/test_owner_workspace.py`](../../../tests/test_owner_workspace.py) | Local races, CAS, snapshot, restore and journal | Artifact manifest and output registry binding |
| [`tests/test_google_drive_adversarial.py`](../../../tests/test_google_drive_adversarial.py) | Ambiguity, scope and bounded-read failures | Lost-response create/update reconciliation |

The current built-in HTML/DOCX/XLSX/PDF writers are prototypes, not a reusable
format system: HTML has little semantic/responsive styling; DOCX flattens
structure; XLSX lacks normal workbook semantics and accessibility; the direct
PDF path rejects non-Latin-1 text; Edge is used only for PDF. Replacing those
writers behind the current application boundary is smaller and safer than
building a second bot or report framework.

## 4. One rendering model

The single source of truth is an `ArtifactDocument`, not a particular file
format. It contains ordered semantic blocks and a registry of immutable
ValueTokens.

Each ValueToken carries:

- stable `value_id`;
- typed raw value and explicit missing/conflict state;
- unit, currency and timezone;
- rounding/precision and locale;
- final `display_text`;
- fact and provenance digests.

Formatting decisions happen once during compilation. Renderers may escape,
lay out or style a token, but may not re-round, convert units, infer missing
values or run business formulas.

Two digest classes are needed:

- semantic digests bind normalized facts, the compiled document and the
  `value_id -> display_text` projection;
- byte digests bind each produced file.

Byte equality is not a portable semantic requirement for ZIP-based Office
files or browser PDFs because metadata and runtime details can vary. Semantic
equality is mandatory.

## 5. HTML, JPEG and PDF landscape

### 5.1 Recommended: Jinja2 + Playwright

Jinja2 `3.1.6` was released on 2025-03-05 under BSD-3-Clause. Gate 7 should use
curated templates, `StrictUndefined`, contextual autoescape and no
model-supplied template source. [Jinja2 releases](https://pypi.org/project/Jinja2/)

Playwright Python `1.61.0` was released on 2026-06-29 under Apache-2.0 and pins
a corresponding browser build. It supports page/element JPEG screenshots and
Chromium PDF generation from the same DOM. PDF options include tagged output
and an outline, although neither proves PDF/UA conformance.
[Playwright Python releases](https://github.com/microsoft/playwright-python/releases),
[screenshots](https://playwright.dev/python/docs/screenshots),
[page PDF](https://playwright.dev/python/docs/api/class-page#page-pdf)

One self-contained HTML document should expose three CSS profiles:

- `screen` for the stored HTML;
- `card` for Telegram JPEG;
- `print` for PDF.

The runtime must deny external network/file fetches, wait for fonts and charts,
disable animations and pin browser, OS, fonts, viewport, locale, timezone,
clock and randomness. Playwright visual baselines are environment-specific, so
goldens must be produced and compared in the same Gate 8 image.
[Playwright snapshot guidance](https://playwright.dev/docs/next/test-snapshots)

### 5.2 WeasyPrint

WeasyPrint `69.0`, released 2026-06-02 under BSD-3-Clause, is strong for paged
CSS, font subsetting and PDF/A/UA profiles. It remains a fallback because
JPEG would use another engine and Windows library installation is materially
heavier. Its documentation warns that untrusted HTML/CSS can cause file or
network disclosure, excessive CPU/memory use and long render times. Release
69.0 also contains the CVE-2026-49452 security update.
[WeasyPrint releases](https://github.com/Kozea/WeasyPrint/releases),
[security considerations](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html),
[API and versioning](https://doc.courtbouillon.org/weasyprint/stable/api_reference.html)

### 5.3 Typst, ReportLab and Paged.js

Typst `0.15.0`, released 2026-06-15 under Apache-2.0, has strong tagged
PDF/PDF-A/PDF-UA capabilities, but its HTML output remains explicitly
experimental and incomplete. It is valuable only for an explicit
high-compliance PDF profile, not as the primary factory.
[Typst changelog](https://typst.app/docs/changelog/0.15.0/),
[HTML](https://typst.app/docs/reference/html/),
[PDF](https://typst.app/docs/reference/pdf/)

ReportLab `5.0.0`, released 2026-06-18 under BSD, supports embedded TrueType
fonts and Unicode but creates an independent imperative layout system. That is
exactly the drift Gate 7 must avoid.
[ReportLab package](https://pypi.org/project/reportlab/),
[font documentation](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/)

Paged.js is MIT-licensed and useful for advanced paged-media behavior, but it
adds a JavaScript pagination layer and operational/debugging surface that the
MVP does not require. [Paged.js repository](https://github.com/pagedjs/pagedjs)

## 6. Office formats and Russian text

### XLSX

XlsxWriter `3.2.9`, released 2025-09-16 under BSD-2-Clause, is the preferred
new-workbook writer. It supports tables, formats, freeze panes, charts and
image descriptions, but intentionally cannot read or modify an existing
workbook. Formula cached results must be treated carefully because non-Excel
viewers can initially see the stored placeholder value.
[XlsxWriter changes](https://xlsxwriter.readthedocs.io/changes.html),
[FAQ](https://xlsxwriter.readthedocs.io/faq.html),
[license](https://xlsxwriter.readthedocs.io/license.html)

openpyxl `3.1.5`, released 2024-06-28 under MIT, may update a restricted,
feature-inventoried workbook. Its documentation warns that shapes can be lost
when an existing file is opened and saved. Arbitrary workbook round-trip is
therefore fail-closed; macros, shapes, external links and unknown OOXML
relationships require a new version or refusal.
[openpyxl package](https://pypi.org/project/openpyxl/),
[tutorial warning](https://openpyxl.readthedocs.io/en/3.1/tutorial.html)

### DOCX

python-docx `1.2.0`, released 2025-06-16 under MIT, is sufficient for new
documents based on curated Word templates with known styles, headings,
tables, headers and footers. [python-docx package](https://pypi.org/project/python-docx/),
[document/template behavior](https://python-docx.readthedocs.io/en/latest/user/documents.html)

docxtpl `0.20.2`, released 2025-11-13 under LGPL-2.1-only, may be evaluated for
trusted internal templates, but not for arbitrary uploaded templates and not
on the critical path. [docxtpl package](https://pypi.org/project/docxtpl/)

Existing DOCX updates are allowed only through a known template revision and
stable anchors/content controls. Otherwise Gate 7 creates a new version.

### Fonts and QA

Digest-pinned Noto Sans/Serif/Mono Cyrillic fonts under OFL-1.1 remove the
Windows/VPS font dependency and permit consistent Russian rendering.
[Noto Latin, Greek and Cyrillic](https://github.com/notofonts/latin-greek-cyrillic)

LibreOffice `26.2.5`, released 2026-07-24, is suitable only for isolated
headless conversion/visual QA with macros disabled, a unique profile, blocked
network and resource limits. Version 26.2.4 fixed multiple security issues, so
older builds are unsuitable. [LibreOffice release notes](https://www.libreoffice.org/release-notes/),
[security advisories](https://www.libreoffice.org/security/)

## 7. Charts and cards

Vega-Lite `6.4.3`, released 2026-04-24 under BSD-3-Clause, is the preferred
chart grammar. Specs use inline data assembled from ValueTokens; the pinned
runtime is vendored locally and emits SVG into the canonical HTML DOM.
[Vega-Lite repository](https://github.com/vega/vega-lite),
[specification](https://vega.github.io/vega-lite/docs/spec.html)

Every chart also has a text summary and an accessible data table. Plotly/Kaleido
is more operationally expensive and brings another Chrome-dependent export
path. Matplotlib is a reliable emergency static fallback, but not a second
normal renderer. [Plotly static export](https://plotly.com/python/static-image-export/)

## 8. Google write contracts

### 8.1 Identity and owner-only destination

Gate 7 consumes Gate 3 OAuth and provider capabilities. Prefer per-file
`drive.file` authority over full Drive authority. Full `drive` is a restricted
scope and is not justified by artifact creation.
[Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

Creation must target a verified private owner folder. Drive permissions inherit
from the parent, so an owner-created file inside a shared folder is not
owner-only. Normal Gate 7 effects never call `permissions.create`.
[Drive sharing](https://developers.google.com/workspace/drive/api/guides/manage-sharing)

### 8.2 Binary create/upload

For binary files, `files.generateIds` provides the file ID before upload.
Creating with the same ID prevents an accidental second file after a lost
response. Resumable upload sessions must be persisted and probed: `200/201`
means complete, `308` supplies the next range, and `404` means the session
expired.
[Create files](https://developers.google.com/workspace/drive/api/guides/create-file),
[resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads)

### 8.3 Native Docs/Sheets create

Pre-generated IDs do not support Google Workspace files. Create a native MIME
file through Drive with a unique private `appProperties` effect marker. If the
response is lost, reconcile by exact marker, parent, MIME and `trashed=false`:

- one matching resource: read back and complete;
- multiple matches: conflict;
- no authoritative match: remain `UNKNOWN`.

[Custom properties](https://developers.google.com/workspace/drive/api/guides/properties),
[search files](https://developers.google.com/workspace/drive/api/guides/search-files)

### 8.4 Docs update

`documents.batchUpdate` accepts `requiredRevisionId`. A stale required revision
causes the write to be rejected rather than rebased. The response supplies the
post-write control and a subsequent `documents.get` provides semantic
readback. Revision IDs are opaque and time-limited; they are not durable
business identifiers.
[Docs batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate),
[Document resource](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents)

### 8.5 Sheets and Drive blob updates

Sheets `batchUpdate` validates and applies one batch atomically, but its
request has no Docs-like write-control field. Collaboration can alter the
spreadsheet after the batch; returned values and `batchGet` are readback, not
CAS. Strict existing-Sheet updates therefore default to a new version/copy or
fail closed.
[Sheets batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate),
[values batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate)

Drive `version`, `headRevisionId` and checksums help readback and
reconciliation, but the inspected Drive v3 contract did not prove a strict
conditional binary overwrite equivalent to Docs `requiredRevisionId`.
Existing blob updates use new-version semantics until such a contract is
officially documented and integration-tested.
[Drive File resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)

## 9. Local controlled writeback

The current Nobus local algorithm is the correct basis:

1. resolve an opaque output reference inside an allowlisted scope;
2. bind the current handle identity and digest;
3. create a pre-write snapshot for update;
4. show payload/destination preview when they were formed after analysis;
5. revalidate approval, destination, artifact digest and CAS;
6. write a temporary file in the destination directory, flush and fsync;
7. replace through the handle-bound Windows algorithm;
8. read back identity and digest;
9. record a receipt;
10. restore only when the current digest still equals the failed write digest.

An open Word/Excel handle can deny delete sharing and make replacement fail.
Gate 7 must return a sharing-violation reason and ask the owner to close the
file. It must not fall back to delete-and-rewrite.
[CreateFile sharing](https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilea),
[ReplaceFile](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-replacefilea),
[moving and replacing files](https://learn.microsoft.com/windows/win32/fileio/moving-and-replacing-files)

## 10. MCP, self-hosted and paid landscape

The community [Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp)
is MIT-licensed and broad, with useful OAuth/scope examples. Repository
inspection did not establish Nobus-grade revision CAS, durable idempotency,
unknown-outcome reconciliation or approval binding. It is a reference, not
the write authority.

Gotenberg `8.32.0`, released 2026-04-30 under MIT, offers Chromium and
LibreOffice conversion in Docker. Recent releases strengthened file URL and
DNS-rebinding protections, but permissive outbound/private-network defaults
remain unacceptable for Nobus. It is an optional authenticated, isolated,
network-denied fallback only.
[Gotenberg 8.32.0](https://github.com/gotenberg/gotenberg/releases/tag/v8.32.0)

Paid candidates:

| Platform | Strength | Gate 7 limitation |
|---|---|---|
| [Carbone](https://carbone.io/) | Editable Office templates, cloud/self-host, MCP | Cost/template lock-in; no Nobus effect guarantees |
| [Docmosis](https://www.docmosis.com/pricing/) | Mature self-hosted templating; pricing updated 2026-06-01 | Java/service burden; one-time tiers start around USD 3,795 |
| [Plumsail Documents](https://plumsail.com/docs/documents/v1.x/general/security-policy.html) | Low-code Office generation | External data boundary and retention |
| [DocRaptor](https://docraptor.com/security-and-privacy) | Strong Prince HTML-to-PDF | External boundary; no Office/writeback plane |

These may reduce complex template work, but none replaces tenant-bound policy,
approval, idempotency, reconciliation and readback. They are not critical-path
dependencies.

## 11. Complete option comparison

| Option | Maturity | Windows/VPS | Privacy/security | Code reduction | Ops | Lock-in | Verdict |
|---|---|---|---|---|---|---|---|
| Jinja + Playwright + Vega + XlsxWriter + python-docx + official APIs | High | Good with pins | Local, controllable | High | Medium | Low | **Recommended** |
| Jinja + WeasyPrint + Playwright + Office writers | High | Native Windows friction | Two render surfaces | Medium | Medium/high | Low | PDF fallback |
| Gotenberg + LibreOffice + template platform | High components | Docker-oriented | Requires hard isolation | High | High | Medium | Later adaptation |
| Typst-first + separate HTML/Office | High PDF, experimental HTML | Good | Local | Medium | Medium | Medium | Reject primary |
| SaaS generation + Google connectors | High vendor maturity | OS-neutral | External data boundary | Highest | Low local | High | Reject default |

## 12. Provenance and verification

Every artifact manifest must bind:

- tenant/project/client and owner subject;
- source/result/plan/template/profile digests;
- ValueToken semantic digest;
- font/browser/library versions and asset digests;
- per-output byte and semantic digests;
- exact opaque destination and expected revision;
- preview/confirmation/action digest;
- snapshot, provider marker/session/file ID;
- readback and reconciliation evidence;
- final receipt.

Minimum test families:

- semantic extraction from HTML, PDF, XLSX, DOCX and Google readback;
- exact chart-data-to-token equality;
- mobile widths 320/360/390 CSS px and 200% zoom;
- Cyrillic, long text, missing/conflicting values and large tables;
- pinned screenshot regression and ARIA snapshots;
- tagged PDF text extraction and veraPDF validation;
- local collision, path/reparse, open-file, CAS, crash and rollback tests;
- Google lost-response, marker 0/1/2, stale Docs revision, Sheets fail-closed,
  resumable `308/404` and private-parent tests;
- cross-tenant, cross-project, payload/destination drift and expired approval;
- external URL, SSRF, oversized CSS/data, malicious OOXML/XML and macro tests.

[WCAG 2.2](https://www.w3.org/TR/WCAG22/),
[veraPDF validation](https://docs.verapdf.org/validation/)

## 13. Threat and failure summary

| Failure | Required response |
|---|---|
| Cross-format value drift | Fail semantic verification; no delivery |
| Template/external fetch injection | Curated templates and network deny |
| Font/runtime drift | Pinned digests; Gate 8 readiness failure |
| Local collision | New version or owner clarification |
| Local concurrent edit | CAS conflict |
| Windows sharing violation | No replace; ask owner to close file |
| Docs collaborator update | `requiredRevisionId` conflict |
| Sheets/blob strict CAS unavailable | New version/copy or fail closed |
| Lost create/upload response | Read-only reconciliation; no blind retry |
| Multiple marker matches | Conflict/manual review |
| Inherited Google sharing | Deny owner-only delivery |
| Rollback could overwrite later edit | Rollback CAS denies restore |
| MCP/SaaS requests broad authority | Deny; official adapter remains authority |
| Telegram acknowledgement lost | Durable `UNKNOWN`; acknowledge residual at-least-once window |

## 14. Gate dependencies

- **Gate 2:** closed `ArtifactPlan`, `DocumentWritePlan`, output registry,
  opaque refs and approval binding.
- **Gate 3:** OAuth subject/scopes, Google transports, provider capability,
  Docs/Sheets/Drive adapters and reconciliation.
- **Gate 4:** normative durable effect state machine, leases, receipts,
  reconciliation workers and owner status semantics.
- **Gate 5:** document gateway, opaque ref store, Windows handle containment
  and Bridge jobs.
- **Gate 6:** immutable `AnalysisResult`, normalized facts, provenance,
  conflicts, limitations and result digest.
- **Gate 8:** dependency/license/vulnerability pins, browser/fonts/runtime
  packaging, resource limits, pilot smoke and recovery evidence.

## 15. L1/L2/L3 research verification

### L1 — deterministic completeness: PASS

The pinned canon, relevant code and tests, versions, dates, licenses, required
formats, local/Google write cases and prohibited actions were checked. No
secret or credential was read or recorded. No write/runtime action occurred.

### L2 — primary-source reconciliation: PASS

Critical API and renderer claims were reconciled against official
documentation, primary repositories/releases and security notices. The
recommended architecture remains compatible with the Gate 2/3/4/5/6/8
contracts.

### L3 — adversarial review: PASS

The review found the Sheets and Drive blob CAS gaps, native Google ID
limitation, inherited sharing, Windows sharing violation, openpyxl feature
loss, renderer SSRF/resource risks, LibreOffice macro/CVE risk and
browser/font nondeterminism. Each now has an explicit fail-closed rule or
isolated fallback.

Implementation and live-provider L1/L2/L3 remain future work. Human approval
is required before any real external write.

## 16. Research conclusion

`RESEARCH READY`.

The implementation should add one compilation/rendering layer and backend
adapters to the existing Nobus contracts and durable effect plane. It must not
add a second bot, a generic plugin framework, a second calculation model or a
parallel write queue. Strict update is allowed only where the backend proves
the required precondition; otherwise Gate 7 creates a new version or fails
closed.
