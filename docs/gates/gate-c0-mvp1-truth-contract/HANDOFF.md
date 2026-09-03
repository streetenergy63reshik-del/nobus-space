# Gate C0 — единая истина и semantic contract

**Candidate verdict:** `C0 LOCAL CANDIDATE PASS / NOT PUBLISHED`, действителен
только вместе с независимыми L2/L3, привязанными в итоговом C0-чате к exact
result SHA/tree.
**Product verdict:** `MVP-1 PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / PATCH REQUIRED`
**Deployment identity:** `DEPLOYMENT REVISION UNVERIFIED`
**Program boundary:** `MVP-2 HOLD`

Этот файл — единственный C0 handoff/acceptance. Он не исправляет runtime defect,
не возвращает `MVP-1 READY` и не запускает автоматически C1, publication или
external effect.

Candidate `c2c97db725df13ee2e86d0a7fb0f4501f8c133f6` / tree
`0ef426ba6195d19724203ad6b6f9cac7621da15a` отклонён владельцем и
**superseded** этим rework. Он не является допустимой базой C1. Rework закрывает
четыре Major finding: model role не является authority; все source/target refs
проверяются относительно текущего durable intake; compound decision order
един; conditional predicate закрыт и server-evaluable.

Промежуточный freeze `078e2230927c66724415b5a0ca09c3e03ef91b18` / tree
`b06b9e162b8d2949f7d99ddf015d8ec2df43b722` также superseded: первый новый
L3 доказал, что schema допускала `APPROVAL_REQUIRED` при predicate
`FALSE/UNKNOWN`, scalar predicate result не закрывал несколько conditional
operations, а первый injection-case не имел противоположного server-owned
ground truth. Финальный contract запрещает approval для FALSE/UNKNOWN,
допускает не более одной conditional operation и проверяет injection при
`matching_count=0`; regression покрывает все три обхода.

Freeze `eb799cd0c495b5fd2b23251bc26eeffa62f54f4c` / tree
`0f0146845d690d6133c52a2d0da3eaf3dbf3e268` superseded во время L2: verified
predicate subject присутствовал в reference checks, но его usage не был явно
помечен `PREDICATE_SUBJECT`. Финальные corpus/tests требуют эту evidence-метку
для каждого conditional case.

## 1. Контракт результата C0

**Бизнес-результат:** владелец и следующий Gate получают одну доказанную версию
состояния MVP-1 и один обязательный контракт исправления semantic admission.

**В scope:** read-only Git/GitHub/runtime evidence; active status/index sync;
forward ADR; SemanticProposal/CoreDecision schema; Capability Registry; sanitized
gold corpus; issue C1–C6 mapping; governance checks; один local checkpoint.

**Вне scope:** production/runtime/code fixes, ASR replacement, Mini App/Bot/VPS/
Cloudflare/SQLite changes, C1, MVP-2, push/PR/merge/tag/deploy/Memory write.

**Приёмка:** exact base и source preservation; единый CURRENT; one Gate/one
chat; closed model contract без authority; registry CURRENT/TARGET; corpus;
issue ownership; sealed Gate 0; no production diff; L1/L2/L3.

## 2. Exact Git binding

| Поле | Значение |
|---|---|
| Repository | `C:\Хранилище\АГЕНТ\PROстранство\ОРКЕСТРАТОР\Code\nobus-orchestrator-dev` |
| C0 worktree | `.runtime/worktrees/mvp1-closure-c0-truth-contract` |
| Branch | `codex/mvp1-closure-c0-truth-contract` |
| Exact base | `f5a9119cc0aa1bcce735a3c608f9751747002694` |
| Base tree | `01f6399fbbeca20d4c956482776329a9ee8adc20` |
| Result SHA/tree | фиксируются итоговым сообщением этого C0-чата после создания единственного checkpoint; self-containing commit не дублирует собственный SHA |
| Publication | `NOT PUBLISHED` |

## 3. Source → claim → fact → disposition

| Source | Claim | Доказанный факт C0 | Disposition |
|---|---|---|---|
| direct owner request 2026-09-02 | text и voice-transcript эквивалентной transform-задачи ложно отклонены | owner acceptance reopened; ASR для voice завершился до одинакового отказа | **retain / current authority** |
| remote `refs/heads/main` | опубликованная ветка — release v1.0.1 | `f5a9119...`, tree `01f6399...` | **retain** |
| remote `refs/tags/v1.0.1` | tag указывает на published main | annotated object `1322e922...`, peeled commit `f5a9119...` | **retain** |
| GitHub API | `main` protected и release/checks опубликованы | branch `protected=true`; checks/status contexts `0`; GitHub Release API `404` | **update**: tag доказан, отдельный Release/check success — нет |
| published active docs | `MVP-1 READY` — текущий verdict | claim старше переоткрытой acceptance и остаётся на remote | **supersede locally**; `STALE PUBLISHED CLAIM / PUBLICATION PENDING AUTHORIZATION` |
| `telegram-live` checkout | deployed files соответствуют release | clean HEAD `f5a9119...`; task config указывает на его runner | **retain as configuration claim**, не runtime binding |
| scheduled task/process/health | runtime активен | task `Disabled`, `enabled=false`, last run `2026-09-02T14:33:44Z`, result `267014`; action-args SHA-256 `8282036e...ad6f5`; matching process отсутствует; public health/readiness `502` | **update**: current runtime inactive/unhealthy at readback |
| bounded supervisor log + authoritative SQLite | runtime работал 2 сентября | 18 stable events; latest safe event `17:38:42 MSK`; recent terminal jobs and fully acked outbox | **retain** as `LIVE RUNTIME OBSERVED` historical evidence |
| loaded runtime revision/config | deployed revision = release | active process/readback отсутствует | **update**: `DEPLOYMENT REVISION UNVERIFIED` |
| published code | rejection — только ASR defect | broad keyword/regex admission охватывает полный material до durable task | **supersede**: primary defect = semantic admission |
| ADR 0014 | typed message ingress, Core policy, voice confirmation | transport/trust invariants полезны; hints не дают semantic authority | **retain transport / supersede semantic hints** |
| ADR 0017 | один Core/state/effect authority | authority boundary сохраняется; модель не назначает route/permissions/risk | **retain authority / supersede model-authority interpretation** |
| ADR 0022 | thin Mini App + existing Core и delivery workflow | topology сохраняется; old six-slice/current READY process устарел | **retain topology / supersede closure process** |
| sealed Gate 0 | historical accepted evidence | 20/20 source hashes и весь каталог сохраняются byte-identical | **historical retain** |
| Nobus Memory project/decision cards | compact CURRENT/TARGET pointer | snapshot stale (`adf3bfbb...`, 26 августа), не authority C0 | **historical pointer; no write** |
| previous Codex chat `01a04371-d8f8-7561-afb5-6ecdaae31d9f` and handoff | release deployed/accepted | claim подтверждён для Git publication и earlier runtime evidence, но superseded новой acceptance | **historical claim** |
| dirty canonical checkout | newer local main/WIP — possible base | HEAD `f18a664...`, unrelated modified/untracked files | **exclude as base; preserve** |
| local docs 15/16 | proposed closure roadmap and management view | exact source hashes recorded, content reviewed, imported whole | **retain local / PUBLICATION HOLD** |

## 4. Конфликты до → после

| До C0 | После C0 candidate |
|---|---|
| active docs называли MVP-1 READY | единый current verdict `PUBLISHED / LIVE RUNTIME OBSERVED / ACCEPTANCE REOPENED / PATCH REQUIRED`; READY только historical/pre-incident или future C6 outcome |
| deployed release считался exact-bound по checkout/config claim | deployment revision отдельно `UNVERIFIED`; clean checkout не заменяет active readback |
| voice incident мог читаться как ASR quality | ASR success отделён; confirmed defect — semantic admission/routing |
| full-message keyword/regex фактически решал capability rejection | accepted target: model интерпретирует, deterministic Core решает по registry/policy |
| quoted/nested/negated content не имел строгой роли | model roles закрыты, но недоверенны; server-derived provenance доказывает direct owner boundary либо инертный material |
| модель/worker contracts могли смешивать interpretation и authority | `SemanticProposal` не имеет authority; отдельный `TrustedAdmissionContext` связывает intake/provenance/refs; `CoreDecision` server-derived |
| syntactically valid source/target ref мог читаться как доказательство | Core требует server issuance, current-intake membership, owner/tenant/conversation/revision и exact boundary; forged/stale/mismatch fail closed |
| compound precedence и conditional result были неполны | принят один порядок trust → prohibited → ambiguity → heterogeneous → implementation → approval → execute; typed predicate даёт TRUE/FALSE/UNKNOWN до approval/effect |
| implementation и policy могли смешиваться | registry разделяет `implementation_state` и `policy_state` |
| старые slices/R steps читались как множество task-чатов | один Gate = одна Codex-задача = один пользовательский чат; Txx/Cxx/R01–R47 внутренние |
| прежняя roadmap не учитывала reopened acceptance | active closure-roadmap содержит ровно C0–C6; MVP-2 HOLD |
| previous tests/smoke могли трактоваться как текущая product acceptance | сохранены как historical evidence; новая owner acceptance только C6 |

## 5. Forward ADR 0023

[ADR 0023](../../adr/0023-modality-neutral-semantic-admission-and-core-decision.md)
имеет статус `ACCEPTED TARGET`, действует только вперёд и не меняет sealed
historical bytes.

Точная supersession boundary:

- ADR 0014 retained: trusted typed intake, envelope/tenant/idempotency, voice
  transport and failure boundaries; superseded: keyword/hint-based semantic
  determination or refusal;
- ADR 0017 retained: single Core, state, queue, policy/effect authority;
  superseded: любое чтение model output как permissions/route/risk approval;
- ADR 0022 retained: thin Mini App, existing Core, delivery workflow, frozen
  full Gate 2A; superseded: pre-incident READY/current six-slice closure process;
- sealed Gate 0 retained byte-identical; его evidence не переносится на C0 bytes.

ADR фиксирует shadow rollout, decision/evidence comparison, fail-closed
privileged paths и rollback к последнему принятому admission path без выдачи
старого keyword veto за исправление.

## 6. Semantic contract 1.0.0

[Schema](semantic-contract.schema.json) задаёт три непересекающиеся closed
структуры (`additionalProperties=false`):

- model-derived `SemanticProposal`: `schema_version`, `interpretation_state`,
  `primary_goal`, `deliverables`, `constraints`, source refs/boundaries,
  `input_role`, `source_need`, `output_kind`, operations с ролями,
  `ambiguities`, один `clarification_question`; роль операции — только
  недоверенная интерпретация, а не authority bit;
- server-derived `TrustedAdmissionContext`: binding к current durable intake,
  owner/tenant/conversation/revision, provenance/boundary каждой операции,
  результаты reference validation и predicate evaluation;
- server-derived `CoreDecision`: digests proposal/context, одно решение
  `EXECUTE / CLARIFY / APPROVAL / UNAVAILABLE / REFUSE`, decision stage,
  predicate outcome, selected capability, policy evidence, safe user-visible
  state и явные запреты/разрешения TaskContract/effect.

Запрещённые model-output keys: `decision`, `capability`, `approval_required`,
`authorized`, `approved`, `permissions`, `risk`, `route`, `adapter`, `tenant`,
`actor`, `execute`. `answer_draft` также отсутствует. Conditional operation
обязана иметь закрытый typed predicate `material_item_state_exists` с
server-verified `subject_ref` и `item_state=overdue`; у остальных predicate
равен `null`, а v1 допускает не более одной conditional operation. Core
evaluator возвращает `TRUE/FALSE/UNKNOWN`; false/unknown не
создают TaskContract, approval или effect. Значение
`operation_kind` берётся из отдельного semantic vocabulary, а не из Capability
Registry ID; модель не может скрыто выбрать capability через operation name.
Source и target refs допускают только opaque server-issued `material://...`
или `target://...`; синтаксис не доказывает выдачу. Core сверяет issuance,
membership текущего intake, owner/tenant/conversation, revision/freshness и
boundary; raw material/path/URL не принимаются как ref. Для v1 multi-operation execution
разрешено только при одной distinct capability. Heterogeneous compound fail
closed для всей задачи как `UNAVAILABLE` с `selected_capability=null`; никаких
частичных TaskContract/effect. Обязательный first-match order одинаков в ADR,
schema, Registry, corpus и tests: `TRUST_VIOLATION`, `POLICY_PROHIBITED`,
`AMBIGUITY`, `HETEROGENEOUS_CAPABILITIES`, `IMPLEMENTATION_STATE`,
`APPROVAL_REQUIRED`, `EXECUTE_ALLOWED`.

## 7. Capability Registry 1.0.0

[Registry](capability-registry.v1.json) не выдаёт target за current:

| State | Capability IDs |
|---|---|
| CURRENT / ALLOWED | `task.answer.general`, `content.transform`, `input.voice.transcribe.local`, `task.status.read`, `artifact.owner.deliver` |
| TARGET / ALLOWED | `semantic.compile.modality_neutral`, `task.cancel` |
| FROZEN / ALLOWED | `web.public.read`, `owner.file.read` |
| FROZEN / REQUIRES_APPROVAL | `owner.file.create`, `calendar.event.write` |
| UNAVAILABLE / PROHIBITED | `security.secret.exfiltration` |
| UNAVAILABLE / REQUIRES_APPROVAL | `marketplace.campaign.write` |

Каждая запись содержит закрытое `semantic_operation_kinds` mapping,
owner-visible outcome, минимальный route/profile,
dependencies, effect type, approval requirement, authoritative success
evidence, safe failure, owning Gate, evidence refs и limitations. Core decision
order детерминирован и зафиксирован тем же закрытым массивом. Каждая capability
явно помечает privileged status и server-owned authority requirement; model
role никогда не заменяет provenance/policy. Unsupported capability не
становится разрешённой из-за слов пользователя.

## 8. Gold corpus

[Corpus](semantic-gold-corpus.v1.json) содержит 25 sanitized cases:

- direct task и равная text/voice-transcript пара;
- обезличенная incident regression и её text/voice pair;
- transform supplied material;
- quoted, nested, prompt-injection и recounted/mentioned-only instructions;
- negated operation и отдельная requested cancel;
- conditional operation с typed predicate и исходами TRUE/FALSE/UNKNOWN;
- predicate injection, которая остаётся инертным материалом;
- compound transform одной capability и heterogeneous compound с whole-task
  fail-closed без частичного effect;
- model `role=requested` внутри цитаты, который trusted provenance отклоняет;
- wrong tenant, missing current-intake membership, boundary substitution,
  syntactically-valid forged ref и stale ref для source/target binding;
- unavailable external read/write и marketplace write;
- ambiguity с одним конкретным clarification;
- prohibited secret exfiltration refusal.

Каждый case задаёт expected proposal, requested/mentioned-only sets,
TrustedAdmissionContext, CoreDecision, capability, approval expectation и
user-visible behavior. Proposal/context digests вычислены из canonical UTF-8
JSON. Несвязанные `#summary/#checklist` target fragments удалены. Corpus задаёт acceptance C1,
но не доказывает реализацию C1.

## 9. Confirmed findings → C1–C6

Единый детальный register:
[MVP-1-ISSUES.md](../../handoffs/MVP-1-ISSUES.md).

| Gate | Findings |
|---|---|
| C1 | false semantic reject; tool-less compiler/authority boundary |
| C2 | durable voice parity requalification; Russian ASR qualification; temp/privacy path |
| C3 | worker retry/authority, status completeness, hung-live recovery, multipart/source idempotency |
| C4 | Mini App expiry recovery, honest verified/success labels, complete Telegram/Mini App journey |
| C5 | ingress budgets/HSTS, backup/restore, temp/artifact cleanup, ops/rollback/security |
| C6 | exact deployment binding, docs/manual sync, frozen release, repeated owner acceptance |

Наличие historical CLOSED реализации не удаляет `REQUALIFY`: новые admission
bytes и reopened end-to-end acceptance требуют свежего evidence.

## 10. Active roadmap: семь Gate, семь чатов

| Gate = одна Codex-задача/чат | Выход |
|---|---|
| C0 — единая истина и контракт | этот local candidate + accepted exact SHA/tree |
| C1 — универсальное семантическое понимание | corpus PASS, compiler + deterministic Core decision |
| C2 — voice parity и ASR qualification | durable shared route + Russian bake-off |
| C3 — стабильность Core/backend/worker | failure/retry/state/status/recovery matrix PASS |
| C4 — завершённый frontend/user journey | Telegram/Mini App complete E2E PASS |
| C5 — operations/recovery/security | ops, backup/restore, cleanup, security, rollback PASS |
| C6 — frozen release и owner acceptance | exact publish/activate/readback + owner acceptance |

Txx/Cxx и R01–R47 — внутренние checkpoints. C1 начинается только новым чатом
от принятого exact C0 result SHA/tree; он не стартует от `origin/main` или
непринятого local checkpoint.

## 11. Verification record

### L1

Предварительный и финальный L1 выполняются на тех же bytes, которые затем
замораживаются как Git tree. Итоговый C0-ответ привязывает exact frozen commit,
tree и результаты команд. На pre-freeze bytes получено:

- governance/documentation pytest: `37 passed`; JSON parse: PASS;
- штатный JSON Schema validator: `75/75` positive documents accepted,
  `5/5` negative authority/predicate/approval/multi-conditional fixtures rejected;
- запрет authority-полей модели, model-role/provenance negative fixture,
  reference verifier negative matrix и typed predicate injection rejection;
- единый decision order, heterogeneous whole-task fail-closed, TRUE/FALSE/
  UNKNOWN predicate states, corpus digests и text/voice route parity;
- documentation tests подтвердили ADR numbering/journal и link/path integrity,
  единый CURRENT, C0–C6, one-Gate/one-chat и отсутствие production diff;
- sealed Gate 0: `59` tracked files, `0` byte mismatches с exact base;
- изменённые files: `0` secret-pattern findings, `0` production files;
- `git diff --check`: exit `0`; отдельный scan всех 20 candidate files:
  `0` trailing-whitespace findings;
- source editorial WIP docs 15/16 повторно совпал с pre-import SHA-256.

Schema validation выполняется штатным PowerShell draft-2020-12 validator без
установки новой зависимости. Exact frozen tree, final expected status и
независимые verdict L2/L3 привязываются итоговым C0-сообщением.

### Independent L2

Read-only reviewer воспроизводит Git/GitHub facts, CURRENT/supersession,
contract/registry/corpus, sealed Gate 0 и one-Gate/one-chat на frozen bytes.
Его exact verdict привязывается итоговым C0-сообщением к result SHA/tree.

### Adversarial L3

Read-only reviewer атакует quoted/nested/negated/conditional semantics,
model authority, keyword-derived unavailable, TARGET-as-CURRENT,
historical READY, premature MVP-2, chat fragmentation, unqualified ASR,
evidence-free success и contamination из dirty/live worktrees. Exact verdict
привязывается итоговым C0-сообщением к result SHA/tree.

## 12. Preservation and publication boundary

- sealed Gate 0 remains byte-identical;
- dirty canonical WIP remains in place and unmodified except by its owner;
- `telegram-live` remains clean and unmodified;
- docs 15/16 imported whole from recorded source hashes and remain
  `LOCAL EDITORIAL WIP / PUBLICATION HOLD`;
- no secret, raw Telegram payload, raw private text, audio or credential is in
  C0 artifacts/evidence;
- production code/runtime/state/config are unchanged.

Protected remote still contains the stale current READY claim. Until a future
authorized docs publication this remains `STALE PUBLISHED CLAIM / PUBLICATION PENDING AUTHORIZATION`.

**C0 PERFORMED NO PUSH / PR / MERGE / TAG / DEPLOY.**

## 13. Gate C1 handoff

В новом пользовательском чате C1:

1. read back accepted C0 result SHA/tree and this handoff;
2. implement only modality-neutral semantic admission from ADR 0023, включая
   server-derived `TrustedAdmissionContext` и reference verifier;
3. считать model role недоверенным и сохранять existing Core/queue/state/effect
   authority и Faster-Whisper;
4. реализовать exact decision order и typed predicate evaluator; не создавать
   partial TaskContract/effect для heterogeneous или FALSE/UNKNOWN condition;
5. run the 25-case C0 corpus as executable C1 acceptance, включая text/voice,
   provenance, forged/stale/wrong-boundary refs и predicate injection;
6. shadow old/new decisions before activation; fail closed for privileged paths;
7. keep C2–C6 and MVP-2 on HOLD;
8. stop for exact authorization before any external write/publication/deploy.

Не использовать непринятый local checkpoint или remote `main` как замену
accepted C0 result. Один C1 Gate целиком выполняется в одном новом чате.
