# Gate 8 — Hybrid Release and 72-hour Pilot Architecture

**Document status:** TARGET / NORMATIVE FOR GATE 8 / ARCHITECTURE READY
**Gate execution status:** IMPLEMENTATION/PILOT BLOCKED; no deployment or Gate 8 PASS
**Canonical baseline:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Research:** [`RESEARCH.md`](RESEARCH.md)
**Higher authority:** repository and parent `AGENTS.md`, accepted ADRs and canonical
documents 01–12

This document specifies the target product, operations, release and security
architecture for Gate 8. It does not authorize SSH, service installation, tunnel
creation, secret access, backup, migration, runtime start or deployment.

## Status model

| Layer | Status | Meaning |
|---|---|---|
| TARGET architecture | **ARCHITECTURE READY** | Root decisions are normative and document-level L1/L2/L3 pass |
| Gate 8 implementation/pilot | **BLOCKED** | Prerequisite implementations, exact L4 actions and runtime evidence are absent |
| Gate 8 PASS | **NOT CLAIMED** | Full smoke, restore evidence and unchanged 72-hour pilot have not run |

Design readiness never implies that a service, backup, migration, restore or pilot was
executed.

## 1. Owner operational outcome

After Gate 8 PASS, the owner has:

- one always-on Linux Nobus Core;
- one globally fenced Telegram polling consumer;
- one authorized Windows Local Library Bridge;
- continuing Telegram and Google operation when the Windows PC is offline;
- exact current and previous Core/Bridge artifacts;
- a content-free owner status showing Core, polling, Google, DB, Bridge, queues,
  reconciliation and recovery evidence;
- an encrypted off-host recovery chain with a portable restore drill;
- a deterministic stop/reconcile/rollback decision for every release failure class;
- 72 hours of evidence with no orphan, duplicate or unrequested effect.

The owner is not required to operate containers, PostgreSQL, Kubernetes, a message
broker or a full observability platform for MVP-1.

## 2. Non-goals

Gate 8 does not provide:

- active/active or active/passive Core;
- a second or standby Telegram poller;
- multiple authorized Bridges;
- network filesystem access to SQLite or the Windows owner library;
- arbitrary shell, PowerShell or filesystem API on Bridge;
- automatic PostgreSQL migration;
- automatic recovery from an ambiguous external write;
- rollback of Google/Telegram/local effects by switching a code pointer;
- deletion, sharing/access changes, third-party delivery, money actions, remote or
  push beyond the exact Gate 8 L4;
- autostart or supervised restart before pilot PASS.

## 3. CURRENT and TARGET

| Concern | HISTORICAL HANDOFF (UNVERIFIED) | TARGET Gate 8 |
|---|---|---|
| Core host | Windows owner session | Linux VPS, static `nobus-core` identity |
| Core supervisor | Task Scheduler | systemd |
| Bridge | Not production-current | WinSW 2.12.0, separate identity |
| Polling fence | Windows mutex + local SQLite lease | One server credential boundary + generation lease + ingress dedupe |
| Storage | Four local SQLite runtime DBs | Dynamically inventoried single-node SQLite set, write-fenced recovery sets |
| Secrets | Current Windows user/DPAPI | Separate Core and Bridge credentials; revoke and re-enroll per target identity |
| Health | DB-centric local probe | Composite fresh health and independent heartbeat |
| Backup | Local backup/restore implementation | Encrypted off-host data restore plus target-identity credential re-enrollment |
| Release | Local commit/runtime | Signed immutable artifacts and current/previous pointers |
| Supervision | Restart currently available locally | Disabled during acceptance; enabled only after 72h PASS |

`TARGET` is not evidence of implementation. The middle column only records the
handoff-reported baseline at the documentation base commit and is `UNVERIFIED` as
runtime evidence. A fresh Gate 0 process/Scheduler/DB/network evidence pack is
required before any `CURRENT` claim; `CURRENT-STATUS.md` alone is not live proof.

## 4. Target topology and trust boundaries

```text
Owner Telegram
      |
      | Telegram Bot API TLS; one current bot token
      v
+------------------------------------------------------+
| Linux VPS / Nobus Core trust boundary                |
|                                                      |
| systemd -> one nobus-core process                    |
| policy + L4 + polling + queue/outbox/effect ledger   |
| Google adapters + Bridge job issuer                  |
| discovered SQLite DB inventory + release/health evidence |
+------------------------------------------------------+
          |                              |
          | Google TLS/OAuth             | Tailscale reachability
          v                              | + application mTLS
   Google Workspace                      | + signed closed jobs
                                         v
                         +--------------------------------------+
                         | Windows Bridge trust boundary        |
                         | WinSW -> one Bridge process          |
                         | approved-root adapters only          |
                         | device key + dedupe/result journal   |
                         +--------------------------------------+
                                         |
                                         v
                           approved owner-library roots

Off-host recovery boundary:
Core snapshot set -> restic client encryption -> independent repository
```

Trust is not transitive:

- Telegram identity does not authorize a Bridge job.
- Tailscale membership does not authorize a device.
- systemd and WinSW supervise local processes; neither proves a global singleton.
- A valid device certificate does not authorize an arbitrary capability/path.
- A release signature does not authorize deployment; exact L4 still applies.
- A backup manifest does not prove that data restores or that target identities can
  be re-enrolled; DPAPI blobs/private keys are not portable backup payloads.
- A previous code artifact does not define the state of external providers.

## 5. Service identities and authority

### 5.1 Linux identities

| Identity | May | Must not |
|---|---|---|
| `root`/release operator | Install verified artifact, unit and ACL under exact L4 | Run normal Core work or hold application tokens longer than required |
| `nobus-core` | Read current release/config, write Core state, call Telegram/Google/Bridge endpoints | Login, sudo, modify releases, read unrelated host data |
| backup writer | Read completed fenced snapshot sets and append to recovery repository | Read live DB directly, prune immutable generations |
| backup maintainer | Run approved check/retention/prune after immutability window | Run Core or external effects |
| health heartbeat | Read content-free health summary and emit heartbeat | Read DB payloads or secrets |

The Core service identity is static, has no interactive shell or sudo and receives
only the credentials required by the current process. Releases are owned by the
release operator and are read-only to `nobus-core`.

### 5.2 Windows identities

| Identity | May | Must not |
|---|---|---|
| Bridge installer/operator | Install exact WinSW/Bridge artifact under L4 | Perform normal document work |
| `nobus-bridge` local service account | Read/write explicit registry roots through closed operations; use its device key | Interactive logon, Google/Telegram secrets, arbitrary shell, other user roots |
| Tailscale Windows service | Provide network overlay | Grant Nobus application authority |

The Bridge account receives `Log on as a service`, deny-interactive-logon policy and
explicit ACLs only. The device key is non-exportable where supported and readable only
by this identity. No password or private key is stored in WinSW XML.

### 5.3 Exact authority ownership

| Authority | Sole owner |
|---|---|
| Telegram bot token and polling offset | One active Core server-side credential boundary; never Bridge |
| Google OAuth credentials | Core Google adapter |
| Policy, tenant binding and L4 validation | Deterministic Core |
| External-effect ledger and reconciliation state | Core DB |
| Bridge device private key | Authorized Windows device/service identity |
| Local file access | Closed Bridge adapters |
| Release signing key | Approved release-signing process, never Core/Bridge |
| Backup encryption/recovery secret | Recovery process separate from VPS snapshot |

## 6. Immutable release artifacts

### 6.1 Artifact composition

Core artifact:

```text
nobus-core-<commit>-<artifact_sha256>.tar
  app/
  wheelhouse/
  requirements.lock
  manifest.json
  manifest.sigstore.json
  sbom.cdx.json
  verification/
    secret-scan-summary.json
    dependency-audit-summary.json
    static-analysis-summary.json
```

Bridge artifact has the equivalent structure plus the exact WinSW 2.12.0 binary and
its digest. Artifacts contain no `.git`, `.env`, credentials, tokens, cookies, live DB,
logs, caches or owner payloads.

### 6.2 Release manifest contract

The manifest is canonical JSON and contains at least:

```json
{
  "schema_version": "nobus.release-manifest.v1",
  "component": "core|bridge",
  "release_commit": "<40-hex>",
  "artifact_sha256": "<64-hex>",
  "built_at": "<UTC RFC3339>",
  "target": {"os": "<exact>", "arch": "<exact>", "python": "<exact>"},
  "dependency_lock_sha256": "<64-hex>",
  "wheelhouse_digest": "<64-hex>",
  "sbom_sha256": "<64-hex>",
  "external_binary_digests": {},
  "contract_digests": {},
  "expected_database_set": [],
  "schema_digests": {},
  "migration_ids": [],
  "compatible_previous_release": "<commit+artifact>",
  "required_peer_protocols": {},
  "source_evidence_refs": [],
  "verification_summary_digests": {}
}
```

Rules:

- every digest is computed over canonical bytes, not a display representation;
- `migration_ids` is exact and defaults to an empty list;
- unknown manifest fields or unsupported schema versions fail closed;
- `release_commit` alone is insufficient; commit and artifact digest are inseparable;
- SBOM, scan reports and external binaries are themselves digest-bound;
- the manifest contains identifiers/evidence only, never secrets;
- Core and Bridge manifests pin mutually compatible protocol versions.

### 6.3 Dependency and supply-chain gates

Before an artifact becomes a candidate:

- dependencies are exact-version and hash pinned;
- installation succeeds offline with `--require-hashes` and binary-only policy where
  supported;
- Gitleaks scans source history and artifact;
- Semgrep/static checks pass or have an explicit expiring exception;
- pip-audit checks the exact lock/wheel set;
- Syft generates the CycloneDX SBOM;
- licenses are inventoried;
- artifact and manifest signatures verify against a pre-pinned verifier identity/key;
- scan output is content-free and contains no discovered secret value.

An upstream version change creates a new artifact and a new Gate 8 approval binding.

## 7. Deployment directories and pointers

### 7.1 Linux

```text
/opt/nobus/
  releases/
    <commit>-<artifact_sha256>/
      app/
      wheelhouse/
      requirements.lock
      manifest.json
      sbom.cdx.json
      .venv/
  current  -> releases/<candidate>
  previous -> releases/<last-accepted>

/etc/nobus/
  public/
  credentials/          # root/service ACL; outside releases

/var/lib/nobus/
  db/
  bridge/
  release/
  snapshots/

/var/cache/nobus/       # bounded disposable caches only
```

The venv is created at its final immutable release path from the included wheelhouse.
It is never copied from another host.

Pointer rules:

- service is stopped and write/effect dispatch fenced before a pointer change;
- target artifact signature and all digests are reverified;
- `previous` is set to the exact previously accepted artifact;
- directory and pointer updates are flushed before start;
- old releases are not deleted inside the Gate 8 window;
- pointers select code only, never DB or external-effect state.

### 7.2 Windows

```text
C:\Program Files\Nobus\
  releases\<commit>-<artifact_sha256>\
  current\
  previous\

C:\ProgramData\Nobus\
  bridge-state\
  logs\
  release\
```

The service is stopped while the validated directory junction/pointer is replaced.
Replacement uses Windows write-through semantics and is read back before start.
Bridge state, credentials and logs remain outside release directories.

## 8. Service supervision concepts

### 8.1 systemd units

The minimal target set is:

- `nobus-core.service`;
- `nobus-backup.service` as an explicit one-shot operation;
- `nobus-backup.timer` only after recovery policy approval;
- an outbound health heartbeat timer/service if it is not part of Core.

Core unit concept:

- `User=nobus-core`, `Group=nobus-core`, `UMask=0077`;
- `WorkingDirectory=/opt/nobus/current`;
- `ExecStartPre` validates manifest, pointers, DB set/schema and no conflicting local
  process;
- `ExecStart` uses the full `.venv/bin/python` path;
- `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`,
  `ProtectHome=true`;
- explicit `ReadWritePaths=/var/lib/nobus` and required cache path;
- address families restricted to Unix/IPv4/IPv6;
- no ambient capabilities;
- secrets supplied through a protected credential mechanism, never unit text;
- `Restart=no` during acceptance and pilot;
- after pilot, bounded `Restart=on-failure`, start limits and technical
  restart-preventing exit statuses.

The service must not auto-restart after integrity, schema, fencing, tenant, digest,
reconciliation or unknown-effect failure.

### 8.2 WinSW concept

The WinSW XML is configuration-only and digest-bound:

- exact Bridge executable and working directory;
- service ID/display name;
- `startmode=Manual` through pilot;
- no restart action through pilot;
- bounded log rolling with content-free application logs;
- no credentials or service-account password;
- stop timeout compatible with Bridge lease/result flush;
- exact environment allowlist.

After pilot PASS and separate L4:

- start becomes delayed automatic;
- a bounded restart action is enabled only for safe process-level failure;
- technical/security exit codes remain restart-preventing.

SCM provides one configured service, but Bridge also uses a local process lock and a
Core-issued active-device lease. WinSW alone is not the singleton proof.

## 9. Global Telegram polling fence

### 9.1 Invariant

At every instant, at most one process with the current bot token may invoke
`getUpdates`. A healthy status requires positive proof of the active owner, not merely
absence of an observed conflict.

### 9.2 Layers

1. **Global credential fence.** The current bot token exists only in one active Core
   server-side secret boundary. Bridge never receives it. Host cutover with uncertain
   token erasure requires BotFather token rotation before start.
2. **Deployment inventory.** Preflight proves old server service, Windows Scheduler,
   manual runner and webhook are inactive.
3. **Host process fence.** One systemd unit plus a process lock owned by
   `nobus-core`.
4. **Durable lease.** The Core DB stores consumer ID, release ID, generation,
   acquired/renewed/expiry times and current offset.
5. **Ingress dedupe.** Unique `(bot_identity, update_id)` plus source digest is durable
   before admission acknowledgement/offset advance.
6. **Generation CAS.** Only the current generation advances the offset or admits
   effects.

The polling lease covers polling ownership only; it does not bound a three-hour worker
or make an already-started external effect safe to repeat.

### 9.3 Loss and split brain

- lease loss stops new admission and cancels/relinquishes claims where safe;
- a Telegram conflict, unexpected offset movement or second consumer signal is
  `FAIL_STOP`;
- both suspected consumers are stopped;
- current token is rotated if exclusive custody cannot be proven;
- pending/accepted updates and effects are reconciled before one Core restarts;
- no automatic election or failover exists in MVP-1.

## 10. Bridge device and job fencing

### 10.1 Enrollment

Exactly one device record may be active:

```text
device_id
certificate_fingerprint
device_generation
bridge_release_digest
allowed_registry_digest
status = pending|active|revoked
issued_at / expires_at
last_sequence
```

Enrollment and revocation require action-bound L4. Re-enrollment increments
`device_generation` and revokes the previous certificate before new jobs are issued.

### 10.2 Closed job envelope

Every job binds:

- `job_id` and idempotency key;
- tenant/project/client scope;
- active `device_id` and `device_generation`;
- exact closed operation;
- normalized relative targets/source references;
- input revision/digest;
- capability/policy/release digests;
- nonce, monotonically increasing sequence and expiry;
- expected output/result contract;
- Core signature.

Bridge rejects unknown fields, operation names, expired jobs, stale sequences, wrong
device/generation, wrong release/protocol, invalid signature, absolute/out-of-scope
paths and reparse ancestors.

### 10.3 Replay and result

Bridge persists `job_id`, request digest and state before local mutation:

```text
received -> executing -> completed|unknown -> result_delivered
```

- same `job_id` and same request digest returns the persisted result;
- same `job_id` and different digest is a security conflict;
- interrupted read may be repeated;
- interrupted write becomes `UNKNOWN` until snapshot/current digest/readback
  reconciliation;
- a new generation cannot claim an old executing write automatically;
- Core stores the Bridge receipt before acknowledging the external effect.

Tailscale compromise without the device key cannot create a valid job. Device-key
theft triggers revocation, Tailscale grant removal, generation rotation, stop of local
writes and audit of all jobs since the last trusted heartbeat.

## 11. Composite health and owner status

### 11.1 Health schema

The content-free snapshot uses a versioned schema:

```json
{
  "schema": "nobus.composite-health.v2",
  "sampled_at": "<UTC>",
  "evidence": {
    "collector_id": "<pinned independent identity>",
    "boot_id": "<opaque>",
    "sample_sequence": 0,
    "previous_sample_digest": "<sha256|null>",
    "sample_digest": "<sha256>",
    "release_digest": "<sha256>",
    "config_digest": "<sha256>",
    "schema_set_digest": "<sha256>",
    "db_inventory_digest": "<sha256>",
    "db_transaction_epoch": 0,
    "probe_refs": ["<signed content-free evidence ref>"],
    "collector_signature": "<signature>"
  },
  "overall": "STARTING|HEALTHY|DEGRADED_LOCAL|DEGRADED_GOOGLE|FAIL_STOP",
  "ready": false,
  "release": {"commit": "", "artifact_sha256": "", "manifest_ok": true},
  "core": {"service_identity": "", "uptime_s": 0, "loop_fresh_s": 0},
  "poller": {
    "bot_identity_digest": "",
    "consumer_id": "",
    "generation": 0,
    "lease_fresh_s": 0,
    "last_poll_success_s": 0,
    "offset": 0,
    "singleton_proof": "ok|unknown|conflict"
  },
  "db": {
    "expected_count": 0,
    "healthy_count": 0,
    "schema_ok": true,
    "integrity_ok": true,
    "application_digest_ok": true,
    "wal_bytes": 0
  },
  "google": {"auth": "ok|stale|fail", "sentinel_age_s": 0},
  "bridge": {
    "expected": true,
    "device_id_digest": "",
    "generation": 0,
    "auth": "ok|offline|revoked|fail",
    "heartbeat_age_s": 0,
    "release_ok": true
  },
  "work": {
    "ready": 0,
    "running": 0,
    "dead_letter": 0,
    "orphan": 0,
    "unknown": 0,
    "unreconciled": 0
  },
  "recovery": {
    "last_backup_age_s": 0,
    "off_host_ok": true,
    "last_restore_drill_age_s": 0,
    "last_restore_rpo_s": 0,
    "last_restore_rto_s": 0
  },
  "clock_skew_s": 0
}
```

IDs are opaque/digested. No message text, document title, path, token, email, OAuth
subject or payload appears.

`overall`, `ready` and all precomputed booleans are display projections, never
PASS inputs. A separately supervised read-only evaluator with a pinned identity
reads the underlying signed/content-free poller lease, process, DB inventory and
transaction epoch, Gate 4 invariant counts, Google/Bridge probes and recovery
manifests, verifies their freshness and chain, and recomputes each pilot sample.
It does not call the aggregator's `overall` decision. Replayed sequence/boot ID,
broken sample chain, missing DB/probe, release/config/schema/inventory digest
drift or contradictory counts fail the sample closed. The external heartbeat
forwards the evidence-bound evaluator verdict; it cannot turn an aggregator
summary into proof.

### 11.2 Freshness and states

Pilot defaults:

| Signal | Fresh limit |
|---|---:|
| Whole snapshot | 120 seconds |
| Core event loop | 60 seconds |
| Poll lease and last successful long poll | 90 seconds |
| Google read-only sentinel | 10 minutes |
| Online Bridge heartbeat | 120 seconds |
| Off-host recovery point | 20 minutes for 15-minute RPO |
| Restore drill at pilot entry | 24 hours |
| Clock skew | 30 seconds |

State rules:

- `HEALTHY`: Core, poller, DB, Google and expected Bridge are fresh; zero orphan,
  unknown and unreconciled.
- `DEGRADED_LOCAL`: Bridge is offline/unavailable, but Core/poller/DB/Google remain
  safe. Local jobs wait within bounded TTL.
- `DEGRADED_GOOGLE`: Google is unavailable; Telegram/local read-safe work may
  continue, Google writes do not.
- `FAIL_STOP`: integrity/schema/digest/tenant/singleton/auth/reconciliation conflict,
  stale Core/poller, orphan effect, unrequested effect or unknown write.

Gate 8 PASS requires `HEALTHY`; degraded operation may be correct runtime behavior but
does not count as pilot healthy time except an approved offline-Bridge observation
window.

### 11.3 Owner status

The owner sees:

- exact release short ID/digest;
- Core and poller freshness/singleton;
- Google and Bridge state/last seen;
- DB and recovery state;
- running/queued/dead-letter/orphan/unknown counts and oldest eligible wait;
- last successful backup and restore drill;
- pilot elapsed healthy hours and reset reason;
- a safe incident code and next owner action.

## 12. Coordinated DB and external-effect write fence

The historical handoff reports four SQLite runtime databases; Gate 0 must verify the
actual runtime inventory. Separate SQLite databases cannot form one transaction, and
TARGET does not freeze their count. Preflight discovers every runtime DB from the
authoritative registry/config, reconciles it with SQLite files in the state directory,
and records an inventory digest. An omitted, duplicate
or unexpected runtime DB is a technical fail-stop. Gate 8 then applies one
application-wide maintenance fence to the complete discovered inventory.

### 12.1 Fence acquisition

1. Discover and reconcile the complete runtime DB inventory; pin its digest.
2. Acquire a generation-bound maintenance lease in the authoritative runtime state.
3. Stop Telegram admission after the current durable ingress boundary.
4. Stop new Google/Bridge/local effect dispatch.
5. Wait for read-only jobs or cancel them safely.
6. Let completed writes persist receipts; mark interrupted writes `UNKNOWN`.
7. Reconcile or block every executing/unknown effect.
8. Record the external-effect watermark and queue/outbox generations.
9. Checkpoint WAL as defined by the backup implementation.
10. Hold the fence until all inventoried DB backups and the set manifest complete.

If the fence expires or a writer generation changes, the backup set is invalid.

### 12.2 Backup set

Every DB in the pinned discovered inventory is copied through the SQLite online
backup API into a new immutable staging set. Discovery is repeated under the fence;
any inventory drift invalidates the set.
The set manifest records:

- backup epoch, maintenance generation, inventory count and inventory digest;
- every DB logical ID/path, discovery source, size and SHA-256;
- proof that no discovered DB was omitted and no unregistered SQLite file was accepted;
- schema/application digests and integrity results;
- release and contract digests;
- polling offset/lease generation;
- queue/outbox/effect watermarks;
- external-effect reconciliation watermark;
- backup start/end UTC;
- encryption/repository snapshot reference.

`integrity_check` does not replace `foreign_key_check`. A valid SQLite file with the
wrong schema/application digest fails.

### 12.3 Off-host restic

- restic encrypts before data leaves the Core host;
- repository credentials are scoped to the backup writer;
- repository password/recovery material is stored separately from the VPS and backup;
- recovery repository is outside the VPS/account failure domain;
- backend immutability/object lock is preferred;
- writer cannot prune protected generations;
- retention/prune uses a separate controlled identity;
- `restic check`, including data reads on a schedule, is evidence but not restore proof.

Proposed retention:

- 15-minute points for 48 hours;
- hourly for 14 days;
- daily for 35 days;
- weekly for 8 weeks;
- never longer than the applicable memory/data retention policy.

### 12.4 Portable restore drill

A passing drill:

1. selects a recovery point not pre-known to the restorer;
2. uses an isolated other Linux host/directory;
3. recovers the release artifact from the signed release source, not the backup DB;
4. restores every DB in the pinned manifest inventory and rejects missing/extra DBs;
5. verifies hashes, schemas, application digests, integrity and foreign keys;
6. re-enrolls/re-authorizes Core credentials for the isolated target identity through
   the recovery procedure; it never copies Windows/Bridge DPAPI blobs or private keys;
7. starts Core with Telegram/Google/Bridge external writes disabled;
8. runs read-only startup and reconciliation checks;
9. proves tenant isolation and owner status;
10. measures actual RPO and RTO;
11. revokes drill credentials and destroys the isolated copy according to retention
    policy.

Bridge recovery is separate: revoke the old device generation and re-enroll the target
Windows service identity. A DB that still treats an old identity-bound secret as an
active portable credential fails the drill even when SQLite integrity passes.

### 12.5 Recovery objectives and escalation

Design SLO candidates (not measured CURRENT facts and not Gate PASS evidence):

- Core DB RPO <= 15 minutes;
- Core DB RTO <= 60 minutes;
- total VPS-loss RTO <= 2 hours;
- release code RPO 0 and pointer rollback RTO <= 15 minutes;
- external-effect safety RPO 0 by failing closed on missing certainty;
- Bridge artifact RTO <= 30 minutes;
- local file recovery RTO <= 4 hours with a pre-write snapshot.

Portable-drill measurement and owner approval are mandatory before Gate 8 PASS. If
a measured candidate fails:

- do not lower the reported measurement;
- identify backup, bandwidth, secret-recovery or startup bottleneck;
- either improve the mechanism and repeat the drill or explicitly approve a less
  demanding business objective;
- keep Gate 8 implementation/pilot PASS blocked; architecture readiness is unchanged.

## 13. Migration protocol

No migration occurs unless its ID is in both the release manifest and the action-bound
L4.

Every migration specifies:

- source/target schema and application digests;
- affected DBs and records;
- whether old code can read the new schema;
- forward and rollback procedure;
- preconditions and invariant queries;
- worst-case duration/disk requirement;
- pre-migration recovery point;
- crash points and resume/abort semantics;
- post-migration health and reconciliation;
- whether any external effect may occur during the migration.

Protocol:

1. maintenance/effect fence;
2. verified pre-migration off-host recovery point;
3. exact source checks;
4. journal state `prepared`;
5. execute each exact step once with durable step receipt;
6. validate after each step;
7. journal state `committed`;
8. full DB/application health;
9. one candidate start with external writes still fenced;
10. release the fence only after composite PASS.

Migrations are offline for Gate 8. A migration must not start external effects. Partial,
unknown or unlisted migration is technical failure. PostgreSQL migration is not part
of Gate 8.

## 14. Error taxonomy

### 14.1 Procedural

Examples:

- wrong synthetic object ID entered by the operator;
- test step executed out of order;
- expected exact-prefix fixture not yet created;
- a smoke assertion uses the wrong documented test reference.

Conditions:

- artifact, configuration, schema and policy digests are unchanged;
- no trust, tenant, effect or recovery invariant failed;
- no external outcome is unknown.

The test input/procedure may be corrected on the same live Core/Bridge. Changing code,
dependency, configuration, unit/WinSW definition or manifest creates a new artifact
and restarts Gate 8 acceptance.

### 14.2 Technical

Includes:

- migration, schema, integrity or application-digest failure;
- service start, identity or manifest failure;
- stale/second poller or offset conflict;
- Bridge mTLS, device, replay or signature failure;
- tenant/scope/revision/digest mismatch;
- orphan, reconciliation or unrequested-effect failure;
- backup/restore corruption;
- technical health false-green.

Reaction: stop new admission/effects, stop candidate Core/Bridge as required, preserve
evidence, reconcile external outcomes and use the rollback decision tree. No automatic
retry.

### 14.3 Ambiguous

Includes:

- provider/Telegram/Bridge acceptance cannot be proven or disproven;
- two hosts may have used the current token;
- migration step completion is uncertain;
- recovery point and external-effect watermark disagree;
- failure cannot be safely classified.

Reaction: fail stop, preserve state and ask the owner. Neither retry nor data restore
is automatic.

## 15. Release and pilot sequence

### 15.1 Preflight before L4 action

- exact local commit/artifact/signature/manifest;
- target OS/Python/WinSW/Tailscale versions;
- hash-pinned offline dependencies and clean/accepted scans;
- exact Core/Bridge protocol compatibility;
- exact expected DB set and schema/application digests;
- exact migration list;
- current/previous releases;
- verified off-host recovery point and portable restore evidence;
- exclusive bot-token custody, no webhook, no server/manual/Windows second runner;
- Bridge device/certificate/generation and registry digests;
- Google/Telegram/Bridge synthetic scopes;
- disk, clock, network and independent alert path;
- rollback decision and operator contacts;
- accepted Gate 0–7 handoffs.

Read-only preflight produces evidence but changes nothing.

### 15.2 Action-bound Gate 8 sequence

1. Acquire maintenance/effect fence.
2. Create and verify pre-release backup set.
3. Transfer exact artifacts without Git remote/push.
4. Verify signatures/digests at targets.
5. Install into new immutable directories.
6. Apply only approved migration IDs, if any.
7. Set current/previous pointers while stopped.
8. Start one Core exactly once with autorestart disabled.
9. Prove fresh Core/DB/poller/Google health and singleton.
10. Start one Bridge exactly once with autorestart disabled.
11. Prove device, release and registry binding.
12. Run the exact synthetic smoke.
13. Perform exact-prefix cleanup from the created-object ledger.
14. Observe a stabilization window.
15. Start the 72-hour pilot clock.
16. Freeze evidence and evaluate PASS.
17. Only after PASS and separate L4 enable bounded supervision/autostart.

## 16. Rollback decision tree

```text
Failure detected
  |
  +-- Procedural, no invariant/effect uncertainty?
  |      -> correct procedure on unchanged live candidate -> repeat exact step
  |
  +-- Technical or ambiguous
         -> fence admission and all new effects
         -> preserve health/log/lease/migration/effect evidence
         -> any external write may have started?
                |
                +-- yes/unknown -> reconcile provider/Bridge/Telegram first
                |                 -> unresolved => owner decision; no data restore
                |
                +-- no -> continue
         -> schema/data changed?
                |
                +-- no -> stop candidate; switch code/Bridge pointer to previous
                |
                +-- yes -> previous code compatible with current data?
                              |
                              +-- yes -> code rollback, validate
                              |
                              +-- no -> restore exact pre-migration set only after
                                        effect watermark/reconciliation proof
         -> start previous Core once with effects fenced
         -> composite/read-only reconciliation
         -> owner-authorized resume
```

### 16.1 Code rollback

Code rollback selects the exact previous artifact. It does not modify DB or external
providers. It is safe only when schema/protocol compatibility is proven.

### 16.2 Data rollback

Data restore is allowed only when:

- the selected set is valid and portable;
- its release/schema compatibility is known;
- all effects after its watermark are reconciled;
- lost receipts become `UNKNOWN`, never replayable pending work;
- the exact restore is covered by L4.

### 16.3 Bridge rollback

Bridge artifact may roll back independently only if its device generation, job schema
and Core protocol remain compatible. An executing/unknown local write is reconciled
against snapshot/current digest/readback first.

### 16.4 Google and Telegram

- Code/data rollback never deletes or reverses Google objects automatically.
- A compensating update/delete is a new external effect with its own preview/L4.
- Telegram delivery with a missing receipt stays `UNKNOWN`; it is not resent.
- Polling offset is restored/reconciled with durable ingress dedupe; it is never moved
  backwards merely to “try again”.

## 17. Synthetic smoke matrix

All synthetic objects use the exact Gate 8 L4 scopes and prefix
`[NOBUS-MVP1-SMOKE]`. A created-object ledger records provider ID, type, scope,
creation receipt, expected cleanup operation and cleanup receipt.

| Gate | Positive smoke | Negative/failure smoke | Required evidence |
|---|---|---|---|
| 1 Natural Language/Voice | Natural text and confirmed voice reach same bounded intent | Ambiguous intent asks one clarification; unconfirmed voice cannot write | Intent/owner/source digests |
| 2 Scope/contracts | Allowed synthetic root/document selected exactly | Tenant mismatch, secret/deny path, reparse/unknown field rejected | Registry/contract digests |
| 3 Google Foundation | Auth/read sentinel and exact scoped read | Expired auth, wrong folder/list/calendar fail closed | Auth subject digest, read receipt |
| 4 Notes/Calendar/Tasks | Note flow; deterministic Calendar create/update; Task create/update/complete | Duplicate create, ETag/revision conflict, timeout/unknown reconciliation | Effect IDs and provider bindings |
| 5 Document Gateway/Bridge | Metadata search, bounded read, create, snapshot+CAS update, readback | PC offline, wrong device, stale sequence, replay, digest change | Job/result/snapshot receipts |
| 6 Multi-document Analytics | Bounded multi-source facts and deterministic calculations | Missing/conflicting sources remain explicit | Provenance and calculation evidence |
| 7 Artifact Factory | Telegram/JPEG/HTML/XLSX/DOCX/PDF and permitted Google/local writeback | Destination/payload drift, collision and revision mismatch stop | Artifact/destination/readback digests |

Additional Gate 8 fault smoke:

- second local poller denied;
- simulated stale polling lease fails readiness;
- Bridge disconnect produces `DEGRADED_LOCAL`, not global failure;
- backup set restores in isolation;
- previous code pointer validates without external effects;
- interrupted external call becomes `UNKNOWN`;
- orphan audit returns zero.

### Cleanup

Cleanup may delete only objects that:

- are in the approved synthetic scopes;
- have an ID in the created-object ledger;
- retain the exact prefix;
- have the expected current revision/digest.

Missing prefix, unknown ID, changed revision or non-synthetic dependency stops cleanup
for owner review. Broad folder/calendar/tasklist cleanup is forbidden. Cleanup receipts
are part of PASS evidence.

## 18. 72-hour pilot

### 18.1 Observation windows

1. **Preflight freshness:** 10 continuous minutes before one-start.
2. **Natural smoke:** complete Gate 1–7 matrix.
3. **Stabilization:** 6 continuous healthy hours after smoke/cleanup.
4. **Pilot:** 72 continuous hours on the same artifact/config/schema/policy digests.
5. **Evidence freeze:** one hour to collect/check evidence without changing runtime.

Any code, dependency, configuration, service definition, manifest, schema or policy
change resets acceptance and the pilot clock. A procedural correction that changes
only synthetic input/step ordering does not reset the clock before the pilot begins.
No procedural correction is permitted to disguise an incident during the 72-hour
window.

### 18.2 Pilot SLOs

| Objective | PASS threshold |
|---|---|
| Poller singleton | 100% of samples; zero conflict/second owner |
| Core/poller freshness | No unplanned stale interval over 120 seconds |
| Composite healthy time | >= 99.5%, excluding exact approved offline-Bridge window |
| Ingress acknowledgement | p95 <= 30 seconds; worker completion excluded |
| Bridge online heartbeat | >= 99% while PC is scheduled online |
| Offline classification | 100% `DEGRADED_LOCAL`; Google/Telegram continue |
| Google read sentinel | >= 99%; no blind write retry |
| Backup recovery points | 100% schedule; gap never exceeds approved RPO |
| Alert detection | <= 2 minutes for stale Core/poller |
| Owner notification | <= 5 minutes through an independent channel |
| Provider/local/Google orphan, duplicate or unrequested effect | Exactly 0 |
| Observed duplicate Telegram notification | Exactly 0; possible/owner-authorized resend is reported separately |
| Unreconciled provider or delivery `UNKNOWN` | Exactly 0 at PASS; no blind resend |
| Dead letters | 0 unexplained; every injected one reconciled |

These thresholds do not claim a long-term 99.9% SLA from a 72-hour sample.

### 18.3 Alerts

Immediate fail-stop/owner alert:

- second poller/split brain;
- integrity/schema/manifest mismatch;
- stale Core/poller;
- device auth/replay/key-revocation event;
- orphan, unrequested effect or unreconciled unknown;
- backup RPO breach or corrupt recovery point;
- disk/clock condition threatening correctness.

Warning/degraded:

- Bridge offline;
- Google read sentinel failure;
- queue pressure/dead letter;
- approaching backup/disk/WAL threshold.

Telegram cannot be the sole alert path. At least one email/push/managed heartbeat
channel is external to Core.

### 18.4 PASS evidence bundle

The bundle contains only metadata/evidence:

- Core/Bridge manifests, signatures and artifact digests;
- current/previous pointer evidence;
- systemd/WinSW configuration digests;
- singleton/token-custody proof;
- device certificate fingerprint/generation and grant digest;
- health samples and SLO calculation;
- queue/effect/reconciliation summaries;
- smoke created-object/cleanup ledger;
- backup/restic snapshot and portable restore evidence;
- measured RPO/RTO;
- incident/error classification log;
- L1/L2/L3 records and owner L4 references.

No secret, raw prompt, message, document content, absolute owner path or credential is
included.

## 19. Minimal observability

### 19.1 Logs

Required fields:

- UTC timestamp, severity and stable event code;
- release/component/version;
- correlation, update, task, effect, job and lease generation IDs in opaque/digested
  form;
- tenant/project scope as opaque IDs;
- phase, state transition, result class and duration;
- safe dependency/error class;
- evidence digest where applicable.

Forbidden:

- message/document content;
- prompt/transcript;
- token/cookie/credential;
- email or raw Google identity;
- absolute Windows owner path;
- secret scan finding value;
- exception text containing payload/path/secrets.

### 19.2 Metrics

Only bounded-cardinality metrics:

- health state and freshness ages;
- polling lease/offset progress and conflict count;
- queue counts/claim latency/dead letters;
- effect states and reconciliation age;
- Bridge heartbeat/replay/rejection counts;
- DB/WAL/disk sizes and integrity result;
- backup age/duration/bytes and restore RPO/RTO;
- external-call latency/result class.

No tenant, filename, document ID or error text becomes an unbounded label.

### 19.3 Traces

Distributed tracing is deferred. If later required, traces contain correlation and
state-transition metadata only and use OpenTelemetry APIs without granting the
collector payload access.

## 20. Security, permissions and secret lifecycle

### 20.1 Least privilege

- Core release dirs are immutable/read-only to the service.
- Core writes only state/cache paths.
- Bridge writes only approved registry roots through closed operations.
- No open filesystem share or arbitrary endpoint.
- Firewall/Tailscale grants expose only the private Core/Bridge application endpoint.
- Every external write remains owner/policy/L4 bound by canonical rules.

### 20.2 Secret storage and recovery

- secrets never reside in release artifact, manifest, unit/WinSW XML, Git or logs;
- Core receives separate Telegram, Google, Bridge CA and backup credentials;
- Bridge receives only its device private key/certificate;
- backup repository secret is not stored inside the same recovery repository;
- recovery material has an independently tested owner-approved procedure;
- secret rotation increments related credential/device generations;
- suspected bot-token copy requires token rotation before polling resumes;
- suspected Bridge key theft revokes the certificate and active device generation.

### 20.3 Patch/update procedure

1. Refresh upstream security/release evidence.
2. Update exact dependency/binary pins.
3. Rebuild wheelhouse/artifact.
4. Regenerate SBOM and scans.
5. Run full regression and protocol compatibility.
6. Produce new manifest/signature.
7. Re-run Gate 8 preflight and action-bound approval.

No in-place `pip install`, WinSW replacement, OS package drift or Bridge self-update is
permitted.

## 21. Code and operations impact map

### 21.1 Reuse

- SQLite schema/application digest and online backup primitives;
- durable Telegram admission, offset checkpoint and generation leases;
- durable queue, outbox and receipt state machines;
- a migration adapter for the legacy product-effect
  `pending/executing/completed/unknown/delivered` vocabulary only; TARGET persists
  exclusively the Gate 4 lifecycle, provider-outcome and delivery axes;
- startup probe and read-only sentinel concepts;
- exact owner/tenant/revision/digest bindings;
- existing restore journal/write-through replacement patterns;
- Gate 1–7 contracts and negative tests.

### 21.2 Add

- release manifest/signature verifier;
- systemd entrypoint/preflight and safe exit-class mapping;
- Linux process lock and polling ownership health;
- global bot-token custody/rotation runbook;
- composite health/status schema;
- maintenance/effect fence and backup-set manifest;
- restic integration and portable restore verifier;
- Bridge protocol, mTLS enrollment, active-device registry and local journal;
- pilot recorder/SLO/evidence bundle;
- failure classifier and rollback planner.

### 21.3 Modify/adapt

- identity-bound secret handling: exclude DPAPI blobs/keys from transfer, revoke old bindings and re-enroll Core/Bridge separately;
- health to include freshness, external dependencies, effect certainty and recovery;
- backup/restore from the handoff-reported four-DB layout (`UNVERIFIED` until
  fresh Gate 0 inventory) to a dynamically inventoried coordinated off-host set;
- runner startup from Scheduler assumptions to service-neutral ownership;
- reconciliation to cover release/restore watermarks and Bridge jobs;
- operator status to distinguish `DEGRADED_LOCAL` from Core failure.

### 21.4 Deprecate for target

- Task Scheduler as normal Core/Bridge supervisor;
- current-user service identity;
- local-only backup as production recovery;
- process-only singleton claims;
- health green based only on process/DB;
- automatic retry of ambiguous external writes;
- deployment that installs from the internet;
- code-only rollback language.

Deprecation does not delete CURRENT fallback before Gate 8 acceptance and explicit
transition approval.

## 22. Gate 0–7 design handoffs and execution prerequisites

| Gate | Required handoff to Gate 8 |
|---|---|
| 0 Product baseline | Accepted product boundary, owner identity, non-goals and canonical digest |
| 1 Natural Language/Voice | Golden corpus, direct/confirmed-effect policy, ambiguity behavior and voice source binding |
| 2 Scope/contracts | Versioned registries, deny digests, tenant isolation, strict wire schemas and migration rules |
| 3 Google Foundation | Exact OAuth subject/scopes, provider health, idempotency/reconciliation and test IDs |
| 4 Notes/Calendar/Tasks | Durable effect admission, object bindings, revision/ETag rules, unknown handling and cleanup receipts |
| 5 Document Gateway/Bridge | Closed Bridge operations, registry roots, device enrollment/replay/offline tests and protocol version |
| 6 Analytics | Bounded extraction, provenance, deterministic calculation and conflict evidence |
| 7 Artifact/writeback | Renderer/output parity, destination/payload/revision binding, atomic/readback and rollback tests |

The corresponding `docs/gates` research and architecture documents supply the TARGET
design handoffs and are sufficient prerequisites for architecture readiness. Before
Gate 8 execution/PASS, every gate must additionally supply:

- exact accepted commit/artifact/contract digests;
- L1/L2/L3 VerificationBundle;
- zero unresolved technical/ambiguous blocker;
- no orphan `PENDING`;
- exact synthetic fixtures and cleanup contract;
- CURRENT capability evidence rather than TARGET prose alone.

## 23. Implementation slices

Each slice is independently reviewed and cannot claim runtime readiness from
documentation alone.

1. **Release contracts:** manifest/schema, artifact layout, verifier and pointer tests.
2. **Linux Core packaging:** offline wheelhouse/venv, entrypoint and systemd hardening.
3. **Global poller fence:** token custody, process lock, durable ownership and
   split-brain tests.
4. **Composite health:** schema, freshness, degraded/fail rules and owner status.
5. **Coordinated recovery:** maintenance/effect fence, backup-set manifest, restic and
   portable restore.
6. **Identity-local credentials:** revoke old bindings and re-enroll/re-authorize separate Core and Bridge identities; copy no DPAPI blob/private key.
7. **Bridge identity/protocol:** WinSW packaging, mTLS enrollment, signed jobs and
   replay/result journal.
8. **Migration/rollback:** migration journal, compatibility and external-effect-aware
   decision tree.
9. **Smoke automation:** Gate 1–7 matrix, exact-prefix ledger and cleanup.
10. **Pilot/evidence:** SLO sampler, independent alerts and VerificationBundle.
11. **Supervision activation:** post-pilot bounded restart/autostart under new L4.

## 24. Acceptance and Definition of Done

### 24.1 TARGET architecture DoD — satisfied

The design is `ARCHITECTURE READY` when:

- accepted root decisions are normative and internally consistent;
- CURRENT, TARGET, implementation/pilot and Gate PASS are explicitly separated;
- topology, authority, release, dynamic DB inventory, credential re-enrollment,
  health, backup, migration, rollback, smoke and pilot contracts are complete;
- Gate 0–7 design handoffs are represented by the corresponding `docs/gates` set;
- document-level L1/L2/L3 pass and no runtime execution is claimed.

These design conditions are satisfied by this revision.

### 24.2 Gate 8 implementation/pilot PASS DoD — not yet satisfied

Gate 8 may claim PASS only when:

- exact Core and Bridge artifacts verify offline;
- service identities/ACLs pass negative tests;
- one current bot token exists only in the active server credential boundary and
  Bridge has no copy;
- one poller remains true under restart, second-process and other-host tests;
- one device is active; stolen/stale device generations fail closed;
- Core remains safe when Bridge/Google is offline;
- composite health never reports false ready for injected failures;
- every dynamically discovered runtime DB is backed up under one fence and manifest;
- encrypted off-host data restore succeeds elsewhere, target credentials are
  re-enrolled, and measured RPO/RTO are owner-approved;
- partial migration/power-loss tests recover deterministically;
- rollback reconciles committed external effects;
- Gate 0–7 implementation VerificationBundles and all required smoke pass;
- exact-prefix cleanup is proven;
- 72-hour SLOs pass on unchanged artifacts;
- no orphan, duplicate, unrequested or unreconciled effect remains;
- full execution L1/L2/L3 evidence exists;
- owner provides exact action-bound L4 and separately approves post-pilot supervision.

## 25. Owner approvals required before execution/PASS

The root architecture decisions are accepted: SQLite MVP-1 default, dynamic DB
inventory, identity-local credential re-enrollment, server-only Telegram token custody
and RPO/RTO as candidate SLOs. They are not open design conflicts.

The following approvals remain execution gates, not architecture blockers:

1. approve or revise measured Core DB and VPS-loss RPO/RTO after the portable drill;
2. approve backup retention and the exact off-host provider/account boundary;
3. approve BotFather rotation for any cutover where old-host custody is uncertain;
4. approve the independent alert channel and its content-free data boundary;
5. issue exact action-bound L4 for each release/migration/restore/pilot action;
6. after pilot PASS, separately approve bounded restart/autostart policy.

## 26. Verification

### 26.1 L1 — document, contracts, links and secrets

Required deterministic checks:

- exactly `RESEARCH.md` and `ARCHITECTURE.md` exist in this Gate 8 directory;
- both identify baseline and separate CURRENT, TARGET architecture,
  implementation/pilot and Gate PASS;
- every required architecture topic has a heading/contract;
- all relative repository links resolve;
- external links use official/primary sources in the research dossier;
- examples contain placeholders only;
- secret-pattern scan finds no token, credential, cookie, private key, host secret or
  customer payload;
- document contains ARCHITECTURE READY but no claim that implementation,
  deployment, backup, restore, pilot or Gate 8 PASS was executed.

### 26.2 L2 — disaster and release semantics walkthrough

The architecture must reproduce these outcomes:

1. **Total VPS loss:** retrieve signed artifact, restore encrypted snapshot elsewhere,
   re-enroll target Core credentials independently, rotate uncertain bot token,
   start read-only,
   reconcile and measure RPO/RTO.
2. **Corrupt newest backup:** repository/integrity check rejects it, selects the newest
   older valid point, reports the real RPO gap and keeps Gate 8 PASS blocked if target
   is exceeded.
3. **Partial migration:** maintenance fence stays held; durable step receipts decide
   resume versus pre-migration restore; no external effect has started.
4. **External effect before code failure:** receipt/provider readback reconciles the
   effect; code rollback does not restore DB past the effect watermark.
5. **Bridge write interrupted:** snapshot/current digest/result journal determine
   applied/not-applied/unknown; no blind job replay.
6. **Previous release start:** schema/protocol compatibility is proven before pointer
   switch; external writes stay fenced until composite health/reconciliation passes.

### 26.3 L3 — adversarial scenarios

| Scenario | Mandatory result |
|---|---|
| Second poller on another host | Both stop; token custody investigated/rotated; no automatic election |
| Split brain with two valid-looking leases | Global credential fence dominates; fail stop and reconcile |
| Stale self-reported health | Freshness expires; independent monitor alerts; ready becomes false |
| Backup corruption | Set rejected; older point measured; no “backup succeeded” claim |
| Restore on another machine | All inventoried DBs restore; identity-bound secrets are re-enrolled, never copied |
| Partial migration/power loss | Journal and pre-migration set give one deterministic path |
| External effect immediately before rollback | Provider/receipt reconciliation precedes data rollback |
| Bridge private-key theft | Revoke certificate/grant, increment generation, audit jobs, no new writes |
| Tailscale account/peer compromise | mTLS/job signature still blocks application authority |
| Windows/VPS power loss | Durable leases expire by generation; writes become reconciled or unknown |
| Procedural smoke error | Correct test input on unchanged live artifact; no false rollback |
| Ambiguous failure | Stop and owner decision; neither retry nor restore is automatic |

## 27. Decision summary and status

Normative Gate 8 root decisions:

- systemd + immutable native Python release/venv;
- WinSW 2.12.0 under a separate Windows identity;
- Tailscale grants plus device-bound application mTLS and job fencing;
- single-node SQLite is the MVP-1 default; PostgreSQL requires a measured post-pilot
  multi-writer, throughput or HA trigger; network SQLite is prohibited;
- the historical handoff reports four runtime DBs (`UNVERIFIED`); fresh Gate 0
  inventory is required before any CURRENT claim, while TARGET dynamically
  inventories and fences every discovered runtime DB instead of trusting a fixed list;
- DPAPI blobs/private keys are not copied; Core and Bridge credentials are distinct and
  re-enrolled/re-authorized on each target identity;
- the Telegram bot token exists only in one server-side credential boundary; Bridge
  never receives it; lease/generation/dedupe provide runtime fencing;
- encrypted off-host restic and portable data restore;
- RPO/RTO values are design SLO candidates until measured and owner-approved;
- one Core, one globally fenced poller and one authorized active Bridge;
- composite fresh readiness and `UNKNOWN -> reconcile`, never blind retry;
- effect-aware rollback;
- no Kubernetes, active HA, second poller, network filesystem or automatic PostgreSQL
  migration.

Resolved design conflicts:

- the generic PostgreSQL production statement is specialized/replaced for Nobus MVP-1;
- older three-DB wording cannot override discovered CURRENT/runtime inventory;
- DPAPI portability is replaced by revocation and target-identity re-enrollment;
- token custody is assigned exclusively to the server credential boundary;
- proposed RPO/RTO are explicitly separated from measured evidence;
- Gate 0–7 design documents are handoff prerequisites, while their implementation
  evidence belongs to Gate execution/PASS.

Open execution/PASS blockers:

- prerequisite Gate 0–7 implementations and VerificationBundles;
- production Core/Bridge artifacts, identities, fences and exact release manifest;
- off-host backup and another-host restore with measured/approved RPO/RTO;
- action-bound L4, full natural smoke, cleanup/reconciliation evidence;
- unchanged 72-hour pilot and separate approval for post-pilot supervision.

**Architecture verdict: ARCHITECTURE READY.** Document-level L1/L2/L3 design checks
pass after this root rework.

**Gate verdict: GATE 8 IMPLEMENTATION/PILOT BLOCKED.** No deployment, runtime smoke,
restore drill, 72-hour pilot or Gate 8 PASS is claimed by this document.