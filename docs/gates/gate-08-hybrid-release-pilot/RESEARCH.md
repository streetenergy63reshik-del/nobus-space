# Gate 8 — Hybrid Release and 72-hour Pilot Research Dossier

**Document status:** RESEARCH READY
**Architecture status:** RESEARCH READY; TARGET design accepted for architecture
**Gate execution status:** IMPLEMENTATION/PILOT BLOCKED; not deployed and no Gate 8 PASS
**Canonical baseline:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Evidence cut-off:** 2026-07-28
**Scope:** Server Core release, Windows Local Library Bridge release, health, backup,
restore, migration, rollback, reconciliation and 72-hour pilot
**Authority:** supporting Gate 8 research. In a conflict, `AGENTS.md`, accepted ADRs
and canonical documents 01–12 have priority.

## 1. Research question and constraints

Gate 8 must release one exact Server Core artifact and one exact Windows Bridge
artifact without introducing cyclic private fixes. Recovery must be predictable after
a process failure, host loss, interrupted migration, ambiguous external write or
compromised device.

This dossier compares production-capable but proportionate approaches under these
fixed constraints:

- one Linux Server Core;
- one globally fenced Telegram polling consumer;
- one authorized Windows Bridge;
- no Git remote/push or Git checkout on a production host;
- immutable releases with explicit current and previous pointers;
- single-node SQLite remains the MVP-1 default; PostgreSQL is considered only after
  the pilot on a measured multi-writer, throughput or HA trigger;
- no Kubernetes, active/active Core, second poller or network filesystem;
- Windows Bridge is not a Telegram runner and never receives Google credentials;
- `unknown -> reconcile`; an unknown external effect is never repeated blindly;
- backup success is not restore evidence;
- code rollback does not reverse an already committed Google, Telegram or local-file
  effect.

Phase 1 and this documentation phase performed no SSH, deployment, service,
Scheduler, Bridge, tunnel, backup, migration or runtime action.

## 2. Executive verdict

The recommended Gate 8 stack is:

> Linux `systemd` + immutable native Python release/venv; WinSW 2.12.0 under a
> separate Windows identity; Tailscale grants as network overlay plus
> application-level device-bound mTLS and signed job fencing; the current SQLite
> database set protected by a coordinated write fence, SQLite online backup API and
> encrypted off-host restic snapshots.

This stack is selected because it:

- reuses the existing Python/SQLite runtime and durable effect vocabulary;
- has the fewest new stateful components;
- supports exact local artifacts without a registry or Git remote;
- provides native Linux and Windows service management;
- permits code rollback in minutes while keeping data/effect rollback explicit;
- keeps a future move to containers or PostgreSQL possible without making it part of
  the MVP release.

### Adopt

- distro-supported systemd and journald;
- disposable per-release Python venv recreated from a hash-pinned wheelhouse;
- WinSW `2.12.0` as the stable Windows SCM wrapper;
- Tailscale grants for private reachability;
- application mTLS, device identity, job signatures, nonces and sequence fencing;
- SQLite WAL and online backup API;
- restic `0.19.1` for client-side encrypted off-host snapshots;
- structured content-free logs and a small independent heartbeat service.

### Adapt from the repository

- Windows runner mutex and SQLite polling lease into a cross-release single-consumer
  contract;
- exact schema/application-digest health into composite fresh readiness;
- CURRENT four-DB backup/restore tooling into a dynamically inventoried,
  application-wide write-fenced backup set that cannot omit a discovered runtime DB;
- durable queue, outbox, product-effect and `UNKNOWN` reconciliation semantics;
- existing startup sentinel and health evidence into a release-bound status snapshot.

### Build only the missing domain layer

- release manifest, artifact verifier and preflight;
- Core composite health and owner status;
- Bridge enrollment, device identity and closed signed job protocol;
- Bridge result/dedupe journal;
- cross-database backup epoch/write fence;
- release/effect reconciliation and pilot evidence bundle.

## 3. Evidence from CURRENT

At the baseline commit, CURRENT is a local Windows runtime, not the target hybrid
release.

| Area | CURRENT evidence | Gate 8 gap |
|---|---|---|
| Supervision | Task Scheduler with `IgnoreNew`, health task and bounded restarts | No server service, production identity or pilot sequence |
| Telegram singleton | Windows mutex plus generation-bound SQLite polling lease | No proof against a process on another host holding the same bot token |
| Runtime state | Four SQLite runtime databases with WAL, DDL and application digests | No coordinated off-host recovery point or portable Linux restore |
| Health | Exact discovered four-DB CURRENT inventory plus integrity/digest checks | No Core/Google/Bridge/version/poll-freshness/backup freshness composite |
| Backup | SQLite backup API under a mutex, hashes and authenticated manifest | Backup files are not a proven encrypted off-host portable restore |
| Restore | Staging, journal, write-through replacement and startup rollback | Current-user DPAPI identity is not portable to a Linux service/new Windows identity |
| Queue/effects | Durable admission, generation leases, outbox receipts and `UNKNOWN` | Telegram delivery retains a narrow at-least-once crash window |
| Bridge | TARGET contract in ADR 0017 | No production Bridge implementation or service evidence |
| Release | Exact local commit required by Gate 8 L4 | No artifact manifest, current/previous topology or release runner |

Relevant repository evidence:

- `ops/windows/Install-NobusSpaceBot.ps1`;
- `scripts/check_telegram_health.py`;
- `scripts/backup_telegram_runtime.py`;
- `scripts/restore_telegram_runtime.py`;
- `src/application/runtime_maintenance.py`;
- `src/application/durable_runtime.py`;
- `src/application/product_effects.py`;
- `src/transport/telegram/bot_api.py`;
- `src/transport/telegram/durable_telegram_state.py`;
- `src/transport/telegram/sqlite_store.py`;
- associated health, backup, queue, polling, effect and reconciliation tests.

## 4. Systemic failure map

| Failure | False local fix | Required systemic control |
|---|---|---|
| A second poller starts on another host | Add another local mutex | Exclusive bot-token custody; token rotation at host cutover; startup inventory and runtime lease |
| Polling lease expires during a handler | Increase lease forever | Durable ingress and `update_id` dedupe before offset advance; generation CAS |
| Telegram accepts a send but receipt is lost | Retry send | Persist `UNKNOWN`, stop replay and reconcile/ask owner |
| Core fails after Google/Bridge write | Switch `current` back | Freeze dispatch, reconcile provider/local effect, then decide code/data rollback |
| Backup command exits zero | Mark recovery green | Restore elsewhere, run integrity/application checks and start the exact release |
| Tailscale peer is reachable | Treat peer as authorized Bridge | Device-bound mTLS, active device generation, job signature/nonce/sequence |
| Bridge PC is offline | Mark all Core unready | `DEGRADED_LOCAL`; Telegram and Google continue |
| Supervisor restart loop | Raise restart count | Technical exit circuit breaker; no autorestart during acceptance |
| Partial schema migration | Re-run migration | Migration journal, exact step list, compatibility check and pre-migration restore point |
| DB restore loses recent receipts | Replay pending effects | Convert missing certainty to `UNKNOWN`; safety fails closed |
| Health process is alive | Report ready | Fresh composite sample plus an external sentinel |
| DPAPI blobs/keys are copied across identities | Treat integrity as secret portability | Exclude identity-bound secrets; revoke and re-enroll/re-authorize on each target identity |
| Disk fills and WAL grows | Restart SQLite | Capacity thresholds, checkpoint policy and off-host recovery evidence |
| Clock moves backwards | Extend TTL | UTC evidence plus monotonic elapsed time and skew alarm |

## 5. Candidate deployment and operations stacks

Versions are evidence snapshots, not permanent pins. The release manifest must use
the exact versions actually approved and installed.

### 5.1 Stack A — native systemd/venv + WinSW + SQLite/restic

| Dimension | Assessment |
|---|---|
| Server | systemd service, native Python, offline wheelhouse, per-release venv |
| Windows | WinSW 2.12.0, separate local service identity |
| Network | Tailscale grants, application mTLS and outbound Bridge pull |
| Storage | Existing SQLite database set, coordinated snapshots, restic off-host |
| Maturity | High; standard OS service and backup primitives |
| License | systemd GPL/LGPL; WinSW MIT; restic BSD-2-Clause |
| Cost | OSS license cost $0; network/backup provider cost depends on plan/storage |
| Operations | Low–medium; no container engine or database server |
| Code reduction | High: OS owns supervision/logging; restic owns encryption/dedup |
| Lock-in | Low; artifact is Python/wheels, storage is SQLite files |
| RPO/RTO candidate | Core data RPO <= 15 min; RTO <= 60 min only if measured and owner-approved |
| Failure/fallback | Recreate venv from wheelhouse; switch to previous artifact |
| Verdict | **ADOPT for MVP-1** |

### 5.2 Stack B — Docker Compose + PostgreSQL

| Dimension | Assessment |
|---|---|
| Server | Docker Engine/Compose, Core image and PostgreSQL |
| Windows/network | Same WinSW/Tailscale/mTLS contract |
| Maturity | High and broadly supported |
| License | Compose Apache-2.0; PostgreSQL License |
| Cost | OSS license cost $0, but more RAM, patching and backup operations |
| Operations | Medium–high: engine, image lifecycle, database, WAL/PITR |
| Code reduction | Image reduces host variance; Postgres can centralize leases |
| Lock-in | Medium; image build/registry conventions and DB operational coupling |
| RPO/RTO potential | RPO minutes with archived WAL; RTO 45–90 min after drills |
| Failure/fallback | Previous image digest and verified base backup/WAL chain |
| Verdict | **ADAPT later only after measured need** |

The stack is not selected for Gate 8 because containerization and a database migration
would change too many failure surfaces simultaneously. PostgreSQL becomes justified
only by measured write contention, a second legitimate writer, approved PITR/HA
requirements or inability to meet the approved SQLite RPO/RTO.

### 5.3 Stack C — Podman Quadlet + SQLite/Litestream

| Dimension | Assessment |
|---|---|
| Server | Podman 5.8.2, Quadlet-generated systemd units, rootless where practical |
| Windows/network | WinSW plus WireGuard or Tailscale |
| Storage | SQLite plus Litestream 0.5.15 continuous replication |
| Maturity | High upstream maturity; more Linux storage/cgroup/SELinux detail |
| License | Podman and Litestream Apache-2.0 |
| Cost | OSS license cost $0; object storage and operator time remain |
| Operations | Medium: container storage, generator, image and replication lifecycle |
| Code reduction | OCI packaging reduces host variance |
| Lock-in | Medium to OCI/Podman/Quadlet conventions |
| RPO/RTO potential | RPO minutes, RTO 30–60 min after proof |
| Failure/fallback | Native systemd release and standard SQLite snapshot |
| Verdict | **Reserve fallback, not pilot default** |

Podman 5.8.1 fixed a partial internal BoltDB-to-SQLite migration associated with
Quadlet that could not be recovered automatically. This does not reject Podman, but it
demonstrates that an additional runtime has its own state and migration failures.

### 5.4 Process-supervision alternatives

| Candidate | Conclusion |
|---|---|
| supervisord 4.3.0 | Mature but duplicates systemd process, logging and boot controls; reject on a systemd VPS |
| NSSM | Functional Windows wrapper; retain only as emergency fallback to WinSW |
| Native Python Windows Service | Reject: custom SCM lifecycle code without product value |
| Task Scheduler | Keep only as CURRENT/manual rollback fallback during transition; not target Bridge supervisor |
| Kubernetes | Reject: no scale/HA need and directly conflicts with a single polling consumer |

## 6. Server runtime findings

systemd is the preferred service boundary because it already owns boot ordering,
process groups, restart budgeting, identities, filesystem restrictions and journald.
The target uses the distro-supported systemd package; upstream `260.2` was the current
release observed at the evidence cut-off.

The artifact must not contain or move an existing venv. Python documents venvs as
disposable and inherently non-portable because installed scripts contain absolute
paths. Each release recreates its venv at the final release path from an offline,
hash-pinned wheelhouse.

Required server principles:

- static unprivileged `nobus-core` identity; no login shell or sudo;
- release code read-only to the service;
- writable state limited to `/var/lib/nobus`;
- secrets outside releases and outside the manifest;
- no Git metadata or network package installation during deployment;
- `Restart=no` for acceptance; a bounded `on-failure` policy only after pilot PASS;
- technical/corruption exit classes are restart-preventing;
- previous artifact stays complete and verified.

Sources:

- [systemd upstream and releases](https://github.com/systemd/systemd)
- [Python venv](https://docs.python.org/3/library/venv.html)
- [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/)

## 7. Windows Bridge supervision findings

Microsoft distinguishes SCM services for long-running daemons from scheduled
one-shot/event work. WinSW is therefore a better target than Task Scheduler.

WinSW `2.12.0` is the latest stable 2.x release observed; WinSW 3.x remains
pre-release. The age of 2.12.0 is a patch-management risk, so its executable digest,
upstream security state and Windows compatibility must be rechecked at every release.

The Bridge identity must:

- be a dedicated non-interactive local account;
- have `Log on as a service`;
- have explicit ACL only to the Bridge state and approved registry roots;
- have no Telegram/Google/server release credentials;
- own a non-exportable device private key where the Windows certificate provider
  supports it;
- store DPAPI/Credential Manager material under this final identity, not the current
  interactive owner identity.

Autostart and automatic restart remain disabled through the 72-hour pilot. They are
enabled only by a separate post-pilot L4.

Sources:

- [WinSW repository](https://github.com/winsw/winsw)
- [WinSW releases](https://github.com/winsw/winsw/releases)
- [Microsoft Windows services](https://learn.microsoft.com/en-us/windows/win32/services/about-services)
- [Service user accounts](https://learn.microsoft.com/en-us/windows/win32/services/service-user-accounts)
- [DPAPI `CryptProtectData`](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

## 8. Secure network findings

Tailscale is recommended for the pilot because it reduces firewall, NAT and Windows
reachability work. Its grants/ACL layer is deny-by-default and suitable for limiting
Core-to-Bridge reachability. It is not application authentication.

The application still needs:

- a dedicated Core CA/trust anchor;
- one active Bridge device certificate and generation;
- mutual TLS;
- signed jobs bound to device, tenant, capability, artifact version and expiry;
- monotonic job sequence plus nonce;
- a Bridge-side dedupe/result journal;
- revocation and re-enrollment after key theft;
- outbound Bridge pull; no Windows listener, SMB or shared filesystem.

WireGuard is the low-control-plane-lock-in fallback. It moves key rotation, route,
AllowedIPs and firewall recovery to Nobus operations and is therefore not selected for
the pilot.

Sources:

- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale ACLs](https://tailscale.com/docs/features/access-control/acls)
- [Tailscale pricing](https://tailscale.com/pricing)
- [WireGuard cryptokey routing](https://www.wireguard.com/)

## 9. SQLite, backup and restore findings

SQLite remains suitable for one Core with a single main writer and is the normative
MVP-1 default. WAL permits concurrent readers and a writer, but only one writer exists
at a time. PostgreSQL is evaluated only after the pilot when measurements prove a
multi-writer, throughput or HA need. SQLite on a network filesystem is never a
migration or HA strategy.

The SQLite online backup API produces a transactionally consistent snapshot of one
database while it is in use. The historical handoff reports four runtime databases, but this is UNVERIFIED until fresh Gate 0 runtime evidence. TARGET does not
silently hard-code that count: preflight discovers every runtime SQLite DB from the
authoritative runtime registry/config and reconciles it with the state directory.
Consistency of the discovered set requires an application-wide write/effect fence
around all individual backups.

Validation must include:

- discovered runtime DB inventory, its count and digest, with omissions and unexpected
  SQLite files failing closed;
- exact DDL/application digests for every inventoried DB;
- `PRAGMA quick_check` or full `integrity_check`;
- a separate `PRAGMA foreign_key_check`;
- backup epoch and external-effect watermark;
- hash and size for each DB and the manifest;
- restore and application startup on another host.

restic is selected over raw rclone because restic provides encrypted,
content-addressed snapshots, retention and repository checking. rclone remains only a
transport primitive. Borg is a valid SSH-only backup alternative but still requires a
consistent SQLite snapshot first.

Litestream can reduce SQLite RPO if measurement proves the 15-minute snapshot target
insufficient. Litestream 0.5.x no longer supplies the former Age encryption path, so
backend encryption and a separate immutable recovery copy are required. It does not
replace restore drills.

Sources:

- [SQLite WAL](https://www.sqlite.org/wal.html)
- [SQLite online backup](https://www.sqlite.org/backup.html)
- [SQLite PRAGMA checks](https://www.sqlite.org/pragma.html)
- [restic 0.19.1 documentation](https://restic.readthedocs.io/en/stable/)
- [Litestream releases](https://github.com/benbjohnson/litestream/releases)
- [Litestream restore and PITR](https://litestream.io/reference/restore/)
- [Borg documentation](https://borgbackup.readthedocs.io/en/stable/)
- [rclone crypt](https://rclone.org/crypt/)

## 10. Telegram single-consumer and reconciliation findings

Telegram `getUpdates` confirms an update when a later offset is supplied and can return
unconfirmed updates again. Long polling and webhook delivery are mutually exclusive.
The application must therefore have exactly one component calling `getUpdates`.

The global fence is not supplied by systemd or SQLite alone:

1. Bot token custody permits the current token only on the active Core host.
2. At host cutover, any doubt about a copied token requires BotFather token rotation.
3. On the active host, systemd singleton, a process lock and the durable generation
   lease fence releases and restarts.
4. Admission persists the unique `update_id` and canonical digest before offset
   advance.
5. The health monitor never calls `getUpdates`; it uses `getMe` and Core-reported
   polling freshness.

For outgoing Telegram methods there is no documented client idempotency key. A crash
after Telegram accepts a message/document but before the receipt is stored remains
ambiguous. The correct state is `UNKNOWN`, not a resend.

Sources:

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)

## 11. Health and observability findings

Process liveness does not prove polling, Google, DB or Bridge readiness. Gate 8 needs
a signed or digest-bound composite snapshot with explicit freshness.

The minimum stack is:

- JSON structured logs to journald and WinSW-managed files/Event Log;
- application counters and composite health;
- a private owner status endpoint;
- an outbound heartbeat to a monitor outside the Core failure domain;
- email/push escalation independent of Telegram.

Prometheus/Grafana and OpenTelemetry remain deferred. OpenTelemetry is a
vendor-neutral telemetry framework, not a storage/backend. With one Core and one
Bridge, it adds more components than diagnostic value until distributed trace demand
is measured.

Healthchecks.io can monitor missed heartbeats but its own FAQ describes a small
single-person operating team and possible prolonged incidents. It must not be the only
evidence source. Uptime Kuma is acceptable only on another host/failure domain.

Sources:

- [OpenTelemetry overview](https://opentelemetry.io/docs/what-is-opentelemetry/)
- [Prometheus FAQ and license](https://prometheus.io/docs/introduction/faq/)
- [Healthchecks documentation](https://healthchecks.io/docs/)
- [Healthchecks operational FAQ](https://healthchecks.io/docs/faq/)
- [Uptime Kuma](https://github.com/louislam/uptime-kuma)

## 12. Supply-chain findings

Every release artifact must be reproducible from the exact commit and contain:

- hash-pinned dependency lock;
- offline wheelhouse with digests;
- CycloneDX SBOM;
- secret-scan result reference;
- dependency vulnerability report;
- source/static analysis report;
- manifest and artifact signature;
- exact license inventory;
- digests of WinSW, restic and other external binaries.

Recommended verification tools at the evidence cut-off:

| Tool | Observed version | License/use |
|---|---:|---|
| Gitleaks | 8.30.1 | Secret scanning; feature-complete project, security fixes only |
| Semgrep OSS | 1.164.0 | LGPL-2.1; local static analysis |
| pip-audit | 2.10.0 | Apache-2.0; Python vulnerability audit |
| Syft | 1.44.0 | Apache-2.0; CycloneDX/SPDX SBOM |
| Cosign | 3.0.6 | Apache-2.0; artifact/blob signature verification |

Sources:

- [Gitleaks releases](https://github.com/gitleaks/gitleaks/releases)
- [Semgrep OSS](https://github.com/semgrep/semgrep)
- [pip-audit](https://github.com/pypa/pip-audit)
- [Syft](https://github.com/anchore/syft)
- [Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/)

## 13. Proposed recovery objectives

These values are Gate 8 design SLO candidates, not measured CURRENT facts. They become
Gate PASS criteria only after a portable restore drill measures them and the owner
approves or changes them.

| Asset/invariant | Proposed objective | Evidence required |
|---|---|---|
| Release artifact/config | RPO 0; RTO <= 15 min | Previous artifact verified and pointer rollback rehearsed |
| Core SQLite set | RPO <= 15 min; RTO <= 60 min | Off-host recovery points and another-host restore |
| Executed-effect safety | Safety RPO 0 | Missing receipts become `UNKNOWN`; no blind replay |
| Bridge service artifact | RPO 0; RTO <= 30 min | Current/previous Bridge artifact and service rollback |
| Local owner write | Pre-write snapshot; RTO <= 4 h | Snapshot/readback and authorized restore procedure |
| Complete VPS loss | RTO <= 2 h initial target | New-host recovery with secret recovery and token fencing |

Proposed restic retention, subject to the stricter data-retention policy:

- 15-minute recovery points for 48 hours;
- hourly recovery points for 14 days;
- daily recovery points for 35 days;
- weekly recovery points for 8 weeks;
- prune only through a separate controlled identity after the immutability window.

If a restore drill exceeds RTO or proves an RPO gap, Gate 8 PASS remains blocked. The
response is to adjust backup frequency/design or escalate the business target, not to
declare a better number.

## 14. Cost and lock-in

| Item | Incremental cost/lock-in |
|---|---|
| systemd/Python/SQLite/WinSW/restic | No software license charge; operator time and storage remain |
| Tailscale | Personal tier may be $0 only if its eligibility/limits fit; paid plan must be budgeted otherwise |
| Off-host object/storage provider | Depends on encrypted snapshot volume, retention and egress |
| Healthchecks managed service | Low entry cost, but external provider dependency |
| Docker/Postgres option | Potential VPS RAM tier increase and materially more operator work |
| WireGuard option | Lower control-plane lock-in, higher key/firewall operations |
| Sentry/Prometheus/Grafana | Deferred cost and maintenance until measured need |

The dominant MVP risk is operational complexity, not license price. Adding a
container engine, database server, monitoring stack and continuous replication
simultaneously would increase recovery paths and produce the private-fix cycle Gate 8
is intended to stop.

## 15. Explicit rejects and deferred choices

Rejected for Gate 8:

- Kubernetes, Swarm or another cluster orchestrator;
- active/active Core or a warm second poller;
- network/shared filesystem for SQLite or owner files;
- automatic SQLite-to-PostgreSQL migration;
- Bridge with arbitrary shell/PowerShell/filesystem access;
- Telegram or Google credentials on Bridge;
- Tailscale identity as the only application authorization;
- backup stored only on the Core host;
- rollback implemented only as a `current` symlink switch;
- automatic retry of `UNKNOWN`;
- monitoring that calls Telegram `getUpdates`;
- enabling Core/Bridge autostart before pilot PASS.

Deferred until measured need:

- PostgreSQL and WAL/PITR;
- Litestream continuous replication;
- Docker Compose or Podman Quadlet;
- Prometheus/Grafana/OpenTelemetry Collector;
- Sentry or another full error-observability platform;
- multiple authorized Bridges.

## 16. Accepted root decisions and execution prerequisites

The former architecture conflicts are resolved for Nobus MVP-1 by the owner decisions
below. They are no longer blockers to TARGET architecture readiness. Missing runtime
implementations, L4 approvals and evidence remain blockers to Gate 8 execution/PASS.

### 16.1 SQLite versus PostgreSQL — resolved for MVP-1

Single-node SQLite is the normative MVP-1 state source. This specializes and replaces
the earlier general statement that production necessarily requires PostgreSQL for the
Nobus MVP-1 scope. PostgreSQL is evaluated only after the pilot when measurements show
one or more explicit triggers: a legitimate multi-writer topology, throughput or lock
contention outside the approved SLO, or an approved HA requirement. Such a change is a
separate migration program with its own L4 and proof. Network-mounted SQLite is
prohibited.

### 16.2 Runtime database inventory — resolved contract

The historical handoff reports four SQLite runtime databases; fresh Gate 0
evidence must discover the actual CURRENT. TARGET backup, health, migration and
restore never rely on a silently fixed list or an older three-DB statement. Preflight
discovers every runtime DB through the authoritative registry/config, reconciles that
inventory against runtime state, records count/logical ID/path/schema/application
digest in the release and backup-set manifests, and fails closed on any omission,
duplicate or unexpected SQLite file.

### 16.3 Identity-bound secrets — resolved contract

DPAPI blobs, private keys and other identity-bound secrets are never copied between
Windows identities or between Windows and the VPS. Core and Bridge receive different
least-privilege credentials. Recovery or host/identity replacement revokes the old
binding and re-enrolls/re-authorizes each target identity through its provider-specific
procedure. Portable DB restore proves data and reconciliation state; it does not claim
that identity-bound credentials are portable.

### 16.4 Telegram global custody — resolved contract

The current bot token exists only inside one server-side Core credential boundary.
The Windows Bridge never receives it. systemd and a SQLite lease remain local controls,
so host cutover also uses credential inventory, generation fencing and token rotation
whenever old-host custody is uncertain. One durable polling lease and ingress dedupe
bind the single authorized Core generation.

### 16.5 RPO/RTO — design candidates, not evidence

The values in section 13 are explicit SLO candidates. They are neither measured
CURRENT facts nor Gate PASS evidence. Before Gate 8 PASS, a portable restore drill must
measure actual RPO/RTO and the owner must approve the measured targets or approve a
revised business objective.

### 16.6 Gate 0–7 handoff status

The corresponding `docs/gates` research and architecture documents represent the
Gate 0–7 design handoffs and are architecture prerequisites. Gate 8 design may be
ready from those contracts. Their implementation VerificationBundles, exact artifacts,
smoke fixtures and accepted runtime evidence remain execution prerequisites; absence
of that evidence blocks implementation/pilot/PASS, not this TARGET design.

## 17. Research verification

### L1 — source, version and scope validation

- exact baseline commit and CURRENT/TARGET distinction recorded;
- canonical Gate 8 L4, ADR 0007/0009/0011/0016/0017 and docs 03/05/07/08/12
  cross-referenced;
- primary upstream documentation and release pages used;
- versions are explicitly evidence snapshots;
- no secrets, tokens, hostnames, credentials or customer payloads recorded;
- no deployment/runtime action described as completed.

### L2 — independent method check

The preferred stack was compared with two materially different implementations:
Docker Compose/PostgreSQL and Podman/Quadlet/Litestream. Recovery semantics were
checked from the reverse direction: starting with total host loss and ambiguous
external writes rather than from successful deployment. The native stack remained
the only option that meets the accepted verdict without requiring simultaneous DB,
container and supervision migrations.

### L3 — adversarial findings incorporated

The dossier treats the following as hard controls rather than caveats:

- a supervisor is not a global singleton;
- an overlay network is not device authorization;
- a hash-valid backup is not a portable restore;
- a current-pointer switch is not external-effect rollback;
- DB RPO is distinct from duplicate-safety RPO;
- liveness is distinct from fresh readiness;
- independently valid snapshots of all inventoried DBs are not a coordinated
  recovery point;
- a reachable Bridge is not necessarily the currently authorized device.

## 18. Research conclusion

**RESEARCH READY.**

The accepted root decisions remove the former design conflicts. Stack A and the TARGET
contracts are sufficient for `ARCHITECTURE READY` after the document-level L1/L2/L3
checks pass.

**GATE 8 IMPLEMENTATION/PILOT BLOCKED.** No runtime PASS is claimed. Execution remains
blocked until all of the following exist under exact action-bound L4:

1. exact Core and Bridge artifacts, service identities and release manifests;
2. dynamic inventory and coordinated fencing of every discovered runtime SQLite DB;
3. server-only Telegram credential custody and tested global polling fencing;
4. identity-specific Core/Bridge re-enrollment and revocation procedures;
5. encrypted off-host backup plus another-host restore drill, measured RPO/RTO and
   owner acceptance of the resulting SLO;
6. Gate 0–7 implementation VerificationBundles, smoke fixtures and accepted evidence;
7. full natural smoke, reconciliation evidence and an unchanged 72-hour pilot.