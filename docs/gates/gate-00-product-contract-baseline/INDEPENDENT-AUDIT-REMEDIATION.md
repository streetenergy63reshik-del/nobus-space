# Gate 0 — independent audit remediation

**Audit date:** 2026-07-31
**Audit artifact SHA-256:** `sha256:a968830f9261a78f7193310e402ec6ac15e920b4fb457b6329d4139d42f4ef9b`
**Audited commit:** `0a0f56e8b6f77deccba2b51239a3fe1f207da349`
**Current status:** `REWORK` until a new sealed result commit and a separate
immutable acceptance binding exist.

The audit's blocking findings are correct and relevant. The old commit is
mechanically coherent, but it freezes an obsolete semantic oracle and cannot be
used as Gate 1 integration authority.

## Accepted findings and corrective contract

| Finding | Decision | Required correction |
|---|---|---|
| ADR 0020, Gate 2A and `development` are absent | Accepted, P1 | Closed digest-bound normative catalog; Product Contract/corpus v2; Gate 2A roles and handoffs; omission attacks |
| L2/L3 receipts are self-stamped | Accepted, P1 | `record-review` validates and preserves an external identified submission; it never awards a verdict; seal requires three unique reviewer identities |
| READY is not immutably bound to a result commit/tree | Accepted, P1 | Result commit first, then a separate accepted `GATE-0-ACCEPTANCE.json` binding its exact commit and tree |
| Runtime freshness expired before the old commit | Accepted, P2 | New action-bound capture and reviews must complete within one fresh window; historical evidence cannot support present-tense READY |
| Pure verification is mixed with live-capable maintenance | Accepted, P2 | Explicit pure argv lists only contract/evidence tests; live maintenance remains direct-invocation-only and L4-bound |

The recommendation to preserve strict schemas, hashing, path/secret guards,
tenant isolation and fail-closed behavior is also accepted. The remediation does
not replace those controls with a new framework.

## Implemented static remediation

- `product/normative-catalog.json` closes the accepted source set with exact
  SHA-256 values and declares seven domains, Gate 2A and six specialist roles.
- Product Contract and corpus version `2.0.0` add `development`, Gate 2A
  contracts and 8 text/voice development cases, bringing the target to 104.
- Cross-source tests remove or mutate ADR 0020/catalog inputs and require a
  fail-closed result.
- External review submissions carry exact candidate/frozen/capture/review-tree
  bindings, reviewer identity/type/method, check results and evidence refs.
- Duplicate reviewer identities, duplicate JSON keys, non-finite values,
  missing submissions and identity mismatches are rejected.
- `verification-profiles.json` separates the pure contract/evidence argv from
  `manage_runtime_maintenance.ps1`.

## Remaining closure sequence

Until every item below succeeds, Gate 0 remains `REWORK` and Gate 1 remains
blocked:

1. Recompute the catalog source digests after the final documentation bytes.
2. Regenerate Product Contract, schemas/goldens, corpus, inventories and the
   blocked pre-capture candidate.
3. Pass the pure profile and full local regression without invoking live
   maintenance.
4. Obtain exact action-bound L4 for one start/capture attempt on the frozen
   candidate; no retry is implied.
5. Complete external candidate-bound L1, L2 and L3 within the capture window;
   preserve only validated receipts.
6. Seal 22/22 and create the local result commit with named staging only.
7. Create a separate acceptance record binding the exact result commit and Git
   tree; only that later commit may update canonical status to READY.

No deploy, push, remote publication or security-boundary expansion is part of
this remediation.
