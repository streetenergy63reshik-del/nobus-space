# Gate 0 — Product Contract and Baseline Evidence handoff

**Status:** `GATE 0 READY`

**Candidate generated:** `2026-07-31T09:21:47.793676Z`

All G0-01..G0-22 criteria and independent L1/L2/L3 evidence are sealed.

## Authoritative artifacts

- Product Contract: `product/product-contract.json`
- synthetic corpus: `corpus/requests.v1.jsonl`
- baseline: `evidence/baseline-evidence.json`
- evidence manifest: `evidence/evidence-manifest.json`
- machine handoff: `fixtures/contracts/valid/gate-handoff.json`
- verification receipts: `verification/l1.json`, `verification/l2.json`,
  `verification/l3.json`

## Verified closure facts

- The saved Telegram runner status is `VERIFIED` with
  `1` observed Scheduler-bound instance.
- Verified database roles: `checkpoint, core, legacy, telegram_state`.
  Non-verified database roles: `none`.
- Telegram genesis baseline: `VERIFIED`.
  Historical legacy migration execution is never claimed; a Gate 2 ledger starts
  only from an accepted genesis.
- Exact-tree verifier/release evidence: `VERIFIED`.
  Historical tool receipts do not satisfy current candidate binding.
- Server CURRENT is owner-verified `NOT_APPLICABLE_VERIFIED`; this says nothing
  about TARGET Gate 3/8.
- Legacy Scheduler stop semantics can leave detached runner processes. Gate 0
  uses owner-authorized exact-runner maintenance with opaque identities and
  creation-time-bound native process handles; the
  durable WinSW supervision correction belongs to the runtime/deployment Gate,
  and the current launcher remains unchanged.
- CURRENT Scheduler, runner and four SQLite databases are bound to the
  canonical candidate worktree. The separate telegram-live isolation remains TARGET
  for the runtime/deployment Gate and is not claimed as CURRENT by Gate 0.
- The one-start precondition freezes canonical repository HEAD, branch,
  sanitized Git status, the exact tracked repository closure excluding quality
  ledgers, and every existing `ops`, `scripts`, `src` and `tests` file. The
  runner and singleton guard are therefore exact-tree inputs. Traversal is
  no-follow and reject-before-read: credential/database names and symlink or
  reparse topology fail closed before content access. Every hash is read from
  atomic validated file handles whose opened identity must equal the pre-open
  lstat identity. Ignored local credentials, runtime databases and local runtime
  state are not read.
- Start authority binds the exact whole launcher, exact Scheduler definition
  and canonical runtime artifact hashes to expected opaque digests. The internal
  path requires all eight expected digests before any read and executes the fixed
  `core/live/core/core/live/start` sequence. Two stable live reads and three
  frozen core readbacks must match; the final live read is immediately before
  the single in-process start-verified Scheduler start. Any mismatch fails
  closed before start.
  Both live definitions must also carry a strictly boolean true
  `ActionIdContractExact`, derived from installer-equivalent empty `Action.Id`;
  missing, non-boolean or false blocks even when all digests match.
  Principal and trigger spellings are equivalent only for the same resolved
  Windows SID. Scheduler arguments must satisfy the closed eight-token action
  contract represented by a single-command AST without control tokens or
  redirections. Case and whitespace normalization is allowed; launcher quoting
  is optional but limited to a single matching outer quote pair. An unresolved
  identity or any missing, changed or extra token fails closed.
  An action-contract failure may emit only the fixed 20-field action bitmap;
  raw Scheduler values, arguments and paths are never persisted.
- The owner-authorized one-shot repair may replace only `Action.Arguments`
  after two stable coherent task-object/XML reads match the exact Inspect C
  bitmap, canonical shifted `-File` target, approved PowerShell, canonical
  launcher and installer-equivalent empty `Action.Id`. An exclusive
  sanctioned-writer mutex and third final coherent freshness read immediately
  precede the only `Set-ScheduledTask`; the postcondition requires the
  non-argument definition digest unchanged and the complete task contract.
  Mismatch or error stops without retry. Windows Task Scheduler has no
  OS-level compare-and-swap against unsanctioned external writers, so live
  mutation remains blocked pending explicit owner acceptance of that residual.
- Gitleaks coverage binds `scanned_file_count` to the exact immutable
  `input_entries`. The self-referential receipt files are excluded from the
  scanner tree but exact-hash bound through `receipt_entries` and
  `frozen_tree_digest`. After receipt bind, the targeted and full test suites
  rerun on the final materialized bytes before independent L1/L2/L3 or
  Scheduler start.


## Evidence boundaries

- documentation, candidate repository, runtime release, process, Scheduler, DB,
  configuration, dependencies and external capabilities remain separate layers;
- candidate repository is `d11eda855a4e2ff88096dc536f36374daacc4de6`, runtime release is
  `d11eda855a4e2ff88096dc536f36374daacc4de6`, and design base is `9d816b35d3f419b42e24ad09ae6aadc92c33db43`;
- raw argv, environment, connection strings, secrets, owner/client payloads and
  absolute local paths are not persisted;
- no provider call, DB mutation, backup, deployment or remote Git action
  occurred; runtime activity was limited to owner-authorized exact-runner
  maintenance, subsequent offline handle-safety hardening, and one bounded
  Scheduler start required for fresh capture.

## Protected worktree

All pre-existing root-integration changes remain unstaged and untouched.
`.nobus-quality/cases.ndjson` was not changed; root integration must separately
record a sanitized case only after accepting the Gate 0 commit.

## Gate 1–8 consumer handoff

| Gate | Exact Gate 0 inputs | Explicitly not pre-completed |
|---:|---|---|
| 1 | corpus digest, intent vocabulary, ambiguity/effect rules, CURRENT score | parser/prompt implementation |
| 2 | catalog, schemas/golden fixtures, registry and fitness rules | production models/migrations |
| 3 | provider/data policy and external capability baseline | provider adapters/cost cap |
| 4 | authority, idempotency and unknown-outcome cases | end-to-end effects |
| 5 | document lifecycle and deny/source/output cases | Bridge/indexer/parser |
| 6 | AnalysisRequest/provenance/calculation cases | formulas/datasets/metrics |
| 7 | artifact/write-plan revision/digest rules | renderers/writeback |
| 8 | evidence schema, manifest and freshness rules | deployment/pilot |

The result remains a Gate 0 product/evidence foundation, not runtime deployment
or Gate 1 implementation. A local commit is eligible only after the READY seal.
