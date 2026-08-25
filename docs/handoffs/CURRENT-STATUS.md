# Nobus Space — CURRENT

**Актуально на:** 25 августа 2026 года
**Lifecycle rule:** containing revision outside protected GitHub `main` is
`GATE_CANDIDATE`; after an authorized merge and exact reachability readback it
is part of `ACCEPTED_PUBLISHED_BASELINE`
**Active decision:** [ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)

Telegram Mini App и Telegram-оркестратор обязательны в MVP-1. Они используют
existing local Core, одну queue/state model и одну effect authority. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.

## Git binding

| Поле | Значение |
|---|---|
| Repository | `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev` |
| Candidate branch record | `docs/mvp1-thin-architecture` |
| Baseline `main` at candidate freeze | `8b896fbca9b23c8751d651d14a122506338b5827` |
| Stage-1 checkpoint | `6f2fa50` (`AGENTS.md` only) |
| Initial PR head before refresh | `d3a235e4db2257826d5a5c5661a709c442be981e`; tree `bf503ae0bb7d243e083055e2631084987af3c1c0` |
| Pull request record | [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1); live state and head must be read from GitHub |
| Containing revision | resolve with `git rev-parse HEAD`; canonical only if exact revision is reachable from protected remote `main` |
| Origin | public GitHub repository; live refs are not duplicated in this document |
| Protection snapshot, 2026-08-25 | PR + conversation resolution required; bypass, force-push and deletion disabled; required status checks not configured |

Git commit не может содержать собственный hash без циклической ссылки. Поэтому
этот файл фиксирует исходный snapshot и воспроизводимое правило binding, а не
самоаттестацию. Literal candidate commit/tree и независимый verdict фиксируются
во внешнем task/PR handoff. Текущий канон определяется live readback защищённой
remote `main` и проверкой достижимости содержащей revision; постоянный документ
не копирует подвижные PR/ref значения.

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
| Initial architecture candidate | `11 passed`; 20/20 hashes; diff/path/link/secret/stale-claim scans; independent L2/L3 | historical `PASS` @ `d3a235e...` / `bf503ae...` |
| Containing revision | docs tests; 20 hashes; diff/path/link/secret/stale-claim scans; distinct L2 and L3 | no self-verdict; read exact external handoff |

Новая revision не объявляет собственный независимый verdict. Команды, counts,
literal commit/tree и reviewer verdict фиксируются в task/PR handoff,
привязанном к exact candidate SHA.

## Blockers and risks

- Способ public HTTPS ingress/hostname не выбран; это один bounded
  implementation input следующего slice, не разрешение на VPS Core migration.
- Push, merge и другие внешние изменения всегда требуют отдельной точной
  авторизации; документ или локальный commit её не создаёт.
- Dirty Gate 1 WIP может содержать полезные изменения и debt; нужен отдельный
  recovery/reuse audit до любого merge/cleanup.
- Existing local runtime и historical docs могут описывать разные revisions;
  exact Git revision и воспроизводимая проверка имеют приоритет.
- Nobus Memory должна получать live Git pointer/status/freshness и никогда не
  продвигать candidate PR в канон без merge + exact `main` readback.

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
Nobus Space: public GitHub repository streetenergy63reshik-del/nobus-space.
Accepted published canon = <exact protected main SHA from live readback>.
ADR 0022 status = active only if its containing revision is reachable from
that SHA; otherwise candidate. Mention PR #1 only after live readback and only
while it is open. Gate 1 recovery remains HOLD/NOT_ACCEPTED and unpublished.
Freshness = <readback timestamp>.
```

Этот шаблон не разрешает Memory update, push, изменение GitHub description,
merge, deploy, recovery, deletion или live/provider actions.
