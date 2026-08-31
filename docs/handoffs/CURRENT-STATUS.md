# Nobus Space — CURRENT

**Актуально на:** 31 августа 2026 года
**Lifecycle rule:** containing revision outside protected GitHub `main` is
`GATE_CANDIDATE`; after an authorized merge and exact reachability readback it
is part of `ACCEPTED_PUBLISHED_BASELINE`
**Active decision:** [ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md)

**Owner priority:** в срочном порядке довести MVP-1 до полностью готового,
стабильно работающего business-product; code-ready backend или frontend slice
не является MVP verdict.

**Product verdict:** `MVP-1 IN PROGRESS / NOT PRODUCT READY`.

Telegram Mini App и Telegram-оркестратор обязательны в MVP-1. Они используют
existing local Core, одну queue/state model и одну effect authority. Полный
распределённый Gate 2A — **FROZEN / NOT CURRENT**.

## Git binding

| Поле | Значение |
|---|---|
| Repository | `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev` |
| Historical architecture candidate branch | `docs/mvp1-thin-architecture` |
| Baseline `main` at candidate freeze | `8b896fbca9b23c8751d651d14a122506338b5827` |
| Stage-1 checkpoint | `6f2fa50` (`AGENTS.md` only) |
| Initial PR head before refresh | `d3a235e4db2257826d5a5c5661a709c442be981e`; tree `bf503ae0bb7d243e083055e2631084987af3c1c0` |
| Pull request records | Architecture [#1](https://github.com/streetenergy63reshik-del/nobus-space/pull/1); Mini App + Gate 0 integrity [#2](https://github.com/streetenergy63reshik-del/nobus-space/pull/2); publication readback [#3](https://github.com/streetenergy63reshik-del/nobus-space/pull/3); product-readiness boundary [#4](https://github.com/streetenergy63reshik-del/nobus-space/pull/4) |
| Accepted product/integrity publication readback, 2026-08-28 | merge `205cd66d4094f59673e89aa8d616b7826f16f8b0`; exact Commit A and B reachable from protected `origin/main` after fetch/readback |
| Accepted protected-main base for this continuation | `d7e2b8275f20a1a261bbf541573f76db82240901`; fetched/read back before branch creation 2026-08-31 |
| Accepted architecture commit | `ac0bc08e2cf13fdd67f8b31cd1abe1afd4763f03`; reachable from accepted `main` |
| Thin Mini App source revisions | base `efb6be0324f70260284bb59e48cc798e37cd2fca`; read-only checkpoint `3771b1eac5a0a215d0fa65a60a9addaf7a72ab9a`; task-create checkpoint `a13243c677d03a0a4415504c720635d3d97092aa`; all reachable from the accepted publication merge |
| Local product candidate | branch `codex/mvp1-release-continuation`; containing revision `61b5a5ebbba100d666747cfc4c5b39b08a77a826`, tree `761c907292e37a778d617b3001f0687ce2e326ae`; frozen code `fc43edf098098e95099fa3882a0d97ca12ddf89b`, tree `a7da9d682c21b08aa18fe5482aa0b81f134d067e`; G2–G6 **VERIFIED LOCAL CANDIDATE / NOT PUBLISHED / NOT DEPLOYED** |
| Containing revision | resolve with `git rev-parse HEAD`; canonical only if exact revision is reachable from protected remote `main` |
| Origin | public GitHub repository; live refs are not duplicated in this document |
| Protection snapshot, read back 2026-08-31 | PR + conversation resolution required; admins enforced; bypass, force-push and deletion disabled; required status checks not configured |

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
- Локальный continuation candidate добавляет channel-neutral product status,
  bounded events, tenant/task/revision-bound verified answer и один реальный
  deterministic UTF-8 artifact из existing tamper-evident outbox.
- Artifact связывает tenant/task/task revision/result revision/result digest,
  filename/MIME/size/content digest; Telegram и Mini App возвращают одинаковые
  bytes, а stale/tampered/cross-owner refs fail closed без path/existence leak.
- Candidate собирает existing Telegram/Core/Codex runtime, Mini App
  FastAPI/Uvicorn boundary и static frontend в один process lifecycle. Он
  слушает только `127.0.0.1:8765`, имеет `/healthz`/`/readyz`, bounded startup
  и graceful shutdown; использует тот же `SQLiteStore` и durable control queue.
- На неизменённых code bytes `fc43edf...` выполнен real Browser E2E через
  локальный Telegram SDK stub с подписанным test `initData`: create -> status ->
  bounded events -> verified answer -> artifact HTTP `200` -> client digest/size
  validation -> browser `downloadWillBegin`. Блокировка `/api/tasks*` дала
  только safe UI state `Nobus Space временно недоступен`.
- G4 verdict: отдельный external effect для принятого create/status/result/
  artifact journey не достижим, поэтому `ApprovalRequest NOT_REQUIRED`.
  Existing approval/effect/reconciliation boundaries не менялись.
- Candidate не является GitHub publication, deploy или verdict о готовности
  всего MVP-1. HTTPS, BotFather menu, activation readback и live owner smoke ещё
  не завершены.
- Локальная редакционная roadmap и её HTML view остаются на owner publication
  hold; эта docs-only актуализация их не публикует и не меняет.
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
- На snapshot 31 августа зарегистрировано пять worktrees с разными ролями;
  точный live-состав определяется `git worktree list --porcelain`, а не этим
  подвижным числом. Роли и последний аудит описаны в
  [WORKSPACE-INVENTORY](WORKSPACE-INVENTORY.md).
- Локальный checkout `main` @ `f18a664...` содержит 20-path несвязанный WIP,
  включая непубликуемые roadmap/HTML; он не используется для этой публикации.
- Product candidate изолирован в clean `codex/mvp1-release-continuation`.
  Документационная актуализация изолирована в отдельном docs-only worktree от
  exact `d7e2b827...`; code/tests, sealed Gate 0 bytes и Gate 1 WIP не меняются.
- `gate-01-integration` удалён; его ветка, recovery refs, bundles и stash
  сохранены.

## Verification state

Профиль: `software-development`; риск: high; candidate обязан пройти один
coherent L1/L2/L3 по frozen bytes.

| Уровень | Проверка | Статус |
|---|---|---|
| Initial architecture candidate | `11 passed`; 20/20 hashes; diff/path/link/secret/stale-claim scans; independent L2/L3 | historical `PASS` @ `d3a235e...` / `bf503ae...` |
| Thin Mini App read-only checkpoint | `tests/test_miniapp.py`: `16 passed`; Mini App + SQLiteStore + legacy main subset: `81 passed`; replay/schema/backup focused set: `87 passed` | published checkpoint `3771b1e...`; reachable through PR #2 |
| Mini App task-create pre-fix full audit | full canonical `tests/`: `1500 passed`, `6 skipped`, `43 failed` outside changed layer (`39` historical Gate 0 verifier/stale-context, `1` checkout EOL, `3` Windows runtime-layout/permission) | exact pre-fix `4159accc4c9cd07656a8231529f67af4bb60ecfe`; evidence не переиспользуется после byte changes |
| Mini App task-create final-fix L1 | target Mini App: `24 passed`; Mini App/runtime/queue/recovery groups: `316 passed`; checkpoint set: `99 passed`, `1 failed` на описанном ниже Gate 0 `SPECIFICATION_CONFLICT` | published checkpoint `a13243c...`; Gate 0 conflict subsequently closed; reachable through PR #2 |
| Mini App G2 status/events/verified-result candidate | targeted recheck after review fixes: `91 passed`; final checkpoint: `384 passed`; local L1/L2/L3 `PASS`. Historical full-suite on earlier pre-review-fix WIP: `1562 passed`, `6 skipped`, `17 failed`; exact tree was not recorded and bytes then changed | exact `f18a664...`: **VERIFIED LOCAL CANDIDATE / NOT PUBLISHED**; full-suite evidence must not be rebound to this tree; not a product/release smoke |
| Local G2–G5 product candidate | G5 target/restart/rollback set: `207 passed`; real loopback Uvicorn static/health/readiness test: `PASS`; exact docs-inclusive `c8a59a3...` full `tests/`: `1551 passed`, `5 skipped`, `45 failed`; isolated historical Gate0/pre-Gate group with system temp: `188 passed`, `4 skipped`, `33 failed`; full release-relevant suite excluding only that historical group: `1374 passed`, `2 skipped` | historical G5 state; all `33` isolated failures classified below; superseded by the frozen G6 row |
| Frozen G6 local candidate | exact `fc43edf...` release-relevant suite: `1377 passed`, `2 skipped`; Telegram polling/runtime health: `31 passed`; final adversarial focused recheck: `4 passed`; compileall, `pip check`, `git diff --check` and bounded secret scan: `PASS`; real Browser create/status/events/result/artifact and fail-safe unavailable state: `PASS` | coherent L1, independent L2 and adversarial L3: `PASS`; no known Critical/Major defect; **VERIFIED LOCAL CANDIDATE / NOT PUBLISHED / NOT DEPLOYED** |
| Independent status-audit recheck, 2026-08-31 | focused auth/create/status/result/artifact/composition/Telegram/store set: `249 passed`, `1` known Starlette/httpx deprecation warning, explicit system temp; product worktree remained clean | reproduced on containing `61b5a5e...` with unchanged code checkpoint `fc43edf...`; complements, does not replace, the frozen G6 evidence |
| Gate 0 integrity repair @ `a30a203f24a5cd9d123d7e9ae0d7b9eee4a8b343` | L1: source verifier/current/clean checkout `20/20`, impacted Gate 0 `24 passed`, integrity/docs `11 passed`, checkpoint `100 passed`, clean exact-byte/regression `7 passed`; independent L2 and adversarial L3 reproduced the frozen candidate | **SPECIFICATION_CONFLICT: CLOSED**; L1/L2/L3 `PASS`; **PUBLISHED** through PR #2; exact A/B reachability read back from `origin/main` |
| Publication merge | pre-publication checkpoint `100 passed`, `1 warning`; PR head exact `0612f1456bf050e54aac8bb2afc2c4f9a5b99328`; non-force merge with commit preservation | `205cd66d4094f59673e89aa8d616b7826f16f8b0`; accepted product/integrity content anchor |

Новая revision не объявляет собственный независимый verdict. Команды, counts,
literal commit/tree и reviewer verdict фиксируются в task/PR handoff,
привязанном к exact candidate SHA.

## Blockers and risks

- Главный product risk — спутать готовность отдельного backend/frontend slice с
  готовностью MVP. До activation и owner acceptance используются только статусы
  `WIP`, `LOCAL CHECKPOINT`, `GATE CANDIDATE` или `PUBLISHED SOURCE SLICE`.
- Способ public HTTPS ingress/hostname не выбран; это один bounded
  implementation input следующего slice, не разрешение на VPS Core migration.
- Push, merge и другие внешние изменения всегда требуют отдельной точной
  авторизации; документ или локальный commit её не создаёт.
- Dirty Gate 1 WIP может содержать полезные изменения и debt; нужен отдельный
  recovery/reuse audit до любого merge/cleanup.
- Existing local runtime и historical docs могут описывать разные revisions;
  exact Git revision и воспроизводимая проверка имеют приоритет.
- Exact docs-inclusive checkpoint `c8a59a3...` получил полный rerun `tests/`:
  `1551 passed`, `5 skipped`, `45 failed`. Размещение первого pytest temp
  внутри source repo добавило `12` clone/topology failures. Повтор только
  historical `tests/gate0` + pre-Gate verifier с system temp дал точную группу
  `188 passed`, `4 skipped`, `33 failed`.
- Из этих `33`: `32` принадлежат frozen historical Gate 0 verifier и требуют
  старые source/evidence digests, старую Git/status topology или exact старый
  `.gitattributes`; это `VERIFIER_DEFECT / STALE_CONTEXT` для текущего ADR 0022
  release boundary. Один pre-Gate failure воспроизводит CRLF materialization
  только двух sealed source в этом старом Windows worktree —
  `ENVIRONMENT_FAILURE / checkout normalization`. Sealed evidence/catalog/source
  для MVP candidate не переписывались.
- Полный release-relevant набор на exact code bytes `fc43edf...`, исключающий
  только весь frozen `tests/gate0` и
  `tests/test_pre_gate1_architecture_integration.py`, прошёл: `1377 passed`,
  `2 skipped`, одна известная Starlette/httpx deprecation warning.
  Необъяснённых release-relevant failures нет.
- Browser trust preflight после требуемого restart дал `READY`. Real Browser
  E2E на `fc43edf...` прошёл create/status/events/verified-result/artifact и
  safe unavailable path. Первичный Browser `waitForEvent("download")` не выдал
  high-level event, но CDP readback подтвердил artifact fetch `200 text/plain`
  и `Page.downloadWillBegin` с безопасным filename; это `VERIFIER_DEFECT`, а не
  product failure.
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

## MVP-1 product readiness

| Product boundary | Статус на 2026-08-31 |
|---|---|
| Architecture / one Core, queue, state and effect authority | **ACCEPTED / PUBLISHED** |
| Owner auth, list/detail, task create backend | **CODE READY / PUBLISHED** |
| Static frontend for auth/list/detail/create | **CODE READY / PUBLISHED** |
| Status/events/verified result | **VERIFIED LOCAL CANDIDATE / NOT PUBLISHED** |
| Real artifact metadata/download and Telegram byte parity | **VERIFIED LOCAL CANDIDATE / NOT PUBLISHED** |
| Conditional approval/recovery for a reachable effect | **NOT_REQUIRED for accepted journey; existing effects unchanged** |
| Production composition, runner, config, health and autostart | **VERIFIED LOCAL CANDIDATE / NOT DEPLOYED** |
| HTTPS ingress and Telegram menu activation | **NOT ACTIVATED** |
| Live owner create/status/result/artifact/restart smoke | **NO EVIDENCE** |
| Final GitHub release tag/readback | **ABSENT** |
| Full MVP-1 business product | **IN PROGRESS / NOT PRODUCT READY** |

`MVP-1 READY` допускается только по одному exact release SHA, когда одновременно:

1. backend и frontend собраны одним production composition root;
2. Mini App открывается из Telegram exact owner через HTTPS;
3. create -> Core/Codex -> status -> verified result -> real artifact проходит
   end-to-end в Telegram и Mini App с одной task identity;
4. auth/tenant/replay/idempotency/failure/restart/recovery negatives проходят;
5. реально reachable effect либо закрыт как `NOT_REQUIRED`, либо проходит один
   immutable approval и reconciliation path;
6. frozen release candidate не имеет известных Critical/Major defects, все
   release-relevant suites зелёные, а полный L1, независимый L2 и adversarial
   L3 завершены;
7. exact SHA опубликован и активирован, owner smoke выполнен, health,
   backup/restore и rollback воспроизводимы, final tag прочитан обратно.

G2–G6 собраны и проверены локально. Ближайшая последовательность: отдельно
авторизованные HTTPS/menu/owner acceptance G7 -> release record/tag/readback G8.
Срочность не разрешает пропуск этих границ.

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

## Current local candidate and next vertical slice

Локальная `codex/mvp1-release-continuation` закрывает G2–G6: status, events,
verified result, real artifact parity, same-process product composition и
frozen assurance. Следующий product gate — G7: отдельно авторизованные public
HTTPS ingress/hostname, Telegram menu activation и bounded live owner smoke.

## Proposed Nobus Memory pointer sync

```text
Nobus Space: public GitHub repository streetenergy63reshik-del/nobus-space.
Accepted protected-main base for the 2026-08-31 local continuation =
d7e2b8275f20a1a261bbf541573f76db82240901. Architecture and published Mini App
auth/list/detail/create checkpoints are reachable. Local G2-G6 product
candidate 61b5a5ebbba100d666747cfc4c5b39b08a77a826, frozen code
fc43edf098098e95099fa3882a0d97ca12ddf89b, is NOT PUBLISHED/NOT DEPLOYED and
must not be promoted by Memory. ADR 0022 remains active; architecture commit
ac0bc08e2cf13fdd67f8b31cd1abe1afd4763f03 remains reachable.
Gate 1 recovery remains HOLD/NOT_ACCEPTED and unpublished. Live worktree state
must be read from Git; WORKSPACE-INVENTORY records roles and the last audit.
```

Этот шаблон не разрешает Memory update, push, изменение GitHub description,
merge, deploy, recovery, deletion или live/provider actions.
