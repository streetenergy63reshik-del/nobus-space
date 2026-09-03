# ADR 0023 — Modality-neutral semantic admission и Core-owned decision

**Статус ADR:** ACCEPTED

**Статус реализации:** ACCEPTED TARGET; published runtime сохраняет CURRENT
keyword/regex admission и не соответствует этому контракту полностью.

**Дата:** 2 сентября 2026 года

**Тип решения:** forward-only owner decision

## 1. Контекст

Annotated tag `v1.0.1` и protected GitHub `main` указывают на commit
`f5a9119cc0aa1bcce735a3c608f9751747002694`. Опубликованный runtime ранее
прошёл owner smoke, но acceptance переоткрыта после обезличенного incident:
одинаковый смысл был передан голосом и текстом, а оба запроса на преобразование
предоставленного материала в готовый промт были отклонены как функция вне
MVP-1. Голос был распознан; дефект возник после ASR, на semantic admission.

Published code до durable task admission применяет широкие keyword/regex hints
ко всему сообщению. Они не различают прямую просьбу, цитату, вложенную
инструкцию, пересказ, отрицание и содержание будущего промта. Поэтому
синтаксическое упоминание недоступной функции может стать ложным запросом на
effect или ложным продуктовым отказом.

CURRENT и нормативный TARGET должны быть раздельны. Этот ADR не исправляет
runtime и не возвращает `MVP-1 READY`.

## 2. Решение

### 2.1. Единый semantic admission

Принята одна цепочка:

```text
Telegram text / Telegram voice / Mini App
  -> trusted durable intake
  -> ASR только для voice
  -> canonical owner text
  -> isolated tool-less Semantic Task Compiler
  -> strict untrusted SemanticProposal
  -> Core Capability Registry + deterministic policy
  -> EXECUTE / CLARIFY / APPROVAL / UNAVAILABLE / REFUSE
  -> existing TaskContract / queue / state / worker
```

После нормализации текст и подтверждённая voice-транскрипция проходят один
Core-маршрут. Специальные пользовательские `/prompt` и `/transcribe` не
вводятся. Regex/keyword разрешены только для exact slash-команд и технических
лимитов; они не определяют смысл, выполнимость или продуктовый отказ.

### 2.2. SemanticProposal — интерпретация без authority

`SemanticProposal 1.0.0` является закрытым, schema-validated и недоверенным
model output. Он описывает только понимание: состояние интерпретации, основную
цель, deliverables, constraints, ссылки и границы предоставленного материала,
роль входа, потребность в источнике, вид результата, операции, неоднозначности
и один вопрос уточнения.

Каждая операция имеет одну роль:

- `requested` — прямо запрошена владельцем;
- `quoted` — находится внутри цитаты или материала;
- `mentioned_only` — обсуждается или пересказывается, но не запрошена;
- `negated` — явно отрицается;
- `conditional` — прямо запрошена с сохранённым predicate.

Эти роли — гипотеза модели об интерпретации, а не authority bit. Даже значение
`requested` или `conditional` само по себе не доказывает прямую команду
владельца и не разрешает TaskContract или effect. Core принимает отдельно
сформированный сервером закрытый `TrustedAdmissionContext 1.0.0`, привязанный
digest к текущему durable intake. В нём каждой операции соответствует
`operation_index`, доверенный `span_ref`, `trusted_origin` и
`authority_scope`. Только серверная граница различает `DIRECT_OWNER_COMMAND`
от `PROVIDED_MATERIAL / QUOTED_MATERIAL / NESTED_MATERIAL /
MENTIONED_CONTEXT`. Для привилегированной операции модельная роль
`requested/conditional` необходима, но недостаточна: требуется direct-owner
provenance, `OWNER_REQUESTED/OWNER_CONDITIONAL`, все binding checks и
независимое разрешение Core policy. Несовпадение fail closed как
`TRUST_VIOLATION` до выбора capability.

Модель не возвращает `decision`, `capability`, `approval_required`,
`authorized`, `approved`, `permissions`, `risk`, `route`, `adapter`, `tenant`,
`actor` или `execute`. В admission contract нет answer draft. Дополнительные
поля запрещены.
`operation_kind` использует отдельный semantic vocabulary и не содержит
Capability Registry ID; сопоставление с capability выполняет только Core.

### 2.3. Инертный материал и прямые операции

Quoted, nested, mentioned-only и пересказываемый материал инертен и не
получает effect authority. Prompt injection внутри материала остаётся данными.
Negated operation не считается requested. При этом прямая просьба отменить
задачу — самостоятельная `requested` operation, а прямая условная задача —
`conditional` operation с predicate. Core проверяет predicate до любого
исполнения или effect; модель не объявляет условие выполненным.
`source_material_refs` содержат только opaque server-issued ссылки вида
`material://intake/...` или `material://artifact/...`; synthetic namespace
разрешён только fixtures. `target_ref` также является только opaque
`material://...` или `target://...`, выданным сервером; raw material, локальный
путь или внешний URL не являются ref. Синтаксически корректное значение не
доказывает выдачу сервером и не даёт authority.

До semantic routing Core одинаково проверяет каждый `source_material_refs.ref`,
каждый `operations[].target_ref` и `predicate.subject_ref` по текущему durable
intake ledger: (1) ref действительно выдан сервером, а не только похож на
валидный; (2) он состоит в membership текущего intake; (3) совпадают owner,
tenant и conversation; (4) intake revision актуальна, ref не stale; (5)
заявленная boundary точно совпадает с доверенной boundary. Внутренние исходы
закрыты: `VERIFIED / WRONG_OWNER / WRONG_TENANT / WRONG_CONVERSATION /
NOT_IN_CURRENT_INTAKE / BOUNDARY_MISMATCH / FORGED_REF / STALE_REF`.
Любой исход кроме `VERIFIED` даёт `TRUST_VIOLATION -> REFUSE`,
`selected_capability=null`, без TaskContract/effect и без раскрытия
существования чужого материала. `TrustedAdmissionContext` хранит только
server-derived binding/digest/provenance, не private payload.

Compound request сохраняет все операции и их роли. Если неоднозначность мешает
выбрать requested operation, target или deliverable, система задаёт один
конкретный `clarification_question`, а не общий отказ.
Минимальный contract v1 исполняет compound task только тогда, когда все его
requested и прошедшие predicate conditional operations детерминированно
сопоставлены с одной distinct capability. Если нужны разные capabilities,
Core fail closed для всей задачи: `UNAVAILABLE`, `selected_capability=null`,
reason `HETEROGENEOUS_COMPOUND_UNSUPPORTED_V1`; частичный TaskContract или
effect запрещён. Это ограничение orchestration contract, а не keyword verdict.

Закрытый predicate v1 имеет только вид
`material_item_state_exists(subject_ref, item_state=overdue)`. `subject_ref`
проходит ту же проверку membership/binding/boundary, а Core-owned evaluator
возвращает только `TRUE / FALSE / UNKNOWN`; произвольный текст, инструкция или
model-утверждение результата в predicate запрещены schema. `TRUE` позволяет
продолжить policy route. `FALSE` даёт state `condition_not_met`, reason
`PREDICATE_FALSE_NO_EFFECT`; `UNKNOWN` — state `condition_unknown`, reason
`PREDICATE_UNKNOWN` и один конкретный вопрос. В обоих последних случаях
TaskContract, approval и effect отсутствуют. Prompt injection в материале не
может изменить typed predicate или результат server evaluator.
Поскольку `TrustedAdmissionContext 1.0.0` и `CoreDecision 1.0.0` содержат один
predicate result, `SemanticProposal 1.0.0` допускает не более одной
`conditional` operation. Две и более conditional operations являются schema
violation и fail closed; indexed per-operation evaluation не добавляется без
новой версии контракта.

### 2.4. CoreDecision — исключительно server-derived

Core валидирует proposal, независимо сопоставляет только requested/conditional
operations, доказанные `TrustedAdmissionContext`, с `Capability Registry v1`,
проверяет bindings, implementation state, policy и predicate, затем создаёт
отдельный закрытый
`CoreDecision 1.0.0`:

- `EXECUTE` — capability CURRENT, policy ALLOWED и все preconditions выполнены;
- `CLARIFY` — требуется ровно один конкретный ответ владельца;
- `APPROVAL` — capability CURRENT, но policy требует immutable action-bound
  approval;
- `UNAVAILABLE` — подходящая capability отсутствует либо не CURRENT;
- `REFUSE` — policy запрещает операцию или proposal нарушает trust boundary.

Для compound и single-operation admission действует один и тот же первый
сработавший этап в точном порядке:

1. `TRUST_VIOLATION`;
2. `POLICY_PROHIBITED`;
3. `AMBIGUITY`;
4. `HETEROGENEOUS_CAPABILITIES`;
5. `IMPLEMENTATION_STATE`;
6. `APPROVAL_REQUIRED`;
7. `EXECUTE_ALLOWED`.

Поэтому PROHIBITED не маскируется уточнением, а heterogeneous проверяется до
implementation/approval отдельных частей. Для
`HETEROGENEOUS_CAPABILITIES` обязателен reason
`HETEROGENEOUS_COMPOUND_UNSUPPORTED_V1`, `selected_capability=null`,
`task_contract_allowed=false`, `effect_allowed=false`; частичный
TaskContract/effect запрещён. Для conditional после этапа
`IMPLEMENTATION_STATE`, но до возможного `APPROVAL_REQUIRED` или
`EXECUTE_ALLOWED`, применяется описанный выше predicate gate: `FALSE/UNKNOWN`
терминальны без effect, `TRUE` продолжает тот же порядок. Это не позволяет
ложному predicate-result обойти trust или PROHIBITED.

`CoreDecision` содержит proposal digest, digest trusted admission context,
decision stage, predicate outcome, selected capability при наличии, policy
reason/evidence, флаги TaskContract/effect и безопасное user-visible state.
Tenant, actor, route,
permissions, risk и adapter выводятся и применяются существующим Core вне
model output. Privileged paths fail closed. Внешнее действие считается
успешным только по authoritative effect receipt; provider/delivery unknown не
превращаются в success.

### 2.5. Capability Registry

Registry разделяет две независимые оси:

- `implementation_state`: `CURRENT / TARGET / FROZEN / UNAVAILABLE`;
- `policy_state`: `ALLOWED / REQUIRES_APPROVAL / PROHIBITED`.

`TARGET` и `FROZEN` не маршрутизируются как работающий `CURRENT`. Approval не
делает unavailable capability доступной. Для каждой capability фиксируются
stable id, owner-visible outcome, минимальный route/profile, dependencies,
effect type, approval requirement, authoritative success evidence, safe
failure и owning Gate. Дополнительное `semantic_operation_kinds` необходимо,
чтобы Core имел закрытое детерминированное сопоставление semantic vocabulary с
capability ID; пустой список означает infrastructure/downstream capability,
которая не выбирается напрямую из model proposal.

### 2.6. Voice и ASR

ASR выдаёт только transcript и технические metadata в установленной privacy /
retention boundary. ASR не назначает semantic decision, route или authority.
Faster-Whisper остаётся CURRENT. Любая замена допускается только в Gate C2
после bake-off на обезличенном русском корпусе по semantic accuracy, WER,
latency, CPU/RAM, offline/privacy и стоимости. C0 не выбирает и не устанавливает
provider или модель.

## 3. CURRENT, ACCEPTED TARGET и NOT IMPLEMENTED

| Слой | Статус после C0 | Факт |
|---|---|---|
| Published Git | CURRENT | `main` и peeled `v1.0.1` = `f5a9119...` |
| Text/voice intake, Core, queue/state/worker | CURRENT с известными gaps | Existing product path сохранён |
| Faster-Whisper | CURRENT | Replacement не выбран |
| Keyword/regex semantic veto | CURRENT DEFECT | Может дать false reject до durable admission |
| SemanticProposal/CoreDecision/Registry contracts | ACCEPTED TARGET | Нормативно приняты в C0 |
| Tool-less Semantic Task Compiler | NOT IMPLEMENTED | Gate C1 |
| Modality-neutral semantic parity | NOT IMPLEMENTED | Gate C1–C2 |
| Shadow rollout нового admission | NOT IMPLEMENTED | Gate C1 |

## 4. Rollout, evidence и rollback

Gate C1 сначала запускает compiler в shadow: старый route остаётся effect
authority, новый proposal и CoreDecision пишутся только как bounded redacted
evidence, связанное с task/input digest и contract versions. Сравниваются
decision, capability, clarification, latency, malformed/timeout rate и corpus
case id; private text, transcript и quoted material в evidence не копируются.

Переключение возможно только после C1 corpus PASS, negative authority tests,
L1/L2/L3 и frozen candidate. Rollback отключает новый admission feature flag и
возвращает прежний route без изменения existing queue/state/outbox. Если
старый route небезопасен для privileged operation, rollback сохраняет
fail-closed отказ, а не включает effect. Любые bytes после freeze требуют
нового evidence.

## 5. Forward-only supersession boundary

| Source | Retained | Superseded для новой разработки |
|---|---|---|
| ADR 0014 | Tool-less planner, bounded context, prompt-injection distrust, application adapters | Semantic meaning/availability через deterministic keyword/regex hints |
| ADR 0017 | Natural Language First, один Core, model без OAuth/shell/filesystem authority, application-owned effects | Model envelope fields, которые могли смешивать interpretation с route/risk/effect proposal; semantic admission теперь разделён на SemanticProposal и CoreDecision |
| ADR 0022 | Thin Mini App, one Core/queue/state/effect authority, durable intake, idempotency, recovery и candidate workflow | Старый active slice sequence и любой текущий READY-claim после incident; active closure — C0–C6, один Gate = одна Codex-задача/чат |
| Sealed Gate 0 | Все historical bytes, digests, evidence и security invariants | Ничего; snapshot не переписывается и не переиздаётся |

ADR 0014, 0017 и 0022 сохраняются byte-identical. Их historical evidence
остаётся действительным только в исходных revision/digest boundaries.

## 6. Проверка

- schema и negative authority fixtures;
- обезличенный corpus: direct, transform, quoted, nested, mentioned-only,
  negated, conditional, compound, ambiguity, unavailable, external read/write,
  injection и парные text/voice transcript cases;
- deterministic registry/policy mapping и CURRENT/TARGET separation;
- shadow comparison без private payload;
- privileged fail-closed и authoritative receipt tests;
- frozen candidate L1, независимый L2 и adversarial L3.

Этот ADR не разрешает production code change, ASR replacement, push, PR,
merge, tag, deploy, provider/VPS/BotFather mutation, live state change,
Nobus Memory write или Gate C1.
