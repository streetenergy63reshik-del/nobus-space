# Gate 2 — Scope Registry and Unified Document Contracts

**Document:** verified research dossier
**Status:** TARGET research baseline
**Canonical repository commit:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Evidence cutoff:** 2026-07-28
**Implementation status:** not implemented

## 1. Executive conclusion

Gate 2 must **ADAPT the existing Nobus boundary**, not introduce a general
filesystem sandbox, a model-facing Google toolset, or an external policy
platform.

The minimum strict stack is:

1. Pydantic v2 wire models with `strict=True`, `extra="forbid"`,
   `frozen=True`, closed enums and explicit discriminated unions.
2. The seven contracts required by
   [`docs/12-Эталон-MVP-1-и-дорожная-карта.md`](../../12-Эталон-MVP-1-и-дорожная-карта.md):
   `IntentEnvelope`, `DocumentRef`, `DocumentQuery`, `DocumentReadPlan`,
   `AnalysisRequest`, `ArtifactPlan`, and `DocumentWritePlan`.
3. Three application-owned canonical JSON registries: `source`, `output`, and
   `deny`. Their active revisions are schema-validated, digest-bound,
   signature-verified, anti-rollback protected, and activated atomically.
4. A small deny-overrides application policy with exact
   `tenant_id/project_ref/client_ref` equality. OPA, Cedar, and Casbin are not
   part of MVP-1.
5. A local adapter implemented only through identity/handle-based Windows
   APIs, and a Google adapter whose OAuth authority and backend locators remain
   server-side.
6. A document pipeline of metadata-first discovery, exact selection, bounded
   extraction, local DLP, and a tool-less model.
7. The current Nobus secret scanner as a mandatory runtime gate. Gitleaks is an
   optional local stdin reinforcement. Presidio is deferred until a PII policy
   exists. TruffleHog and YARA are not in the critical path.

The normative design is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 2. Research scope and method

The research compared:

- the canonical product roadmap, contract specification, memory policy,
  external-write policy, status and issue handoffs;
- ADR 0010, 0012, 0014, and 0017;
- current contract, policy, owner-file, owner-workspace and Google Drive code
  and their adversarial tests;
- official upstream documentation, primary repositories, releases, security
  advisories, and pricing pages;
- application policy, OPA, Cedar, Casbin, and signed capability patterns;
- Windows path, reparse, alternate-stream, handle identity and race controls;
- local secret/PII scanning and generic MCP authority models.

Nobus Memory was not used as an authority. Owner documents, VPN data, arbitrary
`Системные`, and secret stores were not read.

## 3. Canonical evidence

Primary repository sources:

- [`docs/02-Глоссарий.md`](../../02-Глоссарий.md)
- [`docs/05-Спецификации-контрактов.md`](../../05-Спецификации-контрактов.md)
- [`docs/07-Правила-внешней-записи.md`](../../07-Правила-внешней-записи.md)
- [`docs/10-Политика-памяти.md`](../../10-Политика-памяти.md)
- [`docs/12-Эталон-MVP-1-и-дорожная-карта.md`](../../12-Эталон-MVP-1-и-дорожная-карта.md)
- [`ADR 0010`](../../adr/0010-owner-library-read-scope.md)
- [`ADR 0012`](../../adr/0012-owner-command-authority-and-calendar.md)
- [`ADR 0014`](../../adr/0014-natural-product-router-and-bounded-context.md)
- [`ADR 0017`](../../adr/0017-hybrid-natural-google-local-document-plane.md)
- [`CURRENT-STATUS.md`](../../handoffs/CURRENT-STATUS.md)
- [`MVP-1-ISSUES.md`](../../handoffs/MVP-1-ISSUES.md)

Relevant CURRENT code:

- [`src/contracts/models.py`](../../../src/contracts/models.py)
- [`src/core/policy.py`](../../../src/core/policy.py)
- [`src/application/owner_files.py`](../../../src/application/owner_files.py)
- [`src/application/owner_workspace.py`](../../../src/application/owner_workspace.py)
- [`src/integrations/google_drive.py`](../../../src/integrations/google_drive.py)
- [`tests/test_contracts.py`](../../../tests/test_contracts.py)
- [`tests/test_owner_files.py`](../../../tests/test_owner_files.py)
- [`tests/test_owner_workspace.py`](../../../tests/test_owner_workspace.py)
- [`tests/test_google_drive_adversarial.py`](../../../tests/test_google_drive_adversarial.py)

## 4. CURRENT findings

### 4.1. Contracts

CURRENT `ContractModel` already rejects unknown fields and is immutable, but it
does not apply global strict validation. Selected fields use strict primitives;
free `source` and `permissions` strings remain in `TaskContract`.

The current digest and negative-test patterns are reusable. The missing Gate 2
surface is the seven-contract document family, exact project/client binding,
schema digests, registry bindings, and closed document actions.

### 4.2. Local read

`OwnerFileService` already provides:

- metadata-first discovery and exact ambiguity handling;
- extension/format allowlists and bounded extraction;
- final-handle path verification with `GetFinalPathNameByHandleW`;
- before/after stat checks;
- current local DLP and answer exfiltration checks.

It does not yet prove production-grade containment against every ancestor
reparse type, hard-link alias, per-directory case-sensitivity, or all same-user
TOCTOU races.

### 4.3. Local write

`OwnerWorkspace` already provides:

- verified snapshots and content digests;
- destination CAS;
- a pinned directory handle on Windows;
- handle-relative atomic replacement;
- readback, journaling, crash recovery, and concurrency locking.

This is the correct implementation lineage. Gate 2/5 must remove the remaining
path-based prelude and validate root, every ancestor, and final target by
identity.

### 4.4. Google

The Google Drive adapter already provides:

- server-side OAuth handling;
- metadata pagination and bounded requests;
- folder ancestry checks;
- ambiguity handling;
- bounded streaming and safe output names.

It does not yet expose the unified `DocumentRef/Query/ReadPlan` contracts or
Google Docs/Sheets revision semantics.

## 5. Contract technology

### 5.1. Pydantic and JSON Schema

The canonical dependency is Pydantic `2.13.4`, which was also the latest stable
release at the evidence cutoff. `2.14.0a1` was a prerelease.

Sources:

- [Pydantic 2.13.4 release and provenance](https://pypi.org/project/pydantic/)
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [Pydantic unions](https://docs.pydantic.dev/latest/concepts/unions/)
- [Pydantic TypeAdapter](https://docs.pydantic.dev/latest/concepts/type_adapter/)
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)

Verdict:

- Pydantic models are the runtime source of truth.
- Generated JSON Schema Draft 2020-12 is a derived, checked artifact.
- `TypeAdapter` is appropriate for explicit version/backend discriminated
  unions.
- Smart/unscored unions and hand-maintained duplicate JSON schemas are
  rejected.

### 5.2. Canonicalization and signatures

RFC 8785 JSON Canonicalization Scheme produces invariant UTF-8 JSON suitable
for hashing and signing. Registry and contract digests use SHA-256 over JCS
bytes. Duplicate keys, invalid Unicode, NaN, and Infinity are rejected.

Ed25519 is used for registry and Bridge-job signatures. PyCA `cryptography
49.0.0` was production-stable, supported Windows and Linux wheels, and was
licensed under Apache-2.0 or BSD-3-Clause.

Sources:

- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [RFC 8032 — EdDSA/Ed25519](https://www.rfc-editor.org/rfc/rfc8032.html)
- [PyCA cryptography 49.0.0](https://pypi.org/project/cryptography/)

## 6. Policy landscape

| Candidate | Version at cutoff | License | Maturity and maintenance | Windows/VPS/Python | Security model | Cost and operational burden | Code reduction / lock-in | Verdict |
|---|---:|---|---|---|---|---|---|---|
| Nobus application policy | repository-owned | repository | Existing and testable | Native Python on both hosts | Exact equality, closed rules, deny-overrides | No service or policy-language operations | Lowest code and lock-in | **ADAPT/ADOPT** |
| OPA | `1.17.0` | Apache-2.0 | Mature, active | Separate Go binary/sidecar | Rego, bundles, signed bundle verification | Extra process, bundle lifecycle, RPC, metrics | Useful only with distributed policy ownership | **Fallback, not MVP** |
| Cedar | `4.11.0` | Apache-2.0 | Mature Rust project | No first-class Python runtime; CLI/sidecar/FFI | Schema-validated analyzable authorization | Second runtime and domain language | AWS/Cedar model lock-in | **Defer** |
| PyCasbin | `1.43.0` | Apache-2.0 | Mature Python library | Easy to embed | Generic subject/object/action matchers | Low runtime cost but custom matcher burden | Does not remove Nobus path/DLP code | **Reject** |
| Signed capability job | design pattern | n/a | Established cryptographic pattern | Python + mTLS/Ed25519 | Exact short-lived one-use authority | Replay store and key lifecycle required | Reduces Bridge attack surface | **Adopt as overlay** |

Sources:

- [OPA releases](https://github.com/open-policy-agent/opa/releases)
- [OPA bundle management and signing](https://www.openpolicyagent.org/docs/management-bundles)
- [Cedar repository](https://github.com/cedar-policy/cedar)
- [Cedar schema validation](https://docs.cedarpolicy.com/policies/validation.html)
- [Cedar security guidance](https://docs.cedarpolicy.com/other/security.html)
- [PyCasbin](https://pypi.org/project/casbin/)
- [Casbin model syntax](https://v3.casbin.org/docs/syntax-for-models)

OPA becomes a valid fallback only when independently authored policies,
multiple policy-consuming services, or distributed tenant policy rollout make
its operational cost smaller than application-owned code.

AWS Verified Permissions is a paid Cedar option. At the evidence cutoff,
single authorization requests cost `$0.000005` each and policy-management
requests `$0.00004` each. It adds a network dependency and AWS lock-in and is
not needed for Gate 2.

- [AWS Verified Permissions pricing](https://aws.amazon.com/verified-permissions/pricing/)

## 7. Windows path security evidence

Windows path safety must account for:

- DOS, drive-relative, UNC, device, volume GUID, `\\?\` and `GLOBALROOT` paths;
- reserved device names and trailing dot/space normalization;
- alternate data streams;
- case-insensitive and per-directory case-sensitive behavior;
- symlink, junction, mount point, cloud placeholder, and other reparse tags;
- hard links;
- ancestor replacement and same-user TOCTOU.

Primary sources:

- [Windows path formats](https://learn.microsoft.com/en-us/dotnet/standard/io/file-path-formats)
- [Naming files, paths, and namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
- [File streams / alternate data streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams)
- [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Reparse point operations](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-operations)
- [Reparse points and file operations](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)
- [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
- [FILE_ATTRIBUTE_TAG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_attribute_tag_info)
- [SetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
- [FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info)
- [CreateHardLinkW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw)

Library findings:

- `pathvalidate 3.3.1`, MIT, is useful only for lexical validation and tests.
  It does not provide containment, reparse rejection, or race safety.
- `pywin32 312`, PSF, is mature and Windows-native, but an additional
  dependency is not justified if the existing narrow `ctypes` layer can expose
  only the required APIs.

Sources:

- [pathvalidate 3.3.1](https://pypi.org/project/pathvalidate/)
- [pywin32 312](https://pypi.org/project/pywin32/)

Verdict: build a narrow audited Windows I/O boundary by adapting the current
handle-based code. Do not trust a general path library.

## 8. Classification and DLP landscape

| Candidate | Version | License | Maturity / maintenance | Security fit | Operational burden | Verdict |
|---|---:|---|---|---|---|---|
| Current Nobus scanner | canonical commit | repository | Existing tests and runtime integration | Local regex, entropy, encoded/opaque data and exfil checks | Already paid | **Mandatory; adapt** |
| Gitleaks | `8.30.1` | MIT | Feature-complete; future releases limited to security fixes | Local stdin scanning and full redaction | One pinned Go binary/config/checksum | **Optional reinforcement** |
| TruffleHog | `3.95.2` | AGPL-3.0 | Very active, large detector set | Verification-oriented; may introduce provider/network authority | Heavy binary, rules and license review | **Not critical path** |
| Presidio | `2.2.363` | MIT | Mature, transitioning to community ownership | PII recognizers, NER, regex and checksum; documented false negatives | Python/NLP models or containers | **Future PII policy only** |
| YARA | `4.5.5` | BSD-3-Clause | Mature C engine | Malware/pattern matching, not semantic secret/PII policy | Native rules/build lifecycle | **Not critical path** |
| Google Sensitive Data Protection | managed | commercial | Mature cloud service | Requires transmitting inspected data to Google Cloud | Per-byte billing and cloud policy | **Reject for local pre-model gate** |
| Microsoft Purview DLP | managed | commercial/M365 | Mature enterprise suite | Strong M365 estate controls, not a narrow local gateway | Licensing and tenant administration | **Reject for MVP** |

Sources:

- [Gitleaks releases](https://github.com/gitleaks/gitleaks/releases)
- [Gitleaks stdin and redaction](https://github.com/gitleaks/gitleaks)
- [TruffleHog releases](https://github.com/trufflesecurity/trufflehog/releases)
- [TruffleHog repository and license](https://github.com/trufflesecurity/trufflehog)
- [Presidio documentation](https://microsoft.github.io/presidio/)
- [Presidio package](https://pypi.org/project/presidio/)
- [YARA repository and releases](https://github.com/VirusTotal/yara)
- [Google Sensitive Data Protection pricing](https://cloud.google.com/sensitive-data-protection/pricing)
- [Microsoft Purview pricing](https://www.microsoft.com/en-us/security/microsoft-purview-pricing)

No scanner proves the absence of secrets. Classification, path deny rules,
bounded parsing, tool-less execution, model-provider policy, and post-model
exfiltration checks remain independent controls.

## 9. Google/local parity evidence

Google Drive recommends the per-file `drive.file` scope where owner selection
or app-created/shared files permit it. Broad Drive read/write scopes are
restricted and may require verification and security assessment.

- [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

Drive exposes a monotonically increasing file `version`. Google Docs supports
`requiredRevisionId`, which rejects stale writes. `targetRevisionId` merges
against collaborator changes and is not strict CAS.

- [Drive Files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [Google Docs batchUpdate and WriteControl](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate)

Google Sheets validates and atomically applies subrequests within one
`batchUpdate`, but collaborator changes may affect the resulting spreadsheet.
It does not expose an equivalent strict revision precondition.

- [Google Sheets batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate)

Therefore parity means equal Nobus contracts and policy guarantees, not
pretending that every backend provides the same primitives. A strict-CAS plan
must be denied by an adapter that cannot provide strict CAS.

Canonical Google dependencies:

- `google-api-python-client==2.198.0`, current at the cutoff and officially in
  maintenance mode;
- `google-auth==2.29.0`, behind the then-current `2.56.x` line and requiring a
  Gate 3 upgrade/security review.

Sources:

- [google-api-python-client 2.198.0](https://pypi.org/project/google-api-python-client/)
- [google-auth release history](https://pypi.org/project/google-auth/)

## 10. MCP and reusable repositories

The reference filesystem MCP exposes read/write/move/delete operations,
accepts allowed directories or dynamic client Roots, and can disclose its
allowed directories. Its repository has published advisories for path-prefix
and symlink validation bypasses. It is not a Nobus authority boundary.

- [Reference filesystem MCP](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md)
- [Model Context Protocol server advisories](https://github.com/modelcontextprotocol/servers/security)

Other reviewed examples:

- [mark3labs/mcp-filesystem-server](https://github.com/mark3labs/mcp-filesystem-server):
  MIT and useful for operation/test ideas, but still a general filesystem tool.
- [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp):
  active MIT Python project with broad Workspace read/write/share and OAuth
  authority; useful only as an API-shape reference.
- [isaacphi/mcp-gdrive](https://github.com/isaacphi/mcp-gdrive):
  MIT, small history, broad Drive read and direct Sheets update tools; not an
  acceptable trusted boundary.

MCP guidance itself forbids token passthrough and documents confused-deputy,
session-hijack, and prompt-injection risks.

- [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [MCP authorization specification](https://modelcontextprotocol.io/specification/draft/basic/authorization)

Verdict: MCP may be a transport outside the authority decision, but no generic
filesystem or Google MCP server may grant model-visible authority in MVP-1.

## 11. Shortlist

### 11.1. Adopt/adapt

- Pydantic `2.13.4`;
- generated JSON Schema Draft 2020-12;
- RFC 8785 JCS + SHA-256;
- PyCA `cryptography 49.0.0` Ed25519;
- existing Nobus application policy;
- existing owner-file and owner-workspace algorithms;
- existing Google Drive pagination/ancestry adapter;
- current local scanner;
- optional pinned Gitleaks stdin mode.

### 11.2. Fallbacks

- OPA signed bundles after demonstrated multi-service policy-distribution need;
- Cedar/AWS Verified Permissions after demonstrated formal authorization need;
- Presidio after owner-approved PII taxonomy, languages, thresholds, and
  regression corpus;
- managed cloud DLP after explicit data-residency and procurement approval.

### 11.3. Rejected for MVP

- OPA/Cedar/Casbin in the Gate 2 critical path;
- generic filesystem/Google MCP authority;
- raw roots, paths, file IDs, OAuth tokens, or provider query fragments in
  model contracts;
- unsigned or partially refreshed registries;
- bearer capability tokens without mTLS, device binding, expiry, nonce, replay
  protection, and exact digest bindings;
- TruffleHog verification and YARA as primary runtime DLP;
- cloud DLP before the local secret gate;
- best-effort Google Sheets update represented as strict CAS.

## 12. Research verification

### L1 — deterministic completeness

- Canonical commit and required repository sources were checked.
- Candidate versions, licenses, primary links, shortlist, fallbacks, and
  rejects are present.
- No credentials, tokens, cookies, raw owner data, absolute owner roots in
  model examples, or client payloads are included.

### L2 — source reconciliation

- Product claims were reconciled against canonical documentation and current
  code.
- Technology claims were checked against official documentation, primary
  repositories, release pages, advisories, and pricing pages.
- GitHub repository search was used for the policy and MCP landscape.

### L3 — adversarial research audit

The recommendation was challenged against:

- tenant/project/client swaps;
- registry tamper and rollback;
- device/UNC/ADS/reserved-name/path escape;
- ancestor/final reparse and same-user races;
- MIME lies and decompression bombs;
- secret and post-model exfiltration;
- prompt injection;
- arbitrary MCP authority;
- Google/local revision mismatch.

The remaining implementation risks are made explicit in
[`ARCHITECTURE.md`](ARCHITECTURE.md); none is silently accepted as a Gate 2
PASS.
