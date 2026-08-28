# Nobus Space — CURRENT

**Актуально на:** 28 августа 2026 года
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
| Pull request records | Architecture [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1); Mini App + Gate 0 integrity publication [#2](https://github.com/streetenergy63reshik-del/nobus-space/pull/2) |
| Accepted product/integrity publication readback, 2026-08-28 | merge `205cd66d4094f59673e89aa8d616b7826f16f8b0`; exact Commit A and B reachable from protected `origin/main` after fetch/readback |
| Accepted architecture commit | `ac0bc08e2cf13fdd67f8b31cd1abe1afd4763f03`; reachable from accepted `main` |
| Thin Mini App source revisions | base `efb6be0324f70260284bb59e48cc798e37cd2fca`; read-only checkpoint `3771b1eac5a0a215d0fa65a60a9addaf7a72ab9a`; task-create checkpoint `a13243c677d03a0a4415504c720635d3d97092aa`; all reachable from the accepted publication merge |
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
- В содержащей локальной revision реализован thin Mini App read-only slice:
  exact-bot/owner initData verification, freshness/future skew, durable replay
  digest, short hashed in-memory session, tenant-scoped list/detail и safe
  unavailable UI.
- Новый boundary читает существующий `SQLiteStore`/`DurableTaskProjection`, не
  создаёт вторую БД, queue, policy/effect plane и не использует `src/main.py`.
- В содержащей локальной revision `POST /api/tasks` создаёт одну bounded
  natural-text task через server-derived owner/tenant/actor, session-bound
  idempotency, существующий Core admission и существующую
  `SQLiteTelegramState` queue; retry возвращает ту же task, rebinding fail closed.
- Mini App admission фиксирует encrypted job до Core task; enqueue failure не
  создаёт task/outbox, а restart повторно валидирует binding и восстанавливает
  exact prepared contract из существующего job.
- Server-derived task id детерминирован по tenant/request, а exact
  session/request envelope стабилен; точный retry до admission не размножает
  durable jobs, а content/session rebinding fail closed.
- Exhausted dead-letter не повторяет Core admission: exact retry даёт safe
  unavailable без task/outbox и orphan PENDING state.
- Live HTTPS/provider/BotFather/Telegram menu/runtime не проверялись и не
  изменялись.

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
- Финальный реестр Git содержит только канонический `main` и этот сохранённый
  worktree. `gate-01-integration` удалён; его ветка оставлена.
- Recovery refs, bundles и stash сохранены. До этого документационного
  checkpoint рабочий каталог был чист; checkpoint меняет только два handoff.

## Verification state

Профиль: `software-development`; риск: high; candidate обязан пройти один
coherent L1/L2/L3 по frozen bytes.

| Уровень | Проверка | Статус |
|---|---|---|
| Initial architecture candidate | `11 passed`; 20/20 hashes; diff/path/link/secret/stale-claim scans; independent L2/L3 | historical `PASS` @ `d3a235e...` / `bf503ae...` |
| Thin Mini App read-only checkpoint | `tests/test_miniapp.py`: `16 passed`; Mini App + SQLiteStore + legacy main subset: `81 passed`; replay/schema/backup focused set: `87 passed` | published checkpoint `3771b1e...`; reachable through PR #2 |
| Mini App task-create pre-fix full audit | full canonical `tests/`: `1500 passed`, `6 skipped`, `43 failed` outside changed layer (`39` historical Gate 0 verifier/stale-context, `1` checkout EOL, `3` Windows runtime-layout/permission) | exact pre-fix `4159accc4c9cd07656a8231529f67af4bb60ecfe`; evidence не переиспользуется после byte changes |
| Mini App task-create final-fix L1 | target Mini App: `24 passed`; Mini App/runtime/queue/recovery groups: `316 passed`; checkpoint set: `99 passed`, `1 failed` на описанном ниже Gate 0 `SPECIFICATION_CONFLICT` | published checkpoint `a13243c...`; Gate 0 conflict subsequently closed; reachable through PR #2 |
| Gate 0 integrity repair @ `a30a203f24a5cd9d123d7e9ae0d7b9eee4a8b343` | L1: source verifier/current/clean checkout `20/20`, impacted Gate 0 `24 passed`, integrity/docs `11 passed`, checkpoint `100 passed`, clean exact-byte/regression `7 passed`; independent L2 and adversarial L3 reproduced the frozen candidate | **SPECIFICATION_CONFLICT: CLOSED**; L1/L2/L3 `PASS`; **PUBLISHED** through PR #2; exact A/B reachability read back from `origin/main` |
| Publication merge | pre-publication checkpoint `100 passed`, `1 warning`; PR head exact `0612f1456bf050e54aac8bb2afc2c4f9a5b99328`; non-force merge with commit preservation | `205cd66d4094f59673e89aa8d616b7826f16f8b0`; accepted product/integrity content anchor |

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
- `SPECIFICATION_CONFLICT: CLOSED` в опубликованном Commit A
  `a30a203f24a5cd9d123d7e9ae0d7b9eee4a8b343`. Причина: catalog связывал три
  source с CRLF-вариантами и ещё четыре с SHA, отсутствующими в истории пути,
  тогда как Git blobs и `.gitattributes` требуют LF. Владелец нормативно выбрал
  exact blobs, общие для `origin/main` @ `adf3bfbb601a12182c420a720b16459c15970da4`
  и исходного HEAD `a13243c677d03a0a4415504c720635d3d97092aa`, с LF как canonical EOL и
  разрешил исправить семь catalog SHA без изменения source content.
- Commit A исправляет семь entries и только их прямые current
  digest/component/golden bindings; historical evidence, verdict и submissions
  не переизданы. Все 20 source Git blobs идентичны исходному HEAD и
  `origin/main`; current Windows worktree и clean checkout с
  `core.autocrlf=true` дают LF и exact catalog match `20/20`. L1, независимый L2
  и adversarial L3: `PASS`; Mini App, Core, runtime и queue не изменены.
  Publication state: **PUBLISHED** через PR #2 и merge
  `205cd66d4094f59673e89aa8d616b7826f16f8b0`. Fetch/readback подтвердил
  достижимость exact Commit A `a30a203f24a5cd9d123d7e9ae0d7b9eee4a8b343`
  и документационного Commit B
  `0612f1456bf050e54aac8bb2afc2c4f9a5b99328` из `origin/main`.
- Nobus Memory должна получать live Git pointer/status/freshness и никогда не
  продвигать candidate PR в канон без merge + exact `main` readback.

## Completed published vertical slice

**Thin Mini App owner authentication + read-only task list/detail + создание
одной обычной текстовой задачи.**

Acceptance:

1. Telegram `initData` ограничивается по размеру/времени и проверяется для
   exact bot/owner, freshness и replay;
2. short-lived opaque session хранится только in-memory;
3. list/detail читаются из existing authoritative state, без второй DB/queue;
4. cross-owner/task ref и client-selected authority fail closed;
5. task create использует server-derived authority, session-bound request id и
   существующие Core admission/authoritative state/durable queue;
6. same-request retry возвращает ту же task, rebinding отклоняется, а local Core
   unavailable не создаёт task/effect и даёт safe UI state.

Out of scope: единая result/artifact delivery, approvals/effects,
Core/token/poller migration, Agent Registry, Web IDE/shell/self-deploy и live
publication.

Срез опубликован в protected `main` через PR #2. Это подтверждённая Git
publication, но не live runtime release, deploy или разрешение следующему
срезу менять существующие Core/effect authority границы.

## Next vertical slice

**Единый статус и безопасное получение результата/артефакта через Telegram и
Mini App** с owner/tenant/task/revision binding и без раскрытия локального пути,
raw payload или данных другого tenant.

## Proposed Nobus Memory pointer sync

```text
Nobus Space: public GitHub repository streetenergy63reshik-del/nobus-space.
Accepted product/integrity publication anchor =
205cd66d4094f59673e89aa8d616b7826f16f8b0 from PR #2 and 2026-08-28
fetch/readback. Exact Gate 0 repair A/B and Mini App checkpoints are reachable
from protected main. ADR 0022 is active; architecture commit
ac0bc08e2cf13fdd67f8b31cd1abe1afd4763f03 remains reachable.
Gate 1 recovery remains HOLD/NOT_ACCEPTED and unpublished. Registered
worktrees: canonical main + preserved gate-01-acceptance.
```

Этот шаблон не разрешает Memory update, push, изменение GitHub description,
merge, deploy, recovery, deletion или live/provider actions.
