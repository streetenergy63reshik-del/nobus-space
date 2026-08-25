# Nobus Space — CURRENT

**Актуально на:** 25 августа 2026 года
**Lifecycle:** `GATE_CANDIDATE` — architecture rebaseline published in an open
PR; post-publication status refresh is local until separately authorized push
**Active decision:** [ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)

Telegram Mini App и Telegram-оркестратор обязательны в MVP-1. Они используют
existing local Core, одну queue/state model и одну effect authority. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.

## Git binding

| Поле | Значение |
|---|---|
| Repository | `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev` |
| Branch | `docs/mvp1-thin-architecture` |
| Published protected `main` | `8b896fbca9b23c8751d651d14a122506338b5827` |
| Local main | `420c9a6d4fcdb8f73fc71e23257fa319dafb6354`; ancestor of safe base |
| Stage-1 checkpoint | `6f2fa50` (`AGENTS.md` only) |
| Published architecture candidate | `d3a235e4db2257826d5a5c5661a709c442be981e`; tree `bf503ae0bb7d243e083055e2631084987af3c1c0` |
| Pull request | [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1), `OPEN`, not merged |
| Local status-refresh candidate | exact branch tip after the final local commit; resolve with `git rev-parse HEAD` |
| Origin | public GitHub repository; remote-tracking refs confirmed; branch upstream not configured |
| `main` protection | PR + conversation resolution required; bypass, force-push and deletion disabled; required status checks not configured |

Git commit не может содержать собственный hash без циклической ссылки. Поэтому
этот файл фиксирует exact published refs и воспроизводимую команду binding;
literal final refresh commit SHA фиксируется в итоговом handoff задачи сразу
после commit. Защищённая GitHub `main` @ `8b896f...` остаётся текущим принятым
опубликованным каноном. Кандидат PR #1 не становится каноном до отдельно
разрешённого merge и последующего readback exact `main` SHA.

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
| Architecture candidate | `11 passed`; 20/20 hashes; diff/path/link/secret/stale-claim scans; independent L2/L3 | `PASS` @ `d3a235e...` / `bf503ae...` |
| Refresh L1 | docs tests; 20 hashes; diff/path/link/secret/stale-claim scans | `PASS` on final refresh tree |
| Refresh L2 | distinct independent identity; remote/local/document-state reproduction | `PASS` on final refresh tree |
| Refresh L3 | separate adversarial identity; authority, recovery and stale-claim challenge | `PASS` on final refresh tree |

Статусы выше относятся к exact tree и локальному commit этого
handoff, а не к промежуточному WIP. Команды, counts, literal commit/tree
и reviewer verdict фиксируются в task handoff: commit не может
содержать собственный hash.

## Blockers and risks

- Способ public HTTPS ingress/hostname не выбран; это один bounded
  implementation input следующего slice, не разрешение на VPS Core migration.
- PR #1 открыт и не слит; push обновлённого head и merge требуют отдельных
  точных разрешений. Текущий канон `main` остаётся на `8b896f...`.
- Описание публичного GitHub-репозитория всё ещё называет его private; это
  отдельная внешняя запись и не исправляется без точного разрешения.
- Dirty Gate 1 WIP может содержать полезные изменения и debt; нужен отдельный
  recovery/reuse audit до любого merge/cleanup.
- Existing local runtime и historical docs могут описывать разные revisions;
  exact Git revision и воспроизводимая проверка имеют приоритет.
- Активные записи Nobus Memory содержат stale wording «изменения ещё не
  применены» и неверно продвигают Gate 1 WIP. Официальный bridge доступен
  только для чтения; исправление требует отдельного разрешения и должно
  ссылаться на текущую `main` и открытый PR, не объявляя PR каноном.

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

## Proposed Nobus Memory pointer sync

```text
Nobus Space: public GitHub repository streetenergy63reshik-del/nobus-space;
protected main @ 8b896fb... is the current accepted published canon. PR #1 is
open and unmerged: docs/mvp1-thin-architecture, initial accepted head
d3a235e..., tree bf503ae...; it contains the thin Telegram Mini App + existing
Core roadmap, but is not main canon until separately authorized merge and SHA
readback. Gate 1 recovery remains HOLD/NOT_ACCEPTED and unpublished.
Freshness: 2026-08-25.
```

Memory update, push обновлённого head, изменение GitHub description, merge,
deploy, recovery, deletion и live/provider actions этой задачей не выполняются.
