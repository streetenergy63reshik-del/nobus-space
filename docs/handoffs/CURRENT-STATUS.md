# Nobus Space — CURRENT

**Актуально на:** 4 сентября 2026 года
**Текущий продуктовый verdict:** `C1 CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Следующая продуктовая линия:** `MVP-2 HOLD`

Candidate `381a1e54e6c2281fe335b2835972cc27ee9d486d` / tree
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — **REJECTED / SUPERSEDED**:
conditional-tail reference gap. L3 REJECT, L2 independently reproduced finding,
но без final ACCEPT из-за platform error. Прежний FINAL REVIEW PENDING для
этого SHA отменён; текущий pending относится только к новым repair bytes.

Candidate `9de145ccc1c456927623885212f8d5ac64ff8ef0` / tree
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED по
C1-B01/C1-B02; прежний PASS и reviews отменены. Replacement требует новых
exact L1/L2/L3, и этот статус не объявляет их результат заранее.

Это единственная активная статусная проекция. Локальный C1 candidate исправляет
ложный semantic reject и проходит новую exact security-квалификацию, но ещё не
опубликован и не активирован. Релиз `v1.0.1` остаётся опубликованным
Git-фактом, а наблюдавшийся 2 сентября runtime — фактом эксплуатации. До
отдельной publication authorization, последующих C2–C6 и новой owner
acceptance продукт не имеет verdict `READY`.

Thin MVP-1 topology с Telegram Mini App и одним существующим Core остаётся
привязана к
[ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md);
полный Gate 2A — **FROZEN / NOT CURRENT**.

## 1. Exact Git и GitHub readback C0

| Проверка | Доказанный факт |
|---|---|
| Repository | `streetenergy63reshik-del/nobus-space` |
| C0 contract publication merge (PR #9) | `70085f8bdf20d139edf042bffa2a1169daf6791c` |
| C0 contract publication tree | `3a31914ac9b1732ea8344aaa09cd7075506ce315` |
| Final protected `refs/heads/main` | exact status-only merge SHA/tree фиксируются remote readback в итоговом C0-сообщении; self-containing commit не дублирует собственный SHA |
| Annotated tag object `refs/tags/v1.0.1` | `1322e922968d938194f689851c204ac551e6822b` |
| Peeled `v1.0.1^{commit}` | `f5a9119cc0aa1bcce735a3c608f9751747002694` |
| Reachability | release commit `f5a9119...` является предком remote `main`; C0 merge commit содержит docs/contracts tree, tag не двигался |
| GitHub branch API | `main` сообщает `protected=true` |
| Protection details | endpoint детальных правил ответил `401`; точная текущая policy не доказана |
| Relevant PR | PR #9 merged publication commit `d25b1b4...` в `70085f8...`; follow-up status-only PR закрывает exact readback |
| Checks/status | PR #9 head/merge: workflow runs `0`, status contexts `0`; status-only PR проверяется отдельно перед merge; required checks не доказаны |
| GitHub Release object | API вернул `404`; доказан annotated Git tag, но не отдельная GitHub Release entity |

Remote readback после PR #9 подтвердил exact SHA/tree выше. Dirty canonical
checkout не является base или опубликованным каноном.

## 2. Runtime и deployment identity

Read-only preflight подтвердил:

- clean worktree `telegram-live` указывает на `f5a9119...`;
- Scheduled Task `NobusSpaceBot` настроена на runner из этого worktree, но на
  момент C0 была `Disabled` (`enabled=false`), без matching процесса; last run
  `2026-09-02T14:33:44Z`, last result `267014`; sanitized action arguments
  SHA-256 `8282036e5d7e7c070ff668a7484d80887a6e000ead1a4c98b23daa0c8ad6f5`;
- bounded supervisor log содержит 18 safe stable events, последнее —
  `2026-09-02 17:38:42 MSK`;
- authoritative SQLite содержит завершённые и failed jobs за 2 сентября, а
  outbox не имеет неподтверждённых доставок; raw private text, audio и payload
  не читались и не переносились в evidence;
- локальные readiness endpoints недоступны, public health/readiness возвращают
  `502`.

Это доказывает `LIVE RUNTIME OBSERVED`, но не доказывает текущий работающий
процесс и не связывает загруженные runtime bytes/config с exact release.
Следовательно, deployment revision остаётся `UNVERIFIED`, даже несмотря на
совпадение clean live worktree с release commit.

## 3. Acceptance incident и root-cause boundary

Owner evidence фиксирует два эквивалентных запроса: voice успешно прошёл ASR,
тот же смысл был передан текстом, и оба запроса получили ложный product отказ.
Задачей было преобразовать предоставленный материал в готовый промт, а не
исполнить перечисленные внутри материала операции.

Published `src/application/telegram_product.py` применяет broad
keyword/regex-проверку к полному сообщению до durable admission. Проверка не
имеет структурного различия между requested operation и quoted/nested/
mentioned-only material и может вернуть unavailable до создания задачи.
Поэтому основной confirmed defect — `FALSE_SEMANTIC_REJECT`; ASR не является
доказанным источником этого отказа. Исправление кода относится к C1, а не C0.

## 4. CURRENT, ACCEPTED TARGET и NOT IMPLEMENTED

### CURRENT

- published `v1.0.1`/`f5a9119...` содержит owner-bound Telegram Bot, Mini App,
  existing Core, durable queue/state/outbox, worker, result и artifact paths;
- text и локальный Faster-Whisper voice ingress существуют;
- runtime наблюдался 2 сентября, но сейчас не подтверждён активным health;
- опубликованный runtime всё ещё использует broad keyword/regex boundary и
  имеет подтверждённый false reject;
- historical release/owner acceptance доказательства сохраняются только как
  pre-incident evidence.

### LOCAL C1 GATE CANDIDATE

Ветка `codex/mvp1-closure-c1-semantic-compiler` от exact predecessor
`5feccfd...` реализует [ADR 0023](../adr/0023-modality-neutral-semantic-admission-and-core-decision.md):
modality-neutral canonical input, tool-less Semantic Task Compiler, закрытый
`SemanticProposal`, server-derived Capability Registry/CoreDecision и решения
`EXECUTE / CLARIFY / APPROVAL / UNAVAILABLE / REFUSE`. Existing Core, queue,
state и effect authority сохранены. Opaque refs привязаны к issuance,
owner/tenant/conversation, current intake revision и exact material boundary.
Server-delimited direct spans подтверждаются отдельным compiler pass, который
не получает quoted/nested/material text. Authority выдаётся только при
полной occurrence-level биекции operation kind, role и typed predicate
kind/arguments между основным и всеми direct-span proposals. Все direct
proposals understood и без ambiguity/question; extra/missing/excess duplicate
делают всю authority INERT. Порядок неважен, occurrences не переиспользуются. Model-selected refs не дают
authority и независимо проходят полный exact server verifier; отдельного
model alignment нет. Для единственного span, полностью
покрывающего direct owner text, повторно используется основной validated
proposal. Provider generation schema server-side сужается до exact refs и пар
ref/boundary текущего intake, но общий C0 schema и финальная Core validation не
изменяются.
ASCII/Unicode single quotes, inline/fenced code и nested delimiters отделяются
линейным bounded parser. Word apostrophes не являются цитатой; malformed
boundary делает весь intake inert. Duplicate occurrences не схлопываются. Structural
ledger ограничен 24 spans, совокупно компилируются не более 8 direct/tail
spans, а все compiler calls делят один admission-wide timeout. Хвост после
поддерживаемого overdue predicate отдельно проходит тот же tool-less compiler:
он должен дать одну matching unconditional requested operation без
predicate/ambiguity, иначе следует уточнение. До semantic matching его
source/target/predicate refs проходят тот же reference verifier; любой failure
попадает в итоговый context и даёт TRUST_VIOLATION раньше ambiguity/predicate,
без нового active binding, TaskContract или effect. Tail не добавляется в
multiset прямых команд. Корректные TRUE/FALSE/UNKNOWN outcomes сохранены.
Clarification принимается только как exact Telegram reply или по
opaque Mini App token; новый полный intent остаётся новым intent. Feature
flag штатного runner — default-off.
Один acceptance record и C2 handoff находятся в
[C1 gate package](../gates/gate-c1-semantic-task-compiler/ACCEPTANCE.md).

### NOT PUBLISHED / NOT IMPLEMENTED

- публикация и activation локального C1 candidate;
- production shadow rollout C1;
- C2 русский ASR bake-off и доказанная text/voice parity;
- повторная полная C3–C6 квалификация и owner acceptance.

Согласованная semantic kind substitution самим compiler остаётся ограниченным
`MEDIUM / non-blocking` риском качества для текущих `no_effect` capabilities.
Любая будущая effectful capability требует собственных server-verifiable
target/precondition/approval controls и новой квалификации boundary.

Faster-Whisper остаётся CURRENT. C0 не выбирает и не устанавливает новый ASR.

## 5. Единица управления и active roadmap

**Один Gate = одна Codex-задача = один пользовательский чат.** Txx/Cxx и
прежние R01–R47 — только внутренние tasks/checkpoints соответствующего Gate.
Исправления, повторные проверки и запрос точной внешней авторизации продолжают
тот же Gate-чат. Новый чат открывается только для следующего Gate от принятого
exact result SHA/tree и handoff.

| Gate | Единственный результат | Статус |
|---|---|---|
| C0 — единая истина и контракт | доказанный CURRENT и обязательный semantic contract | PUBLISHED / ACCEPTED |
| C1 — универсальное семантическое понимание | semantic admission и deterministic Core decision | CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING |
| C2 — voice parity и ASR qualification | общий text/voice Core-route и русский bake-off | HOLD до принятого опубликованного C1 |
| C3 — стабильность Core/backend/worker | queue/state/retry/recovery/status stability | HOLD до C2 |
| C4 — завершённый frontend/user journey | Telegram/Mini App input→result→artifact→recovery | HOLD до C3 |
| C5 — operations/recovery/security | воспроизводимые ops, backup/restore, rollback, security | HOLD до C4 |
| C6 — frozen release и owner acceptance | exact опубликованный active release и owner acceptance | HOLD до C5 |

Редакционная product roadmap и HTML-карта остаются
`LOCAL EDITORIAL WIP / PUBLICATION HOLD` и не входят в published tree.

## 6. C0 contract package

- [ADR 0023](../adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
  — forward semantic admission decision;
- [Semantic schema](../gates/gate-c0-mvp1-truth-contract/semantic-contract.schema.json)
  — closed version `1.0.0`, model output без authority-полей;
- [Capability Registry](../gates/gate-c0-mvp1-truth-contract/capability-registry.v1.json)
  — независимые `implementation_state` и `policy_state`;
- [Gold corpus](../gates/gate-c0-mvp1-truth-contract/semantic-gold-corpus.v1.json)
  — обезличенные C1 acceptance cases, не доказательство реализации;
- [C0 handoff](../gates/gate-c0-mvp1-truth-contract/HANDOFF.md) — единая
  передача следующему Gate;
- [issue register](MVP-1-ISSUES.md) — подтверждённые findings и C1–C6 owners.
- [C1 acceptance](../gates/gate-c1-semantic-task-compiler/ACCEPTANCE.md) и
  [C2 handoff](../gates/gate-c1-semantic-task-compiler/HANDOFF.md) — локальный
  frozen candidate и обязательная publication boundary.

Historical sealed Gate 0 сохранён byte-identical и не переиздан C0.

## 7. Workspace safety

| Контур | Роль C1 |
|---|---|
| canonical checkout `nobus-orchestrator-dev` | dirty foreign/editorial WIP; сохранён и не использован как base |
| `telegram-live` @ `f5a9119...` | clean published/live claim; read-only, не редактировался |
| `codex/mvp1-closure-c1-semantic-compiler` from `5feccfd...` | единственный C1 implementation worktree |
| dirty Gate 1 WIP @ `db0a24e...` | preserved `HOLD / NOT_ACCEPTED`; не импортировался |

Docs 15/16 отсутствуют в C1 predecessor/tree и не импортировались. Исходный
dirty checkout, live worktree, production config/runtime/state и recovery refs
не изменялись.

## 8. Publication boundary и следующий чат

Protected `main` exact predecessor C1 — `5feccfd...`, tree `480b2f85...`.
Локальный frozen C1 candidate остаётся вне GitHub до точной авторизации
владельца. Разрешённый будущий publication scope: non-force push exact branch,
один PR в `main`, merge и protected-main SHA/tree readback. Tag, GitHub Release,
deploy, activation и любые live effects в C1 запрещены.

C2 разрешён только в отдельном будущем чате от принятого опубликованного exact
protected-main SHA/tree C1 и
[handoff](../gates/gate-c1-semantic-task-compiler/HANDOFF.md), не от floating
`origin/main` и не от локального candidate.

**C1 CONDITIONAL-TAIL REPAIR CANDIDATE / EXACT REVIEW PENDING. NO TAG / NO DEPLOY / NO LIVE EFFECT.**
