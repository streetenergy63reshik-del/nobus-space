# Nobus Space — CURRENT

**Актуально на:** 3 сентября 2026 года
**Текущий продуктовый verdict:** `MVP-1 PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / PATCH REQUIRED`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Следующая продуктовая линия:** `MVP-2 HOLD`

Это единственная активная статусная проекция. Релиз `v1.0.1` остаётся
опубликованным Git-фактом, а наблюдавшийся 2 сентября runtime — фактом
эксплуатации. Пользовательская проверка позже в тот же день переоткрыла
приёмку: одинаковый смысл, переданный текстом и после успешной расшифровки
голоса, был ошибочно отклонён как функция вне MVP-1. До исправления и новой
owner acceptance продукт не имеет текущего verdict `READY`.

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
- semantic admission до Core использует broad keyword/regex boundary и имеет
  подтверждённый false reject;
- historical release/owner acceptance доказательства сохраняются только как
  pre-incident evidence.

### ACCEPTED TARGET

Forward [ADR 0023](../adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
принимает modality-neutral canonical input, tool-less Semantic Task Compiler,
закрытый `SemanticProposal`, server-derived Capability Registry/CoreDecision и
решения `EXECUTE / CLARIFY / APPROVAL / UNAVAILABLE / REFUSE`. Existing Core,
queue, state и effect authority сохраняются.

### NOT IMPLEMENTED

- ADR 0023 pipeline и semantic compiler;
- deterministic mapping нового proposal к registry/policy;
- C1 corpus pass и shadow rollout;
- C2 русский ASR bake-off и доказанная text/voice parity;
- повторная полная C3–C6 квалификация и owner acceptance.

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
| C1 — универсальное семантическое понимание | semantic admission и deterministic Core decision | NOT STARTED; отдельный чат от exact C0 predecessor |
| C2 — voice parity и ASR qualification | общий text/voice Core-route и русский bake-off | HOLD до C1 |
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

Historical sealed Gate 0 сохранён byte-identical и не переиздан C0.

## 7. Workspace safety

| Контур | Роль C0 |
|---|---|
| canonical checkout `nobus-orchestrator-dev` @ `f18a664...` | dirty foreign/editorial WIP; read-only source, не base |
| `telegram-live` @ `f5a9119...` | clean published/live claim; read-only, не редактировался |
| `codex/mvp1-closure-c0-truth-contract` from `f5a9119...` | единственный C0 implementation worktree |
| dirty Gate 1 WIP @ `db0a24e...` | preserved `HOLD / NOT_ACCEPTED`; не импортировался |

До импорта двух editorial файлов зафиксированы исходные bytes:

- `docs/15-Продуктовая-дорожная-карта.md`: `200633` bytes,
  SHA-256 `92c8abb64aebdc3363157aae00961bccc47c3491b3d7e8ab38901a3c768716bc`;
- `docs/16-Управленческая-карта-разработки.html`: `84410` bytes,
  SHA-256 `eb447fa7a1264c9272e9bb6619d021b6b7692808bb2a4188a053b3257faede46`.

Они перенесены целыми файлами с повторной hash-проверкой. Исходный dirty
checkout, live worktree, production code/runtime/state и recovery refs не
изменялись.

## 8. Publication boundary и следующий чат

Protected `main` опубликовал C0 contract через PR #9 @ `70085f8...`, tree
`3a31914a...`; follow-up status-only PR публикует этот readback без изменения
semantic contract. Exact final protected-main SHA/tree фиксируются итоговым
C0-readback, поскольку self-containing commit не может включить собственный
SHA. Historical `MVP-1 READY` остаётся только в ancestry и superseded текущим
verdict; tag/release/deployment не изменялись.

C1 разрешён только в новом отдельном чате от exact final protected-main
SHA/tree из итогового C0-readback и этого handoff. C1 не стартует автоматически
от floating `origin/main`, не меняет ASR и не начинает MVP-2.

**C0 PERFORMED PR #9 + STATUS-ONLY PR / MERGES; NO TAG / NO DEPLOY / NO LIVE EFFECT.**
