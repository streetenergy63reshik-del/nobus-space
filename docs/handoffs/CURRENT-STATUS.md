# Nobus Space — CURRENT

**Актуально на:** 2 сентября 2026 года
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
| Live activation continuation | branch `codex/mvp1-g7-activation`; pre-fix parent `3daffc397e98b508fc364def273850b38158a319`; containing revision resolves with `git rev-parse HEAD`; public runtime **DEPLOYED / AWAITING OWNER SMOKE**, containing Git candidate **NOT PUBLISHED** |
| MVP-1 command-surface correction | branch `codex/mvp1-command-surface`; parent `a189ce1ac574df56bb8c934ceb7dd9839891b45e`; containing revision resolves with `git rev-parse HEAD`; **LOCAL CANDIDATE / NOT DEPLOYED / NOT PUBLISHED** |
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
- Public Mini App отвечает по `https://app.nobusspace.com`; Cloudflare
  Tunnel работает на Hostinger VPS, а restricted reverse SSH доставляет
  трафик к owner-PC `127.0.0.1:8765`. Core, SQLite, Telegram token и
  Codex на VPS не перенесены; existing x-ui/443 не изменены.
- Exact-owner private Telegram menu содержит web-app button `Nobus Space`
  на `https://app.nobusspace.com/`; default/global menu не изменялось.
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
  natural-text task через server-derived owner/tenant/actor, verified-owner-context
  idempotency, существующий Core admission и существующую
  `SQLiteTelegramState` queue; retry возвращает ту же task, rebinding fail closed.
- Mini App admission фиксирует encrypted job до Core task; enqueue failure не
  создаёт task/outbox, а restart повторно валидирует binding и восстанавливает
  exact prepared contract из существующего job.
- Server-derived task id детерминирован по tenant/request, а exact
  verified-owner/request envelope стабилен между короткими bearer-сессиями;
  точный retry после restart не размножает durable jobs, а content/authority
  rebinding fail closed.
- Exhausted dead-letter не повторяет Core admission: exact retry даёт safe
  unavailable без task/outbox и orphan PENDING state.
- Локальный continuation candidate добавляет channel-neutral product status,
  bounded events, tenant/task/revision-bound verified answer и один реальный
  deterministic UTF-8 artifact из existing tamper-evident outbox.
- Artifact связывает tenant/task/task revision/result revision/result digest,
  filename/MIME/size/content digest; Telegram и Mini App возвращают одинаковые
  bytes, а stale/tampered/cross-owner refs fail closed без path/existence leak.
- В содержащей локальной correction revision Telegram delivery до внешней
  отправки создаёт immutable owner-visible `.txt` в едином каталоге
  `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\NOBUS SPACE BOT\Проекты Telegram`.
  Это производная проекция existing SQLite/outbox, не вторая artifact DB;
  idempotent retry не дублирует файл, конфликт имени/bytes fail closed. Один
  локальный backfill из live SQLite создал `38` файлов (`29 921` bytes),
  повтор сохранил те же `38`, byte parity `PASS`; содержимое в evidence не
  выводилось. Live runtime пока использует предыдущую revision, поэтому новые
  результаты начнут автоматически попадать в папку только после deploy.
- Candidate собирает existing Telegram/Core/Codex runtime, Mini App
  FastAPI/Uvicorn boundary и static frontend в один process lifecycle. Он
  слушает только `127.0.0.1:8765`, имеет `/healthz`/`/readyz`, bounded startup
  и graceful shutdown; использует тот же `SQLiteStore` и durable control queue.
- `scripts/run_nobus_space_live.py` запускает Core и restricted reverse SSH
  в одном kill-on-close Windows Job Object. Task Scheduler `NobusSpaceBot`
  и health task активны; stop/start smoke доказал отсутствие orphan
  processes и восстановление public readiness.
- Содержащая command-surface correction оставляет в Telegram MVP-1 только
  обычные text/voice tasks и `/start`, `/status`, `/limit`, `/help`. `/task`,
  `/calendar`, `/research`, `/document`, `/download`, `/network`, `/file`,
  `/notes` и команды future-effect отклоняются до task/effect admission.
  Production runner больше не конструирует local-file, document/download,
  network, Google, Business Notes или Memory-write adapters. Их наличие в
  отдельных модулях не считается функцией MVP-1.
- Текущий deployed runtime основан на предыдущем candidate `a189ce1...` и ещё
  не содержит эту command-surface correction. До отдельного authorized deploy
  и Telegram profile write старые команды могут оставаться видимыми в live bot.
- Synthetic live Mini App smoke создал task
  `df41c71c-65a8-4ec1-9cf5-03bd2c5f83bb`: status `ready`, result revision `1`,
  result digest `sha256:634c2077fc6b4f5f5c59e52d67900eb477af3118da1494cd61a689466e9cc961`,
  artifact digest `sha256:2605fe75c9b69fe849e3f085f77530d3c28a383bd374cf06102818d60380875b`,
  `24` bytes. Durable outbox/Telegram receipt `acked`; public download вернул
  те же bytes/digest. Secrets/initData/bearer в evidence не записывались.
- Human owner 2 сентября открыл Mini App через exact private Telegram menu и
  создал task `729fec70-ecf1-4c70-8f7c-6e542fa0bba8`. Authoritative state
  подтвердил переход в `answered`, result revision `1` и два bounded events:
  задача реально прошла существующий Core/Codex, а не осталась только в UI.
  Smoke выявил Major usability defect: list не позволял идентифицировать
  задачу, а detail отрисовывался ниже длинного списка. Содержащая correction
  revision выводит отдельный bounded owner-visible title и short task id,
  открывает detail/create как отдельные bottom sheets и сохраняет title только в
  DPAPI-protected tenant/task/contract-bound field той же task snapshot. Bounded
  instruction входит в тот же encrypted payload и доступен только exact owner в
  detail; list его не получает, plaintext в SQLite не появляется, а legacy rows
  используют safe fallback.
  Повторный public synthetic smoke на code checkpoint `06395e9...` создал task
  `9243be1c-254e-4624-b8d8-b0e460e68e90`: owner detail вернул exact title и
  instruction, list сохранил instruction redaction, статус прошёл
  `queued -> ready`, получены два bounded events, expected verified answer и
  artifact revision `1`, `22` bytes,
  `sha256:7d470225e01ef8ce4faacd67974d02a9ecd1d41fff6f16a981c57bb630515b94`.
  Public health/readiness после deployment вернули `200`; secrets, raw initData
  и bearer в evidence не записывались. Остаётся визуальный owner smoke
  обновлённой карточки внутри Telegram.
- На неизменённых code bytes `fc43edf...` выполнен real Browser E2E через
  локальный Telegram SDK stub с подписанным test `initData`: create -> status ->
  bounded events -> verified answer -> artifact HTTP `200` -> client digest/size
  validation -> browser `downloadWillBegin`. Блокировка `/api/tasks*` дала
  только safe UI state `Nobus Space временно недоступен`.
- G4 verdict: отдельный external effect для принятого create/status/result/
  artifact journey не достижим, поэтому `ApprovalRequest NOT_REQUIRED`.
  Future approval/effect adapters не входят в активную MVP-1 composition.
- Candidate развёрнут и ожидает визуальный owner smoke, но ещё не является
  GitHub publication, final release или verdict о готовности всего MVP-1.
- Локальная редакционная roadmap и её HTML view остаются на owner publication
  hold; эта docs-only актуализация их не публикует и не меняет.

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
| Owner UI correction candidate, 2026-09-02 | exact code checkpoint `06395e9...`, tree `1c035c3...`: docs-inclusive target `109 passed`; full release-relevant suite `1381 passed`, `2 skipped`; adversarial recheck `7 passed`; runtime/backup/restore integration `76 passed`; verified backup, Python compileall, `git diff --check`, three real headless Edge renders and public task `9243be1c...` owner-detail/Core/Codex/result/artifact smoke: `PASS` | **DEPLOYED / AWAITING OWNER SMOKE**; no known Critical/Major implementation defect; not published in protected `main` |
| MVP-1 command-surface and artifact-projection correction, 2026-09-02 | red/green command proof: `23 passed`; complete Telegram surface/runner: `183 passed`; final Telegram/Mini App/effect-isolation/docs focused set: `262 passed`; artifact projection + parity/runner/docs: `257 passed`; release-relevant set excluding only frozen Gate 0/pre-Gate group: `1403 passed`, `2 skipped`, `5 deselected`, one known Starlette warning. The exact five deselected backup/restore mutex tests were rerun outside sandbox and all returned `RunnerAlreadyActive`, proving the deployed bot owns `Global\NobusSpaceBot`; they were not silently counted as green | containing revision on `codex/mvp1-command-surface`: **LOCAL CANDIDATE / NOT DEPLOYED / NOT PUBLISHED**; active command/effect surface defect closed; future Telegram results have one immutable owner-visible filesystem projection; live bot remains unchanged |
| Gate 0 integrity repair @ `a30a203f24a5cd9d123d7e9ae0d7b9eee4a8b343` | L1: source verifier/current/clean checkout `20/20`, impacted Gate 0 `24 passed`, integrity/docs `11 passed`, checkpoint `100 passed`, clean exact-byte/regression `7 passed`; independent L2 and adversarial L3 reproduced the frozen candidate | **SPECIFICATION_CONFLICT: CLOSED**; L1/L2/L3 `PASS`; **PUBLISHED** through PR #2; exact A/B reachability read back from `origin/main` |
| Publication merge | pre-publication checkpoint `100 passed`, `1 warning`; PR head exact `0612f1456bf050e54aac8bb2afc2c4f9a5b99328`; non-force merge with commit preservation | `205cd66d4094f59673e89aa8d616b7826f16f8b0`; accepted product/integrity content anchor |

Новая revision не объявляет собственный независимый verdict. Команды, counts,
literal commit/tree и reviewer verdict фиксируются в task/PR handoff,
привязанном к exact candidate SHA.

## Blockers and risks

- Главный product risk — спутать успешный synthetic live smoke с
  фактическим owner acceptance и опубликованным release. До этих границ
  используется `DEPLOYED / AWAITING OWNER SMOKE`.
- Развёрнутый Telegram profile/runtime пока опережает подтверждённую MVP-1
  поверхность. Локальная correction закрывает дефект в коде, но до её deploy и
  `setMyCommands` readback live menu не является исправленным.
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

| Product boundary | Статус на 2026-09-02 |
|---|---|
| Architecture / one Core, queue, state and effect authority | **ACCEPTED / PUBLISHED** |
| Owner auth, list/detail, task create backend | **CODE READY / PUBLISHED** |
| Static frontend for auth/list/detail/create | **OWNER UX CORRECTION / DEPLOYED; repeat smoke pending; NOT PUBLISHED** |
| Status/events/verified result | **DEPLOYED / AWAITING OWNER SMOKE; NOT PUBLISHED** |
| Real artifact metadata/download and Telegram byte parity | **DEPLOYED / synthetic live parity PASS; NOT PUBLISHED** |
| Conditional approval/recovery for a reachable effect | **NOT_REQUIRED; future effects excluded from MVP-1 runner** |
| Production composition, runner, config, health and autostart | **DEPLOYED / restart smoke PASS** |
| HTTPS ingress and Telegram menu activation | **HTTPS ACTIVE; command-profile correction NOT DEPLOYED** |
| Live create/status/result/artifact/restart smoke | **synthetic owner-bound PASS; human open/create PASS; corrected detail/result/artifact repeat pending** |
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

G2–G6 собраны; HTTPS и synthetic G7 активированы. Первый human smoke подтвердил
open/create/Core/Codex и выявил исправленный UX-дефект, затем аудит команд
обнаружил premature future routes. Ближайшая последовательность: заморозить и
развернуть command-surface correction -> прочитать Telegram commands обратно ->
visual exact-owner detail/result/artifact smoke -> protected-main publication ->
final release tag/readback. До этих доказательств вердикт не повышается до
`MVP-1 READY`.

## Completed published vertical slice

**Thin Mini App owner authentication + read-only task list/detail + создание
одной обычной текстовой задачи.**

Acceptance:

1. Telegram `initData` ограничивается по размеру/времени и проверяется для
   exact bot/owner, freshness и replay;
2. short-lived opaque session хранится только in-memory;
3. list/detail читаются из existing authoritative state, без второй DB/queue;
4. cross-owner/task ref и client-selected authority fail closed;
5. task create использует server-derived authority, owner-context-bound request id и
   существующие Core admission/authoritative state/durable queue;
6. same-request retry возвращает ту же task, rebinding отклоняется, а local Core
   unavailable не создаёт task/effect и даёт safe UI state.

Out of scope: единая result/artifact delivery, approvals/effects,
Core/token/poller migration, Agent Registry, Web IDE/shell/self-deploy и live
publication.

Срез опубликован в protected `main` через PR #2. Это подтверждённая Git
publication, но не live runtime release, deploy или разрешение следующему
срезу менять существующие Core/effect authority границы.

## Current deployed candidate and next boundary

`codex/mvp1-g7-activation` закрывает code path G2–G6 и развёрнут за public HTTPS.
Новая `codex/mvp1-command-surface` ограничивает Telegram функциями, доказанными
для MVP-1, но пока локальна. Следующая граница G7 — authorized deploy этого exact
candidate, Telegram command-profile readback и повторная проверка
detail/result/artifact. Затем требуются protected-main publication, final tag и
readback одного exact release SHA.

## Proposed Nobus Memory pointer sync

```text
Nobus Space: public GitHub repository streetenergy63reshik-del/nobus-space.
Live activation branch codex/mvp1-g7-activation is deployed at
https://app.nobusspace.com and AWAITING OWNER SMOKE, but is NOT PUBLISHED and
must not be promoted by Memory to MVP-1 READY. ADR 0022 remains active; architecture commit
ac0bc08e2cf13fdd67f8b31cd1abe1afd4763f03 remains reachable.
Gate 1 recovery remains HOLD/NOT_ACCEPTED and unpublished. Live worktree state
must be read from Git; WORKSPACE-INVENTORY records roles and the last audit.
```

Этот шаблон не разрешает Memory update, push, изменение GitHub description,
merge, deploy, recovery, deletion или live/provider actions.
