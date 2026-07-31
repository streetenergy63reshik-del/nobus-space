# Gate 0 — Product Contract и Baseline Evidence Architecture

**Статус документа:** TARGET DESIGN
**Статус Gate 0:** NOT IMPLEMENTED / NOT PASS
**Каноническая база design:** `9d816b35d3f419b42e24ad09ae6aadc92c33db43`
**Дата:** 28 июля 2026 года
**Владелец решения:** владелец продукта Nobus Space
**Исследовательское основание:** [`RESEARCH.md`](RESEARCH.md)

## 0.1. Интеграционное изменение ADR 0020

Gate 0 обязан включить в Product Contract и corpus обязательный Gate 2A:
полноценный Mini App, `development` intent, specialist worker profiles,
Agent Registry и ранний server foundation. Текущий exact fingerprint/evidence,
созданный до синхронизации канонических документов 12–13, не является основанием
для commit/PASS и должен быть заново сгенерирован и проверен тем же Gate 0
pipeline. Это изменение TARGET, а не доказательство реализации.

## 1. Нормативный язык

В этом документе:

- **MUST / ОБЯЗАН** — обязательное условие PASS;
- **MUST NOT / ЗАПРЕЩЕНО** — нарушение блокирует Gate;
- **SHOULD / СЛЕДУЕТ** — рекомендуемое решение; отклонение требует
  зафиксированного обоснования;
- **MAY / МОЖЕТ** — допустимый, но необязательный вариант.

Документ определяет TARGET Gate 0. Он не изменяет `CURRENT-STATUS.md`, не
подтверждает живой runtime и не разрешает реализацию следующих Gate.

## 2. Продуктовый результат Gate 0

### 2.1. Outcome

После PASS Gate 0 владелец и любой следующий Gate должны иметь один
воспроизводимый ответ на четыре вопроса:

1. Что Nobus Space доказанно умеет сейчас?
2. Какой exact product behavior должен быть достигнут в MVP-1?
3. По каким данным, контрактам и критериям это будет проверяться?
4. К каким exact repository/runtime/config/DB состояниям относятся утверждения?

Gate 0 создаёт:

- свежий и машиночитаемый Baseline Evidence Pack;
- замороженный Product Contract;
- канонический обезличенный corpus natural text/voice requests;
- contract/eval fixtures и golden outputs;
- architecture fitness contracts;
- формальный handoff Gate 1–8.

### 2.2. Пользовательская ценность

Gate 0 не добавляет новую кнопку или интеграцию. Его продуктовая ценность —
предотвратить:

- повторную реализацию уже существующего кода;
- расхождение Google и local document behavior;
- ложное объявление TARGET как CURRENT;
- регрессии natural language routing;
- небезопасные эффекты из-за неоднозначных owner-команд;
- зависимость приёмки от субъективного ответа модели;
- выпуск runtime, который нельзя связать с exact code/config/DB evidence.

### 2.3. Non-goals

Gate 0 MUST NOT:

- реализовывать `IntentEnvelope` или шесть document contracts в production code;
- менять текущий parser, routing, Google adapters или Telegram behavior;
- создавать server Core, Bridge или Google writeback;
- создавать новый eval/spec/agent framework;
- внедрять Promptfoo, OpenTelemetry, Langfuse или другой stateful backend;
- менять runtime, Scheduler, DB, credentials, Google или Telegram data;
- объявлять старый local Gate 0 доказательством нового hybrid Gate 0;
- обновлять `docs/12`, ADR или `CURRENT-STATUS.md` до cross-Gate review;
- создавать real owner/client corpus;
- выполнять deployment, remote или push.

## 3. Неподвижные принципы Gate 0

1. **CURRENT отдельно от TARGET.**
2. **Нормативный документ отдельно от runtime evidence.**
3. **Один Pydantic contract source; параллельные модели запрещены.**
4. **Deterministic oracle раньше model grader.**
5. **Canonical corpus локален, обезличен и переносим.**
6. **Deny и tenant boundary проверяются до content/model access.**
7. **Exact evidence важнее устного или Markdown-утверждения.**
8. **Неизвестное состояние — `UNVERIFIABLE` или `BLOCKED`, не PASS.**
9. **Инструменты являются сменяемыми consumers открытых артефактов.**
10. **Gate 0 замораживает смысл, но не реализует Gate 1–8 заранее.**

## 4. Source-of-truth hierarchy

### 4.1. Нормативная иерархия

Для требований действует иерархия `docs/README.md`:

1. безопасность, права и ближайшие `AGENTS.md`;
2. accepted ADR;
3. документы 01–10;
4. принятый продуктовый TARGET документа 12;
5. CURRENT handoff и README;
6. кодовые комментарии, research и исторические материалы.

Research объясняет решение, но не становится каноном автоматически.

### 4.2. Иерархия фактов CURRENT

Для утверждения о CURRENT используется другой порядок:

1. свежий прямой read-only runtime/process/DB/config evidence;
2. exact loaded artifact и его digest/commit provenance;
3. тесты на exact commit и environment;
4. фактически присутствующий код;
5. `CURRENT-STATUS.md`;
6. исторический handoff или research.

Нижний уровень не может отменить противоречие верхнего. Runtime evidence не
может изменить нормативную архитектуру, а архитектурный документ не может
объявить runtime работающим.

### 4.3. Evidence layers

Baseline MUST хранить независимо:

| Layer | Идентификатор | Что доказывает |
|---|---|---|
| `documentation` | commit + required blob digests | Какой текст был канонической базой |
| `repository` | worktree HEAD, branch/ref, dirty manifest | Какой код и локальные изменения исследованы |
| `runtime_release` | runtime worktree/artifact commit и digest | Из какого release source должен быть runtime |
| `process` | executable/module/config digest, start time, PID evidence | Что фактически запущено |
| `scheduler` | task/action/principal/trigger digest | Как runtime должен запускаться/перезапускаться |
| `database` | schema/migration/integrity/state aggregates | С каким durable state работает runtime |
| `configuration` | safe config/registry digests | Какие policy/scope значения применяются |
| `dependencies` | installed inventory и lock digests | На каком software environment выполнена проверка |
| `tests` | collection/result/evidence digest | Какие проверки пройдены на exact inputs |
| `external_capabilities` | fresh status/evidence ref | Что доказано про Google/Telegram/provider/Bridge |

### 4.4. Conflict policy

При конфликте:

1. обе версии сохраняются;
2. ставится `CONTRADICTORY`, а не выбирается удобная;
3. указываются affected claims и Gate;
4. до reconciliation соответствующий capability не может иметь `CURRENT`;
5. исправление создаёт новую evidence revision;
6. старые L1/L2/L3 не переносятся.

## 5. Baseline Evidence Pack

### 5.1. Общий contract

Baseline Evidence Pack MUST быть каноническим JSON UTF-8:

- schema: `nobus.gate0.baseline.v1`;
- `additionalProperties=false`;
- timestamps: RFC 3339 UTC;
- digest: `sha256:<64 lowercase hex>`;
- unknown enum/field и `bool` вместо integer запрещены;
- массивы имеют определённый порядок либо нормализуются перед digest;
- secrets, raw environment, command line и document content запрещены;
- каждый nested record имеет `status`, `observed_at` и `evidence_refs`;
- верхний `baseline_digest` вычисляется существующим
  `canonical_json_digest` без самого поля digest.

Нормативная форма:

```yaml
schema: nobus.gate0.baseline.v1
baseline_id: uuid
gate: 0
scope: nobus-space-mvp1
capture:
  started_at: utc datetime
  completed_at: utc datetime
  collector_identity: non-secret stable ref
  host_ref: opaque host ref
  policy_version: string
  method_version: string
documentation: DocumentationEvidence
repository: RepositoryEvidence
runtime_release: RuntimeReleaseEvidence
processes: [ProcessEvidence]
scheduler: [SchedulerEvidence]
databases: [DatabaseEvidence]
configuration: ConfigurationEvidence
dependencies: DependencyEvidence
tests: TestEvidence
external_capabilities: [ExternalCapabilityEvidence]
claims: [CapabilityClaim]
limitations: [SafeLimitation]
evidence_manifest_ref: EvidenceRef
baseline_digest: sha256 digest
```

### 5.2. Общие evidence primitives

```yaml
EvidenceRef:
  kind: command_output | json_report | manifest | git_object | test_report |
        database_check | process_snapshot | scheduler_snapshot |
        external_receipt | review
  path_or_uri: repository-relative or opaque internal ref
  sha256: sha256 digest
  media_type: string
  bytes: integer >= 0
  classification: public | internal | confidential
  created_at: utc datetime

EvidenceStatus:
  VERIFIED | CONTRADICTORY | STALE | UNVERIFIABLE | NOT_APPLICABLE |
  NOT_CHECKED | FAILED
```

`SECRET` classification запрещена в evidence pack. Если проверка требует
секрета, сохраняется только факт наличия защищённой ссылки и безопасный digest
структуры, но не значение.

### 5.3. DocumentationEvidence

Обязательные поля:

```yaml
canonical_commit: full 40-character commit
head_commit: full 40-character commit
head_matches_canonical: boolean
required_documents:
  - path: repository-relative path
    git_blob: full object id
    sha256: digest of exact bytes
    status: EvidenceStatus
source_hierarchy_version: docs-readme blob id
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Required document set:

- `docs/README.md`;
- `docs/12-Эталон-MVP-1-и-дорожная-карта.md`;
- `docs/adr/0017-hybrid-natural-google-local-document-plane.md`;
- `docs/handoffs/CURRENT-STATUS.md`;
- `docs/handoffs/MVP-1-ISSUES.md`;
- `docs/handoffs/WORKSPACE-INVENTORY.md`;
- `docs/05-Спецификации-контрактов.md`;
- `docs/06-Регламент-качества-L1-L4.md`.

Отсутствие или несовпадение любого required blob блокирует Gate 0, пока
отклонение не классифицировано новым canonical base.

### 5.4. RepositoryEvidence и dirty manifest

```yaml
repo_ref: stable repository id
worktree_ref: opaque path ref
head_commit: full commit
branch_or_detached: string
upstream_ref: string | null
merge_bases:
  docs_to_repo: full commit | null
  docs_to_runtime_release: full commit | null
  repo_to_runtime_release: full commit | null
dirty:
  is_dirty: boolean
  entries:
    - path: repository-relative safe path
      status: git porcelain status
      tracked: boolean
      safe_content_sha256: digest | null
      content_omitted_reason: secret_like | binary | unreadable | not_needed | null
      owner: preexisting | gate0
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Правила:

- Gate 0 не требует искусственно чистого дерева, но MUST точно отделить
  pre-existing changes от Gate 0 files.
- Неидентифицированный dirty entry делает итог `UNVERIFIABLE`.
- Secret-like/untracked files не читаются ради digest.
- Gate 0 PASS допускает только явно принадлежащие Gate 0 изменения и
  зафиксированные pre-existing entries, которые не пересекаются с его зоной.
- Dirty manifest не является разрешением изменять чужой файл.

### 5.5. RuntimeReleaseEvidence

```yaml
runtime_worktree_ref: opaque path ref
runtime_head_commit: full commit
runtime_branch_or_detached: string
expected_feature_commit: full commit | null
expected_feature_is_ancestor: boolean | null
docs_commit_is_ancestor: boolean
release_artifact_ref: EvidenceRef | null
release_artifact_digest: digest | null
runtime_code_manifest_digest: digest | null
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Для исходной базы ожидается явное отражение, что docs commit `9d816...` и live
runtime layer различны. Это не автоматически `FAILED`, но смешивание полей
блокирует PASS.

### 5.6. ProcessEvidence

Для каждого ожидаемого Nobus process:

```yaml
process_role: telegram_runner | codex_app_server | bridge | helper
expected_count: integer >= 0
observed_count: integer >= 0
instances:
  - pid: integer
    parent_pid: integer | null
    started_at: utc datetime
    executable_ref: opaque normalized ref
    executable_sha256: digest
    executable_version: string | null
    argv_profile: closed safe profile
    argv_digest: digest
    working_directory_ref: opaque allowed ref
    identity_ref: opaque principal ref
    loaded_release_commit: full commit | null
    loaded_code_digest: digest | null
    config_digest: digest | null
    health: healthy | degraded | unhealthy | unknown
polling_checkpoint:
  observed_at: utc datetime | null
  age_seconds: integer | null
  source_ref: EvidenceRef | null
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Raw command line, environment и usernames не сохраняются. Вместо них
используются closed profile, allowlisted fields и digests.

Для owner Telegram runtime `observed_count != 1` блокирует соответствующий
CURRENT claim.

### 5.7. SchedulerEvidence

```yaml
scheduler_kind: windows_task_scheduler | systemd | other
task_ref: opaque stable ref
enabled: boolean
state: ready | running | disabled | unknown
action_executable_ref: opaque ref
action_executable_digest: digest
action_arguments_profile: closed safe profile
action_arguments_digest: digest | null
working_directory_ref: opaque ref
principal_ref: opaque ref
trigger_profile: closed bounded object
restart_policy_profile: closed bounded object
last_run_at: utc datetime | null
last_result_code: integer | null
next_run_at: utc datetime | null
definition_changed_at: utc datetime | null
definition_digest: digest
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Scheduler evidence собирается read-only. Exported XML допускается только после
санитизации и не должен содержать credentials.

Collector MUST NOT access raw Scheduler arguments when the active L4 boundary
forbids raw command-line reads. In that case `action_arguments_profile` MUST be
`not_read_forbidden`, `action_arguments_digest` MUST be `null`, the Scheduler
record MUST be `UNVERIFIABLE`, and `G0-04` remains blocked. `definition_digest`
then binds only an explicitly labelled safe definition projection that excludes
arguments; it MUST NOT be described as a digest of the complete Scheduler
definition. A digest is mandatory only when an authorized safe projection can be
obtained without reading forbidden raw values or expanding L4 authority.

For the 2026-07-29 evidence-closure capture, action-bound owner L4
`owner-authority:gate0-evidence-closure-2026-07-29` explicitly authorizes one
transient read of Scheduler `Action.Arguments` and process command lines only for
candidates first matched to the Scheduler-selected executable. Raw values remain
collector-memory-only; environment values are not read; secret-shaped candidates
are rejected; persisted evidence contains only a closed sanitized projection,
path-free digests, booleans and timestamps. This exception does not authorize
ambient process command-line reads and does not survive this capture.

#### 5.7.1. Legacy Windows Scheduler supervision limitation

The current Scheduler launcher can leave a detached Nobus runner after the task
returns to `ready`. Gate 0 therefore treats Scheduler state alone as insufficient
runtime evidence. The test-only maintenance helper classifies every runner
candidate by opaque identity and fails closed on any unapproved profile. Its
owner-authorized remediation path is bounded to an exact stable candidate set. It
opens creation-time-bound native handles for every root and descendant and
validates parent chronology before any termination. It must then prove
`candidate_count=0` plus a free production mutex after one termination.

This is maintenance evidence, not the durable supervision design. The current
launcher remains unchanged in Gate 0; WinSW/service-identity supervision and
bounded restart semantics belong to the runtime/deployment Gate.

The 2026-07-30 sanitized revalidation supersedes the earlier assumed runtime
worktree binding: CURRENT Scheduler action, runner and all four SQLite databases
are bound to the canonical candidate worktree. The separate `telegram-live`
isolation remains TARGET for the runtime/deployment Gate. Gate 0 neither migrates
runtime state nor changes Scheduler, launcher or credentials.

The single-start boundary is frozen before any live action. The pre-capture core
binds the canonical repository HEAD and branch, a sanitized Git-status digest,
the exact tracked repository closure (excluding `.nobus-quality` ledgers), and
every existing file below `ops`, `scripts`, `src` and `tests`. This makes
`scripts/run_telegram_mvp1.py`, `src/application/windows_singleton.py` and the
full pytest tree explicit immutable inputs.

Traversal is no-follow and reject-before-read. Every path component is checked
with link/reparse-aware metadata before content access; symlink, junction or
other reparse topology fails closed. Credential/secret names, SQLite database
files and their WAL/SHM companions, plus `.runtime` state are rejected before a
digest or dirty-manifest read. This rule applies to both tracked and discovered
inputs, so Git tracking cannot downgrade the security boundary. Content hashes
use atomic validated file handles: the opened device/inode/type, size and
modification marker must equal the pre-open `lstat` identity before the first
content read and remain stable through EOF. A path-to-reparse swap therefore
fails before external bytes can be consumed.

Readback recomputes those safe inputs and the Git identity/status without
writing. A changed, added or removed relevant file fails closed before Scheduler
start. Raw argv/env, absolute paths, credentials, database bytes and payloads
are not persisted.

The start helper then validates the exact whole ignored launcher against the
installer template, the exact Scheduler task/action/settings/principal/trigger
contract, and the canonical Python/runner/action artifact digests. It performs
identity comparison by the same resolved Windows SID, never by suffix or
substring. Scheduler arguments are parsed into a closed eight-token action
contract represented by a single-command AST without control tokens or
redirections. Representation-only case and whitespace normalization is
accepted; launcher quoting is optional but limited to a single matching outer
quote pair. An unresolved identity or any missing, changed or extra token fails
closed.
The internal start path requires all eight expected digests before its first
read. In one process it executes the fixed
`core/live/core/core/live/start` sequence. The two live
`ready / 0 candidates / mutex free` classifications must be stable, and all
three frozen core readbacks must equal the expected opaque digests. The final
live read occurs immediately before the single literal `Start-ScheduledTask`
call, so no frozen readback can leave stale live authority at the launch
boundary. Each live definition must also carry a strictly boolean true
`ActionIdContractExact`, derived from installer-equivalent empty `Action.Id`;
missing, non-boolean or false blocks even when all digests match. Mismatch or
error blocks without start or retry; a separate precheck
cannot authorize launch. A task-contract failure persists only a closed
20-field boolean task match bitmap. When `action_arguments=false`, it may also
emit one fixed 20-field structural action bitmap. Raw Scheduler values,
arguments and paths are never persisted; secret-shaped input stops before
parsing. Executable resolution has a separate stage.

#### 5.7.3. One-shot Scheduler action repair

The owner-authorized Gate 0 repair may replace only `Action.Arguments`. Before
mutation, two stable repair observations must be coherent across the task object
and exported XML and match the exact Inspect C bitmap, canonical shifted
`-File` target, approved PowerShell executable, canonical launcher,
installer-equivalent empty `Action.Id` and the complete non-argument task
contract. An exclusive named mutex prevents concurrent sanctioned repair
helpers. After constructing the in-memory replacement Action, a third final
coherent freshness observation must still equal the accepted authority
immediately before one literal `Set-ScheduledTask`. The repair never calls stop
or start.

An in-memory Scheduler XML projection replaces only the argument node with a
fixed sentinel and excludes volatile registration date metadata. Its opaque
non-argument definition digest must be stable before mutation and unchanged
after it. The postcondition requires every task and action contract predicate
to be true and the action executable and working directory to remain equal.
Any precondition, mutation or postcondition error stops without retry. Raw
Scheduler XML, arguments, identities and paths are never persisted.

Windows Task Scheduler exposes no OS-level compare-and-swap for task
definitions. The final read minimizes but cannot eliminate a concurrent write
from an unsanctioned external administrator in the interval before mutation.
Live repair therefore requires explicit owner acceptance of that residual
threat-model assumption.

### 5.8. DatabaseEvidence

Для каждой известной runtime DB:

```yaml
database_role: core | telegram_state | product_effects | checkpoint | legacy
database_ref: opaque allowlisted ref
source_profile: closed observed-location profile
runtime_binding_status: EvidenceStatus
runtime_binding_reason: closed reason code
engine: sqlite
file_identity_digest: digest
size_bytes: integer
modified_at: utc datetime
journal_mode: delete | wal | truncate | persist | memory | off | unknown
user_version: integer
application_id: integer
schema_digest: digest
migration_inventory:
  applied: [closed migration id]
  pending: [closed migration id]
  unknown: [string]
integrity:
  quick_check: ok | failed | not_checked
  foreign_key_check: ok | failed | not_applicable | not_checked
state_aggregates:
  pending: integer | null
  in_progress: integer | null
  waiting_human: integer | null
  failed: integer | null
  dead_letters: integer | null
  orphaned_leases: integer | null
  unreconciled_effects: integer | null
  undelivered_outbox: integer | null
content_exported: false
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Правила:

- проверки MUST быть read-only;
- таблицы и counts определяются schema-aware collector, а не догадкой;
- отсутствие ожидаемой таблицы или неизвестная migration — `CONTRADICTORY`;
- live DB hash не подменяет schema/state evidence и не вычисляется способом,
  создающим inconsistent WAL snapshot;
- payload, note text, Telegram text, file content и credentials не экспортируются;
- orphan/unreconciled значения не превращаются в ноль при ошибке чтения.
- найденный в candidate-worktree SQLite-файл не объявляется live runtime DB без отдельной проверяемой привязки runner→database; отсутствие такой привязки — `UNVERIFIABLE`.

Owner decision `owner-authority:gate0-evidence-closure-2026-07-29` принимает
текущую Telegram SQLite schema как **genesis baseline** только если один fresh
capture одновременно доказывает runner→DB binding, source-schema digest match,
WAL-aware consistent read transaction, `quick_check=ok` и пустой
`foreign_key_check`. Это не доказывает, что historical legacy migration когда-либо
исполнялась: historical application record остаётся `not_proven` и исключается из
genesis-forward lineage claim. Gate 2 MUST создать durable migration ledger,
привязанный к exact genesis schema digest, до первой post-genesis migration.
Любое mismatch/inconsistent snapshot/unknown post-genesis migration оставляет
`G0-05` в `CONTRADICTORY/BLOCKED`.

### 5.9. ConfigurationEvidence и registries

```yaml
config_schema_version: string
active_profile: closed profile
safe_config_digest: digest
secret_store:
  provider: windows_credential_manager | environment_ref | vault | other
  required_refs_present: boolean | null
  values_read: false
registries:
  source:
    schema_version: string
    digest: digest
    entries_count: integer
  output:
    schema_version: string
    digest: digest
    entries_count: integer
  deny:
    schema_version: string
    digest: digest
    entries_count: integer
  google_folders:
    schema_version: string | null
    digest: digest | null
    entries_count: integer | null
policy_digest: digest
model_profile_digest: digest
config_sources: [safe repository-relative or opaque ref]
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

До Gate 2 отсутствующий production registry фиксируется как TARGET gap, а не
заполняется вымышленным digest.
Если presence secret refs не разрешено проверять без чтения credential metadata, `required_refs_present` остаётся `null`; `false` допустимо только как доказанное отсутствие.

`deny` имеет приоритет над source/output. Модель не получает absolute owner
root, credentials или raw registry internals.

### 5.10. DependencyEvidence

```yaml
os:
  family: windows | linux
  version: string
  architecture: string
python:
  implementation: string
  version: string
  executable_digest: digest
pip:
  version: string
  inspect_schema_version: string
  inspect_report_ref: EvidenceRef
  inspect_report_digest: digest
requirements:
  files:
    - path: repository-relative path
      sha256: digest
  fully_pinned: boolean
pip_check:
  status: passed | failed | not_run
external_tools:
  - name: git | codex_cli | gitleaks | pip_audit | other
    version: string
    executable_digest: digest | null
vulnerability_report:
  tool: pip-audit
  version: string
  database_observed_at: utc datetime
  status: passed | findings | unavailable | not_run
  report_ref: EvidenceRef | null
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

`pip inspect` является authoritative installed inventory. `requirements.txt`
доказывает intent, но не фактически установленное environment.

### 5.11. TestEvidence

```yaml
test_contract_version: string
commit_under_test: full commit
environment_digest: digest
collection:
  files: integer
  collected_cases: integer
  collection_report_ref: EvidenceRef
runs:
  - profile: gate0_docs | gate0_contracts | full_regression |
             property | architecture | release_security
    command_profile: closed safe profile
    started_at: utc datetime
    finished_at: utc datetime
    exit_code: integer
    passed: integer | null
    failed: integer | null
    skipped: integer | null
    warnings: integer | null
    seed: string | null
    report_ref: EvidenceRef
    report_digest: digest
baseline_scores:
  current_system:
    corpus_version: string
    corpus_digest: digest
    report_ref: EvidenceRef
    pass_rate: decimal | null
status: EvidenceStatus
observed_at: utc datetime
evidence_refs: [EvidenceRef]
```

Количество test functions из source search не подменяет pytest collection.

Gate 0 фиксирует baseline score CURRENT, но не обязан заставить текущий parser
достичь TARGET Gate 1. Недостижение будущего target threshold является
измеренным gap, а не автоматическим провалом baseline capture.

### 5.12. ExternalCapabilityEvidence

```yaml
capability:
  telegram_polling | codex_sdk | web_search | google_calendar |
  google_tasks | google_drive | google_docs | google_sheets |
  local_owner_files | local_library_bridge_read_v1 |
  local_library_bridge_write_v2
implementation_status:
  current | partial | target | deferred
verification_status:
  verified_live | verified_fake | configured_not_called |
  unavailable | not_checked | unverifiable
mode:
  read_only | fake | metadata_only | not_applicable
provider_or_adapter_version: string | null
last_success_at: utc datetime | null
fresh_evidence_at: utc datetime | null
safe_summary: string
limitations: [string]
status: EvidenceStatus
evidence_refs: [EvidenceRef]
```

`configured_not_called` не равен `verified_live`. Gate 0 не выполняет внешнюю
запись ради health check.

### 5.13. CapabilityClaim

Каждое утверждение CURRENT/TARGET MUST быть отдельной записью:

```yaml
claim_id: stable string
capability: stable string
implementation_status: CURRENT | PARTIAL | TARGET | DEFERRED
statement: bounded safe text
requires_layers: [documentation, repository, runtime_release, process,
                  scheduler, database, configuration, dependencies, tests,
                  external_capabilities]
evidence_refs: [EvidenceRef]
contradictions: [EvidenceRef]
fresh_until: utc datetime | null
verdict: VERIFIED | CONTRADICTORY | STALE | UNVERIFIABLE
```

CURRENT разрешён только при `verdict=VERIFIED`.

### 5.14. Freshness и invalidation

Default freshness:

| Evidence | Freshness |
|---|---:|
| process count, loaded release, polling checkpoint | 5 минут |
| Scheduler definition/state | 15 минут |
| DB integrity и state aggregates | 15 минут |
| config/registry digests | 24 часа при неизменном file identity |
| dependency inventory и `pip check` | 24 часа |
| full test run | 24 часа |
| external read-only capability health | 60 минут |
| immutable Git blob/commit | без TTL, пока hash тот же |

Evidence инвалидируется раньше TTL при:

- изменении commit, dirty manifest или artifact digest;
- restart процесса;
- изменении Scheduler definition;
- DB migration/schema change;
- config/registry/requirements/environment change;
- изменении corpus, fixtures, expected outputs или verifier policy;
- rework результата.

Если часы host нельзя считать доверенными, baseline становится
`UNVERIFIABLE`.

## 6. Product Contract freeze

### 6.1. Замораживаемые продуктовые положения

Gate 0 MUST зафиксировать:

- owner-bound Telegram MVP-1 и его границы;
- Natural Language First;
- text и подтверждённый voice как семантически равные owner inputs;
- slash-команды только как operational fallback;
- один понятный clarification вместо угадывания;
- домены `notes`, `calendar`, `tasks`, `documents`, `research`, `general`;
- общий Google/local document lifecycle;
- закрытые actions, requested outputs и proposed effects;
- Core как владелец policy, state, risk и idempotency;
- application-owned effects;
- отсутствие ambient model OAuth/shell/filesystem authority;
- tenant/project/client binding;
- metadata-first search и exact selection;
- revision/digest-bound read/update;
- unknown outcome → reconciliation/escalation, не blind retry;
- `deny wins`;
- L1/L2/L3 и action-bound L4;
- CURRENT/TARGET/evidence semantics.

### 6.2. Contract catalog freeze

Gate 0 фиксирует назначение, schema ID, producer, consumer, trust boundary,
обязательные поля, closed enums, invariants и golden examples:

- текущих `TrustedIngressEnvelope`, `TaskContract`, `WorkerEvent`,
  `VerificationBundle`, approval/effect records;
- TARGET `nobus.intent.v1`;
- TARGET `nobus.document_ref.v1`;
- TARGET `DocumentQuery`;
- TARGET `DocumentReadPlan`;
- TARGET `AnalysisRequest`;
- TARGET `ArtifactPlan`;
- TARGET `DocumentWritePlan`.

Gate 0 MUST NOT создавать вторую production-модель этих контрактов.
Pydantic-реализация и migrations принадлежат Gate 2.

### 6.3. Change control

После accepted Gate 0:

- typo/source metadata без изменения expected semantics → patch corpus revision;
- новые совместимые cases → minor corpus revision;
- изменение domain/action/effect/error semantics, trust boundary или expected
  outcome → major Product Contract/corpus revision;
- удаление case заменяется tombstone/deprecation, не бесследным удалением;
- любое incompatible contract change требует impact analysis, Gate 1–8
  consumer map, L1/L2/L3 и при необходимости ADR;
- изменение authority, external action, data retention, cost или production
  behavior требует владельца/L4;
- один bug или success case не меняет contract автоматически.

## 7. Канонический natural request corpus

### 7.1. Размер и taxonomy

Минимум — 80 cases. Нормативный стартовый target — **96 cases**:

| Категория | Cases |
|---|---:|
| Business Notes | 8 |
| Calendar | 12 |
| Tasks | 12 |
| Documents: Google/local lifecycle | 24 |
| Analytics/research/general | 12 |
| Voice/text/context/clarification | 12 |
| Security/effect/tenant/provider/adversarial | 16 |
| **Итого** | **96** |

Дополнительные coverage requirements:

- минимум 30 negative/adversarial cases;
- минимум 16 paired text/voice transcripts;
- минимум 12 multi-turn/context/clarification cases;
- Google и local представлены в search/select/read/analyze/create/update/deliver;
- create/update/delete/share/money/third-party delivery различаются;
- provider unavailable, Bridge offline и unknown write outcome представлены;
- cross-tenant/project/client, prompt injection, replay, secret-path, traversal,
  reparse и stale revision представлены.

Один case может иметь несколько tags, но не используется для искусственного
выполнения количественных квот двух первичных категорий одновременно.

### 7.2. Corpus case schema

```yaml
schema: nobus.gate0.corpus_case.v1
corpus_version: semver
case_id: immutable stable id
status: active | deprecated | tombstone
locale: ru-RU
source_kind: synthetic | sanitized_pattern
modality: text | voice_transcript
pair_ref: case_id | null
turns:
  - turn: integer >= 1
    speaker: owner | system_context
    text: bounded synthetic/sanitized text
    trusted_context_ref: synthetic stable ref | null
expected:
  intent:
    schema: nobus.intent.v1
    domain: closed enum
    action: closed enum
    entities: closed bounded object
    period: normalized object | null
    source_scope: bounded references
    requested_outputs: [closed enum]
    proposed_effects: [closed enum]
    ambiguity: none | clarify | reject
  decision: accept | clarify | reject | require_l4 | degraded
  effects:
    - kind: closed effect kind
      execution: forbidden | proposed | allowed_after_l4
  errors:
    - code: stable safe error code
      required: boolean
  user_message_profile: stable profile
forbidden:
  domains: [closed enum]
  actions: [closed enum]
  effects: [closed enum]
  data_exposure: [secret | raw_path | cross_tenant | raw_prompt | raw_document]
assertions: [stable assertion id]
tags: [closed tag]
ownership:
  product_owner: stable role ref
  curator: stable role ref
  security_reviewer: stable role ref | null
provenance:
  created_from: canonical_requirement | incident_pattern | synthetic_boundary
  source_refs: [repository-relative document/issue ref]
  created_at: utc datetime
  reviewed_at: utc datetime
```

### 7.3. Data policy

Corpus MUST:

- использовать только synthetic или необратимо sanitized patterns;
- не содержать реальные owner/client names, chat IDs, file IDs, task IDs,
  document text, paths с персональными сегментами или business figures;
- не содержать audio владельца;
- представлять voice как synthetic transcript и paired semantic case;
- не содержать secrets, tokens, credentials, cookies или auth headers;
- проходить deterministic secret/PII/path scan;
- храниться в Git только после L1/L2/L3.

Real production failure может породить новый case только после ручной
минимизации и sanitization; raw payload не прикладывается.

### 7.4. Versioning и digest

- JSONL: UTF-8, LF, одна canonical JSON запись на строку;
- cases сортируются по `case_id`;
- ключи canonical JSON сортируются существующим algorithm;
- `corpus_digest` вычисляется по точным canonical lines;
- expected semantic change создаёт новую corpus revision;
- rework инвалидирует score/evidence предыдущего digest;
- baseline report всегда хранит `corpus_version` и `corpus_digest`.

Exact-byte artifacts MUST оставаться LF после Git clean/smudge при
`core.autocrlf=true`. Repository policy MUST быть узко ограничена только
`docs/gates/gate-00-product-contract-baseline/**`, `tests/gate0/**` и самой
`.gitattributes`; глобальный `* text eol=lf` запрещён. L1 обязан проверять
`git check-attr` positive/negative cases и clean-checkout manifest readback.

### 7.5. Ownership

- Product Owner утверждает product semantics и authority changes.
- Gate 0 curator отвечает за schema, coverage и provenance.
- Security reviewer владеет adversarial/tenant/effect expected decisions.
- Gate 1 является первым runtime consumer intent cases.
- Gate 2 владеет production schema compatibility.
- Gate 3–7 добавляют domain cases через change control.
- Gate 8 не может менять expected results для прохождения release.

## 8. Contracts, fixtures и golden outputs

### 8.1. Fixture classes

Обязательны:

- valid contract JSON;
- invalid unknown field;
- invalid/unknown enum;
- `bool` вместо integer;
- naive datetime;
- cross-tenant/task/project/client;
- duplicate/replayed idempotency;
- stale revision/digest;
- secret-like nested field;
- oversized/deep payload;
- Unicode normalization boundaries;
- ambiguous selection;
- provider unavailable;
- unknown effect outcome;
- Bridge offline;
- forbidden path/reparse/deny;
- prompt injection inside untrusted document.

### 8.2. Golden outputs

Golden outputs включают:

- canonical JSON;
- canonical digest;
- Pydantic-generated validation JSON Schema;
- independent jsonschema validation result;
- normalized expected intent;
- expected effect proposal/decision/error;
- sanitized user-message profile;
- baseline score summary.

Golden не включает модельную формулировку целиком, если продукту важен смысл,
а не точный текст. Exact-string golden допускается только для stable error или
transport profile.

### 8.3. Evaluation order

1. size/encoding/duplicate-key checks;
2. corpus JSON Schema;
3. Pydantic validation;
4. independent python-jsonschema validation;
5. deterministic expected intent/effect/error assertions;
6. property tests;
7. CURRENT baseline run;
8. optional future model/prompt evaluation consumer.

Model judge не может отменить failure уровней 1–6.

## 9. Architecture fitness functions

### 9.1. Gate 0 enforced boundaries

Минимальные declarative contracts:

1. `src.contracts` MUST NOT import `application`, `integrations`, `transport`,
   `storage`, `workers`, `voice`, FastAPI или LangGraph.
2. `src.core` MAY import contracts/stdlib, но MUST NOT import Telegram, Google,
   owner filesystem, worker SDK или renderer.
3. `src.integrations.google_*` MUST NOT import Telegram transport, local owner
   path implementation или credentials values.
4. Worker/model modules MUST NOT execute Google/local/Telegram effects directly;
   effect execution остаётся application-owned.
5. Gate 0 dev tools MUST NOT появляться в production imports.
6. Corpus/tests/docs MUST NOT содержать secret-like payload или real owner/client
   data.

### 9.2. Progressive boundaries

Следующие rules фиксируются сейчас, но активируются соответствующим Gate:

- Gate 2: один production class на canonical contract/schema version;
- Gate 3: provider gateways не владеют policy/state;
- Gate 5: Bridge не импортирует Telegram/Google credentials и не публикует shell;
- Gate 6: formulas/facts отделены от narrative generation;
- Gate 7: renderers не выполняют destination effect;
- Gate 8: observability exporter не получает prohibited raw fields.

Если CURRENT нарушает future rule, Gate 0 записывает measured debt и owner Gate,
но не переписывает код в baseline-фазе.

### 9.3. Enforcement

- Import Linter — основной dev-only engine.
- Малые data/secret rules могут быть pytest checks.
- Не создаётся собственный AST/import framework.
- Любой waiver имеет rule ID, exact path, owner Gate, expiry и rationale.
- Бессрочный wildcard waiver запрещён.

## 10. Minimal toolchain

### 10.1. Source of truth

- Pydantic `2.13.4`;
- pytest `9.1.1`;
- stdlib `json`, `hashlib`, `pathlib`, `platform`, `importlib.metadata`;
- `pip inspect`.

### 10.2. Dev-only

Зафиксированные exact pins из изолированного L4 verifier 29 июля 2026:

- python-jsonschema `4.26.0`;
- Hypothesis `6.163.0`;
- Import Linter `2.13`.

Они не импортируются production package и не запускаются в live runtime.
Воспроизводимый verifier создаётся только в одном owner-authorized
`C:\\tmp\\nobus-gate0-verifiers-<uuid>`, использует Python `3.12.10` и pip
`26.1.2`, устанавливает 39 wheel artifacts через `--require-hashes
--only-binary=:all:` и не изменяет canonical `.venv`.

### 10.3. Release checks

- `pip check`;
- pip-audit `2.10.1`, report-only, без auto-fix;
- Gitleaks `8.30.1`, exact binary/version/digest pin;
- full pytest;
- schema/corpus/architecture checks;
- `git diff --check`;
- manifest/secret/link validation.

Gitleaks `scanned_file_count` must equal the exact immutable
`pre-capture-core.input_entries` count. The self-referential receipt files are
not copied into the scanner tree; instead, their exact bytes are bound by
`receipt_entries` and `frozen_tree_digest`. After receipt bind, targeted Gate 0
and full pytest suites run again against the final materialized tree. Their
post-bind success is required before independent L1/L2/L3 and before Scheduler
start; any failure invalidates the freeze.

Network failure pip-audit даёт `UNVERIFIABLE`, а не успешный audit. Release
policy решает, блокирует ли недоступная advisory DB конкретный internal Gate;
production release без свежего vulnerability evidence запрещён.

### 10.4. CI order

```text
structure/link/encoding
→ secret and forbidden-data scan
→ schema/fixture validation
→ deterministic corpus tests
→ property tests
→ architecture fitness
→ targeted current regressions
→ full pytest
→ pip inspect + pip check
→ pip-audit + Gitleaks
→ manifest digest
→ independent L2
→ adversarial L3
```

CI jobs MUST use exact tool versions. `latest` tags и runtime install с
unbounded lifecycle scripts запрещены в accepted evidence.

## 11. Criteria for future tools

### 11.1. Promptfoo

Разрешён только когда одновременно:

1. canonical corpus имеет минимум 80 accepted cases;
2. deterministic harness стабилен;
3. существует bounded Nobus endpoint или sanitized export;
4. Promptfoo не становится source of truth;
5. exact version/Node runtime pinned;
6. telemetry/update checks disabled;
7. untrusted config execution запрещено;
8. credentials отсутствуют в config/UI/export;
9. data retention и provider cost утверждены;
10. pilot доказывает измеримую пользу: найденные регрессии или удалённый custom
    eval code.

MCP server Promptfoo не подключается к production runtime.

### 11.2. OpenTelemetry

SDK вводится, когда:

- существует server path;
- принят stable sanitized event field contract;
- запрещённые raw fields покрыты tests;
- утверждены sampling, exporter allowlist и retention;
- проверены volume/cost и failure behavior;
- отсутствие collector не ломает product path.

Gate 0 фиксирует только внутренние поля:

- tenant pseudonymous ref;
- task/attempt/span/effect IDs;
- contract/result/corpus/config/registry digests;
- stage/status/error code;
- duration/queue depth/retry/reconcile;
- provider/model/version/usage/cost;
- exact release commit.

Запрещены raw owner text, prompt, output, audio, document content/path,
credentials, headers, tokens и cookies.

### 11.3. Langfuse

Langfuse рассматривается не раньше Gate 8, когда:

- OTel/internal event contract стабилен;
- выбран Cloud или self-host;
- приняты auth, tenant isolation, encryption, backup/restore и RPO/RTO;
- retention реализована, а не только обещана;
- стоимость и operational ownership назначены;
- удаление backend не требует переписывать Nobus contracts.

Fallback: sanitized structured logs/metrics и OTel-compatible exporter без
Langfuse.

## 12. Gate 0 artifacts и directory layout

После реализации directory должен иметь:

```text
docs/gates/gate-00-product-contract-baseline/
├── RESEARCH.md
├── ARCHITECTURE.md
├── HANDOFF.md
├── decisions/
│   └── decision-register.json
├── schemas/
│   ├── baseline-evidence.schema.json
│   ├── capability-claim.schema.json
│   ├── product-contract.schema.json
│   ├── corpus-case.schema.json
│   └── gate-handoff.schema.json
├── product/
│   └── product-contract.json
├── corpus/
│   ├── requests.v1.jsonl
│   ├── coverage.json
│   └── corpus-manifest.json
├── fixtures/
│   ├── contracts/valid/
│   ├── contracts/invalid/
│   └── golden/
├── evidence/
│   ├── baseline-evidence.json
│   ├── dirty-manifest.json
│   ├── dependency-inventory.json
│   ├── test-inventory.json
│   ├── external-capabilities.json
│   └── evidence-manifest.json
└── verification/
    ├── l1.json
    ├── l2.json
    └── l3.json
```

Test/collector implementation, если потребуется:

```text
tests/gate0/
├── test_baseline_schema.py
├── test_corpus_schema.py
├── test_corpus_coverage.py
├── test_contract_golden.py
├── test_contract_properties.py
├── test_architecture_boundaries.py
└── test_gate0_documentation.py

scripts/gate0/
├── collect_baseline.py
└── validate_gate0.py
```

Это impact map, а не разрешение создавать все файлы одним change-set.

### 12.1. Evidence manifest

`evidence-manifest.json` MUST перечислять каждый Gate 0 artifact:

```yaml
schema: nobus.gate0.evidence_manifest.v1
gate: 0
base_commit: full commit
result_commit: full commit | null before commit
result_tree_digest: digest
entries:
  - path: repository-relative
    role: research | architecture | schema | product_contract | corpus |
          fixture | evidence | verification | handoff
    media_type: string
    bytes: integer
    sha256: digest
    classification: public | internal | confidential
created_at: utc datetime
tool_versions: closed object
limitations: [safe string]
manifest_digest: digest
```

Manifest не перечисляет secrets/runtime databases как copied artifacts. Для
них остаются sanitized evidence refs.

## 13. Gate 1–8 interface и handoff

| Gate | Обязательные входы Gate 0 | Что нельзя считать выполненным заранее |
|---|---|---|
| 1 Intent/Voice | corpus version/digest, intent vocabulary, ambiguity/effect rules, baseline score | parser/prompt/confidence/context implementation |
| 2 Contracts/Registries | contract catalog, schema/golden fixtures, registry semantics, fitness rules | production models, migrations, registry data |
| 3 Google/Gemini | provider/data policy, external capability baseline, event fields | model/provider selection, cost cap, adapter implementation |
| 4 Notes/Calendar/Tasks | domain cases, authority and idempotency rules | end-to-end effects |
| 5 Documents/Bridge | lifecycle, deny/source/output semantics, path/adversarial cases | Bridge protocol/auth/indexer/parser |
| 6 Analytics | AnalysisRequest semantics, provenance rules, calculation cases | formulas, datasets, calibrated quality metrics |
| 7 Artifacts/Writeback | Artifact/WritePlan semantics, revision/digest/collision rules | renderers, Google/local writeback |
| 8 Release/Pilot | Baseline schema, manifest, SLO candidates, evidence/freshness rules | deployment, retention backend, 72-hour pilot |

Каждый consumer MUST ссылаться на exact Product Contract и corpus digest.

Gate handoff принимает:

- Gate number/name;
- exact base/result commit;
- artifact manifest;
- CURRENT before/after;
- TARGET remaining;
- applied contract/corpus versions;
- L1/L2/L3 evidence;
- migrations/backups/external effects;
- L4, если применим;
- unresolved risks;
- exact inputs следующего Gate;
- `READY` или `BLOCKED`.

## 14. Code/test impact map

Gate 0 design не требует изменений кода. Реализация должна оценить:

| Path | Будущий impact | Gate owner |
|---|---|---|
| `src/contracts/models.py` | Переиспользовать canonical digest/base model; production hybrid models не добавлять раньше Gate 2 | 2 |
| `src/core/policy.py` | Сверить authority/effect/tenant invariants | 2 |
| `src/orchestrator/intent_parser.py` | Только CURRENT baseline against corpus | 1 |
| `src/application/durable_runtime.py` | Снять state/retry evidence, не менять в Gate 0 | 8 |
| `src/application/product_effects.py` | Сверить effect taxonomy/idempotency | 2/4/7 |
| `src/application/owner_files.py` | Переиспользовать path/security cases | 5 |
| `src/application/owner_workspace.py` | Переиспользовать snapshot/CAS/golden cases | 7 |
| `src/application/runtime_maintenance.py` | Переиспользовать read-only DB checks | 0/8 |
| `src/integrations/google_*` | Снять capability/behavior inventory | 3–5 |
| `src/storage/sqlite_store.py` | Снять schema/migration/state evidence | 0/2/8 |
| `src/transport/telegram/*` | Снять owner ingress/polling evidence | 0/1/8 |
| `scripts/check_telegram_health.py` | Кандидат на bounded evidence primitive | 0/8 |
| `ops/windows/Install-NobusSpaceBot.ps1` | Source для Scheduler expected contract | 0/8 |
| `tests/test_contracts.py` | Reuse digest/round-trip golden tests | 0/2 |
| `tests/test_documentation.py` | Расширить structure/link/status checks | 0 |
| `tests/test_runtime_operations.py` | Reuse manifest/DB safety cases | 0/8 |
| `tests/test_*google*` | Reuse adapter/adversarial cases | 3–5 |
| `tests/test_owner_*` | Reuse local file/update safety cases | 5/7 |
| `tests/test_product_effect*` | Reuse effect/recovery cases | 2/4/7 |

Gate 0 implementation MUST NOT переносить существующие tests в новый framework.

## 15. Failure modes и required behavior

| Failure | Detection | Required outcome |
|---|---|---|
| Stale evidence | TTL/invalidation mismatch | `STALE`, affected CURRENT removed |
| Docs/runtime split | lineage/process artifact comparison | Separate layers; `CONTRADICTORY` if claims mixed |
| Dirty tree | porcelain + ownership manifest | Preserve pre-existing; unidentified entry blocks |
| Runtime commit cannot be proved | process artifact lacks provenance | `UNVERIFIABLE`, not guessed |
| Scheduler/process disagreement | expected action vs loaded process | capability `CONTRADICTORY` |
| DB unreadable/migration unknown | schema-aware read-only check | `UNVERIFIABLE` or `FAILED`, never zero counts |
| Secret leakage | deterministic scan/classification | reject artifact and rotate/escalate outside Gate |
| Real owner/client corpus | provenance/data scan | reject case; sanitize from source separately |
| Flaky/property nondeterminism | repeat/seed/minimal example | save reproducer; no PASS on non-reproduction |
| Provider unavailable | external capability record | `DEGRADED/UNAVAILABLE`; local checks continue |
| LLM grader disagrees | deterministic oracle order | deterministic verdict wins |
| Promptfoo/tool unavailable | adapter isolation | canonical pytest remains operable |
| Tool version drift | dependency/tool manifest | evidence invalidated |
| Gate 1–8 contract drift | digest/handoff comparison | consuming Gate BLOCKED until reconciliation |
| False PASS | missing mandatory artifact/level | Gate status `BLOCKED` |

## 16. Implementation slices

Каждый slice — отдельная ревизия результата с L1/L2/L3.

### Slice 0 — Scope and preflight

- подтвердить base commit;
- перечитать required docs;
- зафиксировать pre-existing dirty manifest;
- проверить разрешения задачи;
- не выполнять runtime/external action без отдельного scope.

**Exit:** exact task contract и file ownership.

### Slice 1 — Schemas and manifests

- создать JSON Schemas baseline, claim, Product Contract, corpus и handoff;
- зафиксировать canonical JSON/digest rules;
- добавить schema/golden tests.

**Exit:** schemas проходят Pydantic/jsonschema agreement и negative fixtures.

### Slice 2 — Product Contract

- сформировать machine-readable Product Contract;
- зафиксировать vocabularies, authority, trust boundaries и Gate ownership;
- сверить с docs 05/06/12 и ADR 0017.

**Exit:** нет противоречий или они явно `BLOCKED`.

### Slice 3 — Corpus

- создать 96 synthetic/sanitized cases;
- проверить taxonomy/coverage;
- провести product и security review expected decisions;
- сформировать corpus digest.

**Exit:** coverage и data policy PASS.

### Slice 4 — Baseline collector

- переиспользовать stdlib, Git, `pip inspect`, existing runtime maintenance;
- собирать только read-only/sanitized evidence;
- поддержать explicit `UNVERIFIABLE`;
- исключить secret/raw payload access.

**Exit:** deterministic fixture baseline и negative collector tests PASS.

### Slice 5 — Fresh live baseline

- после точного разрешения снять repo/runtime/process/Scheduler/DB/config/
  dependency/test/external capability evidence;
- связать layers и claims;
- не исправлять найденные runtime проблемы внутри capture.

**Exit:** complete evidence pack или `BLOCKED` с точным gap.

### Slice 6 — Evaluation and fitness

- запустить corpus baseline CURRENT;
- property tests;
- Import Linter rules;
- сохранить scores/debt без переписывания Gate 1–8.

**Exit:** reproducible reports with exact digests.

### Slice 7 — Verification and handoff

- L1 deterministic;
- L2 independent reproduction from exact inputs;
- L3 adversarial audit;
- manifest review;
- создать handoff.

**Exit:** `GATE 0 READY` либо `BLOCKED`; только владелец/root integration может
принять handoff и обновить канон.

## 17. Acceptance matrix

| ID | Criterion | Evidence | Blocking |
|---|---|---|---|
| G0-01 | Base commit и required blobs exact | DocumentationEvidence | Да |
| G0-02 | Repo/docs/runtime/process commits не смешаны | Layer/lineage report | Да |
| G0-03 | Dirty manifest полный и ownership определён | RepositoryEvidence | Да |
| G0-04 | Process/Scheduler evidence свежий | Process/Scheduler records | Да для CURRENT runtime |
| G0-05 | DB schema/migrations/integrity/state aggregates проверяемы | DatabaseEvidence | Да |
| G0-06 | Config/registry digests есть либо gap честно TARGET | ConfigurationEvidence | Да |
| G0-07 | Installed dependencies зафиксированы `pip inspect` | DependencyEvidence | Да |
| G0-08 | pytest collection и full result привязаны к environment | TestEvidence | Да |
| G0-09 | External capabilities имеют отдельный status/freshness | ExternalCapabilityEvidence | Да |
| G0-10 | Product Contract machine-readable и непротиворечив | Contract + L2 review | Да |
| G0-11 | Corpus ≥80; target 96 и coverage выполнен | Corpus manifest/coverage | Да |
| G0-12 | Нет real owner/client payload и secrets | Data/secret scan | Да |
| G0-13 | Positive/negative/adversarial expected decisions reviewed | Fixtures + reviews | Да |
| G0-14 | Pydantic/jsonschema/golden agreement | Contract reports | Да |
| G0-15 | Property tests reproducible | Seed/minimal examples | Да |
| G0-16 | Architecture fitness и waivers recorded | Import report | Да |
| G0-17 | CURRENT baseline score сохранён без false target PASS | Score report | Да |
| G0-18 | Evidence manifest полон и hashes совпадают | Manifest validation | Да |
| G0-19 | L1/L2/L3 независимы и относятся к одной revision | Verification records | Да |
| G0-20 | Handoff содержит точные входы Gate 1–8 | HANDOFF | Да |
| G0-21 | Нет runtime/external mutation вне отдельного L4 | Action audit | Да |
| G0-22 | Документ не объявляет Gate 0 PASS до evidence | Status check | Да |

## 18. L1, L2 и L3

### 18.1. L1 — deterministic

Обязательно:

- required files/schema fields;
- JSON/JSONL parse, encoding, LF и duplicate-key checks;
- schema validation;
- corpus counts/coverage/unique IDs/pairs;
- canonical digest/golden comparisons;
- link validation;
- secret/PII/path-pattern scan;
- Git diff/status/manifest check;
- tool/version/dependency inventory;
- architecture import rules;
- no prohibited file changes;
- exact artifact hashes.

### 18.2. L2 — independent reproduction

Независимый verifier:

- собирает baseline другим процессом или из raw command evidence;
- пересчитывает artifact/corpus/manifest digests;
- сравнивает code map с actual imports/requirements/tests;
- проверяет Product Contract по docs 05/06/12 и ADR 0017;
- повторяет corpus schema/coverage без использования итоговой сводки автора;
- сверяет primary source versions/licenses для добавляемых dependencies.

### 18.3. L3 — adversarial

Аудитор обязан атаковать:

- stale baseline;
- contradictory docs/repo/runtime commits;
- process без доказанного loaded code;
- pre-existing dirty changes, ошибочно приписанные Gate 0;
- unsafe или деанонимизируемый corpus;
- secret leakage через errors, command lines, env, paths и reports;
- false PASS при `NOT_CHECKED`/`UNVERIFIABLE`;
- flaky/property randomness;
- provider/network dependence;
- Promptfoo/OTel/Langfuse lock-in;
- model judge override;
- Gate 1–8 scope drift;
- waiver без owner/expiry;
- изменение TARGET, выданное за CURRENT.

L3 PASS не заменяет L1/L2.

## 19. Definition of Done

Gate 0 считается реализованным только когда:

1. все artifacts раздела 12 существуют и входят в manifest;
2. evidence pack относится к свежему exact environment;
3. Product Contract и corpus приняты на одной revision;
4. минимум 80 cases есть, target 96 и все coverage requirements выполнены;
5. real owner/client payload отсутствует;
6. baseline claims не смешивают docs/repo/runtime/process/DB/config;
7. все mandatory acceptance IDs PASS;
8. L1/L2/L3 имеют независимые evidence;
9. все contradictions reconciled либо Gate имеет `BLOCKED`;
10. создан Gate handoff с exact inputs Gate 1;
11. root integration/владелец явно принимает handoff;
12. только после этого статус может быть изменён на PASS в каноническом
    integration change-set.

Текущая ФАЗА 2 выполняет только TARGET design и поэтому не удовлетворяет этим
условиям автоматически.

## 20. Открытые решения владельца

Они не блокируют `ARCHITECTURE READY`, потому что до решения применяются
безопасные defaults:

| Решение | Safe default | Нужен ответ до |
|---|---|---|
| Может ли raw owner/client content уходить в eval/trace service | Нет | Promptfoo/OTel/Langfuse pilot |
| Retention sanitized operational events | 30 дней; raw content не сохраняется | Gate 8 |
| Budget model-graded evals | 0 в Gate 0; отдельный cap | Gate 3/6 |
| Offline Bridge / unknown write outcome | bounded wait → `DEGRADED`; no blind retry | Gate 5 |

Изменение safe default, влияющее на данные, стоимость или внешние действия,
требует явного решения владельца.

## 21. Статус этого design

Этот документ может получить статус `ARCHITECTURE READY` после:

- L1 structure/link/secret checks;
- L2 сверки с [`RESEARCH.md`](RESEARCH.md), exact canonical docs и CURRENT code;
- L3 аудита stale/contradictory/unsafe/false-PASS/tool-lock-in/Gate-drift;
- подтверждения, что изменены только два разрешённых файла.

`ARCHITECTURE READY` означает готовность design к реализации. Это не `Gate 0
PASS` и не разрешение следующего Gate.
