# Nobus Space — workspace inventory

**Актуально на:** 2 сентября 2026 года
**Назначение:** роли checkout/worktree и границы сохранности, а не active roadmap

Текущий verdict: `MVP-1 PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / PATCH REQUIRED`; `DEPLOYMENT REVISION UNVERIFIED`; `MVP-2 HOLD`.

Git-репозиторий — source of truth для code/tests/ADR/CURRENT/docs. Protected
GitHub `main` и release tags — канон принятой опубликованной истории после
readback. Nobus Memory, handoff и чаты — указатели/claims, а не замена exact
Git revision.

## Worktree manifest C0

| Worktree / branch | HEAD при preflight | Роль и граница |
|---|---|---|
| canonical `nobus-orchestrator-dev` / `main` | `f18a664f2fab2fbd193e894bc93d5624683badf2` | dirty local WIP; источник только для exact-reviewed editorial files; не base, не изменять |
| `.runtime/worktrees/mvp1-closure-c0-truth-contract` / `codex/mvp1-closure-c0-truth-contract` | base `f5a9119cc0aa1bcce735a3c608f9751747002694` | единственный C0 implementation worktree |
| `worktrees/telegram-live` / `codex/mvp1-g7-activation` | `f5a9119cc0aa1bcce735a3c608f9751747002694` | clean live claim; read-only, не редактировать |
| `worktrees/gate-01-acceptance` / `agent/gate-01-acceptance` | `db0a24e8d7be8b1d1f1ddcd701d424c49164784e` | dirty historical Gate 1 WIP; `HOLD / NOT_ACCEPTED`, не импортировать целиком |
| `.runtime/worktrees/mvp1-command-surface` | `14c80131b2a702d75f92abb4fe22d49ea6aa975c` | clean historical checkpoint; read-only |
| `.runtime/worktrees/mvp1-owner-ui` | `a189ce1ac574df56bb8c934ceb7dd9839891b45e` | clean historical checkpoint; read-only |
| `.runtime/worktrees/mvp1-release-docs` | `6f3a32c4a3e2c3fda46b410f23596e73c86b08ce` | clean historical checkpoint; read-only |
| `.runtime/worktrees/mvp1-runtime-recovery` | `6e19d9e43d05c41a703abed1658a19d72a5f2678` | clean historical checkpoint; read-only |
| `worktrees/docs-mvp1-product-readiness` | `c70738c2bee15a3b86e68d0c3720dfbf136748ab` | clean historical docs checkpoint; read-only |
| `worktrees/docs-mvp1-status-g7-ready` | `a27c7460e02fa6a18852e6f09288206a24e8ccb5` | clean historical docs checkpoint; read-only |

`git worktree list --porcelain` и отдельный dirty/untracked manifest были
прочитаны до C0 edits. Ни один соседний worktree не менялся, не удалялся, не
stash/reset/clean/rebase.

### Canonical dirty source manifest до C0

`M` (18): `README.md`, docs 01/02/03/04/08/11/14, `docs/README.md`, ADR 0022,
`docs/gates/README.md`, `docs/handoffs/CURRENT-STATUS.md`,
`docs/handoffs/WORKSPACE-INVENTORY.md`, `scripts/run_telegram_mvp1.py`,
`src/application/miniapp.py`, `src/application/runtime_maintenance.py`,
`tests/test_documentation.py`, `tests/test_telegram_mvp1_runner.py`.

`??` (2): `docs/15-Продуктовая-дорожная-карта.md` и
`docs/16-Управленческая-карта-разработки.html`.

C0 не переносил modified code/runtime/tests/ADR 0022 или другие modified docs.
Из untracked source были импортированы только docs 15/16 по exact hashes ниже.

## Exact base и publication state

- remote `refs/heads/main`: `f5a9119cc0aa1bcce735a3c608f9751747002694`;
- remote annotated tag object `v1.0.1`:
  `1322e922968d938194f689851c204ac551e6822b`;
- peeled `v1.0.1^{commit}`: `f5a9119cc0aa1bcce735a3c608f9751747002694`;
- release tree: `01f6399fbbeca20d4c956482776329a9ee8adc20`;
- C0 branch начата от exact remote main, а не от dirty local `main`;
- C0 не выполняет push, PR, merge, tag, release, deploy или runtime mutation.

## Editorial import manifest

До импорта source dirty checkout был зафиксирован. В C0 перенесены только два
целых файла, после чего их hashes повторно совпали:

| Файл | Bytes | SHA-256 | Статус |
|---|---:|---|---|
| `docs/15-Продуктовая-дорожная-карта.md` | 200633 | `92c8abb64aebdc3363157aae00961bccc47c3491b3d7e8ab38901a3c768716bc` | exact whole-file import; `PUBLICATION HOLD` |
| `docs/16-Управленческая-карта-разработки.html` | 84410 | `eb447fa7a1264c9272e9bb6619d021b6b7692808bb2a4188a053b3257faede46` | exact whole-file import; `PUBLICATION HOLD` |

Код/runtime/tests из dirty checkout не копировались. После manifest все
редакции выполняются только в C0 worktree.

## Historical sealed Gate 0

- result commit: `f5086b2a71a9ae22be3c858ff69453287f6925da`;
- каталог `docs/gates/gate-00-product-contract-baseline/**` immutable;
- все 20 `required_sources` совпали со своими SHA-256 catalog entries;
- C0 дополнительно сравнивает весь каталог с published base `f5a9119...`.

ADR 0023 forward-only: historical evidence и старые ADR не переписываются.

## Recovery boundary

Safety refs, bundles, stash, dirty Gate 1 WIP и прочие recovery artifacts не
являются C0 scope. Они сохраняются без изменений до отдельного exact target
audit и применимой авторизации. Никакой broad cleanup не разрешён.

## Управление работой

**Один Gate = одна Codex-задача = один пользовательский чат.** Внутренние
Txx/Cxx и прежние R01–R47 не создают отдельные пользовательские чаты. Active
closure-roadmap — C0, C1, C2, C3, C4, C5, C6; `MVP-2 HOLD` до принятого C6.

**C0 PERFORMED NO PUSH / PR / MERGE / TAG / DEPLOY.**
