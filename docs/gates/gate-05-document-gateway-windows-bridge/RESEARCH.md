# Gate 5 — Unified Document Gateway and Windows Local Library Bridge

**Document:** verified research dossier
**Status:** TARGET research baseline
**Canonical repository commit:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Evidence cutoff:** 2026-07-28
**Implementation status:** not implemented
**Research status:** `RESEARCH READY`

## 1. Executive verdict

Gate 5 must:

> **ADAPT the current Nobus document boundaries and BUILD one minimal outbound
> HTTPS pull-worker for Windows.**

The accepted foundation is:

1. Nobus Core remains the sole owner of Telegram, the durable queue, Google
   credentials and APIs, policy, audit, verification, and provider routing.
2. Windows has no network listener, inbound document API, SMB share, remote
   shell, or arbitrary filesystem endpoint.
3. The Windows Bridge initiates one outbound HTTPS connection to Core and
   accepts only signed, device-bound, fenced jobs with closed operations:
   `search`, `read`, `cancel`, and `status`.
4. A local `DocumentRef` contains a Bridge-minted opaque `doc_id`; it never
   contains a relative or absolute path, UNC path, device path, glob, regular
   expression, or provider-supplied URL.
5. Google Drive, Docs, and Sheets remain server-side native API adapters.
6. Local metadata search uses embedded SQLite FTS5 on Windows. Durable full
   document bodies are not indexed.
7. The primary parser stack is deliberately narrow:
   - standard-library text and bounded static HTML;
   - `python-docx`;
   - `openpyxl`;
   - `pypdf`;
   - `pdfplumber` only for selected PDF page/table fallback.
8. Docling Slim is a corpus-gated fallback, not an MVP critical dependency.
   OCR is a separate selected-page fallback and is off by default.
9. WinSW `2.12.0` supervises the Bridge under a separate Windows identity.
   WinSW is not a security boundary; SCM identity, ACLs, credential storage,
   restricted parser execution, and network policy create the boundary.
10. Tailscale may be added as defense in depth. It never replaces mTLS,
    application signatures, tenant authority, lease fencing, or replay state.

Rejected as the MVP foundation:

- arbitrary filesystem MCP servers;
- Untether, cc-connect, and other full coding-agent bridges;
- Cloudflare Tunnel to a local document origin;
- bare WebSocket or MQTT protocols;
- NATS/JetStream before multi-device or broker-scale requirements exist;
- open SMB/share, inbound HTTP/gRPC on Windows, shell, PowerShell, or
  model-controlled paths.

The normative design is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 2. Research scope and method

The research covered:

- the canonical MVP-1 roadmap, document contracts, write policy, runbook,
  CURRENT status, issues, and accepted ADRs;
- current owner-file, owner-workspace, Google Drive, durable SQLite, Windows
  Job Object, DPAPI, and credential code and their negative tests;
- outbound transport and queue alternatives;
- Windows service packaging and credential boundaries;
- local parsers, PDF/OCR fallbacks, embedded and server search indexes;
- official and community Google/filesystem MCP servers;
- ready Telegram/coding-agent bridges with evidence for Windows installation,
  runtime, tests, CI, issues, releases, security, and licensing;
- path/reparse/TOCTOU, secret/DLP, prompt injection, parser bombs, tenant
  binding, replay, split brain, reconnect, cancellation, and audit.

Evidence preference:

1. canonical repository at the pinned commit;
2. official protocol and vendor documentation;
3. primary repositories, release pages, security advisories, issues, and CI;
4. secondary commentary only when no primary source exists.

No owner-library content, VPN data, arbitrary `Системные`, secret stores, or
credentials were read. No Bridge, parser runtime, service, tunnel, Google
write, installation, or download was started.

## 3. Canonical evidence

Primary repository sources:

- [`docs/05-Спецификации-контрактов.md`](../../05-Спецификации-контрактов.md)
- [`docs/07-Правила-внешней-записи.md`](../../07-Правила-внешней-записи.md)
- [`docs/08-Runbook-эксплуатации.md`](../../08-Runbook-эксплуатации.md)
- [`docs/12-Эталон-MVP-1-и-дорожная-карта.md`](../../12-Эталон-MVP-1-и-дорожная-карта.md)
- [`ADR 0010`](../../adr/0010-owner-library-read-scope.md)
- [`ADR 0014`](../../adr/0014-natural-product-router-and-bounded-context.md)
- [`ADR 0017`](../../adr/0017-hybrid-natural-google-local-document-plane.md)
- [`CURRENT-STATUS.md`](../../handoffs/CURRENT-STATUS.md)
- [`MVP-1-ISSUES.md`](../../handoffs/MVP-1-ISSUES.md)
- [`WORKSPACE-INVENTORY.md`](../../handoffs/WORKSPACE-INVENTORY.md)
- [`Gate 2 research`](../gate-02-scope-document-contracts/RESEARCH.md)
- [`Gate 3 research`](../gate-03-google-foundation/RESEARCH.md)

Relevant CURRENT code:

- [`src/application/owner_files.py`](../../../src/application/owner_files.py)
- [`src/application/owner_workspace.py`](../../../src/application/owner_workspace.py)
- [`src/integrations/google_drive.py`](../../../src/integrations/google_drive.py)
- [`src/integrations/google_transport.py`](../../../src/integrations/google_transport.py)
- [`src/application/durable_telegram_state.py`](../../../src/application/durable_telegram_state.py)
- [`src/storage/sqlite_store.py`](../../../src/storage/sqlite_store.py)
- [`src/security/dpapi.py`](../../../src/security/dpapi.py)
- [`src/security/windows_credentials.py`](../../../src/security/windows_credentials.py)
- [`src/workers/windows_job.py`](../../../src/workers/windows_job.py)

Relevant tests:

- [`tests/test_owner_files.py`](../../../tests/test_owner_files.py)
- [`tests/test_owner_workspace.py`](../../../tests/test_owner_workspace.py)
- [`tests/test_google_drive.py`](../../../tests/test_google_drive.py)
- [`tests/test_google_drive_adversarial.py`](../../../tests/test_google_drive_adversarial.py)
- [`tests/test_google_drive_durable.py`](../../../tests/test_google_drive_durable.py)
- [`tests/test_windows_job.py`](../../../tests/test_windows_job.py)
- [`tests/test_queue12_crash_regressions.py`](../../../tests/test_queue12_crash_regressions.py)
- [`tests/test_network_boundaries.py`](../../../tests/test_network_boundaries.py)

## 4. CURRENT, reusable primitives, and gaps

### 4.1 Local owner-file read

`OwnerFileService` already provides:

- bounded metadata-first discovery;
- exact-versus-ambiguous selection;
- type and sensitive-name allow/deny rules;
- a 50 MiB source limit;
- bounded text extraction;
- `GetFinalPathNameByHandleW` verification of the opened file;
- before/after file-state checks;
- local secret/PII heuristics;
- an output-exfiltration check for substantially verbatim answers.

This is a valid implementation lineage, but not the TARGET Bridge boundary.
The gaps are:

- it runs in the server/Telegram process under the desktop account;
- search results are path-shaped;
- it has no device job, mTLS, fencing, replay, reconnect, or cancellation
  contract;
- DOCX/XLSX extraction is intentionally narrow;
- PDF text is unavailable;
- same-user ancestor replacement and broader Windows path forms are not
  eliminated by service isolation;
- no local index revision/tombstone model exists.

### 4.2 Owner workspace

`OwnerWorkspace` already demonstrates:

- snapshots and SHA-256 digests;
- destination compare-and-swap;
- pinned Windows directory handles;
- handle-relative replacement;
- readback, journaling, recovery, and concurrency locks.

Gate 5 is read-only. It must reuse the identity, CAS, and recovery lessons, but
must not expose current create/update/restore operations through the read
Bridge. Write jobs remain Gate 7 work.

### 4.3 Google Drive

`GoogleDriveClient` already provides:

- server-owned OAuth;
- paginated metadata search;
- bounded request and candidate budgets;
- folder ancestry validation;
- exact ambiguity handling;
- bounded streaming and safe filenames;
- no blind chunk retry.

It lacks:

- the unified `DocumentGateway` contract;
- Drive change-log indexing and tombstones;
- structured Google Docs reads;
- true Sheets range reads;
- provider-neutral revisions and normalized slices;
- a strictly separated read-only credential lineage.

### 4.4 Durable queue and Windows Job Object

The existing SQLite queue/outbox and Windows Job Object implementation provide
reusable patterns for:

- durable leases and restart recovery;
- compare-and-swap state;
- bounded retries and dead letters;
- immutable receipts;
- kill-on-close process trees and explicit cancellation.

They are not the Bridge wire protocol. Gate 5 must define a separate,
device-bound job state and must not reuse Telegram payloads or expose task
internals to Windows.

## 5. Transport and device-bridge landscape

Versions are the versions observed at the evidence cutoff and must be pinned
again during implementation.

| Candidate | Observed version / license | Maturity and Windows fit | Offline, streaming, and security | Cost / operations / lock-in | Verdict |
|---|---|---|---|---|---|
| HTTPS long-poll pull | HTTP/TLS platform primitives | Native on Windows, VPS, Python, and every reverse proxy | Core-owned queue, lease, heartbeat, chunks, and cancellation must be explicit; no Windows listener | No broker or SaaS data path; smallest operational surface | **BUILD minimal protocol** |
| gRPC client-initiated bidi | `grpcio 1.82.1`, Apache-2.0 | Mature; Windows/Python wheels available | Strong flow control, deadlines, and cancellation; durable queue and idempotency remain application work, and cancellation does not terminate a handler automatically | Protobuf/toolchain and harder packet-level diagnosis | **Fallback after measured need** |
| NATS JetStream pull | NATS Server `2.14.0`, Apache-2.0 | Mature and cross-platform | Durable consumers, explicit ACK and redelivery; rolling dedup/double-ACK do not replace the long-lived replay ledger or fencing | Extra broker, disk, ACL, backup, upgrade, and monitoring | **Defer until scale** |
| MQTT 5 / Mosquitto | Mosquitto `2.1.2`, EPL-2.0/EDL-1.0 | Mature Windows broker/client | QoS and persistent sessions exist; RPC lease, fencing, cancellation, and result audit remain custom | Broker without a document-specific benefit | **Reject MVP** |
| Bare WebSocket | `websockets 16.1.1`, BSD-3-Clause | Easy Python/Windows fit | Reconnect, durability, flow control, resume, replay, and cancellation are custom | Small library, large protocol responsibility | **Reject** |
| Tailscale overlay | Tailscale `1.98.9`, BSD-3-Clause | Strong Windows unattended support | WireGuard E2E identity and directional grants; not job authorization or replay protection | SaaS control-plane metadata and commercial-plan dependency | **Optional defense in depth** |
| Raw WireGuard | official Windows client | Mature tunnel | Strong network crypto; key/routing/firewall ownership remains local | No SaaS data path, highest network operations | **Network fallback** |
| Cloudflare Tunnel | `cloudflared 2026.7.3`, Apache-2.0 | Signed Windows MSI and outbound connector | Publishes a local origin through Cloudflare; does not create job semantics | Third-party request path, tunnel credential, Access-policy risk | **Reject local Bridge ingress** |

Primary sources:

- [gRPC authentication](https://grpc.io/docs/guides/auth/)
- [gRPC flow control](https://grpc.io/docs/guides/flow-control/)
- [gRPC cancellation](https://grpc.io/docs/guides/cancellation/)
- [gRPC deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC retry](https://grpc.io/docs/guides/retry/)
- [NATS JetStream consumers](https://docs.nats.io/nats-concepts/jetstream/consumers)
- [NATS reconnect behavior](https://docs.nats.io/using-nats/developer/connecting/reconnect)
- [NATS TLS](https://docs.nats.io/running-a-nats-service/configuration/securing_nats/tls)
- [MQTT 5.0 specification](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html)
- [Tailscale identity](https://tailscale.com/docs/concepts/tailscale-identity)
- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [WireGuard for Windows enterprise usage](https://git.zx2c4.com/wireguard-windows/about/docs/enterprise.md)
- [Cloudflare Tunnel model](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)

### Transport conclusion

The minimum safe protocol is not “HTTP instead of gRPC.” It is:

- Windows-originated pull;
- mTLS device identity;
- application-signed strict jobs;
- durable replay ledger;
- lease fencing;
- bounded heartbeat/cancellation;
- resumable ordered chunks;
- server-authoritative receipt and audit.

Changing HTTP to gRPC, NATS, MQTT, or WebSocket does not remove those
application invariants.

## 6. Windows service and credential packaging

| Candidate | Observed version / license | Recovery, identity, and logging | Maintenance risk | Verdict |
|---|---|---|---|---|
| WinSW | `2.12.0`, MIT | SCM wrapper, service account, failure actions, graceful stop, rolling logs, Event Log | Stable release is from 2023; v3 remains alpha | **Adopt, pinned** |
| Native .NET/Go Windows Service | platform | Best SCM, Schannel/CNG, Event Log, and single-binary lifecycle | Requires rewrite or additional native component | **Long-term option** |
| NSSM | stable `2.24` from 2014; Windows 10 fix in 2017 prerelease | Restart, accounts, and log rotation | Stale release and support lifecycle | **Reject** |
| Scheduled Task | Windows platform | Current Nobus pattern; logon/start triggers and finite restart | Weaker service readiness, dependency, identity, and stop semantics | **Not primary Bridge supervisor** |
| pywin32 ServiceFramework | pywin32 `312`, PSF | Native SCM integration from Python | Global install, DLL placement, LocalSystem/user-Python traps | **Defer** |

Primary sources:

- [WinSW releases](https://github.com/winsw/winsw/releases)
- [WinSW 2 configuration](https://github.com/winsw/winsw/blob/v2/doc/xmlConfigFile.md)
- [Microsoft service accounts](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts)
- [Restricted service SID](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/ns-winsvc-service_sid_info)
- [NSSM downloads](https://www.nssm.cc/download)
- [Task Scheduler restart schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element)
- [pywin32 repository](https://github.com/mhammond/pywin32)

WinSW is only a supervisor. The boundary is created by:

- a dedicated non-interactive service identity;
- service SID and explicit filesystem ACLs;
- protected executable/config/trust/replay/state directories;
- no plaintext password in WinSW XML, environment, command line, or logs;
- disabled WinSW download/self-update;
- owner/admin-driven signed upgrade and rollback;
- a concrete private-key storage design.

Python `SSLContext.load_cert_chain()` loads a PEM certificate/private-key path;
Python certificate enumeration does not provide a Windows private-key handle.
Therefore a claim that ordinary Python `ssl` automatically uses a
non-exportable Windows Store key would be false.

Sources:

- [Python `SSLContext.load_cert_chain`](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_cert_chain)
- [Python Windows certificate enumeration](https://docs.python.org/3/library/ssl.html#ssl.enum_certificates)
- [Windows CNG key storage providers](https://learn.microsoft.com/en-us/windows/win32/seccertenroll/cng-key-storage-providers)
- [`NCryptSignHash`](https://learn.microsoft.com/en-us/windows/win32/api/ncrypt/nf-ncrypt-ncryptsignhash)
- [`BCryptSignHash` ECDSA signature format](https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcryptsignhash)

The TARGET fixes a real non-exportable Windows key boundary: distinct ECDSA
P-256 keys are created by a CNG key storage provider; private-key ACLs admit
only the Bridge service SID/identity and administrators; mTLS uses
Schannel/WinHTTP, and application signing uses `NCryptSignHash` through a
small signed in-process native/.NET helper when Python cannot use the CNG
handle directly. The helper exposes no listener, named-pipe API, shell, path,
or generic signing oracle. PEM/PKCS#8 plus DPAPI was evaluated as a simpler
fallback but is rejected for the Gate 5 hard gate: inability to provision and
exercise the CNG boundary blocks activation instead of silently downgrading.

## 7. Parser landscape

### 7.1 Recommended narrow set

| Format | Candidate | Observed version / license | Strength | Mandatory boundary | Verdict |
|---|---|---|---|---|---|
| Text/CSV/JSON/Markdown | Python standard library | PSF | Minimal dependency and deterministic bounds | bytes/encoding/line/output limits | **Adopt current lineage** |
| Static HTML | standard library parser/sanitizer | PSF | No renderer or network | strip script/style, no URL fetch, output cap | **Adopt** |
| DOCX | `python-docx 1.2.0`, MIT | Mature OOXML document API | ZIP preflight, no macros/OLE/external relationships, parser child | **Adopt** |
| XLSX | `openpyxl 3.1.5`, MIT | Read-only worksheets and exact cells | `read_only=True`, `keep_links=False`, `defusedxml`, cell/formula caps | **Adopt** |
| PDF text | `pypdf 6.14.2`, BSD-3-Clause | Pure Python, selected pages | content-stream/memory/page/output limits, parser child | **Adopt** |
| PDF tables | `pdfplumber 0.11.10`, MIT | Selected page/region and table extraction | selected fallback only; not OCR | **Adapt fallback** |
| Complex layout | Docling Slim `2.115.0`, MIT code | Modular extras and normalized representation | exact extras/hashes; plugins, remote services, models, VLM, OCR off; model licenses separate | **Corpus-gated only** |
| Scanned PDF/images | OCR engine | varies | Extracts image text | selected pages, approved pinned artifact, separate corpus gate | **Off by default** |

Sources:

- [python-docx](https://pypi.org/project/python-docx/)
- [openpyxl and XML security note](https://pypi.org/project/openpyxl/)
- [pypdf](https://pypi.org/project/pypdf/)
- [pypdf extraction memory warning](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
- [pdfplumber](https://pypi.org/project/pdfplumber/)
- [Docling Slim](https://pypi.org/project/docling-slim/)

`pypdf` documents that page text extraction parses the whole content stream
and reports an observed case of roughly 10 GiB RAM for a 300 MiB uncompressed
stream. A file-size check alone is therefore not a parser boundary.

Every Office/PDF parser must run in a restricted child process on a staged copy
of the one selected file with:

- Windows Job Object memory, CPU, wall-time, process-count, and kill-on-close
  limits;
- an AppContainer/LPAC token without network capability;
- an outbound firewall deny for the dedicated parser host executable as defense in depth;
- no read ACL to the owner library;
- only a per-job temp directory;
- deterministic cleanup after success, error, timeout, cancellation, or crash.

A Job Object is a resource/process-tree boundary, not a network boundary.
The no-network claim depends on AppContainer/LPAC capability isolation and is
verified in the installed service environment.

Primary Windows sources:

- [Job Object basic limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)
- [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
- [CreateRestrictedToken](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken)

### 7.2 Broad parser alternatives

| Candidate | Evidence | Result |
|---|---|---|
| Apache Tika `3.3.2`, Apache-2.0 | Very broad mature parser set; Java 11+. Apache states parsing is dangerous and Tika is not a security boundary. [Security model](https://tika.apache.org/security-model.html), [security advisories](https://tika.apache.org/security.html) | Fixed-config isolated legacy DOC/XLS fallback only; no Tika server/gRPC Bridge |
| Unstructured `0.24.x`, Apache-2.0 | Broad formats, but full Windows stack adds libmagic, Poppler, Tesseract, LibreOffice, Pandoc, and version-specific inference dependencies | Reject MVP |
| PyMuPDF `1.28.x` | Fast, high-quality Windows wheels | AGPL-3.0 or commercial license; reject until legal/commercial decision |
| LibreOffice `26.2.5`, MPL-2.0 | Mature Windows/headless legacy conversion | Isolated legacy fallback only; never automatic formula recalculation |
| Tesseract | Apache-2.0 | Windows can run it, but the project does not publish a current official Windows installer | Separate pinned OCR artifact only |

## 8. Metadata index and incremental refresh

| Candidate | Observed version / license | Fit | Operations and isolation | Verdict |
|---|---|---|---|---|
| SQLite FTS5 | upstream SQLite `3.53.4`, public domain | Embedded, ACID, BM25, phrase/prefix/NEAR, no daemon | Python may bundle another SQLite; startup must check `sqlite_version()` and exercise FTS5; authority predicate precedes ranking | **Adopt** |
| Tantivy | `0.26.1`, MIT | Fast BM25/facets; Windows/Python wheels | Native dependency, schema/index migration, Windows mmap lifecycle | **Fallback after measured SLO failure** |
| Meilisearch | `1.45.1`, community MIT plus enterprise BUSL | Ready server search | Separate service, keys, TLS, backups; Windows Desktop not primary supported production target | **Reject MVP** |
| Whoosh | unmaintained | Pure Python | No active maintenance/security response | **Reject** |
| Windows Search | Windows component | Existing system catalog and IFilters | LocalSystem/shared catalog, policy/admin-dependent coverage, non-portable query semantics | **Not authority; optional accelerator only** |

Sources:

- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [SQLite release log](https://www.sqlite.org/releaselog/current.html)
- [SQLite security](https://www.sqlite.org/security.html)
- [Tantivy repository](https://github.com/quickwit-oss/tantivy)
- [Meilisearch releases](https://github.com/meilisearch/meilisearch/releases)
- [Whoosh repository](https://github.com/whoosh-community/whoosh)
- [Windows Search overview](https://learn.microsoft.com/en-us/windows/win32/search/-search-3x-wds-overview)

FTS5 is metadata-only for MVP. It may index bounded display names, normalized
tags, media type, safe project/client labels, and dates. It must not durably
store extracted body text, secrets, document snippets, raw absolute paths, or
model prompts. Raw user `MATCH` syntax is not accepted; the application builds
a bounded parameterized query.

`ReadDirectoryChangesW` or USN can accelerate discovery, but neither is the
source of truth. Startup and periodic bounded reconciliation must recover from
offline gaps, buffer overflow, USN rollover, or missed events.

## 9. Google Drive, Docs, and Sheets evidence

### Drive

- `files.list` supports bounded `fields`, `q`, corpora, ordering, pagination,
  and may report `incompleteSearch`.
- Drive change logs use `startPageToken`, `changes.list`, and
  `newStartPageToken`; shared drives require separate handling.
- revoke/delete becomes a tombstone, not a false “not found.”
- native Google files and blob files have different download/export behavior.

Sources:

- [Drive `files.list`](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list)
- [Search files](https://developers.google.com/workspace/drive/api/guides/search-files)
- [Track changes](https://developers.google.com/workspace/drive/api/guides/manage-changes)
- [Download and export](https://developers.google.com/workspace/drive/api/guides/manage-downloads)

### Docs

`documents.get` accepts document/view parameters but no text range or page
size. It returns a complete `Document`. `Range` is part of the document model
and update operations; it is not a server-side ranged-read parameter.

Therefore Gate 5 must describe Docs range semantics honestly:

> full structured fetch under a hard wire/decompressed response cap, followed
> by adapter-side tab/UTF-16 range selection.

An oversized response fails closed as `DOCUMENT_TOO_LARGE_FOR_SAFE_READ`.
It is never silently truncated into a seemingly complete answer.

Sources:

- [Docs `documents.get`](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get)
- [Docs Document and Range model](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents)

### Sheets

Sheets supports true bounded reads:

- `values.batchGet` accepts exact A1/R1C1 ranges;
- `spreadsheets.get` accepts ranges and field masks;
- cells, ranges, response bytes, and request deadlines remain application
  bounded.

Sources:

- [Sheets `values.batchGet`](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet)
- [Sheets `spreadsheets.get`](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get)
- [Sheets field masks](https://developers.google.com/workspace/sheets/api/guides/field-masks)

Google transport failure is `PROVIDER_UNAVAILABLE` or partial/degraded search,
never an empty result set.

## 10. MCP, GitHub, paid connectors, and ready bridges

### 10.1 MCP and connector candidates

| Candidate | Maturity / authority | Risk | Verdict |
|---|---|---|---|
| Official Google Workspace remote MCP | Developer Preview; official OAuth and tool schemas | Includes read and write tools; Google requires prompt/response injection screening | Read-only canary/reference only; native APIs remain authority |
| `taylorwilsdon/google_workspace_mcp 1.22.2`, MIT | Active community project, Windows config and read-only mode | Broad services, credentials, attachments/local paths; published CI is not Windows proof | Disposable evaluation/reference only |
| Official MCP filesystem server | Official reference server | Read/write/edit/move/delete/tree and dynamic Roots create broad path authority | Reject as Bridge |
| Community Drive MCP servers | Mixed maturity and scopes | Provider IDs, broad OAuth, write tools, local attachment paths | Reference only |
| Composio / managed connectors | Paid managed integration plane | Additional processor, credential, retention, residency, and tool-authority boundary | Contingency only after DPA/residency/tool allowlist review |
| Nango | Managed/self-host integration platform | Considerable database/queue/operations footprint for this narrow problem | Reject MVP |

Sources:

- [Official Google Workspace MCP configuration](https://developers.google.com/workspace/guides/configure-mcp-servers)
- [Official Google Workspace MCP security](https://developers.google.com/workspace/guides/configure-mcp-security)
- [Official MCP filesystem server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)

No MCP server may become a model-facing local filesystem authority. If an MCP
transport is ever evaluated, Core still exposes only the same closed
`DocumentGateway` operations and keeps provider credentials outside the model.

### 10.2 Untether

Untether `0.35.4` is MIT and declares Python `>=3.12` and an
`OS Independent` classifier. That classifier is not Windows runtime evidence.
Its published CI runs on `ubuntu-latest`, and the product launches coding-agent
subprocesses with browsing, restart, file, and control surfaces.

Sources:

- [Untether `pyproject.toml`](https://github.com/littlebearapps/untether/blob/main/pyproject.toml)
- [Untether CI](https://github.com/littlebearapps/untether/blob/main/.github/workflows/ci.yml)

Verdict:

- reject the whole product as the document boundary;
- reuse only conceptual patterns such as deduplication, cancellation,
  reconnect, and redaction;
- do not claim Windows support without install/runtime/service/sleep/reconnect
  evidence.

### 10.3 cc-connect and similar bridges

cc-connect has stronger Windows evidence: a Windows binary, Task Scheduler
daemon code, hidden launcher, restart loop, and log handling.

Sources:

- [cc-connect installation](https://github.com/chenhg5/cc-connect/blob/main/INSTALL.md)
- [cc-connect Windows daemon](https://github.com/chenhg5/cc-connect/blob/main/daemon/windows.go)

It is still rejected as a whole because `/shell`, directory switching,
coding-agent subprocesses, permissive/yolo modes, attachment transfer, and
remote agent control violate the Gate 5 authority boundary. Packaging patterns
may be studied; its runtime must not be adapted into the Bridge.

## 11. Windows filesystem and data-security findings

The Bridge must account for:

- DOS, drive-relative, UNC, device, volume GUID, `\\?\`, and `GLOBALROOT`
  namespaces;
- alternate data streams;
- trailing dot/space and reserved device-name normalization;
- symlink, junction, mount point, cloud placeholder, and other reparse tags;
- hard-link aliasing;
- ancestor replacement and same-user TOCTOU;
- case-insensitive and per-directory case-sensitive behavior.

Primary sources:

- [Windows path formats](https://learn.microsoft.com/en-us/dotnet/standard/io/file-path-formats)
- [File streams / ADS](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams)
- [`CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
- [Reparse points and file operations](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)
- [`GetFinalPathNameByHandleW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
- [`GetFileInformationByHandle`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle)

Containment requires both:

1. OS denial: the Bridge identity cannot read outside approved roots or write
   into them.
2. Application proof: registry lookup, reparse rejection, pinned root and
   opened-file identity, final path/volume/file-ID comparison, stable
   before/after state, and reading only from the verified handle.

String normalization by itself is not a containment boundary.

Extracted document content is untrusted data. It cannot change the job,
request tools, expand roots, alter tenant bindings, or authorize another
operation. Analysis receives no shell, filesystem, network, or mutation
capabilities.

Secrets and restricted content:

- are scanned before transfer to Core/model;
- are never placed in the FTS body index, logs, audit, job payload, or error;
- return a stable blocked/classification result;
- may be processed only by an explicitly allowed local deterministic route.

## 12. Coherent end-to-end alternatives

| Dimension | A — HTTPS pull + narrow parsers + SQLite | B — HTTPS/gRPC + Docling Slim + optional Tailscale | C — NATS + Tika/Tantivy legacy/scale | D — MCP/managed agent plane |
|---|---|---|---|---|
| Maturity | Mature platform primitives; new small Nobus protocol | Mature transport and active parser, but rapid release cadence | Mature components and broad format coverage | Product maturity varies; official Workspace MCP is preview |
| Maintenance | Low-to-medium | Medium; native/model dependency pinning | High: broker, JVM/Rust, schemas, backups | High policy/credential/vendor coordination |
| Windows/VPS/Python | Best match to current runtime | Good, but larger dependency surface | Possible, with several runtimes/services | Uneven and tool-schema driven |
| License | PSF/MIT/BSD/public-domain components | MIT code; model licenses separate | Apache-2.0/MIT | Mixed service terms and licenses |
| Security | Smallest authority and data-transfer surface | Strong if isolated; more parser attack surface | More services, ACLs, ports, and patching | Broad tools, credentials, paths, third-party processing |
| Data transfer | Bounded metadata and selected slices only | Same, optionally through Tailscale | Control through broker, content through separate HTTPS | Often provider/tool controlled |
| Cost | Existing VPS/PC and package maintenance | Optional Tailscale and model/artifact cost | Broker/storage/operations | SaaS and connector cost |
| Operational burden | Lowest | Medium | Highest | Medium-to-high |
| Code reduction | Reuses current code and standard libraries | Reduces normalization code for complex layout | Reduces queue/parser breadth code, adds integration code | High prototype reduction, low authority control |
| Lock-in | Low | Medium parser/network lock-in | Medium infrastructure lock-in | High tool/vendor lock-in |
| Fallback | gRPC or Docling can be added independently | Revert to narrow parser/HTTPS | Fall back to A | Difficult to prove equivalent audit/replay |
| Verdict | **ADOPT/ADAPT/BUILD** | **Corpus/latency-gated fallback** | **Defer** | **Reject foundation** |

## 13. Recommended stack, fallbacks, and explicit rejects

### Adopt

- Core-owned native Drive/Docs/Sheets APIs.
- Provider-neutral `DocumentGateway`.
- Windows-originated HTTPS pull.
- mTLS plus signed strict job envelopes.
- SQLite FTS5 metadata-only local index.
- current bounded owner-file and Windows-handle implementation lineage.
- current durable SQLite/lease/recovery and Windows Job Object patterns.
- WinSW `2.12.0` as pinned supervisor.
- standard library, `python-docx`, `openpyxl`, `pypdf`.

### Adapt

- `pdfplumber` for exact selected PDF page/table fallback.
- Docling Slim after a golden corpus proves net benefit.
- Tailscale as optional network defense in depth.
- Tantivy only after measured SQLite SLO failure.
- Tika/LibreOffice only for explicitly accepted legacy formats in an isolated
  child.

### Build

- strict Bridge DTOs and endpoints;
- registration and device-key lifecycle;
- signed lease/fencing/replay/cancel/resume protocol;
- local source registry and opaque document map;
- FTS5 index and tombstone/reconciliation state;
- staged parser host with Job Object and network deny;
- normalized Google/local slices and partial-provider merge;
- Bridge health, audit, packaging, upgrade, migration, and rollback.

### Reject

- any path, URL, command, executable, parser option, or tool name supplied by
  a Bridge job;
- Windows listener or Core-initiated connection to Windows;
- Cloudflare local origin, SMB, share, filesystem MCP;
- Untether/cc-connect/Takopi or other agent bridge as the runtime;
- model-held Google, Telegram, Bridge, or Windows credentials;
- durable full-content FTS index;
- parser in the long-lived Bridge process;
- HTTP redirects, proxy environment inheritance, compressed wire bodies, or
  unbounded decoded content;
- blind retry after unknown result;
- false “nothing found” when a provider is unavailable.

## 14. Threat and failure register

| Threat / failure | Required control |
|---|---|
| Cross-tenant/project/client candidate leak | Authority predicate before ranking and repeated binding on read |
| Relative-path capability or opaque-ID swap | Bridge-minted random `doc_id`, local mapping, signed response, revision and authority recheck |
| Reparse/junction/directory swap | Service ACL, reparse rejection, pinned/open handle and final identity verification |
| Hard-link/ADS/device namespace | Reject links with multiple aliases where policy cannot prove safety; no colon/UNC/device path from jobs |
| Stale index | Metadata revision, tombstone, bounded reconciliation, fail stale read |
| Duplicate or old worker | Durable replay ledger and monotonic lease fencing epoch |
| Stolen device key | Short-lived cert, protected key, rotation/revocation, conflicting-session quarantine |
| Chunk truncation/reorder | Sequence, decoded/wire totals, per-chunk and final digest, atomic commit |
| Parser bomb/OOM | ZIP/content preflight, restricted parser child, Job Object and output limits |
| Parser escape/network | Restricted token, parser executable firewall deny, no library ACL, process-count limit |
| Prompt injection | Untrusted content channel and tool-less analysis |
| Secret leak | local DLP/classification; no content index/log/audit; safe stable error |
| Google Docs oversized full fetch | wire/decompressed cap and fail-closed result |
| Provider outage | explicit partial/degraded status, never empty-result substitution |
| Offline reconnect herd | exponential backoff with jitter and server `Retry-After` |
| Disk full/state corruption | fail closed, health degradation, no new lease until durable state is writable |

## 15. Gate dependencies

| Gate | Gate 5 dependency / handoff |
|---|---|
| Gate 2 | Freezes provider-neutral document contracts, strict schemas, canonicalization, registry revisions, authority equality, and signature primitives |
| Gate 3 | Supplies server-owned Google identity, Drive/Docs/Sheets adapters, provider error taxonomy, quota and retention policy |
| Gate 6 | Consumes normalized `DocumentSlice`, provenance, classification, and deterministic calculation inputs; must not gain source authority |
| Gate 7 | Adds separate create/update contracts, snapshot/CAS/preview/readback; must not silently extend Gate 5 read jobs |
| Gate 8 | Installs service/ACL/firewall/key material, performs rotation, migration, rollback, pilot, release L4, and live fault tests |

## 16. Research verification

### L1

- canonical commit and CURRENT/TARGET distinction checked;
- required scope, candidates, versions, licenses, Windows evidence, links,
  rejects, and hard gates are present;
- no secret, credential, account identifier, owner content, or absolute
  runtime path value is recorded;
- no implementation or external action was performed.

### L2

- recommendations were replayed against current owner-file, Google Drive,
  durable SQLite, Windows Job Object, DPAPI, and test primitives;
- protocol and library claims were checked against official documentation,
  repositories, releases, security advisories, CI, and issues;
- HTTP pull was compared as a complete system, not only as a transport.

### L3

The adversarial checklist includes:

- stolen key and conflicting device session;
- two Bridges and lease split brain;
- replay before/after restart;
- chunk truncation, reorder, duplication, and digest mismatch;
- ZIP/PDF/XML bomb;
- parser process escape and network probe;
- reparse/directory swap;
- opaque-ID and tenant swap;
- stale index and tombstone;
- Google Docs full-fetch overflow;
- local offline/reconnect and provider partial results.

Research conclusion: **`RESEARCH READY`**. No implementation or release gate is
claimed as passed.
