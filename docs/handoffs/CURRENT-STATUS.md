# Nobus Space — CURRENT

**Актуально на:** 4 сентября 2026 года
**Текущий продуктовый verdict:** `C1 ACCEPTED / PUBLISHED / NOT DEPLOYED`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Следующая продуктовая линия:** `MVP-2 HOLD`

Candidate `381a1e54e6c2281fe335b2835972cc27ee9d486d` / tree
`ab8fa02cc6d358ba998acc0cc3b4ecd8862c7bc4` — **REJECTED / SUPERSEDED**:
conditional-tail reference gap. L3 REJECT, L2 independently reproduced finding,
но без final ACCEPT из-за platform error. Прежний FINAL REVIEW PENDING для
этого SHA отменён. Последующий frozen candidate 8e5e5fd… принят и опубликован.

Candidate `9de145ccc1c456927623885212f8d5ac64ff8ef0` / tree
`f7db924f46a1b5ff10694b0c2bc3f2c17e3cdcb1` — REJECTED / SUPERSEDED по
C1-B01/C1-B02; прежний PASS и reviews отменены. Replacement 8e5e5fd… получил
собственные exact L1 PASS / L2 ACCEPT / L3 ACCEPT.

Это единственная активная статусная проекция. C1 принят и опубликован через
[PR #11](https://github.com/streetenergy63reshik-del/nobus-space/pull/11):
product commit `2732a11122179c4197a74594dd0c8ba3ed9ec52d`, tree
`6a8f968f2b447a7a20d88321d8610adcb76c9cb9`. Он совпадает с tree проверенного
candidate `8e5e5fd3bf5680b5dbcf78a5f7de40da63ba93da`. C1 default-off и не
активирован. C2 — READY TO START / NOT STARTED. Релиз `v1.0.1` остаётся
историческим опубликованным Git-фактом; до C2–C6 и новой owner acceptance
весь продукт не имеет verdict `READY`.

Существующие проверки: semantic 316 PASS; impacted 762 PASS; release
1766 PASS / 2 skips / 1 historical deselect; L2 ACCEPT / L3 ACCEPT.
Полные docs/governance 35 PASS / 2 historical FAIL и первый безопасный
provider timeout сохранены, не засчитаны PASS; один unchanged retry — 5/5.
Точные binding, хеши и остаточные ограничения —
[EVIDENCE.json](../gates/gate-c1-semantic-task-compiler/EVIDENCE.json).
Документная синхронизация не повторяет L1–L3 C1 и не меняет product code.

Thin MVP-1 topology с Telegram Mini App и одним существующим Core остаётся
привязана к
[ADR 0022](../adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md);
полный Gate 2A — **FROZEN / NOT CURRENT**.

## 1. Исторический Git/GitHub readback C0

| Проверка | Доказанный факт |
|---|---|
| Repository | `streetenergy63reshik-del/nobus-space` |
| C0 contract publication merge (PR #9) | `70085f8bdf20d139edf042bffa2a1169daf6791c` |
| C0 contract publication tree | `3a31914ac9b1732ea8344aaa09cd7075506ce315` |
| Final C0 protected-main predecessor | `5feccfd7626d4382259c3488a9cfb3b3e6c48a0b`, tree `480b2f85978e94a8a5a470d09fe3f343a60849bc`; последующий C1 описан выше |
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

Исторический read-only preflight C0 подтвердил (не новая проверка live):

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

Release `v1.0.1` и legacy/default-off path `src/application/telegram_product.py` применяют broad
keyword/regex-проверку к полному сообщению до durable admission. Проверка не
имеет структурного различия между requested operation и quoted/nested/
mentioned-only material и может вернуть unavailable до создания задачи.
Поэтому основной confirmed defect — `FALSE_SEMANTIC_REJECT`; ASR не является
доказанным источником этого отказа. Исправление принято в opt-in C1 semantic
path; оно не доказывает исправление ещё не активированного live runtime.

## 4. CURRENT, ACCEPTED TARGET и NOT IMPLEMENTED

### Исторический runtime baseline (не C1 activation)

- published `v1.0.1`/`f5a9119...` содержит owner-bound Telegram Bot, Mini App,
  existing Core, durable queue/state/outbox, worker, result и artifact paths;
- text и локальный Faster-Whisper voice ingress существуют;
- runtime наблюдался 2 сентября, но сейчас не подтверждён активным health;
- опубликованный runtime всё ещё использует broad keyword/regex boundary и
  имеет подтверждённый false reject;
- historical release/owner acceptance доказательства сохраняются только как
  pre-incident evidence.

### ACCEPTED / PUBLISHED C1 (default-off)

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

### NOT ACTIVATED / NOT IMPLEMENTED

- activation опубликованного C1;
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
| C1 — универсальное семантическое понимание | semantic admission и deterministic Core decision | ACCEPTED / PUBLISHED / NOT DEPLOYED |
| C2 — voice parity и ASR qualification | общий text/voice Core-route и русский bake-off | READY TO START / NOT STARTED |
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
  [C2 handoff](../gates/gate-c1-semantic-task-compiler/HANDOFF.md) — принятый
  опубликованный C1 и условия перехода к C2.

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

C1 code publication завершена: PR #11 merged в `2732a11122179c4197a74594dd0c8ba3ed9ec52d`.
Readback подтвердил exact tree, C0 parent и protected main. CI status contexts
и workflow runs у PR #11 отсутствуют; это не новый PASS.
Текущий follow-up изменяет только статусную документацию. Его итоговый
protected-main SHA/tree и SHA-256 C1 HANDOFF/ACCEPTANCE передаются в промте C2
после merge; собственный будущий SHA в этот документ не записывается.
Tag, GitHub Release, deploy, activation и live effects не выполнялись.

C2 разрешён только в отдельном будущем чате от принятого опубликованного exact
protected-main SHA/tree C1 и
[handoff](../gates/gate-c1-semantic-task-compiler/HANDOFF.md), не от floating
`origin/main` и не от локального candidate.

**C1 ACCEPTED / PUBLISHED / NOT DEPLOYED. NO TAG / NO DEPLOY / NO LIVE EFFECT.**
