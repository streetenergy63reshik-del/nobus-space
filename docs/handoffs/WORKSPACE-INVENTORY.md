# Nobus Space — workspace inventory

**C5, 8 сентября 2026:** отдельный Code/worktrees/mvp1-closure-c5, ветка codex/mvp1-closure-c5-ops-security, база 1b3cf67405c4523258dd8b400d17d09601f815ff. 20 незавершённых файлов canonical, telegram-live и принятый C4 worktree сохраняются. Проверенный C5 source9efad0f2 принят; публикация ожидается. Это не deploy. Recovery refs и копии не удаляются.

**Актуально на:** 8 сентября 2026 года
**Назначение:** роли checkout/worktree и границы сохранности, а не active roadmap

Текущий статус: C0–C3 ACCEPTED / PUBLISHED; C4 ACCEPTED / PASS / PUBLISHED; C5 ACCEPTED / PASS / PUBLICATION_PENDING; C6 HOLD; MVP1 NOT READY.

Git-репозиторий — source of truth для code/tests/ADR/CURRENT/docs. Protected
GitHub `main` и release tags — канон принятой опубликованной истории после
readback. Nobus Memory, handoff и чаты — указатели/claims, а не замена exact
Git revision.

## Текущий C4 worktree

C4 выполняется только в `.runtime/worktrees/mvp1-closure-c4-frontend-journey`,
ветка `codex/mvp1-closure-c4-frontend-journey`, от принятой базы C3
`b9283b3419928042c80278b5088b526edebab6e7` /
`77062335b1dbccb3694721d357e484c856ac89c7`.
Проверенный code checkpoint: `68f87f18da3de7c995f83b9cb08b391d0af5cdfb` /
`5ae168bf613b18fc2f14e24973b5167a2b4c7b74`.
Позднейшие docs/evidence-only изменения имеют отдельный manifest.

Canonical checkout остаётся чужим dirty WIP @ f18a664; его 20 dirty paths
сохранены. C2/C3/live и другие worktrees не изменяются. Изолированные disposable
состояния, бюджет и временные smoke receipts находятся только в C4 `.runtime`;
production DB не используется. Временные процессы контролируются по exact
PID/start time и Windows Job, без остановки процессов по общему имени.
Текущая передача — [C4 HANDOFF](../gates/gate-c4-frontend-journey/HANDOFF.md).

## Исторический worktree manifest C0

Далее сохранён снимок C0 от 3 сентября. Его SHA, dirty manifests, editorial
hashes и тогдашние статусы описывают только тот момент, а не состояние нынешней main.

| Worktree / branch | Зафиксированный HEAD/base | Роль и граница |
|---|---|---|
| canonical `nobus-orchestrator-dev` / `main` | `f18a664f2fab2fbd193e894bc93d5624683badf2` | dirty local WIP; источник только для exact-reviewed editorial files; не base, не изменять |
| `.runtime/worktrees/mvp1-closure-c0-truth-contract` / `codex/mvp1-closure-c0-truth-contract` | base `f5a9119cc0aa1bcce735a3c608f9751747002694` | единственный C0 implementation worktree |
| `.runtime/worktrees/mvp1-closure-c0-publication` / `codex/mvp1-closure-c0-publication` | `d25b1b46f2c2c75688fa215c46167d742dd66b8a` | publication-safe projection, merged only through PR #9 |
| `.runtime/worktrees/mvp1-closure-c0-publication-readback` / `codex/mvp1-closure-c0-publication-readback` | base `70085f8bdf20d139edf042bffa2a1169daf6791c` | status/readback projection; publication only through separately authorized PR |
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
Из untracked source в local accepted candidate были импортированы только docs
15/16 по exact hashes ниже; publication-safe tree их не содержит.

## Exact base и publication state

- protected remote `refs/heads/main` after PR #9:
  `70085f8bdf20d139edf042bffa2a1169daf6791c`;
- published C0 tree: `3a31914ac9b1732ea8344aaa09cd7075506ce315`;
- final protected-main SHA/tree after status-only sync фиксируются exact remote
  readback в итоговом C0-сообщении;
- remote annotated tag object `v1.0.1`:
  `1322e922968d938194f689851c204ac551e6822b`;
- peeled `v1.0.1^{commit}`: `f5a9119cc0aa1bcce735a3c608f9751747002694`;
- release tree: `01f6399fbbeca20d4c956482776329a9ee8adc20`;
- C0 implementation и publication-safe ветки начаты от exact pre-publication
  remote main, а не от dirty local `main`;
- publication выполнена только через PR #9; tag, release, deploy и runtime не
  изменялись.

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

**C0 PERFORMED PR #9 + STATUS-ONLY PR / MERGES; NO TAG / NO DEPLOY / NO LIVE EFFECT.**
