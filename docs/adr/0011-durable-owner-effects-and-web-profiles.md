# ADR 0011 — Durable Telegram queue and explicit owner effects

**Status:** ACCEPTED LIVE LOCAL OWNER RUNTIME
**Date:** 2026-07-24

## Context

The owner-facing Telegram runner must accept several tasks quickly, survive a process
restart, preserve confirmation decisions, and execute risky effects only after an exact
owner confirmation. The previous process-memory queue and short-lived effect
capabilities could lose accepted work or block FIFO after a poison job.

## Decision

1. Accepted `draft`, `patch`, and confirmed `effect` jobs are persisted before Telegram
   admission returns. The SQLite queue is bounded to 40 records and uses renewable,
   generation-bound CAS leases.
2. A safe read-only draft may be claimed at most three times. A lost lease cancels the
   active child process. A transient failure releases the job; the third failed claim
   moves it to `failed` (dead letter), so one poison job cannot block FIFO.
3. Patch and artifact operations recover from their exact persisted proposal and
   baseline. A changed baseline or target blocks execution.
4. A network effect is persisted as `pending → executing → completed/unknown`.
   If the process restarts while it is `executing`, its result becomes `unknown`; the
   command is never repeated automatically.
5. Product-effect capabilities are encrypted with current-user DPAPI, bound to tenant,
   actor and chat, and retained for at most seven days. Expiry or corruption fails
   closed and eventually dead-letters the queue job instead of blocking later work.
6. Telegram delivery has a separate durable receipt:
   `completed/unknown → delivered → queue ACK → capability cleanup`. A replay after the
   receipt does not send the result again.
7. Telegram `sendDocument` remains at-least-once in the narrow crash window after the
   Telegram API accepted the document but before the local delivery receipt was
   persisted. The Bot API has no idempotency key for this operation; the residual risk
   must be visible in the release evidence.
8. `/research` is the only profile that enables live public-web search. The concrete
   process allowlist includes its exact Codex CLI argv. Signed-in browser sessions,
   publication, purchase, upload and arbitrary external writes remain forbidden.
9. Structured `git fetch` is bound to the exact HTTPS destination shown to the owner.
   Repository includes and URL rewrites are rejected; system/global Git config is
   disabled for execution. Structured `pip install` rejects nested requirements,
   constraints, editable/local/direct references and requires exact versions plus
   SHA-256 hashes and binary-only artifacts.
10. Health, backup and restore require exact application schemas. The Telegram queue
    additionally decrypts and verifies every protected payload. Dead letters make the
    health probe report `DEGRADED` for operator reconciliation.
11. Restore is journaled and uses flushed staging/rollback files plus write-through
    replacement. Startup completes rollback before opening runtime stores.
12. One cross-session Windows mutex protects runner, backup and restore. Task
    Scheduler is the sole bounded liveness supervisor; health only records an alert
    and never stop/starts a persistent degraded state.

## Restart semantics

- A pending job remains pending.
- An expired lease is reclaimed with a new lease generation.
- A completed durable Core task is reconciled and its redundant admission job is ACKed.
- A safe read-only job may resume, bounded by three durable claims.
- An interrupted network command is `unknown` and is not repeated.
- A delivered effect is not resent; its queue job is ACKed and the receipt is cleaned.
- A third failed claim becomes a dead letter and requires operator reconciliation.

These rules supersede older process-memory and “manual reconciliation only” statements
in historical handoff sections.

## Consequences

- Queue admission is restart-safe and a poison item cannot permanently block later work.
- Exact L4 decisions survive runner restart without granting broader authority.
- Backup/restore detects a valid but unrelated SQLite database.
- Live activation at `aa8a02e`, Task Scheduler update, Telegram menu publication,
  startup probe, Whisper warmup, health and owner smoke are complete.
- A destructive crash/reboot drill and every future network/write smoke remain explicit owner L4.

### Windows path boundary

Owner workspace and quarantine writes revalidate root/parent identity and reject
reparse ancestors immediately before path-based replace/link. Python's portable
filesystem API does not provide a fully handle-relative Windows rename contract, so
the release does not claim protection against a privileged same-account process that
can replace a directory in the final syscall window. MVP operation is limited to the
owner-controlled directories; a separate restricted OS identity/ACL remains a
production-hardening item.
