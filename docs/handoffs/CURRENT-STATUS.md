# Nobus Space — CURRENT

**Актуально на:** 25 августа 2026 года
**Lifecycle:** `GATE_CANDIDATE` — one consolidated rework integrated;
candidate-bound L1/L2/L3 accepted at the local docs commit
**Active decision:** [ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)

Telegram Mini App и Telegram-оркестратор обязательны в MVP-1. Они используют
existing local Core, одну queue/state model и одну effect authority. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.

## Git binding

| Поле | Значение |
|---|---|
| Repository | `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev` |
| Branch | `docs/mvp1-thin-architecture` |
| Safe base | `8b896fbca9b23c8751d651d14a122506338b5827` |
| Local main | `420c9a6d4fcdb8f73fc71e23257fa319dafb6354`; ancestor of safe base |
| Stage-1 checkpoint | `6f2fa50` (`AGENTS.md` only) |
| Docs candidate | exact branch tip after the final local docs commit; resolve with `git rev-parse HEAD` |
| Origin | configured; no remote-tracking refs/upstream confirmed |

Git commit не может содержать собственный hash без циклической ссылки. Поэтому
этот файл фиксирует exact branch/base/checkpoint и воспроизводимую команду
binding; literal final docs commit SHA фиксируется в итоговом handoff задачи
сразу после commit. До разрешённых push/PR/merge и remote SHA readback GitHub `main`
не является каноном этого candidate.

Git-репозиторий — источник истины для code/tests/ADR/CURRENT/docs. Nobus Memory
сохраняет только pointer/status/decision/freshness и не переопределяет Git.

## CURRENT facts

- В exact Git base существует owner-bound local Telegram/Core/Codex runtime.
- Live process/provider/VPS/Telegram state в этой documentation-задаче не
  проверялся и не изменялся.
- Gate 0 исторически accepted:
  `result_commit=f5086b2a71a9ae22be3c858ff69453287f6925da`,
  `result_tree=2e3248eb295b1627d36f196c26dfc21c6ebd90fd`.
- Все 20 Gate 0 `required_sources` должны оставаться byte-identical.
- Active roadmap — шесть коротких slices из ADR 0022, не Gate 0–8.
- Mini App ещё не реализован; это TARGET следующего slice.

## Frozen WIP and recovery

- `agent/gate-01-acceptance` @
  `db0a24e8d7be8b1d1f1ddcd701d424c49164784e`:
  41 tracked modified + 45 untracked = 86 paths,
  `HOLD / NOT_ACCEPTED`.
- Reuse возможен только будущим exact diff; весь worktree нельзя merge или
  объявлять принятым.
- Шесть `refs/nobus-safety/*` и соответствующие verified bundles сохранены;
  latest WIP pause: `73958b72a17cda01f435905c12d1e6118477d299`.
- Path-limited recovery stash `8270192a...` сохранён.
- Worktrees, refs, bundles, stash и recovery files этой задачей не изменяются.
- `.nobus-quality/cases.ndjson` содержит pre-existing +22-line user change,
  остаётся unstaged и не входит в candidate.

## Verification state

Профиль: `software-development`; риск: high; candidate обязан пройти один
coherent L1/L2/L3 по frozen bytes.

| Уровень | Проверка | Статус |
|---|---|---|
| WIP L1 | links + ADR overlay: `11 passed`; diff/path set; 20 hashes; targeted secret patterns | `PASS` |
| Candidate L1 | `11 passed`; 20/20 hashes; diff/path/link/secret/stale-claim scans | `PASS` on final tree |
| L2 | distinct independent L2 identity; decision-map reproduction after one rework package | `PASS` on final tree |
| L3 | separate adversarial L3 identity, different from L2; scenarios 3/5 plus auth/recovery target recheck | `PASS` on final tree |

Статусы выше относятся к exact tree и локальному commit этого
handoff, а не к промежуточному WIP. Команды, counts, literal commit/tree
и reviewer verdict фиксируются в task handoff: commit не может
содержать собственный hash.

## Blockers and risks

- Способ public HTTPS ingress/hostname не выбран; это один bounded
  implementation input следующего slice, не разрешение на VPS Core migration.
- Remote state не проверялся сетью; push/fetch/pull запрещены текущей задачей.
- Dirty Gate 1 WIP может содержать полезные изменения и debt; нужен отдельный
  recovery/reuse audit до любого merge/cleanup.
- Existing local runtime и historical docs могут описывать разные revisions;
  exact Git revision и воспроизводимая проверка имеют приоритет.
- Nobus Memory содержит stale wording «изменения ещё не применены»; Memory
  read-only и не обновляется до принятия Git-кандидата.

## Next vertical slice

**Thin Mini App owner authentication + read-only task list/detail.**

Acceptance:

1. bounded Telegram `initData` проверяется для exact bot/owner, freshness и
   replay;
2. short-lived opaque session хранится только in-memory;
3. list/detail читаются из existing authoritative state, без второй DB/queue;
4. cross-owner/task ref и client-selected authority fail closed;
5. local Core unavailable не создаёт task/effect и даёт safe UI state.

Out of scope: task create, approvals/effects, Core/token/poller migration,
Agent Registry, Web IDE/shell/self-deploy и live publication.

## Proposed Nobus Memory sync after accepted merge

```text
Nobus Space: ADR 0022 accepted in Git; thin Telegram Mini App + existing local
Core is active MVP-1 roadmap. Full distributed Gate 2A is frozen; Gate 1 WIP
remains HOLD/NOT_ACCEPTED. Source: accepted Git main SHA; next slice is
owner-auth + read-only task list/detail. Freshness: 2026-08-25.
```

Memory update, push, PR, merge, deploy, deletion и live/provider actions этой
задачей не выполняются.
